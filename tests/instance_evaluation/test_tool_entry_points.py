"""Moved workflow entry points must work as documented from the repo root."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "tool",
    [
        "audit_instance_chip",
        "compare_instance_methods",
        "compare_instance_runs",
        "visualize_instance_methods",
        "visualize_instances",
    ],
)
def test_module_help(tool):
    result = subprocess.run(
        [sys.executable, "-m", f"scripts.instance_evaluation.{tool}", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
