# Historical connected-component diagnostics and manual review

This preliminary workflow is preserved with its scripts, notebook and tests.
For the broader, ongoing research, see [metric complementarity](../metric-complementarity.md).

Run the read-only analysis on saved test comparisons with `--save_labels`:

```sh
uv run python -m research.instance_metrics.archive.diagnose_component_metrics \
  "$HOME"/working/ftw/metrics/test/prue-b7_{belgium,cambodia,croatia,denmark,germany,vietnam}_methods_fixed_labels \
  --out_dir "$HOME/working/ftw/metrics/analysis/components4_metric_diagnostics_final"
```

Supply any further eligible country comparison directories as positional inputs.
The script rejects presence-only countries (including Brazil), missing baseline
labels, inconsistent saved scores, duplicate countries, and mixed checkpoints.
Outputs must go to a **new** directory on every run; existing runs are untouched.
For a fast table-only run use `--no_figures`; `--per_case` controls the number of
shortlisted examples per country and category (default 2). To change the
positive-control shortlist, set `--high_score` (default 0.7 for both measures,
and PQ when applicable) and `--agreement_tolerance` (default 0.1 for each pair).
Both must be in [0, 1]. Countries with no qualifying high-quality chips simply
have no examples in that category; a high *relative* rank is not treated as
high absolute quality.

The output contains `manifest.json`, `report.md`, `chip_diagnostics.parquet`,
`reference_fields.parquet`, `predicted_fields.parquet`, `country_summary.csv`,
`size_bin_summary.csv`, `case_candidates.csv`, `case_review.csv`, and a `figures/`
gallery. The field tables contain best IoU, match status, area, overlap partner,
and size bin; predicted fields also record pixels outside reference foreground.
The 1–4, 5–16, 17–64, 65–256 and >256 pixel bins are descriptive, not a filter
or a physical-area classification. Within each bin, `match_rate` is a
reference-side recall-like or prediction-side precision-like fraction;
`mean_best_iou` counts misses as zero, `area_weighted_best_iou` weights by the
source-side area (a bin-restricted recovery/support), and
`mean_matched_best_iou` is averaged only over matched objects in that side's
bin (SQ-like, not PQ). Empty bins have undefined means/rates; a bin with no
matches has undefined matched-only mean. Per-bin PQ and Rand scores are not
reported because cross-bin matches require additional attribution rules.
The source masks, matching rule, and pooled score definitions remain unchanged.

Use `case_candidates.csv` to inspect recall/recovery, precision/support, and
Rand disagreements as well as similar-PQ chips with different area scores.
Similar-PQ-and-area pairs with different Rand scores are proposed topology
counterexamples; both members are rendered, identified by `paired_aoi_id`.
`case_candidates.csv` includes every saved chip-level instance score (object
precision, recall, F1/RQ, SQ, PQ, recovery, support, Rand split/merge), plus
TP/FP/FN. It also includes high-and-agree recall/recovery and precision/support
examples, and examples meeting both agreements *and* high PQ. The figures show
the raw three-class mask alongside instance IDs, with the standard outline
legend and metric text below the panels.
The report lists *selection hypotheses*, not confirmed diagnoses. Inspect the
imagery and masks and record conclusions in `case_review.csv`. In particular,
small references are not necessarily rasterization artifacts; high Rand merge
with little coverage does not indicate successful segmentation. SQ is undefined
without TP and should not be treated as zero in SQ comparisons.

For a quick manual review, open
[`review_component_cases.ipynb`](../../../research/instance_metrics/archive/review_component_cases.ipynb)
using a Python environment with `ipywidgets` installed. Install it in the
notebook kernel's environment if needed, then restart the kernel. No project
dependency or lockfile change is needed for this optional review workflow.
Set `analysis` to the desired output directory and run both code cells. Choose
a country, comparison category and chip from the dropdowns. Click **Load figures**
once after the controls appear; subsequent selections load images automatically.
Any existing review appears with its chip, without blocking input prompts.
**Fragment checked?** records whether you inspected the labels; the separate
**Reference fragments?** control records your assessment (Not assessed,
Present, Likely, Unlikely, Absent, or Uncertain). Older CSVs without this assessment column
remain readable, and their existing review text is retained. Enter a finding and
press **Save review** to persist it, or **Next chip** to browse without saving;
**Reload CSV** picks up changes made since the last load. Paired examples show
both figures. Reviews are keyed by country, AOI ID and case: different
selection hypotheses for the same chip can receive different reviews. The
notebook refreshes `case_review.csv` between cases and writes it atomically;
it leaves the generated figures, candidates, and any spreadsheet untouched.
Avoid editing the CSV simultaneously in another application. The earlier
text-input `browse()` workflow was removed because Jupyter frontends can
appear to hang while waiting for `input()`.

The analysis uses held-out test examples for interpretation only, not for
Phase 4 parameter selection. `country_summary.csv` includes pooled object
scores, recovery/support, Rand split/merge and counts; its scores retain full
precision. The report rounds these pooled metrics to three decimals. Its
`finite_pq` counts chips with defined PQ (at least one reference or prediction
object), while `finite_sq` counts chips with at least one qualifying match;
neither is a denominator for pooled PQ/SQ. Chip-score medians in the report
are not pooled PQ; compare countries separately before generalizing.
