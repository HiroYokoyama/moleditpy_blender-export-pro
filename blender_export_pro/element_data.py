"""Element display data (CPK radii and colors) used by codegen and preview.

Pure Python — no third-party imports so it stays testable headlessly.
"""

# Covalent-ish display radii in Angstroms (ball-and-stick scale base).
CPK_RADII = {
    "H": 0.31, "He": 0.28,
    "Li": 1.28, "Be": 0.96, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66,
    "F": 0.57, "Ne": 0.58,
    "Na": 1.66, "Mg": 1.41, "Al": 1.21, "Si": 1.11, "P": 1.07, "S": 1.05,
    "Cl": 1.02, "Ar": 1.06,
    "K": 2.03, "Ca": 1.76, "Sc": 1.70, "Ti": 1.60, "V": 1.53, "Cr": 1.39,
    "Mn": 1.39, "Fe": 1.32, "Co": 1.26, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22,
    "Ga": 1.22, "Ge": 1.20, "As": 1.19, "Se": 1.20, "Br": 1.20, "Kr": 1.16,
    "Rb": 2.20, "Sr": 1.95, "Y": 1.90, "Zr": 1.75, "Nb": 1.64, "Mo": 1.54,
    "Tc": 1.47, "Ru": 1.46, "Rh": 1.42, "Pd": 1.39, "Ag": 1.45, "Cd": 1.44,
    "In": 1.42, "Sn": 1.39, "Sb": 1.39, "Te": 1.38, "I": 1.39, "Xe": 1.40,
    "Cs": 2.44, "Ba": 2.15, "La": 2.07, "Pt": 1.36, "Au": 1.36, "Hg": 1.32,
    "Tl": 1.45, "Pb": 1.46, "Bi": 1.48,
}
DEFAULT_RADIUS = 1.20

# CPK-like colors as (r, g, b) floats in 0..1.
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
    """Display radius (Angstrom) for an element symbol."""
    return CPK_RADII.get(symbol, DEFAULT_RADIUS)


def color_of(symbol: str) -> tuple:
    """CPK (r, g, b) floats for an element symbol."""
    return CPK_COLORS.get(symbol, DEFAULT_COLOR)
