from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .sampling import SECTOR_TARGETS


class NationalSnapshotIntegrityError(RuntimeError):
    """A fetched page cannot safely join the declared national snapshot."""


class NationalSourceTotalDriftError(NationalSnapshotIntegrityError):
    def __init__(self, *, page: int, expected: int | None, observed: int | None):
        self.page = page
        self.expected = expected
        self.observed = observed
        super().__init__(
            f"source total drift on page {page}: expected {expected}, observed {observed}"
        )


class NationalDuplicatePublicIdError(NationalSnapshotIntegrityError):
    def __init__(self, *, page: int, public_ids: Iterable[int]):
        ids = tuple(sorted({int(value) for value in public_ids}))
        self.page = page
        self.public_ids = ids
        super().__init__(
            f"duplicate DIFE public ID(s) on/against page {page}: "
            + ", ".join(str(value) for value in ids[:20])
        )


class NationalPageCardinalityError(NationalSnapshotIntegrityError):
    def __init__(self, *, page: int, expected: int, observed: int):
        self.page = page
        self.expected = expected
        self.observed = observed
        super().__init__(
            f"page {page} row count mismatch: expected {expected}, observed {observed}"
        )


def expected_records_on_page(
    expected_total: int,
    *,
    page: int,
    page_size: int,
) -> int:
    if expected_total <= 0:
        raise ValueError("expected_total must be positive")
    if page <= 0:
        raise ValueError("page must be positive")
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    remaining = expected_total - (page - 1) * page_size
    if remaining <= 0:
        return 0
    return min(page_size, remaining)


@dataclass(frozen=True)
class NationalPageRequest:
    page: int
    source_url: str
    reason: str = "NATIONAL_SNAPSHOT_PAGE"


@dataclass(frozen=True)
class NationalPageStatus:
    page: int
    status: str
    records_parsed: int | None
    source_reported_total: int | None


@dataclass(frozen=True)
class NationalUniverseQuality:
    expected_total: int | None
    pages_planned: int
    pages_staged: int
    failed_pages: int
    skipped_pages: int
    membership_rows: int
    unique_public_ids: int
    duplicate_public_ids: int
    min_source_total: int | None
    max_source_total: int | None
    source_total_stable: bool
    all_pages_staged: bool
    record_count_matches_total: bool
    eligible_for_national_analysis: bool


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def explicit_sector_family(source_label: str | None) -> str | None:
    """Map only explicit known DIFE labels; never force unknowns into another family."""
    label = _norm(source_label)
    if not label:
        return None
    for code, _, _, tokens in SECTOR_TARGETS:
        if any(_norm(token) in label for token in tokens):
            return code
    return None


def _replace_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["page"] = [str(page)]
    encoded = urlencode([(key, item) for key, values in query.items() for item in values])
    return urlunparse(parsed._replace(query=encoded))


def plan_national_pages(
    expected_total: int,
    *,
    first_page_url: str,
    page_size: int = 30,
) -> list[NationalPageRequest]:
    if expected_total <= 0:
        raise ValueError("expected_total must be positive")
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    last_page = math.ceil(expected_total / page_size)
    return [
        NationalPageRequest(
            page=page,
            source_url=_replace_page(first_page_url, page),
        )
        for page in range(1, last_page + 1)
    ]


def assess_national_universe_quality(
    page_statuses: Iterable[NationalPageStatus],
    member_public_ids: Iterable[int],
    *,
    expected_total: int | None,
) -> NationalUniverseQuality:
    pages = list(page_statuses)
    member_ids = list(member_public_ids)
    pages_planned = len(pages)
    pages_staged = sum(page.status == "STAGED" for page in pages)
    failed_pages = sum(page.status == "FAILED" for page in pages)
    skipped_pages = sum(page.status == "SKIPPED" for page in pages)

    totals = [
        int(page.source_reported_total)
        for page in pages
        if page.status == "STAGED" and page.source_reported_total is not None
    ]
    min_total = min(totals) if totals else None
    max_total = max(totals) if totals else None
    source_total_stable = bool(totals) and min_total == max_total == expected_total

    unique_ids = len(set(member_ids))
    duplicate_ids = len(member_ids) - unique_ids
    all_pages_staged = pages_planned > 0 and pages_staged == pages_planned
    record_count_matches_total = (
        expected_total is not None
        and expected_total > 0
        and len(member_ids) == expected_total
        and unique_ids == expected_total
    )
    eligible = (
        all_pages_staged
        and failed_pages == 0
        and skipped_pages == 0
        and duplicate_ids == 0
        and source_total_stable
        and record_count_matches_total
    )
    return NationalUniverseQuality(
        expected_total=expected_total,
        pages_planned=pages_planned,
        pages_staged=pages_staged,
        failed_pages=failed_pages,
        skipped_pages=skipped_pages,
        membership_rows=len(member_ids),
        unique_public_ids=unique_ids,
        duplicate_public_ids=duplicate_ids,
        min_source_total=min_total,
        max_source_total=max_total,
        source_total_stable=source_total_stable,
        all_pages_staged=all_pages_staged,
        record_count_matches_total=record_count_matches_total,
        eligible_for_national_analysis=eligible,
    )


def _share(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100.0, 4)


def _location_quotient(
    cell: int,
    district_total: int,
    sector_total: int,
    national_total: int,
) -> float | None:
    if not cell or not district_total or not sector_total or not national_total:
        return None
    district_sector_share = cell / district_total
    national_sector_share = sector_total / national_total
    if national_sector_share == 0:
        return None
    return round(district_sector_share / national_sector_share, 4)


def build_national_rollups(
    records: Iterable[Mapping[str, object]],
    *,
    universe_label: str,
) -> dict[str, object]:
    rows = list(records)
    total = len(rows)
    if total == 0:
        raise ValueError("national rollups require at least one record")

    district_counts: Counter[str] = Counter()
    division_counts: Counter[str] = Counter()
    sector_counts: Counter[str] = Counter()
    source_sector_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    district_sector_counts: Counter[tuple[str, str]] = Counter()

    for row in rows:
        district = str(row.get("district") or "UNKNOWN")
        division = str(row.get("division") or "UNKNOWN")
        source_sector = str(row.get("sector_label") or "UNKNOWN")
        family = str(row.get("sector_family") or "UNCLASSIFIED")
        status = str(row.get("status") or "UNKNOWN")

        district_counts[district] += 1
        division_counts[division] += 1
        sector_counts[family] += 1
        source_sector_counts[source_sector] += 1
        status_counts[status] += 1
        district_sector_counts[(district, family)] += 1

    district_rows = [
        {
            "district": district,
            "establishments": count,
            "share_national_pct": _share(count, total),
        }
        for district, count in sorted(
            district_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    division_rows = [
        {
            "division": division,
            "establishments": count,
            "share_national_pct": _share(count, total),
        }
        for division, count in sorted(
            division_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    sector_rows: list[dict[str, object]] = []
    for sector, count in sorted(
        sector_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        district_shares = [
            cell / count
            for (district, family), cell in district_sector_counts.items()
            if family == sector and count > 0
        ]
        hhi = sum(share * share for share in district_shares)
        sector_rows.append({
            "sector_family": sector,
            "establishments": count,
            "share_national_pct": _share(count, total),
            "district_count": sum(
                1 for (district, family), cell in district_sector_counts.items()
                if family == sector and cell > 0
            ),
            "district_hhi": round(hhi, 6),
        })

    district_sector_rows: list[dict[str, object]] = []
    for (district, sector), cell in sorted(
        district_sector_counts.items(),
        key=lambda item: (-item[1], item[0][0], item[0][1]),
    ):
        district_total = district_counts[district]
        sector_total = sector_counts[sector]
        district_sector_rows.append({
            "district": district,
            "sector_family": sector,
            "establishments": cell,
            "share_of_district_pct": _share(cell, district_total),
            "share_of_national_sector_pct": _share(cell, sector_total),
            "location_quotient": _location_quotient(
                cell,
                district_total,
                sector_total,
                total,
            ),
        })

    statuses = [
        {
            "status": status,
            "establishments": count,
            "share_national_pct": _share(count, total),
        }
        for status, count in sorted(
            status_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    source_sectors = [
        {
            "source_sector_label": label,
            "establishments": count,
            "share_national_pct": _share(count, total),
        }
        for label, count in sorted(
            source_sector_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    mapped = total - sector_counts.get("UNCLASSIFIED", 0)
    return {
        "universe_label": universe_label,
        "universe_kind": "NATIONAL_REGISTRY",
        "origin": "CALCULATED",
        "summary": {
            "establishments": total,
            "districts": len(district_counts),
            "divisions": len(division_counts),
            "source_sector_labels": len(source_sector_counts),
            "mapped_sector_family_records": mapped,
            "unclassified_sector_records": sector_counts.get("UNCLASSIFIED", 0),
            "sector_mapping_coverage_pct": _share(mapped, total),
        },
        "districts": district_rows,
        "divisions": division_rows,
        "sector_families": sector_rows,
        "district_sector_cells": district_sector_rows,
        "statuses": statuses,
        "source_sector_labels": source_sectors,
        "method": {
            "location_quotient": (
                "(district-sector / district total) / "
                "(national sector total / national total)"
            ),
            "district_hhi": (
                "sum of squared district shares within each sector; "
                "reported with the underlying district-sector shares"
            ),
        },
    }
