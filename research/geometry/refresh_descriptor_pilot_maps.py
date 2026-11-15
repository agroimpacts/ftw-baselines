"""Refresh only pilot HTML/colors; verify and preserve all measurement artifacts."""

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from ftw_geometry.io.manifests import file_digest, write_json

from research.geometry import describe_descriptor_pilot as renderer
from research.geometry.select_descriptor_pilot import now


def refresh(root):
    root = Path(root).expanduser().resolve()
    manifest = json.loads((root / "complete.json").read_text())
    for name, digest in manifest["output_sha256"].items():
        if file_digest(root / name) != digest:
            raise ValueError(f"Changed artifact: {name}")
    backup = root.parent / ("map-history-" + now().replace(":", "-").replace("+", "_"))
    backup.mkdir()
    (backup / "complete.json").write_bytes((root / "complete.json").read_bytes())
    unchanged = {
        name: digest
        for name, digest in manifest["output_sha256"].items()
        if not name.endswith("/review.html")
        and name not in {"map-renderer-source.py", "common-color-scales.json"}
    }
    primary = pd.read_parquet(root / "primary-descriptors.parquet")
    scales = renderer.common_scales(primary)
    write_json(
        root / "common-color-scales.json",
        {
            "population": "primary only; diagnostic excluded",
            "primary_rows": len(primary),
            "scales": scales,
        },
    )
    review = Path(manifest["review_dir"])
    count = 0
    for path in sorted(root.glob("*/descriptors.parquet")):
        window = json.loads(
            (review / path.parent.name / "provenance.json").read_text()
        )["window"]
        html = path.parent / "review.html"
        (backup / (path.parent.name + ".html")).write_bytes(html.read_bytes())
        html.write_text(renderer.descriptor_map(window, gpd.read_parquet(path), scales))
        count += 1
    for name, digest in unchanged.items():
        if file_digest(root / name) != digest:
            raise ValueError(f"Measurement/audit unexpectedly changed: {name}")
    (root / "map-renderer-source.py").write_bytes(Path(renderer.__file__).read_bytes())
    manifest["common_scale_refresh"] = {
        "at": now(),
        "backup": str(backup),
        "maps": count,
        "measurements_changed": False,
    }
    manifest["output_sha256"] = {
        str(p.relative_to(root)): file_digest(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "complete.json"
    }
    write_json(root / "complete.json", manifest)
    print(
        f"Refreshed {count} maps; common scale default, local toggle retained. Measurements unchanged."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("descriptor_dir")
    refresh(parser.parse_args().descriptor_dir)
