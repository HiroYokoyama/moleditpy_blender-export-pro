"""Live in-app preview of the Blender export style, drawn with PyVista.

Registered via context.register_3d_style(). This is an approximation of the
final Blender render: sphere/cylinder geometry with the configured radii,
colors, jitter and noise displacement, so users can iterate before exporting.
"""

import logging

from .blender_codegen import extract_geometry, extract_rings, hex_to_rgb
from .element_data import radius_of, color_of
from .style_config import StyleConfig

try:
    import numpy as np
    import pyvista as pv
except ImportError:  # headless / test environment
    np = None
    pv = None


def _atom_radius(symbol: str, cfg: StyleConfig) -> float:
    if cfg.atom_radius_mode == "uniform":
        return max(cfg.uniform_radius, 0.01)
    return max(radius_of(symbol) * cfg.atom_radius_scale, 0.01)


def _atom_color(symbol: str, cfg: StyleConfig) -> tuple:
    if cfg.color_mode == "single":
        return hex_to_rgb(cfg.single_color)
    return color_of(symbol)


_PREVIEW_MATERIALS = {
    "metal":      {"metallic": 1.0, "roughness": 0.3, "pbr": True},
    "chrome":     {"metallic": 1.0, "roughness": 0.05, "pbr": True},
    "gold":       {"metallic": 1.0, "roughness": 0.25, "pbr": True},
    "copper":     {"metallic": 1.0, "roughness": 0.35, "pbr": True},
    "iridescent": {"metallic": 0.8, "roughness": 0.15, "pbr": True},
    "glass":      {"opacity": 0.35, "specular": 1.0, "smooth_shading": True},
    "ice":        {"opacity": 0.45, "specular": 1.0, "smooth_shading": True},
    "gummy":      {"opacity": 0.75, "specular": 0.6, "smooth_shading": True},
    "matte":      {"specular": 0.05, "diffuse": 1.0},
    "chalk":      {"specular": 0.0, "diffuse": 1.0, "ambient": 0.25},
    "stone":      {"specular": 0.02, "diffuse": 0.95, "ambient": 0.1},
    "velvet":     {"specular": 0.0, "diffuse": 1.0, "ambient": 0.2},
    "toon":       {"specular": 0.0, "diffuse": 1.0, "ambient": 0.35},
    "neon":       {"specular": 0.0, "diffuse": 0.4, "ambient": 0.9},
    "clay":       {"specular": 0.1, "diffuse": 0.9, "ambient": 0.15},
    "wax":        {"specular": 0.3, "diffuse": 0.9, "smooth_shading": True},
    "ceramic":    {"specular": 0.9, "diffuse": 0.9, "smooth_shading": True},
}


def _material_kwargs(cfg: StyleConfig) -> dict:
    default = {"specular": 0.5, "smooth_shading": True}
    return dict(_PREVIEW_MATERIALS.get(cfg.material_preset, default))


def _displace(mesh, cfg: StyleConfig, rng) -> None:
    """Cheap noise displacement along normals to mimic the Displace modifier."""
    if cfg.deformation_noise <= 0.0:
        return
    try:
        mesh.compute_normals(inplace=True, auto_orient_normals=True)
        normals = mesh.point_data.get("Normals")
        if normals is None:
            return
        amounts = rng.uniform(
            -cfg.deformation_noise, cfg.deformation_noise, mesh.n_points
        )
        mesh.points = mesh.points + normals * amounts[:, None] * 0.5
    except Exception:
        logging.debug("BlenderExportPro: preview displace failed", exc_info=True)


def draw_preview_style(mw, mol, cfg: StyleConfig) -> None:
    """3D style callback: draw the styled molecule into the host plotter."""
    if pv is None or np is None:
        logging.warning("BlenderExportPro: pyvista/numpy unavailable, cannot preview.")
        return
    v3d = getattr(mw, "view_3d_manager", None)
    plotter = getattr(v3d, "plotter", None)
    if mol is None or plotter is None:
        return

    try:
        atoms, bonds = extract_geometry(mol)
    except Exception:
        logging.exception("BlenderExportPro: could not extract geometry for preview")
        return
    if not atoms:
        return

    rng = np.random.default_rng(42)
    mat = _material_kwargs(cfg)
    resolution = 12 if cfg.atom_shape == "ico_sphere" else 24

    try:
        plotter.clear()
    except Exception:
        logging.debug("BlenderExportPro: plotter.clear failed", exc_info=True)

    positions = np.array([pos for _s, pos in atoms])
    for idx, (symbol, pos) in enumerate(atoms):
        radius = _atom_radius(symbol, cfg)
        sphere = pv.Sphere(
            radius=radius,
            center=pos,
            theta_resolution=resolution,
            phi_resolution=resolution,
        )
        if cfg.atom_jitter > 0.0:
            scale = 1.0 + rng.uniform(
                -cfg.atom_jitter, cfg.atom_jitter, 3) * 0.5
            pts = np.asarray(sphere.points)
            sphere.points = (pts - np.array(pos)) * scale + np.array(pos)
        _displace(sphere, cfg, rng)
        plotter.add_mesh(
            sphere,
            color=_atom_color(symbol, cfg),
            name=f"bep_atom_{idx}",
            smooth_shading=cfg.shade_smooth,
            **mat,
        )

    bond_radius = max(cfg.bond_radius, 0.01)
    for idx, (i, j, order) in enumerate(bonds):
        start, end = positions[i], positions[j]
        direction = end - start
        length = float(np.linalg.norm(direction))
        if length < 1e-6:
            continue
        direction = direction / length
        color = tuple(
            (a + b) / 2.0
            for a, b in zip(_atom_color(atoms[i][0], cfg), _atom_color(atoms[j][0], cfg))
        )

        if order > 1 and cfg.show_multiple_bonds:
            ref = np.array([0.0, 0.0, 1.0])
            if abs(float(np.dot(direction, ref))) > 0.99:
                ref = np.array([0.0, 1.0, 0.0])
            perp = np.cross(direction, ref)
            perp /= np.linalg.norm(perp)
            if order == 2:
                offsets = [-cfg.multi_bond_offset / 2.0, cfg.multi_bond_offset / 2.0]
            else:
                offsets = [-cfg.multi_bond_offset, 0.0, cfg.multi_bond_offset]
            radius = bond_radius * 0.7
        else:
            perp = np.zeros(3)
            offsets = [0.0]
            radius = bond_radius

        for k, off in enumerate(offsets):
            shift = perp * off
            cyl = pv.Cylinder(
                center=(start + end) / 2.0 + shift,
                direction=direction,
                radius=radius,
                height=length,
                resolution=max(6, cfg.bond_segments),
            )
            _displace(cyl, cfg, rng)
            plotter.add_mesh(
                cyl,
                color=color,
                name=f"bep_bond_{idx}_{k}",
                smooth_shading=cfg.shade_smooth,
                **mat,
            )

    if cfg.ring_style == "panel":
        _draw_ring_panels(plotter, mol, atoms, positions, cfg)

    try:
        plotter.render()
    except Exception:
        logging.debug("BlenderExportPro: plotter.render failed", exc_info=True)


def _draw_ring_panels(plotter, mol, atoms, positions, cfg: StyleConfig) -> None:
    """Draw rings (e.g. benzene) as translucent filled polygon panels."""
    try:
        rings = extract_rings(mol, None, cfg.ring_aromatic_only)
    except Exception:
        logging.exception("BlenderExportPro: ring extraction failed")
        return

    for idx, ring in enumerate(rings):
        pts = positions[list(ring)].astype(float)
        center = pts.mean(axis=0)
        pts = center + (pts - center) * cfg.ring_scale
        n_pts = len(pts)
        face = np.hstack([[n_pts], np.arange(n_pts)])

        if cfg.ring_color_mode == "match_atoms":
            member_colors = [_atom_color(atoms[i][0], cfg) for i in ring]
            color = tuple(sum(c[k] for c in member_colors) / n_pts
                          for k in range(3))
        else:
            color = hex_to_rgb(cfg.ring_color)

        try:
            panel = pv.PolyData(pts, faces=face)
            if cfg.ring_thickness > 0.0:
                normal = np.cross(pts[1] - pts[0], pts[2] - pts[0])
                norm_len = np.linalg.norm(normal)
                if norm_len > 1e-9:
                    normal = normal / norm_len * cfg.ring_thickness
                    panel.points = panel.points - normal / 2.0
                    panel = panel.extrude(normal, capping=True)
            plotter.add_mesh(
                panel,
                color=color,
                opacity=cfg.ring_opacity,
                name=f"bep_ring_{idx}",
            )
        except Exception:
            logging.exception("BlenderExportPro: ring panel preview failed")
