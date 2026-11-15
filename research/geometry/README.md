# Published-map geometry research

Study-specific infrastructure for the 2024 FTW 2nd Edition descriptor pilot.
Study commands are excluded from the installed `ftw-tools` package. Reusable code
is now an independently installable **local** `ftw-geometry` project nested here,
importing as `ftw_geometry`. It has no dependency on FTW training, inference, FBP
or research commands. Run study modules from the repository root.

```text
research/geometry/
  pyproject.toml               # Independent geometry dependency set
  ftw_geometry/
    core/descriptors.py       # Schema-3 measurements
    core/dataset.py           # Bounded dataset generation
    core/analysis.py          # Regional summaries and associations
    io/manifests.py           # Hashes and atomic manifests
    io/sources.py             # Remote snapshots and identities
    io/vectors.py             # Bounded HTTP/GeoParquet access
  configs/                    # Study configuration
  *_descriptor_pilot.py       # Study orchestration, excluded from geometry wheel
```

Install just reusable geometry, without the model stack:

```sh
uv pip install ./research/geometry
```

For this checkout, `uv sync --extra geometry` installs it editable through the
root's local UV source mapping. `uv sync --extra fbp` also includes the local
geometry package, preserving FBP descriptor-sidecar defaults. This project is
not yet published: do not release a root FTW distribution requiring this optional
dependency until the geometry distribution is available or release packaging is
explicitly revised. Pip users must install the local geometry project first.

| Module | Purpose |
| --- | --- |
| `pilot_sampling` | Study grid, crop screening, priorities and separated sampling |
| `select_descriptor_pilot` | Freeze study inputs and draw primary/reserve windows |
| `add_descriptor_pilot_diagnostic` | Supplementary user-selected windows |
| `retrieve_descriptor_pilot` | Geometry-preserving study extracts and outline maps |
| `describe_descriptor_pilot` | Assigned-field descriptor orchestration and maps |
| `refresh_descriptor_pilot_maps` | Verified map-only updates |
| `analyze_descriptor_pilot` / `report_descriptor_pilot` | Descriptive study associations/PCA and reporting |
| `build_descriptor_review_index` | Field-focused disagreement review links |

Configuration: `research/geometry/configs/ftw2e-descriptor-pilot-v1.json`.
Full instructions and artifact locations: [pilot guide](../../docs/descriptor-pilot.md).

```sh
uv run --extra geometry python -m research.geometry.select_descriptor_pilot --help
uv run --extra geometry python -m research.geometry.describe_descriptor_pilot --help
uv run --extra geometry python -m research.geometry.build_descriptor_review_index --help
uv run --extra dev --extra fbp pytest --noconftest -n 0 tests/geometry tests/research/geometry
```

Generic descriptor implementations are in `ftw_geometry.core`; the old
`ftw_tools.postprocess` descriptor modules are thin compatibility adapters only.
Generic dataset/analysis entry points remain in `scripts/geometry/`. Tests for this study
live in `tests/research/geometry/`.

## Relocation and historical runs

Moved here on 2026-11-14 from `scripts/geometry/`, with `pilot_sampling.py` removed
from `ftw_tools/postprocess/` and the study configuration removed from
`configs/geometry/`. No compatibility wrappers keep pilot research in the runtime
package. Use `python -m research.geometry.MODULE`, not the old module paths.

Existing external artifacts, hashes, historical commands and frozen source-code
snapshots were **not** rewritten. Those retain the paths/imports used at creation.
Replay historical code against its original checkout/environment, rather than
expecting old imports to work in the reorganized tree. A new selection run with
the moved code must use a fresh output directory because its code hashes differ;
this relocation is not a scientific rerun or a change to any draw/measurement.

The subsequent independent-package extraction retains compatibility imports for
generic descriptors, unlike the earlier removal of pilot command wrappers.
See [reproduction safeguards](../../docs/geometry-extraction-and-reproduction.md)
for the pre-extraction archive, install requirements and verification details.
