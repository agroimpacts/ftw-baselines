# How much different instance metrics tell us

For the consolidated interpretation and figures, read the
[reference-metric synthesis](reference-metrics-synthesis.md). This page preserves
the historical analysis and reproduction details.

## Question and main findings

Do the existing instance scores mostly repeat each other, or do they describe
different aspects of the same predictions?

The eight-score study found substantial shared variation, but not one common
dimension. Changing from connected reference patches to supplied field IDs made
recall and recovery more closely associated even when the same chips were used
and Denmark was removed. A stronger precision/support association did **not**
survive Denmark exclusion. These results do not establish that any score should
be dropped or that disagreement identifies a validated mapping error.

The new [Chamfer extension](boundary-chamfer.md) reports an eleven-measure rerun
in both reference modes, including shared-population and Denmark controls. The
eight-score findings below remain historical and unchanged.

The initial analysis and supplied-ID follow-up are complete for these eight
scores. Reference-metric research remains open: the [boundary Chamfer extension](boundary-chamfer.md)
now has initial complementarity findings, with further validation outstanding. No boundary
distance is included in the historical results below. These are local research findings,
not an externally published assessment.

## Reproduce the existing analysis

Run `research.instance_metrics.analyze_metric_complementarity` on **single-method, test-split**
`ftw model test` run directories. It reads existing `chips.parquet` files; it
does not run inference or compare post-processors. Supply one run per country,
the same checkpoint and metric contract, and a **new** output directory:

```sh
uv run --with scikit-learn python -m research.instance_metrics.analyze_metric_complementarity \
  "$HOME"/working/ftw/metrics/test/prue-b7_*_test_prob \
  --out_dir "$HOME/working/ftw/metrics/analysis/baseline_complementarity"
```

Check the glob before using it: avoid duplicate country runs and include
Portugal's `prue-b7_portugal_test_prob` where available. Inputs and excluded
countries are recorded in `inputs.json`. Brazil, India, Kenya and Rwanda have
presence-only references and are excluded from the **common multivariate
population** because object precision and PQ cannot evaluate FP errors there.
The `FULL_DATA_COUNTRIES` policy includes Finland and Spain. Missing scores
remain missing: do not replace undefined SQ (no matches) with zero. Every
table identifies its finite population; scores are **chip-level**, not pooled
country-level evaluation scores.

## What each output means

* `availability.csv`: number of chips and chips with all eight distinct score
  columns defined, by country and combined. F1/RQ is excluded because it is
  identical by definition; PQ = RQ × SQ, so these are not eight independent
  sources of information. Check complete-case counts before comparing outputs.
* `associations.csv`: pairwise Pearson (linear) and Spearman (rank) correlations
  and their pairwise-finite counts. Strong correlation indicates shared ordering
  across these chips, **not** interchangeability in important edge cases.
* `pca_components.csv` and `pca_loadings.csv`: PCA of standardized,
  complete-case scores, separately per country and for all eligible chips.
  Each component's variance fraction and its metric loadings describe common
  directions of variation. `effective_rank = exp(-sum(p log p))` uses the
  normalized eigenvalues to describe an effective number of dimensions.
  PCA describes prevalent variation, not the importance of rare errors; a
  low-dimensional result is also partly expected from F1/PQ definitions.
* `clusters.csv`: average-linkage hierarchy of measures using distance
  `1 - abs(Spearman correlation)` on complete chips. Leaves `0..7` follow
  `inputs.json` metric order; later node IDs refer to earlier merges. Absolute
  correlation groups inversely related measures too, so inspect signs in
  `associations.csv` before interpreting a cluster.
* `predictability.csv`: reconstruct each score using the other seven, reporting
  out-of-fold R² and RMSE for ridge regression and a small nonlinear boosted
  tree. Within countries, five shuffled chip folds describe **reconstructability
  on similar chips**, not independent spatial generalization. The global run
  holds out entire countries (five folds). R² can be negative; compare RMSE
  with `target_std`. Exact nonlinear identities may not be learned perfectly by
  an approximate tree. High predictability is empirical redundancy, not proof
  of uselessness; low predictability can represent noise or missing references.
* `disagreement.csv`: within-scope percentile rank disagreement for specified
  interpretable pairs: recall/recovery, precision/support, PQ/recovery,
  PQ/support, and Rand split/merge. `top_quartile_disagreement` means exactly
  one score puts a chip in its top quartile; `opposite_extremes` means one
  puts it in the bottom and the other in the top quartile. Ties at cutoffs are
  excluded by rank definitions. `median_absolute_score_gap` describes raw
  score separation, **not** a calibrated quality difference: the denominators
  and meanings differ. These are relative rankings, not quality thresholds.
* `discordant_chips.csv`: ten chips with the largest absolute percentile-rank
  gap per scope/pair, with signed raw gaps and both scores. This is a review
  shortlist, not a representative sample or a validated failure label. Inspect
  imagery, possible missing annotations, and object sizes before attributing
  disagreement to model behavior. The existing manual reviews were themselves
  selected for contrasts and cannot estimate error prevalence.
* `matched_pq.csv`: near-PQ counterexamples (`|PQ_a-PQ_b| <= 0.02`) with the
  greatest recovery, support, Rand split or Rand merge separation, limited to
  nearby entries in PQ order. Pairs may come from different countries in the
  `all` scope; inspect country rows first. This shortlist demonstrates possible
  distinctions at similar PQ; it does not measure their prevalence, and
  Rand merge must be read alongside actual overlap and coverage.

The `all` rows weight chips, so large countries dominate. Country rows expose
heterogeneity and should accompany any global statement. These diagnostics
cannot establish incremental value for independently judged mapping errors:
that would require a separately sampled, blinded label audit. Neither PCA nor
out-of-fold prediction alone establishes that a measure should be dropped.

## Initial 25-run test snapshot

The first baseline-only analysis included all 25 saved country runs: 21
countries with labeled background contributed 7,156 chips to the common
population, of which 5,601 had all eight scores defined (notably, SQ requires
at least one matched field). Four presence-only countries were excluded.
Across the 5,601 complete chips, the first standardized principal component
accounted for 58.1% of variance, with an effective rank of 3.83: there is
substantial shared quality variation, but not a single empirical dimension.

Across finite chip pairs, recall/recovery had Spearman 0.730 and top-quartile
disagreement 21.0%; precision/support had 0.688 and 20.1%. Rand split/merge
had Spearman 0.159 and top-quartile disagreement 34.5%, consistent with
different sensitivities, although both need coverage context. With whole
countries held out, nonlinear reconstruction R² was 0.697 for support,
0.803 for Rand merge, 0.824 for Rand split, and 0.933 for recovery. PQ's
R² of 0.997 is unsurprising because the inputs include the factors that
mathematically determine it (F1 from precision/recall, and SQ). These figures
describe statistical reconstruction, **not** validated failure-mode utility.
Chip-ranked and equal-country conclusions may differ; inspect country rows and
review the saved counterexamples before drawing general conclusions.

## Supplied-reference-ID rerun

For per-chip figures with full metrics and mode-correct TP/FP/FN outlines, use
`scripts.instance_evaluation.visualize_instances` on the original run and its `rescored-runs/` counterpart;
the [visualization guide](../offline-instance-evaluation.md) describes
the commands (including Belgium `g2_00045_5`). The manifest selects reference
identity automatically; no additional evaluation is needed.

The follow-up reuses the exact run list recorded in
`baseline_complementarity_all25_complete/inputs.json`, not a fresh glob. It
rescores **only four-connected predicted class-1 components** against the paired
FTW instance masks, preserving disconnected reference pieces under their supplied
IDs. There is no FBP, new inference, size filtering or training change. Grid
alignment and reference/class-1 foreground equality on valid pixels are required.
Original prediction/probability rasters are referenced, not copied. Pixel scores
remain unchanged; instance sufficient statistics and scores are recomputed.

Preflight found all masks present/aligned, but 26 chips lack instance IDs for
some class-1 pixels: India `g2_0000` (211 pixels) and 25 Kenya chips. These
countries were already excluded from the common multivariate population. The
rerun retains every row and pixel score, marks those instance scores/statistics
undefined, and records `reference_status` and each summary's `unscorable_chips`
with missing/extra pixel counts. No synthetic IDs, fallback reference extraction
or silent chip deletion is used. Pooled summaries cover only `scored_chips`.
Missing/misaligned files still fail. The standalone rescoring helper remains
strict unless its explicit `allow_unscorable` policy is enabled by this rerun.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 uv run --with scikit-learn \
  python -m research.instance_metrics.analyze_metric_complementarity \
  --rerun-reference-analysis "$HOME/working/ftw/metrics/analysis/baseline_complementarity_all25_complete" \
  --out_dir "$HOME/working/ftw/metrics/analysis/baseline_complementarity_all25_complete/reference-modes/dataset-instance-ids"
```

Existing output paths are refused. `--resume` can reuse verified country
rescoring artifacts after interruption; completed analyses are not overwritten.
The original analysis stays untouched.

### Why compare several sets of chips?

There are two reference definitions: **semantic components** treat separate
four-connected reference patches as objects; **dataset instance IDs** keep pixels
with the same supplied ID together, even when disconnected. Predictions do not change.

A score is "finite" when it has a numerical value rather than being undefined.
For example, SQ is undefined when no objects match. Changing reference grouping
can change whether matches exist, so it can also change which chips have all
eight scores available.

In this study, 5,601 chips had all eight scores under semantic-component references,
and 5,584 under supplied-ID references. **5,582 had all eight under both definitions.**
If we compare different chip sets, a changed correlation or PCA result could
reflect either changed reference grouping or changed chip membership. Using the
same 5,582 chips removes the membership difference. This is the meaning of
"shared complete": the same chips, with no missing scores in either version.

Denmark is a second, independent concern: its supplied IDs group many separate
patches, and their provenance is unresolved. Removing Denmark checks how much
it influences the findings; it is not an annotation repair or proof its IDs are wrong.

| Comparison | Chips included | Purpose / saved location |
| --- | --- | --- |
| **All available chips** | Each analysis uses the scores it requires; Denmark included | Broad comparison; supplied-ID results in `full/`, original results in the source analysis directory |
| **Same chips under both definitions** | The same 5,582 chips, all eight scores available in both versions | Removes chip-membership differences; `comparison/shared-complete/` |
| **Exclude Denmark** | Denmark removed; each analysis otherwise uses its available scores | Checks Denmark's influence, but does not force identical chip sets; `comparison/without-denmark/` |
| **Same chips, excluding Denmark** | The same 5,280 chips in both versions, without Denmark | Applies both checks; `comparison/shared-complete-without-denmark/` |

Each `comparison/` folder above has `semantic-components/` and
`dataset-instance-ids/` results. These are the same analysis procedures applied
to the two reference definitions, not different prediction methods. "Available"
depends on the analysis: correlations use chips with both scores, while PCA
and other complete-score analyses require all eight.

`rescored-runs/` holds the updated chip scores, pooled summaries and manifests
for each original run. Manifests identify source runs and
`reference_mode=dataset-instance-ids`. The loader rejects mixed reference modes;
older manifests without a mode mean `semantic-components`.

`comparison/metric_changes.csv` compares each metric on chips where **that metric**
is available under both definitions. It reports chip-score averages and changes,
not country-level scores calculated by pooling object counts. Chip membership
can differ between metrics. Its `all` rows include only countries with labeled
background. `populations.json` records overall/shared counts; `availability.csv`,
pairwise `n` and `inputs.json` identify the chips contributing to each analysis.

The same four presence-only countries remain excluded from the multivariate
analysis; their rescored tables and applicable recall diagnostics are retained.
The eight metrics, transformations, model settings, seeds, CV definitions and
shortlist construction are unchanged. Within shared populations, chip ordering
and fold assignment are held fixed between reference modes. PCA component signs
are arbitrary, so compare explained variance and patterns rather than signed
loadings alone. These remain statistical diagnostics, not validated error labels.

### Completed results

All 25 runs / 7,805 chip rows were retained; 7,779 were rescored, with the 26
India/Kenya exceptions above explicitly undefined. The primary multivariate
population remains **7,156 chips from 21 labeled-background countries**.
All-eight-score complete cases change from **5,601 to 5,584**: 5,582 are shared,
19 old complete cases cease to be complete and two become newly complete.
Without Denmark, the shared complete population is 5,280. The shell completion
message called all 7,805 rows "eligible"; that label was misleading and has been
corrected in the script. Use `availability.csv` for actual eligible populations.

On each mode's full finite populations, recall/recovery Spearman increases from
.730 to .776 (n=6,027), precision/support from .688 to .730 (n=5,786), and Rand
split/merge decreases from .159 to .072 (n=6,027). Recall/recovery top-quartile
disagreement decreases from 21.0% to 18.8%; precision/support remains about 20%
(20.1% → 20.4%); Rand split/merge disagreement rises from 34.5% to 37.2%.

The comparisons using the same chips show which findings persist when chip
membership is held fixed, with and without Denmark:

| Diagnostic | Same chips: components (5,582) | Same chips: supplied IDs (5,582) | Same chips, no Denmark: components (5,280) | Same chips, no Denmark: IDs (5,280) |
| --- | ---: | ---: | ---: | ---: |
| Recall/recovery Spearman | .664 | .719 | .665 | .738 |
| Precision/support Spearman | .656 | .701 | .662 | .657 |
| Rand split/merge Spearman | .020 | -.087 | .031 | -.015 |
| First PCA variance fraction | 58.2% | 59.9% | 58.4% | 59.6% |
| Effective rank | 3.83 | 3.63 | 3.81 | 3.69 |

Thus stronger recall/recovery association is robust to these controls. The
precision/support increase is not: it disappears without Denmark. Rand measures
remain weakly associated; the more negative shared-population result is also
strongly affected by Denmark. There is slightly more common score variation,
but still multiple effective dimensions—not evidence that all scores are
interchangeable or that any metric can be dropped.

Held-out-country nonlinear reconstruction R² on shared chips changes from .876
to .937 for precision and .983 to .909 for recall with Denmark included. Without
Denmark these become .873 → .923 and .982 → .972. Support changes .693 → .749
with Denmark, but only .696 → .700 without it. Recovery remains highly
reconstructable (.931 → .945 with Denmark, .932 → .945 without). These are
reconstructability diagnostics with unchanged models/folds, not independent
validation of score quality or model improvement.

Paired-finite chip means across eligible countries change by +.0835 for recall,
-.0465 for precision and +.0200 for PQ; these are **not pooled evaluation scores**
and are sensitive to country composition. Inspect country rows in
`comparison/metric_changes.csv` rather than interpreting those changes as better
predictions. Only reference grouping changed.

`comparison/verification.json` records successful checks: all original chip keys,
pixel scores/counts, and prediction-component counts on scored chips were
preserved; all seven analysis suites contain their nine CSV outputs and input
records. It also records package versions. Original analysis files and model
artifacts were not overwritten; no raster/probability copies were made.

These eight-score results preceded polygon export and final-geometry descriptors.
They remain unchanged. See [current status](../instance-metrics-progress.md) and
the [boundary-distance to-do](../instance-metrics-backlog.md#ref-1-boundary-chamfer-distance)
for the next reference-metric research, separate from a larger-area geometry study.
