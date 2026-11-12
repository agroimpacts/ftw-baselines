# Current status: instance metrics and map descriptors

Updated **2026-11-12**. Start with the [documentation index](README.md).

## What is available

| Work | Status |
| --- | --- |
| Existing reference metrics, shared scoring and offline artifacts | Implemented; [rules](instance-metrics-contract.md) and [usage](offline-instance-evaluation.md) |
| Method and object-identity comparisons | Initial studies complete; [reports](research/README.md) |
| Metric complementarity | Existing eight-score analysis complete; boundary-distance extension still outstanding |
| Optional FTW_2E 0.2.0 polygon export | Implemented and validated on one real chip; defaults unchanged |
| Final-polygon descriptors | Schema 3.0 implemented; [definitions](polygon-export-and-descriptors.md) |
| Larger-area geometry tools | Implemented and tested on synthetic data, not yet applied to a real regional study |

The reference-metric research is **not finished**. Completed results establish
the starting point for new work; they are not an instruction to skip further
metric investigations.

## What has been checked on real geometry

Germany chip `g1_00003_16`: 13 predicted polygons, two holes, four export formats,
valid geometry, matching read-back descriptors and no uncleaned raster round-trip
differences. The current artifact directory is
`~/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany/polygon-validation/g1_00003_16_schema3/`.
See [validation details](research/polygon-export-validation.md).

There is no real larger-area descriptor dataset, regional summary, descriptor
correlation/PCA study or spatial-bootstrap finding yet. Software test counts are
not empirical study sample sizes.

## Outstanding work

1. **Boundary distance:** test object-boundary Chamfer distance using standard
   matching and investigate best-IoU pairing; then assess complementarity with
   existing scores. No definition is selected or implemented yet.
2. **Map-descriptor study design:** choose data, surveyed regions, a suitable common
   metric CRS, field/fragment interpretation, duplicate/edge policy, gap radius
   and spatial-block size before a real larger-area run.

The [to-do list](instance-metrics-backlog.md) gives the details and deferred ideas.
These are separate outstanding tracks, not a commitment to run either study as
part of documentation maintenance.

## Important limits

- Vectorization-window checks do not validate windowed FBP inference, cross-chip
  reconstruction, global seam ownership or continental runtime/memory use.
- Regional exact geometry/quantiles have an explicit region-plus-halo field cap.
  Spearman, PCA and block intervals use bounded samples above the sample cap;
  only streamed Pearson uses every finite pair.
- Near-duplicate resolution, automatic stitching/repair and clustering are not
  implemented. Geometry measures do not change field boundaries.
- Denmark's supplied-ID grouping needs provenance review. Presence-only reference
  restrictions remain in force.

Documentation, tools and tests are now grouped by supported workflows, active
research and historical experiments. Existing analysis artifacts and scoring
defaults were not changed. No PR, branch split or repository migration is being
prepared; this remains work on `feat/instance-metrics`.
