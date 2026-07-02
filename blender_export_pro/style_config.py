"""StyleConfig — single source of truth for the Blender Export Pro style.

Pure Python (stdlib only) so it can be unit-tested headlessly and serialized
into project files / companion settings.json without side effects.
"""

from dataclasses import dataclass, asdict, field, fields
import json
import logging
import os

STYLE_NAME = "Blender Export Pro (Preview)"

ATOM_SHAPES = ("uv_sphere", "ico_sphere", "metaball")
ATOM_RADIUS_MODES = ("cpk", "uniform")
BOND_STYLES = ("cylinder", "curve")
MATERIAL_PRESETS = (
    "matte", "plastic", "metal", "glass", "toon", "clay",
    "chrome", "gold", "copper", "velvet", "wax", "gummy",
    "ceramic", "chalk", "neon", "ice", "stone", "iridescent",
)
SCENE_PRESETS = ("none", "studio", "dark")
BACKGROUND_MODES = ("preset", "color", "hdri", "transparent")
RENDER_ENGINES = ("keep", "cycles", "eevee")
BOND_COLOR_MODES = ("atoms", "gradient", "split", "single")
LIGHT_TYPES = ("AREA", "POINT", "SUN", "SPOT")


def default_light() -> dict:
    """A sensible default custom-light spec."""
    return {
        "type": "AREA",
        "azimuth": -45.0,
        "elevation": 45.0,
        "distance": 2.5,
        "energy": 1000.0,
        "color": "#FFFFFF",
        "size": 5.0,
    }
IMAGE_FORMATS = ("PNG", "JPEG", "TIFF", "OPEN_EXR", "WEBP")
LABEL_MODES = ("none", "symbol", "symbol_index", "index")
RING_STYLES = ("none", "panel", "outline", "panel+outline")
RING_COLOR_MODES = ("custom", "match_atoms")
BLENDER_TARGETS = ("4.x", "3.x", "2.8x")


@dataclass
class StyleConfig:
    """All user-tunable parameters for preview and Blender codegen."""

    # Atoms
    atom_shape: str = "uv_sphere"
    atom_subdivisions: int = 3
    atom_radius_mode: str = "cpk"
    atom_radius_scale: float = 0.3   # x RDKit vdW radius; 0.3 = main app look
    uniform_radius: float = 0.35
    hide_hydrogens: bool = False     # omit all H atoms and their bonds
    hydrogen_scale: float = 1.0      # extra factor on H atoms (0.5 = half size)
    atom_jitter: float = 0.0  # per-atom squash/stretch randomness (0..1)
    # Per-atom radius overrides, keyed by the atom's RDKit index as a string
    # (JSON-safe). Values: {"scale": factor} or {"radius": absolute Angstrom}.
    atom_overrides: dict = field(default_factory=dict)
    # Per-atom color overrides: {index_str: "#RRGGBB"}.
    atom_color_overrides: dict = field(default_factory=dict)
    # Specific atoms to hide entirely (sphere + bonds): {index_str: True}.
    atom_hidden: dict = field(default_factory=dict)

    # Labels (3D text objects for atom symbols / indices)
    label_mode: str = "none"         # none | symbol | symbol_index | index
    label_size: float = 0.35
    label_color: str = "#202020"
    label_offset: float = 1.3        # distance from atom center, x radius
    label_face_camera: bool = True   # billboard labels toward the camera

    # Bonds
    bond_style: str = "cylinder"
    bond_radius: float = 0.12
    bond_segments: int = 24
    show_multiple_bonds: bool = True
    multi_bond_offset: float = 0.18
    bond_color_mode: str = "atoms"   # atoms | gradient | split | single
    bond_color: str = "#808080"      # used when bond_color_mode == "single"
    # Radius factor on each cylinder of a double/triple (e.g. aromatic ring)
    # bond, relative to bond_radius. 1.0 = same thickness as single bonds.
    multi_bond_scale: float = 0.7
    # Specific bonds to hide, keyed by sorted original atom indices
    # ("3-7": True). Atoms stay; only the bond cylinder is omitted.
    bond_hidden: dict = field(default_factory=dict)
    hide_all_bonds: bool = False     # draw no bonds at all (atoms-only look)

    # Rings (benzene etc. drawn as filled polygon panels/plates and/or a
    # perimeter line — the classic hexagon outline)
    ring_style: str = "none"          # none | panel | outline | panel+outline
    ring_aromatic_only: bool = True   # False = panel every small ring
    ring_scale: float = 0.9           # inset of panel corners toward center
    ring_thickness: float = 0.06      # plate thickness (0 = flat sheet)
    ring_color_mode: str = "custom"   # "custom" | "match_atoms"
    ring_color: str = "#E8D44D"
    ring_opacity: float = 0.55
    ring_outline_radius: float = 0.04  # perimeter line tube radius (Å)
    ring_bevel: bool = True           # softly round the plate edges in Blender
    ring_hide_atoms: bool = False     # hide atoms of paneled rings (show plate only)
    ring_hide_bonds: bool = False     # hide the ring's internal bonds too
    # Per-ring style overrides, keyed by ring_key() (sorted atom indices,
    # e.g. "0-1-2-3-4-5"). Values: {"visible", "scale", "thickness",
    # "color", "opacity"} — missing keys fall back to the globals above.
    ring_overrides: dict = field(default_factory=dict)

    # Deformation
    deformation_noise: float = 0.0   # Displace modifier strength
    deformation_noise_scale: float = 1.5
    deformation_bend: float = 0.0    # SimpleDeform bend angle (degrees)
    deformation_twist: float = 0.0   # SimpleDeform twist angle (degrees)
    subdivision_level: int = 0
    shade_smooth: bool = True

    # Material
    material_preset: str = "plastic"
    color_mode: str = "cpk"          # "cpk" | "single"
    single_color: str = "#CCCCCC"
    roughness_override: float = -1.0  # <0 means "use preset default"
    # Global per-element color overrides: {"C": "#333333", ...}. Overrides the
    # app/CPK color for that element everywhere (below per-atom overrides).
    element_colors: dict = field(default_factory=dict)

    # Scene
    scene_preset: str = "studio"
    add_ground_plane: bool = True
    add_camera: bool = True
    turntable_frames: int = 0        # 0 disables the turntable animation
    # Key-light placement (spherical around the molecule center) and power.
    key_light_azimuth: float = -45.0   # degrees around vertical axis
    key_light_elevation: float = 45.0  # degrees above the horizon
    key_light_strength: float = 1.0    # multiplier on the preset energy
    fill_light_strength: float = 0.3   # fill light power, x the key light
    rim_light_strength: float = 0.5    # rim light power, x the key light
    light_distance_scale: float = 2.5  # light distance = this x molecule size
    camera_distance_scale: float = 3.2  # camera distance = this x molecule size
    # Custom lights: when enabled, replace the auto 3-point rig with this list.
    # {name: {"type","azimuth","elevation","distance","energy","color","size"}}
    use_custom_lights: bool = False
    custom_lights: dict = field(default_factory=dict)

    # Background & render
    background_mode: str = "preset"  # preset | color | hdri | transparent
    background_color: str = "#F0F0F0"
    hdri_path: str = ""              # .hdr/.exr/.png environment image
    hdri_strength: float = 1.0
    render_engine: str = "keep"      # keep | cycles | eevee
    render_samples: int = 128
    resolution_x: int = 1920
    resolution_y: int = 1080

    # Render output (write an image when the script runs)
    render_on_run: bool = False      # add a render + save at the end of script
    render_output_path: str = ""     # image file path written by the script
    image_format: str = "PNG"

    # glTF / USD fallback export (no Blender needed to view)
    # (handled directly by the plugin; no StyleConfig runtime state needed
    #  beyond geometry + colors already present.)

    # Export
    blender_target: str = "4.x"
    clear_scene: bool = True
    collection_name: str = "Molecule"

    def to_dict(self) -> dict:
        return asdict(self)

    def update_from_dict(self, data: dict) -> None:
        """Apply known keys from *data*, coercing to the field's declared type."""
        if not isinstance(data, dict):
            return
        types = {f.name: f.type for f in fields(self)}
        for key, value in data.items():
            if key not in types:
                continue
            current = getattr(self, key)
            try:
                if isinstance(current, dict):
                    setattr(self, key, dict(value) if isinstance(value, dict) else {})
                elif isinstance(current, bool):
                    setattr(self, key, bool(value))
                elif isinstance(current, int):
                    setattr(self, key, int(value))
                elif isinstance(current, float):
                    setattr(self, key, float(value))
                else:
                    setattr(self, key, str(value))
            except (TypeError, ValueError):
                logging.warning(
                    "BlenderExportPro: ignoring bad value %r for %s", value, key
                )

    def reset_defaults(self) -> None:
        defaults = StyleConfig()
        for f in fields(self):
            setattr(self, f.name, getattr(defaults, f.name))


def settings_path() -> str:
    """Path of the small companion settings.json inside the plugin folder."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


def presets_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")


def load_settings() -> dict:
    """Read settings.json — holds only lightweight preferences
    ({"last_preset": display name}), never the full style."""
    path = settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            logging.exception("BlenderExportPro: failed to read %s", path)
    return {}


def save_last_preset(name: str) -> None:
    """Remember which preset was applied last (the only global persistence)."""
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump({"last_preset": str(name)}, f, indent=4)
    except OSError:
        logging.exception("BlenderExportPro: failed to write settings.json")


def load_config() -> StyleConfig:
    """Fresh defaults each launch, plus the last-applied preset (if any).

    The full style is deliberately NOT persisted globally: every launch
    starts clean, and only project files (.pmeprj save/load handlers)
    restore a saved style. settings.json just names the last preset.
    """
    cfg = StyleConfig()
    name = load_settings().get("last_preset")
    if name:
        path = list_presets().get(str(name))
        if path:
            load_preset(cfg, path)
    return cfg


def list_presets() -> dict:
    """Return {display_name: path} for bundled JSON presets."""
    result = {}
    directory = presets_dir()
    if not os.path.isdir(directory):
        return result
    for name in sorted(os.listdir(directory)):
        if name.lower().endswith(".json"):
            display = os.path.splitext(name)[0].replace("_", " ").title()
            result[display] = os.path.join(directory, name)
    return result


def load_preset(cfg: StyleConfig, path: str) -> bool:
    """Apply a preset JSON file onto *cfg*. Returns True on success."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg.update_from_dict(json.load(f))
        return True
    except (OSError, json.JSONDecodeError):
        logging.exception("BlenderExportPro: failed to load preset %s", path)
        return False


def save_preset(cfg: StyleConfig, path: str) -> bool:
    """Write *cfg* to a preset JSON file. Returns True on success."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg.to_dict(), f, indent=4)
        return True
    except OSError:
        logging.exception("BlenderExportPro: failed to save preset %s", path)
        return False
