from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .collector import PoliteHttpCollector
from .detail_runner import CheckpointRunSummary, run_ready_detail_checkpoint
from .detail_validation import DEFAULT_CHECKPOINT_POLICY, CheckpointDecision, CheckpointPolicy, DetailCheckpointMetrics
from .local_store import LocalValidationStore
from .validation_reporting import ValidationReport


@dataclass(frozen=True)
class ProgressionStageResult:
    checkpoint_n: int
    collection: CheckpointRunSummary
    metrics: DetailCheckpointMetrics
    decision: CheckpointDecision
    report_id: int
    report: ValidationReport


@dataclass(frozen=True)
class ProgressiveValidationResult:
    validation_label: str
    completed_checkpoints: tuple[int, ...]
    stopped_at: int | None
    all_passed: bool
    stages: tuple[ProgressionStageResult, ...]


def run_progressive_detail_validation(
    store: LocalValidationStore,
    collector: PoliteHttpCollector,
    *,
    validation_label: str,
    raw_root: str | Path,
    policy: CheckpointPolicy = DEFAULT_CHECKPOINT_POLICY,
) -> ProgressiveValidationResult:
    """Run every currently reachable checkpoint until failure or completion.

    A pass automatically unlocks and runs the next checkpoint. The controller never
    overrides a failed gate and never touches a LOCKED checkpoint.
    """
    stages: list[ProgressionStageResult] = []
    completed: list[int] = []
    stopped_at: int | None = None

    while True:
        states = store.detail_checkpoint_states(validation_label)
        if not states:
            raise ValueError(f"no detail checkpoints planned for {validation_label!r}")

        ready = [checkpoint for checkpoint, state in states.items() if state == "READY"]
        if not ready:
            failed = [checkpoint for checkpoint, state in states.items() if state == "FAILED"]
            locked = [checkpoint for checkpoint, state in states.items() if state == "LOCKED"]
            if failed:
                stopped_at = min(failed)
            elif locked:
                # This should only happen when a prior checkpoint failed or was not
                # evaluated, but preserve the state rather than guessing.
                stopped_at = min(locked)
            break

        checkpoint_n = min(ready)
        collection = run_ready_detail_checkpoint(
            store,
            collector,
            validation_label=validation_label,
            checkpoint_n=checkpoint_n,
            raw_root=raw_root,
        )
        evaluated_at = collector.now_iso()
        metrics, decision = store.evaluate_detail_checkpoint(
            validation_label,
            checkpoint_n,
            evaluated_at=evaluated_at,
            policy=policy,
        )
        report_id, report, _ = store.generate_validation_report(
            validation_label,
            checkpoint_n,
            generated_at=collector.now_iso(),
        )
        stages.append(
            ProgressionStageResult(
                checkpoint_n=checkpoint_n,
                collection=collection,
                metrics=metrics,
                decision=decision,
                report_id=report_id,
                report=report,
            )
        )

        if not decision.passed:
            stopped_at = checkpoint_n
            break

        completed.append(checkpoint_n)

        states = store.detail_checkpoint_states(validation_label)
        if all(state == "PASSED" for state in states.values()):
            break

    final_states = store.detail_checkpoint_states(validation_label)
    all_passed = bool(final_states) and all(state == "PASSED" for state in final_states.values())
    return ProgressiveValidationResult(
        validation_label=validation_label,
        completed_checkpoints=tuple(completed),
        stopped_at=stopped_at,
        all_passed=all_passed,
        stages=tuple(stages),
    )
