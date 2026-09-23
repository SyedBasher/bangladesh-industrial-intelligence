from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Iterable


class AdminLevel(StrEnum):
    DIVISION = "DIVISION"
    DISTRICT = "DISTRICT"
    UPAZILA = "UPAZILA"


class GeoMatchStatus(StrEnum):
    EXACT_NAME = "EXACT_NAME"
    APPROVED_ALIAS = "APPROVED_ALIAS"
    AMBIGUOUS = "AMBIGUOUS"
    NO_MATCH = "NO_MATCH"


@dataclass(frozen=True)
class AdminUnit:
    geo_ref: str
    level: AdminLevel
    division_code: str
    division_name_en: str
    division_name_bn: str | None = None
    district_code: str | None = None
    district_name_en: str | None = None
    district_name_bn: str | None = None
    upazila_code: str | None = None
    upazila_name_en: str | None = None
    upazila_name_bn: str | None = None
    source_name: str = "Bangladesh Bureau of Statistics"
    source_vintage: str | None = None


@dataclass(frozen=True)
class GeoAlias:
    level: AdminLevel
    alias: str
    geo_ref: str
    source_name: str
    note: str


@dataclass(frozen=True)
class GeoMatch:
    status: GeoMatchStatus
    level: AdminLevel
    query: str
    geo_ref: str | None
    matched_name: str | None
    matched_on: str | None
    unit: AdminUnit | None


NORMALIZED_BBS_COLUMNS = (
    "division_code",
    "division_name_en",
    "division_name_bn",
    "district_code",
    "district_name_en",
    "district_name_bn",
    "upazila_code",
    "upazila_name_en",
    "upazila_name_bn",
)


def normalize_admin_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    text = text.casefold().strip()
    text = re.sub(r"[.,;:_/\\()\[\]{}-]+", " ", text)
    text = text.replace("'", "")
    text = re.sub(r"\b(district|zila|zilla|upazila|upozilla|thana|division)\b", " ", text)
    return " ".join(text.split())


def make_geo_ref(
    level: AdminLevel,
    *,
    division_code: str,
    district_code: str | None = None,
    upazila_code: str | None = None,
) -> str:
    division = str(division_code).strip()
    if not division:
        raise ValueError("division_code is required")
    if level == AdminLevel.DIVISION:
        return f"BBS:DIV:{division}"
    district = str(district_code or "").strip()
    if not district:
        raise ValueError("district_code is required")
    if level == AdminLevel.DISTRICT:
        return f"BBS:DIST:{division}:{district}"
    upazila = str(upazila_code or "").strip()
    if not upazila:
        raise ValueError("upazila_code is required")
    return f"BBS:UPZ:{division}:{district}:{upazila}"


def load_normalized_bbs_geocode_csv(
    path: str | Path,
    *,
    source_vintage: str | None = None,
) -> list[AdminUnit]:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("BBS geography CSV has no header")
        missing = [
            column for column in NORMALIZED_BBS_COLUMNS
            if column not in reader.fieldnames
        ]
        if missing:
            raise ValueError(
                "BBS geography CSV missing canonical columns: " + ", ".join(missing)
            )

        divisions: dict[str, AdminUnit] = {}
        districts: dict[tuple[str, str], AdminUnit] = {}
        upazilas: dict[tuple[str, str, str], AdminUnit] = {}

        for line_no, raw in enumerate(reader, start=2):
            division_code = (raw.get("division_code") or "").strip()
            division_name_en = (raw.get("division_name_en") or "").strip()
            division_name_bn = (raw.get("division_name_bn") or "").strip() or None
            district_code = (raw.get("district_code") or "").strip() or None
            district_name_en = (raw.get("district_name_en") or "").strip() or None
            district_name_bn = (raw.get("district_name_bn") or "").strip() or None
            upazila_code = (raw.get("upazila_code") or "").strip() or None
            upazila_name_en = (raw.get("upazila_name_en") or "").strip() or None
            upazila_name_bn = (raw.get("upazila_name_bn") or "").strip() or None

            if not division_code or not division_name_en:
                raise ValueError(
                    f"division code/name missing at BBS geography CSV line {line_no}"
                )

            divisions.setdefault(
                division_code,
                AdminUnit(
                    geo_ref=make_geo_ref(
                        AdminLevel.DIVISION,
                        division_code=division_code,
                    ),
                    level=AdminLevel.DIVISION,
                    division_code=division_code,
                    division_name_en=division_name_en,
                    division_name_bn=division_name_bn,
                    source_vintage=source_vintage,
                ),
            )

            if district_code or district_name_en or district_name_bn:
                if not district_code or not district_name_en:
                    raise ValueError(
                        f"partial district geography at CSV line {line_no}"
                    )
                districts.setdefault(
                    (division_code, district_code),
                    AdminUnit(
                        geo_ref=make_geo_ref(
                            AdminLevel.DISTRICT,
                            division_code=division_code,
                            district_code=district_code,
                        ),
                        level=AdminLevel.DISTRICT,
                        division_code=division_code,
                        division_name_en=division_name_en,
                        division_name_bn=division_name_bn,
                        district_code=district_code,
                        district_name_en=district_name_en,
                        district_name_bn=district_name_bn,
                        source_vintage=source_vintage,
                    ),
                )

            if upazila_code or upazila_name_en or upazila_name_bn:
                if not district_code or not district_name_en:
                    raise ValueError(
                        f"upazila lacks district parent at CSV line {line_no}"
                    )
                if not upazila_code or not upazila_name_en:
                    raise ValueError(
                        f"partial upazila geography at CSV line {line_no}"
                    )
                upazilas.setdefault(
                    (division_code, district_code, upazila_code),
                    AdminUnit(
                        geo_ref=make_geo_ref(
                            AdminLevel.UPAZILA,
                            division_code=division_code,
                            district_code=district_code,
                            upazila_code=upazila_code,
                        ),
                        level=AdminLevel.UPAZILA,
                        division_code=division_code,
                        division_name_en=division_name_en,
                        division_name_bn=division_name_bn,
                        district_code=district_code,
                        district_name_en=district_name_en,
                        district_name_bn=district_name_bn,
                        upazila_code=upazila_code,
                        upazila_name_en=upazila_name_en,
                        upazila_name_bn=upazila_name_bn,
                        source_vintage=source_vintage,
                    ),
                )

    return [
        *sorted(divisions.values(), key=lambda unit: unit.geo_ref),
        *sorted(districts.values(), key=lambda unit: unit.geo_ref),
        *sorted(upazilas.values(), key=lambda unit: unit.geo_ref),
    ]


class AdministrativeGeographyCrosswalk:
    def __init__(
        self,
        units: Iterable[AdminUnit],
        aliases: Iterable[GeoAlias] = (),
    ):
        self.units = tuple(units)
        self.by_ref = {unit.geo_ref: unit for unit in self.units}
        if len(self.by_ref) != len(self.units):
            raise ValueError("duplicate canonical geography geo_ref")
        self.aliases = tuple(aliases)
        for alias in self.aliases:
            if alias.geo_ref not in self.by_ref:
                raise ValueError(
                    f"alias points to unknown canonical geography: {alias.geo_ref}"
                )
            if self.by_ref[alias.geo_ref].level != alias.level:
                raise ValueError("alias level does not match canonical geography level")

    def _names_for_unit(self, unit: AdminUnit) -> tuple[str | None, ...]:
        if unit.level == AdminLevel.DIVISION:
            return (unit.division_name_en, unit.division_name_bn)
        if unit.level == AdminLevel.DISTRICT:
            return (unit.district_name_en, unit.district_name_bn)
        return (unit.upazila_name_en, unit.upazila_name_bn)

    def _division_matches(self, unit: AdminUnit, division: str | None) -> bool:
        if not division:
            return True
        normalized = normalize_admin_name(division)
        return normalized in {
            normalize_admin_name(unit.division_name_en),
            normalize_admin_name(unit.division_name_bn),
        }

    def _district_parent_matches(self, unit: AdminUnit, district: str | None) -> bool:
        if not district:
            return True
        normalized = normalize_admin_name(district)
        if normalized in {
            normalize_admin_name(unit.district_name_en),
            normalize_admin_name(unit.district_name_bn),
        }:
            return True
        if unit.level != AdminLevel.UPAZILA or not unit.district_code:
            return False
        parent_ref = make_geo_ref(
            AdminLevel.DISTRICT,
            division_code=unit.division_code,
            district_code=unit.district_code,
        )
        return any(
            alias.level == AdminLevel.DISTRICT
            and alias.geo_ref == parent_ref
            and normalize_admin_name(alias.alias) == normalized
            for alias in self.aliases
        )

    def resolve(
        self,
        level: AdminLevel,
        name: str,
        *,
        division: str | None = None,
        district: str | None = None,
    ) -> GeoMatch:
        query = str(name or "").strip()
        normalized = normalize_admin_name(query)
        if not normalized:
            return GeoMatch(
                GeoMatchStatus.NO_MATCH, level, query, None, None, None, None
            )

        exact: list[tuple[AdminUnit, str]] = []
        for unit in self.units:
            if unit.level != level:
                continue
            if not self._division_matches(unit, division):
                continue
            if not self._district_parent_matches(unit, district):
                continue
            for candidate in self._names_for_unit(unit):
                if candidate and normalize_admin_name(candidate) == normalized:
                    exact.append((unit, candidate))

        refs = {unit.geo_ref for unit, _ in exact}
        if len(refs) == 1:
            unit, matched_name = exact[0]
            return GeoMatch(
                GeoMatchStatus.EXACT_NAME,
                level,
                query,
                unit.geo_ref,
                matched_name,
                "canonical_name",
                unit,
            )
        if len(refs) > 1:
            return GeoMatch(
                GeoMatchStatus.AMBIGUOUS,
                level,
                query,
                None,
                None,
                "canonical_name",
                None,
            )

        alias_refs = set()
        for alias in self.aliases:
            if alias.level != level:
                continue
            if normalize_admin_name(alias.alias) != normalized:
                continue
            unit = self.by_ref[alias.geo_ref]
            if not self._division_matches(unit, division):
                continue
            if not self._district_parent_matches(unit, district):
                continue
            alias_refs.add(alias.geo_ref)

        if len(alias_refs) == 1:
            geo_ref = next(iter(alias_refs))
            unit = self.by_ref[geo_ref]
            matched_name = next(
                (name for name in self._names_for_unit(unit) if name),
                None,
            )
            return GeoMatch(
                GeoMatchStatus.APPROVED_ALIAS,
                level,
                query,
                geo_ref,
                matched_name,
                "approved_alias",
                unit,
            )
        if len(alias_refs) > 1:
            return GeoMatch(
                GeoMatchStatus.AMBIGUOUS,
                level,
                query,
                None,
                None,
                "approved_alias",
                None,
            )

        return GeoMatch(
            GeoMatchStatus.NO_MATCH, level, query, None, None, None, None
        )

    def resolve_district(
        self,
        name: str,
        *,
        division: str | None = None,
    ) -> GeoMatch:
        return self.resolve(
            AdminLevel.DISTRICT,
            name,
            division=division,
        )

    def resolve_upazila(
        self,
        name: str,
        *,
        district: str,
        division: str | None = None,
    ) -> GeoMatch:
        return self.resolve(
            AdminLevel.UPAZILA,
            name,
            division=division,
            district=district,
        )


def ddm_aware_default_aliases(
    units: Iterable[AdminUnit],
) -> list[GeoAlias]:
    crosswalk = AdministrativeGeographyCrosswalk(units)
    candidates = [
        ("Jhalokati", "Jhalokathi", "DDM spelling variant"),
        ("Nawabganj", "Chapai Nawabganj", "DDM shortened district label"),
        ("Brahmmanbaria", "Brahmanbaria", "BBS/DDM English spelling variant"),
    ]
    aliases: list[GeoAlias] = []
    for alias, canonical_name, note in candidates:
        match = crosswalk.resolve_district(canonical_name)
        if match.status == GeoMatchStatus.EXACT_NAME and match.geo_ref:
            aliases.append(
                GeoAlias(
                    level=AdminLevel.DISTRICT,
                    alias=alias,
                    geo_ref=match.geo_ref,
                    source_name="DDM AWARE",
                    note=note,
                )
            )
    return aliases
