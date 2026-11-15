# Current status: instance metrics and map descriptors

Updated **2026-11-14**. Start with the [documentation index](README.md).

## What is available

| Work | Status |
| --- | --- |
| Existing reference metrics, shared scoring and offline artifacts | Implemented; [rules](instance-metrics-contract.md) and [usage](offline-instance-evaluation.md) |
| Method and object-identity comparisons | Initial studies complete; [reports](research/README.md) |
| Metric complementarity | Existing eight-score analysis complete; boundary-distance extension still outstanding |
| Optional FTW_2E 0.2.0 polygon export | Implemented and validated on one real chip; defaults unchanged |
| Final-polygon descriptors | Schema 3.0 implemented; [definitions](polygon-export-and-descriptors.md) |
| Larger-area geometry tools | Implemented and tested on synthetic data, not yet applied to a real regional study |
| Published-map descriptor pilot | 21 primary windows plus 42 reserves selected and validated; [specification and selected IDs](descriptor-pilot.md) |

The reference-metric research is **not finished**. Completed results establish
the starting point for new work; they are not an instruction to skip further
metric investigations.

## What has been checked on real geometry

Germany chip `g1_00003_16`: 13 predicted polygons, two holes, four export formats,
valid geometry, matching read-back descriptors and no uncleaned raster round-trip
differences. The current artifact directory is
`~/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/germany/polygon-validation/g1_00003_16_schema3/`.
See [validation details](research/polygon-export-validation.md).

The published-map pilot now has real field-level descriptors. There is still no
regional-summary study or spatial-bootstrap finding. Initial full-table
descriptor correlations/PCA are now available in the
[pilot report](research/descriptor-complementarity.md). Software test counts are
not empirical study sample sizes.

Published-map pilot area selection is complete: seven zones, three 10 km primary
windows per zone and six ordered reserves per zone, using 2024 processing coverage
and a separate WorldCover 2021 agricultural-presence screen. Native crop chips,
input snapshots, code and hashes are under
`~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/selection-2024-administrative/`.
This validates sampling eligibility, **not field polygons or prediction accuracy**.
A separate user-selected Bahia pivot diagnostic is saved 35 km west of
`bahia_45_871`; it does not replace a primary window or enter statistical estimates.
See [the pilot notes](descriptor-pilot.md#user-selected-bahia-pivot-diagnostic).
Polygon retrieval and interactive outline-map generation are complete for all
22 windows, under the sibling `polygon-review-2024/` directory (`index.html`).
Primary extracts contain 60,769 intersecting records, of which 59,350 have their
representative point inside the window; 28 use MultiPolygon storage and none are
invalid. All 28 contain exactly one component: none is genuinely multipart.
The diagnostic contains 91 intersecting records (69 assigned), none multipart
or invalid. These are summed extract records, not yet cross-extract deduplicated
field counts. All per-window artifact hashes were verified. The first Rwanda
window returned an empty published-vector query from both neighboring zone
assets. The user reviewed the maps and attributes the empty window to false
negatives; the other Rwanda windows also miss many fields. This is qualitative
review, not measured recall. Preserve all windows and report mapped-field
descriptors as conditional on detection. Schema-3 descriptors and colored maps
are complete for 59,350 assigned primary records and 69 separate diagnostic
records, under the sibling `descriptor-review-2024/` directory (`index.html`).
All 28 single-component containers were unwrapped without boundary/ID changes;
the empty Rwanda window remains explicit. No primary collection-qualified ID is
duplicated. Artifact hashes and sampled remeasurements were validated; 62 geometry
tests passed at generation. Initial descriptive correlations/PCA now use all
59,350 primary records; 66 geometry tests pass. Descriptor-disagreement visual
review, spatial sensitivity and practical feature-selection findings remain
outstanding; see [the initial analysis](research/descriptor-complementarity.md).
An interactive disagreement-review index now links 105 pair examples (93 unique
fields) to exact-ID zoom/highlights in descriptor maps, under the sibling
`disagreement-review-2024/index.html`. This enables review; it does not mean the
examples have been interpreted or validated.

Study-specific sampling, configuration and pilot commands now live in
`research/geometry/`, with tests in `tests/research/geometry/`. No pilot code remains
in the installed postprocessing package. Reusable descriptors and generic geometry
tools remain in their original library/workflow locations. The relocation passes
67 combined geometry/research tests and preserves historical artifacts/snapshots.

Reusable geometry is now independently packaged under
`research/geometry/ftw_geometry/{core,io}/`. Research/download utilities no longer
import FTW modules. Old descriptor imports remain compatibility adapters; the
FBP extra explicitly includes the local geometry package so existing sidecars
and CLI defaults are preserved. Training metrics and both polygonizers are
unchanged. The archived pre-extraction checkout passes 67 tests; current code
passes 69, including package-isolation/compatibility checks. All 546 frozen
artifact hashes verify unchanged. See [reproduction safeguards](geometry-extraction-and-reproduction.md).

## Outstanding work

1. **Boundary distance:** test object-boundary Chamfer distance using standard
   matching and investigate best-IoU pairing; then assess complementarity with
   existing scores. No definition is selected or implemented yet.
2. **Published-map descriptor pilot:** the seven-zone 2024 draw is complete.
   Published polygons are retrieved and user-reviewed; assigned-field descriptors
    and colored maps are generated; initial correlations/PCA are complete. Review
    disagreement examples, investigate spatial sensitivity and assess practical
    complementarity. See [the pilot](descriptor-pilot.md).
   Future reference evaluation needs separate provenance/matching checks. Regional
   gap/density studies, spatial-block scale and larger-area application remain
    additional work. Initial correlations are exploratory, not global findings.

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
