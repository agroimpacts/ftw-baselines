"""Compare baseline chip-level instance measures, without rerunning predictions.

Run with ``uv run --with scikit-learn python -m research.instance_metrics.analyze_metric_complementarity
RUN [RUN ...] --out_dir NEW_DIRECTORY``.
"""

import argparse
import importlib.metadata
import json
import math
from copy import deepcopy
from dataclasses import asdict
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ftw_tools.settings import has_labeled_background
from ftw_tools.training.metrics import (
    InstanceStatistics,
    instance_scores_for_reporting,
    instance_statistics,
)
from research.instance_metrics.analyze_instances import load_runs
from scripts.instance_evaluation.compare_instance_methods import read_reference_ids

METRICS = (
    "object_precision",
    "object_recall",
    "sq",
    "pq",
    "recovery",
    "support",
    "rand_split_score",
    "rand_merge_score",
)
PAIRS = (
    ("object_recall", "recovery"),
    ("object_precision", "support"),
    ("pq", "recovery"),
    ("pq", "support"),
    ("rand_split_score", "rand_merge_score"),
)


def dimensionality(frame, scope, *, metrics=METRICS):
    """PCA on complete, nonconstant standardized scores; entropy effective rank."""
    finite = frame[list(metrics)].replace([np.inf, -np.inf], np.nan).dropna()
    columns = [name for name in metrics if finite[name].nunique() > 1]
    if len(finite) < 3 or len(columns) < 2:
        return [], []
    x = StandardScaler().fit_transform(finite[columns])
    model = PCA().fit(x)
    proportions = model.explained_variance_ratio_
    positive = proportions[proportions > 0]
    effective_rank = float(np.exp(-np.sum(positive * np.log(positive))))
    components = [
        {
            "scope": scope,
            "component": i + 1,
            "n": len(finite),
            "variance_ratio": float(value),
            "effective_rank": effective_rank,
        }
        for i, value in enumerate(proportions)
    ]
    loadings = [
        {
            "scope": scope,
            "component": i + 1,
            "metric": metric,
            "loading": float(
                model.components_[i, j] * np.sqrt(model.explained_variance_[i])
            ),
        }
        for i in range(len(proportions))
        for j, metric in enumerate(columns)
    ]
    return components, loadings


def disagreements(frame, scope, *, pairs=PAIRS, lower_is_better=()):
    """Use within-scope ranks; exclude ties at the quartile boundaries."""
    results, examples = [], []
    for first, second in pairs:
        pair = (
            frame[["country", "aoi_id", first, second]]
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
            .copy()
        )
        if len(pair) < 4:
            continue
        oriented = pair[[first, second]].copy()
        for name in lower_is_better:
            if name in oriented:
                oriented[name] = -oriented[name]
        ranks = oriented.rank(pct=True)
        low = ranks <= 0.25
        high = ranks > 0.75
        extreme = (low[first] & high[second]) | (high[first] & low[second])
        top_disagreement = high[first] != high[second]
        pair["rank_gap"] = (ranks[first] - ranks[second]).abs()
        pair["score_gap"] = pair[first] - pair[second]
        results.append(
            {
                "scope": scope,
                "first": first,
                "second": second,
                "n": len(pair),
                "spearman": pair[first].corr(pair[second], method="spearman"),
                "top_quartile_disagreement": float(top_disagreement.mean()),
                "opposite_extremes": float(extreme.mean()),
                "median_absolute_score_gap": float(pair.score_gap.abs().median()),
            }
        )
        for row in pair.nlargest(10, "rank_gap").to_dict("records"):
            examples.append(dict(scope=scope, first=first, second=second, **row))
    return results, examples


def predictability(
    frame, scope, grouped=False, *, metrics=METRICS, predictor_metrics=None
):
    """Out-of-fold linear and nonlinear reconstruction, without score imputation."""
    required = list(dict.fromkeys([*metrics, *(predictor_metrics or metrics)]))
    finite = frame[["country", *required]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(finite) < 20 or (grouped and finite.country.nunique() < 5):
        return []
    splitter = (
        GroupKFold(n_splits=5)
        if grouped
        else KFold(n_splits=5, shuffle=True, random_state=42)
    )
    folds = list(splitter.split(finite, groups=finite.country if grouped else None))
    results = []
    for target in metrics:
        predictors = [name for name in (predictor_metrics or metrics) if name != target]
        x, y = finite[predictors].to_numpy(), finite[target].to_numpy()
        if np.std(y) == 0:
            continue
        for kind in ("linear", "nonlinear"):
            estimated = np.empty(len(y))
            for train, test in folds:
                model = (
                    make_pipeline(StandardScaler(), Ridge(alpha=1.0))
                    if kind == "linear"
                    else HistGradientBoostingRegressor(
                        max_iter=100,
                        max_leaf_nodes=10,
                        min_samples_leaf=10,
                        random_state=42,
                    )
                )
                model.fit(x[train], y[train])
                estimated[test] = model.predict(x[test])
            results.append(
                {
                    "scope": scope,
                    "target": target,
                    "model": kind,
                    "n": len(y),
                    "cv": "held-out-country" if grouped else "held-out-chip",
                    "r2": r2_score(y, estimated),
                    "rmse": np.sqrt(mean_squared_error(y, estimated)),
                    "target_std": float(np.std(y)),
                }
            )
    return results


def matched_pq_examples(frame, scope, tolerance=0.02):
    """Find neighboring-PQ chips with different diagnostic scores."""
    rows = []
    for metric in ("recovery", "support", "rand_split_score", "rand_merge_score"):
        finite = (
            frame[["country", "aoi_id", "pq", metric]]
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
            .sort_values("pq")
            .reset_index(drop=True)
        )
        candidates = []
        for i in range(len(finite)):
            for j in range(i + 1, min(i + 12, len(finite))):
                if finite.at[j, "pq"] - finite.at[i, "pq"] > tolerance:
                    break
                gap = abs(finite.at[j, metric] - finite.at[i, metric])
                candidates.append((gap, i, j))
        for gap, i, j in sorted(candidates, reverse=True)[:10]:
            left, right = finite.iloc[i], finite.iloc[j]
            rows.append(
                {
                    "scope": scope,
                    "metric": metric,
                    "country_a": left.country,
                    "aoi_a": left.aoi_id,
                    "country_b": right.country,
                    "aoi_b": right.aoi_id,
                    "pq_a": left.pq,
                    "pq_b": right.pq,
                    "score_a": left[metric],
                    "score_b": right[metric],
                    "score_gap": gap,
                }
            )
    return rows


def analyze(run_dirs, out_dir, *, chip_keys=None, exclude_countries=()):
    """Validate comparable saved runs and write reproducible diagnostic tables."""
    out = Path(out_dir).expanduser().resolve()
    if out.exists():
        raise FileExistsError(out)
    table, names, inputs = load_runs(run_dirs)
    if chip_keys is not None:
        table = table.loc[
            [
                (country, aoi) in chip_keys
                for country, aoi in zip(table.country, table.aoi_id)
            ]
        ]
    if exclude_countries:
        table = table.loc[~table.country.isin(exclude_countries)]
    if not set(METRICS).issubset(names) or {i["split"] for i in inputs} != {"test"}:
        raise ValueError("Expected comparable test runs with all instance scores")
    if any(len(item["countries"]) != 1 for item in inputs):
        raise ValueError("Use one country per run")
    # FP-dependent measures are not evaluable for presence-only reference labels.
    full = table.loc[table.country.map(has_labeled_background)].copy()
    if full.empty:
        raise ValueError("No countries with labeled background")
    scores = []
    pca, loadings, differences, examples, predict, matched = [], [], [], [], [], []
    for scope, frame in [(country, part) for country, part in full.groupby("country")]:
        scores.append(
            {
                "scope": scope,
                "chips": len(frame),
                "complete": frame[list(METRICS)].notna().all(axis=1).sum(),
            }
        )
        a, b = dimensionality(frame, scope)
        pca.extend(a)
        loadings.extend(b)
        a, b = disagreements(frame, scope)
        differences.extend(a)
        examples.extend(b)
        predict.extend(predictability(frame, scope))
        matched.extend(matched_pq_examples(frame, scope))
    scores.append(
        {
            "scope": "all",
            "chips": len(full),
            "complete": full[list(METRICS)].notna().all(axis=1).sum(),
        }
    )
    a, b = dimensionality(full, "all")
    pca.extend(a)
    loadings.extend(b)
    # Pooled chip ranks can be driven by country size: country results above are primary.
    a, b = disagreements(full, "all")
    differences.extend(a)
    examples.extend(b)
    predict.extend(predictability(full, "all", grouped=True))
    matched.extend(matched_pq_examples(full, "all"))
    associations = []
    clusters = []
    for scope, frame in [("all", full), *full.groupby("country")]:
        for first, second in combinations(METRICS, 2):
            pair = frame[[first, second]].replace([np.inf, -np.inf], np.nan).dropna()
            associations.append(
                {
                    "scope": scope,
                    "first": first,
                    "second": second,
                    "n": len(pair),
                    "pearson": pair[first].corr(pair[second]),
                    "spearman": pair[first].corr(pair[second], method="spearman"),
                }
            )
        complete = frame[list(METRICS)].replace([np.inf, -np.inf], np.nan).dropna()
        correlation = complete.corr(method="spearman").abs()
        if len(complete) >= 3 and correlation.notna().all().all():
            distances = (1 - correlation).clip(lower=0).to_numpy(copy=True)
            np.fill_diagonal(distances, 0)
            for i, (left, right, distance, size) in enumerate(
                linkage(squareform(distances, checks=False), method="average"),
                start=len(METRICS),
            ):
                clusters.append(
                    {
                        "scope": scope,
                        "cluster": i,
                        "left": int(left),
                        "right": int(right),
                        "distance": distance,
                        "size": int(size),
                    }
                )
    out.mkdir(parents=True)
    (out / "inputs.json").write_text(
        json.dumps(
            {
                "runs": inputs,
                "metrics": METRICS,
                "software_versions": {
                    name: importlib.metadata.version(name)
                    for name in ("numpy", "pandas", "scikit-learn", "scipy")
                },
                "population": {
                    "shared_complete_cases": chip_keys is not None,
                    "excluded_countries": list(exclude_countries),
                    "included_chips": len(table),
                },
                "excluded_presence_only": sorted(
                    set(table.country) - set(full.country)
                ),
            },
            indent=2,
        )
        + "\n"
    )
    for filename, rows in (
        ("availability", scores),
        ("associations", associations),
        ("pca_components", pca),
        ("pca_loadings", loadings),
        ("disagreement", differences),
        ("discordant_chips", examples),
        ("predictability", predict),
        ("matched_pq", matched),
        ("clusters", clusters),
    ):
        pd.DataFrame(rows).to_csv(out / f"{filename}.csv", index=False)
    return len(inputs), len(full)


def rescore_baseline(run_dir, out_dir, *, allow_unscorable=False):
    """Rescore saved four-connected predictions, preserving supplied reference IDs."""
    run, out = Path(run_dir), Path(out_dir)
    if out.exists():
        raise FileExistsError(out)
    manifest = json.loads((run / "manifest.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    settings = manifest["settings"]
    if settings.get("prediction_connectivity") != 4 or not settings.get(
        "test_on_3_classes"
    ):
        raise ValueError("Expected a three-class, four-connected baseline")
    if settings.get("reference_mode", "semantic-components") != "semantic-components":
        raise ValueError("Expected original semantic-component reference runs")
    table = pd.read_parquet(run / "chips.parquet")
    pooled = InstanceStatistics()
    references = []
    failures = []
    statuses = []
    for index, chip in enumerate(table.itertuples(index=False)):
        with (
            rasterio.open(chip.reference) as ref,
            rasterio.open(run / chip.prediction) as pred,
        ):
            if (ref.shape, ref.transform, ref.crs) != (
                pred.shape,
                pred.transform,
                pred.crs,
            ):
                raise ValueError(f"Misaligned prediction: {chip.country}/{chip.aoi_id}")
            truth, prediction = ref.read(1), pred.read(1)
            supplied, path = read_reference_ids(chip.reference, truth, ref.profile)
        try:
            stats = instance_statistics(
                truth,
                prediction,
                iou_threshold=settings["iou_threshold"],
                prediction_connectivity=4,
                reference_connectivity=settings["reference_connectivity"],
                ignore_index=settings.get("ignore_index"),
                reference_labels=supplied,
            )
        except ValueError as error:
            if (
                not allow_unscorable
                or str(error) != "Reference ID foreground differs from semantic class 1"
            ):
                raise
            valid = np.isin(truth, (0, 1, 2))
            if settings.get("ignore_index") is not None:
                valid &= truth != settings["ignore_index"]
            failures.append(
                {
                    "country": chip.country,
                    "aoi_id": chip.aoi_id,
                    "reason": str(error),
                    "missing_instance_pixels": int(
                        np.count_nonzero(valid & (truth == 1) & (supplied == 0))
                    ),
                    "extra_instance_pixels": int(
                        np.count_nonzero(valid & (truth != 1) & (supplied > 0))
                    ),
                }
            )
            for key in [
                key
                for key in table
                if key.startswith("stat_") or key in summary["instance_scores"]
            ]:
                table.loc[table.index[index], key] = np.nan
            references.append(path)
            statuses.append("unscorable: reference foreground mismatch")
            continue
        pooled += stats
        for key, value in asdict(stats).items():
            table.loc[table.index[index], f"stat_{key}"] = value
        for key, value in instance_scores_for_reporting(
            stats, background_known=has_labeled_background(chip.country)
        ).items():
            table.loc[table.index[index], key] = value
        references.append(path)
        statuses.append("scored")
    table["reference_instances"] = references
    table["reference_status"] = statuses
    table["reference_mode"] = "dataset-instance-ids"
    # Artifacts point back to originals; no rasters/probabilities are copied.
    for column in ("prediction", "probabilities"):
        if column in table:
            table[column] = table[column].map(
                lambda value: (
                    str((run / value).resolve()) if isinstance(value, str) else value
                )
            )
    updated = deepcopy(manifest)
    updated["settings"]["reference_mode"] = "dataset-instance-ids"
    updated["source_run"] = str(run.resolve())
    updated["rescoring"] = {
        "prediction_method": "components-4",
        "reference_identity": "preserved supplied IDs",
        "inference_rerun": False,
        "unscorable_policy": "retain rows, null instance statistics/scores, report reasons; no reference fallback",
    }
    summary["instance_statistics"] = asdict(pooled)
    summary["instance_scores"] = {
        key: value if math.isfinite(value) else None
        for key, value in instance_scores_for_reporting(
            pooled,
            background_known=all(
                has_labeled_background(c) for c in settings["countries"]
            ),
        ).items()
    }
    summary["reference_mode"] = "dataset-instance-ids"
    summary["scored_chips"] = len(table) - len(failures)
    summary["unscorable_chips"] = failures
    summary["pooled_population"] = "scored chips only; see unscorable_chips"
    out.mkdir(parents=True)
    table.to_parquet(out / "chips.parquet", index=False)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    (out / "manifest.json").write_text(
        json.dumps(updated, indent=2, allow_nan=False) + "\n"
    )


def rerun_reference_analysis(baseline_dir, out_dir, *, resume=False):
    """Repeat the recorded cohort and isolate population/Denmark sensitivity."""
    baseline, out = Path(baseline_dir).resolve(), Path(out_dir).resolve()
    if out.exists() and not resume:
        raise FileExistsError(out)
    recorded = json.loads((baseline / "inputs.json").read_text())
    original_runs = [Path(item["run_dir"]) for item in recorded["runs"]]
    original, _, verified_inputs = load_runs(original_runs)
    for saved, current in zip(recorded["runs"], verified_inputs):
        if any(
            saved[key] != current[key] for key in ("countries", "split", "chip_count")
        ):
            raise ValueError("Recorded analysis inputs no longer match source runs")
    rescored = []
    for run in original_runs:
        destination = out / "rescored-runs" / run.name
        if destination.exists() and resume:
            manifest = json.loads((destination / "manifest.json").read_text())
            source_manifest = json.loads((run / "manifest.json").read_text())
            if (
                manifest.get("source_run") != str(run.resolve())
                or manifest["settings"].get("reference_mode") != "dataset-instance-ids"
                or manifest.get("checkpoint_sha256")
                != source_manifest.get("checkpoint_sha256")
                or {
                    key: value
                    for key, value in manifest["settings"].items()
                    if key != "reference_mode"
                }
                != {
                    key: value
                    for key, value in source_manifest["settings"].items()
                    if key != "reference_mode"
                }
            ):
                raise ValueError("Cannot resume incompatible rescoring artifacts")
            load_runs([destination])
        else:
            rescore_baseline(run, destination, allow_unscorable=True)
        rescored.append(destination)
        print(f"Rescored {run.name}", flush=True)
    updated, _, _ = load_runs(rescored)
    keys = ["country", "aoi_id"]
    before = original.set_index(keys)
    after = updated.set_index(keys).reindex(before.index)
    if set(map(tuple, updated[keys].to_numpy())) != set(before.index):
        raise ValueError("Rescoring changed the chip population")
    complete = np.isfinite(before[list(METRICS)].to_numpy(float)).all(
        axis=1
    ) & np.isfinite(after[list(METRICS)].to_numpy(float)).all(axis=1)
    shared = set(before.index[complete])
    analyze(rescored, out / "full")
    analyze(
        original_runs,
        out / "comparison/shared-complete/semantic-components",
        chip_keys=shared,
    )
    analyze(
        rescored,
        out / "comparison/shared-complete/dataset-instance-ids",
        chip_keys=shared,
    )
    analyze(
        original_runs,
        out / "comparison/without-denmark/semantic-components",
        exclude_countries=("denmark",),
    )
    analyze(
        rescored,
        out / "comparison/without-denmark/dataset-instance-ids",
        exclude_countries=("denmark",),
    )
    analyze(
        original_runs,
        out / "comparison/shared-complete-without-denmark/semantic-components",
        chip_keys=shared,
        exclude_countries=("denmark",),
    )
    analyze(
        rescored,
        out / "comparison/shared-complete-without-denmark/dataset-instance-ids",
        chip_keys=shared,
        exclude_countries=("denmark",),
    )
    changes = []
    for metric in METRICS:
        a, b = before[metric].to_numpy(float), after[metric].to_numpy(float)
        finite = np.isfinite(a) & np.isfinite(b)
        for country in ["all", *sorted(original.country.unique())]:
            chosen = finite & (
                before.index.get_level_values("country")
                .map(has_labeled_background)
                .to_numpy()
                if country == "all"
                else before.index.get_level_values("country") == country
            )
            delta = b[chosen] - a[chosen]
            changes.append(
                {
                    "scope": country,
                    "metric": metric,
                    "n": len(delta),
                    "old_mean": float(np.mean(a[chosen])) if len(delta) else np.nan,
                    "new_mean": float(np.mean(b[chosen])) if len(delta) else np.nan,
                    "mean_change": float(np.mean(delta)) if len(delta) else np.nan,
                    "median_change": float(np.median(delta)) if len(delta) else np.nan,
                }
            )
    pd.DataFrame(changes).to_csv(out / "comparison/metric_changes.csv", index=False)
    (out / "comparison/populations.json").write_text(
        json.dumps(
            {
                "baseline_analysis": str(baseline),
                "run_count": len(original_runs),
                "chip_count": len(original),
                "eligible_background_chips": int(
                    original.country.map(has_labeled_background).sum()
                ),
                "unscorable_chip_count": int(
                    updated.get("reference_status", pd.Series(dtype=str))
                    .fillna("scored")
                    .ne("scored")
                    .sum()
                ),
                "shared_complete_count": len(shared),
                "denmark_retained_in_primary": True,
                "pixel_scores_unchanged": True,
            },
            indent=2,
        )
        + "\n"
    )
    return len(original_runs), len(updated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="*", type=Path)
    parser.add_argument(
        "--rerun-reference-analysis",
        type=Path,
        help="Original analysis directory whose recorded cohort is rescored",
    )
    parser.add_argument("--out_dir", required=True, type=Path)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse verified rescored runs after an interrupted reference rerun",
    )
    args = parser.parse_args()
    if args.rerun_reference_analysis:
        if args.runs:
            parser.error("Use recorded inputs or explicit runs, not both")
        runs, chips = rerun_reference_analysis(
            args.rerun_reference_analysis, args.out_dir, resume=args.resume
        )
    else:
        runs, chips = analyze(args.runs, args.out_dir)
    population = "input" if args.rerun_reference_analysis else "eligible"
    print(f"Analyzed {runs} runs and {chips} {population} chips")


if __name__ == "__main__":
    main()
