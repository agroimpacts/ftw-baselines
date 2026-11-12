"""Non-blocking Jupyter browser for component metric case reviews."""

import ipywidgets as widgets

from research.instance_metrics.archive.review_component_cases import (
    figure_path,
    load_cases,
    save_review,
)


class CaseReviewBrowser:
    """Select a country/category/chip and save reviews without blocking input()."""

    def __init__(self, directory):
        self.directory = directory
        self.country = widgets.Dropdown(description="Country:", layout=widgets.Layout(width="350px"))
        self.comparison = widgets.Dropdown(description="Comparison:", layout=widgets.Layout(width="520px"))
        self.chip = widgets.Dropdown(description="Chip:", layout=widgets.Layout(width="550px"))
        self.finding = widgets.Textarea(description="Finding:", layout=widgets.Layout(width="850px", height="70px"))
        self.fragment = widgets.Dropdown(
            description="Fragment checked:",
            options=[("Not checked", ""), ("Yes", "yes"), ("No", "no"),
                     ("Uncertain", "uncertain")],
            layout=widgets.Layout(width="350px"),
        )
        self.reference_fragments = widgets.Dropdown(
            description="Reference fragments?",
            options=[("Not assessed", ""), ("Present", "present"), 
                     ("Likely", "likely"), ("Unlikely", "unlikely"),
                     ("Absent", "absent"), ("Uncertain", "uncertain")],
            style={"description_width": "initial"},
            layout=widgets.Layout(width="350px"),
        )
        self.uncertainty = widgets.Textarea(description="Notes:", layout=widgets.Layout(width="850px", height="60px"))
        self.save = widgets.Button(description="Save review", button_style="success")
        self.skip = widgets.Button(description="Next chip")
        self.load_image = widgets.Button(description="Load figures")
        self.refresh = widgets.Button(description="Reload CSV")
        self.status = widgets.HTML()
        self.save_feedback = widgets.HTML()
        self.primary_image = widgets.Image(format="png", layout=widgets.Layout(width="100%"))
        self.paired_image = widgets.Image(format="png", layout=widgets.Layout(width="100%"))
        self.primary_image.layout.display = "none"
        self.paired_image.layout.display = "none"
        self.images_ready = False
        self.view = widgets.VBox([
            widgets.HBox([self.country, self.comparison]), self.chip,
            self.status, self.primary_image, self.paired_image,
            self.finding, widgets.HBox([self.fragment, self.reference_fragments]),
            self.uncertainty,
            widgets.HBox([self.load_image, self.save, self.skip, self.refresh]),
            self.save_feedback,
        ])
        self.country.observe(self._country_changed, names="value")
        self.comparison.observe(self._comparison_changed, names="value")
        self.chip.observe(self._chip_changed, names="value")
        self.save.on_click(self._save)
        self.skip.on_click(self._next)
        self.load_image.on_click(self._load_images)
        self.refresh.on_click(self._reload)
        self._reload()

    def _reload(self, _=None):
        selected = (self.country.value, self.comparison.value, self.chip.value)
        self.rows = load_cases(self.directory)
        countries = sorted(self.rows.country.unique())
        self.country.options = countries
        self.country.value = selected[0] if selected[0] in countries else countries[0]
        self._country_changed()
        if selected[1] in self.comparison.options:
            self.comparison.value = selected[1]
        self._comparison_changed()
        if selected[2] in self.chip.options:
            self.chip.value = selected[2]
        self._chip_changed()

    def _country_changed(self, _=None):
        if self.country.value is None:
            return
        comparisons = sorted(self.rows.loc[self.rows.country == self.country.value, "case"].unique())
        self.comparison.options = comparisons
        if self.comparison.value not in comparisons:
            self.comparison.value = comparisons[0]

    def _comparison_changed(self, _=None):
        if self.comparison.value is None:
            return
        self.group = self.rows.loc[
            (self.rows.country == self.country.value)
            & (self.rows.case == self.comparison.value)
        ].reset_index(drop=True)
        self.chip.options = list(self.group.aoi_id)
        if self.chip.value not in self.chip.options:
            self.chip.value = self.chip.options[0]

    def _chip_changed(self, _=None):
        if self.chip.value is None or self.comparison.value is None:
            return
        self.save_feedback.value = ""
        row = self.group.loc[self.group.aoi_id == self.chip.value].iloc[0]
        self.finding.value = str(row.finding)
        fragment = str(row.label_fragment_checked)
        self.fragment.value = fragment if fragment in ("", "yes", "no", "uncertain") else ""
        self.reference_fragments.value = str(row.reference_fragments)
        self.uncertainty.value = str(row.uncertainty)
        reviewed = self.group.finding.astype(str).str.strip().ne("").sum()
        self.status.value = (
            f"<b>{row.country}/{row.aoi_id} — {row.case}</b> | "
            f"{reviewed}/{len(self.group)} reviewed in this comparison | "
            f"PQ {row.pq:.3f} · recall {row.object_recall:.3f} · "
            f"precision {row.object_precision:.3f}"
        )
        if self.images_ready:
            self._show_images()

    def _load_images(self, _=None):
        self.images_ready = True
        self._show_images()

    def _show_images(self):
        row = self.group.loc[self.group.aoi_id == self.chip.value].iloc[0]
        self.primary_image.value = figure_path(self.directory, row.figure).read_bytes()
        self.primary_image.layout.display = "block"
        self.paired_image.value = b""
        self.paired_image.layout.display = "none"
        if row.paired_aoi_id:
            paired = self.group.loc[self.group.aoi_id == row.paired_aoi_id]
            if len(paired) != 1:
                raise ValueError(f"Missing pair for {row.country}/{row.aoi_id}")
            self.paired_image.value = figure_path(self.directory, paired.iloc[0].figure).read_bytes()
            self.paired_image.layout.display = "block"

    def _save(self, _=None):
        if not self.finding.value.strip():
            self.save_feedback.value = "<b>Not saved: enter a finding, or use Next chip.</b>"
            return
        key = (self.country.value, self.chip.value, self.comparison.value)
        try:
            save_review(self.directory, *key, finding=self.finding.value,
                        label_fragment_checked=self.fragment.value,
                        reference_fragments=self.reference_fragments.value,
                        uncertainty=self.uncertainty.value)
        except (OSError, ValueError) as error:
            self.save_feedback.value = f"<b>Not saved:</b> {error}"
            return
        self._reload()
        self.save_feedback.value = "<b>Saved to case_review.csv</b>"

    def _next(self, _=None):
        options = list(self.chip.options)
        index = options.index(self.chip.value)
        if index + 1 < len(options):
            self.chip.value = options[index + 1]
        else:
            self.status.value += " | <b>End of this comparison</b>"
