from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from bs4 import BeautifulSoup

from .admin_geography import (
    AdministrativeGeographyCrosswalk,
    GeoMatchStatus,
)


DDM_AWARE_SOURCE_NAME = "DDM AWARE Risk Information"
DDM_AWARE_RISK_URL = "https://rapid.ddm.gov.bd/risk/riskinfo"
DDM_ORDINAL_CATEGORIES = frozenset({
    "Very Low",
    "Low",
    "Medium",
    "High",
    "Very High",
})


@dataclass(frozen=True)
class DdmAwareRiskRecord:
    division: str
    district: str
    climate_zone: str
    hazard_exposure: str
    vulnerability: str
    lack_of_coping_capacity: str
    risk: str


@dataclass(frozen=True)
class DdmAwareUnresolvedGeography:
    division: str
    district: str
    status: str


@dataclass(frozen=True)
class DdmAwareConversionResult:
    observations: tuple[dict[str, object], ...]
    unresolved: tuple[DdmAwareUnresolvedGeography, ...]
    mapped_districts: int
    source_records: int


def _clean(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _header_key(value: str) -> str:
    return _clean(value).casefold()


_REQUIRED_HEADERS = {
    "division": "division",
    "district": "district",
    "climate zone": "climate_zone",
    "hazard exposure": "hazard_exposure",
    "vulnerability": "vulnerability",
    "lack of coping capacity": "lack_of_coping_capacity",
    "risk": "risk",
}


def parse_ddm_aware_risk_html(html: str) -> list[DdmAwareRiskRecord]:
    soup = BeautifulSoup(html, "html.parser")
    selected = None
    header_map: dict[int, str] = {}

    for table in soup.find_all("table"):
        header_cells = table.find_all("th")
        headers = [_header_key(cell.get_text(" ", strip=True)) for cell in header_cells]
        mapping = {
            index: _REQUIRED_HEADERS[header]
            for index, header in enumerate(headers)
            if header in _REQUIRED_HEADERS
        }
        if set(mapping.values()) == set(_REQUIRED_HEADERS.values()):
            selected = table
            header_map = mapping
            break

    if selected is None:
        raise ValueError("DDM AWARE risk table with required headers not found")

    records: list[DdmAwareRiskRecord] = []
    for row_no, tr in enumerate(selected.find_all("tr"), start=1):
        cells = tr.find_all("td")
        if not cells:
            continue
        values: dict[str, str] = {}
        for index, field in header_map.items():
            if index >= len(cells):
                raise ValueError(
                    f"DDM AWARE row {row_no} has fewer cells than the table header"
                )
            values[field] = _clean(cells[index].get_text(" ", strip=True))

        if not values.get("division") or not values.get("district"):
            raise ValueError(f"DDM AWARE row {row_no} lacks division/district")

        for field in (
            "hazard_exposure",
            "vulnerability",
            "lack_of_coping_capacity",
            "risk",
        ):
            if values[field] not in DDM_ORDINAL_CATEGORIES:
                raise ValueError(
                    f"DDM AWARE row {row_no} has unknown {field} category: "
                    f"{values[field]!r}"
                )

        records.append(
            DdmAwareRiskRecord(
                division=values["division"],
                district=values["district"],
                climate_zone=values["climate_zone"],
                hazard_exposure=values["hazard_exposure"],
                vulnerability=values["vulnerability"],
                lack_of_coping_capacity=values["lack_of_coping_capacity"],
                risk=values["risk"],
            )
        )

    if not records:
        raise ValueError("DDM AWARE risk table contained no data rows")
    return records


def ddm_records_to_exposure_observations(
    records: Iterable[DdmAwareRiskRecord],
    crosswalk: AdministrativeGeographyCrosswalk,
    *,
    source_vintage: str | None,
    observed_at: str,
) -> DdmAwareConversionResult:
    source_records = list(records)
    observations: list[dict[str, object]] = []
    unresolved: list[DdmAwareUnresolvedGeography] = []
    mapped_districts = 0

    metrics = (
        (
            "DDM_HAZARD_EXPOSURE",
            "DDM published hazard exposure",
            lambda row: row.hazard_exposure,
        ),
        (
            "DDM_VULNERABILITY",
            "DDM published vulnerability",
            lambda row: row.vulnerability,
        ),
        (
            "DDM_LACK_COPING_CAPACITY",
            "DDM published lack of coping capacity",
            lambda row: row.lack_of_coping_capacity,
        ),
        (
            "DDM_RISK_CATEGORY",
            "DDM published risk category",
            lambda row: row.risk,
        ),
        (
            "DDM_CLIMATE_ZONE",
            "DDM published climate zone",
            lambda row: row.climate_zone,
        ),
    )

    for row in source_records:
        match = crosswalk.resolve_district(
            row.district,
            division=row.division,
        )
        if (
            match.status
            not in {GeoMatchStatus.EXACT_NAME, GeoMatchStatus.APPROVED_ALIAS}
            or match.unit is None
            or match.geo_ref is None
        ):
            unresolved.append(
                DdmAwareUnresolvedGeography(
                    division=row.division,
                    district=row.district,
                    status=match.status.value,
                )
            )
            continue

        mapped_districts += 1
        canonical_district = match.unit.district_name_en
        if not canonical_district:
            raise RuntimeError("resolved DDM district lacks canonical district name")

        for metric_code, metric_label, value_fn in metrics:
            observations.append({
                "source": DDM_AWARE_SOURCE_NAME,
                "domain": "DISASTER_RISK",
                "metric_code": metric_code,
                "metric_label": metric_label,
                "spatial_scope": "DISTRICT",
                "district": canonical_district,
                "value_text": value_fn(row),
                "value_numeric": None,
                "unit": None,
                "direction": "CONTEXT_ONLY",
                "source_vintage": source_vintage,
                "observed_at": observed_at,
                "evidence_note": (
                    "DDM AWARE district-level published category; "
                    f"BBS geography match={match.status.value}. "
                    "Area context only; not site-specific impact."
                ),
                "canonical_geo_ref": match.geo_ref,
                "geography_match_type": match.status.value,
                "source_geography_label": f"{row.division} / {row.district}",
            })

    return DdmAwareConversionResult(
        observations=tuple(observations),
        unresolved=tuple(unresolved),
        mapped_districts=mapped_districts,
        source_records=len(source_records),
    )
