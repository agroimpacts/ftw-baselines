# Instance evaluation and map geometry

These pages separate **using the software**, **research findings**, and
**earlier experiments**. Start with a guide rather than an experiment log.

## Using the software

| Task | Guide |
| --- | --- |
| Understand object scores, coverage, splits and merges | [Reading instance metrics](instance-metrics-guide.md) |
| Check exact matching, masking and undefined-score rules | [Scoring contract](instance-metrics-contract.md) |
| Save predictions, inspect chips and compare post-processing methods | [Offline evaluation](offline-instance-evaluation.md) |
| Export field polygons and understand their geometry measures | [Polygon export and descriptors](polygon-export-and-descriptors.md) |
| Build descriptor tables, summarize regions and study shape relationships | [Geometry analysis](geometry-analysis.md) |
| Install independent geometry tooling or reproduce pre-extraction runs | [Geometry extraction and reproduction](geometry-extraction-and-reproduction.md) |
| Select published prediction maps for descriptor complementarity research | [2024 descriptor pilot](descriptor-pilot.md) |
| Explore relationships between reference-dependent scores | [Chip-score analysis](chip-score-analysis.md) |

Commands use `uv run python -m …` from the **repository root**. This keeps imports
working consistently for tools in different directories. See the
[tool inventory](../scripts/README.md) for their locations.

## Research findings

Start with [What the reference-based measures tell us about field maps](research/reference-metrics-synthesis.md):
one illustrated synthesis of detection, overlap, split/merge and boundary-distance
results, including both reference definitions. Earlier stage reports support this
account rather than provide separate introductions.

The [research index](research/README.md) links the FTW_2E 0.2.0 assessment,
object-identity investigation, metric-complementarity study and export-validation
report. These are local research reports, **not claims of external publication**.
Initial component diagnostics and pre-0.2.0 FBP comparisons are under
[historical work](research/archive/README.md), not current recommendations.

## Current status and outstanding work

See [status](instance-metrics-progress.md), [research and development to-dos](instance-metrics-backlog.md),
and [scope and design decisions](instance-metrics-implementation-plan.md).

The existing reference metrics have been implemented and analyzed, but the
reference-metric research is **not finished**: Chamfer complementarity analyses
are complete, while independent imagery review and resolution/edge sensitivity remain open.

The descriptor/export workflow was initially checked on one Germany chip with
13 predicted polygons. The [published-map pilot](descriptor-pilot.md) now has
schema-3 tables and colored maps for 59,350 assigned primary fields plus 69
separate diagnostic fields. [Initial descriptive associations/PCA](research/descriptor-complementarity.md)
are complete. The user has reviewed disagreements; a written synthesis, spatial
uncertainty and practical feature selection remain outstanding.
[Regional landscape profiles](research/regional-landscape-profiles.md) now summarize
all 21 primary windows, including all shape descriptors and edge-guarded spacing.
The [Lubushi–Bahia illustration](research/lubushi-bahia-landscape-illustration.md)
is complete for the approved Zambia window and separate Bahia pivot diagnostic.
It shows a strong size contrast and how internal boundaries reduce circularity
even in near-circular pivots. The backlog stages
a narrow-neck repair-agent pilot, geometry–segmentation performance
research and interpretable landscape synthesis/queries.

**Reference coverage matters:** Brazil, India, Kenya and Rwanda have presence-only
labels, not fully labeled background. Their object precision, F1/RQ and PQ are
not evaluable, including when pooled with other countries. Older artifacts may
still contain numerical values for these scores; consult the
[contract](instance-metrics-contract.md) before citing them.

## Development

The [testing guide](development.md) explains the supported-tool, research and
historical test groups. This reorganization does not prepare a PR or change
the scoring rules, model predictions or saved analysis outputs.
