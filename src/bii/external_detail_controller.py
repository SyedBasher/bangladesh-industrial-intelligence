from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .collector import PoliteHttpCollector
from .external_detail_runner import ExternalDetailRunSummary, run_external_detail_requests
from .local_store import LocalValidationStore


@dataclass(frozen=True)
class ExternalEnrichmentCycleResult:
    source_name: str
    collection: ExternalDetailRunSummary
    status_counts: dict[str, int]
    candidate_run_id: int | None
    auto_selected: int
    ambiguous: int
    review_required: int
    no_staged_candidate: int
    auto_links_applied: int


def run_external_enrichment_cycle(
    store: LocalValidationStore,
    collector: PoliteHttpCollector,
    *,
    validation_label: str,
    source_name: str,
    raw_root: str | Path,
    max_records: int | None = None,
    max_candidates: int = 5,
) -> ExternalEnrichmentCycleResult:
    """Fetch planned profiles once, then resolve the richer staged records.

    The resolver runs only when no planned detail request remains for the selected
    validation/source pair. Retrieval failures remain visible and can contribute to
    REVIEW_REQUIRED or NO_STAGED_CANDIDATE outcomes; they are never converted into a
    negative business fact.
    """
    source_name = source_name.upper()
    collection = run_external_detail_requests(
        store,
        collector,
        source_name=source_name,
        raw_root=raw_root,
        max_records=max_records,
    )

    status_counts = store.external_detail_target_status_counts(
        validation_label,
        source_name,
    )
    if status_counts.get("PLANNED", 0):
        return ExternalEnrichmentCycleResult(
            source_name=source_name,
            collection=collection,
            status_counts=status_counts,
            candidate_run_id=None,
            auto_selected=0,
            ambiguous=0,
            review_required=0,
            no_staged_candidate=0,
            auto_links_applied=0,
        )

    run = store.generate_external_candidates(
        validation_label,
        source_name,
        generated_at=collector.now_iso(),
        max_candidates=max_candidates,
    )
    run_id = int(run["run_id"])
    applied = store.apply_auto_resolutions(
        run_id,
        applied_at=collector.now_iso(),
        rule_version="1.6",
    )
    return ExternalEnrichmentCycleResult(
        source_name=source_name,
        collection=collection,
        status_counts=status_counts,
        candidate_run_id=run_id,
        auto_selected=int(run["auto_selected"]),
        ambiguous=int(run["ambiguous"]),
        review_required=int(run["review_required"]),
        no_staged_candidate=int(run["no_staged_candidate"]),
        auto_links_applied=applied,
    )
