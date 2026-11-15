# Geometry extraction and historical reproduction

Reusable geometry is an independently installable **local**, unpublished project
at `research/geometry/`: distribution `ftw-geometry==0.1.0`, import `ftw_geometry`.
Its wheel contains `core/` (descriptors, datasets, analysis) and `io/` (manifests,
snapshots, identities, remote GeoParquet access), not study orchestration. It has
geometry-only dependencies and imports no FTW, research, Torch, Lightning or FBP.

The old `ftw_tools.postprocess.descriptors`, `descriptor_dataset` and
`descriptor_analysis` are thin compatibility adapters to the same functions,
not duplicated algorithms. The FBP adapter, CLI dispatch, default semantic
polygonization, training metrics and matching are unchanged. FBP sidecar defaults
are preserved through an explicit optional geometry dependency. Research commands
and general descriptor workflows now import geometry directly.

## Installation

```sh
uv sync --extra geometry
uv run --extra geometry python -m research.geometry.select_descriptor_pilot --help
uv sync --extra fbp       # also includes geometry for existing FBP sidecars
```

Root UV sources/lock resolve geometry to the editable local project. Existing
external dependency versions were not updated. Geometry without the model stack:

```sh
uv pip install ./research/geometry
# Optional plots: uv pip install './research/geometry[visualization]'
```

Pip users should install the local geometry project before FTW's FBP extra.
**Do not publish a root FTW distribution depending on this optional version until
the geometry distribution is available or release packaging is explicitly revised.**
Neither project is being published as part of this work.

## Historical code and results

Pre-extraction checkout archive:
`~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/pre-extraction-20261114T221928Z/`.

It contains the tracked **and uncommitted/untracked source**, dependency versions,
Python version, Git revision/diff and source/archive hashes. To replay historical
code, extract `checkout.tar.gz` into a separate directory, use the recorded
environment and run from that checkout into fresh result directories. The Git
revision alone is insufficient because source was uncommitted. Never reset the
current tree or overwrite historical runs to restore that version.

Frozen results, maps, source snapshots and manifests are not rewritten. Compatibility
imports preserve API behavior, **not source-file hashes**. Dataset/selection
fingerprints intentionally reject changed code: new code needs new output
directories. Do not edit old manifests to force resumption. Original snapshots
retain their historical imports and should run against their original checkout.

## Verification

- Archived checkout extracted separately: **67 tests passed**.
- New checkout: **69 tests passed**, including old import compatibility and an
  isolated interpreter test prohibiting FTW/research/Torch/Lightning/FBP imports.
- Descriptor module AST identical to its pre-extraction implementation.
- Existing FBP tests still check sidecars, read-back measurements and CLI defaults.
- Independent geometry source distribution and wheel built successfully.
- Frozen artifact hashes are checked separately from code tests.

This supports unchanged algorithms and artifacts, not bitwise equality under
arbitrary future GDAL/GEOS/dependency versions or changed remote sources.
