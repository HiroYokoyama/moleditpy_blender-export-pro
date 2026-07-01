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
