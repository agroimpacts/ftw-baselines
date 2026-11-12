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

**Outstanding study design and application.** Select production polygons,
surveyed regions, common metric CRS, whole-field versus tile-fragment meaning,
duplicate/edge policies, gap radius and spatial-block size. The tools exist;
no dataset or scientifically appropriate scale has been chosen. Measure runtime
and memory before making continental-scale claims.

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
