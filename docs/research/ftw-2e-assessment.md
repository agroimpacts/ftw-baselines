# FTW_2E 0.2.0 assessment: seven countries

## Question and main finding

Does the unchanged `FTW_2E` preset from FBP 0.2.0 improve instance delineation
relative to four-connected semantic components?

**There was no consistent across-country PQ gain.** Defaults were not changed.
This is a local research assessment, not an externally published study.

## Data and setup

The study used the same PRUE EFNet B7 checkpoint and saved three-class probability
rasters for all methods: 1,469 test chips across Belgium (198), Cambodia (25),
Brazil (188), Croatia (353), Denmark (332), Germany (350) and Vietnam (23).
Checkpoint SHA-256:
`2b1b34a17b85b8f70da6ff737529743b6bc6049e987bce5a1fcdd7279eb3b120`.

No parameter sweep or tuning on test results was performed. This original
comparison used semantic-component references and split-component prediction
identity. Later supplied-ID and preserved-prediction studies are reported
[separately](object-identity.md); do not mix their absolute scores.

## Results

These are country-pooled PQ values, calculated from summed sufficient statistics,
not averages of chip scores.

| Country | Components-4 PQ | FTW_2E PQ | Difference |
| --- | ---: | ---: | ---: |
| Belgium | .5485 | .5234 | -.0251 |
| Cambodia | .2499 | .2762 | +.0263 |
| Croatia | .3484 | .3521 | +.0037 |
| Denmark | .5672 | .5650 | -.0022 |
| Germany | .4143 | .4080 | -.0063 |
| Vietnam | .1523 | .1435 | -.0088 |
| Brazil (presence-only) | — | — | — |

FTW_2E increased precision in five of the six fully labeled countries, but
reduced recall in all except Cambodia. Recovery/support also fell in those five;
both Rand scores rose in all six. Better partition diagnostics therefore did
not imply better overall delineation. Brazil recall changed from .7394 to .7439;
its precision and PQ cannot be evaluated from presence-only labels.

## Limits

No uncertainty intervals were computed for this fixed-preset assessment.
It evaluates raw instances, not the catalog's full polygon pipeline. Saved
geographic grids were not resampled: the fixed 900 m² filter used chip-mean
geodesic pixel area. Transfer from the preset's native 2.5 m data is a limitation;
saved floats are quantized internally by `fast=True`.

The findings neither select a universal winner nor establish production-scale
inference/export performance. See [export validation](polygon-export-validation.md)
for the different question of preserving IDs and geometry.

## Reproduction and artifacts

Outputs are under
`~/working/ftw/metrics/test/prue-b7_ftw-2e_0.2.0_assessment/<country>/`.
They reuse saved inputs and contain chip tables and pooled summaries; labels
are cached only when requested. Do not overwrite these directories.

Use the [current method-comparison instructions](../offline-instance-evaluation.md#compare-post-processing-methods)
with new output paths. The [development record](archive/assessment-development-record.md#ftw_2e-020-follow-up-2026-11-05)
preserves original commands and details. Pre-0.2.0 string strategies are
[historical experiments](archive/early-fbp-comparison.md), not this preset.
