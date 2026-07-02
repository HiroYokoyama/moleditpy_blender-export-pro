"""Blender Python (bpy) script generation.

Pure string templating: this module never imports bpy or rdkit. It takes a
plain geometry description (extracted from an RDKit Mol by duck-typing) plus a
StyleConfig and emits a self-contained script runnable inside Blender 2.8x-4.x.
"""

import datetime
import math
import pprint

from . import __version__
from .element_data import radius_of, color_of
from .style_config import StyleConfig

def _mat(metallic=0.0, roughness=0.5, transmission=0.0, ior=1.45,
         subsurface=0.0, emission=0.0, tint=None):
    """Material preset parameter record.

    tint: optional (r, g, b) multiplied onto the base color inside Blender —
    lets e.g. gold/copper keep a metallic hue on top of CPK colors.
    """
    return {
        "metallic": metallic,
        "roughness": roughness,
        "transmission": transmission,
        "ior": ior,
        "subsurface": subsurface,
        "emission": emission,
        "tint": list(tint) if tint else [1.0, 1.0, 1.0],
    }


MATERIAL_PRESET_PARAMS = {
    "matte":      _mat(roughness=0.9),
    "plastic":    _mat(roughness=0.3),
    "metal":      _mat(metallic=1.0, roughness=0.25, ior=2.5),
    "glass":      _mat(roughness=0.05, transmission=1.0),
    "toon":       _mat(roughness=1.0),
    "clay":       _mat(roughness=0.8, ior=1.4, subsurface=0.15),
    "chrome":     _mat(metallic=1.0, roughness=0.03, ior=3.0),
    "gold":       _mat(metallic=1.0, roughness=0.2, ior=0.47,
                       tint=(1.0, 0.77, 0.34)),
    "copper":     _mat(metallic=1.0, roughness=0.3, ior=1.1,
                       tint=(0.95, 0.64, 0.54)),
    "velvet":     _mat(roughness=1.0, subsurface=0.1),
    "wax":        _mat(roughness=0.45, subsurface=0.4, ior=1.44),
    "gummy":      _mat(roughness=0.25, transmission=0.35, subsurface=0.5,
                       ior=1.35),
    "ceramic":    _mat(roughness=0.1, ior=1.52),
    "chalk":      _mat(roughness=1.0, tint=(0.95, 0.95, 0.95)),
    "neon":       _mat(roughness=0.4, emission=4.0),
    "ice":        _mat(roughness=0.15, transmission=0.9, ior=1.31,
                       tint=(0.85, 0.95, 1.0)),
    "stone":      _mat(roughness=0.95, tint=(0.8, 0.8, 0.78)),
    "iridescent": _mat(metallic=0.8, roughness=0.15, ior=1.8,
                       tint=(0.9, 0.85, 1.0)),
}


def hex_to_rgb(hex_color: str) -> tuple:
    """'#RRGGBB' -> (r, g, b) floats in 0..1. Falls back to grey."""
    text = (hex_color or "").lstrip("#")
    if len(text) != 6:
        return (0.8, 0.8, 0.8)
    try:
        return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.8, 0.8, 0.8)


def _keep_list(num_atoms, selected_indices):
    """Original atom indices to export, in export order."""
    if selected_indices:
        return sorted(
            set(int(i) for i in selected_indices if 0 <= int(i) < num_atoms))
    return list(range(num_atoms))


def resolve_atom_radius(cfg: StyleConfig, symbol: str, orig_index=None) -> float:
    """Effective display radius for one atom.

    Applies, in order: radius mode (RDKit vdW x scale, or uniform), the
    hydrogen size factor, and any per-atom override ({"scale": f} or
    {"radius": absolute}) keyed by the atom's original RDKit index.
    """
    if cfg.atom_radius_mode == "uniform":
        radius = cfg.uniform_radius
    else:
        radius = radius_of(symbol) * cfg.atom_radius_scale
    if symbol == "H":
        radius *= cfg.hydrogen_scale
    if orig_index is not None and isinstance(cfg.atom_overrides, dict):
        override = cfg.atom_overrides.get(str(orig_index))
        if isinstance(override, dict):
            try:
                if "radius" in override:
                    radius = float(override["radius"])
                elif "scale" in override:
                    radius *= float(override["scale"])
            except (TypeError, ValueError):
                pass
    return max(radius, 0.01)


def resolve_element_color(cfg: StyleConfig, symbol: str) -> tuple:
    """Base color for an element: global per-element override, else app/CPK."""
    if isinstance(cfg.element_colors, dict):
        override = cfg.element_colors.get(symbol)
        if override:
            return hex_to_rgb(override)
    return color_of(symbol)


def resolve_atom_color(cfg: StyleConfig, symbol: str, orig_index=None) -> tuple:
    """Effective (r, g, b) for one atom.

    Priority: per-atom override > single-color mode > per-element override /
    app CPK color.
    """
    if orig_index is not None and isinstance(cfg.atom_color_overrides, dict):
        override = cfg.atom_color_overrides.get(str(orig_index))
        if override:
            return hex_to_rgb(override)
    if cfg.color_mode == "single":
        return hex_to_rgb(cfg.single_color)
    return resolve_element_color(cfg, symbol)


def _custom_light_list(cfg: StyleConfig):
    """Custom lights as an ordered list of fully-populated spec dicts."""
    from .style_config import default_light
    result = []
    if not isinstance(cfg.custom_lights, dict):
        return result
    for name, spec in cfg.custom_lights.items():
        entry = default_light()
        if isinstance(spec, dict):
            entry.update({k: spec[k] for k in entry if k in spec})
        entry["name"] = str(name)
        entry["color"] = [round(c, 4) for c in hex_to_rgb(entry["color"])]
        result.append(entry)
    return result


def resolve_bond_color(cfg: StyleConfig, color_a, color_b) -> list:
    """Bond color: fixed single color, or the average of its two atoms."""
    if cfg.bond_color_mode == "single":
        return [round(c, 4) for c in hex_to_rgb(cfg.bond_color)]
    return [round((color_a[k] + color_b[k]) / 2.0, 4) for k in range(3)]


def noise_displacement(point, strength, scale) -> float:
    """Smooth deterministic pseudo-noise approximating Blender's clouds
    Displace: a scalar in [-strength, strength] varying smoothly with world
    position. Used by the preview and the glTF export; the Blender script
    uses a real Displace modifier instead."""
    if strength <= 0.0:
        return 0.0
    k = 2.0 / max(float(scale), 1e-3)
    x, y, z = (float(point[0]) * k, float(point[1]) * k, float(point[2]) * k)
    # two octaves: broad blobs plus fine detail an atom-sized surface shows
    coarse = (math.sin(x * 1.7 + y * 0.8 + 2.4)
              + math.sin(y * 1.3 + z * 1.1 + 4.1)
              + math.sin(z * 0.9 + x * 1.5 + 1.2)) / 3.0
    fine = (math.sin(x * 6.1 + z * 4.7 + 0.7)
            + math.sin(y * 5.3 + x * 4.3 + 3.3)
            + math.sin(z * 6.7 + y * 5.9 + 5.1)) / 3.0
    return (coarse + 0.7 * fine) / 1.7 * float(strength)


GRADIENT_BOND_PIECES = 4


def bond_piecewise(cfg: StyleConfig, start, end, color_a, color_b) -> list:
    """Bond as colored segments: [(seg_start, seg_end, color)].

    Implements the bond color modes for renderers without per-object
    materials: "split" = half/half at the midpoint, "gradient" =
    GRADIENT_BOND_PIECES interpolated slices, "single"/"atoms" = one
    segment. (The generated Blender script uses a true node-based
    gradient instead of slices.)
    """
    def lerp_point(t):
        return tuple(start[k] + (end[k] - start[k]) * t for k in range(3))

    def lerp_color(t):
        return tuple(round(color_a[k] + (color_b[k] - color_a[k]) * t, 4)
                     for k in range(3))

    mode = cfg.bond_color_mode
    if mode == "split":
        mid = lerp_point(0.5)
        return [(tuple(start), mid, tuple(color_a)),
                (mid, tuple(end), tuple(color_b))]
    if mode == "gradient":
        n = GRADIENT_BOND_PIECES
        return [(lerp_point(p / n), lerp_point((p + 1) / n),
                 lerp_color((p + 0.5) / n)) for p in range(n)]
    color = tuple(resolve_bond_color(cfg, color_a, color_b))
    return [(tuple(start), tuple(end), color)]


def extract_geometry(mol, selected_indices=None):
    """Extract (atoms, bonds) from an RDKit-like Mol via duck-typing.

    Returns:
        atoms: list of (symbol, (x, y, z)) in export order.
        bonds: list of (i, j, order) with indices into *atoms*.

    If *selected_indices* is a non-empty collection, only those atoms (and
    bonds fully inside the selection) are exported.
    """
    conf = mol.GetConformer()
    num_atoms = mol.GetNumAtoms()

    keep = _keep_list(num_atoms, selected_indices)
    remap = {old: new for new, old in enumerate(keep)}

    atoms = []
    for old_idx in keep:
        pos = conf.GetAtomPosition(old_idx)
        symbol = mol.GetAtomWithIdx(old_idx).GetSymbol()
        atoms.append((str(symbol), (float(pos.x), float(pos.y), float(pos.z))))

    bonds = []
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if i in remap and j in remap:
            try:
                order = int(round(bond.GetBondTypeAsDouble()))
            except (TypeError, ValueError):
                order = 1
            bonds.append((remap[i], remap[j], max(1, min(order, 3))))
    return atoms, bonds


def ring_key(indices) -> str:
    """Stable identifier for a ring: sorted atom indices, e.g. '0-1-2-3-4-5'."""
    return "-".join(str(i) for i in sorted(int(i) for i in indices))


def bond_key(i, j) -> str:
    """Stable identifier for a bond: sorted original atom indices, '3-7'."""
    a, b = sorted((int(i), int(j)))
    return "%d-%d" % (a, b)


def hidden_bond_keys(cfg: StyleConfig) -> set:
    """Keys of bonds the user hid explicitly (cfg.bond_hidden)."""
    if isinstance(cfg.bond_hidden, dict):
        return {str(k) for k, v in cfg.bond_hidden.items() if v}
    return set()


def extract_rings(mol, selected_indices=None, aromatic_only=True,
                  keep_original=False):
    """Extract small rings (3-8 atoms) as tuples of export-order indices.

    Uses RDKit's ring info via duck-typing. Rings crossing a selection
    boundary are dropped. With *aromatic_only*, only fully aromatic rings
    (e.g. benzene) are returned. With *keep_original*, tuples keep the
    original molecule indices instead of being remapped to export order
    (needed for stable per-ring override keys).
    """
    try:
        atom_rings = mol.GetRingInfo().AtomRings()
    except (AttributeError, RuntimeError, ValueError):
        return []

    num_atoms = mol.GetNumAtoms()
    keep = _keep_list(num_atoms, selected_indices)
    remap = {old: new for new, old in enumerate(keep)}

    rings = []
    for ring in atom_rings:
        if not 3 <= len(ring) <= 8:
            continue
        if any(i not in remap for i in ring):
            continue
        if aromatic_only:
            try:
                if not all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring):
                    continue
            except AttributeError:
                continue
        if keep_original:
            rings.append(tuple(int(i) for i in ring))
        else:
            rings.append(tuple(remap[i] for i in ring))
    return rings


def _atom_records(atoms, cfg: StyleConfig, atom_keys=None, hidden_atoms=None):
    """Per-atom (symbol, position, radius, color, visible) records.

    atom_keys: original RDKit indices per atom (for per-atom overrides);
    defaults to the export position.
    hidden_atoms: export-order indices whose spheres should not be drawn
    (e.g. atoms of a ring rendered as a panel only).
    """
    hidden = hidden_atoms or set()
    records = []
    for pos_idx, (symbol, pos) in enumerate(atoms):
        orig = atom_keys[pos_idx] if atom_keys else pos_idx
        radius = resolve_atom_radius(cfg, symbol, orig)
        color = resolve_atom_color(cfg, symbol, orig)
        records.append(
            {
                "symbol": symbol,
                "pos": [round(c, 6) for c in pos],
                "radius": round(radius, 6),
                "color": [round(c, 4) for c in color],
                "visible": pos_idx not in hidden,
            }
        )
    return records


def _bond_records(bonds, cfg: StyleConfig, hide_bond_rings=None,
                  hidden_endpoints=None, atom_keys=None):
    """Per-bond records with a visibility flag.

    A bond is hidden if either endpoint is a fully-omitted atom
    (*hidden_endpoints*, e.g. hydrogens), both endpoints lie in a ring
    whose internal bonds are hidden (*hide_bond_rings*), or the user hid
    that specific bond (cfg.bond_hidden, keyed by original indices).
    """
    hide_rings = hide_bond_rings or []
    endpoints = hidden_endpoints or set()
    hidden_keys = hidden_bond_keys(cfg)
    records = []
    for i, j, order in bonds:
        orig_i = atom_keys[i] if atom_keys else i
        orig_j = atom_keys[j] if atom_keys else j
        visible = (not cfg.hide_all_bonds
                   and i not in endpoints and j not in endpoints
                   and bond_key(orig_i, orig_j) not in hidden_keys
                   and not any(i in members and j in members
                               for members in hide_rings))
        records.append({
            "a": i, "b": j,
            "order": order if cfg.show_multiple_bonds else 1,
            "visible": visible,
        })
    return records


def hidden_hydrogen_indices(atoms, cfg: StyleConfig):
    """Export-order indices of hydrogens to omit (empty unless enabled)."""
    if not cfg.hide_hydrogens:
        return set()
    return {idx for idx, (symbol, _pos) in enumerate(atoms) if symbol == "H"}


def hidden_atom_indices(atoms, cfg: StyleConfig, atom_keys=None):
    """Export-order indices of atoms omitted entirely (sphere + all bonds).

    Combines the global 'omit hydrogens' option with specific atoms the user
    hid by original RDKit index (cfg.atom_hidden).
    """
    hidden = hidden_hydrogen_indices(atoms, cfg)
    if isinstance(cfg.atom_hidden, dict) and cfg.atom_hidden:
        for pos_idx, _atom in enumerate(atoms):
            orig = atom_keys[pos_idx] if atom_keys else pos_idx
            if str(orig) in cfg.atom_hidden:
                hidden.add(pos_idx)
    return hidden


def ring_panels_enabled(cfg: StyleConfig) -> bool:
    """True when rings are drawn as filled plates ('panel', 'panel+outline')."""
    return "panel" in (cfg.ring_style or "")


def ring_outlines_enabled(cfg: StyleConfig) -> bool:
    """True when rings get a perimeter line ('outline', 'panel+outline')."""
    return "outline" in (cfg.ring_style or "")


def resolve_ring_style(cfg: StyleConfig, key: str) -> dict:
    """Effective style values for one ring: globals + per-ring override."""
    override = {}
    if isinstance(cfg.ring_overrides, dict):
        candidate = cfg.ring_overrides.get(key)
        if isinstance(candidate, dict):
            override = candidate
    return {
        "visible": bool(override.get("visible", True)),
        "scale": float(override.get("scale", cfg.ring_scale)),
        "thickness": float(override.get("thickness", cfg.ring_thickness)),
        "opacity": float(override.get("opacity", cfg.ring_opacity)),
        "color": override.get("color") or None,  # None -> use global mode
        "hide_atoms": bool(override.get("hide_atoms", cfg.ring_hide_atoms)),
        "hide_bonds": bool(override.get("hide_bonds", cfg.ring_hide_bonds)),
    }


def ring_hidden_geometry(cfg: StyleConfig, rings, ring_keys=None):
    """Compute which atoms/ring-bonds to hide because a panel replaces them.

    Returns (hidden_atoms: set of export indices, hide_bond_rings: list of
    export-index sets for rings whose internal bonds are hidden). Only rings
    that are actually drawn as a visible panel contribute.
    """
    hidden_atoms = set()
    hide_bond_rings = []
    if not (ring_panels_enabled(cfg) or ring_outlines_enabled(cfg)):
        return hidden_atoms, hide_bond_rings
    for pos, ring in enumerate(rings or []):
        key = ring_keys[pos] if ring_keys else ring_key(ring)
        style = resolve_ring_style(cfg, key)
        if not style["visible"]:
            continue
        if style["hide_atoms"]:
            hidden_atoms.update(ring)
        if style["hide_bonds"]:
            hide_bond_rings.append(set(ring))
    return hidden_atoms, hide_bond_rings


def _ring_records(atoms, rings, cfg: StyleConfig, ring_keys=None):
    """Per-ring records with color and per-ring overrides already resolved."""
    atom_records = _atom_records(atoms, cfg)
    records = []
    for pos, ring in enumerate(rings or []):
        key = ring_keys[pos] if ring_keys else ring_key(ring)
        style = resolve_ring_style(cfg, key)
        if style["color"]:
            color = [round(c, 4) for c in hex_to_rgb(style["color"])]
        elif cfg.ring_color_mode == "match_atoms":
            members = [atom_records[i]["color"] for i in ring]
            color = [round(sum(c[k] for c in members) / len(members), 4)
                     for k in range(3)]
        else:
            color = [round(c, 4) for c in hex_to_rgb(cfg.ring_color)]
        records.append(
            {
                "indices": list(ring),
                "color": color,
                "visible": style["visible"],
                "scale": round(style["scale"], 4),
                "thickness": round(style["thickness"], 4),
                "opacity": round(style["opacity"], 4),
            }
        )
    return records


def generate_script(atoms, bonds, cfg: StyleConfig, rings=None,
                    ring_keys=None, atom_keys=None) -> str:
    """Build the full bpy script text.

    Args:
        atoms: list of (symbol, (x, y, z)).
        bonds: list of (i, j, order).
        cfg: style configuration.
        rings: optional list of atom-index tuples to draw as panels/plates.
        ring_keys: optional per-ring override keys (original-molecule
            indices); defaults to keys derived from *rings* themselves.
        atom_keys: optional original RDKit index per atom, for per-atom
            radius overrides; defaults to export positions.
    """
    params = dict(MATERIAL_PRESET_PARAMS.get(
        cfg.material_preset, MATERIAL_PRESET_PARAMS["plastic"]))
    if cfg.roughness_override >= 0.0:
        params["roughness"] = min(cfg.roughness_override, 1.0)

    hidden_atoms, hide_bond_rings = ring_hidden_geometry(cfg, rings, ring_keys)
    endpoints = hidden_atom_indices(atoms, cfg, atom_keys)
    hidden_atoms = set(hidden_atoms) | endpoints
    atom_data = pprint.pformat(
        _atom_records(atoms, cfg, atom_keys, hidden_atoms), indent=4)
    bond_data = pprint.pformat(
        _bond_records(bonds, cfg, hide_bond_rings, endpoints, atom_keys),
        indent=4)
    ring_data = pprint.pformat(
        _ring_records(atoms, rings, cfg, ring_keys), indent=4)
    generated_on = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f'''"""Generated by MoleditPy — Blender Export Pro v{__version__}.

Exported: {generated_on}
Target Blender: {cfg.blender_target}
Atoms: {len(atoms)}  Bonds: {len(bonds)}  Ring panels: {len(rings or [])}
Material preset: {cfg.material_preset}  Scene: {cfg.scene_preset}

Run inside Blender (Scripting workspace > Run Script).
This file is self-contained; no external data needed.
"""
GENERATOR = "MoleditPy Blender Export Pro"
GENERATOR_VERSION = {__version__!r}

import bpy
import math
import random
from mathutils import Vector

ATOMS = {atom_data}

BONDS = {bond_data}

RINGS = {ring_data}

COLLECTION_NAME = {cfg.collection_name!r}
CLEAR_SCENE = {cfg.clear_scene!r}
ATOM_SHAPE = {cfg.atom_shape!r}
ATOM_SUBDIV = {int(cfg.atom_subdivisions)!r}
ATOM_JITTER = {float(cfg.atom_jitter)!r}
BOND_STYLE = {cfg.bond_style!r}
BOND_RADIUS = {float(cfg.bond_radius)!r}
BOND_SEGMENTS = {int(cfg.bond_segments)!r}
MULTI_BOND_OFFSET = {float(cfg.multi_bond_offset)!r}
MULTI_BOND_SCALE = {float(cfg.multi_bond_scale)!r}
BOND_COLOR_MODE = {cfg.bond_color_mode!r}
BOND_COLOR = {repr([round(c, 4) for c in hex_to_rgb(cfg.bond_color)])}
RING_STYLE = {cfg.ring_style!r}
RING_SCALE = {float(cfg.ring_scale)!r}
RING_THICKNESS = {float(cfg.ring_thickness)!r}
RING_OPACITY = {float(cfg.ring_opacity)!r}
RING_OUTLINE_RADIUS = {float(cfg.ring_outline_radius)!r}
RING_BEVEL = {cfg.ring_bevel!r}
NOISE_STRENGTH = {float(cfg.deformation_noise)!r}
NOISE_SCALE = {float(cfg.deformation_noise_scale)!r}
BEND_DEG = {float(cfg.deformation_bend)!r}
TWIST_DEG = {float(cfg.deformation_twist)!r}
SUBDIV_LEVEL = {int(cfg.subdivision_level)!r}
SHADE_SMOOTH = {cfg.shade_smooth!r}
MAT_PARAMS = {repr(params)}
MAT_PRESET = {cfg.material_preset!r}
SCENE_PRESET = {cfg.scene_preset!r}
ADD_GROUND = {cfg.add_ground_plane!r}
ADD_CAMERA = {cfg.add_camera!r}
TURNTABLE_FRAMES = {int(cfg.turntable_frames)!r}
KEY_LIGHT_AZIMUTH = {float(cfg.key_light_azimuth)!r}
KEY_LIGHT_ELEVATION = {float(cfg.key_light_elevation)!r}
KEY_LIGHT_STRENGTH = {float(cfg.key_light_strength)!r}
FILL_LIGHT_STRENGTH = {float(cfg.fill_light_strength)!r}
RIM_LIGHT_STRENGTH = {float(cfg.rim_light_strength)!r}
LIGHT_DISTANCE_SCALE = {float(cfg.light_distance_scale)!r}
CAMERA_DISTANCE_SCALE = {float(cfg.camera_distance_scale)!r}
USE_CUSTOM_LIGHTS = {cfg.use_custom_lights!r}
CUSTOM_LIGHTS = {repr(_custom_light_list(cfg))}
BG_MODE = {cfg.background_mode!r}
BG_COLOR = {repr([round(c, 4) for c in hex_to_rgb(cfg.background_color)])}
HDRI_PATH = {cfg.hdri_path!r}
HDRI_STRENGTH = {float(cfg.hdri_strength)!r}
RENDER_ENGINE = {cfg.render_engine!r}
RENDER_SAMPLES = {int(cfg.render_samples)!r}
RESOLUTION = ({int(cfg.resolution_x)!r}, {int(cfg.resolution_y)!r})
LABEL_MODE = {cfg.label_mode!r}
LABEL_SIZE = {float(cfg.label_size)!r}
LABEL_COLOR = {repr([round(c, 4) for c in hex_to_rgb(cfg.label_color)])}
LABEL_OFFSET = {float(cfg.label_offset)!r}
LABEL_FACE_CAMERA = {cfg.label_face_camera!r}
RENDER_ON_RUN = {cfg.render_on_run!r}
RENDER_OUTPUT_PATH = {cfg.render_output_path!r}
IMAGE_FORMAT = {cfg.image_format!r}

random.seed(42)
'''

    body = r'''

def _set_input(node, names, value):
    """Set the first matching Principled BSDF input (API differs across 2.8-4.x)."""
    for name in names:
        sock = node.inputs.get(name)
        if sock is not None:
            try:
                sock.default_value = value
            except (TypeError, ValueError):
                pass
            return


def make_material(name, rgb):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            bsdf = node
            break
    if bsdf is None:
        return mat
    tint = MAT_PARAMS.get("tint", [1.0, 1.0, 1.0])
    rgb = [min(rgb[k] * tint[k], 1.0) for k in range(3)]
    _set_input(bsdf, ["Base Color"], (rgb[0], rgb[1], rgb[2], 1.0))
    _set_input(bsdf, ["Metallic"], MAT_PARAMS["metallic"])
    _set_input(bsdf, ["Roughness"], MAT_PARAMS["roughness"])
    _set_input(bsdf, ["Transmission Weight", "Transmission"], MAT_PARAMS["transmission"])
    _set_input(bsdf, ["IOR"], MAT_PARAMS["ior"])
    _set_input(bsdf, ["Subsurface Weight", "Subsurface"], MAT_PARAMS["subsurface"])
    emission = MAT_PARAMS.get("emission", 0.0)
    if emission > 0.0:
        _set_input(bsdf, ["Emission Color", "Emission"], (rgb[0], rgb[1], rgb[2], 1.0))
        _set_input(bsdf, ["Emission Strength"], emission)
    if MAT_PARAMS["transmission"] > 0.5 and hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    mat.diffuse_color = (rgb[0], rgb[1], rgb[2], 1.0)
    return mat


def _color_key(rgb):
    return "_".join("%.3f" % c for c in rgb)


def make_gradient_material(name, rgb_a, rgb_b):
    """Material with a smooth color gradient along the bond axis.

    Uses Generated coordinates (0..1 over the object's bounding box); the
    cylinder's local Z is the bond axis, rotated onto the gradient's X.
    """
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = None
    for node in tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            bsdf = node
            break
    avg = [(rgb_a[k] + rgb_b[k]) / 2.0 for k in range(3)]
    mat.diffuse_color = (avg[0], avg[1], avg[2], 1.0)
    if bsdf is None:
        return mat

    tint = MAT_PARAMS.get("tint", [1.0, 1.0, 1.0])
    rgb_a = [min(rgb_a[k] * tint[k], 1.0) for k in range(3)]
    rgb_b = [min(rgb_b[k] * tint[k], 1.0) for k in range(3)]

    coords = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    gradient = tree.nodes.new("ShaderNodeTexGradient")
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    # rotate the vector so local Z (bond axis) drives the gradient's X
    mapping.inputs["Rotation"].default_value = (0.0, math.radians(90.0), 0.0)
    ramp.color_ramp.elements[0].color = (rgb_a[0], rgb_a[1], rgb_a[2], 1.0)
    ramp.color_ramp.elements[1].color = (rgb_b[0], rgb_b[1], rgb_b[2], 1.0)
    tree.links.new(coords.outputs["Generated"], mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], gradient.inputs["Vector"])
    tree.links.new(gradient.outputs["Fac"], ramp.inputs["Fac"])
    tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    _set_input(bsdf, ["Metallic"], MAT_PARAMS["metallic"])
    _set_input(bsdf, ["Roughness"], MAT_PARAMS["roughness"])
    _set_input(bsdf, ["Transmission Weight", "Transmission"], MAT_PARAMS["transmission"])
    _set_input(bsdf, ["IOR"], MAT_PARAMS["ior"])
    _set_input(bsdf, ["Subsurface Weight", "Subsurface"], MAT_PARAMS["subsurface"])
    if MAT_PARAMS["transmission"] > 0.5 and hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    return mat


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block_list in (bpy.data.meshes, bpy.data.materials, bpy.data.curves):
        for block in list(block_list):
            if block.users == 0:
                block_list.remove(block)


def get_collection():
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION_NAME)
        bpy.context.scene.collection.children.link(coll)
    return coll


def link_to(coll, obj):
    for other in list(obj.users_collection):
        other.objects.unlink(obj)
    coll.objects.link(obj)


def shade_smooth(obj):
    if not SHADE_SMOOTH or obj.type != "MESH":
        return
    for poly in obj.data.polygons:
        poly.use_smooth = True


def add_deform_modifiers(obj):
    # SimpleDeform (bend/twist) also works on curve bonds; Displace and
    # Subsurf are mesh-only.
    if obj.type not in ("MESH", "CURVE"):
        return
    if obj.type == "MESH" and SUBDIV_LEVEL > 0:
        mod = obj.modifiers.new("StyleSubdiv", "SUBSURF")
        mod.levels = SUBDIV_LEVEL
        mod.render_levels = SUBDIV_LEVEL
    if obj.type == "MESH" and NOISE_STRENGTH > 0.0:
        tex = bpy.data.textures.get("BlenderExportProNoise")
        if tex is None:
            tex = bpy.data.textures.new("BlenderExportProNoise", type="CLOUDS")
            tex.noise_scale = NOISE_SCALE
        mod = obj.modifiers.new("StyleDisplace", "DISPLACE")
        mod.texture = tex
        mod.strength = NOISE_STRENGTH
        mod.texture_coords = "GLOBAL"
    if abs(BEND_DEG) > 0.01:
        mod = obj.modifiers.new("StyleBend", "SIMPLE_DEFORM")
        mod.deform_method = "BEND"
        mod.angle = math.radians(BEND_DEG)
    if abs(TWIST_DEG) > 0.01:
        mod = obj.modifiers.new("StyleTwist", "SIMPLE_DEFORM")
        mod.deform_method = "TWIST"
        mod.angle = math.radians(TWIST_DEG)


def create_atom(coll, index, rec):
    loc = Vector(rec["pos"])
    if ATOM_SHAPE == "metaball":
        bpy.ops.object.metaball_add(type="BALL", location=loc, radius=rec["radius"] * 1.3)
        obj = bpy.context.active_object
    elif ATOM_SHAPE == "ico_sphere":
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=max(1, ATOM_SUBDIV), radius=rec["radius"], location=loc)
        obj = bpy.context.active_object
    else:
        seg = max(8, ATOM_SUBDIV * 8)
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=seg, ring_count=max(4, seg // 2),
            radius=rec["radius"], location=loc)
        obj = bpy.context.active_object

    obj.name = "Atom_%03d_%s" % (index, rec["symbol"])
    if ATOM_JITTER > 0.0:
        obj.scale = tuple(
            1.0 + random.uniform(-ATOM_JITTER, ATOM_JITTER) * 0.5 for _ in range(3))

    mat = make_material("Mat_%s_%s" % (MAT_PRESET, rec["symbol"]), rec["color"])
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(mat)
    link_to(coll, obj)
    shade_smooth(obj)
    add_deform_modifiers(obj)
    return obj


def _perpendicular(direction):
    axis = Vector((0.0, 0.0, 1.0))
    if abs(direction.dot(axis)) > 0.99:
        axis = Vector((0.0, 1.0, 0.0))
    return direction.cross(axis).normalized()


def create_bond_segment(coll, name, start, end, radius, color,
                        gradient_to=None):
    direction = end - start
    length = direction.length
    if length < 1e-6:
        return None
    mid = (start + end) / 2.0

    if BOND_STYLE == "curve":
        curve = bpy.data.curves.new(name, type="CURVE")
        curve.dimensions = "3D"
        curve.bevel_depth = radius
        curve.bevel_resolution = max(2, BOND_SEGMENTS // 8)
        spline = curve.splines.new("POLY")
        spline.points.add(1)
        spline.points[0].co = (start.x, start.y, start.z, 1.0)
        spline.points[1].co = (end.x, end.y, end.z, 1.0)
        obj = bpy.data.objects.new(name, curve)
        bpy.context.scene.collection.objects.link(obj)
    else:
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=max(6, BOND_SEGMENTS), radius=radius, depth=length, location=mid)
        obj = bpy.context.active_object
        obj.name = name
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = direction.to_track_quat("Z", "Y")

    if gradient_to is not None:
        mat = make_gradient_material(
            "Mat_%s_grad_%s_%s" % (MAT_PRESET, _color_key(color),
                                   _color_key(gradient_to)),
            color, gradient_to)
    else:
        # one material per color (a shared name would freeze the first color)
        mat = make_material(
            "Mat_%s_bond_%s" % (MAT_PRESET, _color_key(color)), color)
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(mat)
    link_to(coll, obj)
    shade_smooth(obj)
    add_deform_modifiers(obj)
    return obj


def create_bond(coll, index, rec):
    a = ATOMS[rec["a"]]
    b = ATOMS[rec["b"]]
    start = Vector(a["pos"])
    end = Vector(b["pos"])
    color_a = list(a["color"])
    color_b = list(b["color"])
    if BOND_COLOR_MODE == "single":
        color_a = color_b = list(BOND_COLOR)
    elif BOND_COLOR_MODE not in ("split", "gradient"):
        avg = [(color_a[k] + color_b[k]) / 2.0 for k in range(3)]
        color_a = color_b = avg
    order = rec["order"]

    if order <= 1:
        offsets = [0.0]
    elif order == 2:
        offsets = [-MULTI_BOND_OFFSET / 2.0, MULTI_BOND_OFFSET / 2.0]
    else:
        offsets = [-MULTI_BOND_OFFSET, 0.0, MULTI_BOND_OFFSET]

    direction = (end - start).normalized()
    perp = _perpendicular(direction)
    radius = BOND_RADIUS if order <= 1 else BOND_RADIUS * MULTI_BOND_SCALE
    mid = (start + end) / 2.0
    for k, off in enumerate(offsets):
        shift = perp * off
        name = "Bond_%03d_%d" % (index, k)
        if BOND_COLOR_MODE == "split" and color_a != color_b:
            create_bond_segment(coll, name + "a", start + shift, mid + shift,
                                radius, color_a)
            create_bond_segment(coll, name + "b", mid + shift, end + shift,
                                radius, color_b)
        elif BOND_COLOR_MODE == "gradient" and color_a != color_b:
            create_bond_segment(coll, name, start + shift, end + shift,
                                radius, color_a, gradient_to=color_b)
        else:
            create_bond_segment(coll, name, start + shift, end + shift,
                                radius, color_a)


def make_ring_material(name, rgb, alpha):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            bsdf = node
            break
    if bsdf is not None:
        _set_input(bsdf, ["Base Color"], (rgb[0], rgb[1], rgb[2], 1.0))
        _set_input(bsdf, ["Roughness"], 0.4)
        _set_input(bsdf, ["Alpha"], alpha)
    if alpha < 1.0 and hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    mat.diffuse_color = (rgb[0], rgb[1], rgb[2], alpha)
    return mat


def create_ring_panel(coll, index, rec):
    """Draw a ring (e.g. benzene) as a filled polygon panel / plate.

    Each record carries its own scale/thickness/opacity/color so single
    rings can be styled individually.
    """
    if not rec.get("visible", True):
        return None
    thickness = rec.get("thickness", RING_THICKNESS)
    opacity = rec.get("opacity", RING_OPACITY)
    verts = _ring_verts(rec)

    name = "RingPanel_%03d" % index
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], [list(range(len(verts)))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)

    if thickness > 0.0:
        mod = obj.modifiers.new("RingSolidify", "SOLIDIFY")
        mod.thickness = thickness
        mod.offset = 0.0
        if RING_BEVEL:
            # Softly rounded plate edges read better than razor-sharp ones.
            bev = obj.modifiers.new("RingBevel", "BEVEL")
            bev.width = min(thickness * 0.25, 0.03)
            bev.segments = 2
            bev.limit_method = "ANGLE"

    mat_name = "Mat_ring_%s_%.2f" % (
        "_".join("%.3f" % c for c in rec["color"]), opacity)
    mat = make_ring_material(mat_name, rec["color"], opacity)
    obj.data.materials.append(mat)
    link_to(coll, obj)
    return obj


def _ring_verts(rec):
    """Ring corner positions, inset toward the center by the ring's scale."""
    verts = [Vector(ATOMS[i]["pos"]) for i in rec["indices"]]
    center = Vector((0.0, 0.0, 0.0))
    for v in verts:
        center += v
    center /= len(verts)
    scale = rec.get("scale", RING_SCALE)
    return [center + (v - center) * scale for v in verts]


def create_ring_outline(coll, index, rec):
    """Draw the ring perimeter as a closed tube — the hexagon-line look."""
    if not rec.get("visible", True):
        return None
    verts = _ring_verts(rec)

    name = "RingOutline_%03d" % index
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = RING_OUTLINE_RADIUS
    curve.bevel_resolution = 4
    spline = curve.splines.new("POLY")
    spline.points.add(len(verts) - 1)
    for point, v in zip(spline.points, verts):
        point.co = (v.x, v.y, v.z, 1.0)
    spline.use_cyclic_u = True
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)

    mat_name = "Mat_ringline_%s" % "_".join("%.3f" % c for c in rec["color"])
    mat = make_ring_material(mat_name, rec["color"], 1.0)
    obj.data.materials.append(mat)
    link_to(coll, obj)
    return obj


def bounding_box():
    xs = [a["pos"][0] for a in ATOMS]
    ys = [a["pos"][1] for a in ATOMS]
    zs = [a["pos"][2] for a in ATOMS]
    center = Vector(((min(xs) + max(xs)) / 2.0,
                     (min(ys) + max(ys)) / 2.0,
                     (min(zs) + max(zs)) / 2.0))
    size = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)
    return center, size


def setup_scene(coll):
    if SCENE_PRESET == "none":
        return
    center, size = bounding_box()

    def add_light(name, kind, location, energy, color=None, area_size=None):
        light = bpy.data.lights.new(name, kind)
        light.energy = energy
        if color is not None:
            light.color = (color[0], color[1], color[2])
        if area_size is not None and hasattr(light, "size"):
            light.size = area_size
        obj = bpy.data.objects.new(name, light)
        obj.location = location
        # aim the light at the molecule center
        aim = center - location
        if aim.length > 1e-6:
            obj.rotation_mode = "QUATERNION"
            obj.rotation_quaternion = aim.to_track_quat("-Z", "Y")
        bpy.context.scene.collection.objects.link(obj)
        return obj

    def place(azimuth, elevation, distance_scale):
        az, el = math.radians(azimuth), math.radians(elevation)
        d = size * distance_scale
        return center + Vector((math.cos(el) * math.sin(az),
                                -math.cos(el) * math.cos(az),
                                math.sin(el))) * d

    if USE_CUSTOM_LIGHTS and CUSTOM_LIGHTS:
        for spec in CUSTOM_LIGHTS:
            add_light(
                spec.get("name", "Light"),
                spec.get("type", "AREA"),
                place(spec.get("azimuth", -45.0), spec.get("elevation", 45.0),
                      spec.get("distance", 2.5)),
                spec.get("energy", 1000.0),
                color=spec.get("color"),
                area_size=spec.get("size"))
        return

    dist = size * LIGHT_DISTANCE_SCALE
    key_energy = (1000.0 if SCENE_PRESET == "studio" else 400.0) * KEY_LIGHT_STRENGTH

    # Key light placed on a sphere around the center from azimuth/elevation.
    az = math.radians(KEY_LIGHT_AZIMUTH)
    el = math.radians(KEY_LIGHT_ELEVATION)
    key_dir = Vector((math.cos(el) * math.sin(az),
                      -math.cos(el) * math.cos(az),
                      math.sin(el)))
    add_light("BEP_Key", "AREA", center + key_dir * dist, key_energy)
    # Fill from the opposite azimuth, rim from behind — relative to the key.
    fill_dir = Vector((-key_dir.x, -key_dir.y, abs(key_dir.z) * 0.5 + 0.2))
    add_light("BEP_Fill", "AREA", center + fill_dir * dist,
              key_energy * FILL_LIGHT_STRENGTH)
    add_light("BEP_Rim", "AREA",
              center + Vector((-key_dir.x, key_dir.y, key_dir.z)) * dist,
              key_energy * RIM_LIGHT_STRENGTH)

    if ADD_GROUND:
        zmin = min(a["pos"][2] - a["radius"] for a in ATOMS)
        bpy.ops.mesh.primitive_plane_add(
            size=size * 20.0, location=(center.x, center.y, zmin - 0.2))
        ground = bpy.context.active_object
        ground.name = "BEP_Ground"
        if hasattr(ground, "is_shadow_catcher"):
            ground.is_shadow_catcher = True

    if ADD_CAMERA:
        cam_data = bpy.data.cameras.new("BEP_Camera")
        cam = bpy.data.objects.new("BEP_Camera", cam_data)
        # 0.4375 keeps the stock 3.2 : 1.4 back/up framing ratio.
        cam.location = center + Vector(
            (0.0, -size * CAMERA_DISTANCE_SCALE,
             size * CAMERA_DISTANCE_SCALE * 0.4375))
        bpy.context.scene.collection.objects.link(cam)
        direction = center - cam.location
        cam.rotation_mode = "QUATERNION"
        cam.rotation_quaternion = direction.to_track_quat("-Z", "Y")
        bpy.context.scene.camera = cam


def setup_background():
    """World background: scene-preset color, custom color, HDRI image, or
    transparent film."""
    scene = bpy.context.scene
    if BG_MODE == "transparent":
        scene.render.film_transparent = True
        return
    if BG_MODE == "preset" and SCENE_PRESET == "none":
        return  # leave the world untouched

    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("BEP_World")
        scene.world = world
    world.use_nodes = True
    tree = world.node_tree
    bg = tree.nodes.get("Background")
    if bg is None:
        return

    if BG_MODE == "hdri" and HDRI_PATH:
        try:
            img = bpy.data.images.load(HDRI_PATH, check_existing=True)
            env = tree.nodes.new("ShaderNodeTexEnvironment")
            env.image = img
            env.location = (bg.location.x - 300, bg.location.y)
            tree.links.new(env.outputs["Color"], bg.inputs["Color"])
            bg.inputs[1].default_value = HDRI_STRENGTH
            return
        except Exception as exc:
            print("Blender Export Pro: could not load HDRI %r: %s"
                  % (HDRI_PATH, exc))

    if BG_MODE == "color":
        bg.inputs[0].default_value = (BG_COLOR[0], BG_COLOR[1], BG_COLOR[2], 1.0)
    elif SCENE_PRESET == "dark":
        bg.inputs[0].default_value = (0.01, 0.01, 0.015, 1.0)
    else:
        bg.inputs[0].default_value = (0.9, 0.9, 0.92, 1.0)
    bg.inputs[1].default_value = 1.0


def setup_render():
    """Optional render engine / quality / resolution setup."""
    if RENDER_ENGINE == "keep":
        return
    scene = bpy.context.scene
    if RENDER_ENGINE == "cycles":
        try:
            scene.render.engine = "CYCLES"
            scene.cycles.samples = RENDER_SAMPLES
        except Exception as exc:
            print("Blender Export Pro: Cycles setup failed: %s" % exc)
    else:
        for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            try:
                scene.render.engine = name
                break
            except Exception:
                continue
        try:
            scene.eevee.taa_render_samples = RENDER_SAMPLES
        except Exception as exc:
            print("Blender Export Pro: EEVEE samples setup failed: %s" % exc)
    scene.render.resolution_x = RESOLUTION[0]
    scene.render.resolution_y = RESOLUTION[1]


def create_labels(coll):
    """3D text labels for atom symbols/indices, optionally camera-billboarded."""
    if LABEL_MODE == "none":
        return
    mat = bpy.data.materials.new("Mat_bep_label")
    mat.use_nodes = True
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            _set_input(node, ["Base Color"],
                       (LABEL_COLOR[0], LABEL_COLOR[1], LABEL_COLOR[2], 1.0))
            _set_input(node, ["Roughness"], 1.0)
            break
    mat.diffuse_color = (LABEL_COLOR[0], LABEL_COLOR[1], LABEL_COLOR[2], 1.0)

    cam = bpy.context.scene.camera
    for idx, rec in enumerate(ATOMS):
        if not rec.get("visible", True):
            continue
        if LABEL_MODE == "symbol":
            text = rec["symbol"]
        elif LABEL_MODE == "index":
            text = str(idx)
        else:
            text = "%s%d" % (rec["symbol"], idx)

        curve = bpy.data.curves.new("Label_%03d" % idx, type="FONT")
        curve.body = text
        curve.size = LABEL_SIZE
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        obj = bpy.data.objects.new("Label_%03d" % idx, curve)
        obj.location = Vector(rec["pos"]) + Vector(
            (0.0, 0.0, rec["radius"] * LABEL_OFFSET + LABEL_SIZE * 0.5))
        bpy.context.scene.collection.objects.link(obj)
        if obj.data and hasattr(obj.data, "materials"):
            obj.data.materials.append(mat)
        if LABEL_FACE_CAMERA and cam is not None:
            constraint = obj.constraints.new("TRACK_TO")
            constraint.target = cam
            constraint.track_axis = "TRACK_Z"
            constraint.up_axis = "UP_Y"
        link_to(coll, obj)


def render_image():
    """Render and save an image (or animation) when RENDER_ON_RUN is set."""
    if not RENDER_ON_RUN or not RENDER_OUTPUT_PATH:
        return
    scene = bpy.context.scene
    if scene.camera is None:
        print("Blender Export Pro: no camera, skipping render.")
        return
    scene.render.image_settings.file_format = IMAGE_FORMAT
    scene.render.filepath = RENDER_OUTPUT_PATH
    if TURNTABLE_FRAMES > 0:
        bpy.ops.render.render(animation=True)
    else:
        bpy.ops.render.render(write_still=True)
    print("Blender Export Pro: rendered to %s" % RENDER_OUTPUT_PATH)


def setup_turntable(coll):
    if TURNTABLE_FRAMES <= 0:
        return
    center, _size = bounding_box()
    pivot = bpy.data.objects.new("BEP_Turntable", None)
    pivot.location = center
    bpy.context.scene.collection.objects.link(pivot)
    for obj in coll.objects:
        if obj.parent is None:
            obj.parent = pivot
            obj.matrix_parent_inverse = pivot.matrix_world.inverted()
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = TURNTABLE_FRAMES
    pivot.rotation_euler = (0.0, 0.0, 0.0)
    pivot.keyframe_insert(data_path="rotation_euler", frame=1)
    pivot.rotation_euler = (0.0, 0.0, math.radians(360.0))
    pivot.keyframe_insert(data_path="rotation_euler", frame=TURNTABLE_FRAMES)
    if pivot.animation_data and pivot.animation_data.action:
        for fcurve in pivot.animation_data.action.fcurves:
            for kp in fcurve.keyframe_points:
                kp.interpolation = "LINEAR"


def main():
    if CLEAR_SCENE:
        clear_scene()
    coll = get_collection()
    for idx, rec in enumerate(ATOMS):
        if rec.get("visible", True):
            create_atom(coll, idx, rec)
    for idx, rec in enumerate(BONDS):
        if rec.get("visible", True):
            create_bond(coll, idx, rec)
    for idx, rec in enumerate(RINGS):
        if "panel" in RING_STYLE:
            create_ring_panel(coll, idx, rec)
        if "outline" in RING_STYLE:
            create_ring_outline(coll, idx, rec)
    setup_scene(coll)
    setup_background()
    setup_render()
    create_labels(coll)
    setup_turntable(coll)
    render_image()
    print("Blender Export Pro: built %d atoms / %d bonds." % (len(ATOMS), len(BONDS)))


main()
'''
    return header + body


def generate_script_from_mol(mol, cfg: StyleConfig, selected_indices=None) -> str:
    """Convenience wrapper: extract geometry from an RDKit Mol and generate."""
    atoms, bonds = extract_geometry(mol, selected_indices)
    if not atoms:
        raise ValueError("No atoms to export.")
    atom_keys = _keep_list(mol.GetNumAtoms(), selected_indices)
    rings, ring_keys = [], []
    if cfg.ring_style != "none":
        rings = extract_rings(mol, selected_indices, cfg.ring_aromatic_only)
        originals = extract_rings(
            mol, selected_indices, cfg.ring_aromatic_only, keep_original=True)
        ring_keys = [ring_key(r) for r in originals]
    return generate_script(atoms, bonds, cfg, rings, ring_keys, atom_keys)
