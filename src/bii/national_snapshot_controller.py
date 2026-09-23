from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .collector import CollectionError, PoliteHttpCollector
from .local_store import LocalValidationStore
from .national_universe import NationalSnapshotIntegrityError


@dataclass(frozen=True)
class NationalSnapshotBatchSummary:
    collection_run_id: int
    universe_id: int
    universe_label: str
    attempted: int
    staged: int
    failed: int
    pages_remaining: int
    failed_pages_remaining: int
    universe_status: str
    finalized: bool
    eligible_for_national_analysis: bool
    stop_reason: str
    raw_directory: str


def _safe_label(value: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "_"
        for ch in value
    )
    return cleaned.strip("_") or "national_snapshot"


def _ensure_manifest_expanded_if_seed_staged(
    store: LocalValidationStore,
    universe_id: int,
    *,
    planned_at: str,
) -> None:
    run = store.national_universe_run(universe_id)
    if run["status"] != "RUNNING":
        return
    if int(run["pages_planned"]) != 1:
        return

    page_one = store.conn.execute(
        """SELECT status FROM national_universe_pages
           WHERE universe_id=? AND page=1""",
        (universe_id,),
    ).fetchone()
    if (
        page_one is not None
        and page_one["status"] == "STAGED"
        and run["expected_total"] is not None
        and int(run["expected_total"]) > int(run["page_size"])
    ):
        store.expand_national_universe_run(
            universe_id,
            planned_at=planned_at,
        )


def run_national_snapshot_batch(
    store: LocalValidationStore,
    collector: PoliteHttpCollector,
    *,
    universe_id: int,
    raw_root: str | Path,
    max_pages: int = 50,
    auto_finalize: bool = True,
) -> NationalSnapshotBatchSummary:
    """Collect a bounded, restartable tranche of one declared national snapshot.

    Normal batch limits leave the universe RUNNING and the next call resumes from
    the first PLANNED page. A recoverable fetch/parser failure marks the page FAILED
    and stops the batch; the page must be explicitly requeued before retry. A source
    total drift, duplicate public ID, or impossible page cardinality aborts the
    entire universe because mixing those pages would invalidate national inference.
    """
    if max_pages <= 0:
        raise ValueError("max_pages must be positive")
    if collector.policy.source_name != "DIFE/LIMA":
        raise ValueError("national DIFE snapshot requires a DIFE/LIMA access policy")

    run = store.national_universe_run(universe_id)
    if run["status"] != "RUNNING":
        raise ValueError("national universe run is not RUNNING")

    universe_label = str(run["universe_label"])
    raw_directory = (
        Path(raw_root)
        / "dife_national"
        / _safe_label(universe_label)
        / f"universe_{universe_id}"
    )
    raw_directory.mkdir(parents=True, exist_ok=True)

    started_at = collector.now_iso()
    try:
        store.national_ingest_source(universe_id)
    except KeyError:
        store.record_national_ingest_source(
            universe_id,
            ingest_mode="LIVE_PAGINATED",
            artifact_path=None,
            artifact_sha256=None,
            manifest_json=None,
            imported_at=started_at,
        )

    _ensure_manifest_expanded_if_seed_staged(
        store,
        universe_id,
        planned_at=started_at,
    )

    policy_review_id = store.record_access_policy_review(
        collector.policy,
        recorded_at=started_at,
    )
    collection_run_id = store.start_national_snapshot_collection_run(
        universe_id=universe_id,
        policy_review_id=policy_review_id,
        started_at=started_at,
        max_pages=max_pages,
        raw_directory=str(raw_directory),
        notes="Private bounded DIFE national-list snapshot collection.",
    )

    attempted = 0
    staged = 0
    failed = 0
    stop_reason = "BATCH_LIMIT_REACHED"
    finalized = False

    try:
        while attempted < max_pages:
            progress = store.national_universe_progress(universe_id)
            failed_remaining = int(
                progress["page_status_counts"].get("FAILED", 0)
            )
            planned = store.national_universe_requests(
                universe_id,
                status="PLANNED",
            )

            if not planned:
                if failed_remaining:
                    stop_reason = "FAILED_PAGES_REQUIRE_EXPLICIT_REQUEUE"
                    break
                stop_reason = "NO_PLANNED_PAGES"
                break

            request = planned[0]
            page = int(request["page"])
            source_url = str(request["source_url"])
            attempted_at = collector.now_iso()
            attempted += 1

            try:
                result = collector.fetch_text(source_url)
            except CollectionError as exc:
                failed_at = collector.now_iso()
                store.mark_national_universe_page_failed(
                    universe_id,
                    source_url,
                    failed_at=failed_at,
                    error_message=str(exc),
                )
                store.record_national_snapshot_page_attempt(
                    collection_run_id=collection_run_id,
                    universe_id=universe_id,
                    page=page,
                    source_url=source_url,
                    attempted_at=attempted_at,
                    completed_at=failed_at,
                    status="COLLECTION_FAILED",
                    error_message=str(exc),
                )
                failed += 1
                stop_reason = "COLLECTION_FAILURE_REQUIRES_REQUEUE"
                store.finish_national_snapshot_collection_run(
                    collection_run_id,
                    completed_at=failed_at,
                    attempted=attempted,
                    staged=staged,
                    failed=failed,
                    status="FAILED",
                    stop_reason=stop_reason,
                )
                progress = store.national_universe_progress(universe_id)
                return NationalSnapshotBatchSummary(
                    collection_run_id=collection_run_id,
                    universe_id=universe_id,
                    universe_label=universe_label,
                    attempted=attempted,
                    staged=staged,
                    failed=failed,
                    pages_remaining=int(
                        progress["page_status_counts"].get("PLANNED", 0)
                    ),
                    failed_pages_remaining=int(
                        progress["page_status_counts"].get("FAILED", 0)
                    ),
                    universe_status=str(progress["status"]),
                    finalized=False,
                    eligible_for_national_analysis=False,
                    stop_reason=stop_reason,
                    raw_directory=str(raw_directory),
                )

            payload_hash = hashlib.sha256(
                result.text.encode("utf-8")
            ).hexdigest()
            raw_path = raw_directory / (
                f"page_{page:05d}_{payload_hash[:16]}.html"
            )
            raw_path.write_text(result.text, encoding="utf-8")

            try:
                staged_result = store.ingest_national_universe_page(
                    universe_id,
                    result.text,
                    source_url=source_url,
                    retrieved_at=result.retrieved_at,
                    raw_payload_path=str(raw_path),
                    parser_version="2.1",
                )
            except NationalSnapshotIntegrityError as exc:
                failed_at = collector.now_iso()
                store.mark_national_universe_page_failed(
                    universe_id,
                    source_url,
                    failed_at=failed_at,
                    error_message=str(exc),
                )
                store.record_national_snapshot_page_attempt(
                    collection_run_id=collection_run_id,
                    universe_id=universe_id,
                    page=page,
                    source_url=source_url,
                    attempted_at=attempted_at,
                    completed_at=failed_at,
                    status="INTEGRITY_ABORT",
                    http_status=result.http_status,
                    fetch_attempts=result.attempts,
                    content_sha256=result.content_sha256,
                    raw_payload_path=str(raw_path),
                    source_reported_total=getattr(exc, "observed", None),
                    error_message=str(exc),
                )
                failed += 1
                stop_reason = f"INTEGRITY_ABORT: {type(exc).__name__}"
                store.abort_national_universe_run(
                    universe_id,
                    aborted_at=failed_at,
                    reason=str(exc),
                )
                store.finish_national_snapshot_collection_run(
                    collection_run_id,
                    completed_at=failed_at,
                    attempted=attempted,
                    staged=staged,
                    failed=failed,
                    status="ABORTED",
                    stop_reason=stop_reason,
                )
                progress = store.national_universe_progress(universe_id)
                return NationalSnapshotBatchSummary(
                    collection_run_id=collection_run_id,
                    universe_id=universe_id,
                    universe_label=universe_label,
                    attempted=attempted,
                    staged=staged,
                    failed=failed,
                    pages_remaining=int(
                        progress["page_status_counts"].get("PLANNED", 0)
                    ),
                    failed_pages_remaining=int(
                        progress["page_status_counts"].get("FAILED", 0)
                    ),
                    universe_status=str(progress["status"]),
                    finalized=False,
                    eligible_for_national_analysis=False,
                    stop_reason=stop_reason,
                    raw_directory=str(raw_directory),
                )
            except Exception as exc:
                failed_at = collector.now_iso()
                store.mark_national_universe_page_failed(
                    universe_id,
                    source_url,
                    failed_at=failed_at,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                store.record_national_snapshot_page_attempt(
                    collection_run_id=collection_run_id,
                    universe_id=universe_id,
                    page=page,
                    source_url=source_url,
                    attempted_at=attempted_at,
                    completed_at=failed_at,
                    status="PARSE_FAILED",
                    http_status=result.http_status,
                    fetch_attempts=result.attempts,
                    content_sha256=result.content_sha256,
                    raw_payload_path=str(raw_path),
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                failed += 1
                stop_reason = "PARSER_FAILURE_REQUIRES_REQUEUE"
                store.finish_national_snapshot_collection_run(
                    collection_run_id,
                    completed_at=failed_at,
                    attempted=attempted,
                    staged=staged,
                    failed=failed,
                    status="FAILED",
                    stop_reason=stop_reason,
                )
                progress = store.national_universe_progress(universe_id)
                return NationalSnapshotBatchSummary(
                    collection_run_id=collection_run_id,
                    universe_id=universe_id,
                    universe_label=universe_label,
                    attempted=attempted,
                    staged=staged,
                    failed=failed,
                    pages_remaining=int(
                        progress["page_status_counts"].get("PLANNED", 0)
                    ),
                    failed_pages_remaining=int(
                        progress["page_status_counts"].get("FAILED", 0)
                    ),
                    universe_status=str(progress["status"]),
                    finalized=False,
                    eligible_for_national_analysis=False,
                    stop_reason=stop_reason,
                    raw_directory=str(raw_directory),
                )

            completed_at = collector.now_iso()
            store.record_national_snapshot_page_attempt(
                collection_run_id=collection_run_id,
                universe_id=universe_id,
                page=page,
                source_url=source_url,
                attempted_at=attempted_at,
                completed_at=completed_at,
                status="FETCHED_STAGED",
                http_status=result.http_status,
                fetch_attempts=result.attempts,
                content_sha256=result.content_sha256,
                raw_payload_path=str(raw_path),
                snapshot_id=int(staged_result["snapshot_id"]),
                source_reported_total=(
                    None
                    if staged_result["source_reported_total"] is None
                    else int(staged_result["source_reported_total"])
                ),
            )
            staged += 1

            if page == 1:
                store.expand_national_universe_run(
                    universe_id,
                    planned_at=completed_at,
                )

        progress = store.national_universe_progress(universe_id)
        planned_remaining = int(
            progress["page_status_counts"].get("PLANNED", 0)
        )
        failed_remaining = int(
            progress["page_status_counts"].get("FAILED", 0)
        )

        if (
            auto_finalize
            and str(progress["status"]) == "RUNNING"
            and planned_remaining == 0
            and failed_remaining == 0
        ):
            final = store.finalize_national_universe_run(
                universe_id,
                completed_at=collector.now_iso(),
            )
            finalized = True
            stop_reason = (
                "NATIONAL_SNAPSHOT_COMPLETED"
                if final["status"] == "COMPLETED"
                else "FINAL_QC_FAILED"
            )
            progress = store.national_universe_progress(universe_id)
        elif planned_remaining > 0 and attempted >= max_pages:
            stop_reason = "BATCH_LIMIT_REACHED"
        elif failed_remaining:
            stop_reason = "FAILED_PAGES_REQUIRE_EXPLICIT_REQUEUE"

        store.finish_national_snapshot_collection_run(
            collection_run_id,
            completed_at=collector.now_iso(),
            attempted=attempted,
            staged=staged,
            failed=failed,
            status="COMPLETED",
            stop_reason=stop_reason,
        )
        return NationalSnapshotBatchSummary(
            collection_run_id=collection_run_id,
            universe_id=universe_id,
            universe_label=universe_label,
            attempted=attempted,
            staged=staged,
            failed=failed,
            pages_remaining=int(
                progress["page_status_counts"].get("PLANNED", 0)
            ),
            failed_pages_remaining=int(
                progress["page_status_counts"].get("FAILED", 0)
            ),
            universe_status=str(progress["status"]),
            finalized=finalized,
            eligible_for_national_analysis=bool(
                progress["eligible_for_national_analysis"]
            ),
            stop_reason=stop_reason,
            raw_directory=str(raw_directory),
        )
    except Exception as exc:
        # Do not overwrite an explicitly finalized/aborted collection run.
        row = store.conn.execute(
            """SELECT status FROM national_snapshot_collection_runs
               WHERE collection_run_id=?""",
            (collection_run_id,),
        ).fetchone()
        if row is not None and row["status"] == "RUNNING":
            store.finish_national_snapshot_collection_run(
                collection_run_id,
                completed_at=collector.now_iso(),
                attempted=attempted,
                staged=staged,
                failed=failed,
                status="FAILED",
                stop_reason="UNEXPECTED_CONTROLLER_FAILURE",
                notes=f"{type(exc).__name__}: {exc}",
            )
        raise
