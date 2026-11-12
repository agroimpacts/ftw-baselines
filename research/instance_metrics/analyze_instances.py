"""Chip-level correlations and regressions from saved offline evaluation runs.

Usage: python -m research.instance_metrics.analyze_instances RUN_DIR [RUN_DIR ...] --out_dir OUTPUT
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm
from matplotlib.patches import Rectangle
from matplotlib.ticker import FormatStrFormatter
from scipy.stats import linregress

DEFAULT_PAIRS = (("support", "object_precision"), ("recovery", "object_recall"))
FIELD_INTERIOR_PIXEL_IOU = "pixel_binary_interior_iou_class_1"
COMPARABLE_SETTINGS = (
    "split",
    "iou_threshold",
    "reference_connectivity",
    "prediction_connectivity",
    "ignore_index",
    "test_on_3_classes",
    "model_predicts_3_classes",
    "remap_boundary",
)


def correlations(table, names):
    """Return pairwise-complete Pearson/Spearman coefficients and sample counts."""
    scores = table[list(names)].replace([np.inf, -np.inf], np.nan)
    valid = scores.notna().astype(int)
    counts = valid.T @ valid
    return scores.corr(method="pearson"), scores.corr(method="spearman"), counts


def regression(table, first, second):
    """Fit ordinary least squares: second = slope * first + intercept."""
    finite = table[[first, second]].replace([np.inf, -np.inf], np.nan).dropna()
    result = {
        "n": len(finite),
        "slope": np.nan,
        "intercept": np.nan,
        "r_squared": np.nan,
    }
    if len(finite) >= 2 and finite[first].nunique() >= 2:
        fit = linregress(finite[first], finite[second])
        result.update(
            slope=fit.slope,
            intercept=fit.intercept,
            r_squared=fit.rvalue**2 if np.isfinite(fit.rvalue) else np.nan,
        )
    return result


def heatmap_style(matrix):
    """Use 0.05-wide r bins on both triangles, leaving the diagonal uncolored."""
    data = matrix.to_numpy(dtype=float).copy()
    np.fill_diagonal(data, np.nan)
    cmap = plt.colormaps["coolwarm"].resampled(40)
    cmap.set_bad("white")
    norm = BoundaryNorm(np.linspace(-1, 1, 41), cmap.N, clip=True)
    return np.ma.masked_invalid(data), cmap, norm


def draw_correlation_heatmap(axis, matrix):
    """Color both triangles and annotate the lower triangle to three decimals."""
    data, cmap, norm = heatmap_style(matrix)
    image = axis.imshow(data, cmap=cmap, norm=norm)
    for row in range(len(matrix)):
        axis.add_patch(
            Rectangle(
                (row - 0.5, row - 0.5), 1, 1, facecolor="#bdbdbd", edgecolor="none"
            )
        )
        for column in range(row):
            value = matrix.iloc[row, column]
            if np.isfinite(value):
                red, green, blue, _ = cmap(norm(value))
                luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
                axis.text(
                    column,
                    row,
                    f"{value:.3f}",
                    ha="center",
                    va="center",
                    color="white" if luminance < 0.55 else "black",
                    fontsize=9,
                )
    return image


def load_runs(run_dirs):
    """Combine disjoint chip rows from comparable single-prediction runs."""
    paths = [Path(path).expanduser().resolve() for path in run_dirs]
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("Provide one or more distinct run directories")
    frames = []
    inputs = []
    names = None
    baseline = None
    for path in paths:
        summary = json.loads((path / "summary.json").read_text())
        manifest = json.loads((path / "manifest.json").read_text())
        if "instance_scores" not in summary:
            raise ValueError(f"Expected a single-prediction evaluation run: {path}")
        scores = [*summary["instance_scores"], FIELD_INTERIOR_PIXEL_IOU]
        settings = manifest["settings"]
        contract = (
            manifest.get("checkpoint_sha256"),
            tuple(settings.get(key) for key in COMPARABLE_SETTINGS),
            settings.get("reference_mode", "semantic-components"),
        )
        if baseline is None:
            baseline, names = contract, scores
        elif contract != baseline or set(scores) != set(names):
            raise ValueError(
                f"Incompatible checkpoint, scoring settings or scores: {path}"
            )
        table = pd.read_parquet(path / "chips.parquet")
        if not set(names).issubset(table.columns) or not {"country", "aoi_id"}.issubset(
            table
        ):
            raise ValueError(
                f"Chip table is missing country, AOI ID, instance scores or "
                f"{FIELD_INTERIOR_PIXEL_IOU}: {path}"
            )
        if (
            len(table) != summary["chip_count"]
            or len(table) != manifest["evaluated_chips"]
        ):
            raise ValueError(f"Chip count does not match run metadata: {path}")
        if set(table.country) != set(settings["countries"]):
            raise ValueError(f"Chip countries differ from manifest: {path}")
        frames.append(table)
        inputs.append(
            {
                "run_dir": str(path),
                "countries": settings["countries"],
                "split": settings["split"],
                "chip_count": len(table),
                "reference_mode": settings.get("reference_mode", "semantic-components"),
                "unscorable_chip_count": len(summary.get("unscorable_chips", [])),
            }
        )
    combined = pd.concat(frames, ignore_index=True)
    if combined.duplicated(["country", "aoi_id"]).any():
        raise ValueError(
            "Duplicate country/AOI_ID across runs; each chip must appear once"
        )
    return combined, names, inputs


def analyze(run_dirs, out_dir, *, pairs=DEFAULT_PAIRS):
    """Write chip correlations, per-pair regressions and plots for selected runs."""
    if isinstance(run_dirs, (str, Path)):
        run_dirs = [run_dirs]
    out_dir = Path(out_dir).expanduser().resolve()
    table, names, inputs = load_runs(run_dirs)
    if not names or not pairs:
        raise ValueError("No instance scores or comparisons specified")
    for first, second in pairs:
        if first not in names or second not in names or first == second:
            raise ValueError(f"Choose two distinct instance scores: {first}, {second}")
    if out_dir.exists():
        raise FileExistsError(f"Output already exists: {out_dir}")
    pearson, spearman, counts = correlations(table, names)
    fits = []
    for first, second in pairs:
        fits.append(
            {"first": first, "second": second, **regression(table, first, second)}
        )
    out_dir.mkdir(parents=True)
    (out_dir / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    for name, matrix in (
        ("pearson", pearson),
        ("spearman", spearman),
        ("pair_counts", counts),
    ):
        matrix.to_csv(out_dir / f"{name}.csv")
    pd.DataFrame(fits).to_csv(out_dir / "regressions.csv", index=False)
    for name, matrix in (("pearson", pearson), ("spearman", spearman)):
        fig, axis = plt.subplots(figsize=(10, 9))
        image = draw_correlation_heatmap(axis, matrix)
        axis.set_xticks(range(len(names)), names, rotation=90)
        axis.set_yticks(range(len(names)), names)
        colorbar = fig.colorbar(image, ax=axis, ticks=np.linspace(-1, 1, 11))
        colorbar.ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
        colorbar.set_label(f"{name.title()} r (0.05 bins)")
        fig.tight_layout()
        fig.savefig(out_dir / f"{name}.png", dpi=150)
        plt.close(fig)
    for fit in fits:
        first, second = fit["first"], fit["second"]
        finite = table[["country", first, second]].replace([np.inf, -np.inf], np.nan)
        finite = finite.dropna(subset=[first, second])
        fig, axis = plt.subplots(figsize=(6, 5))
        for country, chips in finite.groupby("country", sort=True):
            axis.scatter(
                chips[first],
                chips[second],
                s=16,
                alpha=0.55,
                label=f"{country} (n={len(chips)})",
            )
        bounds = (
            min(0, finite[[first, second]].min().min()) if len(finite) else 0,
            max(1, finite[[first, second]].max().max()) if len(finite) else 1,
        )
        axis.plot(bounds, bounds, color="gray", linestyle="--", label="1:1")
        if np.isfinite(fit["slope"]):
            axis.plot(
                bounds,
                np.asarray(bounds) * fit["slope"] + fit["intercept"],
                color="black",
                label="Least squares",
            )
        axis.text(
            0.03,
            0.97,
            f"y = {fit['slope']:.3f}x {fit['intercept']:+.3f}\n"
            f"R² = {fit['r_squared']:.3f}   n = {fit['n']}",
            transform=axis.transAxes,
            ha="left",
            va="top",
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"},
        )
        axis.set(
            xlabel=first,
            ylabel=second,
            title=f"{second} vs {first}",
            xlim=bounds,
            ylim=bounds,
        )
        axis.legend(loc="best", fontsize="small")
        fig.tight_layout()
        fig.savefig(out_dir / f"{first}-vs-{second}.png", dpi=150)
        plt.close(fig)
    return len(table)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", metavar="RUN_DIR")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument(
        "--pair",
        nargs=2,
        action="append",
        metavar=("FIRST", "SECOND"),
        help="Instance or field-interior pixel IoU pair (repeatable); defaults to support/precision and recovery/recall",
    )
    args = parser.parse_args()
    count = analyze(
        args.run_dirs,
        args.out_dir,
        pairs=args.pair if args.pair is not None else DEFAULT_PAIRS,
    )
    print(f"Analyzed {count} chips from {len(args.run_dirs)} run(s)")


if __name__ == "__main__":
    main()
