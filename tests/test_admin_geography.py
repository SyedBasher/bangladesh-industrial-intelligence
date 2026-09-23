from pathlib import Path

from bii.admin_geography import (
    AdminLevel,
    AdministrativeGeographyCrosswalk,
    GeoAlias,
    GeoMatchStatus,
    ddm_aware_default_aliases,
    load_normalized_bbs_geocode_csv,
)


FIXTURE = Path(__file__).parent / "fixtures" / "bbs_geocode_minimal.csv"


def _crosswalk():
    units = load_normalized_bbs_geocode_csv(
        FIXTURE,
        source_vintage="synthetic-test",
    )
    aliases = ddm_aware_default_aliases(units)
    return units, AdministrativeGeographyCrosswalk(units, aliases)


def test_bbs_crosswalk_resolves_english_and_bangla_to_same_district():
    units, crosswalk = _crosswalk()
    english = crosswalk.resolve_district("Gazipur", division="Dhaka")
    bangla = crosswalk.resolve_district("গাজীপুর", division="ঢাকা")

    assert english.status == GeoMatchStatus.EXACT_NAME
    assert bangla.status == GeoMatchStatus.EXACT_NAME
    assert english.geo_ref == bangla.geo_ref
    assert english.geo_ref == "BBS:DIST:30:33"


def test_normalization_removes_admin_suffix_but_does_not_fuzzy_match():
    _, crosswalk = _crosswalk()
    exact = crosswalk.resolve_district("Gazipur District", division="Dhaka")
    assert exact.status == GeoMatchStatus.EXACT_NAME

    miss = crosswalk.resolve_district("Gajipur", division="Dhaka")
    assert miss.status == GeoMatchStatus.NO_MATCH


def test_ddm_shortened_nawabganj_is_approved_alias_only():
    units, crosswalk = _crosswalk()
    alias = crosswalk.resolve_district("Nawabganj", division="Rajshahi")
    assert alias.status == GeoMatchStatus.APPROVED_ALIAS
    assert alias.geo_ref == "BBS:DIST:50:70"
    assert alias.unit is not None
    assert alias.unit.district_name_en == "Chapai Nawabganj"

    without_alias = AdministrativeGeographyCrosswalk(units)
    miss = without_alias.resolve_district("Nawabganj", division="Rajshahi")
    assert miss.status == GeoMatchStatus.NO_MATCH


def test_upazila_resolution_requires_parent_context():
    _, crosswalk = _crosswalk()
    match = crosswalk.resolve_upazila(
        "টঙ্গী",
        district="গাজীপুর",
        division="ঢাকা",
    )
    assert match.status == GeoMatchStatus.EXACT_NAME
    assert match.geo_ref == "BBS:UPZ:30:33:94"


def test_alias_must_point_to_known_same_level_unit():
    units, _ = _crosswalk()
    try:
        AdministrativeGeographyCrosswalk(
            units,
            [
                GeoAlias(
                    level=AdminLevel.UPAZILA,
                    alias="Wrong level",
                    geo_ref="BBS:DIST:30:33",
                    source_name="test",
                    note="invalid on purpose",
                )
            ],
        )
    except ValueError as exc:
        assert "level" in str(exc).lower()
    else:
        raise AssertionError("expected alias level mismatch to fail")
