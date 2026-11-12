# Offline evaluation and inspection

Save model predictions once, then inspect or compare them without repeating
inference. For score interpretation, read the [metric guide](instance-metrics-guide.md)
and [exact scoring contract](instance-metrics-contract.md).
Polygon export is covered separately in [its guide](polygon-export-and-descriptors.md).

Run the following commands from the repository root.

## Save an evaluation run

`ftw model test` requires a local checkpoint; it does not download one. For example:

```sh
uv run ftw model test \
  --model "$HOME/working/models/ftw/FTW_PRUE_EFNET_B7.ckpt" \
  --dir "$HOME/data/labels/cropland/ftw" \
  --countries germany --model_predicts_3_classes \
  --test_on_3_classes --gpu -1 --save_probabilities \
  --out_dir "$HOME/working/ftw/metrics/test/prue-b7_germany_test_prob"
```

The default split is test; use `--use_val_set` for validation. `--gpu -1` uses
CPU. The default input uses stacked B-then-A imagery and radiance divisor 3000.
The three-class flags above request three-class predictions and references;
the default CLI loads two-class reference masks.

The output directory must be absent or empty. With `--out_dir`, the default
`metrics.csv` is written inside it; an explicitly supplied `--out` is honored.
`--save_probabilities` requires both `--out_dir` and `--model_predicts_3_classes`.

| Saved file | Contents |
| --- | --- |
| `manifest.json` | Checkpoint path/digest, data paths, preprocessing, code revision and scoring settings |
| `summary.json` | Scores calculated from pooled object statistics and pixel confusion counts; undefined JSON values are `null` |
| `chips.parquet` | One row per chip, with input/output paths, scores, valid/ignored pixel counts and additive `stat_*` columns |
| `metrics.csv` | The usual offline summary row, including extra instance metrics |
| `predictions/<country>/<chip>.tif` | Raw semantic argmax classes on the reference grid, without an inherited nodata flag |
| `probabilities/<country>/<chip>.tif` | Optional float32 background/interior/boundary probabilities on the same grid |

The manifest, rather than the checkpoint filename, identifies the model and
scoring setup. Missing image windows or reference masks can cause the dataset
loader to skip AOIs; the evaluated population is not necessarily every metadata row.
Probabilities are resized using nearest-neighbor sampling when needed, so their
argmax agrees with saved classes. Class rasters cannot recover missing probabilities.

## Understand the scoring setup

Default instance evaluation uses four-connectivity and strict IoU > 0.5 matching.
Reference labels 3/255 and configured ignored pixels are removed from both masks.
Objects crossing chip edges are not reconstructed across chips.

The legacy offline pixel score maps predicted class 2 to class 0. Saved prediction
rasters retain the original classes. Additional recorded pixel comparisons are:

- `three_class`: raw three-class reference versus raw prediction.
- `binary_interior`: field-interior pixels versus all other pixels.
- `legacy_asymmetric`: reference classes versus predictions with class 2 mapped to 0.

Three-class comparisons require the corresponding three-class flags. Scores use
summed confusion counts for pooling. Check the paper's evaluation protocol before
comparing to externally reported numbers.

For country/region evaluation, **sum sufficient statistics before calculating
scores**; do not average chip ratios. Chip-score averages and correlations are
valid descriptive analyses, but answer a different question. Undefined scores
remain missing rather than being replaced by zero.

Presence-only references cannot evaluate false positives. New outputs report
object precision, F1/RQ and PQ as undefined there, or when pooled with such
countries. Raw FP counts are debugging information, not validated false positives.
Support and pixel IoU on annotated areas do not establish accuracy outside them.

## Inspect a chip or rank examples

```sh
RUN="$HOME/working/ftw/metrics/test/prue-b7_germany_test_prob"
uv run python -m scripts.instance_evaluation.visualize_instances "$RUN" \
  --chip germany/g1_00001_10
```

Repeat `--chip COUNTRY/AOI_ID` for several chips. To rank by score disagreement:

```sh
uv run python -m scripts.instance_evaluation.visualize_instances "$RUN" \
  --metrics support object_precision --order absolute --limit 10
```

`high` sorts by the largest FIRST − SECOND; `low` by the smallest; `absolute`
by magnitude. Undefined values are skipped. Built-in `--ranking` choices are
`rand-split-merge` (default), `f1-recovery` and `f1-support`. Do not combine an
explicit chip selection with ranking options.

Figures show both image windows, plain reference/prediction labels and a separate
outline panel: green matched predictions (TP), orange unmatched predictions (FP),
and magenta unmatched references (FN). Red in the plain semantic panels means
class-2 boundary, not FN. Ignored areas are overlaid on raw predictions. FP
outlines and FP-dependent scores are suppressed for presence-only references.
Outlines follow exact pixel edges; matching is checked against saved statistics.

Figures are saved inside the run under `figures/selected/`,
`figures/<ranking>-oriented/` or `figures/<first>-vs-<second>-<order>/`.
Existing figures are not overwritten. The renderer requires aligned,
non-rotated grids and accessible source imagery.

### Compare reference definitions

The visualizer reads `manifest.settings.reference_mode`. Older manifests without
this setting mean `semantic-components`. With `dataset-instance-ids`, it loads
the paired instance mask, checks alignment and preserves supplied IDs.

For example, point the same visualizer at an original run and its rescored
counterpart under `rescored-runs/`; both show full metrics and matching outlines.
No FBP installation, label caching or additional scoring run is needed.
See [object identity](research/object-identity.md) for interpretation.

## Compare post-processing methods

Use a new output directory for each experiment:

```sh
uv run --extra fbp python -m scripts.instance_evaluation.compare_instance_methods \
  "$RUN" --out_dir "$HOME/working/ftw/metrics/test/germany_method_comparison"
```

The current default compares connected components with the unchanged `FTW_2E`
preset from FBP 0.2.0. Optional `--reference-mode dataset-instance-ids` preserves
reference IDs. Optional `--prediction-identity preserve-ids` preserves surviving
FBP IDs after masking; the default remains `split-components`.
Record both choices when interpreting results. Neither changes training defaults.

```sh
uv run --extra fbp python -m scripts.instance_evaluation.visualize_instance_methods \
  "$HOME/working/ftw/metrics/test/germany_method_comparison" \
  --method ftw-2e --chip germany/g1_00003_16 --generate-missing-labels
```

Selected label caching verifies provenance and scoring before adding label paths;
saved scores and summaries remain unchanged. Figures are written inside the
comparison directory. Use the single-run visualizer above for full-metric
reference-definition comparisons; this visualizer compares post-processors.

The [FTW_2E assessment](research/ftw-2e-assessment.md) reports the completed
seven-country study. [Chip-score analysis](chip-score-analysis.md) explains
correlations and paired comparisons. `compare_instance_runs` can also produce
a one-row-per-run CSV; use `--help` for its arguments.

## Audit object counts

```sh
uv run python -m scripts.instance_evaluation.audit_instance_chip \
  "$RUN" germany/g1_00001_10
```

This audit is for four-connected semantic-component baseline runs, not the
supplied-ID reference mode. Use the mode-aware visualizer for that comparison.
The JSON output includes component sizes, best IoUs, ignored pixels, tiny unmatched
references and current versus original-helper counts. Size thresholds are
diagnostics, not object filters. The original helper did not mask ignored pixels
in the same way; its raw FP count is not an evaluable presence-only score.

For verification against historical source, see the
[original-helper procedure](research/archive/original-helper-verification.md).
