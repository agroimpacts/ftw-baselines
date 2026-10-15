"""Render selected offline test chips without rerunning the model.

Usage: python -m ftw_tools.training.visualize_instances RUN_DIR
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
from matplotlib.colors import BoundaryNorm, ListedColormap


RANKINGS = {
    "f1-recovery": ("object_f1", "covering_truth_to_prediction"),
    "f1-support": ("object_f1", "covering_prediction_to_truth"),
    "rand-split-merge": ("rand_split_score", "rand_merge_score"),
}


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
    figures = run_dir / "figures" / ranking
    figures.mkdir(parents=True, exist_ok=True)
    palette = ListedColormap(["#444444", "#65ac53", "#eeaf51", 
                              "#111111"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], palette.N)
    for row in ranked.itertuples():
        fig, axes = plt.subplots(1, 4, figsize=(16, 4))
        for axis, column, title in (
            (axes[0], "window_a", "Window A"),
            (axes[1], "window_b", "Window B"),
        ):
            with rasterio.open(getattr(row, column)) as source:
                rgb = source.read([1, 2, 3]).transpose(1, 2, 0)
            axis.imshow(np.clip(rgb / normalization, 0, 1))
            axis.set_title(title)
        for axis, path, title in (
            (axes[2], row.reference, "Reference"),
            (axes[3], run_dir / row.prediction, "Raw prediction"),
        ):
            with rasterio.open(path) as source:
                classes = source.read(1)
            axis.imshow(
                classes, cmap=palette, norm=norm, interpolation="nearest"
            )
            axis.set_title(title)
        for axis in axes:
            axis.set_axis_off()
        fig.suptitle(
            f"{row.country}/{row.aoi_id}: {first}={getattr(row, first):.3f}, "
            f"{second}={getattr(row, second):.3f}"
        )
        fig.tight_layout()
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
