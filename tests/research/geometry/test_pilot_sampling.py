import hashlib
import io
import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import box

from research.geometry import select_descriptor_pilot as runner
from research.geometry.pilot_sampling import (
    candidate_grid,
    crop_observation,
    draw_windows,
    geographic_window,
    priority,
    processing_coverage,
    worldcover_tiles,
)


def candidate(ix, *, order=None):
    return {
        "window_id": f"cell-{ix}",
        "ix": ix,
        "iy": 0,
        "priority": f"{ix if order is None else order:04d}",
        "geometry": box(ix * 10000, 0, (ix + 1) * 10000, 10000),
    }


def test_priority_contract():
    value = "ftw2e-descriptor-pilot-v1|20261112|bahia|10|-2"
    assert (
        priority("ftw2e-descriptor-pilot-v1", "20261112", "bahia", 10, -2)
        == hashlib.sha256(value.encode()).hexdigest()
    )


def test_draw_spacing_thresholds_order_and_reserves():
    calls = []

    def screen(row):
        calls.append(row["ix"])
        return {"eligible": row["ix"] != 0}

    rows = [candidate(i) for i in range(12)]
    primary, reserves, checks = draw_windows(
        list(reversed(rows)), screen, count=3, reserves=2, spacing=10000
    )
    assert [r["ix"] for r in primary] == [1, 3, 5]
    assert [r["ix"] for r in reserves] == [2, 4]
    assert calls == [0, 1, 3, 5, 2, 4]
    assert 6 not in [row["ix"] for row in rows if row["window_id"] in checks]
    for i, row in enumerate(primary):
        assert all(
            row["geometry"].distance(other["geometry"]) >= 10000
            for other in primary[:i]
        )


def test_lazy_draw_matches_exhaustive_eligibility():
    rows = [candidate(i, order=(i * 7) % 19) for i in range(19)]
    eligible = {i: i % 3 != 0 for i in range(19)}
    actual, _, _ = draw_windows(
        rows,
        lambda row: {"eligible": eligible[row["ix"]]},
        count=3,
        reserves=0,
        spacing=10000,
    )
    expected = []
    for row in sorted(rows, key=lambda r: r["priority"]):
        if eligible[row["ix"]] and all(
            row["geometry"].distance(other["geometry"]) >= 10000 for other in expected
        ):
            expected.append(row)
            if len(expected) == 3:
                break
    assert actual == expected


def test_insufficient_sample_fails_without_relaxing_spacing():
    with pytest.raises(ValueError, match="separated"):
        draw_windows(
            [candidate(0), candidate(1)],
            lambda _: {"eligible": True},
            count=2,
            reserves=0,
            spacing=10000,
        )
    with pytest.raises(ValueError, match="reserves"):
        draw_windows(
            [candidate(0)], lambda _: {"eligible": True}, count=1, reserves=1, spacing=0
        )


def test_grid_full_containment_and_holes():
    zone = {
        "zone_id": "test",
        "bounds": [3.0, 0.0, 3.5, 0.5],
        "metric_crs": "EPSG:32631",
    }
    settings = {"study_id": "test", "seed": "1", "grid_size_m": 10000}
    domain = box(*zone["bounds"])
    full, _ = candidate_grid(zone, domain, domain, settings)
    assert full
    hole = full[len(full) // 2]["footprint"].representative_point().buffer(0.001)
    country = domain.difference(hole)
    actual, audit = candidate_grid(zone, domain, country, settings)
    assert len(actual) < len(full)
    assert any(row["status"] == "outside_country" for row in audit)
    assert all(country.covers(row["footprint"]) for row in actual)
    assert all(row["geometry"].area == 100000000 for row in actual)
    assert [row["priority"] for row in actual] == sorted(
        row["priority"] for row in actual
    )
    assert len(actual[0]["footprint"].exterior.coords) > 4


def test_no_processing_coverage_is_not_empty_predictions():
    with pytest.raises(ValueError, match="No published"):
        processing_coverage([box(10, 10, 11, 11)], [0, 0, 1, 1])
    assert processing_coverage([box(0, 0, 1, 1), box(1, 0, 2, 1)], [0, 0, 2, 1]).equals(
        box(0, 0, 2, 1)
    )


def test_worldcover_tile_hemispheres_and_boundaries():
    assert [key for key, _ in worldcover_tiles(box(-46, -13, -45.5, -12.5))] == [
        "S15W048"
    ]
    assert [key for key, _ in worldcover_tiles(box(3, 0, 6, 3))] == ["N00E003"]
    assert len(worldcover_tiles(box(2.99, -0.01, 3.01, 0.01))) == 4


def test_native_crop_chip_water_nodata_unknown_and_full_denominator():
    data = np.array([[40, 40, 80, 0], [40, 10, 255, 80]], dtype="uint8")
    profile = {
        "driver": "GTiff",
        "height": 2,
        "width": 4,
        "count": 1,
        "dtype": "uint8",
        "crs": 4326,
        "transform": from_origin(3, 1, 0.001, 0.001),
        "nodata": 0,
    }
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(data, 1)
        with mem.open() as src:
            observation = crop_observation(src, box(*src.bounds))
    weights = observation["row_area_m2"]
    assert observation["crop_area_m2"] == pytest.approx(2 * weights[0] + weights[1])
    assert observation["valid_area_m2"] == pytest.approx(
        3 * weights[0] + 3 * weights[1]
    )
    assert observation["sampled_area_m2"] == pytest.approx(4 * weights.sum())
    assert observation["data"].tolist() == data.tolist()
    assert not observation["valid"][0, 3]
    assert not observation["valid"][1, 2]


def test_window_densification_round_trip():
    square = box(700000, 8700000, 710000, 8710000)
    geographic = geographic_window(square, 32723)
    transformer = Transformer.from_crs(4326, 32723, always_xy=True)
    projected_corners = [
        transformer.transform(*xy) for xy in geographic.exterior.coords
    ]
    assert min(x for x, y in projected_corners) == pytest.approx(700000, abs=1e-7)
    assert max(y for x, y in projected_corners) == pytest.approx(8710000, abs=1e-7)


def fake_response(url, data):
    response = io.BytesIO(data)
    response.url = url
    response.headers = {"ETag": "test", "Content-Length": str(len(data))}
    return response


def test_source_snapshots_verify_expected_and_cached_bytes(tmp_path, monkeypatch):
    payload = b"frozen-source"
    monkeypatch.setattr(
        runner.urllib.request,
        "urlopen",
        lambda request, **kw: fake_response(request.full_url, payload),
    )
    sources = runner.Sources(tmp_path)
    digest = hashlib.sha256(payload).hexdigest()
    path, _ = sources.fetch("https://example.test/input", "input.bin", "1220" + digest)
    assert path.read_bytes() == payload
    monkeypatch.setattr(
        runner.urllib.request,
        "urlopen",
        lambda *args, **kw: pytest.fail("Unexpected network access"),
    )
    assert sources.fetch("https://example.test/input", "input.bin", digest)[0] == path
    with pytest.raises(ValueError, match="checksum mismatch"):
        sources.fetch("https://example.test/input", "input.bin", "0" * 64)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="cache changed"):
        sources.fetch("https://example.test/input", "input.bin")


def test_selection_run_outputs_resume_and_integrity(tmp_path, monkeypatch):
    geometry = box(3, 0, 3.8, 0.8)
    stream = io.BytesIO()
    pq.write_table(pa.table({"geometry": [geometry.wkb]}), stream)
    inventory = stream.getvalue()
    country = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"ADM0_A3": "SYN"},
                    "geometry": geometry.__geo_interface__,
                }
            ],
        }
    ).encode()
    config = {
        "study_id": "synthetic-pilot",
        "year": 2024,
        "seed": "1",
        "grid_size_m": 10000,
        "min_spacing_m": 10000,
        "windows_per_zone": 3,
        "reserves_per_zone": 2,
        "min_crop_fraction": 0.1,
        "min_valid_fraction": 0.99,
        "worldcover_version": "v200/2021",
        "inventory_url": "https://example.test/raster/2024/items.parquet",
        "inventory_sha256": hashlib.sha256(inventory).hexdigest(),
        "vector_collection_url": "https://example.test/vector/2024/collection.json",
        "country_url": "https://example.test/countries.geojson",
        "country_sha256": hashlib.sha256(country).hexdigest(),
        "zones": [
            {
                "zone_id": "synthetic",
                "bounds": [3, 0, 3.8, 0.8],
                "metric_crs": "EPSG:32631",
                "country": "SYN",
            }
        ],
    }
    payloads = {
        config["inventory_url"]: inventory,
        config["country_url"]: country,
        config["vector_collection_url"]: b'{"links": []}',
        "https://example.test/raster/2024/collection.json": json.dumps(
            {
                "assets": {
                    "mirror": {"file:checksum": "1220" + config["inventory_sha256"]}
                }
            }
        ).encode(),
    }
    monkeypatch.setattr(
        runner.urllib.request,
        "urlopen",
        lambda request, **kw: fake_response(
            request.full_url, payloads[request.full_url]
        ),
    )

    class Screen:
        def __init__(self, *args):
            pass

        def __call__(self, row):
            return {"eligible": True, "crop_fraction": 0.5, "valid_fraction": 1.0}

        def verify(self):
            pass

    monkeypatch.setattr(runner, "CropScreen", Screen)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    out = tmp_path / "selection"
    runner.run(path, out)
    selected = json.loads((out / "selected-windows.geojson").read_text())["features"]
    assert len(selected) == 3
    assert (
        len(json.loads((out / "reserve-windows.geojson").read_text())["features"]) == 2
    )
    assert all(f["properties"]["role"] == "primary" for f in selected)
    assert (out / "complete.json").exists()
    assert (out / "source-code/select_descriptor_pilot.py").exists()
    monkeypatch.setattr(
        runner.urllib.request,
        "urlopen",
        lambda *args, **kw: pytest.fail("Unexpected network access"),
    )
    runner.run(path, out)
    (out / "selected-windows.csv").write_text("changed")
    with pytest.raises(ValueError, match="artifact changed"):
        runner.run(path, out)
    config["seed"] = "2"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="inputs/code/environment changed"):
        runner.run(path, out)
