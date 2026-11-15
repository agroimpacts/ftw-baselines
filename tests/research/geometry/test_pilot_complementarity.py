import numpy as np
import pandas as pd

from research.geometry.analyze_descriptor_pilot import SHAPES, pca


def test_pca_variance_and_orthonormal_weights():
    rng = np.random.default_rng(4)
    frame = pd.DataFrame(rng.uniform(0.1, 1, (40, len(SHAPES))), columns=SHAPES)
    frame["elongation"] += 1
    weights, variance, status = pca(frame)
    assert status["rows"] == 40
    assert status["status"] == "ok"
    assert np.isclose(sum(r["explained_fraction"] for r in variance), 1)
    matrix = (
        pd.DataFrame(weights)
        .pivot(index="component", columns="feature", values="weight")
        .to_numpy()
    )
    assert np.allclose(matrix @ matrix.T, np.eye(len(SHAPES)))


def test_pca_reports_constants_and_insufficient_rows():
    frame = pd.DataFrame({key: np.arange(8, dtype=float) + 1 for key in SHAPES})
    frame["hole_area_fraction"] = 0
    weights, _variance, status = pca(frame)
    assert status["dropped_constants"] == "hole_area_fraction"
    assert "hole_area_fraction" not in [r["feature"] for r in weights]
    assert pca(frame.iloc[:2])[2]["status"] == "insufficient_rows"
