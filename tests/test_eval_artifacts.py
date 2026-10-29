import json
import shutil
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import rasterio
import torch
from affine import Affine
from click.testing import CliRunner
from rasterio.transform import from_origin
from torch.utils.data import DataLoader

from ftw_tools.cli import model_test
from ftw_tools.settings import (
    ALL_COUNTRIES,
    FULL_DATA_COUNTRIES,
    has_labeled_background,
)
from ftw_tools.training import eval as offline
from ftw_tools.training.eval_artifacts import EvaluationArtifacts
from ftw_tools.training.metrics import instance_statistics
from scripts import visualize_instances
from scripts.analyze_instances import (
    analyze,
    correlations,
    draw_correlation_heatmap,
    heatmap_style,
    load_runs,
    regression,
)
from scripts.visualize_instances import (
    LABEL_COLORS,
    MATCH_COLORS,
    draw_object_contours,
    format_instance_scores,
    object_status_labels,
    orient_for_display,
    render,
    select_chips,
)


def _chip(root, chip_id, country="germany"):
    country = root / country
    reference = country / "label_masks" / "semantic_3class"
    reference.mkdir(parents=True, exist_ok=True)
    mask = reference / f"{chip_id}.tif"
    profile = {
        "driver": "GTiff",
        "height": 2,
        "width": 2,
        "count": 1,
        "dtype": "uint8",
        "crs": "EPSG:32632",
        "transform": from_origin(500000, 5800000, 10, 10),
    }
    with rasterio.open(mask, "w", **profile) as dst:
        dst.write(np.array([[1, 2], [0, 3]], dtype=np.uint8), 1)
    paths = {}
    for window in ("window_a", "window_b"):
        image = country / "s2_images" / window / f"{chip_id}.tif"
        image.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            image, "w", **{**profile, "count": 3, "dtype": "uint16"}
        ) as dst:
            dst.write(np.full((3, 2, 2), 1500, dtype=np.uint16))
        paths[window] = str(image)
    return {"mask": str(mask), **paths}


def test_artifacts_pool_and_render_without_model(tmp_path, monkeypatch):
    checkpoint = tmp_path / "checkpoint.ckpt"
    checkpoint.write_bytes(b"synthetic checkpoint")
    record = _chip(tmp_path, "one")
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
    stats = instance_statistics(truth, scored)
    writer.add(record, raw, scored, truth, stats)
    writer.finish({"pixel_iou": 1.0})
    with rasterio.open(run / "predictions/germany/one.tif") as result:
        assert np.array_equal(result.read(1), raw)
        with rasterio.open(record["mask"]) as source:
            assert result.transform == source.transform
            assert result.crs == source.crs
        assert result.nodata is None
    table = pd.read_parquet(run / "chips.parquet")
    assert table.loc[0, "stat_tp"] == stats.tp
    assert table.loc[0, "raw_boundary_pixels"] == 2
    assert table.loc[0, "scored_boundary_pixels"] == 0
    summary = json.loads((run / "summary.json").read_text())
    assert summary["instance_statistics"]["tp"] == stats.tp
    assert summary["instance_scores"]["sq"] == stats.scores()["sq"]
    for name in ("recovery", "support"):
        assert table.loc[0, name] == stats.scores()[name]
        assert summary["instance_scores"][name] == stats.scores()[name]
    comparisons = summary["pixel_comparisons"]
    assert set(comparisons) == {"three_class", "binary_interior", "legacy_asymmetric"}
    assert comparisons["three_class"]["confusion"][2][2] == 1
    assert comparisons["legacy_asymmetric"]["confusion"][2][0] == 1
    assert comparisons["binary_interior"]["scores"]["iou_class_1"] == 1
    assert table.loc[0, "pixel_three_class_count_2_2"] == 1
    assert table.loc[0, "pixel_legacy_asymmetric_count_2_0"] == 1
    assert (
        json.loads((run / "manifest.json").read_text())["scored_raster"]
        == "class 2 remapped to 0"
    )
    subplots = plt.subplots
    panels = []

    def capture_panels(*args, **kwargs):
        fig, axes = subplots(*args, **kwargs)
        panels.append(axes)
        return fig, axes

    monkeypatch.setattr(visualize_instances.plt, "subplots", capture_panels)
    assert render(run, ranking="f1-recovery", limit=1) == 1
    monkeypatch.setattr(visualize_instances.plt, "subplots", subplots)
    assert len(panels[0]) == 5
    assert not panels[0][2].collections and not panels[0][3].collections
    assert len(panels[0][4].collections) == 1  # only the matched prediction
    assert np.array_equal(panels[0][2].images[0].get_array(), truth)
    assert np.array_equal(panels[0][3].images[0].get_array(), raw)
    assert (run / "figures/f1-recovery-oriented/germany_one.png").exists()
    assert render(run, chips=["germany/one"]) == 1
    assert (run / "figures/selected/germany_one.png").exists()
    assert render(run, metrics=("support", "object_precision")) == 1
    assert (
        run / "figures/support-vs-object_precision-absolute/germany_one.png"
    ).exists()
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
    with pytest.raises(FileExistsError):
        render(run, ranking="f1-recovery", limit=1)
    with pytest.raises(FileExistsError):
        EvaluationArtifacts(
            run,
            checkpoint=checkpoint,
            dataset=tmp_path,
            settings={"remap_boundary": True},
        )


def test_score_panel_explains_high_merge_with_missed_fields():
    row = SimpleNamespace(
        country="germany",
        rand_split_score=0.017362,
        rand_merge_score=1.0,
        recovery=0.049633,
        support=0.20375,
        stat_tp=0,
        stat_fp=4,
        stat_fn=19,
        object_precision=0.0,
        object_recall=0.0,
        object_f1=0.0,
        rq=0.0,
        sq=float("nan"),
        pq=0.0,
        pixel_binary_interior_iou_class_1=0.05,
    )
    left, right = format_instance_scores(row)
    assert "Rand split / merge    " in left
    assert "0.017 / 1.000" in left
    assert "TP / FP / FN" in left
    assert "0 / 4 / 19" in left
    assert "RQ / SQ / PQ" in left
    assert "0.000 / — / 0.000" in left
    assert "Support / recovery" in right
    assert "0.204 / 0.050" in right
    assert "Object precision / recall / F1" in right
    assert "0.000 / 0.000 / 0.000" in right
    assert "Field-interior pixel IoU" in right
    assert "0.050" in right
    assert [line[32] for line in left.splitlines()] == ["0", "0", "0"]
    assert [line[32] for line in right.splitlines()] == ["0", "0", "0"]


@pytest.mark.parametrize(
    "country", sorted(set(ALL_COUNTRIES) - set(FULL_DATA_COUNTRIES))
)
def test_unknown_background_excludes_fp_based_scores_but_preserves_raw_mask(
    tmp_path, monkeypatch, country
):
    assert not has_labeled_background(country)
    record = _chip(tmp_path, "one", country=country)
    checkpoint = tmp_path / "checkpoint.ckpt"
    checkpoint.write_bytes(b"checkpoint")
    run = tmp_path / "run"
    truth = np.array([[1, 2], [3, 3]], dtype=np.uint8)
    raw = np.array([[1, 0], [1, 1]], dtype=np.uint8)
    with rasterio.open(record["mask"], "r+") as target:
        target.write(truth, 1)
    writer = EvaluationArtifacts(
        run,
        checkpoint=checkpoint,
        dataset=tmp_path,
        settings={"countries": [country], "remap_boundary": False},
    )
    stats = instance_statistics(truth, raw)
    writer.add(record, raw, raw, truth, stats)
    writer.finish({"pixel_iou": 1.0})
    table = pd.read_parquet(run / "chips.parquet")
    summary = json.loads((run / "summary.json").read_text())
    assert (stats.tp, stats.fp, stats.fn) == (1, 0, 0)
    assert table.loc[0, "object_recall"] == 1
    for name in ("object_precision", "object_f1", "rq", "pq"):
        assert pd.isna(table.loc[0, name])
        assert summary["instance_scores"][name] is None
    assert summary["instance_statistics"]["tp"] == 1
    left, right = format_instance_scores(table.iloc[0])
    assert "1 / — / 0" in left
    assert "— / 1.000 / —" in right
    subplots = plt.subplots
    panels = []

    def capture(*args, **kwargs):
        fig, axes = subplots(*args, **kwargs)
        panels.append(axes)
        return fig, axes

    monkeypatch.setattr(visualize_instances.plt, "subplots", capture)
    assert render(run, chips=[f"{country}/one"]) == 1
    assert panels[0][3].images[0].get_array()[1, 0] == 1  # raw still shown
    assert panels[0][3].images[1].get_array()[1, 0, 3] > 0  # ignored overlay
    assert panels[0][3].images[1].get_array()[0, 0, 3] == 0


def test_mixed_background_coverage_preserves_recall_not_pooled_precision(tmp_path):
    checkpoint = tmp_path / "checkpoint.ckpt"
    checkpoint.write_bytes(b"checkpoint")
    truth = np.array([[1, 2], [0, 3]], dtype=np.uint8)
    pred = np.array([[1, 0], [0, 1]], dtype=np.uint8)
    writer = EvaluationArtifacts(
        tmp_path / "run",
        checkpoint=checkpoint,
        dataset=tmp_path,
        settings={"countries": ["germany", "kenya"], "remap_boundary": False},
    )
    for country in ("germany", "kenya"):
        writer.add(
            _chip(tmp_path, "one", country=country),
            pred,
            pred,
            truth,
            instance_statistics(truth, pred),
        )
    writer.finish({"pixel_iou": 1.0})
    table = pd.read_parquet(tmp_path / "run/chips.parquet").set_index("country")
    summary = json.loads((tmp_path / "run/summary.json").read_text())
    assert table.loc["germany", "object_precision"] == 1
    assert pd.isna(table.loc["kenya", "object_precision"])
    assert summary["instance_scores"]["object_precision"] is None
    assert summary["instance_scores"]["object_recall"] == 1


def test_custom_rankings_and_pairwise_correlations():
    table = pd.DataFrame(
        {
            "country": ["germany"] * 4,
            "aoi_id": ["a", "b", "c", "d"],
            "support": [0.9, 0.2, 0.7, np.nan],
            "object_precision": [0.1, 0.8, 0.6, 0.4],
            "recovery": [0.2, 0.4, np.nan, 0.8],
        }
    )
    selection = {"metrics": ("support", "object_precision"), "limit": 2}
    assert select_chips(table, **selection)[0].aoi_id.tolist() == ["a", "b"]
    assert select_chips(table, **selection, order="low")[0].aoi_id.tolist() == [
        "b",
        "c",
    ]
    assert select_chips(table, **selection, order="high")[0].aoi_id.tolist() == [
        "a",
        "c",
    ]
    assert select_chips(table, chips=["germany/c"])[0].aoi_id.tolist() == ["c"]
    with pytest.raises(ValueError, match="one chip"):
        select_chips(table, chips=["germany/missing"])
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


def test_analyze_combines_disjoint_countries_and_rejects_duplicate_chips(tmp_path):
    checkpoint = tmp_path / "model.ckpt"
    checkpoint.write_bytes(b"same model")
    runs = []
    for country, pred in (
        ("germany", [[1, 0], [0, 0]]),
        ("portugal", [[0, 0], [0, 0]]),
    ):
        run = tmp_path / country / "run"
        record = _chip(tmp_path / country, "one", country)
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


def test_object_status_labels_classify_matched_unmatched_and_ignored():
    truth = np.array([[1, 1, 0, 1, 1, 0, 1, 1, 3, 0]])
    pred = np.array([[1, 1, 0, 1, 0, 0, 0, 0, 1, 1]])
    statuses = object_status_labels(truth, pred, {}, (1, 2, 2))
    predicted, tp_ids = statuses["TP"]
    assert np.isin(predicted[0, :2], tp_ids).all()
    _, fp_ids = statuses["FP"]
    assert predicted[0, 3] in fp_ids
    assert predicted[0, 8] == 0  # ignored reference pixel removes prediction
    assert predicted[0, 9] in fp_ids
    reference, fn_ids = statuses["FN"]
    assert np.isin(reference[0, 3:5], fn_ids).all()
    assert np.isin(reference[0, 6:8], fn_ids).all()
    assert (len(tp_ids), len(fp_ids), len(fn_ids)) == (1, 2, 2)
    assert list(MATCH_COLORS) == ["TP", "FP", "FN"]
    with pytest.raises(ValueError, match="saved chip statistics"):
        object_status_labels(truth, pred, {}, (2, 1, 2))


def test_tp_prediction_can_overlap_a_different_fn_reference():
    truth = np.array([[1, 1, 1, 0, 1, 1]])
    pred = np.array([[1, 1, 1, 1, 1, 0]])
    statuses = object_status_labels(truth, pred, {}, (1, 0, 1))
    gt, missed = statuses["FN"]
    predicted, matched = statuses["TP"]
    assert len(missed) == len(matched) == 1
    assert gt[0, 0] not in missed  # matched reference is never FN
    assert gt[0, 4] in missed
    assert predicted[0, 4] in matched  # same location, different objects


def test_object_contour_tracks_exact_reference_pixel_boundary():
    fig, axis = plt.subplots()
    labels = np.array([[0, 0, 0], [0, 1, 0], [0, 0, 0]])
    draw_object_contours(axis, labels, [1], MATCH_COLORS["FN"])
    segments = axis.collections[0].get_segments()
    assert {frozenset(map(tuple, segment)) for segment in segments} == {
        frozenset(((0.5, 0.5), (1.5, 0.5))),
        frozenset(((0.5, 1.5), (1.5, 1.5))),
        frozenset(((0.5, 0.5), (0.5, 1.5))),
        frozenset(((1.5, 0.5), (1.5, 1.5))),
    }
    plt.close(fig)


def test_plot_orientation_and_label_palette():
    values = np.array([[1, 2], [3, 4]])
    south_up = Affine(1, 0, 0, 0, 1, 0)
    north_up = Affine(1, 0, 0, 0, -1, 0)
    assert orient_for_display(values, south_up).tolist() == [[3, 4], [1, 2]]
    assert np.array_equal(orient_for_display(values, north_up), values)
    assert orient_for_display(values, Affine(-1, 0, 0, 0, 1, 0)).tolist() == [
        [4, 3],
        [2, 1],
    ]
    assert orient_for_display(np.stack([values] * 3, axis=-1), south_up)[
        0, 0
    ].tolist() == [3, 3, 3]
    with pytest.raises(ValueError, match="Rotated"):
        orient_for_display(values, Affine(1, 0.1, 0, 0, 1, 0))
    assert LABEL_COLORS[1] == "#2478c8"
    assert LABEL_COLORS[2] == "#d74141"


def test_cli_optional_out_dir(monkeypatch, tmp_path):
    arguments = []
    monkeypatch.setattr(
        offline, "test", lambda *args, **kwargs: arguments.append(kwargs)
    )
    checkpoint = tmp_path / "model.ckpt"
    checkpoint.write_bytes(b"x")
    base = [
        "--model",
        str(checkpoint),
        "--dir",
        str(tmp_path),
        "--countries",
        "germany",
    ]
    runner = CliRunner()
    assert runner.invoke(model_test, base).exit_code == 0
    assert arguments[-1]["out_dir"] is None
    out_dir = tmp_path / "run"
    assert runner.invoke(model_test, base + ["--out_dir", str(out_dir)]).exit_code == 0
    assert arguments[-1]["out_dir"] == str(out_dir)
    assert arguments[-1]["save_probabilities"] is False
    assert (
        runner.invoke(
            model_test, base + ["--out_dir", str(out_dir), "--save_probabilities"]
        ).exit_code
        == 0
    )
    assert arguments[-1]["save_probabilities"] is True
    assert not out_dir.exists()


def test_offline_artifacts_follow_partial_batch(monkeypatch, tmp_path):
    records = [_chip(tmp_path, str(i)) for i in range(3)]
    checkpoint = tmp_path / "model.ckpt"
    checkpoint.write_bytes(b"fake weights")

    class FakeDataset:
        def __init__(self, **kwargs):
            self.filenames = records

        def __len__(self):
            return len(self.filenames)

        def __getitem__(self, index):
            return {
                "image": torch.zeros((8, 2, 2)),
                "mask": torch.tensor([[1, 2], [0, 3]]),
            }

    class FakeModel(torch.nn.Module):
        def forward(self, x):
            output = torch.zeros((len(x), 3, 2, 2))
            output[:, 1, 0, 0] = 5
            output[:, 2, 0, 1] = 5
            return output

    class FakeTask:
        hparams = {"model": "unet", "ignore_index": 3}
        model = FakeModel()

    monkeypatch.setattr(offline, "FTW", FakeDataset)
    monkeypatch.setattr(
        offline.CustomSemanticSegmentationTask,
        "load_from_checkpoint",
        lambda *args, **kwargs: FakeTask(),
    )
    monkeypatch.setattr(
        offline, "DataLoader", lambda ds, **kwargs: DataLoader(ds, batch_size=2)
    )
    run = tmp_path / "run"
    offline.test(
        str(checkpoint),
        str(tmp_path),
        -1,
        ["germany"],
        0.5,
        None,
        True,
        True,
        "stacked",
        False,
        False,
        None,
        1,
        1,
        out_dir=str(run),
    )
    table = pd.read_parquet(run / "chips.parquet")
    assert table.aoi_id.tolist() == ["0", "1", "2"]
    assert len(list((run / "predictions/germany").glob("*.tif"))) == 3
    summary = json.loads((run / "summary.json").read_text())
    assert summary["chip_count"] == 3
    assert summary["instance_statistics"]["tp"] == table.stat_tp.sum()
    assert summary["pixel_comparisons"]["three_class"]["scores"]["iou_class_2"] == 1
    assert (
        summary["pixel_comparisons"]["legacy_asymmetric"]["scores"]["iou_class_2"] == 0
    )
    assert (
        summary["pixel_scores"]["pixel_iou"]
        == summary["pixel_comparisons"]["legacy_asymmetric"]["scores"]["iou_class_1"]
    )
    for mode, details in summary["pixel_comparisons"].items():
        for reference, line in enumerate(details["confusion"]):
            for prediction, count in enumerate(line):
                column = f"pixel_{mode}_count_{reference}_{prediction}"
                assert count == table[column].sum()
    default_csv = tmp_path / "default.csv"
    offline.test(
        str(checkpoint),
        str(tmp_path),
        -1,
        ["germany"],
        0.5,
        str(default_csv),
        True,
        True,
        "stacked",
        False,
        False,
        None,
        1,
        1,
    )
    assert default_csv.exists()
    assert not (tmp_path / "predictions").exists()
    assert (
        pd.read_csv(default_csv).iloc[0]["object_level_f1"]
        == (summary["instance_scores"]["object_f1"])
    )


def test_probability_artifacts_follow_partial_batch(monkeypatch, tmp_path):
    records = [_chip(tmp_path, str(i)) for i in range(3)]
    checkpoint = tmp_path / "model.ckpt"
    checkpoint.write_bytes(b"fake weights")

    class FakeDataset:
        def __init__(self, **kwargs):
            self.filenames = records

        def __len__(self):
            return len(records)

        def __getitem__(self, index):
            return {
                "image": torch.zeros((8, 2, 2)),
                "mask": torch.tensor([[1, 2], [0, 3]]),
            }

    class FakeModel(torch.nn.Module):
        def forward(self, x):
            logits = torch.zeros((len(x), 3, 2, 2))
            logits[:, 1, 0, 0] = 5
            logits[:, 2, 0, 1] = 5
            return logits

    class FakeTask:
        hparams = {"model": "unet", "ignore_index": 3}
        model = FakeModel()

    monkeypatch.setattr(offline, "FTW", FakeDataset)
    monkeypatch.setattr(
        offline.CustomSemanticSegmentationTask,
        "load_from_checkpoint",
        lambda *args, **kwargs: FakeTask(),
    )
    monkeypatch.setattr(
        offline, "DataLoader", lambda ds, **kwargs: DataLoader(ds, batch_size=2)
    )
    run = tmp_path / "run"
    offline.test(
        str(checkpoint),
        str(tmp_path),
        -1,
        ["germany"],
        0.5,
        None,
        True,
        True,
        "stacked",
        False,
        False,
        None,
        1,
        1,
        out_dir=str(run),
        save_probabilities=True,
    )
    table = pd.read_parquet(run / "chips.parquet")
    for row in table.itertuples():
        with (
            rasterio.open(run / row.prediction) as classes,
            rasterio.open(run / row.probabilities) as scores,
        ):
            assert scores.count == 3
            assert scores.dtypes == ("float32",) * 3
            assert scores.transform == classes.transform
            assert scores.crs == classes.crs
            np.testing.assert_array_equal(scores.read().argmax(axis=0), classes.read(1))
            np.testing.assert_allclose(scores.read().sum(axis=0), 1)
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["settings"]["save_probabilities"] is True
