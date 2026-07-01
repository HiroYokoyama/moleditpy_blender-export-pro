"""StyleConfig — single source of truth for the Blender Export Pro style.

Pure Python (stdlib only) so it can be unit-tested headlessly and serialized
into project files / companion settings.json without side effects.
"""

from dataclasses import dataclass, asdict, fields
import json
import logging
import os

ATOM_SHAPES = ("uv_sphere", "ico_sphere", "metaball")
ATOM_RADIUS_MODES = ("cpk", "uniform")
BOND_STYLES = ("cylinder", "curve")
MATERIAL_PRESETS = (
    "matte", "plastic", "metal", "glass", "toon", "clay",
    "chrome", "gold", "copper", "velvet", "wax", "gummy",
    "ceramic", "chalk", "neon", "ice", "stone", "iridescent",
)
SCENE_PRESETS = ("none", "studio", "dark")
BLENDER_TARGETS = ("4.x", "3.x", "2.8x")


@dataclass
class StyleConfig:
    """All user-tunable parameters for preview and Blender codegen."""

    # Atoms
    atom_shape: str = "uv_sphere"
    atom_subdivisions: int = 3
    atom_radius_mode: str = "cpk"
    atom_radius_scale: float = 0.45
    uniform_radius: float = 0.35
    atom_jitter: float = 0.0  # per-atom squash/stretch randomness (0..1)

    # Bonds
    bond_style: str = "cylinder"
    bond_radius: float = 0.12
    bond_segments: int = 24
    show_multiple_bonds: bool = True
    multi_bond_offset: float = 0.18

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

    # Scene
    scene_preset: str = "studio"
    add_ground_plane: bool = True
    add_camera: bool = True
    turntable_frames: int = 0        # 0 disables the turntable animation

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
                if isinstance(current, bool):
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
    """Path of the durable companion settings.json inside the plugin folder."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


def presets_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")


def load_config() -> StyleConfig:
    """Load the user's last-used config from settings.json (or defaults)."""
    cfg = StyleConfig()
    path = settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg.update_from_dict(json.load(f))
        except (OSError, json.JSONDecodeError):
            logging.exception("BlenderExportPro: failed to read %s", path)
    return cfg


def save_config(cfg: StyleConfig) -> None:
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(cfg.to_dict(), f, indent=4)
    except OSError:
        logging.exception("BlenderExportPro: failed to write settings.json")


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
