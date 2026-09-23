import json

import pytest

from bii.national_product import (
    build_national_dashboard_payload,
    build_national_registry_rows,
    write_national_dashboard_json,
    write_national_registry_jsonl,
)
from bii.national_universe import build_national_rollups


def _records():
    return [
        {
            "dife_public_id": 101,
            "name": "A",
            "location": "Tongi, Gazipur",
            "upazila": "Tongi",
            "district": "Gazipur",
            "division": "Dhaka",
            "sector_label": "Knit",
            "sector_family": "RMG_TEXTILE",
            "status": "Registered",
            "licence_class": "A",
            "observed_at": "2026-09-24T04:00:00+06:00",
        },
        {
            "dife_public_id": 102,
            "name": "B",
            "location": "Tejgaon, Dhaka",
            "upazila": "Tejgaon",
            "district": "Dhaka",
            "division": "Dhaka",
            "sector_label": "Food",
            "sector_family": "FOOD_AGRO",
            "status": "Registered",
            "licence_class": "A",
            "observed_at": "2026-09-24T04:00:00+06:00",
        },
    ]


def test_national_dashboard_is_safe_and_decomposable():
    rollups = build_national_rollups(_records(), universe_label="demo")
    payload = build_national_dashboard_payload(
        rollups,
        universe_label="demo",
        generated_at="2026-09-24T04:10:00+06:00",
        completed_at="2026-09-24T04:05:00+06:00",
        expected_total=2,
        unique_public_ids=2,
        ingest_mode="STAGED_HTML_ARCHIVE",
    )
    assert payload["schema_version"] == "1.0"
    assert payload["universe"]["kind"] == "NATIONAL_REGISTRY"
    assert payload["summary"]["establishments"] == 2
    assert len(payload["district_sector_cells"]) == 2
    serialized = json.dumps(payload)
    for forbidden in ("artifact_path", "source_url", "snapshot_id", "universe_id"):
        assert forbidden not in serialized


def test_dashboard_refuses_inexact_national_coverage():
    rollups = build_national_rollups(_records(), universe_label="demo")
    with pytest.raises(ValueError):
        build_national_dashboard_payload(
            rollups,
            universe_label="demo",
            generated_at="2026-09-24T04:10:00+06:00",
            completed_at=None,
            expected_total=3,
            unique_public_ids=2,
            ingest_mode="NORMALIZED_BULK_EXPORT",
        )


def test_registry_rows_use_public_refs_not_internal_ids():
    rows = build_national_registry_rows(
        _records(),
        universe_label="demo",
        generated_at="2026-09-24T04:10:00+06:00",
    )
    assert [row["establishment_ref"] for row in rows] == ["DIFE:101", "DIFE:102"]
    assert all("dife_public_id" not in row for row in rows)
    assert rows[0]["upazila"] == "Tongi"


def test_national_product_writers_emit_safe_json_and_jsonl(tmp_path):
    records = _records()
    rollups = build_national_rollups(records, universe_label="demo")
    dashboard = build_national_dashboard_payload(
        rollups,
        universe_label="demo",
        generated_at="2026-09-24T04:10:00+06:00",
        completed_at="2026-09-24T04:05:00+06:00",
        expected_total=2,
        unique_public_ids=2,
        ingest_mode="NORMALIZED_BULK_EXPORT",
    )
    registry = build_national_registry_rows(
        records,
        universe_label="demo",
        generated_at="2026-09-24T04:10:00+06:00",
    )
    dashboard_path = write_national_dashboard_json(
        dashboard,
        tmp_path / "dashboard.json",
    )
    registry_path = write_national_registry_jsonl(
        registry,
        tmp_path / "registry.jsonl",
    )

    assert json.loads(dashboard_path.read_text(encoding="utf-8"))["summary"]["establishments"] == 2
    first = json.loads(registry_path.read_text(encoding="utf-8").splitlines()[0])
    assert first["establishment_ref"] == "DIFE:101"
