import io

import geopandas as gpd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from research.geometry.retrieve_descriptor_pilot import overlapping_groups, review_html


def test_row_group_pruning_keeps_boundary_intersections():
    stream = io.BytesIO()
    table = pa.table(
        {
            "bbox": [
                {"xmin": float(i), "ymin": 0.0, "xmax": float(i + 1), "ymax": 1.0}
                for i in range(4)
            ]
        }
    )
    pq.write_table(table, stream, row_group_size=1)
    metadata = pq.read_metadata(io.BytesIO(stream.getvalue()))
    assert overlapping_groups(metadata, (1.5, 0.5, 2.0, 0.9)) == [1, 2]
    assert overlapping_groups(metadata, (8.0, 0.0, 9.0, 1.0)) == []


def test_pruning_refuses_unbounded_scan_without_statistics():
    stream = io.BytesIO()
    pq.write_table(pa.table({"geometry": [b"test"]}), stream)
    with pytest.raises(ValueError, match="Missing bbox"):
        overlapping_groups(
            pq.read_metadata(io.BytesIO(stream.getvalue())), (0, 0, 1, 1)
        )


def test_empty_review_map_retains_window_without_claiming_no_agriculture():
    fields = gpd.GeoDataFrame({"id": [], "score": []}, geometry=[], crs=4326)
    window = {
        "type": "Feature",
        "properties": {"window_id": "empty-review"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        },
    }
    html = review_html(window, fields)
    assert "0 intersecting published polygons" in html
    assert "empty-review" in html
    assert '"features": []' in html
