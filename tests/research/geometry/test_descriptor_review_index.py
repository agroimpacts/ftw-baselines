from urllib.parse import parse_qs, urlsplit

from research.geometry.build_descriptor_review_index import field_link


def test_review_link_encodes_exact_field_id_and_descriptor(tmp_path):
    root = tmp_path / "index"
    maps = tmp_path / "maps"
    link = field_link(root, maps, "window_1", "id + & space", "circularity")
    assert link.startswith("../maps/window_1/review.html#")
    assert parse_qs(urlsplit(link).fragment) == {
        "field": ["id + & space"],
        "feature": ["circularity"],
    }
