# Polygon export and geometry descriptors

This guide describes the current schema-3 outputs. They measure the shape of
mapped fields, **not the accuracy of their boundaries against reference data**.
See [geometry analysis](geometry-analysis.md) for dataset and regional workflows,
and [export validation](research/polygon-export-validation.md) for checks on real data.

## Optional fixed-preset polygon export

The default semantic polygonization route is unchanged. To use the unchanged
`FTW_2E` preset from `ftw-fbp[fast]==0.2.0` and preserve field IDs:

```sh
uv run --extra fbp ftw inference polygonize probabilities.tif \
  --method ftw-2e --out fields.parquet --simplify 0 --min_size 0
```

Input has background/interior/boundary bands: float probabilities in [0,1], or
uint8 probabilities decoded by dividing by 255. Band sums must be within 0.02
of one. Class-only, masked and nodata grids are rejected. No resampling is done.
Projected grids use affine pixel area converted to m²; axis-aligned geographic
grids use mean geodesic pixel area across rows. Rotated geographic grids are
rejected. The preset retains its own 900 m² filter even with `--min_size 0`.

Outputs can be fiboa GeoParquet (`.parquet`), GeoJSON, GeoPackage or FlatGeobuf.
GeoJSON uses EPSG:4326; other formats retain the input CRS. Each export includes
`.descriptors.csv` and `.metadata.json` siblings recording IDs, preset/version,
grid/encoding, pixel area, metric CRS and cleanup settings.

IDs are scene-local `<instance_id>:<part>`. Multipart parts are ordered by their
pixel-coordinate bounds. Non-fiboa formats also retain `instance_id`; a fiboa
schema may drop that column, but the original ID remains encoded in `id`.

`--stride` divides **vectorization only** into windows. FBP still processes the
whole scene in memory. Fragments with the same ID are reunited; different IDs
are never dissolved. Holes remain unless `--close_interiors` is explicit.
Legacy morphology, threshold and adjacency-merging options cannot be combined
with this route.

Cleanup uses metres and m² in a suitable source metric CRS or local UTM. The
existing defaults are `--simplify 15 --min_size 500`; explicit zeroes above avoid
those cleanup changes for pixel-edge checks. Size filtering follows cleanup for
each single part. Descriptors are recomputed from the persisted final geometry.

## Descriptor schema 3.0

Measurements require a suitable projected CRS in metres. Local UTM is not a
universal solution for multi-zone or global data.

### Notation

- **A**: field area, excluding holes.
- **P**: total boundary length, including boundaries around holes.
- **L, W**: long and short sides of the smallest-area enclosing rectangle,
  allowed to rotate.
- **H**: combined hole area.
- **Aₕ, Pₕ**: area and perimeter of the convex hull—the outline formed by
  stretching a rubber band around the field.

### Size and shape

| Descriptor | Meaning | Formula |
| --- | --- | --- |
| Area (`area_m2`) | Ground covered, excluding holes | A, in m² |
| Perimeter (`perimeter_m`) | Boundary length, including hole boundaries | P, in m |
| Circularity (`circularity`) | How efficiently the boundary encloses area; circles score 1, elongated/indented/holey shapes lower | 4πA/P² |
| Elongation (`elongation`) | How stretched the enclosing rectangle is; squares score 1 | L/W |
| Solidity (`solidity`) | How completely the field fills its rubber-band outline | A/Aₕ |
| Rectangularity (`rectangularity`) | How completely it fills its enclosing rectangle; all perfect rectangles score 1 | A/(LW) |
| Convex-hull index (`convex_hull_index`) | Rubber-band boundary length relative to the actual boundary | Pₕ/P |

Circularity is the existing compactness definition, exported under one name.
These ratios do not distinguish the different causes of an irregular shape.

### Supporting dimensions

| Descriptor | Meaning |
| --- | --- |
| `rectangle_length_m`, `rectangle_width_m` | L and W, in metres |
| `rectangle_area_m2` | LW, in m² |
| `convex_hull_area_m2` | Aₕ, in m² |
| `convex_hull_perimeter_m` | Pₕ, in metres |

These help interpret the ratios but are not independent of them.

### Holes, orientation and narrow connections

| Descriptor | Meaning and definition |
| --- | --- |
| `hole_count` | Number of interior rings |
| `hole_area_m2` | Combined hole area H |
| `hole_area_fraction` | H/(A+H): share of the area inside the outer boundary occupied by holes |
| `orientation_deg` | Angle of the enclosing rectangle's long side: atan2(Δy, Δx), in degrees modulo 180 |
| `orientation_ambiguous` | True when L/W ≤ 1.05; orientation is then undefined |
| `narrow_neck` | True when shrinking inward by 0.10√(A/π) leaves at least two pieces each with area ≥ 0.02A |

Orientation is counterclockwise from the projected CRS's positive x-axis,
not necessarily true east. Opposite directions are equivalent. Use axial
statistics, not ordinary averages of raw angles. A hole's cause cannot be
determined from geometry alone.

Simplification, hole removal, resolution and field fragmentation affect these
measures, especially perimeter-based ratios and narrow-neck flags. Invalid,
empty or degenerate polygon inputs raise; ratios are not clipped.

### Schema changes and feature selection

There are 17 numeric/boolean measures plus `orientation_ambiguous` and the ID.
Schema 3 removes `compactness` (identical to circularity), `area_ha`,
`equal_area_circle_radius_m`, `ftw_elongation_short_long`,
`convex_hull_deviation_ratio`, `shape_index` and `boundary_complexity` (redundant
transforms). It also removes unit-dependent `fractal_index`, which was not an
estimated fractal dimension. No fitted-circle overlap measure is implemented.

Old outputs retain their original schema; new code does not emit compatibility
aliases. Select columns by name and use a new dataset directory rather than
resuming an older schema with changed code.

Even retained features have mathematical dependencies: rectangle area = L×W,
elongation = L/W, rectangularity = A/(LW), solidity = A/Aₕ, hull index = Pₕ/P,
and hole fraction = H/(A+H). Choose ratios or supporting dimensions deliberately
for PCA rather than including every related column.

## Use existing polygons directly

```python
import geopandas as gpd
from ftw_tools.postprocess.descriptors import describe_polygons

fields = gpd.read_file("existing_fields.gpkg")
describe_polygons(fields).to_csv("existing_fields.descriptors.csv", index=False)
```

Inputs require unique, non-null `id` values and single polygons. Explode multipart
geometry and assign unique per-part IDs first. Geometry is not changed. The
function retains a metre-projected CRS or chooses local UTM; pass `metric_crs=`
to choose explicitly. Geographic empty data needs an explicit metric CRS.
Empty exports have a header-only descriptor CSV; empty GeoJSON has no property schema.
For large inputs use the [bounded-batch workflow](geometry-analysis.md).

## Relationship to the evaluation prototype

Definitions were reviewed against the local
`../evaluation/metric_package/src/field_shape_metrics/` snapshot, but implemented
independently. There is no sibling runtime dependency or code transfer.
Size, shape, rectangle, hull, hole, orientation and narrow-neck measures are
covered here. Hull dimensions and hole-area outputs extend the snapshot's
standalone columns. Regional counts, density, coverage, distributions, overlaps
and finite-radius gaps are in the [geometry workflow](geometry-analysis.md).

Reference-dependent scores are a separate family. Boundary-distance evaluation
is outstanding research, not a schema-3 geometry descriptor; see
[the boundary-distance to-do](instance-metrics-backlog.md#ref-1-boundary-chamfer-distance).
