# CLAUDE.md — moleditpy_blender-export-pro

Development guide for **Blender Export Pro**, a MoleditPy V4 plugin for
stylized/deformed Blender export (bpy script generation, live PyVista
preview, glTF/USD fallback).

## Repository Layout

```
blender_export_pro/       # The plugin package (copy into ~/.moleditpy/plugins/)
├── __init__.py           # PLUGIN_* metadata, initialize(context), menu/export
│                         #   actions, style switch + 3D Style menu sync.
│                         #   PLUGIN_VERSION lives here as a LITERAL string —
│                         #   the host AST-parses this file for metadata
├── style_config.py       # StyleConfig dataclass (single source of truth),
│                         #   presets/settings I/O, option constants
├── element_data.py       # Colors/radii: prefers main app CPK_COLORS and RDKit
│                         #   GetRvdw at runtime; bundled fallbacks otherwise
├── blender_codegen.py    # bpy script generation (pure string templating) +
│                         #   shared resolvers (radius/color/ring/hide/lights)
├── preview_style.py      # In-app PyVista preview (register_3d_style callback)
├── mesh_export.py        # Blender-free .glb / .usda writers (pure stdlib)
├── dialog.py             # PyQt6 tabbed panel (Quick Start + Advanced tabs)
├── presets/              # Bundled JSON style presets (26+)
└── settings.json         # Runtime user settings — gitignored, never commit
tests/                    # Headless pytest suite (no GUI/chem deps needed)
.github/workflows/        # CI: pytest matrix on Python 3.10–3.13
```

## Running Tests

```bash
python -m pytest tests/ -v          # full suite
python -m pytest tests/test_blender_codegen.py -v
python -m pytest tests/ -k ring     # by keyword
```

All tests run headlessly. `tests/conftest.py` provides:
- `mock_optional_imports()` — MetaPathFinder that replaces PyQt6 / pyvista /
  vtk / numpy / rdkit / moleditpy with MagicMock (DECIMER-plugin pattern).
- `FakeMol` / `make_benzene_like()` / `make_ethanol_like()` — duck-typed
  RDKit stand-ins (conformer, bonds, ring info, aromatic flags).
- `make_context()` — stub PluginContext with a non-None main window.

Core modules (`style_config`, `element_data`, `blender_codegen`,
`mesh_export`) import clean with stdlib only — test them directly, no mocks.
GUI modules (`dialog`, `preview_style`) import under `mock_optional_imports()`.

## Architecture Rules

- **No bpy/rdkit imports at module level.** `blender_codegen` and
  `mesh_export` are pure templating/math; rdkit and the main app are reached
  only through lazy imports inside `element_data` functions with fallbacks.
- **StyleConfig is the single source of truth.** Every user-tunable value is
  a dataclass field. Dict fields (`*_overrides`, `custom_lights`,
  `element_colors`, `atom_hidden`) are JSON-safe: keys are strings
  (`str(rdkit_index)` or `ring_key()` = sorted indices "0-1-2-3-4-5").
- **Override keys use ORIGINAL RDKit indices**, so per-atom/per-ring styling
  survives selection-only export (the export remaps to local order; keys are
  carried alongside via `atom_keys` / `ring_keys`).
- **Every visual rule must apply in all three renderers**: the generated bpy
  script, the PyVista preview, and the glTF/USD export. Shared resolvers in
  `blender_codegen` (`resolve_atom_radius/color`, `resolve_ring_style`,
  `ring_hidden_geometry`, `hidden_atom_indices`, `_custom_light_list`) are
  the mechanism — never duplicate the logic per renderer.
- **Blender API drift**: material sockets are set via `_set_input(node,
  [name_candidates], value)` name-fallback (e.g. "Transmission Weight" →
  "Transmission"), not version branches.
- **Dialog widget↔config binding** goes through `_WIDGET_FIELDS`
  (name, kind) tuples; add new scalar fields there and they get
  refresh/pull/live-update wiring for free. Dict-backed UI (ring table,
  lights table, element colors) has explicit handlers.

## Known Gotchas

- `plotter.clear()` drops the host's lights → preview must re-add lighting
  (`_apply_lighting`, falls back to `enable_lightkit`), else everything
  renders flat/unlit.
- `_material_kwargs()` dicts must NEVER contain keys that
  `plotter.add_mesh()` receives explicitly (`color`, `name`,
  `smooth_shading`) — duplicate-kwarg TypeError (regression-tested).
- `set_3d_style()` does not update the app's 3D Style menu check state;
  call `sync_style_menu(context, style_name)` after switching.
- The user runs the DEPLOYED copy at `%USERPROFILE%\.moleditpy\plugins\
  blender_export_pro` — edits happen in this repo; the user re-copies.
- `settings.json` inside the package is written at runtime; it is
  gitignored and must stay named exactly `settings.json` (Plugin Installer
  preserves it across updates).

## Conventions

- Version: semver, single source of truth is `PLUGIN_VERSION` in
  `__init__.py` (user preference — not date-based). It MUST stay a literal
  string: the host Plugin Manager AST-parses `__init__.py` and only reads
  constant assignments (a name reference shows as "Unknown"). `__version__`
  aliases it; `blender_codegen` stamps scripts via `from . import __version__`.
- Radius semantics: base radius is RDKit vdW; `atom_radius_scale` 0.3 =
  main-app ball-and-stick look, 1.0 = space-filling. Presets are calibrated
  to this base.
- Presets: JSON files in `presets/`; every field optional (unknown keys
  ignored, missing keys keep current values). New presets must load through
  `test_bundled_presets_listed_and_loadable` and generate a compilable
  script (`test_every_bundled_preset_generates_valid_script`) automatically.
- Error handling: `logging.exception/warning` in except blocks; GUI paths
  degrade gracefully (status message or silent skip), never crash the host.

## Main App Contract

Uses `PluginContext` from
`../python_molecular_editor/moleditpy/src/moleditpy/plugins/plugin_interface.py`:
`add_menu_action`, `register_3d_style`, `add_export_action`,
`register_save/load_handler`, `register_document_reset_handler`,
`register_window`/`get_window`, `get_selected_atom_indices`,
`current_molecule`, `refresh_3d_view`, `show_status_message`.
Direct main-window access is limited to `view_3d_manager.set_3d_style`,
`view_3d_manager.plotter`, and `init_manager.style_button` (menu sync) —
all guarded with getattr/try.
