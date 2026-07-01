"""Live in-app preview of the Blender export style, drawn with PyVista.

Registered via context.register_3d_style(). This is an approximation of the
final Blender render: sphere/cylinder geometry with the configured radii,
colors, jitter and noise displacement, so users can iterate before exporting.
"""

import logging

from .blender_codegen import extract_geometry, hex_to_rgb
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


def _material_kwargs(cfg: StyleConfig) -> dict:
    preset = cfg.material_preset
    if preset == "metal":
        return {"metallic": 1.0, "roughness": 0.3, "pbr": True}
    if preset == "glass":
        return {"opacity": 0.35, "specular": 1.0, "smooth_shading": True}
    if preset == "matte":
        return {"specular": 0.05, "diffuse": 1.0}
    if preset == "toon":
        return {"specular": 0.0, "diffuse": 1.0, "ambient": 0.35}
    if preset == "clay":
        return {"specular": 0.1, "diffuse": 0.9, "ambient": 0.15}
    return {"specular": 0.5, "smooth_shading": True}


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

    try:
        plotter.render()
    except Exception:
        logging.debug("BlenderExportPro: plotter.render failed", exc_info=True)
