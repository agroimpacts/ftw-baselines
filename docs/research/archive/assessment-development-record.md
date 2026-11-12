# Historical assessment and export development record

This combined record preserves the original tables, commands and experiment
chronology. It is not the current guide. Start with the separate reports on the
[FTW_2E assessment](../ftw-2e-assessment.md), [object identity](../object-identity.md),
and [schema-3 export validation](../polygon-export-validation.md).

## Conclusion and chronology

Reference-metric findings below are completed work for their original scope,
not a claim that all reference-metric research is finished. Boundary-distance
research remains outstanding in the [to-do list](../../instance-metrics-backlog.md).
Polygon validation checks export fidelity, not prediction accuracy. Descriptor
definitions live in the [descriptor guide](../../polygon-export-and-descriptors.md), rather than this report.

Read the dated experiments **newest first**: schema-3 rerun → schema-2 descriptors → polygon
fidelity (Nov 10) → reference/prediction identity follow-ups (Nov 5) →
FTW_2E 0.2.0 assessment (Nov 5) → archived pre-0.2.0 methods. Same-day sections follow
their experimental dependency order in reverse. No table has been pooled across
different identity modes or rewritten as a result of documentation cleanup.

The fixed preset did not establish a consistent across-country PQ gain; defaults
remain unchanged. Export fidelity is verified on the selected Germany chip, not
at continental inference scale. Current operational status is in the
[current status](../../instance-metrics-progress.md), not in old experiment instructions.

## Descriptor schema 3.0 rerun and artifact cleanup (2026-11-11)

The Germany chip was rerun from the same saved probabilities and fixed-method
labels using unchanged FTW_2E 0.2.0. The single current output is
`~/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany/polygon-validation/g1_00003_16_schema3/`.

All four formats pass: 13 valid single polygons, two holes, zero uncleaned raster
round-trip mismatches, and descriptor agreement with persisted geometry.
Vectorization strides 31/64/127/2048 agree. The cleaned example retains 13 fields
and passes descriptor checks. Every sidecar declares version 3.0; removed columns
are absent. Retained values and geometries were compared to schema 2 before
cleanup and are unchanged (descriptor tolerance `rtol=1e-12`, `atol=1e-8`).

After verification, four superseded folders were removed: `g1_00003_16`
(incomplete debug), `_verified` (before redundant vertex cleanup), `_final`
(original five descriptors), and `_descriptors_v2` (schema 2). The parent
`polygon-validation/README.md` records this history and describes the current
files. Source probabilities, saved labels and all reference-score assessments
were left untouched. This run is export/geometry validation, not a larger-area
correlation/PCA study.

## Descriptor schema 2.0 follow-up (2026-11-10; superseded artifacts)

Germany `g1_00003_16` was regenerated using the unchanged preset and expanded
descriptors at `germany/polygon-validation/g1_00003_16_descriptors_v2/` under the
existing assessment root. All four formats pass: 13 IDs, two holes, valid
polygons, zero uncleaned raster mismatches, and matching read-back descriptors.
These artifacts were superseded and removed after the schema-3 rerun above.
Schema 2.0 included circularity,
rectangle/hull quantities, holes, orientation and narrow-neck diagnostics.

## Polygon export and final-geometry validation (2026-11-10)

This is export-fidelity validation, not another accuracy assessment or preset
selection. The unchanged published `FTW_2E` is recomputed from Germany
`g1_00003_16` saved float probabilities and checked against its previously saved
instance labels. No reference masks, training behavior or defaults are changed.

The checks below originally used `g1_00003_16_final/`. That folder and the other
intermediate chip exports were removed after the schema-3 rerun; use
`g1_00003_16_schema3/` for the current verified artifacts. `validation.json`
records checks; each export also has `.descriptors.csv` and `.metadata.json`
siblings. The historical check results below remain unchanged.

| Check | Verified result |
| --- | --- |
| Recomputed IDs versus saved fixed-method labels | All 13 IDs agree |
| Geometry | 13 valid single polygons; both holes preserved |
| CRS | Source/output EPSG:4326; cleanup/descriptors EPSG:32633 |
| Export formats | fiboa GeoParquet, GeoJSON, GeoPackage, FlatGeobuf |
| Rasterization of each uncleaned export | 0 differing pixels from saved FBP labels |
| Vectorization stride 31 / 64 / 127 / 2048 | Same IDs and topologically equal geometry; 0 differing pixels |
| Final uncleaned polygon area in local UTM | 750,645.5202 m² total (not the scalar FBP filtering area) |
| Descriptor sidecars | Match recomputation from each file's persisted geometry |
| Explicit 15 m simplification / 500 m² filtering | 13 valid exported fields; sidecar matches final geometry |

The seam test exposed microscopic gaps caused by applying floating-point
georeferencing separately per window. Vectorization now joins fragments by ID
on exact integer pixel coordinates, removes redundant collinear vertices there,
then applies the affine once. Different IDs are never dissolved together.
Synthetic tests also cover rotated/fractional affines, touching IDs, multipart
identity, holes, empty outputs, uint8 decoding, geographic cleanup, invalid
probabilities, overwrites and the unchanged legacy CLI route. GeoParquet's
fiboa geometry-metrics attributes use float32 (checked with `rtol=1e-7`);
the descriptor CSV is independently computed from read-back geometry at float64.

Reproduce into a **new or empty directory** (the validator refuses existing
artifacts rather than overwriting them):

```sh
uv run --extra fbp python -m scripts.geometry.validate_instance_polygon_export \
  "$HOME/working/ftw/metrics/test/prue-b7_germany_test_prob/probabilities/germany/g1_00003_16.tif" \
  "$HOME/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany/labels/ftw-2e/germany/g1_00003_16.tif" \
  --out_dir "$HOME/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany/polygon-validation/g1_00003_16_schema3_recheck"
```

Limits: FBP itself still processes the whole scene. These stride checks validate
**vectorization seams**, not `fbp.run_windowed`, cross-chip reconstruction,
global seam ownership, or large-scene memory use. Axis-aligned geographic grids
use the existing assessment's mean geodesic pixel-area convention without
resampling probabilities; rotated geographic grids and masked/nodata inputs are
rejected. The preset's own 900 m² filter remains unchanged even when export
`min_size=0`. Denmark provenance remains deferred as described below.

## Reference identity audit and opt-in assessment (2026-11-05)

Read-only audit of the same 1,469 test chips found all paired
`label_masks/instance/<chip>.tif` files present, spatially aligned with
`semantic_3class/<chip>.tif`, and **exact equality** between positive instance
pixels and semantic class 1 on every chip. Supplied IDs retain information that
connected components of class 1 cannot recover. Counts below sum chip-local IDs,
not globally unique fields; chip-edge portions are not reconstructed across chips.

| Country | Supplied IDs | 4-connected components | 8-connected components |
| --- | ---: | ---: | ---: |
| Belgium | 6,498 | 7,541 | 3,529 |
| Cambodia | 15,370 | 15,811 | 7,786 |
| Brazil | 689 | 898 | 711 |
| Croatia | 15,191 | 18,648 | 7,405 |
| Denmark | 1,597 | 6,674 | 4,506 |
| Germany | 2,867 | 4,043 | 2,054 |
| Vietnam | 10,490 | 11,224 | 5,692 |
| Total | 52,702 | 64,839 | 31,683 |

Four-connectivity splits at least one supplied ID in 1,043 chips (5,128
fragmented IDs) and merges IDs in 240 chips (496 merged components). There are
5,228 single-pixel components; total component count is 23% above supplied-ID
count. Eight-connectivity still fragments IDs in 807 chips and merges IDs in
921 chips (7,796 merged components), so switching connectivity is not a repair.
These findings establish identity changes, not their causes or the correctness
of every source annotation. Denmark's substantial grouping needs source-provenance
review before any proposal to change defaults.

The new **offline-only**, opt-in `--reference-mode dataset-instance-ids` preserves
disconnected reference pieces under one positive ID, compacts sparse uint64 IDs,
and requires foreground equality on valid pixels. Semantic masks still define
the valid domain; class 0 remains valid background despite nodata metadata.
Training validation, pixel metrics and the default `semantic-components` mode
are unchanged. In this initial reference-only experiment, prediction handling
was deliberately unchanged: component methods
keep their requested connectivity, while FBP predictions are split into
4-connected pieces after valid-domain masking. The separate prediction-ID
comparison below does not overwrite this reference-only experiment.

For `germany/g1_00003_16`, references change from 63 components to 47 supplied
IDs. All three methods retain 10 TP; recall rises from .1587 to .2128.
Components-4 PQ changes from .2218 to .2800; FTW_2E from .2039 to .2582.
These are different reference definitions, not improvements to the predictions.

The opt-in cohort assessment completed on all 1,469 chips. Country-pooled PQ:

| Country | Components-4, semantic refs | Components-4, supplied IDs | FTW_2E, supplied IDs |
| --- | ---: | ---: | ---: |
| Belgium | .5485 | .5892 | .5643 |
| Cambodia | .2499 | .2542 | .2811 |
| Croatia | .3484 | .3842 | .3913 |
| Denmark | .5672 | .1810 | .1856 |
| Germany | .4143 | .4946 | .4917 |
| Vietnam | .1523 | .1595 | .1506 |
| Brazil (presence-only) | — | — | — |

Reference identity changes can lower scores as well as raise them. Denmark's
supplied IDs group many components; baseline precision falls to .1488 and recall
to .5492 (FTW_2E .1589/.5410). This is not grounds to reject those IDs, but it
requires annotation-provenance review before calling them individual-field
ground truth or changing defaults. Brazil recall changes from .7394 to .9448
for components-4 and from .7439 to .9492 for FTW_2E; precision/PQ stay undefined.
Within the supplied-ID mode FTW_2E PQ exceeds components-4 in Cambodia, Croatia
and Denmark but is lower in Belgium, Germany and Vietnam. No universal gain is
established; no settings were tuned and no uncertainty intervals computed.

The selected Germany chip has also been rendered under the nested mode's
`figures/ftw-2e/selected/` directory. Only its baseline and FTW_2E labels were
cached. The original component-reference figure and scores remain unchanged.

Cohort outputs are nested within the existing assessment:
`prue-b7_ftw-2e_0.2.0_assessment/<country>/reference-modes/dataset-instance-ids/`.
Each has its own chip table and pooled summary, with explicit `reference_mode`
and `prediction_identity`. Do not pool or compare absolute scores without
identifying the reference mode. Existing assessment files are not overwritten.

```sh
uv run --extra fbp python -m scripts.instance_evaluation.compare_instance_methods \
  "$HOME/working/ftw/metrics/test/prue-b7_germany_test_prob" \
  --reference-mode dataset-instance-ids \
  --out_dir "$HOME/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany/reference-modes/dataset-instance-ids"
```

Use `--chip COUNTRY/AOI_ID` for a subset in a new output directory. To visualize
the new mode, point `visualize_instance_methods` at its nested directory and use
`--method ftw-2e --chip germany/g1_00003_16 --generate-missing-labels`.
The reference panel and match outlines then use supplied IDs; the raw classes
panel stays semantic. Cached-label regeneration honors the recorded reference mode.

### Preserving FBP prediction IDs

The offline comparison now accepts `--prediction-identity preserve-ids`, alongside
the unchanged default `split-components`. Both apply the semantic valid-domain
mask first; preservation then compacts surviving positive IDs without separating
disconnected pieces. IDs with no surviving pixels disappear. Component methods
still use their requested connectivity in either mode. No training behavior,
FBP configuration or probability input changes.

The audit records raw/masked method-ID counts, four-connected component counts,
fragmented IDs/chips, IDs removed by masking, and IDs whose piece count increases
through masking. Counts sum chip-local objects, not globally unique fields.
`identity_*` chip-table columns and `prediction_identity_audit` in the summary
contain the measurements. `prediction_identity_mode` records the scoring choice;
older assessments lacking it mean `split-components`. Cached-label generation
and visualization honor that choice and reject a regenerated mode mismatch.

On `germany/g1_00003_16`, all 13 FBP IDs are four-connected before and after
masking. Preservation therefore leaves TP/FP/FN (10/3/37), recall (.2128) and PQ
(.2582) unchanged with supplied-ID references.

Completed cohort audit: **all 41,957 raw FBP IDs are four-connected** across
1,469 chips. Disconnection occurs only after masking, and only in Brazil:

| Country | Raw FBP IDs | Surviving IDs | Post-mask components | Fragmented IDs | Affected chips |
| --- | ---: | ---: | ---: | ---: | ---: |
| Belgium | 5,362 | 5,362 | 5,362 | 0 | 0 |
| Cambodia | 9,584 | 9,584 | 9,584 | 0 | 0 |
| Brazil | 2,443 | 978 | 2,876 | 355 | 126 |
| Croatia | 12,885 | 12,885 | 12,885 | 0 | 0 |
| Denmark | 5,439 | 5,439 | 5,439 | 0 | 0 |
| Germany | 1,946 | 1,946 | 1,946 | 0 | 0 |
| Vietnam | 4,298 | 4,298 | 4,298 | 0 | 0 |
| Total | 41,957 | 40,492 | 42,390 | 355 | 126 |

Brazil masking removes 1,465 IDs entirely and increases the piece count of
355 surviving IDs. Preserving membership changes additive statistics in exactly
126 chips. The six fully labeled countries have identical FBP statistics and
scores between prediction modes (so the preceding PQ table also applies to
preserved predictions). Both component methods have exactly unchanged pooled
statistics and scores in every country, verified programmatically.

Brazil FTW_2E object recall falls from .9492 with split predictions to .7707
with preserved IDs. Disconnected visible pieces can no longer match separate
references independently when they belong to one predicted ID: IoU is computed
over their combined surviving area and matching remains one-to-one. This is a
mask/identity/matching interaction, not changed model output or evidence about
the ignored area's correctness. Presence-only reference coverage limits its
interpretation; precision and PQ remain undefined. No new tuning or inference
was performed. The Germany figure has been rendered in the preserved-mode
directory; only its two requested label rasters were cached.

Outputs are nested under the supplied-reference assessment at
`prediction-modes/preserve-ids/`, with previous assessments unchanged:

```sh
uv run --extra fbp python -m scripts.instance_evaluation.compare_instance_methods \
  "$HOME/working/ftw/metrics/test/prue-b7_germany_test_prob" \
  --reference-mode dataset-instance-ids --prediction-identity preserve-ids \
  --out_dir "$HOME/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany/reference-modes/dataset-instance-ids/prediction-modes/preserve-ids"
```

For visualization use that output directory with the same existing visualizer
and `--method ftw-2e --chip germany/g1_00003_16 --generate-missing-labels`.
Denmark's source-ID grouping still requires provenance review before any
interpretation as individual-field ground truth or default change.

## FTW_2E 0.2.0 follow-up (2026-11-05)

The follow-up uses `ftw-fbp[fast]==0.2.0`'s distributed `FTW_2E` preset unchanged,
with no sweep or test-based tuning. It compares components-4, components-8
and `ftw-2e` on the same seven saved test runs listed below. It is a raw
instance assessment, not evaluation of the catalog's full polygon pipeline.
Completed: 1,469 chips. Results are under
`~/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/<country>/`.
Only chip tables and summaries are written; inputs are reused and labels are
not duplicated by default. Summary files record the complete preset and package
version. For visual inspection, cache only the selected chip's missing labels
inside its existing assessment directory (no separate visual comparison run):

```sh
uv run --extra fbp python -m scripts.instance_evaluation.visualize_instance_methods \
  "$HOME/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany" \
  --method ftw-2e --chip germany/g1_00003_16 --generate-missing-labels
```

This verifies recorded provenance/configuration and reproduces all additive
statistics for the selected methods before caching TIFFs under `labels/` and
updating only label paths in `chips.parquet`. Scores and `summary.json` remain
unchanged. The figure is saved under
`figures/ftw-2e/selected/germany_g1_00003_16.png`. Subsequent visualizations can
omit `--generate-missing-labels`; existing figure files are not overwritten.
Without `--chip`, only the ranked selection (controlled by `--limit`) is cached.

| Country | Components-4 PQ | FTW_2E PQ | Difference |
| --- | ---: | ---: | ---: |
| Belgium | .5485 | .5234 | -.0251 |
| Cambodia | .2499 | .2762 | +.0263 |
| Croatia | .3484 | .3521 | +.0037 |
| Denmark | .5672 | .5650 | -.0022 |
| Germany | .4143 | .4080 | -.0063 |
| Vietnam | .1523 | .1435 | -.0088 |
| Brazil (presence-only) | — | — | — |

These are country-pooled scores, not averages of chip scores. FTW_2E raises
object precision in five of the six fully labeled countries, but lowers recall
in all except Cambodia. Recovery and support also fall in those five countries;
both Rand scores rise in all six. Thus improved partition diagnostics do not
imply improved overall delineation. Brazil object recall rises from .7394 to
.7439; precision and PQ remain undefined. No uncertainty intervals were computed.
This assessment does not establish a consistent PQ gain or justify switching
defaults. At this stage the decision was to retain the existing baseline and
review final polygon behavior before optional integration; the later export
validation is documented above. No settings were changed after observing results.

The saved geographic grids are not resampled. FBP receives mean geodesic
pixel area across each chip's rows for its fixed 900 m² filter (projected
grids use affine area converted to m²). This chip-average approximation and
the transfer from the preset's native 2.5 m data must accompany interpretation.
Saved float probabilities are quantized internally by the preset's `fast=True`.
The source manifest retains the checkpoint, reference extraction and input
provenance; presence-only countries still have no evaluable precision or PQ.

Example (repeat for the seven countries; existing output paths are refused):

```sh
uv run --extra fbp python -m scripts.instance_evaluation.compare_instance_methods \
  "$HOME/working/ftw/metrics/test/prue-b7_belgium_test_prob" \
  --out_dir "$HOME/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/belgium"
```

## Archived pre-0.2.0 assessment (earliest experiment)

The results and commands below used FBP commit `6997c53`, now preserved as
`archive/pre-ftw-fbp-0.2.0` in the FBP fork. They are not results for `FTW_2E`.
To reproduce the historical commands, use that archived package and explicitly
pass `--strategies arg-ws2 arg-pb-h0.01-t0.3 nbg-pb-h0.01-t0.3`;
the current script defaults to `ftw-2e` instead.

PRUE B7 checkpoint SHA-256 `2b1b34a17b85b8f70da6ff737529743b6bc6049e987bce5a1fcdd7279eb3b120`.
This follow-up is **test only**, with the previously fixed methods and parameters:
`components-4`, `components-8`, `arg-ws2`, `arg-pb-h0.01-t0.3`,
`nbg-pb-h0.01-t0.3`. No settings were selected from these test results.
The existing Germany and Vietnam probability runs were reused; the five other
probability runs were generated with the same checkpoint and three-class settings.

| Country | Evaluated test chips | Components-4 PQ | Arg-pb PQ | Nbg-pb PQ |
| --- | ---: | ---: | ---: | ---: |
| Belgium | 198 | .5485 | .5509 | .2126 |
| Cambodia | 25 | .2499 | .2503 | .2496 |
| Brazil (presence-only) | 188 | — | — | — |
| Croatia | 353 | .3484 | .3523 | .1707 |
| Denmark | 332 | .5672 | .5686 | .1676 |
| Germany | 350 | .4143 | .4155 | .1224 |
| Vietnam | 23 | .1523 | .1524 | .1158 |

For countries with labeled background, these are **pooled** PQ values,
computed from summed sufficient statistics,
not means of per-chip PQ. Cambodia has 34 metadata test AOIs but only 25
with both image windows and a three-class reference mask; those 25 were
evaluated. The counts above sum to 1,469. Do not treat the large difference
in per-country sample sizes as equal evidence or silently average countries.
The archived Brazil run calculated component-4/arg-pb/nbg-pb PQ as
`.5635/.5640/.1994`, respectively. Those are **historical calculations, not
evaluable results**: Brazil has presence-only labels without true background,
so its FP count, precision, RQ and PQ cannot be interpreted as full-detection
quality. New evaluation and method-comparison runs report these scores as
undefined; existing saved runs were not rewritten. Brazil recall remains
evaluable. In the archived Brazil comparison, pooled object recall is `.7394`
for components-4 and arg-pb (664 TP / 234 FN), and `.7595` for nbg-pb
(682 TP / 216 FN). This is a **recall-only** comparison, not evidence that
nbg-pb has better precision or overall detection quality. Raw object counts
remain useful for debugging.
This policy also applies to other presence-only countries (India, Kenya and
Rwanda), although they are not included in this seven-country assessment.
`arg-ws2` collapses its watershed splits and should not be interpreted as an
independent split strategy. The no-filter `nbg` variant includes class-2
boundary pixels as foreground. See [early comparison](early-fbp-comparison.md)
for the original validation and test selection history.

The paired score diagnostics show why inspecting more than PQ matters. For the
4-component baseline, the Spearman relationship between chip recovery and
object recall ranges from .181 in Brazil (188 finite chips) to .971 in Vietnam
(23 chips); these measures can select different examples even when their
country-level trends agree. With `arg-pb` versus components-4 in Cambodia,
chip-level PQ and recovery move in **opposite directions on 11 of 25** finite
chips. This identifies cases to inspect, not evidence for a preferred measure.

Run from the repository root (replace paths if needed):

```sh
for country in belgium cambodia brazil croatia denmark; do
  uv run ftw model test \
    --model "$HOME/working/models/ftw/FTW_PRUE_EFNET_B7.ckpt" \
    --dir "$HOME/data/labels/cropland/ftw" \
    --countries "$country" --model_predicts_3_classes \
    --test_on_3_classes --gpu -1 --save_probabilities \
    --out_dir "$HOME/working/ftw/metrics/test/prue-b7_${country}_test_prob"
done
for country in belgium cambodia brazil croatia denmark germany vietnam; do
  uv run --with ../fbp python -m scripts.instance_evaluation.compare_instance_methods \
    "$HOME/working/ftw/metrics/test/prue-b7_${country}_test_prob" \
    --strategies arg-ws2 arg-pb-h0.01-t0.3 nbg-pb-h0.01-t0.3 \
    --out_dir "$HOME/working/ftw/metrics/test/prue-b7_${country}_methods_fixed_labels" \
    --save_labels
done
```

The second command writes `chips.parquet`, `summary.json`, and
`labels/<method>/<country>/<aoi_id>.tif` to each **new** comparison directory.
The TIFFs retain integer instance IDs and the reference grid. Existing output
directories are never overwritten. To inspect the largest absolute chip-level
PQ changes from `components-4` for `arg-pb`:

```sh
uv run python -m scripts.instance_evaluation.visualize_instance_methods \
  "$HOME/working/ftw/metrics/test/prue-b7_belgium_methods_fixed_labels" \
  --method arg-pb-h0.01-t0.3 --metric pq --limit 10
```

Use `--chip belgium/AOI_ID` to select a specific chip, `--baseline components-8`
to change the paired baseline, or `--method nbg-pb-h0.01-t0.3` for that variant.
Plots show both imagery windows, plain reference and semantic masks, side-by-side
baseline and method instance IDs, and TP/FP/FN outlines **for the chosen method**.
New Brazil plots omit FP outlines and show FP as unavailable.
Figures are saved within the comparison directory under
`figures/<method>/selected/` or `figures/<method>/delta-<metric>/`.

To quantify measure relationships and method changes by country and globally:

```sh
uv run python -m research.instance_metrics.assess_instance_measures \
  "$HOME/working/ftw/metrics/test/prue-b7_belgium_methods_fixed_labels" \
  "$HOME/working/ftw/metrics/test/prue-b7_cambodia_methods_fixed_labels" \
  "$HOME/working/ftw/metrics/test/prue-b7_brazil_methods_fixed_labels" \
  "$HOME/working/ftw/metrics/test/prue-b7_croatia_methods_fixed_labels" \
  "$HOME/working/ftw/metrics/test/prue-b7_denmark_methods_fixed_labels" \
  "$HOME/working/ftw/metrics/test/prue-b7_germany_methods_fixed_labels" \
  "$HOME/working/ftw/metrics/test/prue-b7_vietnam_methods_fixed_labels" \
  --out_dir "$HOME/working/ftw/metrics/analysis/seven_countries_test_fixed"
```

`measure_pairs.csv` reports pairwise-complete Spearman correlation and the
fraction of chips in exactly one measure's top quartile. `discordant_chips.csv`
lists the largest *rank* disagreements for visual inspection.
`method_differences.csv` reports per-country paired **mean chip-score** changes,
95% chip-bootstrap intervals (1,000 draws, seed 42), improved/worsened/tied
counts, and counts of opposing metric directions. These means and intervals
are **not pooled PQ** or spatially independent confidence intervals: nearby
chips can be correlated. Undefined scores are excluded separately for each
measure; check `n`. These comparisons quantify different reactions to the
same predictions, not independent proof of which measure is best. A future
evaluation against blinded expert review or an external downstream outcome
would support a stronger claim about complementary *usefulness*.
The previously generated Brazil comparison tables still contain finite
FP-dependent scores: do **not** interpret Brazil's PQ/precision differences
from those tables or include them in pooled FP-dependent analysis. Recreate
the method-comparison output with the updated script to obtain undefined
scores for Brazil; for cross-country analysis, also recreate any derived
analysis outputs from those new inputs. The assessment script pools raw
`stat_*` values, so even with new Brazil chip tables its seven-country
`global_pooled_scores.csv` can still calculate invalid FP-dependent ratios:
exclude Brazil when reporting pooled precision/F1/RQ/PQ.

The seven-country run also writes `global_measure_pairs.csv`,
`global_method_differences.csv` and `global_discordant_chips.csv` with the
same analyses on **all chips together**. Global correlations and top quartiles
are calculated on the combined finite chip population, not averages of
country correlations; global examples retain `chip_country` for locating
their imagery. A pooled chip-level correlation may reflect between-country
differences, so read it alongside the country rows. Global paired differences
use `(country, aoi_id)` as the join key and their intervals resample countries
and paired chips within countries (seed 42). `equal_country_differences.csv`
averages each country's finite paired mean with **one vote per country** and
resamples country means for its intervals. Check the finite `n` / `countries`:
the archived global mean chip PQ change used 1,318 finite pairs, including
non-evaluable Brazil PQ pairs. That historical global PQ change is therefore
**not** a valid seven-country PQ comparison; recalculate on the six countries
with labeled background before citing it.
`global_pooled_scores.csv` instead sums additive `stat_*` columns before
calculating scores. The archived seven-country pooled PQ values (.3552 for
components-4, .3570 for `arg-pb`, .1788 for `nbg-pb`) are likewise **not
evaluable** because Brazil contributes to the pooled FP counts. Compute PQ
only for the six countries with labeled background; no replacement six-country
values are asserted here. These three
aggregations answer different questions; none alone establishes a preferred
post-processing method. Confidence intervals do not account for spatial
dependence among neighbouring chips, and seven countries limit inference to
new regions.

The later scope dropped parameter sweeps entirely and validated an opt-in
published-preset export, as documented above. This archived experiment is not an
outstanding task; remaining large-scene limitations are in [current status](../../instance-metrics-progress.md).
