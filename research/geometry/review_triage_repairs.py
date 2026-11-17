"""Targeted split-set and exact-union previews; no map corrections are applied."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from ftw_geometry.core.descriptors import polygon_descriptors
from ftw_geometry.io.manifests import file_digest, write_json
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, maximum_flow
from shapely.geometry import shape
from shapely.ops import unary_union

from research.geometry.select_descriptor_pilot import now
from research.geometry.triage_descriptor_pilot import (
    erosion_profile,
    field_key,
    verify_inputs,
)

VERSION = "targeted-repair-preview-0.1"
SETTINGS = {
    "capacity_units_per_m": 100,
    "minimum_child_parent_area_fraction": 0.02,
    "max_triangles": 4000,
    "max_cut_length_m": 100,
    "context_radius_m": 100,
    "max_alternatives": 3,
    "max_coreless_fragment_parent_fraction": 0.001,
}
SPLIT_TARGETS = {"10SFH_0_0-8520": None, "10SFH_0_0-9043": None,
                 "10SFH_0_0-8617": 3}
MERGE_IDS = ("10SFH_0_0-8571", "10SFH_0_0-8581")
COLLECTION = "ftw-s2-2024"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def partition_checks(parent, children):
    """Validate a complete original-boundary partition, including holes."""
    if len(children) < 2 or any(
        g.geom_type != "Polygon" or g.is_empty or not g.is_valid for g in children
    ):
        return None
    tolerance = max(1e-6, parent.area * 1e-10)
    fractions = sorted(g.area / parent.area for g in children)
    if fractions[0] < SETTINGS["minimum_child_parent_area_fraction"]:
        return None
    union = unary_union(children)
    union_error = union.symmetric_difference(parent).area
    area_error = abs(sum(g.area for g in children) - parent.area)
    overlap = sum(a.intersection(b).area for a, b in itertools.combinations(children, 2))
    if max(union_error, area_error, overlap) > tolerance:
        return None
    return {"child_area_fractions": fractions, "union_error_m2": union_error,
            "area_error_m2": area_error, "sibling_overlap_m2": overlap,
            "tolerance_m2": tolerance}


def triangle_graph(parent):
    if not hasattr(shapely, "constrained_delaunay_triangles"):
        raise ValueError("Split-set previews require Shapely >=2.1 and GEOS >=3.10")
    triangles = list(shapely.constrained_delaunay_triangles(parent).geoms)
    if not triangles or len(triangles) > SETTINGS["max_triangles"]:
        raise ValueError("Triangulation exceeds the bounded preview limit")
    if unary_union(triangles).symmetric_difference(parent).area > max(1e-6, parent.area * 1e-10):
        raise ValueError("Triangulation does not conserve original polygon")
    tree = shapely.STRtree(triangles)
    edges = []
    for i, triangle in enumerate(triangles):
        for j in tree.query(triangle, predicate="intersects"):
            j = int(j)
            if j <= i:
                continue
            shared = triangle.boundary.intersection(triangles[j].boundary)
            if shared.length > 1e-6:
                edges.append((i, j, shared))
    return triangles, edges


def terminal_cut(triangles, edges, cores, isolated):
    """Minimum-length dual-graph cut isolating one erosion core from the others.

    Integer capacities quantize edge lengths to centimetres; geometry stays exact.
    This is not an image-derived boundary or a globally optimal multiway cut.
    """
    owners = [set() for _ in triangles]
    for label, core in enumerate(cores):
        for i, triangle in enumerate(triangles):
            if triangle.intersection(core).area > max(1e-6, triangle.area * 1e-9):
                owners[i].add(label)
    if any(len(labels) > 1 for labels in owners):
        return None
    if any(not any(label in labels for labels in owners) for label in range(len(cores))):
        return None
    capacities = [max(1, round(edge.length * SETTINGS["capacity_units_per_m"]))
                  for _, _, edge in edges]
    infinite = 1 + 2 * sum(capacities)
    if infinite >= 2**31:
        raise ValueError("Flow capacities exceed bounded integer range")
    source, sink = len(triangles), len(triangles) + 1
    rows, cols, values = [], [], []
    for (i, j, _), capacity in zip(edges, capacities):
        rows.extend((i, j))
        cols.extend((j, i))
        values.extend((capacity, capacity))
    for i, labels in enumerate(owners):
        if labels:
            a, b = (source, i) if isolated in labels else (i, sink)
            rows.append(a)
            cols.append(b)
            values.append(infinite)
    graph = csr_matrix((np.array(values, dtype=np.int64), (rows, cols)),
                       shape=(sink + 1, sink + 1))
    flow = maximum_flow(graph, source, sink)
    residual = (graph - flow.flow).tocsr()
    visited, stack = {source}, [source]
    while stack:
        i = stack.pop()
        for index in range(residual.indptr[i], residual.indptr[i + 1]):
            j = int(residual.indices[index])
            if residual.data[index] > 0 and j not in visited:
                visited.add(j)
                stack.append(j)
    return {index for index, (i, j, _) in enumerate(edges) if (i in visited) != (j in visited)}


def graph_partition(parent, triangles, edges, cores):
    removed = set()
    for isolated in range(1 if len(cores) == 2 else len(cores)):
        cut = terminal_cut(triangles, edges, cores, isolated)
        if cut is None:
            return None
        removed.update(cut)
    def components():
        rows, cols = [], []
        for index, (i, j, _) in enumerate(edges):
            if index not in removed:
                rows.extend((i, j))
                cols.extend((j, i))
        adjacency = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(triangles),) * 2)
        return connected_components(adjacency, directed=False)

    count, labels = components()
    consolidated_area = 0.0
    # Uniting isolating cuts can strand tiny coreless triangle cells. Restore
    # their longest boundary connection to a core-bearing component. This moves
    # no original boundary and never discards area; large coreless pieces abstain.
    for _ in range(len(cores) + 1):
        if count <= len(cores):
            break
        anchored = set()
        for core in cores:
            areas = [sum(t.intersection(core).area for t, label in zip(triangles, labels) if label == i)
                     for i in range(count)]
            anchored.add(int(np.argmax(areas)))
        orphans = [i for i in range(count) if i not in anchored]
        if not orphans:
            return None
        orphan = orphans[0]
        area = sum(t.area for t, label in zip(triangles, labels) if label == orphan)
        if area > parent.area * SETTINGS["max_coreless_fragment_parent_fraction"]:
            return None
        connections = {}
        for i, j, edge in edges:
            a, b = int(labels[i]), int(labels[j])
            if a == orphan and b in anchored:
                connections[b] = connections.get(b, 0.0) + edge.length
            if b == orphan and a in anchored:
                connections[a] = connections.get(a, 0.0) + edge.length
        if not connections:
            return None
        target = max(connections, key=connections.get)
        removed.difference_update(index for index, (i, j, _) in enumerate(edges)
                                  if {int(labels[i]), int(labels[j])} == {orphan, target})
        consolidated_area += area
        count, labels = components()
    if count != len(cores):
        return None
    children = [unary_union([t for t, label in zip(triangles, labels) if label == i])
                for i in range(count)]
    checks = partition_checks(parent, children)
    if checks is None:
        return None
    tolerance = checks["tolerance_m2"]
    owners = [max(range(count), key=lambda i: children[i].intersection(core).area) for core in cores]
    if len(set(owners)) != len(cores) or any(
        core.difference(children[i]).area > tolerance for core, i in zip(cores, owners)
    ):
        return None
    cuts = unary_union([edges[index][2] for index in sorted(removed)])
    if cuts.length > SETTINGS["max_cut_length_m"]:
        return None
    def lines(geometry):
        if geometry.geom_type == "LineString":
            return [geometry]
        return [line for part in getattr(geometry, "geoms", []) for line in lines(part)]

    actual_shared = unary_union([line for a, b in itertools.combinations(children, 2)
                                for line in lines(a.boundary.intersection(b.boundary))])
    if (actual_shared.hausdorff_distance(cuts) > 1e-5
            or abs(actual_shared.length - cuts.length) > 1e-5):
        return None
    children.sort(key=lambda g: (-g.area, g.wkb_hex))
    return {"children": children, "cuts": cuts, "checks": checks,
            "total_cut_length_m": cuts.length, "triangle_count": len(triangles),
            "coreless_fragment_reconnected_area_m2": consolidated_area}


def split_previews(parent, expected_count=None):
    """Keep entire original triangle cells; never regrow eroded cores."""
    profiles, lobe_sets = erosion_profile(parent)
    triangles, edges = triangle_graph(parent)
    proposals = []
    for profile, cores in zip(profiles, lobe_sets):
        if not 2 <= len(cores) <= 4 or (expected_count and len(cores) != expected_count):
            continue
        proposal = graph_partition(parent, triangles, edges, cores)
        if proposal is None:
            continue
        if any(proposal["cuts"].hausdorff_distance(old["cuts"]) < 2.5 for old in proposals):
            continue
        proposal["erosion_distance_m"] = profile["distance_m"]
        proposal["core_count"] = len(cores)
        proposals.append(proposal)
    proposals.sort(key=lambda p: p["total_cut_length_m"])
    return proposals[:SETTINGS["max_alternatives"]], profiles


def exact_union(parents):
    """No gap filling, snapping, hull replacement or buffering."""
    union = unary_union(parents)
    if union.is_empty or not union.is_valid or union.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Exact union is not valid polygonal geometry")
    parts = list(union.geoms) if union.geom_type == "MultiPolygon" else [union]
    return {"geometry": union, "component_count": len(parts),
            "parent_gap_m": parents[0].distance(parents[1]),
            "parent_overlap_m2": parents[0].intersection(parents[1]).area,
            "shared_parent_boundary_m": parents[0].boundary.intersection(parents[1].boundary).length,
            "added_area_m2": union.difference(unary_union(parents)).area,
            "single_field_descriptor_available": union.geom_type == "Polygon"}


def validate_reviews(path, triage):
    manifest = json.loads((triage / "complete.json").read_text())
    for name, digest in manifest["output_sha256"].items():
        if file_digest(triage / name) != digest:
            raise ValueError(f"Changed triage artifact: {name}")
    review = json.loads(path.read_text())
    if review["run_id"] != manifest["run_id"] or review["application_authorized"]:
        raise ValueError("Review run identity or no-application guard differs")
    candidates = {c["field_key"]: c for c in json.loads((triage / "candidates.json").read_text())}
    seen = set()
    for row in review["reviews"]:
        key = row["field_key"]
        if key in seen:
            raise ValueError("Duplicate reviewed identity")
        seen.add(key)
        candidate = candidates[key]
        if (key != field_key(row["collection"], row["id"])
                or row["source_geometry_sha256"] != candidate["source_geometry_sha256"]
                or row["proposed_outcome"] != candidate["proposed_outcome"]
                or row["application_authorized"]):
            raise ValueError("Review parent fingerprint or route differs")
    return review


def neighbor_audit(before, after, neighbors):
    tolerance = max(1e-6, before.area * 1e-10)
    changes = [abs(before.intersection(n).area - after.intersection(n).area) for n in neighbors]
    maximum = max(changes, default=0.0)
    if maximum > tolerance:
        raise ValueError("Preview changes overlap with saved neighboring polygons")
    return {"saved_neighbors_checked": len(neighbors), "max_overlap_change_m2": maximum,
            "tolerance_m2": tolerance, "exterior_halo_retrieved": False}


def run(root, review_path, out):
    root, review_path, out = [Path(p).expanduser().resolve() for p in (root, review_path, out)]
    if out.exists() or out == root or out in root.parents or (root in out.parents and out.parent != root):
        raise ValueError("Use a fresh separate sibling output directory")
    triage = review_path.parent
    review = validate_reviews(review_path, triage)
    window_id = review["window_id"]
    if window_id != "california_61_424":
        raise ValueError("This targeted demo uses the reviewed California window only")
    source = root / "polygon-review-2024" / window_id
    descriptors = root / "descriptor-review-2024" / window_id
    inputs = verify_inputs(source, descriptors, window_id)
    for path in (review_path, triage / "complete.json", triage / "candidates.json"):
        inputs[str(path)] = file_digest(path)
    fields = gpd.read_parquet(source / "fields.parquet")
    fields["field_key"] = [field_key(c, i) for c, i in zip(fields.collection, fields.id)]
    if fields.field_key.duplicated().any():
        raise ValueError("Duplicate original field identities")
    fields = fields.set_index("field_key", drop=False)
    for row in review["reviews"]:
        if hashlib.sha256(fields.loc[row["field_key"]].geometry.wkb).hexdigest() != row["source_geometry_sha256"]:
            raise ValueError("Reviewed geometry differs from original source")
    reviewed = {row["id"]: row for row in review["reviews"]}
    for ident in (*SPLIT_TARGETS, MERGE_IDS[0]):
        if reviewed[ident]["review_outcome"] != "repair":
            raise ValueError("Target is not labeled for repair")
    window = json.loads((source / "provenance.json").read_text())["window"]
    crs = window["properties"]["metric_crs"]
    metric = fields.to_crs(crs)
    boundary = gpd.GeoSeries([shape(window["geometry"])], crs=4326).to_crs(crs).iloc[0]
    cases, previews, geometries = [], [], []

    def add_preview(kind, parents, children, cuts=None, checks=None, details=None):
        before = unary_union([metric.loc[k].geometry for k in parents])
        after = unary_union(children)
        others = metric.loc[~metric.index.isin(parents)].geometry
        audit = neighbor_audit(before, after, others)
        parent_hashes = {k: hashlib.sha256(fields.loc[k].geometry.wkb).hexdigest() for k in parents}
        canonical = {"algorithm": VERSION, "settings": SETTINGS, "metric_crs": crs,
                     "parents": parent_hashes, "children_wkb": [g.wkb_hex for g in children],
                     "cuts_wkb": cuts.wkb_hex if cuts is not None else None}
        proposal_id = fingerprint(canonical)[:24]
        complete = boundary.covers(before) and before.distance(boundary.boundary) >= SETTINGS["context_radius_m"]
        record = {"proposal_id": proposal_id, "repair_subtype": kind,
                  "parent_keys": parents, "source_geometry_sha256": parent_hashes,
                  "metric_crs": crs, "children_wkt": [g.wkt for g in children],
                  "cuts_wkt": cuts.wkt if cuts is not None else None,
                  "checks": checks, "details": details, "neighbor_audit": audit,
                  "context_100m_complete": bool(complete),
                  "approval_status": "pending", "applied": False,
                  "child_descriptors": [polygon_descriptors(g) if g.geom_type == "Polygon" else None
                                        for g in children]}
        # Round near-square undefined orientation to JSON null, not nonstandard NaN.
        for descriptor in record["child_descriptors"]:
            if descriptor:
                for name, value in descriptor.items():
                    if isinstance(value, float) and not np.isfinite(value):
                        descriptor[name] = None
        previews.append(record)
        for index, geometry in enumerate(children):
            geometries.append({"proposal_id": proposal_id, "role": "preview_child",
                               "preview_index": index, "geometry": geometry})
        if cuts is not None:
            geometries.append({"proposal_id": proposal_id, "role": "cut_set",
                               "preview_index": -1, "geometry": cuts})
        return proposal_id

    for ident, expected in SPLIT_TARGETS.items():
        key = field_key(COLLECTION, ident)
        parent = metric.loc[key].geometry
        proposals, profiles = split_previews(parent, expected)
        ids = []
        for proposal in proposals:
            ids.append(add_preview("split", [key], proposal["children"], proposal["cuts"],
                                   proposal["checks"], {k: v for k, v in proposal.items()
                                                         if k not in ("children", "cuts", "checks")}))
        cases.append({"case_id": ident, "repair_subtype": "split", "parent_keys": [key],
                      "expected_child_count_from_review": expected, "proposal_ids": ids,
                      "erosion_profile": profiles,
                      "status": "preview_available" if ids else "abstain_no_supported_partition",
                      "reason": "Geometry-only split sets; review placement against imagery." if ids else
                      ("Review identifies three fields, but retained erosion cores never resolve three; no forced split."
                       if expected == 3 else "No validated short split set found; abstain.")})
    parents = [field_key(COLLECTION, ident) for ident in MERGE_IDS]
    union = exact_union([metric.loc[k].geometry for k in parents])
    union_id = add_preview("merge_fragments", parents, [union["geometry"]],
                           details={k: v for k, v in union.items() if k != "geometry"})
    cases.append({"case_id": "+".join(MERGE_IDS), "repair_subtype": "merge_fragments",
                  "parent_keys": parents, "proposal_ids": [union_id],
                  "status": "preview_available_multipart_policy_unresolved" if union["component_count"] > 1 else "preview_available",
                  "reason": "Exact set union only; no bridging or new agricultural area. Multipart results need an explicit field-identity policy."})
    interpretation = {"source_review_sha256": file_digest(review_path),
                      "split_targets": SPLIT_TARGETS, "merge_parents": list(MERGE_IDS),
                      "merge_partner_provenance": "User corrected partner from self-reference to 10SFH_0_0-8581 in conversation.",
                      "deferred_boundary_completion": ["10SFH_0_0-9142", "10SFH_0_0-9100", "10SFH_0_0-8713"],
                      "exclusion_labels_carried_forward": [r["id"] for r in review["reviews"] if r["review_outcome"] == "exclude"],
                      "application_authorized": False}
    template_path = Path(__file__).with_name("repair_review.html")
    run_id = fingerprint({"version": VERSION, "settings": SETTINGS, "inputs": inputs,
                          "interpretation": interpretation, "source": file_digest(Path(__file__)),
                          "template": file_digest(template_path), "shapely": shapely.__version__})[:24]
    out.mkdir(parents=True)
    write_json(out / "review-interpretation.json", interpretation)
    write_json(out / "cases.json", cases)
    write_json(out / "proposals.json", previews)
    geojson = json.loads(gpd.GeoDataFrame(geometries, crs=crs).to_crs(4326).to_json()) if geometries else {"type": "FeatureCollection", "features": []}
    write_json(out / "preview-geometries.geojson", geojson)
    payload = {"run_id": run_id, "cases": cases, "proposals": previews, "previews": geojson,
               "interpretation": interpretation,
               "originals": json.loads(fields.reset_index(drop=True)[["field_key", "id", "geometry"]].to_crs(4326).to_json())}
    template = template_path.read_text()
    (out / "index.html").write_text(template.replace("__REPAIR_PAYLOAD__", json.dumps(payload, allow_nan=False).replace("<", "\\u003c")))
    (out / "preview-source.py").write_bytes(Path(__file__).read_bytes())
    (out / "preview-template.html").write_text(template)
    (out / "README.md").write_text(
        "# Targeted repair previews — not applied\n\nOpen index.html. Compare exact original outlines with proposed child partitions or unions. "
        "All geometry is preview-only. Labels/preferences do not authorize application. "
        "Split cuts minimize triangulation-graph edge length between erosion cores, not imagery error. "
        "No cores are buffered back outward. Multipart exact unions remain multipart, without gap filling. "
        "The 8617 three-field case and boundary-completion cases remain unresolved. "
        "Context uses saved window-intersecting polygons only, with no exterior halo.\n"
    )
    for path, digest in inputs.items():
        if file_digest(path) != digest:
            raise ValueError(f"Input changed during generation: {path}")
    write_json(out / "complete.json", {
        "completed_at": now(), "run_id": run_id, "algorithm": VERSION, "settings": SETTINGS,
        "case_count": len(cases), "proposal_count": len(previews), "input_sha256": inputs,
        "repairs_applied": 0, "exclusions_applied": 0, "application_authorized": False,
        "environment": {"shapely": shapely.__version__, "geos": shapely.geos_version_string},
        "output_sha256": {p.name: file_digest(p) for p in sorted(out.iterdir()) if p.is_file()},
    })
    print(json.dumps({"out": str(out), "cases": [{"id": c["case_id"], "status": c["status"],
                                                        "proposals": len(c["proposal_ids"])} for c in cases]}, indent=2))
    return cases, previews


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot_root")
    parser.add_argument("review_json")
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(args.pilot_root, args.review_json, args.out_dir)
