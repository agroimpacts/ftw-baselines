"""Proposal-only four-outcome field triage; never excludes or repairs input fields."""

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from ftw_geometry.io.manifests import file_digest, write_json
from shapely.geometry import LineString, shape
from shapely.ops import nearest_points, split, unary_union

from research.geometry.describe_descriptor_pilot import single_polygon
from research.geometry.select_descriptor_pilot import now

VERSION = "shape-triage-demo-0.1"
SETTINGS = {
    "erosion_radius_fractions": [0.025, 0.05, 0.075, 0.1, 0.125, 0.15],
    "minimum_eroded_lobe_parent_area_fraction": 0.02,
    "context_radius_m": 100,
    # Exploratory strip screen, not a minimum width for a valid field.
    "exclusion_max_rectangle_width_m": 25,
    "exclusion_min_elongation": 8,
    "exclusion_max_circularity": 0.25,
    "minimum_preview_child_area_fraction": 0.05,
    "max_cut_alternatives": 3,
}
OUTCOMES = ("exclude", "repair", "retain", "abstain")

# Conversation evidence is not an exclusion label or permission to change geometry.
REVIEW_SEEDS = {
    ("ftw-s2-2024", "10SFH_0_0-8520"): "user_identified_joined_fields",
    ("ftw-s2-2024", "10SFH_0_0-9043"): "user_identified_joined_fields",
    **{
        ("ftw-s2-2024", ident): "user_rejected_neck_screen_not_a_field_exclusion_label"
        for ident in (
            "10SFH_0_0-9364", "10SFH_0_0-8820",
            "10SFH_0_0-9175", "10SFH_0_0-9369",
        )
    },
}


def field_key(collection, ident):
    return json.dumps([str(collection), str(ident)], separators=(",", ":"))


def erosion_profile(polygon):
    """Keep original boundaries; eroded lobes are diagnostic geometry only."""
    radius = math.sqrt(polygon.area / math.pi)
    profiles, lobes = [], []
    for fraction in SETTINGS["erosion_radius_fractions"]:
        distance = fraction * radius
        eroded = polygon.buffer(-distance)
        parts = list(eroded.geoms) if hasattr(eroded, "geoms") else [eroded]
        retained = sorted(
            [p for p in parts if not p.is_empty and p.area >=
             SETTINGS["minimum_eroded_lobe_parent_area_fraction"] * polygon.area],
            key=lambda p: p.area, reverse=True,
        )
        profiles.append({
            "radius_fraction": fraction, "distance_m": distance,
            "retained_lobe_area_fractions": [p.area / polygon.area for p in retained],
        })
        lobes.append(retained)
    return profiles, lobes


def validate_cut(polygon, cut, lobe_a=None, lobe_b=None):
    """Validate an independent, zero-width cut of the original polygon in memory."""
    if cut.is_empty or cut.geom_type != "LineString" or cut.length <= 0:
        return None
    tolerance = max(1e-6, polygon.area * 1e-10)
    if not polygon.buffer(1e-7).covers(cut):
        return None
    # GEOS intersections may leave clipped endpoints a few ULPs inside a ring.
    # Extend the splitter by a sub-millimetre tolerance, without moving any
    # polygon boundary or changing the recorded clipped approval geometry.
    start, end = cut.coords[0], cut.coords[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    span = math.hypot(dx, dy)
    if span == 0 or abs(span - cut.length) > 1e-7:
        return None
    epsilon = 1e-6
    splitter = LineString([
        (start[0] - epsilon * dx / span, start[1] - epsilon * dy / span),
        (end[0] + epsilon * dx / span, end[1] + epsilon * dy / span),
    ])
    children = list(split(polygon, splitter).geoms)
    if len(children) != 2 or any(
        g.geom_type != "Polygon" or not g.is_valid or g.is_empty for g in children
    ):
        return None
    shared = children[0].boundary.intersection(children[1].boundary)
    if shared.hausdorff_distance(cut) > 1e-5 or abs(shared.length - cut.length) > 1e-5:
        return None
    fractions = sorted(g.area / polygon.area for g in children)
    if fractions[0] < SETTINGS["minimum_preview_child_area_fraction"]:
        return None
    if lobe_a is not None and lobe_b is not None:
        owners = [
            max(range(2), key=lambda i: children[i].intersection(lobe).area)
            for lobe in (lobe_a, lobe_b)
        ]
        if owners[0] == owners[1]:
            return None
        # Both eroded cores must remain intact, not merely have different majorities.
        if any(lobe.difference(children[i]).area > tolerance
               for lobe, i in zip((lobe_a, lobe_b), owners)):
            return None
    union_error = unary_union(children).symmetric_difference(polygon).area
    area_error = abs(sum(g.area for g in children) - polygon.area)
    overlap = children[0].intersection(children[1]).area
    if max(union_error, area_error, overlap) > tolerance:
        return None
    return {
        "child_area_fractions": fractions,
        "union_symmetric_difference_m2": union_error,
        "absolute_area_error_m2": area_error,
        "child_overlap_m2": overlap,
        "validation_tolerance_m2": tolerance,
    }


def cut_alternatives(polygon, lobes):
    """Explore local cross-neck chords, never buffer eroded cores back outward.

    Every alternative independently splits the original into two preview children.
    Alternatives are NOT a validated multi-cut recipe and may be wrong semantically.
    """
    found = []
    span = math.hypot(polygon.bounds[2] - polygon.bounds[0],
                      polygon.bounds[3] - polygon.bounds[1]) * 2
    for parts in lobes:
        # Complex multi-lobe cases remain visible but have bounded proposal work.
        if not 2 <= len(parts) <= 4:
            continue
        for a, b in itertools.combinations(parts, 2):
            p, q = nearest_points(a, b)
            connector = LineString([p, q])
            if connector.length == 0 or not polygon.buffer(1e-7).covers(connector):
                continue
            dx, dy = q.x - p.x, q.y - p.y
            norm = math.hypot(dx, dy)
            nx, ny = -dy / norm, dx / norm
            for position in (0.25, 0.5, 0.75):
                middle = connector.interpolate(position, normalized=True)
                line = LineString([
                    (middle.x - span * nx, middle.y - span * ny),
                    (middle.x + span * nx, middle.y + span * ny),
                ])
                clipped = polygon.intersection(line)
                chords = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
                for chord in chords:
                    if chord.geom_type != "LineString" or chord.distance(middle) > 1e-6:
                        continue
                    # Validation extends endpoints only to overcome ULP-scale
                    # clipping errors, not to search for a different neck.
                    checks = validate_cut(polygon, chord, a, b)
                    if checks is None:
                        continue
                    found.append((chord, checks))
    selected = []
    for chord, checks in sorted(found, key=lambda item: item[0].length):
        if any(chord.hausdorff_distance(old[0]) < max(2.5, chord.length * 0.25)
               for old in selected):
            continue
        selected.append((chord, checks))
        if len(selected) == SETTINGS["max_cut_alternatives"]:
            break
    return selected


def classify(row, profile, has_cut, context_complete, seed=None):
    """Exploratory routing, not calibrated detection accuracy or approval."""
    if seed == "user_identified_joined_fields":
        return "repair", "User-identified joined valid fields; review each exact cut."
    if seed == "user_rejected_neck_screen_not_a_field_exclusion_label":
        return "abstain", "User rejected neck interpretation; field validity remains unlabelled."
    if not context_complete:
        return "abstain", "Incomplete 100 m exterior context in saved extract."
    thin = (
        row["rectangle_width_m"] <= SETTINGS["exclusion_max_rectangle_width_m"]
        and row["elongation"] >= SETTINGS["exclusion_min_elongation"]
        and row["circularity"] < SETTINGS["exclusion_max_circularity"]
    )
    if thin:
        return "exclude", "Very thin elongated shape: investigate non-field detection; may be a valid narrow field."
    if row["narrow_neck"]:
        counts = [len(p["retained_lobe_area_fractions"]) for p in profile]
        if has_cut and counts.count(2) >= 3 and max(counts) == 2:
            return "repair", "Persistent two-lobe screen with a geometric cut; not proof of joined fields."
        return "abstain", "Neck screen is scale-sensitive or complex; no simple supported cut."
    return "retain", "No selected shape rule triggered; not a verification of field validity."


def verify_inputs(source, descriptors, window_id):
    """Verify retrieval artifacts and the frozen descriptor subset used by this run."""
    retrieval = json.loads((source / "complete.json").read_text())
    expected = {source / name: digest for name, digest in retrieval["sha256"].items()}
    manifest_path = descriptors.parent / "complete.json"
    manifest = json.loads(manifest_path.read_text())
    for name in ("descriptors.parquet", "corrected-component-audit.csv"):
        relative = f"{window_id}/{name}"
        expected[descriptors / name] = manifest["output_sha256"][relative]
    for path, digest in expected.items():
        if file_digest(path) != digest:
            raise ValueError(f"Changed input artifact: {path}")
    for path in (source / "complete.json", manifest_path):
        expected[path] = file_digest(path)
    return {str(path): digest for path, digest in expected.items()}


def build_candidates(fields, measured, window, metric_crs):
    """Keep assigned originals and collection-qualified identities; context is separate."""
    fields, measured = fields.copy(), measured.copy()
    for frame in (fields, measured):
        frame["field_key"] = [field_key(c, i) for c, i in zip(frame.collection, frame.id)]
        if frame.field_key.duplicated().any():
            raise ValueError("Duplicate collection-qualified field identity")
    sources = fields.set_index("field_key")
    for row in measured.itertuples():
        if row.field_key not in sources.index or not single_polygon(row.geometry).equals(
            single_polygon(sources.loc[row.field_key].geometry)
        ):
            raise ValueError("Assigned geometry differs from source")
    measured.geometry = measured.geometry.map(single_polygon)
    metric = measured.to_crs(metric_crs)
    boundary = gpd.GeoSeries([shape(window["geometry"])], crs=4326).to_crs(metric_crs).iloc[0]
    records, cuts = [], []
    for (_, row), polygon in zip(measured.iterrows(), metric.geometry):
        if polygon.geom_type != "Polygon" or not polygon.is_valid or polygon.is_empty:
            raise ValueError("Triage requires valid complete projected polygons")
        profile, lobes = erosion_profile(polygon)
        clearance = polygon.distance(boundary.boundary) if boundary.covers(polygon) else -1
        context_complete = clearance >= SETTINGS["context_radius_m"]
        seed = REVIEW_SEEDS.get((str(row.collection), str(row.id)))
        alternatives = cut_alternatives(polygon, lobes) if row.narrow_neck else []
        outcome, reason = classify(row, profile, bool(alternatives), context_complete, seed)
        parent_digest = hashlib.sha256(sources.loc[row.field_key].geometry.wkb).hexdigest()
        proposal_ids = []
        for cut, checks in alternatives:
            cut = shapely.normalize(cut)
            digest_input = json.dumps({
                "version": VERSION, "settings": SETTINGS, "field_key": row.field_key,
                "source_geometry_sha256": parent_digest,
                "metric_crs": str(metric_crs), "cut_wkb_hex": cut.wkb_hex,
            }, sort_keys=True)
            proposal_id = hashlib.sha256(digest_input.encode()).hexdigest()[:24]
            proposal_ids.append(proposal_id)
            cuts.append({
                "field_key": row.field_key, "proposal_id": proposal_id,
                "source_geometry_sha256": parent_digest,
                "metric_crs": str(metric_crs), "cut_wkt": cut.wkt,
                "length_m": cut.length, **checks, "geometry": cut,
                "approval_status": "pending", "applied": False,
            })
        records.append({
            "field_key": row.field_key, "id": str(row.id), "collection": str(row.collection),
            "proposed_outcome": outcome, "reason": reason,
            "conversation_evidence": seed or "none",
            "source_geometry_sha256": parent_digest,
            "context_100m_complete": bool(context_complete),
            "window_edge_clearance_m": clearance,
            "source_seam_status": "unknown",
            "area_ha": float(row.area_m2 / 10000),
            **{key: float(row[key]) for key in (
                "elongation", "rectangle_width_m", "circularity", "solidity",
                "rectangularity", "hole_count",
            )},
            "narrow_neck": bool(row.narrow_neck),
            "erosion_profile": profile, "cut_proposal_ids": proposal_ids,
            "approval_status": "pending", "applied": False,
        })
    return records, cuts


def run(pilot_root, out, window_id="california_61_424"):
    root, out = Path(pilot_root).expanduser().resolve(), Path(out).expanduser().resolve()
    # Only a new sibling directory under the pilot root (or an external directory).
    protected = [root / "polygon-review-2024", root / "descriptor-review-2024"]
    if out == root or out in root.parents or any(
        out == p or p in out.parents or out in p.parents for p in protected
    ):
        raise ValueError("Use a separate output directory; preserve original artifacts")
    if root in out.parents and out.parent != root:
        raise ValueError("Use a new sibling directory; preserve existing study directories")
    if Path(window_id).name != window_id:
        raise ValueError("window_id must be a single directory name")
    if out.exists():
        raise ValueError("Use a fresh output directory")
    source = root / "polygon-review-2024" / window_id
    descriptors = root / "descriptor-review-2024" / window_id
    input_hashes = verify_inputs(source, descriptors, window_id)
    window = json.loads((source / "provenance.json").read_text())["window"]
    metric_crs = window["properties"]["metric_crs"]
    fields = gpd.read_parquet(source / "fields.parquet")
    measured = gpd.read_parquet(descriptors / "descriptors.parquet")
    records, cuts = build_candidates(fields, measured, window, metric_crs)
    identity = {
        "version": VERSION, "settings": SETTINGS, "inputs": input_hashes,
        "source_sha256": file_digest(Path(__file__)),
        "template_sha256": file_digest(Path(__file__).with_name("triage_review.html")),
    }
    run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    counts = {outcome: sum(r["proposed_outcome"] == outcome for r in records)
              for outcome in OUTCOMES}
    out.mkdir(parents=True)
    write_json(out / "candidates.json", records)
    write_json(out / "cut-proposals.json", [
        {k: v for k, v in cut.items() if k != "geometry"} for cut in cuts
    ])
    pd.DataFrame([{k: v for k, v in r.items() if k not in
                   ("erosion_profile", "cut_proposal_ids")} for r in records]).to_csv(
        out / "candidates.csv", index=False
    )
    cut_geojson = {"type": "FeatureCollection", "features": []}
    if cuts:
        cut_frame = gpd.GeoDataFrame(cuts, crs=metric_crs).to_crs(4326)
        cut_geojson = json.loads(cut_frame.to_json())
    write_json(out / "cut-proposals.geojson", cut_geojson)
    payload = {
        "run_id": run_id, "version": VERSION, "window": window,
        "candidates": records, "cuts": cut_geojson,
        "fields": json.loads(measured[["collection", "id", "geometry"]].to_crs(4326).to_json()),
        "context": json.loads(fields[["collection", "id", "geometry"]].to_crs(4326).to_json()),
        "counts": counts, "settings": SETTINGS,
    }
    template = Path(__file__).with_name("triage_review.html").read_text()
    (out / "index.html").write_text(template.replace(
        "__TRIAGE_PAYLOAD__", json.dumps(payload, allow_nan=False).replace("<", "\\u003c")
    ))
    (out / "triage-source.py").write_bytes(Path(__file__).read_bytes())
    (out / "triage-template.html").write_text(template)
    (out / "README.md").write_text(
        f"# Four-outcome triage demo: {window_id}\n\n"
        f"Algorithm {VERSION}; run {run_id}. Open index.html.\n\n"
        f"Proposal counts: {json.dumps(counts)}. All {len(records)} assigned fields remain unchanged.\n\n"
        "These are uncalibrated review routes, not confirmed errors or accuracy estimates. "
        "Retain means no selected rule triggered, not validated correctness. Thin-field "
        "exclusions may be valid fields. Conversation rejections of neck flags are NOT "
        "field-exclusion labels. Imagery dates vary and need not match 2024.\n\n"
        "Context is window-intersecting polygons only, with no downloaded halo; "
        "100 m completeness is guarded against window edges. Source seam status is unknown. "
        "User-identified repair cases remain visible even with incomplete context.\n\n"
        "Cuts are independent alternatives, not a multi-cut recipe. In-memory preview "
        "checks establish geometry conservation only, not semantic correctness or "
        "cut placement accuracy. No children or repaired datasets are written. "
        "Neighbor overlaps cannot increase in exact arithmetic because preview children "
        "partition the parent; a future application must audit them explicitly.\n\n"
        "The review page exports labels tied to run, parent geometry and proposal IDs. "
        "Labels do not authorize application. Exact exclusions/cuts require separate "
        "approval before a future versioned derivative is written. No apply command exists.\n"
    )
    # Recheck the inputs after generation, before marking the run complete.
    for path, digest in input_hashes.items():
        if file_digest(path) != digest:
            raise ValueError(f"Input changed during generation: {path}")
    write_json(out / "complete.json", {
        "completed_at": now(), "algorithm": VERSION, "run_id": run_id,
        "settings": SETTINGS, "window_id": window_id, "metric_crs": metric_crs,
        "counts": counts, "assigned_count": len(records), "context_count": len(fields),
        "cut_alternative_count": len(cuts), "input_sha256": input_hashes,
        "repairs_applied": 0, "exclusions_applied": 0,
        "approval_required": True,
        "environment": {"shapely": shapely.__version__, "geos": shapely.geos_version_string,
                        "geopandas": gpd.__version__},
        "output_sha256": {p.name: file_digest(p) for p in sorted(out.iterdir()) if p.is_file()},
    })
    print(json.dumps({"out": str(out), "counts": counts, "cuts": len(cuts)}, indent=2))
    return records, cuts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot_root")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--window_id", default="california_61_424")
    args = parser.parse_args()
    run(args.pilot_root, args.out_dir, args.window_id)
