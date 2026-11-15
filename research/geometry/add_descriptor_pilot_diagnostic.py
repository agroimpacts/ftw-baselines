"""Add a user-selected shifted diagnostic without changing a frozen pilot draw."""

import argparse
import json
import math
import re
from contextlib import ExitStack
from pathlib import Path

import geopandas as gpd
import pyarrow.parquet as pq
import rasterio
from ftw_geometry.io.manifests import file_digest, write_json
from shapely import from_wkb
from shapely.affinity import translate
from shapely.geometry import box, shape

from research.geometry.pilot_sampling import geographic_window, processing_coverage
from research.geometry.select_descriptor_pilot import CropScreen, now, write_features


def shifted_diagnostic(source, west_m, window_id):
    if not math.isfinite(west_m) or west_m <= 0:
        raise ValueError("west_m must be finite and positive")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", window_id):
        raise ValueError("window_id must be a simple filename-safe identifier")
    return {
        "zone_id": source["zone_id"],
        "window_id": window_id,
        "source_window_id": source["window_id"],
        "year": source["year"],
        "role": "diagnostic",
        "include_in_primary_statistics": False,
        "selection_method": "user-selected grid-west translation; not a random draw",
        "shift_easting_m": -float(west_m),
        "shift_northing_m": 0.0,
        "geometry": translate(source["geometry"], xoff=-west_m),
    }


def run(selection_dir, source_window_id, west_m, window_id, out_dir):
    selection_dir = Path(selection_dir).expanduser().resolve()
    out_dir = Path(out_dir).expanduser().resolve()
    if out_dir == selection_dir or selection_dir in out_dir.parents:
        raise ValueError("Diagnostic output must be outside the frozen selection")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError("Use a new empty diagnostic output directory")
    # Validate the parent before deriving a supplementary geometry.
    complete = json.loads((selection_dir / "complete.json").read_text())
    for name, digest in complete["output_sha256"].items():
        if file_digest(selection_dir / name) != digest:
            raise ValueError(f"Parent selection artifact changed: {name}")
    settings = json.loads((selection_dir / "inputs.json").read_text())["settings"]
    matches = []
    for zone in settings["zones"]:
        frame = gpd.read_parquet(selection_dir / zone["zone_id"] / "windows.parquet")
        matches.extend(
            (zone, row)
            for row in frame.to_dict("records")
            if row["window_id"] == source_window_id
        )
    if len(matches) != 1:
        raise ValueError("Source window must identify exactly one frozen window")
    zone, source = matches[0]
    row = shifted_diagnostic(source, west_m, window_id)
    row["footprint"] = geographic_window(row["geometry"], zone["metric_crs"])
    countries = json.loads((selection_dir / "sources/countries.geojson").read_text())
    country = next(
        shape(f["geometry"])
        for f in countries["features"]
        if f["properties"]["ADM0_A3"] == zone["country"]
    )
    inventory = pq.read_table(
        selection_dir / "sources/raster-items.parquet", columns=["geometry"]
    )
    coverage = processing_coverage(
        [from_wkb(v) for v in inventory["geometry"].to_pylist()], zone["bounds"]
    )
    for name, geometry in (
        ("zone", box(*zone["bounds"])),
        ("country", country),
        ("coverage", coverage),
    ):
        if not geometry.covers(row["footprint"]):
            raise ValueError(f"Diagnostic falls outside {name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        out_dir / "inputs.json",
        {
            "parent_selection": str(selection_dir),
            "parent_complete_sha256": file_digest(selection_dir / "complete.json"),
            "source_window_id": source_window_id,
            "window_id": window_id,
            "west_m": west_m,
            "metric_crs": zone["metric_crs"],
            "script_sha256": file_digest(__file__),
            "settings": settings,
            "reason": f"User-selected {west_m:g} m grid-west diagnostic from {source_window_id}; imagery confirmation pending",
        },
    )
    with ExitStack() as stack:
        stack.enter_context(
            rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                GDAL_HTTP_MAX_RETRY=3,
                GDAL_HTTP_RETRY_DELAY=1,
            )
        )
        screen = CropScreen(out_dir / "crop-observations", settings, stack)
        observation = screen(row)
        screen.verify()
    row.update({key: observation[key] for key in ("crop_fraction", "valid_fraction")})
    row["meets_primary_crop_screen"] = observation["eligible"]
    write_features(
        out_dir / "diagnostic-windows.geojson", [row], {zone["zone_id"]: zone}
    )
    gpd.GeoDataFrame(
        [{key: value for key, value in row.items() if key != "footprint"}],
        geometry="geometry",
        crs=zone["metric_crs"],
    ).to_parquet(out_dir / "diagnostic-windows.parquet")
    (out_dir / "add_descriptor_pilot_diagnostic.py").write_bytes(
        Path(__file__).read_bytes()
    )
    write_json(
        out_dir / "complete.json",
        {
            "completed_at": now(),
            "diagnostic_count": 1,
            "primary_sample_changed": False,
            "output_sha256": {
                str(p.relative_to(out_dir)): file_digest(p)
                for p in sorted(out_dir.rglob("*"))
                if p.is_file()
            },
        },
    )
    print(f"Added diagnostic {window_id}: {out_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection_dir")
    parser.add_argument("--source_window", required=True)
    parser.add_argument("--west_m", type=float, required=True)
    parser.add_argument("--window_id", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(
        args.selection_dir,
        args.source_window,
        args.west_m,
        args.window_id,
        args.out_dir,
    )


if __name__ == "__main__":
    main()
