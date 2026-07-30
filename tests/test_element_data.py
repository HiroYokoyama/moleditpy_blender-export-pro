"""Tests for element_data: live main-app/RDKit lookups and fallbacks."""

import sys
import types

import pytest

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
        assert element_data.color_of("O") == (1.0000, 0.2000, 0.2000)
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


# ---------------------------------------------------------------------------
# Drift guards: the bundled tables are generated from RDKit and the main app,
# so a headless render must match an in-app one. These fail if either source
# moves and the bundled copy is not regenerated.
# ---------------------------------------------------------------------------


def test_fallback_radii_match_rdkit():
    Chem = pytest.importorskip("rdkit.Chem")
    pt = Chem.GetPeriodicTable()
    drift = []
    for symbol, bundled in element_data.VDW_RADII.items():
        live = float(pt.GetRvdw(pt.GetAtomicNumber(symbol)))
        if abs(live - bundled) > 0.005:
            drift.append(f"{symbol}: bundled {bundled} vs RDKit {live}")
    assert not drift, "bundled radii drifted from RDKit: " + "; ".join(drift)


def test_fallback_radii_cover_every_element_rdkit_knows():
    Chem = pytest.importorskip("rdkit.Chem")
    pt = Chem.GetPeriodicTable()
    missing = [
        pt.GetElementSymbol(z)
        for z in range(1, 104)
        if pt.GetElementSymbol(z) not in element_data.VDW_RADII
    ]
    assert not missing, f"no bundled radius for: {missing}"


def test_fallback_colors_match_the_main_app():
    constants = pytest.importorskip("moleditpy.utils.constants")
    drift = []
    for symbol, bundled in element_data.CPK_COLORS.items():
        qcolor = constants.CPK_COLORS.get(symbol)
        if qcolor is None:
            drift.append(f"{symbol}: not in the app table")
            continue
        live = (qcolor.redF(), qcolor.greenF(), qcolor.blueF())
        if max(abs(a - b) for a, b in zip(live, bundled)) > 0.001:
            drift.append(f"{symbol}: bundled {bundled} vs app {live}")
    assert not drift, "bundled colors drifted from the app: " + "; ".join(drift)


def test_fallback_colors_cover_the_whole_app_table():
    constants = pytest.importorskip("moleditpy.utils.constants")
    missing = [
        s
        for s in constants.CPK_COLORS
        if s != "DEFAULT" and s not in element_data.CPK_COLORS
    ]
    assert not missing, f"no bundled color for: {missing}"


def test_every_element_with_a_radius_also_has_a_color():
    """Runs with no optional dependencies, so CI always exercises it.

    A symbol present in one table but not the other renders at a default,
    which is how the previous tables lost 40 radii and 74 colors.
    """
    missing_color = sorted(set(element_data.VDW_RADII) - set(element_data.CPK_COLORS))
    missing_radius = sorted(set(element_data.CPK_COLORS) - set(element_data.VDW_RADII))
    assert not missing_color, f"radius but no color: {missing_color}"
    assert not missing_radius, f"color but no radius: {missing_radius}"


def test_bundled_tables_span_the_periodic_table():
    """Guards against a truncated regeneration."""
    assert len(element_data.VDW_RADII) >= 103
    assert len(element_data.CPK_COLORS) >= 103
    for symbol in ("H", "C", "W", "Th", "U", "Lr"):
        assert symbol in element_data.VDW_RADII
        assert symbol in element_data.CPK_COLORS
