from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path

from .hashutil import sha256_text
from .parsers import parse_dife_list_page
from .sampling import ValidationCandidate, select_validation_sample


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

    def ingest_dife_list_html(
        self,
        html: str,
        *,
        source_url: str,
        retrieved_at: str,
        raw_payload_path: str | None = None,
        parser_version: str = "0.7",
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

    def freeze_validation_sample(
        self,
        validation_label: str,
        *,
        selected_at: str,
        target_n: int = 2000,
    ) -> int:
        selection = select_validation_sample(self.validation_candidates(), target_n=target_n)
        self.conn.execute("DELETE FROM validation_sample WHERE validation_label=?", (validation_label,))
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
                for item in selection
            ],
        )
        self.conn.commit()
        return len(selection)

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
