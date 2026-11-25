"""Experimental saved-prediction Chamfer rescoring and complementarity.

Use --baseline-analysis RECORDED_ANALYSIS --out_dir NEW_DIRECTORY.
No inference, training integration, source mutation or synthetic reference IDs.
"""

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform

from ftw_tools.settings import has_labeled_background
from ftw_tools.training.metrics import (
    chamfer_statistics,
    instance_scores_for_reporting,
    instance_statistics,
)
from research.instance_metrics.analyze_instances import load_runs
from research.instance_metrics.analyze_metric_complementarity import (
    METRICS,
    PAIRS,
    dimensionality,
    disagreements,
    predictability,
)
from scripts.instance_evaluation.compare_instance_methods import read_reference_ids

NEW = ("threshold_chamfer_m", "best_iou_chamfer_m", "best_iou_reference_coverage")
ALL = (*METRICS, *NEW)
LOWER = NEW[:2]
EXTRA_PAIRS = (
    (NEW[0], NEW[1]),
    (NEW[0], "sq"),
    (NEW[1], "sq"),
    (NEW[0], "recovery"),
    (NEW[1], "recovery"),
    (NEW[2], "object_recall"),
    (NEW[2], "recovery"),
)


def pixel_spacing(dataset):
    """Local metre spacing; geographic grids use geodesic steps at chip centre.

    This extends FTP's nominal scalar GSD to row/column metre spacing. Geographic
    spacing is locally constant, not exact geodesic distance across the chip.
    Rotated/sheared grids are rejected rather than silently approximated.
    """
    transform, crs = dataset.transform, CRS.from_user_input(dataset.crs)
    if transform.b != 0 or transform.d != 0 or not transform.a or not transform.e:
        raise ValueError("Rotated/sheared/degenerate grids are unsupported")
    if crs.is_projected:
        factors = [axis.unit_conversion_factor for axis in crs.axis_info[:2]]
        return abs(transform.e) * factors[1], abs(transform.a) * factors[0]
    if crs.is_geographic:
        x, y = transform * (dataset.width / 2, dataset.height / 2)
        geod = crs.get_geod()
        col = geod.inv(x, y, x + transform.a, y)[2]
        row = geod.inv(x, y, x, y + transform.e)[2]
        return abs(row), abs(col)
    raise ValueError("Unsupported CRS")


def rescore(run, *, limit=None):
    """Return both reference modes, preserving all original per-chip columns."""
    run = Path(run)
    manifest = json.loads((run / "manifest.json").read_text())
    settings = manifest["settings"]
    if any(
        settings.get(k) != v
        for k, v in {
            "iou_threshold": 0.5,
            "reference_connectivity": 4,
            "prediction_connectivity": 4,
            "test_on_3_classes": True,
        }.items()
    ) or settings.get("ignore_index") not in (None, 3, 255):
        raise ValueError("Unsupported scoring contract")
    if settings.get("reference_mode", "semantic-components") != "semantic-components":
        raise ValueError("Expected original semantic reference runs")
    table = pd.read_parquet(run / "chips.parquet")
    if limit is not None:
        table = table.head(limit)
    rows = []
    for chip in table.to_dict("records"):
        with (
            rasterio.open(chip["reference"]) as ref,
            rasterio.open(run / chip["prediction"]) as pred,
        ):
            if (ref.shape, ref.transform, ref.crs) != (
                pred.shape,
                pred.transform,
                pred.crs,
            ):
                raise ValueError("Misaligned prediction")
            truth, prediction = ref.read(1), pred.read(1)
            spacing = pixel_spacing(ref)
            supplied, path = read_reference_ids(chip["reference"], truth, ref.profile)
        for mode in ("semantic-components", "dataset-instance-ids"):
            labels = supplied if mode == "dataset-instance-ids" else None
            row = dict(
                chip,
                reference_mode=mode,
                source_run=str(run),
                reference_instances=str(path),
                row_spacing_m=spacing[0],
                column_spacing_m=spacing[1],
            )
            try:
                stats = instance_statistics(truth, prediction, reference_labels=labels)
                row.update({f'stat_{key}': value for key, value in asdict(stats).items()})
                row.update(
                    instance_scores_for_reporting(
                        stats, background_known=has_labeled_background(chip["country"])
                    )
                )
                row.update(
                    chamfer_statistics(
                        truth, prediction, pixel_size_m=spacing, reference_labels=labels
                    )
                )
                row["reference_status"] = "scored"
                row["mean_reference_area_m2"] = (
                    stats.truth_area * np.prod(spacing) / (stats.tp + stats.fn)
                    if stats.tp + stats.fn
                    else np.nan
                )
            except ValueError as error:
                if (
                    str(error)
                    != "Reference ID foreground differs from semantic class 1"
                ):
                    raise
                for name in (*ALL, "object_f1", "rq"):
                    row[name] = np.nan
                for name in list(row):
                    if name.startswith("stat_"):
                        row[name] = np.nan
                row["reference_status"] = str(error)
            rows.append(row)
    return pd.DataFrame(rows)


def analyze(frame, out, *, fit=True):
    """Separate pairwise populations from same-chip multivariate comparisons."""
    out.mkdir(parents=True, exist_ok=False)
    outputs = {
        k: []
        for k in (
            "availability",
            "distributions",
            "associations",
            "pca_components",
            "pca_loadings",
            "clusters",
            "disagreement",
            "discordant_chips",
            "predictability",
            "counterexamples",
        )
    }
    for scope, part in [("all", frame), *frame.groupby("country", sort=True)]:
        complete = part.replace([np.inf, -np.inf], np.nan).dropna(subset=list(ALL))
        for name in ALL:
            values = part[name].replace([np.inf, -np.inf], np.nan).dropna()
            outputs["availability"].append(
                {
                    "scope": scope,
                    "metric": name,
                    "chips": len(part),
                    "finite": len(values),
                    "complete": len(complete),
                }
            )
            if len(values):
                outputs["distributions"].append(
                    dict(
                        scope=scope,
                        metric=name,
                        n=len(values),
                        mean=values.mean(),
                        **{
                            f"q{q}": values.quantile(q / 100)
                            for q in (5, 25, 50, 75, 95)
                        },
                    )
                )
        for a, b in combinations(ALL, 2):
            pair = part[[a, b]].replace([np.inf, -np.inf], np.nan).dropna()
            outputs["associations"].append(
                {
                    "scope": scope,
                    "first": a,
                    "second": b,
                    "n": len(pair),
                    "pearson": pair[a].corr(pair[b]),
                    "spearman": pair[a].corr(pair[b], method="spearman"),
                }
            )
        for suite, metrics in [("original8_same_chips", METRICS), ("expanded11", ALL)]:
            components, loadings = dimensionality(complete, scope, metrics=metrics)
            outputs["pca_components"].extend(dict(suite=suite, **r) for r in components)
            outputs["pca_loadings"].extend(dict(suite=suite, **r) for r in loadings)
            if fit:
                outputs["predictability"].extend(
                    dict(suite=suite, **r)
                    for r in predictability(
                        complete, scope, grouped=scope == "all", metrics=metrics
                    )
                )
            varying = [m for m in metrics if complete[m].nunique() > 1]
            corr = complete[varying].corr(method="spearman").abs()
            if len(complete) >= 3 and len(varying) >= 2 and corr.notna().all().all():
                distance = (1 - corr).clip(lower=0).to_numpy(copy=True)
                np.fill_diagonal(distance, 0)
                for i, (a, b, d, n) in enumerate(
                    linkage(squareform(distance, checks=False), method="average"),
                    start=len(varying),
                ):
                    outputs["clusters"].append(
                        {
                            "scope": scope,
                            "suite": suite,
                            "cluster": i,
                            "left": int(a),
                            "right": int(b),
                            "distance": d,
                            "size": int(n),
                            "leaves": json.dumps(varying),
                        }
                    )
        if fit:
            outputs["predictability"].extend(
                dict(suite="new_from_original8", **r)
                for r in predictability(
                    complete,
                    scope,
                    grouped=scope == "all",
                    metrics=NEW,
                    predictor_metrics=METRICS,
                )
            )
        disagreements_rows, examples = disagreements(
            part, scope, pairs=(*PAIRS, *EXTRA_PAIRS), lower_is_better=LOWER
        )
        outputs["disagreement"].extend(disagreements_rows)
        outputs["discordant_chips"].extend(examples)
        for anchor, target in [("pq", NEW[0]), ("pq", NEW[1]), ("sq", NEW[0])]:
            eligible = (
                part.dropna(subset=[anchor, target])
                .sort_values([anchor, "country", "aoi_id"])
                .reset_index(drop=True)
            )
            candidates = []
            for i in range(len(eligible)):
                for j in range(i + 1, min(i + 12, len(eligible))):
                    if eligible.at[j, anchor] - eligible.at[i, anchor] > 0.02:
                        break
                    candidates.append(
                        (abs(eligible.at[j, target] - eligible.at[i, target]), i, j)
                    )
            for gap, i, j in sorted(candidates, reverse=True)[:10]:
                a, b = eligible.iloc[i], eligible.iloc[j]
                outputs["counterexamples"].append(
                    {
                        "scope": scope,
                        "anchor": anchor,
                        "target": target,
                        "gap": gap,
                        "country_a": a.country,
                        "aoi_a": a.aoi_id,
                        "country_b": b.country,
                        "aoi_b": b.aoi_id,
                        "anchor_a": a[anchor],
                        "anchor_b": b[anchor],
                        "target_a": a[target],
                        "target_b": b[target],
                        "coverage_a": a[NEW[2]],
                        "coverage_b": b[NEW[2]],
                    }
                )
    for name, rows in outputs.items():
        pd.DataFrame(rows).to_csv(out / f"{name}.csv", index=False)
    frame[["country", "aoi_id"]].to_csv(out / "population.csv", index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-analysis", type=Path, required=True)
    parser.add_argument("--out_dir", type=Path, required=True)
    parser.add_argument("--pilot-chips", type=int)
    parser.add_argument("--skip-predictability", action="store_true")
    args = parser.parse_args()
    recorded = json.loads((args.baseline_analysis / "inputs.json").read_text())
    runs = [Path(item["run_dir"]) for item in recorded["runs"]]
    original, _, verified = load_runs(runs)
    for saved, current in zip(recorded["runs"], verified):
        if any(saved[k] != current[k] for k in ("countries", "split", "chip_count")):
            raise ValueError("Recorded cohort changed")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    frames = []
    for run in runs:
        table = rescore(run, limit=args.pilot_chips)
        table.to_parquet(args.out_dir / f"{run.name}.parquet", index=False)
        frames.append(table)
        print(
            f"{run.name}: {len(table) // 2} chips, elapsed {time.monotonic() - start:.1f}s",
            flush=True,
        )
    data = pd.concat(frames, ignore_index=True)
    data.to_parquet(args.out_dir / "chips.parquet", index=False)
    if not args.pilot_chips:
        assert len(data) == 2 * len(original)
    eligible = data[data.country.map(has_labeled_background)].copy()
    indexed = [
        part.set_index(["country", "aoi_id"])
        for _, part in eligible.groupby("reference_mode")
    ]
    shared = set.intersection(
        *(
            set(part.index[np.isfinite(part[list(ALL)].to_numpy(float)).all(axis=1)])
            for part in indexed
        )
    )
    for population in (
        "available",
        "shared-complete",
        "without-denmark",
        "shared-complete-without-denmark",
    ):
        selected = eligible
        if "shared-complete" in population:
            selected = selected[
                [key in shared for key in zip(selected.country, selected.aoi_id)]
            ]
        if "without-denmark" in population:
            selected = selected[selected.country != "denmark"]
        for mode, part in selected.groupby("reference_mode"):
            print(f"Analyzing {population}/{mode}", flush=True)
            analyze(
                part, args.out_dir / population / mode, fit=not args.skip_predictability
            )
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in args.out_dir.glob("*.parquet")
    }
    (args.out_dir / "complete.json").write_text(
        json.dumps(
            {
                "runs": verified,
                "metrics": ALL,
                "shared_complete": len(shared),
                "rows": len(data),
                "elapsed_seconds": time.monotonic() - start,
                "pilot_chips": args.pilot_chips,
                "predictability": not args.skip_predictability,
                "hashes": hashes,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
