from bii.validation_reporting import (
    DetailComparisonRecord,
    Severity,
    build_validation_report,
    detect_detail_anomalies,
)


def _record(**overrides):
    values = dict(
        public_id=1,
        sequence_no=1,
        sector_family="RMG_TEXTILE",
        geography_group="CORE_DHAKA",
        request_status="PARSED",
        parser_valid=True,
        core_complete=True,
        list_name="Example Factory Ltd.",
        list_sector="Knit garments",
        list_district="Gazipur",
        list_status="Registered",
        list_class="A",
        detail_name_en="Example Factory Ltd.",
        detail_name_bn=None,
        detail_sector="Knit garments",
        detail_district="Gazipur",
        detail_status="Registered",
        detail_class="A",
        establishment_type="Factory",
        licence_no="L1",
        registration_no="R1",
        worker_total=10,
        licence_expiry_raw="2027-12-31",
    )
    values.update(overrides)
    return DetailComparisonRecord(**values)


def test_exact_list_detail_record_has_no_anomaly():
    assert detect_detail_anomalies([_record()]) == []


def test_source_contradictions_are_flagged_not_overwritten():
    anomalies = detect_detail_anomalies(
        [
            _record(
                detail_district="Dhaka",
                detail_status="Cancelled",
                detail_sector="Food",
                detail_class="B",
            )
        ]
    )
    types = {item.anomaly_type for item in anomalies}
    assert {"DISTRICT_MISMATCH", "STATUS_MISMATCH", "SECTOR_MISMATCH", "CLASS_MISMATCH"} <= types
    assert any(
        item.anomaly_type == "STATUS_MISMATCH" and item.severity == Severity.HIGH
        for item in anomalies
    )


def test_missing_value_does_not_create_false_mismatch():
    anomalies = detect_detail_anomalies(
        [_record(detail_district=None, detail_class=None)]
    )
    assert not any(item.anomaly_type == "DISTRICT_MISMATCH" for item in anomalies)
    assert not any(item.anomaly_type == "CLASS_MISMATCH" for item in anomalies)


def test_failed_and_unresolved_requests_are_critical():
    anomalies = detect_detail_anomalies(
        [
            _record(public_id=1, request_status="FAILED"),
            _record(public_id=2, sequence_no=2, request_status="PLANNED"),
        ]
    )
    assert {item.anomaly_type for item in anomalies} == {
        "RETRIEVAL_FAILURE",
        "UNRESOLVED_REQUEST",
    }
    assert all(item.severity == Severity.CRITICAL for item in anomalies)


def test_report_breaks_down_sector_geography_and_anomalies():
    report, anomalies = build_validation_report(
        [
            _record(public_id=1),
            _record(
                public_id=2,
                sequence_no=2,
                sector_family="FOOD_AGRO",
                geography_group="NORTHWEST",
                detail_status="Cancelled",
            ),
        ],
        validation_label="demo",
        checkpoint_n=2,
        generated_at="2026-09-23T22:30:00+06:00",
    )
    assert report.total_records == 2
    assert report.anomalies_total == 1
    assert report.anomaly_counts["STATUS_MISMATCH"] == 1
    assert len(report.sector_breakdown) == 2
    assert len(report.geography_breakdown) == 2
    assert len(anomalies) == 1
