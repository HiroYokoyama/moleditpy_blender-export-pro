"""Blender Export Pro configuration dialog (PyQt6).

Layout philosophy: a "Quick Start" section on top covers the whole basic
workflow in three clicks (pick preset -> preview in 3D -> export), while every
detailed control stays available in the collapsible Advanced Settings tabs.
Uses the hide-on-close singleton pattern so state survives while the app runs.
"""

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import style_config as sc
from .blender_codegen import generate_script_from_mol
from .style_config import (
    ATOM_RADIUS_MODES,
    ATOM_SHAPES,
    BACKGROUND_MODES,
    BLENDER_TARGETS,
    BOND_COLOR_MODES,
    BOND_STYLES,
    IMAGE_FORMATS,
    LABEL_MODES,
    LIGHT_TYPES,
    MATERIAL_PRESETS,
    RENDER_ENGINES,
    RING_COLOR_MODES,
    RING_STYLES,
    SCENE_PRESETS,
    StyleConfig,
)


class BlenderExportDialog(QDialog):
    """Config panel: quick-start actions plus advanced tabbed settings."""

    def __init__(self, parent, context, cfg: StyleConfig):
        super().__init__(parent)
        self._context = context
        self._cfg = cfg
        self._loading = False

        self.setWindowTitle("Blender Export Pro")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_quick_start())

        self.advanced_toggle = QPushButton("Advanced Settings  ▸")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolTip(
            "Fine-tune atoms, bonds, deformation, materials, scene and export "
            "options. Presets are a starting point — every value can be edited "
            "here.")
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        layout.addWidget(self.advanced_toggle)

        self._tabs = QTabWidget(self)
        self._tabs.setVisible(False)
        layout.addWidget(self._tabs)

        self._build_atoms_tab()
        self._build_bonds_tab()
        self._build_rings_tab()
        self._build_deformation_tab()
        self._build_material_tab()
        self._build_labels_tab()
        self._build_scene_tab()
        self._build_export_tab()
        self._build_preset_files_tab()

        self._refresh_widgets()
        self._connect_live_updates()
        try:
            self._refresh_ring_table()
        except Exception:
            logging.exception("BlenderExportPro: initial ring table fill failed")

    # ------------------------------------------------------------ quick start

    def _build_quick_start(self) -> QGroupBox:
        box = QGroupBox("Quick Start")
        vbox = QVBoxLayout(box)

        steps = QLabel(
            "1. Pick a style  →  2. Preview it in the 3D view  →  "
            "3. Export and run the script in Blender.")
        steps.setWordWrap(True)
        vbox.addWidget(steps)

        row = QHBoxLayout()
        row.addWidget(QLabel("Style:"))
        self.preset_combo = QComboBox()
        self.preset_combo.setToolTip(
            "Bundled style presets. Applying one overwrites the current "
            "settings; tweak them afterwards under Advanced Settings.")
        self._presets = sc.list_presets()
        self.preset_combo.addItems(list(self._presets))
        row.addWidget(self.preset_combo, 1)

        apply_btn = QPushButton("Apply")
        apply_btn.setToolTip("Load the selected preset into the settings.")
        apply_btn.clicked.connect(self._apply_preset)
        row.addWidget(apply_btn)
        vbox.addLayout(row)

        row = QHBoxLayout()
        self.preview_btn = QPushButton("Show in 3D View")
        self.preview_btn.setToolTip(
            "Switch the 3D view to the styled preview. While it is active, "
            "any setting change updates the view immediately.")
        self.preview_btn.clicked.connect(self._activate_preview)
        row.addWidget(self.preview_btn)

        self.standard_btn = QPushButton("Standard View")
        self.standard_btn.setToolTip(
            "Switch the 3D view back to the normal ball-and-stick style.")
        self.standard_btn.clicked.connect(self._activate_standard)
        row.addWidget(self.standard_btn)
        vbox.addLayout(row)

        export_btn = QPushButton("Export Blender Script…")
        export_btn.setToolTip(
            "Generate a self-contained .py file. In Blender: Scripting "
            "workspace → open the file → Run Script. Blender is NOT required "
            "on this machine.")
        export_btn.setDefault(True)
        export_btn.clicked.connect(self._export_script)
        vbox.addWidget(export_btn)

        return box

    def _toggle_advanced(self, checked: bool) -> None:
        self._tabs.setVisible(checked)
        self.advanced_toggle.setText(
            "Advanced Settings  ▾" if checked else "Advanced Settings  ▸")
        if not checked:
            self.adjustSize()

    # ------------------------------------------------------------------ tabs

    def _build_atoms_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.atom_shape = QComboBox()
        self.atom_shape.addItems(ATOM_SHAPES)
        self.atom_shape.setToolTip(
            "uv_sphere: smooth classic spheres · ico_sphere: low-poly look · "
            "metaball: blobs that merge into an organic surface (Blender only).")
        form.addRow("Sphere type:", self.atom_shape)

        self.atom_subdivisions = QSpinBox()
        self.atom_subdivisions.setRange(1, 6)
        self.atom_subdivisions.setToolTip(
            "Mesh detail. Low = faceted/low-poly, high = smooth (heavier).")
        form.addRow("Subdivisions:", self.atom_subdivisions)

        self.atom_radius_mode = QComboBox()
        self.atom_radius_mode.addItems(ATOM_RADIUS_MODES)
        self.atom_radius_mode.setToolTip(
            "cpk: element-dependent van der Waals radii (RDKit, same as the "
            "main app) · uniform: same radius for all atoms.")
        form.addRow("Radius mode:", self.atom_radius_mode)

        self.atom_radius_scale = self._dspin(
            0.05, 3.0, 0.05,
            "Multiplier on the RDKit van der Waals radius. 0.3 = "
            "ball-and-stick (main app look), 1.0 = space-filling.")
        form.addRow("vdW radius scale:", self.atom_radius_scale)

        self.uniform_radius = self._dspin(
            0.05, 3.0, 0.05, "Radius in Angstrom used when radius mode is 'uniform'.")
        form.addRow("Uniform radius (Å):", self.uniform_radius)

        self.hide_hydrogens = QCheckBox("Omit hydrogens")
        self.hide_hydrogens.setToolTip(
            "Hide all hydrogen atoms and their bonds — the common "
            "'heavy-atoms only' view.")
        form.addRow(self.hide_hydrogens)

        self.hydrogen_scale = self._dspin(
            0.0, 2.0, 0.05,
            "Extra size factor for hydrogen atoms only. 0.5 = half-size H "
            "(popular for cleaner renders), 1.0 = normal.")
        form.addRow("Hydrogen size:", self.hydrogen_scale)

        self.atom_jitter = self._dspin(
            0.0, 1.0, 0.05,
            "Random squash & stretch per atom. 0 = perfect spheres, "
            "higher = hand-made / cartoon feel.")
        form.addRow("Squash/stretch jitter:", self.atom_jitter)

        group = QGroupBox("Selected-Atom Styles")
        gform = QFormLayout(group)
        group.setToolTip(
            "Select atoms in the 2D/3D editor first, then restyle just "
            "those atoms here. Overrides are saved with the project.")

        row = QHBoxLayout()
        self.selection_scale = self._dspin(
            0.05, 5.0, 0.05,
            "Multiplier on the normal radius of each selected atom.")
        self.selection_scale.setValue(1.5)
        row.addWidget(self.selection_scale)
        scale_btn = QPushButton("Scale Selected Atoms")
        scale_btn.clicked.connect(self._scale_selected_atoms)
        row.addWidget(scale_btn)
        gform.addRow("Scale factor:", row)

        row = QHBoxLayout()
        self.selection_radius = self._dspin(
            0.01, 5.0, 0.05,
            "Absolute radius in Angstrom for each selected atom.")
        self.selection_radius.setValue(0.5)
        row.addWidget(self.selection_radius)
        radius_btn = QPushButton("Set Radius of Selected")
        radius_btn.clicked.connect(self._set_selected_atom_radius)
        row.addWidget(radius_btn)
        gform.addRow("Radius (Å):", row)

        row = QHBoxLayout()
        self.selection_color = QLineEdit("#FF8800")
        self.selection_color.setToolTip(
            "#RRGGBB color applied to each selected atom.")
        row.addWidget(self.selection_color)
        color_btn = QPushButton("Color Selected Atoms")
        color_btn.clicked.connect(self._color_selected_atoms)
        row.addWidget(color_btn)
        gform.addRow("Color:", row)

        row = QHBoxLayout()
        hide_btn = QPushButton("Hide Selected Atoms")
        hide_btn.setToolTip("Hide the selected atoms and their bonds entirely.")
        hide_btn.clicked.connect(self._hide_selected_atoms)
        row.addWidget(hide_btn)
        show_btn = QPushButton("Show Selected Atoms")
        show_btn.setToolTip("Un-hide the selected atoms.")
        show_btn.clicked.connect(self._show_selected_atoms)
        row.addWidget(show_btn)
        gform.addRow("Visibility:", row)

        row = QHBoxLayout()
        reset_sel_btn = QPushButton("Reset Selected")
        reset_sel_btn.setToolTip(
            "Remove size, color and hide overrides from the selected atoms.")
        reset_sel_btn.clicked.connect(self._reset_selected_atom_sizes)
        row.addWidget(reset_sel_btn)
        reset_all_btn = QPushButton("Reset All")
        reset_all_btn.setToolTip("Remove all per-atom overrides.")
        reset_all_btn.clicked.connect(self._reset_all_atom_sizes)
        row.addWidget(reset_all_btn)
        gform.addRow(row)

        self.atom_override_label = QLabel()
        gform.addRow(self.atom_override_label)
        self._update_atom_override_label()

        form.addRow(group)

        self._tabs.addTab(tab, "Atoms")

    def _build_bonds_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.bond_style = QComboBox()
        self.bond_style.addItems(BOND_STYLES)
        self.bond_style.setToolTip(
            "cylinder: rigid mesh cylinders · curve: Blender curves with a "
            "bevel — stays editable/bendable inside Blender.")
        form.addRow("Representation:", self.bond_style)

        self.bond_radius = self._dspin(
            0.01, 1.0, 0.01, "Bond thickness in Angstrom.")
        form.addRow("Radius (Å):", self.bond_radius)

        self.bond_segments = QSpinBox()
        self.bond_segments.setRange(3, 64)
        self.bond_segments.setToolTip(
            "Cylinder cross-section vertices. 6 = low-poly, 24+ = smooth.")
        form.addRow("Segments:", self.bond_segments)

        self.show_multiple_bonds = QCheckBox("Render double/triple bonds")
        self.show_multiple_bonds.setToolTip(
            "Draw 2 or 3 parallel cylinders for double/triple bonds. "
            "Off = one cylinder per bond (cleaner for stylized looks).")
        form.addRow(self.show_multiple_bonds)

        self.multi_bond_offset = self._dspin(
            0.02, 1.0, 0.02, "Spacing between the parallel cylinders.")
        form.addRow("Multi-bond offset (Å):", self.multi_bond_offset)

        self.bond_color_mode = QComboBox()
        self.bond_color_mode.addItems(BOND_COLOR_MODES)
        self.bond_color_mode.setToolTip(
            "atoms: each bond blends the colors of its two atoms · "
            "single: one fixed color for every bond.")
        form.addRow("Bond color:", self.bond_color_mode)

        self.bond_color = QLineEdit()
        self.bond_color.setPlaceholderText("#RRGGBB")
        self.bond_color.setToolTip("Bond color when the mode is 'single'.")
        form.addRow("Single bond color:", self.bond_color)

        self._tabs.addTab(tab, "Bonds")

    def _build_rings_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.ring_style = QComboBox()
        self.ring_style.addItems(RING_STYLES)
        self.ring_style.setToolTip(
            "panel: draw rings (benzene etc.) as filled polygon plates — a "
            "hexagonal panel for a six-membered ring. none: bonds only.")
        form.addRow("Ring rendering:", self.ring_style)

        self.ring_aromatic_only = QCheckBox("Aromatic rings only")
        self.ring_aromatic_only.setToolTip(
            "On: only aromatic rings like benzene get a panel. "
            "Off: every small ring (3-8 atoms), e.g. cyclohexane too.")
        form.addRow(self.ring_aromatic_only)

        self.ring_scale = self._dspin(
            0.1, 1.5, 0.05,
            "Panel size relative to the ring atoms. <1 insets the panel "
            "corners toward the ring center; 1.0 touches the atoms.")
        form.addRow("Panel size:", self.ring_scale)

        self.ring_thickness = self._dspin(
            0.0, 1.0, 0.02,
            "Plate thickness in Angstrom. 0 = flat sheet, "
            "0.05-0.15 = solid plate.")
        form.addRow("Plate thickness (Å):", self.ring_thickness)

        self.ring_color_mode = QComboBox()
        self.ring_color_mode.addItems(RING_COLOR_MODES)
        self.ring_color_mode.setToolTip(
            "custom: use the panel color below · match_atoms: average of "
            "the ring atoms' colors.")
        form.addRow("Panel color mode:", self.ring_color_mode)

        self.ring_color = QLineEdit()
        self.ring_color.setPlaceholderText("#RRGGBB")
        self.ring_color.setToolTip("Panel color when the mode is 'custom'.")
        form.addRow("Panel color:", self.ring_color)

        self.ring_opacity = self._dspin(
            0.0, 1.0, 0.05,
            "Panel transparency. ~0.5 = stained-glass look, 1.0 = solid.")
        form.addRow("Panel opacity:", self.ring_opacity)

        self.ring_hide_atoms = QCheckBox("Hide atoms of paneled rings")
        self.ring_hide_atoms.setToolTip(
            "Show only the ring plate, not the ball atoms — a clean "
            "aromatic-ring figure look. Per-ring overrides in the table "
            "below take precedence.")
        form.addRow(self.ring_hide_atoms)

        self.ring_hide_bonds = QCheckBox("Also hide the ring's internal bonds")
        self.ring_hide_bonds.setToolTip(
            "Additionally hide the bonds inside paneled rings (substituent "
            "bonds to the ring are kept).")
        form.addRow(self.ring_hide_bonds)

        hint = QLabel(
            "Per-ring styles — select a row to highlight that ring in the "
            "3D preview; edit a row to style just that ring:")
        hint.setWordWrap(True)
        form.addRow(hint)

        self.ring_table = QTableWidget(0, 7)
        self.ring_table.setHorizontalHeaderLabels(
            ["Ring", "Panel", "Atoms", "Color", "Opacity", "Thickness", "Size"])
        self.ring_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.ring_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.ring_table.verticalHeader().setVisible(False)
        self.ring_table.setMinimumHeight(140)
        self.ring_table.setToolTip(
            "One row per detected ring. Changes here override the global "
            "ring settings above for that ring only.")
        self.ring_table.currentCellChanged.connect(self._on_ring_row_selected)
        form.addRow(self.ring_table)

        row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh Ring List")
        refresh_btn.setToolTip(
            "Re-detect rings from the current molecule (use after loading "
            "or editing a molecule).")
        refresh_btn.clicked.connect(self._refresh_ring_table)
        row.addWidget(refresh_btn)

        reset_ring_btn = QPushButton("Reset Selected Ring")
        reset_ring_btn.setToolTip(
            "Remove the per-ring override so the selected ring follows the "
            "global settings again.")
        reset_ring_btn.clicked.connect(self._reset_selected_ring)
        row.addWidget(reset_ring_btn)
        form.addRow(row)

        self._ring_keys_by_row = []
        self.ring_aromatic_only.toggled.connect(self._refresh_ring_table)
        self.ring_hide_atoms.toggled.connect(self._refresh_ring_table)

        self._tabs.addTab(tab, "Rings")

    def _build_deformation_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.deformation_noise = self._dspin(
            0.0, 2.0, 0.05,
            "Organic surface wobble (Blender Displace modifier). "
            "0 = clean, 0.1-0.3 = clay/hand-made.")
        form.addRow("Noise displacement:", self.deformation_noise)

        self.deformation_noise_scale = self._dspin(
            0.1, 10.0, 0.1,
            "Noise feature size. Small = fine grain, large = broad waves.")
        form.addRow("Noise scale:", self.deformation_noise_scale)

        self.deformation_bend = self._dspin(
            -180.0, 180.0, 5.0, "Bend every object (SimpleDeform modifier).")
        form.addRow("Bend (degrees):", self.deformation_bend)

        self.deformation_twist = self._dspin(
            -180.0, 180.0, 5.0, "Twist every object (SimpleDeform modifier).")
        form.addRow("Twist (degrees):", self.deformation_twist)

        self.subdivision_level = QSpinBox()
        self.subdivision_level.setRange(0, 4)
        self.subdivision_level.setToolTip(
            "Subdivision Surface smoothing applied in Blender. "
            "2 gives soft, rounded 'inflated' shapes.")
        form.addRow("Subdivision smoothing:", self.subdivision_level)

        self.shade_smooth = QCheckBox("Shade smooth")
        self.shade_smooth.setToolTip(
            "Smooth surface normals. Turn OFF for faceted low-poly styles.")
        form.addRow(self.shade_smooth)

        self._tabs.addTab(tab, "Deformation")

    def _build_material_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.material_preset = QComboBox()
        self.material_preset.addItems(MATERIAL_PRESETS)
        self.material_preset.setToolTip(
            "Surface look (Principled BSDF in Blender): glass and ice are "
            "transparent, neon glows, gold/copper/chrome are metallic, "
            "gummy is translucent.")
        form.addRow("Material preset:", self.material_preset)

        self.color_mode = QComboBox()
        self.color_mode.addItems(("cpk", "single"))
        self.color_mode.setToolTip(
            "cpk: element colors (C grey, O red, …) · single: one color "
            "for the whole molecule.")
        form.addRow("Color mode:", self.color_mode)

        self.single_color = QLineEdit()
        self.single_color.setPlaceholderText("#RRGGBB")
        self.single_color.setToolTip("Hex color used when color mode is 'single'.")
        form.addRow("Single color:", self.single_color)

        self.roughness_override = self._dspin(
            -1.0, 1.0, 0.05,
            "-1 = use the material preset's default. 0 = mirror-glossy, "
            "1 = fully matte.")
        form.addRow("Roughness override:", self.roughness_override)

        group = QGroupBox("Element Colors")
        gform = QFormLayout(group)
        group.setToolTip(
            "Recolor a whole element everywhere (e.g. all carbons). Leave "
            "empty to use the main app's CPK colors.")

        row = QHBoxLayout()
        self.element_symbol = QLineEdit()
        self.element_symbol.setPlaceholderText("e.g. C")
        self.element_symbol.setMaxLength(3)
        self.element_symbol.setToolTip("Element symbol to recolor.")
        row.addWidget(self.element_symbol)
        self.element_color = QLineEdit()
        self.element_color.setPlaceholderText("#RRGGBB")
        row.addWidget(self.element_color)
        set_btn = QPushButton("Set")
        set_btn.clicked.connect(self._set_element_color)
        row.addWidget(set_btn)
        gform.addRow("Element / color:", row)

        self.element_color_label = QLabel()
        gform.addRow(self.element_color_label)

        clear_btn = QPushButton("Clear Element Colors")
        clear_btn.clicked.connect(self._clear_element_colors)
        gform.addRow(clear_btn)
        form.addRow(group)
        self._update_element_color_label()

        self._tabs.addTab(tab, "Material")

    def _build_labels_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.label_mode = QComboBox()
        self.label_mode.addItems(LABEL_MODES)
        self.label_mode.setToolTip(
            "Add 3D text next to each atom: element symbol, symbol+index "
            "(C0, C1, …) or index only. 'none' = no labels.")
        form.addRow("Label text:", self.label_mode)

        self.label_size = self._dspin(
            0.05, 3.0, 0.05, "Text height in Blender units (Angstrom scale).")
        form.addRow("Text size:", self.label_size)

        self.label_color = QLineEdit()
        self.label_color.setPlaceholderText("#RRGGBB")
        self.label_color.setToolTip("Label text color.")
        form.addRow("Text color:", self.label_color)

        self.label_offset = self._dspin(
            0.5, 5.0, 0.1,
            "How far the label sits from the atom center, as a multiple of "
            "the atom radius.")
        form.addRow("Offset:", self.label_offset)

        self.label_face_camera = QCheckBox("Always face the camera")
        self.label_face_camera.setToolTip(
            "Adds a tracking constraint so labels stay readable from the "
            "camera (needs the auto camera or an existing one).")
        form.addRow(self.label_face_camera)

        self._tabs.addTab(tab, "Labels")

    def _build_scene_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.scene_preset = QComboBox()
        self.scene_preset.addItems(SCENE_PRESETS)
        self.scene_preset.setToolTip(
            "studio: bright 3-point lighting · dark: moody backdrop (best "
            "for neon/glass/gold) · none: no lights or world, bring your own.")
        form.addRow("Lighting preset:", self.scene_preset)

        self.add_ground_plane = QCheckBox("Ground plane / shadow catcher")
        self.add_ground_plane.setToolTip(
            "Adds a floor below the molecule that catches shadows.")
        form.addRow(self.add_ground_plane)

        self.add_camera = QCheckBox("Auto-framed camera")
        self.add_camera.setToolTip(
            "Adds a camera aimed at the molecule, framed to its size — "
            "the scene is render-ready immediately.")
        form.addRow(self.add_camera)

        self.turntable_frames = QSpinBox()
        self.turntable_frames.setRange(0, 10000)
        self.turntable_frames.setToolTip(
            "Adds a 360° rotation animation over this many frames. "
            "0 = no animation. 240 frames ≈ 10 s at 24 fps.")
        form.addRow("Turntable frames:", self.turntable_frames)

        self._build_lighting_group(form)

        self.background_mode = QComboBox()
        self.background_mode.addItems(BACKGROUND_MODES)
        self.background_mode.setToolTip(
            "preset: light/dark backdrop from the lighting preset · "
            "color: the custom color below · hdri: an environment image "
            "file (.hdr/.exr, also lights the scene) · transparent: "
            "renders with a see-through background (for compositing).")
        form.addRow("Background:", self.background_mode)

        self.background_color = QLineEdit()
        self.background_color.setPlaceholderText("#RRGGBB")
        self.background_color.setToolTip(
            "Background color when the mode is 'color'.")
        form.addRow("Background color:", self.background_color)

        row = QHBoxLayout()
        self.hdri_path = QLineEdit()
        self.hdri_path.setPlaceholderText("environment image (.hdr / .exr)")
        self.hdri_path.setToolTip(
            "Environment image used when the mode is 'hdri'. The path is "
            "written into the script, so keep the file available on the "
            "machine running Blender.")
        row.addWidget(self.hdri_path)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_hdri)
        row.addWidget(browse_btn)
        form.addRow("HDRI file:", row)

        self.hdri_strength = self._dspin(
            0.0, 20.0, 0.1, "Brightness of the HDRI environment lighting.")
        form.addRow("HDRI strength:", self.hdri_strength)

        self.render_engine = QComboBox()
        self.render_engine.addItems(RENDER_ENGINES)
        self.render_engine.setToolTip(
            "keep: don't change Blender's render settings · cycles: "
            "photorealistic (glass/HDRI look best) · eevee: fast preview "
            "quality.")
        form.addRow("Render engine:", self.render_engine)

        self.render_samples = QSpinBox()
        self.render_samples.setRange(1, 8192)
        self.render_samples.setToolTip(
            "Render quality (samples). Higher = cleaner but slower.")
        form.addRow("Render samples:", self.render_samples)

        row = QHBoxLayout()
        self.resolution_x = QSpinBox()
        self.resolution_x.setRange(16, 16384)
        self.resolution_y = QSpinBox()
        self.resolution_y.setRange(16, 16384)
        row.addWidget(self.resolution_x)
        row.addWidget(QLabel("×"))
        row.addWidget(self.resolution_y)
        for box in (self.resolution_x, self.resolution_y):
            box.setToolTip("Output resolution (applied when engine ≠ keep).")
        form.addRow("Resolution:", row)

        self.render_on_run = QCheckBox("Render an image when the script runs")
        self.render_on_run.setToolTip(
            "The script saves a rendered image automatically — no need to "
            "press F12 in Blender. Great for headless/batch rendering: "
            "blender -b -P script.py")
        form.addRow(self.render_on_run)

        row = QHBoxLayout()
        self.render_output_path = QLineEdit()
        self.render_output_path.setPlaceholderText("output image path")
        self.render_output_path.setToolTip(
            "Where the rendered image is written. For turntable animations "
            "this is the frame-name prefix.")
        row.addWidget(self.render_output_path)
        out_btn = QPushButton("Browse…")
        out_btn.clicked.connect(self._browse_render_output)
        row.addWidget(out_btn)
        form.addRow("Image output:", row)

        self.image_format = QComboBox()
        self.image_format.addItems(IMAGE_FORMATS)
        self.image_format.setToolTip("Output image file format.")
        form.addRow("Image format:", self.image_format)

        self._tabs.addTab(tab, "Scene")

    def _build_lighting_group(self, form):
        group = QGroupBox("Lighting")
        gform = QFormLayout(group)

        self.key_light_azimuth = self._dspin(
            -180.0, 180.0, 5.0, "Key light direction around the molecule.")
        gform.addRow("Key azimuth (°):", self.key_light_azimuth)
        self.key_light_elevation = self._dspin(
            -90.0, 90.0, 5.0, "Key light height above the horizon.")
        gform.addRow("Key elevation (°):", self.key_light_elevation)
        self.key_light_strength = self._dspin(
            0.0, 10.0, 0.1, "Multiplier on the key light power.")
        gform.addRow("Key strength:", self.key_light_strength)
        self.light_distance_scale = self._dspin(
            0.5, 10.0, 0.5, "Light distance = this × molecule size.")
        gform.addRow("Light distance:", self.light_distance_scale)

        self.use_custom_lights = QCheckBox("Use custom lights (below)")
        self.use_custom_lights.setToolTip(
            "Replace the automatic 3-point rig with your own list of lights.")
        gform.addRow(self.use_custom_lights)

        self.lights_table = QTableWidget(0, 7)
        self.lights_table.setHorizontalHeaderLabels(
            ["Name", "Type", "Azimuth", "Elevation", "Distance", "Energy",
             "Color"])
        self.lights_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.lights_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.lights_table.verticalHeader().setVisible(False)
        self.lights_table.setMinimumHeight(120)
        self.lights_table.setToolTip(
            "Each row is one light with its own type, position, intensity "
            "(energy) and color.")
        gform.addRow(self.lights_table)

        row = QHBoxLayout()
        add_btn = QPushButton("Add Light")
        add_btn.clicked.connect(self._add_light)
        row.addWidget(add_btn)
        del_btn = QPushButton("Remove Selected Light")
        del_btn.clicked.connect(self._remove_light)
        row.addWidget(del_btn)
        gform.addRow(row)

        form.addRow(group)
        self._refresh_lights_table()

    def _build_export_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.blender_target = QComboBox()
        self.blender_target.addItems(BLENDER_TARGETS)
        self.blender_target.setToolTip(
            "Blender version you will run the script in. The script is "
            "written defensively, so this mostly affects the header comment.")
        form.addRow("Target Blender:", self.blender_target)

        self.clear_scene = QCheckBox("Clear default scene in script")
        self.clear_scene.setToolTip(
            "The script deletes Blender's default cube/light/camera first. "
            "Disable to add the molecule to an existing scene.")
        form.addRow(self.clear_scene)

        self.collection_name = QLineEdit()
        self.collection_name.setToolTip(
            "Blender collection that will contain all molecule objects.")
        form.addRow("Collection name:", self.collection_name)

        self.selection_only = QCheckBox("Export selected atoms only")
        self.selection_only.setToolTip(
            "Export only the atoms currently selected in the editor "
            "(bonds to unselected atoms are dropped).")
        form.addRow(self.selection_only)

        self._tabs.addTab(tab, "Export Options")

    def _build_preset_files_tab(self):
        tab = QWidget()
        vbox = QVBoxLayout(tab)
        vbox.addWidget(QLabel(
            "Save the current settings as a shareable JSON preset,\n"
            "or load one from disk."))

        row = QHBoxLayout()
        load_btn = QPushButton("Load Preset File…")
        load_btn.clicked.connect(self._load_preset_file)
        save_btn = QPushButton("Save Preset File…")
        save_btn.clicked.connect(self._save_preset_file)
        row.addWidget(load_btn)
        row.addWidget(save_btn)
        vbox.addLayout(row)

        reset_btn = QPushButton("Reset All Settings to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        vbox.addWidget(reset_btn)
        vbox.addStretch(1)
        self._tabs.addTab(tab, "Preset Files")

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _dspin(minimum, maximum, step, tooltip=""):
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setSingleStep(step)
        box.setDecimals(3)
        if tooltip:
            box.setToolTip(tooltip)
        return box

    _WIDGET_FIELDS = (
        ("atom_shape", "combo"),
        ("atom_subdivisions", "int"),
        ("atom_radius_mode", "combo"),
        ("atom_radius_scale", "float"),
        ("uniform_radius", "float"),
        ("hide_hydrogens", "bool"),
        ("hydrogen_scale", "float"),
        ("atom_jitter", "float"),
        ("bond_style", "combo"),
        ("bond_radius", "float"),
        ("bond_segments", "int"),
        ("show_multiple_bonds", "bool"),
        ("multi_bond_offset", "float"),
        ("bond_color_mode", "combo"),
        ("bond_color", "text"),
        ("ring_style", "combo"),
        ("ring_aromatic_only", "bool"),
        ("ring_scale", "float"),
        ("ring_thickness", "float"),
        ("ring_color_mode", "combo"),
        ("ring_color", "text"),
        ("ring_opacity", "float"),
        ("ring_hide_atoms", "bool"),
        ("ring_hide_bonds", "bool"),
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
        ("label_mode", "combo"),
        ("label_size", "float"),
        ("label_color", "text"),
        ("label_offset", "float"),
        ("label_face_camera", "bool"),
        ("scene_preset", "combo"),
        ("add_ground_plane", "bool"),
        ("add_camera", "bool"),
        ("turntable_frames", "int"),
        ("key_light_azimuth", "float"),
        ("key_light_elevation", "float"),
        ("key_light_strength", "float"),
        ("light_distance_scale", "float"),
        ("use_custom_lights", "bool"),
        ("background_mode", "combo"),
        ("background_color", "text"),
        ("hdri_path", "text"),
        ("hdri_strength", "float"),
        ("render_engine", "combo"),
        ("render_samples", "int"),
        ("resolution_x", "int"),
        ("resolution_y", "int"),
        ("render_on_run", "bool"),
        ("render_output_path", "text"),
        ("image_format", "combo"),
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

    def _connect_live_updates(self):
        """While the preview style is active, changes redraw the 3D view."""
        for name, kind in self._WIDGET_FIELDS:
            widget = getattr(self, name)
            if kind == "combo":
                widget.currentTextChanged.connect(self._on_setting_changed)
            elif kind == "bool":
                widget.toggled.connect(self._on_setting_changed)
            elif kind == "text":
                widget.editingFinished.connect(self._on_setting_changed)
            else:
                widget.valueChanged.connect(self._on_setting_changed)

    def _on_setting_changed(self, *_args):
        if self._loading:
            return
        self._pull_config()
        self._refresh_preview_if_active()

    def _refresh_preview_if_active(self):
        from . import is_preview_style_active
        try:
            if is_preview_style_active(self._context):
                self._context.refresh_3d_view()
        except Exception:
            logging.exception("BlenderExportPro: live preview refresh failed")

    def _browse_hdri(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Environment Image", "",
            "Environment images (*.hdr *.exr *.png *.jpg *.jpeg);;All files (*)")
        if path:
            self.hdri_path.setText(path)
            idx = self.background_mode.findText("hdri")
            if idx >= 0:
                self.background_mode.setCurrentIndex(idx)
            self._on_setting_changed()

    def _browse_render_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Rendered Image Output", "render.png",
            "Images (*.png *.jpg *.jpeg *.tif *.exr *.webp);;All files (*)")
        if path:
            self.render_output_path.setText(path)
            self.render_on_run.setChecked(True)
            self._on_setting_changed()

    # -------------------------------------------------------- element colors

    def _update_element_color_label(self):
        count = len(self._cfg.element_colors or {})
        if count:
            pairs = ", ".join(f"{k}={v}" for k, v in
                              list(self._cfg.element_colors.items())[:6])
            self.element_color_label.setText(f"Overrides: {pairs}")
        else:
            self.element_color_label.setText("No element color overrides.")

    def _set_element_color(self):
        symbol = self.element_symbol.text().strip()
        color = self.element_color.text().strip()
        if not symbol or not color:
            return
        symbol = symbol[0].upper() + symbol[1:].lower()
        if not isinstance(self._cfg.element_colors, dict):
            self._cfg.element_colors = {}
        self._cfg.element_colors[symbol] = color
        self._update_element_color_label()
        self._refresh_preview_if_active()
        self._context.show_status_message(
            f"Element color set: {symbol} = {color}", 3000)

    def _clear_element_colors(self):
        self._cfg.element_colors = {}
        self._update_element_color_label()
        self._refresh_preview_if_active()

    # ------------------------------------------------------ atom size tools

    def _selected_atoms_or_warn(self):
        try:
            selected = self._context.get_selected_atom_indices()
        except Exception:
            logging.exception("BlenderExportPro: selection lookup failed")
            selected = None
        if not selected:
            QMessageBox.information(
                self, "Blender Export Pro",
                "No atoms are selected. Select atoms in the 2D or 3D "
                "editor first.")
            return None
        return selected

    def _update_atom_override_label(self):
        sizes = len(self._cfg.atom_overrides or {})
        colors = len(self._cfg.atom_color_overrides or {})
        hidden = sorted((self._cfg.atom_hidden or {}), key=lambda s: int(s)
                        if s.isdigit() else 0)
        parts = []
        if sizes:
            parts.append(f"custom sizes: {sizes}")
        if colors:
            parts.append(f"custom colors: {colors}")
        if hidden:
            shown = ", ".join(hidden[:12]) + ("…" if len(hidden) > 12 else "")
            parts.append(f"hidden atoms [{shown}]")
        self.atom_override_label.setText(
            " · ".join(parts) if parts else "No per-atom overrides.")

    def _hide_selected_atoms(self):
        selected = self._selected_atoms_or_warn()
        if selected is None:
            return
        if not isinstance(self._cfg.atom_hidden, dict):
            self._cfg.atom_hidden = {}
        for idx in selected:
            self._cfg.atom_hidden[str(int(idx))] = True
        self._update_atom_override_label()
        self._refresh_preview_if_active()
        self._context.show_status_message(
            f"Hid {len(selected)} atom(s).", 3000)

    def _show_selected_atoms(self):
        selected = self._selected_atoms_or_warn()
        if selected is None:
            return
        if isinstance(self._cfg.atom_hidden, dict):
            for idx in selected:
                self._cfg.atom_hidden.pop(str(int(idx)), None)
        self._update_atom_override_label()
        self._refresh_preview_if_active()

    def _apply_atom_override(self, override: dict):
        selected = self._selected_atoms_or_warn()
        if selected is None:
            return
        if not isinstance(self._cfg.atom_overrides, dict):
            self._cfg.atom_overrides = {}
        for idx in selected:
            self._cfg.atom_overrides[str(int(idx))] = dict(override)
        self._update_atom_override_label()
        self._refresh_preview_if_active()
        self._context.show_status_message(
            f"Size applied to {len(selected)} atom(s).", 3000)

    def _scale_selected_atoms(self):
        self._pull_config()
        self._apply_atom_override({"scale": float(self.selection_scale.value())})

    def _set_selected_atom_radius(self):
        self._pull_config()
        self._apply_atom_override({"radius": float(self.selection_radius.value())})

    def _color_selected_atoms(self):
        self._pull_config()
        selected = self._selected_atoms_or_warn()
        if selected is None:
            return
        color = self.selection_color.text().strip()
        if not color:
            return
        if not isinstance(self._cfg.atom_color_overrides, dict):
            self._cfg.atom_color_overrides = {}
        for idx in selected:
            self._cfg.atom_color_overrides[str(int(idx))] = color
        self._update_atom_override_label()
        self._refresh_preview_if_active()
        self._context.show_status_message(
            f"Color applied to {len(selected)} atom(s).", 3000)

    def _reset_selected_atom_sizes(self):
        selected = self._selected_atoms_or_warn()
        if selected is None:
            return
        for overrides in (self._cfg.atom_overrides,
                          self._cfg.atom_color_overrides,
                          self._cfg.atom_hidden):
            if isinstance(overrides, dict):
                for idx in selected:
                    overrides.pop(str(int(idx)), None)
        self._update_atom_override_label()
        self._refresh_preview_if_active()

    def _reset_all_atom_sizes(self):
        self._cfg.atom_overrides = {}
        self._cfg.atom_color_overrides = {}
        self._cfg.atom_hidden = {}
        self._update_atom_override_label()
        self._refresh_preview_if_active()
        self._context.show_status_message("All per-atom overrides reset.", 3000)

    # ------------------------------------------------------------- lights

    def _refresh_lights_table(self):
        from .style_config import default_light
        table = self.lights_table
        self._loading = True
        try:
            table.setRowCount(0)
            self._light_names = []
            lights = (self._cfg.custom_lights
                      if isinstance(self._cfg.custom_lights, dict) else {})
            table.setRowCount(len(lights))
            for r, (name, spec) in enumerate(lights.items()):
                base = default_light()
                if isinstance(spec, dict):
                    base.update(spec)
                self._light_names.append(name)

                name_edit = QLineEdit(str(name))
                table.setCellWidget(r, 0, name_edit)
                type_cb = QComboBox()
                type_cb.addItems(LIGHT_TYPES)
                type_cb.setCurrentText(str(base["type"]))
                table.setCellWidget(r, 1, type_cb)
                az = self._dspin(-180.0, 180.0, 5.0)
                az.setValue(float(base["azimuth"]))
                table.setCellWidget(r, 2, az)
                el = self._dspin(-90.0, 90.0, 5.0)
                el.setValue(float(base["elevation"]))
                table.setCellWidget(r, 3, el)
                dist = self._dspin(0.5, 20.0, 0.5)
                dist.setValue(float(base["distance"]))
                table.setCellWidget(r, 4, dist)
                energy = QDoubleSpinBox()
                energy.setRange(0.0, 1_000_000.0)
                energy.setDecimals(0)
                energy.setSingleStep(50.0)
                energy.setValue(float(base["energy"]))
                energy.setToolTip("Light intensity (power).")
                table.setCellWidget(r, 5, energy)
                color = QLineEdit(str(base["color"]))
                color.setToolTip("Light color #RRGGBB.")
                table.setCellWidget(r, 6, color)

                handler = lambda *_a: self._rebuild_custom_lights()
                name_edit.editingFinished.connect(handler)
                type_cb.currentTextChanged.connect(handler)
                az.valueChanged.connect(handler)
                el.valueChanged.connect(handler)
                dist.valueChanged.connect(handler)
                energy.valueChanged.connect(handler)
                color.editingFinished.connect(handler)
            table.resizeColumnsToContents()
        finally:
            self._loading = False

    def _rebuild_custom_lights(self):
        if self._loading:
            return
        table = self.lights_table
        lights = {}
        for r in range(table.rowCount()):
            name = table.cellWidget(r, 0).text().strip() or "Light"
            unique, k = name, 1
            while unique in lights:
                unique = f"{name}_{k}"
                k += 1
            lights[unique] = {
                "type": table.cellWidget(r, 1).currentText(),
                "azimuth": float(table.cellWidget(r, 2).value()),
                "elevation": float(table.cellWidget(r, 3).value()),
                "distance": float(table.cellWidget(r, 4).value()),
                "energy": float(table.cellWidget(r, 5).value()),
                "color": table.cellWidget(r, 6).text().strip() or "#FFFFFF",
            }
        self._cfg.custom_lights = lights

    def _add_light(self):
        from .style_config import default_light
        if not isinstance(self._cfg.custom_lights, dict):
            self._cfg.custom_lights = {}
        base, n = "Light", len(self._cfg.custom_lights) + 1
        name = f"{base}{n}"
        while name in self._cfg.custom_lights:
            n += 1
            name = f"{base}{n}"
        self._cfg.custom_lights[name] = default_light()
        self.use_custom_lights.setChecked(True)
        self._refresh_lights_table()

    def _remove_light(self):
        row = self.lights_table.currentRow()
        if 0 <= row < len(self._light_names):
            name = self._light_names[row]
            if isinstance(self._cfg.custom_lights, dict):
                self._cfg.custom_lights.pop(name, None)
            self._refresh_lights_table()

    # ---------------------------------------------------------- ring table

    def _refresh_ring_table(self, *_args):
        """Rebuild the per-ring table from the current molecule."""
        from .blender_codegen import extract_rings, resolve_ring_style, ring_key

        table = self.ring_table
        self._loading = True
        try:
            table.setRowCount(0)
            self._ring_keys_by_row = []
            mol = self._context.current_molecule
            if mol is None:
                return
            try:
                rings = extract_rings(
                    mol, None, self.ring_aromatic_only.isChecked())
            except Exception:
                logging.exception("BlenderExportPro: ring detection failed")
                return

            table.setRowCount(len(rings))
            for row, ring in enumerate(rings):
                key = ring_key(ring)
                self._ring_keys_by_row.append(key)
                style = resolve_ring_style(self._cfg, key)
                overridden = key in (self._cfg.ring_overrides or {})

                label = QTableWidgetItem(
                    "%d-ring [%s]%s" % (
                        len(ring), ", ".join(str(i) for i in ring),
                        "  *" if overridden else ""))
                label.setFlags(label.flags() & ~Qt.ItemFlag.ItemIsEditable)
                label.setToolTip(
                    "Atom indices of this ring. * = has a per-ring override.")
                table.setItem(row, 0, label)

                show = QComboBox()
                show.addItems(("show", "hide"))
                show.setCurrentText("show" if style["visible"] else "hide")
                show.setToolTip("Show or hide this ring's panel.")
                table.setCellWidget(row, 1, show)

                atoms = QComboBox()
                atoms.addItems(("show", "hide"))
                atoms.setCurrentText("hide" if style["hide_atoms"] else "show")
                atoms.setToolTip(
                    "Show or hide this ring's atoms (and internal bonds) so "
                    "only the plate remains.")
                table.setCellWidget(row, 2, atoms)

                color = QLineEdit(style["color"] or "")
                color.setPlaceholderText("(global)")
                color.setToolTip(
                    "#RRGGBB for this ring only; empty = use global color.")
                table.setCellWidget(row, 3, color)

                opacity = self._dspin(0.0, 1.0, 0.05)
                opacity.setValue(style["opacity"])
                table.setCellWidget(row, 4, opacity)

                thickness = self._dspin(0.0, 1.0, 0.02)
                thickness.setValue(style["thickness"])
                table.setCellWidget(row, 5, thickness)

                size = self._dspin(0.1, 1.5, 0.05)
                size.setValue(style["scale"])
                table.setCellWidget(row, 6, size)

                handler = lambda *_a, r=row: self._on_ring_cell_changed(r)
                show.currentTextChanged.connect(handler)
                atoms.currentTextChanged.connect(handler)
                color.editingFinished.connect(handler)
                opacity.valueChanged.connect(handler)
                thickness.valueChanged.connect(handler)
                size.valueChanged.connect(handler)
            table.resizeColumnsToContents()
        finally:
            self._loading = False

    def _ring_row_widgets(self, row):
        return tuple(self.ring_table.cellWidget(row, c) for c in range(1, 7))

    def _on_ring_cell_changed(self, row):
        if self._loading or row >= len(self._ring_keys_by_row):
            return
        show, atoms, color, opacity, thickness, size = self._ring_row_widgets(row)
        if show is None:
            return
        key = self._ring_keys_by_row[row]
        override = {
            "visible": show.currentText() == "show",
            "hide_atoms": atoms.currentText() == "hide",
            "opacity": float(opacity.value()),
            "thickness": float(thickness.value()),
            "scale": float(size.value()),
        }
        text = color.text().strip()
        if text:
            override["color"] = text
        if not isinstance(self._cfg.ring_overrides, dict):
            self._cfg.ring_overrides = {}
        self._cfg.ring_overrides[key] = override
        item = self.ring_table.item(row, 0)
        if item is not None and not item.text().endswith("*"):
            item.setText(item.text() + "  *")
        self._refresh_preview_if_active()

    def _on_ring_row_selected(self, row, _col=0, _prev_row=-1, _prev_col=-1):
        from .preview_style import set_highlighted_ring
        if 0 <= row < len(self._ring_keys_by_row):
            set_highlighted_ring(self._ring_keys_by_row[row])
        else:
            set_highlighted_ring(None)
        self._refresh_preview_if_active()

    def _reset_selected_ring(self):
        row = self.ring_table.currentRow()
        if not 0 <= row < len(self._ring_keys_by_row):
            return
        key = self._ring_keys_by_row[row]
        if isinstance(self._cfg.ring_overrides, dict):
            self._cfg.ring_overrides.pop(key, None)
        self._refresh_ring_table()
        self.ring_table.selectRow(row)
        self._refresh_preview_if_active()

    # ------------------------------------------------------------- actions

    def _activate_preview(self):
        from . import activate_preview_style
        self._pull_config()
        if activate_preview_style(self._context):
            try:
                self._context.refresh_3d_view()
            except Exception:
                logging.exception("BlenderExportPro: preview refresh failed")
            self._context.show_status_message(
                "Blender Export Pro preview active — settings update the "
                "3D view live.", 4000)

    def _activate_standard(self):
        from . import activate_standard_style
        activate_standard_style(self._context)

    def _apply_preset(self):
        name = self.preset_combo.currentText()
        path = self._presets.get(name)
        if path and sc.load_preset(self._cfg, path):
            self._refresh_widgets()
            self._refresh_ring_table()
            self._refresh_lights_table()
            self._update_atom_override_label()
            self._update_element_color_label()
            self._refresh_preview_if_active()
            self._context.show_status_message(f"Preset applied: {name}", 3000)

    def _load_preset_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Preset", "", "JSON preset (*.json)")
        if path and sc.load_preset(self._cfg, path):
            self._refresh_widgets()
            self._refresh_ring_table()
            self._refresh_lights_table()
            self._update_atom_override_label()
            self._update_element_color_label()
            self._refresh_preview_if_active()
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
        self._refresh_ring_table()
        self._refresh_lights_table()
        self._update_atom_override_label()
        self._update_element_color_label()
        self._refresh_preview_if_active()
        self._context.show_status_message("Style reset to defaults.", 3000)

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
            from .preview_style import set_highlighted_ring
            set_highlighted_ring(None)
            self._refresh_preview_if_active()
        except Exception:
            logging.exception("BlenderExportPro: failed to clear highlight")
        try:
            self._pull_config()
            sc.save_config(self._cfg)
        except Exception:
            logging.exception("BlenderExportPro: failed to save on close")
        event.ignore()
        self.hide()
