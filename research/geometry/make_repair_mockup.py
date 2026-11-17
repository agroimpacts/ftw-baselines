"""Render a GIF of two accepted split previews; never apply dataset repairs."""

import argparse
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import shapely
from ftw_geometry.io.manifests import file_digest, write_json
from matplotlib.patches import PathPatch
from matplotlib.path import Path as PlotPath
from PIL import Image
from shapely.geometry.polygon import orient


def polygon_patch(ax, geometry, **style):
    geometry = orient(geometry)
    vertices, codes = [], []
    for ring in (geometry.exterior, *geometry.interiors):
        coords = list(ring.coords)
        vertices.extend(coords)
        codes.extend([PlotPath.MOVETO] + [PlotPath.LINETO] * (len(coords) - 2) + [PlotPath.CLOSEPOLY])
    ax.add_patch(PathPatch(PlotPath(vertices, codes), **style))


def run(root, out):
    font_dir = Path("/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts")
    for name in ("Aptos.ttf", "Aptos-Bold.ttf"):
        font_manager.fontManager.addfont(str(font_dir / name))
    plt.rcParams["font.family"] = "Aptos"
    root, out = Path(root).expanduser().resolve(), Path(out).expanduser().resolve()
    if out.exists() or out == root or out in root.parents or (root in out.parents and out.parent != root):
        raise ValueError("Use a fresh separate sibling output directory")
    previews = root / "targeted-repair-review-2024-v1"
    manifest = json.loads((previews / "complete.json").read_text())
    for name, digest in manifest["output_sha256"].items():
        if file_digest(previews / name) != digest:
            raise ValueError(f"Changed preview: {name}")
    review_path = previews / "repair-preview-review-80650f812b46fe179b6cf784.json"
    review = json.loads(review_path.read_text())
    if review["run_id"] != manifest["run_id"]:
        raise ValueError("Review does not match the preview run")
    accepted = {r["proposal_id"] for r in review["reviews"] if r["assessment"] == "prefer"}
    records = json.loads((previews / "proposals.json").read_text())
    selected = [r for r in records if r["proposal_id"] in accepted and r["repair_subtype"] == "split"]
    selected.sort(key=lambda r: r["parent_keys"])
    if len(selected) != 2:
        raise ValueError("Expected exactly the two preferred split previews")
    source = root / "polygon-review-2024/california_61_424/fields.parquet"
    if file_digest(source) != manifest["input_sha256"][str(source)]:
        raise ValueError("Original source hash differs")
    fields = gpd.read_parquet(source)
    fields["key"] = [json.dumps([c, i], separators=(",", ":")) for c, i in zip(fields.collection, fields.id)]
    fields = fields.set_index("key")
    out.mkdir(parents=True)
    panels, imagery_sources = [], []
    for record in selected:
        key = record["parent_keys"][0]
        parent = fields.loc[key].geometry
        children = [shapely.from_wkt(w) for w in record["children_wkt"]]
        cuts = shapely.from_wkt(record["cuts_wkt"])
        display = gpd.GeoSeries([*children, cuts], crs=record["metric_crs"]).to_crs(3857)
        parent_display = gpd.GeoSeries([parent], crs=fields.crs).to_crs(3857).iloc[0]
        xmin, ymin, xmax, ymax = parent_display.bounds
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
        side = max(xmax - xmin, ymax - ymin) * 1.24
        bounds = [cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2]
        params = {"bbox": ",".join(map(str, bounds)), "bboxSR": 3857, "imageSR": 3857,
                  "size": "850,850", "format": "png", "f": "image"}
        url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?" + urllib.parse.urlencode(params)
        ident = fields.loc[key]["id"]
        cache = root / "repair-mockup-2024-v1" / f"{ident}-imagery.png"
        if cache.is_file():
            image = Image.open(cache).convert("RGB")
        else:
            request = urllib.request.Request(url, headers={"User-Agent": "FTW-research-mockup/1.0"})
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
            image = Image.open(io.BytesIO(raw)).convert("RGB")
        image.save(out / f"{ident}-imagery.png")
        imagery_sources.append({"id": ident, "url": url, "bounds_epsg3857": bounds,
                                "imagery_date": "unknown; not necessarily 2024"})
        panels.append((ident, parent_display, list(display.iloc[:-1]), display.iloc[-1], bounds, image))
    palette = ["#34d5eb", "#ffc64b", "#ed70cf"]
    frames = []
    combined = shapely.union_all([panel[1] for panel in panels])
    xmin, ymin, xmax, ymax = combined.bounds
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    height = (ymax - ymin) * 1.35
    width = max((xmax - xmin) * 1.35, height * 1.9)
    landscape_bounds = [cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2]
    params = {"bbox": ",".join(map(str, landscape_bounds)), "bboxSR": 3857, "imageSR": 3857,
              "size": "1500,790", "format": "png", "f": "image"}
    url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?" + urllib.parse.urlencode(params)
    landscape_cache = root / "repair-mockup-2024-v3/california-landscape-imagery.png"
    if landscape_cache.is_file():
        landscape = Image.open(landscape_cache).convert("RGB")
    else:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "FTW-research-mockup/1.0"}), timeout=90) as response:
            landscape = Image.open(io.BytesIO(response.read())).convert("RGB")
    landscape.save(out / "california-landscape-imagery.png")
    imagery_sources.append({"id": "california-landscape", "url": url, "bounds_epsg3857": landscape_bounds,
                            "imagery_date": "unknown; not necessarily 2024"})
    context = fields.to_crs(3857)
    for progress in np.linspace(0, 1, 16):
        fig = plt.figure(figsize=(14, 7.7), dpi=90, facecolor="#101923")
        ax = fig.add_axes([.025, .025, .95, .795])
        ax.imshow(landscape, extent=[landscape_bounds[0], landscape_bounds[2], landscape_bounds[1], landscape_bounds[3]])
        for geometry in context.geometry:
            parts = list(geometry.geoms) if hasattr(geometry, "geoms") else [geometry]
            for part in parts:
                xy = np.array(part.exterior.coords)
                ax.plot(xy[:, 0], xy[:, 1], color="white", alpha=.23, linewidth=.55)
        for i, (ident, parent, *_) in enumerate(panels):
            polygon_patch(ax, parent, facecolor=(1, .65, .15, .22), edgecolor="#ffd453", linewidth=2.8)
            point = parent.representative_point()
            ax.scatter([point.x], [point.y], s=1200 + 550 * np.sin(np.pi * progress),
                       facecolors="none", edgecolors="#00ffff", linewidths=2.5)
            ax.annotate("Selected " + ident, (point.x, point.y), xytext=(50, 20 if i == 0 else -30),
                        textcoords="offset points", color="white", fontsize=13, weight="bold",
                        bbox={"fc": "#101923", "ec": "#00ffff", "alpha": .95, "pad": 6},
                        arrowprops={"arrowstyle": "->", "color": "#00ffff"})
        ax.set_xlim(landscape_bounds[0], landscape_bounds[2])
        ax.set_ylim(landscape_bounds[1], landscape_bounds[3])
        ax.set_aspect("equal")
        ax.axis("off")
        ax.text(.99, .01, "© Esri", transform=ax.transAxes, ha="right", color="white", fontsize=7)
        fig.text(.5, .945, "California landscape", ha="center", color="white", fontsize=23, weight="bold")
        fig.text(.5, .89, "1  |  Narrow necks found · Two examples selected", ha="center", color="#59dbe7", fontsize=20)
        fig.canvas.draw()
        frame = Image.fromarray(np.array(fig.canvas.buffer_rgba())[:, :, :3]).convert("RGB")
        frames.append(frame)
        plt.close(fig)
    frames[-1].save(out / "stage-landscape.png")
    stages = ["1  |  Selected narrow connections", "2  |  Cuts proposed", "3  |  Cutting", "4  |  Final fields"]
    timeline = ([(0, 0.0)] * 6 + [(1, float(t)) for t in np.linspace(0, 1, 12)]
                + [(2, float(t)) for t in np.linspace(0, 1, 22)]
                + [(3, float(t)) for t in np.linspace(0, 1, 24)] + [(3, 1.0)] * 12)
    for frame_index, (stage, progress) in enumerate(timeline):
        title = stages[stage]
        fig, axes = plt.subplots(1, 2, figsize=(14, 7.7), dpi=90, facecolor="#101923")
        fig.subplots_adjust(left=0.025, right=0.975, top=0.82, bottom=0.025, wspace=0.04)
        fig.text(0.5, 0.945, "Narrow-neck repair", ha="center", color="white", fontsize=23, weight="bold")
        fig.text(0.5, 0.89, title, ha="center", color="#59dbe7", fontsize=20)
        for ax, (ident, parent, children, cuts, bounds, image) in zip(axes, panels):
            ax.imshow(image, extent=[bounds[0], bounds[2], bounds[1], bounds[3]])
            if stage < 3:
                polygon_patch(ax, parent, facecolor=(1, 0.5, 0.1, 0.08), edgecolor="#ffac45", linewidth=2.8)
            else:
                for i, child in enumerate(children):
                    reveal = min(1.0, max(0.0, progress * 1.6 - i * .22))
                    polygon_patch(ax, child, facecolor=matplotlib.colors.to_rgba(palette[i], 0.32 * reveal),
                                  edgecolor=matplotlib.colors.to_rgba(palette[i], reveal), linewidth=2.8)
                    polygon_patch(ax, child, facecolor="none", edgecolor=matplotlib.colors.to_rgba("#ffac45", 1 - reveal), linewidth=2.8)
                    point = child.representative_point()
                    ax.text(point.x, point.y, str(i + 1), color="white", fontsize=20, weight="bold",
                            ha="center", va="center", alpha=reveal,
                            bbox={"boxstyle": "circle,pad=.25", "fc": "#101923", "ec": palette[i], "alpha": .9 * reveal})
            segments = list(cuts.geoms) if hasattr(cuts, "geoms") else [cuts]
            if stage == 0:
                for segment in segments:
                    point = segment.interpolate(.5, normalized=True)
                    ax.scatter([point.x], [point.y], s=650, facecolors="none", edgecolors="#ffdf71", linewidths=2)
            if stage == 1:
                for segment in segments:
                    xy = np.array(segment.coords)
                    ax.plot(xy[:, 0], xy[:, 1], color="#00ffff", linewidth=4, linestyle="--")
                    point = segment.interpolate(.5, normalized=True)
                    ax.scatter([point.x], [point.y], s=650 + 150 * np.sin(np.pi * progress),
                               facecolors="none", edgecolors="#00ffff", linewidths=2)
            if stage == 2:
                for segment_index, segment in enumerate(segments):
                    local = min(1.0, max(0.0, progress * len(segments) - segment_index))
                    if local <= 0:
                        continue
                    start = segment.interpolate(0)
                    end = segment.interpolate(local, normalized=True)
                    xy = np.array([[start.x, start.y], [end.x, end.y]])
                    ax.plot(xy[:, 0], xy[:, 1], color="black", linewidth=7, solid_capstyle="round")
                    ax.plot(xy[:, 0], xy[:, 1], color="#00ffff", linewidth=4, solid_capstyle="round")
                    point = segment.interpolate(.5, normalized=True)
                    pulse = 1 + .65 * np.sin(np.pi * local)
                    ax.scatter([point.x], [point.y], s=650 * pulse, facecolors="none", edgecolors="#00ffff", linewidths=2)
                    ax.scatter([end.x], [end.y], s=45, color="white", zorder=10)
            ax.set_xlim(bounds[0], bounds[2])
            ax.set_ylim(bounds[1], bounds[3])
            ax.set_aspect("equal")
            ax.axis("off")
            ax.set_title(ident + (f"  →  {len(children)} fields" if stage == 3 else ""), color="white", fontsize=13, pad=10)
        # Keep imagery attribution off the footer, unobtrusively inside each map.
        for ax in axes:
            ax.text(.99, .01, "© Esri", transform=ax.transAxes, ha="right", color="white", fontsize=7, alpha=.8)
        fig.canvas.draw()
        frame = Image.fromarray(np.array(fig.canvas.buffer_rgba())[:, :, :3]).convert("RGB")
        if frame_index in (5, 17, 39, len(timeline) - 1):
            frame.save(out / f"stage-{stage + 1}.png")
        frames.append(frame)
        plt.close(fig)
    frames[0].save(out / "narrow-neck-repair.gif", save_all=True, append_images=frames[1:],
                   duration=100, loop=0, optimize=True, disposal=1)
    write_json(out / "imagery-provenance.json", imagery_sources)
    (out / "render-source.py").write_bytes(Path(__file__).read_bytes())
    write_json(out / "complete.json", {"preview_run_id": manifest["run_id"], "repairs_applied": 0,
               "input_sha256": {str(source): file_digest(source), str(review_path): file_digest(review_path),
                                str(previews / "proposals.json"): file_digest(previews / "proposals.json")},
               "output_sha256": {p.name: file_digest(p) for p in out.iterdir() if p.is_file()}})
    print(out / "narrow-neck-repair.gif")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot_root")
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(args.pilot_root, args.out_dir)
