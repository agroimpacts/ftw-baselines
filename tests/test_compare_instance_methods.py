"""Metric area conversion for fixed-preset comparisons."""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from affine import Affine
from rasterio.crs import CRS

from scripts import compare_instance_methods as comparison_module
from scripts.compare_instance_methods import _pixel_area_m2


def test_projected_pixel_area():
    dataset = SimpleNamespace(
        crs=CRS.from_epsg(32631), transform=Affine(2.5, 0, 0, 0, -2.5, 0)
    )
    assert _pixel_area_m2(dataset) == 6.25


def test_geographic_area_is_positive_for_either_row_direction():
    areas = []
    for direction in (-1, 1):
        dataset = SimpleNamespace(
            crs=CRS.from_epsg(4326),
            transform=Affine(0.0001, 0, 4, 0, direction * 0.0001, 51),
            width=10,
            height=10,
        )
        areas.append(_pixel_area_m2(dataset))
    assert 70 < areas[0] < 85
    assert np.isclose(*areas, rtol=0.001)


def test_area_requires_crs():
    with pytest.raises(ValueError, match="known CRS"):
        _pixel_area_m2(SimpleNamespace(crs=None, transform=Affine.identity()))


@pytest.mark.parametrize("mismatch", [None, "fbp_version", "statistics"])
@pytest.mark.parametrize("reference_mode", [None, "dataset-instance-ids"])
@pytest.mark.parametrize("prediction_identity", [None, "preserve-ids"])
def test_selected_cache_verifies_before_writing(
    tmp_path, monkeypatch, mismatch, reference_mode, prediction_identity
):
    summary = {
        "source_run": str(tmp_path / "source"),
        "fbp_version": "0.2.0",
        "method_configurations": {"ftw-2e": {"fast": True}},
    }
    if reference_mode is not None:
        summary["reference_mode"] = reference_mode
    if prediction_identity is not None:
        summary["prediction_identity_mode"] = prediction_identity
    (tmp_path / "summary.json").write_text(json.dumps(summary))
    table = pd.DataFrame(
        [
            {
                "country": "germany",
                "aoi_id": aoi,
                "method": method,
                "labels": None,
                "stat_tp": 2,
                "pq": 0.5,
            }
            for aoi in ("chosen", "untouched")
            for method in ("components-4", "ftw-2e")
        ]
    )
    table.to_parquet(tmp_path / "chips.parquet", index=False)

    def regenerate(run, strategies, *, labels_dir, chip_keys, **kwargs):
        expected = {"reference_mode": reference_mode} if reference_mode else {}
        if prediction_identity is not None:
            expected["prediction_identity"] = prediction_identity
        assert kwargs == expected
        assert chip_keys == {("germany", "chosen")}
        assert strategies == ("ftw-2e",)
        rows = table.loc[table.aoi_id == "chosen"].copy()
        for index, row in rows.iterrows():
            relative = f"labels/{row.method}/germany/chosen.tif"
            path = labels_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test labels")
            rows.loc[index, "labels"] = relative
        result = summary.copy()
        if mismatch == "fbp_version":
            result["fbp_version"] = "other"
        if mismatch == "statistics":
            rows["stat_tp"] = 3
        return rows, result

    monkeypatch.setattr(comparison_module, "_compare", regenerate)
    if mismatch:
        with pytest.raises(ValueError):
            comparison_module.ensure_selected_labels(
                tmp_path, {("germany", "chosen")}, {"components-4", "ftw-2e"}
            )
        pd.testing.assert_frame_equal(
            pd.read_parquet(tmp_path / "chips.parquet"), table
        )
        assert not (tmp_path / "labels").exists()
    else:
        comparison_module.ensure_selected_labels(
            tmp_path, {("germany", "chosen")}, {"components-4", "ftw-2e"}
        )
        cached = pd.read_parquet(tmp_path / "chips.parquet")
        pd.testing.assert_frame_equal(
            cached.drop(columns="labels"), table.drop(columns="labels")
        )
        assert cached.loc[cached.aoi_id == "untouched", "labels"].isna().all()
        assert len(list((tmp_path / "labels").rglob("*.tif"))) == 2


def test_prediction_identity_audit_distinguishes_mask_splits():
    labels = np.array([[7, 7, 7, 0, 9, 0, 9, 0, 10]])
    truth = np.array([[1, 255, 1, 0, 1, 0, 1, 0, 255]])
    audit = comparison_module.prediction_identity_audit(labels, truth)
    assert audit["raw_ids"] == 3
    assert audit["raw_components"] == 4
    assert audit["raw_fragmented_ids"] == 1
    assert audit["masked_ids"] == 2
    assert audit["masked_components"] == 4
    assert audit["masked_fragmented_ids"] == 2
    assert audit["ids_further_split_by_mask"] == 1
    assert audit["ids_removed_by_mask"] == 1
