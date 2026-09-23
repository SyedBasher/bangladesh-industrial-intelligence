from bii.enrichment import (
    DifeMatchRecord,
    address_result,
    decide_external_link,
    name_strength,
)
from bii.external_sources import ExternalRecordPayload
from bii.matching import MatchType


def _dife(**overrides):
    values = dict(
        public_id=100,
        name="Example Garments Limited",
        address="Tongi Industrial Area, Gazipur",
        district="Gazipur",
        upazila="Tongi",
        sector_family="RMG_TEXTILE",
    )
    values.update(overrides)
    return DifeMatchRecord(**values)


def _external(source_name="BGMEA", **overrides):
    values = dict(
        source_name=source_name,
        external_key="123",
        entity_name="Example Garments Ltd.",
        site_text="Tongi Industrial Area, Gazipur",
        district="Gazipur",
        upazila="Tongi",
        source_url="https://example.invalid/123",
        source_updated_at_raw=None,
        source_fields={},
    )
    values.update(overrides)
    return ExternalRecordPayload(**values)


def test_transparent_name_strength():
    assert name_strength("Example Industries Ltd.", "Example") == "exact"
    assert name_strength("Example Garments Ltd.", "Example Garments Unit 1") in {"strong", "weak"}


def test_exact_site_requires_site_evidence():
    decision = decide_external_link(_dife(), _external())
    assert decision.match_type == MatchType.EXACT_SITE
    assert decision.site_level_match is True


def test_district_conflict_downgrades_to_organization_only():
    decision = decide_external_link(
        _dife(),
        _external(district="Dhaka", site_text="Tejgaon, Dhaka", upazila="Tejgaon"),
    )
    assert decision.match_type == MatchType.ORGANIZATION_ONLY
    assert decision.site_level_match is False


def test_bkmea_is_capped_at_organization_level_even_when_geography_matches():
    decision = decide_external_link(_dife(), _external(source_name="BKMEA"))
    assert decision.match_type == MatchType.ORGANIZATION_ONLY
    assert decision.site_level_match is False


def test_out_of_scope_source_returns_no_match_not_negative_business_claim():
    decision = decide_external_link(
        _dife(sector_family="FOOD_AGRO"),
        _external(source_name="BGMEA"),
    )
    assert decision.match_type == MatchType.NO_MATCH
    assert decision.evidence[0].result == "OUT_OF_SCOPE"


def test_multiple_candidates_remains_ambiguous():
    decision = decide_external_link(
        _dife(),
        _external(),
        multiple_candidates=True,
    )
    assert decision.match_type == MatchType.AMBIGUOUS


def test_address_overlap_is_exposed_not_hidden_score():
    result, overlap = address_result(
        "Tongi Industrial Area Gazipur",
        "Tongi Industrial Area, Gazipur",
    )
    assert result == "strong"
    assert overlap == 1.0
