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
- **20 bundled presets**: Classic Ball-and-Stick, Space-Filling CPK, Cute
  Cartoon, Toon Comic, Low-Poly Toy, Paper Origami, Glass Sculpture, Ice
  Crystal, Claymation, Gummy Candy, Jelly Wobble, Balloon Animal, Velvet
  Plush, Wax Crayon, Stone Sculpture, Ceramic Figurine, Chalkboard Sketch,
  Neon Glow, Gold Jewelry, Chrome Showroom, Copper Steampunk, Wire Model,
  Holographic Display, Metaball Blob — plus save/load of custom JSON presets.
- **Ring panels**: draw benzene and other rings as filled hexagonal
  panels/plates — flat or extruded, translucent stained-glass or solid,
  custom-colored or matched to the ring atoms (aromatic-only or all small
  rings).
- **Per-ring styling**: a table on the Rings tab lists every detected ring;
  each row has its own panel show/hide, atoms show/hide, color, opacity,
  thickness and size controls. Selecting a row highlights that ring in the
  3D preview with a bright outline. Per-ring overrides are saved with the
  project.
- **Show the plate only**: hide the atoms (and optionally the internal
  bonds) of paneled rings — globally or per ring — for clean aromatic-ring
  figures.
- **Deformation**: noise displacement (`Displace` + clouds texture), bend /
  twist (`SimpleDeform`), subdivision smoothing, per-atom squash & stretch.
- **18 material presets**: matte, plastic, metal, glass, toon, clay, chrome,
  gold, copper, velvet, wax, gummy, ceramic, chalk, neon (emissive), ice,
  stone, iridescent — Principled BSDF with version-robust socket naming
  (Blender 2.8x–4.x) plus metallic tinting and emission.
- **Scene setup**: 3-point studio lighting, ground plane / shadow catcher,
  auto-framed camera, optional turntable animation.
- **Background & render**: preset backdrop, custom color, HDRI environment
  image file (browse from the panel; also lights the scene), or transparent
  film for compositing — plus optional Cycles/EEVEE engine, sample count and
  output resolution so the script is render-ready.
- **Atom sizes & colors**: global vdW scale, a one-click hydrogen size
  factor, and per-selected-atom scaling (relative factor or absolute radius)
  and coloring with reset buttons — overrides are saved with the project.
- **Hide what you don't want**: omit all hydrogens in one click, or hide
  specific selected atoms (and their bonds). Hidden atoms keep their ring
  panel, so an aromatic ring can show just its plate.
- **Lighting control**: aim the key light (azimuth/elevation), set its
  strength and distance, or switch to a fully custom light list — add and
  remove lights, each with its own type (area/point/sun/spot), position,
  intensity and color.
- **Atom labels**: optional 3D text per atom (symbol, symbol+index, or
  index) with size/color/offset controls, camera-billboarded in Blender and
  previewed in-app.
- **Partial export** of the current atom selection.
- **Render straight to an image**: optionally the script renders and saves a
  PNG/JPEG/EXR/etc. when it runs — no need to press F12, and ideal for
  headless batch rendering (`blender -b -P script.py`). Choose engine,
  samples and resolution.
- **No-Blender export**: write a standard **glTF (.glb)** or **USD (.usda)**
  3D model that opens in Windows 3D Viewer, web viewers, PowerPoint, Blender,
  Maya, etc. — for people who don't have Blender at all.
- **Full color control**: recolor a whole element (all carbons, etc.),
  override individual atoms, and choose whether bonds blend their atoms'
  colors or use one fixed bond color.
- **Consistent with the main app**: atom colors come from MoleditPy's own
  CPK color table (including your customizations) and radii from RDKit's
  van der Waals table — a scale of 0.3 reproduces the main app's
  ball-and-stick look, 1.0 is space-filling. Bundled fallback tables keep
  everything working headlessly.
- Per-project style persistence (`.pmeprj` save/load handlers) and a durable
  companion `settings.json` for user defaults.

## Installation

Copy the `blender_export_pro/` folder into your MoleditPy plugins directory:

- Windows: `%USERPROFILE%\.moleditpy\plugins\`
- Linux/macOS: `~/.moleditpy/plugins/`

Restart MoleditPy (or reload plugins).

## Usage

The panel opens with a **Quick Start** section — the whole workflow is three
clicks:

1. Load or build a molecule with 3D coordinates, then open
   `Visuals > Blender Export Pro…`.
2. Pick a style preset and click **Apply**.
3. Click **Show in 3D View** — the 3D view switches to the styled preview.
   While it is active, every setting change updates the view live.
   **Standard View** switches back to normal ball-and-stick.
4. Click **Export Blender Script…**, then in Blender: Scripting workspace →
   open the generated `.py` → **Run Script**.

Every detail (atom shapes, bond styles, deformation, materials, lighting,
turntable animation, export options, preset files) is available under the
collapsible **Advanced Settings** tabs. `File > Export > Export to Blender
Script (.py)…` also works as a one-click export with the current style.

## Development

```bash
python -m pytest tests/ -v
```

The test suite runs fully headless — PyQt6/pyvista/rdkit are mocked or
duck-typed; no GUI or chemistry libraries are required.

## License

GPL-3.0 — see [LICENSE](LICENSE).
