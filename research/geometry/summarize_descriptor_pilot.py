"""Regional landscape profiles of the primary FTW pilot windows."""

import argparse
import html
import json
import math
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from ftw_geometry.core import analysis as geometry_analysis
from ftw_geometry.core.analysis import summarize_regions
from ftw_geometry.core.descriptors import DESCRIPTOR_COLUMNS
from ftw_geometry.io.manifests import file_digest, write_json
from shapely.geometry import shape

from research.geometry.describe_descriptor_pilot import single_polygon
from research.geometry.select_descriptor_pilot import now

GAP_RADII = (50, 100, 250)
PROFILE_FEATURES = (
    "area_m2",
    "circularity",
    "elongation",
    "solidity",
    "rectangularity",
    "convex_hull_index",
    "hole_area_fraction",
    "perimeter_m",
)


def verify(root, key):
    manifest = json.loads((root / "complete.json").read_text())
    for name, digest in manifest[key].items():
        if file_digest(root / name) != digest:
            raise ValueError(f"Changed input artifact: {root / name}")
    return manifest


def measured_context(fields, measured, crs):
    """Reuse frozen measurements; unassigned context needs geometry, not descriptors."""
    fields = fields.copy()
    fields.geometry = fields.geometry.map(single_polygon)
    keys = [json.dumps([str(c), str(i)]) for c, i in zip(fields.collection, fields.id)]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate collection-qualified IDs in extract")
    fields["field_key"] = pd.Series(keys, index=fields.index, dtype="str")
    measured = measured.copy()
    measured["field_key"] = pd.Series(
        [
            json.dumps([str(c), str(i)])
            for c, i in zip(measured.collection, measured.id)
        ],
        index=measured.index,
        dtype="str",
    )
    if measured.field_key.duplicated().any():
        raise ValueError("Duplicate assigned field identities")
    if not set(measured.field_key).issubset(keys):
        raise ValueError("Assigned fields absent from extract")
    if not fields.is_valid.all():
        raise ValueError("Invalid source polygon in extract")
    source_geometry = fields.set_index("field_key").geometry
    for row in measured.itertuples():
        if not source_geometry.loc[row.field_key].equals(single_polygon(row.geometry)):
            raise ValueError("Frozen descriptor geometry differs from source")
    columns = ["field_key", *DESCRIPTOR_COLUMNS[1:]]
    values = measured[columns]
    projected = fields.to_crs(crs)
    table = projected.drop(columns="geometry").merge(
        values, on="field_key", how="left", validate="one_to_one"
    )
    geometries = projected.set_index("field_key").geometry.loc[table.field_key]
    table["geometry_wkb"] = geometries.to_wkb().to_numpy()
    # Release schema does not identify seams or original vectorization edges.
    table["touches_source_edge"] = pd.array([None] * len(table), dtype="boolean")
    return table


def write_context_dataset(table, crs, destination):
    """Persist a verified adapter to the generic regional-analysis table schema."""
    part = destination / "sources" / "extract"
    part.mkdir(parents=True)
    table.to_parquet(part / "part.parquet", index=False)
    write_json(
        part / "complete.json",
        {
            "parts": [
                {"file": "part.parquet", "sha256": file_digest(part / "part.parquet")}
            ]
        },
    )
    write_json(
        destination / "manifest.json",
        {
            "metric_crs": crs,
            "sources": [{"source_id": "window-extract", "partition": "extract"}],
            "adapter": "Frozen assigned descriptors; unassigned context descriptors are null",
            "spatial_extent": "window-intersecting polygons only; no halo retrieval",
        },
    )


def enrich_summary(summary, assigned, boundary, radii=GAP_RADII):
    """Guard spacing against missing exterior context and summarize rare features."""
    assigned = assigned.copy()
    area = assigned.area_m2.to_numpy(dtype=float)
    total = area.sum()
    summary["narrow_neck_area_fraction"] = (
        float(area[assigned.narrow_neck.to_numpy(dtype=bool)].sum() / total)
        if total
        else math.nan
    )
    summary["fields_with_holes_area_fraction"] = (
        float(area[assigned.hole_count.to_numpy() > 0].sum() / total)
        if total
        else math.nan
    )
    holes = float(assigned.hole_area_m2.sum())
    summary["hole_area_fraction_of_enclosed_area"] = (
        holes / (total + holes) if total else math.nan
    )
    summary["orientation_ambiguous_fraction"] = (
        float(assigned.orientation_ambiguous.mean()) if len(assigned) else math.nan
    )
    geometries = gpd.GeoSeries.from_wkb(
        assigned.geometry_wkb, crs=summary["metric_crs"]
    )
    clearance = np.array(
        [
            g.distance(boundary.boundary) if boundary.covers(g) else -1.0
            for g in geometries
        ]
    )
    gaps = assigned.nearest_positive_gap_m.to_numpy(dtype=float)
    rows = []
    assigned["sampling_edge_clearance_m"] = clearance
    for radius in radii:
        complete = clearance > radius
        observed = complete & np.isfinite(gaps) & (gaps <= radius)
        values = gaps[observed]
        prefix = f"gap_{radius}m"
        assigned[prefix + "_context_complete"] = complete
        rows.append(
            {
                "window_id": summary["region_id"],
                "zone_id": summary["zone_id"],
                "radius_m": radius,
                "assigned_fields": len(assigned),
                "context_complete_fields": int(complete.sum()),
                "edge_context_incomplete_fields": int((~complete).sum()),
                "observed_fields": int(observed.sum()),
                "radius_censored_fields": int((complete & ~observed).sum()),
                "mean_observed_gap_m": float(values.mean())
                if len(values)
                else math.nan,
                "median_observed_gap_m": float(np.median(values))
                if len(values)
                else math.nan,
                "q95_observed_gap_m": float(np.quantile(values, 0.95))
                if len(values)
                else math.nan,
            }
        )
    # Generic outputs remain available in per-window folders, explicitly extract-only.
    for name in (
        "positive_gap_observed_count",
        "positive_gap_censored_count",
        "mean_observed_positive_gap_m",
    ):
        summary["extract_only_" + name] = summary.pop(name)
    return summary, assigned, rows


def plot_profiles(regions, out, *, population_label="Primary", figure_height=14):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = regions.region_id.tolist()
    zones = sorted(regions.zone_id.unique())
    colors = {z: plt.get_cmap("tab10")(i) for i, z in enumerate(zones)}
    y = np.arange(len(regions))
    fig, axes = plt.subplots(2, 4, figsize=(20, figure_height), sharey=True)
    for ax, feature in zip(axes.flat, PROFILE_FEATURES):
        for pos, row in regions.iterrows():
            color = colors[row.zone_id]
            if row.field_count == 0:
                continue
            ax.plot(
                [row[feature + "_q05"], row[feature + "_q95"]],
                [pos, pos],
                color=color,
                lw=1,
            )
            ax.plot(
                [row[feature + "_q25"], row[feature + "_q75"]],
                [pos, pos],
                color=color,
                lw=5,
            )
            ax.plot(row[feature + "_q50"], pos, "o", color="black", ms=3)
            ax.plot(row[feature + "_area_weighted_mean"], pos, "x", color=color, ms=6)
        if feature in {"area_m2", "perimeter_m", "elongation"}:
            ax.set_xscale("log")
        ax.set_title(feature)
        ax.set_yticks(y, labels)
        ax.grid(axis="x", alpha=0.2)
    axes[0, 0].invert_yaxis()
    fig.suptitle(
        f"{population_label} windows: 5–95% range, thick 25–75%, dot median, × area-weighted mean\nEmpty windows have no shape observations; values describe detected fields"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out / "descriptor-profiles.png", dpi=160)
    plt.close(fig)
    metrics = [
        "field_count",
        "mapped_fraction",
        "narrow_neck_fraction",
        "polygons_with_holes_fraction",
        "orientation_resultant",
        "orientation_ambiguous_fraction",
    ]
    fig, axes = plt.subplots(2, 3, figsize=(18, figure_height), sharey=True)
    for ax, metric in zip(axes.flat, metrics):
        ax.barh(y, regions[metric], color=[colors[z] for z in regions.zone_id])
        ax.set_yticks(y, labels)
        ax.set_title(metric)
        ax.grid(axis="x", alpha=0.2)
    axes[0, 0].invert_yaxis()
    fig.suptitle(
        f"Mapped landscape characteristics — {population_label.lower()} 10 km windows"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out / "landscape-profiles.png", dpi=160)
    plt.close(fig)


def run(review, descriptors, out, *, expected_windows=21, max_fields=100000):
    review, descriptors, out = [
        Path(p).expanduser().resolve() for p in (review, descriptors, out)
    ]
    if out in {review, descriptors} or any(
        root in out.parents for root in (review, descriptors)
    ):
        raise ValueError("Use a separate output directory")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a fresh output directory")
    verify(descriptors, "output_sha256")
    inventory = pd.read_csv(descriptors / "window-summary.csv")
    inventory = inventory.loc[inventory.role.eq("primary")].sort_values("window_id")
    if len(inventory) != expected_windows or not inventory.window_id.is_unique:
        raise ValueError("Unexpected primary window inventory")
    out.mkdir(parents=True, exist_ok=True)
    summaries, distributions, gap_rows, hashes, seen, links = [], [], [], {}, set(), []
    for entry in inventory.itertuples():
        wid = entry.window_id
        source = review / wid
        verify(source, "sha256")
        provenance = json.loads((source / "provenance.json").read_text())
        window = provenance["window"]
        props = window["properties"]
        if props["role"] != "primary" or props["window_id"] != wid:
            raise ValueError("Window provenance does not match primary inventory")
        fields = gpd.read_parquet(source / "fields.parquet")
        if len(fields) > max_fields:
            raise ValueError("Window extract exceeds max_fields")
        measured = gpd.read_parquet(descriptors / wid / "descriptors.parquet")
        keys = set(zip(measured.collection.astype(str), measured.id.astype(str)))
        if seen & keys:
            raise ValueError("Repeated assigned identity across windows")
        seen.update(keys)
        crs = props["metric_crs"]
        boundary = (
            gpd.GeoSeries([shape(window["geometry"])], crs=4326).to_crs(crs).iloc[0]
        )
        destination = out / wid
        destination.mkdir()
        table = measured_context(fields, measured, crs)
        write_context_dataset(table, crs, destination / "context-dataset")
        region = gpd.GeoDataFrame({"window_id": [wid]}, geometry=[boundary], crs=crs)
        # Use a projected GPKG for the generic region reader.
        region.to_file(destination / "window.gpkg", driver="GPKG")
        result = summarize_regions(
            destination / "context-dataset",
            destination / "window.gpkg",
            destination / "regional",
            region_id="window_id",
            edge_policy="include",
            gap_radius_m=max(GAP_RADII),
            max_fields=max_fields,
        )
        summary = result.iloc[0].to_dict()
        summary.update(zone_id=props["zone_id"], metric_crs=crs)
        projected = fields.to_crs(crs)
        summary["projection_invalid_context_count"] = int((~projected.is_valid).sum())
        summary["clipped_invalid_count"] = int(
            (~projected.geometry.intersection(boundary).is_valid).sum()
        )
        if summary["clipped_invalid_count"]:
            raise ValueError(
                "Invalid clipped coverage geometry; investigate without repair"
            )
        assigned_path = (
            destination / "regional" / "assigned_fields" / "region-000000.parquet"
        )
        assigned = (
            pd.read_parquet(assigned_path)
            if assigned_path.exists()
            else table.iloc[:0].copy()
        )
        if not len(assigned):
            assigned["nearest_positive_gap_m"] = pd.Series(dtype=float)
        if set(assigned.field_key) != {json.dumps([c, i]) for c, i in keys}:
            raise ValueError(
                "Regional assignment differs from frozen descriptor population"
            )
        summary, assigned, gaps = enrich_summary(summary, assigned, boundary)
        assigned.to_parquet(destination / "assigned-fields.parquet", index=False)
        summaries.append(summary)
        gap_rows.extend(gaps)
        distributions.append(
            pd.read_csv(destination / "regional" / "distributions.csv")
        )
        for path in (
            source / "complete.json",
            source / "fields.parquet",
            source / "provenance.json",
            descriptors / wid / "descriptors.parquet",
        ):
            hashes[str(path)] = file_digest(path)
        link = Path(os.path.relpath(descriptors / wid / "review.html", out))
        links.append(
            f'<li><a href="{html.escape(str(link))}">{html.escape(wid)}</a>: {len(assigned):,} fields</li>'
        )
        print(
            f"{wid}: {len(assigned):,} assigned, {summary['mapped_fraction']:.3%} mapped",
            flush=True,
        )
    regions = pd.DataFrame(summaries).reset_index(drop=True)
    regions.to_csv(out / "regions.csv", index=False)
    regions.to_parquet(out / "regions.parquet", index=False)
    pd.concat(distributions, ignore_index=True).to_csv(
        out / "distributions.csv", index=False
    )
    pd.DataFrame(gap_rows).to_csv(out / "gap-sensitivity.csv", index=False)
    plot_profiles(regions, out)
    (out / "README.md").write_text(
        "# FTW pilot regional landscape profiles\n\n"
        "21 primary windows; diagnostic excluded. Each window is one regional observation.\n"
        "Whole fields assigned by metric representative point; coverage uses clipped intersections of all extracted fields.\n"
        "All numeric/boolean descriptors have finite counts, means, area-weighted means and 5/25/50/75/95% quantiles.\n"
        "Orientation uses doubled angles and reports alignment and ambiguity. Directions are projected-grid axial angles.\n\n"
        "## Files\n\n"
        "- `regions.csv` / `.parquet`: all regional measurements.\n"
        "- `descriptor-profiles.png`: shape/size distributions and area-weighted means.\n"
        "- `landscape-profiles.png`: abundance, coverage, rare features and orientation.\n"
        "- `distributions.csv`: size and orientation counts.\n"
        "- `gap-sensitivity.csv`: 50/100/250 m search radii, complete-context eligibility and censoring.\n"
        "- Per-window `assigned-fields.parquet`: individual gaps and edge-context flags.\n"
        "- Per-window `regional/`: generic outputs; gaps there use only extracted polygons and are unguarded.\n\n"
        "## Interpretation limits\n\n"
        "These describe published mapped fields, conditional on detection. Rwanda has known missing detections; its empty window is retained.\n"
        "Mapped coverage uses the entire window, not an agricultural-land denominator.\n"
        "No halo was retrieved. Main gap summaries require the entire field to be more than the search radius inside the window.\n"
        "Touching/overlapping neighbors are ignored for strictly positive gaps. Censored observations are not zeros; observed means are conditional.\n"
        "Unknown release seams/source edges are retained and counted. Sampling edges do not truncate whole-field descriptors.\n"
        "Unassigned context descriptors are null. Projection-invalid context and clipped-invalid counts are explicit; no geometry repair is performed.\n"
        "No reference accuracy, inference, repair, regional PCA, significance tests or confidence intervals were run.\n"
    )
    (out / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>FTW regional landscape profiles</title>'
        "<h1>FTW regional landscape profiles</h1><p>21 primary windows; detected fields only. "
        "Rwanda missing detections affect interpretation. Empty window retained.</p>"
        '<p><a href="README.md">Methods and limitations</a> · <a href="regions.csv">Regional table</a> · '
        '<a href="gap-sensitivity.csv">Spacing sensitivity</a></p>'
        '<img src="descriptor-profiles.png" style="max-width:100%"><img src="landscape-profiles.png" style="max-width:100%">'
        "<h2>Field descriptor maps</h2><ul>" + "".join(links) + "</ul>"
    )
    for path, digest in hashes.items():
        if file_digest(path) != digest:
            raise ValueError(f"Input changed during analysis: {path}")
    write_json(
        out / "complete.json",
        {
            "completed_at": now(),
            "primary_windows": len(regions),
            "assigned_fields": len(seen),
            "input_sha256": hashes,
            "descriptor_manifest_sha256": file_digest(descriptors / "complete.json"),
            "code_sha256": {
                str(p): file_digest(p)
                for p in [Path(__file__), Path(geometry_analysis.__file__)]
            },
            "gap_radii_m": list(GAP_RADII),
            "halo_retrieved": False,
            "output_sha256": {
                str(p.relative_to(out)): file_digest(p)
                for p in sorted(out.rglob("*"))
                if p.is_file()
            },
        },
    )
    return regions


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review")
    parser.add_argument("descriptors")
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(args.review, args.descriptors, args.out_dir)
