from collections import Counter

import pytest

from bii.detail_validation import (
    CheckpointPolicy,
    DetailCheckpointMetrics,
    FrozenValidationRecord,
    assess_detail_record,
    composition_counts,
    evaluate_checkpoint,
    plan_progressive_detail_batches,
)
from bii.parsers import DifeDetailRecord


def _detail(**overrides):
    values = dict(
        name_en="Example Factory Ltd.",
        name_bn=None,
        address="Industrial Area",
        upazila="Gazipur Sadar",
        district="Gazipur",
        division="Dhaka",
        status="Registered",
        licence_expiry_raw="2027-12-31",
        sector="Knit garments",
        licence_no="L-1",
        old_licence_no=None,
        registration_no="R-1",
        old_registration_no=None,
        licence_class="A",
        establishment_type="Factory",
        worker_component_1=10,
        worker_component_2=5,
        worker_total=15,
    )
    values.update(overrides)
    return DifeDetailRecord(**values)


def test_progressive_batches_are_nested_and_composition_aware():
    records = [
        FrozenValidationRecord(i, "A", "X") for i in range(1, 61)
    ] + [
        FrozenValidationRecord(i, "B", "Y") for i in range(61, 101)
    ]
    assignments = plan_progressive_detail_batches(
        records,
        validation_label="demo",
        checkpoints=(10, 50, 100),
    )
    assert len(assignments) == 100
    assert [a.first_checkpoint for a in assignments].count(10) == 10
    assert [a.first_checkpoint for a in assignments].count(50) == 40
    assert [a.first_checkpoint for a in assignments].count(100) == 50

    counts = composition_counts(assignments, checkpoint_n=10)["sector_family"]
    assert counts == Counter({"A": 6, "B": 4})


def test_progressive_batches_refuse_sample_smaller_than_final_checkpoint():
    with pytest.raises(ValueError):
        plan_progressive_detail_batches(
            [FrozenValidationRecord(1, "A", "X")],
            validation_label="demo",
            checkpoints=(1, 2),
        )


def test_detail_assessment_separates_parser_validity_from_core_completeness():
    valid = assess_detail_record(_detail())
    assert valid.parser_valid is True
    assert valid.core_complete is True
    assert valid.employment_present is True

    partial = assess_detail_record(
        _detail(
            district=None,
            establishment_type=None,
            licence_no=None,
            registration_no=None,
        )
    )
    assert partial.parser_valid is True
    assert partial.core_complete is False

    invalid = assess_detail_record(
        _detail(
            name_en=None,
            name_bn=None,
            address=None,
            upazila=None,
            district=None,
            status=None,
            sector=None,
            licence_no=None,
            registration_no=None,
            licence_class=None,
            establishment_type=None,
            worker_total=None,
        )
    )
    assert invalid.parser_valid is False


def test_checkpoint_gate_requires_resolution_and_qc_thresholds():
    metrics = DetailCheckpointMetrics(
        checkpoint_n=100,
        planned=100,
        resolved=100,
        parsed=97,
        failed=3,
        skipped=0,
        retrieval_success_rate=0.97,
        parser_valid_rate=0.97,
        provenance_complete_rate=1.0,
        url_id_integrity_rate=1.0,
        core_complete_rate=0.88,
        employment_coverage_rate=0.70,
        expiry_coverage_rate=0.80,
        licence_coverage_rate=0.90,
        registration_coverage_rate=0.90,
        district_coverage_rate=0.95,
        sector_coverage_rate=0.98,
        status_coverage_rate=0.98,
        establishment_type_coverage_rate=0.90,
    )
    assert evaluate_checkpoint(metrics).passed is True

    failed = DetailCheckpointMetrics(
        **{
            **metrics.__dict__,
            "resolved": 99,
            "retrieval_success_rate": 0.94,
        }
    )
    decision = evaluate_checkpoint(failed)
    assert decision.passed is False
    assert any("unresolved" in reason for reason in decision.reasons)
    assert any("retrieval success" in reason for reason in decision.reasons)


def test_checkpoint_policy_is_configurable():
    metrics = DetailCheckpointMetrics(
        checkpoint_n=2,
        planned=2,
        resolved=2,
        parsed=1,
        failed=1,
        skipped=0,
        retrieval_success_rate=0.5,
        parser_valid_rate=1.0,
        provenance_complete_rate=1.0,
        url_id_integrity_rate=1.0,
        core_complete_rate=1.0,
        employment_coverage_rate=1.0,
        expiry_coverage_rate=1.0,
        licence_coverage_rate=1.0,
        registration_coverage_rate=1.0,
        district_coverage_rate=1.0,
        sector_coverage_rate=1.0,
        status_coverage_rate=1.0,
        establishment_type_coverage_rate=1.0,
    )
    policy = CheckpointPolicy(min_retrieval_success_rate=0.5)
    assert evaluate_checkpoint(metrics, policy).passed is True
