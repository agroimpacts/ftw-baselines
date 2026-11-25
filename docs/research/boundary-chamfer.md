# Boundary Chamfer implementation checkpoint

Read the [reference-metric synthesis](reference-metrics-synthesis.md) for the
combined scientific interpretation. This page provides supporting methods and
the detailed execution record.

The shared API is now `ftw_tools.training.metrics.boundary_chamfer` and
`chamfer_statistics`, implemented in `ftw_tools/training/_boundary_metrics.py`.
The old research import is a compatibility adapter. These explicit functions do
not change training defaults, prediction extraction or existing scores. All
15,610 saved rows were recomputed through the shared API, with all eleven scores
and instance statistics matching within numerical tolerance. Verification took
258 seconds; the record is `chamfer-integrated-verification-v1.json` beside the
original analysis directory. The integrated API supports the existing matching,
connectivity, ignore-index and reference-ID options.

## FTP cross-check

Checked upstream `taylor-geospatial/fields-of-the-planet` revision
`a626650d2944773b48b9ddd43d914405e6d95cae`, file
[`src/ftw_planet/eval.py`](https://github.com/taylor-geospatial/fields-of-the-planet/blob/a626650d2944773b48b9ddd43d914405e6d95cae/src/ftw_planet/eval.py).

FTP uses binary raster boundaries: foreground pixels with interior Euclidean
distance transform less than 1.5 pixels. Its distance is half the sum of the
two directed mean nearest-boundary distances, unsquared, multiplied by pixel
ground size. It is not a polygon-vertex or length-weighted polygon measure.
Hole boundaries contribute. There is no exterior padding; array-edge behavior
is inherited from SciPy's distance transform. This behavior is intentionally
preserved, rather than silently replacing it with an idealized polygon edge.

A live parity check executed only the upstream `_boundary_pixels` and
`_symmetric_chamfer` function definitions in memory. All 100 seeded randomized
32-by-32 mask pairs agreed exactly at 10 m pixel size. Upstream source was not
added to this repository. Nine local controlled tests also passed.

The upstream matching implementation uses strict IoU > threshold despite a
nearby comment saying >= 0.5. Our existing strict > 0.5 assignment is retained.
For disjoint instances, qualifying matches at that threshold are unique.
Upstream averages distances across matched objects, not equally across chips.
Our sums and counts permit that same object-weighted pooling.

## Additional diagnostic and explicit limits

Best-IoU pairing selects one positive-overlap prediction per reference; repeated
prediction selection is allowed. Exact ties select the lowest compact prediction
ID. Coverage counts references with positive overlap, independently of whether
the boundary distance is finite. No overlap has no distance, not zero error.
No qualifying distances yields NaN; zero eligible references yields NaN coverage.

Reference extraction supports both semantic connected components and preserved
supplied IDs through the existing identity API. Predictions remain four-connected
semantic components. Both sides are masked to the existing reference-valid
domain before boundary extraction. This can introduce artificial edges around
ignored pixels; it is not evidence of full untruncated boundary accuracy.
Supplied reference IDs can retain disconnected components, unlike upstream's
polygon-component extraction. Numerical parity of the distance kernel does not
establish equivalence of complete evaluation pipelines.

## Experimental offline integration

The analyses remain research utilities, separate from the shared metric API.
`research.instance_metrics.analyze_chamfer` now rescores the recorded baseline
cohort in both reference modes, retaining original runs and rasters. It requires
the existing strict 0.5, four-connected test contract. Supplied-ID foreground
mismatches remain explicit unscorable rows, without synthetic IDs or fallback.

Projected grids use their axis-unit conversion factors. Geographic grids use
geodesic row/column steps at the chip centre, treated as locally constant metre
spacing. This is an explicit approximation, not an exact geodesic distance for
every boundary-point pair. Anisotropic spacing extends FTP's square-pixel kernel:
boundary selection still uses its <1.5 pixel rule, while nearest-point distance
uses row/column metre spacing. Rotated/sheared grids are rejected. Consequently,
FTP kernel agreement on square pixels is not full-pipeline numerical equivalence
on these geographic rasters. A cached bounding-box boundary/KD-tree calculation
avoids repeated full-chip transforms; controlled tests compare it to full-grid
EDT distances, including image-edge objects.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 uv run --with scikit-learn \
  python -m research.instance_metrics.analyze_chamfer \
  --baseline-analysis ~/working/ftw/metrics/analysis/baseline_complementarity_all25_complete \
  --out_dir ~/working/ftw/metrics/analysis/chamfer_reference_modes_v1

uv run --with scikit-learn python -m research.instance_metrics.review_chamfer \
  ~/working/ftw/metrics/analysis/chamfer_reference_modes_v1
```

Use a new output directory for each run. `--pilot-chips N` limits each country
to its first N chips and records that limit; these are timing/debug samples, not
representative findings. `--skip-predictability` is explicitly recorded.

### Analysis design

The original eight measures are extended with threshold Chamfer, best-IoU Chamfer
and best-IoU reference coverage. Report pairwise Pearson/Spearman with finite
sample counts, distributions/availability, PCA/effective rank, average-linkage
metric clustering, ridge/boosted-tree out-of-fold reconstruction, direction-aware
rank disagreements and near-PQ/near-SQ counterexamples. Raw correlations retain
their signs. Lower distances are reversed only for quality-rank disagreement;
raw gaps between metres and unitless scores are not calibrated quality gaps.

Original-eight and expanded-eleven PCA/reconstruction use the same eleven-score
complete cases. New measures are also reconstructed using only the original
eight predictors. Within-country folds are shuffled chips, not spatial holdouts;
combined folds hold countries out. Fixed populations/order preserve fold assignment.
Both modes use available populations, shared-eleven-score complete cases, and
both comparisons without Denmark. Presence-only countries retain score tables but
are excluded from the main multivariate population. `population.csv` records
actual chip identities, not only counts.

The review supplement provides within-country/mode terciles of mean reference
object area and best-IoU coverage, plus outline panels for selected disagreements.
Mean-area strata are chip-level controls, not an object-level size study. Tied
quantiles may yield fewer strata. Outline review is not imagery-based validation
or evidence of error prevalence. Existing historical analysis outputs are untouched.

### Completed run and initial findings (2026-11-21)

The three-chip Cambodia pilot scored both reference modes in approximately
0.7 seconds after optimization. Eighteen focused/regression tests passed before
launching the full 25-country run; the expanded regression run subsequently
passed 42 tests, including the existing instance metric suite. The full run
completed in **810 seconds (13.5 minutes)** under
`~/working/ftw/metrics/analysis/chamfer_reference_modes_v1/`.

All 25 countries and 7,805 original chips are retained under each reference mode
(15,610 rows). Semantic references score all chips; supplied-ID references score
7,779, retaining the same 26 India/Kenya foreground-mismatch rows as undefined.
The main labeled-background population remains 7,156 chips per mode. Availability
of threshold/best-IoU Chamfer is 5,601/5,689 semantic chips and 5,584/5,689 supplied-ID
chips. Shared eleven-measure complete cases number 5,582, or 5,280 without Denmark.

All saved parquet hashes verify. Pixel scores match the originals in both modes.
Semantic instance scores match the originals except for the intentional current
presence-only reporting mask: historical source tables contain precision/PQ in
presence-only countries, whereas the new tables correctly leave those undefined.
This does not affect the labeled-background multivariate comparison. Coverage is
at least object recall wherever both are defined, and finite threshold-distance
counts never exceed threshold TP counts. These checks are in `verification.json`.
The original source artifacts are unchanged. Research source snapshots and hashes
are in `source-snapshot/`. All eight analysis suites contain their expected tables;
161 final artifact hashes verify, including 36 outline-review panels. The hash list
is `artifact-hashes.json` (it does not include itself).

On **identical shared chips**, combined chip-level results are:

| Diagnostic | Semantic components | Supplied instance IDs |
| --- | ---: | ---: |
| Threshold vs best-IoU Chamfer Spearman | .579 | .652 |
| Threshold Chamfer vs SQ Spearman | -.365 | -.389 |
| Best-IoU Chamfer vs recovery Spearman | -.368 | -.451 |
| Coverage vs object recall Spearman | .620 | .558 |
| Effective rank, original eight → eleven | 3.83 → 5.53 | 3.63 → 5.30 |
| Threshold Chamfer reconstructed from original eight, held-country nonlinear R² | .203 | .223 |
| Best-IoU Chamfer reconstructed from original eight, held-country nonlinear R² | .475 | .436 |
| Coverage reconstructed from original eight, held-country nonlinear R² | .703 | .720 |

The two distances share information but are not interchangeable in this cohort.
Without Denmark, their correlation remains .586/.639, and their best-quartile
classifications disagree for **22.3%/20.2%** of chips. Threshold Chamfer's
correlation with SQ remains only -.360/-.345. Best-IoU Chamfer reconstructed from
the original eight has held-country R² .463/.497 without Denmark; threshold
Chamfer has .192/.153. Those associations survive the Denmark check, although
absolute distances and reconstruction errors can be strongly influenced by
supplied-ID grouping. Country rows remain essential: pooled chip results weight
larger countries more heavily.

**Interpretation:** retain both variants for further review rather than discard
best-IoU as redundant. Neither these correlations nor increased effective rank
establish independent physical factors, improved accuracy, or validated practical
utility. Best-IoU increases distance availability only modestly at chip level;
within-chip pairing changes can nevertheless alter the mean substantially.
Distances remain conditional on overlap/matching and must accompany coverage or
recall. Their metre scale also depends on object size and raster resolution.

### Review artifacts and remaining work

`review/index.html` links selected outline panels with reference/prediction objects,
threshold and best-IoU centroid links, both distances and coverage. It is a
development shortlist, not a representative imagery audit. A rendered Denmark
panel illustrates how supplied IDs spanning disconnected pieces can yield low
threshold Chamfer but very large best-IoU Chamfer; this is a grouping-sensitive
diagnostic, not an adjudicated annotation or model error.

`review/stratified_associations.csv` records within-country/mode mean-reference-area
and coverage terciles. Small or constant strata produce undefined correlations;
NumPy/pandas emitted warnings during generation, and these entries remain NaN,
not zero. They do not support reliable subgroup claims. Detailed country/size
interpretation, independent imagery review, grid-resolution/edge sensitivity and
further practical validation remain open. Both Chamfers are now exposed through
the shared metrics module; automatic training computation remains unchanged.
