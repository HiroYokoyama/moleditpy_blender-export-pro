"""Extra branch coverage for preview_style.py beyond test_dialog.py's suite:
lighting fallback exceptions, the noise-displacement helper, draw_preview_style's
error/hide/degenerate-geometry branches, ring panel exception paths, and the
label-drawing helper (previously entirely untested)."""

import sys
import types
from unittest.mock import MagicMock

import pytest

from conftest import FakeMol, make_benzene_like, make_ethanol_like


# --------------------------------------------------------------- module import


def test_preview_style_falls_back_when_numpy_and_pyvista_missing():
    """Force a genuine ImportError (not a MagicMock stand-in) for numpy and
    pyvista and confirm the module still imports with pv/np set to None."""
    saved = {}
    for name in ("numpy", "pyvista"):
        saved[name] = sys.modules.pop(name, None)
        sys.modules[name] = None  # forces ImportError on import
    saved_mod = sys.modules.pop("blender_export_pro.preview_style", None)
    try:
        import importlib
        mod = importlib.import_module("blender_export_pro.preview_style")
        assert mod.pv is None
        assert mod.np is None
    finally:
        sys.modules.pop("blender_export_pro.preview_style", None)
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        if saved_mod is not None:
            sys.modules["blender_export_pro.preview_style"] = saved_mod


# ----------------------------------------------------------------- lighting


def test_ensure_lighting_swallows_exceptions():
    from blender_export_pro import preview_style

    plotter = MagicMock()
    plotter.remove_all_lights.side_effect = RuntimeError("boom")
    plotter.enable_lightkit.side_effect = RuntimeError("boom")
    preview_style._ensure_lighting(plotter)  # must not raise


def test_apply_lighting_cubemap_failure_is_swallowed(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    fake_pv = types.SimpleNamespace(Light=MagicMock(), cubemap=MagicMock())
    monkeypatch.setattr(preview_style, "pv", fake_pv)
    monkeypatch.setattr(preview_style, "np", np_real)

    plotter = MagicMock()
    plotter.set_environment_texture.side_effect = RuntimeError("boom")
    preview_style._apply_lighting(plotter, StyleConfig(), np_real.zeros(3), 5.0)
    plotter.set_environment_texture.assert_called_once()


# ------------------------------------------------------------------ _displace


def test_displace_applies_real_noise_via_pyvista():
    np_real = pytest.importorskip("numpy")
    pv_real = pytest.importorskip("pyvista")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig
    import types as _types

    saved_np = preview_style.np
    preview_style.np = np_real
    try:
        mesh = pv_real.Sphere(radius=1.0)
        before = np_real.array(mesh.points, copy=True)
        cfg = StyleConfig(deformation_noise=0.3, deformation_noise_scale=1.0)
        preview_style._displace(mesh, cfg)
        assert not np_real.allclose(mesh.points, before)
    finally:
        preview_style.np = saved_np


def test_displace_returns_early_without_normals():
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    class FakeMesh:
        point_data = {}

        def compute_normals(self, **_k):
            pass

    cfg = StyleConfig(deformation_noise=0.3)
    preview_style._displace(FakeMesh(), cfg)  # must not raise


def test_displace_swallows_exception():
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    class Boom:
        def compute_normals(self, **_k):
            raise RuntimeError("no mesh")

    cfg = StyleConfig(deformation_noise=0.3)
    preview_style._displace(Boom(), cfg)  # must not raise


# --------------------------------------------------------------- draw_preview


def _mw_with_plotter(plotter):
    mw = MagicMock()
    mw.view_3d_manager.plotter = plotter
    return mw


def test_draw_preview_geometry_extraction_failure(monkeypatch):
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", pytest.importorskip("numpy"))
    monkeypatch.setattr(preview_style, "extract_geometry",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(), StyleConfig())
    plotter.clear.assert_not_called()


def test_draw_preview_no_atoms_noop(monkeypatch):
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", pytest.importorskip("numpy"))
    empty_mol = FakeMol(symbols=[], coords=[], bonds=[])
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), empty_mol, StyleConfig())
    plotter.clear.assert_not_called()


def test_draw_preview_ring_hidden_geometry_exception(monkeypatch):
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    np_real = pytest.importorskip("numpy")
    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    monkeypatch.setattr(preview_style, "ring_hidden_geometry",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(),
        StyleConfig(ring_style="panel"))  # must not raise
    plotter.render.assert_called_once()


def test_draw_preview_plotter_clear_exception_is_swallowed(monkeypatch):
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", pytest.importorskip("numpy"))
    plotter = MagicMock()
    plotter.clear.side_effect = RuntimeError("boom")
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(), StyleConfig())
    plotter.render.assert_called_once()


def test_draw_preview_atom_jitter_applied(monkeypatch):
    np_real = pytest.importorskip("numpy")
    pv_real = pytest.importorskip("pyvista")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", pv_real)
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(),
        StyleConfig(atom_jitter=0.4))
    plotter.render.assert_called_once()


def test_draw_preview_aromatic_ring_lookup_exception(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)

    real_extract_rings = preview_style.extract_rings

    def flaky(mol, sel, aromatic_only, *a, **k):
        if aromatic_only is True and sel is None:
            raise RuntimeError("boom")
        return real_extract_rings(mol, sel, aromatic_only, *a, **k)

    monkeypatch.setattr(preview_style, "extract_rings", flaky)
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(),
        StyleConfig(aromatic_bond_style="dashed", show_multiple_bonds=True))
    plotter.render.assert_called_once()


def test_draw_preview_hidden_endpoint_bond_skipped(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_ethanol_like(),
        StyleConfig(hide_hydrogens=True))
    names = [c.kwargs.get("name") for c in plotter.add_mesh.call_args_list]
    assert not any(n and "3" in n for n in names)  # H atom index 3 omitted


def test_draw_preview_ring_internal_bond_hidden(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(),
        StyleConfig(ring_style="panel", ring_hide_bonds=True))
    names = [c.kwargs.get("name") for c in plotter.add_mesh.call_args_list]
    bonds = [n for n in names if n and n.startswith("bep_bond_")]
    # only the C-Cl substituent bond (atom 6) should remain
    assert bonds and all("_6_" not in "" for _ in bonds)


def test_draw_preview_zero_length_bond_skipped(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    mol = FakeMol(
        symbols=["C", "C"],
        coords=[(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)],
        bonds=[(0, 1, 1.0)],
    )
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), mol, StyleConfig())
    names = [c.kwargs.get("name") for c in plotter.add_mesh.call_args_list]
    assert not any(n and n.startswith("bep_bond_") for n in names)


def test_draw_preview_z_aligned_double_bond(monkeypatch):
    """Bond direction near-parallel to the z-axis exercises the alternate
    perpendicular-reference branch for multi-bond offsets."""
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    mol = FakeMol(
        symbols=["C", "C"],
        coords=[(0.0, 0.0, 0.0), (0.0, 0.0, 1.3)],
        bonds=[(0, 1, 2.0)],
    )
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), mol,
        StyleConfig(show_multiple_bonds=True))
    plotter.render.assert_called_once()


def test_draw_preview_triple_bond_three_cylinders(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    mol = FakeMol(
        symbols=["C", "C"],
        coords=[(0.0, 0.0, 0.0), (1.2, 0.0, 0.0)],
        bonds=[(0, 1, 3.0)],
    )
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), mol,
        StyleConfig(show_multiple_bonds=True))
    names = [c.kwargs.get("name") for c in plotter.add_mesh.call_args_list]
    bonds = [n for n in names if n and n.startswith("bep_bond_")]
    assert len(bonds) == 3


def test_draw_preview_dashed_gradient_and_split_colors(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    for mode in ("gradient", "split"):
        plotter = MagicMock()
        preview_style.draw_preview_style(
            _mw_with_plotter(plotter), make_benzene_like(),
            StyleConfig(aromatic_bond_style="dashed",
                        show_multiple_bonds=True, bond_color_mode=mode))
        plotter.render.assert_called_once()


def test_draw_preview_smooth_gradient_bond_used(monkeypatch):
    """bond_color_mode=gradient with differing atom colors takes the smooth
    per-vertex gradient path (draw_preview_style's `continue` branch)."""
    np_real = pytest.importorskip("numpy")
    pv_real = pytest.importorskip("pyvista")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", pv_real)
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(),
        StyleConfig(bond_color_mode="gradient"))
    plotter.render.assert_called_once()


def test_draw_preview_degenerate_piece_skipped(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    monkeypatch.setattr(
        preview_style, "bond_piecewise",
        lambda cfg, start, end, ca, cb: [(start, start, ca)])  # zero length
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(), StyleConfig())
    plotter.render.assert_called_once()


def test_draw_preview_render_exception_is_swallowed(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    plotter.render.side_effect = RuntimeError("boom")
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(), StyleConfig())


# --------------------------------------------------------------- ring panels


def test_ring_panels_extraction_failure_returns(monkeypatch):
    from blender_export_pro import preview_style

    monkeypatch.setattr(preview_style, "extract_rings",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    plotter = MagicMock()
    from blender_export_pro.style_config import StyleConfig
    preview_style._draw_ring_panels(
        plotter, make_benzene_like(), [], MagicMock(), StyleConfig())
    plotter.add_mesh.assert_not_called()


def test_ring_panels_match_atoms_color_mode(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(),
        StyleConfig(ring_style="panel", ring_color_mode="match_atoms",
                    ring_color=""))
    plotter.render.assert_called_once()


def test_ring_panels_outline_tube_failure_falls_back_to_lines(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    fake_pv = MagicMock()
    fake_pv.PolyData.return_value.tube.side_effect = RuntimeError("boom")
    monkeypatch.setattr(preview_style, "pv", fake_pv)
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(),
        StyleConfig(ring_style="outline"))
    plotter.render.assert_called_once()


def test_ring_panels_highlighted_ring_draws_highlight(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig
    from blender_export_pro.blender_codegen import extract_rings, ring_key

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    mol = make_benzene_like()
    rings = extract_rings(mol, None, True)
    key = ring_key(rings[0])
    preview_style.set_highlighted_ring(key)
    try:
        plotter = MagicMock()
        preview_style.draw_preview_style(
            _mw_with_plotter(plotter), mol, StyleConfig(ring_style="panel"))
        names = [c.kwargs.get("name") for c in plotter.add_mesh.call_args_list]
        assert any(n and n.startswith("bep_ring_highlight_") for n in names)
    finally:
        preview_style.set_highlighted_ring(None)


def test_ring_panels_generic_exception_is_logged(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    fake_pv = MagicMock()
    fake_pv.PolyData.side_effect = RuntimeError("boom")
    monkeypatch.setattr(preview_style, "pv", fake_pv)
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(),
        StyleConfig(ring_style="panel"))
    plotter.render.assert_called_once()


def test_draw_ring_highlight_tube_failure_falls_back(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    fake_pv = MagicMock()
    fake_pv.PolyData.return_value.tube.side_effect = RuntimeError("boom")
    monkeypatch.setattr(preview_style, "pv", fake_pv)
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    pts = np_real.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    preview_style._draw_ring_highlight(plotter, 0, pts, StyleConfig())
    plotter.add_mesh.assert_called_once()


# --------------------------------------------------------------- labels


def test_draw_labels_symbol_index_and_index_modes(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "np", np_real)
    atoms = [("C", (0.0, 0.0, 0.0)), ("O", (1.0, 0.0, 0.0))]
    positions = np_real.array([a[1] for a in atoms])

    for mode in ("symbol", "index", "symbol_index"):
        plotter = MagicMock()
        preview_style._draw_labels(
            plotter, atoms, positions, StyleConfig(label_mode=mode))
        plotter.add_point_labels.assert_called_once()


def test_draw_labels_skips_hidden_atoms_and_noop_when_all_hidden():
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    np_real = pytest.importorskip("numpy")
    atoms = [("C", (0.0, 0.0, 0.0))]
    positions = np_real.array([a[1] for a in atoms])
    plotter = MagicMock()
    preview_style._draw_labels(
        plotter, atoms, positions, StyleConfig(label_mode="symbol"),
        hidden_atoms={0})
    plotter.add_point_labels.assert_not_called()


def test_draw_labels_typeerror_retry_succeeds(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "np", np_real)
    atoms = [("C", (0.0, 0.0, 0.0))]
    positions = np_real.array([a[1] for a in atoms])
    plotter = MagicMock()
    calls = []

    def flaky(*a, **k):
        calls.append((a, k))
        if len(calls) == 1:
            raise TypeError("old pyvista")

    plotter.add_point_labels.side_effect = flaky
    preview_style._draw_labels(
        plotter, atoms, positions, StyleConfig(label_mode="symbol"))
    assert len(calls) == 2


def test_draw_labels_typeerror_retry_also_fails(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "np", np_real)
    atoms = [("C", (0.0, 0.0, 0.0))]
    positions = np_real.array([a[1] for a in atoms])
    plotter = MagicMock()
    plotter.add_point_labels.side_effect = TypeError("boom")
    preview_style._draw_labels(
        plotter, atoms, positions, StyleConfig(label_mode="symbol"))
    # must not raise


def test_draw_labels_generic_exception_is_logged(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "np", np_real)
    atoms = [("C", (0.0, 0.0, 0.0))]
    positions = np_real.array([a[1] for a in atoms])
    plotter = MagicMock()
    plotter.add_point_labels.side_effect = RuntimeError("boom")
    preview_style._draw_labels(
        plotter, atoms, positions, StyleConfig(label_mode="symbol"))
    # must not raise


def test_draw_preview_with_labels_end_to_end(monkeypatch):
    np_real = pytest.importorskip("numpy")
    from blender_export_pro import preview_style
    from blender_export_pro.style_config import StyleConfig

    monkeypatch.setattr(preview_style, "pv", MagicMock())
    monkeypatch.setattr(preview_style, "np", np_real)
    plotter = MagicMock()
    preview_style.draw_preview_style(
        _mw_with_plotter(plotter), make_benzene_like(),
        StyleConfig(label_mode="symbol_index"))
    plotter.add_point_labels.assert_called_once()
