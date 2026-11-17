import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from ftw_geometry.core.descriptors import DESCRIPTOR_COLUMNS, describe_polygons
from ftw_geometry.io.manifests import file_digest, write_json
from shapely.geometry import MultiPolygon, box

from research.geometry.summarize_descriptor_pilot import (
    enrich_summary,
    measured_context,
    run,
    verify,
)


def sample_fields():
    return gpd.GeoDataFrame(
        {"id": ["a", "b", "c"], "collection": ["test"] * 3},
        geometry=[
            box(400, 400, 420, 430),
            box(450, 400, 480, 430),
            box(-10, 20, 10, 40),
        ],
        crs=32632,
    )


def measured(fields):
    return fields.merge(describe_polygons(fields), on="id", validate="one_to_one")


def test_context_preserves_frozen_values_and_normalizes_containers():
    fields = sample_fields()
    frozen = measured(fields.iloc[:2].copy())
    frozen.loc[0, "circularity"] = (
        0.123  # Ensure measurement is reused, not recomputed.
    )
    fields.loc[2, "geometry"] = MultiPolygon([fields.geometry.iloc[2]])
    table = measured_context(fields, frozen, "EPSG:32632")
    assert len(table) == 3
    assert table.loc[table.id.eq("a"), "circularity"].iloc[0] == 0.123
    assert table.field_key.is_unique
    assert table.touches_source_edge.isna().all()
    assert table.loc[table.id.eq("c"), "circularity"].isna().all()
    with pytest.raises(ValueError, match="Duplicate"):
        measured_context(pd.concat([fields, fields.iloc[:1]]), frozen, "EPSG:32632")


def test_gap_context_and_radius_censoring():
    table = measured_context(sample_fields(), measured(sample_fields()), "EPSG:32632")
    table["nearest_positive_gap_m"] = [30.0, np.nan, 20.0]
    summary = {
        "region_id": "one",
        "zone_id": "test",
        "metric_crs": "EPSG:32632",
        "positive_gap_observed_count": 2,
        "positive_gap_censored_count": 1,
        "mean_observed_positive_gap_m": 25.0,
    }
    summary, assigned, gaps = enrich_summary(summary, table, box(0, 0, 1000, 1000))
    assert len(gaps) == 3
    assert gaps[0]["context_complete_fields"] == 2
    assert gaps[0]["observed_fields"] == 1
    assert gaps[0]["radius_censored_fields"] == 1
    assert gaps[0]["edge_context_incomplete_fields"] == 1
    assert gaps[0]["mean_observed_gap_m"] == 30
    assert not assigned.gap_50m_context_complete.iloc[2]
    assert "mean_observed_positive_gap_m" not in summary
    assert summary["extract_only_mean_observed_positive_gap_m"] == 25


def test_rare_feature_area_fractions_and_source_mismatch():
    fields = sample_fields()
    frozen = measured(fields)
    table = measured_context(fields, frozen, "EPSG:32632")
    table["narrow_neck"] = [True, False, False]
    table["hole_count"] = [0, 1, 0]
    table["hole_area_m2"] = [0.0, 100.0, 0.0]
    table["nearest_positive_gap_m"] = [30.0, 30.0, np.nan]
    summary = {
        "region_id": "one",
        "zone_id": "test",
        "metric_crs": "EPSG:32632",
        "positive_gap_observed_count": 2,
        "positive_gap_censored_count": 1,
        "mean_observed_positive_gap_m": 30.0,
    }
    result, _, _ = enrich_summary(summary, table, box(0, 0, 1000, 1000))
    total = 600 + 900 + 400
    assert result["narrow_neck_area_fraction"] == pytest.approx(600 / total)
    assert result["fields_with_holes_area_fraction"] == pytest.approx(900 / total)
    assert result["hole_area_fraction_of_enclosed_area"] == pytest.approx(
        100 / (total + 100)
    )
    frozen.loc[0, "geometry"] = box(400, 400, 421, 430)
    with pytest.raises(ValueError, match="differs from source"):
        measured_context(fields, frozen, "EPSG:32632")


def test_run_keeps_empty_window_and_validates_hashes(tmp_path):
    review, descriptors, out = [tmp_path / p for p in ("review", "descriptors", "out")]
    descriptors.mkdir()
    windows = []
    for wid, fields in [
        ("one", sample_fields().iloc[:2].copy()),
        ("empty", sample_fields().iloc[:0].copy()),
    ]:
        source, destination = review / wid, descriptors / wid
        source.mkdir(parents=True)
        destination.mkdir()
        fields.to_parquet(source / "fields.parquet")
        boundary = (
            gpd.GeoSeries([box(0, 0, 1000, 1000)], crs=32632).to_crs(4326).iloc[0]
        )
        write_json(
            source / "provenance.json",
            {
                "window": {
                    "type": "Feature",
                    "geometry": boundary.__geo_interface__,
                    "properties": {
                        "window_id": wid,
                        "role": "primary",
                        "zone_id": "test",
                        "metric_crs": "EPSG:32632",
                    },
                }
            },
        )
        write_json(
            source / "complete.json",
            {"sha256": {p.name: file_digest(p) for p in source.iterdir()}},
        )
        measured(fields).to_parquet(destination / "descriptors.parquet")
        (destination / "review.html").write_text("test")
        windows.append({"window_id": wid, "role": "primary"})
    pd.DataFrame(windows).to_csv(descriptors / "window-summary.csv", index=False)
    write_json(
        descriptors / "complete.json",
        {
            "output_sha256": {
                str(p.relative_to(descriptors)): file_digest(p)
                for p in descriptors.rglob("*")
                if p.is_file()
            }
        },
    )
    result = run(review, descriptors, out, expected_windows=2)
    empty = result.set_index("region_id").loc["empty"]
    assert empty.field_count == 0
    assert empty.mapped_fraction == 0
    assert np.isnan(empty.circularity_mean)
    assert np.isnan(empty.narrow_neck_fraction)
    nonempty = result.set_index("region_id").loc["one"]
    assert nonempty.field_count == 2
    assert nonempty.mapped_fraction == pytest.approx(0.0015)
    assert nonempty.circularity_area_weighted_mean > 0
    for feature in DESCRIPTOR_COLUMNS[1:]:
        if feature not in {"orientation_deg", "orientation_ambiguous"}:
            assert nonempty[feature + "_finite_count"] == 2
            assert np.isfinite(nonempty[feature + "_mean"])
            assert np.isfinite(nonempty[feature + "_area_weighted_mean"])
            assert nonempty[feature + "_q05"] <= nonempty[feature + "_q95"]
    gaps = pd.read_csv(out / "gap-sensitivity.csv")
    assert len(gaps) == 6
    assert gaps.loc[gaps.window_id.eq("empty"), "mean_observed_gap_m"].isna().all()
    manifest = json.loads((out / "complete.json").read_text())
    assert manifest["assigned_fields"] == 2
    verify(out, "output_sha256")
    with pytest.raises(ValueError, match="fresh"):
        run(review, descriptors, out, expected_windows=2)
    (descriptors / "one" / "descriptors.parquet").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Changed input"):
        run(review, descriptors, tmp_path / "other", expected_windows=2)
