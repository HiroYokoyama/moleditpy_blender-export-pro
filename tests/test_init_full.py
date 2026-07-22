"""Behavioral coverage of blender_export_pro/__init__.py branches not hit by
test_initialize.py: sync_style_menu edge cases, activate_standard_style
without a 3D view, open_panel's stale-window recreate path, and the
quick_export / quick_export_mesh menu actions (success + every failure
branch)."""

import os
import sys
import types
from unittest.mock import MagicMock

import pytest

import dialog_qt_stubs
from conftest import make_context, make_ethanol_like

import blender_export_pro as plugin

_PYQT_MODULES = ("PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets")


@pytest.fixture
def qt_stubs():
    """Install dialog_qt_stubs' fake PyQt6 so quick_export()'s local
    ``from PyQt6.QtWidgets import QFileDialog, QMessageBox`` resolves to
    controllable stand-ins instead of MagicMock or the real Qt bindings."""
    snapshot = {name: sys.modules.get(name) for name in _PYQT_MODULES}
    dialog_qt_stubs.install()
    try:
        yield dialog_qt_stubs
    finally:
        dialog_qt_stubs.remove()
        for name, value in snapshot.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        dialog_qt_stubs.QMessageBox.reset()


# ------------------------------------------------------------ sync_style_menu


def test_sync_style_menu_none_menu_noop():
    ctx = make_context()
    ctx.get_main_window.return_value.init_manager.style_button.menu \
        .return_value = None
    plugin.sync_style_menu(ctx, plugin.STYLE_NAME)  # must not raise


def test_sync_style_menu_swallows_exception():
    ctx = make_context()
    menu = MagicMock()
    menu.actions.side_effect = RuntimeError("boom")
    ctx.get_main_window.return_value.init_manager.style_button.menu \
        .return_value = menu
    plugin.sync_style_menu(ctx, plugin.STYLE_NAME)  # must not raise


# ------------------------------------------------------- activate_standard


def test_activate_standard_style_without_3d_view():
    ctx = make_context()
    ctx.get_main_window.return_value = MagicMock(spec=[])
    assert plugin.activate_standard_style(ctx) is False


# ------------------------------------------------------------------ open_panel


def _install_fake_dialog_module(monkeypatch, fake_win):
    """Replace the whole ``blender_export_pro.dialog`` sys.modules entry with
    a throwaway module exposing a stub BlenderExportDialog.

    Patching an attribute on whatever module object happens to already be
    cached there is fragile: other test files' fixtures leave a real
    ``dialog`` module behind whose ``BlenderExportDialog`` name was bound to
    a MagicMock artifact of subclassing a mocked QDialog (see dialog_qt_stubs
    / conftest's blanket mock). Swapping the whole module via
    monkeypatch.setitem sidesteps that and self-reverts after the test."""
    fake_mod = types.ModuleType("blender_export_pro.dialog")
    fake_mod.BlenderExportDialog = lambda *a, **k: fake_win
    monkeypatch.setitem(sys.modules, "blender_export_pro.dialog", fake_mod)


def test_open_panel_recreates_after_stale_window(monkeypatch):
    ctx = make_context()
    plugin.initialize(ctx)

    stale = MagicMock()
    stale.show.side_effect = RuntimeError("stale widget")
    ctx.get_window.return_value = stale

    fake_win = MagicMock()
    _install_fake_dialog_module(monkeypatch, fake_win)
    plugin.open_panel(ctx)
    ctx.register_window.assert_called_once()
    fake_win.show.assert_called_once()


def test_open_panel_creates_new_window_when_none_registered(monkeypatch):
    ctx = make_context()
    plugin.initialize(ctx)
    ctx.get_window.return_value = None

    fake_win = MagicMock()
    _install_fake_dialog_module(monkeypatch, fake_win)
    plugin.open_panel(ctx)
    ctx.register_window.assert_called_once_with("panel", fake_win)
    fake_win.show.assert_called_once()


# ------------------------------------------------------------- quick_export


def test_quick_export_success_writes_file(qt_stubs, tmp_path):
    ctx = make_context()
    ctx.current_molecule = make_ethanol_like()
    out_path = tmp_path / "quick.py"
    qt_stubs.QFileDialog.save_return = (str(out_path), "")
    plugin.quick_export(ctx)
    assert out_path.exists()
    ctx.show_status_message.assert_called()


def test_quick_export_cancelled_save_dialog(qt_stubs):
    ctx = make_context()
    ctx.current_molecule = make_ethanol_like()
    qt_stubs.QFileDialog.save_return = ("", "")
    plugin.quick_export(ctx)  # returns quietly


def test_quick_export_codegen_failure_shows_critical(qt_stubs, monkeypatch):
    ctx = make_context()
    ctx.current_molecule = make_ethanol_like()
    import blender_export_pro.blender_codegen as blender_codegen
    monkeypatch.setattr(blender_codegen, "generate_script_from_mol",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    plugin.quick_export(ctx)
    assert qt_stubs.QMessageBox.calls[-1][0] == "critical"


def test_quick_export_write_failure_shows_critical(qt_stubs, tmp_path):
    ctx = make_context()
    ctx.current_molecule = make_ethanol_like()
    bad_path = os.path.join(str(tmp_path), "missing_dir_xyz", "out.py")
    qt_stubs.QFileDialog.save_return = (bad_path, "")
    plugin.quick_export(ctx)
    assert qt_stubs.QMessageBox.calls[-1][0] == "critical"


# -------------------------------------------------------- quick_export_mesh


def test_quick_export_mesh_success_writes_file(qt_stubs, tmp_path):
    ctx = make_context()
    ctx.current_molecule = make_ethanol_like()
    out_path = tmp_path / "quick.glb"
    qt_stubs.QFileDialog.save_return = (str(out_path), "")
    plugin.quick_export_mesh(ctx)
    assert out_path.exists()
    ctx.show_status_message.assert_called()


def test_quick_export_mesh_cancelled_save_dialog(qt_stubs):
    ctx = make_context()
    ctx.current_molecule = make_ethanol_like()
    qt_stubs.QFileDialog.save_return = ("", "")
    plugin.quick_export_mesh(ctx)  # returns quietly


def test_quick_export_mesh_no_molecule_shows_status(qt_stubs):
    ctx = make_context()
    ctx.current_molecule = None
    plugin.quick_export_mesh(ctx)
    ctx.show_status_message.assert_called()


def test_quick_export_mesh_failure_shows_critical(qt_stubs, monkeypatch, tmp_path):
    ctx = make_context()
    ctx.current_molecule = make_ethanol_like()
    out_path = tmp_path / "quick.glb"
    qt_stubs.QFileDialog.save_return = (str(out_path), "")

    import blender_export_pro.mesh_export as mesh_export
    monkeypatch.setattr(mesh_export, "export_mesh_file",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    plugin.quick_export_mesh(ctx)
    assert qt_stubs.QMessageBox.calls[-1][0] == "critical"
