# Blender Export Pro — Implementation Plan
### A MoleditPy V4 Plugin for Stylized / Deformed Blender Export

---

## 1. Concept

A MoleditPy plugin that adds a new **drawing style** to the application. Opening its panel exposes deep, granular controls for turning a molecule (e.g. a benzene ring) into a stylized or artistically deformed 3D representation — cartoonish, low-poly, glass, claymation, hand-drawn, etc. The final output is a ready-to-run **Blender Python (`bpy`) script** that reconstructs the styled scene inside Blender.

MoleditPy itself never imports `bpy`. It only generates a text file; Blender is not required to be installed on the machine running MoleditPy.

---

## 2. Confirmed Plugin API (MoleditPy V4)

Source: `PLUGIN_DEVELOPMENT_MANUAL_V4.html` (official).

### 2.1 Plugin shape
- A plugin is either a single `.py` file or a folder with `__init__.py`.
- Installed under `~/.moleditpy/plugins/` (Linux/macOS) or `%USERPROFILE%\.moleditpy\plugins\` (Windows).
- Entry point: `initialize(context)`, where `context` is a `PluginContext` — the stable, versioned abstraction layer. Direct `MainWindow` access (`context.get_main_window()`) is allowed but discouraged except for uncovered edge cases.
- Metadata declared as module-level constants: `PLUGIN_NAME` (required), `PLUGIN_VERSION`, `PLUGIN_AUTHOR`, `PLUGIN_DESCRIPTION`, `PLUGIN_CATEGORY`, `PLUGIN_TAGS`, `PLUGIN_DEPENDENCIES`, `PLUGIN_SUPPORTED_MOLEDITPY_VERSION`.

### 2.2 API surface this plugin will use

| Purpose | API |
|---|---|
| Open the config panel from a menu | `context.add_menu_action("Visuals/Blender Export Pro…", cb)` |
| **Register as a drawing style** (the core requirement) | `context.register_3d_style(name, callback)` — callback signature `(mw, mol) -> None`, draws into `mw.plotter` (PyVista) |
| Add an export entry | `context.add_export_action("Export to Blender Script (.py)…", cb)` |
| Read the active molecule | `context.current_molecule` (RDKit `Mol`) |
| Read 3D coordinates only | `context.to_xyz_block()` |
| Read current selection (partial export) | `context.get_selected_atom_indices()` |
| Direct PyVista access (for live style preview) | `context.plotter` |
| Keep the config dialog alive | `context.register_window(id, win)` / `context.get_window(id)` |
| Per-user persisted defaults | `context.get_setting(key, default)` / `context.set_setting(key, value)` (wiped on global "Reset All Settings") |
| Durable persisted defaults (survives reset & plugin updates) | companion `settings.json` inside the plugin folder |
| Per-project persisted style | `context.register_save_handler(cb)` / `context.register_load_handler(cb)` → serialized into `.pmeprj` |
| Reset on File > New | `context.register_document_reset_handler(cb)` |
| Status feedback | `context.show_status_message(msg, ms)` |

### 2.3 Data model notes (V4-specific)
- Chemistry and visuals are decoupled: `data.atoms` / `data.bonds` hold chemistry; `scene.atom_items` / `scene.bond_items` hold the 2D visual items. There is no `'item'` key on data objects anymore.
- Atom indices are 0-based RDKit indices.
- All callbacks run on the main UI thread — anything slow (mesh generation for large molecules, file I/O) should be deferred with `QThread`/`threading` if it risks exceeding ~100 ms.

---

## 3. Architecture

### 3.1 Folder layout
```
plugins/
  BlenderExportPro/
      __init__.py          # PLUGIN_* metadata + initialize(context)
      dialog.py             # PyQt6 config panel (singleton dialog pattern)
      style_config.py       # StyleConfig dataclass — single source of truth
      preview_style.py      # register_3d_style callback: in-app live preview
      blender_codegen.py    # StyleConfig + molecule -> bpy script (string templating)
      presets/               # bundled JSON style presets
          classic_ball_and_stick.json
          cute_cartoon.json
          low_poly_toy.json
          glass_sculpture.json
          chalkboard_sketch.json
      settings.json          # user's last-used config (companion JSON, survives reset)
```

### 3.2 Data flow
```
context.current_molecule (RDKit Mol)
   + context.to_xyz_block()            -> atom coordinates
   + mol.GetBonds() / GetAtoms()       -> bond graph, bond orders, elements
   + context.get_selected_atom_indices() (optional) -> partial-molecule export
   + StyleConfig (from dialog)          -> deformation / material / scene params
          |
          v
   blender_codegen.generate(mol, xyz, style_config) -> str (bpy script text)
          |
          v
   write to disk via QFileDialog.getSaveFileName(...)
```

### 3.3 Integration points (three, all confirmed by the API)
1. **Menu entry** — `add_menu_action("Visuals/Blender Export Pro…", open_panel)` opens the config dialog using the singleton-dialog pattern (`register_window` / `get_window`).
2. **Drawing style registration** — `register_3d_style("Blender Export Pro (Preview)", preview_callback)`. This is the literal fulfillment of "add to drawing styles": selecting it from MoleditPy's own 3D style list renders a live in-app approximation of the deformation/material look using PyVista, so users can iterate before exporting.
3. **Export action** — `add_export_action("Export to Blender Script (.py)…", export_callback)` runs the codegen and writes the file.

### 3.4 Persistence strategy
- **User-level default style** → companion `settings.json` in the plugin folder. Survives "Reset All Settings" and is preserved across updates by the Plugin Installer plugin (must be named exactly `settings.json`).
- **Per-project style** → `register_save_handler` / `register_load_handler`, serialized into `.pmeprj`, so reopening a project restores the exact style used for that molecule (same pattern as the published NICS Placer plugin).
- **Document reset** → `register_document_reset_handler` resets `StyleConfig` to defaults on File > New.

---

## 4. Panel UI (tabs)

1. **Presets** — one-click styles (Classic Ball-and-Stick, Cute/Deformed Cartoon, Low-Poly Toy, Glass Sculpture, Chalkboard Sketch, Claymation, Metaball Blob). Save/load custom presets as JSON.
2. **Atoms** — sphere type (UV sphere / icosphere / metaball), radius scale (CPK / uniform / per-element), color+material override, per-atom squash/stretch jitter.
3. **Bonds** — representation (cylinder / curve+bevel / ribbon), radius, double/triple-bond offset style, taper toward atoms.
4. **Deformation** — global noise displacement, bend/twist/taper (maps to Blender's `SimpleDeform` modifier), organic wobble (`Displace` + noise texture), hand-drawn line jitter, subdivision smoothing amount.
5. **Material / Shading** — Principled BSDF presets (matte, glass, metallic, toon/NPR with Freestyle outlines, subsurface "gummy" look), per-element color ramps.
6. **Scene & Lighting** — studio 3-point rig, HDRI backdrop, ground plane / shadow catcher, camera auto-framed to bounding box.
7. **Animation (optional)** — turntable rotation, assembly/explode-in reveal, bond-formation build animation (pairs well with multi-frame data from the Reaction Sketcher plugin).
8. **Export** — target Blender version (2.8–4.x differ in Geometry Nodes API), output path, "Generate Script" button, live PyVista preview before export.

---

## 5. Expanded feature ideas

- **Non-destructive setup**: generate a Geometry Nodes graph (scripted node creation) instead of baked meshes, so users can keep tweaking noise/deformation sliders inside Blender after import.
- **Physics option**: auto-add Soft Body / Cloth to bonds for a simulated "jelly molecule" wobble.
- **Batch / multi-molecule export**: export a full reaction pathway or conformer set into one Blender collection, one object per frame, ready for animation.
- **Label objects**: optional 3D text objects for atom symbols/indices, camera-billboarded.
- **Partial export**: use `context.get_selected_atom_indices()` to export only a selected fragment/substructure.
- **Fallback path**: also support plain glTF/USD export from the same `StyleConfig`, for users without Blender.
- **Preset sharing**: publish curated presets through the Plugin Explorer, matching the ecosystem's existing distribution model.

---

## 6. Code skeleton

### `__init__.py`
```python
PLUGIN_NAME = "Blender Export Pro"
PLUGIN_VERSION = "0.1.0"
PLUGIN_AUTHOR = "you"
PLUGIN_DESCRIPTION = "Stylized/deformed Blender export with a live-preview drawing style."
PLUGIN_CATEGORY = "Visualization"
PLUGIN_DEPENDENCIES = ["numpy"]

from .dialog import BlenderExportDialog
from .preview_style import draw_preview_style
from .blender_codegen import generate_script
from .style_config import StyleConfig, load_config

_style = None  # module-level StyleConfig, loaded in initialize()

def initialize(context):
    global _style
    _style = load_config(context)

    context.add_menu_action("Visuals/Blender Export Pro…", lambda: open_panel(context))
    context.register_3d_style(
        "Blender Export Pro (Preview)",
        lambda mw, mol: draw_preview_style(mw, mol, _style),
    )
    context.add_export_action(
        "Export to Blender Script (.py)…", lambda: do_export(context)
    )

    context.register_save_handler(lambda: _style.to_dict())
    context.register_load_handler(lambda d: _style.update_from_dict(d))
    context.register_document_reset_handler(lambda: _style.reset_defaults())

def open_panel(context):
    win = context.get_window("panel")
    if win:
        win.show()
        win.raise_()
        return
    win = BlenderExportDialog(context.get_main_window(), context, _style)
    context.register_window("panel", win)
    win.show()

def do_export(context):
    try:
        mol = context.current_molecule
        if not mol:
            context.show_status_message("No molecule loaded.", 3000)
            return
        script = generate_script(mol, context.to_xyz_block(), _style)
        # QFileDialog.getSaveFileName(...) then write `script` to disk
        context.show_status_message("Blender script exported.", 3000)
    except Exception as e:
        context.show_status_message(f"Export failed: {e}", 5000)
```

### `style_config.py` (sketch)
```python
from dataclasses import dataclass, asdict, field
import os, json

@dataclass
class StyleConfig:
    atom_shape: str = "icosphere"
    atom_radius_mode: str = "cpk"
    bond_style: str = "cylinder"
    deformation_noise: float = 0.0
    deformation_bend: float = 0.0
    material_preset: str = "matte"
    scene_preset: str = "studio"
    blender_target_version: str = "4.x"

    def to_dict(self):
        return asdict(self)

    def update_from_dict(self, d: dict):
        for k, v in d.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def reset_defaults(self):
        self.__init__()


def _settings_path():
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(plugin_dir, "settings.json")


def load_config(context) -> StyleConfig:
    cfg = StyleConfig()
    path = _settings_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            cfg.update_from_dict(json.load(f))
    return cfg


def save_config(cfg: StyleConfig):
    with open(_settings_path(), "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, indent=4)
```

### `blender_codegen.py` — responsibilities
- Pure string templating; **no `bpy` import** required in the MoleditPy process.
- Input: RDKit `Mol`, XYZ block, `StyleConfig`.
- Output: a complete `bpy` script string that:
  1. Clears the default scene (optionally).
  2. Creates one primitive per atom (`bpy.ops.mesh.primitive_ico_sphere_add`, etc.), scaled per element.
  3. Creates one curve+bevel or cylinder per bond, oriented between atom pairs.
  4. Applies modifiers matching `deformation_*` fields (`Displace`, `SimpleDeform`, `Subdivision`).
  5. Assigns materials built from Principled BSDF node trees matching `material_preset`.
  6. Optionally sets up lighting/camera/HDRI per `scene_preset`.
  7. Version-branches around Blender API differences (2.8–4.x) using `blender_target_version`.

---

## 7. Phased roadmap

| Phase | Scope |
|---|---|
| **1 — MVP** | Atoms + Bonds tabs only, one built-in preset (Classic Ball-and-Stick), static script export, no lighting/animation, no live preview style yet. |
| **2 — Styling** | Materials tab, Deformation tab, live preview via `register_3d_style`, additional presets (Cute Cartoon, Low-Poly Toy). |
| **3 — Scene & Motion** | Scene & Lighting tab, Animation tab (turntable, explode, reaction-frame build), Physics (soft body wobble). |
| **4 — Ecosystem** | Preset marketplace polish, packaging for the Plugin Explorer, Blender-version targeting for 4.x Geometry Nodes, glTF/USD fallback export. |

---

## 8. Risks & open questions

- **Blender API drift**: Geometry Nodes and material node APIs changed significantly between Blender 2.8x and 4.x — codegen must branch on `blender_target_version` rather than assuming one API surface.
- **Large molecules**: mesh/script generation for big structures could exceed the ~100 ms main-thread budget; move codegen to a background thread if needed and report progress via `show_status_message`.
- **Partial-fragment export**: needs explicit handling of dangling bonds when only a subset of `get_selected_atom_indices()` is exported (cap with implicit hydrogens or leave open — needs a UI toggle).
- **Version compatibility**: set `PLUGIN_SUPPORTED_MOLEDITPY_VERSION` once the target MoleditPy release is confirmed, since V4 API details may still evolve.
