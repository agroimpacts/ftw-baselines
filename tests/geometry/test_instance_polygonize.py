import math

import numpy as np
import pytest
from affine import Affine
from rasterio.features import rasterize
from shapely.geometry import box

from ftw_tools.postprocess.descriptors import describe_polygons, polygon_descriptors
from ftw_tools.postprocess.instance_polygonize import labels_to_polygons


def test_windows_preserve_ids_holes_and_pixels():
    labels = np.ones((8, 8), dtype="int32")
    labels[:, 4:] = 2
    labels[2:4, 1:3] = 0
    affine = Affine.translation(100, 200) * Affine.scale(10, -10)
    frame = labels_to_polygons(labels, affine, "EPSG:32632", stride=3)
    assert len(frame) == 2
    assert frame.geometry.is_valid.all()
    assert len(frame.geometry.iloc[0].interiors) == 1
    assert frame.area.sum() == (labels > 0).sum() * 100
    reconstructed = rasterize(
        zip(frame.geometry, frame.instance_id), out_shape=labels.shape, transform=affine
    )
    np.testing.assert_array_equal(reconstructed, labels)


def test_multipart_and_empty():
    labels = np.array([[9, 0, 9]], dtype="int32")
    frame = labels_to_polygons(labels, Affine.identity(), "EPSG:32632", 1)
    assert frame.id.tolist() == ["9:1", "9:2"]
    assert labels_to_polygons(labels * 0, Affine.identity(), "EPSG:32632").empty


@pytest.mark.parametrize(
    "affine",
    [
        Affine(
            5.4053999999997826e-05,
            0,
            13.925049138,
            0,
            5.405400000002558e-05,
            52.80816340799999,
        ),
        Affine(9.7, 0.15, 500000.123, 0.21, -9.7, 5000000.321),
    ],
)
def test_fractional_affine_window_seams(affine):
    labels = np.ones((64, 64), dtype="int32")
    labels[:, 35:] = 2
    labels[12:26, 7:24] = 0
    reference = labels_to_polygons(labels, affine, "EPSG:4326").set_index("id")
    for stride in (3, 17, 31):
        tiled = labels_to_polygons(labels, affine, "EPSG:4326", stride).set_index("id")
        assert tiled.index.tolist() == reference.index.tolist()
        assert all(
            tiled.loc[key].geometry.equals(row.geometry)
            for key, row in reference.iterrows()
        )
        np.testing.assert_array_equal(
            rasterize(
                zip(tiled.geometry, tiled.instance_id),
                out_shape=labels.shape,
                transform=affine,
            ),
            labels,
        )


@pytest.mark.parametrize(
    "labels",
    [
        np.array([1]),
        np.array([[1.5]]),
        np.array([[-1]]),
        np.array([[2**31]], dtype="uint32"),
    ],
)
def test_invalid_label_inputs(labels):
    with pytest.raises(ValueError):
        labels_to_polygons(labels, Affine.identity(), "EPSG:32632")


def test_rectangle_descriptors():
    values = polygon_descriptors(box(0, 0, 4, 2))
    assert {
        key: values[key]
        for key in ("area_m2", "perimeter_m", "circularity", "elongation", "solidity")
    } == pytest.approx(
        {
            "area_m2": 8,
            "perimeter_m": 12,
            "circularity": 2 * math.pi / 9,
            "elongation": 2,
            "solidity": 1,
        }
    )


@pytest.mark.parametrize("suffix", [".parquet", ".geojson", ".gpkg", ".fgb"])
@pytest.mark.parametrize("empty", [False, True])
def test_fbp_export_sidecar(tmp_path, suffix, empty):
    pytest.importorskip("fbp")
    import pandas as pd
    import rasterio

    from ftw_tools.postprocess.instance_polygonize import polygonize_fbp

    probabilities = np.zeros((3, 64, 64), dtype="float32")
    probabilities[0] = 1
    if not empty:
        probabilities[0, 10:50, 10:50] = 0
        probabilities[1, 10:50, 10:50] = 1
    source = tmp_path / "probabilities.tif"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        count=3,
        width=64,
        height=64,
        dtype="float32",
        crs="EPSG:32632",
        transform=Affine.translation(500000, 5000000) * Affine.scale(10, -10),
    ) as dst:
        dst.write(probabilities)
    target = tmp_path / ("fields" + suffix)
    frame = polygonize_fbp(source, target, stride=17)
    assert frame.empty == empty
    descriptors = pd.read_csv(str(target) + ".descriptors.csv")
    assert set(descriptors.id) == set(frame.id)
    import geopandas as gpd

    written = (
        gpd.read_parquet(target) if suffix == ".parquet" else gpd.read_file(target)
    )
    if empty and suffix == ".geojson":
        assert written.empty
        written = frame.iloc[:0].copy()
    expected = (
        describe_polygons(written, metric_crs=frame.crs).set_index("id").sort_index()
    )
    actual = descriptors.set_index("id").sort_index()
    np.testing.assert_allclose(
        actual.to_numpy(dtype=float), expected.to_numpy(dtype=float)
    )
    assert {"id", "metrics:area", "metrics:perimeter"}.issubset(written.columns)
    assert written.geometry.is_valid.all()
    with pytest.raises(FileExistsError):
        polygonize_fbp(source, target)
    polygonize_fbp(source, target, overwrite=True)
    rewritten = (
        gpd.read_parquet(target) if suffix == ".parquet" else gpd.read_file(target)
    )
    assert len(rewritten) == len(frame)


def test_descriptor_crs_and_invalid_inputs():
    import geopandas as gpd
    from shapely.geometry import Polygon

    frame = gpd.GeoDataFrame(
        {"id": ["field"]}, geometry=[box(500000, 5000000, 500020, 5000010)], crs=32632
    )
    result = describe_polygons(frame)
    assert result.area_m2.iloc[0] == 200
    geographic = frame.to_crs(4326)
    assert describe_polygons(geographic).area_m2.iloc[0] == pytest.approx(200, rel=1e-8)
    with pytest.raises(ValueError, match="metres"):
        describe_polygons(frame, metric_crs=4326)
    for invalid in (None, Polygon(), Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])):
        with pytest.raises(ValueError):
            polygon_descriptors(invalid)
    frame.id = None
    with pytest.raises(ValueError, match="unique"):
        describe_polygons(frame)


def test_hole_and_concavity_descriptors():
    from shapely.geometry import Polygon

    polygon = Polygon(
        box(0, 0, 10, 10).exterior.coords, [box(2, 2, 4, 4).exterior.coords]
    )
    values = polygon_descriptors(polygon)
    assert values["area_m2"] == 96
    assert values["perimeter_m"] == 48
    assert values["solidity"] == 0.96
    assert values["circularity"] == pytest.approx(4 * math.pi * 96 / 48**2)


@pytest.mark.parametrize("encoding", ["float32", "uint8"])
def test_geographic_cleanup_and_input_encoding(tmp_path, monkeypatch, encoding):
    fbp = pytest.importorskip("fbp")
    import geopandas as gpd
    import rasterio

    from ftw_tools.postprocess.instance_polygonize import pixel_area_m2, polygonize_fbp

    affine = Affine(0.0001, 0, 13.9, 0, -0.0001, 52.8)
    labels = np.zeros((16, 16), dtype="int32")
    labels[2:14, 2:14] = 7
    labels[5:7, 5:7] = 0
    probabilities = np.zeros((3, 16, 16), dtype=encoding)
    probabilities[0] = 255 if encoding == "uint8" else 1
    source = tmp_path / "geographic.tif"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=16,
        height=16,
        count=3,
        dtype=encoding,
        crs=4326,
        transform=affine,
    ) as dst:
        dst.write(probabilities)
    calls = []

    def preset(semantic, probability, *, pixel_area_m2):
        calls.append(pixel_area_m2)
        assert probability.dtype == np.float32
        assert probability.max() == 1
        return labels

    # Preserve the real typed preset for metadata while replacing only its call.
    monkeypatch.setattr(
        type(fbp.FTW_2E),
        "__call__",
        lambda self, *args, **kwargs: preset(*args, **kwargs),
    )
    target = tmp_path / "cleaned.gpkg"
    frame = polygonize_fbp(
        source, target, simplify=0.1, close_interiors=True, min_size=100
    )
    assert frame.crs.to_epsg() == 4326
    assert frame.id.tolist() == ["7:1"]
    assert len(frame.geometry.iloc[0].interiors) == 0
    written = gpd.read_file(target)
    assert describe_polygons(written).area_m2.iloc[0] > 100
    with rasterio.open(source) as src:
        assert calls == [pixel_area_m2(src)]


@pytest.mark.parametrize("problem", ["nan", "range", "sum", "bands", "nodata"])
def test_probability_validation(tmp_path, problem):
    pytest.importorskip("fbp")
    import rasterio

    from ftw_tools.postprocess.instance_polygonize import polygonize_fbp

    probabilities = np.zeros((3, 8, 8), dtype="float32")
    probabilities[0] = 1
    if problem == "nan":
        probabilities[0, 0, 0] = np.nan
    elif problem == "range":
        probabilities[0, 0, 0] = 2
    elif problem == "sum":
        probabilities[1] = 1
    elif problem == "bands":
        probabilities = probabilities[:1]
    source = tmp_path / "invalid.tif"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=len(probabilities),
        dtype="float32",
        crs=32632,
        transform=Affine.scale(10, -10),
    ) as dst:
        dst.write(probabilities)
        if problem == "nodata":
            mask = np.full((8, 8), 255, dtype="uint8")
            mask[0, 0] = 0
            dst.write_mask(mask)
    target = tmp_path / "invalid.geojson"
    with pytest.raises(ValueError):
        polygonize_fbp(source, target)
    assert not target.exists()


def test_cli_default_dispatch_and_fbp_options(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from ftw_tools.cli import ftw
    from ftw_tools.postprocess import instance_polygonize, polygonize

    source = tmp_path / "input.tif"
    source.touch()
    calls = []
    monkeypatch.setattr(polygonize, "polygonize", lambda *args: calls.append(args))
    runner = CliRunner()
    base = ["inference", "polygonize", str(source)]
    result = runner.invoke(ftw, base)
    assert result.exit_code == 0, result.output
    assert calls == [
        (
            str(source),
            None,
            15,
            500,
            None,
            False,
            False,
            2048,
            None,
            None,
            0,
            0,
            0,
            0,
            False,
        )
    ]
    fbp_calls = []
    monkeypatch.setattr(
        instance_polygonize,
        "polygonize_fbp",
        lambda *args, **kwargs: fbp_calls.append(kwargs),
    )
    result = runner.invoke(
        ftw, [*base, "--method", "ftw-2e", "--simplify", "0", "--min_size", "0"]
    )
    assert result.exit_code == 0, result.output
    assert fbp_calls[0]["simplify"] == 0
    for option in (
        ["--merge_adjacent", "0"],
        ["--softmax_threshold", "0"],
        ["--thin_boundaries"],
    ):
        result = runner.invoke(ftw, [*base, "--method", "ftw-2e", *option])
        assert result.exit_code == 2
    assert len(calls) == len(fbp_calls) == 1


def test_legacy_semantic_output(tmp_path):
    import geopandas as gpd
    import rasterio
    from click.testing import CliRunner

    from ftw_tools.cli import ftw

    mask = np.zeros((12, 12), dtype="uint8")
    mask[1:5, 1:5] = 1
    mask[7:10, 7:10] = 1
    source, target = tmp_path / "semantic.tif", tmp_path / "legacy.geojson"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        count=1,
        width=12,
        height=12,
        dtype="uint8",
        crs="EPSG:32632",
        transform=Affine.translation(500000, 5000000) * Affine.scale(10, -10),
    ) as dst:
        dst.write(mask, 1)
    result = CliRunner().invoke(
        ftw,
        [
            "inference",
            "polygonize",
            str(source),
            "--out",
            str(target),
            "--simplify",
            "0",
            "--min_size",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    frame = gpd.read_file(target)
    assert len(frame) == 2
    np.testing.assert_allclose(sorted(frame["metrics:area"]), [900, 1600])
    assert not (tmp_path / "legacy.geojson.descriptors.csv").exists()
