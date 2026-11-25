# Instance-metric and geometry research

These are reports of work performed in this project, not external publications.
“FBP 0.2.0” identifies the package/preset version, not publication of an assessment.
For current commands and definitions, start with the [software guides](../README.md).

For interpreting reference-based scores, start with
[What the reference-based measures tell us about field maps](reference-metrics-synthesis.md).
It brings the established measures and both Chamfers together in one illustrated
analysis. The earlier metric reports are supporting methods and historical results.

| Report | Main question | Status |
| --- | --- | --- |
| [FTW_2E 0.2.0 assessment](ftw-2e-assessment.md) | Does this fixed post-processor improve the existing baseline? | Initial seven-country assessment complete; no consistent PQ gain established |
| [Reference and prediction identity](object-identity.md) | What changes when supplied reference IDs or FBP prediction IDs are preserved? | Initial audits and comparisons complete; Denmark provenance unresolved |
| [Reference-metric synthesis](reference-metrics-synthesis.md) | What do detection, overlap, partitioning and boundary distance each add? | Eleven-measure analysis, both reference definitions; Denmark excluded from main comparisons |
| [Schema-3 export validation](polygon-export-validation.md) | Do polygons and descriptors faithfully represent the saved instance labels? | Checked on one real Germany chip, not a large-area study |
| [Descriptor complementarity](descriptor-complementarity.md) | How much do field descriptors overlap, and where do they differ? | Initial full-primary-table associations/PCA complete; spatial sensitivity and feature recommendations open |
| [Regional landscape profiles](regional-landscape-profiles.md) | How do geometry measures summarize mapped field characteristics across pilot windows? | Regional methods and results for the 21 primary windows |
| [Lubushi–Bahia illustration](lubushi-bahia-landscape-illustration.md) | Can contrasting small-field and pivot landscapes share circularity but differ in size? | Complete for two approved/selected windows; size contrast and boundary-component interpretation |
| [Shape-assisted triage pilot](shape-triage-pilot.md) | Can shape help route exclusion, repair, retention and abstention candidates? | Proposal-only California demo; no corrections applied or accuracy claim |

These studies answer different questions. Export fidelity is not prediction
accuracy; changed reference grouping is not improved model output; correlated
scores are not necessarily interchangeable.

[Historical work](archive/README.md) contains early FBP comparisons, preliminary
component diagnostics, and the combined development record. They remain
available for tracing decisions without competing with current guidance.

Reusable analyses and notebooks are in
[`research/instance_metrics/`](../../research/instance_metrics/README.md).
Outstanding research, including further boundary-distance validation, is recorded in
the [to-do list](../instance-metrics-backlog.md).
