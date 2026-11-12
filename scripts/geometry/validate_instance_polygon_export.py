"""Validate fixed-preset vector exports against a saved instance-label chip.

Run with INPUT_PROBABILITIES SAVED_LABELS --out_dir NEW_DIRECTORY. Inputs are
read-only; exports and a machine-readable validation summary go in NEW_DIRECTORY.
This checks geometry/export fidelity, not reference-dependent model accuracy.
"""

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize

from ftw_tools.postprocess.descriptors import describe_polygons, metric_geometry_crs
from ftw_tools.postprocess.instance_polygonize import labels_to_polygons, polygonize_fbp


def validate(probabilities, saved_labels, out_dir):
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with rasterio.open(probabilities) as source, rasterio.open(saved_labels) as saved:
        assert (source.shape, source.transform, source.crs) == (
            saved.shape,
            saved.transform,
            saved.crs,
        ), "Saved-label grid differs"
        labels = saved.read(1)
        affine, crs = source.transform, source.crs
    baseline = labels_to_polygons(labels, affine, crs)
    metric_crs = metric_geometry_crs(baseline)
    baseline_by_id = baseline.set_index("id")
    seams = {}
    for stride in (31, 64, 127, 2048):
        tiled = labels_to_polygons(labels, affine, crs, stride).set_index("id")
        assert set(tiled.index) == set(baseline_by_id.index)
        assert all(
            tiled.loc[field_id].geometry.equals(row.geometry)
            for field_id, row in baseline_by_id.iterrows()
        )
        reconstructed = rasterize(
            zip(tiled.geometry, tiled.instance_id),
            out_shape=labels.shape,
            transform=affine,
            dtype="int32",
        )
        mismatch = int(np.count_nonzero(reconstructed != labels))
        assert mismatch == 0
        seams[str(stride)] = {"raster_mismatches": mismatch, "geometry_equal": True}
    exports = {}
    for suffix in ("parquet", "geojson", "gpkg", "fgb"):
        target = out_dir / f"fields.{suffix}"
        polygonize_fbp(probabilities, target, stride=31, simplify=0, min_size=0)
        written = (
            gpd.read_parquet(target) if suffix == "parquet" else gpd.read_file(target)
        )
        assert written.geometry.is_valid.all() and written.geom_type.eq("Polygon").all()
        assert set(written.id) == set(baseline.id), (
            "Recomputed FBP IDs differ from saved assessment"
        )
        source_frame = written.to_crs(crs)
        instance_ids = source_frame.id.str.split(":").str[0].astype(int)
        reconstructed = rasterize(
            zip(source_frame.geometry, instance_ids),
            out_shape=labels.shape,
            transform=affine,
            dtype="int32",
        )
        mismatch = int(np.count_nonzero(reconstructed != labels))
        assert mismatch == 0, "Export raster round-trip differs"
        expected = describe_polygons(written, metric_crs).set_index("id").sort_index()
        actual = (
            pd.read_csv(str(target) + ".descriptors.csv").set_index("id").sort_index()
        )
        np.testing.assert_allclose(
            actual.to_numpy(dtype=float),
            expected.to_numpy(dtype=float),
            rtol=1e-12,
            atol=1e-8,
        )
        metrics = written.set_index("id").sort_index()
        # fiboa geometry-metrics schema stores these attributes as float32.
        np.testing.assert_allclose(metrics["metrics:area"], expected.area_m2, rtol=1e-7)
        np.testing.assert_allclose(
            metrics["metrics:perimeter"], expected.perimeter_m, rtol=1e-7
        )
        exports[suffix] = {
            "fields": len(written),
            "valid": True,
            "raster_mismatches": mismatch,
            "holes": int(sum(len(g.interiors) for g in written.geometry)),
            "area_m2": float(expected.area_m2.sum()),
            "descriptor_agreement": True,
            "output_crs": written.crs.to_string(),
        }
    cleaned_path = out_dir / "fields_cleaned.parquet"
    polygonize_fbp(probabilities, cleaned_path, simplify=15, min_size=500)
    cleaned = gpd.read_parquet(cleaned_path)
    expected = describe_polygons(cleaned, metric_crs).set_index("id").sort_index()
    actual = (
        pd.read_csv(str(cleaned_path) + ".descriptors.csv").set_index("id").sort_index()
    )
    np.testing.assert_allclose(
        actual.to_numpy(dtype=float),
        expected.to_numpy(dtype=float),
        rtol=1e-12,
        atol=1e-8,
    )
    assert expected.area_m2.ge(500).all()
    summary = {
        "input": str(probabilities),
        "saved_labels": str(saved_labels),
        "source_crs": str(crs),
        "metric_crs": metric_crs.to_string(),
        "instance_ids": sorted(int(value) for value in np.unique(labels) if value),
        "seams": seams,
        "exports": exports,
        "cleaned": {
            "fields": len(cleaned),
            "simplify_m": 15,
            "min_area_m2": 500,
            "descriptor_agreement": True,
        },
        "limitations": [
            "Whole-scene FBP only; vectorization seam checks are not inference seam validation",
            "No cross-chip or global seam ownership assessment",
        ],
    }
    (out_dir / "validation.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probabilities", type=Path)
    parser.add_argument("saved_labels", type=Path)
    parser.add_argument("--out_dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            validate(args.probabilities, args.saved_labels, args.out_dir), indent=2
        )
    )
