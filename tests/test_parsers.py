from pathlib import Path

from bii.parsers import extract_public_id, parse_dife_list


def test_extract_public_id():
    assert extract_public_id("/public-report/establishment/12345") == 12345
    assert extract_public_id("/other/12345") is None


def test_parse_dife_list_only_uses_exposed_link_ids():
    html = Path("tests/fixtures/dife_list_minimal.html").read_text(encoding="utf-8")
    rows = parse_dife_list(html)
    assert len(rows) == 1
    row = rows[0]
    assert row.public_id == 12345
    assert row.name == "Example Factory Ltd."
    assert row.detail_url.endswith("/public-report/establishment/12345")
