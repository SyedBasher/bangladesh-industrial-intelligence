from pathlib import Path

from bii.parsers import (
    bengali_digits_to_ascii,
    extract_public_id,
    parse_dife_detail,
    parse_dife_list,
    parse_dife_list_page,
    parse_int_mixed,
)


def test_extract_public_id():
    assert extract_public_id("/public-report/establishment/12345") == 12345
    assert extract_public_id("/other/12345") is None


def test_digit_normalization():
    assert bengali_digits_to_ascii("১২৩") == "123"
    assert parse_int_mixed("১,২০০ টি") == 1200


def test_parse_dife_list_only_uses_exposed_link_ids():
    html = Path("tests/fixtures/dife_list_minimal.html").read_text(encoding="utf-8")
    rows = parse_dife_list(html)
    assert len(rows) == 1
    row = rows[0]
    assert row.public_id == 12345
    assert row.name == "Example Factory Ltd."
    assert row.detail_url.endswith("/public-report/establishment/12345")


def test_parse_list_metadata_and_admin_parts():
    html = Path("tests/fixtures/dife_list_metadata_minimal.html").read_text(encoding="utf-8")
    meta, rows = parse_dife_list_page(html)
    assert meta.total_records == 1200
    assert meta.showing_records == 30
    assert meta.source_reported_at_raw == "২৩-০৯-২০২৬ ২০:৩০"
    assert rows[0].upazila == "গাজীপুর সদর"
    assert rows[0].district == "গাজীপুর"
    assert rows[0].division == "ঢাকা"


def test_parse_detail_keeps_source_fields_separate():
    html = Path("tests/fixtures/dife_detail_minimal.html").read_text(encoding="utf-8")
    detail = parse_dife_detail(html)
    assert detail.name_en == "Example Factory Ltd."
    assert detail.name_bn == "উদাহরণ ফ্যাক্টরি লিঃ"
    assert detail.district == "গাজীপুর"
    assert detail.status == "নিবন্ধিত"
    assert detail.establishment_type == "কারখানা"
    assert detail.worker_component_1 == 12
    assert detail.worker_component_2 == 8
    assert detail.worker_total == 20
