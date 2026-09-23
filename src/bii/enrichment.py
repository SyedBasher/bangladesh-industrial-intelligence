from __future__ import annotations

import re
from dataclasses import dataclass

from .external_sources import ExternalRecordPayload, is_sector_eligible, source_spec
from .matching import MatchEvidence, MatchType, classify_match, normalize_company_core, normalize_text


@dataclass(frozen=True)
class DifeMatchRecord:
    public_id: int
    name: str | None
    address: str | None
    district: str | None
    upazila: str | None
    sector_family: str


@dataclass(frozen=True)
class MatchComponent:
    evidence_type: str
    dife_value: str | None
    external_value: str | None
    result: str
    note: str | None = None


@dataclass(frozen=True)
class ExternalLinkDecision:
    public_id: int
    source_name: str
    external_key: str
    match_type: MatchType
    site_level_match: bool
    evidence: tuple[MatchComponent, ...]


def _tokens(value: str | None) -> set[str]:
    return {token for token in normalize_text(value).split() if len(token) > 1}


def _token_jaccard(left: str | None, right: str | None) -> float | None:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def name_strength(dife_name: str | None, external_name: str | None) -> str:
    left = normalize_company_core(dife_name)
    right = normalize_company_core(external_name)
    if not left or not right:
        return "missing"
    if left == right:
        return "exact"
    if left in right or right in left:
        shorter = min(len(left), len(right))
        longer = max(len(left), len(right))
        if shorter >= 5 and shorter / longer >= 0.70:
            return "strong"
    overlap = _token_jaccard(left, right)
    if overlap is not None and overlap >= 0.75:
        return "strong"
    if overlap is not None and overlap >= 0.40:
        return "weak"
    return "weak"


def geography_result(dife_value: str | None, external_value: str | None) -> str:
    left = normalize_text(dife_value)
    right = normalize_text(external_value)
    if not left or not right:
        return "missing"
    return "match" if left == right else "conflict"


def address_result(dife_address: str | None, external_address: str | None) -> tuple[str, float | None]:
    overlap = _token_jaccard(dife_address, external_address)
    if overlap is None:
        return "missing", None
    if overlap >= 0.50:
        return "strong", overlap
    if overlap >= 0.20:
        return "consistent", overlap
    if overlap < 0.05:
        return "conflict", overlap
    return "consistent", overlap


def decide_external_link(
    dife: DifeMatchRecord,
    external: ExternalRecordPayload,
    *,
    multiple_candidates: bool = False,
) -> ExternalLinkDecision:
    if not is_sector_eligible(external.source_name, dife.sector_family):
        return ExternalLinkDecision(
            public_id=dife.public_id,
            source_name=external.source_name,
            external_key=external.external_key,
            match_type=MatchType.NO_MATCH,
            site_level_match=False,
            evidence=(
                MatchComponent(
                    "SOURCE_ELIGIBILITY",
                    dife.sector_family,
                    external.source_name,
                    "OUT_OF_SCOPE",
                    "The source is not targeted to this validation sector family.",
                ),
            ),
        )

    nstrength = name_strength(dife.name, external.entity_name)
    district = geography_result(dife.district, external.district)
    upazila = geography_result(dife.upazila, external.upazila)
    address, address_overlap = address_result(dife.address, external.site_text)

    match_type = classify_match(
        MatchEvidence(
            name_strength=nstrength,
            district=district,
            upazila=upazila,
            address=address,
            multiple_candidates=multiple_candidates,
        )
    )

    spec = source_spec(external.source_name)
    if (
        spec.default_linkage == "ORGANIZATION"
        and match_type in {MatchType.EXACT_SITE, MatchType.PROBABLE_SITE}
    ):
        match_type = MatchType.ORGANIZATION_ONLY

    site_level = match_type in {MatchType.EXACT_SITE, MatchType.PROBABLE_SITE}
    overlap_note = None if address_overlap is None else f"token_jaccard={address_overlap:.3f}"

    evidence = (
        MatchComponent("NAME", dife.name, external.entity_name, nstrength),
        MatchComponent("DISTRICT", dife.district, external.district, district),
        MatchComponent("UPAZILA", dife.upazila, external.upazila, upazila),
        MatchComponent("ADDRESS", dife.address, external.site_text, address, overlap_note),
        MatchComponent(
            "SOURCE_LINKAGE_SCOPE",
            dife.sector_family,
            spec.default_linkage,
            "SITE_ALLOWED" if spec.default_linkage != "ORGANIZATION" else "ORGANIZATION_CAP",
        ),
    )
    return ExternalLinkDecision(
        public_id=dife.public_id,
        source_name=external.source_name,
        external_key=external.external_key,
        match_type=match_type,
        site_level_match=site_level,
        evidence=evidence,
    )


@dataclass(frozen=True)
class EnrichmentCoverage:
    source_name: str
    eligible: int
    staged_records: int
    exact_site: int
    probable_site: int
    organization_only: int
    ambiguous: int
    no_match: int
    feasibility_only: int

    @property
    def site_match_rate(self) -> float:
        return (self.exact_site + self.probable_site) / self.eligible if self.eligible else 0.0

    @property
    def any_positive_link_rate(self) -> float:
        return (
            self.exact_site + self.probable_site + self.organization_only
        ) / self.eligible if self.eligible else 0.0
