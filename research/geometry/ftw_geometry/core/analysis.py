"""Descriptive spatial summaries and associations, separate from accuracy scoring."""

import hashlib
import itertools
import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import spearmanr

from ftw_geometry.core.dataset import (
    dataset_parts,
    file_digest,
    geometry_frame,
    write_json,
)
from ftw_geometry.core.descriptors import DESCRIPTOR_COLUMNS


def _new_output(out_dir):
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError("Choose a new/empty analysis output directory")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def summarize_regions(
    dataset,
    regions_path,
    out_dir,
    *,
    region_id,
    edge_policy,
    gap_radius_m,
    max_fields=100000,
):
    """Measure whole fields, assign by representative point, clip coverage only.

    Regions must be the explicitly surveyed valid domain, not administrative
    areas containing unsurveyed land. Regions may touch, but must not overlap.
    A representative point on a shared boundary raises rather than double-counts.
    Input descriptor batches stream per region; exact geometry/distribution work
    is bounded by max_fields for each region plus its gap-context halo.
    """
    dataset = Path(dataset)
    manifest = json.loads((dataset / "manifest.json").read_text())
    if (
        edge_policy not in {"include", "exclude"}
        or not math.isfinite(gap_radius_m)
        or gap_radius_m <= 0
        or max_fields < 1
    ):
        raise ValueError(
            "Choose include/exclude edge policy, positive finite gap radius and field limit"
        )
    regions = gpd.read_file(regions_path).to_crs(manifest["metric_crs"])
    if (
        region_id not in regions
        or regions[region_id].isna().any()
        or not regions[region_id].astype(str).is_unique
    ):
        raise ValueError("Surveyed regions need unique non-null IDs")
    if (
        regions.empty
        or not regions.geometry.is_valid.all()
        or regions.geometry.is_empty.any()
        or not regions.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    ):
        raise ValueError("Surveyed regions must be nonempty valid polygons")
    region_index = regions.sindex
    for index, geometry in enumerate(regions.geometry):
        for other in region_index.query(geometry, predicate="intersects"):
            if (
                other > index
                and geometry.intersection(regions.geometry.iloc[other]).area > 0
            ):
                raise ValueError("Surveyed regions must not overlap")
    parts = list(dataset_parts(dataset))
    out_dir = _new_output(out_dir)
    assigned_dir = out_dir / "assigned_fields"
    assigned_dir.mkdir()
    summaries, distributions = [], []
    for region_position, (_, row) in enumerate(regions.iterrows()):
        boundary = row.geometry
        context = boundary.buffer(gap_radius_m)
        chunks, count = [], 0
        for part in parts:
            table = pd.read_parquet(part)
            if edge_policy == "exclude":
                if table.touches_source_edge.isna().any():
                    raise ValueError(
                        "Excluding edge fields requires source footprints for all inputs"
                    )
                table = table.loc[~table.touches_source_edge].copy()
            frame = geometry_frame(table, manifest["metric_crs"])
            frame = frame.loc[frame.intersects(context)].copy()
            count += len(frame)
            if count > max_fields:
                raise ValueError(
                    "Region plus gap halo exceeds max_fields; use smaller regions or explicitly raise the limit"
                )
            if len(frame):
                chunks.append(frame)
        candidates = (
            gpd.GeoDataFrame(
                pd.concat(chunks, ignore_index=True), crs=manifest["metric_crs"]
            )
            if chunks
            else gpd.GeoDataFrame(
                columns=["geometry"], geometry="geometry", crs=manifest["metric_crs"]
            )
        )
        if len(candidates):
            points = candidates.representative_point()
            selected = []
            for point in points:
                owners = region_index.query(point, predicate="intersects")
                if len(owners) > 1:
                    raise ValueError(
                        "A field representative point lies on a shared region boundary"
                    )
                selected.append(len(owners) == 1 and owners[0] == region_position)
            assigned = candidates.loc[selected].copy()
            clipped = candidates.geometry.intersection(boundary)
            clipped = clipped.loc[clipped.area > 0]
        else:
            assigned = candidates.copy()
            clipped = gpd.GeoSeries([], crs=regions.crs)
        area = boundary.area
        union_area = clipped.union_all().area if len(clipped) else 0.0
        summary = {
            "region_id": str(row[region_id]),
            "surveyed_area_m2": area,
            "field_count": len(assigned),
            "field_density_per_km2": len(assigned) / (area / 1e6),
            "mapped_union_area_m2": union_area,
            "mapped_fraction": union_area / area,
            "summed_clipped_area_m2": float(clipped.area.sum()),
            "overlap_excess_area_m2": float(clipped.area.sum()) - union_area,
            "coverage_intersecting_field_count": len(clipped),
            "centroid_x": boundary.centroid.x,
            "centroid_y": boundary.centroid.y,
            "context_field_count": len(candidates),
            "source_edge_count": int(assigned.touches_source_edge.fillna(False).sum())
            if len(assigned)
            else 0,
            "unknown_source_edge_count": int(assigned.touches_source_edge.isna().sum())
            if len(assigned)
            else 0,
            "region_crossing_field_count": int(
                (~assigned.geometry.map(boundary.covers)).sum()
            )
            if len(assigned)
            else 0,
        }
        for column in regions.columns:
            if column not in {region_id, regions.geometry.name}:
                summary["region_" + column] = row[column]
        clipped = clipped.reset_index(drop=True)
        overlaps = 0
        if len(clipped):
            index = clipped.sindex
            for position, geometry in enumerate(clipped):
                for other in index.query(geometry, predicate="intersects"):
                    if (
                        other > position
                        and geometry.intersection(clipped.iloc[other]).area > 0
                    ):
                        overlaps += 1
        summary["overlapping_polygon_pairs"] = overlaps
        summary["polygons_with_holes_fraction"] = (
            float((assigned.hole_count > 0).mean()) if len(assigned) else math.nan
        )
        summary["narrow_neck_fraction"] = (
            float(assigned.narrow_neck.mean()) if len(assigned) else math.nan
        )
        gaps = []
        if len(assigned):
            index = candidates.sindex
            for field in assigned.itertuples():
                nearby = candidates.iloc[
                    index.query(
                        field.geometry.buffer(gap_radius_m), predicate="intersects"
                    )
                ]
                distances = nearby.loc[
                    nearby.field_key != field.field_key
                ].geometry.distance(field.geometry)
                positive = distances[(distances > 0) & (distances <= gap_radius_m)]
                gaps.append(float(positive.min()) if len(positive) else math.nan)
            assigned["nearest_positive_gap_m"] = gaps
            assigned["positive_gap_censored"] = np.isnan(gaps)
            assigned["region_id"] = str(row[region_id])
            assigned["crosses_region_boundary"] = ~assigned.geometry.map(
                boundary.covers
            )
            table = pd.DataFrame(assigned.drop(columns="geometry"))
            table["geometry_wkb"] = assigned.geometry.to_wkb()
            table.to_parquet(
                assigned_dir / f"region-{region_position:06d}.parquet", index=False
            )
        finite_gaps = np.asarray(gaps)[np.isfinite(gaps)]
        summary["positive_gap_observed_count"] = len(finite_gaps)
        summary["positive_gap_censored_count"] = len(assigned) - len(finite_gaps)
        summary["mean_observed_positive_gap_m"] = (
            float(finite_gaps.mean()) if len(finite_gaps) else math.nan
        )
        for column in DESCRIPTOR_COLUMNS[1:]:
            if column in {"orientation_deg", "orientation_ambiguous"}:
                continue
            values = (
                pd.to_numeric(assigned[column], errors="coerce").to_numpy(dtype=float)
                if len(assigned)
                else np.array([])
            )
            finite = np.isfinite(values)
            clean = values[finite]
            summary[column + "_finite_count"] = len(clean)
            summary[column + "_mean"] = float(clean.mean()) if len(clean) else math.nan
            summary[column + "_area_weighted_mean"] = (
                float(np.average(clean, weights=assigned.area_m2.to_numpy()[finite]))
                if len(clean)
                else math.nan
            )
            for quantile in (0.05, 0.25, 0.5, 0.75, 0.95):
                summary[f"{column}_q{int(quantile * 100):02d}"] = (
                    float(np.quantile(clean, quantile)) if len(clean) else math.nan
                )
        angles = assigned.orientation_deg.to_numpy() if len(assigned) else np.array([])
        finite = np.isfinite(angles)
        for weighted in (False, True):
            weights = (
                assigned.area_m2.to_numpy()[finite]
                if weighted and len(assigned)
                else None
            )
            vector = (
                np.average(np.exp(2j * np.deg2rad(angles[finite])), weights=weights)
                if finite.any()
                else complex(math.nan, math.nan)
            )
            prefix = "orientation_area_weighted" if weighted else "orientation"
            summary[prefix + "_resultant"] = abs(vector)
            summary[prefix + "_axial_mean_deg"] = (
                (np.rad2deg(np.angle(vector)) / 2) % 180
                if abs(vector) > 1e-12
                else math.nan
            )
        summary["orientation_finite_count"] = int(finite.sum())
        summary["orientation_ambiguous_count"] = (
            int(assigned.orientation_ambiguous.sum()) if len(assigned) else 0
        )
        if len(assigned):
            size_class = pd.cut(
                assigned.area_m2, [0, 1000, 10000, 100000, np.inf], right=False
            )
            for label, total in size_class.value_counts(sort=False).items():
                distributions.append(
                    {
                        "region_id": str(row[region_id]),
                        "distribution": "size_m2",
                        "bin": str(label),
                        "field_count": int(total),
                    }
                )
            orientation_class = pd.cut(
                assigned.orientation_deg, np.arange(0, 181, 15), right=False
            )
            for label, total in orientation_class.value_counts(sort=False).items():
                distributions.append(
                    {
                        "region_id": str(row[region_id]),
                        "distribution": "axial_orientation_deg",
                        "bin": str(label),
                        "field_count": int(total),
                    }
                )
        summaries.append(summary)
    result = pd.DataFrame(summaries)
    result.to_parquet(out_dir / "regions.parquet", index=False)
    result.to_csv(out_dir / "regions.csv", index=False)
    pd.DataFrame(
        distributions, columns=["region_id", "distribution", "bin", "field_count"]
    ).to_csv(out_dir / "distributions.csv", index=False)
    write_json(
        out_dir / "analysis.json",
        {
            "dataset": str(dataset.resolve()),
            "dataset_manifest_sha256": file_digest(dataset / "manifest.json"),
            "regions": str(Path(regions_path).resolve()),
            "regions_sha256": file_digest(regions_path),
            "region_id_column": region_id,
            "metric_crs": manifest["metric_crs"],
            "analysis_code_sha256": file_digest(__file__),
            "edge_policy": edge_policy,
            "assignment": "whole-field representative point; coverage clipped independently",
            "gap_radius_m": gap_radius_m,
            "max_fields_per_region_and_halo": max_fields,
            "gap_definition": "nearest strictly positive distance within radius; no observation is censored, not zero",
            "complete": True,
        },
    )
    return result


class PairMoments:
    """Stable mergeable pairwise-finite Pearson statistics."""

    def __init__(self):
        self.n, self.mx, self.my, self.xx, self.yy, self.xy = 0, 0.0, 0.0, 0.0, 0.0, 0.0

    def add(self, x, y):
        finite = np.isfinite(x) & np.isfinite(y)
        x, y = x[finite], y[finite]
        n = len(x)
        if not n:
            return
        mx, my = x.mean(), y.mean()
        dx, dy = mx - self.mx, my - self.my
        weight = self.n * n / (self.n + n)
        self.xx += float(np.sum((x - mx) ** 2)) + dx * dx * weight
        self.yy += float(np.sum((y - my) ** 2)) + dy * dy * weight
        self.xy += float(np.sum((x - mx) * (y - my))) + dx * dy * weight
        self.mx += dx * n / (self.n + n)
        self.my += dy * n / (self.n + n)
        self.n += n

    def correlation(self):
        return (
            float(np.clip(self.xy / math.sqrt(self.xx * self.yy), -1, 1))
            if self.n >= 3 and self.xx > 0 and self.yy > 0
            else math.nan
        )


def _association(x, y, method):
    finite = np.isfinite(x) & np.isfinite(y)
    x, y = x[finite], y[finite]
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return math.nan
    return (
        float(np.corrcoef(x, y)[0, 1])
        if method == "pearson"
        else float(spearmanr(x, y).statistic)
    )


def _bootstrap_pair(sample, first, second, block_size, replicates, rng):
    finite = np.isfinite(
        sample[[first, second, "centroid_x", "centroid_y"]].to_numpy(dtype=float)
    ).all(axis=1)
    frame = sample.loc[finite]
    if frame.empty:
        return 0, {}
    blocks = np.floor(
        frame[["centroid_x", "centroid_y"]].to_numpy() / block_size
    ).astype("int64")
    _, labels = np.unique(blocks, axis=0, return_inverse=True)
    unique = np.unique(labels)
    if len(unique) < 3 or replicates == 0:
        return len(unique), {}
    groups = [np.flatnonzero(labels == block) for block in unique]
    values = {"pearson": [], "spearman": []}
    x, y = frame[first].to_numpy(), frame[second].to_numpy()
    for _ in range(replicates):
        indexes = np.concatenate(
            [groups[i] for i in rng.integers(0, len(groups), len(groups))]
        )
        for method, estimates in values.items():
            value = _association(x[indexes], y[indexes], method)
            if np.isfinite(value):
                estimates.append(value)
    result = {}
    for method, estimates in values.items():
        result[method + "_bootstrap_valid"] = len(estimates)
        bounds = (
            np.quantile(estimates, [0.025, 0.975])
            if len(estimates) >= max(2, replicates // 2)
            else [math.nan, math.nan]
        )
        result[method + "_ci_low"], result[method + "_ci_high"] = map(float, bounds)
    return len(unique), result


def correlate_tables(
    paths,
    out_dir,
    *,
    features,
    group_column,
    sample_size=2000,
    max_groups=256,
    block_size_m,
    bootstrap_replicates=200,
    seed=42,
    log_features=(),
    pca_features=(),
    level="field",
    size_bins=(0, 1000, 10000, 100000, np.inf),
    size_strata=True,
    metric_crs=None,
):
    """Exact streamed Pearson; reservoir Spearman/PCA and spatial-block intervals.

    Per-group sampling is reproducible and bounded. No raw-angle correlations.
    Spatial intervals are conditional on the sampled rows, not full-data CIs.
    """
    if (
        level not in {"field", "area"}
        or sample_size < 3
        or max_groups < 1
        or block_size_m <= 0
        or not math.isfinite(block_size_m)
        or bootstrap_replicates < 0
    ):
        raise ValueError(
            "Invalid level, sample/group limit or spatial-bootstrap settings"
        )
    if metric_crs is None:
        raise ValueError(
            "Explicit metre-based metric_crs is required for spatial blocks"
        )
    from ftw_geometry.core.descriptors import metric_geometry_crs

    metric_geometry_crs(gpd.GeoDataFrame(geometry=[], crs=metric_crs))
    features, pca_features = list(features), list(pca_features)
    if (
        len(features) < 2
        or len(features) != len(set(features))
        or not set(log_features).issubset(features)
        or not set(pca_features).issubset(features)
    ):
        raise ValueError("Provide distinct features and valid log/PCA subsets")
    if any(
        column == "orientation_deg" or column.endswith("axial_mean_deg")
        for column in features
    ):
        raise ValueError(
            "Raw angles need a separate axial analysis, not linear correlation/PCA"
        )
    if set(features) & {"centroid_x", "centroid_y", group_column}:
        raise ValueError(
            "Features must not duplicate grouping/spatial-coordinate columns"
        )
    if len(pca_features) != len(set(pca_features)):
        raise ValueError("PCA features must be distinct")
    if (
        size_strata
        and level == "field"
        and (
            len(size_bins) < 2 or any(a >= b for a, b in itertools.pairwise(size_bins))
        )
    ):
        raise ValueError("Size bins must be increasing")
    paths = [Path(path) for path in paths]
    if not paths or len(paths) != len({path.resolve() for path in paths}):
        raise ValueError("Supply nonduplicate input tables")
    out_dir = _new_output(out_dir)
    groups, availability = {}, []
    pairs = list(itertools.combinations(features, 2))

    def update(label, frame):
        key = json.dumps(label, sort_keys=True)
        if key not in groups:
            if len(groups) >= max_groups:
                raise ValueError(
                    "Too many analysis groups; raise max_groups explicitly"
                )
            group_seed = int(
                hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()[:16], 16
            )
            groups[key] = {
                "label": label,
                "n": 0,
                "finite": dict.fromkeys(features, 0),
                "minimum": dict.fromkeys(features, math.inf),
                "maximum": dict.fromkeys(features, -math.inf),
                "complete_pca_n": 0,
                "moments": {pair: PairMoments() for pair in pairs},
                "sample": [],
                "rng": np.random.default_rng(group_seed),
            }
        group = groups[key]
        for column in features:
            clean = frame.loc[np.isfinite(frame[column]), column]
            group["finite"][column] += len(clean)
            if len(clean):
                group["minimum"][column] = min(group["minimum"][column], clean.min())
                group["maximum"][column] = max(group["maximum"][column], clean.max())
        if pca_features:
            group["complete_pca_n"] += int(
                np.isfinite(frame[pca_features]).all(axis=1).sum()
            )
        for first, second in pairs:
            group["moments"][(first, second)].add(
                frame[first].to_numpy(), frame[second].to_numpy()
            )
        for values in frame[[*features, "centroid_x", "centroid_y"]].itertuples(
            index=False, name=None
        ):
            group["n"] += 1
            if len(group["sample"]) < sample_size:
                group["sample"].append(values)
            else:
                index = group["rng"].integers(0, group["n"])
                if index < sample_size:
                    group["sample"][index] = values

    for path in paths:
        parquet = pq.ParquetFile(path)
        required = list(
            dict.fromkeys(
                [
                    *features,
                    group_column,
                    "centroid_x",
                    "centroid_y",
                    *(["area_m2"] if level == "field" and size_strata else []),
                ]
            )
        )
        for batch in parquet.iter_batches(batch_size=10000, columns=required):
            frame = batch.to_pandas()
            if frame[group_column].isna().any():
                raise ValueError("Grouping column contains null values")
            for column in features:
                frame[column] = pd.to_numeric(frame[column], errors="raise").astype(
                    float
                )
                if column in log_features:
                    if (frame[column].dropna() < 0).any():
                        raise ValueError("log1p features must be nonnegative")
                    frame[column] = np.log1p(frame[column])
            update({"scope": "pooled", "stratum": "all"}, frame)
            for value, subset in frame.groupby(group_column, sort=True):
                update(
                    {"scope": "within-group", "group": str(value), "stratum": "all"},
                    subset,
                )
            if level == "field" and size_strata:
                # Bin original area, even if area is log-transformed for analysis.
                areas = (
                    np.expm1(frame.area_m2)
                    if "area_m2" in log_features
                    else frame.area_m2
                )
                strata = pd.cut(areas, size_bins, right=False)
                for value, indexes in strata.groupby(
                    strata, observed=True
                ).groups.items():
                    subset = frame.loc[indexes]
                    update({"scope": "pooled", "stratum": str(value)}, subset)
                    for group_value, local in subset.groupby(group_column, sort=True):
                        update(
                            {
                                "scope": "within-group",
                                "group": str(group_value),
                                "stratum": str(value),
                            },
                            local,
                        )
    if not groups:
        raise ValueError("No input observations are available for correlation analysis")
    rows, pca_rows, pca_status = [], [], []
    for key, group in groups.items():
        sample = pd.DataFrame(
            group["sample"], columns=[*features, "centroid_x", "centroid_y"]
        )
        sample_path = (
            "sample-" + hashlib.sha256(key.encode()).hexdigest()[:20] + ".parquet"
        )
        sample.to_parquet(out_dir / sample_path, index=False)
        for column in features:
            clean = sample[column].to_numpy()
            clean = clean[np.isfinite(clean)]
            availability.append(
                {
                    **group["label"],
                    "feature": column,
                    "population_rows": group["n"],
                    "finite_rows": group["finite"][column],
                    "sample_rows": len(sample),
                    "population_constant": group["finite"][column] > 0
                    and group["minimum"][column] == group["maximum"][column],
                    "sample_unique_values": len(np.unique(clean)),
                    "sample_file": sample_path,
                }
            )
        for first, second in pairs:
            moments = group["moments"][(first, second)]
            blocks, intervals = _bootstrap_pair(
                sample, first, second, block_size_m, bootstrap_replicates, group["rng"]
            )
            rows.append(
                {
                    **group["label"],
                    "first": first,
                    "second": second,
                    "population_pair_n": moments.n,
                    "pearson_full": moments.correlation(),
                    "sample_pair_n": int(
                        np.isfinite(sample[[first, second]]).all(axis=1).sum()
                    ),
                    "pearson_sample": _association(
                        sample[first].to_numpy(), sample[second].to_numpy(), "pearson"
                    ),
                    "spearman_sample": _association(
                        sample[first].to_numpy(), sample[second].to_numpy(), "spearman"
                    ),
                    "spatial_blocks": blocks,
                    "ci_status": "sample-conditional"
                    if blocks >= 3 and bootstrap_replicates
                    else "insufficient-blocks-or-disabled",
                    **intervals,
                }
            )
        if pca_features:
            matrix = sample[pca_features].to_numpy(dtype=float)
            matrix = matrix[np.isfinite(matrix).all(axis=1)]
            scales = matrix.std(axis=0) if len(matrix) else np.zeros(len(pca_features))
            status = (
                "ok"
                if len(matrix) >= 3 and np.all(scales > 0)
                else "insufficient-complete-rows-or-constant-feature"
            )
            pca_status.append(
                {
                    **group["label"],
                    "complete_population_rows": group["complete_pca_n"],
                    "complete_sample_rows": len(matrix),
                    "status": status,
                }
            )
            if status == "ok":
                _, singular, vectors = np.linalg.svd(
                    (matrix - matrix.mean(axis=0)) / scales, full_matrices=False
                )
                variance = singular**2 / np.sum(singular**2)
                for component, vector in enumerate(vectors):
                    for feature, loading in zip(pca_features, vector):
                        pca_rows.append(
                            {
                                **group["label"],
                                "component": component + 1,
                                "variance_fraction": variance[component],
                                "feature": feature,
                                "loading": loading,
                            }
                        )
    pd.DataFrame(rows).to_csv(out_dir / "associations.csv", index=False)
    pd.DataFrame(availability).to_csv(out_dir / "availability.csv", index=False)
    pd.DataFrame(
        pca_rows,
        columns=[
            "scope",
            "group",
            "stratum",
            "component",
            "variance_fraction",
            "feature",
            "loading",
        ],
    ).to_csv(out_dir / "pca_loadings.csv", index=False)
    pd.DataFrame(
        pca_status,
        columns=[
            "scope",
            "group",
            "stratum",
            "complete_population_rows",
            "complete_sample_rows",
            "status",
        ],
    ).to_csv(out_dir / "pca_status.csv", index=False)
    write_json(
        out_dir / "analysis.json",
        {
            "inputs": [
                {"path": str(path.resolve()), "sha256": file_digest(path)}
                for path in paths
            ],
            "features": features,
            "group_column": group_column,
            "level": level,
            "analysis_code_sha256": file_digest(__file__),
            "metric_crs": str(metric_crs),
            "log1p_features": list(log_features),
            "pca_features": pca_features,
            "sample_limit_per_group": sample_size,
            "max_groups": max_groups,
            "seed": seed,
            "block_size_m": block_size_m,
            "bootstrap_replicates": bootstrap_replicates,
            "size_bins_m2": [
                None if not np.isfinite(value) else value for value in size_bins
            ],
            "size_strata": size_strata and level == "field",
            "pearson_population": "all pairwise-finite input rows",
            "spearman_pca_ci_population": "bounded reservoir sample; block intervals conditional on sample",
            "complete": True,
        },
    )
    return pd.DataFrame(rows)
