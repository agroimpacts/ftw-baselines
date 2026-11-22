"""Spatial units and analysis population/ranking controls."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from affine import Affine

from research.instance_metrics.analyze_chamfer import ALL, NEW, analyze, pixel_spacing
from research.instance_metrics.analyze_metric_complementarity import disagreements


def test_projected_spacing_and_rotation_guard():
    ds = SimpleNamespace(
        transform=Affine(10, 0, 0, 0, -20, 0), crs="EPSG:32632", width=256, height=256
    )
    assert pixel_spacing(ds) == (20, 10)
    ds.transform = Affine(10, 1, 0, 0, -10, 0)
    with pytest.raises(ValueError):
        pixel_spacing(ds)


def test_geographic_spacing():
    ds = SimpleNamespace(
        transform=Affine(0.0001, 0, 10, 0, -0.0001, 50),
        crs="EPSG:4326",
        width=256,
        height=256,
    )
    row, col = pixel_spacing(ds)
    assert 10 < row < 12
    assert 6 < col < 8


def test_lower_distance_is_better_for_rank_disagreement():
    frame = pd.DataFrame(
        {
            "country": ["germany"] * 8,
            "aoi_id": list(map(str, range(8))),
            "distance": range(8),
            "quality": list(reversed(range(8))),
        }
    )
    rows, _ = disagreements(
        frame, "all", pairs=(("distance", "quality"),), lower_is_better=("distance",)
    )
    assert rows[0]["top_quartile_disagreement"] == 0


def test_original_and_expanded_pca_use_same_chips(tmp_path):
    rng = np.random.default_rng(3)
    frame = pd.DataFrame({m: rng.random(15) for m in ALL})
    frame["country"] = "germany"
    frame["aoi_id"] = list(map(str, range(15)))
    frame.loc[0, NEW[0]] = np.nan
    out = tmp_path / "analysis"
    analyze(frame, out, fit=False)
    components = pd.read_csv(out / "pca_components.csv")
    assert set(components.n) == {14}
    assert set(components.suite) == {"original8_same_chips", "expanded11"}
    availability = pd.read_csv(out / "availability.csv")
    assert set(availability.complete) == {14}
