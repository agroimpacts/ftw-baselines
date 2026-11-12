# How object identity changes instance scores

## Question and main findings

Do scores change when we preserve supplied field IDs rather than reconstructing
objects from connected pixels? And does masking split an FBP prediction into
several scored objects?

**Yes. Object grouping can substantially change a score without changing any
prediction pixels.** Supplied IDs are not automatically validated field truth:
Denmark's grouping still needs provenance review. Preserving FBP prediction IDs
changed the seven-country results only in Brazil, where ignored areas fragment
some predictions.

## Two independent choices

| Choice | Default | Explicit offline alternative |
| --- | --- | --- |
| Reference identity | Separate four-connected patches of class-1 pixels | `--reference-mode dataset-instance-ids`: keep pixels with the same supplied positive ID together, even if disconnected |
| Prediction identity | `split-components`: split FBP labels into connected pieces after masking | `--prediction-identity preserve-ids`: keep surviving pixels of each FBP ID together |

Semantic labels still define valid pixels. Supplied-reference foreground must
agree with semantic class 1 there, and rasters must align. Sparse IDs are
compacted; wholly masked IDs disappear. Component methods retain their requested
connectivity. Neither alternative changes training, probabilities or defaults.

## Reference-ID audit and comparison

All paired masks for the 1,469-chip cohort were aligned and had exactly matching
foreground. Counts sum chip-local objects, not unique fields across chips.

| Country | Supplied IDs | Four-connected reference components |
| --- | ---: | ---: |
| Belgium | 6,498 | 7,541 |
| Cambodia | 15,370 | 15,811 |
| Brazil | 689 | 898 |
| Croatia | 15,191 | 18,648 |
| Denmark | 1,597 | 6,674 |
| Germany | 2,867 | 4,043 |
| Vietnam | 10,490 | 11,224 |
| Total | 52,702 | 64,839 |

Four-connectivity fragmented 5,128 supplied IDs across 1,043 chips and merged IDs
in 240 chips. Eight-connectivity also fragmented and merged IDs, so changing
connectivity is not an identity repair.

Country-pooled PQ in the reference-only follow-up:

| Country | Components-4, semantic refs | Components-4, supplied IDs | FTW_2E, supplied IDs |
| --- | ---: | ---: | ---: |
| Belgium | .5485 | .5892 | .5643 |
| Cambodia | .2499 | .2542 | .2811 |
| Croatia | .3484 | .3842 | .3913 |
| Denmark | .5672 | .1810 | .1856 |
| Germany | .4143 | .4946 | .4917 |
| Vietnam | .1523 | .1595 | .1506 |
| Brazil (presence-only) | — | — | — |

Denmark's supplied IDs group many separate components. The score reduction is
not proof those IDs are wrong, but it prevents treating them uncritically as
individual-field identity. Under supplied-ID references FTW_2E still showed no
universal gain. No parameters were tuned or uncertainty intervals computed.

For Germany `g1_00003_16`, references changed from 63 components to 47 supplied
IDs. All methods retained 10 TP; recall rose from .1587 to .2128. The predictions
did not improve—only the denominator and reference grouping changed.

## Preserving prediction IDs

All 41,957 raw FBP IDs were four-connected before masking. Fragmentation after
masking occurred only in Brazil: 355 surviving IDs fragmented across 126 chips;
1,465 IDs disappeared entirely. Across the cohort there were 40,492 surviving
IDs versus 42,390 post-mask components.

The six fully labeled countries had identical statistics and scores in both
prediction modes, so their supplied-ID PQ table above also applies to preserved
predictions. Component-method results were unchanged everywhere.

Brazil FTW_2E recall fell from .9492 with split predictions to .7707 with preserved
IDs. Pieces belonging to one prediction can no longer match several references
independently: IoU uses their combined surviving area and matching is one-to-one.
This is an identity/masking interaction, not changed model output. Brazil's
precision and PQ remain undefined.

## Artifacts and further analysis

Reference-mode outputs are nested under each original country assessment at
`reference-modes/dataset-instance-ids/`. Preserved-prediction outputs are nested
within those at `prediction-modes/preserve-ids/`. Each has separate scores and
metadata; the original assessments were not overwritten.

Use [current commands](../offline-instance-evaluation.md#compare-post-processing-methods)
for reproduction into new paths. The
[development record](archive/assessment-development-record.md#reference-identity-audit-and-opt-in-assessment-2026-11-05)
retains detailed audits and original commands. The subsequent
[25-country complementarity study](metric-complementarity.md) tested how reference
identity affects relationships between metrics, with explicit population controls.
