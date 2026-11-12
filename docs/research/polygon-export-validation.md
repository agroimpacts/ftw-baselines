# Schema-3 polygon export validation

## Question and finding

Do exported polygons preserve the saved FBP objects, and do descriptor sidecars
describe the geometry that was actually written?

**The selected Germany chip passes these checks in all four formats.** This
establishes export fidelity for that example, not prediction accuracy or
large-area inference performance.

## Data and checks

Germany `g1_00003_16` was regenerated on 2026-11-11 from the same saved
probabilities and labels using unchanged FTW_2E 0.2.0 and descriptor schema 3.0.

| Check | Result |
| --- | --- |
| Recomputed FBP labels versus saved labels | All 13 IDs agree |
| Geometry | 13 valid single polygons; both holes retained |
| Formats | fiboa GeoParquet, GeoJSON, GeoPackage, FlatGeobuf |
| Uncleaned raster round trip | No differing pixels |
| Vectorization strides 31/64/127/2048 | Same IDs and topologically equal geometry |
| CRS | Source/output EPSG:4326; cleanup/descriptors EPSG:32633 |
| Uncleaned metric area | 750,645.5202 m² total |
| Descriptor sidecars | Agree with recomputation from persisted geometry |
| Explicit 15 m simplification / 500 m² filtering | 13 valid fields; descriptors agree |

Retained schema-3 values/geometries were compared with schema 2 before replacing
the old exports (`rtol=1e-12`, `atol=1e-8` for descriptors). fiboa's float32
geometry attributes use a separate `rtol=1e-7` check; descriptor CSV values are
computed from read-back geometry in float64.

Window seam checks exposed microscopic georeferencing gaps during development.
Vectorization now joins same-ID pieces in integer pixel coordinates, removes
redundant collinear vertices and applies the affine transform once. Different
IDs are not dissolved together.

## Limits

FBP still processes the whole input scene. These tests do not validate windowed
FBP inference, cross-chip ownership, stitching or continental memory/runtime.
The preset's own 900 m² filter is unchanged. Geographic area filtering uses
chip-mean geodesic pixel area; rotated geographic and masked/nodata inputs are
rejected. No larger-area descriptor correlation/PCA study was performed.

## Artifacts and reproduction

Current outputs:
`~/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany/polygon-validation/g1_00003_16_schema3/`.
`validation.json` records checks; exports have descriptor and metadata sidecars.
Four intermediate validation folders were removed only after verification;
the parent artifact README records their original purposes. Source probabilities,
labels and reference-score assessments were retained.

Recheck into a new directory:

```sh
uv run --extra fbp python -m scripts.geometry.validate_instance_polygon_export \
  "$HOME/working/ftw/metrics/test/prue-b7_germany_test_prob/probabilities/germany/g1_00003_16.tif" \
  "$HOME/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany/labels/ftw-2e/germany/g1_00003_16.tif" \
  --out_dir "$HOME/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany/polygon-validation/g1_00003_16_schema3_recheck"
```

Existing artifacts are refused rather than overwritten. See the
[export/descriptor guide](../polygon-export-and-descriptors.md) for current
definitions and the [development record](archive/assessment-development-record.md)
for superseded schema checks.
