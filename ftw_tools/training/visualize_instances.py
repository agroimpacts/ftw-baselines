"""Render selected offline test chips without rerunning the model.

Usage: python -m ftw_tools.training.visualize_instances RUN_DIR
"""

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from scipy.ndimage import find_objects

from ftw_tools.training.metrics import instance_match_labels


RANKINGS = {
    "f1-recovery": ("object_f1", "recovery"),
    "f1-support": ("object_f1", "support"),
    "rand-split-merge": ("rand_split_score", "rand_merge_score"),
}
LABEL_COLORS = ("#999999", "#2478c8", "#d74141", "#f2f2f2")
MATCH_COLORS = {"TP": "#00e060", "FP": "#ff9f1c", "FN": "#e000ff"}


def orient_for_display(array, transform):
    """Show north up and east right for axis-aligned raster grids."""
    if abs(transform.b) > 1e-12 or abs(transform.d) > 1e-12:
        raise ValueError("Rotated raster grids are not supported by this plot")
    if transform.a == 0 or transform.e == 0:
        raise ValueError("Raster grid has a zero pixel dimension")
    if transform.e > 0:
        array = np.flip(array, axis=0)
    if transform.a < 0:
        array = np.flip(array, axis=1)
    return array


def format_instance_scores(row):
    """Build aligned left/right score columns from a chip-table row."""

    def score(name):
        value = getattr(row, name)
        return f"{value:.3f}" if math.isfinite(value) else "—"

    def column(rows):
        return "\n".join(f"{label:<32}{value}" for label, value in rows)

    left = column(
        (
            (
                "Rand split / merge",
                (f"{score('rand_split_score')} / {score('rand_merge_score')}"),
            ),
            (
                "TP / FP / FN",
                (f"{int(row.stat_tp)} / {int(row.stat_fp)} / {int(row.stat_fn)}"),
            ),
            ("RQ / SQ / PQ", (f"{score('rq')} / {score('sq')} / {score('pq')}")),
        )
    )
    right = column(
        (
            ("Support / recovery", (f"{score('support')} / {score('recovery')}")),
            (
                "Object precision / recall / F1",
                (
                    f"{score('object_precision')} / "
                    f"{score('object_recall')} / {score('object_f1')}"
                ),
            ),
            ("Field-interior pixel IoU", (score("pixel_binary_interior_iou_class_1"))),
        )
    )
    return left, right


def object_status_labels(truth, pred, settings, expected_counts):
    """Return component IDs classified using the saved chip's matching contract."""
    gt, predicted, gt_matches, pred_matches, stats = instance_match_labels(
        truth,
        pred,
        iou_threshold=settings.get("iou_threshold", 0.5),
        ignore_index=settings.get("ignore_index"),
        reference_connectivity=settings.get("reference_connectivity", 4),
        prediction_connectivity=settings.get("prediction_connectivity", 4),
    )
    if (stats.tp, stats.fp, stats.fn) != tuple(expected_counts):
        raise ValueError(
            "Recomputed TP/FP/FN differ from saved chip statistics: "
            f"{(stats.tp, stats.fp, stats.fn)} != {tuple(expected_counts)}"
        )

    return {
        "TP": (predicted, pred_matches),
        "FP": (
            predicted,
            np.setdiff1d(np.arange(1, predicted.max() + 1), pred_matches),
        ),
        "FN": (gt, np.setdiff1d(np.arange(1, gt.max() + 1), gt_matches)),
    }


def draw_object_contours(axis, labels, ids, color, *, linewidth=1.4):
    """Draw exposed pixel sides, including sides between adjacent object IDs."""
    boxes = find_objects(labels)
    segments = []
    for object_id in ids:
        ys, xs = boxes[object_id - 1]
        local = labels[ys, xs] == object_id
        padded = np.pad(local, 1)
        for exposed, start, end in (
            (local & ~padded[:-2, 1:-1], (-0.5, -0.5), (0.5, -0.5)),
            (local & ~padded[2:, 1:-1], (-0.5, 0.5), (0.5, 0.5)),
            (local & ~padded[1:-1, :-2], (-0.5, -0.5), (-0.5, 0.5)),
            (local & ~padded[1:-1, 2:], (0.5, -0.5), (0.5, 0.5)),
        ):
            y, x = np.nonzero(exposed)
            origin = np.column_stack((x + xs.start, y + ys.start))
            segments.extend(np.stack((origin + start, origin + end), axis=1))
    if segments:
        axis.add_collection(
            LineCollection(segments, colors=[color], linewidths=linewidth)
        )


def select_chips(
    table,
    *,
    ranking="rand-split-merge",
    metrics=None,
    chips=(),
    order="absolute",
    limit=10,
):
    """Select individual chips or rank by a configurable pair of chip scores."""
    if limit < 1 or order not in ("absolute", "high", "low"):
        raise ValueError("Choose a positive limit and absolute, high or low order")
    if metrics is not None and (ranking != "rand-split-merge" or chips):
        raise ValueError("Custom metrics cannot be combined with ranking or chips")
    if chips and ranking != "rand-split-merge":
        raise ValueError("Choose chips or a ranking, not both")
    if chips:
        if len(set(chips)) != len(chips):
            raise ValueError("Duplicate chip selection")
        selected = []
        for chip in chips:
            if "/" not in chip:
                raise ValueError("Select chips as COUNTRY/AOI_ID")
            country, chip_id = chip.split("/", 1)
            rows = table.loc[(table.country == country) & (table.aoi_id == chip_id)]
            if len(rows) != 1:
                raise ValueError(f"Expected one chip for {chip}, found {len(rows)}")
            selected.append(rows.iloc[0])
        return pd.DataFrame(selected), None
    if metrics is None:
        if ranking not in RANKINGS:
            raise ValueError(f"Unknown ranking: {ranking}")
        metrics = RANKINGS[ranking]
    if len(metrics) != 2 or metrics[0] == metrics[1]:
        raise ValueError("Select two different metrics")
    for name in metrics:
        if name not in table or not pd.api.types.is_numeric_dtype(table[name]):
            raise ValueError(f"Not a numeric chip metric: {name}")
    first, second = metrics
    gap = pd.to_numeric(table[first]) - pd.to_numeric(table[second])
    ranked = table.assign(gap=gap).replace([np.inf, -np.inf], np.nan)
    ranked = ranked.dropna(subset=[first, second, "gap"])
    ranked = ranked.assign(
        _rank=ranked.gap.abs() if order == "absolute" else ranked.gap
    )
    ranked = ranked.sort_values("_rank", ascending=order == "low").head(limit)
    return ranked, (first, second)


def render(
    run_dir,
    *,
    ranking="rand-split-merge",
    limit=10,
    metrics=None,
    chips=(),
    order="absolute",
):
    """Plot chosen chips or ranked score gaps without changing their scores."""
    run_dir = Path(run_dir).expanduser().resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    normalization = manifest["settings"].get("normalization_constant", 3000.0)
    table = pd.read_parquet(run_dir / "chips.parquet")
    ranked, pair = select_chips(
        table, ranking=ranking, metrics=metrics, chips=chips, order=order, limit=limit
    )
    folder = (
        "selected"
        if chips
        else f"{pair[0]}-vs-{pair[1]}-{order}"
        if metrics
        else f"{ranking}-oriented"
    )
    figures = run_dir / "figures" / folder
    existing = [
        row.aoi_id
        for row in ranked.itertuples()
        if (figures / f"{row.country}_{row.aoi_id}.png").exists()
    ]
    if existing:
        raise FileExistsError(
            f"Annotated figures already exist in {figures}: " + ", ".join(existing)
        )
    figures.mkdir(parents=True, exist_ok=True)
    palette = ListedColormap(LABEL_COLORS)
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], palette.N)
    for row in ranked.itertuples():
        # fig, axes = plt.subplots(1, 5, figsize=(20, 5.6))
        fig, axes = plt.subplots(1, 5, figsize=(16, 5.2))
        for axis, column, title in (
            (axes[0], "window_a", "Window A"),
            (axes[1], "window_b", "Window B"),
        ):
            with rasterio.open(getattr(row, column)) as source:
                rgb = source.read([1, 2, 3]).transpose(1, 2, 0)
                rgb = orient_for_display(rgb, source.transform)
            axis.imshow(np.clip(rgb / normalization, 0, 1))
            axis.set_title(title)
        for axis, path, title in (
            (axes[2], row.reference, "Reference"),
            (axes[3], run_dir / row.prediction, "Raw prediction (0/1/2)"),
        ):
            with rasterio.open(path) as source:
                classes = source.read(1)
                classes = orient_for_display(classes, source.transform)
                transform = source.transform
            axis.imshow(classes, cmap=palette, norm=norm, interpolation="nearest")
            axis.set_title(title)
            if title == "Reference":
                reference = classes
                reference_shape = classes.shape
                reference_transform = transform
            else:
                if classes.shape != reference_shape or transform != reference_transform:
                    raise ValueError("Reference and prediction grids differ")
                statuses = object_status_labels(
                    reference,
                    classes,
                    manifest["settings"],
                    (row.stat_tp, row.stat_fp, row.stat_fn),
                )
                axes[4].imshow(
                    np.full(reference.shape, 0.96),
                    cmap="gray",
                    vmin=0,
                    vmax=1,
                    interpolation="nearest",
                )
                axes[4].set_title("Object outlines (TP / FP / FN)")
                # Wide FN first; narrow prediction lines leave a magenta rim
                # when different objects share an edge.
                for status in ("FN", "FP", "TP"):
                    labels, ids = statuses[status]
                    draw_object_contours(
                        axes[4],
                        labels,
                        ids,
                        MATCH_COLORS[status],
                        linewidth=3 if status == "FN" else 1.4,
                    )
        for axis in axes:
            axis.set_axis_off()
        title = f"{row.country}/{row.aoi_id}"
        if pair:
            title += f" — {pair[0]} − {pair[1]}: {row.gap:+.3f}"
        fig.suptitle(title, y=0.99)
        fig.legend(
            handles=[
                Patch(facecolor=color, edgecolor="gray", label=label)
                for color, label in zip(
                    LABEL_COLORS,
                    ("Background", "Field interior", "Boundary", "Ignored"),
                )
            ]
            + [
                Line2D(
                    [0],
                    [0],
                    color=color,
                    linewidth=3 if status == "FN" else 1.4,
                    label=f"{status} ({'reference' if status == 'FN' else 'prediction'})",
                )
                for status, color in MATCH_COLORS.items()
            ],
            loc="upper center",
            bbox_to_anchor=(0.5, 0.96),
            ncol=7,
            frameon=False,
        )
        # fig.subplots_adjust(left=0.02, right=0.98, top=0.84, bottom=0.24)
        fig.subplots_adjust(left=0.01, right=0.99, top=0.84, bottom=0.24, 
                            wspace=0.02)
        for x, text in zip((0.04, 0.52), format_instance_scores(row)):
            fig.text(x, 0.055, text, family="monospace", fontsize=10, va="bottom")
        fig.savefig(figures / f"{row.country}_{row.aoi_id}.png", dpi=150)
        plt.close(fig)
    return len(ranked)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--ranking", choices=RANKINGS, default="rand-split-merge")
    parser.add_argument(
        "--metrics",
        nargs=2,
        metavar=("FIRST", "SECOND"),
        help="Rank by FIRST minus SECOND (numeric chip columns)",
    )
    parser.add_argument(
        "--order",
        choices=("absolute", "high", "low"),
        default="absolute",
        help="Absolute gap or signed difference",
    )
    parser.add_argument(
        "--chip",
        action="append",
        default=[],
        metavar="COUNTRY/AOI_ID",
        help="Plot an exact chip; repeat for multiple chips",
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    count = render(
        args.run_dir,
        ranking=args.ranking,
        limit=args.limit,
        metrics=args.metrics,
        chips=args.chip,
        order=args.order,
    )
    print(f"Rendered {count} chips")


if __name__ == "__main__":
    main()
