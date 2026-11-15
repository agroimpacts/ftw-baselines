"""Regional geometry summaries or correlations of final-polygon descriptors."""

import argparse
import json
from pathlib import Path

from ftw_geometry.core.analysis import correlate_tables, summarize_regions
from ftw_geometry.core.dataset import dataset_parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    regions = commands.add_parser("regions")
    regions.add_argument("dataset")
    regions.add_argument("regions")
    regions.add_argument("--region_id", required=True)
    regions.add_argument("--edge_policy", choices=["include", "exclude"], required=True)
    regions.add_argument("--gap_radius_m", type=float, required=True)
    regions.add_argument("--max_fields", type=int, default=100000)
    regions.add_argument("--out_dir", required=True)
    correlations = commands.add_parser("correlations")
    inputs = correlations.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--dataset")
    inputs.add_argument("--tables", nargs="+")
    correlations.add_argument(
        "--metric_crs",
        help="Required for --tables; dataset CRS is read from its manifest",
    )
    correlations.add_argument("--features", nargs="+", required=True)
    correlations.add_argument("--group_column", required=True)
    correlations.add_argument("--level", choices=["field", "area"], default="field")
    correlations.add_argument("--sample_size", type=int, default=2000)
    correlations.add_argument("--max_groups", type=int, default=256)
    correlations.add_argument("--block_size_m", type=float, required=True)
    correlations.add_argument("--bootstrap_replicates", type=int, default=200)
    correlations.add_argument("--seed", type=int, default=42)
    correlations.add_argument("--log_features", nargs="*", default=[])
    correlations.add_argument("--pca_features", nargs="*", default=[])
    correlations.add_argument("--no_size_strata", action="store_true")
    correlations.add_argument("--out_dir", required=True)
    args = vars(parser.parse_args())
    if args.pop("command") == "regions":
        summarize_regions(
            args.pop("dataset"), args.pop("regions"), args.pop("out_dir"), **args
        )
    else:
        dataset, paths = args.pop("dataset"), args.pop("tables")
        if dataset:
            manifest = json.loads((Path(dataset) / "manifest.json").read_text())
            if args["metric_crs"] and args["metric_crs"] != manifest["metric_crs"]:
                parser.error("metric_crs must match the dataset manifest")
            args["metric_crs"] = manifest["metric_crs"]
            paths = list(dataset_parts(dataset))
        args["size_strata"] = not args.pop("no_size_strata")
        correlate_tables(paths, args.pop("out_dir"), **args)


if __name__ == "__main__":
    main()
