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

    import numpy as np_real
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

    import numpy as np_real
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
