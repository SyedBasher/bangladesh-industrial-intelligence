from __future__ import annotations

import email.utils
import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .policy import SourceAccessPolicy


@dataclass(frozen=True)
class FetchResult:
    url: str
    http_status: int
    text: str
    retrieved_at: str
    content_sha256: str
    attempts: int


class CollectionError(RuntimeError):
    def __init__(self, url: str, message: str, *, retryable: bool):
        self.url = url
        self.retryable = retryable
        super().__init__(message)


class PoliteHttpCollector:
    """Single-threaded, rate-limited HTTP GET collector.

    The collector cannot make a request until an explicit reviewed source policy is
    supplied. Public visibility alone never flips that policy to allowed.
    """

    RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        policy: SourceAccessPolicy,
        *,
        opener: Callable[..., object] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        max_response_bytes: int = 5_000_000,
    ):
        self.policy = policy
        self.policy.assert_live_collection_allowed()
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._now = now_fn
        self._last_request_at: float | None = None
        self.max_response_bytes = max_response_bytes

    @property
    def minimum_interval_seconds(self) -> float:
        return 60.0 / self.policy.requests_per_minute

    def now_iso(self) -> str:
        return self._now().isoformat()

    def _rate_limit(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            wait = self.minimum_interval_seconds - (now - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._monotonic()

    def _retry_after_seconds(self, headers: object | None) -> float | None:
        if headers is None:
            return None
        value = getattr(headers, "get", lambda _key: None)("Retry-After")
        if not value:
            return None
        value = str(value).strip()
        if value.isdigit():
            return max(0.0, float(value))
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (parsed - self._now()).total_seconds())
        except (TypeError, ValueError):
            return None

    def fetch_text(self, url: str) -> FetchResult:
        self.policy.assert_url_allowed(url)
        last_error: Exception | None = None

        for attempt in range(1, self.policy.max_retries + 2):
            self._rate_limit()
            request = urllib.request.Request(
                url,
                method="GET",
                headers={
                    "User-Agent": self.policy.user_agent,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "bn,en;q=0.8",
                },
            )
            try:
                response = self._opener(request, timeout=self.policy.timeout_seconds)
                with response:
                    status = int(getattr(response, "status", 200))
                    payload = response.read(self.max_response_bytes + 1)
                    if len(payload) > self.max_response_bytes:
                        raise CollectionError(
                            url,
                            f"response exceeded {self.max_response_bytes} bytes",
                            retryable=False,
                        )
                    charset = "utf-8"
                    headers = getattr(response, "headers", None)
                    if headers is not None:
                        detected = getattr(headers, "get_content_charset", lambda: None)()
                        if detected:
                            charset = detected
                    text = payload.decode(charset, errors="replace")
                    retrieved_at = self._now().isoformat()
                    return FetchResult(
                        url=url,
                        http_status=status,
                        text=text,
                        retrieved_at=retrieved_at,
                        content_sha256=hashlib.sha256(payload).hexdigest(),
                        attempts=attempt,
                    )
            except urllib.error.HTTPError as exc:
                last_error = exc
                retryable = exc.code in self.RETRYABLE_STATUS
                if not retryable or attempt > self.policy.max_retries:
                    raise CollectionError(
                        url,
                        f"HTTP {exc.code} after {attempt} attempt(s)",
                        retryable=retryable,
                    ) from exc
                retry_after = self._retry_after_seconds(exc.headers)
                self._sleep(
                    retry_after if retry_after is not None else min(30.0, 2.0 ** (attempt - 1))
                )
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt > self.policy.max_retries:
                    raise CollectionError(
                        url,
                        f"network error after {attempt} attempt(s): {exc.reason}",
                        retryable=True,
                    ) from exc
                self._sleep(min(30.0, 2.0 ** (attempt - 1)))

        raise CollectionError(
            url,
            f"collection failed: {last_error}",
            retryable=True,
        )
