from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from urllib.parse import urlencode

from .parsers import parse_dife_list_page
from .sampling import GEOGRAPHY_FLOORS, SECTOR_TARGETS, ValidationCandidate, classify_sector, spread_pages
from .taxonomy import FilterOption


DIFE_FILTER_URL = "https://lima.dife.gov.bd/public-report/establishment-list-filter"
DEFAULT_CANDIDATE_MULTIPLIER = 1.5
DEFAULT_PAGE_SIZE = 30


@dataclass(frozen=True)
class DiscoveryRequest:
    sector_family: str
    source_sector_value: str
    source_sector_label: str
    page: int
    source_url: str
    reason: str


@dataclass(frozen=True)
class SectorUniverse:
    sector_family: str
    source_sector_value: str
    source_sector_label: str
    total_records: int


def build_filter_url(
    *,
    sector_value: str,
    page: int = 1,
    district_value: str | None = None,
    status_value: str | None = None,
    base_url: str = DIFE_FILTER_URL,
) -> str:
    """Build a public DIFE filter URL without assuming undocumented endpoints."""
    params = {
        "category": "",
        "district": district_value or "",
        "employee_from": "",
        "employee_to": "",
        "factory_name": "",
        "filter": "filter",
        "industry_id": sector_value,
        "license_number": "",
        "page": str(page),
        "registration_number": "",
        "status": status_value or "",
        "upazila": "",
    }
    return f"{base_url}?{urlencode(params)}"


def sector_filter_options(options: list[FilterOption]) -> list[FilterOption]:
    """Return only currently exposed industrial-sector filter options."""
    return sorted(
        (option for option in options if option.dimension == "INDUSTRIAL_SECTOR"),
        key=lambda option: (classify_sector(option.source_label), option.source_label, option.source_value),
    )


def plan_seed_requests(options: list[FilterOption]) -> list[DiscoveryRequest]:
    """Plan exactly one public first-page request for every exposed sector option."""
    requests: list[DiscoveryRequest] = []
    for option in sector_filter_options(options):
        requests.append(
            DiscoveryRequest(
                sector_family=classify_sector(option.source_label),
                source_sector_value=option.source_value,
                source_sector_label=option.source_label,
                page=1,
                source_url=build_filter_url(sector_value=option.source_value, page=1),
                reason="UNIVERSE_SEED",
            )
        )
    return requests


def universe_from_seed_html(request: DiscoveryRequest, html: str) -> SectorUniverse:
    """Extract the current source-reported universe size from a staged seed page."""
    metadata, _ = parse_dife_list_page(html)
    if metadata.total_records is None:
        raise ValueError(
            f"Could not parse a source-reported total for sector {request.source_sector_label!r}"
        )
    return SectorUniverse(
        sector_family=request.sector_family,
        source_sector_value=request.source_sector_value,
        source_sector_label=request.source_sector_label,
        total_records=metadata.total_records,
    )


def _family_target_map(multiplier: float) -> dict[str, int]:
    if multiplier < 1:
        raise ValueError("candidate multiplier must be at least 1.0")
    return {
        code: math.ceil(target * multiplier)
        for code, _, target, _ in SECTOR_TARGETS
    }


def allocate_desired_rows(
    universes: list[SectorUniverse],
    *,
    candidate_multiplier: float = DEFAULT_CANDIDATE_MULTIPLIER,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[tuple[str, str], int]:
    """Allocate a discovery pool across source sector options within each family.

    Allocation is proportional to current source-reported universe size, while
    preserving at least one page for every non-empty source sector. This is a
    validation design, not an estimate of sector population shares.
    """
    family_targets = _family_target_map(candidate_multiplier)
    grouped: dict[str, list[SectorUniverse]] = defaultdict(list)
    for universe in universes:
        if universe.total_records > 0:
            grouped[universe.sector_family].append(universe)

    allocation: dict[tuple[str, str], int] = {}
    for family, members in grouped.items():
        family_total = sum(member.total_records for member in members)
        family_target = family_targets.get(family, page_size)

        raw: list[tuple[SectorUniverse, int]] = []
        for member in members:
            share = family_target * member.total_records / family_total if family_total else 0
            desired = max(page_size, min(member.total_records, math.ceil(share)))
            raw.append((member, desired))

        for member, desired in raw:
            allocation[(member.source_sector_value, member.source_sector_label)] = desired

    return allocation


def plan_spread_requests(
    universes: list[SectorUniverse],
    *,
    candidate_multiplier: float = DEFAULT_CANDIDATE_MULTIPLIER,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[DiscoveryRequest]:
    """Plan deterministic follow-up pages after seed-page universe discovery.

    Page 1 is omitted because it has already been staged as the universe seed.
    """
    allocation = allocate_desired_rows(
        universes,
        candidate_multiplier=candidate_multiplier,
        page_size=page_size,
    )
    requests: list[DiscoveryRequest] = []

    for universe in sorted(
        universes,
        key=lambda item: (item.sector_family, item.source_sector_label, item.source_sector_value),
    ):
        desired_rows = allocation.get(
            (universe.source_sector_value, universe.source_sector_label),
            0,
        )
        pages = spread_pages(universe.total_records, desired_rows, page_size=page_size)
        for page in pages:
            if page == 1:
                continue
            requests.append(
                DiscoveryRequest(
                    sector_family=universe.sector_family,
                    source_sector_value=universe.source_sector_value,
                    source_sector_label=universe.source_sector_label,
                    page=page,
                    source_url=build_filter_url(
                        sector_value=universe.source_sector_value,
                        page=page,
                    ),
                    reason="UNIVERSE_SPREAD",
                )
            )

    return requests


def candidate_pool_health(candidates: list[ValidationCandidate]) -> dict[str, object]:
    """Report whether the staged candidate pool can satisfy validation quotas/floors."""
    unique = list({candidate.public_id: candidate for candidate in candidates}.values())
    sector_counts = Counter(candidate.sector_family for candidate in unique)
    geo_counts = Counter(candidate.geography_group for candidate in unique)

    sector_deficits = {
        code: max(0, target - sector_counts.get(code, 0))
        for code, _, target, _ in SECTOR_TARGETS
        if sector_counts.get(code, 0) < target
    }
    geography_deficits = {
        code: max(0, target - geo_counts.get(code, 0))
        for code, _, target, _ in GEOGRAPHY_FLOORS
        if geo_counts.get(code, 0) < target
    }

    return {
        "unique_candidates": len(unique),
        "sector_counts": dict(sector_counts),
        "geography_counts": dict(geo_counts),
        "sector_deficits": sector_deficits,
        "geography_deficits": geography_deficits,
        "ready_for_2000_freeze": len(unique) >= 2000 and not sector_deficits and not geography_deficits,
    }
