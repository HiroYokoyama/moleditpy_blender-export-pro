"""Blender-free 3D export: glTF binary (.glb) and USD ascii (.usda).

For users who don't have Blender, this bakes the molecule to standard 3D
files that open in Windows 3D Viewer, web viewers, PowerPoint, Blender,
Maya, etc. Pure stdlib + math (no numpy/bpy/rdkit) so it stays testable.

Geometry is merged per unique color: one mesh/material per color group,
with sphere and cylinder primitives pre-transformed into world space.
"""

import json
import math
import struct

from .blender_codegen import (
    extract_geometry,
    extract_rings,
    hidden_hydrogen_indices,
    resolve_atom_color,
    resolve_atom_radius,
    resolve_bond_color,
    ring_hidden_geometry,
    ring_key,
)
from .style_config import StyleConfig


def _unit_sphere(segments=16, rings=8):
    """Unit-radius UV sphere: (positions, normals, triangle indices)."""
    verts, normals, faces = [], [], []
    for r in range(rings + 1):
        theta = math.pi * r / rings
        st, ct = math.sin(theta), math.cos(theta)
        for s in range(segments + 1):
            phi = 2.0 * math.pi * s / segments
            x, y, z = st * math.cos(phi), ct, st * math.sin(phi)
            verts.append((x, y, z))
            normals.append((x, y, z))
    row = segments + 1
    for r in range(rings):
        for s in range(segments):
            a = r * row + s
            b = a + row
            faces += [a, b, a + 1, a + 1, b, b + 1]
    return verts, normals, faces


def _unit_cylinder(segments=12):
    """Unit cylinder along +Z, radius 1, height 1 centered at origin."""
    verts, normals, faces = [], [], []
    for s in range(segments + 1):
        phi = 2.0 * math.pi * s / segments
        cx, cy = math.cos(phi), math.sin(phi)
        verts.append((cx, cy, -0.5))
        normals.append((cx, cy, 0.0))
        verts.append((cx, cy, 0.5))
        normals.append((cx, cy, 0.0))
    for s in range(segments):
        a = s * 2
        faces += [a, a + 1, a + 2, a + 2, a + 1, a + 3]
    return verts, normals, faces


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(v):
    length = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if length < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def _axis_angle_to_euler_xyz(axis, angle_deg):
    """Convert an angle-axis rotation to XYZ Euler degrees (for USD rotateXYZ)."""
    a = math.radians(angle_deg)
    x, y, z = _norm(axis)
    c, s, t = math.cos(a), math.sin(a), 1.0 - math.cos(a)
    # rotation matrix (row-major)
    m00 = t * x * x + c
    m01 = t * x * y - s * z
    m02 = t * x * z + s * y
    m10 = t * x * y + s * z
    m11 = t * y * y + c
    m12 = t * y * z - s * x
    m20 = t * x * z - s * y
    m21 = t * y * z + s * x
    m22 = t * z * z + c
    sy = math.sqrt(m00 * m00 + m10 * m10)
    if sy > 1e-6:
        rx = math.atan2(m21, m22)
        ry = math.atan2(-m20, sy)
        rz = math.atan2(m10, m00)
    else:  # gimbal lock
        rx = math.atan2(-m12, m11)
        ry = math.atan2(-m20, sy)
        rz = 0.0
    return math.degrees(rx), math.degrees(ry), math.degrees(rz)


def _basis_from_z(direction):
    """Orthonormal basis (x, y, z) with z along *direction*."""
    z = _norm(direction)
    ref = (0.0, 0.0, 1.0) if abs(z[2]) < 0.99 else (0.0, 1.0, 0.0)
    x = _norm(_cross(ref, z))
    y = _cross(z, x)
    return x, y, z


class _ColorGroup:
    """Accumulates merged geometry for one material color."""

    def __init__(self):
        self.positions = []
        self.normals = []
        self.indices = []

    def add(self, verts, normals, faces, transform, normal_transform):
        base = len(self.positions)
        for v in verts:
            self.positions.append(transform(v))
        for n in normals:
            self.normals.append(_norm(normal_transform(n)))
        self.indices.extend(base + i for i in faces)


def _sphere_transform(center, radius):
    def t(v):
        return (v[0] * radius + center[0],
                v[1] * radius + center[1],
                v[2] * radius + center[2])
    return t


def _oriented_transform(start, end, radius):
    """Map a unit +Z cylinder onto the segment start->end with given radius."""
    direction = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
    length = math.sqrt(sum(d * d for d in direction))
    x, y, z = _basis_from_z(direction)
    mid = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0,
           (start[2] + end[2]) / 2.0)

    def pos(v):
        sx, sy, sz = v[0] * radius, v[1] * radius, v[2] * length
        return (x[0] * sx + y[0] * sy + z[0] * sz + mid[0],
                x[1] * sx + y[1] * sy + z[1] * sz + mid[1],
                x[2] * sx + y[2] * sy + z[2] * sz + mid[2])

    def nrm(v):
        return (x[0] * v[0] + y[0] * v[1] + z[0] * v[2],
                x[1] * v[0] + y[1] * v[1] + z[1] * v[2],
                x[2] * v[0] + y[2] * v[1] + z[2] * v[2])

    return pos, nrm, length


def build_color_groups(atoms, bonds, cfg: StyleConfig, atom_keys=None,
                       rings=None, ring_keys=None):
    """Merge all geometry into {color_hexkey: (_ColorGroup, rgb)}.

    Honors hidden hydrogens and ring atom/bond hiding so the exported mesh
    matches the preview and the Blender script.
    """
    sphere = _unit_sphere()
    cylinder = _unit_cylinder()
    groups = {}

    def group_for(rgb):
        key = "%.4f_%.4f_%.4f" % tuple(rgb)
        if key not in groups:
            groups[key] = (_ColorGroup(), tuple(rgb))
        return groups[key][0]

    hidden_atoms, hide_bond_rings = ring_hidden_geometry(
        cfg, rings or [], ring_keys)
    hidden_atoms = set(hidden_atoms) | hidden_hydrogen_indices(atoms, cfg)
    hydrogens = hidden_hydrogen_indices(atoms, cfg)

    colors = []
    for pos_idx, (symbol, pos) in enumerate(atoms):
        orig = atom_keys[pos_idx] if atom_keys else pos_idx
        radius = resolve_atom_radius(cfg, symbol, orig)
        rgb = resolve_atom_color(cfg, symbol, orig)
        colors.append(rgb)
        if pos_idx in hidden_atoms:
            continue
        t = _sphere_transform(pos, radius)
        group_for(rgb).add(sphere[0], sphere[1], sphere[2], t, lambda n: n)

    for i, j, _order in bonds:
        if i in hydrogens or j in hydrogens:
            continue
        if any(i in members and j in members for members in hide_bond_rings):
            continue
        rgb = resolve_bond_color(cfg, colors[i], colors[j])
        pos_t, nrm_t, length = _oriented_transform(
            atoms[i][1], atoms[j][1], max(cfg.bond_radius, 0.01))
        if length < 1e-6:
            continue
        group_for(rgb).add(
            cylinder[0], cylinder[1], cylinder[2], pos_t, nrm_t)

    return groups


# --------------------------------------------------------------------- glTF


def _pad(data, alignment=4, fill=b"\x00"):
    remainder = len(data) % alignment
    return data if remainder == 0 else data + fill * (alignment - remainder)


def build_glb(atoms, bonds, cfg: StyleConfig, atom_keys=None,
              rings=None, ring_keys=None) -> bytes:
    """Return a binary glTF (.glb) document for the molecule."""
    groups = build_color_groups(atoms, bonds, cfg, atom_keys, rings, ring_keys)

    bin_blob = bytearray()
    accessors, buffer_views, meshes, materials, nodes = [], [], [], [], []

    for group, rgb in groups.values():
        if not group.positions:
            continue
        # index buffer view
        idx_bytes = struct.pack("<%dI" % len(group.indices), *group.indices)
        idx_offset = len(bin_blob)
        bin_blob += _pad(idx_bytes)
        idx_view = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": idx_offset,
                             "byteLength": len(idx_bytes), "target": 34963})

        # position buffer view
        flat_pos = [c for v in group.positions for c in v]
        pos_bytes = struct.pack("<%df" % len(flat_pos), *flat_pos)
        pos_offset = len(bin_blob)
        bin_blob += _pad(pos_bytes)
        pos_view = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": pos_offset,
                             "byteLength": len(pos_bytes), "target": 34962})

        flat_nrm = [c for v in group.normals for c in v]
        nrm_bytes = struct.pack("<%df" % len(flat_nrm), *flat_nrm)
        nrm_offset = len(bin_blob)
        bin_blob += _pad(nrm_bytes)
        nrm_view = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": nrm_offset,
                             "byteLength": len(nrm_bytes), "target": 34962})

        xs = [v[0] for v in group.positions]
        ys = [v[1] for v in group.positions]
        zs = [v[2] for v in group.positions]

        idx_acc = len(accessors)
        accessors.append({"bufferView": idx_view, "componentType": 5125,
                          "count": len(group.indices), "type": "SCALAR"})
        pos_acc = len(accessors)
        accessors.append({"bufferView": pos_view, "componentType": 5126,
                          "count": len(group.positions), "type": "VEC3",
                          "min": [min(xs), min(ys), min(zs)],
                          "max": [max(xs), max(ys), max(zs)]})
        nrm_acc = len(accessors)
        accessors.append({"bufferView": nrm_view, "componentType": 5126,
                          "count": len(group.normals), "type": "VEC3"})

        mat_idx = len(materials)
        materials.append({
            "pbrMetallicRoughness": {
                "baseColorFactor": [rgb[0], rgb[1], rgb[2], 1.0],
                "metallicFactor": 0.0, "roughnessFactor": 0.5,
            },
            "name": "col_%d" % mat_idx,
        })
        mesh_idx = len(meshes)
        meshes.append({"primitives": [{
            "attributes": {"POSITION": pos_acc, "NORMAL": nrm_acc},
            "indices": idx_acc, "material": mat_idx}]})
        nodes.append({"mesh": mesh_idx})

    gltf = {
        "asset": {"version": "2.0", "generator": "MoleditPy Blender Export Pro"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(bin_blob)}],
    }

    json_bytes = _pad(json.dumps(gltf).encode("utf-8"), fill=b" ")
    bin_bytes = _pad(bytes(bin_blob))
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, total)
    out += struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes
    out += struct.pack("<I4s", len(bin_bytes), b"BIN\x00") + bin_bytes
    return bytes(out)


# ---------------------------------------------------------------------- USD


def build_usda(atoms, bonds, cfg: StyleConfig, atom_keys=None,
               rings=None, ring_keys=None) -> str:
    """Return an ASCII USD (.usda) document using native Sphere/Cylinder prims."""
    hidden_atoms, hide_bond_rings = ring_hidden_geometry(
        cfg, rings or [], ring_keys)
    hidden_atoms = set(hidden_atoms) | hidden_hydrogen_indices(atoms, cfg)
    hydrogens = hidden_hydrogen_indices(atoms, cfg)

    lines = [
        '#usda 1.0',
        '(',
        '    defaultPrim = "Molecule"',
        '    upAxis = "Z"',
        '    metersPerUnit = 1',
        ')',
        '',
        'def Xform "Molecule"',
        '{',
    ]

    colors = []
    for pos_idx, (symbol, pos) in enumerate(atoms):
        orig = atom_keys[pos_idx] if atom_keys else pos_idx
        radius = resolve_atom_radius(cfg, symbol, orig)
        rgb = resolve_atom_color(cfg, symbol, orig)
        colors.append(rgb)
        if pos_idx in hidden_atoms:
            continue
        lines += [
            '    def Sphere "Atom_%03d"' % pos_idx,
            '    {',
            '        double radius = %g' % radius,
            '        color3f[] primvars:displayColor = [(%g, %g, %g)]'
            % (rgb[0], rgb[1], rgb[2]),
            '        double3 xformOp:translate = (%g, %g, %g)'
            % (pos[0], pos[1], pos[2]),
            '        uniform token[] xformOpOrder = ["xformOp:translate"]',
            '    }',
        ]

    for bidx, (i, j, _order) in enumerate(bonds):
        if i in hydrogens or j in hydrogens:
            continue
        if any(i in members and j in members for members in hide_bond_rings):
            continue
        start, end = atoms[i][1], atoms[j][1]
        direction = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
        length = math.sqrt(sum(d * d for d in direction))
        if length < 1e-6:
            continue
        mid = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0,
               (start[2] + end[2]) / 2.0)
        rgb = resolve_bond_color(cfg, colors[i], colors[j])
        # USD cylinder default axis is Z; rotate Z onto the bond direction
        # with a single angle-axis (rotateXYZ built from the rotation matrix).
        z = _norm(direction)
        axis = _cross((0.0, 0.0, 1.0), z)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, z[2]))))
        axis = _norm(axis) if any(a for a in axis) else (1.0, 0.0, 0.0)
        rx, ry, rz = _axis_angle_to_euler_xyz(axis, angle)
        lines += [
            '    def Cylinder "Bond_%03d"' % bidx,
            '    {',
            '        double radius = %g' % max(cfg.bond_radius, 0.01),
            '        double height = %g' % length,
            '        uniform token axis = "Z"',
            '        color3f[] primvars:displayColor = [(%g, %g, %g)]'
            % (rgb[0], rgb[1], rgb[2]),
            '        double3 xformOp:translate = (%g, %g, %g)'
            % (mid[0], mid[1], mid[2]),
            '        float3 xformOp:rotateXYZ = (%g, %g, %g)' % (rx, ry, rz),
            '        uniform token[] xformOpOrder = '
            '["xformOp:translate", "xformOp:rotateXYZ"]',
            '    }',
        ]

    lines += ['}', '']
    return "\n".join(lines)


def export_mesh_file(mol, cfg: StyleConfig, path: str, selected_indices=None):
    """Write a .glb or .usda file for *mol*. Format from the path extension."""
    atoms, bonds = extract_geometry(mol, selected_indices)
    if not atoms:
        raise ValueError("No atoms to export.")
    from .blender_codegen import _keep_list
    atom_keys = _keep_list(mol.GetNumAtoms(), selected_indices)

    rings, ring_keys = [], []
    if cfg.ring_style != "none":
        rings = extract_rings(mol, selected_indices, cfg.ring_aromatic_only)
        originals = extract_rings(
            mol, selected_indices, cfg.ring_aromatic_only, keep_original=True)
        ring_keys = [ring_key(r) for r in originals]

    lower = path.lower()
    if lower.endswith((".usda", ".usd")):
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_usda(atoms, bonds, cfg, atom_keys, rings, ring_keys))
    else:
        with open(path, "wb") as f:
            f.write(build_glb(atoms, bonds, cfg, atom_keys, rings, ring_keys))
