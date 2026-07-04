# Blender Export Pro

[![Tests](https://github.com/HiroYokoyama/moleditpy_blender-export-pro/actions/workflows/pytest.yml/badge.svg)](https://github.com/HiroYokoyama/moleditpy_blender-export-pro/actions/workflows/pytest.yml)
[![Downloads](https://img.shields.io/github/downloads/HiroYokoyama/moleditpy_blender-export-pro/total)](https://github.com/HiroYokoyama/moleditpy_blender-export-pro/releases)

A [MoleditPy](https://github.com/HiroYokoyama/python_molecular_editor) V4 plugin
for stylized / artistically deformed Blender export.

Turn a molecule into a cartoonish, low-poly, glass, claymation or custom-styled
3D scene. The plugin generates a ready-to-run **Blender Python (`bpy`) script**
窶・MoleditPy never imports `bpy` and Blender does not need to be installed on
the machine running MoleditPy.

## Features

- **Live preview drawing style** 窶・registers `Blender Export Pro (Preview)` in
  the 3D style list so you can iterate on the look inside MoleditPy (PyVista).
- **Tabbed config panel** (`Extensions > Blender Export Pro窶ｦ`): Presets, Atoms,
  Bonds, Deformation, Material, Scene, Export.
- **36 bundled presets**: Classic Ball-and-Stick (split bond colors),
  Space-Filling CPK, Cute Cartoon, Toon Comic, Low-Poly Toy, Paper Origami,
  Glass Sculpture, Ice Crystal, Claymation, Gummy Candy, Jelly Wobble,
  Balloon Animal, Velvet Plush, Wax Crayon, Stone Sculpture, Ceramic
  Figurine, Chalkboard Sketch, Neon Glow, Gold Jewelry, Chrome Showroom,
  Copper Steampunk, Wire Model, Holographic Display, Metaball Blob,
  Aromatic Plates, Stained Glass Rings, Hexagon Outline, Glass Plate Rings,
  Gradient Bonds, Atoms Only Pearls, Disco Party, Lava Lamp, Radioactive
  Slime, Cotton Candy, Soap Bubble, Spaghetti Meatballs 窶・plus save/load of
  custom JSON presets.
- **Ring panels & outlines**: draw benzene and other rings as filled
  hexagonal panels/plates 窶・flat or extruded, translucent stained-glass or
  solid, custom-colored or matched to the ring atoms (aromatic-only or all
  small rings) 窶・and/or as a tube along the ring perimeter (the classic
  hexagon-line look) with an adjustable line width. Ring plates and outlines
  appear identically in the live preview, the Blender script and the
  glTF/USD export, including plate transparency.
- **Per-ring styling**: a table on the Rings tab lists every detected ring;
  each row has its own panel show/hide, atoms show/hide, color, opacity,
  thickness and size controls. Selecting a row highlights that ring in the
  3D preview with a bright outline. Per-ring overrides are saved with the
  project.
- **Show the plate only**: hide the atoms (and optionally the internal
  bonds) of paneled rings 窶・globally or per ring 窶・for clean aromatic-ring
  figures.
- **Deformation**: noise displacement (`Displace` + clouds texture), bend /
  twist (`SimpleDeform`), subdivision smoothing, per-atom squash & stretch.
- **18 material presets**: matte, plastic, metal, glass, toon, clay, chrome,
  gold, copper, velvet, wax, gummy, ceramic, chalk, neon (emissive), ice,
  stone, iridescent 窶・Principled BSDF with version-robust socket naming
  (Blender 2.8x窶・.x) plus metallic tinting and emission.
- **Scene setup**: 3-point studio lighting, ground plane / shadow catcher,
  auto-framed camera with an adjustable camera distance, optional turntable
  animation.
- **Background & render**: preset backdrop, custom color, HDRI environment
  image file (browse from the panel; also lights the scene), or transparent
  film for compositing 窶・plus optional Cycles/EEVEE engine, sample count and
  output resolution so the script is render-ready.
- **Atom sizes & colors**: global vdW scale, a one-click hydrogen size
  factor, and per-selected-atom scaling (relative factor or absolute radius)
  and coloring with reset buttons 窶・overrides are saved with the project.
- **Hide what you don't want**: omit all hydrogens in one click, or hide
  specific selected atoms (and their bonds). Hidden atoms keep their ring
  panel, so an aromatic ring can show just its plate.
- **Lighting control**: aim the key light (azimuth/elevation), set its
  strength and distance, tune the fill and rim light power relative to the
  key, or switch to a fully custom light list 窶・add and remove lights, each
  with its own type (area/point/sun/spot), position, intensity and color.
- **Atom labels**: optional 3D text per atom (symbol, symbol+index, or
  index) with size/color/offset controls, camera-billboarded in Blender and
  previewed in-app.
- **Partial export** of the current atom selection.
- **Render straight to an image**: optionally the script renders and saves a
  PNG/JPEG/EXR/etc. when it runs 窶・no need to press F12, and ideal for
  headless batch rendering (`blender -b -P script.py`). Choose engine,
  samples and resolution.
- **No-Blender export**: write a standard **glTF (.glb)** or **USD (.usda)**
  3D model that opens in Windows 3D Viewer, web viewers, PowerPoint, Blender,
  Maya, etc. 窶・for people who don't have Blender at all. Ring plates,
  outlines, anisotropic (jittered) atoms, bond colors and all hide options
  export identically to the Blender script.
- **Full color control**: recolor a whole element (all carbons, etc.),
  override individual atoms, and choose whether bonds blend their atoms'
  colors or use one fixed bond color.
- **Bond detailing**: radius, cross-section segments, double/triple-bond
  rendering with adjustable spacing and an adjustable thickness factor for
  the parallel cylinders (aromatic rings like benzene included).
- **Bond color modes**: blend the two atom colors, a smooth **gradient**
  from atom to atom (true node-based gradient in Blender), a **half/half
  split** at the bond midpoint (classic ball-and-stick), or one fixed
  color 窶・consistent across the preview, the Blender script and glTF/USD.
- **Hide specific bonds**: select the bond's atoms and hide just that
  bond cylinder (both atoms stay) 窶・for contacts or coordination the
  drawing contains but the render shouldn't show. Works in all exports
  and is saved with the project.
- **Consistent with the main app**: atom colors come from MoleditPy's own
  CPK color table (including your customizations) and radii from RDKit's
  van der Waals table 窶・a scale of 0.3 reproduces the main app's
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

The panel opens with a **Quick Start** section 窶・the whole workflow is three
clicks:

1. Load or build a molecule with 3D coordinates, then open
   `Visuals > Blender Export Pro窶ｦ`.
2. Pick a style preset and click **Apply**.
3. Click **Show in 3D View** 窶・the 3D view switches to the styled preview.
   While it is active, every setting change updates the view live.
   **Standard View** switches back to normal ball-and-stick.
4. Click **Export Blender Script窶ｦ**, then in Blender: Scripting workspace 竊・   open the generated `.py` 竊・**Run Script**.

Every detail (atom shapes, bond styles, deformation, materials, lighting,
turntable animation, export options, preset files) is available under the
collapsible **Advanced Settings** tabs. `File > Export > Export to Blender
Script (.py)窶ｦ` also works as a one-click export with the current style.

## Development

```bash
python run_tests.py              # full suite
python run_tests.py -v           # verbose
python run_tests.py -k ring      # by keyword
python run_tests.py --coverage   # with coverage (needs pytest-cov)
```

`python -m pytest tests/ -v` works too 窶・the runner is just a convenience
wrapper. The test suite runs fully headless 窶・PyQt6/pyvista/rdkit are mocked
or duck-typed; no GUI or chemistry libraries are required (only `pytest`).

## License

GPL-3.0 窶・see [LICENSE](LICENSE).
