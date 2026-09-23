from bii.discovery import SectorUniverse
from bii.supplement import (
    SupplementRequest,
    SupplementUniverse,
    build_district_sector_url,
    plan_geographic_seed_requests,
    plan_geographic_spread_requests,
    universe_from_supplement_seed_html,
)
from bii.taxonomy import FilterOption


def _options():
    return [
        FilterOption("DISTRICT", "33", "গাজীপুর"),
        FilterOption("DISTRICT", "27", "ঢাকা"),
        FilterOption("DISTRICT", "14", "দিনাজপুর"),
        FilterOption("DISTRICT", "50", "রংপুর"),
        FilterOption("INDUSTRIAL_SECTOR", "1", "গার্মেন্টস/তৈরি পোশাক (নীট)"),
        FilterOption("INDUSTRIAL_SECTOR", "44", "ফার্মাসিউটিক্যালস (এ্যালোপ্যাথিক)"),
        FilterOption("INDUSTRIAL_SECTOR", "80", "রাইস মিল (অটো)"),
    ]


def test_district_sector_url_carries_both_live_filter_values():
    url = build_district_sector_url(district_value="14", sector_value="80", page=4)
    assert "district=14" in url
    assert "industry_id=80" in url
    assert "page=4" in url


def test_geographic_seed_requests_only_target_deficient_groups():
    health = {
        "geography_deficits": {"NORTHWEST": 120},
        "sector_deficits": {"FOOD_AGRO": 80},
    }
    universes = [
        SectorUniverse("FOOD_AGRO", "80", "রাইস মিল (অটো)", 800),
        SectorUniverse("RMG_TEXTILE", "1", "গার্মেন্টস/তৈরি পোশাক (নীট)", 4000),
    ]
    requests = plan_geographic_seed_requests(
        _options(),
        health,
        sector_universes=universes,
        max_districts_per_group=2,
        max_sector_options_per_group=2,
    )
    assert requests
    assert all(request.geography_group == "NORTHWEST" for request in requests)
    assert any(request.source_sector_value == "80" for request in requests)
    assert all(request.page == 1 for request in requests)


def test_geographic_seed_plan_is_bounded_not_cartesian():
    health = {
        "geography_deficits": {"NORTHWEST": 300, "CORE_DHAKA": 300},
        "sector_deficits": {},
    }
    requests = plan_geographic_seed_requests(
        _options(),
        health,
        max_districts_per_group=1,
        max_sector_options_per_group=2,
    )
    assert len(requests) <= 4


def test_supplement_universe_comes_from_source_total():
    request = SupplementRequest(
        "NORTHWEST",
        "14",
        "দিনাজপুর",
        "FOOD_AGRO",
        "80",
        "রাইস মিল (অটো)",
        1,
        "https://example.invalid",
        "GEOGRAPHY_SEED",
    )
    html = """
    <html><body>
      <div>প্রাপ্ত তথ্য : ৬২ টি</div>
      <table><tr>
        <td><a href="/public-report/establishment/123">A</a></td>
        <td>রাইস মিল (অটো)</td>
        <td>দিনাজপুর সদর, দিনাজপুর, রংপুর</td><td>এ</td><td>নিবন্ধিত</td>
      </tr></table>
    </body></html>
    """
    universe = universe_from_supplement_seed_html(request, html)
    assert universe.total_records == 62
    assert universe.geography_group == "NORTHWEST"


def test_spread_plan_uses_only_nonempty_supplement_universes():
    universes = [
        SupplementUniverse(
            "NORTHWEST", "14", "দিনাজপুর", "FOOD_AGRO", "80", "রাইস মিল (অটো)", 62
        ),
        SupplementUniverse(
            "NORTHWEST", "50", "রংপুর", "FOOD_AGRO", "80", "রাইস মিল (অটো)", 0
        ),
    ]
    requests = plan_geographic_spread_requests(
        universes,
        {"NORTHWEST": 50},
        candidate_multiplier=1.25,
        page_size=30,
    )
    assert requests
    assert all(request.source_district_value == "14" for request in requests)
    assert all(request.page != 1 for request in requests)
