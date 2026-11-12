"""Read and persist manual reviews of components-4 diagnostic case candidates.

The notebook in notebooks/review_component_cases.ipynb provides the viewer.
This module only touches case_review.csv, never candidate tables or figures.
"""

import os
import tempfile
from pathlib import Path

import pandas as pd

KEY = ("country", "aoi_id", "case")
REVIEW_COLUMNS = (*KEY, "finding", "label_fragment_checked", "reference_fragments", "uncertainty")
FRAGMENT_ASSESSMENTS = ("", "present", "likely", "unlikely", "absent", "uncertain")
NUMERIC_COLUMNS = (
    "gap", "object_recall", "object_precision", "object_f1", "rq", "sq", "pq",
    "recovery", "support", "rand_split_score", "rand_merge_score",
    "stat_tp", "stat_fp", "stat_fn",
)


def load_cases(directory):
    """Read candidate rows and existing reviews, preserving original order."""
    directory = Path(directory).expanduser().resolve()
    cases = pd.read_csv(directory / "case_candidates.csv", keep_default_na=False)
    if not set((*KEY, "figure")).issubset(cases):
        raise ValueError("Candidate table lacks country/AOI/case/figure columns")
    if cases.duplicated(list(KEY)).any():
        raise ValueError("Duplicate candidate review keys")
    for name in NUMERIC_COLUMNS:
        if name in cases:
            cases[name] = pd.to_numeric(cases[name], errors="raise")
    reviews = load_reviews(directory)
    merged = cases.merge(reviews, on=list(KEY), how="left", validate="one_to_one",
                         suffixes=("", "_review"))
    merged[list(REVIEW_COLUMNS[3:])] = merged[list(REVIEW_COLUMNS[3:])].fillna("")
    return merged


def load_reviews(directory):
    """Read the current on-disk review CSV, including additional user columns."""
    path = Path(directory).expanduser().resolve() / "case_review.csv"
    if not path.exists():
        return pd.DataFrame(columns=REVIEW_COLUMNS)
    reviews = pd.read_csv(path, dtype=str, keep_default_na=False)
    legacy_columns = set(REVIEW_COLUMNS) - {"reference_fragments"}
    if not legacy_columns.issubset(reviews):
        raise ValueError(f"Review CSV missing required columns: {path}")
    if "reference_fragments" not in reviews:
        # Existing reviews recorded only whether fragments were checked; do
        # not infer a positive/negative assessment from that status.
        reviews["reference_fragments"] = ""
    if reviews.duplicated(list(KEY)).any():
        raise ValueError(f"Duplicate review keys: {path}")
    return reviews


def figure_path(directory, figure):
    """Only allow figure paths inside the selected analysis directory."""
    directory = Path(directory).expanduser().resolve()
    path = (directory / figure).resolve()
    if not path.is_relative_to(directory / "figures") or path.suffix.lower() != ".png":
        raise ValueError(f"Unexpected figure path: {figure}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def save_review(directory, country, aoi_id, case, *, finding,
                label_fragment_checked="", reference_fragments="", uncertainty=""):
    """Atomically update one keyed row, retaining other reviews and extra columns."""
    directory = Path(directory).expanduser().resolve()
    key = (str(country), str(aoi_id), str(case))
    candidates = pd.read_csv(directory / "case_candidates.csv", dtype=str,
                             keep_default_na=False)
    if not ((candidates[list(KEY)] == key).all(axis=1)).any():
        raise ValueError(f"Not a candidate: {key}")
    reviews = load_reviews(directory)
    review = dict(zip(KEY, key))
    review.update(finding=str(finding).strip(),
                  label_fragment_checked=str(label_fragment_checked).strip(),
                  reference_fragments=str(reference_fragments).strip(),
                  uncertainty=str(uncertainty).strip())
    if not review["finding"]:
        raise ValueError("Finding must not be empty; use 'uncertain' if needed")
    if review["reference_fragments"] not in FRAGMENT_ASSESSMENTS:
        raise ValueError("Reference fragments must be not assessed, present, likely, unlikely, absent, or uncertain")
    matched = (reviews[list(KEY)] == key).all(axis=1)
    if matched.any():
        for name, value in review.items():
            reviews.loc[matched, name] = value
    else:
        reviews = pd.concat([reviews, pd.DataFrame([review])], ignore_index=True)
    # Write in the same directory so os.replace is atomic on this filesystem.
    with tempfile.NamedTemporaryFile(mode="w", prefix=".case_review-", suffix=".csv",
                                     dir=directory, delete=False, newline="") as temporary:
        scratch = Path(temporary.name)
    try:
        reviews.to_csv(scratch, index=False)
        os.replace(scratch, directory / "case_review.csv")
    finally:
        scratch.unlink(missing_ok=True)
    return directory / "case_review.csv"
