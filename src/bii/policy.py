from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse


class AccessDecision(StrEnum):
    UNKNOWN = "UNKNOWN"
    REVIEWED_ALLOWED = "REVIEWED_ALLOWED"
    REVIEWED_RESTRICTED = "REVIEWED_RESTRICTED"


class AccessPolicyError(PermissionError):
    pass


@dataclass(frozen=True)
class SourceAccessPolicy:
    source_name: str
    decision: AccessDecision
    reviewed_at: str | None
    review_note: str
    allowed_hosts: tuple[str, ...]
    allowed_path_prefixes: tuple[str, ...]
    requests_per_minute: float = 20.0
    max_retries: int = 2
    timeout_seconds: float = 20.0
    user_agent: str = "BangladeshIndustrialIntelligence/0.11 (+public-data-validation)"

    def assert_live_collection_allowed(self) -> None:
        if self.decision != AccessDecision.REVIEWED_ALLOWED:
            raise AccessPolicyError(
                f"{self.source_name} live collection is not approved: {self.decision}"
            )
        if not self.reviewed_at or not self.review_note.strip():
            raise AccessPolicyError(
                f"{self.source_name} approval requires reviewed_at and a non-empty review_note"
            )
        if self.requests_per_minute <= 0:
            raise AccessPolicyError("requests_per_minute must be positive")
        if self.max_retries < 0:
            raise AccessPolicyError("max_retries cannot be negative")

    def assert_url_allowed(self, url: str) -> None:
        self.assert_live_collection_allowed()
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https":
            raise AccessPolicyError("only HTTPS source URLs are allowed")
        if host not in {item.casefold() for item in self.allowed_hosts}:
            raise AccessPolicyError(f"source host is outside the reviewed allowlist: {host}")
        if not any(parsed.path.startswith(prefix) for prefix in self.allowed_path_prefixes):
            raise AccessPolicyError(
                f"source path is outside the reviewed allowlist: {parsed.path}"
            )


DIFE_POLICY_TEMPLATE = SourceAccessPolicy(
    source_name="DIFE/LIMA",
    decision=AccessDecision.UNKNOWN,
    reviewed_at=None,
    review_note=(
        "Public report pages were verified during feasibility work, but a clear "
        "automation/commercial-reuse permission has not yet been recorded."
    ),
    allowed_hosts=("lima.dife.gov.bd",),
    allowed_path_prefixes=("/public-report/",),
    requests_per_minute=20.0,
    max_retries=2,
    timeout_seconds=20.0,
)
