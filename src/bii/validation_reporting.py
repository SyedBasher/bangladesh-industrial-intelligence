from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable


class Severity:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    INFO = "INFO"


@dataclass(frozen=True)
class DetailComparisonRecord:
    public_id: int
    sequence_no: int
    sector_family: str
    geography_group: str
    request_status: str
    parser_valid: bool | None
    core_complete: bool | None
    list_name: str | None
    list_sector: str | None
    list_district: str | None
    list_status: str | None
    list_class: str | None
    detail_name_en: str | None
    detail_name_bn: str | None
    detail_sector: str | None
    detail_district: str | None
    detail_status: str | None
    detail_class: str | None
    establishment_type: str | None
    licence_no: str | None
    registration_no: str | None
    worker_total: int | None
    licence_expiry_raw: str | None


@dataclass(frozen=True)
class ValidationAnomaly:
    public_id: int
    sequence_no: int
    anomaly_type: str
    severity: str
    list_value: str | None
    detail_value: str | None
    note: str


def _norm(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _same(left: str | None, right: str | None) -> bool:
    return bool(_norm(left)) and _norm(left) == _norm(right)


def detect_detail_anomalies(
    records: Iterable[DetailComparisonRecord],
) -> list[ValidationAnomaly]:
    anomalies: list[ValidationAnomaly] = []

    for record in records:
        if record.request_status == "FAILED":
            anomalies.append(
                ValidationAnomaly(
                    record.public_id,
                    record.sequence_no,
                    "RETRIEVAL_FAILURE",
                    Severity.CRITICAL,
                    None,
                    None,
                    "The planned DIFE detail request failed.",
                )
            )
            continue

        if record.request_status != "PARSED":
            anomalies.append(
                ValidationAnomaly(
                    record.public_id,
                    record.sequence_no,
                    "UNRESOLVED_REQUEST",
                    Severity.CRITICAL,
                    None,
                    None,
                    f"Detail request remains {record.request_status}.",
                )
            )
            continue

        if record.parser_valid is False:
            anomalies.append(
                ValidationAnomaly(
                    record.public_id,
                    record.sequence_no,
                    "PARSER_INVALID",
                    Severity.CRITICAL,
                    None,
                    None,
                    "Retrieved HTML did not expose enough expected DIFE detail anchors.",
                )
            )

        comparisons = (
            (
                "DISTRICT_MISMATCH",
                Severity.HIGH,
                record.list_district,
                record.detail_district,
                "List-page and detail-page district values conflict.",
            ),
            (
                "STATUS_MISMATCH",
                Severity.HIGH,
                record.list_status,
                record.detail_status,
                "List-page and detail-page DIFE status values conflict.",
            ),
            (
                "SECTOR_MISMATCH",
                Severity.HIGH,
                record.list_sector,
                record.detail_sector,
                "List-page and detail-page industrial-sector values conflict.",
            ),
            (
                "CLASS_MISMATCH",
                Severity.MEDIUM,
                record.list_class,
                record.detail_class,
                "List-page and detail-page class values conflict.",
            ),
        )
        for anomaly_type, severity, left, right, note in comparisons:
            if left and right and not _same(left, right):
                anomalies.append(
                    ValidationAnomaly(
                        record.public_id,
                        record.sequence_no,
                        anomaly_type,
                        severity,
                        left,
                        right,
                        note,
                    )
                )

        detail_name = record.detail_name_en or record.detail_name_bn
        if record.list_name and detail_name and not _same(record.list_name, detail_name):
            anomalies.append(
                ValidationAnomaly(
                    record.public_id,
                    record.sequence_no,
                    "NAME_VARIATION",
                    Severity.INFO,
                    record.list_name,
                    detail_name,
                    "Normalized list/detail establishment names differ; review before treating as identity conflict.",
                )
            )

        if record.core_complete is False:
            anomalies.append(
                ValidationAnomaly(
                    record.public_id,
                    record.sequence_no,
                    "CORE_FIELDS_INCOMPLETE",
                    Severity.MEDIUM,
                    None,
                    None,
                    "Detail page parsed but does not contain all validation core fields.",
                )
            )

    return anomalies


@dataclass(frozen=True)
class BreakdownRow:
    group: str
    total: int
    parsed: int
    parser_valid: int
    core_complete: int
    failed: int


@dataclass(frozen=True)
class ValidationReport:
    validation_label: str
    checkpoint_n: int
    generated_at: str
    total_records: int
    anomalies_total: int
    anomaly_counts: dict[str, int]
    severity_counts: dict[str, int]
    sector_breakdown: tuple[BreakdownRow, ...]
    geography_breakdown: tuple[BreakdownRow, ...]


def _breakdown(
    records: list[DetailComparisonRecord],
    attribute: str,
) -> tuple[BreakdownRow, ...]:
    groups: dict[str, list[DetailComparisonRecord]] = {}
    for record in records:
        value = str(getattr(record, attribute) or "UNKNOWN")
        groups.setdefault(value, []).append(record)

    rows: list[BreakdownRow] = []
    for group, members in sorted(groups.items()):
        rows.append(
            BreakdownRow(
                group=group,
                total=len(members),
                parsed=sum(item.request_status == "PARSED" for item in members),
                parser_valid=sum(item.parser_valid is True for item in members),
                core_complete=sum(item.core_complete is True for item in members),
                failed=sum(item.request_status == "FAILED" for item in members),
            )
        )
    return tuple(rows)


def build_validation_report(
    records: Iterable[DetailComparisonRecord],
    *,
    validation_label: str,
    checkpoint_n: int,
    generated_at: str,
) -> tuple[ValidationReport, list[ValidationAnomaly]]:
    rows = list(records)
    anomalies = detect_detail_anomalies(rows)
    anomaly_counts = Counter(item.anomaly_type for item in anomalies)
    severity_counts = Counter(item.severity for item in anomalies)

    report = ValidationReport(
        validation_label=validation_label,
        checkpoint_n=checkpoint_n,
        generated_at=generated_at,
        total_records=len(rows),
        anomalies_total=len(anomalies),
        anomaly_counts=dict(anomaly_counts),
        severity_counts=dict(severity_counts),
        sector_breakdown=_breakdown(rows, "sector_family"),
        geography_breakdown=_breakdown(rows, "geography_group"),
    )
    return report, anomalies


def report_as_dict(report: ValidationReport) -> dict[str, object]:
    return asdict(report)
