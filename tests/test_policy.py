import pytest

from bii.policy import AccessDecision, AccessPolicyError, SourceAccessPolicy


def _policy(decision=AccessDecision.REVIEWED_ALLOWED):
    return SourceAccessPolicy(
        source_name="DIFE/LIMA",
        decision=decision,
        reviewed_at="2026-09-23T22:10:00+06:00" if decision == AccessDecision.REVIEWED_ALLOWED else None,
        review_note="Reviewed for test purposes." if decision == AccessDecision.REVIEWED_ALLOWED else "Not approved.",
        allowed_hosts=("lima.dife.gov.bd",),
        allowed_path_prefixes=("/public-report/",),
        requests_per_minute=20,
    )


def test_unknown_policy_blocks_live_collection():
    with pytest.raises(AccessPolicyError):
        _policy(AccessDecision.UNKNOWN).assert_live_collection_allowed()


def test_restricted_policy_blocks_live_collection():
    with pytest.raises(AccessPolicyError):
        _policy(AccessDecision.REVIEWED_RESTRICTED).assert_live_collection_allowed()


def test_allowed_policy_restricts_host_and_path():
    policy = _policy()
    policy.assert_url_allowed(
        "https://lima.dife.gov.bd/public-report/establishment/123"
    )
    with pytest.raises(AccessPolicyError):
        policy.assert_url_allowed("https://example.com/public-report/establishment/123")
    with pytest.raises(AccessPolicyError):
        policy.assert_url_allowed("https://lima.dife.gov.bd/admin/users")


def test_http_is_rejected_even_on_allowed_host():
    with pytest.raises(AccessPolicyError):
        _policy().assert_url_allowed(
            "http://lima.dife.gov.bd/public-report/establishment/123"
        )
