from bii.national_universe import (
    NationalPageStatus,
    assess_national_universe_quality,
    build_national_rollups,
    explicit_sector_family,
    plan_national_pages,
)


def test_page_plan_uses_complete_declared_total():
    plan = plan_national_pages(
        61,
        first_page_url="https://lima.dife.gov.bd/public-report/establishment-list?page=1",
        page_size=30,
    )
    assert [item.page for item in plan] == [1, 2, 3]
    assert plan[-1].source_url.endswith("page=3")


def test_quality_requires_exact_complete_stable_snapshot():
    quality = assess_national_universe_quality(
        [
            NationalPageStatus(1, "STAGED", 2, 5),
            NationalPageStatus(2, "STAGED", 2, 5),
            NationalPageStatus(3, "STAGED", 1, 5),
        ],
        [101, 102, 103, 104, 105],
        expected_total=5,
    )
    assert quality.eligible_for_national_analysis is True
    assert quality.unique_public_ids == 5
    assert quality.duplicate_public_ids == 0


def test_total_drift_or_duplicate_ids_blocks_national_eligibility():
    drift = assess_national_universe_quality(
        [
            NationalPageStatus(1, "STAGED", 2, 5),
            NationalPageStatus(2, "STAGED", 2, 6),
            NationalPageStatus(3, "STAGED", 1, 6),
        ],
        [101, 102, 103, 104, 105],
        expected_total=5,
    )
    assert drift.eligible_for_national_analysis is False
    assert drift.source_total_stable is False

    duplicate = assess_national_universe_quality(
        [
            NationalPageStatus(1, "STAGED", 2, 5),
            NationalPageStatus(2, "STAGED", 2, 5),
            NationalPageStatus(3, "STAGED", 1, 5),
        ],
        [101, 102, 102, 104, 105],
        expected_total=5,
    )
    assert duplicate.eligible_for_national_analysis is False
    assert duplicate.duplicate_public_ids == 1


def test_unknown_sector_is_not_forced_into_other_manufacturing():
    assert explicit_sector_family("গার্মেন্টস/তৈরি পোশাক (নীট)") == "RMG_TEXTILE"
    assert explicit_sector_family("একটি নতুন অজানা খাত") is None


def test_national_rollups_are_decomposable():
    records = [
        {
            "district": "Gazipur",
            "division": "Dhaka",
            "sector_label": "গার্মেন্টস/তৈরি পোশাক (নীট)",
            "sector_family": "RMG_TEXTILE",
            "status": "Registered",
        },
        {
            "district": "Gazipur",
            "division": "Dhaka",
            "sector_label": "গার্মেন্টস/তৈরি পোশাক (নীট)",
            "sector_family": "RMG_TEXTILE",
            "status": "Registered",
        },
        {
            "district": "Dhaka",
            "division": "Dhaka",
            "sector_label": "ফুড ইন্ডাষ্ট্রিজ",
            "sector_family": "FOOD_AGRO",
            "status": "Registered",
        },
        {
            "district": "Dhaka",
            "division": "Dhaka",
            "sector_label": "নতুন খাত",
            "sector_family": "UNCLASSIFIED",
            "status": "Cancelled",
        },
    ]
    result = build_national_rollups(records, universe_label="demo_national")
    assert result["summary"]["establishments"] == 4
    assert result["summary"]["unclassified_sector_records"] == 1
    rmg = next(
        row for row in result["sector_families"]
        if row["sector_family"] == "RMG_TEXTILE"
    )
    assert rmg["establishments"] == 2
    cell = next(
        row for row in result["district_sector_cells"]
        if row["district"] == "Gazipur"
        and row["sector_family"] == "RMG_TEXTILE"
    )
    assert cell["share_of_district_pct"] == 100.0
    assert cell["share_of_national_sector_pct"] == 100.0
    assert cell["location_quotient"] == 2.0
