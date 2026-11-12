import json

import pandas as pd
import pytest

from research.instance_metrics.archive.review_component_cases import (
    figure_path,
    load_cases,
    save_review,
)


def _analysis(tmp_path):
    directory = tmp_path / "analysis"
    directory.mkdir()
    (directory / "figures").mkdir()
    (directory / "figures" / "one.png").write_bytes(b"fake png")
    pd.DataFrame([
        {"country": "belgium", "aoi_id": "one", "case": "high_pq",
         "figure": "figures/one.png", "pq": 0.75, "sq": 0.8,
         "object_recall": 0.9, "object_precision": 0.8,
         "paired_aoi_id": ""},
        {"country": "belgium", "aoi_id": "one", "case": "size_gap",
         "figure": "figures/one.png", "pq": "", "sq": "",
         "object_recall": 0.5, "object_precision": 0.6,
         "paired_aoi_id": ""},
    ]).to_csv(directory / "case_candidates.csv", index=False)
    pd.DataFrame(columns=["country", "aoi_id", "case", "finding",
                          "label_fragment_checked", "uncertainty", "reviewer_note"]
                 ).to_csv(directory / "case_review.csv", index=False)
    return directory


def test_save_review_updates_one_case_preserves_other_rows_and_extra_columns(tmp_path):
    directory = _analysis(tmp_path)
    assert load_cases(directory).finding.tolist() == ["", ""]
    assert load_cases(directory).reference_fragments.tolist() == ["", ""]
    assert load_cases(directory).pq.iloc[0] == pytest.approx(0.75)
    assert pd.isna(load_cases(directory).pq.iloc[1])
    save_review(directory, "belgium", "one", "high_pq", finding="good",
                label_fragment_checked="yes", reference_fragments="unlikely",
                uncertainty="slightly clipped")
    assert load_cases(directory).finding.tolist() == ["good", ""]
    reviews = pd.read_csv(directory / "case_review.csv", keep_default_na=False)
    reviews.loc[0, "reviewer_note"] = "keep me"
    reviews.to_csv(directory / "case_review.csv", index=False)
    save_review(directory, "belgium", "one", "size_gap", finding="small miss")
    save_review(directory, "belgium", "one", "high_pq", finding="actually poor")
    reviews = pd.read_csv(directory / "case_review.csv", keep_default_na=False)
    assert len(reviews) == 2
    assert reviews.loc[0, "reviewer_note"] == "keep me"
    assert reviews.loc[0, "finding"] == "actually poor"
    assert reviews.loc[0, "reference_fragments"] == ""
    assert reviews.loc[1, "finding"] == "small miss"


def test_save_rejects_non_candidate_empty_review_and_outside_figure(tmp_path):
    directory = _analysis(tmp_path)
    assert figure_path(directory, "figures/one.png").name == "one.png"
    for path in ("../outside.png", "figures/../case_candidates.csv"):
        with pytest.raises(ValueError, match="Unexpected figure"):
            figure_path(directory, path)
    with pytest.raises(ValueError, match="Not a candidate"):
        save_review(directory, "belgium", "other", "high_pq", finding="test")
    with pytest.raises(ValueError, match="Finding must not be empty"):
        save_review(directory, "belgium", "one", "high_pq", finding=" ")
    with pytest.raises(ValueError, match="Reference fragments"):
        save_review(directory, "belgium", "one", "high_pq", finding="test",
                    reference_fragments="definitely")
    assert pd.read_csv(directory / "case_review.csv").empty


def test_notebook_is_valid_and_does_not_use_blocking_input():
    from pathlib import Path

    import nbformat

    from research.instance_metrics.archive import review_component_cases

    notebook = Path(review_component_cases.__file__).with_name(
        "review_component_cases.ipynb"
    )
    nbformat.validate(nbformat.read(notebook, as_version=4))
    data = json.loads(notebook.read_text())
    code = "\n".join("".join(cell["source"]) for cell in data["cells"]
                     if cell["cell_type"] == "code")
    assert "input(" not in code


def test_widget_country_comparison_and_chip_selection(tmp_path):
    pytest.importorskip("ipywidgets")
    from research.instance_metrics.archive.component_review_widget import (
        CaseReviewBrowser,
    )

    directory = _analysis(tmp_path)
    browser = CaseReviewBrowser(directory)
    assert browser.country.value == "belgium"
    assert browser.chip.value == "one"
    assert browser.primary_image.value == b""  # No image rendering during cell startup.
    browser.finding.value = "Plausible reference slivers"
    browser.fragment.value = "yes"
    browser.reference_fragments.value = "likely"
    browser._save()
    stored = pd.read_csv(directory / "case_review.csv", keep_default_na=False)
    assert stored.loc[0, "label_fragment_checked"] == "yes"
    assert stored.loc[0, "reference_fragments"] == "likely"
    browser.reference_fragments.value = "present"
    browser._save()
    assert "Saved" in browser.save_feedback.value
    assert pd.read_csv(directory / "case_review.csv").loc[0, "reference_fragments"] == "present"
    browser.reference_fragments.value = "absent"
    browser._save()
    assert pd.read_csv(directory / "case_review.csv").loc[0, "reference_fragments"] == "absent"
    browser.comparison.value = "size_gap"
    assert browser.group.case.tolist() == ["size_gap"]
    assert browser.chip.value == "one"
    browser._load_images()
    assert browser.primary_image.value == b"fake png"
    assert len(pd.read_csv(directory / "case_review.csv")) == 1
