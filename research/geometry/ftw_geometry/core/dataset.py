"""Resumable, bounded-batch descriptors of existing final polygon datasets.

No model inference, geometry repair, cross-tile stitching or reference scoring.
"""

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from shapely import from_wkb, normalize, to_wkb

from ftw_geometry.core.descriptors import (
    DESCRIPTOR_COLUMNS,
    DESCRIPTOR_VERSION,
    NARROW_NECK_COMPONENT_FRACTION,
    NARROW_NECK_RADIUS_FRACTION,
    describe_polygons,
    metric_geometry_crs,
)
from ftw_geometry.io.manifests import file_digest, write_json


def vector_batches(path, batch_size, layer=None):
    """Read standard WKB GeoParquet by row group batches, other vectors by rows."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        parquet = pq.ParquetFile(path)
        metadata = json.loads(parquet.schema_arrow.metadata.get(b"geo", b"{}"))
        column = metadata.get("primary_column")
        if column is None:
            raise ValueError(f"Expected GeoParquet metadata: {path}")
        geometry_metadata = metadata["columns"][column]
        if geometry_metadata.get("encoding") != "WKB":
            raise ValueError(
                "Only standard WKB GeoParquet geometry encoding is supported"
            )
        # GeoParquet omission defaults to OGC:CRS84; an explicit null is unknown.
        crs = geometry_metadata.get("crs", "OGC:CRS84")
        if crs is None:
            raise ValueError("Input geometry CRS is unknown")
        for batch in parquet.iter_batches(batch_size=batch_size):
            frame = batch.to_pandas()
            geometry = gpd.GeoSeries.from_wkb(frame.pop(column), crs=crs)
            yield gpd.GeoDataFrame(frame, geometry=geometry, crs=crs)
    else:
        import pyogrio

        offset = 0
        while True:
            frame = pyogrio.read_dataframe(
                path, layer=layer, skip_features=offset, max_features=batch_size
            )
            if frame.empty:
                break
            yield frame
            offset += len(frame)


def dataset_parts(directory):
    """Yield only completed, verified source partitions in manifest order."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    for source in manifest["sources"]:
        location = directory / "sources" / source["partition"]
        checkpoint = location / "complete.json"
        if not checkpoint.exists():
            raise ValueError(f"Incomplete descriptor source: {source['source_id']}")
        complete = json.loads(checkpoint.read_text())
        for part in complete["parts"]:
            path = location / part["file"]
            if file_digest(path) != part["sha256"]:
                raise ValueError(f"Descriptor partition changed: {path}")
            yield path


def descriptor_batches(directory):
    for path in dataset_parts(directory):
        yield pd.read_parquet(path)


def geometry_frame(table, crs):
    return gpd.GeoDataFrame(
        table.drop(columns="geometry_wkb"),
        geometry=from_wkb(table.geometry_wkb.to_numpy()),
        crs=crs,
    )


def build_dataset(config_path, out_dir, batch_size=10000):
    """Freeze inputs/settings, then atomically checkpoint each complete source.

    Resume reuses completed sources only when config, input bytes, descriptor
    version and batch size match. Incomplete sources restart, never append.
    """
    config_path, out_dir = Path(config_path).resolve(), Path(out_dir)
    config = json.loads(config_path.read_text())
    required = {
        "dataset_id",
        "run_id",
        "metric_crs",
        "duplicate_policy",
        "field_semantics",
        "sources",
    }
    if required - config.keys():
        raise ValueError(
            f"Missing manifest settings: {sorted(required - config.keys())}"
        )
    if not config["dataset_id"] or not config["run_id"] or not config["sources"]:
        raise ValueError("Nonempty dataset/run IDs and sources are required")
    if config["duplicate_policy"] not in {"keep", "error-identical"}:
        raise ValueError("duplicate_policy must be keep or error-identical")
    if config["field_semantics"] not in {"complete-fields", "tile-fragments"}:
        raise ValueError("field_semantics must be complete-fields or tile-fragments")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    crs = metric_geometry_crs(gpd.GeoDataFrame(geometry=[], crs=config["metric_crs"]))
    sources, seen = [], set()
    for original in config["sources"]:
        source = dict(original)
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in seen:
            raise ValueError("Each source_id must be a unique nonempty string")
        seen.add(source_id)
        if "provenance" not in source:
            raise ValueError("Each source must explicitly supply a provenance object")
        if not isinstance(source["provenance"], dict):
            raise TypeError("Source provenance must be an object")
        for name in ("path", "footprint"):
            if source.get(name) is not None:
                path = Path(source[name])
                path = path if path.is_absolute() else config_path.parent / path
                source[name] = str(path.resolve())
                source[name + "_sha256"] = file_digest(path)
        if not source.get("path"):
            raise ValueError("Each source needs a vector path")
        if Path(source["path"]).suffix.lower() == ".shp":
            raise ValueError(
                "Convert shapefile inputs to GeoParquet/GPKG first; provenance must hash all data"
            )
        source["partition"] = hashlib.sha256(source_id.encode()).hexdigest()[:24]
        sources.append(source)
    manifest = {
        **config,
        "sources": sources,
        "metric_crs": crs.to_string(),
        "descriptor_version": DESCRIPTOR_VERSION,
        "batch_size": batch_size,
        "dataset_schema_version": "1.0",
        "pipeline_sha256": file_digest(__file__),
        "descriptor_code_sha256": file_digest(
            Path(__file__).with_name("descriptors.py")
        ),
        "parameters": {
            "orientation_ambiguity_max_elongation": 1.05,
            "narrow_neck_radius_fraction": NARROW_NECK_RADIUS_FRACTION,
            "narrow_neck_component_fraction": NARROW_NECK_COMPONENT_FRACTION,
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_manifest = out_dir / "manifest.json"
    if saved_manifest.exists():
        if json.loads(saved_manifest.read_text()) != manifest:
            raise ValueError("Inputs/settings changed; choose a new output directory")
    elif any(out_dir.iterdir()):
        raise ValueError("Output must be new/empty or a matching descriptor dataset")
    else:
        write_json(saved_manifest, manifest)
    root = out_dir / "sources"
    root.mkdir(exist_ok=True)
    # SQLite keeps cross-batch identity validation bounded in RAM.
    with tempfile.TemporaryDirectory(prefix=".identity-", dir=out_dir) as scratch:  # noqa: SIM117 -- database must close before directory cleanup
        with sqlite3.connect(Path(scratch) / "seen.sqlite") as database:
            database.execute(
                "CREATE TABLE ids (source TEXT, id TEXT, PRIMARY KEY(source,id))"
            )
            database.execute("CREATE TABLE shapes (hash TEXT PRIMARY KEY)")

            def register(table, source_id):
                for field_id, geometry_hash in zip(table.id, table.geometry_hash):
                    try:
                        database.execute(
                            "INSERT INTO ids VALUES (?, ?)", (source_id, str(field_id))
                        )
                    except sqlite3.IntegrityError as error:
                        raise ValueError(
                            f"Duplicate field ID in {source_id}: {field_id}"
                        ) from error
                    if config["duplicate_policy"] == "error-identical":
                        try:
                            database.execute(
                                "INSERT INTO shapes VALUES (?)", (geometry_hash,)
                            )
                        except sqlite3.IntegrityError as error:
                            raise ValueError(
                                "Identical geometry repeated; fix inputs or explicitly choose keep"
                            ) from error
                database.commit()

            for source in sources:
                destination = root / source["partition"]
                if destination.exists():
                    complete = json.loads((destination / "complete.json").read_text())
                    for part in complete["parts"]:
                        path = destination / part["file"]
                        if file_digest(path) != part["sha256"]:
                            raise ValueError(f"Descriptor partition changed: {path}")
                        register(pd.read_parquet(path), source["source_id"])
                    continue
                footprint = None
                if source.get("footprint"):
                    boundary = gpd.read_file(source["footprint"]).to_crs(crs)
                    if (
                        boundary.empty
                        or not boundary.is_valid.all()
                        or not boundary.geom_type.isin(
                            ["Polygon", "MultiPolygon"]
                        ).all()
                    ):
                        raise ValueError(
                            "Footprint must contain valid polygon geometry"
                        )
                    footprint = boundary.geometry.union_all()
                with tempfile.TemporaryDirectory(
                    prefix=".source-", dir=out_dir
                ) as temporary:
                    staged = Path(temporary) / "partition"
                    staged.mkdir()
                    parts, count = [], 0
                    for index, frame in enumerate(
                        vector_batches(source["path"], batch_size, source.get("layer"))
                    ):
                        id_column = source.get("id_column", "id")
                        if id_column not in frame or frame[id_column].isna().any():
                            raise ValueError(
                                f"Missing/null field IDs in {source['source_id']}"
                            )
                        projected = frame.to_crs(crs).copy()
                        projected["id"] = frame[id_column].astype(str)
                        table = describe_polygons(projected, crs)
                        table["id"] = table.id.astype("string")
                        for column in DESCRIPTOR_COLUMNS[1:]:
                            dtype = (
                                "bool"
                                if column in {"narrow_neck", "orientation_ambiguous"}
                                else ("int64" if column == "hole_count" else "float64")
                            )
                            table[column] = table[column].astype(dtype)
                        table["dataset_id"], table["run_id"] = (
                            config["dataset_id"],
                            config["run_id"],
                        )
                        table["source_id"] = source["source_id"]
                        table["field_key"] = [
                            json.dumps(
                                [
                                    config["dataset_id"],
                                    config["run_id"],
                                    source["source_id"],
                                    value,
                                ],
                                separators=(",", ":"),
                            )
                            for value in table.id
                        ]
                        table["descriptor_version"] = DESCRIPTOR_VERSION
                        table["geometry_wkb"] = to_wkb(projected.geometry.to_numpy())
                        table["geometry_hash"] = [
                            hashlib.sha256(value).hexdigest()
                            for value in to_wkb(
                                normalize(projected.geometry.to_numpy())
                            )
                        ]
                        table["centroid_x"] = projected.centroid.x.to_numpy()
                        table["centroid_y"] = projected.centroid.y.to_numpy()
                        table["orientation_cos2"] = np.cos(
                            2 * np.deg2rad(table.orientation_deg)
                        )
                        table["orientation_sin2"] = np.sin(
                            2 * np.deg2rad(table.orientation_deg)
                        )
                        tolerance = float(source.get("edge_tolerance_m", 0))
                        if tolerance < 0:
                            raise ValueError("edge_tolerance_m must be nonnegative")
                        inner = (
                            footprint.buffer(-tolerance)
                            if footprint is not None
                            else None
                        )
                        table["touches_source_edge"] = pd.array(
                            [
                                not inner.contains(geometry)
                                or footprint.boundary.intersects(geometry)
                                for geometry in projected.geometry
                            ]
                            if footprint is not None
                            else [None] * len(table),
                            dtype="boolean",
                        )
                        if (
                            footprint is not None
                            and not projected.geometry.map(footprint.covers).all()
                        ):
                            raise ValueError(
                                "Source footprint does not cover its fields"
                            )
                        register(table, source["source_id"])
                        path = staged / f"part-{index:06d}.parquet"
                        table.to_parquet(path, index=False)
                        parts.append(
                            {
                                "file": path.name,
                                "sha256": file_digest(path),
                                "rows": len(table),
                            }
                        )
                        count += len(table)
                    for name in ("path", "footprint"):
                        if (
                            source.get(name)
                            and file_digest(source[name]) != source[name + "_sha256"]
                        ):
                            raise ValueError(
                                "Source changed during descriptor generation; choose a new output directory"
                            )
                    write_json(
                        staged / "complete.json",
                        {
                            "source_id": source["source_id"],
                            "rows": count,
                            "parts": parts,
                        },
                    )
                    staged.replace(destination)
    write_json(
        out_dir / "complete.json",
        {
            "sources": len(sources),
            "rows": sum(
                json.loads((root / source["partition"] / "complete.json").read_text())[
                    "rows"
                ]
                for source in sources
            ),
        },
    )
    return manifest
