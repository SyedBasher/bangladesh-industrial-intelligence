from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .analytical_intelligence import (
    evidence_freshness,
    export_product_breadth,
    numeric_change_signals,
    numeric_source_consistency,
)


SCHEMA_VERSION = "1.1"

APPROVED_OBSERVATION_TYPES = frozenset({
    "EMPLOYMENT_COUNT",
    "MACHINE_COUNT",
    "PRODUCTION_CAPACITY",
    "PRINCIPAL_PRODUCT",
    "HS_CODE",
    "EXPORT_MARKET",
    "CERTIFICATION",
    "ASSOCIATION_MEMBERSHIP_RECORD",
    "ASSOCIATION_REGISTRATION",
    "EXPORT_REGISTRATION",
    "EXPORTER_DATABASE_RECORD",
    "ASSOCIATION",
    "EXPORTER_CATEGORY",
})

EXPORT_EVIDENCE_TYPES = frozenset({
    "EXPORTER_DATABASE_RECORD",
    "EXPORT_REGISTRATION",
    "HS_CODE",
    "EXPORT_MARKET",
    "EXPORTER_CATEGORY",
})

FORBIDDEN_PRODUCT_KEYS = frozenset({
    "raw_label",
    "raw_value",
    "source_url",
    "raw_payload_path",
    "snapshot_id",
    "external_record_id",
    "external_version_id",
    "entity_link_id",
    "typed_observation_id",
    "match_evidence_id",
    "observation_sha256",
    "content_sha256",
})


@dataclass(frozen=True)
class ProductBaseRecord:
    public_id: int
    name: str | None
    address: str | None
    upazila: str | None
    district: str | None
    division: str | None
    official_status: str | None
    industrial_sector: str | None
    establishment_type: str | None
    licence_class: str | None
    licence_expiry_raw: str | None
    worker_total: int | None
    observed_at: str | None


def _approved_evidence(
    observations: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()

    for row in observations:
        observation_type = str(row.get("observation_type") or "")
        if observation_type not in APPROVED_OBSERVATION_TYPES:
            continue

        item = {
            "type": observation_type,
            "source": str(row.get("source_name") or ""),
            "scope": str(row.get("display_scope") or row.get("source_scope") or ""),
            "match_type": str(row.get("match_type") or ""),
            "site_attributable": bool(row.get("site_attributable")),
            "value": row.get("value_text"),
            "numeric_value": row.get("value_numeric"),
            "unit": row.get("unit"),
            "source_vintage": row.get("source_updated_at_raw"),
            "observed_at": row.get("observed_at"),
        }
        fingerprint = tuple(item.get(key) for key in (
            "type", "source", "scope", "match_type", "value",
            "numeric_value", "unit", "source_vintage", "observed_at",
        ))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        evidence.append(item)

    evidence.sort(
        key=lambda item: (
            str(item["type"]),
            str(item["source"]),
            str(item.get("value") or ""),
        )
    )
    return evidence


def _values(
    evidence: Iterable[Mapping[str, object]],
    observation_type: str,
) -> list[dict[str, object]]:
    return [
        {
            "source": item["source"],
            "scope": item["scope"],
            "match_type": item["match_type"],
            "site_attributable": item["site_attributable"],
            "value": item["value"],
            "numeric_value": item["numeric_value"],
            "unit": item["unit"],
            "source_vintage": item["source_vintage"],
            "observed_at": item["observed_at"],
        }
        for item in evidence
        if item["type"] == observation_type
    ]


def _employment_band(value: int | float | None) -> dict[str, object]:
    if value is None:
        return {
            "value": "UNKNOWN",
            "label": "Employment count unavailable",
            "basis": None,
            "origin": "CALCULATED",
            "rule": "Analytical worker-count band; not an official Bangladesh enterprise classification.",
        }
    numeric = float(value)
    if numeric < 50:
        code, label = "UNDER_50", "Under 50 workers"
    elif numeric < 250:
        code, label = "50_249", "50–249 workers"
    elif numeric < 1000:
        code, label = "250_999", "250–999 workers"
    else:
        code, label = "1000_PLUS", "1,000+ workers"
    return {
        "value": code,
        "label": label,
        "basis": numeric,
        "origin": "CALCULATED",
        "rule": "Analytical worker-count band; not an official Bangladesh enterprise classification.",
    }


def _export_breadth(
    evidence: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    sources = sorted({
        str(item["source"])
        for item in evidence
        if item["type"] in EXPORT_EVIDENCE_TYPES and item.get("source")
    })
    count = len(sources)
    label = "NONE" if count == 0 else ("SINGLE_SOURCE" if count == 1 else "MULTI_SOURCE")
    return {
        "value": count,
        "label": label,
        "sources": sources,
        "origin": "CALCULATED",
        "rule": "Count of distinct validated external sources contributing approved export-related evidence.",
    }


def _employment_consistency(
    dife_worker_total: int | None,
    evidence: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    if dife_worker_total is None or dife_worker_total <= 0:
        return {
            "value": "NOT_CHECKED",
            "comparisons": [],
            "origin": "CALCULATED",
            "rule": "Requires a positive DIFE worker total and at least one site-attributable external employment count.",
        }

    comparisons: list[dict[str, object]] = []
    severity = 0
    for item in evidence:
        if item["type"] != "EMPLOYMENT_COUNT":
            continue
        if not item.get("site_attributable"):
            continue
        external = item.get("numeric_value")
        if external is None:
            continue
        external_value = float(external)
        difference_pct = abs(external_value - dife_worker_total) / dife_worker_total * 100.0
        if difference_pct <= 10:
            flag, level = "WITHIN_10_PERCENT", 1
        elif difference_pct <= 25:
            flag, level = "DIFFERENCE_10_TO_25_PERCENT", 2
        else:
            flag, level = "DIFFERENCE_OVER_25_PERCENT", 3
        severity = max(severity, level)
        comparisons.append({
            "source": item["source"],
            "dife_worker_total": dife_worker_total,
            "external_worker_total": external_value,
            "absolute_difference_pct": round(difference_pct, 2),
            "flag": flag,
        })

    if not comparisons:
        overall = "NOT_CHECKED"
    elif severity == 1:
        overall = "CONSISTENT_WITHIN_10_PERCENT"
    elif severity == 2:
        overall = "MODERATE_DIFFERENCE"
    else:
        overall = "MATERIAL_DIFFERENCE"

    return {
        "value": overall,
        "comparisons": comparisons,
        "origin": "CALCULATED",
        "rule": "Absolute employment difference relative to DIFE: <=10% consistent; >10–25% moderate; >25% material. Diagnostic only.",
    }


def build_product_payload(
    base: ProductBaseRecord,
    observations: Iterable[Mapping[str, object]],
    *,
    generated_at: str,
    history: Iterable[Mapping[str, object]] = (),
    cluster_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    evidence = _approved_evidence(observations)

    external_employment = _values(evidence, "EMPLOYMENT_COUNT")
    analytical_employment: int | float | None = base.worker_total
    if analytical_employment is None:
        for item in external_employment:
            if item["site_attributable"] and item["numeric_value"] is not None:
                analytical_employment = float(item["numeric_value"])
                break

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "establishment": {
            "establishment_ref": f"DIFE:{base.public_id}",
            "name": base.name,
            "address": base.address,
            "upazila": base.upazila,
            "district": base.district,
            "division": base.division,
            "official_status": base.official_status,
            "industrial_sector": base.industrial_sector,
            "establishment_type": base.establishment_type,
            "licence_class": base.licence_class,
            "licence_expiry": base.licence_expiry_raw,
            "dife_worker_total": base.worker_total,
            "dife_observed_at": base.observed_at,
            "source": "DIFE",
        },
        "facts": {
            "external_employment": external_employment,
            "machines": _values(evidence, "MACHINE_COUNT"),
            "production_capacity": _values(evidence, "PRODUCTION_CAPACITY"),
            "products": _values(evidence, "PRINCIPAL_PRODUCT"),
            "hs_codes": _values(evidence, "HS_CODE"),
            "export_markets": _values(evidence, "EXPORT_MARKET"),
            "certifications": _values(evidence, "CERTIFICATION"),
            "association_membership": _values(evidence, "ASSOCIATION_MEMBERSHIP_RECORD"),
            "association_registration": _values(evidence, "ASSOCIATION_REGISTRATION"),
            "export_registration": _values(evidence, "EXPORT_REGISTRATION"),
            "exporter_database_evidence": _values(evidence, "EXPORTER_DATABASE_RECORD"),
            "associations": _values(evidence, "ASSOCIATION"),
            "exporter_category": _values(evidence, "EXPORTER_CATEGORY"),
        },
        "calculated": {
            "employment_scale_band": _employment_band(analytical_employment),
            "export_evidence_breadth": _export_breadth(evidence),
            "employment_consistency": _employment_consistency(base.worker_total, evidence),
            "evidence_freshness": evidence_freshness(evidence, as_of=generated_at),
            "export_product_breadth": export_product_breadth(evidence),
            "external_numeric_consistency": {
                observation_type: numeric_source_consistency(evidence, observation_type)
                for observation_type in (
                    "EMPLOYMENT_COUNT",
                    "MACHINE_COUNT",
                    "PRODUCTION_CAPACITY",
                )
            },
            "change_signals": numeric_change_signals(history),
            "cluster_context": (
                dict(cluster_context)
                if cluster_context is not None
                else {
                    "status": "NOT_AVAILABLE",
                    "origin": "CALCULATED",
                    "rule": "Cluster context requires an explicitly declared comparison universe.",
                }
            ),
        },
        "evidence": evidence,
    }
    assert_product_payload_safe(payload)
    return payload


def assert_product_payload_safe(payload: Mapping[str, object]) -> None:
    """Fail closed if internal/private field names leak into a product payload."""
    violations: list[str] = []

    def walk(value: object, path: str = "$") -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key)
                if key_text in FORBIDDEN_PRODUCT_KEYS:
                    violations.append(f"{path}.{key_text}")
                if key_text.endswith("_id") and key_text != "public_id":
                    violations.append(f"{path}.{key_text}")
                walk(child, f"{path}.{key_text}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload)
    if violations:
        raise ValueError(
            "product payload contains forbidden internal/private fields: "
            + ", ".join(sorted(set(violations)))
        )
