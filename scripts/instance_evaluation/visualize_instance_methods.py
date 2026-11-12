"""Render matched instance labels from a saved method comparison.

Usage: python -m scripts.instance_evaluation.visualize_instance_methods COMPARISON --method METHOD
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

from ftw_tools.settings import has_labeled_background
from ftw_tools.training.metrics import FP_DEPENDENT_SCORES, instance_label_matches
from scripts.instance_evaluation.visualize_instances import (
    MATCH_COLORS,
    draw_object_contours,
    orient_for_display,
)


def select_method_chips(table, method, baseline, chips, metric, limit):
    """Pair methods by country/AOI and rank by absolute score change."""
    keys = ["country", "aoi_id"]
    if table.duplicated([*keys, "method"]).any():
        raise ValueError("Duplicate country/AOI/method rows")
    methods = set(table.method)
    if method not in methods or baseline not in methods:
        raise ValueError(f"Unknown method: {method} or {baseline}")
    selected = table.loc[table.method == method].set_index(keys)
    reference = table.loc[table.method == baseline].set_index(keys)
    if not selected.index.equals(reference.index):
        if set(selected.index) != set(reference.index):
            raise ValueError("Methods do not contain the same chips")
        reference = reference.reindex(selected.index)
    if metric not in selected or not pd.api.types.is_numeric_dtype(selected[metric]):
        raise ValueError(f"Not a numeric method score: {metric}")
    if metric in FP_DEPENDENT_SCORES:
        unknown_background = [
            not has_labeled_background(country) for country, _ in selected.index
        ]
        selected.loc[unknown_background, metric] = np.nan
        reference.loc[unknown_background, metric] = np.nan
    selected = selected.assign(delta=selected[metric] - reference[metric])
    if chips:
        keys_to_plot = [tuple(chip.split("/", 1)) for chip in chips]
        if any(len(key) != 2 or key not in selected.index for key in keys_to_plot):
            raise ValueError("Choose existing chips as COUNTRY/AOI_ID")
        if len(set(keys_to_plot)) != len(keys_to_plot):
            raise ValueError("Duplicate chip selection")
        return selected.loc[keys_to_plot].reset_index()
    if limit < 1:
        raise ValueError("Limit must be positive")
    return (
        selected.replace([np.inf, -np.inf], np.nan)
        .dropna(subset=["delta"])
        .assign(rank=lambda rows: rows.delta.abs())
        .sort_values("rank", ascending=False)
        .head(limit)
        .reset_index()
    )


def render(
    comparison,
    method,
    *,
    baseline="components-4",
    chips=(),
    metric="pq",
    limit=10,
    generate_missing_labels=False,
):
    comparison = Path(comparison).expanduser().resolve()
    summary = json.loads((comparison / "summary.json").read_text())
    run = Path(summary["source_run"])
    settings = json.loads((run / "manifest.json").read_text())["settings"]
    source = pd.read_parquet(run / "chips.parquet").set_index(["country", "aoi_id"])
    table = pd.read_parquet(comparison / "chips.parquet")
    rows = select_method_chips(table, method, baseline, chips, metric, limit)
    if generate_missing_labels:
        from scripts.instance_evaluation.compare_instance_methods import (
            ensure_selected_labels,
        )

        ensure_selected_labels(
            comparison, set(zip(rows.country, rows.aoi_id)), {method, baseline}
        )
        table = pd.read_parquet(comparison / "chips.parquet")
        rows = select_method_chips(table, method, baseline, chips, metric, limit)
    out = comparison / "figures" / method / ("selected" if chips else f"delta-{metric}")
    for row in rows.itertuples(index=False):
        destination = out / f"{row.country}_{row.aoi_id}.png"
        if destination.exists():
            raise FileExistsError(destination)
        chip = source.loc[row.country, row.aoi_id]
        with rasterio.open(chip.reference) as ref:
            truth, transform, crs = ref.read(1), ref.transform, ref.crs
            reference_profile = ref.profile.copy()
        reference_labels = None
        if (
            summary.get("reference_mode", "semantic-components")
            == "dataset-instance-ids"
        ):
            from scripts.instance_evaluation.compare_instance_methods import (
                read_reference_ids,
            )

            reference_labels, _ = read_reference_ids(
                chip.reference, truth, reference_profile
            )
        with rasterio.open(run / chip.prediction) as pred:
            if (pred.shape, pred.transform, pred.crs) != (truth.shape, transform, crs):
                raise ValueError("Prediction grid differs from reference")
            semantic = pred.read(1)
        images = []
        for window in ("window_a", "window_b"):
            with rasterio.open(chip[window]) as image:
                images.append(
                    orient_for_display(
                        image.read([1, 2, 3]).transpose(1, 2, 0), image.transform
                    )
                )
        fig, axes = plt.subplots(1, 7, figsize=(24, 5))
        for ax, image, name in zip(axes[:2], images, ("Window A", "Window B")):
            ax.imshow(
                np.clip(image / settings.get("normalization_constant", 3000), 0, 1)
            )
            ax.set_title(name)
        for ax, image, name in (
            (axes[2], truth, "Reference"),
            (axes[3], semantic, "Raw classes"),
        ):
            ax.imshow(
                orient_for_display(image, transform),
                cmap="tab10",
                vmin=0,
                vmax=3,
                interpolation="nearest",
            )
            ax.set_title(name)
        baseline_row = table.loc[
            (table.country == row.country)
            & (table.aoi_id == row.aoi_id)
            & (table.method == baseline)
        ].iloc[0]
        if pd.isna(baseline_row.labels):
            raise ValueError("Missing baseline labels; use --generate-missing-labels")
        with rasterio.open(comparison / baseline_row.labels) as base_source:
            if (base_source.shape, base_source.transform, base_source.crs) != (
                truth.shape,
                transform,
                crs,
            ):
                raise ValueError("Baseline label grid differs from reference")
            base_labels = base_source.read(1)
        axes[4].imshow(
            orient_for_display(
                np.ma.masked_where(base_labels == 0, base_labels), transform
            ),
            cmap="nipy_spectral",
            interpolation="nearest",
        )
        axes[4].set_title(f"{baseline} (instance IDs)")
        if pd.isna(row.labels):
            raise ValueError("Missing method labels; use --generate-missing-labels")
        with rasterio.open(comparison / row.labels) as label_source:
            if (label_source.shape, label_source.transform, label_source.crs) != (
                truth.shape,
                transform,
                crs,
            ):
                raise ValueError("Instance label grid differs from reference")
            labels = label_source.read(1)
        gt, predicted, gt_matched, pred_matched, stats = instance_label_matches(
            truth,
            labels,
            iou_threshold=summary["iou_threshold"],
            ignore_index=settings.get("ignore_index"),
            reference_connectivity=summary["reference_connectivity"],
            reference_labels=reference_labels,
            prediction_identity=(
                "preserve-ids"
                if method in ("components-4", "components-8")
                else summary.get("prediction_identity_mode", "split-components")
            ),
        )
        if (stats.tp, stats.fp, stats.fn) != (row.stat_tp, row.stat_fp, row.stat_fn):
            raise ValueError("Saved labels do not reproduce method counts")
        if reference_labels is not None:
            axes[2].clear()
            axes[2].imshow(
                orient_for_display(np.ma.masked_where(gt == 0, gt), transform),
                cmap="nipy_spectral",
                interpolation="nearest",
            )
            axes[2].set_title("Reference (supplied field IDs)")
        ids = np.unique(predicted[predicted > 0])
        axes[5].imshow(
            orient_for_display(
                np.ma.masked_where(predicted == 0, predicted), transform
            ),
            cmap="nipy_spectral",
            interpolation="nearest",
        )
        axes[5].set_title(f"{method} (instance IDs)")
        axes[6].imshow(np.ones(truth.shape), cmap="gray", vmin=0, vmax=1)
        axes[6].set_title("TP / FP / FN outlines")
        for name, image, chosen in (
            ("FN", gt, np.setdiff1d(np.unique(gt[gt > 0]), gt_matched)),
            ("FP", predicted, np.setdiff1d(ids, pred_matched)),
            ("TP", predicted, pred_matched),
        ):
            if not has_labeled_background(row.country) and name == "FP":
                continue
            draw_object_contours(
                axes[6],
                orient_for_display(image, transform),
                chosen,
                MATCH_COLORS[name],
                linewidth=3 if name == "FN" else 1.4,
            )
        for ax in axes:
            ax.set_axis_off()
        fig.suptitle(
            f"{row.country}/{row.aoi_id}  [{summary.get('reference_mode', 'semantic-components')}; {summary.get('prediction_identity_mode', 'split-components')}]  {method}  {metric}={getattr(row, metric):.3f} "
            f"(vs {baseline}: {row.delta:+.3f})  "
            f"TP/FP/FN={stats.tp}/{'n/a' if not has_labeled_background(row.country) else stats.fp}/{stats.fn}"
        )
        fig.tight_layout()
        out.mkdir(parents=True, exist_ok=True)
        fig.savefig(destination, dpi=150)
        plt.close(fig)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--method", required=True)
    parser.add_argument("--baseline", default="components-4")
    parser.add_argument("--chip", action="append", default=[])
    parser.add_argument("--metric", default="pq")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--generate-missing-labels",
        action="store_true",
        help="Cache labels for selected chips in this assessment after verification",
    )
    args = parser.parse_args()
    print(
        f"Rendered {render(args.comparison, args.method, baseline=args.baseline, chips=args.chip, metric=args.metric, limit=args.limit, generate_missing_labels=args.generate_missing_labels)} chips"
    )


if __name__ == "__main__":
    main()
