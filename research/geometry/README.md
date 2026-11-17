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
| `summarize_descriptor_pilot` | Regional profiles of all primary windows, with edge-guarded spacing sensitivity |
| `prepare_zambia_landscape_diagnostic` | Bounded original-polygon extraction and proposed Lubushi outline review; no descriptor assessment before approval |
| `compare_landscape_illustrations` | Approved cross-source Lubushi–Bahia descriptors, regional profiles, joint distributions and boundary interpretation |
| `triage_descriptor_pilot` | Proposal-only four-outcome review: exclude, repair, retain or abstain; original maps unchanged |
| `review_triage_repairs` | User-labeled targeted split-set and exact-union previews; no correction/apply stage |

Configuration: `research/geometry/configs/ftw2e-descriptor-pilot-v1.json`.
Full instructions and artifact locations: [pilot guide](../../docs/descriptor-pilot.md).

Regional analysis of the existing frozen pilot extracts and assigned descriptors:

```sh
uv run --extra geometry python -m research.geometry.summarize_descriptor_pilot \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/polygon-review-2024 \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/descriptor-review-2024 \
  --out_dir ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/regional-landscape-2024-v2
```

Use a fresh output directory. The command excludes the diagnostic, preserves all
21 primary windows and reuses their frozen assigned measurements. Additional
intersecting fields supply geometry for coverage/context, in each window's CRS;
their descriptors are left null because they do not enter shape summaries.
Spacing summaries at 50/100/250 m retain only fields with full search context
inside the extraction window. No halo downloads, repairs or reference evaluation
are performed. The [backlog](../../docs/instance-metrics-backlog.md) stages the
Zambia–Bahia illustration, subsequent narrow-neck repair pilot and later
geometry–accuracy and landscape-synthesis work.

The Zambia stub has now advanced to a completed user-selected Lubushi–Bahia illustration.
See [the assessment notes](../../docs/research/lubushi-bahia-landscape-illustration.md)
for the approved window, source terms, commands, results and limits. Reproduce the
comparison without another country scan:

```sh
uv run --extra geometry python -m research.geometry.compare_landscape_illustrations \
  ~/working/ftw/metrics/landscape-illustrations/mapping-africa-zambia-lubushi-2024-v1/window-review \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1 \
  --out_dir ~/working/ftw/metrics/landscape-illustrations/lubushi-bahia-2024-v3 \
  --approve_window
```

Use a fresh output directory. Source attributes are namespaced, original Bahia
descriptors are reused, and both examples stay outside the primary FTW sample.
Supplementary boundary diagnostics retain the standard hole-inclusive circularity
definition and do not filter the regional populations. Existing map/profile
renderers accept explicit population labels; no old artifacts are regenerated.

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

## Shape-assisted triage demo

The user-approved GEO-3 extension now includes possible false-field exclusions,
joined-field repairs, valid single fields and abstentions. The initial California
demo and approval boundaries are documented in the
[triage pilot report](../../docs/research/shape-triage-pilot.md).

```sh
uv run --extra geometry python -m research.geometry.triage_descriptor_pilot \
  ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1 \
  --out_dir ~/working/ftw/metrics/descriptor-pilot/ftw2e-descriptor-pilot-v1/triage-review-2024-v2
```

Open the new `index.html`. Screening thresholds are exploratory, not calibrated.
Record assessments and export labels; exports do not authorize application.
There is no apply command and no original geometry is modified. Use a fresh output
directory; `triage-review-2024-v1/` is the initial frozen demo.

The subsequent `targeted-repair-review-2024-v1/` uses the user's 17 exported
assessments and corrected `8571`–`8581` merge partner. It shows coordinated split
sets, an unresolved three-field case and a still-multipart exact union. The
[report](../../docs/research/shape-triage-pilot.md#targeted-second-review-split-sets-and-fragment-union)
gives the command, validations and review instructions. Split-set generation
requires Shapely >=2.1 / GEOS >=3.10. Preferences do not authorize application;
boundary completion and actual corrections remain future work.

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
