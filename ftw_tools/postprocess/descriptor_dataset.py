"""Compatibility imports for independently packaged descriptor datasets."""

from ftw_geometry.core import dataset as _implementation

__all__ = [name for name in dir(_implementation) if not name.startswith("_")]


def __getattr__(name):
    return getattr(_implementation, name)
