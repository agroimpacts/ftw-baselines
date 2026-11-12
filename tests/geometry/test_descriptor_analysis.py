import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from ftw_tools.postprocess.descriptor_analysis import (
    PairMoments,
    correlate_tables,
    summarize_regions,
)
from ftw_tools.postprocess.descriptor_dataset import (
    build_dataset,
    dataset_parts,
    descriptor_batches,
    vector_batches,
)


def make_dataset(tmp_path, *, duplicate=False, footprint=True, batch_size=2):
    geometries = [box(1, 1, 3, 3), box(4, 1, 6, 3), box(8, 2, 14, 4)]
    if duplicate:
        geometries.append(geometries[0])
    fields = gpd.GeoDataFrame(
        {"id": [str(i) for i in range(len(geometries))]}, geometry=geometries, crs=32632
    )
    source = tmp_path / "fields.parquet"
    fields.to_parquet(source)
    boundary = tmp_path / "footprint.gpkg"
    gpd.GeoDataFrame(geometry=[box(0, 0, 20, 10)], crs=32632).to_file(boundary)
    config = {
        "dataset_id": "synthetic",
        "run_id": "test",
        "metric_crs": "EPSG:32632",
        "duplicate_policy": "keep",
        "field_semantics": "complete-fields",
        "sources": [
            {
                "source_id": "one",
                "path": "fields.parquet",
                "footprint": "footprint.gpkg" if footprint else None,
                "provenance": {"resolution_m": None, "simplify_m": 0},
            }
        ],
    }
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps(config))
    output = tmp_path / "dataset"
    build_dataset(path, output, batch_size)
    return path, output


def test_batched_generation_resume_and_provenance(tmp_path):
    config, output = make_dataset(tmp_path)
    paths = list(dataset_parts(output))
    assert len(paths) == 2
    before = [path.stat().st_mtime_ns for path in paths]
    build_dataset(config, output, 2)
    assert before == [path.stat().st_mtime_ns for path in paths]
    frame = pd.concat(descriptor_batches(output))
    assert len(frame) == 3
    assert frame.field_key.is_unique
    assert frame.touches_source_edge.eq(False).all()
    assert set(frame.descriptor_version) == {"3.0"}
    assert frame.orientation_cos2.iloc[2] == pytest.approx(1)
    with pytest.raises(ValueError, match="changed"):
        build_dataset(config, output, 3)
    paths[0].write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        list(dataset_parts(output))


def test_duplicate_policy_and_cross_batch_ids(tmp_path):
    config, _ = make_dataset(tmp_path, duplicate=True)
    settings = json.loads(config.read_text())
    settings["duplicate_policy"] = "error-identical"
    config.write_text(json.dumps(settings))
    with pytest.raises(ValueError, match="Identical"):
        build_dataset(config, tmp_path / "reject", 2)
    fields = gpd.read_parquet(tmp_path / "fields.parquet")
    fields.loc[2, "id"] = "0"
    fields.to_parquet(tmp_path / "fields.parquet")
    settings["duplicate_policy"] = "keep"
    config.write_text(json.dumps(settings))
    with pytest.raises(ValueError, match="Duplicate field ID"):
        build_dataset(config, tmp_path / "bad-ids", 2)


def test_vector_batch_geopackage(tmp_path):
    source = tmp_path / "fields.gpkg"
    gpd.GeoDataFrame(
        {"id": ["a", "b", "c"]},
        geometry=[box(i, 0, i + 1, 1) for i in range(3)],
        crs=32632,
    ).to_file(source)
    batches = list(vector_batches(source, 2))
    assert [len(frame) for frame in batches] == [2, 1]
    assert pd.concat(batches).id.tolist() == ["a", "b", "c"]


def test_regional_assignment_union_and_gaps(tmp_path):
    _, dataset = make_dataset(tmp_path)
    regions = tmp_path / "regions.gpkg"
    gpd.GeoDataFrame(
        {"name": ["A", "B", "empty"]},
        geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10), box(30, 0, 40, 10)],
        crs=32632,
    ).to_file(regions)
    output = tmp_path / "regions-output"
    summary = summarize_regions(
        dataset,
        regions,
        output,
        region_id="name",
        edge_policy="exclude",
        gap_radius_m=5,
    ).set_index("region_id")
    assert summary.loc["A", "field_count"] == 2
    assert summary.loc["B", "field_count"] == 1
    assert summary.loc["A", "mapped_union_area_m2"] == 12
    assert summary.loc["B", "mapped_union_area_m2"] == 8
    assert summary.loc["A", "mean_observed_positive_gap_m"] == 1
    assert summary.loc["B", "mean_observed_positive_gap_m"] == 2
    assert summary.loc["B", "region_crossing_field_count"] == 1
    assert summary.loc["empty", "field_count"] == 0
    assigned = pd.concat(
        pd.read_parquet(path) for path in (output / "assigned_fields").glob("*.parquet")
    )
    assert assigned.field_key.is_unique
    assert assigned.area_m2.sum() == 20  # full fields, not clipped descriptors
    assert json.loads((output / "analysis.json").read_text())["complete"]
    with pytest.raises(ValueError, match="exceeds"):
        summarize_regions(
            dataset,
            regions,
            tmp_path / "too-small",
            region_id="name",
            edge_policy="include",
            gap_radius_m=5,
            max_fields=1,
        )


def test_overlap_coverage_and_censored_gaps(tmp_path):
    _, dataset = make_dataset(tmp_path, duplicate=True)
    regions = tmp_path / "regions.gpkg"
    gpd.GeoDataFrame({"id": ["all"]}, geometry=[box(0, 0, 20, 10)], crs=32632).to_file(
        regions
    )
    result = summarize_regions(
        dataset,
        regions,
        tmp_path / "summary",
        region_id="id",
        edge_policy="include",
        gap_radius_m=0.1,
    ).iloc[0]
    assert result.overlapping_polygon_pairs == 1
    assert result.overlap_excess_area_m2 == 4
    assert result.mapped_union_area_m2 == 20
    assert result.positive_gap_censored_count == 4
    assert np.isnan(result.mean_observed_positive_gap_m)


def test_unknown_footprint_and_ambiguous_region_rejected(tmp_path):
    _, dataset = make_dataset(tmp_path, footprint=False)
    regions = tmp_path / "regions.gpkg"
    gpd.GeoDataFrame({"id": ["all"]}, geometry=[box(0, 0, 20, 10)], crs=32632).to_file(
        regions
    )
    with pytest.raises(ValueError, match="footprints"):
        summarize_regions(
            dataset,
            regions,
            tmp_path / "unknown",
            region_id="id",
            edge_policy="exclude",
            gap_radius_m=5,
        )
    gpd.GeoDataFrame(
        {"id": ["a", "b"]}, geometry=[box(0, 0, 2, 10), box(2, 0, 20, 10)], crs=32632
    ).to_file(regions)
    with pytest.raises(ValueError, match="shared region"):
        summarize_regions(
            dataset,
            regions,
            tmp_path / "ambiguous",
            region_id="id",
            edge_policy="include",
            gap_radius_m=5,
        )


def test_stable_pairwise_moments():
    x = 1e10 + np.arange(100, dtype=float)
    y = 3 * np.arange(100, dtype=float)
    y[4] = np.nan
    moments = PairMoments()
    for offset in range(0, 100, 7):
        moments.add(x[offset : offset + 7], y[offset : offset + 7])
    assert moments.n == 99
    assert moments.correlation() == pytest.approx(1, abs=1e-8)


def test_correlations_sampling_strata_bootstrap_and_pca(tmp_path):
    values = np.arange(1, 61, dtype=float)
    frame = pd.DataFrame(
        {
            "group": ["a"] * 30 + ["b"] * 30,
            "area_m2": values * 100,
            "x": values,
            "y": values**2,
            "constant": np.ones(60),
            "centroid_x": (values % 10) * 1000,
            "centroid_y": (values // 10) * 1000,
        }
    )
    frame.loc[0, "y"] = np.nan
    path = tmp_path / "table.parquet"
    frame.to_parquet(path)
    arguments = {
        "features": ["x", "y", "constant"],
        "group_column": "group",
        "sample_size": 20,
        "block_size_m": 1000,
        "bootstrap_replicates": 8,
        "seed": 9,
        "pca_features": ["x", "y"],
        "metric_crs": "EPSG:32632",
    }
    result = correlate_tables([path], tmp_path / "analysis", **arguments)
    pooled = result[
        (result.scope == "pooled")
        & (result.stratum == "all")
        & (result["first"] == "x")
        & (result["second"] == "y")
    ].iloc[0]
    assert pooled.population_pair_n == 59
    assert pooled.sample_pair_n <= 20
    assert pooled.pearson_full == pytest.approx(frame.x.corr(frame.y))
    assert pooled.spearman_sample == pytest.approx(1)
    assert pooled.spatial_blocks >= 3
    assert pooled.pearson_bootstrap_valid > 0
    assert set(result.scope) == {"pooled", "within-group"}
    assert result.stratum.nunique() > 1
    availability = pd.read_csv(tmp_path / "analysis/availability.csv")
    assert availability.loc[
        availability.feature == "constant", "population_constant"
    ].all()
    assert not pd.read_csv(tmp_path / "analysis/pca_loadings.csv").empty
    second = correlate_tables([path], tmp_path / "again", **arguments)
    pd.testing.assert_frame_equal(result, second)


def test_correlation_guards_and_log_transform(tmp_path):
    path = tmp_path / "table.parquet"
    pd.DataFrame(
        {
            "group": ["a"] * 4,
            "x": [1, 2, 3, 4],
            "y": [1, 4, 9, 16],
            "centroid_x": [0, 1, 2, 3],
            "centroid_y": [0] * 4,
        }
    ).to_parquet(path)
    base = {
        "group_column": "group",
        "block_size_m": 1,
        "metric_crs": "EPSG:32632",
        "level": "area",
        "bootstrap_replicates": 0,
    }
    with pytest.raises(ValueError, match="Raw angles"):
        correlate_tables(
            [path], tmp_path / "bad-angle", features=["x", "orientation_deg"], **base
        )
    with pytest.raises(ValueError, match="PCA features must be distinct"):
        correlate_tables(
            [path],
            tmp_path / "bad-pca",
            features=["x", "y"],
            pca_features=["x", "x"],
            **base,
        )
    result = correlate_tables(
        [path], tmp_path / "logs", features=["x", "y"], log_features=["y"], **base
    )
    expected = np.corrcoef([1, 2, 3, 4], np.log1p([1, 4, 9, 16]))[0, 1]
    assert result.pearson_full.iloc[0] == pytest.approx(expected)


def test_command_line_entry_points(tmp_path):
    import subprocess
    import sys

    for module in (
        "scripts.geometry.describe_field_dataset",
        "scripts.geometry.analyze_field_descriptors",
    ):
        result = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_cli_dataset_region_and_area_analysis(tmp_path, monkeypatch):
    from scripts.geometry.analyze_field_descriptors import main as analyze_main
    from scripts.geometry.describe_field_dataset import main as describe_main

    config, dataset = make_dataset(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["describe", str(config), "--out_dir", str(dataset), "--batch_size", "2"],
    )
    describe_main()  # CLI resume, not another inferred population
    regions = tmp_path / "regions.gpkg"
    gpd.GeoDataFrame(
        {"id": ["a", "b", "c"], "country": ["example"] * 3},
        geometry=[box(0, 0, 7, 10), box(7, 0, 15, 10), box(15, 0, 20, 10)],
        crs=32632,
    ).to_file(regions)
    output = tmp_path / "regional-cli"
    monkeypatch.setattr(
        "sys.argv",
        [
            "analysis",
            "regions",
            str(dataset),
            str(regions),
            "--region_id",
            "id",
            "--edge_policy",
            "include",
            "--gap_radius_m",
            "5",
            "--out_dir",
            str(output),
        ],
    )
    analyze_main()
    summary = pd.read_parquet(output / "regions.parquet")
    assert set(summary.region_country) == {"example"}
    assert summary.polygons_with_holes_fraction.iloc[0] == 0
    associations = tmp_path / "area-cli"
    monkeypatch.setattr(
        "sys.argv",
        [
            "analysis",
            "correlations",
            "--tables",
            str(output / "regions.parquet"),
            "--metric_crs",
            "EPSG:32632",
            "--level",
            "area",
            "--group_column",
            "region_country",
            "--features",
            "field_count",
            "mapped_fraction",
            "--bootstrap_replicates",
            "0",
            "--block_size_m",
            "10",
            "--out_dir",
            str(associations),
        ],
    )
    analyze_main()
    assert (associations / "analysis.json").exists()


def test_known_source_edges_excluded_and_empty_source(tmp_path):
    config, _ = make_dataset(tmp_path)
    fields = gpd.read_parquet(tmp_path / "fields.parquet")
    fields.loc[0, "geometry"] = box(0, 1, 3, 3)
    fields.to_parquet(tmp_path / "fields.parquet")
    dataset = tmp_path / "edge-dataset"
    build_dataset(config, dataset, 2)
    table = pd.concat(descriptor_batches(dataset))
    assert table.loc[table.id == "0", "touches_source_edge"].iloc[0]
    regions = tmp_path / "regions.gpkg"
    gpd.GeoDataFrame({"id": ["all"]}, geometry=[box(0, 0, 20, 10)], crs=32632).to_file(
        regions
    )
    summary = summarize_regions(
        dataset,
        regions,
        tmp_path / "edge-excluded",
        region_id="id",
        edge_policy="exclude",
        gap_radius_m=5,
    )
    assert summary.field_count.iloc[0] == 2
    assert summary.mapped_union_area_m2.iloc[0] == 16
    fields.iloc[:0].to_parquet(tmp_path / "fields.parquet")
    empty = tmp_path / "empty-dataset"
    build_dataset(config, empty, 2)
    assert list(dataset_parts(empty)) == []
    assert json.loads((empty / "complete.json").read_text())["rows"] == 0
