import math

import pytest
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from ftw_tools.postprocess.descriptors import DESCRIPTOR_COLUMNS, polygon_descriptors


def test_rectangle_and_reduced_schema():
    values = polygon_descriptors(box(0, 0, 8, 2))
    assert set(values) == set(DESCRIPTOR_COLUMNS) - {"id"}
    assert values["rectangle_area_m2"] == 16
    assert values["rectangularity"] == 1
    assert values["orientation_deg"] == 0
    assert not values["orientation_ambiguous"]
    assert values["circularity"] == pytest.approx(4 * math.pi * 16 / 20**2)
    assert values["elongation"] == 4
    assert not set(values) & {
        "compactness",
        "area_ha",
        "equal_area_circle_radius_m",
        "ftw_elongation_short_long",
        "convex_hull_deviation_ratio",
        "shape_index",
        "boundary_complexity",
        "fractal_index",
    }


def test_holes_circle_and_orientation():
    polygon = Polygon(
        box(0, 0, 10, 10).exterior.coords, [box(2, 2, 4, 4).exterior.coords]
    )
    values = polygon_descriptors(polygon)
    assert values["hole_count"] == 1
    assert values["hole_area_m2"] == 4
    assert values["hole_area_fraction"] == 0.04
    assert values["orientation_ambiguous"]
    assert math.isnan(values["orientation_deg"])
    assert polygon_descriptors(Point(0, 0).buffer(10, quad_segs=256))[
        "circularity"
    ] == pytest.approx(1, rel=1e-4)


def test_narrow_neck():
    shape = unary_union([box(0, 0, 10, 10), box(20, 0, 30, 10), box(9, 4.8, 21, 5.2)])
    assert polygon_descriptors(shape)["narrow_neck"]
    assert not polygon_descriptors(box(0, 0, 30, 10))["narrow_neck"]


def test_processing_sensitivity_and_scale_invariance():
    from shapely.affinity import rotate, scale

    shape = Polygon([(0, 0), (10, 0), (10, 3), (9.8, 3.1), (10, 3.2), (10, 5), (0, 5)])
    raw = polygon_descriptors(shape)
    cleaned = polygon_descriptors(shape.simplify(0.5))
    assert cleaned["perimeter_m"] < raw["perimeter_m"]
    assert cleaned["circularity"] != raw["circularity"]
    enlarged = polygon_descriptors(scale(shape, xfact=10, yfact=10))
    assert enlarged["area_m2"] == pytest.approx(raw["area_m2"] * 100)
    for column in (
        "circularity",
        "elongation",
        "solidity",
        "rectangularity",
        "convex_hull_index",
    ):
        assert enlarged[column] == pytest.approx(raw[column])
    rotated = polygon_descriptors(rotate(box(0, 0, 8, 2), 30))
    assert rotated["orientation_deg"] == pytest.approx(30)
    holed = Polygon(
        box(0, 0, 10, 10).exterior.coords, [box(2, 2, 4, 4).exterior.coords]
    )
    filled = polygon_descriptors(Polygon(holed.exterior))
    assert filled["hole_count"] == 0
    assert filled["area_m2"] > polygon_descriptors(holed)["area_m2"]
