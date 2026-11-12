# Workflow tools

Run modules from the repository root with `uv run python -m MODULE --help`.

| Directory | Tools and purpose |
| --- | --- |
| `instance_evaluation/` | `audit_instance_chip`, `visualize_instances`, `compare_instance_runs`, `compare_instance_methods`, `visualize_instance_methods` |
| `geometry/` | `describe_field_dataset`, `analyze_field_descriptors`, `validate_instance_polygon_export` |

Method comparison and export validation use the optional `--extra fbp` environment.
The [offline guide](../docs/offline-instance-evaluation.md) and
[geometry guide](../docs/geometry-analysis.md) provide examples.

Research analyses are in [`research/instance_metrics/`](../research/instance_metrics/README.md),
not mixed with supported workflow entry points. Their preliminary review tools
are archived separately. The old flat script paths have moved; use module paths
such as `scripts.instance_evaluation.audit_instance_chip`.

`add_edges_to_dataset.py` is an unrelated data-preparation utility and has not moved.
