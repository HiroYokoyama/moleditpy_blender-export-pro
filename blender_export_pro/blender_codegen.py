"""Blender Python (bpy) script generation.

Pure string templating: this module never imports bpy or rdkit. It takes a
plain geometry description (extracted from an RDKit Mol by duck-typing) plus a
StyleConfig and emits a self-contained script runnable inside Blender 2.8x-4.x.
"""

import datetime
import json

from .element_data import radius_of, color_of
from .style_config import StyleConfig
from .version import __version__

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


def _atom_records(atoms, cfg: StyleConfig, atom_keys=None):
    """Per-atom (symbol, position, radius, color) records for the script.

    atom_keys: original RDKit indices per atom (for per-atom overrides);
    defaults to the export position.
    """
    records = []
    for pos_idx, (symbol, pos) in enumerate(atoms):
        orig = atom_keys[pos_idx] if atom_keys else pos_idx
        radius = resolve_atom_radius(cfg, symbol, orig)
        if cfg.color_mode == "single":
            color = hex_to_rgb(cfg.single_color)
        else:
            color = color_of(symbol)
        records.append(
            {
                "symbol": symbol,
                "pos": [round(c, 6) for c in pos],
                "radius": round(radius, 6),
                "color": [round(c, 4) for c in color],
            }
        )
    return records


def _bond_records(bonds, cfg: StyleConfig):
    return [
        {"a": i, "b": j, "order": order if cfg.show_multiple_bonds else 1}
        for i, j, order in bonds
    ]


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
    }


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

    atom_data = json.dumps(_atom_records(atoms, cfg, atom_keys), indent=1)
    bond_data = json.dumps(_bond_records(bonds, cfg), indent=1)
    ring_data = json.dumps(_ring_records(atoms, rings, cfg, ring_keys), indent=1)

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
RING_STYLE = {cfg.ring_style!r}
RING_SCALE = {float(cfg.ring_scale)!r}
RING_THICKNESS = {float(cfg.ring_thickness)!r}
RING_OPACITY = {float(cfg.ring_opacity)!r}
NOISE_STRENGTH = {float(cfg.deformation_noise)!r}
NOISE_SCALE = {float(cfg.deformation_noise_scale)!r}
BEND_DEG = {float(cfg.deformation_bend)!r}
TWIST_DEG = {float(cfg.deformation_twist)!r}
SUBDIV_LEVEL = {int(cfg.subdivision_level)!r}
SHADE_SMOOTH = {cfg.shade_smooth!r}
MAT_PARAMS = {json.dumps(params)}
MAT_PRESET = {cfg.material_preset!r}
SCENE_PRESET = {cfg.scene_preset!r}
ADD_GROUND = {cfg.add_ground_plane!r}
ADD_CAMERA = {cfg.add_camera!r}
TURNTABLE_FRAMES = {int(cfg.turntable_frames)!r}
BG_MODE = {cfg.background_mode!r}
BG_COLOR = {json.dumps([round(c, 4) for c in hex_to_rgb(cfg.background_color)])}
HDRI_PATH = {cfg.hdri_path!r}
HDRI_STRENGTH = {float(cfg.hdri_strength)!r}
RENDER_ENGINE = {cfg.render_engine!r}
RENDER_SAMPLES = {int(cfg.render_samples)!r}
RESOLUTION = ({int(cfg.resolution_x)!r}, {int(cfg.resolution_y)!r})

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
    if obj.type != "MESH":
        return
    if SUBDIV_LEVEL > 0:
        mod = obj.modifiers.new("StyleSubdiv", "SUBSURF")
        mod.levels = SUBDIV_LEVEL
        mod.render_levels = SUBDIV_LEVEL
    if NOISE_STRENGTH > 0.0:
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


def create_bond_segment(coll, name, start, end, radius, color):
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

    mat = make_material("Mat_%s_bond" % MAT_PRESET, color)
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
    color = [(a["color"][k] + b["color"][k]) / 2.0 for k in range(3)]
    order = rec["order"]

    if order <= 1:
        offsets = [0.0]
    elif order == 2:
        offsets = [-MULTI_BOND_OFFSET / 2.0, MULTI_BOND_OFFSET / 2.0]
    else:
        offsets = [-MULTI_BOND_OFFSET, 0.0, MULTI_BOND_OFFSET]

    direction = (end - start).normalized()
    perp = _perpendicular(direction)
    radius = BOND_RADIUS if order <= 1 else BOND_RADIUS * 0.7
    for k, off in enumerate(offsets):
        shift = perp * off
        create_bond_segment(
            coll, "Bond_%03d_%d" % (index, k), start + shift, end + shift,
            radius, color)


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
    scale = rec.get("scale", RING_SCALE)
    thickness = rec.get("thickness", RING_THICKNESS)
    opacity = rec.get("opacity", RING_OPACITY)

    verts = [Vector(ATOMS[i]["pos"]) for i in rec["indices"]]
    center = Vector((0.0, 0.0, 0.0))
    for v in verts:
        center += v
    center /= len(verts)
    verts = [center + (v - center) * scale for v in verts]

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

    mat_name = "Mat_ring_%s_%.2f" % (
        "_".join("%.3f" % c for c in rec["color"]), opacity)
    mat = make_ring_material(mat_name, rec["color"], opacity)
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

    def add_light(name, kind, location, energy):
        light = bpy.data.lights.new(name, kind)
        light.energy = energy
        obj = bpy.data.objects.new(name, light)
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)
        return obj

    dist = size * 2.5
    key_energy = 1000.0 if SCENE_PRESET == "studio" else 400.0
    add_light("BEP_Key", "AREA", center + Vector((dist, -dist, dist)), key_energy)
    add_light("BEP_Fill", "AREA", center + Vector((-dist, -dist * 0.5, dist * 0.5)), key_energy * 0.3)
    add_light("BEP_Rim", "AREA", center + Vector((0.0, dist, dist * 0.7)), key_energy * 0.5)

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
        cam.location = center + Vector((0.0, -size * 3.2, size * 1.4))
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
        create_atom(coll, idx, rec)
    for idx, rec in enumerate(BONDS):
        create_bond(coll, idx, rec)
    if RING_STYLE == "panel":
        for idx, rec in enumerate(RINGS):
            create_ring_panel(coll, idx, rec)
    setup_scene(coll)
    setup_background()
    setup_render()
    setup_turntable(coll)
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
