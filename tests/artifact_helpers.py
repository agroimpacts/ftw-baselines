"""Small aligned raster inputs shared by artifact and research tests."""

import numpy as np
import rasterio
from rasterio.transform import from_origin


def chip_record(root, chip_id, country="germany"):
    country = root / country
    reference = country / "label_masks" / "semantic_3class"
    reference.mkdir(parents=True, exist_ok=True)
    mask = reference / f"{chip_id}.tif"
    profile = {
        "driver": "GTiff",
        "height": 2,
        "width": 2,
        "count": 1,
        "dtype": "uint8",
        "crs": "EPSG:32632",
        "transform": from_origin(500000, 5800000, 10, 10),
    }
    with rasterio.open(mask, "w", **profile) as dst:
        dst.write(np.array([[1, 2], [0, 3]], dtype=np.uint8), 1)
    paths = {}
    for window in ("window_a", "window_b"):
        image = country / "s2_images" / window / f"{chip_id}.tif"
        image.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            image, "w", **{**profile, "count": 3, "dtype": "uint16"}
        ) as dst:
            dst.write(np.full((3, 2, 2), 1500, dtype=np.uint16))
        paths[window] = str(image)
    return {"mask": str(mask), **paths}
