"""Live in-app preview of the Blender export style, drawn with PyVista.

Registered via context.register_3d_style(). This is an approximation of the
final Blender render: sphere/cylinder geometry with the configured radii,
colors, jitter and noise displacement, so users can iterate before exporting.
"""

import logging

from .blender_codegen import (
    _custom_light_list,
    bond_key,
    bond_piecewise,
    dash_bounds,
    extract_geometry,
    extract_rings,
    hex_to_rgb,
    hidden_atom_indices,
    hidden_bond_keys,
    noise_displacement,
    resolve_atom_color,
    resolve_atom_radius,
    resolve_ring_style,
    ring_hidden_geometry,
    resolve_aromatic_display,
    ring_key,
    ring_outlines_enabled,
    ring_panels_enabled,
)
from .style_config import StyleConfig

try:
    import numpy as np
    import pyvista as pv
except ImportError:  # headless / test environment
    np = None
    pv = None

# Ring currently highlighted in the preview (set from the dialog's ring
# table). Stored as a ring_key() string, or None for no highlight.
_highlighted_ring_key = None

HIGHLIGHT_COLOR = (1.0, 0.35, 0.1)


def set_highlighted_ring(key) -> None:
    """Select which ring gets an outline highlight on the next redraw."""
    global _highlighted_ring_key
    _highlighted_ring_key = key


def get_highlighted_ring():
    return _highlighted_ring_key


def _atom_color(symbol: str, cfg: StyleConfig, orig_index=None) -> tuple:
    return resolve_atom_color(cfg, symbol, orig_index)


# NOTE: must never contain keys that draw_preview_style passes to add_mesh
# explicitly (color, name, smooth_shading) — duplicate kwargs raise TypeError.
_PREVIEW_MATERIALS = {
    "metal":      {"metallic": 1.0, "roughness": 0.3, "pbr": True},
    "chrome":     {"metallic": 1.0, "roughness": 0.05, "pbr": True},
    "gold":       {"metallic": 1.0, "roughness": 0.25, "pbr": True},
    "copper":     {"metallic": 1.0, "roughness": 0.35, "pbr": True},
    "iridescent": {"metallic": 0.8, "roughness": 0.15, "pbr": True},
    "glass":      {"opacity": 0.35, "specular": 1.0},
    "ice":        {"opacity": 0.45, "specular": 1.0},
    "gummy":      {"opacity": 0.75, "specular": 0.6},
    "matte":      {"specular": 0.05, "diffuse": 1.0},
    "chalk":      {"specular": 0.0, "diffuse": 1.0, "ambient": 0.25},
    "stone":      {"specular": 0.02, "diffuse": 0.95, "ambient": 0.1},
    "velvet":     {"specular": 0.0, "diffuse": 1.0, "ambient": 0.2},
    "toon":       {"specular": 0.0, "diffuse": 1.0, "ambient": 0.35},
    "neon":       {"specular": 0.0, "diffuse": 0.4, "ambient": 0.9},
    "clay":       {"specular": 0.1, "diffuse": 0.9, "ambient": 0.15},
    "wax":        {"specular": 0.3, "diffuse": 0.9},
    "ceramic":    {"specular": 0.9, "diffuse": 0.9},
}


def _material_kwargs(cfg: StyleConfig) -> dict:
    default = {"specular": 0.5}
    res = dict(_PREVIEW_MATERIALS.get(cfg.material_preset, default))
    res.pop("color", None)
    res.pop("name", None)
    res.pop("smooth_shading", None)
    return res


def _ensure_lighting(plotter) -> None:
    """Restore scene lighting after plotter.clear() (which drops lights).

    Without this the spheres render flat/unlit ("like planes"). We reset to a
    deterministic 3-point light kit so the look is stable across redraws and
    independent of whatever the host had configured.
    """
    try:
        plotter.remove_all_lights()
    except Exception:
        logging.debug("BlenderExportPro: remove_all_lights failed", exc_info=True)
    try:
        plotter.enable_lightkit()
    except Exception:
        logging.debug("BlenderExportPro: enable_lightkit failed", exc_info=True)


def _light_direction(azimuth_deg, elevation_deg):
    """Unit direction from azimuth/elevation — same convention as codegen."""
    import math
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    return np.array([math.cos(el) * math.sin(az),
                     -math.cos(el) * math.cos(az),
                     math.sin(el)])


def _apply_lighting(plotter, cfg: StyleConfig, center, size) -> None:
    """Light the preview to match the exported Blender scene.

    Mirrors the key-light azimuth/elevation/strength and, when enabled,
    the custom light list (per-light position, intensity and color).
    Falls back to the standard light kit if anything goes wrong.
    """
    try:
        plotter.remove_all_lights()

        def add(direction_deg, distance_scale, intensity, color=(1.0, 1.0, 1.0)):
            direction = _light_direction(*direction_deg)
            pos = center + direction * size * distance_scale
            light = pv.Light(position=tuple(pos), focal_point=tuple(center),
                             color=tuple(color),
                             intensity=max(0.0, min(float(intensity), 3.0)))
            plotter.add_light(light)

        if cfg.use_custom_lights and isinstance(cfg.custom_lights, dict) \
                and cfg.custom_lights:
            for spec in _custom_light_list(cfg):
                # Blender energies are ~watts; normalize 1000 W -> 1.0.
                add((spec["azimuth"], spec["elevation"]), spec["distance"],
                    spec["energy"] / 1000.0, spec["color"])
        else:
            key_dir = (cfg.key_light_azimuth, cfg.key_light_elevation)
            strength = cfg.key_light_strength
            dist = cfg.light_distance_scale
            add(key_dir, dist, 1.0 * strength)
            add((cfg.key_light_azimuth + 180.0, cfg.key_light_elevation * 0.5),
                dist, cfg.fill_light_strength * strength)
            add((cfg.key_light_azimuth + 135.0, cfg.key_light_elevation),
                dist, cfg.rim_light_strength * strength)
        
        if hasattr(plotter, "set_environment_texture") and hasattr(pv, "cubemap"):
            try:
                plotter.set_environment_texture(pv.cubemap())
            except Exception:
                pass
    except Exception:
        logging.exception("BlenderExportPro: styled lighting failed, "
                          "falling back to light kit")
        _ensure_lighting(plotter)


def _displace(mesh, cfg: StyleConfig) -> None:
    """Smooth noise displacement along normals, mimicking the Displace
    modifier — same noise_displacement() field as the glTF export."""
    if cfg.deformation_noise <= 0.0:
        return
    try:
        mesh.compute_normals(inplace=True, auto_orient_normals=True)
        normals = mesh.point_data.get("Normals")
        if normals is None:
            return
        amounts = np.array([
            noise_displacement(p, cfg.deformation_noise,
                               cfg.deformation_noise_scale)
            for p in mesh.points])
        mesh.points = mesh.points + normals * amounts[:, None] * 0.5
    except Exception:
        logging.debug("BlenderExportPro: preview displace failed", exc_info=True)


def _add_smooth_gradient_bond(plotter, cfg, mat, seg_start, direction,
                              length, radius, color_a, color_b, name) -> bool:
    """One cylinder with per-vertex colors: a genuinely smooth gradient.

    Returns False on any failure so the caller can fall back to the
    piecewise-slice approximation.
    """
    try:
        seg_end = seg_start + direction * length
        cyl = pv.Cylinder(
            center=(seg_start + seg_end) / 2.0,
            direction=direction,
            radius=radius,
            height=length,
            resolution=max(6, cfg.bond_segments),
        )
        pts = np.asarray(cyl.points, dtype=float)
        t = np.clip((pts - seg_start) @ direction / length, 0.0, 1.0)
        colors = (np.outer(1.0 - t, np.asarray(color_a, dtype=float))
                  + np.outer(t, np.asarray(color_b, dtype=float)))
        if cfg.deform_bonds:
            _displace(cyl, cfg)
        plotter.add_mesh(
            cyl,
            scalars=colors,
            rgb=True,
            name=name,
            smooth_shading=cfg.shade_smooth,
            **mat,
        )
        return True
    except Exception:
        logging.debug("BlenderExportPro: smooth gradient bond failed, "
                      "falling back to slices", exc_info=True)
        return False


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

    # Atoms/bonds of paneled/outlined rings can be hidden (plate/line only).
    hidden_atoms, hide_bond_rings = set(), []
    if ring_panels_enabled(cfg) or ring_outlines_enabled(cfg):
        try:
            hidden_atoms, hide_bond_rings = ring_hidden_geometry(
                cfg, extract_rings(mol, None, cfg.ring_aromatic_only))
            hidden_atoms = set(hidden_atoms)
        except Exception:
            logging.exception("BlenderExportPro: ring-hide computation failed")

    # Hydrogens / specific atoms omitted entirely (sphere + every bond to it).
    hidden_endpoints = hidden_atom_indices(atoms, cfg)
    hidden_atoms |= hidden_endpoints

    positions = np.array([pos for _s, pos in atoms])
    center = positions.mean(axis=0)
    spans = positions.max(axis=0) - positions.min(axis=0)
    size = float(max(spans.max(), 1.0))

    try:
        plotter.clear()
    except Exception:
        logging.debug("BlenderExportPro: plotter.clear failed", exc_info=True)
    _apply_lighting(plotter, cfg, center, size)

    for idx, (symbol, pos) in enumerate(atoms):
        if idx in hidden_atoms:
            continue
        radius = resolve_atom_radius(cfg, symbol, idx)
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
        if cfg.deform_atoms:
            _displace(sphere, cfg)
        plotter.add_mesh(
            sphere,
            color=_atom_color(symbol, cfg, idx),
            name=f"bep_atom_{idx}",
            smooth_shading=cfg.shade_smooth,
            **mat,
        )

    bond_radius = max(cfg.bond_radius, 0.01)
    hidden_bonds = hidden_bond_keys(cfg)
    if cfg.hide_all_bonds:
        bonds = []
    for idx, bond in enumerate(bonds):
        i, j, order = bond[0], bond[1], bond[2]
        aromatic = bool(bond[3]) if len(bond) > 3 else False
        if i in hidden_endpoints or j in hidden_endpoints:
            continue
        if bond_key(i, j) in hidden_bonds:
            continue
        if any(i in members and j in members for members in hide_bond_rings):
            continue
        order, dashed = resolve_aromatic_display(cfg, order, aromatic)
        start, end = positions[i], positions[j]
        direction = end - start
        length = float(np.linalg.norm(direction))
        if length < 1e-6:
            continue
        direction = direction / length
        color_a = _atom_color(atoms[i][0], cfg, i)
        color_b = _atom_color(atoms[j][0], cfg, j)
        pieces = bond_piecewise(cfg, tuple(start), tuple(end),
                                color_a, color_b)

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
            radius = max(bond_radius * cfg.multi_bond_scale, 0.01)
        else:
            perp = np.zeros(3)
            offsets = [0.0]
            radius = bond_radius

        for k, off in enumerate(offsets):
            shift = perp * off
            if dashed and k == 1:
                # dashed second line for aromatic bonds
                axis = end - start
                for di, (t0, t1) in enumerate(dash_bounds()):
                    tm = (t0 + t1) / 2.0
                    if cfg.bond_color_mode == "gradient":
                        c = tuple(color_a[m] + (color_b[m] - color_a[m]) * tm
                                  for m in range(3))
                    elif cfg.bond_color_mode == "split":
                        c = color_a if tm < 0.5 else color_b
                    else:
                        c = pieces[0][2]
                    dash_start = start + axis * t0 + shift
                    dash_end = start + axis * t1 + shift
                    cyl = pv.Cylinder(
                        center=(dash_start + dash_end) / 2.0,
                        direction=direction,
                        radius=radius,
                        height=float(np.linalg.norm(dash_end - dash_start)),
                        resolution=max(6, cfg.bond_segments),
                    )
                    if cfg.deform_bonds:
                        _displace(cyl, cfg)
                    plotter.add_mesh(
                        cyl,
                        color=c,
                        name=f"bep_bond_{idx}_{k}_dash{di}",
                        smooth_shading=cfg.shade_smooth,
                        **mat,
                    )
                continue
            if (cfg.bond_color_mode == "gradient"
                    and tuple(color_a) != tuple(color_b)
                    and _add_smooth_gradient_bond(
                        plotter, cfg, mat, start + shift, direction, length,
                        radius, color_a, color_b, f"bep_bond_{idx}_{k}_0")):
                continue
            for p, (seg_start, seg_end, seg_color) in enumerate(pieces):
                seg_start = np.asarray(seg_start) + shift
                seg_end = np.asarray(seg_end) + shift
                seg_len = float(np.linalg.norm(seg_end - seg_start))
                if seg_len < 1e-6:
                    continue
                cyl = pv.Cylinder(
                    center=(seg_start + seg_end) / 2.0,
                    direction=direction,
                    radius=radius,
                    height=seg_len,
                    resolution=max(6, cfg.bond_segments),
                )
                if cfg.deform_bonds:
                    _displace(cyl, cfg)
                plotter.add_mesh(
                    cyl,
                    color=seg_color,
                    name=f"bep_bond_{idx}_{k}_{p}",
                    smooth_shading=cfg.shade_smooth,
                    **mat,
                )

    if ring_panels_enabled(cfg) or ring_outlines_enabled(cfg):
        _draw_ring_panels(plotter, mol, atoms, positions, cfg)

    if cfg.label_mode != "none":
        _draw_labels(plotter, atoms, positions, cfg, hidden_atoms)

    try:
        plotter.render()
    except Exception:
        logging.debug("BlenderExportPro: plotter.render failed", exc_info=True)


def _draw_ring_panels(plotter, mol, atoms, positions, cfg: StyleConfig) -> None:
    """Draw rings as filled polygon panels, honoring per-ring overrides.

    The ring selected in the dialog's ring table (set_highlighted_ring)
    additionally gets a bright outline tube so it is easy to spot.
    """
    try:
        rings = extract_rings(mol, None, cfg.ring_aromatic_only)
    except Exception:
        logging.exception("BlenderExportPro: ring extraction failed")
        return

    # Shade plates/outlines with the material preset too — but opacity is
    # passed explicitly for panels, so it must not appear twice.
    mat = _material_kwargs(cfg)
    mat.pop("opacity", None)

    for idx, ring in enumerate(rings):
        key = ring_key(ring)
        style = resolve_ring_style(cfg, key)
        highlighted = key == _highlighted_ring_key

        pts = positions[list(ring)].astype(float)
        center = pts.mean(axis=0)
        panel_pts = center + (pts - center) * style["scale"]
        n_pts = len(pts)
        face = np.hstack([[n_pts], np.arange(n_pts)])

        if style["color"]:
            color = hex_to_rgb(style["color"])
        elif cfg.ring_color_mode == "match_atoms":
            member_colors = [_atom_color(atoms[i][0], cfg, i) for i in ring]
            color = tuple(sum(c[k] for c in member_colors) / n_pts
                          for k in range(3))
        else:
            color = hex_to_rgb(cfg.ring_color)

        try:
            if style["visible"] and ring_panels_enabled(cfg):
                panel = pv.PolyData(panel_pts, faces=face)
                if style["thickness"] > 0.0:
                    normal = np.cross(
                        panel_pts[1] - panel_pts[0], panel_pts[2] - panel_pts[0])
                    norm_len = np.linalg.norm(normal)
                    if norm_len > 1e-9:
                        normal = normal / norm_len * style["thickness"]
                        panel.points = panel.points - normal / 2.0
                        panel = panel.extrude(normal, capping=True)
                plotter.add_mesh(
                    panel,
                    color=color,
                    opacity=style["opacity"],
                    name=f"bep_ring_{idx}",
                    **mat,
                )
            if style["visible"] and ring_outlines_enabled(cfg):
                loop = np.vstack([panel_pts, panel_pts[:1]])
                lines = np.hstack([[n_pts + 1], np.arange(n_pts + 1)])
                outline = pv.PolyData(loop)
                outline.lines = lines
                try:
                    outline = outline.tube(
                        radius=max(cfg.ring_outline_radius, 0.005))
                except Exception:
                    logging.debug("BlenderExportPro: outline tube() failed, "
                                  "using lines", exc_info=True)
                plotter.add_mesh(
                    outline,
                    color=color,
                    name=f"bep_ring_line_{idx}",
                    smooth_shading=True,
                    **mat,
                )
            if highlighted:
                _draw_ring_highlight(plotter, idx, pts, cfg)
        except Exception:
            logging.exception("BlenderExportPro: ring panel preview failed")


def _draw_labels(plotter, atoms, positions, cfg: StyleConfig,
                 hidden_atoms=None) -> None:
    """Screen-space text labels approximating the exported 3D labels."""
    hidden = hidden_atoms or set()
    labels, pts = [], []
    for idx, (symbol, _pos) in enumerate(atoms):
        if idx in hidden:
            continue
        if cfg.label_mode == "symbol":
            labels.append(symbol)
        elif cfg.label_mode == "index":
            labels.append(str(idx))
        else:
            labels.append(f"{symbol}{idx}")
        pts.append(positions[idx])
    if not pts:
        return
    positions = np.array(pts)
    try:
        plotter.add_point_labels(
            positions,
            labels,
            font_size=max(8, int(cfg.label_size * 40)),
            text_color=hex_to_rgb(cfg.label_color),
            shape=None,
            show_points=False,
            always_visible=True,
            name="bep_labels",
        )
    except TypeError:
        try:  # older pyvista without some kwargs
            plotter.add_point_labels(positions, labels, show_points=False)
        except Exception:
            logging.exception("BlenderExportPro: label preview failed")
    except Exception:
        logging.exception("BlenderExportPro: label preview failed")


def _draw_ring_highlight(plotter, idx, pts, cfg: StyleConfig) -> None:
    """Bright outline tube around the ring perimeter (selection marker)."""
    n_pts = len(pts)
    loop = np.vstack([pts, pts[:1]])
    lines = np.hstack([[n_pts + 1], np.arange(n_pts + 1)])
    outline = pv.PolyData(loop)
    outline.lines = lines
    radius = max(cfg.bond_radius * 1.4, 0.08)
    try:
        outline = outline.tube(radius=radius)
    except Exception:
        logging.debug("BlenderExportPro: tube() failed, using lines",
                      exc_info=True)
    plotter.add_mesh(
        outline,
        color=HIGHLIGHT_COLOR,
        opacity=1.0,
        name=f"bep_ring_highlight_{idx}",
    )
