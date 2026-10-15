"""Pixel evaluation modes calculated from one pair of semantic chip masks."""

import math

import numpy as np


def confusion(truth, prediction, classes, valid):
    """Count reference rows and prediction columns on valid reference pixels."""
    if truth.shape != prediction.shape or truth.shape != valid.shape:
        raise ValueError("Pixel masks and valid domain must share a grid")
    if not np.isin(truth[valid], range(classes)).all():
        raise ValueError("Unexpected reference class on valid pixels")
    if not np.isin(prediction[valid], range(classes)).all():
        raise ValueError("Unexpected prediction class on valid pixels")
    counts = np.bincount(
        truth[valid].astype(np.int64) * classes
        + prediction[valid].astype(np.int64),
        minlength=classes * classes,
    )
    return counts.reshape(classes, classes)


def pixel_confusions(truth, raw, *, three_class, ignore_index=None):
    """Return independent three-class, binary-interior and legacy matrices.

    Three-class and legacy modes require three-class references and model
    outputs. Two-class experiments have only the symmetric binary mode.
    """
    truth = np.asarray(truth)
    raw = np.asarray(raw)
    if truth.ndim != 2 or raw.shape != truth.shape:
        raise ValueError("Pixel masks must be aligned 2D arrays")
    valid = np.isin(truth, (0, 1, 2))
    if ignore_index is not None:
        valid &= truth != ignore_index
    binary = confusion(truth == 1, raw == 1, 2, valid)
    result = {"binary_interior": binary}
    if three_class:
        result["three_class"] = confusion(truth, raw, 3, valid)
        legacy = np.where(raw == 2, 0, raw)
        result["legacy_asymmetric"] = confusion(truth, legacy, 3, valid)
    return result


def pixel_scores(matrix):
    """Per-class precision, recall and IoU; macro averages finite classes."""
    matrix = np.asarray(matrix)
    if matrix.shape not in ((2, 2), (3, 3)):
        raise ValueError("Expected a 2- or 3-class confusion matrix")

    def ratio(numerator, denominator):
        return (
            float(numerator) / float(denominator) if denominator else math.nan
        )

    scores = {}
    ious = []
    for label in range(len(matrix)):
        tp = matrix[label, label]
        predicted = matrix[:, label].sum()
        reference = matrix[label, :].sum()
        union = predicted + reference - tp
        scores[f"precision_class_{label}"] = ratio(tp, predicted)
        scores[f"recall_class_{label}"] = ratio(tp, reference)
        iou = ratio(tp, union)
        scores[f"iou_class_{label}"] = iou
        ious.append(iou)
    finite = [iou for iou in ious if math.isfinite(iou)]
    scores["macro_iou"] = float(np.mean(finite)) if finite else math.nan
    return scores
