"""Research analysis checks, separate from supported artifact/plot tests."""

import json
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from ftw_tools.training.eval_artifacts import EvaluationArtifacts
from ftw_tools.training.metrics import instance_statistics
from research.instance_metrics.analyze_instances import (
    analyze,
    correlations,
    draw_correlation_heatmap,
    heatmap_style,
    load_runs,
    regression,
)
from tests.artifact_helpers import chip_record


def test_pairwise_correlations():
    table = pd.DataFrame(
        {
            "support": [0.9, 0.2, 0.7, np.nan],
            "object_precision": [0.1, 0.8, 0.6, 0.4],
            "recovery": [0.2, 0.4, np.nan, 0.8],
        }
    )
    pearson, spearman, counts = correlations(
        table, ["support", "object_precision", "recovery"]
    )
    assert counts.loc["support", "recovery"] == 2
    assert pearson.loc["support", "object_precision"] == pytest.approx(-0.884615)
    assert spearman.loc["support", "object_precision"] == pytest.approx(-1)


def test_binned_heatmap_and_ols_parameters():
    matrix = pd.DataFrame(
        [[1, -0.1254, np.nan], [-0.1254, 1, 0.78543], [np.nan, 0.78543, 1]],
        columns=["x", "y", "z"],
        index=["x", "y", "z"],
    )
    data, cmap, norm = heatmap_style(matrix)
    assert data.mask[0, 0] and data.mask[1, 1]
    assert not data.mask[0, 1]  # upper triangle retains its color
    assert data.mask[2, 0]  # undefined lower-triangle coefficient
    assert not data.mask[1, 0] and not data.mask[2, 1]
    assert cmap.get_bad()[:3] == pytest.approx((1, 1, 1))
    assert len(norm.boundaries) == 41
    assert norm(0.01) == norm(0.04)
    assert norm(0.01) != norm(0.06)
    fig, axis = plt.subplots()
    draw_correlation_heatmap(axis, matrix)
    assert [label.get_text() for label in axis.texts] == ["-0.125", "0.785"]
    assert len(axis.patches) == 3
    assert axis.patches[0].get_facecolor()[:3] == pytest.approx((189 / 255,) * 3)
    plt.close(fig)
    table = pd.DataFrame({"x": [0, 1, 2, np.nan], "y": [1, 3, 5, 100]})
    fit = regression(table, "x", "y")
    assert fit == {"n": 3, "slope": 2, "intercept": 1, "r_squared": 1}
    assert np.isnan(
        regression(pd.DataFrame({"x": [1, 1], "y": [1, 2]}), "x", "y")["slope"]
    )


def test_analyze_saved_artifacts(tmp_path):
    checkpoint = tmp_path / "checkpoint.ckpt"
    checkpoint.write_bytes(b"synthetic checkpoint")
    record = chip_record(tmp_path, "one")
    run = tmp_path / "run"
    writer = EvaluationArtifacts(
        run,
        checkpoint=checkpoint,
        dataset=tmp_path,
        settings={
            "remap_boundary": True,
            "split": "test",
            "countries": ["germany"],
            "test_on_3_classes": True,
            "model_predicts_3_classes": True,
        },
    )
    truth = np.array([[1, 2], [0, 3]], dtype=np.uint8)
    raw = np.array([[1, 2], [0, 2]], dtype=np.uint8)
    scored = np.where(raw == 2, 0, raw).astype(np.uint8)
    writer.add(record, raw, scored, truth, instance_statistics(truth, scored))
    writer.finish({"pixel_iou": 1.0})
    assert analyze(run, tmp_path / "analysis") == 1
    assert (tmp_path / "analysis/support-vs-object_precision.png").exists()
    assert (
        "pixel_binary_interior_iou_class_1"
        in pd.read_csv(tmp_path / "analysis/pearson.csv", index_col=0).columns
    )
    assert (tmp_path / "analysis/regressions.csv").exists()
    assert (
        json.loads((tmp_path / "analysis/inputs.json").read_text())[0]["chip_count"]
        == 1
    )


def test_analyze_combines_disjoint_countries_and_rejects_duplicate_chips(tmp_path):
    checkpoint = tmp_path / "model.ckpt"
    checkpoint.write_bytes(b"same model")
    runs = []
    for country, pred in (
        ("germany", [[1, 0], [0, 0]]),
        ("portugal", [[0, 0], [0, 0]]),
    ):
        run = tmp_path / country / "run"
        record = chip_record(tmp_path / country, "one", country)
        writer = EvaluationArtifacts(
            run,
            checkpoint=checkpoint,
            dataset=tmp_path,
            settings={"countries": [country], "split": "test", "remap_boundary": False},
        )
        truth = np.array([[1, 2], [0, 3]], dtype=np.uint8)
        raw = np.array(pred, dtype=np.uint8)
        writer.add(record, raw, raw, truth, instance_statistics(truth, raw))
        writer.finish({"pixel_iou": 0})
        runs.append(run)
    table, names, inputs = load_runs(runs)
    assert len(table) == 2 and len(names) == 11
    assert [row["countries"] for row in inputs] == [["germany"], ["portugal"]]
    assert analyze(runs, tmp_path / "combined") == 2
    assert (
        pd.read_csv(tmp_path / "combined/pair_counts.csv", index_col=0).loc[
            "recovery", "object_recall"
        ]
        == 2
    )
    assert pd.read_csv(tmp_path / "combined/regressions.csv").loc[0, "n"] == 1
    assert (
        analyze(
            runs,
            tmp_path / "pixel_vs_recovery",
            pairs=[("pixel_binary_interior_iou_class_1", "recovery")],
        )
        == 2
    )
    assert (
        tmp_path / "pixel_vs_recovery/pixel_binary_interior_iou_class_1-vs-recovery.png"
    ).exists()
    duplicate = tmp_path / "duplicate"
    shutil.copytree(runs[0], duplicate)
    with pytest.raises(ValueError, match="Duplicate country/AOI_ID"):
        load_runs([runs[0], duplicate])
