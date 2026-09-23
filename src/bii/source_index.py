from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from .matching import normalize_company_core, normalize_text


@dataclass(frozen=True)
class SourceIndexMetadata:
    source_name: str
    total_records: int | None
    current_page: int | None
    last_page: int | None
    records_on_page: int
    has_next: bool | None


@dataclass(frozen=True)
class SourceIndexRecord:
    source_name: str
    source_key: str
    entity_name: str
    detail_url: str
    registration_no: str | None = None
    district: str | None = None
    upazila: str | None = None
    office_address: str | None = None
    factory_address: str | None = None


@dataclass(frozen=True)
class IndexRequest:
    source_name: str
    page: int
    source_url: str
    reason: str = "INDEX_PAGE"


@dataclass(frozen=True)
class IndexQuality:
    records: int
    duplicate_keys: int
    missing_names: int
    invalid_detail_urls: int
    unique_name_cores: int

    @property
    def valid(self) -> bool:
        return (
            self.records > 0
            and self.duplicate_keys == 0
            and self.missing_names == 0
            and self.invalid_detail_urls == 0
        )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


def _page_from_url(url: str) -> int | None:
    query = parse_qs(urlparse(url).query)
    value = query.get("page", [None])[0]
    try:
        return int(value) if value is not None else 1
    except (TypeError, ValueError):
        return None


def _replace_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["page"] = [str(page)]
    encoded = urlencode([(key, item) for key, values in query.items() for item in values])
    return urlunparse(parsed._replace(query=encoded))


def _numeric_key_from_path(url: str, segment: str) -> str | None:
    match = re.search(rf"/{re.escape(segment)}/(\d+)(?:[/?#]|$)", url)
    return match.group(1) if match else None


def parse_bgmea_member_index(
    html: str,
    *,
    source_url: str = "https://bgmea.com.bd/page/member-list",
) -> tuple[SourceIndexMetadata, list[SourceIndexRecord]]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    total_match = re.search(r"Total\s+([\d,]+)\s+Member\(s\)\s+Found", text, re.I)
    total = int(total_match.group(1).replace(",", "")) if total_match else None

    records: list[SourceIndexRecord] = []
    seen: set[str] = set()

    for row in soup.select("tr"):
        cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        detail = row.find("a", href=re.compile(r"/member/\d+"))
        if not detail:
            continue
        detail_url = urljoin(source_url, detail.get("href", ""))
        key = _numeric_key_from_path(detail_url, "member")
        if not key or key in seen:
            continue
        entity_name = cells[0]
        registration_no = cells[1] if len(cells) > 1 else None
        if not entity_name:
            continue
        records.append(
            SourceIndexRecord(
                source_name="BGMEA",
                source_key=key,
                entity_name=entity_name,
                detail_url=detail_url,
                registration_no=registration_no,
            )
        )
        seen.add(key)

    current_page = _page_from_url(source_url)
    last_page = math.ceil(total / len(records)) if total and records else None

    # Prefer the actual largest page link when available, because the first page
    # count can differ from normal pages or the source can change page size.
    linked_pages: list[int] = []
    for link in soup.find_all("a", href=True):
        page = _page_from_url(urljoin(source_url, link["href"]))
        label = _clean(link.get_text(" ", strip=True))
        if page and label and label.isdigit():
            linked_pages.append(page)
    if linked_pages:
        last_page = max(linked_pages)

    has_next = None
    if current_page is not None and last_page is not None:
        has_next = current_page < last_page

    return (
        SourceIndexMetadata(
            source_name="BGMEA",
            total_records=total,
            current_page=current_page,
            last_page=last_page,
            records_on_page=len(records),
            has_next=has_next,
        ),
        records,
    )


def _epb_record_from_mapping(item: dict[str, object], base_url: str) -> SourceIndexRecord | None:
    raw_id = item.get("id") or item.get("exporter_id") or item.get("exporterId")
    if raw_id is None:
        return None
    key = str(raw_id).strip()
    if not key.isdigit():
        return None

    name = _clean(str(item.get("name") or item.get("exporter_name") or ""))
    if not name:
        return None

    slug = _clean(str(item.get("slug") or ""))
    detail_url = _clean(str(item.get("url") or item.get("detail_url") or ""))
    if detail_url:
        detail_url = urljoin(base_url, detail_url)
    else:
        suffix = f"/{slug}" if slug else ""
        detail_url = urljoin(base_url, f"/exporter/{key}{suffix}")

    def nested_name(value: object) -> str | None:
        if isinstance(value, dict):
            return _clean(str(value.get("name") or ""))
        return _clean(str(value)) if value is not None else None

    return SourceIndexRecord(
        source_name="EPB",
        source_key=key,
        entity_name=name,
        detail_url=detail_url,
        registration_no=_clean(str(item.get("registration_no") or item.get("reg_no") or "")),
        district=nested_name(item.get("factory_district") or item.get("district")),
        upazila=nested_name(item.get("factory_thana") or item.get("thana") or item.get("upazila")),
        office_address=_clean(str(item.get("office_address") or "")),
        factory_address=_clean(str(item.get("factory_address") or "")),
    )


def parse_epb_exporter_index_json(
    payload: str | bytes | dict[str, object],
    *,
    source_url: str = "https://edb.epb.gov.bd/exporters",
) -> tuple[SourceIndexMetadata, list[SourceIndexRecord]]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        data = json.loads(payload)
    else:
        data = payload

    # Tolerate common pagination envelopes without binding to a private API schema.
    container: object = data
    for key in ("data", "exporters", "results"):
        if isinstance(container, dict) and key in container:
            maybe = container[key]
            if isinstance(maybe, list):
                container = maybe
                break
            if isinstance(maybe, dict):
                container = maybe

    items: list[dict[str, object]] = []
    if isinstance(container, list):
        items = [item for item in container if isinstance(item, dict)]
    elif isinstance(container, dict):
        for key in ("data", "items", "results", "exporters"):
            value = container.get(key)
            if isinstance(value, list):
                items = [item for item in value if isinstance(item, dict)]
                break

    def find_int(*keys: str) -> int | None:
        search_spaces = [data]
        if isinstance(data, dict):
            for key in ("meta", "pagination", "data"):
                value = data.get(key)
                if isinstance(value, dict):
                    search_spaces.append(value)
        for mapping in search_spaces:
            if not isinstance(mapping, dict):
                continue
            for key in keys:
                value = mapping.get(key)
                if value is not None:
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        pass
        return None

    records = [
        record
        for item in items
        if (record := _epb_record_from_mapping(item, source_url)) is not None
    ]
    total = find_int("total", "total_records", "count")
    current_page = find_int("current_page", "page") or _page_from_url(source_url)
    last_page = find_int("last_page", "pages", "total_pages")
    has_next = None
    if current_page is not None and last_page is not None:
        has_next = current_page < last_page

    return (
        SourceIndexMetadata(
            source_name="EPB",
            total_records=total,
            current_page=current_page,
            last_page=last_page,
            records_on_page=len(records),
            has_next=has_next,
        ),
        records,
    )


def parse_epb_exporter_index_html(
    html: str,
    *,
    source_url: str = "https://edb.epb.gov.bd/exporters",
) -> tuple[SourceIndexMetadata, list[SourceIndexRecord]]:
    """Parse server-rendered or captured rendered EPB exporter cards.

    The public EPB directory is client-rendered in some responses, so production
    staging may need a rendered HTML/JSON representation. This parser does not guess
    missing numeric exporter IDs from slugs.
    """
    soup = BeautifulSoup(html, "html.parser")
    records: list[SourceIndexRecord] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=re.compile(r"/exporter/\d+")):
        detail_url = urljoin(source_url, link.get("href", ""))
        key = _numeric_key_from_path(detail_url, "exporter")
        if not key or key in seen:
            continue
        name = _clean(link.get_text(" ", strip=True))
        if not name:
            # Use a nearby heading only when the link itself has no label.
            parent = link.find_parent(["article", "div", "li"])
            heading = parent.find(["h2", "h3", "h4"]) if parent else None
            name = _clean(heading.get_text(" ", strip=True)) if heading else None
        if not name:
            continue
        records.append(
            SourceIndexRecord(
                source_name="EPB",
                source_key=key,
                entity_name=name,
                detail_url=detail_url,
            )
        )
        seen.add(key)

    current_page = _page_from_url(source_url)
    linked_pages = []
    for link in soup.find_all("a", href=True):
        page = _page_from_url(urljoin(source_url, link["href"]))
        label = _clean(link.get_text(" ", strip=True))
        if page and label and label.isdigit():
            linked_pages.append(page)
    last_page = max(linked_pages) if linked_pages else None
    has_next = None if last_page is None or current_page is None else current_page < last_page

    return (
        SourceIndexMetadata(
            source_name="EPB",
            total_records=None,
            current_page=current_page,
            last_page=last_page,
            records_on_page=len(records),
            has_next=has_next,
        ),
        records,
    )


def plan_index_requests(
    source_name: str,
    *,
    first_page_url: str,
    metadata: SourceIndexMetadata,
    max_pages: int | None = None,
) -> list[IndexRequest]:
    """Plan a deterministic index crawl only when page bounds are known."""
    source_name = source_name.upper()
    if metadata.last_page is None:
        return [
            IndexRequest(
                source_name=source_name,
                page=metadata.current_page or 1,
                source_url=first_page_url,
                reason="INDEX_SEED",
            )
        ]

    last_page = metadata.last_page
    if max_pages is not None:
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")
        last_page = min(last_page, max_pages)

    return [
        IndexRequest(
            source_name=source_name,
            page=page,
            source_url=_replace_page(first_page_url, page),
            reason="INDEX_PAGE",
        )
        for page in range(1, last_page + 1)
    ]


def assess_index_quality(
    records: list[SourceIndexRecord],
    *,
    expected_segment: str,
) -> IndexQuality:
    keys = [record.source_key for record in records]
    duplicate_keys = len(keys) - len(set(keys))
    missing_names = sum(not _clean(record.entity_name) for record in records)
    invalid_urls = 0
    for record in records:
        extracted = _numeric_key_from_path(record.detail_url, expected_segment)
        if extracted != record.source_key:
            invalid_urls += 1
    cores = {
        normalize_company_core(record.entity_name)
        for record in records
        if normalize_company_core(record.entity_name)
    }
    return IndexQuality(
        records=len(records),
        duplicate_keys=duplicate_keys,
        missing_names=missing_names,
        invalid_detail_urls=invalid_urls,
        unique_name_cores=len(cores),
    )
