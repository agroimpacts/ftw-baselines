import json
from types import SimpleNamespace

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
from ftw_tools.training import eval as offline
from ftw_tools.training.eval_artifacts import EvaluationArtifacts
from ftw_tools.training.metrics import instance_statistics
from ftw_tools.training.analyze_instances import analyze, correlations
from ftw_tools.training.visualize_instances import (
    LABEL_COLORS,
    format_instance_scores,
    orient_for_display,
    render,
    select_chips,
)


def _chip(root, chip_id):
    country = root / "germany"
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


def test_artifacts_pool_and_render_without_model(tmp_path):
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
    assert render(run, ranking="f1-recovery", limit=1) == 1
    assert (run / "figures/f1-recovery-oriented/germany_one.png").exists()
    assert render(run, chips=["germany/one"]) == 1
    assert (run / "figures/selected/germany_one.png").exists()
    assert render(run, metrics=("support", "object_precision")) == 1
    assert (
        run / "figures/support-vs-object_precision-absolute/germany_one.png"
    ).exists()
    assert analyze(run, tmp_path / "analysis") == 1
    assert (tmp_path / "analysis/support-vs-object_precision.png").exists()
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
    assert "Recovery / support" in right
    assert "0.050 / 0.204" in right
    assert "Object precision / recall / F1" in right
    assert "0.000 / 0.000 / 0.000" in right
    assert "Field-interior pixel IoU" in right
    assert "0.050" in right
    assert [line[32] for line in left.splitlines()] == ["0", "0", "0"]
    assert [line[32] for line in right.splitlines()] == ["0", "0", "0"]


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
