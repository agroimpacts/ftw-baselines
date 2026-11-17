import json

import geopandas as gpd
import pytest
from ftw_geometry.io.manifests import file_digest, write_json
from shapely.geometry import box
from shapely.ops import unary_union

from research.geometry.review_triage_repairs import (
    exact_union,
    neighbor_audit,
    partition_checks,
    split_previews,
    validate_reviews,
    run,
)


def double_bridge():
    return unary_union([box(0, 0, 40, 40), box(60, 0, 100, 40),
                        box(40, 3, 60, 7), box(40, 33, 60, 37)])


def test_coordinated_cuts_disconnect_multiple_connections_without_area_loss():
    parent = double_bridge()
    before = parent.wkb
    proposals, _ = split_previews(parent, 2)
    assert proposals
    for p in proposals:
        assert len(p["children"]) == 2
        assert p["cuts"].geom_type == "MultiLineString"
        assert p["total_cut_length_m"] <= 8.00001
        assert p["checks"]["union_error_m2"] < 1e-6
        assert p["checks"]["sibling_overlap_m2"] == 0
        assert partition_checks(parent, p["children"])
    assert parent.wkb == before


def test_unresolved_three_field_label_is_not_forced():
    proposals, profiles = split_previews(double_bridge(), 3)
    assert not proposals
    assert max(len(p["retained_lobe_area_fractions"]) for p in profiles) == 2


def test_single_rectangle_is_not_split_without_cores():
    assert not split_previews(box(0, 0, 100, 30))[0]


def test_partition_checks_reject_missing_area_overlap_and_tiny_children():
    parent = box(0, 0, 100, 100)
    assert partition_checks(parent, [box(0, 0, 50, 100), box(50, 0, 100, 100)])
    assert partition_checks(parent, [box(0, 0, 50, 100), box(60, 0, 100, 100)]) is None
    assert partition_checks(parent, [box(0, 0, 60, 100), box(50, 0, 100, 100)]) is None
    assert partition_checks(parent, [box(0, 0, 1, 100), box(1, 0, 100, 100)]) is None


def test_exact_union_keeps_disjoint_and_point_touching_parts_without_filling():
    for second in (box(11, 0, 20, 10), box(10, 10, 20, 20)):
        p = exact_union([box(0, 0, 10, 10), second])
        assert p["geometry"].geom_type == "MultiPolygon"
        assert p["component_count"] == 2
        assert p["added_area_m2"] == 0
        assert not p["single_field_descriptor_available"]
    adjacent = exact_union([box(0, 0, 10, 10), box(10, 0, 20, 10)])
    assert adjacent["geometry"].geom_type == "Polygon"


def test_neighbor_audit_checks_positive_area_changes():
    parent = box(0, 0, 10, 10)
    assert neighbor_audit(parent, parent, [box(5, 5, 20, 20)])["max_overlap_change_m2"] == 0
    with pytest.raises(ValueError, match="overlap"):
        neighbor_audit(parent, box(0, 0, 12, 12), [box(5, 5, 20, 20)])


def test_review_provenance_and_application_guards(tmp_path):
    key = '["test","a"]'
    candidate = {"field_key": key, "source_geometry_sha256": "abc", "proposed_outcome": "repair"}
    write_json(tmp_path / "candidates.json", [candidate])
    write_json(tmp_path / "complete.json", {"run_id": "demo", "output_sha256": {
        "candidates.json": file_digest(tmp_path / "candidates.json")}})
    review = {"run_id": "demo", "application_authorized": False, "reviews": [
        {**candidate, "collection": "test", "id": "a", "application_authorized": False}]}
    path = tmp_path / "review.json"
    write_json(path, review)
    assert validate_reviews(path, tmp_path) == review
    review["reviews"][0]["source_geometry_sha256"] = "changed"
    write_json(path, review)
    with pytest.raises(ValueError, match="fingerprint"):
        validate_reviews(path, tmp_path)
    review["application_authorized"] = True
    write_json(path, review)
    with pytest.raises(ValueError, match="guard"):
        validate_reviews(path, tmp_path)


def test_serialized_preview_children_conserve_parent():
    import shapely

    parent = double_bridge()
    proposals, _ = split_previews(parent)
    children = [shapely.from_wkt(g.wkt) for g in proposals[0]["children"]]
    assert unary_union(children).symmetric_difference(parent).area < 1e-6
    # Display projection is not the canonical metric geometry.
    display = gpd.GeoSeries(children, crs=32610).to_crs(4326)
    assert len(display) == 2
    assert json.loads(display.to_json())["type"] == "FeatureCollection"


def test_targeted_run_preserves_sources_and_review_export(tmp_path):
    import hashlib

    from ftw_geometry.core.descriptors import describe_polygons
    from shapely.affinity import translate
    from shapely.geometry import mapping

    from research.geometry.triage_descriptor_pilot import field_key

    root = tmp_path / "pilot"
    source = root / "polygon-review-2024" / "california_61_424"
    descriptors = root / "descriptor-review-2024" / "california_61_424"
    triage = root / "triage-v1"
    for path in (source, descriptors, triage):
        path.mkdir(parents=True)
    ids = ["10SFH_0_0-" + suffix for suffix in ("8520", "9043", "8617", "8571", "8581")]
    fields = gpd.GeoDataFrame(
        {"id": ids, "collection": ["ftw-s2-2024"] * 5},
        geometry=[translate(double_bridge(), 610300 + i * 200, 4240300) for i in range(3)]
        + [box(610300, 4240600, 610340, 4240640), box(610340, 4240640, 610350, 4240650)],
        crs=32610,
    )
    fields.to_parquet(source / "fields.parquet")
    boundary = gpd.GeoSeries([box(610000, 4240000, 612000, 4242000)], crs=32610).to_crs(4326).iloc[0]
    write_json(source / "provenance.json", {"window": {
        "type": "Feature", "geometry": mapping(boundary),
        "properties": {"metric_crs": "EPSG:32610"}}})
    write_json(source / "complete.json", {"sha256": {
        name: file_digest(source / name) for name in ("fields.parquet", "provenance.json")}})
    fields.merge(describe_polygons(fields), on="id").to_parquet(descriptors / "descriptors.parquet")
    (descriptors / "corrected-component-audit.csv").write_text("id\n")
    write_json(descriptors.parent / "complete.json", {"output_sha256": {
        "california_61_424/" + name: file_digest(descriptors / name)
        for name in ("descriptors.parquet", "corrected-component-audit.csv")}})
    candidates = [{"field_key": field_key(row.collection, row.id),
                   "source_geometry_sha256": hashlib.sha256(row.geometry.wkb).hexdigest(),
                   "proposed_outcome": "repair", "collection": row.collection, "id": row.id}
                  for row in fields.iloc[:4].itertuples()]
    write_json(triage / "candidates.json", candidates)
    write_json(triage / "complete.json", {"run_id": "fixture", "output_sha256": {
        "candidates.json": file_digest(triage / "candidates.json")}})
    review_path = triage / "review.json"
    write_json(review_path, {"run_id": "fixture", "window_id": "california_61_424",
                            "application_authorized": False,
                            "reviews": [{**c, "review_outcome": "repair", "application_authorized": False}
                                        for c in candidates]})
    before = {str(p): file_digest(p) for p in root.rglob("*") if p.is_file()}
    out = root / "targeted-v1"
    cases, previews = run(root, review_path, out)
    assert len(cases) == 4
    assert len(previews) == sum(len(c["proposal_ids"]) for c in cases)
    assert cases[0]["proposal_ids"] and cases[1]["proposal_ids"]
    assert cases[2]["status"] == "abstain_no_supported_partition"
    assert cases[3]["status"] == "preview_available_multipart_policy_unresolved"
    assert all(not p["applied"] and p["approval_status"] == "pending" for p in previews)
    assert {name: file_digest(name) for name in before} == before
    manifest = json.loads((out / "complete.json").read_text())
    for name, digest in manifest["output_sha256"].items():
        assert file_digest(out / name) == digest
    _, again = run(root, review_path, root / "targeted-v2")
    assert [p["proposal_id"] for p in previews] == [p["proposal_id"] for p in again]
    with pytest.raises(ValueError, match="fresh"):
        run(root, review_path, out)
    with pytest.raises(ValueError, match="sibling"):
        run(root, review_path, source / "new")
