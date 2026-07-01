"""Tests for geometry extraction and bpy script generation."""

import pytest

from conftest import FakeMol, make_ethanol_like

from blender_export_pro import blender_codegen as bc
from blender_export_pro.style_config import StyleConfig


# ------------------------------------------------------------- hex_to_rgb


def test_hex_to_rgb_valid():
    assert bc.hex_to_rgb("#FF0000") == (1.0, 0.0, 0.0)
    r, g, b = bc.hex_to_rgb("336699")
    assert abs(r - 0x33 / 255) < 1e-9
    assert abs(g - 0x66 / 255) < 1e-9
    assert abs(b - 0x99 / 255) < 1e-9


@pytest.mark.parametrize("bad", ["", None, "#12", "#GGGGGG", "zzz"])
def test_hex_to_rgb_fallback(bad):
    assert bc.hex_to_rgb(bad) == (0.8, 0.8, 0.8)


# ------------------------------------------------------- extract_geometry


def test_extract_geometry_full():
    atoms, bonds = bc.extract_geometry(make_ethanol_like())
    assert [s for s, _p in atoms] == ["C", "C", "O", "H"]
    assert bonds == [(0, 1, 1), (1, 2, 2), (0, 3, 1)]


def test_extract_geometry_selection_remaps_indices():
    atoms, bonds = bc.extract_geometry(make_ethanol_like(), selected_indices=[1, 2])
    assert [s for s, _p in atoms] == ["C", "O"]
    # only the C=O bond survives, remapped to local indices
    assert bonds == [(0, 1, 2)]


def test_extract_geometry_selection_out_of_range_ignored():
    atoms, _bonds = bc.extract_geometry(
        make_ethanol_like(), selected_indices=[0, 99, -5]
    )
    assert len(atoms) == 1


def test_extract_geometry_clamps_bond_order():
    mol = FakeMol(["C", "C"], [(0, 0, 0), (1, 0, 0)], [(0, 1, 9.0)])
    _atoms, bonds = bc.extract_geometry(mol)
    assert bonds == [(0, 1, 3)]


def test_extract_geometry_aromatic_order_rounds():
    mol = FakeMol(["C", "C"], [(0, 0, 0), (1, 0, 0)], [(0, 1, 1.5)])
    _atoms, bonds = bc.extract_geometry(mol)
    assert bonds[0][2] == 2


# -------------------------------------------------------- generate_script


ATOMS = [("C", (0.0, 0.0, 0.0)), ("O", (1.2, 0.0, 0.0)), ("H", (-0.6, 0.9, 0.0))]
BONDS = [(0, 1, 2), (0, 2, 1)]


def _generate(**overrides):
    return bc.generate_script(ATOMS, BONDS, StyleConfig(**overrides))


def test_script_compiles_for_all_material_presets():
    for preset in bc.MATERIAL_PRESET_PARAMS:
        script = _generate(material_preset=preset)
        compile(script, "<generated>", "exec")


def test_script_contains_geometry_and_config():
    script = _generate(collection_name="Benzene", turntable_frames=120)
    assert '"symbol": "C"' in script
    assert 'COLLECTION_NAME = \'Benzene\'' in script
    assert "TURNTABLE_FRAMES = 120" in script
    assert "import bpy" in script
    assert "def main():" in script


def test_script_never_imports_rdkit_or_pyvista():
    script = _generate()
    assert "rdkit" not in script
    assert "pyvista" not in script


def test_uniform_radius_mode():
    script = _generate(atom_radius_mode="uniform", uniform_radius=0.5)
    assert '"radius": 0.5' in script


def test_single_color_mode():
    script = _generate(color_mode="single", single_color="#FF0000")
    assert '"color": [\n   1.0,\n   0.0,\n   0.0\n  ]' in script.replace("\r\n", "\n")


def test_multiple_bonds_flag():
    on = _generate(show_multiple_bonds=True)
    off = _generate(show_multiple_bonds=False)
    assert '"order": 2' in on
    assert '"order": 2' not in off


def test_roughness_override():
    script = _generate(material_preset="plastic", roughness_override=0.77)
    assert '"roughness": 0.77' in script


def test_unknown_material_preset_falls_back():
    script = _generate(material_preset="does_not_exist")
    compile(script, "<generated>", "exec")
    assert '"roughness": 0.3' in script  # plastic defaults


def test_generate_script_from_mol():
    script = bc.generate_script_from_mol(make_ethanol_like(), StyleConfig())
    compile(script, "<generated>", "exec")
    assert '"symbol": "O"' in script


def test_generate_script_from_mol_empty_selection_raises():
    mol = FakeMol([], [], [])
    with pytest.raises(ValueError):
        bc.generate_script_from_mol(mol, StyleConfig())
