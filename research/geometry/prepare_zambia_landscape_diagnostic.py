"""Prepare an exact-polygon review window south of Lubushi Mission; no analysis."""

import argparse
import json
import math
import os
import urllib.request
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from ftw_geometry.io.manifests import file_digest, write_json
from ftw_geometry.io.sources import Sources, now, remote_identity
from ftw_geometry.io.vectors import RangeReader
from pyproj import Transformer
from shapely import from_wkb, intersects
from shapely.geometry import box, mapping

from research.geometry.pilot_sampling import geographic_window

COMMIT = "118eafa3784b3f0b0c1832e0e01fa616db3e4146"
REPOSITORY = f"https://raw.githubusercontent.com/agroimpacts/mapping-africa/{COMMIT}"
DATA_URL = "https://mappingafrica.s3.us-west-2.amazonaws.com/croplands/geoparquet/zambia_2024_v4.parquet"
GEOCODER = "https://nominatim.openstreetmap.org/search?q=Lubushi%20Mission%2C%20Zambia&format=jsonv2"
WINDOW_ID = "lubushi_south_2024_10km"
METRIC_CRS = "EPSG:32736"


class SnapshotReader(RangeReader):
    """Conditional byte ranges with an explicit total transfer budget."""

    def __init__(self, identity, max_bytes):
        super().__init__(identity["url"], identity["size_bytes"])
        self.etag = identity["etag"]
        self.max_bytes = max_bytes
        if not self.etag:
            raise ValueError("An ETag is required to guard the remote snapshot")

    def read(self, size=-1):
        size = min(self.size - self.pos, size if size >= 0 else self.size - self.pos)
        if size <= 0:
            return b""
        if self.transferred + size > self.max_bytes:
            raise ValueError("Remote scan exceeds the explicit transfer budget")
        start, end = self.pos, self.pos + size - 1
        request = urllib.request.Request(
            self.url,
            headers={
                "User-Agent": "FTW-geometry-research/1.0",
                "Range": f"bytes={start}-{end}",
                "If-Match": self.etag,
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            if (
                response.status != 206
                or response.headers.get("Content-Range")
                != f"bytes {start}-{end}/{self.size}"
                or response.headers.get("ETag") != self.etag
            ):
                raise ValueError("Remote identity or exact range changed")
            data = response.read(size + 1)
            if len(data) != size:
                raise ValueError("Incomplete remote range")
        self.pos += size
        self.transferred += size
        return data


def south_window(lon, lat, *, side_m=10000, north_offset_m=500):
    if not (-180 <= lon <= 180 and -80 <= lat < 0):
        raise ValueError("Expected a southern-hemisphere mission coordinate")
    if not (
        math.isfinite(side_m)
        and side_m > 0
        and math.isfinite(north_offset_m)
        and north_offset_m >= 0
    ):
        raise ValueError("Choose a positive side and nonnegative north-edge offset")
    x, y = Transformer.from_crs(4326, METRIC_CRS, always_xy=True).transform(lon, lat)
    metric = box(
        x - side_m / 2, y - north_offset_m - side_m, x + side_m / 2, y - north_offset_m
    )
    footprint = geographic_window(metric, METRIC_CRS)
    return metric, {
        "type": "Feature",
        "geometry": mapping(footprint),
        "properties": {
            "window_id": WINDOW_ID,
            "zone_id": "lubushi",
            "role": "diagnostic",
            "include_in_primary_statistics": False,
            "year": 2024,
            "release": "v4",
            "dataset": "Mapping Africa",
            "metric_crs": METRIC_CRS,
            "side_m": side_m,
            "north_edge_grid_south_of_mission_m": north_offset_m,
            "mission_lon": lon,
            "mission_lat": lat,
            "selection": "user-selected vicinity; unoptimized grid-south window",
            "approval_status": "proposed; awaiting user outline review",
        },
    }


def extract_window(parquet, footprint, *, max_fields=100000, max_scan_rows=10000000):
    """Scan geometry only, then fetch attributes only from intersecting groups."""
    if parquet.metadata.num_rows > max_scan_rows:
        raise ValueError("Dataset exceeds the explicit row scan limit")
    geo = json.loads(parquet.schema_arrow.metadata[b"geo"])
    if (
        geo["primary_column"] != "geometry"
        or geo["columns"]["geometry"]["encoding"] != "WKB"
    ):
        raise ValueError("Expected standard geometry WKB")
    # Release-specific extraction: never assume a different source CRS is lon/lat.
    from pyproj import CRS

    if CRS.from_user_input(geo["columns"]["geometry"]["crs"]) != CRS.from_epsg(4326):
        raise ValueError("This extractor requires source EPSG:4326")
    tables, counts, selected_total = [], [], 0
    for group_id in range(parquet.metadata.num_row_groups):
        raw = parquet.read_row_group(group_id, columns=["geometry"])
        indices, position = [], 0
        for batch in raw.to_batches(max_chunksize=25000):
            geometries = from_wkb(batch.column(0).to_pylist())
            selected = np.flatnonzero(intersects(geometries, footprint))
            indices.extend((position + selected).tolist())
            position += len(batch)
        selected_total += len(indices)
        if selected_total > max_fields:
            raise ValueError("Window exceeds max_fields; no silent truncation")
        if indices:
            # Preserve original geometry bytes and all source attributes.
            attributes = parquet.read_row_group(
                group_id,
                columns=[c for c in parquet.schema_arrow.names if c != "geometry"],
            )
            selected = attributes.take(pa.array(indices, type=pa.int64()))
            selected = selected.append_column(
                "geometry", raw["geometry"].take(pa.array(indices, type=pa.int64()))
            )
            selected = pa.Table.from_arrays(
                [selected[name] for name in parquet.schema_arrow.names],
                schema=parquet.schema_arrow,
            )
            selected = selected.append_column(
                "source_row_group", pa.array([group_id] * len(indices), type=pa.int32())
            )
            selected = selected.append_column(
                "source_row_in_group", pa.array(indices, type=pa.int64())
            )
            tables.append(selected)
        counts.append(
            {
                "row_group": group_id,
                "scanned_rows": position,
                "intersecting_rows": len(indices),
            }
        )
        print(counts[-1], flush=True)
    if tables:
        return pa.concat_tables(tables), counts
    raise ValueError("No intersecting polygons; inspect source coverage and location")


def review_html(window, fields, bahia_link):
    props = window["properties"]
    data = (
        fields[["field_row_id", "area_ha", "geometry"]]
        .to_json()
        .replace("<", "\\u003c")
    )
    boundary = json.dumps(window).replace("<", "\\u003c")
    return f"""<!doctype html><meta charset="utf-8"><title>Lubushi proposed window</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>body{{margin:0;font:15px sans-serif}}header{{padding:12px;line-height:1.5}}#map{{height:78vh}}</style>
<header><b>Proposed 10 × 10 km window south of Lubushi Mission</b><br>
Red boundary; yellow original Mapping Africa 2024 v4 polygons. North edge is 500 m grid-south of the mission.<br>
{len(fields):,} intersecting records. Popups show source IDs and source area, not newly calculated descriptors.<br>
This is a deliberately selected illustration; window approval and chitemene interpretation await user review.
Basemap dates vary and are not 2024 reference evidence.<br>
<label><input id="outlines" type="checkbox" checked>Field outlines</label> ·
<a href="{bahia_link}">Existing Bahia pivot diagnostic</a> · <a href="proposed-window.geojson">Window GeoJSON</a>
<div id="status"></div></header><div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const windowFeature={boundary};const data={data};const map=L.map('map',{{preferCanvas:true}});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',{{maxZoom:19,attribution:'Tiles © Esri, Maxar, Earthstar Geographics, GIS User Community'}}).addTo(map);
const fields=L.geoJSON(data,{{style:{{color:'#ffe000',weight:1,fill:false}},onEachFeature:(f,l)=>{{const el=document.createElement('span');el.textContent='Source field_row_id: '+f.properties.field_row_id+' | source area (ha): '+f.properties.area_ha;l.bindPopup(el);}}}}).addTo(map);
const boundary=L.geoJSON(windowFeature,{{style:{{color:'#ff3344',weight:3,fill:false}}}}).addTo(map);
const mission=L.marker([{props["mission_lat"]},{props["mission_lon"]}]).addTo(map).bindPopup('Lubushi Mission — OpenStreetMap node 9372107435');
document.getElementById('outlines').onchange=e=>{{if(e.target.checked)fields.addTo(map);else map.removeLayer(fields);}};
const extent=boundary.getBounds();extent.extend(mission.getLatLng());map.fitBounds(extent.pad(.05));
document.getElementById('status').textContent='Source polygons loaded: '+data.features.length;
</script>"""


def run(out, bahia, *, max_transfer_bytes=2000000000):
    out, bahia = Path(out).expanduser().resolve(), Path(bahia).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a fresh output directory")
    if not bahia.is_file():
        raise ValueError("Existing Bahia descriptor map is required")
    out.mkdir(parents=True, exist_ok=True)
    sources = Sources(out / "sources")
    for name in ("README.md", "LICENSE", "config.js"):
        sources.fetch(f"{REPOSITORY}/{name}", name)
    location, _ = sources.fetch(GEOCODER, "lubushi-geocoder.json")
    matches = [
        r
        for r in json.loads(location.read_text())
        if r.get("osm_id") == 9372107435 and r.get("osm_type") == "node"
    ]
    if len(matches) != 1:
        raise ValueError(
            "Expected unique Lubushi Mission OSM node; verify location manually"
        )
    mission = matches[0]
    metric, window = south_window(float(mission["lon"]), float(mission["lat"]))
    write_json(
        out / "proposed-window.geojson",
        {"type": "FeatureCollection", "features": [window]},
    )
    identity = remote_identity(DATA_URL)
    identity["integrity"] = (
        "ETag-conditional partial range scan; whole-object checksum not verified"
    )
    write_json(out / "sources" / "zambia-2024-v4-identity.json", identity)
    reader = SnapshotReader(identity, max_transfer_bytes)
    parquet = pq.ParquetFile(reader)
    parquet.metadata.write_metadata_file(
        out / "sources" / "zambia-2024-v4-metadata.parquet"
    )
    footprint = geographic_window(metric, METRIC_CRS)
    table, counts = extract_window(parquet, footprint)
    pq.write_table(table, out / "fields.parquet")
    readback = pq.read_table(out / "fields.parquet")
    if table["geometry"].to_pylist() != readback["geometry"].to_pylist():
        raise ValueError("Source WKB changed during persistence")
    fields = gpd.read_parquet(out / "fields.parquet")
    if fields.field_row_id.isna().any() or not fields.field_row_id.is_unique:
        raise ValueError("Window source field_row_id must be unique/non-null")
    projected = fields.to_crs(METRIC_CRS)
    audit = pd.DataFrame(
        {
            "field_row_id": fields.field_row_id,
            "source_row_group": fields.source_row_group,
            "source_row_in_group": fields.source_row_in_group,
            "source_valid": fields.is_valid,
            "projected_valid": projected.is_valid,
            "geometry_type": fields.geom_type,
            "assigned_to_window": [
                metric.covers(g.representative_point()) for g in projected.geometry
            ],
            "crosses_window_boundary": [
                not metric.covers(g) for g in projected.geometry
            ],
        }
    )
    audit.to_csv(out / "audit.csv", index=False)
    pd.DataFrame(counts).to_csv(out / "scan.csv", index=False)
    (out / "review.html").write_text(
        review_html(window, fields, os.path.relpath(bahia, out))
    )
    write_json(
        out / "provenance.json",
        {
            "prepared_at": now(),
            "window": window,
            "remote": identity,
            "mapping_africa_repository_commit": COMMIT,
            "source_rows": parquet.metadata.num_rows,
            "row_groups": parquet.metadata.num_row_groups,
            "bytes_transferred": reader.transferred,
            "transfer_budget_bytes": max_transfer_bytes,
            "retrieval": "explicit bounded geometry scan; no bbox statistics available",
            "geometry_changed": False,
            "halo_retrieved": False,
            "intersecting_fields": len(fields),
            "assigned_fields": int(audit.assigned_to_window.sum()),
            "source_invalid_count": int((~audit.source_valid).sum()),
            "projected_invalid_count": int((~audit.projected_valid).sum()),
            "approved": False,
            "descriptor_analysis_performed": False,
            "dataset_terms": "README Usage specifies Planet NICFI participant license; repository LICENSE is separately CC BY-SA 4.0",
            "bahia_map": str(bahia),
            "bahia_map_sha256": file_digest(bahia),
        },
    )
    (out / "prepare_zambia_landscape_diagnostic.py").write_bytes(
        Path(__file__).read_bytes()
    )
    write_json(
        out / "complete.json",
        {
            "completed_at": now(),
            "stage": "window review only; awaiting approval",
            "output_sha256": {
                str(p.relative_to(out)): file_digest(p)
                for p in sorted(out.rglob("*"))
                if p.is_file()
            },
        },
    )
    print(f"Proposed window ready: {out / 'review.html'}", flush=True)
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--bahia_map", required=True)
    args = parser.parse_args()
    run(args.out_dir, args.bahia_map)
