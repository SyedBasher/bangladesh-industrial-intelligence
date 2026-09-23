from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from enum import StrEnum
from typing import Iterable, Mapping

from .national_product import assert_national_product_safe


class ExposureDomain(StrEnum):
    CLIMATE_HAZARD = "CLIMATE_HAZARD"
    DISASTER_RISK = "DISASTER_RISK"
    TRANSPORT_ACCESS = "TRANSPORT_ACCESS"
    POWER_SYSTEM = "POWER_SYSTEM"
    ENVIRONMENTAL_REGULATORY = "ENVIRONMENTAL_REGULATORY"


class SpatialScope(StrEnum):
    SITE = "SITE"
    UPAZILA = "UPAZILA"
    DISTRICT = "DISTRICT"


class ExposureAttribution(StrEnum):
    SITE_SPECIFIC = "SITE_SPECIFIC"
    UPAZILA_CONTEXT = "UPAZILA_CONTEXT"
    DISTRICT_CONTEXT = "DISTRICT_CONTEXT"


class ExposureDirection(StrEnum):
    HIGHER_MEANS_MORE_EXPOSURE = "HIGHER_MEANS_MORE_EXPOSURE"
    HIGHER_MEANS_LESS_EXPOSURE = "HIGHER_MEANS_LESS_EXPOSURE"
    CONTEXT_ONLY = "CONTEXT_ONLY"


@dataclass(frozen=True)
class ExposureObservation:
    source: str
    domain: ExposureDomain
    metric_code: str
    metric_label: str
    spatial_scope: SpatialScope
    establishment_ref: str | None = None
    district: str | None = None
    upazila: str | None = None
    value_text: str | None = None
    value_numeric: float | None = None
    unit: str | None = None
    direction: ExposureDirection = ExposureDirection.CONTEXT_ONLY
    source_vintage: str | None = None
    observed_at: str | None = None
    evidence_note: str | None = None
    canonical_geo_ref: str | None = None
    geography_match_type: str | None = None
    source_geography_label: str | None = None


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def validate_exposure_observation(
    observation: Mapping[str, object],
) -> ExposureObservation:
    source = str(observation.get("source") or "").strip()
    metric_code = str(observation.get("metric_code") or "").strip()
    metric_label = str(observation.get("metric_label") or "").strip()
    if not source:
        raise ValueError("exposure source is required")
    if not metric_code:
        raise ValueError("metric_code is required")
    if not metric_label:
        raise ValueError("metric_label is required")

    try:
        domain = ExposureDomain(str(observation.get("domain") or ""))
    except ValueError as exc:
        raise ValueError("unsupported exposure domain") from exc

    try:
        scope = SpatialScope(str(observation.get("spatial_scope") or ""))
    except ValueError as exc:
        raise ValueError("unsupported exposure spatial_scope") from exc

    try:
        direction = ExposureDirection(
            str(observation.get("direction") or ExposureDirection.CONTEXT_ONLY)
        )
    except ValueError as exc:
        raise ValueError("unsupported exposure direction") from exc

    establishment_ref = (
        None
        if observation.get("establishment_ref") is None
        else str(observation.get("establishment_ref")).strip()
    )
    district = (
        None if observation.get("district") is None
        else str(observation.get("district")).strip()
    )
    upazila = (
        None if observation.get("upazila") is None
        else str(observation.get("upazila")).strip()
    )

    if scope == SpatialScope.SITE and not establishment_ref:
        raise ValueError("SITE exposure requires establishment_ref")
    if scope == SpatialScope.UPAZILA and (not district or not upazila):
        raise ValueError("UPAZILA exposure requires both district and upazila")
    if scope == SpatialScope.DISTRICT and not district:
        raise ValueError("DISTRICT exposure requires district")

    value_numeric = observation.get("value_numeric")
    if value_numeric is not None:
        value_numeric = float(value_numeric)

    return ExposureObservation(
        source=source,
        domain=domain,
        metric_code=metric_code,
        metric_label=metric_label,
        spatial_scope=scope,
        establishment_ref=establishment_ref or None,
        district=district or None,
        upazila=upazila or None,
        value_text=(
            None if observation.get("value_text") is None
            else str(observation.get("value_text"))
        ),
        value_numeric=value_numeric,
        unit=None if observation.get("unit") is None else str(observation.get("unit")),
        direction=direction,
        source_vintage=(
            None if observation.get("source_vintage") is None
            else str(observation.get("source_vintage"))
        ),
        observed_at=(
            None if observation.get("observed_at") is None
            else str(observation.get("observed_at"))
        ),
        evidence_note=(
            None if observation.get("evidence_note") is None
            else str(observation.get("evidence_note"))
        ),
        canonical_geo_ref=(
            None if observation.get("canonical_geo_ref") is None
            else str(observation.get("canonical_geo_ref"))
        ),
        geography_match_type=(
            None if observation.get("geography_match_type") is None
            else str(observation.get("geography_match_type"))
        ),
        source_geography_label=(
            None if observation.get("source_geography_label") is None
            else str(observation.get("source_geography_label"))
        ),
    )


def _attribution(scope: SpatialScope) -> ExposureAttribution:
    if scope == SpatialScope.SITE:
        return ExposureAttribution.SITE_SPECIFIC
    if scope == SpatialScope.UPAZILA:
        return ExposureAttribution.UPAZILA_CONTEXT
    return ExposureAttribution.DISTRICT_CONTEXT


def link_exposure_observations(
    registry_rows: Iterable[Mapping[str, object]],
    observations: Iterable[Mapping[str, object]],
    *,
    geography_crosswalk: object | None = None,
) -> list[dict[str, object]]:
    """Attach exposure evidence using exact geography or a reviewed canonical crosswalk."""
    registry = [dict(row) for row in registry_rows]
    by_ref = {
        str(row.get("establishment_ref") or ""): row
        for row in registry
        if row.get("establishment_ref")
    }

    links: list[dict[str, object]] = []
    for raw in observations:
        obs = validate_exposure_observation(raw)
        matched: list[dict[str, object]] = []

        if obs.spatial_scope == SpatialScope.SITE:
            target = by_ref.get(str(obs.establishment_ref))
            if target is not None:
                matched = [target]
        elif obs.spatial_scope == SpatialScope.UPAZILA:
            if geography_crosswalk is not None and obs.canonical_geo_ref:
                matched = []
                for row in registry:
                    district_name = str(row.get("district") or "")
                    upazila_name = str(row.get("upazila") or "")
                    if not district_name or not upazila_name:
                        continue
                    geo_match = geography_crosswalk.resolve_upazila(
                        upazila_name,
                        district=district_name,
                        division=(
                            None if row.get("division") is None
                            else str(row.get("division"))
                        ),
                    )
                    if geo_match.geo_ref == obs.canonical_geo_ref:
                        matched.append(row)
            else:
                matched = [
                    row for row in registry
                    if _norm(row.get("district")) == _norm(obs.district)
                    and _norm(row.get("upazila")) == _norm(obs.upazila)
                ]
        elif obs.spatial_scope == SpatialScope.DISTRICT:
            if geography_crosswalk is not None and obs.canonical_geo_ref:
                matched = []
                for row in registry:
                    district_name = str(row.get("district") or "")
                    if not district_name:
                        continue
                    geo_match = geography_crosswalk.resolve_district(
                        district_name,
                        division=(
                            None if row.get("division") is None
                            else str(row.get("division"))
                        ),
                    )
                    if geo_match.geo_ref == obs.canonical_geo_ref:
                        matched.append(row)
            else:
                matched = [
                    row for row in registry
                    if _norm(row.get("district")) == _norm(obs.district)
                ]

        for row in matched:
            link = {
                "establishment_ref": row.get("establishment_ref"),
                "source": obs.source,
                "domain": obs.domain.value,
                "metric_code": obs.metric_code,
                "metric_label": obs.metric_label,
                "spatial_scope": obs.spatial_scope.value,
                "attribution": _attribution(obs.spatial_scope).value,
                "context_district": obs.district,
                "context_upazila": obs.upazila,
                "value_text": obs.value_text,
                "value_numeric": obs.value_numeric,
                "unit": obs.unit,
                "direction": obs.direction.value,
                "source_vintage": obs.source_vintage,
                "observed_at": obs.observed_at,
                "evidence_note": obs.evidence_note,
                "canonical_geo_ref": obs.canonical_geo_ref,
                "geography_match_type": obs.geography_match_type,
                "source_geography_label": obs.source_geography_label,
                "origin": "SOURCE_OBSERVATION",
            }
            assert_national_product_safe(link)
            links.append(link)

    links.sort(
        key=lambda item: (
            str(item.get("establishment_ref") or ""),
            str(item.get("domain") or ""),
            str(item.get("metric_code") or ""),
            str(item.get("source") or ""),
            str(item.get("spatial_scope") or ""),
        )
    )
    return links


def exposure_link_coverage(
    registry_rows: Iterable[Mapping[str, object]],
    links: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    rows = [dict(row) for row in registry_rows]
    refs = {str(row.get("establishment_ref") or "") for row in rows}
    linked = [
        dict(link) for link in links
        if str(link.get("establishment_ref") or "") in refs
    ]
    by_domain: dict[str, set[str]] = defaultdict(set)
    by_scope: dict[str, set[str]] = defaultdict(set)
    any_refs: set[str] = set()

    for link in linked:
        ref = str(link.get("establishment_ref") or "")
        any_refs.add(ref)
        by_domain[str(link.get("domain") or "UNKNOWN")].add(ref)
        by_scope[str(link.get("spatial_scope") or "UNKNOWN")].add(ref)

    total = len(rows)
    result = {
        "registry_establishments": total,
        "establishments_with_any_exposure_evidence": len(any_refs),
        "coverage_pct": round(len(any_refs) / total * 100.0, 4) if total else None,
        "by_domain": [
            {
                "domain": domain,
                "establishments_with_evidence": len(domain_refs),
                "coverage_pct": round(len(domain_refs) / total * 100.0, 4) if total else None,
            }
            for domain, domain_refs in sorted(by_domain.items())
        ],
        "by_spatial_scope": [
            {
                "spatial_scope": scope,
                "establishments_with_evidence": len(scope_refs),
                "coverage_pct": round(len(scope_refs) / total * 100.0, 4) if total else None,
            }
            for scope, scope_refs in sorted(by_scope.items())
        ],
        "origin": "CALCULATED",
        "note": (
            "Coverage measures the share of registry establishments with at least one "
            "linked exposure observation. It is not the share harmed or at risk."
        ),
    }
    assert_national_product_safe(result)
    return result


def _conditions(
    links: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], set[str]] = defaultdict(set)
    values: dict[tuple[object, ...], dict[str, object]] = {}

    for raw in links:
        link = dict(raw)
        key = (
            link.get("source"),
            link.get("domain"),
            link.get("metric_code"),
            link.get("metric_label"),
            link.get("spatial_scope"),
            link.get("attribution"),
            link.get("context_district"),
            link.get("context_upazila"),
            link.get("value_text"),
            link.get("value_numeric"),
            link.get("unit"),
            link.get("direction"),
            link.get("source_vintage"),
            link.get("observed_at"),
        )
        ref = str(link.get("establishment_ref") or "")
        if ref:
            grouped[key].add(ref)
        values[key] = {
            "source": link.get("source"),
            "domain": link.get("domain"),
            "metric_code": link.get("metric_code"),
            "metric_label": link.get("metric_label"),
            "spatial_scope": link.get("spatial_scope"),
            "attribution": link.get("attribution"),
            "context_district": link.get("context_district"),
            "context_upazila": link.get("context_upazila"),
            "value_text": link.get("value_text"),
            "value_numeric": link.get("value_numeric"),
            "unit": link.get("unit"),
            "direction": link.get("direction"),
            "source_vintage": link.get("source_vintage"),
            "observed_at": link.get("observed_at"),
        }

    result: list[dict[str, object]] = []
    for key, refs in grouped.items():
        item = dict(values[key])
        item["establishments_contextualized"] = len(refs)
        result.append(item)

    result.sort(
        key=lambda item: (
            str(item.get("domain") or ""),
            str(item.get("metric_code") or ""),
            str(item.get("source") or ""),
            str(item.get("context_district") or ""),
            str(item.get("context_upazila") or ""),
        )
    )
    return result


def build_establishment_exposure_profile(
    registry_row: Mapping[str, object],
    links: Iterable[Mapping[str, object]],
    *,
    generated_at: str,
) -> dict[str, object]:
    ref = str(registry_row.get("establishment_ref") or "")
    if not ref:
        raise ValueError("registry row requires establishment_ref")

    selected = [
        dict(link) for link in links
        if str(link.get("establishment_ref") or "") == ref
    ]
    domains = sorted({str(link.get("domain") or "") for link in selected})

    payload = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "establishment": {
            "establishment_ref": ref,
            "name": registry_row.get("name"),
            "district": registry_row.get("district"),
            "upazila": registry_row.get("upazila"),
            "sector_family": registry_row.get("sector_family"),
        },
        "coverage": {
            "linked_observations": len(selected),
            "domains_with_evidence": domains,
            "has_site_specific_evidence": any(
                link.get("attribution") == ExposureAttribution.SITE_SPECIFIC
                for link in selected
            ),
            "has_area_context_evidence": any(
                link.get("attribution") != ExposureAttribution.SITE_SPECIFIC
                for link in selected
            ),
        },
        "exposures": selected,
        "method": {
            "note": (
                "SITE_SPECIFIC evidence is directly attributed to the establishment. "
                "UPAZILA_CONTEXT and DISTRICT_CONTEXT describe surrounding-area "
                "conditions and do not establish that the site itself experienced "
                "the measured condition."
            ),
            "no_composite_score": True,
        },
    }
    assert_national_product_safe(payload)
    return payload


def build_district_exposure_profile(
    district_profile: Mapping[str, object],
    registry_rows: Iterable[Mapping[str, object]],
    links: Iterable[Mapping[str, object]],
    *,
    generated_at: str,
) -> dict[str, object]:
    district = str(district_profile.get("district", {}).get("name") or "")
    if not district:
        raise ValueError("district profile is missing district name")

    rows = [
        dict(row) for row in registry_rows
        if _norm(row.get("district")) == _norm(district)
    ]
    refs = {str(row.get("establishment_ref") or "") for row in rows}
    selected_links = [
        dict(link) for link in links
        if str(link.get("establishment_ref") or "") in refs
    ]

    payload = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "district": {
            "name": district,
            "establishments": len(rows),
        },
        "coverage": exposure_link_coverage(rows, selected_links),
        "conditions": _conditions(selected_links),
        "method": {
            "weighting": "ESTABLISHMENT_COUNT",
            "note": (
                "Coverage and contextualized-establishment counts are establishment-"
                "weighted. They are not employment-, output-, asset- or loss-weighted."
            ),
            "area_context_warning": (
                "District/upazila observations describe area context and must not be "
                "interpreted as site-specific damage or disruption."
            ),
            "no_composite_score": True,
        },
    }
    assert_national_product_safe(payload)
    return payload


def build_sector_exposure_profile(
    sector_profile: Mapping[str, object],
    registry_rows: Iterable[Mapping[str, object]],
    links: Iterable[Mapping[str, object]],
    *,
    generated_at: str,
) -> dict[str, object]:
    sector_family = str(
        sector_profile.get("sector", {}).get("sector_family") or ""
    )
    if not sector_family:
        raise ValueError("sector profile is missing sector_family")

    rows = [
        dict(row) for row in registry_rows
        if str(row.get("sector_family") or "") == sector_family
    ]
    refs = {str(row.get("establishment_ref") or "") for row in rows}
    selected_links = [
        dict(link) for link in links
        if str(link.get("establishment_ref") or "") in refs
    ]

    district_refs: dict[str, set[str]] = defaultdict(set)
    linked_refs_by_district: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        district_refs[str(row.get("district") or "UNKNOWN")].add(
            str(row.get("establishment_ref") or "")
        )
    for link in selected_links:
        ref = str(link.get("establishment_ref") or "")
        row = next(
            (row for row in rows if str(row.get("establishment_ref") or "") == ref),
            None,
        )
        if row is not None:
            linked_refs_by_district[str(row.get("district") or "UNKNOWN")].add(ref)

    district_coverage = []
    for district, district_set in sorted(district_refs.items()):
        linked_set = linked_refs_by_district.get(district, set())
        district_coverage.append({
            "district": district,
            "sector_establishments": len(district_set),
            "establishments_with_any_exposure_evidence": len(linked_set),
            "coverage_pct": (
                round(len(linked_set) / len(district_set) * 100.0, 4)
                if district_set else None
            ),
        })

    payload = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "sector": {
            "sector_family": sector_family,
            "establishments": len(rows),
        },
        "coverage": exposure_link_coverage(rows, selected_links),
        "district_coverage": district_coverage,
        "conditions": _conditions(selected_links),
        "method": {
            "weighting": "ESTABLISHMENT_COUNT",
            "note": (
                "Coverage is evidence coverage across establishments in the sector. "
                "It does not measure the share of sector output, employment or assets exposed."
            ),
            "no_supply_chain_inference": True,
            "no_composite_score": True,
        },
    }
    assert_national_product_safe(payload)
    return payload


def write_exposure_profile_json(
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
