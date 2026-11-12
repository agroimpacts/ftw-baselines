# Test organization

- `instance_evaluation/`: scoring contracts, pixel scores, artifacts, visualization
  and method-comparison behavior.
- `geometry/`: descriptors, export fidelity and larger-area analysis tools.
- `research/instance_metrics/`: active analysis methods and reference-rescoring controls.
- `research/instance_metrics/archive/`: preserved preliminary diagnostics and review UI.
- Existing unrelated tests remain at this directory's top level.

Historical tests are still collected by default. Their location marks the purpose
of the workflow, not permission to remove coverage. See
[development instructions](../docs/development.md) for focused commands and the
existing session-finish-hook caveat.
