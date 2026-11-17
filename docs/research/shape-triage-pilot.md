# Four-outcome shape-assisted polygon triage

Initial proposal-only demo: **2026-11-15**. This broadens GEO-3 with the user's
approval: eventual automated correction needs to distinguish false field
detections from joined valid fields, genuine single fields and uncertain cases.
The FTW regional analysis and separate Lubushi–Bahia illustration are complete
and are not rerun or changed by this experiment.

## Demo window and artifacts

The user accepted the proposed `california_61_424` window for this demo: a 10 km
square in EPSG:32610, bounds `[610000, 4240000, 620000, 4250000]`, centered at
38.34577° N, 121.68399° W. Inputs are frozen published 2024 FTW polygons and their
schema-3 descriptors. There are 419 assigned fields, 20 narrow-neck flags and
469 complete window-intersecting source polygons. The latter provide context,
not additional assigned observations; they do **not** constitute an exterior halo.

Open:

`~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/triage-review-2024-v1/index.html`

| Proposed route | Count | Interpretation |
| --- | ---: | --- |
| Exclude | 3 | Thin elongated shapes worth reviewing as possible non-field detections |
| Repair | 6 | User-identified joined fields or persistent two-lobe screens with geometric cut alternatives |
| Retain | 345 | No selected screening rule triggered; not confirmed valid fields |
| Abstain | 65 | Incomplete context, complex/scale-sensitive geometry, or rejected neck interpretations with unresolved field validity |

All four are **candidate review routes**, not verified outcomes, probabilities,
accuracy estimates or approved changes. No imagery was independently reviewed by
the generating agent. The Esri imagery layer is for human interpretation; dates
vary and may not match the 2024 release. Loading the page requires internet access
for Leaflet and imagery. It also works as a static file without a local server.

## Screening and cut proposals

- The existing `narrow_neck` descriptor remains unchanged: inward erosion by
  10% of equivalent-circle radius, retaining components at least 2% of parent area.
- Additional erosion diagnostics use 2.5/5/7.5/10/12.5/15% of that radius. These
  show component counts and eroded area fractions, not reconstructed boundaries.
  Counts across distances do not establish correspondence of persistent lobes.
- The **exploratory**, uncalibrated exclusion screen uses minimum-rectangle width
  at most 25 m, elongation at least 8 and circularity below 0.25. These are demo
  thresholds, not minimum valid-field dimensions. They were chosen while inspecting
  this window, so no out-of-sample performance claim is justified. The candidates
  are `10SFH_0_0-9296`, `10SFH_0_0-8535` and `10SFH_0_0-8699`. All may be genuine
  narrow agricultural fields; imagery evidence is required before exclusion.
- Shape-only repair routing requires a saved neck flag, exactly two retained
  lobes at at least three distances, no distance with more than two retained lobes,
  and at least one geometrically validated cut. This deliberately remains an
  imperfect rule to assess against reviewed labels, not a semantic merge detector.
- A 100 m context guard checks distance from the full parent to the extraction
  boundary. Ordinary incomplete-context cases abstain. Source seam provenance
  remains unknown; exterior imagery does not supply missing polygon neighbors.
- Short cut searches use local chords perpendicular to nearest-point connectors
  between eroded cores. Only chords that independently partition the **original**
  polygon into two valid children, each at least 5% of parent area, are retained.
  The two diagnostic cores must remain intact in different children. Preview union,
  area and sibling-overlap checks use `max(1e-6 m², parent area × 1e-10)` tolerance.
  The splitter extends chord endpoints by 1 micrometre to handle floating-point
  intersection errors; shared-boundary agreement is checked to 0.00001 m. No
  outward reconstruction of eroded boundaries, polygon simplification or geometry
  cleanup is performed. Tiny buffered copies are used only for tolerance checks.
- Up to three alternative cuts per flagged field are shown, including diagnostic
  alternatives for non-repair routes. The 49 alternatives are independent previews,
  **not** an approved or jointly validated multi-cut recipe. No child dataset is
  written. Geometric conservation does not demonstrate correct placement.

The user identified `10SFH_0_0-8520` (44.212 ha) and `10SFH_0_0-9043` (25.968 ha)
as joined valid fields. Those review seeds remain priority **repair candidates**.
Neither receives a validated single-cut proposal from the current bounded chord
search; manual cut placement or a better multi-connection search remains necessary.
The former also lies only 42.5 m from the window edge and needs exterior polygon
context before correction. An explicit lack of a cut is preferable to forcing an
incorrect one.

The other four previously discussed examples (`9364`, `8820`, `9175`, `9369`, all
with prefix `10SFH_0_0-`) carry conversation evidence rejecting the neck-screen
interpretation. They **do not** receive false-field labels: a false neck flag is
not proof of a false field detection. They route to abstention until field validity
is separately established. Conversation evidence is recorded, not presented as
independent image-based ground truth.

## Review and approval boundary

The page filters all four routes, highlights complete parent outlines, shows
saved neighboring polygons, erosion diagnostics and cut alternatives. Enter a
reviewer name, select a review outcome, optionally choose one exact cut alternative,
and record reasoning/imagery provenance. **Record before navigating, then export
the labels before closing the tab**; this demo has no server or permanent browser
storage. A repair label may have no selected cut when placement remains unresolved.

Exports include the run ID, collection-qualified parent identity, original geometry
SHA-256 and selected proposal ID where applicable. All exports explicitly set
`application_authorized: false`. There is no import/apply command. Labels are not
approvals to alter the map. Review changes to routing and exact cut/exclusion
approval remain distinct steps.

A future correction stage must require explicit approval of exact exclusions and
cuts; write a separate versioned derivative; preserve source attributes only when
applicable; label inherited scores; assign reproducible children with parent lineage;
recompute child descriptors; and audit validity, union/area conservation and
neighbor overlaps. Original maps, descriptor tables and regional profiles remain
unchanged. Before/after regional sensitivity is later work.

## Toward automated correction

This is a bounded demo, not a billion-field processing implementation. Retain
reviewer labels, rejection reasons and abstentions for future training and rule
evaluation, keeping user-seeded cases separate from independent evaluation.
Evaluation needs valid narrow-field controls and false detections beyond the neck
screen, candidate-selection accounting, independent geographic/size strata,
exclusion precision, repair acceptance/placement and abstention/coverage rates.
Tune thresholds separately from evaluation. Eventually automate only sufficiently
validated cases, with uncertain fields unchanged and ongoing sampled audits.
Improved descriptors alone cannot demonstrate improved mapping accuracy.

## Reproduction and validation

```sh
uv run --extra geometry python -m research.geometry.triage_descriptor_pilot \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1 \
  --out_dir ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/triage-review-2024-v2
```

Use a new sibling output directory. The command verifies retrieval and descriptor
input hashes and matching parent identities/geometries, rechecks inputs after
generation, snapshots the source/template, and hashes all outputs in `complete.json`.
Exact metric cut geometry and parent fingerprints are in `cut-proposals.json`;
WGS84 GeoJSON is for display. Source ID/collection qualification is preserved.
All eight output hashes and eight recorded input hashes verify. The 217 primary
regional outputs and 46 Lubushi–Bahia illustration outputs also verify unchanged,
alongside their 84 and nine recorded input hashes respectively.
All 49 serialized metric cut alternatives were independently revalidated against
the original projected parent polygons, including area conservation, original
geometry fingerprints and pending/non-applied status.

Six new Python tests cover controlled shapes, multi-connection abstention, routing,
identity/geometry guards, non-destructive/reproducible runs and hash validation.
All 42 geometry-research tests pass in the available Python environment. A wider
geometry/research run recorded 70 passes, 15 dependency skips and three environment
failures: isolated `ftw_geometry` is not installed, and two CLI tests lack `xarray`.
These failures were not changed or hidden. Ruff lint passes for the new Python files.

The macOS JavaScriptCore smoke test exercises four filters, reviewer gating, exact
proposal selection and provenance-preserving label exports with application disabled:

```sh
osascript -l JavaScript tests/research/geometry/triage_review_smoke.js \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/triage-review-2024-v1/index.html
```

This uses mock DOM/map objects; it does not establish rendered-browser layout,
imagery availability or imagery accuracy.

## Targeted second review: split sets and fragment union

**Screenshot-guided follow-up:** The user preferred the `8520` and `9043` split
previews, rejected the fragment union for now, and supplied two blue screenshot
guides for `8617`. A separate preview is now available at
`~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/guided-8617-review-2024-v1/index.html`.
It partitions the original into three valid polygons of 14.509, 10.524 and
2.742 ha. Total coordinated cut length is 324.167 m, including the broad middle
join. Union error is zero and area residual is below 0.000001 m²; overlap changes
against 468 saved neighbors are zero. No changes are applied.

`research/geometry/guided_8617_preview.py` aligns the orange outline's approximate
pixel bounds with the original north-up Web Mercator bounds, fits the blue guide
pixels, and uses three interior regions away from the guides as graph-cut
terminals. This is **approximate screenshot registration**, not precise digitizing:
assume about five pixels alignment uncertainty, and inspect the actual cyan cuts
before approval. The terminal exclusion band is 30 Web Mercator metres; accepted
cuts must stay within 30 metric metres of the guides. All original triangle cells
are retained; no buffering is used to reconstruct field boundaries. This manually
guided method does not establish automatic three-field detection. Pillow is needed
for screenshot reading. Registration settings, source hashes, full metric preview
WKT and source snapshots are preserved in the new output directory. The original
screenshot, exports, maps and earlier previews remain unchanged.

The user exported 17 assessments in
`triage-review-2024-v1/triage-review-3faf12f5092a3d146a6c26ad.json`:
eight exclusions, seven repairs and two retentions. All run IDs, parent fingerprints
and original routes were checked. These are selected development examples, not
an independent accuracy sample. The user separately corrected the merge partner
for `10SFH_0_0-8571` to **`10SFH_0_0-8581`**. The original review export is unchanged;
that clarification is recorded in a separate interpretation artifact.

The user authorized targeted **previews**, not application. Open:

`~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/targeted-repair-review-2024-v1/index.html`

| Case (all IDs prefixed `10SFH_0_0-`) | Result |
| --- | --- |
| `8520` | Two coordinated cut segments, 7.5 m total; two preview children of approximately 29.910 and 14.302 ha |
| `9043` | Three coordinated cut segments, 10.0 m total; three preview children of approximately 13.343, 8.545 and 4.080 ha |
| `8617` | Abstain: review identifies three fields, but the retained erosion cores never resolve three; no third boundary is invented |
| `8571` + `8581` | Exact union preview, 22.442 ha, remaining a valid two-component MultiPolygon; no added area |

### Method and interpretation

The new split search uses constrained Delaunay triangles **inside the original
polygon**, with shared-edge lengths as dual-graph cut capacities. Eroded lobes
identify terminal cores only; they are not buffered back outward to reconstruct
field boundaries. Minimum cuts can sever several narrow connecting paths together,
which the first demo's single-chord search could not do. Triangle edges constrain
possible placements, so these are geometry-derived suggestions, not exact observed
management boundaries. Capacities are quantized to centimetres; output coordinates
are not rounded to that scale. The command requires Shapely >=2.1 and GEOS >=3.10;
this does not change the general geometry package's older supported descriptor API.

For more than two cores, combined isolating cuts are a heuristic, not a globally
optimal multiway cut. Their union can strand tiny coreless triangle components.
Only components at most 0.1% of parent area may reconnect to a core-bearing neighbor
through their longest shared boundary; all their area is retained. This reconnects
a 6.25 m² coreless cell in `9043`. Large orphan pieces, torn cores, unsupported field
counts, invalid geometry and cuts totaling over 100 m cause abstention. Each preview
child must retain at least 2% of parent area. Geometry checks use the first demo's
area tolerance, `max(1e-6 m², parent area × 1e-10)`.

The exact union of `8571` and `8581` touches at points, with zero shared boundary
length and zero positive-area overlap. It remains **multipart**, rather than
silently filling intervening land. This blocks a resolved single-Polygon repair:
human review must determine whether multipart field identity is appropriate or
whether image-supported gap/boundary completion is needed. No single-field schema-3
descriptor is reported for that MultiPolygon. Split-child descriptors are recomputed
as preview diagnostics; source prediction scores are not copied to them.

Original parent geometry fingerprints, full metric preview WKT, cut sets and
validation results are in `proposals.json`; display-only WGS84 geometry is in
`preview-geometries.geojson`. All outputs are labeled preview/pending/not applied,
not a repaired production dataset. Eight exclusion labels are carried forward
without application. Boundary-completion cases `9142`, `9100` and `8713` remain
deferred pending image-supported methods; no blanket convex-hull expansion is used.

### Validation and what to review next

- All three preview results conserve the original parent union; split siblings
  have zero positive-area overlap and their holes/exterior boundaries are retained.
- Independent checks reloaded the metric WKT, verified source fingerprints and
  conservation, and recomputed overlap changes against all saved non-parent
  neighbors: 468 for each split and 467 for the union. Maximum overlap change is
  **0 m²** in each case. This is a saved-context audit, not a complete exterior audit.
- `8520` still lacks a complete 100 m polygon halo because it is only 42.5 m from
  the extraction edge. The preview is available, but correction remains blocked
  pending context review. No new halo download was performed.
- All eight targeted output hashes and 11 recorded input hashes verify. The first
  triage demo and primary regional artifacts also verify unchanged, as does the
  original user review export. Nine new Python tests include a fresh-output,
  original-preservation and reproducibility integration test; all 51 research
  geometry tests pass. Ruff lint passes for the new Python code.
- A JavaScriptCore smoke test exercises all four cases, exact proposal selection,
  abstention display, reviewer gating and exports. It uses mocked DOM/maps, not a
  rendered-browser or imagery-accuracy assessment.

In the page, compare the orange original outlines with colored preview children;
use **Zoom to cut set** to inspect all coordinated connections. Record whether
each exact preview is preferred, rejected or needs changes, then export preferences.
For `8617`, record where imagery supports the missing separation. For the union,
check the multipart interpretation. Exports remain `application_authorized: false`:
there is no application command, and approval of actual corrections is a separate
future step.

Reproduce into another fresh sibling directory:

```sh
uv run --extra geometry python -m research.geometry.review_triage_repairs \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1 \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/triage-review-2024-v1/triage-review-3faf12f5092a3d146a6c26ad.json \
  --out_dir ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/targeted-repair-review-2024-v2

osascript -l JavaScript tests/research/geometry/repair_review_smoke.js \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/targeted-repair-review-2024-v1/index.html
```
