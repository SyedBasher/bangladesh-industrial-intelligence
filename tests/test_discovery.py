from bii.discovery import (
    DiscoveryRequest,
    SectorUniverse,
    allocate_desired_rows,
    build_filter_url,
    candidate_pool_health,
    plan_seed_requests,
    plan_spread_requests,
    universe_from_seed_html,
)
from bii.sampling import ValidationCandidate
from bii.taxonomy import FilterOption


def test_build_filter_url_is_explicit_and_page_scoped():
    url = build_filter_url(sector_value="44", page=7)
    assert "industry_id=44" in url
    assert "page=7" in url
    assert "filter=filter" in url


def test_seed_plan_uses_live_taxonomy_values_not_hard_coded_ids():
    options = [
        FilterOption("INDUSTRIAL_SECTOR", "9001", "গার্মেন্টস/তৈরি পোশাক (নীট)"),
        FilterOption("INDUSTRIAL_SECTOR", "9002", "ফার্মাসিউটিক্যালস (এ্যালোপ্যাথিক)"),
        FilterOption("DISTRICT", "33", "গাজীপুর"),
    ]
    requests = plan_seed_requests(options)
    assert [request.source_sector_value for request in requests] == ["9002", "9001"]
    assert all(request.page == 1 for request in requests)
    assert all(request.reason == "UNIVERSE_SEED" for request in requests)


def test_universe_comes_from_source_reported_total():
    request = DiscoveryRequest(
        "RMG_TEXTILE",
        "9001",
        "গার্মেন্টস/তৈরি পোশাক (নীট)",
        1,
        "https://example.invalid",
        "UNIVERSE_SEED",
    )
    html = """
    <html><body>
      <div>প্রাপ্ত তথ্য : ৪,১৬৬ টি</div>
      <table><tr>
        <td><a href="/public-report/establishment/123">A</a></td>
        <td>গার্মেন্টস/তৈরি পোশাক (নীট)</td>
        <td>গাজীপুর সদর, গাজীপুর, ঢাকা</td><td>এ</td><td>নিবন্ধিত</td>
      </tr></table>
    </body></html>
    """
    universe = universe_from_seed_html(request, html)
    assert universe.total_records == 4166
    assert universe.source_sector_value == "9001"


def test_allocation_preserves_small_source_sector_with_one_page():
    universes = [
        SectorUniverse("RMG_TEXTILE", "1", "Knit A", 4000),
        SectorUniverse("RMG_TEXTILE", "2", "Knit B", 4),
    ]
    allocation = allocate_desired_rows(universes, candidate_multiplier=1.5, page_size=30)
    assert allocation[("2", "Knit B")] == 4
    assert allocation[("1", "Knit A")] >= 30


def test_spread_plan_skips_already_staged_first_page():
    universes = [SectorUniverse("RMG_TEXTILE", "1", "Knit", 4166)]
    requests = plan_spread_requests(universes, candidate_multiplier=1.5, page_size=30)
    assert requests
    assert all(request.page != 1 for request in requests)
    assert requests[-1].page == 139


def test_candidate_health_reports_real_deficits_without_inventing_rows():
    candidates = [
        ValidationCandidate(1, "গার্মেন্টস/তৈরি পোশাক (নীট)", "গাজীপুর"),
        ValidationCandidate(2, "ফার্মাসিউটিক্যালস (এ্যালোপ্যাথিক)", "ঢাকা"),
    ]
    health = candidate_pool_health(candidates)
    assert health["unique_candidates"] == 2
    assert health["ready_for_2000_freeze"] is False
    assert health["sector_deficits"]["RMG_TEXTILE"] == 499
    assert health["geography_deficits"]["CORE_DHAKA"] == 698
