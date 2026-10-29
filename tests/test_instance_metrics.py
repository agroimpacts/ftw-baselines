import math

import numpy as np
import pytest
import rasterio.features
import shapely.geometry

from ftw_tools.settings import (
    ALL_COUNTRIES,
    FULL_DATA_COUNTRIES,
    has_labeled_background,
)
from ftw_tools.training.metrics import (
    InstanceStatistics,
    instance_label_statistics,
    instance_match_labels,
    instance_statistics,
    instance_scores_for_reporting,
)
from ftw_tools.training.pixel_evaluation import pixel_confusions, pixel_scores
from scripts.audit_instance_chip import audit


def test_diagonal_contact_and_connectivity():
    mask = np.array([[1, 0], [0, 1]])
    assert instance_statistics(mask, mask).tp == 2
    stats = instance_statistics(
        mask, mask, reference_connectivity=8, prediction_connectivity=4
    )
    assert (stats.tp, stats.fp, stats.fn) == (0, 2, 1)
    assert stats.scores()["recovery"] == pytest.approx(0.5)


def test_background_coverage_comes_from_dataset_policy_not_chip_pixels():
    assert {
        country for country in ALL_COUNTRIES if not has_labeled_background(country)
    } == {"brazil", "india", "kenya", "rwanda"}
    assert all(has_labeled_background(country) for country in FULL_DATA_COUNTRIES)
    assert has_labeled_background("germany")  # even if a chip has no class-0 pixels


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


def test_match_labels_agree_with_statistics_for_split_and_ignored_pixels():
    truth = np.array([[1, 1, 1, 1, 1, 3, 1]])
    pred = np.array([[1, 1, 0, 1, 1, 1, 1]])
    gt, predicted, matched_gt, matched_pred, stats = instance_match_labels(
        truth, pred, iou_threshold=0.3
    )
    assert stats == instance_statistics(truth, pred, iou_threshold=0.3)
    assert (stats.tp, stats.fp, stats.fn) == (2, 1, 0)
    assert len(matched_gt) == len(matched_pred) == 2
    assert gt[0, 5] == predicted[0, 5] == 0
    assert predicted[0, 3] not in matched_pred


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


def test_pixel_iou_can_be_perfect_despite_instance_split_or_merge():
    mask = np.array([[1, 0], [0, 1]])
    pixel_iou = pixel_scores(
        pixel_confusions(mask, mask, three_class=False)["binary_interior"]
    )["iou_class_1"]
    assert pixel_iou == 1
    split = instance_statistics(mask, mask, reference_connectivity=8)
    merged = instance_statistics(mask, mask, prediction_connectivity=8)
    assert split.scores()["recovery"] == pytest.approx(0.5)
    assert merged.scores()["recovery"] == pytest.approx(0.5)


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


def test_tiny_reference_fragments_match_legacy_counts():
    truth = np.zeros((5, 9), dtype=np.uint8)
    truth[0, :3] = 1
    truth[2, 1] = truth[4, 2] = 1
    pred = np.zeros_like(truth)
    pred[0, :3] = 1
    stats = instance_statistics(truth, pred)
    assert (stats.tp, stats.fp, stats.fn) == (1, 0, 2)
    assert (stats.tp, stats.fp, stats.fn) == _legacy_object_counts(truth, pred)


def test_ignored_background_and_below_threshold_overlap_are_distinct():
    truth = np.array([[3, 3, 0, 1, 1, 1, 1, 1, 1]], dtype=np.uint8)
    pred = np.array([[1, 1, 0, 1, 1, 0, 0, 0, 0]], dtype=np.uint8)
    gt, labels, matched_gt, matched_pred, stats = instance_match_labels(truth, pred)
    assert (stats.tp, stats.fp, stats.fn) == (0, 1, 1)
    assert not len(matched_gt) and not len(matched_pred)
    assert labels[0, :2].sum() == 0
    assert np.count_nonzero(labels) == 2
    assert np.count_nonzero(gt) == 6
    # Original unmasked helper counts the prediction in ignored territory.
    assert _legacy_object_counts(truth, pred) == (0, 2, 1)
    assert stats.scores()["object_precision"] == 0
    presence_only = instance_scores_for_reporting(stats, background_known=False)
    for name in ("object_precision", "object_f1", "rq", "pq"):
        assert math.isnan(presence_only[name])
    assert presence_only["object_recall"] == 0
    assert (
        instance_scores_for_reporting(stats, background_known=True)["object_precision"]
        == 0
    )
    details = audit(truth, pred)
    assert details["current_counts"] == [0, 1, 1]
    assert details["original_raw_counts"] == [0, 2, 1]
    assert details["prediction_pixels_on_ignored_reference"] == 2
    assert details["reference_objects"][0]["best_iou"] == pytest.approx(1 / 3)
    assert details["reference_unmatched_at_most_1_2_4_10_pixels"]["10"] == 1
