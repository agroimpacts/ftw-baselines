import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from ftw_geometry.core.descriptors import (
    DESCRIPTOR_COLUMNS,
    DESCRIPTOR_VERSION,
    describe_polygons,
)
from ftw_geometry.io.manifests import file_digest, write_json
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping

from research.geometry.compare_landscape_illustrations import (
    BAHIA_ID,
    boundary_components,
    measure_zambia,
    normalize_zambia,
    run,
)
from research.geometry.describe_descriptor_pilot import descriptor_map
from research.geometry.summarize_descriptor_pilot import verify


def snapshot(root, key):
    write_json(
        root / "complete.json",
        {
            key: {
                str(p.relative_to(root)): file_digest(p)
                for p in root.rglob("*")
                if p.is_file()
            }
        },
    )


def fixture_inputs(tmp_path):
    zroot, pilot = tmp_path / "zambia", tmp_path / "pilot"
    zroot.mkdir()
    crs = "EPSG:32736"
    region = box(220000, 8860000, 221000, 8861000)
    footprint = gpd.GeoSeries([region], crs=crs).to_crs(4326).iloc[0]
    window = {
        "type": "Feature",
        "geometry": mapping(footprint),
        "properties": {
            "window_id": "lubushi_test",
            "zone_id": "lubushi",
            "dataset": "Mapping Africa",
            "metric_crs": crs,
            "role": "diagnostic",
        },
    }
    fields = gpd.GeoDataFrame(
        {
            "field_row_id": [10, 11, 12],
            "area_m2": [999.0, 999.0, 999.0],
            "area_ha": [0.0999] * 3,
        },
        geometry=[
            box(220400, 8860400, 220420, 8860430),
            box(220450, 8860400, 220480, 8860430),
            box(220990, 8860100, 221100, 8860130),
        ],
        crs=crs,
    ).to_crs(4326)
    fields.to_parquet(zroot / "fields.parquet")
    projected = fields.to_crs(crs)
    audit = pd.DataFrame(
        {
            "field_row_id": fields.field_row_id,
            "assigned_to_window": [
                region.covers(g.representative_point()) for g in projected.geometry
            ],
        }
    )
    audit.to_csv(zroot / "audit.csv", index=False)
    write_json(
        zroot / "provenance.json",
        {"window": window, "assigned_fields": int(audit.assigned_to_window.sum())},
    )
    write_json(
        zroot / "proposed-window.geojson",
        {"type": "FeatureCollection", "features": [window]},
    )
    snapshot(zroot, "output_sha256")
    saved = json.loads((zroot / "complete.json").read_text())
    saved["stage"] = "window review only; awaiting approval"
    write_json(zroot / "complete.json", saved)
    bsource = pilot / "polygon-review-2024" / BAHIA_ID
    bdesc = pilot / "descriptor-review-2024" / BAHIA_ID
    bsource.mkdir(parents=True)
    bdesc.mkdir(parents=True)
    bfields = gpd.GeoDataFrame(
        {"collection": ["ftw"] * 2, "id": ["a", "b"]},
        geometry=[
            box(220200, 8860200, 220300, 8860300),
            box(220400, 8860200, 220500, 8860300),
        ],
        crs=crs,
    ).to_crs(4326)
    bfields.to_parquet(bsource / "fields.parquet")
    bwindow = json.loads(json.dumps(window))
    bwindow["properties"].update(window_id=BAHIA_ID, zone_id="bahia")
    write_json(bsource / "provenance.json", {"window": bwindow})
    snapshot(bsource, "sha256")
    measured = bfields.merge(
        describe_polygons(bfields, crs), on="id", validate="one_to_one"
    )
    measured["descriptor_version"] = DESCRIPTOR_VERSION
    # Test reuse independently of the circularity decomposition audit.
    measured.loc[0, "rectangle_area_m2"] = 12345.0
    measured.to_parquet(bdesc / "descriptors.parquet")
    snapshot(bdesc.parent, "output_sha256")
    return zroot, pilot, fields, window, audit


def test_source_metrics_are_namespaced_and_assignment_verified(tmp_path):
    _, _, raw, window, audit = fixture_inputs(tmp_path)
    fields, measured = measure_zambia(raw, window, audit)
    assert fields.source_area_m2.eq(999.0).all()
    assert "area_m2" not in fields
    assert len(measured) == 2
    assert np.allclose(measured.area_m2, [600.0, 900.0])
    assert measured.source_area_m2.eq(999.0).all()
    bad = audit.copy()
    bad.loc[0, "assigned_to_window"] = False
    with pytest.raises(ValueError, match="audit/assignment"):
        measure_zambia(raw, window, bad)
    multipart = raw.copy()
    multipart.loc[0, "geometry"] = MultiPolygon(
        [raw.geometry.iloc[0], raw.geometry.iloc[1]]
    )
    with pytest.raises(ValueError, match="multipart"):
        normalize_zambia(multipart)


def test_approved_comparison_is_separate_preserves_inputs_and_all_descriptors(tmp_path):
    zroot, pilot, _, _, _ = fixture_inputs(tmp_path)
    with pytest.raises(ValueError, match="approval"):
        run(zroot, pilot, tmp_path / "not-approved")
    before = {
        p: file_digest(p)
        for root in (zroot, pilot)
        for p in root.rglob("*")
        if p.is_file()
    }
    out = tmp_path / "comparison"
    regions = run(zroot, pilot, out, approved=True)
    assert len(regions) == 2
    assert regions.field_count.sum() == 4
    assert regions.sample_role.eq("illustration").all()
    for feature in DESCRIPTOR_COLUMNS[1:]:
        if feature not in {"orientation_deg", "orientation_ambiguous"}:
            assert regions[feature + "_finite_count"].eq(2).all()
    approval = json.loads((out / "approval.json").read_text())
    assert approval["approved_window_sha256"] == file_digest(
        zroot / "proposed-window.geojson"
    )
    assert all(file_digest(p) == digest for p, digest in before.items())
    verify(out, "output_sha256")
    bmeasured = gpd.read_parquet(out / BAHIA_ID / "descriptors.parquet")
    assert bmeasured.loc[bmeasured.id.eq("a"), "rectangle_area_m2"].iloc[0] == 12345.0
    text = (out / "lubushi_test" / "review.html").read_text()
    assert "Lubushi and Bahia illustrative fields only" in text
    assert "primary-derived bounds" not in text
    assert (out / "size-circularity.png").exists()
    assert len(pd.read_csv(out / "gap-sensitivity.csv")) == 6
    with pytest.raises(ValueError, match="fresh"):
        run(zroot, pilot, out, approved=True)


def test_map_population_label_escapes_script_markup(tmp_path):
    _, _, raw, window, audit = fixture_inputs(tmp_path)
    _, measured = measure_zambia(raw, window, audit)
    page = descriptor_map(window, measured, scale_population="illustrations </script>")
    assert "illustrations \\u003c/script>" in page


def test_circularity_decomposition_separates_holes_from_outer_shape():
    outer = Point(0, 0).buffer(100, quad_segs=64)
    hole = Point(0, 0).buffer(10, quad_segs=64)
    geometry = Polygon(outer.exterior.coords, [hole.exterior.coords])
    fields = gpd.GeoDataFrame(
        {"id": ["donut"], "collection": ["test"]}, geometry=[geometry], crs=32736
    )
    measured = fields.merge(describe_polygons(fields), on="id")
    measured["measurement_crs"] = "EPSG:32736"
    measured["window_id"] = "test"
    row = boundary_components(measured, "test").iloc[0]
    assert row.hull_circularity > 0.99
    assert row.outer_ring_circularity_diagnostic > 0.99
    assert row.circularity < 0.9
    assert row.interior_perimeter_fraction == pytest.approx(1 / 11)
    assert row.reconstructed_circularity == pytest.approx(row.circularity)
