from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .collector import CollectionError, PoliteHttpCollector
from .local_store import LocalValidationStore


@dataclass(frozen=True)
class CheckpointRunSummary:
    validation_label: str
    checkpoint_n: int
    attempted: int
    parsed: int
    failed: int
    raw_directory: str


def _safe_label(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
    return cleaned.strip("_") or "validation"


def run_ready_detail_checkpoint(
    store: LocalValidationStore,
    collector: PoliteHttpCollector,
    *,
    validation_label: str,
    checkpoint_n: int,
    raw_root: str | Path,
    max_records: int | None = None,
) -> CheckpointRunSummary:
    """Collect only the currently authorized detail tranche.

    Raw HTML is written to a private local directory. The function never commits,
    uploads, or publishes raw source material.
    """
    requests = store.detail_requests_for_checkpoint(validation_label, checkpoint_n)
    if max_records is not None:
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        requests = requests[:max_records]

    raw_directory = (
        Path(raw_root)
        / "dife_detail"
        / _safe_label(validation_label)
        / f"checkpoint_{checkpoint_n}"
    )
    raw_directory.mkdir(parents=True, exist_ok=True)

    parsed = 0
    failed = 0

    for item in requests:
        public_id = int(item["dife_public_id"])
        source_url = str(item["source_url"])
        try:
            result = collector.fetch_text(source_url)
            payload_hash = hashlib.sha256(result.text.encode("utf-8")).hexdigest()
            raw_path = raw_directory / f"{public_id}_{payload_hash[:16]}.html"
            raw_path.write_text(result.text, encoding="utf-8")
            store.ingest_dife_detail_html(
                validation_label,
                public_id,
                result.text,
                source_url=source_url,
                retrieved_at=result.retrieved_at,
                raw_payload_path=str(raw_path),
            )
            parsed += 1
        except CollectionError as exc:
            store.mark_detail_request_failed(
                validation_label,
                public_id,
                resolved_at=collector.now_iso(),
                error_message=str(exc),
            )
            failed += 1

    return CheckpointRunSummary(
        validation_label=validation_label,
        checkpoint_n=checkpoint_n,
        attempted=len(requests),
        parsed=parsed,
        failed=failed,
        raw_directory=str(raw_directory),
    )
