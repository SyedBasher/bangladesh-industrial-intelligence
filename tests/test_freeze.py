import pytest

from bii.freeze import (
    ValidationFreezeError,
    build_validation_freeze_plan,
)
from bii.sampling import ValidationCandidate


def test_joint_freeze_satisfies_sector_and_geography_targets():
    candidates = [
        ValidationCandidate(1, "গার্মেন্টস/তৈরি পোশাক (নীট)", "গাজীপুর"),
        ValidationCandidate(2, "গার্মেন্টস/তৈরি পোশাক (নীট)", "দিনাজপুর"),
        ValidationCandidate(3, "ফার্মাসিউটিক্যালস (এ্যালোপ্যাথিক)", "ঢাকা"),
        ValidationCandidate(4, "ফার্মাসিউটিক্যালস (এ্যালোপ্যাথিক)", "দিনাজপুর"),
    ]
    plan = build_validation_freeze_plan(
        candidates,
        sector_targets={"RMG_TEXTILE": 1, "PHARMA_CHEM_PLASTIC": 1},
        geography_targets={"CORE_DHAKA": 1, "NORTHWEST": 1},
    )
    assert len(plan.selections) == 2
    assert plan.diagnostics.jointly_feasible is True
    assert sum(plan.cell_allocation.values()) == 2

    sectors = [item.candidate.sector_family for item in plan.selections]
    geographies = [item.candidate.geography_group for item in plan.selections]
    assert sectors.count("RMG_TEXTILE") == 1
    assert sectors.count("PHARMA_CHEM_PLASTIC") == 1
    assert geographies.count("CORE_DHAKA") == 1
    assert geographies.count("NORTHWEST") == 1


def test_joint_freeze_detects_cross_cell_bottleneck_even_when_margins_look_sufficient():
    candidates = [
        ValidationCandidate(1, "গার্মেন্টস/তৈরি পোশাক (নীট)", "গাজীপুর"),
        ValidationCandidate(2, "গার্মেন্টস/তৈরি পোশাক (নীট)", "গাজীপুর"),
        ValidationCandidate(3, "ফার্মাসিউটিক্যালস (এ্যালোপ্যাথিক)", "দিনাজপুর"),
        ValidationCandidate(4, "ফার্মাসিউটিক্যালস (এ্যালোপ্যাথিক)", "দিনাজপুর"),
    ]
    with pytest.raises(ValidationFreezeError) as exc:
        build_validation_freeze_plan(
            candidates,
            sector_targets={"RMG_TEXTILE": 1, "PHARMA_CHEM_PLASTIC": 1},
            geography_targets={"CORE_DHAKA": 2, "NORTHWEST": 0},
        )
    diagnostics = exc.value.diagnostics
    assert diagnostics.sector_deficits == {}
    assert diagnostics.geography_deficits == {}
    assert diagnostics.jointly_feasible is False
    assert diagnostics.flow_gap == 1


def test_joint_freeze_refuses_insufficient_candidate_pool():
    candidates = [ValidationCandidate(1, "গার্মেন্টস/তৈরি পোশাক (নীট)", "গাজীপুর")]
    with pytest.raises(ValidationFreezeError) as exc:
        build_validation_freeze_plan(
            candidates,
            sector_targets={"RMG_TEXTILE": 2},
            geography_targets={"CORE_DHAKA": 2},
        )
    assert exc.value.diagnostics.flow_gap == 1
    assert exc.value.diagnostics.sector_deficits == {"RMG_TEXTILE": 1}
    assert exc.value.diagnostics.geography_deficits == {"CORE_DHAKA": 1}


def test_target_totals_must_match():
    with pytest.raises(ValueError):
        build_validation_freeze_plan(
            [],
            sector_targets={"RMG_TEXTILE": 2},
            geography_targets={"CORE_DHAKA": 1},
        )
