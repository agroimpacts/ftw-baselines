# Instance-metric and geometry research

These are reports of work performed in this project, not external publications.
“FBP 0.2.0” identifies the package/preset version, not publication of an assessment.
For current commands and definitions, start with the [software guides](../README.md).

| Report | Main question | Status |
| --- | --- | --- |
| [FTW_2E 0.2.0 assessment](ftw-2e-assessment.md) | Does this fixed post-processor improve the existing baseline? | Initial seven-country assessment complete; no consistent PQ gain established |
| [Reference and prediction identity](object-identity.md) | What changes when supplied reference IDs or FBP prediction IDs are preserved? | Initial audits and comparisons complete; Denmark provenance unresolved |
| [Metric complementarity](metric-complementarity.md) | What different information do the existing scores retain? | Eight-score study complete; boundary-distance extension outstanding |
| [Schema-3 export validation](polygon-export-validation.md) | Do polygons and descriptors faithfully represent the saved instance labels? | Checked on one real Germany chip, not a large-area study |

These studies answer different questions. Export fidelity is not prediction
accuracy; changed reference grouping is not improved model output; correlated
scores are not necessarily interchangeable.

[Historical work](archive/README.md) contains early FBP comparisons, preliminary
component diagnostics, and the combined development record. They remain
available for tracing decisions without competing with current guidance.

Reusable analyses and notebooks are in
[`research/instance_metrics/`](../../research/instance_metrics/README.md).
Outstanding research, including object-boundary Chamfer distance, is recorded in
the [to-do list](../instance-metrics-backlog.md).
