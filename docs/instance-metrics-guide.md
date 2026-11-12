# Reading field-instance metrics

For a task-oriented map of all guides, scripts, and notebook recipes, see the
[documentation and tools index](README.md) (README).

This guide explains the scores in `chips.parquet` and `summary.json`. For exact
valid-pixel and matching rules, see the [metric contract](instance-metrics-contract.md).
To render examples, see [offline evaluation](offline-instance-evaluation.md).

## What gets compared

A field is a connected component of class-1 interior pixels. Both reference and
prediction default to **4-connectivity**. Reference pixels labeled 3 or 255 (and
the configured `ignore_index`) are removed from *both* masks before extracting
instances. Class 0 is valid background; class 2 is a valid boundary pixel but
is not part of a field instance. Areas in these scores are pixel counts, not
square metres. Each chip is evaluated separately; objects are not joined across
chip edges.

Let reference field `j` have area `T[j]`, predicted field `i` have area `P[i]`,
and their shared field pixels number `I[i,j]`. Their IoU is
`I[i,j] / (P[i] + T[j] - I[i,j])`. A predicted field can intersect several
reference fields; an intersection alone is **not** an object match.

## Scores that require an object match

Eligible pairs have IoU **strictly greater than 0.5** by default. Matching is
one-to-one, maximizing the number of eligible pairs and then their summed IoU.
Unmatched predictions are FP; unmatched references are FN.

Presence-only countries (currently Brazil, India, Kenya, and Rwanda) have no
labeled background, so FP counts on their labeled domain are diagnostics,
**not evaluable false-positive counts**. New outputs leave their object
precision, F1/RQ and PQ undefined, including for pooled runs containing any
of them. Recall and overlap-based diagnostics remain available,
but the latter cannot validate precision in unlabeled territory. `SQ` describes
only qualifying matched fields and is still available when there is a match.
The original evaluation code did print Brazil precision, but that value should
not be compared as a valid object-precision score.

| Score | Calculation | What a high value means |
| --- | --- | --- |
| Object precision | `TP / (TP + FP)` | Most predicted fields qualify as matches. |
| Object recall | `TP / (TP + FN)` | Most reference fields qualify as matches. |
| Object F1 / RQ | `2 TP / (2 TP + FP + FN)` | A balance of object precision and recall. |
| SQ | `sum(matched IoU) / TP` | Matched fields fit their references well. |
| PQ | `RQ * SQ` | Both detection and matched-field fit are good. |

SQ considers only **matched** fields; high SQ with low RQ does not imply good
overall delineation. SQ is undefined when `TP = 0`. When there are unmatched
objects but no TP, PQ is 0. Object precision or recall with no denominator is
undefined; if both sides contain no fields, RQ and PQ are undefined.

## Scores without an IoU match threshold

**Recovery** (`recovery`) gives every reference field its
best IoU among predictions, weights that IoU by its reference area, and divides
by total reference-field area. A missed reference has best IoU 0. **Support**
(`support`) reverses the direction: every predicted field
gets its best reference IoU, weighted by its *full predicted area*, including
area beyond reference fields. Neither score is object precision or recall. An
absent source-side field population makes that direction undefined.

**Rand split** and **Rand merge** use all intersection areas, not accepted
matches or even per-field IoUs. Write `N = sum(I[i,j] ** 2)`:

```text
rand_split = N / sum(T[j] ** 2)
rand_merge = N / sum((sum_j I[i,j]) ** 2)
```

The merge denominator counts only the portion of each prediction **on reference
foreground**. Predicted area outside reference fields does not directly lower
Rand merge; support is a complementary check. Missing reference-field area
lowers Rand split, even if no field is broken into multiple pieces. If reference
fields exist but there is no prediction overlap, Rand merge is 0. Undefined
ratios (including a chip with no reference fields) are recorded as `NaN` in
Parquet and `null` in JSON.

Consider two equal reference fields: if each stays covered but both are joined
into one prediction, split is 1 and merge is 0.5. Conversely, if one reference
is fully covered by two equal predictions, split is 0.5 and merge is 1. In real
chips, missing coverage and extra predicted area complicate those simple
patterns; read recovery, support, and object counts alongside the Rand scores.

### Worked Germany example: `g1_00001_10`

This test chip has **19 reference fields** (4,634 class-1 pixels). The model
predicted **four** small fields (243 class-1 pixels), all within *one* of the
references. Their overlaps with that reference are 230, 2, 8, and 3 pixels.
No pair exceeds IoU 0.5: `TP = 0`, `FP = 4`, `FN = 19`.

```text
N = 230² + 2² + 8² + 3² = 52,977
rand_split = 52,977 / 3,051,286 = 0.0174
rand_merge = 52,977 / 52,977   = 1.0000
recovery = 0.0496; support = 0.2038
```

Merge is 1 because no predicted field mixes *different* reference fields.
Split is near zero primarily because 18 references are missed and the touched
field is only partly covered. The high merge score does **not** mean this chip
was segmented well.

## Pooling chips and reading figures

For a country, sum the `stat_*` columns and then calculate the ratios permitted
by its evaluation policy (for presence-only countries, not FP-dependent ratios).
Do **not**
average chip ratios: chips differ in field counts and areas. `summary.json`
contains these pooled scores, while `chips.parquet` contains the individual
diagnostics. The figure renderer ranks `rand-split-merge` examples by absolute
score gap; a large gap is a *prompt to inspect the masks*, not a quality rank.
Figures include object counts, RQ/SQ/PQ, recovery/support and field-interior
pixel IoU where evaluable. Presence-only figures omit FP outlines and show FP-dependent
scores as unavailable; its recall and coverage diagnostics still help identify
misses and splits.
