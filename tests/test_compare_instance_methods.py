import json

import numpy as np
import rasterio
from rasterio.transform import from_origin

from scripts.compare_instance_methods import compare
from ftw_tools.training.eval_artifacts import EvaluationArtifacts
from ftw_tools.training.metrics import instance_statistics


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
        {"mask": str(mask), "window_a": "a", "window_b": "b"},
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
