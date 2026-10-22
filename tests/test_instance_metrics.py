import math

import numpy as np
import pytest
import rasterio.features
import shapely.geometry

from ftw_tools.training.metrics import (
    InstanceStatistics,
    instance_label_statistics,
    instance_statistics,
)


def test_diagonal_contact_and_connectivity():
    mask = np.array([[1, 0], [0, 1]])
    assert instance_statistics(mask, mask).tp == 2
    stats = instance_statistics(
        mask, mask, reference_connectivity=8, prediction_connectivity=4
    )
    assert (stats.tp, stats.fp, stats.fn) == (0, 2, 1)
    assert stats.scores()["recovery"] == pytest.approx(0.5)


def _legacy_object_counts(truth, pred, threshold=0.5):
    """Independent oracle for the former Rasterio first-match helper."""

    def polygons(mask):
        return [
            shapely.geometry.shape(geometry)
            for geometry, value in rasterio.features.shapes(mask.astype(np.uint8))
            if value == 1
        ]

    references, predictions = polygons(truth), polygons(pred)
    matched = set()
    tp = 0
    for reference in references:
        for j, prediction in enumerate(predictions):
            intersection = reference.intersection(prediction).area
            union = reference.union(prediction).area
            if intersection / union > threshold:
                tp += 1
                matched.add(j)
                break
    return tp, len(predictions) - len(matched), len(references) - tp


@pytest.mark.parametrize(
    ("truth", "pred"),
    [
        ([[1, 0], [0, 1]], [[1, 0], [0, 1]]),
        ([[1, 1, 1]], [[1, 1, 0]]),
        ([[1, 1, 1, 0, 1, 1]], [[1, 0, 1, 0, 1, 1]]),
        ([[1, 1, 0, 1, 1]], [[1, 1, 1, 1, 1]]),
        ([[0, 0]], [[0, 0]]),
    ],
)
def test_default_counts_match_original_helper(truth, pred):
    truth, pred = np.array(truth), np.array(pred)
    stats = instance_statistics(truth, pred)
    assert (stats.tp, stats.fp, stats.fn) == _legacy_object_counts(truth, pred)


def test_threshold_is_strict_and_partial_overlap():
    truth = np.array([[1, 1, 1]])
    pred = np.array([[1, 1, 0]])
    assert instance_statistics(truth, pred, iou_threshold=2 / 3).tp == 0
    stats = instance_statistics(truth, pred, iou_threshold=0.5)
    assert stats.tp == 1
    assert stats.scores()["sq"] == pytest.approx(2 / 3)
    assert stats.scores()["pq"] == pytest.approx(2 / 3)
    assert instance_statistics(truth, pred, iou_threshold=0.8).scores()["pq"] == 0


def test_ignored_pixels_are_removed_from_both_sides():
    truth = np.array([[1, 3, 1, 255, 0]])
    pred = np.array([[1, 1, 1, 1, 1]])
    stats = instance_statistics(truth, pred)
    assert (stats.tp, stats.fp, stats.fn) == (2, 1, 0)
    assert stats.prediction_area == 3
    assert (
        instance_statistics(
            np.array([[1, 2]]), np.array([[1, 1]]), ignore_index=2
        ).scores()["sq"]
        == 1
    )


def test_split_merge_and_unsupported_area():
    truth = np.array([[1, 1, 1, 0, 1, 1, 1]])
    split = np.array([[1, 0, 1, 0, 1, 1, 1]])
    stats = instance_statistics(truth, split)
    assert stats.scores()["rand_split_score"] < 1
    assert stats.scores()["rand_merge_score"] == 1
    merged = instance_statistics(truth, np.ones_like(truth))
    assert merged.scores()["rand_merge_score"] < 1
    assert merged.scores()["rand_split_score"] == 1
    unsupported = instance_statistics(np.array([[1, 0, 0]]), np.array([[1, 1, 1]]))
    assert unsupported.scores()["support"] == pytest.approx(1 / 3)


def test_empty_and_pooled_chips():
    empty = instance_statistics(np.zeros((2, 2)), np.zeros((2, 2)))
    assert math.isnan(empty.scores()["object_f1"])
    assert math.isnan(empty.scores()["pq"])
    missed = instance_statistics(np.array([[1]]), np.array([[0]]))
    assert math.isnan(missed.scores()["object_precision"])
    assert missed.scores()["object_recall"] == 0
    pooled = InstanceStatistics()
    pooled += empty
    pooled += missed
    pooled += instance_statistics(np.ones((2, 2)), np.ones((2, 2)))
    assert pooled.scores()["object_recall"] == 0.5
    assert pooled.scores()["recovery"] == pytest.approx(4 / 5)


def test_integer_labels_preserve_adjacent_instances_and_ignore_seams():
    truth = np.array([[1, 1, 3, 1, 1], [1, 1, 3, 1, 1]])
    predicted = np.array([[7, 7, 7, 9, 9], [7, 7, 7, 9, 9]])
    stats = instance_label_statistics(truth, predicted)
    assert (stats.tp, stats.fp, stats.fn) == (2, 0, 0)
    assert stats.scores()["pq"] == 1
    split = np.array([[7, 9, 0, 7, 9], [7, 9, 0, 7, 9]])
    assert instance_label_statistics(truth, split).fp == 4
    with pytest.raises(ValueError, match="nonnegative integers"):
        instance_label_statistics(truth, predicted.astype(float))
