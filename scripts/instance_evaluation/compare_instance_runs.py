"""Build a one-row-per-run CSV from offline evaluation artifacts.

Usage: python -m scripts.instance_evaluation.compare_instance_runs RUNS_ROOT --out COMPARISON.csv
"""

import argparse
import csv
import json
from pathlib import Path


def flatten_run(summary_path: Path) -> dict:
    """Flatten named pooled scores without conflating pixel evaluation modes."""
    run_dir = summary_path.parent
    summary = json.loads(summary_path.read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    settings = manifest["settings"]

    row = {
        "run_dir": str(run_dir),
        "countries": ";".join(settings["countries"]),
        "split": settings["split"],
        "checkpoint": manifest["checkpoint"],
        "checkpoint_sha256": manifest["checkpoint_sha256"],
        "chip_count": summary["chip_count"],
        "iou_threshold": settings["iou_threshold"],
        "reference_connectivity": settings["reference_connectivity"],
        "prediction_connectivity": settings["prediction_connectivity"],
    }

    for name, value in summary["instance_scores"].items():
        row[f"instance_{name}"] = value

    for mode, result in summary["pixel_comparisons"].items():
        for name, value in result["scores"].items():
            row[f"{mode}_{name}"] = value

    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs_root", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    root = args.runs_root.expanduser().resolve()
    output = args.out.expanduser().resolve()
    summaries = sorted(root.rglob("summary.json"))
    if not summaries:
        parser.error(f"No summary.json files found under {root}")

    rows = [flatten_run(path) for path in summaries]
    columns = list(dict.fromkeys(key for row in rows for key in row))

    if output.exists():
        parser.error(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} runs to {output}")


if __name__ == "__main__":
    main()
