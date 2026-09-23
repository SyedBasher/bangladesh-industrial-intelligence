import pytest

from bii.national_product import (
    build_national_dashboard_payload,
    build_national_registry_rows,
)
from bii.national_profiles import (
    build_district_profile,
    build_sector_profile,
    filter_registry_for_profile,
    write_national_profile_json,
)
from bii.national_universe import build_national_rollups


def _records():
    return [
        {
            "dife_public_id": 101,
            "name": "Gazipur Knit A",
            "location": "Tongi, Gazipur",
            "upazila": "Tongi",
            "district": "Gazipur",
            "division": "Dhaka",
            "sector_label": "Knit",
            "sector_family": "RMG_TEXTILE",
            "status": "Registered",
            "licence_class": "A",
            "observed_at": "2026-09-24T05:00:00+06:00",
        },
        {
            "dife_public_id": 102,
            "name": "Gazipur Knit B",
            "location": "Kaliakair, Gazipur",
            "upazila": "Kaliakair",
            "district": "Gazipur",
            "division": "Dhaka",
            "sector_label": "Knit",
            "sector_family": "RMG_TEXTILE",
            "status": "Registered",
            "licence_class": "A",
            "observed_at": "2026-09-24T05:00:00+06:00",
        },
        {
            "dife_public_id": 103,
            "name": "Gazipur Food",
            "location": "Tongi, Gazipur",
            "upazila": "Tongi",
            "district": "Gazipur",
            "division": "Dhaka",
            "sector_label": "Food",
            "sector_family": "FOOD_AGRO",
            "status": "Registered",
            "licence_class": "B",
            "observed_at": "2026-09-24T05:00:00+06:00",
        },
        {
            "dife_public_id": 104,
            "name": "Dhaka Knit",
            "location": "Tejgaon, Dhaka",
            "upazila": "Tejgaon",
            "district": "Dhaka",
            "division": "Dhaka",
            "sector_label": "Knit",
            "sector_family": "RMG_TEXTILE",
            "status": "Cancelled",
            "licence_class": "A",
            "observed_at": "2026-09-24T05:00:00+06:00",
        },
        {
            "dife_public_id": 105,
            "name": "Dhaka Unknown",
            "location": "Tejgaon, Dhaka",
            "upazila": "Tejgaon",
            "district": "Dhaka",
            "division": "Dhaka",
            "sector_label": "Unknown source sector",
            "sector_family": "UNCLASSIFIED",
            "status": "Registered",
            "licence_class": "A",
            "observed_at": "2026-09-24T05:00:00+06:00",
        },
    ]


def _safe_inputs():
    records = _records()
    rollups = build_national_rollups(records, universe_label="demo")
    dashboard = build_national_dashboard_payload(
        rollups,
        universe_label="demo",
        generated_at="2026-09-24T05:10:00+06:00",
        completed_at="2026-09-24T05:05:00+06:00",
        expected_total=5,
        unique_public_ids=5,
        ingest_mode="STAGED_HTML_ARCHIVE",
    )
    registry = build_national_registry_rows(
        records,
        universe_label="demo",
        generated_at="2026-09-24T05:10:00+06:00",
    )
    return dashboard, registry


def test_district_profile_is_decomposable_and_drillable():
    dashboard, registry = _safe_inputs()
    profile = build_district_profile(
        dashboard,
        registry,
        district="Gazipur",
        generated_at="2026-09-24T05:11:00+06:00",
    )
    assert profile["schema_version"] == "1.0"
    assert profile["district"]["establishments"] == 3
    assert profile["coverage"]["sector_mapping_coverage_pct"] == 100.0
    assert profile["composition"]["upazilas"][0] == {
        "upazila": "Tongi",
        "establishments": 2,
        "share_pct": 66.6667,
    }
    rmg = next(
        row for row in profile["composition"]["sector_families"]
        if row["sector_family"] == "RMG_TEXTILE"
    )
    assert rmg["establishments"] == 2
    assert rmg["location_quotient"] > 1
    assert rmg["specialization_flag"] == "ABOVE_NATIONAL_SHARE"
    assert profile["drilldown"]["registry_filter"] == {"district": "Gazipur"}

    drill = filter_registry_for_profile(registry, profile)
    assert len(drill) == 3
    assert all(row["district"] == "Gazipur" for row in drill)


def test_sector_profile_shows_geographic_concentration_without_composite_score():
    dashboard, registry = _safe_inputs()
    profile = build_sector_profile(
        dashboard,
        registry,
        sector_family="RMG_TEXTILE",
        generated_at="2026-09-24T05:11:00+06:00",
    )
    assert profile["sector"]["establishments"] == 3
    assert profile["sector"]["district_count"] == 2
    assert profile["concentration"]["district_hhi"] is not None
    assert profile["concentration"]["largest_3_district_share_pct"] == 100.0
    assert "score" not in profile
    assert "score" not in profile["concentration"]
    assert profile["drilldown"]["registry_filter"] == {
        "sector_family": "RMG_TEXTILE"
    }

    drill = filter_registry_for_profile(registry, profile)
    assert len(drill) == 3
    assert all(row["sector_family"] == "RMG_TEXTILE" for row in drill)


def test_district_profile_preserves_unclassified_coverage():
    dashboard, registry = _safe_inputs()
    profile = build_district_profile(
        dashboard,
        registry,
        district="Dhaka",
        generated_at="2026-09-24T05:11:00+06:00",
    )
    assert profile["coverage"]["unclassified_sector_records"] == 1
    assert profile["coverage"]["sector_mapping_coverage_pct"] == 50.0


def test_profile_refuses_registry_that_does_not_match_national_universe():
    dashboard, registry = _safe_inputs()
    with pytest.raises(ValueError):
        build_district_profile(
            dashboard,
            registry[:-1],
            district="Gazipur",
            generated_at="2026-09-24T05:11:00+06:00",
        )


def test_unknown_profile_dimension_fails_explicitly():
    dashboard, registry = _safe_inputs()
    with pytest.raises(KeyError):
        build_sector_profile(
            dashboard,
            registry,
            sector_family="NOT_A_REAL_FAMILY",
            generated_at="2026-09-24T05:11:00+06:00",
        )


def test_profile_json_writer_preserves_safe_contract(tmp_path):
    dashboard, registry = _safe_inputs()
    profile = build_district_profile(
        dashboard,
        registry,
        district="Gazipur",
        generated_at="2026-09-24T05:11:00+06:00",
    )
    path = write_national_profile_json(profile, tmp_path / "gazipur.json")
    loaded = __import__("json").loads(path.read_text(encoding="utf-8"))
    assert loaded["district"]["name"] == "Gazipur"
    serialized = path.read_text(encoding="utf-8")
    for forbidden in ("source_url", "snapshot_id", "universe_id", "artifact_path"):
        assert forbidden not in serialized
