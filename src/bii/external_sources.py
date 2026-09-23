from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .matching import normalize_company_core, normalize_text


SOURCE_NAMES = ("EPB", "BGMEA", "BKMEA", "BEPZA", "DOE")


@dataclass(frozen=True)
class ExternalSourceSpec:
    source_name: str
    source_authority: str
    base_host: str
    default_linkage: str  # SITE | CONDITIONAL | ORGANIZATION
    stable_key_rule: str
    eligible_sector_families: tuple[str, ...] | None
    negative_inference_allowed: bool = False


SOURCE_SPECS: Mapping[str, ExternalSourceSpec] = {
    "EPB": ExternalSourceSpec(
        source_name="EPB",
        source_authority="Export Promotion Bureau",
        base_host="epb.gov.bd",
        default_linkage="CONDITIONAL",
        stable_key_rule="numeric exporter id from public exporter URL",
        eligible_sector_families=None,
    ),
    "BGMEA": ExternalSourceSpec(
        source_name="BGMEA",
        source_authority="Bangladesh Garment Manufacturers and Exporters Association",
        base_host="bgmea.com.bd",
        default_linkage="SITE",
        stable_key_rule="numeric public member id; BGMEA registration retained as source field",
        eligible_sector_families=("RMG_TEXTILE",),
    ),
    "BKMEA": ExternalSourceSpec(
        source_name="BKMEA",
        source_authority="Bangladesh Knitwear Manufacturers and Exporters Association",
        base_host="bkmea.com",
        default_linkage="ORGANIZATION",
        stable_key_rule="membership number",
        eligible_sector_families=("RMG_TEXTILE",),
    ),
    "BEPZA": ExternalSourceSpec(
        source_name="BEPZA",
        source_authority="Bangladesh Export Processing Zones Authority",
        base_host="bepza.gov.bd",
        default_linkage="CONDITIONAL",
        stable_key_rule="zone plus normalized enterprise name",
        eligible_sector_families=None,
    ),
    "DOE": ExternalSourceSpec(
        source_name="DOE",
        source_authority="Department of Environment",
        base_host="ecc.doe.gov.bd",
        default_linkage="CONDITIONAL",
        stable_key_rule="public client id",
        eligible_sector_families=None,
    ),
}


@dataclass(frozen=True)
class ExternalRecordPayload:
    source_name: str
    external_key: str
    entity_name: str
    site_text: str | None
    district: str | None
    upazila: str | None
    source_url: str
    source_updated_at_raw: str | None
    source_fields: dict[str, str]


def source_spec(source_name: str) -> ExternalSourceSpec:
    try:
        return SOURCE_SPECS[source_name.upper()]
    except KeyError as exc:
        raise ValueError(f"unsupported external source: {source_name}") from exc


def is_sector_eligible(source_name: str, sector_family: str) -> bool:
    spec = source_spec(source_name)
    return spec.eligible_sector_families is None or sector_family in spec.eligible_sector_families


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _label_map(html: str) -> dict[str, str]:
    """Extract common label/value structures without assuming one source layout."""
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, str] = {}

    for row in soup.select("tr"):
        cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        cells = [cell for cell in cells if cell]
        if len(cells) >= 2:
            result[normalize_text(cells[0]).rstrip(":")] = cells[1]

    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            key = _clean(dt.get_text(" ", strip=True))
            value = _clean(dd.get_text(" ", strip=True))
            if key and value:
                result[normalize_text(key).rstrip(":")] = value

    for node in soup.find_all(["div", "p", "li"]):
        text = _clean(node.get_text(" ", strip=True))
        if not text or ":" not in text:
            continue
        left, right = text.split(":", 1)
        left = _clean(left)
        right = _clean(right)
        if left and right and len(left) <= 80:
            result.setdefault(normalize_text(left), right)

    return result


def _pick(mapping: Mapping[str, str], *labels: str) -> str | None:
    normalized = {normalize_text(label).rstrip(":") for label in labels}
    for key, value in mapping.items():
        if normalize_text(key).rstrip(":") in normalized:
            return _clean(value)
    return None


def _heading(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in ("h1", "h2", "h3"):
        node = soup.find(tag)
        if node:
            value = _clean(node.get_text(" ", strip=True))
            if value:
                return value
    return None


def _numeric_url_key(url: str, segment: str) -> str | None:
    match = re.search(rf"/{re.escape(segment)}/(\d+)(?:[/?#]|$)", url)
    return match.group(1) if match else None


def _district_from_address(address: str | None, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if not address:
        return None
    # Do not guess a district from arbitrary address tokens. The source must expose
    # an explicit district field for site-level geography evidence.
    return None


def parse_epb_record(html: str, source_url: str) -> ExternalRecordPayload:
    fields = _label_map(html)
    external_key = _numeric_url_key(source_url, "exporter")
    if not external_key:
        raise ValueError("EPB exporter URL does not expose a numeric exporter id")
    entity_name = (
        _pick(fields, "Exporter Name", "Company Name", "Exporter")
        or _heading(html)
    )
    if not entity_name:
        raise ValueError("EPB record does not expose an exporter name")
    site_text = _pick(fields, "Factory Address", "Factory")
    district = _district_from_address(
        site_text,
        _pick(fields, "District", "Factory District"),
    )
    upazila = _pick(fields, "Thana", "Upazila", "Factory Thana", "Factory Upazila")
    updated = _pick(fields, "Updated", "Last Updated", "Update Date")
    return ExternalRecordPayload(
        source_name="EPB",
        external_key=external_key,
        entity_name=entity_name,
        site_text=site_text,
        district=district,
        upazila=upazila,
        source_url=source_url,
        source_updated_at_raw=updated,
        source_fields=dict(fields),
    )


def parse_bgmea_record(html: str, source_url: str) -> ExternalRecordPayload:
    fields = _label_map(html)
    external_key = _numeric_url_key(source_url, "member")
    if not external_key:
        raise ValueError("BGMEA member URL does not expose a numeric member id")
    entity_name = (
        _pick(fields, "Company Name", "Factory Name", "Member Name")
        or _heading(html)
    )
    if not entity_name:
        raise ValueError("BGMEA record does not expose a member/company name")
    site_text = _pick(fields, "Factory Address", "Factory Location")
    return ExternalRecordPayload(
        source_name="BGMEA",
        external_key=external_key,
        entity_name=entity_name,
        site_text=site_text,
        district=_pick(fields, "District", "Factory District"),
        upazila=_pick(fields, "Upazila", "Thana", "Factory Upazila", "Factory Thana"),
        source_url=source_url,
        source_updated_at_raw=_pick(fields, "Updated", "Last Updated"),
        source_fields=dict(fields),
    )


def parse_bkmea_record(html: str, source_url: str) -> ExternalRecordPayload:
    fields = _label_map(html)
    membership_no = _pick(
        fields,
        "Membership No",
        "Membership Number",
        "Member No",
        "Member Number",
    )
    if not membership_no:
        raise ValueError("BKMEA record does not expose a membership number")
    entity_name = (
        _pick(fields, "Company Name", "Member Company", "Company")
        or _heading(html)
    )
    if not entity_name:
        raise ValueError("BKMEA record does not expose a company name")
    return ExternalRecordPayload(
        source_name="BKMEA",
        external_key=normalize_text(membership_no),
        entity_name=entity_name,
        site_text=_pick(fields, "Factory Address"),
        district=_pick(fields, "District", "Factory District"),
        upazila=_pick(fields, "Upazila", "Thana"),
        source_url=source_url,
        source_updated_at_raw=_pick(fields, "Updated", "Last Updated"),
        source_fields=dict(fields),
    )


def parse_bepza_record(html: str, source_url: str) -> ExternalRecordPayload:
    fields = _label_map(html)
    entity_name = (
        _pick(fields, "Enterprise", "Enterprise Name", "Company Name")
        or _heading(html)
    )
    zone = _pick(fields, "Zone", "EPZ", "Economic Zone")
    if not entity_name or not zone:
        raise ValueError("BEPZA record requires enterprise name and zone")
    external_key = f"{normalize_text(zone)}::{normalize_company_core(entity_name)}"
    return ExternalRecordPayload(
        source_name="BEPZA",
        external_key=external_key,
        entity_name=entity_name,
        site_text=_pick(fields, "Address", "Factory Address") or zone,
        district=_pick(fields, "District"),
        upazila=_pick(fields, "Upazila", "Thana"),
        source_url=source_url,
        source_updated_at_raw=_pick(fields, "Updated", "Last Updated", "Published"),
        source_fields=dict(fields),
    )


def parse_doe_record(html: str, source_url: str) -> ExternalRecordPayload:
    fields = _label_map(html)
    client_id = _pick(fields, "Client ID", "Client Id", "Client")
    if not client_id:
        raise ValueError("DoE record does not expose a client id")
    entity_name = (
        _pick(fields, "Project/Industry", "Project / Industry", "Industry Name", "Project Name")
        or _heading(html)
    )
    if not entity_name:
        raise ValueError("DoE record does not expose a project/industry name")
    site_text = _pick(fields, "Address", "Project Address", "Industry Address")
    return ExternalRecordPayload(
        source_name="DOE",
        external_key=normalize_text(client_id),
        entity_name=entity_name,
        site_text=site_text,
        district=_pick(fields, "District"),
        upazila=_pick(fields, "Upazila", "Thana"),
        source_url=source_url,
        source_updated_at_raw=_pick(fields, "Updated", "Last Updated"),
        source_fields=dict(fields),
    )


PARSERS = {
    "EPB": parse_epb_record,
    "BGMEA": parse_bgmea_record,
    "BKMEA": parse_bkmea_record,
    "BEPZA": parse_bepza_record,
    "DOE": parse_doe_record,
}


def parse_external_record(
    source_name: str,
    html: str,
    source_url: str,
) -> ExternalRecordPayload:
    parser = PARSERS.get(source_name.upper())
    if parser is None:
        raise ValueError(f"unsupported external source: {source_name}")
    return parser(html, source_url)
