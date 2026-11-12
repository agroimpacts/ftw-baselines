# Analyze field geometry and mapped areas

These tools describe existing final polygons. They do not run inference, change
boundaries or evaluate prediction accuracy. Descriptor formulas are in the
[export guide](polygon-export-and-descriptors.md#descriptor-schema-30).

The software has synthetic integration tests. The only real-data descriptor
validation so far is the 13-polygon Germany example; **no real larger-area study
or regional correlation/PCA findings have been produced**.

Run commands from the repository root. Before a study, choose the source data,
surveyed boundaries, common metric CRS, whole-field versus fragment interpretation,
duplicate/edge policies, gap radius and spatial-block size.

## 1. Declare inputs and policies

Create `geometry-inputs.json`:

```json
{
  "dataset_id": "study-area",
  "run_id": "final-fields-v1",
  "metric_crs": "EPSG:32633",
  "duplicate_policy": "error-identical",
  "field_semantics": "complete-fields",
  "sources": [
    {
      "source_id": "scene-001",
      "path": "fields.parquet",
      "id_column": "id",
      "footprint": "surveyed-scene.gpkg",
      "edge_tolerance_m": 0,
      "provenance": {"resolution_m": 10, "simplify_m": 0, "close_interiors": false}
    }
  ]
}
```

Paths are relative to the manifest. Use an appropriate common metre-based
projected CRS; the example UTM is not suitable everywhere. Split global or
multi-zone studies into defensible processing domains.

- Inputs must contain valid single polygons with unique non-null IDs per source.
  Generation does not repair, explode, clean or stitch geometry.
- `error-identical` rejects equal normalized geometry hashes across sources;
  `keep` retains duplicates explicitly. Neither resolves near-duplicates.
- `complete-fields` versus `tile-fragments` declares what rows represent.
  Fragment counts must not be presented as unique whole-field counts.
- `footprint` is the source's valid surveyed domain, covering its fields, or
  explicit `null` if unknown. Boundary distance/tolerance determines edge flags;
  unknown is not treated as interior.
- Record known resolution/cleanup/source settings in `provenance`; use null for
  unknown values. Earlier export metadata is not inferred automatically.

GeoParquet uses bounded WKB batches. Other supported formats use GDAL row
windows, which may repeatedly scan earlier rows. Prefer GeoParquet for large
repeated analyses. Shapefiles are rejected because hashing `.shp` alone would
miss companion data.

## 2. Build or resume descriptor tables

```sh
uv run python -m scripts.geometry.describe_field_dataset geometry-inputs.json \
  --out_dir geometry-dataset --batch_size 10000
```

The output contains `manifest.json`, `sources/<hash>/part-*.parquet`, source
checkpoints and a final `complete.json`. It records input/code hashes, settings
and schema version. The same command verifies and reuses complete source partitions;
changed inputs, code, settings or batch size require a new output directory.
Interrupted sources restart atomically from the beginning. Use only one writer
per output directory; abandoned temporary attempts are not considered complete.

Rows contain descriptors, namespaced field keys, source/local IDs, geometry
hashes, metric WKB/centroids, nullable edge flags and doubled-angle sine/cosine
orientation components. Batches and SQLite identity checks bound generation memory.

## 3. Summarize surveyed regions

```sh
uv run python -m scripts.geometry.analyze_field_descriptors regions \
  geometry-dataset surveyed-regions.gpkg --region_id region_id \
  --edge_policy exclude --gap_radius_m 100 --max_fields 100000 \
  --out_dir geometry-regions
```

Regions must be valid, nonoverlapping surveyed-domain polygons—not administrative
areas containing unknown, unobserved land. `exclude` requires known footprints
and omits edge fields from distributions, coverage and topology. `include`
retains them and reports edge/unknown counts. Keep policies consistent.

A representative point assigns a whole field to one region for counts and
descriptors. A point on a shared boundary raises. Coverage is different: every
eligible intersecting field contributes clipped area to each region it touches.
Union coverage is distinct from summed field area, which includes overlap.

| Output | Contents |
| --- | --- |
| `regions.parquet` / `.csv` | Counts/density, coverage, overlaps, edge counts, descriptor summaries, area-weighted means, axial orientation summaries and gaps |
| `distributions.csv` | Area bins 0–1000–10000–100000–∞ m² and 15° axial orientation bins; ambiguous directions excluded |
| `assigned_fields/*.parquet` | Region membership, crossing flags and gap observations/censoring |
| `analysis.json` | Input hashes, CRS, parameters, policies and completion marker |

Other input region attributes are retained with a `region_` prefix, such as
`region_country` for grouped analysis.

Positive gap is the shortest **strictly positive** distance to another eligible
field within the chosen radius, using a region-plus-radius halo. Touching or
overlapping neighbors are ignored for this measure. No positive neighbor found
means **censored**, not zero. The observed mean is not an uncensored global
nearest-gap estimate; unknown source coverage remains a limitation.

Spatial indexing avoids unconditional all-pairs work, but dense overlaps may be
expensive. Exact geometry and quantiles load a region plus halo with an explicit
field cap; exceeding it raises. Regional analysis is not resumable—use a fresh
directory after failure. Continental runtime/memory performance is unmeasured.

## 4. Study descriptor relationships

```sh
uv run python -m scripts.geometry.analyze_field_descriptors correlations \
  --dataset geometry-dataset --group_column source_id --level field \
  --features area_m2 circularity elongation solidity rectangularity convex_hull_index hole_area_fraction \
  --log_features area_m2 \
  --pca_features circularity elongation solidity rectangularity convex_hull_index hole_area_fraction \
  --block_size_m 1000 --sample_size 2000 --bootstrap_replicates 200 \
  --out_dir geometry-correlations
```

For region-assigned fields use `--tables geometry-regions/assigned_fields/*.parquet
--metric_crs EPSG:32633` instead of `--dataset`, grouped by `region_id`.
For comparisons between areas, use `regions.parquet`, `--level area`, region-summary
features and a suitable attribute such as `region_country`. Do not mix duplicate
table populations. One observation per group cannot give within-group correlations.

- `associations.csv` distinguishes full-data pairwise Pearson (`population_pair_n`)
  from sampled Pearson/Spearman (`sample_pair_n`) and sample-conditional block intervals.
- `availability.csv` records finite counts, constants and sample uniqueness.
  Missing/constant results remain blank.
- `sample-*.parquet` saves bounded, seeded reservoir samples for pooled, grouped
  and size-stratified analyses. Groups are sampled independently, not as paired contrasts.
- `pca_status.csv` / `pca_loadings.csv` record complete-score counts, status and
  standardized-sample PCA results. No imputation or clustering is performed.
- `analysis.json` records hashes, features, transforms, CRS, caps, seed and block size.

`--log_features` applies log1p to nonnegative features. Field analyses also stratify
by original area unless `--no_size_strata` is used. `--max_groups` defaults to 256,
including strata. Choose PCA features deliberately to avoid algebraic redundancy.

Bootstrap blocks start at projected (0,0). Choose block size scientifically and
check sensitivity to it and reservoir size. Fewer than three observed blocks
leave intervals undefined. With sampling, intervals are conditional on the saved
sample, not full-data confidence intervals. Only streamed Pearson uses every
finite pair when populations exceed the sample cap.

Raw axial angles are rejected for linear correlations/PCA; doubled-angle sine
and cosine can be explored together, with their dependency and projection
convention acknowledged. Compare within-group and size-stratified results before
interpreting pooled correlations as geography-independent relationships.

## Relate geometry to accuracy at the same observation level

A field table has one row per field; a matched-pair table one per pair; a chip
table one per image chip; a region table one per area. Values correlated on a row
must describe the same observation.

Do not copy a chip's PQ onto its 50 fields and treat them as 50 independent
accuracy observations. Instead, summarize shape per chip, join by dataset/run/chip
and compare chips. For field-level boundary accuracy, explicitly match predictions
to references and join each field to its own score. Matched-only results exclude
unmatched fields and must say so.

State join keys, row units, aggregation and crossing/unmatched-field policies.
Local IDs alone are insufficient across sources. These tools do not automatically
match references or attach chip scores. The outstanding boundary-distance
investigation is in the [to-do list](instance-metrics-backlog.md#ref-1-boundary-chamfer-distance).
