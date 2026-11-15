"""Full-population descriptive descriptor associations; no spatial inference."""

import argparse
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from ftw_geometry.core.descriptors import DESCRIPTOR_COLUMNS
from ftw_geometry.io.manifests import file_digest, write_json

from research.geometry.select_descriptor_pilot import now

FEATURES = [
    c
    for c in DESCRIPTOR_COLUMNS
    if c not in {"id", "orientation_deg", "orientation_ambiguous"}
]
SHAPES = [
    "circularity",
    "elongation",
    "solidity",
    "rectangularity",
    "convex_hull_index",
    "hole_area_fraction",
]
LOG_FEATURES = [
    "area_m2",
    "perimeter_m",
    "elongation",
    "rectangle_area_m2",
    "rectangle_length_m",
    "rectangle_width_m",
    "convex_hull_area_m2",
    "convex_hull_perimeter_m",
    "hole_area_m2",
]


def pca(frame):
    values = frame[SHAPES].astype(float).copy()
    values["elongation"] = np.log1p(values.elongation)
    values = values.replace([np.inf, -np.inf], np.nan).dropna()
    if len(values) < 3:
        return [], [], {"rows": len(values), "status": "insufficient_rows"}
    std = values.std(ddof=0)
    kept = std[std > 0].index.tolist()
    if len(kept) < 2:
        return [], [], {"rows": len(values), "status": "insufficient_variable_features"}
    standardized = (values[kept] - values[kept].mean()) / std[kept]
    _, singular, vectors = np.linalg.svd(standardized.to_numpy(), full_matrices=False)
    variance = singular**2 / (len(values) - 1)
    explained = variance / variance.sum()
    # Deterministic signs; the sign of a principal component has no meaning.
    for vector in vectors:
        if vector[np.argmax(np.abs(vector))] < 0:
            vector *= -1
    loadings = [
        {"component": i + 1, "feature": feature, "weight": float(weight)}
        for i, vector in enumerate(vectors)
        for feature, weight in zip(kept, vector)
    ]
    components = [
        {
            "component": i + 1,
            "explained_fraction": float(v),
            "cumulative_fraction": float(explained[: i + 1].sum()),
        }
        for i, v in enumerate(explained)
    ]
    return (
        loadings,
        components,
        {
            "rows": len(values),
            "status": "ok",
            "features": ",".join(kept),
            "dropped_constants": ",".join(c for c in SHAPES if c not in kept),
        },
    )


def run(root, out):
    root, out = Path(root).expanduser().resolve(), Path(out).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a fresh output directory")
    manifest = json.loads((root / "complete.json").read_text())
    for name, digest in manifest["output_sha256"].items():
        if file_digest(root / name) != digest:
            raise ValueError(f"Changed descriptor artifact: {name}")
    fields = pd.read_parquet(root / "primary-descriptors.parquet")
    if (
        not fields.sample_role.eq("primary").all()
        or fields.duplicated(["collection", "id"]).any()
    ):
        raise ValueError("Expected unique primary field identities only")
    fields["size_band"] = pd.cut(
        fields.area_m2,
        [0, 1000, 10000, 100000, np.inf],
        right=False,
        labels=["under_0.1ha", "0.1_to_1ha", "1_to_10ha", "10ha_plus"],
    )
    out.mkdir(parents=True, exist_ok=True)
    windows = pd.read_csv(root / "window-summary.csv")
    windows[windows.role == "primary"].to_csv(
        out / "window-availability.csv", index=False
    )
    groups = [("pooled", fields)] + [
        ("zone:" + str(z), f) for z, f in fields.groupby("zone_id", sort=True)
    ]
    groups += [
        (name + "|size:" + str(b), subset)
        for name, frame in list(groups)
        for b, subset in frame.groupby("size_band", observed=False)
    ]
    availability, distributions, associations, weights, components, statuses = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    for name, frame in groups:
        for feature in FEATURES:
            values = (
                frame[feature].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
            )
            availability.append(
                {
                    "group": name,
                    "feature": feature,
                    "rows": len(frame),
                    "finite_n": len(values),
                    "unique_n": values.nunique(),
                    "nonzero_n": int(values.ne(0).sum()),
                    "constant": values.nunique() <= 1,
                }
            )
            distributions.append(
                {
                    "group": name,
                    "feature": feature,
                    **{
                        label: float(values.quantile(q)) if len(values) else np.nan
                        for label, q in [
                            ("min", 0),
                            ("p05", 0.05),
                            ("p25", 0.25),
                            ("median", 0.5),
                            ("p75", 0.75),
                            ("p95", 0.95),
                            ("max", 1),
                        ]
                    },
                }
            )
        # Strictly monotone transforms preserve rank associations. Compute ranks
        # on original values so log rounding cannot introduce artificial ties.
        spearman = (
            frame[FEATURES]
            .astype(float)
            .replace([np.inf, -np.inf], np.nan)
            .corr(method="spearman", min_periods=3)
        )
        for representation in ["raw", "log1p_size_and_elongation"]:
            data = frame[FEATURES].astype(float).replace([np.inf, -np.inf], np.nan)
            if representation != "raw":
                data[LOG_FEATURES] = np.log1p(data[LOG_FEATURES])
            pearson = data.corr(method="pearson", min_periods=3)
            for first, second in combinations(FEATURES, 2):
                pair = data[[first, second]].dropna()
                associations.append(
                    {
                        "group": name,
                        "representation": representation,
                        "first": first,
                        "second": second,
                        "pair_n": len(pair),
                        "pearson": pearson.loc[first, second],
                        "spearman": spearman.loc[first, second],
                    }
                )
        loading, explained, status = pca(frame)
        weights.extend({"group": name, **row} for row in loading)
        components.extend({"group": name, **row} for row in explained)
        statuses.append({"group": name, **status})
    for filename, rows in [
        ("availability", availability),
        ("distributions", distributions),
        ("associations", associations),
        ("pca-weights", weights),
        ("pca-variance", components),
        ("pca-status", statuses),
    ]:
        pd.DataFrame(rows).to_csv(out / (filename + ".csv"), index=False)
    examples = []
    for zone, frame in fields.groupby("zone_id"):
        for first, second in [
            ("circularity", "rectangularity"),
            ("circularity", "solidity"),
            ("solidity", "convex_hull_index"),
        ]:
            ranks = frame[[first, second]].rank(pct=True)
            disagreement = (ranks[first] - ranks[second]).abs()
            for index in disagreement.nlargest(5).index:
                row = frame.loc[index]
                examples.append(
                    {
                        "zone_id": zone,
                        "window_id": row.window_id,
                        "collection": row.collection,
                        "id": row.id,
                        "first": first,
                        "second": second,
                        "first_value": row[first],
                        "second_value": row[second],
                        "absolute_rank_difference": disagreement.loc[index],
                        "selection": "illustration from main sample; does not change statistical weights",
                    }
                )
    pd.DataFrame(examples).to_csv(out / "disagreement-candidates.csv", index=False)
    (out / "analysis-source.py").write_bytes(Path(__file__).read_bytes())
    write_json(
        out / "analysis.json",
        {
            "completed_at": now(),
            "primary_rows": len(fields),
            "primary_input_sha256": file_digest(root / "primary-descriptors.parquet"),
            "parent_manifest_sha256": file_digest(root / "complete.json"),
            "features": FEATURES,
            "pca_features": SHAPES,
            "pca_transform": "log1p elongation, then population-SD standardization; complete cases; constants dropped",
            "scope": "All primary rows, not a sample. Diagnostic excluded. Pooled correlations field-count weighted. No p-values, bootstrap intervals or spatial independence claims. Raw axial orientation excluded. Rare boolean correlations are descriptive associations, not Gaussian inference.",
            "group_count": len(groups),
        },
    )
    print(
        f"Analyzed {len(fields)} primary fields across {len(groups)} pooled/zone/size groups: {out}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("descriptor_dir")
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(args.descriptor_dir, args.out_dir)
