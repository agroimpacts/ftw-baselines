"""Diagnose components-4 scores against PQ using saved comparison artifacts.

Usage: uv run python -m research.instance_metrics.archive.diagnose_component_metrics COMPARISON [COMPARISON ...] --out_dir OUT
Only countries with labeled background are accepted. Inputs and outputs are never overwritten.
"""

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from ftw_tools.settings import has_labeled_background
from ftw_tools.training.metrics import InstanceStatistics, instance_label_matches
from scripts.instance_evaluation.visualize_instances import (
    LABEL_COLORS,
    MATCH_COLORS,
    draw_object_contours,
    format_instance_scores,
    orient_for_display,
)

METHOD = "components-4"
SIZES = (4, 16, 64, 256)
SIZE_LABELS = ("1-4", "5-16", "17-64", "65-256", ">256")
SCORES = (
    "object_recall", "object_precision", "object_f1", "rq", "sq", "pq", "recovery",
    "support", "rand_split_score", "rand_merge_score",
)


def _bin(area):
    return SIZE_LABELS[np.searchsorted(SIZES, area)]


def _fields(truth, labels, *, threshold, ignore_index, connectivity):
    gt, pred, matched_gt, matched_pred, stats = instance_label_matches(
        truth, labels, iou_threshold=threshold, ignore_index=ignore_index,
        reference_connectivity=connectivity,
    )
    ng, npred = int(gt.max()), int(pred.max())
    areas_g = np.bincount(gt.ravel(), minlength=ng + 1)[1:]
    areas_p = np.bincount(pred.ravel(), minlength=npred + 1)[1:]
    overlaps = np.bincount(
        (pred.astype(np.int64) * (ng + 1) + gt).ravel(),
        minlength=(npred + 1) * (ng + 1),
    ).reshape(npred + 1, ng + 1)[1:, 1:]
    unions = areas_p[:, None] + areas_g[None, :] - overlaps
    ious = np.divide(overlaps, unions, out=np.zeros(overlaps.shape), where=unions > 0)

    def rows(areas, matrix, matches, axis):
        result = []
        for index, area in enumerate(areas):
            scores = matrix[:, index] if axis == 0 else matrix[index, :]
            intersections = overlaps[:, index] if axis == 0 else overlaps[index, :]
            best = int(np.argmax(scores)) if len(scores) else -1
            result.append({
                "id": index + 1, "pixels": int(area), "size_bin": _bin(area),
                "best_partner_id": best + 1 if intersections.size and intersections[best] else None,
                "best_iou": float(scores[best]) if best >= 0 else 0.0,
                "best_intersection_pixels": int(intersections[best]) if best >= 0 else 0,
                "overlapping_partners": int(np.count_nonzero(intersections)),
                "matched": index + 1 in matches,
                "foreground_overlap_pixels": int(intersections.sum()),
                "outside_other_foreground_pixels": int(area - intersections.sum()),
            })
        return result

    references = rows(areas_g, ious, matched_gt, 0)
    predictions = rows(areas_p, ious, matched_pred, 1)
    return gt, pred, references, predictions, stats, matched_gt, matched_pred


def _check(row, stats):
    for key, value in asdict(stats).items():
        saved = getattr(row, f"stat_{key}")
        if not np.isclose(saved, value, rtol=1e-8, atol=1e-5):
            raise ValueError(f"Statistics disagree on {row.country}/{row.aoi_id}: {key}")
    for key in SCORES:
        saved, computed = getattr(row, key), stats.scores()[key]
        if not (np.isclose(saved, computed, rtol=1e-8, atol=1e-5) or
                (pd.isna(saved) and pd.isna(computed))):
            raise ValueError(f"Score disagrees on {row.country}/{row.aoi_id}: {key}")


def _candidates(chips, per_case, *, high_score=0.7, agreement_tolerance=0.1):
    """Country-balanced shortlists; selections are hypotheses, not diagnoses."""
    if not 0 <= high_score <= 1 or not 0 <= agreement_tolerance <= 1:
        raise ValueError("high_score and agreement_tolerance must be between 0 and 1")
    cases = (
        ("recovery_above_recall", "recovery", "object_recall"),
        ("recall_above_recovery", "object_recall", "recovery"),
        ("support_above_precision", "support", "object_precision"),
        ("precision_above_support", "object_precision", "support"),
        ("recovery_above_pq", "recovery", "pq"),
        ("support_above_pq", "support", "pq"),
        ("split_above_merge", "rand_split_score", "rand_merge_score"),
        ("merge_above_split", "rand_merge_score", "rand_split_score"),
    )
    result = []
    for country, group in chips.groupby("country", sort=True):
        for name, first, second in cases:
            finite = group.replace([np.inf, -np.inf], np.nan).dropna(subset=[first, second])
            finite = finite.assign(gap=finite[first] - finite[second])
            for row in finite.sort_values(["gap", "aoi_id"], ascending=[False, True]).head(per_case).itertuples():
                result.append({"country": country, "aoi_id": row.aoi_id,
                               "case": name, "gap": row.gap, "pq": row.pq,
                               "rq": row.rq, "sq": row.sq, "recovery": row.recovery,
                               "support": row.support})
        # Low PQ with contrasting RQ/SQ, or high merge with little recovery.
        for name, order in (("low_rq_high_sq", [True, False]),
                            ("high_rq_low_sq", [False, True])):
            finite = group.dropna(subset=["rq", "sq", "pq"])
            finite = finite.loc[finite.pq <= finite.pq.median()]
            for row in finite.sort_values(["rq", "sq"], ascending=order).head(per_case).itertuples():
                result.append({"country": country, "aoi_id": row.aoi_id,
                               "case": name, "gap": row.sq - row.rq,
                               "pq": row.pq, "rq": row.rq, "sq": row.sq,
                               "recovery": row.recovery, "support": row.support})
        finite = group.dropna(subset=["rand_merge_score", "recovery", "pq"])
        finite = finite.assign(gap=finite.rand_merge_score - finite.recovery)
        for row in finite.sort_values("gap", ascending=False).head(per_case).itertuples():
            result.append({"country": country, "aoi_id": row.aoi_id,
                           "case": "high_merge_low_coverage", "gap": row.gap,
                           "pq": row.pq, "rq": row.rq, "sq": row.sq,
                           "recovery": row.recovery, "support": row.support})
        # Pair chips at nearly the same PQ: do the area or topology scores
        # distinguish them? Record both members so the figures can be compared.
        for name, measure, controls in (
            ("same_pq_different_recovery", "recovery", ("pq",)),
            ("same_pq_different_support", "support", ("pq",)),
            ("same_pq_area_different_merge", "rand_merge_score", ("pq", "recovery", "support")),
            ("same_pq_area_different_split", "rand_split_score", ("pq", "recovery", "support")),
        ):
            finite = group.dropna(subset=[measure, *controls]).sort_values("aoi_id")
            values = finite[[measure, *controls]].to_numpy()
            pairs = []
            for i in range(len(finite)):
                for j in range(i + 1, len(finite)):
                    if all(abs(values[i, k + 1] - values[j, k + 1]) <= 0.025 for k in range(len(controls))):
                        pairs.append((abs(values[i, 0] - values[j, 0]), i, j))
            used = set()
            for gap, i, j in sorted(pairs, reverse=True):
                if i in used or j in used or gap < 0.1:
                    continue
                used.update((i, j))
                first, second = finite.iloc[i], finite.iloc[j]
                for row, partner in ((first, second), (second, first)):
                    result.append({"country": country, "aoi_id": row.aoi_id,
                                   "case": name, "paired_aoi_id": partner.aoi_id,
                                   "gap": gap, "pq": row.pq, "rq": row.rq, "sq": row.sq,
                                   "recovery": row.recovery, "support": row.support})
                if len(used) >= 2 * per_case:
                    break
        # A positive-control gallery: agreement alone can be low-low, so
        # require both scores high as well as close. PQ is a separate gate.
        for name, first, second in (
            ("high_recall_recovery_agree", "object_recall", "recovery"),
            ("high_precision_support_agree", "object_precision", "support"),
        ):
            finite = group.dropna(subset=[first, second, "pq"])
            finite = finite.loc[
                finite[[first, second]].min(axis=1).ge(high_score)
                & (finite[first] - finite[second]).abs().le(agreement_tolerance)
            ]
            for row in finite.sort_values(["pq", "aoi_id"], ascending=[False, True]).head(per_case).itertuples():
                result.append({"country": country, "aoi_id": row.aoi_id,
                               "case": name, "gap": abs(getattr(row, first) - getattr(row, second))})
        finite = group.dropna(subset=["pq", "object_recall", "recovery", "object_precision", "support"])
        finite = finite.loc[
            finite[["pq", "object_recall", "recovery", "object_precision", "support"]].min(axis=1).ge(high_score)
            & (finite.object_recall - finite.recovery).abs().le(agreement_tolerance)
            & (finite.object_precision - finite.support).abs().le(agreement_tolerance)
        ]
        for row in finite.sort_values(["pq", "aoi_id"], ascending=[False, True]).head(per_case).itertuples():
            result.append({"country": country, "aoi_id": row.aoi_id,
                           "case": "high_pq_both_pairs_agree", "gap": max(
                               abs(row.object_recall - row.recovery),
                               abs(row.object_precision - row.support),
                           )})
    selections = pd.DataFrame(result).drop_duplicates(["country", "aoi_id", "case"])
    # One source of truth for every reported metric; do not keep stale copies
    # of the few scores used while constructing individual shortlist rows.
    selections = selections.drop(columns=list(SCORES), errors="ignore")
    return selections.merge(chips[["country", "aoi_id", *SCORES,
                                   "stat_tp", "stat_fp", "stat_fn"]],
                            on=["country", "aoi_id"], validate="many_to_one")


def _figure(record, destination):
    truth, semantic, gt, predicted, matches_g, matches_p, images, transform, normalization, ignore_index, row = record
    fig, axes = plt.subplots(1, 6, figsize=(20, 6))
    for ax, image, title in zip(axes[:2], images, ("Window A", "Window B")):
        ax.imshow(np.clip(orient_for_display(image, transform) / normalization, 0, 1))
        ax.set_title(title)
    palette = ListedColormap(LABEL_COLORS)
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], palette.N)
    for ax, array, title in ((axes[2], truth, "Reference"),
                             (axes[3], semantic, "Raw prediction (0/1/2)")):
        ax.imshow(orient_for_display(array, transform), cmap=palette, norm=norm,
                  interpolation="nearest")
        ax.set_title(title)
    ignored = ~np.isin(truth, (0, 1, 2))
    if ignore_index is not None:
        ignored |= truth == ignore_index
    overlay = np.zeros((*truth.shape, 4), dtype=float)
    overlay[ignored] = (1, 1, 1, 0.75)
    axes[3].imshow(orient_for_display(overlay, transform), interpolation="nearest")
    axes[4].imshow(orient_for_display(np.ma.masked_where(predicted == 0, predicted), transform),
                   cmap="nipy_spectral", interpolation="nearest")
    axes[4].set_title("Predicted instances (IDs)")
    axes[5].imshow(np.full(truth.shape, 0.96), cmap="gray", vmin=0, vmax=1,
                   interpolation="nearest")
    axes[5].set_title("Object outlines (TP / FP / FN)")
    for name, labels, ids in (
        ("FN", gt, np.setdiff1d(np.arange(1, gt.max() + 1), matches_g)),
        ("FP", predicted, np.setdiff1d(np.arange(1, predicted.max() + 1), matches_p)),
        ("TP", predicted, matches_p),
    ):
        draw_object_contours(axes[5], orient_for_display(labels, transform), ids,
                             MATCH_COLORS[name], linewidth=3 if name == "FN" else 1.4)
    for ax in axes:
        ax.set_axis_off()
    fig.suptitle(f"{row.country}/{row.aoi_id} — components-4", y=0.99)
    fig.legend(
        handles=[Patch(facecolor=color, edgecolor="gray", label=label)
                 for color, label in zip(
                     LABEL_COLORS, ("Background", "Field interior", "Boundary", "Ignored")
                 )] + [Line2D([0], [0], color=color, linewidth=3 if status == "FN" else 1.4,
                              label=f"{status} ({'reference' if status == 'FN' else 'prediction'})")
                       for status, color in MATCH_COLORS.items()],
        loc="upper center", bbox_to_anchor=(0.5, 0.96), ncol=7, frameon=False,
    )
    fig.subplots_adjust(left=0.01, right=0.99, top=0.83, bottom=0.23, wspace=0.02)
    for x, text in zip((0.04, 0.52), format_instance_scores(row)):
        fig.text(x, 0.05, text, family="monospace", fontsize=10, va="bottom")
    fig.savefig(destination, dpi=150)
    plt.close(fig)


def _country_summary(chips):
    """Pool additive statistics; retain chip-level medians as separate context."""
    counts = []
    for country, group in chips.groupby("country"):
        pooled = InstanceStatistics(**{
            name: group[f"stat_{name}"].sum()
            for name in InstanceStatistics.__dataclass_fields__
        }).scores()
        counts.append({"country": country, "chips": len(group),
                       "finite_pq": int(group.pq.notna().sum()),
                       "finite_sq": int(group.sq.notna().sum()),
                       "pooled_object_precision": pooled["object_precision"],
                       "pooled_object_recall": pooled["object_recall"],
                       "pooled_rq": pooled["rq"], "pooled_sq": pooled["sq"],
                       "pooled_pq": pooled["pq"],
                       "pooled_recovery": pooled["recovery"],
                       "pooled_support": pooled["support"],
                       "pooled_rand_split_score": pooled["rand_split_score"],
                       "pooled_rand_merge_score": pooled["rand_merge_score"],
                       "median_chip_pq": group.pq.median(),
                       "median_chip_recovery": group.recovery.median(),
                       "median_chip_support": group.support.median(),
                       "tp": int(group.stat_tp.sum()), "fp": int(group.stat_fp.sum()),
                       "fn": int(group.stat_fn.sum())})
    return counts


def _size_summary(reference, prediction):
    """Source-side bins: do not attribute cross-bin pairs to a per-bin PQ."""
    size_rows = []
    for side, frame in (("reference", reference), ("prediction", prediction)):
        for country, group in frame.groupby("country"):
            total_area = group.pixels.sum()
            for bin_name in SIZE_LABELS:
                subset = group.loc[group.size_bin == bin_name]
                size_rows.append({"country": country, "side": side, "size_bin": bin_name,
                                  "objects": len(subset), "pixels": int(subset.pixels.sum()),
                                  "area_share": subset.pixels.sum() / total_area if total_area else np.nan,
                                  "match_rate": subset.matched.mean() if len(subset) else np.nan,
                                  "mean_best_iou": subset.best_iou.mean(),
                                  "median_best_iou": subset.best_iou.median(),
                                  "area_weighted_best_iou": (
                                      np.average(subset.best_iou, weights=subset.pixels)
                                      if len(subset) else np.nan
                                  ),
                                  "matched_objects": int(subset.matched.sum()),
                                  "mean_matched_best_iou": subset.loc[subset.matched, "best_iou"].mean(),
                                  "near_threshold_unmatched": int((~subset.matched &
                                      subset.best_iou.ge(0.4)).sum())})
    return pd.DataFrame(size_rows)


def diagnose(directories, out_dir, *, per_case=2, high_score=0.7,
             agreement_tolerance=0.1, figures=True):
    """Validate all chips, then write a fresh reproducible analysis directory."""
    if per_case < 1:
        raise ValueError("per_case must be positive")
    out = Path(out_dir).expanduser().resolve()
    if out.exists():
        raise FileExistsError(out)
    inputs, chip_frames, refs, preds, records = [], [], [], [], {}
    for directory in directories:
        directory = Path(directory).expanduser().resolve()
        summary = json.loads((directory / "summary.json").read_text())
        country = summary["country"]
        if not has_labeled_background(country):
            raise ValueError(f"Country lacks labeled background: {country}")
        if summary["split"] != "test" or summary["reference_connectivity"] != 4 or summary["iou_threshold"] != 0.5:
            raise ValueError(f"Expected test, 4-connected reference, IoU 0.5: {directory}")
        if METHOD not in summary["methods"]:
            raise ValueError(f"Missing {METHOD}: {directory}")
        run = Path(summary["source_run"]).expanduser().resolve()
        settings = json.loads((run / "manifest.json").read_text())["settings"]
        source = pd.read_parquet(run / "chips.parquet")
        table = pd.read_parquet(directory / "chips.parquet")
        if (len(table) != summary["chip_count"] * len(summary["methods"])
                or table.duplicated(["country", "aoi_id", "method"]).any()):
            raise ValueError(f"Incomplete or duplicate comparison: {directory}")
        baseline = table.loc[table.method == METHOD].copy()
        if (len(baseline) != summary["chip_count"] or set(baseline.country) != {country}
                or source.duplicated(["country", "aoi_id"]).any()
                or set(zip(source.country, source.aoi_id)) != set(zip(baseline.country, baseline.aoi_id))):
            raise ValueError(f"Comparison/source chips disagree: {directory}")
        source = source.set_index(["country", "aoi_id"])
        for row in baseline.itertuples(index=False):
            chip = source.loc[row.country, row.aoi_id]
            if not isinstance(row.labels, str):
                raise ValueError(f"Missing saved labels: {country}/{row.aoi_id}")
            with rasterio.open(chip.reference) as raster:
                truth, grid = raster.read(1), (raster.shape, raster.transform, raster.crs)
            with rasterio.open(directory / row.labels) as raster:
                if (raster.shape, raster.transform, raster.crs) != grid:
                    raise ValueError(f"Misaligned labels: {country}/{row.aoi_id}")
                labels = raster.read(1)
            gt, pred, reference, prediction, stats, mg, mp = _fields(
                truth, labels, threshold=summary["iou_threshold"],
                ignore_index=settings.get("ignore_index"), connectivity=4,
            )
            _check(row, stats)
            key = (country, row.aoi_id)
            for target, objects in ((refs, reference), (preds, prediction)):
                target.extend({"country": country, "aoi_id": row.aoi_id, **obj} for obj in objects)
            records[key] = (directory, run, chip, row, grid)
        chip_frames.append(baseline)
        inputs.append({"directory": str(directory), "source_run": str(run),
                       "country": country, "chips": len(baseline),
                       "checkpoint_sha256": summary["checkpoint_sha256"]})
    if not inputs or len({item["country"] for item in inputs}) != len(inputs):
        raise ValueError("Provide distinct eligible countries")
    if len({item["checkpoint_sha256"] for item in inputs}) != 1:
        raise ValueError("Comparisons use different checkpoints")
    chips = pd.concat(chip_frames, ignore_index=True)
    reference = pd.DataFrame(refs)
    prediction = pd.DataFrame(preds)
    candidates = _candidates(chips, per_case, high_score=high_score,
                             agreement_tolerance=agreement_tolerance)
    counts = _country_summary(chips)
    sizes = _size_summary(reference, prediction)
    manifest = {"method": METHOD, "split": "test", "threshold": 0.5,
                "reference_connectivity": 4, "size_bin_upper_pixels": list(SIZES),
                 "per_case": per_case, "pair_tolerance": 0.025,
                 "pair_minimum_gap": 0.1, "inputs": inputs,
                 "high_score": high_score, "agreement_tolerance": agreement_tolerance,
                 "note": "Exploratory selections; scores use saved chip statistics. No test-set tuning."}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{out.name}-", dir=out.parent) as temporary:
        work = Path(temporary)
        chips.to_parquet(work / "chip_diagnostics.parquet", index=False)
        reference.to_parquet(work / "reference_fields.parquet", index=False)
        prediction.to_parquet(work / "predicted_fields.parquet", index=False)
        pd.DataFrame(counts).to_csv(work / "country_summary.csv", index=False)
        sizes.to_csv(work / "size_bin_summary.csv", index=False)
        if figures:
            (work / "figures").mkdir()
            for country, aoi_id in candidates[["country", "aoi_id"]].drop_duplicates().itertuples(index=False, name=None):
                directory, run, chip, row, grid = records[(country, aoi_id)]
                with rasterio.open(chip.reference) as src:
                    truth = src.read(1)
                with rasterio.open(directory / row.labels) as src:
                    labels = src.read(1)
                with rasterio.open(run / chip.prediction) as src:
                    if (src.shape, src.transform, src.crs) != grid:
                        raise ValueError(f"Misaligned semantic mask: {country}/{aoi_id}")
                    semantic = src.read(1)
                gt, pred, _, _, _, mg, mp = _fields(truth, labels, threshold=0.5,
                    ignore_index=json.loads((run / "manifest.json").read_text())["settings"].get("ignore_index"),
                    connectivity=4)
                images = []
                for name in ("window_a", "window_b"):
                    with rasterio.open(chip[name]) as src:
                        images.append(src.read([1, 2, 3]).transpose(1, 2, 0))
                settings = json.loads((run / "manifest.json").read_text())["settings"]
                normalization = settings.get("normalization_constant", 3000)
                relative = Path("figures") / f"{country}_{aoi_id}.png"
                scores = SimpleNamespace(**{
                    **row._asdict(),
                    "pixel_binary_interior_iou_class_1": chip.get(
                        "pixel_binary_interior_iou_class_1", float("nan")
                    ),
                })
                _figure((truth, semantic, gt, pred, mg, mp, images, grid[1], normalization,
                         settings.get("ignore_index"), scores), work / relative)
                candidates.loc[(candidates.country == country) & (candidates.aoi_id == aoi_id), "figure"] = str(relative)
        candidates.to_csv(work / "case_candidates.csv", index=False)
        pd.DataFrame(columns=["country", "aoi_id", "case", "finding", "label_fragment_checked", "reference_fragments", "uncertainty"]).to_csv(work / "case_review.csv", index=False)
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        headers = list(counts[0])
        country_table = ["| " + " | ".join(headers) + " |",
                         "| " + " | ".join("---" for _ in headers) + " |"]
        country_table.extend("| " + " | ".join(
            f"{item[key]:.3f}" if isinstance(item[key], (float, np.floating)) else str(item[key])
            for key in headers
        ) + " |" for item in counts)
        sampled = candidates.sort_values("gap", ascending=False).drop_duplicates("case")
        case_table = ["| Selection hypothesis | Chip | Precision | Recall | RQ | SQ | PQ | Recovery | Support |",
                      "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        def fmt(value):
            return f"{value:.3f}" if pd.notna(value) else "—"

        for row in sampled.itertuples():
            chip_link = (f"[{row.country}/{row.aoi_id}]({row.figure})" if figures
                         else f"{row.country}/{row.aoi_id}")
            chip_row = chips.loc[(chips.country == row.country) & (chips.aoi_id == row.aoi_id)].iloc[0]
            case_table.append(f"| {row.case} | {chip_link} | {fmt(chip_row.object_precision)} | {fmt(chip_row.object_recall)} | {fmt(row.rq)} | {fmt(row.sq)} | {fmt(row.pq)} | {fmt(row.recovery)} | {fmt(row.support)} |")
        tiny = sizes.loc[sizes.size_bin == "1-4", ["country", "side", "objects", "area_share", "match_rate"]]
        tiny_table = ["| Country | Side | 1–4 pixel objects | Area share | Match rate |",
                      "| --- | --- | ---: | ---: | ---: |"]
        for row in tiny.itertuples():
            tiny_table.append(f"| {row.country} | {row.side} | {row.objects} | {row.area_share:.3f} | {row.match_rate:.3f} |")
        lines = ["# Components-4 metric diagnostics", "", f"{len(chips)} test chips across {len(inputs)} countries; no presence-only countries.",
                 "", "## Reading the measures", "", "PQ = RQ × SQ: RQ counts matches and misses equally; SQ averages IoU only across matches. Recovery and support weight best IoU by reference and prediction area, including unmatched objects. Rand scores describe overlap concentration, not detection quality. SQ is undefined without matches, even where PQ is zero.",
                 "", "## Country summary", "", *country_table,
                 "", "Pooled scores (including Rand split/merge) use summed sufficient statistics; median chip scores are separate descriptors, not pooled scores. TP/FP/FN are summed counts; countries have different chip populations.",
                 "`finite_pq` is the number of chips whose PQ is defined (chips with at least one object on either side); `finite_sq` counts chips with at least one qualifying match. Empty-both chips have undefined PQ; SQ is undefined without matches. These counts are not the denominators of pooled PQ or SQ.",
                 "", "## Small-component check", "", *tiny_table,
                 "", "These count/area differences can suggest a size effect; small labels are not necessarily artifacts. `size_bin_summary.csv` reports per-bin mean best IoU, area-weighted best IoU, and matched-only mean best IoU. The latter is SQ-like within one side's bin, not per-bin PQ. Reference match rate is recall-like; prediction match rate is precision-like. Per-bin Rand and PQ are not defined here: cross-bin matches make naive bin assignment ambiguous.",
                 "", "## Review queue", "", f"{len(candidates)} case hypotheses in `case_candidates.csv`; figures are in `figures/`.",
                 "High-agreement examples require both measures ≥ " + f"{high_score:.2f}" + " and their gap ≤ " + f"{agreement_tolerance:.2f}" + "; high-PQ examples additionally require PQ ≥ the same threshold and both pairs to agree. A country may have no qualifying chips.",
                 "", *case_table, "",
                 "Review imagery and masks and record findings in `case_review.csv`. A small reference is not automatically a rasterization artifact.",
                 "", "## Limits", "", "The shortlist is exploratory, not a validated failure-mode census. Compare field-size bins in `size_bin_summary.csv`; inspect `reference_fields.parquet` and `predicted_fields.parquet` before attributing a gap to field size, threshold, splits or merges. Chip objects are not stitched across chip boundaries. Do not select Phase 4 settings from test examples."]
        (work / "report.md").write_text("\n".join(lines) + "\n")
        work.rename(out)
    return len(chips)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparisons", nargs="+", type=Path)
    parser.add_argument("--out_dir", required=True, type=Path)
    parser.add_argument("--per_case", type=int, default=2)
    parser.add_argument("--high_score", type=float, default=0.7)
    parser.add_argument("--agreement_tolerance", type=float, default=0.1)
    parser.add_argument("--no_figures", action="store_true")
    args = parser.parse_args()
    print(f"Diagnosed {diagnose(args.comparisons, args.out_dir, per_case=args.per_case, high_score=args.high_score, agreement_tolerance=args.agreement_tolerance, figures=not args.no_figures)} chips")


if __name__ == "__main__":
    main()
