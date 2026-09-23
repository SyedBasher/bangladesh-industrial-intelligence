from bii.sampling import (
    ValidationCandidate,
    classify_geography,
    classify_sector,
    select_validation_sample,
    spread_pages,
    summarize_selection,
)


def test_spread_pages_reaches_both_ends_of_result_set():
    pages = spread_pages(total_records=4166, desired_rows=150, page_size=30)
    assert pages[0] == 1
    assert pages[-1] == 139
    assert len(pages) == 5
    assert pages == sorted(set(pages))


def test_classification_uses_source_labels_not_internal_ids():
    assert classify_sector("গার্মেন্টস/তৈরি পোশাক (নীট)") == "RMG_TEXTILE"
    assert classify_sector("ফার্মাসিউটিক্যালস (এ্যালোপ্যাথিক)") == "PHARMA_CHEM_PLASTIC"
    assert classify_geography("গাজীপুর") == "CORE_DHAKA"
    assert classify_geography("দিনাজপুর") == "NORTHWEST"


def test_sample_planner_is_deterministic_and_deduplicates_public_ids():
    candidates = [
        ValidationCandidate(3, "গার্মেন্টস/তৈরি পোশাক (নীট)", "গাজীপুর"),
        ValidationCandidate(1, "ফার্মাসিউটিক্যালস (এ্যালোপ্যাথিক)", "ঢাকা"),
        ValidationCandidate(2, "রাইস মিল (অটো)", "দিনাজপুর"),
        ValidationCandidate(2, "রাইস মিল (অটো)", "দিনাজপুর"),
    ]
    selection = select_validation_sample(candidates, target_n=3)
    assert [item.candidate.public_id for item in selection] == [1, 2, 3]
    summary = summarize_selection(selection)
    assert sum(summary["sector_family"].values()) == 3
