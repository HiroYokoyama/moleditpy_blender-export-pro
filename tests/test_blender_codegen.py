"""Tests for geometry extraction and bpy script generation."""

import pytest

from conftest import FakeMol, make_benzene_like, make_ethanol_like

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


def test_script_contains_version_info():
    from blender_export_pro.version import __version__

    script = _generate()
    assert f"Blender Export Pro v{__version__}" in script
    assert f"GENERATOR_VERSION = '{__version__}'" in script
    assert "Exported: " in script


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


# ---------------------------------------------------------------- rings


def test_extract_rings_aromatic_only():
    mol = make_benzene_like()
    assert bc.extract_rings(mol, aromatic_only=True) == [(0, 1, 2, 3, 4, 5)]


def test_extract_rings_non_aromatic_filtered():
    mol = FakeMol(
        ["C"] * 6,
        [(i, 0, 0) for i in range(6)],
        [],
        rings=[(0, 1, 2, 3, 4, 5)],
        aromatic=(),  # cyclohexane-like: not aromatic
    )
    assert bc.extract_rings(mol, aromatic_only=True) == []
    assert bc.extract_rings(mol, aromatic_only=False) == [(0, 1, 2, 3, 4, 5)]


def test_extract_rings_selection_boundary_drops_ring():
    mol = make_benzene_like()
    assert bc.extract_rings(mol, selected_indices=[0, 1, 2]) == []


def test_extract_rings_selection_remaps():
    mol = make_benzene_like()
    rings = bc.extract_rings(mol, selected_indices=[0, 1, 2, 3, 4, 5])
    assert rings == [(0, 1, 2, 3, 4, 5)]


def test_extract_rings_size_limits():
    mol = FakeMol(
        ["C"] * 12,
        [(i, 0, 0) for i in range(12)],
        [],
        rings=[(0, 1), (0, 1, 2, 3, 4, 5, 6, 7, 8)],  # too small / too big
    )
    assert bc.extract_rings(mol, aromatic_only=False) == []


def test_extract_rings_without_ring_info():
    assert bc.extract_rings(object()) == []


def test_ring_panel_script_compiles_and_contains_data():
    mol = make_benzene_like()
    cfg = StyleConfig(ring_style="panel", ring_thickness=0.1)
    script = bc.generate_script_from_mol(mol, cfg)
    compile(script, "<generated>", "exec")
    assert "create_ring_panel" in script
    assert '"indices": [\n   0,\n   1,\n   2,\n   3,\n   4,\n   5\n  ]' in (
        script.replace("\r\n", "\n"))
    assert "RING_STYLE = 'panel'" in script


def test_ring_style_none_exports_empty_rings():
    mol = make_benzene_like()
    script = bc.generate_script_from_mol(mol, StyleConfig(ring_style="none"))
    assert "RINGS = []" in script


def test_ring_color_match_atoms():
    atoms = [("C", (float(i), 0.0, 0.0)) for i in range(3)]
    cfg = StyleConfig(ring_style="panel", ring_color_mode="match_atoms")
    records = bc._ring_records(atoms, [(0, 1, 2)], cfg)
    from blender_export_pro.element_data import color_of
    assert records[0]["color"] == [round(c, 4) for c in color_of("C")]


def test_ring_color_custom():
    atoms = [("C", (float(i), 0.0, 0.0)) for i in range(3)]
    cfg = StyleConfig(ring_style="panel", ring_color="#FF0000")
    records = bc._ring_records(atoms, [(0, 1, 2)], cfg)
    assert records[0]["color"] == [1.0, 0.0, 0.0]


# ------------------------------------------------------- labels & colors


def test_labels_in_script_all_modes():
    for mode in ("symbol", "symbol_index", "index"):
        script = _generate(label_mode=mode)
        compile(script, "<generated>", "exec")
        assert f"LABEL_MODE = '{mode}'" in script
        assert "create_labels" in script
        assert "TRACK_TO" in script


def test_labels_disabled_by_default():
    assert "LABEL_MODE = 'none'" in _generate()


def test_resolve_atom_color_override_beats_modes():
    cfg = StyleConfig(color_mode="single", single_color="#FFFFFF",
                      atom_color_overrides={"2": "#FF0000"})
    assert bc.resolve_atom_color(cfg, "C", 2) == (1.0, 0.0, 0.0)
    assert bc.resolve_atom_color(cfg, "C", 1) == (1.0, 1.0, 1.0)


def test_atom_color_override_survives_selection_remap():
    mol = make_ethanol_like()  # atoms C C O H
    cfg = StyleConfig(atom_color_overrides={"2": "#00FF00"})
    script = bc.generate_script_from_mol(mol, cfg, selected_indices=[1, 2])
    assert '"color": [\n   0.0,\n   1.0,\n   0.0\n  ]' in (
        script.replace("\r\n", "\n"))


# ----------------------------------------------------- background & render


def test_hdri_background_in_script():
    script = _generate(background_mode="hdri", hdri_path="C:/tex/studio.hdr",
                       hdri_strength=2.5)
    assert "HDRI_PATH = 'C:/tex/studio.hdr'" in script
    assert "ShaderNodeTexEnvironment" in script
    assert "HDRI_STRENGTH = 2.5" in script


def test_transparent_background_in_script():
    script = _generate(background_mode="transparent")
    assert "film_transparent = True" in script


def test_color_background_in_script():
    script = _generate(background_mode="color", background_color="#112233")
    assert "BG_MODE = 'color'" in script
    assert "0.0667" in script  # 0x11/255


def test_render_settings_in_script():
    script = _generate(render_engine="cycles", render_samples=64,
                       resolution_x=800, resolution_y=600)
    assert "RENDER_ENGINE = 'cycles'" in script
    assert "RENDER_SAMPLES = 64" in script
    assert "RESOLUTION = (800, 600)" in script
    compile(script, "<generated>", "exec")


# -------------------------------------------------- atom radius resolution


def test_resolve_atom_radius_cpk_and_uniform():
    from blender_export_pro.element_data import radius_of

    cfg = StyleConfig(atom_radius_scale=0.5)
    assert bc.resolve_atom_radius(cfg, "C") == radius_of("C") * 0.5
    cfg = StyleConfig(atom_radius_mode="uniform", uniform_radius=0.4)
    assert bc.resolve_atom_radius(cfg, "C") == 0.4


def test_resolve_atom_radius_hydrogen_scale():
    from blender_export_pro.element_data import radius_of

    cfg = StyleConfig(atom_radius_scale=0.5, hydrogen_scale=0.5)
    assert bc.resolve_atom_radius(cfg, "H") == radius_of("H") * 0.5 * 0.5
    assert bc.resolve_atom_radius(cfg, "C") == radius_of("C") * 0.5


def test_resolve_atom_radius_override_scale_and_absolute():
    from blender_export_pro.element_data import radius_of

    cfg = StyleConfig(
        atom_radius_scale=0.5,
        atom_overrides={"3": {"scale": 2.0}, "7": {"radius": 1.23}},
    )
    base = radius_of("C") * 0.5
    assert bc.resolve_atom_radius(cfg, "C", 3) == base * 2.0
    assert bc.resolve_atom_radius(cfg, "C", 7) == 1.23
    assert bc.resolve_atom_radius(cfg, "C", 5) == base


def test_resolve_atom_radius_bad_override_ignored():
    cfg = StyleConfig(atom_overrides={"0": {"radius": "junk"}, "1": "junk"})
    base = bc.resolve_atom_radius(cfg, "C")
    assert bc.resolve_atom_radius(cfg, "C", 0) == base
    assert bc.resolve_atom_radius(cfg, "C", 1) == base


def test_resolve_atom_radius_clamped_to_minimum():
    cfg = StyleConfig(atom_overrides={"0": {"radius": 0.0}})
    assert bc.resolve_atom_radius(cfg, "C", 0) == 0.01


def test_atom_override_survives_selection_remap():
    """Per-atom overrides key on original indices even under selection."""
    mol = make_ethanol_like()  # atoms C C O H
    cfg = StyleConfig(atom_overrides={"2": {"radius": 2.5}})
    # select only atoms 1 (C) and 2 (O); O becomes export index 1
    script = bc.generate_script_from_mol(mol, cfg, selected_indices=[1, 2])
    assert '"radius": 2.5' in script


def test_atom_records_use_export_position_without_keys():
    atoms = [("C", (0.0, 0.0, 0.0))]
    cfg = StyleConfig(atom_overrides={"0": {"radius": 2.0}})
    assert bc._atom_records(atoms, cfg)[0]["radius"] == 2.0


# ------------------------------------------------------ per-ring overrides


def test_ring_key_is_sorted_and_stable():
    assert bc.ring_key((5, 0, 3, 1, 4, 2)) == "0-1-2-3-4-5"
    assert bc.ring_key([2, 1, 0]) == bc.ring_key((0, 2, 1))


def test_resolve_ring_style_defaults():
    cfg = StyleConfig(ring_scale=0.8, ring_opacity=0.4)
    style = bc.resolve_ring_style(cfg, "0-1-2")
    assert style == {
        "visible": True, "scale": 0.8, "thickness": cfg.ring_thickness,
        "opacity": 0.4, "color": None,
        "hide_atoms": False, "hide_bonds": False,
    }


def test_ring_hidden_geometry_global_and_per_ring():
    rings = [(0, 1, 2, 3, 4, 5)]
    keys = ["0-1-2-3-4-5"]
    # global hide
    cfg = StyleConfig(ring_style="panel", ring_hide_atoms=True,
                      ring_hide_bonds=True)
    atoms, bond_rings = bc.ring_hidden_geometry(cfg, rings, keys)
    assert atoms == {0, 1, 2, 3, 4, 5}
    assert bond_rings == [{0, 1, 2, 3, 4, 5}]
    # per-ring hide overrides global off
    cfg = StyleConfig(ring_style="panel",
                      ring_overrides={"0-1-2-3-4-5": {"hide_atoms": True}})
    atoms, _ = bc.ring_hidden_geometry(cfg, rings, keys)
    assert atoms == {0, 1, 2, 3, 4, 5}
    # ring_style none => nothing hidden
    cfg = StyleConfig(ring_style="none", ring_hide_atoms=True)
    atoms, _ = bc.ring_hidden_geometry(cfg, rings, keys)
    assert atoms == set()
    # hidden panel => nothing hidden
    cfg = StyleConfig(ring_style="panel", ring_hide_atoms=True,
                      ring_overrides={"0-1-2-3-4-5": {"visible": False}})
    atoms, _ = bc.ring_hidden_geometry(cfg, rings, keys)
    assert atoms == set()


def test_hidden_atoms_and_bonds_marked_invisible():
    from conftest import make_benzene_like
    cfg = StyleConfig(ring_style="panel", ring_hide_atoms=True,
                      ring_hide_bonds=True)
    script = bc.generate_script_from_mol(make_benzene_like(), cfg)
    compile(script, "<generated>", "exec")
    assert '"visible": false' in script


def test_resolve_ring_style_override():
    cfg = StyleConfig(ring_overrides={
        "0-1-2": {"visible": False, "color": "#112233", "opacity": 0.9}
    })
    style = bc.resolve_ring_style(cfg, "0-1-2")
    assert style["visible"] is False
    assert style["color"] == "#112233"
    assert style["opacity"] == 0.9
    assert style["scale"] == cfg.ring_scale  # not overridden -> global


def test_ring_records_apply_overrides():
    atoms = [("C", (float(i), 0.0, 0.0)) for i in range(3)]
    cfg = StyleConfig(
        ring_style="panel",
        ring_overrides={"0-1-2": {"visible": False, "color": "#FF0000",
                                  "thickness": 0.5}},
    )
    rec = bc._ring_records(atoms, [(0, 1, 2)], cfg)[0]
    assert rec["visible"] is False
    assert rec["color"] == [1.0, 0.0, 0.0]
    assert rec["thickness"] == 0.5
    assert rec["opacity"] == cfg.ring_opacity


def test_ring_override_key_survives_selection_remap():
    """Overrides are keyed on original indices even when a selection
    remaps the exported atom order."""
    mol = make_benzene_like()  # ring atoms 0-5, substituent 6
    cfg = StyleConfig(
        ring_style="panel",
        ring_overrides={"0-1-2-3-4-5": {"color": "#00FF00"}},
    )
    script = bc.generate_script_from_mol(
        mol, cfg, selected_indices=[5, 4, 3, 2, 1, 0])
    assert '"color": [\n   0.0,\n   1.0,\n   0.0\n  ]' in (
        script.replace("\r\n", "\n"))


def test_hidden_ring_script_still_compiles():
    mol = make_benzene_like()
    cfg = StyleConfig(
        ring_style="panel",
        ring_overrides={"0-1-2-3-4-5": {"visible": False}},
    )
    script = bc.generate_script_from_mol(mol, cfg)
    compile(script, "<generated>", "exec")
    assert '"visible": false' in script


def test_generate_script_from_mol_empty_selection_raises():
    mol = FakeMol([], [], [])
    with pytest.raises(ValueError):
        bc.generate_script_from_mol(mol, StyleConfig())
