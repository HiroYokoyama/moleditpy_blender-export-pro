"""Blender Export Pro — MoleditPy V4 plugin.

Adds a stylized/deformed Blender export: a live-preview 3D drawing style, a
tabbed configuration panel, and a self-contained bpy script generator.
MoleditPy never imports bpy; the output is a plain Python text file.
"""

import logging

from .style_config import STYLE_NAME, StyleConfig, load_config

PLUGIN_NAME = "Blender Export Pro"
# Must stay a literal string: the host's Plugin Manager AST-parses this file
# and only picks up constant assignments (Name references read as "Unknown").
PLUGIN_VERSION = "1.0.0"
__version__ = PLUGIN_VERSION
PLUGIN_AUTHOR = "HiroYokoyama"
PLUGIN_DESCRIPTION = (
    "Stylized/deformed Blender export: cartoon, low-poly, glass, clay and "
    "custom styles with a live 3D preview and one-click bpy script generation."
)
PLUGIN_CATEGORY = "Visualization"
PLUGIN_TAGS = ["blender", "export", "rendering", "visualization"]
PLUGIN_DEPENDENCIES = []
PLUGIN_SUPPORTED_MOLEDITPY_VERSION = ">=4.0.0, <5.0.0"

STANDARD_STYLE = "ball_and_stick"

_context = None
_style: StyleConfig = StyleConfig()


def initialize(context) -> None:
    """Plugin entry point."""
    global _context, _style
    _context = context
    _style = load_config()

    context.add_menu_action(
        "Extensions/Blender Export Pro…", lambda: open_panel(context))
    context.register_3d_style(STYLE_NAME, _draw_preview)
    context.add_export_action(
        "Export to Blender Script (.py)…", lambda: quick_export(context))
    context.add_export_action(
        "Export to 3D Model (.glb / .usda)…", lambda: quick_export_mesh(context))

    context.register_save_handler(_style.to_dict)
    context.register_load_handler(_style.update_from_dict)
    context.register_document_reset_handler(_style.reset_defaults)


def get_style() -> StyleConfig:
    """The live, shared StyleConfig instance."""
    return _style


def _draw_preview(mw, mol) -> None:
    from .preview_style import draw_preview_style
    draw_preview_style(mw, mol, _style)


def _get_view_3d_manager(context):
    mw = context.get_main_window()
    return getattr(mw, "view_3d_manager", None)


# Display labels of the app's built-in styles in the 3D Style menu.
_STANDARD_STYLE_LABELS = {
    "ball_and_stick": "Ball & Stick",
    "cpk": "CPK (Space-filling)",
    "wireframe": "Wireframe",
    "stick": "Stick",
}


def sync_style_menu(context, style_name: str) -> None:
    """Check the matching entry in the app's 3D Style menu.

    set_3d_style() changes the style but not the menu's checked action, so
    switching from the plugin would leave the menu stale.
    """
    mw = context.get_main_window()
    try:
        menu = mw.init_manager.style_button.menu()
    except AttributeError:
        return
    if menu is None:
        return
    label = _STANDARD_STYLE_LABELS.get(style_name, style_name)
    try:
        for action in menu.actions():
            if action.isCheckable():
                action.setChecked(action.text() == label)
    except Exception:
        logging.exception("BlenderExportPro: style menu sync failed")


def activate_preview_style(context) -> bool:
    """Switch the 3D view to the plugin's preview style. Returns success."""
    v3d = _get_view_3d_manager(context)
    if v3d is None or not hasattr(v3d, "set_3d_style"):
        context.show_status_message(
            "Blender Export Pro: 3D view is not available.", 4000)
        return False
    v3d.set_3d_style(STYLE_NAME)
    sync_style_menu(context, STYLE_NAME)
    return True


def activate_standard_style(context) -> bool:
    """Switch the 3D view back to the standard ball-and-stick style."""
    v3d = _get_view_3d_manager(context)
    if v3d is None or not hasattr(v3d, "set_3d_style"):
        return False
    v3d.set_3d_style(STANDARD_STYLE)
    sync_style_menu(context, STANDARD_STYLE)
    return True


def is_preview_style_active(context) -> bool:
    """True when the 3D view is currently using the preview style."""
    v3d = _get_view_3d_manager(context)
    return getattr(v3d, "current_3d_style", None) == STYLE_NAME


def open_panel(context) -> None:
    """Show the config dialog (hide-on-close singleton)."""
    win = context.get_window("panel")
    if win is not None:
        try:
            win.show()
            win.raise_()
            win.activateWindow()
            return
        except RuntimeError:
            logging.warning("BlenderExportPro: stale dialog, recreating.")

    from .dialog import BlenderExportDialog
    win = BlenderExportDialog(context.get_main_window(), context, _style)
    context.register_window("panel", win)
    win.show()


def quick_export(context) -> None:
    """Export menu action: generate a script with the current style."""
    from PyQt6.QtWidgets import QFileDialog, QMessageBox

    from .blender_codegen import generate_script_from_mol

    mw = context.get_main_window()
    mol = context.current_molecule
    if mol is None:
        context.show_status_message(
            "Blender Export Pro: no molecule with 3D coordinates.", 4000)
        return
    try:
        script = generate_script_from_mol(mol, _style)
    except Exception as exc:
        logging.exception("BlenderExportPro: codegen failed")
        QMessageBox.critical(mw, "Blender Export Pro",
                             f"Script generation failed:\n{exc}")
        return

    path, _ = QFileDialog.getSaveFileName(
        mw, "Save Blender Script", "molecule_blender.py",
        "Blender Python script (*.py)")
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(script)
    except OSError as exc:
        logging.exception("BlenderExportPro: write failed")
        QMessageBox.critical(mw, "Blender Export Pro",
                             f"Could not write file:\n{exc}")
        return

    context.show_status_message("Blender script exported.", 4000)


def quick_export_mesh(context) -> None:
    """Export menu action: write a Blender-free .glb / .usda 3D model."""
    from PyQt6.QtWidgets import QFileDialog, QMessageBox

    from .mesh_export import export_mesh_file

    mw = context.get_main_window()
    mol = context.current_molecule
    if mol is None:
        context.show_status_message(
            "Blender Export Pro: no molecule with 3D coordinates.", 4000)
        return

    path, _ = QFileDialog.getSaveFileName(
        mw, "Save 3D Model", "molecule.glb",
        "glTF binary (*.glb);;USD ASCII (*.usda)")
    if not path:
        return
    try:
        export_mesh_file(mol, _style, path)
    except Exception as exc:
        logging.exception("BlenderExportPro: mesh export failed")
        QMessageBox.critical(mw, "Blender Export Pro",
                             f"3D model export failed:\n{exc}")
        return

    import os
    context.show_status_message(
        f"3D model exported: {os.path.basename(path)}", 4000)
