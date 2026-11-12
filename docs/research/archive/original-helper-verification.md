# Verify the historical object-count helper

This read-only procedure compares the audit's `original_counts()` with the
actual `get_object_level_metrics()` from trusted local commit `9edc34b`.
No checkout/reset or model inference is needed. It verifies the old helper,
not the current scoring policy on ignored pixels.

Run from the repository root. Generated checks need no dataset; change `root`
for the three saved-chip checks, which require the original local artifacts.

```sh
uv run python - <<'PY'
import subprocess
import types
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from scripts.instance_evaluation.audit_instance_chip import original_counts

revision = "9edc34b"
source = subprocess.run(
    ["git", "show", f"{revision}:ftw_tools/training/metrics.py"],
    check=True, capture_output=True, text=True,
).stdout
historical = types.ModuleType("historical_metrics")
exec(compile(source, f"{revision}:metrics.py", "exec"), historical.__dict__)

rng = np.random.default_rng(2718)
for threshold in (0.5, 0.7, 1.0):
    for _ in range(200):
        truth = rng.choice([0, 1, 2, 3], (8, 9), p=[.45, .35, .1, .1]).astype("uint8")
        pred = rng.choice([0, 1, 2], (8, 9), p=[.55, .35, .1]).astype("uint8")
        assert original_counts(truth, pred, threshold) == historical.get_object_level_metrics(truth, pred, threshold)

root = Path.home() / "working/ftw/metrics/test"
for country, chip in (
    ("belgium", "g2_00041_4"),
    ("brazil", "g4_0000005632-0000004096"),
    ("germany", "g1_00010_2"),
):
    run = root / f"prue-b7_{country}_test_prob"
    row = pd.read_parquet(run / "chips.parquet").query("aoi_id == @chip").iloc[0]
    with rasterio.open(row.reference) as raster:
        truth = raster.read(1)
    with rasterio.open(run / row.prediction) as raster:
        pred = raster.read(1)
    actual = historical.get_object_level_metrics(truth, pred)
    audited = original_counts(truth, pred, 0.5)
    assert audited == actual, (country, chip, audited, actual)
    print(f"{country}/{chip}: original = audit = {actual}")
print("600 generated pairs and three saved chips agree")
PY
```

Expected old-helper TP/FP/FN: Belgium `18/4/20`, Brazil `2/26/15`, Germany `2/3/2`.
The current scorer removes ignored pixels from both sides and gives Brazil FP
`0` on that example. Neither old nor current raw FP counts establish precision
for presence-only references. These checks do not verify the entire historical
evaluation pipeline. Return to the [current audit guide](../../offline-instance-evaluation.md#audit-object-counts).
