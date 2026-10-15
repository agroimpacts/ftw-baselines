import math

import numpy as np
import pytest

from ftw_tools.training.pixel_evaluation import pixel_confusions, pixel_scores


def test_three_modes_distinguish_correct_boundaries_and_ignore_pixels():
    truth = np.array([[0, 1, 2, 3, 255]])
    raw = np.array([[0, 1, 2, 1, 1]])
    matrices = pixel_confusions(truth, raw, three_class=True)
    assert matrices["three_class"].tolist() == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert matrices["binary_interior"].tolist() == [[2, 0], [0, 1]]
    assert matrices["legacy_asymmetric"].tolist() == [
        [1, 0, 0],
        [0, 1, 0],
        [1, 0, 0],
    ]
    scores = {mode: pixel_scores(matrix) for mode, matrix in matrices.items()}
    assert {score["iou_class_1"] for score in scores.values()} == {1.0}
    assert scores["three_class"]["iou_class_2"] == 1
    assert scores["three_class"]["macro_iou"] == 1
    assert scores["legacy_asymmetric"]["iou_class_2"] == 0
    assert scores["legacy_asymmetric"]["macro_iou"] == 0.5


def test_pooled_confusions_weight_pixels_not_chip_ratios():
    small = pixel_confusions(np.array([[1]]), np.array([[1]]), three_class=True)
    large = pixel_confusions(
        np.array([[1, 1, 1]]), np.array([[0, 0, 0]]), three_class=True
    )
    for mode in small:
        pooled = pixel_scores(small[mode] + large[mode])
        assert pooled["recall_class_1"] == pytest.approx(0.25)
        assert pooled["iou_class_1"] == pytest.approx(0.25)
    assert math.isnan(
        pixel_scores(small["binary_interior"])["precision_class_0"]
    )


def test_two_class_run_has_symmetric_mode_only():
    truth = np.array([[1, 0, 3]])
    raw = np.array([[1, 2, 1]])
    matrices = pixel_confusions(truth, raw, three_class=False)
    assert list(matrices) == ["binary_interior"]
    assert matrices["binary_interior"].sum() == 2
