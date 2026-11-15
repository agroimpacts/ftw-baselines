"""Retrieve unchanged published WKB and build interactive pilot review maps."""

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from ftw_geometry.io.manifests import file_digest, write_json
from ftw_geometry.io.vectors import RangeReader, overlapping_groups
from shapely import from_wkb
from shapely.geometry import box, shape

from research.geometry.select_descriptor_pilot import now


def review_html(window, fields):
    data = json.loads(fields[["id", "score", "geometry"]].to_json())
    encoded = json.dumps(data).replace("<", "\\u003c")
    outline = json.dumps(window).replace("<", "\\u003c")
    return f"""<!doctype html><meta charset="utf-8"><title>{window["properties"]["window_id"]}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>body{{margin:0;font:14px sans-serif}}#map{{height:92vh}}header{{padding:8px}}</style>
<header>{window["properties"]["window_id"]} — {len(fields)} intersecting published polygons (full geometry).<br>
Viewing basemap may differ in date from 2024 predictions; not accuracy evidence. Outline review only; no descriptors yet.</header><div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const map=L.map('map'); const imagery=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',{{attribution:'Tiles © Esri — sources: Esri, Maxar, Earthstar Geographics, and the GIS User Community',maxZoom:19}}).addTo(map);
const fields=L.geoJSON({encoded},{{style:{{color:'#ffdd00',weight:1,fill:false}},onEachFeature:(f,l)=>l.bindTooltip(String(f.properties.id)+' | score '+f.properties.score)}}).addTo(map);
const windowLayer=L.geoJSON({outline},{{style:{{color:'#ff3344',weight:3,fill:false}}}}).addTo(map);
L.control.layers({{'Imagery (date varies)':imagery}},{{'Published fields':fields,'Sampling window':windowLayer}}).addTo(map);map.fitBounds(windowLayer.getBounds());
</script>"""


def run(selection, diagnostic, out):
    selection, diagnostic, out = (
        Path(selection).expanduser(),
        Path(diagnostic).expanduser(),
        Path(out).expanduser(),
    )
    out.mkdir(parents=True, exist_ok=True)
    for root in (selection, diagnostic):
        manifest = json.loads((root / "complete.json").read_text())
        for name, digest in manifest["output_sha256"].items():
            if file_digest(root / name) != digest:
                raise ValueError(f"Changed source artifact: {name}")
    windows = (
        json.loads((selection / "selected-windows.geojson").read_text())["features"]
        + json.loads((diagnostic / "diagnostic-windows.geojson").read_text())[
            "features"
        ]
    )
    items = [
        json.loads(p.read_text())
        for p in sorted((selection / "sources").glob("vector-utm*.json"))
        if not p.name.endswith(".source.json")
    ]
    summaries, links = [], []
    for window in windows:
        props = window["properties"]
        wid = props["window_id"]
        location = out / wid
        location.mkdir(exist_ok=True)
        checkpoint = location / "complete.json"
        if checkpoint.exists():
            saved = json.loads(checkpoint.read_text())
            for name, digest in saved["sha256"].items():
                if file_digest(location / name) != digest:
                    raise ValueError(f"Changed extract: {wid}/{name}")
            summaries.append(saved["summary"])
            links.append(f'<li><a href="{wid}/review.html">{wid}</a></li>')
            continue
        footprint = shape(window["geometry"])
        tables, provenance = [], []
        empty_schema = None
        for item in items:
            if not box(*item["bbox"]).intersects(footprint):
                continue
            asset = item["assets"]["data"]
            zone = item["id"].removeprefix("utm")
            url = f"https://data.source.coop/ftw/global-data-2e/vector/2024/zone={zone}/utm{zone}.parquet"
            remote = RangeReader(url, asset["file:size"])
            parquet = pq.ParquetFile(remote)
            empty_schema = parquet.schema_arrow
            groups = overlapping_groups(parquet.metadata, footprint.bounds)
            for group in groups:
                table = parquet.read_row_group(group)
                geometry = from_wkb(table["geometry"].to_pylist())
                mask = np.array([g.intersects(footprint) for g in geometry])
                if mask.any():
                    tables.append(table.filter(pa.array(mask)))
            provenance.append(
                {
                    "url": url,
                    "advertised_asset": asset,
                    "row_groups": groups,
                    "bytes_transferred": remote.transferred,
                    "whole_asset_checksum_verified": False,
                }
            )
        if not tables and empty_schema is None:
            raise ValueError(
                f"No published vector asset covers {wid}; investigate without replacing window"
            )
        # A covered query with zero intersecting predictions is a valid retrieval
        # outcome, not permission to replace the sampled area or infer no fields.
        table = (
            pa.concat_tables(tables)
            if tables
            else pa.Table.from_batches([], schema=empty_schema)
        )
        keys = list(zip(table["collection"].to_pylist(), table["id"].to_pylist()))
        if len(set(keys)) != len(keys):
            raise ValueError(
                f"Duplicate collection-qualified IDs in {wid}; no silent deduplication"
            )
        # Persist original source columns and WKB bytes, not a GeoPandas rewrite.
        pq.write_table(table, location / "fields.parquet")
        assert (
            pq.read_table(location / "fields.parquet")["geometry"].to_pylist()
            == table["geometry"].to_pylist()
        )
        fields = gpd.read_parquet(location / "fields.parquet")
        metric = fields.to_crs(props["metric_crs"])
        metric_window = (
            gpd.GeoSeries([footprint], crs=4326).to_crs(props["metric_crs"]).iloc[0]
        )
        audit = pd.DataFrame(
            {
                "collection": fields["collection"],
                "id": fields.id,
                "valid": fields.geometry.is_valid,
                "geometry_type": fields.geom_type,
                "assigned_to_window": [
                    metric_window.covers(g.representative_point())
                    for g in metric.geometry
                ],
                "crosses_sampling_edge": [
                    not footprint.covers(g) for g in fields.geometry
                ],
                "geometry_hash": [
                    __import__("hashlib").sha256(wkb).hexdigest()
                    for wkb in table["geometry"].to_pylist()
                ],
            }
        )
        audit.to_csv(location / "audit.csv", index=False)
        summary = {
            "window_id": wid,
            "role": props["role"],
            "intersecting_polygons": len(fields),
            "assigned_polygons": int(audit.assigned_to_window.sum()),
            "invalid": int((~audit.valid).sum()),
            "multiparts": int((audit.geometry_type == "MultiPolygon").sum()),
            "duplicate_wkb": int(audit.geometry_hash.duplicated().sum()),
            "seam_status": "unknown: released schema has no seam flag",
            "empty_query_requires_review": len(fields) == 0,
        }
        write_json(
            location / "provenance.json",
            {
                "window": window,
                "assets": provenance,
                "retrieved_at": now(),
                "geometry_changed": False,
            },
        )
        (location / "review.html").write_text(review_html(window, fields))
        write_json(
            checkpoint,
            {
                "summary": summary,
                "sha256": {
                    p.name: file_digest(p) for p in location.iterdir() if p.is_file()
                },
            },
        )
        summaries.append(summary)
        links.append(f'<li><a href="{wid}/review.html">{wid}</a></li>')
        print(summary, flush=True)
    pd.DataFrame(summaries).to_csv(out / "audit-summary.csv", index=False)
    (out / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><h1>2024 FTW polygon review</h1><p>21 primary windows and one separate diagnostic. Internet required for basemap and Leaflet. Basemap dates vary; not a 2024 reference.</p><ul>'
        + "".join(links)
        + "</ul>"
    )
    write_json(
        out / "complete.json",
        {
            "completed_at": now(),
            "windows": len(summaries),
            "script_sha256": file_digest(__file__),
            "descriptor_analysis_performed": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection")
    parser.add_argument("diagnostic")
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(args.selection, args.diagnostic, args.out_dir)
