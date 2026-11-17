# Current status: instance metrics and map descriptors

Updated **2026-11-15**. Start with the [documentation index](README.md).

## What is available

| Work | Status |
| --- | --- |
| Existing reference metrics, shared scoring and offline artifacts | Implemented; [rules](instance-metrics-contract.md) and [usage](offline-instance-evaluation.md) |
| Method and object-identity comparisons | Initial studies complete; [reports](research/README.md) |
| Metric complementarity | Existing eight-score analysis complete; boundary-distance extension still outstanding |
| Optional FTW_2E 0.2.0 polygon export | Implemented and validated on one real chip; defaults unchanged |
| Final-polygon descriptors | Schema 3.0 implemented; [definitions](polygon-export-and-descriptors.md) |
| Regional landscape profiles | Complete for all 21 primary FTW windows; all shape descriptors, coverage/density, orientation and edge-guarded spacing |
| Lubushi–Bahia illustration | Complete for 5,559 Mapping Africa Zambia fields and 69 FTW diagnostic fields; separate from the primary pilot |
| Shape-assisted triage / narrow-neck repair pilot | Four-outcome California demo plus targeted split-set/union previews; 17 user assessments; no exclusions or repairs applied |
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

The published-map pilot now has real field-level descriptors and regional
landscape profiles. There is still no spatial-bootstrap finding. Initial full-table
descriptor correlations/PCA are available in the
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
59,350 primary records; 66 geometry tests pass. The user has reviewed descriptor
disagreements; a written interpretation, spatial sensitivity and practical
feature-selection findings remain outstanding; see
[the initial analysis](research/descriptor-complementarity.md).
An interactive disagreement-review index now links 105 pair examples (93 unique
fields) to exact-ID zoom/highlights in descriptor maps, under the sibling
`disagreement-review-2024/index.html`. The user subsequently reviewed these
examples and described contrasts among circularity, rectangularity, solidity and
hull-perimeter ratio. Their written synthesis and accuracy validation remain open.

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

Regional profiles now summarize all 21 primary windows and 59,350 assigned fields
in `regional-landscape-2024-v2/` under the pilot artifact root. Tables include every
shape descriptor, size/supporting dimensions, holes, narrow-neck prevalence,
orientation, counts/density, clipped union coverage and overlaps. The figures
compare window quantiles and area-weighted means and link to existing descriptor
maps. The empty Rwanda window is retained and the diagnostic is excluded.
Positive spacing compares 50/100/250 m search radii, retaining only fields with
complete within-window search context because the extracts have no exterior halo.
One unassigned context polygon becomes self-touching after projection; it is
retained without repair and has valid clipped coverage geometry. All 217 output
hashes and 84 recorded input hashes verify; 73 geometry/research tests pass.
Independent checks reproduce 480 descriptor summaries, 42 coverage values and
60 sampled gaps. See [findings and limitations](research/regional-landscape-profiles.md).

The user approved the exact Lubushi window. The separate Zambia–Bahia illustration
is complete under `~/working/ftw/metrics/landscape-illustrations/lubushi-bahia-2024-v3/`.
Lubushi's median field area is 0.157 ha versus 35.165 ha in Bahia (about 225×).
Median circularities are 0.748 and 0.435. Bahia's eight largest polygons have
nearly circular hulls, but interior holes and indentations substantially increase
perimeter in several cases. Additional boundary-component diagnostics and outline
examples explain this without redefining circularity or filtering the population.
All 46 comparison output hashes and nine input hashes verify; all original Bahia
descriptors and the 217 primary regional artifact hashes remain unchanged.
There are now 82 passing geometry/research tests. See the
[illustration report](research/lubushi-bahia-landscape-illustration.md).

## Outstanding work

1. **Boundary distance:** test object-boundary Chamfer distance using standard
   matching and investigate best-IoU pairing; then assess complementarity with
   existing scores. No definition is selected or implemented yet.
2. **Published-map descriptor pilot:** the draw, polygon retrieval, field
   descriptors/maps, initial correlations/PCA and regional profiles are complete.
   Write up user-reviewed disagreements, investigate spatial uncertainty/window
   scale/preprocessing sensitivity and assess practical complementarity. Regional
   spacing-radius sensitivity is available; it does not establish spatial-block
   uncertainty or continental performance. Initial findings remain exploratory.
3. **Cross-source landscape interpretation:** the approved Lubushi–Bahia
   illustration is complete. Detailed Mapping Africa processing thresholds and
   local completeness remain provenance limits; broader landscape/system
   generalization requires additional sampling and evidence.
4. **Shape-assisted triage / narrow-neck repair-agent pilot:** user-approved extension
   now has a proposal-only demo in `california_61_424`, presenting exclusion, repair,
   retain and abstention routes for 419 unchanged fields, with review-label export
   and independent diagnostic cut alternatives. Seventeen user assessments now feed
   a separate targeted review: coordinated split sets for two priority parents,
   initial abstention on a three-field case lacking three erosion cores, and an exact
   fragment union whose multipart identity remains unresolved. Boundary completion
   is deferred. A later user-annotated screenshot now supports a separate, approximate
   three-child preview for `8617`; exact cut placement still needs review. The user
   preferred the other two splits and rejected the fragment union for now.
   No correction/apply stage exists. Review exact proposals before
   any versioned exclusions or child polygons
   with lineage/recomputed properties. Original maps remain unchanged. See the
   [demo report and validation limits](research/shape-triage-pilot.md).
5. **Geometry–segmentation performance:** later reference-based research on shape
   and detection/delineation outcomes; provenance and matching checks come first.
6. **Landscape synthesis/queries:** develop interpretable combinations of shape
   measures; validated error-risk queries depend on the later performance study.

The [to-do list](instance-metrics-backlog.md) gives the details and deferred ideas.
The backlog records the agreed staging and remaining work; it does not authorize
running deferred studies as part of documentation maintenance.

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
