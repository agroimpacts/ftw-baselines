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
spatial uncertainty, written disagreement interpretation and practical feature selection
remain outstanding.

Geometry-preserving polygon retrieval and outline-map generation are complete
for all 22 windows, and the user reviewed the maps. Rwanda's missing predictions
were visually assessed as false negatives, without a numerical recall estimate.
All 28 MultiPolygon-typed records have exactly one component; unwrap the container
without splitting observations; this normalization and descriptor generation/maps
are now complete, along with initial availability/distributions, full-table
within-zone/size-stratified associations and selected-feature PCA. The user has
reviewed disagreement examples and described contrasts among circularity,
rectangularity, solidity and hull-perimeter ratio. A written synthesis, spatial
sensitivity and practical complementarity assessment remain, acknowledging
algebraic dependencies.
Pilot infrastructure is isolated in `research/geometry/`; reusable descriptor
functions stay model-independent in the library for eventual CLI integration.
Keep handpicked illustrations separate from the statistical sample. Resolve
multipart/parent semantics and seam/duplicate policies before descriptor generation.
Window selection is not a completed descriptor study.

### Current phase: regional landscape profiles

**Initial profiles complete.** See the [regional report](research/regional-landscape-profiles.md)
and canonical `regional-landscape-2024-v2/` artifacts. All 21 windows and 59,350
assigned fields are included, with plots, full descriptor summaries and guarded
50/100/250 m spacing comparisons. The methods below record the agreed scope;
alternative window scales and spatial uncertainty remain future sensitivity work.

Summarize the **21 primary FTW pilot windows**, one regional observation per 10 km
window. Keep the Bahia diagnostic separate and retain the empty Rwanda window.
The purpose is to demonstrate how combinations of geometry measures summarize
and help interpret mapped field characteristics. Include all shape descriptors,
size and supporting dimensions, holes, narrow-neck prevalence, axial orientation,
counts/density, mapped coverage/overlap and positive inter-field spacing. Report
distributions/quantiles and both field-count- and area-weighted summaries.

Use zone-specific metric CRSs and preserve complete field boundaries. Coverage
uses clipped intersections; whole-field descriptors use representative-point
assignment. Existing extracts have no halo: guard spacing against incomplete
edge context, report radius censoring and compare 50/100/250 m search radii.
Summaries describe detected mapped fields; Rwanda missing detections especially
limit density, coverage and spacing interpretations. Compare windows descriptively;
three windows per zone do not support strong within-zone inference. Spatial-block
uncertainty, alternative window scales and continental performance remain open.

### Mapping Africa Zambia and Bahia assessment (initial illustration complete)

The user advanced this extension ahead of the repair-agent pilot, selected
the area south of **Lubushi Mission** and the existing **Bahia pivot diagnostic**,
and approved the exact 10 km Zambia review window. Common descriptors and regional
profiles are complete for 5,559 Zambia and 69 Bahia assigned fields, under
`~/working/ftw/metrics/landscape-illustrations/lubushi-bahia-2024-v3/`.
The size contrast is strong (median 0.157 versus 35.165 ha), while circularity
differs (median 0.748 versus 0.435). Boundary diagnostics explain how near-circular
pivot hulls can coexist with low full-boundary circularity. All populations and
original maps remain unchanged. See the
[assessment notes](research/lubushi-bahia-landscape-illustration.md).

The comparison includes joint distributions, all regional descriptors and maps,
with cross-source method/completeness limits. Both examples remain outside the
21-window primary FTW population. Additional sampling and detailed source-method
verification would be needed for broader claims. No representative-system claim
or segmentation-accuracy assessment is implied.

## GEO-3: Shape-assisted triage and narrow-neck repair-agent pilot

**User-approved scope extension, 2026-11-15.** Landscape illustrations are complete.
The initial proposal-only demo in `california_61_424` presents four outcomes:
possible false-field **exclusion**, joined-valid-field **repair**, valid-single-field
**retention**, and uncertain-case **abstention**. Shape provides screening evidence,
not a definitive field-validity label. A false narrow-neck flag does not establish
a false field detection. The eventual goal is validated automated correction at
large scale; this demo requires review and does not apply any corrections.
See [demo findings, thresholds and approval boundaries](research/shape-triage-pilot.md).

The demo contains 419 unchanged assigned fields: 3 exclusion, 6 repair, 345 retain
and 65 abstention routes, plus independent diagnostic cut alternatives. These are
not accuracy findings. Seventeen user assessments identified eight exclusions,
seven repairs and two retentions, with split, fragment-merge and boundary-completion
repair subtypes. A separate targeted review now proposes coordinated split sets for
`10SFH_0_0-8520` and `10SFH_0_0-9043`; abstains on the unsupported three-field
partition of `10SFH_0_0-8617`; and previews the exact, still-multipart union of
`10SFH_0_0-8571` with user-corrected partner `10SFH_0_0-8581`. No changes are applied.
Next, review exact split placement and multipart field identity, add exterior
context as needed, and independently assess rejection/acceptance behavior before
building any application/automation stage. Boundary completion remains deferred;
convex hull replacement is not an adopted repair rule.

Start in a user-defined window, retrieve complete polygons and context, and
identify candidate constrictions. The current erosion-based `narrow_neck` flag
screens candidates; it does not establish an erroneous merge. Explore erosion
across distances to identify substantial persistent lobes, locate the neck and
propose a short cross-neck cut of the **original** polygon. Do not reconstruct
boundaries by buffering eroded lobes back outward.

Initially require human approval for exact exclusions and cuts; allow abstention for genuine narrow fields,
ambiguous imagery, tiny lobes, multiple necks and uncertain cut locations. Test
controlled shapes and review real examples before considering automatic approval.
Evaluate proposal acceptance, cut placement and false proposals on genuine narrow
fields; improved descriptor values alone are not proof of a correct repair.

Write a separate versioned repaired dataset, preserving original maps. Give child
fields reproducible new IDs and parent lineage, recompute descriptors, retain only
applicable source attributes, label inherited prediction scores, and record
algorithm/settings/approval and before/after geometry. Check validity, union/area
conservation and new overlaps. Compare regional summaries before/after repairs as
a later sensitivity analysis. No repair implementation is included in GEO-1.

## GEO-4: Geometry and segmentation performance (later research)

Investigate which reference-field characteristics are associated with missed
detections, splits/merges and delineation quality. Use reference geometry to include
missed fields; analyzing predicted shape as an error-screening signal is a separate
question. Establish provenance, year alignment, field meaning, training overlap and
annotation completeness before evaluation. Keep prediction/reference descriptors
and explicit match/outcome tables separate, and account for field area and geography.
Compare original descriptors and cautiously interpreted PCA scores; component names
are provisional, not established independent physical factors. Never replicate chip
scores across fields as independent observations. Chamfer (REF-1) can add a boundary
outcome once defined; existing outcomes need not wait for it. No reference evaluation
is included in the current regional phase.

## Deferred improvements

### GEO-5: Interpretable landscape synthesis and queries

Build on the regional profiles to support intuitive descriptions and queries:
where fields are squarest, most elongated, most geometrically complex, or likely
to have particular segmentation errors. Define interpretable combinations before
adopting thresholds or a single composite score. Rectangularity alone does not
establish squareness; elongation and rectangle filling should be considered
together. Complexity may involve concavity, excess perimeter and holes, and must
distinguish those from simple elongation and resolution effects. Keep distributions
and examples accessible behind any label. The Lubushi–Bahia results also motivate
separating overall envelope shape from holes and excess boundary length; the exact
circularity/hull/solidity decomposition is available as an interpretive starting
point. Segmentation-risk/error-type queries
require independently reviewed/reference outcomes and validation under GEO-4;
geometry alone does not identify the true error or its probability. This is
further work, not part of the initial Zambia–Bahia illustration.

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
