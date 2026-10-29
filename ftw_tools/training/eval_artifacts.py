"""Opt-in chip artifacts for offline semantic model testing."""

import hashlib
import json
import math
import subprocess
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from ftw_tools.inference.model_registry import MODEL_REGISTRY
from ftw_tools.settings import has_labeled_background
from ftw_tools.training.metrics import InstanceStatistics, instance_scores_for_reporting
from ftw_tools.training.pixel_evaluation import pixel_confusions, pixel_scores


def _json_scores(scores):
    """Use JSON null for undefined scores rather than nonstandard NaN."""
    return {
        key: None if not math.isfinite(value) else value
        for key, value in scores.items()
    }


def _checkpoint_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class EvaluationArtifacts:
    """Write each prediction once; pool per-chip statistics at completion."""

    def __init__(self, directory, *, checkpoint, dataset, settings):
        self.directory = Path(directory).expanduser().resolve()
        if self.directory.exists() and any(self.directory.iterdir()):
            raise FileExistsError(f"Output directory is not empty: {self.directory}")
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "predictions").mkdir()
        if settings.get("save_probabilities"):
            (self.directory / "probabilities").mkdir()
        self.rows = []
        self.pooled = InstanceStatistics()
        self.pixel_counts = {}
        self.seen = set()
        registered = MODEL_REGISTRY.get(Path(checkpoint).stem)
        self.manifest = {
            "checkpoint": str(Path(checkpoint).expanduser().resolve()),
            "checkpoint_sha256": _checkpoint_hash(checkpoint),
            "release_url": registered.url if registered else None,
            "dataset": str(Path(dataset).expanduser().resolve()),
            "settings": settings,
            "prediction_raster": "raw model argmax classes",
            "probability_raster": (
                "float32 softmax channels 0=background, 1=field, 2=boundary; "
                "nearest-neighbour resized from model grid when "
                "resize_factor != 1"
                if settings.get("save_probabilities")
                else None
            ),
            "scored_raster": (
                "class 2 remapped to 0"
                if settings["remap_boundary"]
                else "raw model argmax classes"
            ),
            "code_revision": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            or None,
        }

    def add(self, file_record, raw, scored, truth, stats, probabilities=None):
        """Persist raw prediction on the ground-truth grid and score it."""
        reference = Path(file_record["mask"])
        country = reference.parents[2].name
        chip_id = reference.stem
        key = (country, chip_id)
        if key in self.seen:
            raise ValueError(f"Duplicate chip: {country}/{chip_id}")
        self.seen.add(key)
        if raw.shape != scored.shape or raw.shape != truth.shape:
            raise ValueError(f"Prediction/reference shape mismatch: {reference}")
        with rasterio.open(reference) as source:
            if source.count != 1 or source.shape != raw.shape:
                raise ValueError(f"Prediction/reference grid mismatch: {reference}")
            profile = source.profile.copy()
        if not np.isin(raw, [0, 1, 2]).all():
            raise ValueError("Expected raw semantic classes 0, 1 or 2")
        saving_probabilities = self.manifest["settings"].get(
            "save_probabilities", False
        )
        if saving_probabilities != (probabilities is not None):
            raise ValueError("Probability data must match save_probabilities setting")
        if probabilities is not None:
            if (
                probabilities.shape != (3, *raw.shape)
                or not np.isfinite(probabilities).all()
            ):
                raise ValueError("Expected finite, aligned three-channel probabilities")
            if not np.array_equal(probabilities.argmax(axis=0), raw):
                raise ValueError("Probability argmax differs from saved raw classes")
        relative = Path("predictions") / country / f"{chip_id}.tif"
        path = self.directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        profile.update(count=1, dtype="uint8", nodata=None)
        with rasterio.open(path, "w", **profile) as target:
            target.write(raw.astype(np.uint8), 1)
        probability_relative = None
        if probabilities is not None:
            probability_relative = Path("probabilities") / country / f"{chip_id}.tif"
            probability_path = self.directory / probability_relative
            probability_path.parent.mkdir(parents=True, exist_ok=True)
            probability_profile = {**profile, "count": 3, "dtype": "float32"}
            with rasterio.open(probability_path, "w", **probability_profile) as target:
                target.write(probabilities.astype(np.float32))
        self.pooled += stats
        valid = np.isin(truth, (0, 1, 2))
        ignore_index = self.manifest["settings"].get("ignore_index")
        if ignore_index is not None:
            valid &= truth != ignore_index
        matrices = pixel_confusions(
            truth,
            raw,
            three_class=(
                self.manifest["settings"].get("test_on_3_classes", False)
                and self.manifest["settings"].get("model_predicts_3_classes", False)
            ),
            ignore_index=ignore_index,
        )
        chip_pixels = {}
        for mode, matrix in matrices.items():
            if mode not in self.pixel_counts:
                self.pixel_counts[mode] = np.zeros_like(matrix)
            self.pixel_counts[mode] += matrix
            chip_pixels.update(
                {
                    f"pixel_{mode}_{name}": value
                    for name, value in pixel_scores(matrix).items()
                }
            )
            chip_pixels.update(
                {
                    f"pixel_{mode}_count_{reference}_{prediction}": int(count)
                    for (reference, prediction), count in np.ndenumerate(matrix)
                }
            )
        self.rows.append(
            {
                "country": country,
                "aoi_id": chip_id,
                "window_a": file_record["window_a"],
                "window_b": file_record["window_b"],
                "reference": str(reference),
                "prediction": str(relative),
                "probabilities": str(probability_relative)
                if probability_relative
                else None,
                "valid_pixels": int(valid.sum()),
                "ignored_pixels": int((~valid).sum()),
                "scored_boundary_pixels": int((scored == 2).sum()),
                "raw_boundary_pixels": int((raw == 2).sum()),
                **{f"stat_{key}": value for key, value in asdict(stats).items()},
                **instance_scores_for_reporting(
                    stats, background_known=has_labeled_background(country)
                ),
                **chip_pixels,
            }
        )

    def finish(self, existing_pixel_scores):
        """Save chip table and summary only after successful inference."""
        pd.DataFrame(self.rows).to_parquet(
            self.directory / "chips.parquet", index=False
        )
        summary = {
            "chip_count": len(self.rows),
            "pixel_scores": _json_scores(existing_pixel_scores),
            "instance_scores": _json_scores(
                instance_scores_for_reporting(
                    self.pooled,
                    background_known=all(
                        has_labeled_background(row["country"]) for row in self.rows
                    ),
                )
            ),
            "instance_statistics": asdict(self.pooled),
            "pixel_comparisons": {
                mode: {
                    "confusion": counts.tolist(),
                    "scores": _json_scores(pixel_scores(counts)),
                }
                for mode, counts in self.pixel_counts.items()
            },
        }
        self.manifest["evaluated_chips"] = len(self.rows)
        for filename, payload in (
            ("summary.json", summary),
            ("manifest.json", self.manifest),
        ):
            with open(self.directory / filename, "w") as output:
                json.dump(payload, output, indent=2, allow_nan=False)
                output.write("\n")
