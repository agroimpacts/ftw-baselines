from ftw_tools.settings import FULL_DATA_COUNTRIES
from ftw_tools.training.eval import expand_countries
from ftw_tools.training.eval import compute_metrics_from_aggregated_data
from ftw_tools.training.metrics import instance_statistics
import numpy as np
import pytest
import torch


def test_expand_countries_with_full_data():
    """Test that expand_countries() correctly expands 'full_data' to all FULL_DATA_COUNTRIES."""

    # Test basic expansion
    result = expand_countries(["full_data"])

    # Verify that result is now the full list
    assert isinstance(result, list)
    assert len(result) == len(FULL_DATA_COUNTRIES)
    assert set(result) == set(FULL_DATA_COUNTRIES)

    # Verify specific expected countries are included
    expected_countries = ["austria", "belgium", "france", "germany", "netherlands"]
    for country in expected_countries:
        assert country in result, f"Expected country '{country}' not in expanded list"

    # Verify no unexpected values remain
    assert "full_data" not in result, "'full_data' should be replaced, not kept in list"


def test_expand_countries_without_full_data():
    """Test that expand_countries() preserves specific country names when 'full_data' is absent."""
    # Test with specific countries (no full_data)
    input_countries = ["rwanda", "kenya", "belgium"]
    result = expand_countries(input_countries)

    # Should return the same list
    assert result == input_countries
    assert len(result) == 3
    assert "rwanda" in result
    assert "kenya" in result
    assert "belgium" in result


def test_expand_countries_mixed_with_full_data():
    """Test that 'full_data' replaces the entire list when mixed with specific countries."""
    # Test when full_data is mixed with other countries
    result = expand_countries(["rwanda", "full_data", "kenya"])

    # When full_data is present, it should replace the entire list
    assert set(result) == set(FULL_DATA_COUNTRIES)
    assert len(result) == len(FULL_DATA_COUNTRIES)


def test_expand_countries_does_not_modify_original():
    """Test that expand_countries() does not modify the original input list."""
    # Test immutability
    original = ["rwanda", "kenya"]
    original_copy = original.copy()
    result = expand_countries(original)

    # Original should be unchanged
    assert original == original_copy
    assert result == original
    assert result is not original  # Should be a different object


def test_offline_aggregation_uses_same_instance_statistics():
    truth = np.array([[1, 1, 0], [0, 1, 0]], dtype=np.uint8)
    pred = np.array([[1, 0, 0], [0, 1, 1]], dtype=np.uint8)
    chip = instance_statistics(truth, pred)
    scores = compute_metrics_from_aggregated_data(
        torch.tensor(pred),
        torch.tensor(truth),
        [int(chip.tp)],
        [int(chip.fp)],
        [int(chip.fn)],
        instance_stats=[chip],
    )
    for name, value in chip.scores().items():
        assert scores[name] == pytest.approx(value, nan_ok=True)
