from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup


DIMENSION_ALIASES = {
    "industry_id": "INDUSTRIAL_SECTOR",
    "district": "DISTRICT",
    "upazila": "UPAZILA",
    "category": "CLASS_CATEGORY",
    "status": "STATUS",
}


@dataclass(frozen=True)
class FilterOption:
    dimension: str
    source_value: str
    source_label: str


def parse_filter_taxonomy(html: str) -> list[FilterOption]:
    """Extract current public filter labels and values from DIFE/LIMA HTML.

    Internal source values are metadata, not stable business identifiers. Production
    logic should preserve both the current source value and human-readable source label.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[FilterOption] = []

    for select in soup.find_all("select"):
        name = (select.get("name") or select.get("id") or "").strip()
        if not name:
            continue
        dimension = DIMENSION_ALIASES.get(name, name.upper())
        for option in select.find_all("option"):
            value = (option.get("value") or "").strip()
            label = " ".join(option.get_text(" ", strip=True).split())
            if not value or not label:
                continue
            out.append(FilterOption(dimension, value, label))

    return out
