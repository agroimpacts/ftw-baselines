"""Instance evaluation on aligned categorical chips.

See docs/instance-metrics-contract.md for definitions.
"""

from dataclasses import dataclass, fields

import numpy as np
from scipy.ndimage import label
from scipy.optimize import linear_sum_assignment
from skimage.measure import label as label_values


# Without labeled background, unmatched predictions cannot reliably be called
# false positives. Keep their counts for diagnostics, not FP-based scoring.
FP_DEPENDENT_SCORES = ("object_precision", "object_f1", "rq", "pq")


def instance_scores_for_reporting(stats, *, background_known):
    """Return scores with FP-dependent ratios undefined for unlabeled background."""
    scores = stats.scores()
    if not background_known:
        scores.update({name: float("nan") for name in FP_DEPENDENT_SCORES})
    return scores


@dataclass
class InstanceStatistics:
    """Additive chip statistics; pool before computing regional ratios."""

    tp: float = 0
    fp: float = 0
    fn: float = 0
    matched_iou: float = 0
    intersection_sq: float = 0
    truth_area_sq: float = 0
    prediction_on_truth_sq: float = 0
    truth_cover_sum: float = 0
    truth_area: float = 0
    prediction_cover_sum: float = 0
    prediction_area: float = 0

    def __iadd__(self, other):
        for field in fields(self):
            setattr(
                self, field.name, getattr(self, field.name) + getattr(other, field.name)
            )
        return self

    def scores(self):
        """Undefined ratios are NaN; SQ is undefined when no objects match."""

        def ratio(numerator, denominator):
            return numerator / denominator if denominator else float("nan")

        precision = ratio(self.tp, self.tp + self.fp)
        recall = ratio(self.tp, self.tp + self.fn)
        rq = ratio(2 * self.tp, 2 * self.tp + self.fp + self.fn)
        sq = ratio(self.matched_iou, self.tp)
        split = ratio(self.intersection_sq, self.truth_area_sq)
        merge = ratio(self.intersection_sq, self.prediction_on_truth_sq)
        recovery = ratio(self.truth_cover_sum, self.truth_area)
        support = ratio(self.prediction_cover_sum, self.prediction_area)
        return {
            "object_precision": precision,
            "object_recall": recall,
            "object_f1": rq,
            "rq": rq,
            "sq": sq,
            "pq": rq * sq
            if self.tp
            else (0.0 if self.tp + self.fp + self.fn else float("nan")),
            "rand_split_score": split,
            "rand_merge_score": merge
            if self.prediction_on_truth_sq
            else (0.0 if self.truth_area_sq else float("nan")),
            "recovery": recovery,
            "support": support,
        }


def instance_statistics(
    y_true,
    y_pred,
    iou_threshold=0.5,
    prediction_connectivity=4,
    ignore_index=None,
    reference_connectivity=4,
):
    """Score class-1 components on reference-valid pixels (areas in pixels).

    Both masks default to 4-connectivity for historical object-count parity.
    Matching maximizes cardinality first, then IoU, with strict IoU > threshold.
    No geospatial CRS is required.
    """
    if not 0 <= iou_threshold <= 1:
        raise ValueError("iou_threshold must be between 0 and 1")
    gt, predicted, ng, npred = _semantic_instance_labels(
        y_true, y_pred, prediction_connectivity, ignore_index, reference_connectivity
    )
    return _statistics_from_labels(gt, predicted, ng, npred, iou_threshold)


def instance_match_labels(
    y_true,
    y_pred,
    iou_threshold=0.5,
    prediction_connectivity=4,
    ignore_index=None,
    reference_connectivity=4,
):
    """Return reference/prediction ID rasters, matched IDs and chip statistics.

    Matched IDs are positive, one-based component labels on each respective raster.
    Unmatched predictions are FP and unmatched references are FN.
    """
    if not 0 <= iou_threshold <= 1:
        raise ValueError("iou_threshold must be between 0 and 1")
    gt, predicted, ng, npred = _semantic_instance_labels(
        y_true, y_pred, prediction_connectivity, ignore_index, reference_connectivity
    )
    stats, gt_matches, pred_matches = _statistics_from_labels(
        gt, predicted, ng, npred, iou_threshold, return_matches=True
    )
    return gt, predicted, gt_matches, pred_matches, stats


def _semantic_instance_labels(
    y_true, y_pred, prediction_connectivity, ignore_index, reference_connectivity
):
    truth, pred = np.asarray(y_true), np.asarray(y_pred)
    if truth.ndim != 2 or truth.shape != pred.shape:
        raise ValueError("truth and prediction must be aligned 2D arrays")
    if prediction_connectivity not in (4, 8):
        raise ValueError("prediction_connectivity must be 4 or 8")
    if reference_connectivity not in (4, 8):
        raise ValueError("reference_connectivity must be 4 or 8")
    valid = np.isin(truth, (0, 1, 2))
    if ignore_index is not None:
        valid &= truth != ignore_index
    square = np.ones((3, 3), dtype=int)
    gt, ng = label(
        (truth == 1) & valid, structure=square if reference_connectivity == 8 else None
    )
    predicted, npred = label(
        (pred == 1) & valid, structure=square if prediction_connectivity == 8 else None
    )
    return gt, predicted, ng, npred


def instance_label_statistics(
    y_true, labels, iou_threshold=0.5, ignore_index=None, reference_connectivity=4
):
    """Score integer instance IDs against class-1 references on valid pixels.

    Disconnected pieces and pieces divided by ignored pixels count separately.
    """
    return instance_label_matches(
        y_true, labels, iou_threshold, ignore_index, reference_connectivity
    )[-1]


def instance_label_matches(
    y_true, labels, iou_threshold=0.5, ignore_index=None, reference_connectivity=4
):
    """Return valid-domain reference/instance IDs, matched IDs and statistics."""
    truth, predicted = np.asarray(y_true), np.asarray(labels)
    if truth.ndim != 2 or truth.shape != predicted.shape:
        raise ValueError("truth and labels must be aligned 2D arrays")
    if predicted.dtype.kind not in "iu" or np.any(predicted < 0):
        raise ValueError("instance labels must be nonnegative integers")
    if not 0 <= iou_threshold <= 1:
        raise ValueError("iou_threshold must be between 0 and 1")
    if reference_connectivity not in (4, 8):
        raise ValueError("reference_connectivity must be 4 or 8")
    valid = np.isin(truth, (0, 1, 2))
    if ignore_index is not None:
        valid &= truth != ignore_index
    gt, ng = label(
        (truth == 1) & valid,
        structure=(np.ones((3, 3), dtype=int) if reference_connectivity == 8 else None),
    )
    pred = label_values(np.where(valid, predicted, 0), connectivity=1, background=0)
    stats, gt_matches, pred_matches = _statistics_from_labels(
        gt, pred, ng, int(pred.max()), iou_threshold, return_matches=True
    )
    return gt, pred, gt_matches, pred_matches, stats


def _statistics_from_labels(
    gt, predicted, ng, npred, iou_threshold, *, return_matches=False
):
    """Compute the common additive statistics from positive instance IDs."""
    gt_area = np.bincount(gt.ravel(), minlength=ng + 1)[1:].astype(float)
    pd_area = np.bincount(predicted.ravel(), minlength=npred + 1)[1:].astype(float)
    overlaps = (
        np.bincount(
            (predicted * (ng + 1) + gt).ravel(), minlength=(npred + 1) * (ng + 1)
        )
        .reshape(npred + 1, ng + 1)[1:, 1:]
        .astype(float)
    )
    unions = pd_area[:, None] + gt_area[None, :] - overlaps
    ious = np.divide(overlaps, unions, out=np.zeros_like(overlaps), where=unions > 0)
    stats = InstanceStatistics(
        fp=npred,
        fn=ng,
        intersection_sq=float(np.square(overlaps).sum()),
        truth_area_sq=float(np.square(gt_area).sum()),
        prediction_on_truth_sq=float(np.square(overlaps.sum(axis=1)).sum()),
        truth_cover_sum=(float(np.dot(gt_area, ious.max(axis=0))) if npred else 0.0),
        truth_area=float(gt_area.sum()),
        prediction_cover_sum=(float(np.dot(pd_area, ious.max(axis=1))) if ng else 0.0),
        prediction_area=float(pd_area.sum()),
    )
    gt_matches = np.array([], dtype=int)
    pred_matches = np.array([], dtype=int)
    if npred and ng:
        eligible = ious > iou_threshold
        # Bonus exceeds the total IoU gain from every other pair.
        bonus = min(npred, ng) + 1
        rows, cols = linear_sum_assignment(
            np.where(eligible, bonus + ious, 0.0), maximize=True
        )
        selected = eligible[rows, cols]
        stats.tp = int(selected.sum())
        stats.fp -= stats.tp
        stats.fn -= stats.tp
        stats.matched_iou = float(ious[rows[selected], cols[selected]].sum())
        gt_matches = cols[selected] + 1
        pred_matches = rows[selected] + 1
    if return_matches:
        return stats, gt_matches, pred_matches
    return stats


def get_object_level_metrics(y_true, y_pred, iou_threshold=0.5):
    """Return one-to-one TP, FP, FN using the shared instance contract."""
    stats = instance_statistics(y_true, y_pred, iou_threshold=iou_threshold)
    return int(stats.tp), int(stats.fp), int(stats.fn)
