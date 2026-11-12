# Historical comparison: connected components and FBP 0.1.0

This exploratory study predates the FBP 0.2.0 preset now used by the tools.
It is preserved for reproducibility, not as current method-selection guidance.
See the [FTW_2E 0.2.0 assessment](../ftw-2e-assessment.md) for the later study.

The Phase 3 comparison uses PRUE EFNet B7, checkpoint SHA-256
`2b1b34a17b85b8f70da6ff737529743b6bc6049e987bce5a1fcdd7279eb3b120`,
on the same three-class FTW chips per method. The local fbp checkout used for
these runs was version 0.1.0 at revision
`6997c536c02162567513c060a4c3fad84d6cc33d` (clean worktree).
The ftw-baselines checkout was at revision
`4e64b6b3572a8a6a572971e1ab32655512a71bad` with uncommitted Phase 3
changes. Keep the corresponding source changes when reproducing these results;
the manifests' `code_revision` alone does not identify uncommitted code.

## Inputs and methods

Run `ftw model test` with `--out_dir --save_probabilities` once per country
and split. Saved raw class rasters and unquantized float32 softmax channels
(background, field, boundary) share the reference grid. All methods use the
same valid reference pixels (0/1/2), ignore 3/255 and `ignore_index`, use
4-connected references, strict IoU > 0.5 and the shared instance statistics.
The offline test's legacy class-2-to-0 scoring does **not** alter the saved
classes supplied to fbp. There is no per-method pixel-score comparison; the
same model probabilities are used throughout.

- `components-4` and `components-8`: class-1 connected components. The
  `components-4` result must reproduce `summary.json`'s original instance
  statistics or the comparison stops.
- `arg-ws2`: fbp's FTP-style class-1 watershed followed by connected
  components of its union. Per fbp's implementation this collapses watershed
  splits, so it is **not an independent split strategy**; tiny count changes
  arise where some foreground pixels are omitted.
- `arg-pb-h0.01-t0.3`: fbp's BoundaryVote on class-1 foreground, using
  boundary probabilities; a conservative probability-informed alternative.
- `nbg-pb-h0.01-t0.3`: fbp's non-background foreground and
  probability-informed BoundaryVote strategy, without area filtering. This
  was an exploratory strategy, **not** a tuned best-of-fbp search.

fbp labels are scored as individual instance IDs, never as a binary union;
ignored pixels split disconnected pieces. Statistics are pooled across chips
before ratios are calculated. The files `chips.parquet` and `summary.json` in
each `prue-b7_<country>_methods` directory contain all method results.
New method comparisons on presence-only countries leave object precision,
F1/RQ and PQ undefined while retaining raw counts for diagnosis; see the
[presence-only rule](../../instance-metrics-contract.md). The three-country PQ table
below does not include Brazil. Do not extend a pooled PQ comparison to Brazil
without an independently defined reference-background policy.

Reproduction from the repository root (replace paths as appropriate):

```bash
for split in val test; do
  for country in portugal germany vietnam; do
    extra=()
    if [ "$split" = val ]; then extra=(--use_val_set); fi
    uv run ftw model test \
      --model "$HOME/working/models/ftw/FTW_PRUE_EFNET_B7.ckpt" \
      --dir "$HOME/data/labels/cropland/ftw" \
      --countries "$country" --model_predicts_3_classes \
      --test_on_3_classes --gpu -1 "${extra[@]}" \
      --save_probabilities \
      --out_dir "$HOME/working/ftw/metrics/$split/prue-b7_${country}_${split}_prob"
    uv run --with ../fbp python -m scripts.instance_evaluation.compare_instance_methods \
      "$HOME/working/ftw/metrics/$split/prue-b7_${country}_${split}_prob" \
       --strategies arg-ws2 arg-pb-h0.01-t0.3 nbg-pb-h0.01-t0.3 \
       --out_dir "$HOME/working/ftw/metrics/$split/prue-b7_${country}_methods"
  done
done
```

The three validation outputs used in the actual run were named
`prue-b7_<country>_val` (without `_prob`). The initial comparison used
`arg-ws2` and `nbg-pb-h0.01-t0.3`; `arg-pb-h0.01-t0.3` was evaluated in a
second comparison output named `prue-b7_<country>_argpb` per split. The
script at that time defaulted to all three strategies, producing the combined
comparison in one fresh output directory. Today's default is `ftw-2e`; the
explicit `--strategies` in the historical command above is required.
Output directories must not already exist. The dataset loader skips AOIs
missing a window or three-class mask: 9 of 12 Portugal validation AOIs were
evaluated, versus 30 Germany and 36 Vietnam; test counts are 10, 350, 23.
Earlier Portugal and Germany test summaries match the fresh probability runs
exactly in their baseline instance statistics and pixel comparisons.

## Validation selection and held-out test

Table entries are pooled **PQ** (higher is better). The initial methods were
compared on the three validation sets before their test runs. After reviewing
fbp's `arg-ws2` implementation, `arg-pb-h0.01-t0.3` was added as a separate
comparison: its validation runs preceded its test runs. No parameters were
tuned on the test split. The 4-connected baseline remains the established
choice. `arg-pb-h0.01-t0.3` is a conservative candidate for *opt-in*
product-level integration, not a demonstrated improvement over the baseline.

| Split | Country (chips) | 4 components | 8 components | fbp `arg-ws2` | fbp `arg-pb-h0.01-t0.3` | fbp `nbg-pb-h0.01-t0.3` |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Val | Portugal (9) | .0079 | .0079 | .0079 | .0079 | .0087 |
| Val | Germany (30) | .4564 | .4587 | .4619 | .4572 | .1197 |
| Val | Vietnam (36) | .1528 | .1423 | .1548 | .1536 | .1243 |
| Test | Portugal (10) | .0180 | .0172 | .0180 | .0180 | .0215 |
| Test | Germany (350) | .4143 | .4082 | .4189 | .4155 | .1224 |
| Test | Vietnam (23) | .1523 | .1505 | .1524 | .1524 | .1158 |

The unfiltered probability strategy gains recall in some cases but greatly
increases false positives: on Germany validation it has 1,724 FP versus 66
for 4-connected components; on test, 15,232 versus 634. Vietnam validation
has 12,705 FP versus 3,388. `arg-pb-h0.01-t0.3` barely changes the
baseline (Germany test: 617 FP instead of 634; the same 1,453 TP). `arg-ws2`
reduces Germany test FP from 634 to 567, but since its watershed decisions
are collapsed, this should not be described as a successful split method.
In Portugal the model covers very little reference field area (test recovery
.026). Read recovery, support, Rand split/merge and
chip-level examples alongside PQ before inferring product quality.

These results identify *candidates for opt-in Phase 4 integration*, not a
default CLI route or a production strategy winner. The FTW chip grids are
EPSG:4326: any fbp `+A` minimum area in m² requires a defensible pixel-area
conversion, so none was applied in this comparison. Large-scene window seams,
geographic CRS handling,
individual polygon identity, and final exported geometry still require
Phase 4 validation. The proposed ftw-tools repository migration is outside
this work.
