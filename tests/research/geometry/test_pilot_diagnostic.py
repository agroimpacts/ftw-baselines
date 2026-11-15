import pytest
from shapely.geometry import box

from research.geometry.add_descriptor_pilot_diagnostic import shifted_diagnostic


def test_shift_is_supplementary_preserves_source_and_size():
    source = {
        "zone_id": "bahia",
        "window_id": "bahia_45_871",
        "year": 2024,
        "geometry": box(450000, 8710000, 460000, 8720000),
    }
    diagnostic = shifted_diagnostic(source, 35000, "bahia_45_871_pivots_w35km")
    assert diagnostic["geometry"].bounds == (415000, 8710000, 425000, 8720000)
    assert diagnostic["geometry"].area == source["geometry"].area == 100000000
    assert source["geometry"].bounds == (450000, 8710000, 460000, 8720000)
    assert diagnostic["include_in_primary_statistics"] is False
    assert diagnostic["role"] == "diagnostic"
    assert "priority" not in diagnostic
    assert diagnostic["source_window_id"] == source["window_id"]


def test_shift_requires_positive_distance():
    with pytest.raises(ValueError, match="positive"):
        shifted_diagnostic({}, 0, "bad")
