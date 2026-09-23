from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class MatchType(StrEnum):
    EXACT_SITE = "EXACT_SITE"
    PROBABLE_SITE = "PROBABLE_SITE"
    ORGANIZATION_ONLY = "ORGANIZATION_ONLY"
    AMBIGUOUS = "AMBIGUOUS"
    NO_MATCH = "NO_MATCH"
    SOURCE_FEASIBILITY_ONLY = "SOURCE_FEASIBILITY_ONLY"


_CORPORATE_TOKENS = {
    "limited", "ltd", "ltd.", "company", "co", "co.", "bangladesh",
    "industries", "industry", "group", "plc", "private", "pvt",
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def normalize_company_core(value: str | None) -> str:
    tokens = [t for t in normalize_text(value).split() if t not in _CORPORATE_TOKENS]
    return " ".join(tokens)


@dataclass(frozen=True)
class MatchEvidence:
    name_strength: str  # exact | strong | weak | missing
    district: str  # match | conflict | missing
    upazila: str  # match | conflict | missing
    address: str  # strong | consistent | conflict | missing
    multiple_candidates: bool = False


def classify_match(e: MatchEvidence) -> MatchType:
    """Apply transparent site-vs-organization rules.

    This intentionally avoids an opaque scalar confidence score.
    """
    if e.multiple_candidates:
        return MatchType.AMBIGUOUS

    strong_identity = e.name_strength in {"exact", "strong"}
    if not strong_identity:
        return MatchType.NO_MATCH

    if e.district == "conflict" or e.upazila == "conflict" or e.address == "conflict":
        return MatchType.ORGANIZATION_ONLY

    if e.district == "match" and (e.upazila == "match" or e.address == "strong"):
        return MatchType.EXACT_SITE

    if e.district == "match" and e.address in {"consistent", "missing"}:
        return MatchType.PROBABLE_SITE

    return MatchType.ORGANIZATION_ONLY
