"""Full behavioral coverage of BlenderExportDialog under rich Qt stand-ins.

conftest.py's blanket MagicMock finder makes QDialog un-subclassable, so the
normal test files can only smoke-test dialog.py at the import level (7%
coverage). This file installs genuine pure-Python PyQt6 stand-ins
(dialog_qt_stubs.py) for the exact duration of the module, imports dialog.py
fresh under them, and drives the dialog's real methods so the branch logic
actually executes. The fixture restores every sys.modules mutation so the
rest of the suite (which relies on the MagicMock mocks) is unaffected.
"""

import importlib
import os
import sys
import tempfile

import pytest

import dialog_qt_stubs
from conftest import make_benzene_like, make_context, make_ethanol_like

_PYQT_MODULES = ("PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets")


@pytest.fixture
def dlg_mod():
    """(Re-)import blender_export_pro.dialog under the rich Qt stand-ins."""
    snapshot = {name: sys.modules.get(name) for name in _PYQT_MODULES}
    old_dialog = sys.modules.pop("blender_export_pro.dialog", None)
    dialog_qt_stubs.install()
    try:
        mod = importlib.import_module("blender_export_pro.dialog")
        yield mod
    finally:
        sys.modules.pop("blender_export_pro.dialog", None)
        dialog_qt_stubs.remove()
        for name, value in snapshot.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        if old_dialog is not None:
            sys.modules["blender_export_pro.dialog"] = old_dialog
        dialog_qt_stubs.QMessageBox.reset()


def _make_dialog(dlg_mod, ctx=None, cfg=None):
    from blender_export_pro.style_config import StyleConfig

    ctx = ctx or make_context()
    cfg = cfg if cfg is not None else StyleConfig()
    return dlg_mod.BlenderExportDialog(None, ctx, cfg), ctx, cfg


# --------------------------------------------------------------- construction


def test_dialog_builds_all_tabs(dlg_mod):
    dlg, _ctx, _cfg = _make_dialog(dlg_mod)
    labels = [label for _widget, label in dlg._tabs._tabs]
    assert labels == [
        "Atoms", "Bonds", "Rings", "Deformation", "Material",
        "Labels", "Scene", "Export Options", "Preset Files",
    ]


def test_toggle_advanced_shows_and_hides_scroll(dlg_mod):
    dlg, _ctx, _cfg = _make_dialog(dlg_mod)
    dlg.advanced_toggle.setChecked(True)
    assert dlg._scroll.isVisible() is True
    assert "▾" in dlg.advanced_toggle.text()
    dlg.advanced_toggle.setChecked(False)
    assert dlg._scroll.isVisible() is False
    assert "▸" in dlg.advanced_toggle.text()


def test_refresh_widgets_and_pull_config_round_trip(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dlg.atom_shape.setCurrentIndex(dlg.atom_shape.findText("ico_sphere"))
    dlg.hide_hydrogens.setChecked(True)
    dlg.bond_radius.setValue(0.5)
    dlg.collection_name.setText("Foo")
    dlg._pull_config()
    assert cfg.atom_shape == "ico_sphere"
    assert cfg.hide_hydrogens is True
    assert cfg.bond_radius == pytest.approx(0.5)
    assert cfg.collection_name == "Foo"


def test_on_setting_changed_pulls_config_and_marks_touched(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    assert cfg.is_touched() is False
    dlg.hide_hydrogens.setChecked(True)  # toggled -> _on_setting_changed
    assert cfg.hide_hydrogens is True
    assert cfg.is_touched() is True


def test_on_setting_changed_noop_while_loading(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dlg._loading = True
    cfg.hide_hydrogens = False
    dlg.hide_hydrogens._checked = True  # bypass setChecked's own emit path
    dlg._on_setting_changed()
    assert cfg.hide_hydrogens is False  # not pulled while loading
    dlg._loading = False


def test_refresh_preview_if_active_refreshes_when_style_active(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    v3d = ctx.get_main_window.return_value.view_3d_manager
    from blender_export_pro.style_config import STYLE_NAME
    v3d.current_3d_style = STYLE_NAME
    dlg._refresh_preview_if_active()
    ctx.refresh_3d_view.assert_called()


def test_refresh_preview_if_active_swallows_exception(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    v3d = ctx.get_main_window.return_value.view_3d_manager
    from blender_export_pro.style_config import STYLE_NAME
    v3d.current_3d_style = STYLE_NAME
    ctx.refresh_3d_view.side_effect = RuntimeError("boom")
    dlg._refresh_preview_if_active()  # must not raise


# --------------------------------------------------------------- browse hooks


def test_browse_hdri_sets_path_and_mode(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dialog_qt_stubs.QFileDialog.open_return = ("/tmp/env.hdr", "")
    dlg._browse_hdri()
    assert dlg.hdri_path.text() == "/tmp/env.hdr"
    assert dlg.background_mode.currentText() == "hdri"
    assert cfg.hdri_path == "/tmp/env.hdr"


def test_browse_hdri_noop_on_cancel(dlg_mod):
    dlg, _ctx, _cfg = _make_dialog(dlg_mod)
    dialog_qt_stubs.QFileDialog.open_return = ("", "")
    dlg.hdri_path.setText("")
    dlg._browse_hdri()
    assert dlg.hdri_path.text() == ""


def test_browse_render_output_sets_path_and_enables_render(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dialog_qt_stubs.QFileDialog.save_return = ("/tmp/out.png", "")
    dlg._browse_render_output()
    assert dlg.render_output_path.text() == "/tmp/out.png"
    assert dlg.render_on_run.isChecked() is True
    assert cfg.render_output_path == "/tmp/out.png"


def test_browse_render_output_noop_on_cancel(dlg_mod):
    dlg, _ctx, _cfg = _make_dialog(dlg_mod)
    dialog_qt_stubs.QFileDialog.save_return = ("", "")
    dlg._browse_render_output()
    assert dlg.render_on_run.isChecked() is False


# --------------------------------------------------------------- element colors


def test_set_and_clear_element_color(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    dlg.element_symbol.setText("cl")
    dlg.element_color.setText("#00FF00")
    dlg._set_element_color()
    assert cfg.element_colors["Cl"] == "#00FF00"
    assert "Cl=#00FF00" in dlg.element_color_label.text()
    ctx.show_status_message.assert_called()

    dlg._clear_element_colors()
    assert cfg.element_colors == {}
    assert dlg.element_color_label.text() == "No element color overrides."


def test_set_element_color_ignores_empty_input(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dlg.element_symbol.setText("")
    dlg.element_color.setText("")
    dlg._set_element_color()
    assert cfg.element_colors == {}


def test_element_color_label_truncates_long_list(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    cfg.element_colors = {f"E{i}": "#000000" for i in range(10)}
    dlg._update_element_color_label()
    assert dlg.element_color_label.text().startswith("Overrides:")


# --------------------------------------------------------------- atom tools


def test_selected_atoms_or_warn_none_selected(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.get_selected_atom_indices.return_value = []
    assert dlg._selected_atoms_or_warn() is None
    assert dialog_qt_stubs.QMessageBox.calls[-1][0] == "information"


def test_selected_atoms_or_warn_lookup_failure(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.get_selected_atom_indices.side_effect = RuntimeError("boom")
    assert dlg._selected_atoms_or_warn() is None


def test_hide_show_reset_selected_atoms(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.get_selected_atom_indices.return_value = [0, 1]

    dlg._hide_selected_atoms()
    assert cfg.atom_hidden == {"0": True, "1": True}
    assert "hidden atoms" in dlg.atom_override_label.text()

    dlg._show_selected_atoms()
    assert cfg.atom_hidden == {}

    dlg._scale_selected_atoms()
    assert cfg.atom_overrides["0"] == {"scale": dlg.selection_scale.value()}

    dlg._set_selected_atom_radius()
    assert "radius" in cfg.atom_overrides["0"]

    dlg.selection_color.setText("#123456")
    dlg._color_selected_atoms()
    assert cfg.atom_color_overrides["0"] == "#123456"
    assert "custom sizes" in dlg.atom_override_label.text()
    assert "custom colors" in dlg.atom_override_label.text()

    dlg._reset_selected_atom_sizes()
    assert cfg.atom_overrides == {}
    assert cfg.atom_color_overrides == {}

    dlg._hide_selected_atoms()
    dlg._reset_all_atom_sizes()
    assert cfg.atom_hidden == {}
    ctx.show_status_message.assert_called()


def test_color_selected_atoms_ignores_empty_color(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.get_selected_atom_indices.return_value = [0]
    dlg.selection_color.setText("")
    dlg._color_selected_atoms()
    assert cfg.atom_color_overrides == {}


def test_hide_selected_atoms_none_selected_no_crash(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.get_selected_atom_indices.return_value = []
    dlg._hide_selected_atoms()
    assert cfg.atom_hidden == {}


def test_atom_override_label_many_hidden_truncates(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    cfg.atom_hidden = {str(i): True for i in range(20)}
    dlg._update_atom_override_label()
    assert "…" in dlg.atom_override_label.text()


# --------------------------------------------------------------- bond tools


def test_bond_keys_in_selection_full_flow(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    ctx.get_selected_atom_indices.return_value = [0, 1]
    keys = dlg._bond_keys_in_selection()
    assert keys == ["0-1"]


def test_bond_keys_in_selection_no_molecule(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = None
    ctx.get_selected_atom_indices.return_value = [0, 1]
    assert dlg._bond_keys_in_selection() is None
    assert dialog_qt_stubs.QMessageBox.calls[-1][0] == "information"


def test_bond_keys_in_selection_no_bonds_between_selection(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    ctx.get_selected_atom_indices.return_value = [0, 3]  # not bonded
    assert dlg._bond_keys_in_selection() is None


def test_bond_keys_in_selection_lookup_exception(dlg_mod):
    from unittest.mock import MagicMock
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    mol = MagicMock()
    mol.GetBonds.side_effect = RuntimeError("boom")
    ctx.current_molecule = mol
    ctx.get_selected_atom_indices.return_value = [0, 1]
    assert dlg._bond_keys_in_selection() is None


def test_bond_keys_in_selection_no_selection(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.get_selected_atom_indices.return_value = []
    assert dlg._bond_keys_in_selection() is None


def test_hide_show_reset_bonds(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    ctx.get_selected_atom_indices.return_value = [0, 1]

    dlg._hide_selected_bonds()
    assert cfg.bond_hidden == {"0-1": True}
    assert "Hidden bonds" in dlg.bond_hidden_label.text()

    dlg._show_selected_bonds()
    assert cfg.bond_hidden == {}

    dlg._hide_selected_bonds()
    dlg._reset_hidden_bonds()
    assert cfg.bond_hidden == {}
    assert dlg.bond_hidden_label.text() == "No hidden bonds."


def test_hide_selected_bonds_no_keys_noop(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = None
    ctx.get_selected_atom_indices.return_value = [0, 1]
    dlg._hide_selected_bonds()
    assert cfg.bond_hidden == {}


def test_bond_hidden_label_truncates(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    cfg.bond_hidden = {f"{i}-{i+1}": True for i in range(15)}
    dlg._update_bond_hidden_label()
    assert "…" in dlg.bond_hidden_label.text()


# --------------------------------------------------------------- lights


def test_add_and_remove_light(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dlg._add_light()
    assert dlg.use_custom_lights.isChecked() is True
    assert dlg.lights_table.rowCount() == 1
    assert "Light1" in cfg.custom_lights

    dlg._add_light()
    assert dlg.lights_table.rowCount() == 2

    dlg.lights_table._current_row = 0
    dlg._remove_light()
    assert len(cfg.custom_lights) == 1


def test_remove_light_invalid_row_noop(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dlg._add_light()
    dlg.lights_table._current_row = -1
    dlg._remove_light()
    assert len(cfg.custom_lights) == 1


def test_rebuild_custom_lights_from_table(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dlg._add_light()
    name_edit = dlg.lights_table.cellWidget(0, 0)
    name_edit.setText("MyLight")
    dlg._rebuild_custom_lights()
    assert "MyLight" in cfg.custom_lights


def test_rebuild_custom_lights_dedupes_names(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dlg._add_light()
    dlg._add_light()
    for row in (0, 1):
        dlg.lights_table.cellWidget(row, 0).setText("Same")
    dlg._rebuild_custom_lights()
    assert len(cfg.custom_lights) == 2
    assert "Same" in cfg.custom_lights
    assert "Same_1" in cfg.custom_lights


def test_rebuild_custom_lights_noop_while_loading(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dlg._add_light()
    before = dict(cfg.custom_lights)
    dlg._loading = True
    dlg.lights_table.cellWidget(0, 0).setText("Renamed")
    dlg._rebuild_custom_lights()
    assert cfg.custom_lights == before
    dlg._loading = False


def test_refresh_lights_table_with_spec_dict(dlg_mod):
    from blender_export_pro.style_config import StyleConfig
    cfg = StyleConfig(custom_lights={"A": {"energy": 500.0}})
    dlg, _ctx, _cfg = _make_dialog(dlg_mod, cfg=cfg)
    assert dlg.lights_table.rowCount() == 1


# --------------------------------------------------------------- ring table


def test_refresh_ring_table_populates_rows(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    dlg._refresh_ring_table()
    assert dlg.ring_table.rowCount() == 1
    assert len(dlg._ring_keys_by_row) == 1


def test_refresh_ring_table_no_molecule(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = None
    dlg._refresh_ring_table()
    assert dlg.ring_table.rowCount() == 0


def test_refresh_ring_table_extraction_failure(dlg_mod, monkeypatch):
    import blender_export_pro.blender_codegen as blender_codegen
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    monkeypatch.setattr(blender_codegen, "extract_rings",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    dlg._refresh_ring_table()  # must not raise
    assert dlg.ring_table.rowCount() == 0


def test_on_ring_cell_changed_sets_override(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    dlg._refresh_ring_table()
    show, atoms, color, opacity, thickness, size = dlg._ring_row_widgets(0)
    show.setCurrentText("hide")
    color.setText("#ABCDEF")
    dlg._on_ring_cell_changed(0)
    key = dlg._ring_keys_by_row[0]
    assert cfg.ring_overrides[key]["visible"] is False
    assert cfg.ring_overrides[key]["color"] == "#ABCDEF"
    assert dlg.ring_table.item(0, 0).text().endswith("*")


def test_on_ring_cell_changed_invalid_row_noop(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    dlg._refresh_ring_table()
    dlg._on_ring_cell_changed(5)  # out of range
    assert cfg.ring_overrides == {}


def test_on_ring_cell_changed_while_loading_noop(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    dlg._refresh_ring_table()
    dlg._loading = True
    dlg._on_ring_cell_changed(0)
    assert cfg.ring_overrides == {}
    dlg._loading = False


def test_on_ring_row_selected_sets_highlight(dlg_mod):
    from blender_export_pro import preview_style
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    dlg._refresh_ring_table()
    dlg.ring_table.selectRow(0)
    assert preview_style.get_highlighted_ring() == dlg._ring_keys_by_row[0]
    preview_style.set_highlighted_ring(None)


def test_on_ring_row_selected_invalid_clears_highlight(dlg_mod):
    from blender_export_pro import preview_style
    dlg, _ctx, _cfg = _make_dialog(dlg_mod)
    preview_style.set_highlighted_ring("x")
    dlg._on_ring_row_selected(-1)
    assert preview_style.get_highlighted_ring() is None


def test_reset_selected_ring(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    dlg._refresh_ring_table()
    key = dlg._ring_keys_by_row[0]
    cfg.ring_overrides[key] = {"visible": False}
    dlg.ring_table._current_row = 0
    dlg._reset_selected_ring()
    assert key not in cfg.ring_overrides


def test_reset_selected_ring_invalid_row_noop(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    dlg._refresh_ring_table()
    dlg.ring_table._current_row = -1
    dlg._reset_selected_ring()  # must not raise


def test_set_all_rings_visible_and_reset_all(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_benzene_like()
    dlg._ring_keys_by_row = []  # force internal re-detection branch
    dlg._set_all_rings_visible(False)
    key = dlg._ring_keys_by_row[0]
    assert cfg.ring_overrides[key]["visible"] is False

    dlg._set_all_rings_visible(True)
    assert cfg.ring_overrides[key]["visible"] is True

    dlg._reset_all_rings()
    assert cfg.ring_overrides == {}


# --------------------------------------------------------------- style switch


def test_activate_preview_and_standard(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    dlg._activate_preview()
    v3d = ctx.get_main_window.return_value.view_3d_manager
    v3d.set_3d_style.assert_called()
    ctx.show_status_message.assert_called()

    dlg._activate_standard()
    assert v3d.set_3d_style.call_count == 2


def test_activate_preview_refresh_exception_swallowed(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.refresh_3d_view.side_effect = RuntimeError("boom")
    dlg._activate_preview()  # must not raise


def test_activate_preview_when_no_3d_view(dlg_mod):
    from unittest.mock import MagicMock
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.get_main_window.return_value = MagicMock(spec=[])
    dlg._activate_preview()  # must not raise; activate_preview_style() -> False


# --------------------------------------------------------------- presets


def test_apply_preset_loads_and_activates(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    name = next(iter(dlg._presets))
    dlg.preset_combo.setCurrentText(name)
    dlg._apply_preset()
    assert cfg.is_touched() is True
    ctx.show_status_message.assert_called()


def test_load_preset_file_from_disk(dlg_mod, tmp_path):
    import json
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    preset_path = tmp_path / "custom.json"
    preset_path.write_text(json.dumps({"material_preset": "glass"}))
    dialog_qt_stubs.QFileDialog.open_return = (str(preset_path), "")
    dlg._load_preset_file()
    assert cfg.material_preset == "glass"
    ctx.show_status_message.assert_called()


def test_load_preset_file_cancelled(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dialog_qt_stubs.QFileDialog.open_return = ("", "")
    before = cfg.material_preset
    dlg._load_preset_file()
    assert cfg.material_preset == before


def test_save_preset_file_writes_json(dlg_mod, tmp_path):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    out_path = tmp_path / "saved.json"
    dialog_qt_stubs.QFileDialog.save_return = (str(out_path), "")
    dlg._save_preset_file()
    assert out_path.exists()
    ctx.show_status_message.assert_called()


def test_reset_defaults(dlg_mod):
    dlg, ctx, cfg = _make_dialog(dlg_mod)
    cfg.material_preset = "glass"
    cfg.mark_touched()
    dlg._reset_defaults()
    assert cfg.material_preset == "plastic"
    ctx.show_status_message.assert_called()


# --------------------------------------------------------------- export


def test_export_script_no_molecule_warns(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = None
    dlg._export_script()
    assert dialog_qt_stubs.QMessageBox.calls[-1][0] == "warning"


def test_export_script_selection_only_no_selection_warns(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_ethanol_like()
    dlg.selection_only.setChecked(True)
    ctx.get_selected_atom_indices.return_value = []
    dlg._export_script()
    assert dialog_qt_stubs.QMessageBox.calls[-1][0] == "warning"


def test_export_script_codegen_failure_shows_critical(dlg_mod, monkeypatch):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_ethanol_like()
    monkeypatch.setattr(dlg_mod, "generate_script_from_mol",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    dlg._export_script()
    assert dialog_qt_stubs.QMessageBox.calls[-1][0] == "critical"


def test_export_script_cancelled_save_dialog(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_ethanol_like()
    dialog_qt_stubs.QFileDialog.save_return = ("", "")
    dlg._export_script()  # returns quietly after getSaveFileName cancel


def test_export_script_success_writes_file(dlg_mod, tmp_path):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_ethanol_like()
    out_path = tmp_path / "out.py"
    dialog_qt_stubs.QFileDialog.save_return = (str(out_path), "")
    dlg._export_script()
    assert out_path.exists()
    ctx.show_status_message.assert_called()


def test_export_script_write_failure_shows_critical(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_ethanol_like()
    bad_path = os.path.join(tempfile.gettempdir(),
                            "bep_missing_dir_xyz", "out.py")
    dialog_qt_stubs.QFileDialog.save_return = (bad_path, "")
    dlg._export_script()
    assert dialog_qt_stubs.QMessageBox.calls[-1][0] == "critical"


def test_export_mesh_no_molecule_warns(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = None
    dlg._export_mesh()
    assert dialog_qt_stubs.QMessageBox.calls[-1][0] == "warning"


def test_export_mesh_selection_only_no_selection_warns(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_ethanol_like()
    dlg.selection_only.setChecked(True)
    ctx.get_selected_atom_indices.return_value = []
    dlg._export_mesh()
    assert dialog_qt_stubs.QMessageBox.calls[-1][0] == "warning"


def test_export_mesh_cancelled_save_dialog(dlg_mod):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_ethanol_like()
    dialog_qt_stubs.QFileDialog.save_return = ("", "")
    dlg._export_mesh()


def test_export_mesh_success_writes_file(dlg_mod, tmp_path):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_ethanol_like()
    out_path = tmp_path / "out.glb"
    dialog_qt_stubs.QFileDialog.save_return = (str(out_path), "")
    dlg._export_mesh()
    assert out_path.exists()
    ctx.show_status_message.assert_called()


def test_export_mesh_failure_shows_critical(dlg_mod, monkeypatch, tmp_path):
    dlg, ctx, _cfg = _make_dialog(dlg_mod)
    ctx.current_molecule = make_ethanol_like()
    out_path = tmp_path / "out.glb"
    dialog_qt_stubs.QFileDialog.save_return = (str(out_path), "")

    import blender_export_pro.mesh_export as mesh_export
    monkeypatch.setattr(mesh_export, "export_mesh_file",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    dlg._export_mesh()
    assert dialog_qt_stubs.QMessageBox.calls[-1][0] == "critical"


# --------------------------------------------------------------- lifecycle


def test_close_event_hides_and_pulls_config(dlg_mod):
    dlg, _ctx, cfg = _make_dialog(dlg_mod)
    dlg.collection_name.setText("ClosedName")
    event = dialog_qt_stubs.QCloseEvent()
    dlg.closeEvent(event)
    assert dlg._hidden is True
    assert event._ignored is True
    assert cfg.collection_name == "ClosedName"


def test_close_event_swallows_highlight_exception(dlg_mod, monkeypatch):
    from blender_export_pro import preview_style
    dlg, _ctx, _cfg = _make_dialog(dlg_mod)
    monkeypatch.setattr(preview_style, "set_highlighted_ring",
                        lambda *_a: (_ for _ in ()).throw(RuntimeError("x")))
    event = dialog_qt_stubs.QCloseEvent()
    dlg.closeEvent(event)  # must not raise
    assert dlg._hidden is True


def test_close_event_swallows_pull_config_exception(dlg_mod, monkeypatch):
    dlg, _ctx, _cfg = _make_dialog(dlg_mod)
    monkeypatch.setattr(dlg, "_pull_config",
                        lambda: (_ for _ in ()).throw(RuntimeError("x")))
    event = dialog_qt_stubs.QCloseEvent()
    dlg.closeEvent(event)  # must not raise
    assert dlg._hidden is True
