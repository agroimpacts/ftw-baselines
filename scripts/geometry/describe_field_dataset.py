"""Build/resume a final-polygon descriptor dataset from an explicit JSON manifest."""

import argparse

from ftw_geometry.core.dataset import build_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--batch_size", type=int, default=10000)
    args = parser.parse_args()
    build_dataset(args.manifest, args.out_dir, args.batch_size)


if __name__ == "__main__":
    main()
