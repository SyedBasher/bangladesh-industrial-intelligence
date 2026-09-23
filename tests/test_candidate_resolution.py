from bii.candidate_resolution import (
    CandidateBlockIndex,
    CandidatePriority,
    CandidateRecord,
    ResolutionOutcome,
    candidate_priority,
    resolve_shortlist,
    shortlist_candidates,
)
from bii.enrichment import DifeMatchRecord
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


def _external(record_id, source_name="BGMEA", **overrides):
    values = dict(
        source_name=source_name,
        external_key=str(record_id),
        entity_name="Example Garments Ltd.",
        site_text="Tongi Industrial Area, Gazipur",
        district="Gazipur",
        upazila="Tongi",
        source_url=f"https://example.invalid/{record_id}",
        source_updated_at_raw=None,
        source_fields={},
    )
    values.update(overrides)
    return CandidateRecord(
        external_record_id=record_id,
        payload=ExternalRecordPayload(**values),
    )


def test_block_index_excludes_unrelated_staged_records():
    records = [
        _external(1),
        _external(2, entity_name="Example Garments Unit 2"),
        _external(3, entity_name="Completely Different Textiles PLC"),
    ]
    index = CandidateBlockIndex.build(records)
    blocked = index.records_for(_dife())
    assert [record.external_record_id for record in blocked] == [1, 2]


def test_priority_is_explicit_not_hidden_score():
    priority, signals = candidate_priority(_dife(), _external(1).payload)
    assert priority == CandidatePriority.EXACT_NAME_SITE
    assert signals.name_strength == "exact"
    assert signals.district_result == "match"
    assert signals.address_overlap == 1.0


def test_shortlist_prefers_exact_site_then_exact_name():
    candidates = shortlist_candidates(
        _dife(),
        [
            _external(3, entity_name="Example Garments Unit 2", district="Dhaka", upazila="Tejgaon"),
            _external(2, site_text=None, district=None, upazila=None),
            _external(1),
        ],
        max_candidates=3,
    )
    assert [candidate.external_record_id for candidate in candidates][0] == 1
    assert candidates[0].priority == CandidatePriority.EXACT_NAME_SITE


def test_unrelated_name_with_same_district_is_not_shortlisted():
    candidates = shortlist_candidates(
        _dife(),
        [
            _external(
                9,
                entity_name="Completely Different Textiles PLC",
                district="Gazipur",
                upazila="Tongi",
            )
        ],
    )
    assert candidates == []


def test_unique_site_match_auto_selects_even_with_weaker_alternative():
    dife = _dife()
    records = [
        _external(1),
        _external(
            2,
            entity_name="Example Garments Unit 2",
            district="Dhaka",
            upazila="Tejgaon",
            site_text="Tejgaon, Dhaka",
        ),
    ]
    decision = resolve_shortlist(dife, records)
    assert decision.outcome == ResolutionOutcome.AUTO_SELECTED
    assert decision.selected_external_record_id == 1
    assert decision.selected_match_type == MatchType.EXACT_SITE


def test_two_site_level_candidates_are_ambiguous():
    decision = resolve_shortlist(
        _dife(),
        [
            _external(1),
            _external(2, external_key="2"),
        ],
    )
    assert decision.outcome == ResolutionOutcome.AMBIGUOUS
    assert decision.selected_external_record_id is None


def test_unique_bkmea_org_match_auto_selects_at_org_level():
    decision = resolve_shortlist(
        _dife(),
        [_external(1, source_name="BKMEA")],
    )
    assert decision.outcome == ResolutionOutcome.AUTO_SELECTED
    assert decision.selected_match_type == MatchType.ORGANIZATION_ONLY


def test_empty_staged_shortlist_is_not_no_match():
    decision = resolve_shortlist(_dife(), [])
    assert decision.outcome == ResolutionOutcome.NO_STAGED_CANDIDATE
    assert decision.selected_match_type is None
    assert "no negative business fact" in decision.note.lower()


def test_candidates_without_positive_link_require_review():
    decision = resolve_shortlist(
        _dife(),
        [
            _external(
                3,
                entity_name="Example Holdings",
                district=None,
                upazila=None,
                site_text=None,
            )
        ],
    )
    assert decision.outcome == ResolutionOutcome.REVIEW_REQUIRED
