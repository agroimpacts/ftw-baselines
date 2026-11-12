# Scope and design decisions

Current scope, **2026-11-12**. This page records ownership and decisions, not a
second task checklist. See [status](instance-metrics-progress.md) and
[outstanding work](instance-metrics-backlog.md).

## Responsibilities

- **FBP** supplies predicted integer instance labels. The optional integration
  uses the unchanged `FTW_2E` preset from `ftw-fbp[fast]==0.2.0`.
- **ftw-baselines** supplies georeferencing, ID-preserving polygonization,
  explicit cleanup/export, geometry descriptors, scoring and offline tools.
- **The global catalog** would own orchestration, global seam ownership,
  contextual filtering and publication. Those are not implemented here.
- The local `../evaluation/metric_package/` is a definition/parity reference,
  not a runtime dependency. Definitions were implemented independently; direct
  source transfer would need a provenance/licensing review.

## Scoring decisions

The adopted default retains four-connectivity, valid-domain masking and strict
IoU thresholding for compatibility with ftw-baselines. An early proposal used
eight-connectivity and inclusive matching; that proposal is not the contract.
Eight-connectivity and alternative identity modes remain explicit offline choices.
See the [contract](instance-metrics-contract.md) for exact definitions.

Initial assessments did not establish a consistent across-country PQ gain for
FBP, and no test-based parameter sweep was selected. The FBP 0.1.0 experiments
are historical; they are not results for the 0.2.0 preset. Changing the reference
grouping changes the question being scored, not the predictions.

Reference metrics are not a closed research program. The
[boundary-distance investigation](instance-metrics-backlog.md#ref-1-boundary-chamfer-distance)
must decide its pairing and aggregation contract before implementation.

## Geometry decisions

Preserve individual IDs, reunite only same-ID vectorization fragments, preserve
holes unless explicitly removed, and give multipart pieces stable part IDs.
Measure the final persisted geometry, not an earlier intermediate raster shape.

Schema 3 retains circularity once, removes redundant transforms and the
unit-dependent fractal index, and exposes orientation ambiguity explicitly.
The [descriptor guide](polygon-export-and-descriptors.md) is authoritative.

Geometry generation is bounded-batch and resumable. Regions require explicit
surveyed domains and edge/duplicate/fragment policies. Exact regional operations
have a field cap; correlation/PCA sampling and interval limitations are explicit
in the [workflow](geometry-analysis.md). Automatic stitching, near-duplicate
resolution, clustering and global inference are outside the implemented tools.

## Documentation and repository boundaries

- Current guides describe software behavior and commands.
- `docs/research/` contains interpreted findings; its archive contains preliminary
  studies and development history.
- `scripts/` contains supported workflow tools; `research/instance_metrics/`
  contains active analysis tools/notebooks, with preliminary workflows archived.
- Tests follow those roles, with historical tests still collected by default.

Research remains in this repository for now, organized so it can be separated
later. No repository migration, PR preparation, new branch or default change is
part of this reorganization. Future PR scope and upstream/base must be agreed
separately rather than inferred from the current broad feature branch.
