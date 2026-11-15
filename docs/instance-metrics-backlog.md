# Research and development to-dos

Read with [current status](instance-metrics-progress.md). This list distinguishes
requested research from deferred possibilities; it does not authorize running
studies or changing defaults automatically.

## REF-1: Boundary Chamfer distance

**Outstanding reference-metric research.** Compare boundary discrepancy using:

1. **Standard object matching:** the existing one-to-one, strict-IoU matching
   rule. Distance then describes boundary accuracy among successfully matched
   objects, not all predictions/references. Report matching coverage alongside it.
2. **Best-IoU pairing:** investigate whether choosing the best-overlapping
   prediction per reference gives a defensible additional diagnostic. Specify
   zero-overlap handling, direction, whether predictions can be selected more
   than once, and implications for splits/merges. This is a candidate, not an
   adopted scoring contract.

Before implementation, specify symmetric versus directed distance, squared
versus unsquared distances, boundary sampling/length weighting, holes, metric
units/CRS, valid-domain and chip-edge treatment, empty/unmatched objects and
aggregation from objects to chips/countries. Do not silently turn misses into
zero boundary error or treat matched-only results as full-detection accuracy.

Test controlled offsets, identical boundaries, splits, merges, small objects,
holes, missing matches and sampling/resolution sensitivity. Then evaluate real
saved predictions and extend complementarity analysis, including availability,
matching coverage, size/country effects and visual disagreement review. Existing
reports remain historical results for their original eight metrics.

## GEO-1: Real larger-area descriptor study

**Active polygon-first pilot.** The adopted [study specification](descriptor-pilot.md)
selects published 2024 FTW 2nd Edition maps: three separated 10 km windows in each
of California, Netherlands, Normandy, western Bahia, eastern Rwanda, Cambodia and
Vietnam. Freeze the release, coverage, country masks and independent cropland
screen; retain the deterministic draw and reserves without cherry-picking shapes.
Area selection is complete: 21 primary windows and 42 reserves, with input and
eligibility checks recorded. Assigned-field schema-3 tables/maps are complete for
59,350 primary and 69 separate diagnostic records. The initial full-primary-table
[descriptive correlations/PCA](research/descriptor-complementarity.md) are complete;
spatial uncertainty, visual disagreement review and practical feature selection
remain outstanding.

Geometry-preserving polygon retrieval and outline-map generation are complete
for all 22 windows, and the user reviewed the maps. Rwanda's missing predictions
were visually assessed as false negatives, without a numerical recall estimate.
All 28 MultiPolygon-typed records have exactly one component; unwrap the container
without splitting observations; this normalization and descriptor generation/maps
are now complete, along with initial availability/distributions, full-table
within-zone/size-stratified associations and selected-feature PCA. Next are
descriptor-disagreement map review, spatial sensitivity and practical
complementarity assessment, acknowledging algebraic dependencies.
Pilot infrastructure is isolated in `research/geometry/`; reusable descriptor
functions stay model-independent in the library for eventual CLI integration.
Keep handpicked illustrations separate from the statistical sample. Resolve
multipart/parent semantics and seam/duplicate policies before descriptor generation.
Window selection is not a completed descriptor study.

Prepare for future polygon-reference evaluation with separate prediction/reference
descriptors and explicit match/outcome tables. Review year alignment, field meaning,
training overlap and annotation completeness first. Existing polygons are the main
input, not an instruction to expand inference or re-vectorization. Keep functions
portable for eventual CLI integration without migrating or extracting a package yet.

Regional landscape summaries/gaps and larger-area application remain later work:
choose surveyed domains, gap radius, spatial-block size and appropriate per-domain
CRSs. Measure runtime and memory before making continental-scale claims.

## Deferred improvements

| ID | Work | Current boundary |
| --- | --- | --- |
| GEO-2 | Near-duplicate resolution, stitching, automatic reference joins and clustering | Exact duplicate checks do not solve near-duplicates; PCA is not clustering |
| POLY-2 | Large-scene/windowed FBP inference and cross-chip ownership | Export vectorization seams are checked; inference equivalence is not |
| REF-2 | Denmark annotation provenance | Investigate supplied-ID grouping before treating it as validated individual-field identity; no automatic repair |
| VAL-1 | Make expanded training-validation metrics opt-in | Proposed, not implemented: the trainer currently computes the expanded suite. Preserve original precision/recall/F1 defaults if changed; check distributed pooling and checkpoint monitors |

## Completed foundations

The initial metric suite, method comparisons, identity follow-ups and existing
complementarity analysis are complete for their original scope. Classified chip
outlines and schema-3 chip export validation are also complete. Their completion
does not close REF-1 or imply that a real larger-area geometry study has run.
