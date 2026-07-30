"""Element display data: colors and radii.

Prefers live data from the host environment:
- colors from the main app's CPK table (``moleditpy.utils.constants``),
  which includes any user customizations;
- radii from RDKit's van der Waals table (``GetPeriodicTable().GetRvdw``),
  the same source the main app uses.

Falls back to the bundled tables below when running standalone/headless, so
codegen and tests never require rdkit/moleditpy/Qt. Those tables are generated
from the same two sources, so the fallback and the live path agree -- see
tests/test_element_data.py, which fails if they drift apart.
"""

import logging

# Fallback van der Waals radii in Angstrom, generated from RDKit's table
# (GetPeriodicTable().GetRvdw) for Z=1..103 so the fallback renders exactly
# what the live path does. An earlier hand-written Bondi table disagreed with
# RDKit for 51 of its 63 entries and omitted 40 elements, so the lanthanides,
# actinides and 5d metals all drew at DEFAULT_RADIUS.
VDW_RADII = {
    "H": 1.20, "He": 1.40, "Li": 2.20, "Be": 1.90, "B": 1.80, "C": 1.70,
    "N": 1.60, "O": 1.55, "F": 1.50, "Ne": 1.54, "Na": 2.40, "Mg": 2.20,
    "Al": 2.10, "Si": 2.10, "P": 1.95, "S": 1.80, "Cl": 1.80, "Ar": 1.88,
    "K": 2.80, "Ca": 2.40, "Sc": 2.30, "Ti": 2.15, "V": 2.05, "Cr": 2.05,
    "Mn": 2.05, "Fe": 2.05, "Co": 2.00, "Ni": 2.00, "Cu": 2.00, "Zn": 2.10,
    "Ga": 2.10, "Ge": 2.10, "As": 2.05, "Se": 1.90, "Br": 1.90, "Kr": 2.02,
    "Rb": 2.90, "Sr": 2.55, "Y": 2.40, "Zr": 2.30, "Nb": 2.15, "Mo": 2.10,
    "Tc": 2.05, "Ru": 2.05, "Rh": 2.00, "Pd": 2.05, "Ag": 2.10, "Cd": 2.20,
    "In": 2.20, "Sn": 2.25, "Sb": 2.20, "Te": 2.10, "I": 2.10, "Xe": 2.16,
    "Cs": 3.00, "Ba": 2.70, "La": 2.50, "Ce": 2.48, "Pr": 2.47, "Nd": 2.45,
    "Pm": 2.43, "Sm": 2.42, "Eu": 2.40, "Gd": 2.38, "Tb": 2.37, "Dy": 2.35,
    "Ho": 2.33, "Er": 2.32, "Tm": 2.30, "Yb": 2.28, "Lu": 2.27, "Hf": 2.25,
    "Ta": 2.20, "W": 2.10, "Re": 2.05, "Os": 2.00, "Ir": 2.00, "Pt": 2.05,
    "Au": 2.10, "Hg": 2.05, "Tl": 2.20, "Pb": 2.30, "Bi": 2.30, "Po": 2.00,
    "At": 2.00, "Rn": 2.00, "Fr": 2.00, "Ra": 2.00, "Ac": 2.00, "Th": 2.40,
    "Pa": 2.00, "U": 2.30, "Np": 2.00, "Pu": 2.00, "Am": 2.00, "Cm": 2.00,
    "Bk": 2.00, "Cf": 2.00, "Es": 2.00, "Fm": 2.00, "Md": 2.00, "No": 2.00,
    "Lr": 2.00,
}
DEFAULT_RADIUS = 1.70

# Fallback CPK colors as (r, g, b) floats in 0..1, generated from the main
# app's CPK_COLORS so standalone output matches in-app rendering. The previous
# hand-written table held 29 entries, leaving 74 elements on DEFAULT_COLOR.
CPK_COLORS = {
    "H": (1.0000, 1.0000, 1.0000),
    "He": (0.8510, 1.0000, 1.0000),
    "Li": (0.8000, 0.5020, 1.0000),
    "Be": (0.7608, 1.0000, 0.0000),
    "B": (0.9804, 0.5020, 0.4471),
    "C": (0.1333, 0.1333, 0.1333),
    "N": (0.2000, 0.4667, 1.0000),
    "O": (1.0000, 0.2000, 0.2000),
    "F": (0.6000, 0.9020, 0.9020),
    "Ne": (0.7020, 0.8902, 0.9608),
    "Na": (0.6706, 0.3608, 0.9490),
    "Mg": (0.5412, 1.0000, 0.0000),
    "Al": (0.7020, 0.6510, 0.5608),
    "Si": (0.8549, 0.6471, 0.1255),
    "P": (1.0000, 0.5020, 0.0000),
    "S": (1.0000, 0.7529, 0.0000),
    "Cl": (0.2000, 1.0000, 0.2000),
    "Ar": (0.5020, 0.8196, 0.8902),
    "K": (0.5608, 0.2667, 0.8431),
    "Ca": (0.2392, 1.0000, 0.0000),
    "Sc": (0.9020, 0.9020, 0.9020),
    "Ti": (0.7490, 0.7608, 0.7804),
    "V": (0.6510, 0.6510, 0.6706),
    "Cr": (0.5412, 0.6000, 0.7804),
    "Mn": (0.6118, 0.4784, 0.7804),
    "Fe": (0.8784, 0.4000, 0.2000),
    "Co": (0.9412, 0.5647, 0.6275),
    "Ni": (0.3137, 0.8157, 0.3137),
    "Cu": (0.7843, 0.5020, 0.2000),
    "Zn": (0.4902, 0.5020, 0.6902),
    "Ga": (0.7608, 0.5608, 0.5608),
    "Ge": (0.4000, 0.5608, 0.5608),
    "As": (0.7412, 0.5020, 0.8902),
    "Se": (1.0000, 0.6314, 0.0000),
    "Br": (0.6471, 0.1647, 0.1647),
    "Kr": (0.3608, 0.6745, 0.7843),
    "Rb": (0.4392, 0.1804, 0.7373),
    "Sr": (0.0000, 1.0000, 0.0000),
    "Y": (0.6000, 1.0000, 1.0000),
    "Zr": (0.4941, 0.9059, 0.9059),
    "Nb": (0.4078, 0.8118, 0.8078),
    "Mo": (0.3216, 0.7176, 0.7176),
    "Tc": (0.2314, 0.6196, 0.6196),
    "Ru": (0.1412, 0.5608, 0.5608),
    "Rh": (0.0392, 0.4902, 0.5608),
    "Pd": (0.0000, 0.4118, 0.5216),
    "Ag": (0.7529, 0.7529, 0.7529),
    "Cd": (1.0000, 0.8431, 0.0000),
    "In": (0.6510, 0.4588, 0.4510),
    "Sn": (0.4000, 0.5020, 0.5020),
    "Sb": (0.6196, 0.3882, 0.7098),
    "Te": (0.8314, 0.4784, 0.0000),
    "I": (0.5804, 0.0000, 0.8275),
    "Xe": (0.2588, 0.6196, 0.6902),
    "Cs": (0.3373, 0.1059, 0.6196),
    "Ba": (0.0000, 0.9020, 0.0000),
    "La": (0.4392, 0.8314, 1.0000),
    "Ce": (1.0000, 1.0000, 0.7804),
    "Pr": (0.8510, 1.0000, 0.7804),
    "Nd": (0.7804, 1.0000, 0.7804),
    "Pm": (0.6392, 1.0000, 0.7804),
    "Sm": (0.5608, 1.0000, 0.7804),
    "Eu": (0.3804, 1.0000, 0.7804),
    "Gd": (0.2706, 1.0000, 0.7804),
    "Tb": (0.1882, 1.0000, 0.7804),
    "Dy": (0.1216, 1.0000, 0.7804),
    "Ho": (0.0000, 1.0000, 0.6118),
    "Er": (0.0000, 0.9020, 0.4588),
    "Tm": (0.0000, 0.8314, 0.3216),
    "Yb": (0.0000, 0.7490, 0.2196),
    "Lu": (0.0000, 0.6706, 0.1412),
    "Hf": (0.3020, 0.7608, 1.0000),
    "Ta": (0.3020, 0.6510, 1.0000),
    "W": (0.1294, 0.5804, 0.8392),
    "Re": (0.1490, 0.4902, 0.6706),
    "Os": (0.1490, 0.4000, 0.5882),
    "Ir": (0.0902, 0.3294, 0.5294),
    "Pt": (0.8157, 0.8157, 0.8784),
    "Au": (1.0000, 0.8196, 0.1373),
    "Hg": (0.7216, 0.7216, 0.8157),
    "Tl": (0.6510, 0.3294, 0.3020),
    "Pb": (0.3412, 0.3490, 0.3804),
    "Bi": (0.6196, 0.3098, 0.7098),
    "Po": (0.6706, 0.3608, 0.0000),
    "At": (0.4588, 0.3098, 0.2706),
    "Rn": (0.1608, 0.5608, 0.6353),
    "Fr": (0.2588, 0.0745, 0.5176),
    "Ra": (0.0000, 0.7216, 0.0000),
    "Ac": (0.4392, 0.6706, 0.9804),
    "Th": (0.0000, 0.7294, 1.0000),
    "Pa": (0.0000, 0.6314, 1.0000),
    "U": (0.0000, 0.5608, 1.0000),
    "Np": (0.0000, 0.5020, 1.0000),
    "Pu": (0.0000, 0.4196, 1.0000),
    "Am": (0.3294, 0.3608, 0.9490),
    "Cm": (0.4706, 0.3608, 0.8902),
    "Bk": (0.5412, 0.3098, 0.8902),
    "Cf": (0.6314, 0.2118, 0.8314),
    "Es": (0.7020, 0.1216, 0.8314),
    "Fm": (0.7020, 0.1216, 0.7294),
    "Md": (0.7020, 0.0510, 0.6510),
    "No": (0.7412, 0.0510, 0.5294),
    "Lr": (0.7804, 0.0000, 0.4000),
}
DEFAULT_COLOR = (1.0000, 0.0784, 0.5765)


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
