# Regional landscape profiles of the FTW pilot

Run **2026-11-14**. Regional profiles are complete for all 21 primary windows and
59,350 assigned fields. Canonical artifacts:
`~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/regional-landscape-2024-v2/`.
Open `index.html` for the comparison figures and links to the existing field maps.

## Purpose and population

This study examines how geometry measures can summarize and help interpret
mapped field characteristics across landscapes. The observations are the **21
primary 10 km windows**, three in each of seven pilot zones. The user-selected
Bahia pivot diagnostic is excluded. The empty Rwanda window remains in all
regional tables.

The inputs are the frozen published 2024 polygon extracts and schema-3 assigned
field descriptors. No inference, new filtering, boundary repair or reference
evaluation is involved. Field-level correlations/PCA are reported separately in
[descriptor complementarity](descriptor-complementarity.md).

## Measurements

Each window uses its original suitable metric CRS. Whole polygons enter counts
and descriptor distributions when their representative point falls inside the
window, with assignment checked against the frozen descriptor population.
Coverage uses clipped intersections of **all** retrieved polygons, including
those assigned outside the window. Crossing polygons retain their complete
boundaries for shape measurement.

The regional table includes:

- Every numeric/boolean descriptor except axial orientation: finite counts,
  means, area-weighted means and 5th, 25th, 50th, 75th and 95th percentiles.
  This includes circularity, elongation, solidity, rectangularity, convex-hull
  index, area, perimeter, rectangle/hull dimensions, holes and narrow-neck flags.
- The proportion of fields with holes, the fraction of field area in fields
  with holes or narrow necks, and total hole area divided by total enclosed area.
  The latter is distinct from the area-weighted mean of field hole fractions.
- Axial mean directions, doubled-angle resultant lengths (alignment),
  area-weighted counterparts and orientation ambiguity. Direction is measured
  from projected +x; it is not a true-north bearing. Alignment near zero means
  the regional mean direction is uninformative and can also reflect competing
  orientations; inspect the 15° bins.
- Field counts/density, union coverage, summed clipped area, overlap excess and
  overlapping polygon pairs. Coverage uses total window area, not cropped area.
- Positive inter-field spacing at 50, 100 and 250 m search radii, with explicit
  eligibility and censoring counts.

### Spacing and boundaries

The saved extracts include only window-intersecting polygons. They do not supply
a complete exterior halo. Main spacing summaries therefore require each field
to lie entirely more than the search radius inside the window. The same window
can have different eligible populations at different radii; changes combine
radius and eligibility sensitivity.

Spacing is the nearest **strictly positive** polygon distance within the radius.
Touching and overlapping neighbors are ignored. An eligible field with no such
neighbor is radius-censored, never assigned a zero gap. Reported means/quantiles
are conditional on an observed gap and are not uncensored nearest-neighbor
estimates. Per-window generic outputs also retain extract-only unguarded results;
these are explicitly prefixed `extract_only_` in the combined regional table.

Source-vectorization edges and seams are unknown in the release schema. They
are retained and counted as unknown; the extraction-window edge is a separate
issue. Projection-invalid context and clipped-invalid counts are also recorded.
Unassigned context fields have null descriptors because they contribute only
geometry, not observations in the shape distributions.

## Interpretation and next phases

These profiles characterize detected fields in the published maps. The user's
visual review found substantial Rwanda omissions, which particularly affect
density, coverage and spacing. An empty mapped window has zero mapped count and
coverage, but undefined shape summaries. It does not establish an absence of
agricultural fields.

The published map's minimum-area filtering, hole filling, simplification and
cleanup also influence these profiles. Rare holes and narrow-neck flags reflect
the final release geometry. Differences in perimeter-sensitive measures could
reflect both field characteristics and mapping artifacts; imagery review helps
interpret examples but does not supply a contemporaneous accuracy assessment.

Three windows per zone support descriptive comparisons of these examples. They
do not establish globally representative landscape profiles. No regional PCA,
significance tests, confidence intervals or spatial bootstrap are included.
Alternative window scales and spatial uncertainty remain outstanding.

The [backlog](../instance-metrics-backlog.md) records a preparatory Mapping Africa
Zambia assessment stub, a narrow-neck repair-agent pilot after the regional
analysis, and later geometry–segmentation performance research. No Zambia data
are retrieved and no size–circularity hypothesis is tested in this phase.

## Initial findings

The ranges below describe the three selected windows in each zone. Size and
shape ranges are ranges of **window medians**, not pooled field quantiles or
confidence intervals. Rwanda has only two windows with descriptor observations.

| Zone | Assigned fields per window | Mapped coverage (%) | Median field size (ha) | Median circularity | Median elongation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bahia | 17–134 | 40.9–60.7 | 2.02–314.86 | 0.365–0.454 | 1.64–2.09 |
| California | 375–543 | 32.8–50.3 | 3.89–10.26 | 0.498–0.538 | 1.87–2.08 |
| Cambodia | 11,538–12,758 | 32.7–36.6 | 0.193–0.211 | 0.670–0.681 | 1.42–1.47 |
| Netherlands | 1,248–2,120 | 35.5–49.3 | 1.66–2.03 | 0.368–0.571 | 1.78–3.87 |
| Normandy | 1,053–1,287 | 24.5–67.8 | 1.70–4.46 | 0.521–0.574 | 1.74–1.93 |
| Rwanda | 0–602 | 0–9.58 | 0.212–0.503 | 0.611–0.682 | 1.38–1.62 |
| Vietnam | 2,155–8,078 | 60.8–85.1 | 0.417–1.138 | 0.510–0.564 | 1.55–2.00 |

Several examples show how the measures work together:

1. **The Cambodia windows have similar mapped-field profiles.** Their median
   field size is about 0.2 ha, with relatively high circularity and modest
   elongation. Median rectangularity is 0.795–0.828 and solidity 0.936–0.945.
   Circularity here accompanies reasonably rectangle-filling shapes; it does not
   establish that fields are circles. These windows contain roughly 115–128
   assigned fields per km², despite mapped coverage of only 33–37%.
2. **The Netherlands windows show why circularity needs interpretation alongside
   elongation and rectangularity.** `netherlands_61_578` has median elongation
   3.87 and circularity 0.368, yet rectangularity is 0.812 and solidity 0.915.
   Long, rectangle-filling shapes offer an explanation for low circularity.
   The other two windows have lower median elongation (2.08 and 1.78) and higher
   circularity (0.532 and 0.571).
3. **A single typical field size would obscure Bahia's variation.**
   `bahia_35_867` has only 17 assigned fields and median size 314.86 ha. In
   `bahia_41_861`, the median is 2.02 ha, the ordinary mean is 46.26 ha and the
   area-weighted mean is 160.65 ha. Many small observations coexist with much
   larger polygons accounting for most mapped field area. The distributions
   and weighted summaries make that contrast visible.
4. **Solidity and hull-perimeter ratio describe different boundary properties.**
   Cambodia and Vietnam both have fairly high median solidity (0.936–0.945 and
   0.911–0.920), while their median hull-perimeter ratios differ more clearly
   (0.941–0.954 and 0.875–0.894). The Vietnam polygons have more perimeter relative
   to their hull perimeter. Geometry alone cannot attribute that difference to
   actual management boundaries rather than mapping/extraction effects.
5. **Rare features vary substantially across these windows.** Holes occur in
   27.6–35.6% of Bahia fields and 11.8–20.3% of California fields, compared with
   0.4–1.1% in Cambodia. Narrow-neck flags occur in 7.5–11.8% of Bahia fields,
   compared with 0.13–0.28% in Vietnam. Bahia's small field counts make its
   percentages sensitive to individual polygons. Flags are candidates for
   inspection, not a count of repairable errors.

The doubled-angle orientation resultant ranges from about 0.03 to 0.22 across
nonempty windows. A small value does not necessarily imply disordered fields:
two perpendicular sets cancel in this statistic. Interpret it alongside the
saved orientation histograms, especially in gridded landscapes.

### Spacing sensitivity

| Search radius (m) | Full-context fields | Excluded for edge context | Observed positive gap | Radius-censored |
| --- | ---: | ---: | ---: | ---: |
| 50 | 56,600 | 2,750 | 53,703 | 2,897 |
| 100 | 55,336 | 4,014 | 54,639 | 697 |
| 250 | 51,800 | 7,550 | 51,721 | 79 |

At 100 m, window median observed positive gaps are 46.1–50.6 m in Bahia,
7.8–9.0 m in Cambodia, 11.7–12.6 m in the Netherlands and 10.0–30.0 m in Vietnam.
These are conditional on complete search context and an observed positive gap.
They should not be interpreted as missing agricultural land or universally
nearest field spacing. Rwanda gaps are particularly affected by missed fields.

### Geometry audit

One unassigned context field in `cambodia_48_125`, source ID
`48PVT_0_0-510503`, develops a ring self-touch after UTM projection despite valid
source geometry. Its clipped coverage geometry is valid. Its source boundary is
unchanged and its unneeded shape descriptors remain null. All clipped coverage
geometries in the study are valid.

`cambodia_47_129` has 27 positive-area overlap pairs and about 559.1 m² of overlap
excess. Three Vietnam windows have only floating-point-scale overlap excess
(absolute values below 0.000001 m²), including a tiny negative subtraction
residual. These should not be interpreted as substantive overlaps. No duplicate
resolution, seam repair or geometry cleanup was performed.

## Reproduction and validation

Run the command in the [pilot guide](../descriptor-pilot.md#regional-landscape-profiles)
with a fresh output directory. The earlier `regional-landscape-2024/` directory
is an incomplete first attempt that stopped while unnecessarily trying to measure
the projection-invalid unassigned context polygon. It is preserved for diagnosis;
use the completed `regional-landscape-2024-v2/` results.

- **73 geometry/research tests pass**, including synthetic regional integration,
  empty windows, all descriptor summaries, frozen-value reuse, context eligibility,
  censoring, rare-feature area fractions, source identity/geometry and changed hashes.
- All **217 output artifact hashes** and **84 recorded input hashes** verify.
- Independent checks against the frozen field table reproduce counts and **480
  descriptor means, medians and area-weighted means** across 20 nonempty windows.
- Independent coverage calculations reproduce **42** union/summed-area values.
- Brute-force polygon distances reproduce **60** sampled nearest-positive gaps.

The tables and figures describe this real pilot population; test counts are
software checks, not additional empirical observations.
