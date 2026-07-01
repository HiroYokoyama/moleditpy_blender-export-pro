"""Shared test infrastructure for moleditpy_blender-export-pro.

The core modules (style_config, element_data, blender_codegen) are pure
stdlib and import directly. GUI-facing modules (dialog, preview_style) are
imported under ``mock_optional_imports()`` which stubs PyQt6/pyvista/numpy.
"""

from __future__ import annotations

import contextlib
import importlib.abc
import importlib.machinery
import sys
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BLOCKED_TOPS: frozenset[str] = frozenset(
    {"PyQt6", "pyvista", "vtk", "numpy", "rdkit", "moleditpy"}
)


class _MagicLoader(importlib.abc.Loader):
    def create_module(self, spec: importlib.machinery.ModuleSpec) -> MagicMock:
        m = MagicMock()
        m.__name__ = spec.name
        m.__spec__ = spec
        m.__path__ = []
        m.__package__ = spec.name.split(".")[0]
        return m  # type: ignore[return-value]

    def exec_module(self, module: object) -> None:
        pass


class _MagicFinder(importlib.abc.MetaPathFinder):
    _loader = _MagicLoader()

    def find_spec(self, fullname, path, target=None):
        if fullname.split(".")[0] in BLOCKED_TOPS:
            return importlib.machinery.ModuleSpec(fullname, self._loader)
        return None


@contextlib.contextmanager
def mock_optional_imports() -> Generator[None, None, None]:
    removed = {
        k: sys.modules.pop(k)
        for k in list(sys.modules)
        if k.split(".")[0] in BLOCKED_TOPS
    }
    finder = _MagicFinder()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        sys.modules.update(removed)
        for k in list(sys.modules):
            if k.split(".")[0] in BLOCKED_TOPS and k not in removed:
                del sys.modules[k]


def make_context() -> MagicMock:
    """Stub PluginContext with a non-None main window."""
    ctx = MagicMock()
    ctx.get_main_window.return_value = MagicMock()
    return ctx


# --------------------------------------------------------------- fake RDKit


class FakePos:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class FakeConformer:
    def __init__(self, coords):
        self._coords = coords

    def GetAtomPosition(self, idx):
        return FakePos(*self._coords[idx])


class FakeAtom:
    def __init__(self, symbol, aromatic=False):
        self._symbol = symbol
        self._aromatic = aromatic

    def GetSymbol(self):
        return self._symbol

    def GetIsAromatic(self):
        return self._aromatic


class FakeRingInfo:
    def __init__(self, rings):
        self._rings = rings

    def AtomRings(self):
        return tuple(tuple(r) for r in self._rings)


class FakeBond:
    def __init__(self, i, j, order=1.0):
        self._i, self._j, self._order = i, j, order

    def GetBeginAtomIdx(self):
        return self._i

    def GetEndAtomIdx(self):
        return self._j

    def GetBondTypeAsDouble(self):
        return self._order


class FakeMol:
    """Duck-typed stand-in for an RDKit Mol with a 3D conformer."""

    def __init__(self, symbols, coords, bonds, rings=None, aromatic=None):
        self._symbols = symbols
        self._conf = FakeConformer(coords)
        self._bonds = [FakeBond(*b) for b in bonds]
        self._rings = list(rings or [])
        self._aromatic = set(aromatic or ())

    def GetConformer(self):
        return self._conf

    def GetNumAtoms(self):
        return len(self._symbols)

    def GetAtomWithIdx(self, idx):
        return FakeAtom(self._symbols[idx], aromatic=idx in self._aromatic)

    def GetBonds(self):
        return list(self._bonds)

    def GetRingInfo(self):
        return FakeRingInfo(self._rings)


def make_benzene_like() -> FakeMol:
    """Hexagonal aromatic C6 ring plus one non-aromatic substituent."""
    import math

    coords = [
        (math.cos(math.radians(60 * i)) * 1.4,
         math.sin(math.radians(60 * i)) * 1.4, 0.0)
        for i in range(6)
    ]
    coords.append((2.9, 0.0, 0.0))
    bonds = [(i, (i + 1) % 6, 1.5) for i in range(6)] + [(0, 6, 1.0)]
    return FakeMol(
        symbols=["C"] * 6 + ["Cl"],
        coords=coords,
        bonds=bonds,
        rings=[(0, 1, 2, 3, 4, 5)],
        aromatic=range(6),
    )


def make_ethanol_like() -> FakeMol:
    """Small test molecule: C-C-O with hydrogens omitted, C=O style bond mix."""
    return FakeMol(
        symbols=["C", "C", "O", "H"],
        coords=[
            (0.0, 0.0, 0.0),
            (1.5, 0.0, 0.0),
            (2.2, 1.1, 0.0),
            (-0.6, 0.9, 0.0),
        ],
        bonds=[(0, 1, 1.0), (1, 2, 2.0), (0, 3, 1.0)],
    )
