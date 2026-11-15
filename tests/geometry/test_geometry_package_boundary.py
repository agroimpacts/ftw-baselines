import subprocess
import sys


def test_geometry_package_does_not_import_ftw_or_research():
    script = """
import importlib.abc, sys
class BlockFTW(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'ftw_tools', 'research', 'torch', 'lightning', 'fbp'}:
            raise ImportError('Forbidden geometry dependency: '+fullname)
sys.meta_path.insert(0, BlockFTW())
from ftw_geometry.core import descriptors, dataset, analysis
from ftw_geometry.io import sources, vectors, manifests
from shapely.geometry import box
assert descriptors.polygon_descriptors(box(0,0,10,10))['area_m2'] == 100
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_old_imports_forward_to_same_implementation():
    from ftw_geometry.core import analysis, dataset
    from ftw_geometry.core import descriptors as core

    from ftw_tools.postprocess import (
        descriptor_analysis,
        descriptor_dataset,
        descriptors,
    )

    assert descriptors.describe_polygons is core.describe_polygons
    assert descriptor_dataset.build_dataset is dataset.build_dataset
    assert descriptor_analysis.correlate_tables is analysis.correlate_tables
