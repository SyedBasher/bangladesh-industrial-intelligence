from bii.matching import MatchEvidence, MatchType, classify_match, normalize_company_core


def test_company_normalization_removes_generic_corporate_tokens():
    assert normalize_company_core("Example Industries Limited") == "example"


def test_exact_site_requires_geography():
    e = MatchEvidence("exact", "match", "match", "consistent")
    assert classify_match(e) == MatchType.EXACT_SITE


def test_geographic_conflict_stays_organization_only():
    e = MatchEvidence("exact", "conflict", "missing", "conflict")
    assert classify_match(e) == MatchType.ORGANIZATION_ONLY


def test_multiple_candidates_is_ambiguous():
    e = MatchEvidence("strong", "match", "match", "strong", multiple_candidates=True)
    assert classify_match(e) == MatchType.AMBIGUOUS
