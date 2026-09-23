from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .collector import CollectionError, PoliteHttpCollector
from .local_store import LocalValidationStore


@dataclass(frozen=True)
class ExternalDetailRunSummary:
    source_name: str
    attempted: int
    fetched: int
    failed: int
    raw_directory: str


def _safe(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
    return cleaned.strip("_") or "source"


def run_external_detail_requests(
    store: LocalValidationStore,
    collector: PoliteHttpCollector,
    *,
    source_name: str,
    raw_root: str | Path,
    max_records: int | None = None,
) -> ExternalDetailRunSummary:
    """Stage each planned external profile at most once.

    Requests are already deduplicated by source + stable source key + detail URL.
    Raw HTML stays in the private/gitignored storage tree.
    """
    source_name = source_name.upper()
    requests = store.external_detail_requests(source_name, status="PLANNED")
    if max_records is not None:
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        requests = requests[:max_records]

    raw_directory = Path(raw_root) / "external_detail" / _safe(source_name)
    raw_directory.mkdir(parents=True, exist_ok=True)

    fetched = 0
    failed = 0

    for request in requests:
        request_id = int(request["request_id"])
        source_key = str(request["source_key"])
        detail_url = str(request["detail_url"])
        try:
            result = collector.fetch_text(detail_url)
            payload_hash = hashlib.sha256(result.text.encode("utf-8")).hexdigest()
            raw_path = raw_directory / f"{_safe(source_key)}_{payload_hash[:16]}.html"
            raw_path.write_text(result.text, encoding="utf-8")

            staged = store.ingest_external_record_html(
                source_name,
                result.text,
                source_url=detail_url,
                retrieved_at=result.retrieved_at,
            )
            store.mark_external_detail_fetched(
                request_id,
                external_record_id=int(staged["external_record_id"]),
                resolved_at=result.retrieved_at,
            )
            fetched += 1
        except CollectionError as exc:
            store.mark_external_detail_failed(
                request_id,
                resolved_at=collector.now_iso(),
                error_message=str(exc),
            )
            failed += 1

    return ExternalDetailRunSummary(
        source_name=source_name,
        attempted=len(requests),
        fetched=fetched,
        failed=failed,
        raw_directory=str(raw_directory),
    )
