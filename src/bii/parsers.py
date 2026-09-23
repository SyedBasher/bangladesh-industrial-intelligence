from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup


_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def bengali_digits_to_ascii(value: str | None) -> str:
    return (value or "").translate(_BN_DIGITS)


def parse_int_mixed(value: str | None) -> int | None:
    if not value:
        return None
    normalized = bengali_digits_to_ascii(value).replace(",", "")
    match = re.search(r"\d+", normalized)
    return int(match.group(0)) if match else None


@dataclass(frozen=True)
class DifeListMetadata:
    total_records: int | None = None
    showing_records: int | None = None
    source_reported_at_raw: str | None = None


@dataclass(frozen=True)
class DifeListRecord:
    public_id: int
    name: str
    sector: str | None
    location: str | None
    upazila: str | None
    district: str | None
    division: str | None
    licence_class: str | None
    status: str | None
    detail_url: str


@dataclass(frozen=True)
class DifeDetailRecord:
    name_en: str | None
    name_bn: str | None
    address: str | None
    upazila: str | None
    district: str | None
    division: str | None
    status: str | None
    licence_expiry_raw: str | None
    sector: str | None
    licence_no: str | None
    old_licence_no: str | None
    registration_no: str | None
    old_registration_no: str | None
    licence_class: str | None
    establishment_type: str | None
    worker_component_1: int | None
    worker_component_2: int | None
    worker_total: int | None


def extract_public_id(href: str) -> int | None:
    match = re.search(r"/public-report/establishment/(\d+)(?:[/?#]|$)", href)
    return int(match.group(1)) if match else None


def _parse_location(location: str | None) -> tuple[str | None, str | None, str | None]:
    parts = [part.strip() for part in (location or "").split(",") if part.strip()]
    if len(parts) < 3:
        return None, None, None
    return parts[-3], parts[-2], parts[-1]


def parse_dife_list_page(
    html: str,
    base_url: str = "https://lima.dife.gov.bd",
) -> tuple[DifeListMetadata, list[DifeListRecord]]:
    """Parse one public DIFE/LIMA establishment-list page.

    IDs are accepted only when explicitly exposed in public establishment links.
    Internal IDs are never guessed or generated sequentially.
    """
    soup = BeautifulSoup(html, "html.parser")
    records: list[DifeListRecord] = []
    seen: set[int] = set()

    for row in soup.select("tr"):
        link = row.find("a", href=re.compile(r"/public-report/establishment/\d+"))
        if not link:
            continue
        public_id = extract_public_id(link.get("href", ""))
        if public_id is None or public_id in seen:
            continue

        cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        if len(cells) < 5:
            continue

        name = _clean(link.get_text(" ", strip=True)) or cells[0] or ""
        sector, location, licence_class, status = cells[1:5]
        upazila, district, division = _parse_location(location)
        records.append(
            DifeListRecord(
                public_id=public_id,
                name=name,
                sector=sector,
                location=location,
                upazila=upazila,
                district=district,
                division=division,
                licence_class=licence_class,
                status=status,
                detail_url=urljoin(base_url, link["href"]),
            )
        )
        seen.add(public_id)

    text = soup.get_text(" ", strip=True)
    total_records = None
    showing_records = None
    source_reported_at_raw = None

    match = re.search(r"প্রাপ্ত তথ্য\s*:\s*([০-৯\d,]+)\s*টি", text)
    if match:
        total_records = parse_int_mixed(match.group(1))

    match = re.search(r"দেখাচ্ছে\s*:\s*([০-৯\d,]+)\s*টি", text)
    if match:
        showing_records = parse_int_mixed(match.group(1))

    source_lines = [_clean(item) for item in soup.stripped_strings]
    source_lines = [item for item in source_lines if item]
    label = "প্রতিবেদন তৈরির তারিখ এবং সময়"
    for index, line in enumerate(source_lines):
        if label not in line:
            continue
        tail = line.split(label, 1)[1].lstrip(" :")
        if tail:
            source_reported_at_raw = _clean(tail)
        elif index + 1 < len(source_lines):
            source_reported_at_raw = source_lines[index + 1]
        break

    return DifeListMetadata(total_records, showing_records, source_reported_at_raw), records


def parse_dife_list(html: str, base_url: str = "https://lima.dife.gov.bd") -> list[DifeListRecord]:
    """Compatibility wrapper returning only records."""
    return parse_dife_list_page(html, base_url=base_url)[1]


def _line_value(lines: list[str], label: str) -> str | None:
    for index, line in enumerate(lines):
        if line == label or line.rstrip(":") == label.rstrip(":"):
            if index + 1 < len(lines):
                return lines[index + 1]
        if line.startswith(label) and line != label:
            tail = line[len(label):].lstrip(" :")
            if tail:
                return tail
    return None


def parse_dife_detail(html: str) -> DifeDetailRecord:
    """Parse public fields from a DIFE/LIMA establishment detail page.

    Missing source fields remain None. The parser does not infer operational status
    from licence expiry and does not synthesize employment values.
    """
    soup = BeautifulSoup(html, "html.parser")
    lines = [_clean(line) for line in soup.get_text("\n", strip=True).splitlines()]
    lines = [line for line in lines if line]

    heading = soup.find("h2")
    title = _clean(heading.get_text(" ", strip=True)) if heading else None
    name_en = None
    name_bn = None
    if title:
        match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", title)
        if match:
            name_en = match.group(1).strip()
            name_bn = match.group(2).strip()
        else:
            name_en = title

    joined = " | ".join(lines)
    address = _line_value(lines, "পূর্ণ ঠিকানা")

    upazila = district = division = None
    match = re.search(
        r"উপজেলা\s*:\s*([^,|]+),\s*জেলা\s*:\s*([^,|]+),\s*বিভাগ\s*:\s*([^|]+?)(?:বর্তমান অবস্থা|\|)",
        joined,
    )
    if match:
        upazila, district, division = (part.strip() for part in match.groups())

    status = None
    for index, line in enumerate(lines):
        if "বর্তমান অবস্থা" in line:
            for candidate in lines[index + 1:index + 4]:
                if candidate not in {"মেয়াদ", "ইন্ডাস্ট্রিয়াল সেক্টর:"}:
                    status = candidate
                    break
            break

    licence_expiry_raw = _line_value(lines, "মেয়াদ")
    sector = _line_value(lines, "ইন্ডাস্ট্রিয়াল সেক্টর:")
    licence_no = _line_value(lines, "লাইসেন্স নম্বর:")
    old_licence_no = _line_value(lines, "পুরোন লাইসেন্স নম্বর:")
    registration_no = _line_value(lines, "রেজিস্ট্রেশন নম্বর:")
    old_registration_no = _line_value(lines, "পুরোন রেজিস্ট্রেশন নম্বর:")

    class_raw = _line_value(lines, "শ্রেণী:")
    licence_class = None
    establishment_type = None
    if class_raw:
        match = re.match(r"(.+?)\s*\((.+?)\)\s*$", class_raw)
        if match:
            licence_class = match.group(1).strip()
            establishment_type = match.group(2).strip()
        else:
            licence_class = class_raw

    worker_raw = _line_value(lines, "মোট শ্রমিকের সংখ্যা:")
    worker_component_1 = None
    worker_component_2 = None
    worker_total = None
    if worker_raw:
        normalized = bengali_digits_to_ascii(worker_raw)
        match = re.search(r"(\d+)\s*\+\s*(\d+)\s*=\s*(\d+)", normalized)
        if match:
            worker_component_1, worker_component_2, worker_total = map(int, match.groups())
        else:
            worker_total = parse_int_mixed(normalized)

    return DifeDetailRecord(
        name_en=name_en,
        name_bn=name_bn,
        address=address,
        upazila=upazila,
        district=district,
        division=division,
        status=status,
        licence_expiry_raw=licence_expiry_raw,
        sector=sector,
        licence_no=licence_no,
        old_licence_no=old_licence_no,
        registration_no=registration_no,
        old_registration_no=old_registration_no,
        licence_class=licence_class,
        establishment_type=establishment_type,
        worker_component_1=worker_component_1,
        worker_component_2=worker_component_2,
        worker_total=worker_total,
    )
