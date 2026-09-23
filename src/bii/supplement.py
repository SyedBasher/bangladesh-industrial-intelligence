from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlencode

from .discovery import DIFE_FILTER_URL, SectorUniverse
from .parsers import parse_dife_list_page
from .sampling import GEOGRAPHY_FLOORS, SECTOR_TARGETS, classify_geography, classify_sector, spread_pages
from .taxonomy import FilterOption


DEFAULT_SUPPLEMENT_MULTIPLIER = 1.25
DEFAULT_PAGE_SIZE = 30


@dataclass(frozen=True)
class SupplementRequest:
    geography_group: str
    source_district_value: str
    source_district_label: str
    sector_family: str
    source_sector_value: str
    source_sector_label: str
    page: int
    source_url: str
    reason: str


@dataclass(frozen=True)
class SupplementUniverse:
    geography_group: str
    source_district_value: str
    source_district_label: str
    sector_family: str
    source_sector_value: str
    source_sector_label: str
    total_records: int


def build_district_sector_url(
    *,
    district_value: str,
    sector_value: str,
    page: int = 1,
    status_value: str | None = None,
    base_url: str = DIFE_FILTER_URL,
) -> str:
    params = {
        "category": "",
        "district": district_value,
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


def district_filter_options(options: list[FilterOption]) -> list[FilterOption]:
    return sorted(
        (option for option in options if option.dimension == "DISTRICT"),
        key=lambda option: (classify_geography(option.source_label), option.source_label, option.source_value),
    )


def sector_filter_options_by_family(options: list[FilterOption]) -> dict[str, list[FilterOption]]:
    grouped: dict[str, list[FilterOption]] = defaultdict(list)
    for option in options:
        if option.dimension != "INDUSTRIAL_SECTOR":
            continue
        grouped[classify_sector(option.source_label)].append(option)
    for family in grouped:
        grouped[family].sort(key=lambda option: (option.source_label, option.source_value))
    return dict(grouped)


def _spread_items(items: list[FilterOption], n: int) -> list[FilterOption]:
    if n <= 0 or not items:
        return []
    if n >= len(items):
        return list(items)
    if n == 1:
        return [items[len(items) // 2]]

    selected: list[FilterOption] = []
    for index in range(n):
        position = round(index * (len(items) - 1) / (n - 1))
        item = items[position]
        if item not in selected:
            selected.append(item)
    return selected


def _rank_sector_options(
    sector_options: dict[str, list[FilterOption]],
    sector_universes: list[SectorUniverse] | None,
    family_priority: list[str],
) -> list[tuple[str, FilterOption]]:
    universe_size = {
        universe.source_sector_value: universe.total_records
        for universe in (sector_universes or [])
    }
    ranked: list[tuple[str, FilterOption]] = []
    for family in family_priority:
        options = list(sector_options.get(family, []))
        options.sort(
            key=lambda option: (
                -universe_size.get(option.source_value, -1),
                option.source_label,
                option.source_value,
            )
        )
        ranked.extend((family, option) for option in options)
    return ranked


def plan_geographic_seed_requests(
    options: list[FilterOption],
    candidate_health: dict[str, object],
    *,
    sector_universes: list[SectorUniverse] | None = None,
    max_districts_per_group: int = 3,
    max_sector_options_per_group: int = 3,
) -> list[SupplementRequest]:
    """Plan a bounded first pass for only geography groups that remain deficient.

    The seed pass learns actual district×sector universe sizes. It deliberately avoids
    a full district×sector Cartesian crawl.
    """
    geography_deficits = dict(candidate_health.get("geography_deficits", {}))
    sector_deficits = dict(candidate_health.get("sector_deficits", {}))
    if not geography_deficits:
        return []

    districts_by_group: dict[str, list[FilterOption]] = defaultdict(list)
    for option in district_filter_options(options):
        districts_by_group[classify_geography(option.source_label)].append(option)

    sector_options = sector_filter_options_by_family(options)
    sector_targets = {code: target for code, _, target, _ in SECTOR_TARGETS}

    deficient_families = sorted(
        sector_deficits,
        key=lambda code: (-sector_deficits[code], -sector_targets.get(code, 0), code),
    )
    fallback_families = sorted(
        sector_targets,
        key=lambda code: (-sector_targets[code], code),
    )
    family_priority = deficient_families + [
        family for family in fallback_families if family not in deficient_families
    ]
    ranked_sector_options = _rank_sector_options(
        sector_options,
        sector_universes,
        family_priority,
    )

    requests: list[SupplementRequest] = []
    seen_urls: set[str] = set()
    for geography_group in sorted(
        geography_deficits,
        key=lambda code: (-geography_deficits[code], code),
    ):
        deficit = int(geography_deficits[geography_group])
        districts = districts_by_group.get(geography_group, [])
        if not districts:
            continue

        # Seed more than one district when the deficit is large, but keep the first
        # pass tightly bounded. Subsequent zero/low-yield results can expand the pass.
        desired_districts = min(
            max_districts_per_group,
            len(districts),
            max(1, math.ceil(deficit / 120)),
        )
        selected_districts = _spread_items(districts, desired_districts)
        selected_sector_options = ranked_sector_options[:max_sector_options_per_group]

        for district in selected_districts:
            for family, sector in selected_sector_options:
                url = build_district_sector_url(
                    district_value=district.source_value,
                    sector_value=sector.source_value,
                    page=1,
                )
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                requests.append(
                    SupplementRequest(
                        geography_group=geography_group,
                        source_district_value=district.source_value,
                        source_district_label=district.source_label,
                        sector_family=family,
                        source_sector_value=sector.source_value,
                        source_sector_label=sector.source_label,
                        page=1,
                        source_url=url,
                        reason="GEOGRAPHY_SEED",
                    )
                )

    return requests


def universe_from_supplement_seed_html(
    request: SupplementRequest,
    html: str,
) -> SupplementUniverse:
    metadata, _ = parse_dife_list_page(html)
    if metadata.total_records is None:
        raise ValueError(
            "Could not parse a source-reported total for "
            f"{request.source_district_label!r} × {request.source_sector_label!r}"
        )
    return SupplementUniverse(
        geography_group=request.geography_group,
        source_district_value=request.source_district_value,
        source_district_label=request.source_district_label,
        sector_family=request.sector_family,
        source_sector_value=request.source_sector_value,
        source_sector_label=request.source_sector_label,
        total_records=metadata.total_records,
    )


def _allocate_group_rows(
    members: list[SupplementUniverse],
    desired_rows: int,
    *,
    page_size: int,
) -> dict[tuple[str, str], int]:
    nonempty = [member for member in members if member.total_records > 0]
    if not nonempty or desired_rows <= 0:
        return {}

    total = sum(member.total_records for member in nonempty)
    allocation: dict[tuple[str, str], int] = {}
    for member in nonempty:
        share = desired_rows * member.total_records / total
        requested = min(
            member.total_records,
            max(page_size, math.ceil(share)),
        )
        allocation[
            (member.source_district_value, member.source_sector_value)
        ] = requested
    return allocation


def plan_geographic_spread_requests(
    universes: list[SupplementUniverse],
    geography_deficits: dict[str, int],
    *,
    candidate_multiplier: float = DEFAULT_SUPPLEMENT_MULTIPLIER,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[SupplementRequest]:
    """Plan follow-up pages only for groups still below their geography floor."""
    if candidate_multiplier < 1:
        raise ValueError("candidate multiplier must be at least 1.0")

    grouped: dict[str, list[SupplementUniverse]] = defaultdict(list)
    for universe in universes:
        grouped[universe.geography_group].append(universe)

    requests: list[SupplementRequest] = []
    seen_urls: set[str] = set()
    for geography_group, deficit in sorted(geography_deficits.items()):
        if deficit <= 0:
            continue
        members = grouped.get(geography_group, [])
        desired_rows = math.ceil(deficit * candidate_multiplier)
        allocation = _allocate_group_rows(
            members,
            desired_rows,
            page_size=page_size,
        )

        for member in sorted(
            members,
            key=lambda item: (
                item.source_district_label,
                item.source_sector_label,
                item.source_district_value,
                item.source_sector_value,
            ),
        ):
            requested_rows = allocation.get(
                (member.source_district_value, member.source_sector_value),
                0,
            )
            for page in spread_pages(
                member.total_records,
                requested_rows,
                page_size=page_size,
            ):
                if page == 1:
                    continue
                url = build_district_sector_url(
                    district_value=member.source_district_value,
                    sector_value=member.source_sector_value,
                    page=page,
                )
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                requests.append(
                    SupplementRequest(
                        geography_group=member.geography_group,
                        source_district_value=member.source_district_value,
                        source_district_label=member.source_district_label,
                        sector_family=member.sector_family,
                        source_sector_value=member.source_sector_value,
                        source_sector_label=member.source_sector_label,
                        page=page,
                        source_url=url,
                        reason="GEOGRAPHY_SPREAD",
                    )
                )

    return requests
