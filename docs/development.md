# Development and tests

## Where code and tests belong

| Role | Tools | Tests |
| --- | --- | --- |
| Supported offline evaluation | `scripts/instance_evaluation/` | `tests/instance_evaluation/` |
| Geometry workflows and implementation | `scripts/geometry/`, `ftw_tools/postprocess/` | `tests/geometry/` |
| Active instance-metric research | `research/instance_metrics/` | `tests/research/instance_metrics/` |
| Published-map descriptor pilot | `research/geometry/` | `tests/research/geometry/` |
| Preliminary component-review workflow | `research/instance_metrics/archive/` | `tests/research/instance_metrics/archive/` |

Other repository tests retain their existing locations. Archiving a study does
not invalidate tests of reusable matching/scoring behavior; those stay in the
supported groups. Historical workflow tests are preserved and **still collected
by default**. No tests are disabled merely by moving directories.

## Focused checks

On this macOS checkout use:

```sh
uv run --extra dev --extra fbp --with scikit-learn pytest --noconftest -n 0 \
  tests/instance_evaluation tests/geometry tests/research/instance_metrics tests/research/geometry
```

The existing `tests/conftest.py` session-finish hook calls `os._exit(0)` before
reporting failures and the final exit status. `--noconftest` avoids that hook for
focused checks; this reorganization does not change it. `scikit-learn` is needed
by complementarity research, not by polygon descriptor computation. Widget
tests skip if optional `ipywidgets` is absent.

Run modules from the repository root, for example:

```sh
uv run python -m scripts.instance_evaluation.visualize_instances --help
uv run python -m scripts.geometry.describe_field_dataset --help
uv run --with scikit-learn python -m research.instance_metrics.analyze_metric_complementarity --help
```

No compatibility wrappers are left at the old script locations: use the new
module paths. Saved analysis directories are not renamed or rewritten. Their
historical provenance continues to identify the code/settings originally used.
