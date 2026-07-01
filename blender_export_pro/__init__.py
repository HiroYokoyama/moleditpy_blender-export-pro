"""Blender Export Pro — MoleditPy V4 plugin.

Adds a stylized/deformed Blender export: a live-preview 3D drawing style, a
tabbed configuration panel, and a self-contained bpy script generator.
MoleditPy never imports bpy; the output is a plain Python text file.
"""

import logging

from .style_config import StyleConfig, load_config, save_config

PLUGIN_NAME = "Blender Export Pro"
PLUGIN_VERSION = "0.1.0"
PLUGIN_AUTHOR = "HiroYokoyama"
PLUGIN_DESCRIPTION = (
    "Stylized/deformed Blender export: cartoon, low-poly, glass, clay and "
    "custom styles with a live 3D preview and one-click bpy script generation."
)
PLUGIN_CATEGORY = "Visualization"
PLUGIN_TAGS = ["blender", "export", "rendering", "visualization"]
PLUGIN_DEPENDENCIES = []
PLUGIN_SUPPORTED_MOLEDITPY_VERSION = ">=4.0.0, <5.0.0"

STYLE_NAME = "Blender Export Pro (Preview)"

_context = None
_style: StyleConfig = StyleConfig()


def initialize(context) -> None:
    """Plugin entry point."""
    global _context, _style
    _context = context
    _style = load_config()

    context.add_menu_action(
        "Visuals/Blender Export Pro…", lambda: open_panel(context))
    context.register_3d_style(STYLE_NAME, _draw_preview)
    context.add_export_action(
        "Export to Blender Script (.py)…", lambda: quick_export(context))

    context.register_save_handler(_style.to_dict)
    context.register_load_handler(_style.update_from_dict)
    context.register_document_reset_handler(_style.reset_defaults)


def get_style() -> StyleConfig:
    """The live, shared StyleConfig instance."""
    return _style


def _draw_preview(mw, mol) -> None:
    from .preview_style import draw_preview_style
    draw_preview_style(mw, mol, _style)


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

    save_config(_style)
    context.show_status_message("Blender script exported.", 4000)
