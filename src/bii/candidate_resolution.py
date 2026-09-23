from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from collections import defaultdict
from typing import Iterable

from .enrichment import (
    DifeMatchRecord,
    ExternalLinkDecision,
    address_result,
    decide_external_link,
    geography_result,
    name_strength,
)
from .external_sources import ExternalRecordPayload, is_sector_eligible
from .matching import MatchType, normalize_company_core, normalize_text


class CandidatePriority(StrEnum):
    EXACT_NAME_SITE = "P1_EXACT_NAME_SITE"
    EXACT_NAME = "P2_EXACT_NAME"
    STRONG_NAME_SITE = "P3_STRONG_NAME_SITE"
    STRONG_NAME = "P4_STRONG_NAME"
    WEAK_NAME_SITE = "P5_WEAK_NAME_SITE"


class ResolutionOutcome(StrEnum):
    AUTO_SELECTED = "AUTO_SELECTED"
    AMBIGUOUS = "AMBIGUOUS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NO_STAGED_CANDIDATE = "NO_STAGED_CANDIDATE"


@dataclass(frozen=True)
class CandidateSignals:
    external_record_id: int
    source_name: str
    external_key: str
    entity_name: str
    priority: CandidatePriority
    name_strength: str
    name_token_overlap: float | None
    district_result: str
    upazila_result: str
    address_result: str
    address_overlap: float | None


@dataclass(frozen=True)
class CandidateRecord:
    external_record_id: int
    payload: ExternalRecordPayload


@dataclass(frozen=True)
class ResolutionDecision:
    outcome: ResolutionOutcome
    candidate_count: int
    selected_external_record_id: int | None
    selected_match_type: MatchType | None
    note: str
    decisions: tuple[tuple[int, ExternalLinkDecision], ...]


def _tokens(value: str | None) -> set[str]:
    return {
        token
        for token in normalize_text(value).split()
        if len(token) > 1
    }


def name_token_overlap(left: str | None, right: str | None) -> float | None:
    a = _tokens(normalize_company_core(left))
    b = _tokens(normalize_company_core(right))
    if not a or not b:
        return None
    return len(a & b) / len(a | b)




@dataclass
class CandidateBlockIndex:
    """In-memory blocking index for staged external records.

    Blocking is retrieval only, not a match decision. A record enters the candidate
    pool when it shares an exact normalized company core or at least one informative
    normalized company-name token with the DIFE establishment.
    """

    records_by_id: dict[int, CandidateRecord]
    exact_core: dict[str, set[int]]
    token_index: dict[str, set[int]]

    @classmethod
    def build(cls, records: Iterable[CandidateRecord]) -> "CandidateBlockIndex":
        records_by_id: dict[int, CandidateRecord] = {}
        exact_core: dict[str, set[int]] = defaultdict(set)
        token_index: dict[str, set[int]] = defaultdict(set)

        for record in records:
            records_by_id[record.external_record_id] = record
            core = normalize_company_core(record.payload.entity_name)
            if core:
                exact_core[core].add(record.external_record_id)
                for token in _tokens(core):
                    token_index[token].add(record.external_record_id)

        return cls(
            records_by_id=records_by_id,
            exact_core=dict(exact_core),
            token_index=dict(token_index),
        )

    def records_for(self, dife: DifeMatchRecord) -> list[CandidateRecord]:
        core = normalize_company_core(dife.name)
        if not core:
            return []

        candidate_ids = set(self.exact_core.get(core, set()))
        for token in _tokens(core):
            candidate_ids.update(self.token_index.get(token, set()))

        return [
            self.records_by_id[record_id]
            for record_id in sorted(candidate_ids)
        ]

def candidate_priority(
    dife: DifeMatchRecord,
    external: ExternalRecordPayload,
) -> tuple[CandidatePriority | None, CandidateSignals]:
    """Assign a transparent shortlist priority, not a final match score."""
    nstrength = name_strength(dife.name, external.entity_name)
    noverlap = name_token_overlap(dife.name, external.entity_name)
    district = geography_result(dife.district, external.district)
    upazila = geography_result(dife.upazila, external.upazila)
    aresult, aoverlap = address_result(dife.address, external.site_text)

    site_support = (
        district == "match"
        or upazila == "match"
        or aresult in {"strong", "consistent"}
    )
    strong_site_support = (
        (district == "match" and upazila == "match")
        or aresult == "strong"
    )

    priority: CandidatePriority | None = None
    if nstrength == "exact" and site_support:
        priority = CandidatePriority.EXACT_NAME_SITE
    elif nstrength == "exact":
        priority = CandidatePriority.EXACT_NAME
    elif nstrength == "strong" and site_support:
        priority = CandidatePriority.STRONG_NAME_SITE
    elif nstrength == "strong":
        priority = CandidatePriority.STRONG_NAME
    elif nstrength == "weak" and strong_site_support and (noverlap or 0.0) >= 0.40:
        priority = CandidatePriority.WEAK_NAME_SITE

    signals = CandidateSignals(
        external_record_id=-1,
        source_name=external.source_name,
        external_key=external.external_key,
        entity_name=external.entity_name,
        priority=priority or CandidatePriority.WEAK_NAME_SITE,
        name_strength=nstrength,
        name_token_overlap=noverlap,
        district_result=district,
        upazila_result=upazila,
        address_result=aresult,
        address_overlap=aoverlap,
    )
    return priority, signals


def shortlist_candidates(
    dife: DifeMatchRecord,
    records: Iterable[CandidateRecord],
    *,
    max_candidates: int = 5,
) -> list[CandidateSignals]:
    """Create a deterministic, evidence-labelled candidate shortlist.

    Records outside the source's sector scope are ignored. Weak-name records are only
    shortlisted when there is strong site evidence. No absence-based negative claim
    is created when the shortlist is empty.
    """
    if max_candidates <= 0:
        raise ValueError("max_candidates must be positive")

    candidates: list[CandidateSignals] = []
    priority_order = {
        CandidatePriority.EXACT_NAME_SITE: 1,
        CandidatePriority.EXACT_NAME: 2,
        CandidatePriority.STRONG_NAME_SITE: 3,
        CandidatePriority.STRONG_NAME: 4,
        CandidatePriority.WEAK_NAME_SITE: 5,
    }

    for record in records:
        external = record.payload
        if not is_sector_eligible(external.source_name, dife.sector_family):
            continue
        priority, signals = candidate_priority(dife, external)
        if priority is None:
            continue
        candidates.append(
            CandidateSignals(
                external_record_id=record.external_record_id,
                source_name=signals.source_name,
                external_key=signals.external_key,
                entity_name=signals.entity_name,
                priority=priority,
                name_strength=signals.name_strength,
                name_token_overlap=signals.name_token_overlap,
                district_result=signals.district_result,
                upazila_result=signals.upazila_result,
                address_result=signals.address_result,
                address_overlap=signals.address_overlap,
            )
        )

    candidates.sort(
        key=lambda item: (
            priority_order[item.priority],
            -(item.name_token_overlap or 0.0),
            item.external_key,
            item.external_record_id,
        )
    )
    return candidates[:max_candidates]


def resolve_shortlist(
    dife: DifeMatchRecord,
    candidates: Iterable[CandidateRecord],
) -> ResolutionDecision:
    """Resolve an already-shortlisted set without forcing a best guess.

    Rules:
    - one unique site-level positive -> auto-select;
    - more than one site-level positive -> ambiguous;
    - no site-level positive but one unique organization-level positive -> auto-select;
    - multiple organization-level positives -> ambiguous;
    - candidates with no positive rule-based decision -> manual review;
    - an empty staged shortlist means only that no candidate exists in the staged data.
    """
    records = list(candidates)
    if not records:
        return ResolutionDecision(
            outcome=ResolutionOutcome.NO_STAGED_CANDIDATE,
            candidate_count=0,
            selected_external_record_id=None,
            selected_match_type=None,
            note="No candidate was found in the currently staged external records; no negative business fact is inferred.",
            decisions=(),
        )

    evaluated: list[tuple[int, ExternalLinkDecision]] = [
        (
            record.external_record_id,
            decide_external_link(dife, record.payload, multiple_candidates=False),
        )
        for record in records
    ]
    site_positive = [
        item for item in evaluated
        if item[1].match_type in {MatchType.EXACT_SITE, MatchType.PROBABLE_SITE}
    ]
    organization_positive = [
        item for item in evaluated
        if item[1].match_type == MatchType.ORGANIZATION_ONLY
    ]

    if len(site_positive) == 1:
        record_id, decision = site_positive[0]
        return ResolutionDecision(
            outcome=ResolutionOutcome.AUTO_SELECTED,
            candidate_count=len(records),
            selected_external_record_id=record_id,
            selected_match_type=decision.match_type,
            note="Exactly one candidate satisfies the rule-based site-level match requirements.",
            decisions=tuple(evaluated),
        )

    if len(site_positive) > 1:
        return ResolutionDecision(
            outcome=ResolutionOutcome.AMBIGUOUS,
            candidate_count=len(records),
            selected_external_record_id=None,
            selected_match_type=None,
            note="More than one candidate satisfies site-level match requirements; manual disambiguation is required.",
            decisions=tuple(evaluated),
        )

    if len(organization_positive) == 1:
        record_id, decision = organization_positive[0]
        return ResolutionDecision(
            outcome=ResolutionOutcome.AUTO_SELECTED,
            candidate_count=len(records),
            selected_external_record_id=record_id,
            selected_match_type=decision.match_type,
            note="Exactly one candidate satisfies organization-level match requirements and no site-level candidate exists.",
            decisions=tuple(evaluated),
        )

    if len(organization_positive) > 1:
        return ResolutionDecision(
            outcome=ResolutionOutcome.AMBIGUOUS,
            candidate_count=len(records),
            selected_external_record_id=None,
            selected_match_type=None,
            note="More than one organization-level candidate remains plausible.",
            decisions=tuple(evaluated),
        )

    return ResolutionDecision(
        outcome=ResolutionOutcome.REVIEW_REQUIRED,
        candidate_count=len(records),
        selected_external_record_id=None,
        selected_match_type=None,
        note="Candidates exist, but none satisfies the automatic rule-based positive-link requirements.",
        decisions=tuple(evaluated),
    )
