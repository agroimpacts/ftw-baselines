"""Compatibility imports; implementation lives in the optional geometry package."""

try:
    from ftw_geometry.core import descriptors as _implementation
except ImportError as error:
    raise ImportError(
        "Polygon descriptors require ftw-geometry. From this checkout run `uv sync --extra geometry` or install `./research/geometry`."
    ) from error

__all__ = [name for name in dir(_implementation) if not name.startswith("_")]


def __getattr__(name):
    return getattr(_implementation, name)
