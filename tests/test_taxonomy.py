from pathlib import Path

from bii.taxonomy import parse_filter_taxonomy


def test_parse_filter_taxonomy_preserves_live_values_and_labels():
    html = Path("tests/fixtures/filter_taxonomy_minimal.html").read_text(encoding="utf-8")
    options = parse_filter_taxonomy(html)
    assert len(options) == 6

    knit = next(option for option in options if option.source_label == "গার্মেন্টস/তৈরি পোশাক (নীট)")
    assert knit.dimension == "INDUSTRIAL_SECTOR"
    assert knit.source_value == "1"

    registered = next(option for option in options if option.source_label == "নিবন্ধিত")
    assert registered.dimension == "STATUS"
    assert registered.source_value == "11"
