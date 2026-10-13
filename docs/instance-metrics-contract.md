# Instance metric contract

`ftw_tools.training.metrics.instance_statistics` evaluates aligned 2D semantic
class arrays. Class 1 is field interior; class 0 is valid background, including
when raster metadata calls 0 nodata. Class 2 is a valid boundary/background for
instance extraction. Reference values 3 and 255 are excluded from **both** masks;
an optional training `ignore_index` is also excluded. No raster nodata mask is
applied. Two-class models use 0/1; a boundary-free gap that connects fields will
merge them. Both reference and prediction components default to 4-connectivity,
as in the existing ftw-baselines Rasterio polygon extraction. Both can be set to
8 for explicit offline comparisons. Invalid pixels separate components.

Pairs qualify only at **IoU > threshold** (default 0.5). Assignment maximizes
the number of qualifying pairs, then their total IoU, one-to-one. With the
existing minimum threshold of 0.5, qualifying pairs of disjoint instances are
unique: strict IoU > 0.5 prevents two references from matching one prediction
or vice versa. Thus assignment retains the old first-match TP/FP/FN and object
precision/recall/F1 for the same valid masks and 4-connectivity. Results may
differ on ignored pixels (now removed from both sides), undefined/no-match
ratios (the former validation and offline paths disagreed), or when selecting
8-connectivity or a threshold below 0.5. The sibling FTW raster adapter uses
8-connectivity; its scores should not be compared without matching extraction
settings. RQ = object F1;
SQ = matched IoU sum / TP; PQ = RQ * SQ. Recovery (truth-to-prediction) and
support (prediction-to-truth) are area-weighted best IoUs without thresholding.
Rand split and merge use the sum of squared intersection areas divided by the
sum of squared reference areas and squared predicted areas *on reference
foreground*, respectively. Predicted area outside reference foreground affects
support but not Rand merge. All areas here are pixel counts, not square metres:
aligned chips have equal-area pixel cells; no local CRS is required for this API.

Undefined ratios (zero denominator) are NaN. An empty chip contributes zero
sufficient statistics; when one side alone is empty, defined object ratios are
zero, and PQ is zero. When both are empty, PQ is NaN. SQ without matches is NaN.
Pool statistics across chips, batches, workers or regions *before* taking ratios;
do not average chip scores. Chip-boundary objects are not stitched across chips.
Metre-based polygon descriptors will require a suitable projected CRS separately.

Definitions adapted from the local `../evaluation/metric_package/src/field_shape_metrics/`
snapshot (`evaluation.py`, `ftw_input.py`); this implementation uses raster
intersection counts rather than transferring source code. Provenance and license
of the snapshot must be confirmed before any direct code transfer.
