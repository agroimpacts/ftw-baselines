"""Render descriptive pilot association figures and a bounded interpretation."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from ftw_geometry.io.manifests import file_digest, write_json


def report(out, descriptors):
    out, descriptors = Path(out).expanduser(), Path(descriptors).expanduser()
    info = json.loads((out / "analysis.json").read_text())
    if (
        file_digest(descriptors / "primary-descriptors.parquet")
        != info["primary_input_sha256"]
    ):
        raise ValueError("Analysis input changed")
    frame = pd.read_parquet(descriptors / "primary-descriptors.parquet")
    associations = pd.read_csv(out / "associations.csv")
    variance = pd.read_csv(out / "pca-variance.csv")
    counts = frame.groupby("zone_id").size()
    features = [
        "area_m2",
        "circularity",
        "elongation",
        "solidity",
        "rectangularity",
        "convex_hull_index",
        "hole_area_fraction",
        "narrow_neck",
    ]
    groups = ["pooled"] + ["zone:" + z for z in sorted(counts.index)]
    fig, axes = plt.subplots(2, 4, figsize=(20, 11), layout="constrained")
    for ax, group in zip(axes.flat, groups):
        matrix = np.full((len(features), len(features)), np.nan)
        subset = associations[
            (associations.group == group) & (associations.representation == "raw")
        ]
        for row in subset.itertuples():
            if row.first in features and row.second in features:
                i, j = features.index(row.first), features.index(row.second)
                matrix[i, j] = matrix[j, i] = row.spearman
        np.fill_diagonal(matrix, 1)
        image = ax.imshow(matrix, vmin=-1, vmax=1, cmap="coolwarm")
        ax.set_xticks(
            range(len(features)), features, rotation=65, ha="right", fontsize=8
        )
        ax.set_yticks(range(len(features)), features, fontsize=8)
        ax.set_title(group)
    fig.colorbar(
        image,
        ax=list(axes.flat),
        shrink=0.6,
        label="Spearman rho; full primary observations; no significance claim",
    )
    fig.savefig(out / "spearman-by-landscape.png", dpi=160)
    plt.close(fig)
    pooled = variance[variance.group == "pooled"]
    fig, ax = plt.subplots(figsize=(7, 4), layout="constrained")
    ax.bar(pooled.component, pooled.explained_fraction, label="Individual")
    ax.plot(
        pooled.component,
        pooled.cumulative_fraction,
        "o-",
        color="black",
        label="Cumulative",
    )
    ax.set(
        xlabel="Principal component",
        ylabel="Explained standardized-feature variance",
        ylim=(0, 1),
    )
    ax.legend()
    fig.savefig(out / "pooled-pca-variance.png", dpi=160)
    plt.close(fig)
    lines = [
        "# Descriptor complementarity: initial descriptive results",
        "",
        f"Primary fields: **{len(frame):,}**. The Bahia pivot diagnostic is excluded. All primary rows are used; no reservoir sampling.",
        "",
        "| Landscape | Assigned fields | Fields with holes | Narrow-neck flags |",
        "|---|---:|---:|---:|",
    ]
    for zone, group in frame.groupby("zone_id"):
        lines.append(
            f"| {zone} | {len(group):,} | {int(group.hole_count.gt(0).sum()):,} | {int(group.narrow_neck.sum()):,} |"
        )
    lines += [
        "",
        f"Cambodia and Vietnam contribute **{100 * counts.loc[['cambodia', 'vietnam']].sum() / len(frame):.1f}%** of fields. Pooled associations are field-count weighted, not equal-landscape or globally representative estimates.",
        "",
        "## Selected Spearman associations",
        "",
        "| Pair | Pooled rho | Within-landscape min/max |",
        "|---|---:|---:|",
    ]
    for first, second in [
        ("circularity", "elongation"),
        ("solidity", "rectangularity"),
        ("solidity", "convex_hull_index"),
        ("circularity", "rectangularity"),
    ]:
        pair = associations[
            (associations.representation == "raw")
            & (
                ((associations["first"] == first) & (associations["second"] == second))
                | (
                    (associations["first"] == second)
                    & (associations["second"] == first)
                )
            )
        ]
        pooled_r = pair.loc[pair.group == "pooled", "spearman"].iloc[0]
        within = pair[pair.group.isin(groups[1:])].spearman
        lines.append(
            f"| {first} / {second} | {pooled_r:.3f} | {within.min():.3f} to {within.max():.3f} |"
        )
    lines += [
        "",
        "## Interpretation and limits",
        "",
        "- Shape descriptors are associated, but not empirically interchangeable across all landscapes. This is not yet evidence that every descriptor is useful.",
        "- Algebraic dependencies remain: circularity uses area/perimeter; elongation and rectangularity use enclosing-rectangle dimensions; solidity and hull index use hull measurements. Supporting dimensions should not all enter PCA alongside their derived ratios.",
        "- PCA uses circularity, log1p elongation, solidity, rectangularity, convex-hull index and hole-area fraction, standardized within each group. It excludes area, redundant supporting dimensions, raw axial orientation and binary flags.",
        f"- Pooled PCA: first component {100 * pooled.explained_fraction.iloc[0]:.1f}%; first two {100 * pooled.cumulative_fraction.iloc[1]:.1f}%; first three {100 * pooled.cumulative_fraction.iloc[2]:.1f}%. This is descriptive dimension reduction, not clustering or proof of scientific importance.",
        "- Primary holes occur in only 894 fields and narrow-neck flags in 494; investigate their distinct geometry visually. Rare features and ties affect associations. Published hole filling and size/simplification policies affect these distributions.",
        "- Fixed size bands are <0.1 ha, 0.1–1 ha, 1–10 ha and >=10 ha. Empty/small/constant groups remain explicit in availability and PCA-status outputs; do not interpret undefined correlations as zero.",
        "- Rwanda has 645 detected fields and one empty window. User visual review indicates substantial false negatives. These results describe detected map geometry, not a complete landscape census or measured detection recall.",
        "- No p-values, confidence intervals, spatial bootstrap, independent-observation claims, reference accuracy, resolution sensitivity or temporal inference. Spatial-block scale/sensitivity remains outstanding.",
        "- disagreement-candidates.csv selects within-zone rank contrasts from the existing sample for review only. No fields were added or reweighted; visual interpretation remains outstanding.",
        "",
        "## Files",
        "",
        "- availability.csv, window-availability.csv, distributions.csv: feature/sample availability and quantiles.",
        "- associations.csv: pair counts, raw and log1p-representation Pearson/Spearman, pooled/zone/size groups.",
        "- pca-weights.csv, pca-variance.csv, pca-status.csv: eigenvector weights, variance and complete-case/constant handling. Weights are not correlation loadings.",
        "- spearman-by-landscape.png and pooled-pca-variance.png: initial descriptive figures.",
        "- analysis.json: input hashes and analysis definitions.",
    ]
    (out / "README.md").write_text("\n".join(lines) + "\n")
    (out / "report-source.py").write_bytes(Path(__file__).read_bytes())
    write_json(
        out / "complete.json",
        {
            "input_sha256": info["primary_input_sha256"],
            "output_sha256": {
                p.name: file_digest(p)
                for p in sorted(out.iterdir())
                if p.is_file() and p.name != "complete.json"
            },
        },
    )
    print(out / "README.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_dir")
    parser.add_argument("--descriptor_dir", required=True)
    args = parser.parse_args()
    report(args.analysis_dir, args.descriptor_dir)
