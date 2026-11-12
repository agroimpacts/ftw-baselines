"""Reference-free descriptors of final polygon geometry; no model dependencies."""

import math
from itertools import pairwise

import numpy as np
from pyproj import CRS
from shapely.affinity import translate
from shapely.geometry import Polygon

DESCRIPTOR_VERSION = "3.0"
NARROW_NECK_RADIUS_FRACTION = 0.10
NARROW_NECK_COMPONENT_FRACTION = 0.02

DESCRIPTOR_COLUMNS = [
    "id",
    "area_m2",
    "perimeter_m",
    "circularity",
    "elongation",
    "solidity",
    "rectangle_area_m2",
    "rectangle_length_m",
    "rectangle_width_m",
    "rectangularity",
    "convex_hull_area_m2",
    "convex_hull_perimeter_m",
    "convex_hull_index",
    "hole_count",
    "hole_area_m2",
    "hole_area_fraction",
    "orientation_deg",
    "narrow_neck",
    "orientation_ambiguous",
]


def metric_geometry_crs(frame, metric_crs=None):
    """Keep metre-projected inputs; otherwise select local UTM (no resampling)."""
    if frame.crs is None:
        raise ValueError("A source CRS is required")
    source = CRS.from_user_input(frame.crs)
    if metric_crs is None:
        if source.is_projected and all(
            axis.unit_conversion_factor == 1 for axis in source.axis_info[:2]
        ):
            metric_crs = source
        elif frame.empty:
            raise ValueError("Empty geographic data requires an explicit metric CRS")
        else:
            metric_crs = frame.estimate_utm_crs()
    crs = CRS.from_user_input(metric_crs)
    if not crs.is_projected or any(
        axis.unit_conversion_factor != 1 for axis in crs.axis_info[:2]
    ):
        raise ValueError("Descriptor CRS must be projected in metres")
    return crs


def polygon_descriptors(geometry):
    """Describe a valid single polygon in metres (including hole boundaries).

    Elongation is the minimum rotated rectangle's long/short side ratio.
    Circularity is 4*pi*area/perimeter²; solidity is area/convex-hull area.
    """
    if (
        geometry is None
        or geometry.geom_type != "Polygon"
        or geometry.is_empty
        or not geometry.is_valid
        or not math.isfinite(geometry.area)
        or geometry.area <= 0
    ):
        raise ValueError("Descriptors require a nonempty valid single polygon")
    area, perimeter = geometry.area, geometry.length
    # Avoid large-coordinate cancellation in GEOS's oriented-envelope calculation.
    local = translate(geometry, xoff=-geometry.bounds[0], yoff=-geometry.bounds[1])
    # Some GEOS builds signal floating-point divisions for axis-aligned edges
    # even when the returned rectangle is finite. Validate the result below.
    with np.errstate(divide="ignore", invalid="ignore"):
        corners = list(local.minimum_rotated_rectangle.exterior.coords)
    sides = [math.dist(a, b) for a, b in pairwise(corners)]
    if not sides or any(not math.isfinite(side) or side <= 0 for side in sides):
        raise ValueError("Polygon has a degenerate minimum rotated rectangle")
    long_side, short_side = max(sides), min(sides)
    hull = local.convex_hull
    hole_area = sum(Polygon(ring).area for ring in local.interiors)
    radius = math.sqrt(area / math.pi)
    eroded = local.buffer(-NARROW_NECK_RADIUS_FRACTION * radius)
    parts = list(eroded.geoms) if hasattr(eroded, "geoms") else [eroded]
    retained = [
        part for part in parts if part.area >= NARROW_NECK_COMPONENT_FRACTION * area
    ]
    ambiguous = long_side / short_side <= 1.05
    index = int(np.argmax(sides))
    dx = corners[index + 1][0] - corners[index][0]
    dy = corners[index + 1][1] - corners[index][1]
    # Axial angle counterclockwise from projected +x, not a true-north bearing.
    orientation = math.nan if ambiguous else math.degrees(math.atan2(dy, dx)) % 180
    circularity = 4 * math.pi * area / perimeter**2
    solidity = area / hull.area
    return {
        "area_m2": area,
        "perimeter_m": perimeter,
        "circularity": circularity,
        "elongation": long_side / short_side,
        "solidity": solidity,
        "rectangle_area_m2": long_side * short_side,
        "rectangle_length_m": long_side,
        "rectangle_width_m": short_side,
        "rectangularity": area / (long_side * short_side),
        "convex_hull_area_m2": hull.area,
        "convex_hull_perimeter_m": hull.length,
        "convex_hull_index": hull.length / perimeter,
        "hole_count": len(local.interiors),
        "hole_area_m2": hole_area,
        "hole_area_fraction": hole_area / (area + hole_area),
        "orientation_deg": orientation,
        "orientation_ambiguous": ambiguous,
        "narrow_neck": len(retained) >= 2,
    }


def describe_polygons(frame, metric_crs=None):
    """Return an ID-keyed descriptor table for an existing GeoDataFrame.

    Output geometries are not changed. Geographic inputs use a local UTM CRS
    unless an explicit metre-based projected CRS is supplied.
    """
    import pandas as pd

    if (
        frame.crs is None
        or "id" not in frame
        or frame.id.isna().any()
        or not frame.id.is_unique
    ):
        raise ValueError("A CRS and unique field IDs are required")
    crs = metric_geometry_crs(frame, metric_crs)
    projected = frame.to_crs(crs)
    rows = [
        {"id": row.id, **polygon_descriptors(row.geometry)}
        for row in projected.itertuples()
    ]
    return pd.DataFrame(rows, columns=DESCRIPTOR_COLUMNS)
