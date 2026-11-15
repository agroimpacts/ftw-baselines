"""Compatibility imports for independently packaged geometry analysis."""

from ftw_geometry.core import analysis as _implementation

__all__ = [name for name in dir(_implementation) if not name.startswith("_")]


def __getattr__(name):
    return getattr(_implementation, name)
