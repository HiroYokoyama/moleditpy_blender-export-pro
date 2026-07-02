"""Import-level smoke tests for the GUI modules under mocked PyQt6/pyvista."""

import ast
import importlib
import sys
from pathlib import Path

from conftest import ROOT, mock_optional_imports


def _fresh_import(module_name):
    for key in list(sys.modules):
        if key == module_name or key.startswith(module_name + "."):
            del sys.modules[key]
    return importlib.import_module(module_name)


def test_dialog_module_imports_under_mocks():
    with mock_optional_imports():
        mod = _fresh_import("blender_export_pro.dialog")
        assert hasattr(mod, "BlenderExportDialog")


def test_dialog_widget_fields_match_style_config():
    """Every entry in _WIDGET_FIELDS must be a real StyleConfig attribute.

    The class object is a MagicMock under mocked PyQt6, so read the tuple
    from the source via AST instead.
    """
    from blender_export_pro.style_config import StyleConfig

    source = (Path(ROOT) / "blender_export_pro" / "dialog.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    widget_fields = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_WIDGET_FIELDS":
                    widget_fields = ast.literal_eval(node.value)
    assert widget_fields, "_WIDGET_FIELDS not found in dialog.py"

    cfg_fields = set(StyleConfig().to_dict())
    assert {name for name, _kind in widget_fields} <= cfg_fields


def test_dialog_has_quick_start_actions():
    """The Quick Start handlers (preset, style switch, export) must exist."""
    source = (Path(ROOT) / "blender_export_pro" / "dialog.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    methods = {
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert {"_apply_preset", "_activate_preview", "_activate_standard",
            "_export_script", "_on_setting_changed"} <= methods
    # per-ring table handlers
    assert {"_refresh_ring_table", "_on_ring_cell_changed",
            "_on_ring_row_selected", "_reset_selected_ring"} <= methods
    # selected-atom sizing handlers
    assert {"_scale_selected_atoms", "_set_selected_atom_radius",
            "_reset_selected_atom_sizes", "_reset_all_atom_sizes"} <= methods
    # element color + render output + mesh export handlers
    assert {"_set_element_color", "_clear_element_colors",
            "_browse_render_output", "_color_selected_atoms"} <= methods
    # atom hide + custom light handlers
    assert {"_hide_selected_atoms", "_show_selected_atoms",
            "_add_light", "_remove_light", "_rebuild_custom_lights"} <= methods
    # glTF/USD export button + ring bulk actions
    assert {"_export_mesh", "_set_all_rings_visible",
            "_reset_all_rings"} <= methods
    # per-bond hiding
    assert {"_hide_selected_bonds", "_show_selected_bonds",
            "_reset_hidden_bonds", "_bond_keys_in_selection"} <= methods


def test_dialog_no_global_config_save():
    """The dialog must never persist the full style to settings.json."""
    source = (Path(ROOT) / "blender_export_pro" / "dialog.py").read_text(
        encoding="utf-8")
    assert "save_config" not in source
    assert "save_last_preset" in source     # preset choice is remembered


def test_dialog_has_paper_stylesheet():
    source = (Path(ROOT) / "blender_export_pro" / "dialog.py").read_text(
        encoding="utf-8")
    assert "PAPER_STYLESHEET" in source
    assert "setStyleSheet(PAPER_STYLESHEET)" in source


def test_preview_material_kwargs_never_collide_with_add_mesh_args():
    """Regression: add_mesh() passes color/name/smooth_shading explicitly;
    material kwargs duplicating them raise TypeError at draw time."""
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import MATERIAL_PRESETS, StyleConfig

    reserved = {"color", "name", "smooth_shading"}
    for preset in MATERIAL_PRESETS + ("unknown_preset",):
        kwargs = preview_style._material_kwargs(
            StyleConfig(material_preset=preset))
        assert not reserved & set(kwargs), (preset, kwargs)


def test_apply_lighting_uses_config_lights(monkeypatch):
    """Preview lighting must mirror the configured lights on the plotter."""
    import types
    from unittest.mock import MagicMock
    import pytest

    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    fake_pv = types.SimpleNamespace(Light=MagicMock())
    monkeypatch.setattr(preview_style, "pv", fake_pv)
    monkeypatch.setattr(preview_style, "np", np_real)

    center = np_real.zeros(3)

    # default: key-light rig = 3 lights
    plotter = MagicMock()
    preview_style._apply_lighting(plotter, StyleConfig(), center, 5.0)
    assert plotter.add_light.call_count == 3
    plotter.remove_all_lights.assert_called_once()

    # custom lights: one add_light per configured light, with color+intensity
    plotter = MagicMock()
    fake_pv.Light.reset_mock()
    cfg = StyleConfig(use_custom_lights=True, custom_lights={
        "A": {"energy": 2000.0, "color": "#FF0000"},
        "B": {"energy": 500.0},
    })
    preview_style._apply_lighting(plotter, cfg, center, 5.0)
    assert plotter.add_light.call_count == 2
    intensities = [c.kwargs["intensity"] for c in fake_pv.Light.call_args_list]
    assert intensities == [2.0, 0.5]
    assert fake_pv.Light.call_args_list[0].kwargs["color"] == (1.0, 0.0, 0.0)


def test_apply_lighting_falls_back_to_lightkit(monkeypatch):
    import types
    from unittest.mock import MagicMock
    import pytest

    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    def boom(**_kw):
        raise RuntimeError("no lights")

    monkeypatch.setattr(preview_style, "pv", types.SimpleNamespace(Light=boom))
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    preview_style._apply_lighting(plotter, StyleConfig(), np_real.zeros(3), 5.0)
    plotter.enable_lightkit.assert_called_once()


def test_ensure_lighting_resets_lightkit():
    """After clear() the preview must restore lights (else flat 'planes')."""
    from unittest.mock import MagicMock
    from blender_export_pro import preview_style

    plotter = MagicMock()
    preview_style._ensure_lighting(plotter)
    plotter.remove_all_lights.assert_called_once()
    plotter.enable_lightkit.assert_called_once()


def test_highlighted_ring_setter():
    from blender_export_pro import preview_style

    preview_style.set_highlighted_ring("0-1-2-3-4-5")
    assert preview_style.get_highlighted_ring() == "0-1-2-3-4-5"
    preview_style.set_highlighted_ring(None)
    assert preview_style.get_highlighted_ring() is None


def test_preview_style_module_imports_under_mocks():
    with mock_optional_imports():
        mod = _fresh_import("blender_export_pro.preview_style")
        assert hasattr(mod, "draw_preview_style")


def test_preview_draw_noop_without_plotter():
    """draw_preview_style must exit quietly when the host has no plotter."""
    from unittest.mock import MagicMock

    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    if preview_style.pv is None:
        return  # headless without pyvista: covered by test_initialize

    mw = MagicMock()
    mw.view_3d_manager.plotter = None
    preview_style.draw_preview_style(mw, MagicMock(), StyleConfig())


def _draw_preview(monkeypatch, cfg, mol=None):
    """Run draw_preview_style with real numpy and a fake pyvista.

    Returns (fake_pv, plotter) so tests can inspect the geometry calls.
    """
    from unittest.mock import MagicMock
    import pytest

    np_real = pytest.importorskip("numpy")
    from conftest import make_benzene_like
    from blender_export_pro import preview_style

    fake_pv = MagicMock()
    monkeypatch.setattr(preview_style, "pv", fake_pv)
    monkeypatch.setattr(preview_style, "np", np_real)
    preview_style.set_highlighted_ring(None)

    plotter = MagicMock()
    mw = MagicMock()
    mw.view_3d_manager.plotter = plotter
    preview_style.draw_preview_style(mw, mol or make_benzene_like(), cfg)
    return fake_pv, plotter


def _added_mesh_names(plotter):
    return [c.kwargs.get("name") for c in plotter.add_mesh.call_args_list]


def test_preview_draws_atoms_and_bonds(monkeypatch):
    """Benzene-like: 7 atom spheres, 6 aromatic double bonds + 1 single."""
    from blender_export_pro.style_config import StyleConfig

    _fake_pv, plotter = _draw_preview(monkeypatch, StyleConfig())
    names = _added_mesh_names(plotter)
    assert sum(1 for n in names if n and n.startswith("bep_atom_")) == 7
    # aromatic bonds (order 2) draw two cylinders each, C-Cl draws one
    assert sum(1 for n in names if n and n.startswith("bep_bond_")) == 6 * 2 + 1
    plotter.clear.assert_called_once()
    plotter.render.assert_called_once()


def test_preview_multi_bond_scale_applied(monkeypatch):
    """The multi-bond cylinders must use bond_radius * multi_bond_scale."""
    from blender_export_pro.style_config import StyleConfig

    fake_pv, _plotter = _draw_preview(
        monkeypatch, StyleConfig(bond_radius=0.2, multi_bond_scale=1.0))
    radii = {round(c.kwargs["radius"], 6)
             for c in fake_pv.Cylinder.call_args_list}
    assert radii == {0.2}   # scale 1.0: doubles as thick as singles

    fake_pv, _plotter = _draw_preview(
        monkeypatch, StyleConfig(bond_radius=0.2, multi_bond_scale=0.5))
    radii = {round(c.kwargs["radius"], 6)
             for c in fake_pv.Cylinder.call_args_list}
    assert radii == {0.2, 0.1}


def test_preview_draws_ring_panel_and_outline(monkeypatch):
    from blender_export_pro.style_config import StyleConfig

    _fake_pv, plotter = _draw_preview(
        monkeypatch, StyleConfig(ring_style="panel+outline"))
    names = _added_mesh_names(plotter)
    assert "bep_ring_0" in names
    assert "bep_ring_line_0" in names


def test_preview_hidden_ring_not_drawn(monkeypatch):
    from blender_export_pro.style_config import StyleConfig

    _fake_pv, plotter = _draw_preview(
        monkeypatch,
        StyleConfig(ring_style="panel+outline",
                    ring_overrides={"0-1-2-3-4-5": {"visible": False}}))
    names = _added_mesh_names(plotter)
    assert "bep_ring_0" not in names
    assert "bep_ring_line_0" not in names


def test_preview_hidden_bond_not_drawn(monkeypatch):
    """A bond in cfg.bond_hidden must not draw, its atoms must stay."""
    from blender_export_pro.style_config import StyleConfig

    _fake_pv, plotter = _draw_preview(monkeypatch, StyleConfig())
    all_bonds = sum(1 for n in _added_mesh_names(plotter)
                    if n and n.startswith("bep_bond_"))

    _fake_pv, plotter = _draw_preview(
        monkeypatch, StyleConfig(bond_hidden={"0-6": True}))  # the C-Cl bond
    names = _added_mesh_names(plotter)
    bonds = sum(1 for n in names if n and n.startswith("bep_bond_"))
    atoms = sum(1 for n in names if n and n.startswith("bep_atom_"))
    assert bonds == all_bonds - 1
    assert atoms == 7


def test_preview_aromatic_bond_styles(monkeypatch):
    """single: one cylinder per aromatic bond; dashed: solid + 5 dashes."""
    from blender_export_pro.style_config import StyleConfig

    _fake_pv, plotter = _draw_preview(
        monkeypatch, StyleConfig(aromatic_bond_style="single"))
    names = _added_mesh_names(plotter)
    assert sum(1 for n in names if n and n.startswith("bep_bond_")) == 7

    _fake_pv, plotter = _draw_preview(
        monkeypatch, StyleConfig(aromatic_bond_style="dashed"))
    names = _added_mesh_names(plotter)
    dashes = [n for n in names if n and "_dash" in n]
    solids = [n for n in names
              if n and n.startswith("bep_bond_") and "_dash" not in n]
    assert len(dashes) == 6 * 5          # 5 dashes per aromatic bond
    assert len(solids) == 6 + 1          # solid main lines + the C-Cl bond


def test_preview_smooth_gradient_bond(monkeypatch):
    """Gradient bonds use one cylinder with per-vertex colors (smooth),
    not colored slices."""
    from unittest.mock import MagicMock
    import pytest

    np_real = pytest.importorskip("numpy")
    pv_real = pytest.importorskip("pyvista")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", pv_real)
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    ok = preview_style._add_smooth_gradient_bond(
        plotter, StyleConfig(bond_color_mode="gradient"), {},
        np_real.zeros(3), np_real.array([1.0, 0.0, 0.0]), 1.5, 0.12,
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), "bep_bond_0_0_0")
    assert ok is True
    kwargs = plotter.add_mesh.call_args.kwargs
    assert kwargs["rgb"] is True
    colors = kwargs["scalars"]
    # end-ring vertices carry the two pure colors; the GPU interpolates
    assert {tuple(c) for c in np_real.round(colors, 3)} >= {
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)}


def test_preview_smooth_gradient_falls_back_quietly(monkeypatch):
    from unittest.mock import MagicMock
    import pytest

    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    broken_pv = MagicMock()
    broken_pv.Cylinder.side_effect = RuntimeError("boom")
    monkeypatch.setattr(preview_style, "pv", broken_pv)
    monkeypatch.setattr(preview_style, "np", np_real)
    ok = preview_style._add_smooth_gradient_bond(
        MagicMock(), StyleConfig(), {}, np_real.zeros(3),
        np_real.array([1.0, 0.0, 0.0]), 1.5, 0.12,
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), "n")
    assert ok is False


def test_preview_hide_all_bonds(monkeypatch):
    from blender_export_pro.style_config import StyleConfig

    _fake_pv, plotter = _draw_preview(
        monkeypatch, StyleConfig(hide_all_bonds=True))
    names = _added_mesh_names(plotter)
    assert not any(n and n.startswith("bep_bond_") for n in names)
    assert sum(1 for n in names if n and n.startswith("bep_atom_")) == 7


def test_apply_lighting_fill_and_rim_strengths(monkeypatch):
    """Fill/rim lights must follow the configured fractions of the key."""
    import types
    from unittest.mock import MagicMock
    import pytest

    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    fake_pv = types.SimpleNamespace(Light=MagicMock())
    monkeypatch.setattr(preview_style, "pv", fake_pv)
    monkeypatch.setattr(preview_style, "np", np_real)

    plotter = MagicMock()
    cfg = StyleConfig(fill_light_strength=0.0, rim_light_strength=2.0)
    preview_style._apply_lighting(plotter, cfg, np_real.zeros(3), 5.0)
    intensities = [c.kwargs["intensity"] for c in fake_pv.Light.call_args_list]
    assert intensities == [1.0, 0.0, 2.0]
