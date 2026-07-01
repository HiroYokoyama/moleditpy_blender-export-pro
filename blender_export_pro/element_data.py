"""Element display data: colors and radii.

Prefers live data from the host environment:
- colors from the main app's CPK table (``moleditpy.utils.constants``),
  which includes any user customizations;
- radii from RDKit's van der Waals table (``GetPeriodicTable().GetRvdw``),
  the same source the main app uses.

Falls back to the bundled tables below when running standalone/headless,
so codegen and tests never require rdkit/moleditpy/Qt.
"""

import logging

# Fallback van der Waals radii in Angstrom (Bondi-style, matching RDKit).
VDW_RADII = {
    "H": 1.20, "He": 1.40,
    "Li": 1.82, "Be": 1.53, "B": 1.92, "C": 1.70, "N": 1.55, "O": 1.52,
    "F": 1.47, "Ne": 1.54,
    "Na": 2.27, "Mg": 1.73, "Al": 1.84, "Si": 2.10, "P": 1.80, "S": 1.80,
    "Cl": 1.75, "Ar": 1.88,
    "K": 2.75, "Ca": 2.31, "Sc": 2.15, "Ti": 2.11, "V": 2.07, "Cr": 2.06,
    "Mn": 2.05, "Fe": 2.04, "Co": 2.00, "Ni": 1.97, "Cu": 1.96, "Zn": 2.01,
    "Ga": 1.87, "Ge": 2.11, "As": 1.85, "Se": 1.90, "Br": 1.85, "Kr": 2.02,
    "Rb": 3.03, "Sr": 2.49, "Y": 2.32, "Zr": 2.23, "Nb": 2.18, "Mo": 2.17,
    "Tc": 2.16, "Ru": 2.13, "Rh": 2.10, "Pd": 2.10, "Ag": 2.11, "Cd": 2.18,
    "In": 1.93, "Sn": 2.17, "Sb": 2.06, "Te": 2.06, "I": 1.98, "Xe": 2.16,
    "Cs": 3.43, "Ba": 2.68, "La": 2.43, "Pt": 2.13, "Au": 2.14, "Hg": 2.23,
    "Tl": 1.96, "Pb": 2.02, "Bi": 2.07,
}
DEFAULT_RADIUS = 1.70

# Fallback CPK-like colors as (r, g, b) floats in 0..1.
CPK_COLORS = {
    "H": (0.90, 0.90, 0.90),
    "He": (0.85, 1.00, 1.00),
    "Li": (0.80, 0.50, 1.00),
    "Be": (0.76, 1.00, 0.00),
    "B": (1.00, 0.71, 0.71),
    "C": (0.30, 0.30, 0.30),
    "N": (0.19, 0.31, 0.97),
    "O": (1.00, 0.05, 0.05),
    "F": (0.56, 0.88, 0.31),
    "Ne": (0.70, 0.89, 0.96),
    "Na": (0.67, 0.36, 0.95),
    "Mg": (0.54, 1.00, 0.00),
    "Al": (0.75, 0.65, 0.65),
    "Si": (0.94, 0.78, 0.63),
    "P": (1.00, 0.50, 0.00),
    "S": (1.00, 1.00, 0.19),
    "Cl": (0.12, 0.94, 0.12),
    "Ar": (0.50, 0.82, 0.89),
    "K": (0.56, 0.25, 0.83),
    "Ca": (0.24, 1.00, 0.00),
    "Fe": (0.88, 0.40, 0.20),
    "Cu": (0.78, 0.50, 0.20),
    "Zn": (0.49, 0.50, 0.69),
    "Br": (0.65, 0.16, 0.16),
    "I": (0.58, 0.00, 0.58),
    "Pt": (0.82, 0.82, 0.88),
    "Au": (1.00, 0.82, 0.14),
    "Hg": (0.72, 0.72, 0.82),
    "Pb": (0.34, 0.35, 0.38),
}
DEFAULT_COLOR = (0.78, 0.44, 0.86)


def radius_of(symbol: str) -> float:
    """Van der Waals radius (Angstrom): RDKit's table, else fallback."""
    try:
        from rdkit import Chem
        pt = Chem.GetPeriodicTable()
        num = pt.GetAtomicNumber(str(symbol))
        if num > 0:
            radius = float(pt.GetRvdw(num))
            if radius > 0.0:
                return radius
    except Exception:
        logging.debug("BlenderExportPro: RDKit radius lookup failed",
                      exc_info=True)
    return VDW_RADII.get(symbol, DEFAULT_RADIUS)


def color_of(symbol: str) -> tuple:
    """(r, g, b) floats: main app CPK table (live, incl. user edits), else fallback."""
    try:
        from moleditpy.utils.constants import CPK_COLORS as APP_COLORS
        if isinstance(APP_COLORS, dict):
            qcolor = APP_COLORS.get(symbol) or APP_COLORS.get("DEFAULT")
            if qcolor is not None:
                return (float(qcolor.redF()), float(qcolor.greenF()),
                        float(qcolor.blueF()))
    except Exception:
        logging.debug("BlenderExportPro: main app color lookup failed",
                      exc_info=True)
    return CPK_COLORS.get(symbol, DEFAULT_COLOR)
