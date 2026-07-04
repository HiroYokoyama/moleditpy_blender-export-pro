"""Smoke tests for the plugin entry point and registration wiring."""

import ast
import os
import re
from unittest.mock import MagicMock

from conftest import make_context, mock_optional_imports

import blender_export_pro as plugin


def test_metadata_constants():
    assert plugin.PLUGIN_NAME == "Blender Export Pro"
    assert plugin.PLUGIN_VERSION
    assert plugin.PLUGIN_AUTHOR
    assert plugin.PLUGIN_DESCRIPTION
    assert plugin.PLUGIN_SUPPORTED_MOLEDITPY_VERSION.startswith(">=4")
    assert plugin.__version__ == plugin.PLUGIN_VERSION


def test_plugin_version_is_ast_visible_string_literal():
    """The host Plugin Manager AST-parses __init__.py for metadata and only
    reads constant assignments — PLUGIN_VERSION = __version__ (a Name node)
    would display as 'Unknown'. Guard that it stays a plain string literal."""
    init_path = os.path.join(os.path.dirname(plugin.__file__), "__init__.py")
    with open(init_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PLUGIN_VERSION":
                    assert isinstance(node.value, ast.Constant), \
                        "PLUGIN_VERSION must be a literal for the host AST parser"
                    found = node.value.value
    assert found == plugin.PLUGIN_VERSION
    assert re.fullmatch(r"\d+\.\d+\.\d+", found), "semver expected"


def test_initialize_registers_everything():
    ctx = make_context()
    plugin.initialize(ctx)

    path, _cb = ctx.add_menu_action.call_args[0]
    assert path == "Extensions/Blender Export Pro…"

    style_name, style_cb = ctx.register_3d_style.call_args[0]
    assert style_name == plugin.STYLE_NAME
    assert callable(style_cb)

    export_labels = [call.args[0] for call in ctx.add_export_action.call_args_list]
    assert any("Blender Script" in lbl for lbl in export_labels)
    assert any(".glb" in lbl or "3D Model" in lbl for lbl in export_labels)

    ctx.register_save_handler.assert_called_once()
    ctx.register_load_handler.assert_called_once()
    ctx.register_document_reset_handler.assert_called_once()


def test_save_load_handlers_round_trip():
    ctx = make_context()
    plugin.initialize(ctx)

    save_cb = ctx.register_save_handler.call_args[0][0]
    load_cb = ctx.register_load_handler.call_args[0][0]
    reset_cb = ctx.register_document_reset_handler.call_args[0][0]

    style = plugin.get_style()
    style.material_preset = "glass"
    style.mark_touched()
    saved = save_cb()
    assert saved["material_preset"] == "glass"

    reset_cb()
    assert plugin.get_style().material_preset != "glass"

    load_cb(saved)
    assert plugin.get_style().material_preset == "glass"


def test_untouched_style_saves_nothing():
    """A plugin the user never interacted with must not bloat the project:
    the save handler returns None until the style is actually touched."""
    ctx = make_context()
    plugin.initialize(ctx)

    save_cb = ctx.register_save_handler.call_args[0][0]
    reset_cb = ctx.register_document_reset_handler.call_args[0][0]

    # Fresh launch (defaults, possibly a last preset) — nothing to persist.
    assert save_cb() is None

    style = plugin.get_style()
    style.mark_touched()
    assert save_cb() is not None

    # File > New resets to a pristine, untouched style again.
    reset_cb()
    assert save_cb() is None


def test_load_handler_ignores_empty_payload():
    """Loading a project whose stored value is None/{} must not mark the style
    touched (which would re-save a full blob on the next save)."""
    ctx = make_context()
    plugin.initialize(ctx)

    save_cb = ctx.register_save_handler.call_args[0][0]
    load_cb = ctx.register_load_handler.call_args[0][0]
    reset_cb = ctx.register_document_reset_handler.call_args[0][0]

    reset_cb()
    load_cb(None)
    assert save_cb() is None
    load_cb({})
    assert save_cb() is None


def test_open_panel_reuses_registered_window():
    ctx = make_context()
    plugin.initialize(ctx)

    existing = MagicMock()
    ctx.get_window.return_value = existing
    plugin.open_panel(ctx)
    existing.show.assert_called_once()
    existing.raise_.assert_called_once()
    ctx.register_window.assert_not_called()


def test_quick_export_no_molecule_shows_status():
    with mock_optional_imports():
        ctx = make_context()
        plugin.initialize(ctx)
        ctx.current_molecule = None
        plugin.quick_export(ctx)
        assert ctx.show_status_message.called


def test_activate_preview_style_switches_3d_view():
    ctx = make_context()
    v3d = ctx.get_main_window.return_value.view_3d_manager
    assert plugin.activate_preview_style(ctx) is True
    v3d.set_3d_style.assert_called_once_with(plugin.STYLE_NAME)


def test_activate_standard_style_switches_back():
    ctx = make_context()
    v3d = ctx.get_main_window.return_value.view_3d_manager
    assert plugin.activate_standard_style(ctx) is True
    v3d.set_3d_style.assert_called_once_with(plugin.STANDARD_STYLE)


def test_activate_preview_style_without_3d_view():
    ctx = make_context()
    mw = MagicMock(spec=[])  # no view_3d_manager attribute
    ctx.get_main_window.return_value = mw
    assert plugin.activate_preview_style(ctx) is False
    assert ctx.show_status_message.called


def _fake_style_menu(ctx, labels):
    """Install a fake 3D Style menu with checkable actions on the context."""
    actions = []
    for text in labels:
        act = MagicMock()
        act.text.return_value = text
        act.isCheckable.return_value = True
        actions.append(act)
    menu = MagicMock()
    menu.actions.return_value = actions
    ctx.get_main_window.return_value.init_manager.style_button.menu \
        .return_value = menu
    return actions


def test_activate_preview_checks_menu_entry():
    ctx = make_context()
    actions = _fake_style_menu(
        ctx, ["Ball & Stick", "Wireframe", plugin.STYLE_NAME])
    plugin.activate_preview_style(ctx)
    actions[0].setChecked.assert_called_with(False)
    actions[1].setChecked.assert_called_with(False)
    actions[2].setChecked.assert_called_with(True)


def test_activate_standard_checks_ball_and_stick():
    ctx = make_context()
    actions = _fake_style_menu(
        ctx, ["Ball & Stick", "Wireframe", plugin.STYLE_NAME])
    plugin.activate_standard_style(ctx)
    actions[0].setChecked.assert_called_with(True)
    actions[1].setChecked.assert_called_with(False)
    actions[2].setChecked.assert_called_with(False)


def test_sync_style_menu_tolerates_missing_menu():
    ctx = make_context()
    ctx.get_main_window.return_value = MagicMock(spec=[])  # no init_manager
    plugin.sync_style_menu(ctx, plugin.STYLE_NAME)  # must not raise


def test_is_preview_style_active():
    ctx = make_context()
    v3d = ctx.get_main_window.return_value.view_3d_manager
    v3d.current_3d_style = plugin.STYLE_NAME
    assert plugin.is_preview_style_active(ctx) is True
    v3d.current_3d_style = "ball_and_stick"
    assert plugin.is_preview_style_active(ctx) is False


def test_preview_callback_handles_headless(monkeypatch):
    """The registered style callback must not raise without pyvista."""
    ctx = make_context()
    plugin.initialize(ctx)
    _name, style_cb = ctx.register_3d_style.call_args[0]

    from blender_export_pro import preview_style
    monkeypatch.setattr(preview_style, "pv", None)
    monkeypatch.setattr(preview_style, "np", None)
    style_cb(MagicMock(), MagicMock())  # should log a warning, not raise
