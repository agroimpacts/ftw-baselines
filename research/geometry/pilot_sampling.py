"""Study-specific, geometry-preserving area selection for descriptor pilots."""

import hashlib
import math

import numpy as np
from pyproj import CRS, Geod, Transformer
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds
from shapely import segmentize
from shapely.geometry import box, mapping
from shapely.ops import transform, unary_union

GEOD = Geod(ellps="WGS84")
WORLDCOVER_CLASSES = (10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100)


def priority(study_id, seed, zone_id, ix, iy):
    """Version-1 priority: SHA256 of these five UTF-8 fields separated by '|'."""
    return hashlib.sha256(f"{study_id}|{seed}|{zone_id}|{ix}|{iy}".encode()).hexdigest()


def project(geometry, source, target):
    return transform(
        Transformer.from_crs(source, target, always_xy=True).transform, geometry
    )


def geographic_window(geometry, metric_crs):
    """Densify metric edges at <=100 m before representing them in lon/lat."""
    return project(segmentize(geometry, 100), metric_crs, "EPSG:4326")


def candidate_grid(zone, coverage, country, settings):
    """Return ranked eligible metric squares and an audit of every bounding-grid cell.

    Country and coverage are tested in lon/lat against densified square edges;
    no country simplification, polygon repair, or containment tolerance is used.
    """
    crs = CRS.from_user_input(zone["metric_crs"])
    if not crs.is_projected or any(
        a.unit_conversion_factor != 1 for a in crs.axis_info[:2]
    ):
        raise ValueError("Sampling CRS must be projected in metres")
    domain = box(*zone["bounds"])
    for name, geometry in (("coverage", coverage), ("country", country)):
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Invalid or empty {name} geometry")
    extent = project(segmentize(domain, 0.001), 4326, crs).bounds
    size = settings["grid_size_m"]
    if size <= 0:
        raise ValueError("grid_size_m must be positive")
    candidates, audit = [], []
    for ix in range(math.floor(extent[0] / size), math.ceil(extent[2] / size)):
        for iy in range(math.floor(extent[1] / size), math.ceil(extent[3] / size)):
            square = box(ix * size, iy * size, (ix + 1) * size, (iy + 1) * size)
            footprint = geographic_window(square, crs)
            status = "candidate"
            for name, boundary in (
                ("zone", domain),
                ("country", country),
                ("coverage", coverage),
            ):
                if not boundary.covers(footprint):
                    status = f"outside_{name}"
                    break
            row = {
                "zone_id": zone["zone_id"],
                "window_id": f"{zone['zone_id']}_{ix}_{iy}",
                "ix": ix,
                "iy": iy,
                "priority": priority(
                    settings["study_id"], settings["seed"], zone["zone_id"], ix, iy
                ),
                "status": status,
            }
            audit.append(row)
            if status == "candidate":
                candidates.append(row | {"geometry": square, "footprint": footprint})
    candidates.sort(key=lambda row: (row["priority"], row["ix"], row["iy"]))
    return candidates, audit


def draw_windows(candidates, screen, *, count, reserves, spacing):
    """Screen in hash order, selecting separated primaries then ordered reserves.

    Crop checks are lazy: candidates too close to an accepted primary need not be
    read unless reconsidered for reserves. Unvisited candidates are not labeled
    crop-eligible. This yields the same primary draw as screening every cell first.
    Reserves have no spacing guarantee; check against retained primaries on use.
    """
    if count < 1 or reserves < 0 or spacing < 0:
        raise ValueError("Invalid count, reserves or spacing")
    ordered = sorted(
        candidates, key=lambda row: (row["priority"], row["ix"], row["iy"])
    )
    selected, reserve_rows, checks = [], [], {}

    def eligible(row):
        key = row["window_id"]
        if key not in checks:
            checks[key] = screen(row)
        return checks[key]["eligible"]

    for row in ordered:
        if any(
            row["geometry"].distance(other["geometry"]) < spacing for other in selected
        ):
            continue
        if eligible(row):
            selected.append(row)
            if len(selected) == count:
                break
    if len(selected) != count:
        raise ValueError(
            f"Only {len(selected)} separated eligible windows; need {count}"
        )
    selected_ids = {row["window_id"] for row in selected}
    for row in ordered:
        if len(reserve_rows) == reserves:
            break
        if row["window_id"] not in selected_ids and eligible(row):
            reserve_rows.append(row)
    if len(reserve_rows) != reserves:
        raise ValueError(f"Only {len(reserve_rows)} eligible reserves; need {reserves}")
    return selected, reserve_rows, checks


def worldcover_tiles(footprint):
    """Enumerate native 3-degree WorldCover tile keys intersecting a footprint."""
    xmin, ymin, xmax, ymax = footprint.bounds
    tiles = []
    for lon in range(math.floor(xmin / 3) * 3, math.ceil(xmax / 3) * 3, 3):
        for lat in range(math.floor(ymin / 3) * 3, math.ceil(ymax / 3) * 3, 3):
            tile = box(lon, lat, lon + 3, lat + 3)
            if footprint.intersection(tile).area > 0:
                key = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
                tiles.append((key, tile))
    return tiles


def crop_observation(dataset, footprint):
    """Read a native categorical crop chip; approximate areas by pixel centres.

    No overviews/resampling. Geodesic pixel areas vary by row. Outside/nodata and
    unknown classes are not counted as valid. The complete square, including
    water, is the fraction denominator (computed by the caller).
    """
    if dataset.crs != CRS.from_epsg(4326):
        raise ValueError("WorldCover chip must use EPSG:4326")
    if dataset.transform.b or dataset.transform.d:
        raise ValueError("Expected an axis-aligned WorldCover grid")
    intersection = footprint.intersection(box(*dataset.bounds))
    if intersection.is_empty:
        raise ValueError("WorldCover tile does not overlap window")
    raw = from_bounds(*intersection.bounds, dataset.transform)
    x0, y0 = math.floor(raw.col_off), math.floor(raw.row_off)
    x1, y1 = math.ceil(raw.col_off + raw.width), math.ceil(raw.row_off + raw.height)
    window = Window(x0, y0, x1 - x0, y1 - y0).intersection(
        Window(0, 0, dataset.width, dataset.height)
    )
    values = dataset.read(1, window=window, masked=True)
    affine = dataset.window_transform(window)
    inside = geometry_mask(
        [mapping(footprint)], values.shape, affine, invert=True, all_touched=False
    )
    valid = (
        inside & ~np.ma.getmaskarray(values) & np.isin(values.data, WORLDCOVER_CLASSES)
    )
    crop = valid & (values.data == 40)
    weights = []
    for row in range(values.shape[0]):
        left, top = affine * (0, row)
        right, bottom = affine * (1, row + 1)
        area, _ = GEOD.polygon_area_perimeter(
            [left, right, right, left], [top, top, bottom, bottom]
        )
        weights.append(abs(area))
    weights = np.asarray(weights)
    return {
        "crop_area_m2": float(np.dot(crop.sum(axis=1), weights)),
        "valid_area_m2": float(np.dot(valid.sum(axis=1), weights)),
        "sampled_area_m2": float(np.dot(inside.sum(axis=1), weights)),
        "data": values.data,
        "valid": valid,
        "inside": inside,
        "row_area_m2": weights,
        "transform": list(affine)[:6],
        "window": [window.col_off, window.row_off, window.width, window.height],
    }


def processing_coverage(geometries, bounds):
    domain = box(*bounds)
    intersecting = [g for g in geometries if g.intersects(domain)]
    if not intersecting:
        raise ValueError("No published processing footprints intersect sampling zone")
    return unary_union(intersecting)
