"""Controlled checks for the offline boundary diagnostics."""

import numpy as np
import pytest

from research.instance_metrics.boundary_chamfer import (
    boundary_chamfer,
    chamfer_statistics,
)


def test_optimized_statistics_match_full_grid_distance():
    from ftw_tools.training.metrics import instance_match_labels

    rng = np.random.default_rng(91)
    for _ in range(15):
        a = (rng.random((24, 24)) > 0.35).astype(np.uint8)
        b = (rng.random((24, 24)) > 0.35).astype(np.uint8)
        gt, pred, gi, pi, _ = instance_match_labels(a, b)
        result = chamfer_statistics(a, b, pixel_size_m=(8, 10))
        values = [
            boundary_chamfer(gt == g, pred == p, pixel_size_m=(8, 10))
            for g, p in zip(gi, pi)
        ]
        expected = np.mean(values) if values else np.nan
        assert result["threshold_chamfer_m"] == pytest.approx(expected, nan_ok=True)


def test_best_pairing_reuses_prediction_and_matches_full_grid():
    a = np.zeros((24, 24), dtype=np.uint8)
    a[:8, :8] = 1
    a[12:20, :8] = 1
    b = a.copy()
    b[7:13, 2:5] = 1
    result = chamfer_statistics(a, b, pixel_size_m=(8, 10))
    first = a.copy()
    first[12:20, :8] = 0
    second = a.copy()
    second[:8, :8] = 0
    expected = (
        boundary_chamfer(first, b, pixel_size_m=(8, 10))
        + boundary_chamfer(second, b, pixel_size_m=(8, 10))
    ) / 2
    assert result["best_iou_reference_count"] == 2
    assert result["best_iou_chamfer_m"] == pytest.approx(expected)


def test_no_objects_and_no_predictions():
    empty = np.zeros((12, 12), dtype=np.uint8)
    result = chamfer_statistics(empty, empty, pixel_size_m=10)
    assert np.isnan(result["best_iou_reference_coverage"])
    assert np.isnan(result["best_iou_chamfer_m"])
    truth = empty.copy()
    truth[2:6, 2:6] = 1
    result = chamfer_statistics(truth, empty, pixel_size_m=10)
    assert result["best_iou_reference_coverage"] == 0
    assert result["best_iou_chamfer_m_count"] == 0


def test_identical_and_empty():
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[3:12, 4:13] = 1
    assert boundary_chamfer(mask, mask, pixel_size_m=10) == 0
    assert np.isnan(boundary_chamfer(mask, mask * 0, pixel_size_m=10))


def test_offset_symmetry_and_units():
    a = np.zeros((20, 20), dtype=np.uint8)
    a[3:12, 4:13] = 1
    b = np.roll(a, 2, axis=1)
    distance = boundary_chamfer(a, b, pixel_size_m=1)
    assert distance > 0
    assert boundary_chamfer(b, a, pixel_size_m=10) == pytest.approx(10 * distance)


def test_low_overlap_and_missing_reference():
    truth = np.zeros((30, 30), dtype=np.uint8)
    truth[3:10, 3:10] = 1
    truth[20:25, 20:25] = 1
    prediction = np.zeros_like(truth)
    prediction[3:10, 8:15] = 1
    result = chamfer_statistics(truth, prediction, pixel_size_m=10)
    assert np.isnan(result["threshold_chamfer_m"])
    assert result["best_iou_chamfer_m"] > 0
    assert result["best_iou_reference_coverage"] == 0.5


def test_supplied_ids_preserve_disconnected_reference():
    truth = np.zeros((30, 30), dtype=np.uint8)
    truth[3:10, 3:10] = 1
    truth[20:25, 20:25] = 1
    supplied = truth.astype(np.int32) * 12
    semantic = chamfer_statistics(truth, truth, pixel_size_m=10)
    instance = chamfer_statistics(
        truth, truth, pixel_size_m=10, reference_labels=supplied
    )
    assert semantic["reference_count"] == 2
    assert instance["reference_count"] == 1
    assert semantic["best_iou_chamfer_m"] == 0
    assert instance["best_iou_chamfer_m"] > 0


def test_holes_affect_distance():
    a = np.zeros((30, 30), dtype=np.uint8)
    a[3:27, 3:27] = 1
    b = a.copy()
    b[10:20, 10:20] = 0
    assert boundary_chamfer(a, b, pixel_size_m=1) > 0


@pytest.mark.parametrize("scale", [0, -1, np.nan, np.inf])
def test_invalid_scale(scale):
    with pytest.raises(ValueError):
        boundary_chamfer(np.ones((3, 3)), np.ones((3, 3)), pixel_size_m=scale)
