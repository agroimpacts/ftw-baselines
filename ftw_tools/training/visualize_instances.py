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
from matplotlib.patches import Patch


RANKINGS = {
    "f1-recovery": ("object_f1", "covering_truth_to_prediction"),
    "f1-support": ("object_f1", "covering_prediction_to_truth"),
    "rand-split-merge": ("rand_split_score", "rand_merge_score"),
}
LABEL_COLORS = ("#f2f2f2", "#2478c8", "#d74141", "#999999")


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
                (
                    f"{int(row.stat_tp)} / {int(row.stat_fp)} / "
                    f"{int(row.stat_fn)}"
                ),
            ),
            (
                "RQ / SQ / PQ",
                (f"{score('rq')} / {score('sq')} / {score('pq')}"),
            ),
        )
    )
    right = column(
        (
            (
                "Recovery / support",
                (
                    f"{score('covering_truth_to_prediction')} / "
                    f"{score('covering_prediction_to_truth')}"
                ),
            ),
            (
                "Object precision / recall / F1",
                (
                    f"{score('object_precision')} / "
                    f"{score('object_recall')} / {score('object_f1')}"
                ),
            ),
            (
                "Field-interior pixel IoU",
                (score("pixel_binary_interior_iou_class_1")),
            ),
        )
    )
    return left, right


def render(run_dir, *, ranking="rand-split-merge", limit=10):
    """Rank finite chip-score gaps and plot both windows and class masks."""
    if ranking not in RANKINGS or limit < 1:
        raise ValueError("Choose a valid ranking and positive limit")
    run_dir = Path(run_dir).expanduser().resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    normalization = manifest["settings"].get("normalization_constant", 3000.0)
    table = pd.read_parquet(run_dir / "chips.parquet")
    first, second = RANKINGS[ranking]
    ranked = table.assign(gap=(table[first] - table[second]).abs()).dropna(
        subset=["gap"]
    )
    ranked = ranked.sort_values("gap", ascending=False).head(limit)
    figures = run_dir / "figures" / f"{ranking}-oriented"
    existing = [
        row.aoi_id
        for row in ranked.itertuples()
        if (figures / f"{row.country}_{row.aoi_id}.png").exists()
    ]
    if existing:
        raise FileExistsError(
            f"Annotated figures already exist in {figures}: "
            + ", ".join(existing)
        )
    figures.mkdir(parents=True, exist_ok=True)
    palette = ListedColormap(LABEL_COLORS)
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], palette.N)
    for row in ranked.itertuples():
        fig, axes = plt.subplots(1, 4, figsize=(16, 5.6))
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
            axis.imshow(
                classes, cmap=palette, norm=norm, interpolation="nearest"
            )
            axis.set_title(title)
        for axis in axes:
            axis.set_axis_off()
        fig.suptitle(
            f"{row.country}/{row.aoi_id} — {ranking} gap: {row.gap:.3f}", y=0.99
        )
        fig.legend(
            handles=[
                Patch(facecolor=color, edgecolor="gray", label=label)
                for color, label in zip(
                    LABEL_COLORS,
                    ("Background", "Field interior", "Boundary", "Ignored"),
                )
            ],
            loc="upper center",
            bbox_to_anchor=(0.5, 0.96),
            ncol=4,
            frameon=False,
        )
        fig.subplots_adjust(left=0.02, right=0.98, top=0.84, bottom=0.24)
        for x, text in zip((0.04, 0.52), format_instance_scores(row)):
            fig.text(
                x, 0.055, text, family="monospace", fontsize=10, va="bottom"
            )
        fig.savefig(figures / f"{row.country}_{row.aoi_id}.png", dpi=150)
        plt.close(fig)
    return len(ranked)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument(
        "--ranking", choices=RANKINGS, default="rand-split-merge"
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    count = render(args.run_dir, ranking=args.ranking, limit=args.limit)
    print(f"Rendered {count} chips")


if __name__ == "__main__":
    main()
