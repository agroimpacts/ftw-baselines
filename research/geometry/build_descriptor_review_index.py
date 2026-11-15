"""Build direct field-focus links for existing disagreement candidates."""

import argparse
import json
import os
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode

import pandas as pd
from ftw_geometry.io.manifests import file_digest, write_json

from research.geometry.select_descriptor_pilot import now


def field_link(root, maps, window_id, field_id, feature):
    relative = Path(os.path.relpath(maps / window_id / "review.html", root)).as_posix()
    return (
        relative
        + "#"
        + urlencode({"field": str(field_id), "feature": feature}, quote_via=quote)
    )


def build(analysis, maps, out):
    analysis, maps, out = (
        Path(p).expanduser().resolve() for p in (analysis, maps, out)
    )
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a fresh review-index directory")
    for root in (analysis, maps):
        manifest = json.loads((root / "complete.json").read_text())
        for name, digest in manifest["output_sha256"].items():
            if file_digest(root / name) != digest:
                raise ValueError(f"Changed input: {root}/{name}")
    fields = pd.read_parquet(maps / "primary-descriptors.parquet")
    if (
        file_digest(maps / "primary-descriptors.parquet")
        != json.loads((analysis / "analysis.json").read_text())["primary_input_sha256"]
    ):
        raise ValueError("Analysis and map populations differ")
    candidates = pd.read_csv(
        analysis / "disagreement-candidates.csv", dtype={"id": str, "collection": str}
    )
    lookup = fields.set_index(["collection", "id"], verify_integrity=True)
    out.mkdir(parents=True)
    rows, records = [], []
    for candidate in candidates.to_dict("records"):
        source = lookup.loc[(candidate["collection"], candidate["id"])]
        if (
            source.window_id != candidate["window_id"]
            or source.sample_role != "primary"
        ):
            raise ValueError("Candidate identity or window mismatch")
        links = []
        for key in ("first", "second"):
            feature = candidate[key]
            if abs(float(source[feature]) - float(candidate[key + "_value"])) > 1e-10:
                raise ValueError("Candidate measurement mismatch")
            link = field_link(
                out, maps, candidate["window_id"], candidate["id"], feature
            )
            links.append(
                f'<a href="{escape(link, quote=True)}" target="_blank" rel="noopener">{escape(feature)}: {float(source[feature]):.5g}</a>'
            )
            candidate[key + "_map_link"] = link
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{escape(str(candidate[k]))}</td>"
                for k in ["zone_id", "window_id", "id"]
            )
            + f"<td>{links[0]}</td><td>{links[1]}</td><td>{candidate['absolute_rank_difference']:.3f}</td></tr>"
        )
        records.append(candidate)
    html = (
        """<!doctype html><meta charset="utf-8"><title>Descriptor disagreement review</title>
<style>body{font:15px sans-serif;margin:24px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px}th{position:sticky;top:0;background:#eee}tr:nth-child(even){background:#f6f6f6}</style>
<h1>Descriptor disagreement examples</h1><p>These candidates come from the unchanged primary sample. Click either descriptor value to open its map, zoom to the field and highlight it in magenta. The two links show the same field colored by different descriptors. Field-ID search is also available in every map.</p>
<p>Rank difference is the absolute difference between within-landscape percentile ranks (0–1); it is not an accuracy score. Candidates illustrate potential complementarity, not validated explanations. They were not added or reweighted. Some fields appear in multiple pairs. The handpicked Bahia diagnostic is excluded.</p>
<p>Review questions: does shape explain the disagreement? Are holes or indentations involved? Is a prediction artifact plausible? The imagery basemap has variable dates and is not a contemporaneous reference. Maps require internet for Leaflet and imagery; local measurement data are embedded.</p>
<table><thead><tr><th>Landscape</th><th>Window</th><th>Field ID</th><th>First descriptor / map</th><th>Second descriptor / map</th><th>Rank difference</th></tr></thead><tbody>"""
        + "".join(rows)
        + "</tbody></table>"
    )
    (out / "index.html").write_text(html)
    pd.DataFrame(records).to_csv(out / "examples-with-links.csv", index=False)
    (out / "build-index-source.py").write_bytes(Path(__file__).read_bytes())
    write_json(
        out / "complete.json",
        {
            "created_at": now(),
            "examples": len(records),
            "unique_fields": len(candidates[["collection", "id"]].drop_duplicates()),
            "candidate_input_sha256": file_digest(
                analysis / "disagreement-candidates.csv"
            ),
            "primary_input_sha256": file_digest(maps / "primary-descriptors.parquet"),
            "measurement_changes": False,
            "output_sha256": {
                p.name: file_digest(p) for p in out.iterdir() if p.is_file()
            },
        },
    )
    print(f"Built {len(records)} example-pair links: {out / 'index.html'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_dir")
    parser.add_argument("--maps_dir", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    build(args.analysis_dir, args.maps_dir, args.out_dir)
