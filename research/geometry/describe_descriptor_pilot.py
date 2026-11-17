"""Measure assigned published fields and create descriptor-colored review maps."""

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from ftw_geometry.core.descriptors import DESCRIPTOR_VERSION, describe_polygons
from ftw_geometry.io.manifests import file_digest, write_json

from research.geometry.select_descriptor_pilot import now


def component_count(geometry):
    if geometry.geom_type == "Polygon":
        return 1
    if geometry.geom_type == "MultiPolygon":
        return len(geometry.geoms)
    raise ValueError(f"Unsupported geometry: {geometry.geom_type}")


def single_polygon(geometry):
    if component_count(geometry) != 1:
        raise ValueError("Genuinely multipart geometry requires an explicit policy")
    return geometry.geoms[0] if geometry.geom_type == "MultiPolygon" else geometry


def common_scales(primary):
    """Shared full ranges from the supplied population; ratio bounds are theoretical."""
    scales = {}
    for key in [
        "area_m2",
        "perimeter_m",
        "elongation",
        "circularity",
        "solidity",
        "rectangularity",
        "convex_hull_index",
        "hole_area_fraction",
        "hole_count",
    ]:
        values = primary[key].dropna().to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"Invalid scale values for {key}")
        if key in {
            "circularity",
            "solidity",
            "rectangularity",
            "convex_hull_index",
            "hole_area_fraction",
        }:
            lo, hi, transform = 0.0, 1.0, "linear"
        elif not len(values):
            raise ValueError(
                "Cannot derive shared scales from an empty primary population"
            )
        elif key == "hole_count":
            lo, hi, transform = 0.0, float(values.max()), "log1p"
        else:
            if (values <= 0).any():
                raise ValueError(f"Log scale requires positive {key}")
            lo, hi, transform = float(values.min()), float(values.max()), "log"
        scales[key] = {"lo": lo, "hi": hi, "transform": transform}
    return scales


def descriptor_map(
    window,
    frame,
    shared_scales=None,
    *,
    scale_population="primary fields only (diagnostic excluded)",
):
    columns = [
        "id",
        "area_m2",
        "perimeter_m",
        "circularity",
        "elongation",
        "solidity",
        "rectangularity",
        "convex_hull_index",
        "hole_count",
        "hole_area_fraction",
        "narrow_neck",
        "geometry",
    ]
    data = frame[columns].to_json().replace("<", "\\u003c")
    boundary = json.dumps(window).replace("<", "\\u003c")
    population = json.dumps(scale_population).replace("<", "\\u003c")
    name = window["properties"]["window_id"]
    return f"""<!doctype html><meta charset="utf-8"><title>{name} descriptors</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>body{{margin:0;font:14px sans-serif}}header{{padding:8px}}#map{{height:85vh}}</style>
<header><b>{name}</b> — {len(frame)} assigned fields; {window["properties"]["role"]}<br>
<select id="feature"></select> <select id="scale"><option value="common">Common across sites</option><option value="local">Local contrast</option></select> <span id="legend"></span><br>
<input id="fieldSearch" placeholder="Exact field ID"><button id="findField">Find field</button><button id="clearField">Clear highlight</button> <span id="searchStatus"></span><br>
Common scales use the population named in the legend; local contrast uses window percentiles. Narrow neck: false blue, true red.
Missing values are gray. Esri imagery dates vary; this is not accuracy evaluation.</header><div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const data={data}, boundary={boundary}, shared={json.dumps(shared_scales or {})}, scalePopulation={population};const map=L.map('map',{{preferCanvas:true}});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',{{maxZoom:19,attribution:'Tiles © Esri, Maxar, Earthstar Geographics, GIS User Community'}}).addTo(map);
const keys=['area_m2','perimeter_m','circularity','elongation','solidity','rectangularity','convex_hull_index','hole_count','hole_area_fraction','narrow_neck'];
const select=document.getElementById('feature');keys.forEach(k=>{{const o=document.createElement('option');o.value=k;o.textContent=k;select.appendChild(o)}});
let highlight=null;let fields;function draw(){{const key=select.value;const values=data.features.map(f=>f.properties[key]).filter(v=>v!==null&&Number.isFinite(Number(v))).map(Number).sort((a,b)=>a-b);
const categorical=key==='narrow_neck';
let lo=values.length?values[Math.floor((values.length-1)*.05)]:null,hi=values.length?values[Math.floor((values.length-1)*.95)]:null;
let fallback=false;if(values.length&&lo===hi&&values[0]!==values[values.length-1]){{lo=values[0];hi=values[values.length-1];fallback=true;}}
const common=document.getElementById('scale').value!=='local'&&shared[key];let transform=v=>v;let label=fallback?'full-range fallback':'local 5th–95th percentiles; tails clipped';
if(common){{lo=common.lo;hi=common.hi;transform=common.transform==='log'?Math.log:common.transform==='log1p'?Math.log1p:v=>v;label='common '+common.transform+(common.transform==='linear'&&lo===0&&hi===1?'; fixed 0–1 bounds':'; bounds from '+scalePopulation);}}
document.getElementById('legend').textContent=!values.length?'No mapped fields / no descriptor observations':categorical?'False = blue; True = red':lo===hi?'Constant value: '+lo.toPrecision(4)+' (blue)':'Blue → red: '+lo.toPrecision(4)+' → '+hi.toPrecision(4)+' ('+label+')';
if(fields)map.removeLayer(fields);fields=L.geoJSON(data,{{style:f=>{{const v=f.properties[key];const missing=v===null||v===undefined||!Number.isFinite(Number(v));const t=categorical?(v===true||v===1?1:0):hi===lo?0:Math.max(0,Math.min(1,(transform(Number(v))-transform(lo))/(transform(hi)-transform(lo))));return {{color:'#222',weight:.5,fillOpacity:.7,fillColor:missing?'#999':`hsl(${{240*(1-t)}},85%,55%)`}}}},onEachFeature:(f,l)=>{{l.on('mouseover',()=>{{const el=document.createElement('span');el.textContent=f.properties.id+' | '+key+': '+f.properties[key];l.bindTooltip(el).openTooltip()}})}}}}).addTo(map)}};
function focusField(id){{const feature=data.features.find(f=>String(f.properties.id)===String(id));const status=document.getElementById('searchStatus');
if(!feature){{status.textContent='Field not found in this assigned-field map: '+id;return false;}}
if(highlight)map.removeLayer(highlight);highlight=L.geoJSON(feature,{{style:{{color:'#ff00ff',weight:5,fill:false}}}}).addTo(map);map.fitBounds(highlight.getBounds(),{{padding:[40,40],maxZoom:19}});
const popup=document.createElement('pre');popup.textContent=Object.entries(feature.properties).map(([k,v])=>k+': '+v).join(String.fromCharCode(10));highlight.bindPopup(popup).openPopup();status.textContent='Highlighted: '+id;return true;}}
function applyHash(){{const hash=typeof location==='undefined'?'':location.hash;const params={{}};hash.replace(/^#/, '').split('&').filter(Boolean).forEach(part=>{{const i=part.indexOf('=');if(i>=0){{try{{params[decodeURIComponent(part.slice(0,i))]=decodeURIComponent(part.slice(i+1));}}catch(e){{document.getElementById('searchStatus').textContent='Invalid map link';}}}}}});
if(keys.includes(params.feature))select.value=params.feature;draw();if(params.field){{document.getElementById('fieldSearch').value=params.field;focusField(params.field);}}}}
L.geoJSON(boundary,{{style:{{color:'#ff3344',weight:3,fill:false}}}}).addTo(map);map.fitBounds(L.geoJSON(boundary).getBounds());select.onchange=()=>{{draw();if(highlight)highlight.bringToFront();}};document.getElementById('scale').onchange=select.onchange;
document.getElementById('findField').onclick=()=>focusField(document.getElementById('fieldSearch').value.trim());document.getElementById('fieldSearch').onkeydown=e=>{{if(e.key==='Enter')document.getElementById('findField').onclick();}};
document.getElementById('clearField').onclick=()=>{{if(highlight)map.removeLayer(highlight);highlight=null;document.getElementById('searchStatus').textContent='';}};
if(typeof addEventListener==='function')addEventListener('hashchange',applyHash);applyHash();</script>"""


def run(review, out):
    review, out = Path(review).expanduser().resolve(), Path(out).expanduser().resolve()
    if out == review or review in out.parents:
        raise ValueError(
            "Use a separate output directory; preserve the retrieval audit"
        )
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a fresh descriptor output directory")
    out.mkdir(parents=True, exist_ok=True)
    summaries, populations, links = [], {"primary": [], "diagnostic": []}, []
    for location in sorted(review.iterdir()):
        if not location.is_dir() or not (location / "complete.json").exists():
            continue
        checkpoint = json.loads((location / "complete.json").read_text())
        for name, digest in checkpoint["sha256"].items():
            if file_digest(location / name) != digest:
                raise ValueError(f"Changed retrieval artifact: {location.name}/{name}")
        provenance = json.loads((location / "provenance.json").read_text())
        window = provenance["window"]
        props = window["properties"]
        fields = gpd.read_parquet(location / "fields.parquet")
        audit = pd.read_csv(
            location / "audit.csv", dtype={"id": str, "collection": str}
        )
        if list(zip(audit.collection, audit.id)) != list(
            zip(fields.collection, fields.id)
        ):
            raise ValueError("Audit and source identities do not align")
        audit["component_count"] = [component_count(g) for g in fields.geometry]
        audit["is_genuinely_multipart"] = audit.component_count > 1
        audit["single_component_container"] = (
            fields.geom_type.to_numpy() == "MultiPolygon"
        ) & (audit.component_count == 1)
        if audit.is_genuinely_multipart.any():
            raise ValueError(
                f"Genuinely multipart field found in {location.name}; stop for policy decision"
            )
        destination = out / location.name
        destination.mkdir()
        audit.to_csv(destination / "corrected-component-audit.csv", index=False)
        assigned = audit.assigned_to_window.eq(True).to_numpy()
        measured = fields.loc[assigned].copy()
        original = measured.geometry.copy()
        measured.geometry = measured.geometry.map(single_polygon)
        if not all(a.equals(b) for a, b in zip(original, measured.geometry)):
            raise ValueError("Container normalization changed geometry")
        descriptors = describe_polygons(measured, metric_crs=props["metric_crs"])
        descriptors["id"] = descriptors.id.astype(measured.id.dtype)
        measured = measured.merge(
            descriptors, on="id", how="left", validate="one_to_one"
        )
        measured["window_id"] = location.name
        measured["zone_id"] = props["zone_id"]
        measured["sample_role"] = props["role"]
        measured["descriptor_version"] = DESCRIPTOR_VERSION
        measured["measurement_crs"] = props["metric_crs"]
        measured["container_unwrapped"] = audit.loc[
            assigned, "single_component_container"
        ].to_numpy()
        measured.to_parquet(destination / "descriptors.parquet")
        measured.drop(columns="geometry").to_csv(
            destination / "descriptors.csv", index=False
        )
        (destination / "review.html").write_text(descriptor_map(window, measured))
        populations[props["role"]].append(measured.drop(columns="geometry"))
        summaries.append(
            {
                "window_id": location.name,
                "role": props["role"],
                "assigned_fields": len(measured),
                "single_component_containers": int(
                    audit.single_component_container.sum()
                ),
                "genuinely_multipart": int(audit.is_genuinely_multipart.sum()),
                "empty_window": len(measured) == 0,
                "source_fields_sha256": file_digest(location / "fields.parquet"),
            }
        )
        links.append(
            f'<li><a href="{location.name}/review.html">{location.name} ({props["role"]}, {len(measured)} fields)</a></li>'
        )
        print(summaries[-1], flush=True)
    for role, tables in populations.items():
        table = pd.concat(tables, ignore_index=True)
        if table.duplicated(["collection", "id"]).any():
            raise ValueError(f"Repeated assigned field identities within {role}")
        table.to_parquet(out / f"{role}-descriptors.parquet", index=False)
    scales = common_scales(pd.read_parquet(out / "primary-descriptors.parquet"))
    write_json(
        out / "common-color-scales.json",
        {"population": "primary only", "scales": scales},
    )
    for entry in summaries:
        name = entry["window_id"]
        window = json.loads((review / name / "provenance.json").read_text())["window"]
        frame = gpd.read_parquet(out / name / "descriptors.parquet")
        (out / name / "review.html").write_text(descriptor_map(window, frame, scales))
    pd.DataFrame(summaries).to_csv(out / "window-summary.csv", index=False)
    (out / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><h1>Assigned-field descriptor maps</h1><p>Primary and diagnostic populations are separate. Empty windows remain explicit. No correlations or accuracy estimates computed.</p><ul>'
        + "".join(links)
        + "</ul>"
    )
    (out / "describe_descriptor_pilot.py").write_bytes(Path(__file__).read_bytes())
    (out / "descriptors-source.py").write_bytes(
        Path(
            __import__("ftw_geometry.core.descriptors", fromlist=["__file__"]).__file__
        ).read_bytes()
    )
    write_json(
        out / "complete.json",
        {
            "completed_at": now(),
            "schema_version": DESCRIPTOR_VERSION,
            "review_dir": str(review),
            "windows": summaries,
            "correlation_analysis_performed": False,
            "output_sha256": {
                str(p.relative_to(out)): file_digest(p)
                for p in sorted(out.rglob("*"))
                if p.is_file()
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review")
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(args.review, args.out_dir)
