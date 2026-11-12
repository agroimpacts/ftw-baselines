import json
from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

pytest.importorskip("sklearn")

from ftw_tools.training.metrics import instance_statistics
from research.instance_metrics.analyze_instances import load_runs
from research.instance_metrics.analyze_metric_complementarity import (
    METRICS,
    dimensionality,
    disagreements,
    matched_pq_examples,
    predictability,
    rescore_baseline,
)


def test_disagreement_and_pca_are_chip_level():
    values = np.linspace(0.02, 0.98, 40)
    frame = pd.DataFrame({name: values for name in METRICS})
    frame["recovery"] = values[::-1]
    frame["country"] = "belgium"
    frame["aoi_id"] = [str(i) for i in range(len(frame))]
    results, examples = disagreements(frame, "belgium")
    contrast = next(r for r in results if r["first"] == "object_recall")
    assert contrast["opposite_extremes"] > 0
    assert len(examples) > 0
    components, loadings = dimensionality(frame, "belgium")
    assert sum(row["variance_ratio"] for row in components) == pytest.approx(1)
    assert all(row["metric"] in METRICS for row in loadings)
    matched = matched_pq_examples(frame.assign(pq=0.5), "belgium")
    assert matched
    assert all(abs(row["pq_a"] - row["pq_b"]) <= 0.02 for row in matched)


def test_prediction_uses_country_holdouts_and_missing_scores():
    rng = np.random.default_rng(17)
    frame = pd.DataFrame(rng.random((100, len(METRICS))), columns=METRICS)
    frame["country"] = np.repeat(list("abcde"), 20)
    frame.loc[0, "sq"] = np.nan
    results = predictability(frame, "all", grouped=True)
    assert len(results) == 2 * len(METRICS)
    assert {r["n"] for r in results} == {99}
    assert {r["cv"] for r in results} == {"held-out-country"}


def test_rescore_keeps_predictions_and_pixel_scores_and_rejects_mixed_modes(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    truth = np.array([[1, 0, 1]], dtype=np.uint8)
    reference = tmp_path / "label_masks/semantic_3class/chip.tif"
    instances = tmp_path / "label_masks/instance/chip.tif"
    prediction = source / "prediction.tif"
    for path, data in (
        (reference, truth),
        (instances, np.array([[7, 0, 7]], dtype=np.uint64)),
        (prediction, truth),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=3,
            height=1,
            count=1,
            dtype=data.dtype,
            crs="EPSG:4326",
            transform=from_origin(4, 51, 0.001, 0.001),
        ) as dst:
            dst.write(data, 1)
    stats = instance_statistics(truth, truth)
    # Avoid NaN in the synthetic metadata; real empty scores are serialized null.
    scores = stats.scores()
    summary = {
        "chip_count": 1,
        "instance_statistics": asdict(stats),
        "instance_scores": scores,
        "pixel_scores": {"unchanged": 0.75},
    }
    manifest = {
        "checkpoint_sha256": "fixed",
        "evaluated_chips": 1,
        "settings": {
            "countries": ["belgium"],
            "split": "test",
            "prediction_connectivity": 4,
            "reference_connectivity": 4,
            "test_on_3_classes": True,
            "iou_threshold": 0.5,
        },
    }
    (source / "manifest.json").write_text(json.dumps(manifest))
    (source / "summary.json").write_text(json.dumps(summary))
    original = pd.DataFrame(
        [
            {
                "country": "belgium",
                "aoi_id": "chip",
                "reference": str(reference),
                "prediction": "prediction.tif",
                "pixel_binary_interior_iou_class_1": 0.75,
                **scores,
                **{f"stat_{k}": v for k, v in asdict(stats).items()},
            }
        ]
    )
    original.to_parquet(source / "chips.parquet", index=False)
    out = tmp_path / "rescored"
    rescore_baseline(source, out)
    updated = pd.read_parquet(out / "chips.parquet")
    assert updated.iloc[0].stat_fn == 1
    assert updated.iloc[0].stat_fp == 2
    assert updated.iloc[0].pixel_binary_interior_iou_class_1 == 0.75
    assert updated.iloc[0].prediction == str(prediction)
    assert not list(out.glob("*.tif"))
    assert (
        json.loads((out / "summary.json").read_text())["pixel_scores"]
        == summary["pixel_scores"]
    )
    pd.testing.assert_frame_equal(pd.read_parquet(source / "chips.parquet"), original)
    assert load_runs([out])[2][0]["reference_mode"] == "dataset-instance-ids"
    with pytest.raises(ValueError, match="Incompatible"):
        load_runs([source, out])
    with rasterio.open(instances, "r+") as dst:
        dst.write(np.zeros_like(truth, dtype=np.uint64), 1)
    with pytest.raises(ValueError, match="foreground"):
        rescore_baseline(source, tmp_path / "strict")
    unavailable = tmp_path / "unavailable"
    rescore_baseline(source, unavailable, allow_unscorable=True)
    failed = pd.read_parquet(unavailable / "chips.parquet").iloc[0]
    assert np.isnan(failed.pq)
    assert np.isnan(failed.stat_tp)
    assert failed.pixel_binary_interior_iou_class_1 == 0.75
    report = json.loads((unavailable / "summary.json").read_text())
    assert report["scored_chips"] == 0
    assert len(report["unscorable_chips"]) == 1


def test_rerun_uses_recorded_cohort_and_shared_populations(tmp_path, monkeypatch):
    from research.instance_metrics import analyze_metric_complementarity as module

    source = tmp_path / "source"
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    inputs = [
        {
            "run_dir": str(source),
            "countries": ["belgium", "denmark"],
            "split": "test",
            "chip_count": 3,
        }
    ]
    (baseline / "inputs.json").write_text(json.dumps({"runs": inputs}))
    frame = pd.DataFrame({name: [0.2, 0.4, 0.6] for name in METRICS})
    frame["country"] = ["belgium", "belgium", "denmark"]
    frame["aoi_id"] = ["a", "b", "c"]
    old, new = frame.copy(), frame.copy()
    old.loc[0, "sq"] = np.nan
    new.loc[1, "sq"] = np.nan

    def load(paths):
        return (old if paths == [source] else new).copy(), list(METRICS), inputs

    calls = []

    def analyze(paths, out, **kwargs):
        out.mkdir(parents=True)
        calls.append((out, kwargs))

    def rescore(run, out, *, allow_unscorable):
        assert run == source
        assert allow_unscorable
        out.mkdir(parents=True)

    monkeypatch.setattr(module, "load_runs", load)
    monkeypatch.setattr(module, "rescore_baseline", rescore)
    monkeypatch.setattr(module, "analyze", analyze)
    out = baseline / "reference-modes/dataset-instance-ids"
    assert module.rerun_reference_analysis(baseline, out) == (1, 3)
    assert len(calls) == 7
    shared = [kwargs["chip_keys"] for _, kwargs in calls if "chip_keys" in kwargs]
    assert shared == [{("denmark", "c")}] * 4
    assert (
        sum(kwargs.get("exclude_countries") == ("denmark",) for _, kwargs in calls) == 4
    )
    populations = json.loads((out / "comparison/populations.json").read_text())
    assert populations["shared_complete_count"] == 1
    assert populations["chip_count"] == 3
