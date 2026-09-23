from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Iterable, Mapping

from .national_product import assert_national_product_safe


DISTRICT_PROFILE_SCHEMA_VERSION = "1.0"
SECTOR_PROFILE_SCHEMA_VERSION = "1.0"


def _share(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100.0, 4)


def _validated_inputs(
    dashboard: Mapping[str, object],
    registry_rows: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    universe = dict(dashboard.get("universe") or {})
    if universe.get("kind") != "NATIONAL_REGISTRY":
        raise ValueError("profiles require a NATIONAL_REGISTRY dashboard")
    if universe.get("eligible_for_national_analysis") is not True:
        raise ValueError("profiles require an eligible national universe")

    rows = [dict(row) for row in registry_rows]
    expected = int(universe.get("expected_total") or 0)
    unique_public_ids = int(universe.get("unique_public_ids") or 0)
    if expected <= 0 or unique_public_ids != expected or len(rows) != expected:
        raise ValueError("registry rows do not match the eligible national universe")

    refs = [str(row.get("establishment_ref") or "") for row in rows]
    if len(refs) != len(set(refs)):
        raise ValueError("registry product rows contain duplicate establishment refs")

    return universe, rows


def _status_composition(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    materialized = list(rows)
    total = len(materialized)
    counts = Counter(str(row.get("official_status") or "UNKNOWN") for row in materialized)
    return [
        {
            "status": status,
            "establishments": count,
            "share_pct": _share(count, total),
        }
        for status, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _source_sector_composition(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    materialized = list(rows)
    total = len(materialized)
    counts = Counter(
        str(row.get("source_sector_label") or "UNKNOWN")
        for row in materialized
    )
    return [
        {
            "source_sector_label": label,
            "establishments": count,
            "share_pct": _share(count, total),
        }
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _upazila_composition(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    materialized = list(rows)
    total = len(materialized)
    counts = Counter(str(row.get("upazila") or "UNKNOWN") for row in materialized)
    return [
        {
            "upazila": upazila,
            "establishments": count,
            "share_pct": _share(count, total),
        }
        for upazila, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _concentration_share(
    values: list[int],
    n: int,
) -> float | None:
    total = sum(values)
    if total <= 0:
        return None
    return round(sum(sorted(values, reverse=True)[:n]) / total * 100.0, 4)


def build_district_profile(
    dashboard: Mapping[str, object],
    registry_rows: Iterable[Mapping[str, object]],
    *,
    district: str,
    generated_at: str,
) -> dict[str, object]:
    universe, rows = _validated_inputs(dashboard, registry_rows)

    district_summary = next(
        (
            dict(row)
            for row in dashboard.get("districts", [])
            if str(row.get("district")) == district
        ),
        None,
    )
    if district_summary is None:
        raise KeyError(f"district not found in national dashboard: {district}")

    district_rows = [
        row for row in rows if str(row.get("district") or "") == district
    ]
    if len(district_rows) != int(district_summary["establishments"]):
        raise ValueError("district registry rows do not match dashboard district count")

    cells = [
        dict(row)
        for row in dashboard.get("district_sector_cells", [])
        if str(row.get("district") or "") == district
    ]
    cells.sort(
        key=lambda row: (
            -int(row.get("establishments") or 0),
            str(row.get("sector_family") or ""),
        )
    )

    sector_values = [int(row.get("establishments") or 0) for row in cells]
    mapped = sum(
        1 for row in district_rows
        if str(row.get("sector_family") or "") != "UNCLASSIFIED"
    )
    unclassified = len(district_rows) - mapped

    sectors = []
    for row in cells:
        lq = row.get("location_quotient")
        if lq is None:
            specialization = "NOT_AVAILABLE"
        elif float(lq) > 1:
            specialization = "ABOVE_NATIONAL_SHARE"
        elif float(lq) == 1:
            specialization = "EQUAL_TO_NATIONAL_SHARE"
        else:
            specialization = "BELOW_NATIONAL_SHARE"
        sectors.append({
            "sector_family": row.get("sector_family"),
            "establishments": row.get("establishments"),
            "share_of_district_pct": row.get("share_of_district_pct"),
            "share_of_national_sector_pct": row.get("share_of_national_sector_pct"),
            "location_quotient": lq,
            "specialization_flag": specialization,
        })

    payload = {
        "schema_version": DISTRICT_PROFILE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "universe": universe,
        "district": {
            "name": district,
            "establishments": int(district_summary["establishments"]),
            "share_national_pct": district_summary.get("share_national_pct"),
        },
        "coverage": {
            "national_registry_coverage": "EXACT",
            "records_in_profile": len(district_rows),
            "mapped_sector_records": mapped,
            "unclassified_sector_records": unclassified,
            "sector_mapping_coverage_pct": _share(mapped, len(district_rows)),
            "external_enrichment_coverage": "NOT_INCLUDED_IN_LIST_LEVEL_PROFILE",
        },
        "composition": {
            "upazilas": _upazila_composition(district_rows),
            "statuses": _status_composition(district_rows),
            "source_sector_labels": _source_sector_composition(district_rows),
            "sector_families": sectors,
        },
        "concentration": {
            "largest_3_sector_share_pct": _concentration_share(sector_values, 3),
            "largest_5_sector_share_pct": _concentration_share(sector_values, 5),
            "sectors_with_location_quotient_above_1": sum(
                1 for row in sectors
                if row["location_quotient"] is not None
                and float(row["location_quotient"]) > 1
            ),
            "origin": "CALCULATED",
        },
        "drilldown": {
            "registry_filter": {"district": district},
            "establishment_count": len(district_rows),
        },
        "method": {
            "location_quotient": dashboard.get("method", {}).get("location_quotient"),
            "specialization_flag": (
                "ABOVE_NATIONAL_SHARE when location quotient > 1; "
                "EQUAL_TO_NATIONAL_SHARE at 1; BELOW_NATIONAL_SHARE below 1."
            ),
            "note": (
                "All measures are descriptive counts/shares for the declared national "
                "registry universe; no composite district score is produced."
            ),
        },
    }
    assert_national_product_safe(payload)
    return payload


def build_sector_profile(
    dashboard: Mapping[str, object],
    registry_rows: Iterable[Mapping[str, object]],
    *,
    sector_family: str,
    generated_at: str,
) -> dict[str, object]:
    universe, rows = _validated_inputs(dashboard, registry_rows)

    sector_summary = next(
        (
            dict(row)
            for row in dashboard.get("sector_families", [])
            if str(row.get("sector_family") or "") == sector_family
        ),
        None,
    )
    if sector_summary is None:
        raise KeyError(f"sector family not found in national dashboard: {sector_family}")

    sector_rows = [
        row for row in rows
        if str(row.get("sector_family") or "") == sector_family
    ]
    if len(sector_rows) != int(sector_summary["establishments"]):
        raise ValueError("sector registry rows do not match dashboard sector count")

    cells = [
        dict(row)
        for row in dashboard.get("district_sector_cells", [])
        if str(row.get("sector_family") or "") == sector_family
    ]
    cells.sort(
        key=lambda row: (
            -int(row.get("establishments") or 0),
            str(row.get("district") or ""),
        )
    )
    district_values = [int(row.get("establishments") or 0) for row in cells]

    districts = []
    for row in cells:
        lq = row.get("location_quotient")
        if lq is None:
            specialization = "NOT_AVAILABLE"
        elif float(lq) > 1:
            specialization = "ABOVE_NATIONAL_SHARE"
        elif float(lq) == 1:
            specialization = "EQUAL_TO_NATIONAL_SHARE"
        else:
            specialization = "BELOW_NATIONAL_SHARE"
        districts.append({
            "district": row.get("district"),
            "establishments": row.get("establishments"),
            "share_of_national_sector_pct": row.get("share_of_national_sector_pct"),
            "share_of_district_pct": row.get("share_of_district_pct"),
            "location_quotient": lq,
            "specialization_flag": specialization,
        })

    payload = {
        "schema_version": SECTOR_PROFILE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "universe": universe,
        "sector": {
            "sector_family": sector_family,
            "establishments": int(sector_summary["establishments"]),
            "share_national_pct": sector_summary.get("share_national_pct"),
            "district_count": int(sector_summary.get("district_count") or 0),
        },
        "coverage": {
            "national_registry_coverage": "EXACT",
            "records_in_profile": len(sector_rows),
            "source_sector_label_count": len({
                str(row.get("source_sector_label") or "UNKNOWN")
                for row in sector_rows
            }),
            "external_enrichment_coverage": "NOT_INCLUDED_IN_LIST_LEVEL_PROFILE",
        },
        "composition": {
            "districts": districts,
            "statuses": _status_composition(sector_rows),
            "source_sector_labels": _source_sector_composition(sector_rows),
        },
        "concentration": {
            "district_hhi": sector_summary.get("district_hhi"),
            "largest_3_district_share_pct": _concentration_share(district_values, 3),
            "largest_5_district_share_pct": _concentration_share(district_values, 5),
            "districts_with_location_quotient_above_1": sum(
                1 for row in districts
                if row["location_quotient"] is not None
                and float(row["location_quotient"]) > 1
            ),
            "origin": "CALCULATED",
        },
        "drilldown": {
            "registry_filter": {"sector_family": sector_family},
            "establishment_count": len(sector_rows),
        },
        "method": {
            "location_quotient": dashboard.get("method", {}).get("location_quotient"),
            "district_hhi": dashboard.get("method", {}).get("district_hhi"),
            "note": (
                "District HHI and largest-district shares describe geographic "
                "concentration; no composite sector score is produced."
            ),
        },
    }
    assert_national_product_safe(payload)
    return payload


def filter_registry_for_profile(
    registry_rows: Iterable[Mapping[str, object]],
    profile: Mapping[str, object],
) -> list[dict[str, object]]:
    filters = dict(profile.get("drilldown", {}).get("registry_filter") or {})
    if not filters:
        return []
    rows = [dict(row) for row in registry_rows]
    for key, value in filters.items():
        rows = [row for row in rows if row.get(key) == value]
    rows.sort(
        key=lambda row: (
            str(row.get("name") or ""),
            str(row.get("establishment_ref") or ""),
        )
    )
    return rows


def write_national_profile_json(
    profile: Mapping[str, object],
    path: str | Path,
) -> Path:
    assert_national_product_safe(profile)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(dict(profile), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return destination
