"""Blender Export Pro configuration dialog (PyQt6).

Tabbed panel bound to a shared StyleConfig instance. Uses the hide-on-close
singleton pattern so state survives while the app runs.
"""

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import style_config as sc
from .blender_codegen import generate_script_from_mol
from .style_config import (
    ATOM_RADIUS_MODES,
    ATOM_SHAPES,
    BLENDER_TARGETS,
    BOND_STYLES,
    MATERIAL_PRESETS,
    SCENE_PRESETS,
    StyleConfig,
)


class BlenderExportDialog(QDialog):
    """Config panel: presets, atoms, bonds, deformation, material, scene, export."""

    def __init__(self, parent, context, cfg: StyleConfig):
        super().__init__(parent)
        self._context = context
        self._cfg = cfg
        self._loading = False

        self.setWindowTitle("Blender Export Pro")
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        self._tabs = QTabWidget(self)
        layout.addWidget(self._tabs)

        self._build_presets_tab()
        self._build_atoms_tab()
        self._build_bonds_tab()
        self._build_deformation_tab()
        self._build_material_tab()
        self._build_scene_tab()
        self._build_export_tab()

        self._refresh_widgets()

    # ------------------------------------------------------------------ tabs

    def _build_presets_tab(self):
        tab = QWidget()
        vbox = QVBoxLayout(tab)
        vbox.addWidget(QLabel("Apply a bundled style preset:"))

        self.preset_combo = QComboBox()
        self._presets = sc.list_presets()
        self.preset_combo.addItems(list(self._presets))
        vbox.addWidget(self.preset_combo)

        apply_btn = QPushButton("Apply Preset")
        apply_btn.clicked.connect(self._apply_preset)
        vbox.addWidget(apply_btn)

        row = QHBoxLayout()
        load_btn = QPushButton("Load Preset File…")
        load_btn.clicked.connect(self._load_preset_file)
        save_btn = QPushButton("Save Preset File…")
        save_btn.clicked.connect(self._save_preset_file)
        row.addWidget(load_btn)
        row.addWidget(save_btn)
        vbox.addLayout(row)

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        vbox.addWidget(reset_btn)
        vbox.addStretch(1)
        self._tabs.addTab(tab, "Presets")

    def _build_atoms_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.atom_shape = QComboBox()
        self.atom_shape.addItems(ATOM_SHAPES)
        form.addRow("Sphere type:", self.atom_shape)

        self.atom_subdivisions = QSpinBox()
        self.atom_subdivisions.setRange(1, 6)
        form.addRow("Subdivisions:", self.atom_subdivisions)

        self.atom_radius_mode = QComboBox()
        self.atom_radius_mode.addItems(ATOM_RADIUS_MODES)
        form.addRow("Radius mode:", self.atom_radius_mode)

        self.atom_radius_scale = self._dspin(0.05, 3.0, 0.05)
        form.addRow("CPK radius scale:", self.atom_radius_scale)

        self.uniform_radius = self._dspin(0.05, 3.0, 0.05)
        form.addRow("Uniform radius (Å):", self.uniform_radius)

        self.atom_jitter = self._dspin(0.0, 1.0, 0.05)
        form.addRow("Squash/stretch jitter:", self.atom_jitter)

        self._tabs.addTab(tab, "Atoms")

    def _build_bonds_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.bond_style = QComboBox()
        self.bond_style.addItems(BOND_STYLES)
        form.addRow("Representation:", self.bond_style)

        self.bond_radius = self._dspin(0.01, 1.0, 0.01)
        form.addRow("Radius (Å):", self.bond_radius)

        self.bond_segments = QSpinBox()
        self.bond_segments.setRange(3, 64)
        form.addRow("Segments:", self.bond_segments)

        self.show_multiple_bonds = QCheckBox("Render double/triple bonds")
        form.addRow(self.show_multiple_bonds)

        self.multi_bond_offset = self._dspin(0.02, 1.0, 0.02)
        form.addRow("Multi-bond offset (Å):", self.multi_bond_offset)

        self._tabs.addTab(tab, "Bonds")

    def _build_deformation_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.deformation_noise = self._dspin(0.0, 2.0, 0.05)
        form.addRow("Noise displacement:", self.deformation_noise)

        self.deformation_noise_scale = self._dspin(0.1, 10.0, 0.1)
        form.addRow("Noise scale:", self.deformation_noise_scale)

        self.deformation_bend = self._dspin(-180.0, 180.0, 5.0)
        form.addRow("Bend (degrees):", self.deformation_bend)

        self.deformation_twist = self._dspin(-180.0, 180.0, 5.0)
        form.addRow("Twist (degrees):", self.deformation_twist)

        self.subdivision_level = QSpinBox()
        self.subdivision_level.setRange(0, 4)
        form.addRow("Subdivision smoothing:", self.subdivision_level)

        self.shade_smooth = QCheckBox("Shade smooth")
        form.addRow(self.shade_smooth)

        self._tabs.addTab(tab, "Deformation")

    def _build_material_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.material_preset = QComboBox()
        self.material_preset.addItems(MATERIAL_PRESETS)
        form.addRow("Material preset:", self.material_preset)

        self.color_mode = QComboBox()
        self.color_mode.addItems(("cpk", "single"))
        form.addRow("Color mode:", self.color_mode)

        self.single_color = QLineEdit()
        self.single_color.setPlaceholderText("#RRGGBB")
        form.addRow("Single color:", self.single_color)

        self.roughness_override = self._dspin(-1.0, 1.0, 0.05)
        self.roughness_override.setToolTip("-1 = use preset default")
        form.addRow("Roughness override:", self.roughness_override)

        self._tabs.addTab(tab, "Material")

    def _build_scene_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.scene_preset = QComboBox()
        self.scene_preset.addItems(SCENE_PRESETS)
        form.addRow("Lighting preset:", self.scene_preset)

        self.add_ground_plane = QCheckBox("Ground plane / shadow catcher")
        form.addRow(self.add_ground_plane)

        self.add_camera = QCheckBox("Auto-framed camera")
        form.addRow(self.add_camera)

        self.turntable_frames = QSpinBox()
        self.turntable_frames.setRange(0, 10000)
        self.turntable_frames.setToolTip("0 disables the turntable animation")
        form.addRow("Turntable frames:", self.turntable_frames)

        self._tabs.addTab(tab, "Scene")

    def _build_export_tab(self):
        tab = QWidget()
        vbox = QVBoxLayout(tab)
        form = QFormLayout()

        self.blender_target = QComboBox()
        self.blender_target.addItems(BLENDER_TARGETS)
        form.addRow("Target Blender:", self.blender_target)

        self.clear_scene = QCheckBox("Clear default scene in script")
        form.addRow(self.clear_scene)

        self.collection_name = QLineEdit()
        form.addRow("Collection name:", self.collection_name)

        self.selection_only = QCheckBox("Export selected atoms only")
        form.addRow(self.selection_only)
        vbox.addLayout(form)

        preview_btn = QPushButton("Update 3D Preview")
        preview_btn.setToolTip(
            'Redraws the 3D view. Select the "Blender Export Pro (Preview)" '
            "style in the 3D panel to see the styled rendering."
        )
        preview_btn.clicked.connect(self._refresh_preview)
        vbox.addWidget(preview_btn)

        export_btn = QPushButton("Generate Blender Script…")
        export_btn.clicked.connect(self._export_script)
        vbox.addWidget(export_btn)
        vbox.addStretch(1)

        self._tabs.addTab(tab, "Export")

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _dspin(minimum, maximum, step):
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setSingleStep(step)
        box.setDecimals(3)
        return box

    _WIDGET_FIELDS = (
        ("atom_shape", "combo"),
        ("atom_subdivisions", "int"),
        ("atom_radius_mode", "combo"),
        ("atom_radius_scale", "float"),
        ("uniform_radius", "float"),
        ("atom_jitter", "float"),
        ("bond_style", "combo"),
        ("bond_radius", "float"),
        ("bond_segments", "int"),
        ("show_multiple_bonds", "bool"),
        ("multi_bond_offset", "float"),
        ("deformation_noise", "float"),
        ("deformation_noise_scale", "float"),
        ("deformation_bend", "float"),
        ("deformation_twist", "float"),
        ("subdivision_level", "int"),
        ("shade_smooth", "bool"),
        ("material_preset", "combo"),
        ("color_mode", "combo"),
        ("single_color", "text"),
        ("roughness_override", "float"),
        ("scene_preset", "combo"),
        ("add_ground_plane", "bool"),
        ("add_camera", "bool"),
        ("turntable_frames", "int"),
        ("blender_target", "combo"),
        ("clear_scene", "bool"),
        ("collection_name", "text"),
    )

    def _refresh_widgets(self):
        """Push StyleConfig values into all widgets."""
        self._loading = True
        try:
            for name, kind in self._WIDGET_FIELDS:
                widget = getattr(self, name)
                value = getattr(self._cfg, name)
                if kind == "combo":
                    idx = widget.findText(str(value))
                    widget.setCurrentIndex(idx if idx >= 0 else 0)
                elif kind == "bool":
                    widget.setChecked(bool(value))
                elif kind == "text":
                    widget.setText(str(value))
                elif kind == "int":
                    widget.setValue(int(value))
                else:
                    widget.setValue(float(value))
        finally:
            self._loading = False

    def _pull_config(self):
        """Read all widgets back into StyleConfig."""
        for name, kind in self._WIDGET_FIELDS:
            widget = getattr(self, name)
            if kind == "combo":
                setattr(self._cfg, name, widget.currentText())
            elif kind == "bool":
                setattr(self._cfg, name, widget.isChecked())
            elif kind == "text":
                setattr(self._cfg, name, widget.text())
            elif kind == "int":
                setattr(self._cfg, name, widget.value())
            else:
                setattr(self._cfg, name, float(widget.value()))

    # ------------------------------------------------------------- actions

    def _apply_preset(self):
        name = self.preset_combo.currentText()
        path = self._presets.get(name)
        if path and sc.load_preset(self._cfg, path):
            self._refresh_widgets()
            self._context.show_status_message(f"Preset applied: {name}", 3000)

    def _load_preset_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Preset", "", "JSON preset (*.json)")
        if path and sc.load_preset(self._cfg, path):
            self._refresh_widgets()
            self._context.show_status_message(
                f"Preset loaded: {os.path.basename(path)}", 3000)

    def _save_preset_file(self):
        self._pull_config()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Preset", "my_style.json", "JSON preset (*.json)")
        if path and sc.save_preset(self._cfg, path):
            self._context.show_status_message(
                f"Preset saved: {os.path.basename(path)}", 3000)

    def _reset_defaults(self):
        self._cfg.reset_defaults()
        self._refresh_widgets()
        self._context.show_status_message("Style reset to defaults.", 3000)

    def _refresh_preview(self):
        self._pull_config()
        try:
            self._context.refresh_3d_view()
        except Exception:
            logging.exception("BlenderExportPro: preview refresh failed")

    def _export_script(self):
        self._pull_config()
        mol = self._context.current_molecule
        if mol is None:
            QMessageBox.warning(self, "Blender Export Pro",
                                "No molecule with 3D coordinates is loaded.")
            return

        selected = None
        if self.selection_only.isChecked():
            selected = self._context.get_selected_atom_indices()
            if not selected:
                QMessageBox.warning(self, "Blender Export Pro",
                                    "Selection-only export: no atoms selected.")
                return

        try:
            script = generate_script_from_mol(mol, self._cfg, selected)
        except Exception as exc:
            logging.exception("BlenderExportPro: codegen failed")
            QMessageBox.critical(self, "Blender Export Pro",
                                 f"Script generation failed:\n{exc}")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Blender Script", "molecule_blender.py",
            "Blender Python script (*.py)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(script)
        except OSError as exc:
            logging.exception("BlenderExportPro: write failed")
            QMessageBox.critical(self, "Blender Export Pro",
                                 f"Could not write file:\n{exc}")
            return

        sc.save_config(self._cfg)
        self._context.show_status_message(
            f"Blender script exported: {os.path.basename(path)}", 4000)

    # ------------------------------------------------------------ lifecycle

    def closeEvent(self, event: QCloseEvent):
        """Hide instead of destroying; persist the last-used config."""
        try:
            self._pull_config()
            sc.save_config(self._cfg)
        except Exception:
            logging.exception("BlenderExportPro: failed to save on close")
        event.ignore()
        self.hide()
