# Explore relationships between instance scores

These are research tools for saved scores, not inference commands. Run them from
the repository root. Definitions are in the [metric guide](instance-metrics-guide.md);
completed findings are in the [research reports](research/README.md).

## Correlations and scatterplots

```sh
uv run python -m research.instance_metrics.analyze_instances \
  "$HOME/working/ftw/metrics/test/prue-b7_germany_test_prob" \
  --out_dir "$HOME/working/ftw/metrics/analysis/germany_test"
```

Supply several run directories before `--out_dir` to combine countries. Inputs
must have one prediction per chip, the same checkpoint, split and scoring settings,
and no duplicate country/chip keys. Method-comparison tables have several rows per
chip and cannot be used here. Output directories must be new.

Default scatterplots compare support/precision and recovery/recall. Repeat
`--pair FIRST SECOND` to replace them, for example:

```sh
uv run python -m research.instance_metrics.analyze_instances RUN_DIR \
  --out_dir NEW_DIRECTORY \
  --pair pixel_binary_interior_iou_class_1 recovery \
  --pair rand_split_score rand_merge_score
```

Pairs may use instance-score columns or `pixel_binary_interior_iou_class_1`.
The first variable is x, the second y. Matrices still include all instance scores
and field-interior pixel IoU, regardless of selected scatterplots.

| Output | Meaning |
| --- | --- |
| `pearson.csv` / `.png` | Linear relationships between chip scores |
| `spearman.csv` / `.png` | Rank relationships |
| `pair_counts.csv` | Number of usable chips for each pair |
| `regressions.csv` | Ordinary least-squares slope, intercept, R² and pair count |
| `<first>-vs-<second>.png` | Country-colored points, 1:1 line and fitted line |
| `inputs.json` | Sources, countries, split and chip counts |

Missing scores are excluded separately for each pair, so counts can differ.
Constant variables or too few observations leave the corresponding fit/correlation
undefined. Heatmaps use 0.05-wide color bins with three-decimal annotations;
CSV coefficients are not binned. OLS R² is squared Pearson correlation when the
intercept fit is defined, not Spearman correlation.

Every chip contributes one observation. Larger countries therefore have more
influence; compare country-specific results as well as combined results.
These are not correlations between individual fields or pooled country scores.
Use new outputs for presence-only countries: historical numerical precision/PQ
values may not be evaluable. F1 equals RQ and PQ depends on RQ and SQ, so some
strong relationships are mathematical rather than independent findings.

Field-interior pixel IoU treats all field pixels as a single mask. Recovery
instead averages each reference object's best IoU with an individual prediction,
weighted by reference area. Splits/merges can therefore affect recovery despite
high pixel IoU. Neither uses the object-matching threshold; an unrelated extra
prediction lowers pixel IoU but need not lower recovery.

## Complementarity and paired method differences

Use `research.instance_metrics.analyze_metric_complementarity` for correlations,
PCA, score reconstruction and disagreement shortlists. Its
[report](research/metric-complementarity.md) explains the reference-definition
comparisons and exactly which chips are included.

Use `research.instance_metrics.assess_instance_measures` on saved method-comparison
directories for paired score differences and pooled diagnostics; see `--help`.
Chip-average changes are not pooled detection scores. Chip-bootstrap intervals
are not spatially independent confidence intervals. In particular, do not report
pooled precision/F1/PQ from any population containing presence-only countries,
even if a historical table provides numbers.

The initial component-only case-review workflow is preserved in the
[archive](research/archive/components4-metric-diagnostics.md), not required for
current analysis. Boundary-distance complementarity remains
[outstanding](instance-metrics-backlog.md#ref-1-boundary-chamfer-distance).
