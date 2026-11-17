# FTW 2nd Edition descriptor pilot

The adopted next study describes **published 2024 prediction maps**. References are a separate future comparison. The aim is to test descriptor correlation, redundancy and practical complementarity across
contrasting mapped landscapes. This deliberately stratified exploratory pilot is
not a probability sample of global agriculture.

The executable specification is
[`research/geometry/configs/ftw2e-descriptor-pilot-v1.json`](../research/geometry/configs/ftw2e-descriptor-pilot-v1.json).
Selecting windows does **not** mean the real-data descriptor/correlation/PCA study
has been performed. Descriptor generation and association tools already exist.

Install the local independent geometry package with `uv sync --extra geometry`.
See [installation and historical reproduction](geometry-extraction-and-reproduction.md).
Pilot-specific code and commands live in [`research/geometry/`](../research/geometry/README.md),
with tests in `tests/research/geometry/`. Reusable descriptor computation is in
the independent `ftw_geometry.core` package; old postprocessing imports are
compatibility adapters. General workflows stay in `scripts/geometry/`.
The 2026-11-14 relocation did not rewrite existing artifacts or frozen code;
historical snapshots retain their original paths/imports. Current commands below
use the new locations; selection code hashes have changed, so use a fresh output
directory for a new selection run rather than resuming a historical run with new
code. Existing data, map links and study results are unchanged.

## Sampling design

Seven sampling rectangles, intersected with their respective country boundaries:

| Zone | Bounds (west, south, east, north; degrees) | Metric CRS |
| --- | --- | --- |
| Sacramento Valley, California | -122, 38, -121, 39.5 | EPSG:32610 |
| Central/western Netherlands | 4.3, 51.5, 5.9, 53 | EPSG:32631 |
| Western Normandy | -1.6, 48.6, -0.2, 49.4 | EPSG:32630 |
| Western Bahia | -46.5, -13.5, -44.5, -11 | EPSG:32723 |
| Eastern Rwanda | 30.15, -2.3, 30.85, -1.2 | EPSG:32736 |
| Southern/central Cambodian lowlands | 104.5, 10.8, 106, 12.5 | EPSG:32648 |
| Mekong Delta, Vietnam | 105, 9.5, 106.5, 11 | EPSG:32648 |

- Grid: 10 x 10 km squares aligned to integer multiples of 10,000 m in each CRS.
- Geometry eligibility: whole square inside rectangle, country and the union of
  published 2024 processing footprints. Natural Earth 1:10m ADM0 geometry is pinned
  to commit `9380cca83db5f9aef52d5e762765100745f84b27`, unsimplified by this tool.
  These public-domain cartographic masks are not legal boundary surveys.
  Geographic representations of metric square edges are densified at 100 m.
- Agricultural presence: at least 10% of the **entire square** is cropland in
  ESA WorldCover 2021 v200 (class 40), with at least 99% valid observations.
  Water stays in the denominator. Unknown classes/nodata are not valid observations.
  Native categorical pixels are read without overviews or resampling; pixel-centre
  inclusion and geodesic row weights approximate area. Raw ratios are retained;
  fractions slightly over one from boundary discretization are capped at one.
  The 2021 screen favors established agricultural landscapes and may miss recent
  expansion. It is not 2024 ground truth or an accuracy validation.
- Priority: ascending SHA256 of UTF-8 `study_id|seed|zone_id|ix|iy`, with seed
  `20261112` and signed integer grid coordinates ix/iy. Ties break by ix then iy.
- Primary draw: first three eligible squares in priority order with at least
  10 km edge-to-edge separation from previously accepted squares in the same zone.
  This gives 21 primary windows; separation does not establish independence.
- Reserves: first six remaining crop-eligible squares in the same ranking.
  Reserves are **not** guaranteed separated. On replacement, walk their ranking
  and check spacing against all retained primaries. Preserve the original draw
  and record every replacement and its reason.
- Crop checks are lazy. Screening every geometric candidate before ranking yields
  the same primary draw but costs unnecessary raster reads. Untested cells are
  explicitly `crop_not_evaluated`, never labeled eligible. Retain the full geometric
  candidate ranking if more reserves must subsequently be screened.

A zone with insufficient candidates fails explicitly: no thresholds, window sizes,
spacing or sampling rectangles are silently changed. Poor predictions, low
confidence, sparse mapped fields, absent expected pivots and messy geometry are
**not** replacement reasons. Processing coverage is not detection completeness.

### Boundary preflight correction

An initial implementation attempted geoBoundaries gbOpen ADM0 release `9469f09`.
Its Rwanda mask has 308 pieces and 854 holes, leaving only five fully contained
candidate squares and too few reserves. This fragmented land mask was unsuitable
for the intended country-containment rule. The successful specification uses the
same conventional Natural Earth administrative source for **all seven zones**;
it gives Rwanda 62 geometric candidates before cropland screening. No sampling
threshold was relaxed. Preserve the incomplete attempt separately from the final
draw; it is not a second statistical sample.

## Run area selection

```sh
uv run --extra geometry python -m research.geometry.select_descriptor_pilot \
  research/geometry/configs/ftw2e-descriptor-pilot-v1.json \
  --out_dir ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/selection-2024-administrative
```

Use one writer. Identical interrupted runs resume frozen sources and crop
observations. Changed config, code or recorded package versions require a new
output directory. Completed runs verify all recorded local artifact hashes and
return without querying remote inputs. Never change a frozen draw to improve its
appearance or expected descriptor relationships.

| Output | Purpose |
| --- | --- |
| `selected-windows.geojson` / `.csv` | Primaries in WGS84, centers, metric bounds and crop/valid fractions |
| `reserve-windows.geojson` / `.csv` | Ranked reserves, separate from the primary statistical sample |
| `<zone>/windows.parquet` | Exact metric primary/reserve squares in the zone's own CRS |
| `<zone>/candidate-audit.csv` | Geometric rejections, hash ranks, crop checks, roles and untested cells |
| `sources/` | Frozen collection/item metadata, coverage inventory, country geometry and byte hashes |
| `crop-observations/` | Native WorldCover chips/masks/row weights, transforms, area calculations and source identities |
| `inputs.json`, `source-code/` | Settings, dependency versions, code hashes and code snapshots |
| `selection.json`, `complete.json` | Scope, zone summaries and artifact hashes; completion only after every zone succeeds |

WorldCover size/ETag/Last-Modified are checked before and after reading. Cropped
inputs are saved and hashed, but **whole WorldCover raster checksums are not
verified**. Vector item metadata preserves advertised asset checksums; selecting
areas does not read or verify the full FTW vector files.

The coverage mirror is the live collection's `raster/2024/items.parquet`, SHA256
`22df32f3501738488d8192f88bea63ba1b01864cc9799bb6749603899b3d352d`.
If the live collection advertises a different mirror, selection stops rather than
mixing versions. Coverage footprints do not establish seam-free geometry.

## Completed selection (2026-11-12)

The artifact directory in the command above contains **21 primary windows and
42 ordered reserves**. The incomplete geoBoundaries attempt remains separately
at `../selection-2024/` and has no `complete.json`; do not use it as the pilot.

| Zone | Primary window IDs | Geometric candidates | Crop-screened candidates |
| --- | --- | ---: | ---: |
| California | `california_61_424`, `california_64_421`, `california_61_436` | 122 | 13 |
| Netherlands | `netherlands_65_573`, `netherlands_68_573`, `netherlands_61_578` | 137 | 21 |
| Normandy | `normandy_62_544`, `normandy_66_541`, `normandy_68_545` | 64 | 9 |
| Bahia | `bahia_35_867`, `bahia_41_861`, `bahia_45_871` | 567 | 13 |
| Rwanda | `rwanda_19_980`, `rwanda_21_976`, `rwanda_22_980` | 62 | 9 |
| Cambodia | `cambodia_48_125`, `cambodia_47_129`, `cambodia_47_121` | 246 | 11 |
| Vietnam | `vietnam_52_117`, `vietnam_58_118`, `vietnam_54_111` | 185 | 11 |

The 87 screened candidates are not 87 independent scientific observations; they
are eligibility checks. The 1,383 geometric candidates were **not** all screened
for cropland. Primary cropland fractions range from 14.9% to 92.6%; all primary
valid fractions exceed 99.9%. Within-zone primary spacing is at least 20 km in
this realized draw (the requirement remains 10 km). All squares have 100 km2
projected area. Coordinates, exact native bounds and fractions are in the CSVs.

Validation: verified completed-artifact hashes, recomputed crop/valid/sample
areas from every saved native chip, and checked counts, unique IDs, valid square
geometry, area, spacing, eligibility and SHA256 priorities. Focused tests:
`pytest --noconftest tests/geometry -n 0 -q` — **55 passed**, including 11 sampler
tests. Lint and formatting checks passed. **Published field polygons, imagery
review, descriptor tables and empirical correlations have not yet been run.**

### User-selected Bahia pivot diagnostic

During visual review, the user noted that the original Bahia windows mostly
capture large fields rather than center pivots, and identified a pivot-rich area
35 km west of `bahia_45_871`. A separate 10 km supplementary window,
`bahia_45_871_pivots_w35km`, was added at **35,000 m negative easting** in
EPSG:32723. Its metric bounds are `[415000, 8710000, 425000, 8720000]`, with
center approximately `(-45.733873, -11.623276)` in longitude/latitude.

Artifacts are in the sibling `diagnostic-bahia-pivots-w35km/` directory, including
`diagnostic-windows.geojson`, `.csv`, `.parquet`, native crop observations,
parent-selection hash and derivation provenance. The window is inside the frozen
zone/country/processing coverage and has 80.2% WorldCover cropland with >99.9%
valid observations. Pivot presence is user-reported; it has not been independently
confirmed by polygon/imagery analysis in this workflow.

**All 21 primary windows and 42 reserves remain unchanged.** The new window has
`role=diagnostic` and `include_in_primary_statistics=false`; it is for map-based
descriptor interpretation, not pooled/within-zone statistical estimates.

```sh
uv run --extra geometry python -m research.geometry.add_descriptor_pilot_diagnostic \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/selection-2024-administrative \
  --source_window bahia_45_871 --west_m 35000 \
  --window_id bahia_45_871_pivots_w35km \
  --out_dir ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/diagnostic-bahia-pivots-w35km
```

The diagnostic tool requires a fresh output directory and verifies the parent
artifacts before creating anything. It never edits the frozen primary draw.

## After the draw: maps first, then descriptors

### Polygon retrieval and outline-review tool

```sh
uv run --extra geometry python -m research.geometry.retrieve_descriptor_pilot \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/selection-2024-administrative \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/diagnostic-bahia-pivots-w35km \
  --out_dir ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/polygon-review-2024
```

This verifies frozen selection artifacts and reads intersecting row groups from
the published vector assets. Missing bbox statistics fail rather than trigger an
unbounded whole-file scan. Exact spatial intersection then selects complete
polygons. `fields.parquet` retains the source columns and original WKB bytes,
including invalid or multipart geometry; nothing is simplified, repaired, clipped
or reduced to its largest part. Repeated collection-qualified IDs within one
extract fail explicitly. Original WKB bytes are checked after Parquet read-back.

Per-window `audit.csv` records validity, multipart type, identical-WKB duplicates,
sampling-edge crossings and representative-point membership. Membership is
calculated in the zone's metric CRS; boundary points are included by `covers`.
These independently drawn, separated primary windows cannot share such points;
the diagnostic remains a separate population. The released schema has no seam
flag, so seam status remains **unknown**, not clean. Repeated full polygons across
extracts must still be resolved by collection-qualified ID before pooled analysis.

`index.html` links interactive outline-review maps with a red sampling boundary
and yellow field outlines. Full geometries are embedded, including holes. Leaflet
and Esri World Imagery need internet access; imagery dates vary and **are not
contemporaneous 2024 reference evidence**. Maps are viewing aids, not descriptor
maps or accuracy findings. Use `audit-summary.csv` for extraction counts and
per-window checkpoints for verified restart. HTTP range reads do not verify the
advertised whole-source checksums; the advertised checksums and accessed row
groups are retained in provenance.

A query with published vector assets but zero intersecting polygons is retained
as an empty extract and review map, with `empty_query_requires_review=true`.
Do not replace its window or infer absence of agriculture. Initial retrieval
found this outcome in `rwanda_19_980` after checking both neighboring UTM-zone
assets. It needs comparison with probability coverage, imagery and release
provenance before interpreting missing predictions. This also means descriptor
availability/empty-window counts must accompany later pooled analyses.

Retrieval completed for all 22 windows on 2026-11-12. Open
`polygon-review-2024/index.html` in the study artifact directory to review maps.
The 21 primary extracts contain 60,769 intersecting records (59,350 assigned by
representative point), including 28 MultiPolygon-typed records and no invalid geometry.
Component inspection corrected the initial interpretation: **all 28 containers
have one polygon component**, so none needs splitting or largest-part selection.
The separate Bahia diagnostic has 91 intersecting records, 69 assigned, none
multipart or invalid. No identical-WKB duplicates were detected within individual
extracts; cross-extract duplicate/identity analysis remains outstanding. These
summed extract counts are not a deduplicated global field count. All 22
per-window artifact manifests were hash-verified. The geometry test suite passes
60 tests. Map generation is complete, not systematic visual review or an
accuracy/descriptor-complementarity finding.

### Assigned-field descriptors and maps

```sh
uv run --extra geometry python -m research.geometry.describe_descriptor_pilot \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/polygon-review-2024 \
  --out_dir ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/descriptor-review-2024
```

This verifies retrieval hashes and writes a **new** corrected component audit;
the frozen retrieval files remain unchanged. Single-component MultiPolygon
containers are unwrapped with topological equality checked, preserving IDs,
boundaries and holes. Genuine multiparts cause an explicit stop, never a silent
split. Only representative-point-assigned records enter descriptor tables.

Each window receives schema-3 GeoParquet/CSV descriptors and a colored review map;
`index.html` links them. Dropdowns cover size, perimeter, shape, holes and
narrow-neck flags. **Common across sites is the default**, with an optional
**Local contrast** toggle. Shared ratios (circularity, solidity, rectangularity,
convex-hull index and hole-area fraction) use fixed 0–1 linear bounds. Area,
perimeter and elongation use full primary-population min/max with logarithmic
interpolation; hole count uses zero to primary maximum with log1p interpolation.
The 69 diagnostic fields do not influence shared bounds, but use the same scales.
Exact bounds are saved in `common-color-scales.json`. Out-of-range diagnostic
values saturate at endpoints for display only. Local contrast uses within-window
5th–95th percentiles, clipping tails for visualization. Missing values are
gray. Narrow-neck flags use false=blue and true=red, never percentile scaling.
When numeric percentiles collapse despite distinct values, the display falls
back to full min/max and labels this explicitly. Truly constant values are blue
and labeled constant. Empty windows have no fields
or fabricated zero descriptors. Esri imagery remains a date-variable viewing aid.

`primary-descriptors.parquet` and `diagnostic-descriptors.parquet` keep populations
separate, retaining source attributes, window/zone, measurement CRS, schema version
and normalization flag. Collection-qualified assigned IDs must be unique within
each population. Per-window full geometry outputs remain available for checking
measurements and future spatial analysis. No correlations or PCA are run here.

The user reviewed Rwanda's empty/missing predictions and attributes them to false
negatives. This qualitative assessment is retained; no numerical recall is
inferred. Rwanda descriptors characterize detected fields, not a representative
census of the actual landscape. The empty window contributes to availability
reporting, not zero-valued field-shape observations.

Generation completed on 2026-11-12 for **59,350 primary records and 69 separate
diagnostic records**. All 28 single-component containers were unwrapped; no IDs,
boundaries or observation counts changed, and no assigned collection-qualified
IDs repeat within either population. The empty Rwanda window has a header-only
CSV, empty GeoParquet and an explicit empty map. Corrected audits are alongside
the descriptor outputs, leaving the earlier retrieval artifacts untouched.
All output hashes and sampled per-window remeasurements were checked; numeric
descriptors are finite except deliberately undefined ambiguous orientations.
The geometry suite passes 62 tests. These are generated maps, not a completed
visual review, correlation study or accuracy evaluation.

Color-scale repair: all 22 existing HTML maps were regenerated in place after
the rare-boolean percentile-collapse bug was reported. Original maps and manifest
are preserved in the sibling `descriptor-map-colors-original/` directory. The
refreshed manifest records the renderer and map hashes; all descriptor tables,
CSV measurements and audits retain their original hashes. A JavaScript-executed
regression test covers a 1%-true boolean and rare nonzero numeric values.

On 2026-11-13 all 22 maps were refreshed to common-default/local-toggle rendering.
Measurement and audit hashes are unchanged. Previous HTML and manifests are
preserved in sibling `map-history-*` directories. Reproduce a map-only refresh:

```sh
uv run --extra geometry python -m research.geometry.refresh_descriptor_pilot_maps \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/descriptor-review-2024
```

The refresh tool verifies the existing manifest, backs up maps, derives scales
only from `primary-descriptors.parquet`, and verifies all measurement/audit files
remain unchanged. JavaScript tests exercise local and shared modes, including
rare booleans and log1p shared hole-count rendering.

1. Validate windows and inventories, then retrieve complete intersecting published
   vector geometry, preserving attributes and collection-qualified identities.
   Do not clip fields, impose new confidence/size filters or run inference.
   Assign fields by a deterministic representative point with a fixed boundary
   tie-break, and audit repeated retrievals.
2. Audit validity, multipart prevalence, duplicates and seam/coverage flags.
   Preserve multiparts; do not use the CLI's largest-part-only export path. The
   existing descriptor builder requires single polygons: settle parent/part
   semantics before generation, not an implicit explode or omission.
3. Review imagery plus outlines and selected descriptor maps. Replace only for
   documented corrupt/missing data or verified incomplete processing coverage.
   If needed, add a separate Bahia pivot diagnostic window; do not replace
   statistical windows to obtain perfect circles.
4. Generate schema-3 descriptors in each zone's suitable CRS with traceable joins.
   Per-field shape analysis does not require regional density or gap analysis.
5. Study algebraic dependencies first, then availability, constants/rare features,
   Pearson/Spearman, within-zone and size-stratified associations, selected-feature
   PCA, spatial-block/sample sensitivity and visual descriptor disagreements.
   Do not pool raw projected positions across CRSs or use raw axial angles as
   ordinary linear features. Select a defensible block size after inspecting
   spatial structure; the 10 km sampling gap is not automatically that block size.

Naturally occurring unusual shapes stay in the main sample. Additional handpicked
examples belong in a separate illustration set, not correlation estimates. Low
correlation alone does not prove useful complementarity. Equal counts of windows
do not give equal field counts or globally representative pooled correlations.

## Provenance and eventual integration

### Reviewing descriptor disagreements

Open the sibling `disagreement-review-2024/index.html` for **105 pair examples
covering 93 unique primary fields**. Each row shows the landscape, window, field
ID, two measured descriptor values and their absolute within-landscape percentile
rank difference. The two descriptor links open the same field colored by each
measure, zoom to it and highlight its boundary in magenta. Popups list its
measures. Some fields appear in multiple pairs; none was added or reweighted.

All 22 descriptor maps now include exact field-ID search, Enter/Find navigation
and Clear highlight. Fragment links use `#field=ENCODED_ID&feature=DESCRIPTOR`;
switching a fragment in an already-open map also updates focus. Unknown IDs show
a message rather than silently selecting a different field. The HTML index needs
no data server; internet remains necessary for Leaflet and the imagery basemap.

The review is qualitative interpretation, not an accuracy score or evidence that
a prediction error caused a disagreement. Compare the two shape values and field
geometry, note possible artifacts, and keep basemap date differences in mind.
The index excludes the handpicked Bahia diagnostic. Its source CSV and unchanged
primary descriptor input hashes are recorded in its manifest. All 210 map links
and artifact hashes were validated; JavaScript regression tests exercise hash
focus, zoom/highlight selection and missing-ID handling. Measurement hashes and
statistical samples are unchanged.

Reproduce with `python -m research.geometry.refresh_descriptor_pilot_maps DESCRIPTOR_DIR`,
then `python -m research.geometry.build_descriptor_review_index ANALYSIS_DIR --maps_dir DESCRIPTOR_DIR --out_dir NEW_INDEX_DIR`.

Initial full-primary-table associations/PCA are now available in the
[descriptor-complementarity report](research/descriptor-complementarity.md).
Canonical artifacts are in the sibling `complementarity-2024-stable-ranks/` directory.
The pivot diagnostic is excluded. All fields are used, with no spatial confidence
intervals, significance tests or raw-orientation correlations. Reproduce with
`python -m research.geometry.analyze_descriptor_pilot DESCRIPTOR_DIR --out_dir NEW_DIR`,
then `python -m research.geometry.report_descriptor_pilot NEW_DIR --descriptor_dir DESCRIPTOR_DIR`.
The user has reviewed disagreement examples; a written synthesis and
spatial-sensitivity work remain outstanding.

### Regional landscape profiles

The next phase summarizes all 21 primary windows as regional observations,
retaining the empty Rwanda window and excluding the handpicked Bahia diagnostic.
It includes every shape descriptor, size/supporting dimensions, holes,
narrow-neck prevalence, orientation, counts/density, coverage/overlaps and
edge-guarded positive spacing. See the [regional methods and findings](research/regional-landscape-profiles.md).

```sh
uv run --extra geometry python -m research.geometry.summarize_descriptor_pilot \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/polygon-review-2024 \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/descriptor-review-2024 \
  --out_dir ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/regional-landscape-2024-v2
```

Use a fresh output directory. Main spacing summaries compare 50/100/250 m radii
and exclude fields without complete within-window search context, because the
original extracts contain no exterior halo. Unknown release seams remain explicit.
Rwanda omissions limit mapped density, coverage and spacing interpretation. No
reference evaluation, repairs or Zambia analysis are part of this command.

The live 2024 release documents a newer extraction recipe than the fixed
`ftw-fbp==0.2.0` `FTW_2E` preset assessed here: mean field probability 0.10,
extraction hole fill strictly below 100 m2, minimum area 900 m2, plus coverage
simplification and subsequent filtering/cleanup. Its separate downstream 20 m2
hole rule is distinct from extraction filling. The older GitHub catalog README
is not sufficient provenance. These descriptors characterize the final published
map, not the raw landscape's small-field or hole distribution.

References are optional, separately versioned inputs, not substitutes for maps.
Netherlands BRP and France RPG include 2024 declarations; California 2024 Statewide
Crop Mapping is provisional. Rwanda and AI4SmallFarms Cambodia/Vietnam mapped
references are 2021; the Bahia mapped sample is 2020. Temporal mismatch,
declared-parcel versus visual-field meaning, presence-only coverage and training
overlap require review before accuracy evaluation. Keep reference descriptors,
prediction descriptors and matches/outcomes separate. Do not replicate chip
accuracy scores onto fields and treat them as independent observations.

Descriptor computation is now model-independent in the local `ftw-geometry`
package nested under this repository. A future production CLI adapter or separate
repository remains possible; no publication or production-exporter rewrite is
part of this extraction. FTW FBP sidecar defaults remain supported through the
optional package dependency. Chamfer research stays outstanding and deferred.

Sources: [2024 vectors](https://data.source.coop/ftw/global-data-2e/vector/2024/collection.json),
[2024 rasters](https://data.source.coop/ftw/global-data-2e/raster/2024/collection.json),
[harmonized fields](https://source.coop/ftw/harmonized-field-data),
[WorldCover](https://esa-worldcover.org/en/data-access),
[Natural Earth terms](https://www.naturalearthdata.com/about/terms-of-use/),
[CLI design](https://github.com/fieldsoftheworld/cli/blob/main/docs/design.md).
