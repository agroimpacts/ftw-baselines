# Published-map descriptor associations: initial pilot

Run 2026-11-13. This is **descriptive exploratory analysis**, not a global estimate,
accuracy assessment or completed practical-complementarity study.

## Population and methods

All 59,350 assigned primary fields, with unique collection-qualified identities,
were analyzed. The 69 user-selected pivot diagnostic fields were excluded.
There are 40 pooled/landscape/size groups and 9,600 pair-table rows for 16
numeric/boolean descriptors under raw and log1p representations. Pearson and
Spearman use every finite pair, not sampled reservoirs. Strictly monotone
transforms reuse original ranks to avoid artificial floating-point log ties.
Undefined correlations remain blank. Raw axial orientation and its ambiguity
flag are excluded from linear association/PCA features.

Size bands are <0.1 ha, 0.1–1 ha, 1–10 ha and >=10 ha. Size-stratified analyses
are exploratory conditional relationships, not size-independent causal effects.
Availability records constants, finite counts and nonzero counts. Window
availability retains the empty Rwanda window, which has no field descriptors.

PCA uses circularity, log1p elongation, solidity, rectangularity, convex-hull
index and hole-area fraction, with complete cases and within-group population-SD
standardization. Constants are dropped explicitly; 39 groups have PCA results,
one has insufficient rows. Outputs called weights are eigenvector coefficients,
not correlation loadings. Signs are fixed for reproducibility, not interpretation.
Supporting dimensions, area and binary flags are deliberately absent from PCA.

## Initial results

| Descriptor pair | Pooled Spearman | Range across seven landscapes |
| --- | ---: | ---: |
| Circularity / elongation | -0.570 | -0.733 to -0.430 |
| Solidity / rectangularity | 0.715 | 0.638 to 0.860 |
| Solidity / convex-hull index | 0.610 | 0.353 to 0.797 |
| Circularity / rectangularity | 0.463 | 0.230 to 0.740 |

These associations show overlap but do not establish universal interchangeability.
Pooled circularity/elongation associations within size bands range from -0.615
to -0.386. Pooled shape PCA explains 50.9% with PC1, 70.3% with the first two,
and 86.8% with the first three. That is not proof that three descriptors suffice,
nor that every retained feature adds scientific value.

Cambodia and Vietnam contribute 82.6% of fields, so pooled results heavily reflect
those landscapes. Bahia has only 224 primary fields; Rwanda has 645 detected
fields and one empty window. User visual review indicates many Rwanda false
negatives. Descriptor relationships are conditional on what the map detected.

Holes occur in 894 primary fields (1.5%); narrow-neck flags in 494 (0.83%). These
rare features need targeted visual interpretation, not automatic removal. The
published hole-fill, size-filter and simplification rules affect their prevalence.
Circularity, rectangle ratios and hull ratios also have known algebraic relations;
empirical correlation cannot remove those mathematical dependencies.

## Artifacts and validation

Canonical directory:
`~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/complementarity-2024-stable-ranks/`.
Start with `README.md`, `spearman-by-landscape.png` and `pooled-pca-variance.png`.
CSVs contain distributions, availability, pair counts/associations, PCA weights,
variance/status and within-zone rank-disagreement candidates for subsequent map
review. Candidates are selected from the existing sample, not added observations.

An earlier `complementarity-2024/` pass is preserved but superseded: logarithmic
rounding introduced tiny artificial rank ties (maximum Spearman difference about
0.000003). The canonical pass reuses raw ranks for monotonic transforms. Raw
associations and PCA conclusions were unaffected.

Validation checked artifact hashes, expected pair-table dimensions, independent
SciPy pooled/all-landscape reference associations, rank invariance and PCA variance
sums. The geometry suite passes 66 tests, including PCA orthonormality, constant
feature and insufficient-row checks.

## Outstanding

No p-values, confidence intervals or spatial bootstrap were run. Spatial-block
choice and sensitivity, map review of descriptor disagreements, preprocessing
sensitivity and scientific feature-selection recommendations remain outstanding.
Regional gap/density/coverage analysis, reference accuracy and Chamfer are separate.

The bounded-sample correlation tool documented in the general geometry guide was
not used here: it requires a common metric CRS and block settings. This pilot's
zone-specific CRSs and deliberately inference-free first pass instead use the
full-table descriptive entry points `analyze_descriptor_pilot` and
`report_descriptor_pilot`. See the [pilot specification](../descriptor-pilot.md).
