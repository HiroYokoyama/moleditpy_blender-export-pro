"""Smoke tests for the plugin entry point and registration wiring."""

from unittest.mock import MagicMock

from conftest import make_context, mock_optional_imports

import blender_export_pro as plugin


def test_metadata_constants():
    assert plugin.PLUGIN_NAME == "Blender Export Pro"
    assert plugin.PLUGIN_VERSION
    assert plugin.PLUGIN_AUTHOR
    assert plugin.PLUGIN_DESCRIPTION
    assert plugin.PLUGIN_SUPPORTED_MOLEDITPY_VERSION.startswith(">=4")


def test_initialize_registers_everything():
    ctx = make_context()
    plugin.initialize(ctx)

    path, _cb = ctx.add_menu_action.call_args[0]
    assert path == "Visuals/Blender Export Pro…"

    style_name, style_cb = ctx.register_3d_style.call_args[0]
    assert style_name == plugin.STYLE_NAME
    assert callable(style_cb)

    label, _cb = ctx.add_export_action.call_args[0]
    assert "Blender Script" in label

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
    saved = save_cb()
    assert saved["material_preset"] == "glass"

    reset_cb()
    assert plugin.get_style().material_preset != "glass"

    load_cb(saved)
    assert plugin.get_style().material_preset == "glass"


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
