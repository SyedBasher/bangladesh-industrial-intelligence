from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Mapping

from .discovery import DiscoveryRequest, candidate_pool_health
from .freeze import (
    ValidationFreezeError,
    build_validation_freeze_plan,
)
from .hashutil import sha256_text
from .parsers import parse_dife_list_page
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
