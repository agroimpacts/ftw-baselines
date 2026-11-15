import re
import shutil
import subprocess

import geopandas as gpd
import pandas as pd
import pytest
from ftw_geometry.core.descriptors import describe_polygons
from shapely.geometry import MultiPolygon, box

from research.geometry.describe_descriptor_pilot import (
    common_scales,
    component_count,
    descriptor_map,
    single_polygon,
)


def test_single_component_container_keeps_geometry_and_identity():
    polygon = box(0, 0, 10, 10)
    container = MultiPolygon([polygon])
    assert component_count(container) == 1
    assert single_polygon(container).wkb == polygon.wkb
    assert component_count(MultiPolygon([polygon, box(20, 0, 30, 10)])) == 2
    with pytest.raises(ValueError, match="explicit policy"):
        single_polygon(MultiPolygon([polygon, box(20, 0, 30, 10)]))


def test_empty_descriptor_map_is_not_zero_descriptor_observations():
    fields = gpd.GeoDataFrame(
        {"id": pd.Series(dtype="str"), "score": []}, geometry=[], crs=4326
    )
    descriptors = describe_polygons(fields, metric_crs=32631)
    result = fields.merge(descriptors, on="id", how="left")
    window = {
        "type": "Feature",
        "properties": {"window_id": "empty", "role": "primary"},
        "geometry": box(3, 0, 4, 1).__geo_interface__,
    }
    html = descriptor_map(window, result)
    assert '"features": []' in html
    assert "No mapped fields / no descriptor observations" in html
    assert len(descriptors) == 0


def test_map_boolean_and_rare_numeric_colors_execute_in_javascript():
    command = (
        ["node", "-"]
        if shutil.which("node")
        else ["osascript", "-l", "JavaScript", "-"]
    )
    if not shutil.which(command[0]):
        pytest.skip("JavaScript runtime required for map regression test")
    frame = gpd.GeoDataFrame(
        {"id": [str(i) for i in range(100)]},
        geometry=[box(3, 0, 3.01, 0.01)] * 100,
        crs=4326,
    )
    for column in [
        "area_m2",
        "perimeter_m",
        "circularity",
        "elongation",
        "solidity",
        "rectangularity",
        "convex_hull_index",
        "hole_count",
        "hole_area_fraction",
    ]:
        frame[column] = [0] * 99 + [1]
    frame["narrow_neck"] = [False] * 99 + [True]
    window = {
        "type": "Feature",
        "properties": {"window_id": "rare", "role": "primary"},
        "geometry": box(3, 0, 4, 1).__geo_interface__,
    }
    script = re.findall(
        r"<script>(.*?)</script>",
        descriptor_map(
            window, frame, {"hole_count": {"lo": 0, "hi": 99, "transform": "log1p"}}
        ),
        re.DOTALL,
    )[0]
    stub = """
const selectStub={value:'area_m2',appendChild:()=>{}};const legendStub={};const scaleStub={value:'local'};let lastStyle;let focusedFeature;let fitCalls=0;
var document={getElementById:k=>k==='feature'?selectStub:k==='scale'?scaleStub:legendStub,createElement:()=>({})};
var L={map:()=>({fitBounds:()=>{fitCalls++},removeLayer:()=>{}}),tileLayer:()=>({addTo:()=>{}}),geoJSON:(d,o)=>{if(o&&o.style&&typeof o.style==='function')lastStyle=o.style;if(o&&o.style&&o.style.color==='#ff00ff')focusedFeature=d;const layer={getBounds:()=>({}),bindPopup:()=>({openPopup:()=>{}}),bringToFront:()=>{}};return {addTo:()=>layer,getBounds:()=>({})}}};
"""
    assertions = """
for(const key of ['narrow_neck','hole_count']){
selectStub.value=key;draw();
if(lastStyle(data.features[0]).fillColor!=='hsl(240,85%,55%)')throw Error(key+' false/zero not blue');
if(lastStyle(data.features[99]).fillColor!=='hsl(0,85%,55%)')throw Error(key+' true/outlier not red');
}
if(!legendStub.textContent.includes('full-range fallback'))throw Error('missing fallback legend');
scaleStub.value='common';draw();
if(lastStyle(data.features[99]).fillColor==='hsl(0,85%,55%)')throw Error('common scale ignored');
if(!legendStub.textContent.includes('common log1p'))throw Error('common transform not labeled');
var location={hash:'#field=99&feature=circularity'};applyHash();
if(selectStub.value!=='circularity'||focusedFeature.properties.id!=='99'||fitCalls<2)throw Error('focus navigation failed');
if(focusField('not-present')!==false)throw Error('missing field not handled');
"""
    result = subprocess.run(
        command,
        check=False,
        input=stub + script + assertions,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_shared_scale_bounds_and_transforms():
    primary = pd.DataFrame(
        {key: [1.0, 100.0] for key in ["area_m2", "perimeter_m", "elongation"]}
    )
    for key in [
        "circularity",
        "solidity",
        "rectangularity",
        "convex_hull_index",
        "hole_area_fraction",
    ]:
        primary[key] = [0.2, 0.8]
    primary["hole_count"] = [0, 7]
    scales = common_scales(primary)
    assert scales["area_m2"] == {"lo": 1.0, "hi": 100.0, "transform": "log"}
    assert scales["circularity"] == {"lo": 0.0, "hi": 1.0, "transform": "linear"}
    assert scales["hole_count"] == {"lo": 0.0, "hi": 7.0, "transform": "log1p"}
