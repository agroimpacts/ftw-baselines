"""Freeze public inputs and draw the agreed 2024 FTW descriptor-pilot windows.

    python -m research.geometry.select_descriptor_pilot CONFIG --out_dir DIRECTORY

Only selects areas. Does not download FTW probability imagery, extract fields,
run descriptors, repair geometry, or evaluate accuracy. Use a fresh output directory
after changing code/config; an interrupted identical run can resume cached work.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from collections import Counter
from contextlib import ExitStack
from importlib.metadata import version
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import rasterio
from ftw_geometry.io.manifests import file_digest, write_json
from shapely import from_wkb
from shapely.geometry import mapping, shape

from research.geometry import pilot_sampling as sampling

USER_AGENT = "Mozilla/5.0 FTW-descriptor-pilot/1.0"


from ftw_geometry.io.sources import Sources, now, remote_identity


class CropScreen:
    def __init__(self, root, settings, stack):
        self.root, self.settings, self.stack = root, settings, stack
        self.datasets, self.identities = {}, {}
        root.mkdir(parents=True, exist_ok=True)

    def dataset(self, key):
        url = (
            "https://esa-worldcover.s3.eu-central-1.amazonaws.com/"
            f"{self.settings['worldcover_version']}/map/ESA_WorldCover_10m_2021_v200_{key}_Map.tif"
        )
        if key not in self.datasets:
            identity = remote_identity(url)
            record = self.root / f"{key}.source.json"
            if record.exists() and json.loads(record.read_text()) != identity:
                raise ValueError(f"WorldCover asset changed: {url}")
            write_json(record, identity)
            self.identities[key] = identity
            self.datasets[key] = self.stack.enter_context(rasterio.open(url))
        return self.datasets[key]

    def __call__(self, row):
        location = self.root / row["window_id"]
        location.mkdir(parents=True, exist_ok=True)
        cached = location / "observation.json"
        if cached.exists():
            result = json.loads(cached.read_text())
            for item in result["chips"]:
                self.dataset(item["tile_key"])
                if file_digest(location / item["file"]) != item["sha256"]:
                    raise ValueError(f"Crop chip changed: {location}")
            return result
        footprint = row["footprint"]
        area, _ = sampling.GEOD.geometry_area_perimeter(footprint)
        area = abs(area)
        crop, valid, sampled = 0.0, 0.0, 0.0
        chips = []
        for key, _ in sampling.worldcover_tiles(footprint):
            observation = sampling.crop_observation(self.dataset(key), footprint)
            path = location / f"{key}.npz"
            np.savez_compressed(
                path,
                data=observation["data"],
                valid=observation["valid"],
                inside=observation["inside"],
                row_area_m2=observation["row_area_m2"],
            )
            chips.append(
                {
                    "tile_key": key,
                    "file": path.name,
                    "sha256": file_digest(path),
                    "transform": observation["transform"],
                    "window": observation["window"],
                    "crs": "EPSG:4326",
                }
            )
            crop += observation["crop_area_m2"]
            valid += observation["valid_area_m2"]
            sampled += observation["sampled_area_m2"]
        # Native pixel-centre integration can slightly exceed exact polygon area.
        # Preserve raw area ratios; clamp fractions only at the physical maximum.
        result = {
            "window_id": row["window_id"],
            "window_geodesic_area_m2": area,
            "crop_area_m2": crop,
            "valid_area_m2": valid,
            "sampled_area_m2": sampled,
            "crop_fraction_raw": crop / area,
            "valid_fraction_raw": valid / area,
            "crop_fraction": min(1.0, crop / area),
            "valid_fraction": min(1.0, valid / area),
            "area_method": "native pixel centres, geodesic row weights, complete-square denominator",
            "chips": chips,
        }
        result["eligible"] = (
            result["crop_fraction"] >= self.settings["min_crop_fraction"]
            and result["valid_fraction"] >= self.settings["min_valid_fraction"]
        )
        write_json(cached, result)
        print(
            f"  {row['window_id']}: crop={result['crop_fraction']:.3f}, valid={result['valid_fraction']:.3f}",
            file=sys.stderr,
            flush=True,
        )
        return result

    def verify(self):
        for identity in self.identities.values():
            if remote_identity(identity["url"]) != identity:
                raise ValueError(
                    f"WorldCover asset changed during run: {identity['url']}"
                )


def write_features(path, rows, zone_lookup):
    features = []
    for row in rows:
        properties = {
            k: v for k, v in row.items() if k not in {"geometry", "footprint"}
        }
        properties["metric_crs"] = zone_lookup[row["zone_id"]]["metric_crs"]
        properties["metric_bounds"] = list(row["geometry"].bounds)
        properties["center_lon"], properties["center_lat"] = sampling.project(
            row["geometry"].centroid, properties["metric_crs"], 4326
        ).coords[0]
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(row["footprint"]),
                "properties": properties,
            }
        )
    write_json(path, {"type": "FeatureCollection", "features": features})
    pd.DataFrame([f["properties"] for f in features]).to_csv(
        path.with_suffix(".csv"), index=False
    )


def run(config_path, out_dir):
    config_path, out_dir = Path(config_path), Path(out_dir).expanduser().resolve()
    settings = json.loads(config_path.read_text())
    if settings["year"] != 2024 or settings["worldcover_version"] != "v200/2021":
        raise ValueError(
            "This implementation supports the agreed 2024 / WorldCover 2021 pilot only"
        )
    zone_ids = [z["zone_id"] for z in settings["zones"]]
    if len(set(zone_ids)) != len(zone_ids):
        raise ValueError("Duplicate zone IDs")
    out_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = {
        "settings": settings,
        "code_sha256": {
            "select_descriptor_pilot.py": file_digest(__file__),
            "pilot_sampling.py": file_digest(sampling.__file__),
        },
        "packages": {
            name: version(name)
            for name in (
                "numpy",
                "shapely",
                "pyproj",
                "rasterio",
                "geopandas",
                "pyarrow",
            )
        },
    }
    frozen = out_dir / "inputs.json"
    if frozen.exists() and json.loads(frozen.read_text()) != fingerprint:
        raise ValueError(
            "Run inputs/code/environment changed; use a new output directory"
        )
    write_json(frozen, fingerprint)
    if (out_dir / "complete.json").exists():
        complete = json.loads((out_dir / "complete.json").read_text())
        for name, digest in complete["output_sha256"].items():
            if file_digest(out_dir / name) != digest:
                raise ValueError(f"Completed artifact changed: {name}")
        print(f"Verified completed selection: {out_dir}")
        return
    code_dir = out_dir / "source-code"
    code_dir.mkdir(exist_ok=True)
    for source in (Path(__file__), Path(sampling.__file__)):
        (code_dir / source.name).write_bytes(source.read_bytes())
    sources = Sources(out_dir / "sources")
    collection, _ = sources.fetch(
        settings["vector_collection_url"], "vector-collection.json"
    )
    vector_meta = json.loads(collection.read_text())
    # Freeze every normative vector item, including advertised asset checksums.
    for link in vector_meta["links"]:
        if link["rel"] == "item":
            url = urllib.parse.urljoin(settings["vector_collection_url"], link["href"])
            sources.fetch(url, f"vector-{Path(link['href']).stem}.json")
    raster_url = settings["inventory_url"].rsplit("/", 1)[0] + "/collection.json"
    raster_path, _ = sources.fetch(raster_url, "raster-collection.json")
    published_inventory = json.loads(raster_path.read_text())["assets"]["mirror"]
    expected = published_inventory["file:checksum"]
    if expected != "1220" + settings["inventory_sha256"]:
        raise ValueError("Live raster inventory differs from the agreed snapshot")
    inventory, _ = sources.fetch(
        settings["inventory_url"], "raster-items.parquet", expected
    )
    table = pq.read_table(inventory, columns=["geometry"])
    footprints = [from_wkb(value) for value in table["geometry"].to_pylist()]
    countries_path, _ = sources.fetch(
        settings["country_url"], "countries.geojson", settings["country_sha256"]
    )
    countries = {
        feature["properties"]["ADM0_A3"]: shape(feature["geometry"])
        for feature in json.loads(countries_path.read_text())["features"]
    }
    selected_all, reserve_all, summaries = [], [], []
    with ExitStack() as stack:
        stack.enter_context(
            rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                GDAL_HTTP_USERAGENT=USER_AGENT,
                GDAL_HTTP_MAX_RETRY=3,
                GDAL_HTTP_RETRY_DELAY=1,
            )
        )
        screen = CropScreen(out_dir / "crop-observations", settings, stack)
        for zone in settings["zones"]:
            print(f"Selecting {zone['zone_id']}...", file=sys.stderr, flush=True)
            country = countries[zone["country"]]
            coverage = sampling.processing_coverage(footprints, zone["bounds"])
            candidates, audit = sampling.candidate_grid(
                zone, coverage, country, settings
            )
            selected, reserves, checks = sampling.draw_windows(
                candidates,
                screen,
                count=settings["windows_per_zone"],
                reserves=settings["reserves_per_zone"],
                spacing=settings["min_spacing_m"],
            )
            roles = {
                r["window_id"]: (role, rank)
                for role, rows in (("primary", selected), ("reserve", reserves))
                for rank, r in enumerate(rows, 1)
            }
            for row in audit:
                check = checks.get(row["window_id"])
                if check:
                    row.update(
                        {
                            key: check[key]
                            for key in ("crop_fraction", "valid_fraction", "eligible")
                        }
                    )
                    row["status"] = (
                        "crop_eligible" if check["eligible"] else "crop_ineligible"
                    )
                elif row["status"] == "candidate":
                    row["status"] = "crop_not_evaluated"
                if row["window_id"] in roles:
                    row["role"], row["selection_rank"] = roles[row["window_id"]]
            location = out_dir / zone["zone_id"]
            location.mkdir(exist_ok=True)
            pd.DataFrame(audit).to_csv(location / "candidate-audit.csv", index=False)
            for role, rows in (("primary", selected), ("reserve", reserves)):
                for rank, row in enumerate(rows, 1):
                    row.update(
                        {
                            "role": role,
                            "selection_rank": rank,
                            "year": settings["year"],
                            "crop_fraction": checks[row["window_id"]]["crop_fraction"],
                            "valid_fraction": checks[row["window_id"]][
                                "valid_fraction"
                            ],
                        }
                    )
            gpd.GeoDataFrame(
                [
                    {k: v for k, v in r.items() if k != "footprint"}
                    for r in selected + reserves
                ],
                geometry="geometry",
                crs=zone["metric_crs"],
            ).to_parquet(location / "windows.parquet")
            selected_all.extend(selected)
            reserve_all.extend(reserves)
            summaries.append(
                {
                    "zone_id": zone["zone_id"],
                    "metric_crs": zone["metric_crs"],
                    "geometric_candidates": len(candidates),
                    "crop_evaluated": len(checks),
                    "audit_status_counts": dict(Counter(r["status"] for r in audit)),
                    "primary_ids": [r["window_id"] for r in selected],
                    "reserve_ids": [r["window_id"] for r in reserves],
                }
            )
            write_json(
                out_dir / "progress.json", {"updated_at": now(), "zones": summaries}
            )
        screen.verify()
    lookup = {z["zone_id"]: z for z in settings["zones"]}
    write_features(out_dir / "selected-windows.geojson", selected_all, lookup)
    write_features(out_dir / "reserve-windows.geojson", reserve_all, lookup)
    write_json(
        out_dir / "selection.json",
        {
            "study_id": settings["study_id"],
            "year": settings["year"],
            "completed_at": now(),
            "primary_count": len(selected_all),
            "reserve_count": len(reserve_all),
            "zones": summaries,
            "limits": [
                "Selected areas only: map review, polygon extraction and descriptors NOT performed",
                "Processing footprints do not establish complete detection or seam-free geometry",
                "Cropland screen is WorldCover 2021, not contemporaneous reference truth",
                "Crop eligibility is evaluated lazily in hash order; untested cells are explicit",
                "Reserve spacing must be checked against retained primaries when replacing a window",
                "Separate zone CRSs; no raw projected-coordinate pooling across zones",
                "Natural Earth 1:10m administrative boundaries are sampling masks, not legal boundary surveys",
            ],
        },
    )
    output_hashes = {
        str(p.relative_to(out_dir)): file_digest(p)
        for p in sorted(out_dir.rglob("*"))
        if p.is_file() and p.name != "complete.json"
    }
    write_json(
        out_dir / "complete.json",
        {"completed_at": now(), "output_sha256": output_hashes},
    )
    print(
        f"Selected {len(selected_all)} windows and {len(reserve_all)} reserves: {out_dir}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(args.config, args.out_dir)


if __name__ == "__main__":
    main()
