import io
import urllib.error

import pytest

from bii.collector import CollectionError, PoliteHttpCollector
from bii.policy import AccessDecision, SourceAccessPolicy


class Headers(dict):
    def get_content_charset(self):
        return "utf-8"


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = Headers()

    def read(self, n=-1):
        return self.body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _policy(**overrides):
    values = dict(
        source_name="DIFE/LIMA",
        decision=AccessDecision.REVIEWED_ALLOWED,
        reviewed_at="2026-09-23T22:10:00+06:00",
        review_note="Reviewed for synthetic tests.",
        allowed_hosts=("lima.dife.gov.bd",),
        allowed_path_prefixes=("/public-report/",),
        requests_per_minute=60,
        max_retries=2,
        timeout_seconds=10,
    )
    values.update(overrides)
    return SourceAccessPolicy(**values)


def test_collector_fetches_with_policy_and_hashes_response():
    seen = []
    def opener(request, timeout):
        seen.append((request.full_url, request.get_method(), timeout))
        return FakeResponse("বাংলা".encode("utf-8"))

    collector = PoliteHttpCollector(
        _policy(),
        opener=opener,
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    result = collector.fetch_text(
        "https://lima.dife.gov.bd/public-report/establishment/123"
    )
    assert result.text == "বাংলা"
    assert result.http_status == 200
    assert result.attempts == 1
    assert len(result.content_sha256) == 64
    assert seen[0][1] == "GET"


def test_collector_retries_retryable_http_error():
    attempts = {"n": 0}
    def opener(request, timeout):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                Headers({"Retry-After": "0"}),
                None,
            )
        return FakeResponse(b"ok")

    collector = PoliteHttpCollector(
        _policy(),
        opener=opener,
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    result = collector.fetch_text(
        "https://lima.dife.gov.bd/public-report/establishment/123"
    )
    assert result.text == "ok"
    assert result.attempts == 2


def test_non_retryable_http_error_is_recorded_as_collection_error():
    def opener(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            404,
            "Not Found",
            Headers(),
            None,
        )

    collector = PoliteHttpCollector(
        _policy(),
        opener=opener,
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    with pytest.raises(CollectionError) as exc:
        collector.fetch_text(
            "https://lima.dife.gov.bd/public-report/establishment/123"
        )
    assert exc.value.retryable is False


def test_collector_rejects_oversized_response():
    collector = PoliteHttpCollector(
        _policy(),
        opener=lambda request, timeout: FakeResponse(b"x" * 11),
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: 0.0,
        max_response_bytes=10,
    )
    with pytest.raises(CollectionError) as exc:
        collector.fetch_text(
            "https://lima.dife.gov.bd/public-report/establishment/123"
        )
    assert exc.value.retryable is False
