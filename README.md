# Blender Export Pro

A [MoleditPy](https://github.com/HiroYokoyama/python_molecular_editor) V4 plugin
for stylized / artistically deformed Blender export.

Turn a molecule into a cartoonish, low-poly, glass, claymation or custom-styled
3D scene. The plugin generates a ready-to-run **Blender Python (`bpy`) script**
— MoleditPy never imports `bpy` and Blender does not need to be installed on
the machine running MoleditPy.

## Features

- **Live preview drawing style** — registers `Blender Export Pro (Preview)` in
  the 3D style list so you can iterate on the look inside MoleditPy (PyVista).
- **Tabbed config panel** (`Visuals > Blender Export Pro…`): Presets, Atoms,
  Bonds, Deformation, Material, Scene, Export.
- **Bundled presets**: Classic Ball-and-Stick, Cute Cartoon, Low-Poly Toy,
  Glass Sculpture, Claymation, Metaball Blob — plus save/load of custom JSON
  presets.
- **Deformation**: noise displacement (`Displace` + clouds texture), bend /
  twist (`SimpleDeform`), subdivision smoothing, per-atom squash & stretch.
- **Materials**: Principled BSDF presets (matte, plastic, metal, glass, toon,
  clay) with version-robust socket naming (Blender 2.8x–4.x).
- **Scene setup**: 3-point studio lighting, world background, ground plane /
  shadow catcher, auto-framed camera, optional turntable animation.
- **Partial export** of the current atom selection.
- Per-project style persistence (`.pmeprj` save/load handlers) and a durable
  companion `settings.json` for user defaults.

## Installation

Copy the `blender_export_pro/` folder into your MoleditPy plugins directory:

- Windows: `%USERPROFILE%\.moleditpy\plugins\`
- Linux/macOS: `~/.moleditpy/plugins/`

Restart MoleditPy (or reload plugins).

## Usage

1. Load or build a molecule with 3D coordinates.
2. Open `Visuals > Blender Export Pro…`, pick a preset or tune the tabs.
3. (Optional) Select the `Blender Export Pro (Preview)` drawing style in the
   3D panel to see a live approximation.
4. On the Export tab, click **Generate Blender Script…** (or use
   `File > Export > Export to Blender Script (.py)…` for a one-click export).
5. In Blender: Scripting workspace → open the generated `.py` → **Run Script**.

## Development

```bash
python -m pytest tests/ -v
```

The test suite runs fully headless — PyQt6/pyvista/rdkit are mocked or
duck-typed; no GUI or chemistry libraries are required.

## License

GPL-3.0 — see [LICENSE](LICENSE).
