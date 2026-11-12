"""Opt-in fixed-preset FBP export, separate from legacy semantic cleanup."""

import json
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from affine import Affine
from pyproj import CRS
from rasterio.features import shapes
from shapely import make_valid
from shapely.affinity import affine_transform
from shapely.geometry import Polygon, box, shape
from shapely.ops import unary_union

from ftw_tools.postprocess.descriptors import (
    DESCRIPTOR_VERSION,
    NARROW_NECK_COMPONENT_FRACTION,
    NARROW_NECK_RADIUS_FRACTION,
    describe_polygons,
    metric_geometry_crs,
)


def pixel_area_m2(dataset):
    """Match the fixed-preset assessment's scalar area convention exactly."""
    crs, affine = dataset.crs, dataset.transform
    if crs is None:
        raise ValueError("Area filtering requires a known CRS")
    if crs.is_projected:
        area = (
            abs(affine.a * affine.e - affine.b * affine.d)
            * crs.linear_units_factor[1] ** 2
        )
    elif crs.is_geographic and affine.b == 0 and affine.d == 0:
        geod = CRS.from_user_input(crs).get_geod()
        areas = []
        col = dataset.width // 2
        for row in range(dataset.height):
            points = [
                affine * point
                for point in (
                    (col, row),
                    (col + 1, row),
                    (col + 1, row + 1),
                    (col, row + 1),
                )
            ]
            area, _ = geod.polygon_area_perimeter(*zip(*points))
            areas.append(abs(area))
        area = float(np.mean(areas))
    else:
        raise ValueError("Unsupported grid for metric pixel area")
    if not np.isfinite(area) or area <= 0:
        raise ValueError("Invalid metric pixel area")
    return area


def labels_to_polygons(labels, transform, crs, stride=2048):
    """Join window fragments only within their original ID; explode multipart.

    Holes are preserved. Output IDs are '<instance_id>:<part>', with parts
    ordered by bounds for repeatability. Zero is background.
    """
    if labels.ndim != 2 or labels.dtype.kind not in "iu" or np.any(labels < 0):
        raise ValueError("Expected a nonnegative two-dimensional integer label raster")
    if stride < 1 or labels.max(initial=0) > np.iinfo(np.int32).max:
        raise ValueError("Invalid stride or labels exceed int32 capacity")
    groups = {}
    for y in range(0, labels.shape[0], stride):
        for x in range(0, labels.shape[1], stride):
            tile = labels[y : y + stride, x : x + stride].astype("int32")
            # Reunite exact integer pixel edges before georeferencing. Applying
            # floating-point affine offsets per window creates microscopic gaps.
            affine = Affine.translation(x, y)
            for geometry, value in shapes(tile, mask=tile != 0, transform=affine):
                groups.setdefault(int(value), []).append(shape(geometry))
    rows = []
    for instance_id, fragments in sorted(groups.items()):
        # Drop collinear window-edge vertices while coordinates are still exact;
        # otherwise a rotated affine can turn them into tiny numerical zigzags.
        geometry = make_valid(
            unary_union(fragments).simplify(0, preserve_topology=True)
        )
        parts = [geometry] if isinstance(geometry, Polygon) else list(geometry.geoms)
        for part, polygon in enumerate(sorted(parts, key=lambda g: g.bounds), 1):
            if not isinstance(polygon, Polygon):
                raise TypeError("Instance repair produced non-polygon geometry")
            rows.append(
                {
                    "id": f"{instance_id}:{part}",
                    "instance_id": instance_id,
                    "geometry": affine_transform(
                        polygon,
                        [
                            transform.a,
                            transform.b,
                            transform.d,
                            transform.e,
                            transform.c,
                            transform.f,
                        ],
                    ),
                }
            )
    return gpd.GeoDataFrame(
        rows, columns=["id", "instance_id", "geometry"], geometry="geometry", crs=crs
    )


def polygonize_fbp(
    input,
    out,
    *,
    overwrite=False,
    stride=2048,
    simplify=0,
    min_size=0,
    max_size=None,
    close_interiors=False,
):
    """Export a whole-scene FTW_2E result from three-band saved probabilities.

    Full-scene FBP avoids claiming unverified windowed inference equivalence.
    Only vectorization is tiled, followed by same-ID seam reconstruction.
    """
    try:
        import fbp
    except ImportError as error:
        raise ImportError("FTW_2E export requires ftw-tools[fbp]") from error

    from ftw_tools.inference.utils import convert_to_fiboa

    out = Path(out or str(Path(input).with_suffix(".parquet")))
    sidecar = Path(str(out) + ".descriptors.csv")
    metadata_path = Path(str(out) + ".metadata.json")
    for target in (out, sidecar, metadata_path):
        if target.exists() and not overwrite:
            raise FileExistsError(target)
    if (
        stride < 1
        or simplify < 0
        or min_size < 0
        or (max_size is not None and max_size < min_size)
    ):
        raise ValueError(
            "Stride must be positive and cleanup sizes nonnegative and ordered"
        )
    if out.suffix not in {".parquet", ".geojson", ".gpkg", ".fgb"}:
        raise ValueError("FBP export supports parquet, geojson, gpkg and fgb")
    with rasterio.open(input) as src:
        if src.count != 3 or src.crs is None:
            raise ValueError("FBP requires georeferenced three-band probabilities")
        probabilities = src.read().astype("float32")
        if all(dtype == "uint8" for dtype in src.dtypes):
            probabilities /= 255
        if not np.isfinite(probabilities).all() or np.any(
            (probabilities < 0) | (probabilities > 1)
        ):
            raise ValueError("Probabilities must be finite and in [0, 1]")
        if not np.allclose(probabilities.sum(axis=0), 1, atol=0.02):
            raise ValueError("Probability bands must sum to one")
        if not src.read_masks().all():
            raise ValueError(
                "Masked/nodata probabilities are not supported; supply a complete grid"
            )
        pixel_area = pixel_area_m2(src)
        labels = fbp.FTW_2E(
            probabilities.argmax(axis=0), probabilities, pixel_area_m2=pixel_area
        )
        frame = labels_to_polygons(np.asarray(labels), src.transform, src.crs, stride)
        extent = gpd.GeoDataFrame(geometry=[box(*src.bounds)], crs=src.crs)
        metric_crs = metric_geometry_crs(extent)
        metadata = {
            "method": "ftw-2e",
            "descriptor_version": DESCRIPTOR_VERSION,
            "descriptor_parameters": {
                "narrow_neck_radius_fraction": NARROW_NECK_RADIUS_FRACTION,
                "narrow_neck_component_fraction": NARROW_NECK_COMPONENT_FRACTION,
                "orientation_ambiguity_max_elongation": 1.05,
                "orientation_convention": "axial degrees counterclockwise from projected +x; NaN if ambiguous",
            },
            "ftw_fbp_version": version("ftw-fbp"),
            "configuration": asdict(fbp.FTW_2E),
            "input": str(Path(input).resolve()),
            "input_crs": src.crs.to_string(),
            "metric_crs": metric_crs.to_string(),
            "transform": list(src.transform),
            "shape": list(src.shape),
            "pixel_area_m2": pixel_area,
            "pixel_area_definition": "projected affine area with unit conversion, or mean geodesic pixel area across geographic rows; no resampling",
            "probability_encoding": "uint8 / 255"
            if all(dtype == "uint8" for dtype in src.dtypes)
            else "float [0, 1]",
            "vectorization_stride": stride,
            "fbp_processing": "whole-scene",
            "cleanup": {
                "simplify_m": simplify,
                "min_area_m2": min_size,
                "max_area_m2": max_size,
                "close_interiors": close_interiors,
            },
        }
    source_crs = frame.crs
    # With cleanup disabled retain exact pixel-edge geometry in the source CRS.
    if close_interiors or simplify:
        frame = frame.to_crs(metric_crs)
    if close_interiors:
        frame.geometry = frame.geometry.map(lambda g: Polygon(g.exterior))
    if simplify:
        frame.geometry = frame.geometry.simplify(simplify, preserve_topology=True)
    frame = frame[~frame.geometry.is_empty].copy()
    if not frame.geometry.is_valid.all() or not frame.geom_type.eq("Polygon").all():
        raise ValueError("Cleanup must produce valid single polygons")
    areas = frame.to_crs(metric_crs).area
    frame = frame[
        (areas >= min_size) & ((areas <= max_size) if max_size is not None else True)
    ].copy()
    frame = frame.to_crs(source_crs)
    descriptors = describe_polygons(frame, metric_crs=metric_crs).set_index("id")
    frame["metrics:area"] = frame.id.map(descriptors.area_m2)
    frame["metrics:perimeter"] = frame.id.map(descriptors.perimeter_m)
    if out.suffix == ".parquet":
        convert_to_fiboa(frame.copy(), str(out), None)
    elif out.suffix == ".geojson":
        frame.to_crs(4326).to_file(out, driver="GeoJSON")
    else:
        frame.to_file(out, driver={".gpkg": "GPKG", ".fgb": "FlatGeobuf"}[out.suffix])
    # The sidecar describes the actual persisted geometry, including GeoJSON's
    # mandatory reprojection. Never assume that writer property schemas retain it.
    written = gpd.read_parquet(out) if out.suffix == ".parquet" else gpd.read_file(out)
    if written.empty and out.suffix == ".geojson":
        # Empty GeoJSON has no property schema; the header-only sidecar carries it.
        written = frame.iloc[:0].copy()
    if set(written.id) != set(frame.id) or not written.id.is_unique:
        raise ValueError("Export did not preserve unique field IDs")
    describe_polygons(written, metric_crs=metric_crs).to_csv(sidecar, index=False)
    metadata["exported_fields"] = len(written)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return frame
