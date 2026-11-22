"""Supplement completed Chamfer analyses with strata and outline review panels."""

import argparse
import html
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

from ftw_tools.settings import has_labeled_background
from ftw_tools.training.metrics import instance_match_labels
from research.instance_metrics.analyze_chamfer import EXTRA_PAIRS, NEW
from scripts.instance_evaluation.compare_instance_methods import read_reference_ids


def supplement(root):
    data = pd.read_parquet(root / "chips.parquet")
    out = root / "review"
    out.mkdir(exist_ok=False)
    associations = []
    # Terciles are within country and reference mode, never global size cutoffs.
    for (mode, country), group in data[
        data.country.map(has_labeled_background)
    ].groupby(["reference_mode", "country"]):
        for stratifier in ("mean_reference_area_m2", NEW[2]):
            values = group[stratifier]
            if values.nunique() < 3:
                continue
            bins = pd.qcut(values, 3, duplicates="drop")
            for interval, part in group.groupby(bins, observed=True):
                for a, b in EXTRA_PAIRS:
                    pair = part[[a, b]].replace([np.inf, -np.inf], np.nan).dropna()
                    associations.append(
                        {
                            "reference_mode": mode,
                            "country": country,
                            "stratifier": stratifier,
                            "stratum": str(interval),
                            "first": a,
                            "second": b,
                            "n": len(pair),
                            "spearman": pair[a].corr(pair[b], method="spearman"),
                            "pearson": pair[a].corr(pair[b]),
                        }
                    )
    pd.DataFrame(associations).to_csv(out / "stratified_associations.csv", index=False)
    links = []
    for mode in data.reference_mode.unique():
        shortlist = pd.read_csv(root / "available" / mode / "discordant_chips.csv")
        shortlist = shortlist[
            (shortlist.scope == "all")
            & (shortlist["first"].isin(NEW) | shortlist["second"].isin(NEW))
        ]
        shortlist = shortlist.groupby(["first", "second"], sort=False).head(3)
        shortlist.to_csv(out / f"{mode}-shortlist.csv", index=False)
        keys = shortlist[["country", "aoi_id"]].drop_duplicates()
        for key in keys.itertuples(index=False):
            row = data[
                (data.reference_mode == mode)
                & (data.country == key.country)
                & (data.aoi_id == key.aoi_id)
            ].iloc[0]
            with (
                rasterio.open(row.reference) as ref,
                rasterio.open(Path(row.source_run) / row.prediction) as pred,
            ):
                truth, prediction = ref.read(1), pred.read(1)
                labels = (
                    read_reference_ids(row.reference, truth, ref.profile)[0]
                    if mode == "dataset-instance-ids"
                    else None
                )
            gt, pr, gm, pm, _ = instance_match_labels(
                truth, prediction, reference_labels=labels
            )
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))
            axes[0].imshow(
                np.ma.masked_equal(gt, 0), cmap="tab20", interpolation="nearest"
            )
            axes[1].imshow(
                np.ma.masked_equal(pr, 0), cmap="tab20", interpolation="nearest"
            )
            axes[2].imshow(np.zeros(gt.shape), cmap="gray", vmin=0, vmax=1)
            for rid in np.unique(gt[gt > 0]):
                axes[2].contour(
                    gt == rid, levels=[0.5], colors=["cyan"], linewidths=0.5
                )
            for pid in np.unique(pr[pr > 0]):
                axes[2].contour(
                    pr == pid, levels=[0.5], colors=["orange"], linewidths=0.5
                )

            def centre(mask):
                yy, xx = np.nonzero(mask)
                return xx.mean(), yy.mean()

            for rid, pid in zip(gm, pm):
                a, b = centre(gt == rid), centre(pr == pid)
                axes[2].plot([a[0], b[0]], [a[1], b[1]], color="lime", linewidth=0.6)
            pred_areas = np.bincount(pr.ravel())
            for rid in np.unique(gt[gt > 0]):
                mask = gt == rid
                ids, counts = np.unique(pr[mask], return_counts=True)
                candidates = [
                    (pid, inter / (mask.sum() + pred_areas[pid] - inter))
                    for pid, inter in zip(ids, counts)
                    if pid > 0
                ]
                if candidates:
                    pid = max(candidates, key=lambda t: (t[1], -t[0]))[0]
                    a, b = centre(mask), centre(pr == pid)
                    axes[2].plot(
                        [a[0], b[0]],
                        [a[1], b[1]],
                        color="magenta",
                        linestyle=":",
                        linewidth=0.6,
                    )
            for axis, title in zip(
                axes,
                [
                    "Reference objects",
                    "Prediction objects",
                    "Cyan ref / orange pred; green threshold / magenta best-IoU links",
                ],
            ):
                axis.set_title(title, fontsize=9)
                axis.set_axis_off()
            fig.suptitle(
                f"{mode}: {key.country}/{key.aoi_id}\nThreshold {row[NEW[0]]:.2f} m; best-IoU {row[NEW[1]]:.2f} m; coverage {row[NEW[2]]:.1%}"
            )
            fig.tight_layout()
            filename = f"{mode}-{key.country}-{key.aoi_id}.png"
            fig.savefig(out / filename, dpi=120)
            plt.close(fig)
            links.append(
                f'<li><a href="{html.escape(filename)}">{html.escape(mode + ": " + key.country + "/" + key.aoi_id)}</a></li>'
            )
    (out / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Chamfer disagreement review</title><h1>Selected disagreement examples</h1><p>Development shortlist, not an accuracy sample. No imagery validation. Colours are reused across IDs; centroid links show pairings, not boundary distances. No missing-distance imputation.</p><ul>'
        + "".join(links)
        + "</ul>"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    supplement(parser.parse_args().root)
