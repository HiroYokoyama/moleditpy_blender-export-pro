"""Tests for StyleConfig serialization, coercion, presets and settings I/O."""

import json

from blender_export_pro import style_config as sc
from blender_export_pro.style_config import StyleConfig


def test_round_trip():
    cfg = StyleConfig(atom_shape="ico_sphere", bond_radius=0.2, turntable_frames=90)
    data = cfg.to_dict()
    restored = StyleConfig()
    restored.update_from_dict(data)
    assert restored == cfg


def test_update_ignores_unknown_keys():
    cfg = StyleConfig()
    cfg.update_from_dict({"no_such_field": 1, "atom_jitter": 0.4})
    assert cfg.atom_jitter == 0.4
    assert not hasattr(cfg, "no_such_field")


def test_update_coerces_types():
    cfg = StyleConfig()
    cfg.update_from_dict(
        {"atom_subdivisions": "5", "bond_radius": "0.3", "shade_smooth": 0}
    )
    assert cfg.atom_subdivisions == 5
    assert cfg.bond_radius == 0.3
    assert cfg.shade_smooth is False


def test_update_ignores_bad_values():
    cfg = StyleConfig()
    cfg.update_from_dict({"bond_radius": "not-a-number"})
    assert cfg.bond_radius == StyleConfig().bond_radius


def test_update_non_dict_is_noop():
    cfg = StyleConfig()
    cfg.update_from_dict(None)
    cfg.update_from_dict("junk")
    assert cfg == StyleConfig()


def test_ring_overrides_round_trip():
    cfg = StyleConfig(ring_overrides={"0-1-2": {"visible": False, "opacity": 0.7}})
    restored = StyleConfig()
    restored.update_from_dict(cfg.to_dict())
    assert restored.ring_overrides == {"0-1-2": {"visible": False, "opacity": 0.7}}


def test_ring_overrides_bad_value_becomes_empty():
    cfg = StyleConfig()
    cfg.update_from_dict({"ring_overrides": "junk"})
    assert cfg.ring_overrides == {}


def test_reset_defaults():
    cfg = StyleConfig(deformation_noise=0.9, material_preset="glass")
    cfg.reset_defaults()
    assert cfg == StyleConfig()


def test_bundled_presets_listed_and_loadable():
    presets = sc.list_presets()
    assert len(presets) >= 20
    assert "Classic Ball And Stick" in presets
    for name, path in presets.items():
        cfg = StyleConfig()
        assert sc.load_preset(cfg, path), name
        assert cfg.material_preset in sc.MATERIAL_PRESETS
        assert cfg.atom_shape in sc.ATOM_SHAPES
        assert cfg.bond_style in sc.BOND_STYLES
        assert cfg.scene_preset in sc.SCENE_PRESETS


def test_every_bundled_preset_generates_valid_script():
    from blender_export_pro import blender_codegen as bc

    atoms = [("C", (0.0, 0.0, 0.0)), ("N", (1.4, 0.0, 0.0))]
    bonds = [(0, 1, 3)]
    for name, path in sc.list_presets().items():
        cfg = StyleConfig()
        assert sc.load_preset(cfg, path), name
        script = bc.generate_script(atoms, bonds, cfg)
        compile(script, f"<preset:{name}>", "exec")


def test_every_material_preset_has_codegen_params():
    from blender_export_pro.blender_codegen import MATERIAL_PRESET_PARAMS

    assert set(sc.MATERIAL_PRESETS) == set(MATERIAL_PRESET_PARAMS)


def test_preset_save_and_load(tmp_path):
    cfg = StyleConfig(material_preset="metal", atom_jitter=0.25)
    path = str(tmp_path / "custom.json")
    assert sc.save_preset(cfg, path)

    other = StyleConfig()
    assert sc.load_preset(other, path)
    assert other.material_preset == "metal"
    assert other.atom_jitter == 0.25


def test_load_preset_bad_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    cfg = StyleConfig()
    assert sc.load_preset(cfg, str(bad)) is False
    assert cfg == StyleConfig()


def test_settings_round_trip(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    monkeypatch.setattr(sc, "settings_path", lambda: str(settings))

    cfg = StyleConfig(scene_preset="dark", bond_segments=12)
    sc.save_config(cfg)
    assert settings.exists()
    assert json.loads(settings.read_text(encoding="utf-8"))["scene_preset"] == "dark"

    loaded = sc.load_config()
    assert loaded.scene_preset == "dark"
    assert loaded.bond_segments == 12


def test_load_config_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "settings_path", lambda: str(tmp_path / "nope.json"))
    assert sc.load_config() == StyleConfig()
