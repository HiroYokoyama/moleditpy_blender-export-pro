"""Tests for the Blender-free glTF / USD mesh export."""

import json
import struct

from conftest import make_benzene_like, make_ethanol_like

from blender_export_pro import mesh_export as me
from blender_export_pro.style_config import StyleConfig


def _parse_glb(blob):
    magic, version, total = struct.unpack("<4sII", blob[:12])
    assert magic == b"glTF"
    assert version == 2
    assert total == len(blob)
    jlen, jtag = struct.unpack("<I4s", blob[12:20])
    assert jtag == b"JSON"
    gltf = json.loads(blob[20:20 + jlen])
    off = 20 + jlen
    _blen, btag = struct.unpack("<I4s", blob[off:off + 8])
    assert btag == b"BIN\x00"
    return gltf


def test_glb_is_valid_and_has_geometry():
    atoms, bonds = me.extract_geometry(make_benzene_like())
    gltf = _parse_glb(me.build_glb(atoms, bonds, StyleConfig()))
    assert gltf["asset"]["version"] == "2.0"
    assert gltf["meshes"] and gltf["materials"] and gltf["accessors"]
    # every accessor count is positive
    assert all(a["count"] > 0 for a in gltf["accessors"])


def test_glb_chunks_are_4byte_aligned():
    atoms, bonds = me.extract_geometry(make_ethanol_like())
    blob = me.build_glb(atoms, bonds, StyleConfig())
    assert len(blob) % 4 == 0


def test_glb_merges_by_color():
    """Same-colored geometry shares a material (fewer materials than prims)."""
    atoms, bonds = me.extract_geometry(make_ethanol_like())  # C C O H, 3 bonds
    gltf = _parse_glb(me.build_glb(atoms, bonds, StyleConfig()))
    # 4 atoms + 3 bonds = 7 primitives; the two carbons share one material,
    # so the material count must be strictly fewer than the primitive count.
    assert len(gltf["materials"]) < len(atoms) + len(bonds)
    assert len(gltf["meshes"]) == len(gltf["materials"])


def test_glb_single_color_mode_one_material():
    atoms, bonds = me.extract_geometry(make_benzene_like())
    cfg = StyleConfig(color_mode="single", single_color="#808080",
                      bond_color_mode="single", bond_color="#808080")
    gltf = _parse_glb(me.build_glb(atoms, bonds, cfg))
    assert len(gltf["materials"]) == 1


def test_usda_structure():
    atoms, bonds = me.extract_geometry(make_benzene_like())
    usda = me.build_usda(atoms, bonds, StyleConfig())
    assert usda.startswith("#usda 1.0")
    assert usda.count("def Sphere") == 7        # 6 C + 1 Cl
    assert usda.count("def Cylinder") == len(bonds)
    assert "primvars:displayColor" in usda


def _benzene_with_rings(cfg):
    mol = make_benzene_like()
    atoms, bonds = me.extract_geometry(mol)
    rings = me.extract_rings(mol, None, cfg.ring_aromatic_only)
    ring_keys = [me.ring_key(r) for r in rings]
    return atoms, bonds, rings, ring_keys


def test_ring_plate_mesh_flat_and_thick():
    pts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    verts, normals, faces = me._ring_plate_mesh(pts, 0.0)
    assert len(verts) == len(normals) == 2 * 5   # centroid + corners, x2 faces
    assert len(faces) == 2 * 4 * 3               # two centroid fans of n tris
    verts, _normals, faces = me._ring_plate_mesh(pts, 0.2)
    assert len(faces) == (2 * 4 + 4 * 2) * 3     # fans + 2 tris per side quad
    zs = sorted({round(v[2], 6) for v in verts})
    assert zs == [-0.1, 0.1]                     # centered extrusion


def test_glb_ring_panel_is_transparent_material():
    cfg = StyleConfig(ring_style="panel", ring_color="#FF0000",
                      ring_opacity=0.5)
    atoms, bonds, rings, ring_keys = _benzene_with_rings(cfg)
    gltf = _parse_glb(me.build_glb(atoms, bonds, cfg, rings=rings,
                                   ring_keys=ring_keys))
    blended = [m for m in gltf["materials"] if m.get("alphaMode") == "BLEND"]
    assert len(blended) == 1
    assert blended[0]["pbrMetallicRoughness"]["baseColorFactor"] == \
        [1.0, 0.0, 0.0, 0.5]
    assert blended[0]["doubleSided"] is True


def test_glb_ring_outline_adds_a_material():
    cfg_none = StyleConfig(ring_style="none")
    cfg_line = StyleConfig(ring_style="outline", ring_color="#00FF00")
    atoms, bonds, rings, ring_keys = _benzene_with_rings(cfg_line)
    base = _parse_glb(me.build_glb(atoms, bonds, cfg_none))
    lined = _parse_glb(me.build_glb(atoms, bonds, cfg_line, rings=rings,
                                    ring_keys=ring_keys))
    assert len(lined["materials"]) == len(base["materials"]) + 1


def test_usda_ring_panel_and_outline():
    cfg = StyleConfig(ring_style="panel+outline", ring_opacity=0.4)
    atoms, bonds, rings, ring_keys = _benzene_with_rings(cfg)
    usda = me.build_usda(atoms, bonds, cfg, rings=rings, ring_keys=ring_keys)
    assert 'def Mesh "RingPanel_000"' in usda
    assert "primvars:displayOpacity = [0.4]" in usda
    assert 'def Cylinder "RingLine_000_0"' in usda
    # a 6-ring outline is 6 segments
    assert usda.count("RingLine_000_") == 6


def test_export_mesh_file_with_ring_style(tmp_path):
    cfg = StyleConfig(ring_style="panel+outline")
    for name in ("mol.glb", "mol.usda"):
        path = tmp_path / name
        me.export_mesh_file(make_benzene_like(), cfg, str(path))
        assert path.stat().st_size > 0


def test_export_mesh_file_glb(tmp_path):
    path = tmp_path / "mol.glb"
    me.export_mesh_file(make_benzene_like(), StyleConfig(), str(path))
    data = path.read_bytes()
    assert data[:4] == b"glTF"


def test_export_mesh_file_usda(tmp_path):
    path = tmp_path / "mol.usda"
    me.export_mesh_file(make_benzene_like(), StyleConfig(), str(path))
    assert path.read_text(encoding="utf-8").startswith("#usda 1.0")


def test_export_mesh_file_empty_raises(tmp_path):
    from conftest import FakeMol
    import pytest

    with pytest.raises(ValueError):
        me.export_mesh_file(FakeMol([], [], []), StyleConfig(),
                            str(tmp_path / "x.glb"))


def test_euler_identity_and_90deg():
    assert me._axis_angle_to_euler_xyz((1, 0, 0), 0) == (0, 0, 0)
    rx, ry, rz = me._axis_angle_to_euler_xyz((1, 0, 0), 90)
    assert abs(rx - 90) < 1e-6 and abs(ry) < 1e-6 and abs(rz) < 1e-6
