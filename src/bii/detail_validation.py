from __future__ import annotations

import hashlib
import heapq
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

from .parsers import DifeDetailRecord


DETAIL_CHECKPOINTS = (100, 500, 2000)


@dataclass(frozen=True)
class FrozenValidationRecord:
    public_id: int
    sector_family: str
    geography_group: str


@dataclass(frozen=True)
class DetailBatchAssignment:
    public_id: int
    sector_family: str
    geography_group: str
    sequence_no: int
    first_checkpoint: int


def _stable_member_key(validation_label: str, public_id: int) -> str:
    return hashlib.sha256(f"{validation_label}:{public_id}".encode("utf-8")).hexdigest()


def plan_progressive_detail_batches(
    records: Iterable[FrozenValidationRecord],
    *,
    validation_label: str,
    checkpoints: tuple[int, ...] = DETAIL_CHECKPOINTS,
) -> list[DetailBatchAssignment]:
    """Build deterministic nested checkpoint batches from a frozen sample.

    Candidates are grouped by sector×geography cell. A weighted fair sequence then
    interleaves those cells in proportion to their final frozen-sample size. Inside
    each cell, member order is a stable SHA-256 order rather than DIFE ID order.

    Therefore:
    - checkpoint 100 is a composition-aware prefix;
    - checkpoint 500 strictly contains checkpoint 100;
    - checkpoint 2000 strictly contains checkpoint 500.
    """
    checkpoints = tuple(sorted(set(int(value) for value in checkpoints)))
    if not checkpoints or checkpoints[0] <= 0:
        raise ValueError("checkpoints must contain positive integers")

    unique = {
        int(record.public_id): FrozenValidationRecord(
            int(record.public_id),
            record.sector_family,
            record.geography_group,
        )
        for record in records
    }
    members = list(unique.values())
    if len(members) < checkpoints[-1]:
        raise ValueError(
            f"frozen sample has {len(members)} rows but final checkpoint requires {checkpoints[-1]}"
        )

    groups: dict[tuple[str, str], list[FrozenValidationRecord]] = defaultdict(list)
    for record in members:
        groups[(record.sector_family, record.geography_group)].append(record)

    for cell in groups:
        groups[cell].sort(
            key=lambda record: (_stable_member_key(validation_label, record.public_id), record.public_id)
        )

    # Heap priority = the next fractional position within the cell. Using Fraction
    # avoids floating-point tie noise and produces a deterministic weighted sequence.
    heap: list[tuple[Fraction, str, str, int]] = []
    for (sector, geography), cell_members in sorted(groups.items()):
        heapq.heappush(
            heap,
            (Fraction(1, 2 * len(cell_members)), sector, geography, 0),
        )

    ordered: list[FrozenValidationRecord] = []
    while heap and len(ordered) < checkpoints[-1]:
        _, sector, geography, index = heapq.heappop(heap)
        cell_members = groups[(sector, geography)]
        ordered.append(cell_members[index])
        next_index = index + 1
        if next_index < len(cell_members):
            # (k + 1/2) / N where k is zero-based next index.
            priority = Fraction(2 * next_index + 1, 2 * len(cell_members))
            heapq.heappush(heap, (priority, sector, geography, next_index))

    if len(ordered) < checkpoints[-1]:
        raise RuntimeError("could not construct the requested progressive detail sequence")

    assignments: list[DetailBatchAssignment] = []
    for sequence_no, record in enumerate(ordered, start=1):
        first_checkpoint = next(checkpoint for checkpoint in checkpoints if sequence_no <= checkpoint)
        assignments.append(
            DetailBatchAssignment(
                public_id=record.public_id,
                sector_family=record.sector_family,
                geography_group=record.geography_group,
                sequence_no=sequence_no,
                first_checkpoint=first_checkpoint,
            )
        )
    return assignments


@dataclass(frozen=True)
class DetailParseAssessment:
    parser_valid: bool
    core_complete: bool
    core_present: int
    core_expected: int
    employment_present: bool
    expiry_present: bool


def assess_detail_record(record: DifeDetailRecord) -> DetailParseAssessment:
    """Assess parser integrity separately from source-field completeness.

    Missing source values are allowed. A page is parser-valid if it exposes at least
    two independent anchors from the expected public detail structure. Core-complete
    is a stricter validation metric and is never used to fill source blanks.
    """
    identity_present = bool(record.name_en or record.name_bn)
    regulatory_present = bool(record.licence_no or record.registration_no)
    location_present = bool(record.address or record.district or record.upazila)
    classification_present = bool(record.sector or record.establishment_type or record.licence_class)
    status_present = bool(record.status)

    anchor_count = sum(
        (
            identity_present,
            regulatory_present,
            location_present,
            classification_present,
            status_present,
        )
    )
    parser_valid = anchor_count >= 2

    core_flags = (
        identity_present,
        bool(record.sector),
        bool(record.status),
        bool(record.district),
        bool(record.establishment_type),
        regulatory_present,
    )
    core_present = sum(core_flags)
    core_complete = all(core_flags)

    return DetailParseAssessment(
        parser_valid=parser_valid,
        core_complete=core_complete,
        core_present=core_present,
        core_expected=len(core_flags),
        employment_present=record.worker_total is not None,
        expiry_present=bool(record.licence_expiry_raw),
    )


@dataclass(frozen=True)
class CheckpointPolicy:
    min_retrieval_success_rate: float = 0.95
    min_parser_valid_rate: float = 0.95
    min_provenance_complete_rate: float = 1.00
    min_url_id_integrity_rate: float = 1.00
    min_core_complete_rate: float = 0.85


DEFAULT_CHECKPOINT_POLICY = CheckpointPolicy()


@dataclass(frozen=True)
class DetailCheckpointMetrics:
    checkpoint_n: int
    planned: int
    resolved: int
    parsed: int
    failed: int
    skipped: int
    retrieval_success_rate: float
    parser_valid_rate: float
    provenance_complete_rate: float
    url_id_integrity_rate: float
    core_complete_rate: float
    employment_coverage_rate: float
    expiry_coverage_rate: float
    licence_coverage_rate: float
    registration_coverage_rate: float
    district_coverage_rate: float
    sector_coverage_rate: float
    status_coverage_rate: float
    establishment_type_coverage_rate: float


@dataclass(frozen=True)
class CheckpointDecision:
    passed: bool
    reasons: tuple[str, ...]


def evaluate_checkpoint(
    metrics: DetailCheckpointMetrics,
    policy: CheckpointPolicy = DEFAULT_CHECKPOINT_POLICY,
) -> CheckpointDecision:
    """Apply explicit go/no-go criteria to a completed checkpoint."""
    reasons: list[str] = []

    if metrics.planned != metrics.checkpoint_n:
        reasons.append(
            f"planned records {metrics.planned} != checkpoint size {metrics.checkpoint_n}"
        )
    if metrics.resolved < metrics.planned:
        reasons.append(
            f"checkpoint unresolved: {metrics.resolved}/{metrics.planned} requests resolved"
        )

    checks = (
        (
            "retrieval success",
            metrics.retrieval_success_rate,
            policy.min_retrieval_success_rate,
        ),
        (
            "parser validity",
            metrics.parser_valid_rate,
            policy.min_parser_valid_rate,
        ),
        (
            "provenance completeness",
            metrics.provenance_complete_rate,
            policy.min_provenance_complete_rate,
        ),
        (
            "URL/ID integrity",
            metrics.url_id_integrity_rate,
            policy.min_url_id_integrity_rate,
        ),
        (
            "core completeness",
            metrics.core_complete_rate,
            policy.min_core_complete_rate,
        ),
    )
    for label, value, threshold in checks:
        if value < threshold:
            reasons.append(f"{label} {value:.3f} < required {threshold:.3f}")

    return CheckpointDecision(passed=not reasons, reasons=tuple(reasons))


def composition_counts(
    assignments: Iterable[DetailBatchAssignment],
    *,
    checkpoint_n: int,
) -> dict[str, Counter[str]]:
    selected = [assignment for assignment in assignments if assignment.sequence_no <= checkpoint_n]
    return {
        "sector_family": Counter(assignment.sector_family for assignment in selected),
        "geography_group": Counter(assignment.geography_group for assignment in selected),
    }
