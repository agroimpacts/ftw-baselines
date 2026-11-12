# Instance-metric research tools

These tools operate on saved evaluation artifacts. They are reusable research
utilities, not evidence that a study has been run. See the
[research reports](../../docs/research/README.md) for interpreted findings.

| Tool | Purpose |
| --- | --- |
| `analyze_instances.py` | Chip-score correlations, scatterplots and regressions; shared compatible-run loader |
| `analyze_metric_complementarity.py` | Associations, PCA, reconstruction and disagreement analyses, plus supplied-reference-ID rescoring controls |
| `assess_instance_measures.py` | Paired score differences between post-processing methods and pooled diagnostics |
| `notebooks/metric-methods-comparisons.ipynb` | Mixed exploratory notes and later FBP comparisons; retained outputs belong to their original experiments |

Run from the repository root, for example:

```sh
uv run --with scikit-learn python -m research.instance_metrics.analyze_metric_complementarity --help
```

Complementarity research is active: [boundary Chamfer distance](../../docs/instance-metrics-backlog.md#ref-1-boundary-chamfer-distance)
still needs definition, tests, real-data assessment and comparison with the
existing metrics. No boundary-distance implementation is included yet.

`archive/` preserves the preliminary component-diagnostics, manual-review helper,
widget and notebook together. Their [guide](../../docs/research/archive/components4-metric-diagnostics.md)
explains the old experiment. Nothing in current workflow code depends on them.
Tests live under `tests/research/instance_metrics/`, including `archive/`, and
remain part of normal collection.

Notebooks need repository imports available. Start Jupyter in the repository
root; the archived review notebook also locates the repository from nested
working directories. Do not rerun historical notebooks indiscriminately: they
contain local paths and experiment-specific operations.
