"""Inspect component sizes, best IoUs and original-helper counts for saved chips.

Usage: python -m scripts.instance_evaluation.audit_instance_chip RUN_DIR COUNTRY/AOI_ID
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import rasterio.features
from shapely.geometry import shape

from ftw_tools.settings import has_labeled_background
from ftw_tools.training.metrics import instance_match_labels


def original_counts(truth, prediction, threshold):
    """Reproduce the original unmasked Rasterio polygon first-match helper."""
    references = [
        shape(geometry)
        for geometry, value in rasterio.features.shapes(truth)
        if value == 1
    ]
    predictions = [
        shape(geometry)
        for geometry, value in rasterio.features.shapes(prediction)
        if value == 1
    ]
    used = set()
    tp = 0
    for reference in references:
        for index, prediction in enumerate(predictions):
            if reference.intersects(prediction):
                iou = (
                    reference.intersection(prediction).area
                    / reference.union(prediction).area
                )
                if iou > threshold:
                    used.add(index)
                    tp += 1
                    break
    return tp, len(predictions) - len(used), len(references) - tp


def audit(truth, prediction, *, threshold=0.5, ignore_index=None):
    """Return a read-only diagnostic; size filters never change official scores."""
    gt, pred, matched_gt, matched_pred, stats = instance_match_labels(
        truth, prediction, iou_threshold=threshold, ignore_index=ignore_index
    )
    gt_area = np.bincount(gt.ravel())[1:]
    pred_area = np.bincount(pred.ravel())[1:]
    overlaps = np.bincount(
        (pred * (len(gt_area) + 1) + gt).ravel(),
        minlength=(len(pred_area) + 1) * (len(gt_area) + 1),
    ).reshape(len(pred_area) + 1, len(gt_area) + 1)[1:, 1:]
    unions = pred_area[:, None] + gt_area[None, :] - overlaps
    ious = np.divide(
        overlaps, unions, out=np.zeros_like(unions, dtype=float), where=unions > 0
    )
    valid = np.isin(truth, (0, 1, 2))
    if ignore_index is not None:
        valid &= truth != ignore_index

    def objects(areas, best, matched):
        return [
            {
                "id": index,
                "pixels": int(area),
                "best_iou": float(best[index - 1]),
                "matched": index in matched,
            }
            for index, area in enumerate(areas, start=1)
        ]

    references = objects(
        gt_area,
        ious.max(axis=0) if len(pred_area) else np.zeros(len(gt_area)),
        matched_gt,
    )
    predictions = objects(
        pred_area,
        ious.max(axis=1) if len(gt_area) else np.zeros(len(pred_area)),
        matched_pred,
    )
    return {
        "current_counts": [int(stats.tp), int(stats.fp), int(stats.fn)],
        "original_raw_counts": list(original_counts(truth, prediction, threshold)),
        "prediction_pixels_on_ignored_reference": int(
            np.count_nonzero((prediction == 1) & ~valid)
        ),
        "reference_objects": references,
        "prediction_objects": predictions,
        "reference_unmatched_at_most_1_2_4_10_pixels": {
            str(size): sum(
                not obj["matched"] and obj["pixels"] <= size for obj in references
            )
            for size in (1, 2, 4, 10)
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("chip", help="COUNTRY/AOI_ID")
    args = parser.parse_args()
    country, chip = args.chip.split("/", 1)
    run = args.run_dir.expanduser()
    table = pd.read_parquet(run / "chips.parquet")
    rows = table.loc[(table.country == country) & (table.aoi_id == chip)]
    if len(rows) != 1:
        raise ValueError(f"Expected one chip for {args.chip}; found {len(rows)}")
    row = rows.iloc[0]
    with rasterio.open(row.reference) as source:
        truth = source.read(1)
    with rasterio.open(run / row.prediction) as source:
        prediction = source.read(1)
    settings = json.loads((run / "manifest.json").read_text())["settings"]
    if (
        settings.get("reference_connectivity", 4) != 4
        or settings.get("prediction_connectivity", 4) != 4
    ):
        raise ValueError("Audit currently supports only 4-connected baseline runs")
    result = audit(
        truth,
        prediction,
        threshold=settings.get("iou_threshold", 0.5),
        ignore_index=settings.get("ignore_index"),
    )
    result["chip"] = args.chip
    result["fp_evaluable"] = has_labeled_background(country)
    if result["current_counts"] != [
        int(row.stat_tp),
        int(row.stat_fp),
        int(row.stat_fn),
    ]:
        raise ValueError("Recomputed counts differ from saved statistics")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
