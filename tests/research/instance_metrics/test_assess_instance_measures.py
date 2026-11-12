import json

import pandas as pd
import pytest

from research.instance_metrics.assess_instance_measures import _pooled_scores, assess


def test_assessment_pairs_chips_and_reports_opposed_method_directions(tmp_path):
    comparison = tmp_path / "comparison"
    comparison.mkdir()
    methods = ("components-4", "arg-pb-h0.01-t0.3")
    (comparison / "summary.json").write_text(
        json.dumps(
            {
                "split": "test",
                "country": "belgium",
                "chip_count": 2,
                "methods": dict.fromkeys(methods),
                "checkpoint_sha256": "same-checkpoint",
            }
        )
    )
    rows = []
    for chip, pq, recovery in (("one", 0.3, 0.7), ("two", 0.6, 0.4)):
        for method in methods:
            rows.append(
                {
                    "country": "belgium",
                    "aoi_id": chip,
                    "method": method,
                    "pq": pq + (0.1 if method != "components-4" else 0),
                    "recovery": recovery - (0.1 if method != "components-4" else 0),
                    "object_recall": 0.4,
                    "support": 0.5,
                    "object_precision": 0.5,
                    "rand_split_score": 0.5,
                    "rand_merge_score": 0.5,
                }
            )
    pd.DataFrame(rows[::-1]).to_parquet(comparison / "chips.parquet", index=False)
    assert assess([comparison], tmp_path / "analysis", draws=30) == 1
    differences = pd.read_csv(tmp_path / "analysis/method_differences.csv")
    pq = differences.loc[differences.measure == "pq"].iloc[0]
    assert pq.n == 2
    assert pq.mean_chip_delta == pytest.approx(0.1)
    opposing = differences.loc[differences.measure == "opposed:pq:recovery"].iloc[0]
    assert opposing.opposed == 2
    assert opposing.tied_either == 0
    with pytest.raises(FileExistsError):
        assess([comparison], tmp_path / "analysis")


def test_global_assessment_keeps_chip_and_country_weights_distinct(tmp_path):
    methods = ("components-4", "arg-pb-h0.01-t0.3")
    directories = []
    for country, changes in (("big", [0.1, 0.1, 0.1]), ("small", [-0.2])):
        directory = tmp_path / country
        directory.mkdir()
        directories.append(directory)
        (directory / "summary.json").write_text(
            json.dumps(
                {
                    "country": country,
                    "split": "test",
                    "chip_count": len(changes),
                    "methods": dict.fromkeys(methods),
                    "checkpoint_sha256": "same-checkpoint",
                    "iou_threshold": 0.5,
                    "reference_connectivity": 4,
                }
            )
        )
        rows = []
        for index, change in enumerate(changes):
            for method in methods:
                altered = method != "components-4"
                rows.append(
                    {
                        "country": country,
                        "aoi_id": str(index),
                        "method": method,
                        "pq": 0.5 + change * altered,
                        "recovery": 0.4 - change * altered,
                        "object_recall": 0.5,
                        "support": 0.5,
                        "object_precision": 0.5,
                        "rand_split_score": 0.5,
                        "rand_merge_score": 0.5,
                    }
                )
        pd.DataFrame(rows).to_parquet(directory / "chips.parquet", index=False)
    assert assess(directories, tmp_path / "global", draws=50) == 2
    global_rows = pd.read_csv(tmp_path / "global/global_method_differences.csv")
    pq = global_rows.loc[global_rows.measure == "pq"].iloc[0]
    assert pq.n == 4
    assert pq.mean_chip_delta == pytest.approx(0.025)
    assert (pq.improved, pq.worsened) == (3, 1)
    equal = pd.read_csv(tmp_path / "global/equal_country_differences.csv")
    assert equal.loc[equal.measure == "pq", "mean_country_delta"].iloc[
        0
    ] == pytest.approx(-0.05)
    opposing = global_rows.loc[global_rows.measure == "opposed:pq:recovery"].iloc[0]
    assert opposing.opposed == 4
    assert set(
        pd.read_csv(tmp_path / "global/global_discordant_chips.csv").chip_country
    ) == {"big", "small"}
    assert set(pd.read_csv(tmp_path / "global/measure_pairs.csv").country) == {
        "big",
        "small",
    }
    assert set(pd.read_csv(tmp_path / "global/global_measure_pairs.csv").country) == {
        "all"
    }


def test_global_pooled_scores_use_additive_statistics():
    from ftw_tools.training.metrics import InstanceStatistics

    table = pd.DataFrame(
        [
            {
                "method": "components-4",
                **{
                    f"stat_{name}": getattr(stats, name)
                    for name in InstanceStatistics.__dataclass_fields__
                },
            }
            for stats in (
                InstanceStatistics(tp=1, matched_iou=1),
                InstanceStatistics(fp=9),
            )
        ]
    )
    pq = _pooled_scores(table).query('measure == "pq"').pooled_score.iloc[0]
    assert pq == pytest.approx(2 / 11)
