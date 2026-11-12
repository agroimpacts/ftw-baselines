import numpy as np
import pandas as pd
import pytest

from ftw_tools.training.metrics import InstanceStatistics
from research.instance_metrics.archive.diagnose_component_metrics import (
    _candidates,
    _country_summary,
    _fields,
    _size_summary,
    diagnose,
)


def test_field_diagnostics_distinguish_count_and_area():
    truth = np.zeros((5, 8), dtype=np.uint8)
    truth[0:3, 0:3] = 1
    truth[4, 5] = 1  # Small missed reference.
    labels = np.zeros_like(truth, dtype=np.int32)
    labels[0:3, 0:3] = 7
    gt, pred, refs, predictions, stats, *_ = _fields(
        truth, labels, threshold=0.5, ignore_index=None, connectivity=4
    )
    assert gt.max() == 2 and pred.max() == 1
    assert stats.scores()["object_recall"] == 0.5
    assert stats.scores()["recovery"] == pytest.approx(0.9)
    assert refs[1]["pixels"] == 1
    assert refs[1]["matched"] is False
    assert refs[1]["best_partner_id"] is None
    assert predictions[0]["matched"] is True
    assert predictions[0]["outside_other_foreground_pixels"] == 0


def test_matched_pq_candidates_keep_both_chips():
    rows = pd.DataFrame([
        {"country": "belgium", "aoi_id": aoi, "pq": 0.4, "rq": 0.5,
         "sq": 0.8, "recovery": recovery, "support": support,
         "object_recall": 0.5, "object_precision": 0.5, "object_f1": 0.5,
         "rand_split_score": 0.5, "rand_merge_score": 0.6,
         "stat_tp": 1, "stat_fp": 1, "stat_fn": 1}
        for aoi, recovery, support in (("a", 0.2, 0.5), ("b", 0.8, 0.5))
    ])
    candidates = _candidates(rows, 1)
    paired = candidates.loc[candidates.case == "same_pq_different_recovery"]
    assert set(zip(paired.aoi_id, paired.paired_aoi_id)) == {("a", "b"), ("b", "a")}
    assert {"object_precision", "object_recall", "object_f1", "rand_split_score",
            "rand_merge_score", "stat_tp", "stat_fp", "stat_fn"} <= set(candidates)


def test_high_agreement_requires_high_values_and_high_pq_requires_both_pairs():
    scores = {
        "pq": 0.8, "rq": 0.9, "sq": 0.89, "object_f1": 0.9,
        "object_recall": 0.81, "recovery": 0.82,
        "object_precision": 0.84, "support": 0.83,
        "rand_split_score": 0.7, "rand_merge_score": 0.7,
        "stat_tp": 9, "stat_fp": 1, "stat_fn": 1,
    }
    rows = pd.DataFrame([
        {"country": "belgium", "aoi_id": "good", **scores},
        {"country": "belgium", "aoi_id": "low",
         **{**scores, "pq": 0.2, "object_recall": 0.2, "recovery": 0.21,
            "object_precision": 0.2, "support": 0.21}},
        {"country": "belgium", "aoi_id": "unequal",
         **{**scores, "support": 0.3}},
    ])
    selected = _candidates(rows, 2)
    assert set(selected.loc[selected.case == "high_pq_both_pairs_agree", "aoi_id"]) == {"good"}
    assert "low" not in set(selected.loc[
        selected.case == "high_recall_recovery_agree", "aoi_id"
    ])
    with pytest.raises(ValueError, match="high_score"):
        _candidates(rows, 2, high_score=1.1)


def test_presence_only_country_rejected(tmp_path):
    directory = tmp_path / "brazil"
    directory.mkdir()
    (directory / "summary.json").write_text('{"country": "brazil"}')
    with pytest.raises(ValueError, match="lacks labeled background"):
        diagnose([directory], tmp_path / "output", figures=False)
    assert not (tmp_path / "output").exists()


def test_country_rand_uses_pooled_sufficient_statistics():
    chips = pd.DataFrame([
        {"country": "belgium", "pq": 0.5, "sq": 0.8,
         "recovery": 0.5, "support": 0.5,
         **{f"stat_{name}": getattr(stats, name)
            for name in InstanceStatistics.__dataclass_fields__}}
        for stats in (
            InstanceStatistics(intersection_sq=1, truth_area_sq=1,
                               prediction_on_truth_sq=1),
            InstanceStatistics(intersection_sq=0, truth_area_sq=3,
                               prediction_on_truth_sq=1),
        )
    ])
    summary = _country_summary(chips)[0]
    assert summary["pooled_rand_split_score"] == pytest.approx(0.25)
    assert summary["pooled_rand_merge_score"] == pytest.approx(0.5)


def test_size_bins_mean_and_area_weighted_best_iou_are_distinct():
    references = pd.DataFrame([
        {"country": "belgium", "size_bin": "1-4", "pixels": pixels,
         "best_iou": iou, "matched": matched}
        for pixels, iou, matched in ((1, 1.0, True), (3, 0.0, False))
    ])
    summary = _size_summary(references, references)
    small = summary.loc[(summary.side == "reference") &
                        (summary.size_bin == "1-4")].iloc[0]
    assert small.match_rate == pytest.approx(0.5)
    assert small.mean_best_iou == pytest.approx(0.5)
    assert small.area_weighted_best_iou == pytest.approx(0.25)
    assert small.mean_matched_best_iou == pytest.approx(1.0)
    empty = summary.loc[(summary.side == "reference") &
                        (summary.size_bin == "5-16")].iloc[0]
    assert np.isnan(empty.mean_best_iou)
