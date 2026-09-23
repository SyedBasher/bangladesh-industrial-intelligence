from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import StrEnum
from statistics import mean
from typing import Iterable, Mapping, Sequence


class FreshnessBand(StrEnum):
    CURRENT = "CURRENT"
    AGING = "AGING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ConsistencyBand(StrEnum):
    CONSISTENT = "CONSISTENT"
    MODERATE_DIFFERENCE = "MODERATE_DIFFERENCE"
    MATERIAL_DIFFERENCE = "MATERIAL_DIFFERENCE"
    NOT_CHECKED = "NOT_CHECKED"


class UniverseKind(StrEnum):
    VALIDATION_SAMPLE = "VALIDATION_SAMPLE"
    NATIONAL_REGISTRY = "NATIONAL_REGISTRY"
    OTHER = "OTHER"


@dataclass(frozen=True)
class EvidenceFreshness:
    band: FreshnessBand
    age_days: int | None
    basis_timestamp: str | None
    basis_field: str | None
    source: str | None
    origin: str = "CALCULATED"
    rule: str = (
        "CURRENT <=180 days; AGING 181-365 days; STALE >365 days; "
        "UNKNOWN when no parseable source vintage or observation timestamp is available."
    )


@dataclass(frozen=True)
class ExportBreadth:
    hs_code_count: int
    product_count: int
    market_count: int
    evidence_source_count: int
    hs_codes: tuple[str, ...]
    products: tuple[str, ...]
    markets: tuple[str, ...]
    evidence_sources: tuple[str, ...]
    origin: str = "CALCULATED"
    rule: str = (
        "Distinct approved organization-scoped export/product observations from validated links; "
        "counts describe evidence breadth, not export value or shipment activity."
    )


@dataclass(frozen=True)
class NumericConsistency:
    observation_type: str
    band: ConsistencyBand
    source_count: int
    min_value: float | None
    max_value: float | None
    mean_value: float | None
    relative_spread_pct: float | None
    sources: tuple[str, ...]
    origin: str = "CALCULATED"
    rule: str = (
        "Relative spread = (max-min)/mean across site-attributable source values. "
        "<=10% consistent; >10-25% moderate; >25% material."
    )


@dataclass(frozen=True)
class ChangeSignal:
    observation_type: str
    source: str
    first_value: float
    latest_value: float
    absolute_change: float
    percent_change: float | None
    first_observed_at: str
    latest_observed_at: str
    unit: str | None
    origin: str = "CALCULATED"
    rule: str = (
        "First-to-latest change within the same validated source and observation type. "
        "A change in reported value is not automatically interpreted as real-world growth/decline."
    )


@dataclass(frozen=True)
class ClusterContext:
    universe_label: str
    universe_kind: UniverseKind
    district: str | None
    sector_family: str | None
    universe_size: int
    district_establishments: int
    sector_establishments: int
    district_sector_establishments: int
    district_sector_share_of_district: float | None
    district_sector_share_of_sector: float | None
    suitable_for_national_cluster_claim: bool
    origin: str = "CALCULATED"
    rule: str = (
        "Descriptive counts/shares for the declared universe. "
        "Only NATIONAL_REGISTRY universes are suitable for national cluster claims."
    )


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def evidence_freshness(
    evidence: Iterable[Mapping[str, object]],
    *,
    as_of: str,
) -> dict[str, object]:
    now = _parse_timestamp(as_of)
    if now is None:
        raise ValueError("as_of must be a parseable timestamp")

    dated: list[tuple[datetime, str, str, str]] = []
    for item in evidence:
        source = str(item.get("source") or "")
        vintage = item.get("source_vintage")
        observed = item.get("observed_at")

        dt = _parse_timestamp(vintage)
        if dt is not None:
            dated.append((dt, "source_vintage", str(vintage), source))
            continue
        dt = _parse_timestamp(observed)
        if dt is not None:
            dated.append((dt, "observed_at", str(observed), source))

    if not dated:
        return asdict(EvidenceFreshness(
            band=FreshnessBand.UNKNOWN,
            age_days=None,
            basis_timestamp=None,
            basis_field=None,
            source=None,
        ))

    latest_dt, basis_field, basis_timestamp, source = max(dated, key=lambda item: item[0])
    age_days = max(0, int((now - latest_dt).total_seconds() // 86400))
    if age_days <= 180:
        band = FreshnessBand.CURRENT
    elif age_days <= 365:
        band = FreshnessBand.AGING
    else:
        band = FreshnessBand.STALE

    return asdict(EvidenceFreshness(
        band=band,
        age_days=age_days,
        basis_timestamp=basis_timestamp,
        basis_field=basis_field,
        source=source or None,
    ))


def export_product_breadth(
    evidence: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    hs_codes: set[str] = set()
    products: set[str] = set()
    markets: set[str] = set()
    sources: set[str] = set()

    for item in evidence:
        if str(item.get("scope") or "") != "ORGANIZATION":
            continue
        typ = str(item.get("type") or "")
        value = item.get("value")
        source = str(item.get("source") or "")
        if typ == "HS_CODE" and value:
            hs_codes.add(str(value))
            if source:
                sources.add(source)
        elif typ == "PRINCIPAL_PRODUCT" and value:
            products.add(str(value))
            if source:
                sources.add(source)
        elif typ == "EXPORT_MARKET" and value:
            markets.add(str(value))
            if source:
                sources.add(source)
        elif typ in {"EXPORTER_DATABASE_RECORD", "EXPORT_REGISTRATION", "EXPORTER_CATEGORY"}:
            if source:
                sources.add(source)

    result = ExportBreadth(
        hs_code_count=len(hs_codes),
        product_count=len(products),
        market_count=len(markets),
        evidence_source_count=len(sources),
        hs_codes=tuple(sorted(hs_codes)),
        products=tuple(sorted(products)),
        markets=tuple(sorted(markets)),
        evidence_sources=tuple(sorted(sources)),
    )
    return asdict(result)


def numeric_source_consistency(
    evidence: Iterable[Mapping[str, object]],
    observation_type: str,
) -> dict[str, object]:
    values: list[tuple[str, float]] = []
    for item in evidence:
        if str(item.get("type") or "") != observation_type:
            continue
        if not bool(item.get("site_attributable")):
            continue
        raw = item.get("numeric_value")
        if raw is None:
            continue
        values.append((str(item.get("source") or ""), float(raw)))

    # Use one value per source. Product payloads already contain only the latest
    # validated link per source, but collapse duplicates defensively.
    per_source: dict[str, float] = {}
    for source, value in values:
        per_source[source] = value

    if len(per_source) < 2:
        result = NumericConsistency(
            observation_type=observation_type,
            band=ConsistencyBand.NOT_CHECKED,
            source_count=len(per_source),
            min_value=None,
            max_value=None,
            mean_value=None,
            relative_spread_pct=None,
            sources=tuple(sorted(per_source)),
        )
        return asdict(result)

    numeric = list(per_source.values())
    avg = mean(numeric)
    spread = 0.0 if avg == 0 else (max(numeric) - min(numeric)) / abs(avg) * 100.0
    if spread <= 10:
        band = ConsistencyBand.CONSISTENT
    elif spread <= 25:
        band = ConsistencyBand.MODERATE_DIFFERENCE
    else:
        band = ConsistencyBand.MATERIAL_DIFFERENCE

    result = NumericConsistency(
        observation_type=observation_type,
        band=band,
        source_count=len(per_source),
        min_value=min(numeric),
        max_value=max(numeric),
        mean_value=round(avg, 4),
        relative_spread_pct=round(spread, 2),
        sources=tuple(sorted(per_source)),
    )
    return asdict(result)


def numeric_change_signals(
    history: Iterable[Mapping[str, object]],
    *,
    allowed_types: Sequence[str] = (
        "EMPLOYMENT_COUNT",
        "MACHINE_COUNT",
        "PRODUCTION_CAPACITY",
    ),
) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str | None], list[tuple[datetime, float, str]]] = defaultdict(list)

    for row in history:
        typ = str(row.get("observation_type") or "")
        if typ not in allowed_types:
            continue
        if not bool(row.get("site_attributable")):
            continue
        source = str(row.get("source_name") or "")
        numeric = row.get("value_numeric")
        observed_at = row.get("observed_at")
        unit = None if row.get("unit") is None else str(row.get("unit"))
        dt = _parse_timestamp(observed_at)
        if not source or numeric is None or dt is None:
            continue
        groups[(typ, source, unit)].append((dt, float(numeric), str(observed_at)))

    signals: list[ChangeSignal] = []
    for (typ, source, unit), rows in groups.items():
        # Deduplicate identical timestamp/value pairs.
        unique = sorted(set(rows), key=lambda item: item[0])
        if len(unique) < 2:
            continue
        first_dt, first_value, first_text = unique[0]
        latest_dt, latest_value, latest_text = unique[-1]
        if first_dt == latest_dt:
            continue
        absolute = latest_value - first_value
        pct = None if first_value == 0 else absolute / abs(first_value) * 100.0
        signals.append(ChangeSignal(
            observation_type=typ,
            source=source,
            first_value=first_value,
            latest_value=latest_value,
            absolute_change=absolute,
            percent_change=None if pct is None else round(pct, 2),
            first_observed_at=first_text,
            latest_observed_at=latest_text,
            unit=unit,
        ))

    signals.sort(key=lambda item: (item.observation_type, item.source, item.unit or ""))
    return [asdict(item) for item in signals]


def cluster_context(
    records: Iterable[Mapping[str, object]],
    *,
    district: str | None,
    sector_family: str | None,
    universe_label: str,
    universe_kind: UniverseKind,
) -> dict[str, object]:
    rows = list(records)
    district_rows = [row for row in rows if row.get("district") == district] if district else []
    sector_rows = [row for row in rows if row.get("sector_family") == sector_family] if sector_family else []
    joint = [
        row for row in rows
        if row.get("district") == district and row.get("sector_family") == sector_family
    ] if district and sector_family else []

    district_share = (
        len(joint) / len(district_rows) * 100.0
        if district_rows else None
    )
    sector_share = (
        len(joint) / len(sector_rows) * 100.0
        if sector_rows else None
    )

    result = ClusterContext(
        universe_label=universe_label,
        universe_kind=universe_kind,
        district=district,
        sector_family=sector_family,
        universe_size=len(rows),
        district_establishments=len(district_rows),
        sector_establishments=len(sector_rows),
        district_sector_establishments=len(joint),
        district_sector_share_of_district=None if district_share is None else round(district_share, 2),
        district_sector_share_of_sector=None if sector_share is None else round(sector_share, 2),
        suitable_for_national_cluster_claim=universe_kind == UniverseKind.NATIONAL_REGISTRY,
    )
    return asdict(result)
