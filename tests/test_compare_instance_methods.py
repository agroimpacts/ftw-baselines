import json

import numpy as np
import rasterio
from rasterio.transform import from_origin

from scripts.compare_instance_methods import _compare, _scores, compare
from scripts.visualize_instance_methods import render, select_method_chips
from ftw_tools.training.eval_artifacts import EvaluationArtifacts
from ftw_tools.training.metrics import instance_statistics


def test_method_scores_require_labeled_background_for_fp_dependent_metrics():
    stats = instance_statistics(np.array([[1, 3]]), np.array([[1, 1]]))
    assert _scores(stats, background_known=False)["object_recall"] == 1
    for key in ("object_precision", "object_f1", "rq", "pq"):
        assert _scores(stats, background_known=False)[key] is None
    assert _scores(stats, background_known=True)["pq"] == 1


def test_comparison_reproduces_baseline_and_keeps_methods_distinct(tmp_path):
    country = tmp_path / "germany"
    mask = country / "label_masks/semantic_3class/one.tif"
    mask.parent.mkdir(parents=True)
    truth = np.array([[1, 0, 3], [0, 1, 2], [0, 2, 1]], dtype=np.uint8)
    profile = dict(
        driver="GTiff",
        width=3,
        height=3,
        count=1,
        dtype="uint8",
        crs="EPSG:32632",
        transform=from_origin(0, 30, 10, 10),
    )
    with rasterio.open(mask, "w", **profile) as output:
        output.write(truth, 1)
    for name in ("a", "b"):
        with rasterio.open(
            tmp_path / f"{name}.tif", "w", **{**profile, "count": 3}
        ) as image:
            image.write(np.ones((3, 3, 3), dtype=np.uint8))
    checkpoint = tmp_path / "model.ckpt"
    checkpoint.write_bytes(b"checkpoint")
    settings = dict(
        countries=["germany"],
        split="val",
        iou_threshold=0.5,
        reference_connectivity=4,
        ignore_index=3,
        remap_boundary=True,
        test_on_3_classes=True,
        model_predicts_3_classes=True,
        save_probabilities=True,
    )
    writer = EvaluationArtifacts(
        tmp_path / "run", checkpoint=checkpoint, dataset=tmp_path, settings=settings
    )
    pred = truth.copy()
    pred[0, 2] = 0
    scores = np.full((3, 3, 3), 0.05, np.float32)
    for k in range(3):
        scores[k, pred == k] = 0.9
    writer.add(
        {
            "mask": str(mask),
            "window_a": str(tmp_path / "a.tif"),
            "window_b": str(tmp_path / "b.tif"),
        },
        pred,
        np.where(pred == 2, 0, pred),
        truth,
        instance_statistics(truth, pred, ignore_index=3),
        scores,
    )
    writer.finish({"pixel_iou": 1.0})
    chips, result = compare(tmp_path / "run", ("arg-none",))
    assert len(chips) == 3
    assert result["chip_count"] == 1
    assert result["methods"]["components-4"]["scores"]["pq"] == 1
    assert result["methods"]["components-8"]["statistics"]["tp"] == 0
    assert result["methods"]["arg-none"]["scores"]["pq"] == 1
    summary = json.loads((tmp_path / "run/summary.json").read_text())
    assert summary["chip_count"] == 1
    saved, _ = _compare(tmp_path / "run", ("arg-none",), labels_dir=tmp_path / "saved")
    assert set(saved["labels"].notna()) == {True}
    for row in saved.itertuples(index=False):
        with rasterio.open(tmp_path / "saved" / row.labels) as labels:
            assert labels.crs == profile["crs"]
            assert labels.transform == profile["transform"]
            assert labels.count == 1
    (tmp_path / "saved/chips.parquet").parent.mkdir(exist_ok=True)
    saved.to_parquet(tmp_path / "saved/chips.parquet", index=False)
    result["source_run"] = str(tmp_path / "run")
    (tmp_path / "saved/summary.json").write_text(json.dumps(result))
    selected = select_method_chips(
        saved, "arg-none", "components-4", ["germany/one"], "pq", 1
    )
    assert selected.delta.iloc[0] == 0
    assert render(tmp_path / "saved", "arg-none", chips=["germany/one"]) == 1
    assert (tmp_path / "saved/figures/arg-none/selected/germany_one.png").exists()
