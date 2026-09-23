from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class DifeListRecord:
    public_id: int
    name: str
    sector: str | None
    location: str | None
    licence_class: str | None
    status: str | None
    detail_url: str


def _clean(value: str | None) -> str:
    return " ".join((value or "").split())


def extract_public_id(href: str) -> int | None:
    m = re.search(r"/public-report/establishment/(\d+)(?:[/?#]|$)", href)
    return int(m.group(1)) if m else None


def parse_dife_list(html: str, base_url: str = "https://lima.dife.gov.bd") -> list[DifeListRecord]:
    """Parse establishment rows from a public DIFE/LIMA list page.

    The parser only accepts IDs exposed in public establishment detail links; it
    never manufactures or probes sequential IDs.
    """
    soup = BeautifulSoup(html, "html.parser")
    records: list[DifeListRecord] = []

    for row in soup.select("tr"):
        link = row.find("a", href=re.compile(r"/public-report/establishment/\d+"))
        if not link:
            continue
        public_id = extract_public_id(link.get("href", ""))
        if public_id is None:
            continue
        cells = [_clean(td.get_text(" ", strip=True)) for td in row.find_all("td")]
        if not cells:
            continue
        name = _clean(link.get_text(" ", strip=True)) or cells[0]
        sector = cells[1] if len(cells) > 1 else None
        location = cells[2] if len(cells) > 2 else None
        licence_class = cells[3] if len(cells) > 3 else None
        status = cells[4] if len(cells) > 4 else None
        records.append(
            DifeListRecord(
                public_id=public_id,
                name=name,
                sector=sector,
                location=location,
                licence_class=licence_class,
                status=status,
                detail_url=urljoin(base_url, link["href"]),
            )
        )
    return records
