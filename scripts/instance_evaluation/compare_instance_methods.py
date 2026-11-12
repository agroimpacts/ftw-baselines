"""Compare connected components and fbp on one saved ftw model test run.

Usage: uv run --extra fbp python -m scripts.instance_evaluation.compare_instance_methods
       RUN --out_dir OUT
"""

import argparse
import importlib.metadata
import json
import math
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS
from scipy.ndimage import label as connected_components
from skimage.measure import label as label_values

from ftw_tools.settings import has_labeled_background
from ftw_tools.training.metrics import (
    InstanceStatistics,
    instance_label_statistics,
    instance_scores_for_reporting,
    instance_statistics,
)

DEFAULT_STRATEGIES = ("ftw-2e",)


def _fragment_counts(labels):
    """Return four-connected piece counts per positive method ID."""
    pieces = label_values(labels, connectivity=1, background=0)
    positive = labels > 0
    pairs = np.unique(np.stack((labels[positive], pieces[positive]), axis=1), axis=0)
    ids, counts = np.unique(pairs[:, 0], return_counts=True)
    return dict(zip(ids.tolist(), counts.tolist()))


def prediction_identity_audit(labels, truth, ignore_index=None):
    """Audit method IDs before and after applying the semantic valid domain."""
    valid = np.isin(truth, (0, 1, 2))
    if ignore_index is not None:
        valid &= truth != ignore_index
    raw = _fragment_counts(labels)
    masked = _fragment_counts(np.where(valid, labels, 0))
    result = {}
    for name, counts in (("raw", raw), ("masked", masked)):
        result.update(
            {
                f"{name}_ids": len(counts),
                f"{name}_components": sum(counts.values()),
                f"{name}_fragmented_ids": sum(value > 1 for value in counts.values()),
                f"{name}_fragmented_chips": int(
                    any(value > 1 for value in counts.values())
                ),
            }
        )
    result["ids_further_split_by_mask"] = sum(
        count > raw[ident] for ident, count in masked.items()
    )
    result["ids_removed_by_mask"] = len(raw.keys() - masked.keys())
    return result


def read_reference_ids(reference, truth, profile):
    """Read the paired FTW instance mask; never infer missing field identity."""
    path = Path(reference).parent.parent / "instance" / Path(reference).name
    with rasterio.open(path) as source:
        if (source.shape, source.transform, source.crs) != (
            truth.shape,
            profile["transform"],
            profile["crs"],
        ):
            raise ValueError(f"Misaligned reference instance grid: {path}")
        return source.read(1), str(path)


def _pixel_area_m2(dataset):
    """Metric pixel area, averaged over geographic chip rows without resampling."""
    crs = dataset.crs
    transform = dataset.transform
    if crs is None:
        raise ValueError("Area filtering requires a known CRS")
    if crs.is_projected:
        _, factor = crs.linear_units_factor
        area = abs(transform.a * transform.e - transform.b * transform.d) * factor**2
    elif crs.is_geographic and transform.b == 0 and transform.d == 0:
        geod = CRS.from_user_input(crs).get_geod()
        areas = []
        col = dataset.width // 2
        for row in range(dataset.height):
            points = [
                transform * point
                for point in (
                    (col, row),
                    (col + 1, row),
                    (col + 1, row + 1),
                    (col, row + 1),
                )
            ]
            value, _ = geod.polygon_area_perimeter(*zip(*points))
            areas.append(abs(value))
        area = float(np.mean(areas))
    else:
        raise ValueError("Unsupported grid for metric pixel area")
    if not np.isfinite(area) or area <= 0:
        raise ValueError("Invalid metric pixel area")
    return area


def _methods(strategies):
    """Use published configurations; historical IDs require the archived package."""
    import fbp

    configurations = {}
    for strategy in strategies:
        if strategy == "ftw-2e":
            configurations[strategy] = fbp.FTW_2E
        elif hasattr(fbp, "run"):
            configurations[strategy] = None
        else:
            raise ValueError(
                f"Historical strategy {strategy!r} requires the archived FBP version; "
                "use --strategies ftw-2e with ftw-fbp 0.2.0"
            )
    return configurations


def _scores(stats, *, background_known):
    return {
        key: value if math.isfinite(value) else None
        for key, value in instance_scores_for_reporting(
            stats, background_known=background_known
        ).items()
    }


def compare(run_dir, strategies=DEFAULT_STRATEGIES):
    """Compare each chip and pool statistics for one saved run."""
    return _compare(run_dir, strategies)


def _compare(
    run_dir,
    strategies=DEFAULT_STRATEGIES,
    *,
    labels_dir=None,
    chip_keys=None,
    reference_mode="semantic-components",
    prediction_identity="split-components",
):
    """Optionally persist the exact instance IDs used for scoring."""
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if reference_mode not in ("semantic-components", "dataset-instance-ids"):
        raise ValueError("Unknown reference mode")
    if prediction_identity not in ("split-components", "preserve-ids"):
        raise ValueError("Unknown prediction identity mode")
    source = json.loads((run_dir / "summary.json").read_text())
    settings = manifest["settings"]
    if not all(
        settings.get(key)
        for key in (
            "save_probabilities",
            "test_on_3_classes",
            "model_predicts_3_classes",
        )
    ):
        raise ValueError("Comparison needs aligned three-class probability artifacts")
    if len(settings["countries"]) != 1:
        raise ValueError("Compare one country per run")
    import fbp

    configurations = _methods(strategies)

    methods = ("components-4", "components-8", *strategies)
    if len(set(methods)) != len(methods):
        raise ValueError("Duplicate method IDs")
    rows = []
    pooled = {method: InstanceStatistics() for method in methods}
    chips = pd.read_parquet(run_dir / "chips.parquet")
    if len(chips) != source["chip_count"] or chips.aoi_id.duplicated().any():
        raise ValueError("Chip table does not match summary or has duplicate IDs")
    if chip_keys is not None:
        available = set(zip(chips.country, chips.aoi_id))
        if not chip_keys or not set(chip_keys) <= available:
            raise ValueError("Choose existing chips as COUNTRY/AOI_ID")
        chips = chips.loc[
            [
                (country, aoi) in chip_keys
                for country, aoi in zip(chips.country, chips.aoi_id)
            ]
        ]
    for chip in chips.itertuples(index=False):
        with (
            rasterio.open(chip.reference) as ref,
            rasterio.open(run_dir / chip.prediction) as pred,
            rasterio.open(run_dir / chip.probabilities) as prob,
        ):
            if (
                ref.shape != pred.shape
                or ref.shape != prob.shape
                or ref.transform != pred.transform
                or ref.transform != prob.transform
                or ref.crs != pred.crs
                or ref.crs != prob.crs
                or prob.count != 3
            ):
                raise ValueError(f"Misaligned grids: {chip.country}/{chip.aoi_id}")
            truth = ref.read(1)
            semantic = pred.read(1)
            probabilities = prob.read()
            profile = ref.profile.copy()
            pixel_area_m2 = None
            if any(config is not None for config in configurations.values()):
                pixel_area_m2 = _pixel_area_m2(ref)
        if not np.array_equal(probabilities.argmax(axis=0), semantic):
            raise ValueError(
                f"Probability/class mismatch: {chip.country}/{chip.aoi_id}"
            )
        reference_labels, instance_path = None, None
        if reference_mode == "dataset-instance-ids":
            reference_labels, instance_path = read_reference_ids(
                chip.reference, truth, profile
            )
        for method in methods:
            audit = {}
            if method in ("components-4", "components-8"):
                stats = instance_statistics(
                    truth,
                    semantic,
                    iou_threshold=settings["iou_threshold"],
                    ignore_index=settings.get("ignore_index"),
                    reference_connectivity=settings["reference_connectivity"],
                    prediction_connectivity=int(method[-1]),
                    reference_labels=reference_labels,
                )
                labels = None
                if labels_dir is not None:
                    valid = np.isin(truth, (0, 1, 2))
                    if settings.get("ignore_index") is not None:
                        valid &= truth != settings["ignore_index"]
                    labels, _ = connected_components(
                        (semantic == 1) & valid,
                        structure=np.ones((3, 3), int)
                        if method == "components-8"
                        else None,
                    )
            else:
                config = configurations[method]
                labels = (
                    config(semantic, probabilities, pixel_area_m2=pixel_area_m2)
                    if config is not None
                    else fbp.run(method, semantic, probabilities)
                )
                stats = instance_label_statistics(
                    truth,
                    labels,
                    iou_threshold=settings["iou_threshold"],
                    ignore_index=settings.get("ignore_index"),
                    reference_connectivity=settings["reference_connectivity"],
                    reference_labels=reference_labels,
                    prediction_identity=prediction_identity,
                )
                audit = prediction_identity_audit(
                    labels, truth, settings.get("ignore_index")
                )
            relative = None
            if labels_dir is not None:
                relative = Path("labels") / method / chip.country / f"{chip.aoi_id}.tif"
                destination = labels_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                profile.update(count=1, dtype="int32", nodata=None)
                with rasterio.open(destination, "w", **profile) as target:
                    target.write(np.asarray(labels, dtype=np.int32), 1)
            pooled[method] += stats
            rows.append(
                {
                    "country": chip.country,
                    "aoi_id": chip.aoi_id,
                    "method": method,
                    "pixel_area_m2": pixel_area_m2,
                    "reference_mode": reference_mode,
                    "prediction_identity_mode": prediction_identity,
                    "reference_instances": instance_path,
                    "labels": str(relative) if relative is not None else None,
                    **{f"identity_{key}": value for key, value in audit.items()},
                    **{f"stat_{key}": value for key, value in asdict(stats).items()},
                    **instance_scores_for_reporting(
                        stats, background_known=has_labeled_background(chip.country)
                    ),
                }
            )
    baseline = asdict(pooled["components-4"])
    expected = source["instance_statistics"]
    if (
        reference_mode == "semantic-components"
        and chip_keys is None
        and not np.allclose(
            [baseline[key] for key in expected],
            list(expected.values()),
            rtol=1e-9,
            atol=1e-6,
        )
    ):
        raise ValueError("components-4 does not reproduce original instance statistics")
    result = {
        "source_run": str(run_dir.resolve()),
        "checkpoint_sha256": manifest["checkpoint_sha256"],
        "code_revision": manifest["code_revision"],
        "split": settings["split"],
        "country": settings["countries"][0],
        "chip_count": len(chips),
        "iou_threshold": settings["iou_threshold"],
        "reference_connectivity": settings["reference_connectivity"],
        "reference_mode": reference_mode,
        "prediction_identity_mode": prediction_identity,
        "prediction_identity": f"semantic components use requested connectivity; FBP: {prediction_identity} after valid-domain masking",
        "prediction_identity_audit": {
            method: {
                key.removeprefix("identity_"): int(
                    sum(row.get(key, 0) for row in rows if row["method"] == method)
                )
                for key in {
                    key
                    for row in rows
                    if row["method"] == method
                    for key in row
                    if key.startswith("identity_")
                }
            }
            for method in strategies
        },
        "fbp_version": importlib.metadata.version(
            "ftw-fbp" if hasattr(fbp, "FTW_2E") else "fbp"
        ),
        "method_configurations": {
            name: asdict(config) if config is not None else {"legacy_strategy": name}
            for name, config in configurations.items()
        },
        "probability_encoding": "saved three-channel probabilities; FTW_2E quantizes to 1/255",
        "pixel_area_definition": "projected affine area with unit conversion, or mean geodesic pixel area across geographic chip rows; no resampling",
        "methods": {
            method: {
                "statistics": asdict(stats),
                "scores": _scores(
                    stats,
                    background_known=all(
                        has_labeled_background(country)
                        for country in settings["countries"]
                    ),
                ),
            }
            for method, stats in pooled.items()
        },
    }
    return pd.DataFrame(rows), result


def ensure_selected_labels(comparison, chip_keys, methods):
    """Cache selected labels only after reproducing saved provenance and statistics."""
    comparison = Path(comparison)
    saved = json.loads((comparison / "summary.json").read_text())
    table = pd.read_parquet(comparison / "chips.parquet")
    selected = table.loc[
        [
            (country, aoi) in chip_keys and method in methods
            for country, aoi, method in zip(table.country, table.aoi_id, table.method)
        ]
    ]
    if len(selected) != len(set(chip_keys)) * len(set(methods)):
        raise ValueError("Missing or duplicate chip/method rows")
    missing = selected.loc[
        [
            not isinstance(value, str) or not (comparison / value).is_file()
            for value in selected.labels
        ]
    ]
    if missing.empty:
        return
    # Recompute only requested chips, never the entire country. Temporary outputs
    # are not promoted until every provenance/statistic check has passed.
    strategies = tuple(saved.get("method_configurations", {}))
    if not strategies:
        raise ValueError("Label generation needs recorded method configurations")
    with tempfile.TemporaryDirectory(prefix=".selected-labels-", dir=comparison) as tmp:
        working = Path(tmp)
        regenerated, result = _compare(
            Path(saved["source_run"]),
            strategies,
            labels_dir=working,
            chip_keys=set(zip(missing.country, missing.aoi_id)),
            **(
                {"reference_mode": saved["reference_mode"]}
                if "reference_mode" in saved
                else {}
            ),
            **(
                {"prediction_identity": saved["prediction_identity_mode"]}
                if "prediction_identity_mode" in saved
                else {}
            ),
        )
        for key in (
            "checkpoint_sha256",
            "code_revision",
            "split",
            "country",
            "iou_threshold",
            "reference_connectivity",
            "fbp_version",
            "method_configurations",
            "probability_encoding",
            "pixel_area_definition",
        ):
            if result.get(key) != saved.get(key):
                raise ValueError(f"Assessment provenance changed: {key}")
        if result.get("reference_mode", "semantic-components") != saved.get(
            "reference_mode", "semantic-components"
        ):
            raise ValueError("Assessment reference mode changed")
        if result.get("prediction_identity_mode", "split-components") != saved.get(
            "prediction_identity_mode", "split-components"
        ):
            raise ValueError("Assessment prediction identity changed")
        indexed = regenerated.set_index(["country", "aoi_id", "method"])
        stat_columns = [key for key in table if key.startswith("stat_")]
        for row in selected.itertuples():
            key = (row.country, row.aoi_id, row.method)
            if key not in indexed.index:
                continue
            new = indexed.loc[key]
            if not np.allclose(
                [getattr(row, key) for key in stat_columns],
                new[stat_columns].to_numpy(dtype=float),
                rtol=1e-9,
                atol=1e-6,
                equal_nan=True,
            ):
                raise ValueError(f"Labels do not reproduce saved statistics: {key}")
        for row in missing.itertuples():
            relative = indexed.loc[(row.country, row.aoi_id, row.method), "labels"]
            destination = comparison / relative
            if destination.exists():
                raise FileExistsError(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(working / relative, destination)
            table.loc[row.Index, "labels"] = relative
        staged = working / "chips.parquet"
        table.to_parquet(staged, index=False)
        staged.replace(comparison / "chips.parquet")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--out_dir", type=Path, required=True)
    parser.add_argument("--strategies", nargs="*", default=DEFAULT_STRATEGIES)
    parser.add_argument("--save_labels", action="store_true")
    parser.add_argument(
        "--reference-mode",
        choices=("semantic-components", "dataset-instance-ids"),
        default="semantic-components",
    )
    parser.add_argument(
        "--prediction-identity",
        choices=("split-components", "preserve-ids"),
        default="split-components",
    )
    parser.add_argument(
        "--chip", action="append", default=[], help="Optional COUNTRY/AOI_ID subset"
    )
    args = parser.parse_args()
    out = args.out_dir.expanduser().resolve()
    if out.exists():
        parser.error(f"Output already exists: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{out.name}-", dir=out.parent
    ) as temporary:
        working = Path(temporary)
        rows, result = _compare(
            args.run.expanduser().resolve(),
            args.strategies,
            labels_dir=working if args.save_labels else None,
            reference_mode=args.reference_mode,
            prediction_identity=args.prediction_identity,
            chip_keys={tuple(chip.split("/", 1)) for chip in args.chip}
            if args.chip
            else None,
        )
        rows.to_parquet(working / "chips.parquet", index=False)
        (working / "summary.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n"
        )
        working.rename(out)
    print(f"Compared {result['chip_count']} chips in {out}")


if __name__ == "__main__":
    main()
