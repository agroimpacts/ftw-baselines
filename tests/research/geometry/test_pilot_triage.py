import json

import geopandas as gpd
import pytest
from ftw_geometry.core.descriptors import describe_polygons
from ftw_geometry.io.manifests import file_digest, write_json
from shapely.geometry import LineString, MultiPolygon, box, mapping
from shapely.ops import unary_union

from research.geometry.triage_descriptor_pilot import (
    OUTCOMES,
    build_candidates,
    classify,
    cut_alternatives,
    erosion_profile,
    run,
    validate_cut,
)


def dumbbell():
    return unary_union([box(0, 0, 40, 40), box(40, 18, 60, 22), box(60, 0, 100, 40)])


def test_persistent_lobes_and_original_boundary_cut():
    polygon = dumbbell()
    original = polygon.wkb
    profile, lobes = erosion_profile(polygon)
    assert sum(len(p['retained_lobe_area_fractions']) == 2 for p in profile) >= 3
    cuts = cut_alternatives(polygon, lobes)
    assert cuts
    for cut, checks in cuts:
        assert cut.length == pytest.approx(4)
        assert checks['child_area_fractions'] == pytest.approx([0.5, 0.5], abs=0.02)
        assert checks['union_symmetric_difference_m2'] < 1e-6
        assert checks['child_overlap_m2'] == 0
        assert validate_cut(polygon, cut)
    assert polygon.wkb == original


def test_no_cuts_for_rectangle_and_reject_tiny_or_external_cuts():
    polygon = box(0, 0, 100, 20)
    _, lobes = erosion_profile(polygon)
    assert not cut_alternatives(polygon, lobes)
    assert validate_cut(polygon, LineString([(1, 0), (1, 20)])) is None
    assert validate_cut(polygon, LineString([(50, -10), (50, 30)])) is None
    assert validate_cut(polygon, LineString([(20, 10), (30, 10)])) is None
    assert validate_cut(polygon, LineString([(50, 0), (60, 10), (50, 20)])) is None


def test_multiple_connections_are_not_forced_into_single_cut():
    polygon = unary_union([
        box(0, 0, 40, 40), box(60, 0, 100, 40),
        box(40, 3, 60, 7), box(40, 33, 60, 37),
    ])
    assert len(polygon.interiors) == 1
    profile, lobes = erosion_profile(polygon)
    assert any(len(p['retained_lobe_area_fractions']) == 2 for p in profile)
    assert not cut_alternatives(polygon, lobes)


def test_routing_and_conversation_rejections_are_not_exclusions():
    row = {'rectangle_width_m': 10, 'elongation': 12, 'circularity': 0.1,
           'narrow_neck': False}
    assert classify(row, [], False, True)[0] == 'exclude'
    assert classify(row, [], False, False)[0] == 'abstain'
    assert classify(row, [], False, True,
                    'user_rejected_neck_screen_not_a_field_exclusion_label')[0] == 'abstain'
    assert classify(row, [], False, False, 'user_identified_joined_fields')[0] == 'repair'
    row.update(rectangle_width_m=40, elongation=2, circularity=0.6)
    assert classify(row, [], False, True)[0] == 'retain'
    row['narrow_neck'] = True
    profiles = [{'retained_lobe_area_fractions': [0.3, 0.3]}] * 4
    assert classify(row, profiles, True, True)[0] == 'repair'
    assert classify(row, profiles, False, True)[0] == 'abstain'


def fixture_inputs(tmp_path):
    root = tmp_path / 'pilot'
    source = root / 'polygon-review-2024' / 'demo'
    descriptors = root / 'descriptor-review-2024' / 'demo'
    source.mkdir(parents=True)
    descriptors.mkdir(parents=True)
    geometries = [box(300, 300, 340, 340),
                  box(400, 300, 600, 310),
                  dumbbell().buffer(0), box(50, 50, 60, 60)]
    # Shift the dumbbell well inside the extraction window.
    from shapely.affinity import translate
    geometries[2] = translate(geometries[2], xoff=300, yoff=500)
    fields = gpd.GeoDataFrame({'id': ['a', 'b', 'c', 'context'],
                              'collection': ['test'] * 4},
                             geometry=geometries, crs=32632)
    assigned = fields.iloc[:3].copy()
    measured = assigned.merge(describe_polygons(assigned), on='id', validate='one_to_one')
    fields.to_parquet(source / 'fields.parquet')
    measured.to_parquet(descriptors / 'descriptors.parquet')
    (descriptors / 'corrected-component-audit.csv').write_text('id\na\nb\nc\n')
    window = {'type': 'Feature', 'properties': {'window_id': 'demo', 'metric_crs': 'EPSG:32632'},
              'geometry': mapping(gpd.GeoSeries([box(0, 0, 1000, 1000)], crs=32632).to_crs(4326).iloc[0])}
    write_json(source / 'provenance.json', {'window': window})
    write_json(source / 'complete.json', {'sha256': {
        name: file_digest(source / name) for name in ('fields.parquet', 'provenance.json')
    }})
    write_json(descriptors.parent / 'complete.json', {'output_sha256': {
        f'demo/{name}': file_digest(descriptors / name)
        for name in ('descriptors.parquet', 'corrected-component-audit.csv')
    }})
    return root, fields, measured, window


def test_identity_geometry_guards_and_container_normalization(tmp_path):
    _, fields, measured, window = fixture_inputs(tmp_path)
    fields.loc[0, 'geometry'] = MultiPolygon([fields.geometry.iloc[0]])
    records, _ = build_candidates(fields, measured, window, 'EPSG:32632')
    assert len(records) == 3
    assert {r['proposed_outcome'] for r in records} <= set(OUTCOMES)
    measured.loc[0, 'geometry'] = box(301, 300, 340, 340)
    with pytest.raises(ValueError, match='differs from source'):
        build_candidates(fields, measured, window, 'EPSG:32632')
    with pytest.raises(ValueError, match='Duplicate'):
        build_candidates(fields, measured.iloc[[0, 0]], window, 'EPSG:32632')


def test_run_is_proposal_only_reproducible_and_hash_verified(tmp_path):
    root, _, _, _ = fixture_inputs(tmp_path)
    before = {str(p): file_digest(p) for p in root.rglob('*') if p.is_file()}
    out = root / 'triage-v1'
    records, cuts = run(root, out, 'demo')
    assert len(records) == 3
    assert cuts
    assert {str(p): file_digest(p) for p in root.rglob('*')
            if p.is_file() and out not in p.parents} == before
    manifest = json.loads((out / 'complete.json').read_text())
    assert manifest['repairs_applied'] == manifest['exclusions_applied'] == 0
    assert manifest['context_count'] == 4
    for name, digest in manifest['output_sha256'].items():
        assert file_digest(out / name) == digest
    assert all(c['approval_status'] == 'pending' and not c['applied'] for c in cuts)
    html = (out / 'index.html').read_text()
    assert '__TRIAGE_PAYLOAD__' not in html
    assert 'application_authorized:false' in html
    _, again = run(root, root / 'triage-v2', 'demo')
    assert [c['proposal_id'] for c in cuts] == [c['proposal_id'] for c in again]
    with pytest.raises(ValueError, match='fresh'):
        run(root, out, 'demo')
    with pytest.raises(ValueError, match='preserve'):
        run(root, root / 'descriptor-review-2024' / 'new', 'demo')
    (root / 'polygon-review-2024' / 'demo' / 'provenance.json').write_text('{}')
    with pytest.raises(ValueError, match='Changed input'):
        run(root, root / 'triage-v3', 'demo')
