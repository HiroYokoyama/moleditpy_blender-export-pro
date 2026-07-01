"""Tests for element_data: live main-app/RDKit lookups and fallbacks."""

import sys
import types

from conftest import mock_optional_imports

from blender_export_pro import element_data


def test_radius_fallback_without_rdkit():
    """With rdkit unavailable (mocked away), the bundled vdW table is used."""
    with mock_optional_imports():
        assert element_data.radius_of("C") == 1.70
        assert element_data.radius_of("H") == 1.20
        assert element_data.radius_of("Xx") == element_data.DEFAULT_RADIUS


def test_color_fallback_without_main_app():
    with mock_optional_imports():
        assert element_data.color_of("O") == (1.00, 0.05, 0.05)
        assert element_data.color_of("Xx") == element_data.DEFAULT_COLOR


def test_radius_uses_rdkit_table(monkeypatch):
    fake_pt = types.SimpleNamespace(
        GetAtomicNumber=lambda s: 6, GetRvdw=lambda n: 9.9)
    fake_rdkit = types.ModuleType("rdkit")
    fake_rdkit.Chem = types.SimpleNamespace(GetPeriodicTable=lambda: fake_pt)
    monkeypatch.setitem(sys.modules, "rdkit", fake_rdkit)
    assert element_data.radius_of("C") == 9.9


class _FakeQColor:
    def __init__(self, r, g, b):
        self._rgb = (r, g, b)

    def redF(self):
        return self._rgb[0]

    def greenF(self):
        return self._rgb[1]

    def blueF(self):
        return self._rgb[2]


def _install_fake_app_colors(monkeypatch, colors):
    constants = types.ModuleType("moleditpy.utils.constants")
    constants.CPK_COLORS = colors
    utils = types.ModuleType("moleditpy.utils")
    utils.constants = constants
    app = types.ModuleType("moleditpy")
    app.utils = utils
    monkeypatch.setitem(sys.modules, "moleditpy", app)
    monkeypatch.setitem(sys.modules, "moleditpy.utils", utils)
    monkeypatch.setitem(sys.modules, "moleditpy.utils.constants", constants)


def test_color_uses_main_app_table(monkeypatch):
    _install_fake_app_colors(
        monkeypatch, {"C": _FakeQColor(0.1, 0.2, 0.3)})
    assert element_data.color_of("C") == (0.1, 0.2, 0.3)


def test_color_uses_main_app_default_entry(monkeypatch):
    _install_fake_app_colors(
        monkeypatch, {"DEFAULT": _FakeQColor(0.5, 0.6, 0.7)})
    assert element_data.color_of("Zz") == (0.5, 0.6, 0.7)
