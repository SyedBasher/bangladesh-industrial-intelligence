from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Mapping

from .detail_validation import (
    DEFAULT_CHECKPOINT_POLICY,
    CheckpointDecision,
    CheckpointPolicy,
    DetailCheckpointMetrics,
    FrozenValidationRecord,
    assess_detail_record,
    evaluate_checkpoint,
    plan_progressive_detail_batches,
)
from .discovery import DiscoveryRequest, candidate_pool_health
from .freeze import (
    ValidationFreezeError,
    build_validation_freeze_plan,
)
from .hashutil import sha256_text
from .parsers import extract_public_id, parse_dife_detail, parse_dife_list_page
from .policy import SourceAccessPolicy
from .sampling import ValidationCandidate
from .supplement import SupplementRequest


_LOCAL_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    source_reported_at_raw TEXT,
    source_total_records INTEGER,
    content_sha256 TEXT NOT NULL,
    raw_payload_path TEXT,
    parser_version TEXT NOT NULL,
    UNIQUE(source_name, source_url, content_sha256)
);

CREATE TABLE IF NOT EXISTS discovery_requests (
    request_id INTEGER PRIMARY KEY,
    plan_label TEXT NOT NULL,
    sector_family TEXT NOT NULL,
    source_sector_value TEXT NOT NULL,
    source_sector_label TEXT NOT NULL,
    page INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PLANNED'
        CHECK(status IN ('PLANNED','STAGED','FAILED','SKIPPED')),
    planned_at TEXT NOT NULL,
    staged_snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    error_message TEXT,
    UNIQUE(plan_label, source_url)
);

CREATE TABLE IF NOT EXISTS supplement_requests (
    request_id INTEGER PRIMARY KEY,
    plan_label TEXT NOT NULL,
    geography_group TEXT NOT NULL,
    source_district_value TEXT NOT NULL,
    source_district_label TEXT NOT NULL,
    sector_family TEXT NOT NULL,
    source_sector_value TEXT NOT NULL,
    source_sector_label TEXT NOT NULL,
    page INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PLANNED'
        CHECK(status IN ('PLANNED','STAGED','FAILED','SKIPPED')),
    planned_at TEXT NOT NULL,
    staged_snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    error_message TEXT,
    UNIQUE(plan_label, source_url)
);

CREATE TABLE IF NOT EXISTS establishments (
    dife_public_id INTEGER PRIMARY KEY,
    canonical_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS establishment_observations (
    observation_id INTEGER PRIMARY KEY,
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    snapshot_id INTEGER NOT NULL REFERENCES source_snapshots(snapshot_id),
    name TEXT NOT NULL,
    sector TEXT,
    location TEXT,
    upazila TEXT,
    district TEXT,
    division TEXT,
    licence_class TEXT,
    status TEXT,
    row_sha256 TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    UNIQUE(dife_public_id, snapshot_id, row_sha256)
);

CREATE TABLE IF NOT EXISTS validation_sample (
    validation_label TEXT NOT NULL,
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    sector_family TEXT NOT NULL,
    geography_group TEXT NOT NULL,
    selection_stage TEXT NOT NULL,
    selected_at TEXT NOT NULL,
    PRIMARY KEY(validation_label, dife_public_id)
);


CREATE TABLE IF NOT EXISTS detail_checkpoints (
    validation_label TEXT NOT NULL,
    checkpoint_n INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('LOCKED','READY','PASSED','FAILED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(validation_label, checkpoint_n)
);

CREATE TABLE IF NOT EXISTS detail_requests (
    validation_label TEXT NOT NULL,
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    sequence_no INTEGER NOT NULL,
    first_checkpoint INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PLANNED'
        CHECK(status IN ('PLANNED','PARSED','FAILED','SKIPPED')),
    planned_at TEXT NOT NULL,
    resolved_at TEXT,
    staged_snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    parser_valid INTEGER,
    core_complete INTEGER,
    error_message TEXT,
    PRIMARY KEY(validation_label, dife_public_id),
    UNIQUE(validation_label, sequence_no),
    UNIQUE(validation_label, source_url)
);

CREATE TABLE IF NOT EXISTS detail_observations (
    detail_observation_id INTEGER PRIMARY KEY,
    validation_label TEXT NOT NULL,
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    snapshot_id INTEGER NOT NULL REFERENCES source_snapshots(snapshot_id),
    name_en TEXT,
    name_bn TEXT,
    address TEXT,
    upazila TEXT,
    district TEXT,
    division TEXT,
    status TEXT,
    licence_expiry_raw TEXT,
    sector TEXT,
    licence_no TEXT,
    old_licence_no TEXT,
    registration_no TEXT,
    old_registration_no TEXT,
    licence_class TEXT,
    establishment_type TEXT,
    worker_component_1 INTEGER,
    worker_component_2 INTEGER,
    worker_total INTEGER,
    parser_valid INTEGER NOT NULL,
    core_complete INTEGER NOT NULL,
    core_present INTEGER NOT NULL,
    core_expected INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    row_sha256 TEXT NOT NULL,
    UNIQUE(validation_label, dife_public_id, snapshot_id, row_sha256)
);

CREATE TABLE IF NOT EXISTS detail_checkpoint_decisions (
    decision_id INTEGER PRIMARY KEY,
    validation_label TEXT NOT NULL,
    checkpoint_n INTEGER NOT NULL,
    evaluated_at TEXT NOT NULL,
    passed INTEGER NOT NULL,
    metrics_json TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS access_policy_reviews (
    review_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    decision TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    review_note TEXT NOT NULL,
    allowed_hosts_json TEXT NOT NULL,
    allowed_path_prefixes_json TEXT NOT NULL,
    requests_per_minute REAL NOT NULL,
    max_retries INTEGER NOT NULL,
    timeout_seconds REAL NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS detail_collection_runs (
    run_id INTEGER PRIMARY KEY,
    validation_label TEXT NOT NULL,
    checkpoint_n INTEGER NOT NULL,
    policy_review_id INTEGER NOT NULL REFERENCES access_policy_reviews(review_id),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING','COMPLETED','FAILED')),
    attempted INTEGER NOT NULL DEFAULT 0,
    parsed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    raw_directory TEXT NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS collection_run_checkpoint_idx
    ON detail_collection_runs(validation_label, checkpoint_n, started_at DESC);

CREATE INDEX IF NOT EXISTS detail_request_checkpoint_idx
    ON detail_requests(validation_label, first_checkpoint, status);
CREATE INDEX IF NOT EXISTS detail_observation_public_id_idx
    ON detail_observations(validation_label, dife_public_id, detail_observation_id DESC);

CREATE INDEX IF NOT EXISTS discovery_plan_status_idx
    ON discovery_requests(plan_label, status);
CREATE INDEX IF NOT EXISTS supplement_plan_status_idx
    ON supplement_requests(plan_label, status);
CREATE INDEX IF NOT EXISTS obs_public_id_idx
    ON establishment_observations(dife_public_id, observation_id DESC);
CREATE INDEX IF NOT EXISTS obs_sector_idx
    ON establishment_observations(sector);
CREATE INDEX IF NOT EXISTS obs_district_idx
    ON establishment_observations(district);
"""


class LocalValidationStore:
    """Private local SQLite store for validation-stage work.

    Database files are intentionally excluded by the repository `.gitignore`. This
    store is a development/validation backend, not the public data-distribution layer.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(_LOCAL_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "LocalValidationStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def integrity_check(self) -> str:
        return str(self.conn.execute("PRAGMA integrity_check").fetchone()[0])

    def record_discovery_requests(
        self,
        plan_label: str,
        requests: list[DiscoveryRequest],
        *,
        planned_at: str,
    ) -> int:
        """Persist an auditable manifest before any page is staged."""
        self.conn.executemany(
            """INSERT OR IGNORE INTO discovery_requests(
                   plan_label, sector_family, source_sector_value, source_sector_label,
                   page, source_url, reason, status, planned_at
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            [
                (
                    plan_label,
                    request.sector_family,
                    request.source_sector_value,
                    request.source_sector_label,
                    request.page,
                    request.source_url,
                    request.reason,
                    "PLANNED",
                    planned_at,
                )
                for request in requests
            ],
        )
        self.conn.commit()
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM discovery_requests WHERE plan_label=?",
                (plan_label,),
            ).fetchone()[0]
        )

    def mark_discovery_request(
        self,
        plan_label: str,
        source_url: str,
        *,
        status: str,
        snapshot_id: int | None = None,
        error_message: str | None = None,
    ) -> None:
        self._mark_request(
            "discovery_requests",
            plan_label,
            source_url,
            status=status,
            snapshot_id=snapshot_id,
            error_message=error_message,
        )

    def discovery_status_counts(self, plan_label: str) -> dict[str, int]:
        return self._request_status_counts("discovery_requests", plan_label)

    def record_supplement_requests(
        self,
        plan_label: str,
        requests: list[SupplementRequest],
        *,
        planned_at: str,
    ) -> int:
        """Persist geographic supplement requests before staging any page."""
        self.conn.executemany(
            """INSERT OR IGNORE INTO supplement_requests(
                   plan_label, geography_group, source_district_value,
                   source_district_label, sector_family, source_sector_value,
                   source_sector_label, page, source_url, reason, status, planned_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    plan_label,
                    request.geography_group,
                    request.source_district_value,
                    request.source_district_label,
                    request.sector_family,
                    request.source_sector_value,
                    request.source_sector_label,
                    request.page,
                    request.source_url,
                    request.reason,
                    "PLANNED",
                    planned_at,
                )
                for request in requests
            ],
        )
        self.conn.commit()
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM supplement_requests WHERE plan_label=?",
                (plan_label,),
            ).fetchone()[0]
        )

    def mark_supplement_request(
        self,
        plan_label: str,
        source_url: str,
        *,
        status: str,
        snapshot_id: int | None = None,
        error_message: str | None = None,
    ) -> None:
        self._mark_request(
            "supplement_requests",
            plan_label,
            source_url,
            status=status,
            snapshot_id=snapshot_id,
            error_message=error_message,
        )

    def supplement_status_counts(self, plan_label: str) -> dict[str, int]:
        return self._request_status_counts("supplement_requests", plan_label)

    def _mark_request(
        self,
        table: str,
        plan_label: str,
        source_url: str,
        *,
        status: str,
        snapshot_id: int | None,
        error_message: str | None,
    ) -> None:
        if table not in {"discovery_requests", "supplement_requests"}:
            raise ValueError(f"unsupported request table: {table}")
        if status not in {"PLANNED", "STAGED", "FAILED", "SKIPPED"}:
            raise ValueError(f"unsupported request status: {status}")
        if status == "STAGED" and snapshot_id is None:
            raise ValueError("STAGED requests require a snapshot_id")
        cursor = self.conn.execute(
            f"""UPDATE {table}
                SET status=?, staged_snapshot_id=?, error_message=?
                WHERE plan_label=? AND source_url=?""",
            (status, snapshot_id, error_message, plan_label, source_url),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"request not found: {plan_label} {source_url}")
        self.conn.commit()

    def _request_status_counts(self, table: str, plan_label: str) -> dict[str, int]:
        if table not in {"discovery_requests", "supplement_requests"}:
            raise ValueError(f"unsupported request table: {table}")
        rows = self.conn.execute(
            f"""SELECT status, COUNT(*) AS n
                FROM {table}
                WHERE plan_label=?
                GROUP BY status
                ORDER BY status""",
            (plan_label,),
        ).fetchall()
        return {str(row["status"]): int(row["n"]) for row in rows}

    def ingest_dife_list_html(
        self,
        html: str,
        *,
        source_url: str,
        retrieved_at: str,
        raw_payload_path: str | None = None,
        parser_version: str = "0.9",
    ) -> dict[str, int | str | None]:
        """Parse and persist one already-obtained public DIFE list page.

        This method performs no network request. It is suitable for staged HTML from
        manually verified or separately policy-approved collection workflows.
        """
        metadata, records = parse_dife_list_page(html)
        content_hash = sha256_text(html)
        self.conn.execute(
            """INSERT OR IGNORE INTO source_snapshots(
                   source_name, source_url, retrieved_at, source_reported_at_raw,
                   source_total_records, content_sha256, raw_payload_path, parser_version
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                "DIFE/LIMA",
                source_url,
                retrieved_at,
                metadata.source_reported_at_raw,
                metadata.total_records,
                content_hash,
                raw_payload_path,
                parser_version,
            ),
        )
        snapshot_id = self.conn.execute(
            """SELECT snapshot_id FROM source_snapshots
               WHERE source_name='DIFE/LIMA' AND source_url=? AND content_sha256=?""",
            (source_url, content_hash),
        ).fetchone()[0]

        for record in records:
            self.conn.execute(
                """INSERT INTO establishments(dife_public_id, canonical_name)
                   VALUES(?,?)
                   ON CONFLICT(dife_public_id) DO UPDATE SET canonical_name=excluded.canonical_name""",
                (record.public_id, record.name),
            )
            payload = asdict(record)
            row_hash = sha256_text(repr(sorted(payload.items())))
            self.conn.execute(
                """INSERT OR IGNORE INTO establishment_observations(
                       dife_public_id, snapshot_id, name, sector, location, upazila,
                       district, division, licence_class, status, row_sha256, observed_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.public_id,
                    snapshot_id,
                    record.name,
                    record.sector,
                    record.location,
                    record.upazila,
                    record.district,
                    record.division,
                    record.licence_class,
                    record.status,
                    row_hash,
                    retrieved_at,
                ),
            )

        self.conn.commit()
        return {
            "snapshot_id": int(snapshot_id),
            "records_parsed": len(records),
            "source_total_records": metadata.total_records,
            "content_sha256": content_hash,
        }

    def validation_candidates(self) -> list[ValidationCandidate]:
        rows = self.conn.execute(
            """WITH latest AS (
                   SELECT *, ROW_NUMBER() OVER(
                       PARTITION BY dife_public_id
                       ORDER BY observed_at DESC, observation_id DESC
                   ) AS rn
                   FROM establishment_observations
               )
               SELECT dife_public_id, sector, district
               FROM latest WHERE rn=1
               ORDER BY dife_public_id"""
        ).fetchall()
        return [
            ValidationCandidate(
                public_id=int(row["dife_public_id"]),
                sector_label=row["sector"],
                district=row["district"],
            )
            for row in rows
        ]

    def candidate_pool_health(self) -> dict[str, object]:
        return candidate_pool_health(self.validation_candidates())

    def freeze_diagnostics(
        self,
        *,
        sector_targets: Mapping[str, int] | None = None,
        geography_targets: Mapping[str, int] | None = None,
    ) -> dict[str, object]:
        """Return exact joint-freeze diagnostics without mutating the sample."""
        try:
            plan = build_validation_freeze_plan(
                self.validation_candidates(),
                sector_targets=sector_targets,
                geography_targets=geography_targets,
            )
            diagnostics = plan.diagnostics
        except ValidationFreezeError as exc:
            diagnostics = exc.diagnostics
        return asdict(diagnostics)

    def freeze_validation_sample(
        self,
        validation_label: str,
        *,
        selected_at: str,
        sector_targets: Mapping[str, int] | None = None,
        geography_targets: Mapping[str, int] | None = None,
    ) -> int:
        """Freeze a sample only if all sector and geography constraints are feasible.

        The feasibility plan is computed before the existing labelled sample is
        deleted, so a failed freeze attempt does not destroy a prior valid freeze.
        """
        plan = build_validation_freeze_plan(
            self.validation_candidates(),
            sector_targets=sector_targets,
            geography_targets=geography_targets,
        )

        with self.conn:
            self.conn.execute(
                "DELETE FROM validation_sample WHERE validation_label=?",
                (validation_label,),
            )
            self.conn.executemany(
                """INSERT INTO validation_sample(
                       validation_label, dife_public_id, sector_family,
                       geography_group, selection_stage, selected_at
                   ) VALUES(?,?,?,?,?,?)""",
                [
                    (
                        validation_label,
                        item.candidate.public_id,
                        item.candidate.sector_family,
                        item.candidate.geography_group,
                        item.selection_stage,
                        selected_at,
                    )
                    for item in plan.selections
                ],
            )
        return len(plan.selections)


    def plan_detail_validation(
        self,
        validation_label: str,
        *,
        planned_at: str,
        checkpoints: tuple[int, ...] = (100, 500, 2000),
        base_url: str = "https://lima.dife.gov.bd/public-report/establishment",
    ) -> int:
        """Create immutable progressive detail assignments from a frozen sample.

        Once detail requests exist for a validation label, the plan cannot be silently
        replaced. Re-freezing the underlying validation sample requires a new label.
        """
        existing = self.conn.execute(
            "SELECT COUNT(*) FROM detail_requests WHERE validation_label=?",
            (validation_label,),
        ).fetchone()[0]
        if existing:
            raise ValueError(
                f"detail validation is already planned for {validation_label!r}; use a new validation label"
            )

        rows = self.conn.execute(
            """SELECT dife_public_id, sector_family, geography_group
               FROM validation_sample
               WHERE validation_label=?
               ORDER BY dife_public_id""",
            (validation_label,),
        ).fetchall()
        records = [
            FrozenValidationRecord(
                public_id=int(row["dife_public_id"]),
                sector_family=str(row["sector_family"]),
                geography_group=str(row["geography_group"]),
            )
            for row in rows
        ]
        assignments = plan_progressive_detail_batches(
            records,
            validation_label=validation_label,
            checkpoints=checkpoints,
        )
        checkpoints = tuple(sorted(set(int(value) for value in checkpoints)))

        with self.conn:
            self.conn.executemany(
                """INSERT INTO detail_requests(
                       validation_label, dife_public_id, sequence_no, first_checkpoint,
                       source_url, status, planned_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                [
                    (
                        validation_label,
                        assignment.public_id,
                        assignment.sequence_no,
                        assignment.first_checkpoint,
                        f"{base_url.rstrip('/')}/{assignment.public_id}",
                        "PLANNED",
                        planned_at,
                    )
                    for assignment in assignments
                ],
            )
            self.conn.executemany(
                """INSERT INTO detail_checkpoints(
                       validation_label, checkpoint_n, state, created_at, updated_at
                   ) VALUES(?,?,?,?,?)""",
                [
                    (
                        validation_label,
                        checkpoint,
                        "READY" if index == 0 else "LOCKED",
                        planned_at,
                        planned_at,
                    )
                    for index, checkpoint in enumerate(checkpoints)
                ],
            )
        return len(assignments)

    def detail_checkpoint_states(self, validation_label: str) -> dict[int, str]:
        rows = self.conn.execute(
            """SELECT checkpoint_n, state
               FROM detail_checkpoints
               WHERE validation_label=?
               ORDER BY checkpoint_n""",
            (validation_label,),
        ).fetchall()
        return {int(row["checkpoint_n"]): str(row["state"]) for row in rows}

    def detail_requests_for_checkpoint(
        self,
        validation_label: str,
        checkpoint_n: int,
    ) -> list[dict[str, object]]:
        """Return only the newly authorized tranche for a checkpoint."""
        checkpoint = self.conn.execute(
            """SELECT state FROM detail_checkpoints
               WHERE validation_label=? AND checkpoint_n=?""",
            (validation_label, checkpoint_n),
        ).fetchone()
        if checkpoint is None:
            raise KeyError(f"unknown detail checkpoint: {validation_label} {checkpoint_n}")
        if checkpoint["state"] != "READY":
            raise ValueError(
                f"checkpoint {checkpoint_n} is {checkpoint['state']}, not READY"
            )
        rows = self.conn.execute(
            """SELECT dife_public_id, sequence_no, first_checkpoint, source_url, status
               FROM detail_requests
               WHERE validation_label=? AND first_checkpoint=? AND status='PLANNED'
               ORDER BY sequence_no""",
            (validation_label, checkpoint_n),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_detail_request_failed(
        self,
        validation_label: str,
        dife_public_id: int,
        *,
        resolved_at: str,
        error_message: str,
    ) -> None:
        cursor = self.conn.execute(
            """UPDATE detail_requests
               SET status='FAILED', resolved_at=?, error_message=?,
                   staged_snapshot_id=NULL, parser_valid=NULL, core_complete=NULL
               WHERE validation_label=? AND dife_public_id=?""",
            (resolved_at, error_message, validation_label, dife_public_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(
                f"detail request not found: {validation_label} {dife_public_id}"
            )
        self.conn.commit()

    def reset_failed_detail_request(
        self,
        validation_label: str,
        dife_public_id: int,
    ) -> None:
        """Allow an explicitly failed request to be retried without losing its audit row."""
        cursor = self.conn.execute(
            """UPDATE detail_requests
               SET status='PLANNED', resolved_at=NULL, error_message=NULL,
                   staged_snapshot_id=NULL, parser_valid=NULL, core_complete=NULL
               WHERE validation_label=? AND dife_public_id=? AND status='FAILED'""",
            (validation_label, dife_public_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("only FAILED detail requests can be reset for retry")
        self.conn.commit()

    def ingest_dife_detail_html(
        self,
        validation_label: str,
        dife_public_id: int,
        html: str,
        *,
        source_url: str,
        retrieved_at: str,
        raw_payload_path: str | None = None,
        parser_version: str = "1.0",
    ) -> dict[str, object]:
        """Parse and persist one already-obtained DIFE public detail page."""
        request = self.conn.execute(
            """SELECT source_url, status FROM detail_requests
               WHERE validation_label=? AND dife_public_id=?""",
            (validation_label, dife_public_id),
        ).fetchone()
        if request is None:
            raise KeyError(
                f"detail request not planned: {validation_label} {dife_public_id}"
            )
        if source_url != request["source_url"]:
            raise ValueError("detail source URL differs from the frozen request manifest")
        if extract_public_id(source_url) != int(dife_public_id):
            raise ValueError("detail source URL does not contain the expected public DIFE ID")

        detail = parse_dife_detail(html)
        assessment = assess_detail_record(detail)
        content_hash = sha256_text(html)
        row_hash = sha256_text(repr(sorted(asdict(detail).items())))

        with self.conn:
            self.conn.execute(
                """INSERT OR IGNORE INTO source_snapshots(
                       source_name, source_url, retrieved_at, source_reported_at_raw,
                       source_total_records, content_sha256, raw_payload_path, parser_version
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    "DIFE/LIMA DETAIL",
                    source_url,
                    retrieved_at,
                    None,
                    None,
                    content_hash,
                    raw_payload_path,
                    parser_version,
                ),
            )
            snapshot_id = int(
                self.conn.execute(
                    """SELECT snapshot_id FROM source_snapshots
                       WHERE source_name='DIFE/LIMA DETAIL'
                         AND source_url=? AND content_sha256=?""",
                    (source_url, content_hash),
                ).fetchone()[0]
            )

            self.conn.execute(
                """INSERT OR IGNORE INTO detail_observations(
                       validation_label, dife_public_id, snapshot_id,
                       name_en, name_bn, address, upazila, district, division, status,
                       licence_expiry_raw, sector, licence_no, old_licence_no,
                       registration_no, old_registration_no, licence_class,
                       establishment_type, worker_component_1, worker_component_2,
                       worker_total, parser_valid, core_complete, core_present,
                       core_expected, observed_at, row_sha256
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    validation_label,
                    dife_public_id,
                    snapshot_id,
                    detail.name_en,
                    detail.name_bn,
                    detail.address,
                    detail.upazila,
                    detail.district,
                    detail.division,
                    detail.status,
                    detail.licence_expiry_raw,
                    detail.sector,
                    detail.licence_no,
                    detail.old_licence_no,
                    detail.registration_no,
                    detail.old_registration_no,
                    detail.licence_class,
                    detail.establishment_type,
                    detail.worker_component_1,
                    detail.worker_component_2,
                    detail.worker_total,
                    int(assessment.parser_valid),
                    int(assessment.core_complete),
                    assessment.core_present,
                    assessment.core_expected,
                    retrieved_at,
                    row_hash,
                ),
            )
            self.conn.execute(
                """UPDATE detail_requests
                   SET status='PARSED', resolved_at=?, staged_snapshot_id=?,
                       parser_valid=?, core_complete=?, error_message=NULL
                   WHERE validation_label=? AND dife_public_id=?""",
                (
                    retrieved_at,
                    snapshot_id,
                    int(assessment.parser_valid),
                    int(assessment.core_complete),
                    validation_label,
                    dife_public_id,
                ),
            )

        return {
            "snapshot_id": snapshot_id,
            "content_sha256": content_hash,
            "parser_valid": assessment.parser_valid,
            "core_complete": assessment.core_complete,
            "employment_present": assessment.employment_present,
            "expiry_present": assessment.expiry_present,
        }

    def detail_checkpoint_metrics(
        self,
        validation_label: str,
        checkpoint_n: int,
    ) -> DetailCheckpointMetrics:
        """Calculate cumulative QC metrics through the requested checkpoint."""
        rows = self.conn.execute(
            """SELECT
                   r.dife_public_id, r.sequence_no, r.source_url, r.status,
                   r.parser_valid, r.core_complete, r.staged_snapshot_id,
                   s.source_url AS snapshot_url, s.retrieved_at,
                   s.content_sha256, s.raw_payload_path,
                   o.name_en, o.name_bn, o.district, o.sector, o.status AS detail_status,
                   o.establishment_type, o.licence_no, o.registration_no,
                   o.licence_expiry_raw, o.worker_total
               FROM detail_requests r
               LEFT JOIN source_snapshots s
                 ON s.snapshot_id = r.staged_snapshot_id
               LEFT JOIN detail_observations o
                 ON o.validation_label = r.validation_label
                AND o.dife_public_id = r.dife_public_id
                AND o.snapshot_id = r.staged_snapshot_id
               WHERE r.validation_label=? AND r.sequence_no<=?
               ORDER BY r.sequence_no""",
            (validation_label, checkpoint_n),
        ).fetchall()
        planned = len(rows)
        if planned == 0:
            raise ValueError(
                f"no detail requests planned for {validation_label!r} through {checkpoint_n}"
            )

        parsed_rows = [row for row in rows if row["status"] == "PARSED"]
        failed = sum(row["status"] == "FAILED" for row in rows)
        skipped = sum(row["status"] == "SKIPPED" for row in rows)
        resolved = len(parsed_rows) + failed + skipped

        def rate(numerator: int, denominator: int) -> float:
            return numerator / denominator if denominator else 0.0

        parsed = len(parsed_rows)
        parser_valid = sum(bool(row["parser_valid"]) for row in parsed_rows)
        provenance_complete = sum(
            bool(
                row["staged_snapshot_id"]
                and row["snapshot_url"] == row["source_url"]
                and row["retrieved_at"]
                and row["content_sha256"]
            )
            for row in parsed_rows
        )
        url_id_integrity = sum(
            extract_public_id(str(row["source_url"])) == int(row["dife_public_id"])
            for row in parsed_rows
        )
        core_complete = sum(bool(row["core_complete"]) for row in parsed_rows)

        def coverage(field: str) -> float:
            return rate(
                sum(row[field] is not None and str(row[field]).strip() != "" for row in parsed_rows),
                parsed,
            )

        return DetailCheckpointMetrics(
            checkpoint_n=int(checkpoint_n),
            planned=planned,
            resolved=resolved,
            parsed=parsed,
            failed=failed,
            skipped=skipped,
            retrieval_success_rate=rate(parsed, planned),
            parser_valid_rate=rate(parser_valid, parsed),
            provenance_complete_rate=rate(provenance_complete, parsed),
            url_id_integrity_rate=rate(url_id_integrity, parsed),
            core_complete_rate=rate(core_complete, parsed),
            employment_coverage_rate=coverage("worker_total"),
            expiry_coverage_rate=coverage("licence_expiry_raw"),
            licence_coverage_rate=coverage("licence_no"),
            registration_coverage_rate=coverage("registration_no"),
            district_coverage_rate=coverage("district"),
            sector_coverage_rate=coverage("sector"),
            status_coverage_rate=coverage("detail_status"),
            establishment_type_coverage_rate=coverage("establishment_type"),
        )

    def evaluate_detail_checkpoint(
        self,
        validation_label: str,
        checkpoint_n: int,
        *,
        evaluated_at: str,
        policy: CheckpointPolicy = DEFAULT_CHECKPOINT_POLICY,
    ) -> tuple[DetailCheckpointMetrics, CheckpointDecision]:
        """Evaluate a checkpoint and unlock the next tranche only when it passes."""
        checkpoint = self.conn.execute(
            """SELECT state FROM detail_checkpoints
               WHERE validation_label=? AND checkpoint_n=?""",
            (validation_label, checkpoint_n),
        ).fetchone()
        if checkpoint is None:
            raise KeyError(f"unknown detail checkpoint: {validation_label} {checkpoint_n}")
        if checkpoint["state"] == "LOCKED":
            raise ValueError("cannot evaluate a LOCKED checkpoint")

        metrics = self.detail_checkpoint_metrics(validation_label, checkpoint_n)
        decision = evaluate_checkpoint(metrics, policy)

        with self.conn:
            self.conn.execute(
                """INSERT INTO detail_checkpoint_decisions(
                       validation_label, checkpoint_n, evaluated_at, passed,
                       metrics_json, policy_json, reasons_json
                   ) VALUES(?,?,?,?,?,?,?)""",
                (
                    validation_label,
                    checkpoint_n,
                    evaluated_at,
                    int(decision.passed),
                    json.dumps(asdict(metrics), sort_keys=True),
                    json.dumps(asdict(policy), sort_keys=True),
                    json.dumps(list(decision.reasons), ensure_ascii=False),
                ),
            )
            self.conn.execute(
                """UPDATE detail_checkpoints
                   SET state=?, updated_at=?
                   WHERE validation_label=? AND checkpoint_n=?""",
                (
                    "PASSED" if decision.passed else "FAILED",
                    evaluated_at,
                    validation_label,
                    checkpoint_n,
                ),
            )
            if decision.passed:
                next_row = self.conn.execute(
                    """SELECT checkpoint_n FROM detail_checkpoints
                       WHERE validation_label=? AND checkpoint_n>?
                       ORDER BY checkpoint_n LIMIT 1""",
                    (validation_label, checkpoint_n),
                ).fetchone()
                if next_row is not None:
                    self.conn.execute(
                        """UPDATE detail_checkpoints
                           SET state='READY', updated_at=?
                           WHERE validation_label=? AND checkpoint_n=? AND state='LOCKED'""",
                        (evaluated_at, validation_label, int(next_row["checkpoint_n"])),
                    )
        return metrics, decision


    def record_access_policy_review(
        self,
        policy: SourceAccessPolicy,
        *,
        recorded_at: str,
    ) -> int:
        """Persist the exact reviewed access policy used for a live collection run."""
        policy.assert_live_collection_allowed()
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO access_policy_reviews(
                       source_name, decision, reviewed_at, review_note,
                       allowed_hosts_json, allowed_path_prefixes_json,
                       requests_per_minute, max_retries, timeout_seconds, recorded_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    policy.source_name,
                    str(policy.decision),
                    str(policy.reviewed_at),
                    policy.review_note,
                    json.dumps(list(policy.allowed_hosts), sort_keys=True),
                    json.dumps(list(policy.allowed_path_prefixes), sort_keys=True),
                    float(policy.requests_per_minute),
                    int(policy.max_retries),
                    float(policy.timeout_seconds),
                    recorded_at,
                ),
            )
        return int(cursor.lastrowid)

    def start_detail_collection_run(
        self,
        *,
        validation_label: str,
        checkpoint_n: int,
        policy_review_id: int,
        started_at: str,
        raw_directory: str,
        notes: str | None = None,
    ) -> int:
        checkpoint = self.conn.execute(
            """SELECT state FROM detail_checkpoints
               WHERE validation_label=? AND checkpoint_n=?""",
            (validation_label, checkpoint_n),
        ).fetchone()
        if checkpoint is None:
            raise KeyError(f"unknown detail checkpoint: {validation_label} {checkpoint_n}")
        if checkpoint["state"] != "READY":
            raise ValueError(
                f"checkpoint {checkpoint_n} is {checkpoint['state']}, not READY"
            )
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO detail_collection_runs(
                       validation_label, checkpoint_n, policy_review_id,
                       started_at, status, raw_directory, notes
                   ) VALUES(?,?,?,?,?,?,?)""",
                (
                    validation_label,
                    checkpoint_n,
                    policy_review_id,
                    started_at,
                    "RUNNING",
                    raw_directory,
                    notes,
                ),
            )
        return int(cursor.lastrowid)

    def finish_detail_collection_run(
        self,
        run_id: int,
        *,
        completed_at: str,
        attempted: int,
        parsed: int,
        failed: int,
        status: str = "COMPLETED",
        notes: str | None = None,
    ) -> None:
        if status not in {"COMPLETED", "FAILED"}:
            raise ValueError("final run status must be COMPLETED or FAILED")
        if min(attempted, parsed, failed) < 0 or parsed + failed > attempted:
            raise ValueError("invalid collection run counts")
        cursor = self.conn.execute(
            """UPDATE detail_collection_runs
               SET completed_at=?, status=?, attempted=?, parsed=?, failed=?,
                   notes=COALESCE(?, notes)
               WHERE run_id=? AND status='RUNNING'""",
            (completed_at, status, attempted, parsed, failed, notes, run_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"collection run {run_id} is not RUNNING")
        self.conn.commit()

    def detail_collection_run(self, run_id: int) -> dict[str, object]:
        row = self.conn.execute(
            """SELECT r.*, p.source_name, p.decision, p.reviewed_at,
                      p.review_note, p.requests_per_minute
               FROM detail_collection_runs r
               JOIN access_policy_reviews p ON p.review_id=r.policy_review_id
               WHERE r.run_id=?""",
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"collection run not found: {run_id}")
        return dict(row)

    def counts(self) -> dict[str, int]:
        return {
            table: int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "source_snapshots",
                "establishments",
                "establishment_observations",
                "validation_sample",
            )
        }
