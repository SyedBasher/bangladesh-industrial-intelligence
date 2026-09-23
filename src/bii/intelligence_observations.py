from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping

from .external_sources import ExternalRecordPayload
from .matching import normalize_text


class ObservationScope(StrEnum):
    SITE = "SITE"
    ORGANIZATION = "ORGANIZATION"


@dataclass(frozen=True)
class TypedObservation:
    observation_type: str
    scope: ObservationScope
    value_text: str | None
    value_numeric: float | None
    unit: str | None
    raw_label: str
    raw_value: str


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


def _normalized_fields(fields: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for raw_label, raw_value in fields.items():
        label = normalize_text(raw_label).rstrip(":")
        value = _clean(raw_value)
        if label and value:
            result[label] = (raw_label, value)
    return result


def _pick(
    fields: Mapping[str, tuple[str, str]],
    aliases: Iterable[str],
) -> tuple[str, str] | None:
    wanted = {normalize_text(alias).rstrip(":") for alias in aliases}
    for label, pair in fields.items():
        if label in wanted:
            return pair
    return None


def _split_multi(value: str) -> list[str]:
    pieces = re.split(r"\s*(?:;|\||\n|•|,\s*(?=[A-Za-z]))\s*", value)
    result: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        cleaned = _clean(piece)
        if not cleaned:
            continue
        key = normalize_text(cleaned)
        if key and key not in seen:
            result.append(cleaned)
            seen.add(key)
    return result


def _parse_number(value: str) -> float | None:
    match = re.search(r"(?<!\w)(\d[\d,]*(?:\.\d+)?)\s*(thousand|million|billion|k|m|bn)?", value, re.I)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    scale = (match.group(2) or "").casefold()
    multiplier = {
        "thousand": 1_000,
        "k": 1_000,
        "million": 1_000_000,
        "m": 1_000_000,
        "billion": 1_000_000_000,
        "bn": 1_000_000_000,
    }.get(scale, 1)
    return number * multiplier


def _parse_capacity(value: str) -> tuple[float | None, str | None]:
    numeric = _parse_number(value)
    if numeric is None:
        return None, None
    match = re.search(r"(?<!\w)\d[\d,]*(?:\.\d+)?\s*(?:thousand|million|billion|k|m|bn)?\s*(.*)$", value, re.I)
    unit = _clean(match.group(1)) if match else None
    return numeric, unit


def _single(
    fields: Mapping[str, tuple[str, str]],
    aliases: Iterable[str],
    observation_type: str,
    scope: ObservationScope,
    *,
    numeric: bool = False,
    capacity: bool = False,
) -> list[TypedObservation]:
    pair = _pick(fields, aliases)
    if not pair:
        return []
    raw_label, raw_value = pair
    value_numeric: float | None = None
    unit: str | None = None
    if capacity:
        value_numeric, unit = _parse_capacity(raw_value)
    elif numeric:
        value_numeric = _parse_number(raw_value)
    return [
        TypedObservation(
            observation_type=observation_type,
            scope=scope,
            value_text=raw_value,
            value_numeric=value_numeric,
            unit=unit,
            raw_label=raw_label,
            raw_value=raw_value,
        )
    ]


def _multi(
    fields: Mapping[str, tuple[str, str]],
    aliases: Iterable[str],
    observation_type: str,
    scope: ObservationScope,
) -> list[TypedObservation]:
    pair = _pick(fields, aliases)
    if not pair:
        return []
    raw_label, raw_value = pair
    return [
        TypedObservation(
            observation_type=observation_type,
            scope=scope,
            value_text=value,
            value_numeric=None,
            unit=None,
            raw_label=raw_label,
            raw_value=raw_value,
        )
        for value in _split_multi(raw_value)
    ]


def _hs_codes(
    fields: Mapping[str, tuple[str, str]],
) -> list[TypedObservation]:
    pair = _pick(fields, ("HS Code", "HS Codes", "H.S. Code", "Product HS Code"))
    if not pair:
        return []
    raw_label, raw_value = pair
    codes: list[str] = []
    seen: set[str] = set()
    for code in re.findall(r"(?<!\d)\d{4,10}(?!\d)", raw_value):
        if code not in seen:
            codes.append(code)
            seen.add(code)
    return [
        TypedObservation(
            observation_type="HS_CODE",
            scope=ObservationScope.ORGANIZATION,
            value_text=code,
            value_numeric=None,
            unit=None,
            raw_label=raw_label,
            raw_value=raw_value,
        )
        for code in codes
    ]


def _record_presence(
    observation_type: str,
    scope: ObservationScope,
    source_name: str,
) -> TypedObservation:
    return TypedObservation(
        observation_type=observation_type,
        scope=scope,
        value_text="present",
        value_numeric=None,
        unit=None,
        raw_label="source record",
        raw_value=f"{source_name} public record present",
    )


def extract_bgmea_observations(payload: ExternalRecordPayload) -> list[TypedObservation]:
    fields = _normalized_fields(payload.source_fields)
    observations: list[TypedObservation] = [
        _record_presence(
            "ASSOCIATION_MEMBERSHIP_RECORD",
            ObservationScope.ORGANIZATION,
            "BGMEA",
        )
    ]
    observations += _single(
        fields,
        ("Employees", "No of Employees", "Number of Employees", "Total Employees", "Workers"),
        "EMPLOYMENT_COUNT",
        ObservationScope.SITE,
        numeric=True,
    )
    observations += _single(
        fields,
        ("Machines", "No of Machines", "Number of Machines", "Total Machines"),
        "MACHINE_COUNT",
        ObservationScope.SITE,
        numeric=True,
    )
    observations += _single(
        fields,
        ("Production Capacity", "Production Capacity Per Annum", "Capacity"),
        "PRODUCTION_CAPACITY",
        ObservationScope.SITE,
        capacity=True,
    )
    observations += _multi(
        fields,
        ("Principal Products", "Products", "Product"),
        "PRINCIPAL_PRODUCT",
        ObservationScope.SITE,
    )
    observations += _multi(
        fields,
        ("Export Markets", "Major Export Markets", "Major Markets", "Markets"),
        "EXPORT_MARKET",
        ObservationScope.ORGANIZATION,
    )
    observations += _multi(
        fields,
        ("Certifications", "Certification", "Compliance Certification", "Certificates"),
        "CERTIFICATION",
        ObservationScope.SITE,
    )
    observations += _single(
        fields,
        ("BGMEA Reg No", "BGMEA Registration No", "BGMEA Registration Number"),
        "ASSOCIATION_REGISTRATION",
        ObservationScope.ORGANIZATION,
    )
    observations += _single(
        fields,
        ("EPB Reg No", "EPB Registration No", "EPB Registration Number"),
        "EXPORT_REGISTRATION",
        ObservationScope.ORGANIZATION,
    )
    return observations


def extract_epb_observations(payload: ExternalRecordPayload) -> list[TypedObservation]:
    fields = _normalized_fields(payload.source_fields)
    observations: list[TypedObservation] = [
        _record_presence(
            "EXPORTER_DATABASE_RECORD",
            ObservationScope.ORGANIZATION,
            "EPB",
        )
    ]
    observations += _hs_codes(fields)
    observations += _multi(
        fields,
        ("Principal Products", "Products", "Product", "Export Products", "Product Name"),
        "PRINCIPAL_PRODUCT",
        ObservationScope.ORGANIZATION,
    )
    observations += _multi(
        fields,
        ("Export Markets", "Export Market", "Major Export Markets", "Markets"),
        "EXPORT_MARKET",
        ObservationScope.ORGANIZATION,
    )
    observations += _multi(
        fields,
        ("Association", "Association Name", "Trade Association"),
        "ASSOCIATION",
        ObservationScope.ORGANIZATION,
    )
    observations += _single(
        fields,
        ("EPB Registration", "EPB Registration No", "EPB Reg No", "Registration No"),
        "EXPORT_REGISTRATION",
        ObservationScope.ORGANIZATION,
    )
    observations += _single(
        fields,
        ("Exporter Category", "Category", "Exporter Type"),
        "EXPORTER_CATEGORY",
        ObservationScope.ORGANIZATION,
    )
    return observations


def extract_typed_observations(
    payload: ExternalRecordPayload,
) -> list[TypedObservation]:
    source_name = payload.source_name.upper()
    if source_name == "BGMEA":
        return extract_bgmea_observations(payload)
    if source_name == "EPB":
        return extract_epb_observations(payload)
    return []
