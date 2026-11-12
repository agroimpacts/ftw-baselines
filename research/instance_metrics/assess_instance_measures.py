"""Paired chip-level measure disagreements on fixed-method comparison runs.

Usage: python -m research.instance_metrics.assess_instance_measures COMPARISON [COMPARISON ...] --out_dir OUT
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ftw_tools.training.metrics import InstanceStatistics

PAIRS = (
    ("recovery", "object_recall"),
    ("support", "object_precision"),
    ("rand_split_score", "rand_merge_score"),
    ("pq", "recovery"),
)
MEASURES = (
    "pq",
    "recovery",
    "support",
    "rand_split_score",
    "rand_merge_score",
    "object_precision",
    "object_recall",
)


def _bootstrap(delta, rng, draws, *, grouped=False):
    """Resample paired chips; for global results, resample countries too."""
    if not grouped:
        values = delta.to_numpy()
        return rng.choice(values, size=(draws, len(values)), replace=True).mean(axis=1)
    groups = [group.to_numpy() for _, group in delta.groupby(level="country")]
    samples = np.empty(draws)
    for index in range(draws):
        selected = rng.integers(0, len(groups), size=len(groups))
        chips = [
            rng.choice(groups[c], size=len(groups[c]), replace=True) for c in selected
        ]
        samples[index] = np.concatenate(chips).mean()
    return samples


def _pooled_scores(table):
    """Calculate overall ratios from additive statistics, never chip ratios."""
    fields = InstanceStatistics.__dataclass_fields__
    columns = [f"stat_{name}" for name in fields]
    if not set(columns).issubset(table.columns):
        return pd.DataFrame()
    rows = []
    for method, chips in table.groupby("method"):
        stats = InstanceStatistics(**dict(zip(fields, chips[columns].sum().to_numpy())))
        rows.extend(
            {
                "method": method,
                "measure": measure,
                "pooled_score": score,
                "chips": len(chips),
            }
            for measure, score in stats.scores().items()
        )
    return pd.DataFrame(rows)


def assess(directories, out_dir, *, baseline="components-4", seed=42, draws=1000):
    """Keep countries separate; resample paired chips for mean score differences."""
    if draws < 1:
        raise ValueError("draws must be positive")
    out = Path(out_dir).expanduser().resolve()
    if out.exists():
        raise FileExistsError(out)
    frames = []
    inputs = []
    summaries = []
    for directory in directories:
        directory = Path(directory).expanduser().resolve()
        summary = json.loads((directory / "summary.json").read_text())
        table = pd.read_parquet(directory / "chips.parquet")
        if summary["split"] != "test" or len(table) != summary["chip_count"] * len(
            summary["methods"]
        ):
            raise ValueError(f"Expected complete test comparison: {directory}")
        if table.duplicated(["country", "aoi_id", "method"]).any():
            raise ValueError(f"Duplicate chip/method: {directory}")
        if set(table.method) != set(summary["methods"]):
            raise ValueError(f"Methods differ from summary: {directory}")
        frames.append(table)
        summaries.append(summary)
        inputs.append(
            {
                "directory": str(directory),
                "country": summary["country"],
                "chips": summary["chip_count"],
                "checkpoint_sha256": summary["checkpoint_sha256"],
            }
        )
    if not frames or len({item["country"] for item in inputs}) != len(inputs):
        raise ValueError("Provide distinct country comparisons")
    if len({item["checkpoint_sha256"] for item in inputs}) != 1:
        raise ValueError("Comparisons use different checkpoints")
    if len({frozenset(summary["methods"]) for summary in summaries}) != 1:
        raise ValueError("Comparisons use different methods")
    for key in ("iou_threshold", "reference_connectivity"):
        if len({summary.get(key) for summary in summaries}) != 1:
            raise ValueError(f"Comparisons use different {key}")
    rng = np.random.default_rng(seed)
    pairs = []
    comparisons = []
    examples = []
    for country, table in [
        *((item["country"], frame) for item, frame in zip(inputs, frames)),
        ("all", pd.concat(frames, ignore_index=True)),
    ]:
        global_scope = country == "all"
        if (not global_scope and table.country.nunique() != 1) or baseline not in set(
            table.method
        ):
            raise ValueError(f"Expected one country and {baseline} per comparison")
        for method, rows in table.groupby("method"):
            for first, second in PAIRS:
                finite = (
                    rows[["country", "aoi_id", first, second]]
                    .replace([np.inf, -np.inf], np.nan)
                    .dropna()
                )
                n = len(finite)
                # Rank-based discordance: top-quartile in exactly one measure.
                top_first = finite[first].rank(pct=True) > 0.75
                top_second = finite[second].rank(pct=True) > 0.75
                pairs.append(
                    {
                        "country": country,
                        "method": method,
                        "first": first,
                        "second": second,
                        "n": n,
                        "spearman": finite[first].corr(
                            finite[second], method="spearman"
                        ),
                        "top_quartile_disagreement": (top_first != top_second).mean()
                        if n
                        else np.nan,
                    }
                )
                if n:
                    ranked = finite.assign(
                        rank_gap=(
                            finite[first].rank(pct=True) - finite[second].rank(pct=True)
                        ).abs()
                    )
                    examples.extend(
                        {
                            "country": country,
                            "method": method,
                            "first": first,
                            "second": second,
                            **{
                                key: value
                                for key, value in record.items()
                                if key != "country"
                            },
                            "chip_country": record["country"],
                        }
                        for record in ranked.nlargest(min(5, n), "rank_gap").to_dict(
                            "records"
                        )
                    )
        reference = table.loc[table.method == baseline].set_index(["country", "aoi_id"])
        for method, rows in table.groupby("method"):
            if method == baseline:
                continue
            candidate = rows.set_index(["country", "aoi_id"])
            if set(candidate.index) != set(reference.index):
                raise ValueError(f"Unpaired chips for {country}/{method}")
            candidate = candidate.reindex(reference.index)
            for measure in MEASURES:
                delta = (
                    (candidate[measure] - reference[measure])
                    .replace([np.inf, -np.inf], np.nan)
                    .dropna()
                )
                means = (
                    _bootstrap(delta, rng, draws, grouped=global_scope)
                    if len(delta)
                    else np.array([np.nan])
                )
                comparisons.append(
                    {
                        "country": country,
                        "method": method,
                        "baseline": baseline,
                        "measure": measure,
                        "n": len(delta),
                        "mean_chip_delta": delta.mean() if len(delta) else np.nan,
                        "ci_low": np.quantile(means, 0.025),
                        "ci_high": np.quantile(means, 0.975),
                        "improved": int((delta > 0).sum()),
                        "worsened": int((delta < 0).sum()),
                        "tied": int((delta == 0).sum()),
                    }
                )
            # How often two measures disagree about the method's direction.
            for first, second in PAIRS:
                a = candidate[first] - reference[first]
                b = candidate[second] - reference[second]
                finite = (
                    pd.DataFrame({"a": a, "b": b})
                    .replace([np.inf, -np.inf], np.nan)
                    .dropna()
                )
                opposed = ((finite.a * finite.b) < 0).sum()
                comparisons.append(
                    {
                        "country": country,
                        "method": method,
                        "baseline": baseline,
                        "measure": f"opposed:{first}:{second}",
                        "n": len(finite),
                        "opposed": int(opposed),
                        "tied_either": int(((finite.a == 0) | (finite.b == 0)).sum()),
                    }
                )
    out.mkdir(parents=True)
    (out / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    for filename, data in (
        ("measure_pairs", pairs),
        ("method_differences", comparisons),
        ("discordant_chips", examples),
    ):
        frame = pd.DataFrame(data)
        frame.loc[frame.country != "all"].to_csv(out / f"{filename}.csv", index=False)
        frame.loc[frame.country == "all"].to_csv(
            out / f"global_{filename}.csv", index=False
        )
    country_diffs = pd.DataFrame(comparisons)
    equal_rows = []
    for (method, measure), records in country_diffs.loc[
        (country_diffs.country != "all") & country_diffs.measure.isin(MEASURES)
    ].groupby(["method", "measure"]):
        finite = records.dropna(subset=["mean_chip_delta"])
        if finite.empty:
            continue
        samples = rng.choice(
            finite.mean_chip_delta.to_numpy(), size=(draws, len(finite)), replace=True
        ).mean(axis=1)
        equal_rows.append(
            {
                "method": method,
                "baseline": baseline,
                "measure": measure,
                "countries": len(finite),
                "mean_country_delta": finite.mean_chip_delta.mean(),
                "ci_low": np.quantile(samples, 0.025),
                "ci_high": np.quantile(samples, 0.975),
            }
        )
    pd.DataFrame(equal_rows).to_csv(out / "equal_country_differences.csv", index=False)
    _pooled_scores(pd.concat(frames, ignore_index=True)).to_csv(
        out / "global_pooled_scores.csv", index=False
    )
    return len(frames)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparisons", nargs="+", type=Path)
    parser.add_argument("--out_dir", required=True, type=Path)
    parser.add_argument("--draws", type=int, default=1000)
    args = parser.parse_args()
    print(
        f"Assessed {assess(args.comparisons, args.out_dir, draws=args.draws)} countries"
    )


if __name__ == "__main__":
    main()
