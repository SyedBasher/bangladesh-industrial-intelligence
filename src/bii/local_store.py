from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Mapping

from .analytical_intelligence import UniverseKind, cluster_context
from .national_universe import (
    NationalPageStatus,
    assess_national_universe_quality,
    build_national_rollups,
    explicit_sector_family,
    plan_national_pages,
)
from .candidate_resolution import (
    CandidateBlockIndex,
    CandidateRecord,
    ResolutionOutcome,
    resolve_shortlist,
    shortlist_candidates,
)
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
from .enrichment import (
    DifeMatchRecord,
    EnrichmentCoverage,
    decide_external_link,
)
from .external_sources import (
    ExternalRecordPayload,
    SOURCE_SPECS,
    is_sector_eligible,
    parse_external_record,
    source_spec,
)
from .hashutil import sha256_text
from .intelligence_observations import (
    ObservationScope,
    extract_typed_observations,
)
from .parsers import extract_public_id, parse_dife_detail, parse_dife_list_page
from .policy import SourceAccessPolicy
from .product_view import ProductBaseRecord, build_product_payload
from .sampling import ValidationCandidate
from .source_index import (
    IndexRequest,
    SourceIndexRecord,
    assess_index_quality,
    parse_bgmea_member_index,
    parse_epb_exporter_index_html,
    parse_epb_exporter_index_json,
    plan_index_requests,
)
from .supplement import SupplementRequest
from .validation_reporting import (
    DetailComparisonRecord,
    ValidationAnomaly,
    ValidationReport,
    build_validation_report,
    report_as_dict,
)


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


CREATE TABLE IF NOT EXISTS validation_reports (
    report_id INTEGER PRIMARY KEY,
    validation_label TEXT NOT NULL,
    checkpoint_n INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validation_anomalies (
    anomaly_id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES validation_reports(report_id),
    dife_public_id INTEGER NOT NULL,
    sequence_no INTEGER NOT NULL,
    anomaly_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    list_value TEXT,
    detail_value TEXT,
    note TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS external_source_profiles (
    source_name TEXT PRIMARY KEY,
    source_authority TEXT NOT NULL,
    default_linkage TEXT NOT NULL,
    stable_key_rule TEXT NOT NULL,
    eligible_sector_families_json TEXT,
    negative_inference_allowed INTEGER NOT NULL DEFAULT 0,
    automation_policy_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_verified_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS external_source_records (
    external_record_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL REFERENCES external_source_profiles(source_name),
    external_key TEXT NOT NULL,
    source_url TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    site_text TEXT,
    district TEXT,
    upazila TEXT,
    first_retrieved_at TEXT NOT NULL,
    UNIQUE(source_name, external_key)
);

CREATE TABLE IF NOT EXISTS external_record_versions (
    external_version_id INTEGER PRIMARY KEY,
    external_record_id INTEGER NOT NULL REFERENCES external_source_records(external_record_id),
    content_sha256 TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    site_text TEXT,
    district TEXT,
    upazila TEXT,
    source_updated_at_raw TEXT,
    source_fields_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    UNIQUE(external_record_id, content_sha256)
);


CREATE TABLE IF NOT EXISTS external_typed_observations (
    typed_observation_id INTEGER PRIMARY KEY,
    external_version_id INTEGER NOT NULL REFERENCES external_record_versions(external_version_id),
    source_name TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('SITE','ORGANIZATION')),
    value_text TEXT,
    value_numeric REAL,
    unit TEXT,
    raw_label TEXT NOT NULL,
    raw_value TEXT NOT NULL,
    source_updated_at_raw TEXT,
    observed_at TEXT NOT NULL,
    observation_sha256 TEXT NOT NULL,
    UNIQUE(external_version_id, observation_sha256)
);

CREATE TABLE IF NOT EXISTS linked_intelligence_observations (
    linked_intelligence_id INTEGER PRIMARY KEY,
    entity_link_id INTEGER NOT NULL REFERENCES entity_links(entity_link_id),
    typed_observation_id INTEGER NOT NULL REFERENCES external_typed_observations(typed_observation_id),
    validation_label TEXT NOT NULL,
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    display_scope TEXT NOT NULL CHECK(display_scope IN ('SITE','ORGANIZATION')),
    site_attributable INTEGER NOT NULL,
    linked_at TEXT NOT NULL,
    UNIQUE(entity_link_id, typed_observation_id)
);

CREATE INDEX IF NOT EXISTS typed_observation_version_idx
    ON external_typed_observations(external_version_id, observation_type, scope);
CREATE INDEX IF NOT EXISTS linked_intelligence_establishment_idx
    ON linked_intelligence_observations(validation_label, dife_public_id, linked_intelligence_id);

CREATE TABLE IF NOT EXISTS enrichment_targets (
    validation_label TEXT NOT NULL,
    source_name TEXT NOT NULL REFERENCES external_source_profiles(source_name),
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    eligible INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','STAGED','REVIEWED','OUT_OF_SCOPE')),
    planned_at TEXT NOT NULL,
    PRIMARY KEY(validation_label, source_name, dife_public_id)
);

CREATE TABLE IF NOT EXISTS entity_links (
    entity_link_id INTEGER PRIMARY KEY,
    validation_label TEXT NOT NULL,
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    source_name TEXT NOT NULL REFERENCES external_source_profiles(source_name),
    external_record_id INTEGER NOT NULL REFERENCES external_source_records(external_record_id),
    match_type TEXT NOT NULL CHECK(match_type IN (
        'EXACT_SITE','PROBABLE_SITE','ORGANIZATION_ONLY',
        'AMBIGUOUS','NO_MATCH','SOURCE_FEASIBILITY_ONLY'
    )),
    site_level_match INTEGER NOT NULL,
    rule_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_evidence (
    match_evidence_id INTEGER PRIMARY KEY,
    entity_link_id INTEGER NOT NULL REFERENCES entity_links(entity_link_id),
    evidence_type TEXT NOT NULL,
    dife_value TEXT,
    external_value TEXT,
    result TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS enrichment_reports (
    report_id INTEGER PRIMARY KEY,
    validation_label TEXT NOT NULL,
    source_name TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    coverage_json TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS external_candidate_runs (
    run_id INTEGER PRIMARY KEY,
    validation_label TEXT NOT NULL,
    source_name TEXT NOT NULL REFERENCES external_source_profiles(source_name),
    generated_at TEXT NOT NULL,
    max_candidates INTEGER NOT NULL,
    staged_source_records INTEGER NOT NULL,
    targets_considered INTEGER NOT NULL,
    candidates_generated INTEGER NOT NULL,
    auto_selected INTEGER NOT NULL,
    ambiguous INTEGER NOT NULL,
    review_required INTEGER NOT NULL,
    no_staged_candidate INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS external_match_candidates (
    candidate_id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES external_candidate_runs(run_id),
    validation_label TEXT NOT NULL,
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    source_name TEXT NOT NULL,
    external_record_id INTEGER NOT NULL REFERENCES external_source_records(external_record_id),
    shortlist_position INTEGER NOT NULL,
    priority_class TEXT NOT NULL,
    name_strength TEXT NOT NULL,
    name_token_overlap REAL,
    district_result TEXT NOT NULL,
    upazila_result TEXT NOT NULL,
    address_result TEXT NOT NULL,
    address_overlap REAL,
    UNIQUE(run_id, dife_public_id, external_record_id)
);

CREATE TABLE IF NOT EXISTS external_resolution_outcomes (
    outcome_id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES external_candidate_runs(run_id),
    validation_label TEXT NOT NULL,
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    source_name TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN (
        'AUTO_SELECTED','AMBIGUOUS','REVIEW_REQUIRED','NO_STAGED_CANDIDATE'
    )),
    candidate_count INTEGER NOT NULL,
    selected_external_record_id INTEGER REFERENCES external_source_records(external_record_id),
    selected_match_type TEXT,
    note TEXT NOT NULL,
    applied_entity_link_id INTEGER REFERENCES entity_links(entity_link_id),
    UNIQUE(run_id, dife_public_id)
);


CREATE TABLE IF NOT EXISTS external_index_runs (
    run_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL REFERENCES external_source_profiles(source_name),
    seed_url TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING','COMPLETED','FAILED')),
    source_reported_total INTEGER,
    source_reported_last_page INTEGER,
    pages_planned INTEGER NOT NULL DEFAULT 1,
    pages_staged INTEGER NOT NULL DEFAULT 0,
    records_discovered INTEGER NOT NULL DEFAULT 0,
    unique_keys INTEGER NOT NULL DEFAULT 0,
    quality_json TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS external_index_pages (
    index_page_id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES external_index_runs(run_id),
    page INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PLANNED'
      CHECK(status IN ('PLANNED','STAGED','FAILED','SKIPPED')),
    planned_at TEXT NOT NULL,
    staged_at TEXT,
    snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    content_format TEXT,
    records_parsed INTEGER,
    source_reported_total INTEGER,
    source_reported_last_page INTEGER,
    error_message TEXT,
    UNIQUE(run_id, page),
    UNIQUE(run_id, source_url)
);

CREATE TABLE IF NOT EXISTS external_index_records (
    index_record_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL REFERENCES external_source_profiles(source_name),
    source_key TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    detail_url TEXT NOT NULL,
    registration_no TEXT,
    district TEXT,
    upazila TEXT,
    office_address TEXT,
    factory_address TEXT,
    first_seen_at TEXT NOT NULL,
    UNIQUE(source_name, source_key)
);

CREATE TABLE IF NOT EXISTS external_index_record_versions (
    index_version_id INTEGER PRIMARY KEY,
    index_record_id INTEGER NOT NULL REFERENCES external_index_records(index_record_id),
    run_id INTEGER NOT NULL REFERENCES external_index_runs(run_id),
    index_page_id INTEGER NOT NULL REFERENCES external_index_pages(index_page_id),
    row_sha256 TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    detail_url TEXT NOT NULL,
    registration_no TEXT,
    district TEXT,
    upazila TEXT,
    office_address TEXT,
    factory_address TEXT,
    observed_at TEXT NOT NULL,
    UNIQUE(index_record_id, run_id, index_page_id, row_sha256)
);

CREATE TABLE IF NOT EXISTS external_detail_requests (
    request_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL REFERENCES external_source_profiles(source_name),
    source_key TEXT NOT NULL,
    detail_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PLANNED'
      CHECK(status IN ('PLANNED','FETCHED','FAILED','SKIPPED')),
    planned_at TEXT NOT NULL,
    resolved_at TEXT,
    external_record_id INTEGER REFERENCES external_source_records(external_record_id),
    error_message TEXT,
    UNIQUE(source_name, source_key, detail_url)
);

CREATE TABLE IF NOT EXISTS external_detail_request_targets (
    request_id INTEGER NOT NULL REFERENCES external_detail_requests(request_id),
    validation_label TEXT NOT NULL,
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    index_record_id INTEGER NOT NULL REFERENCES external_index_records(index_record_id),
    shortlist_position INTEGER NOT NULL,
    priority_class TEXT NOT NULL,
    PRIMARY KEY(request_id, validation_label, dife_public_id)
);

CREATE INDEX IF NOT EXISTS external_index_run_source_idx
    ON external_index_runs(source_name, started_at DESC);
CREATE INDEX IF NOT EXISTS external_index_page_status_idx
    ON external_index_pages(run_id, status, page);
CREATE INDEX IF NOT EXISTS external_index_record_key_idx
    ON external_index_records(source_name, source_key);
CREATE INDEX IF NOT EXISTS external_index_version_run_idx
    ON external_index_record_versions(run_id, index_record_id);
CREATE INDEX IF NOT EXISTS external_detail_request_status_idx
    ON external_detail_requests(source_name, status, request_id);
CREATE INDEX IF NOT EXISTS external_detail_target_idx
    ON external_detail_request_targets(validation_label, dife_public_id, request_id);

CREATE INDEX IF NOT EXISTS external_candidate_run_source_idx
    ON external_candidate_runs(validation_label, source_name, generated_at DESC);
CREATE INDEX IF NOT EXISTS external_candidate_target_idx
    ON external_match_candidates(run_id, dife_public_id, shortlist_position);
CREATE INDEX IF NOT EXISTS external_resolution_outcome_idx
    ON external_resolution_outcomes(run_id, outcome, dife_public_id);

CREATE INDEX IF NOT EXISTS external_record_source_key_idx
    ON external_source_records(source_name, external_key);
CREATE INDEX IF NOT EXISTS enrichment_target_status_idx
    ON enrichment_targets(validation_label, source_name, status);
CREATE INDEX IF NOT EXISTS entity_link_dife_source_idx
    ON entity_links(validation_label, dife_public_id, source_name, created_at DESC);


CREATE TABLE IF NOT EXISTS national_universe_runs (
    universe_id INTEGER PRIMARY KEY,
    universe_label TEXT NOT NULL UNIQUE,
    seed_url TEXT NOT NULL,
    page_size INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING','COMPLETED','FAILED')),
    expected_total INTEGER,
    pages_planned INTEGER NOT NULL DEFAULT 1,
    pages_staged INTEGER NOT NULL DEFAULT 0,
    unique_public_ids INTEGER NOT NULL DEFAULT 0,
    duplicate_public_ids INTEGER NOT NULL DEFAULT 0,
    eligible_for_national_analysis INTEGER NOT NULL DEFAULT 0,
    qc_json TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS national_universe_pages (
    universe_id INTEGER NOT NULL REFERENCES national_universe_runs(universe_id),
    page INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PLANNED'
      CHECK(status IN ('PLANNED','STAGED','FAILED','SKIPPED')),
    planned_at TEXT NOT NULL,
    staged_at TEXT,
    snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    records_parsed INTEGER,
    source_reported_total INTEGER,
    error_message TEXT,
    PRIMARY KEY(universe_id, page),
    UNIQUE(universe_id, source_url)
);

CREATE TABLE IF NOT EXISTS national_universe_page_members (
    universe_id INTEGER NOT NULL REFERENCES national_universe_runs(universe_id),
    page INTEGER NOT NULL,
    dife_public_id INTEGER NOT NULL REFERENCES establishments(dife_public_id),
    observation_id INTEGER NOT NULL REFERENCES establishment_observations(observation_id),
    snapshot_id INTEGER NOT NULL REFERENCES source_snapshots(snapshot_id),
    PRIMARY KEY(universe_id, page, dife_public_id)
);

CREATE INDEX IF NOT EXISTS national_universe_status_idx
    ON national_universe_runs(status, eligible_for_national_analysis);
CREATE INDEX IF NOT EXISTS national_universe_page_status_idx
    ON national_universe_pages(universe_id, status, page);
CREATE INDEX IF NOT EXISTS national_universe_member_idx
    ON national_universe_page_members(universe_id, dife_public_id);

CREATE INDEX IF NOT EXISTS validation_report_checkpoint_idx
    ON validation_reports(validation_label, checkpoint_n, generated_at DESC);
CREATE INDEX IF NOT EXISTS validation_anomaly_type_idx
    ON validation_anomalies(report_id, severity, anomaly_type);

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


    def detail_comparison_records(
        self,
        validation_label: str,
        checkpoint_n: int,
    ) -> list[DetailComparisonRecord]:
        """Join frozen/list observations to the staged DIFE detail observations."""
        rows = self.conn.execute(
            """WITH latest_list AS (
                   SELECT eo.*,
                          ROW_NUMBER() OVER(
                              PARTITION BY eo.dife_public_id
                              ORDER BY eo.observed_at DESC, eo.observation_id DESC
                          ) AS rn
                   FROM establishment_observations eo
               )
               SELECT
                   r.dife_public_id,
                   r.sequence_no,
                   v.sector_family,
                   v.geography_group,
                   r.status AS request_status,
                   r.parser_valid,
                   r.core_complete,
                   ll.name AS list_name,
                   ll.sector AS list_sector,
                   ll.district AS list_district,
                   ll.status AS list_status,
                   ll.licence_class AS list_class,
                   d.name_en AS detail_name_en,
                   d.name_bn AS detail_name_bn,
                   d.sector AS detail_sector,
                   d.district AS detail_district,
                   d.status AS detail_status,
                   d.licence_class AS detail_class,
                   d.establishment_type,
                   d.licence_no,
                   d.registration_no,
                   d.worker_total,
                   d.licence_expiry_raw
               FROM detail_requests r
               JOIN validation_sample v
                 ON v.validation_label=r.validation_label
                AND v.dife_public_id=r.dife_public_id
               LEFT JOIN latest_list ll
                 ON ll.dife_public_id=r.dife_public_id AND ll.rn=1
               LEFT JOIN detail_observations d
                 ON d.validation_label=r.validation_label
                AND d.dife_public_id=r.dife_public_id
                AND d.snapshot_id=r.staged_snapshot_id
               WHERE r.validation_label=? AND r.sequence_no<=?
               ORDER BY r.sequence_no""",
            (validation_label, checkpoint_n),
        ).fetchall()
        return [
            DetailComparisonRecord(
                public_id=int(row["dife_public_id"]),
                sequence_no=int(row["sequence_no"]),
                sector_family=str(row["sector_family"]),
                geography_group=str(row["geography_group"]),
                request_status=str(row["request_status"]),
                parser_valid=None if row["parser_valid"] is None else bool(row["parser_valid"]),
                core_complete=None if row["core_complete"] is None else bool(row["core_complete"]),
                list_name=row["list_name"],
                list_sector=row["list_sector"],
                list_district=row["list_district"],
                list_status=row["list_status"],
                list_class=row["list_class"],
                detail_name_en=row["detail_name_en"],
                detail_name_bn=row["detail_name_bn"],
                detail_sector=row["detail_sector"],
                detail_district=row["detail_district"],
                detail_status=row["detail_status"],
                detail_class=row["detail_class"],
                establishment_type=row["establishment_type"],
                licence_no=row["licence_no"],
                registration_no=row["registration_no"],
                worker_total=row["worker_total"],
                licence_expiry_raw=row["licence_expiry_raw"],
            )
            for row in rows
        ]

    def generate_validation_report(
        self,
        validation_label: str,
        checkpoint_n: int,
        *,
        generated_at: str,
    ) -> tuple[int, ValidationReport, list[ValidationAnomaly]]:
        records = self.detail_comparison_records(validation_label, checkpoint_n)
        if not records:
            raise ValueError(
                f"no detail records available for report {validation_label!r} checkpoint {checkpoint_n}"
            )
        report, anomalies = build_validation_report(
            records,
            validation_label=validation_label,
            checkpoint_n=checkpoint_n,
            generated_at=generated_at,
        )
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO validation_reports(
                       validation_label, checkpoint_n, generated_at, report_json
                   ) VALUES(?,?,?,?)""",
                (
                    validation_label,
                    checkpoint_n,
                    generated_at,
                    json.dumps(report_as_dict(report), ensure_ascii=False, sort_keys=True),
                ),
            )
            report_id = int(cursor.lastrowid)
            self.conn.executemany(
                """INSERT INTO validation_anomalies(
                       report_id, dife_public_id, sequence_no, anomaly_type,
                       severity, list_value, detail_value, note
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                [
                    (
                        report_id,
                        anomaly.public_id,
                        anomaly.sequence_no,
                        anomaly.anomaly_type,
                        anomaly.severity,
                        anomaly.list_value,
                        anomaly.detail_value,
                        anomaly.note,
                    )
                    for anomaly in anomalies
                ],
            )
        return report_id, report, anomalies

    def validation_anomalies_for_report(
        self,
        report_id: int,
    ) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """SELECT dife_public_id, sequence_no, anomaly_type, severity,
                      list_value, detail_value, note
               FROM validation_anomalies
               WHERE report_id=?
               ORDER BY
                 CASE severity
                   WHEN 'CRITICAL' THEN 1
                   WHEN 'HIGH' THEN 2
                   WHEN 'MEDIUM' THEN 3
                   ELSE 4
                 END,
                 sequence_no,
                 anomaly_type""",
            (report_id,),
        ).fetchall()
        return [dict(row) for row in rows]


    def register_external_source_profile(
        self,
        source_name: str,
        *,
        automation_policy_status: str = "UNKNOWN",
        last_verified_at: str | None = None,
        notes: str | None = None,
    ) -> None:
        spec = source_spec(source_name)
        if automation_policy_status not in {"UNKNOWN", "REVIEWED_ALLOWED", "REVIEWED_RESTRICTED"}:
            raise ValueError("unsupported automation policy status")
        eligible = (
            None
            if spec.eligible_sector_families is None
            else json.dumps(list(spec.eligible_sector_families), sort_keys=True)
        )
        with self.conn:
            self.conn.execute(
                """INSERT INTO external_source_profiles(
                       source_name, source_authority, default_linkage, stable_key_rule,
                       eligible_sector_families_json, negative_inference_allowed,
                       automation_policy_status, last_verified_at, notes
                   ) VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(source_name) DO UPDATE SET
                     source_authority=excluded.source_authority,
                     default_linkage=excluded.default_linkage,
                     stable_key_rule=excluded.stable_key_rule,
                     eligible_sector_families_json=excluded.eligible_sector_families_json,
                     negative_inference_allowed=excluded.negative_inference_allowed,
                     automation_policy_status=excluded.automation_policy_status,
                     last_verified_at=COALESCE(excluded.last_verified_at, external_source_profiles.last_verified_at),
                     notes=COALESCE(excluded.notes, external_source_profiles.notes)""",
                (
                    spec.source_name,
                    spec.source_authority,
                    spec.default_linkage,
                    spec.stable_key_rule,
                    eligible,
                    int(spec.negative_inference_allowed),
                    automation_policy_status,
                    last_verified_at,
                    notes,
                ),
            )

    def _ensure_external_source_profile(self, source_name: str) -> None:
        existing = self.conn.execute(
            "SELECT 1 FROM external_source_profiles WHERE source_name=?",
            (source_name.upper(),),
        ).fetchone()
        if existing is None:
            self.register_external_source_profile(source_name)

    def register_default_external_sources(
        self,
        *,
        last_verified_at: str | None = None,
    ) -> int:
        for source_name in SOURCE_SPECS:
            existing = self.conn.execute(
                "SELECT 1 FROM external_source_profiles WHERE source_name=?",
                (source_name,),
            ).fetchone()
            if existing is None:
                self.register_external_source_profile(
                    source_name,
                    last_verified_at=last_verified_at,
                    notes="Public source capability profile; live automation permission remains source-specific.",
                )
        return len(SOURCE_SPECS)

    def plan_enrichment_targets(
        self,
        validation_label: str,
        source_name: str,
        *,
        planned_at: str,
    ) -> dict[str, int]:
        """Create source-specific targets without interpreting absence as a negative fact."""
        self._ensure_external_source_profile(source_name)
        rows = self.conn.execute(
            """SELECT dife_public_id, sector_family
               FROM validation_sample
               WHERE validation_label=?
               ORDER BY dife_public_id""",
            (validation_label,),
        ).fetchall()
        if not rows:
            raise ValueError(f"validation sample not found: {validation_label!r}")

        with self.conn:
            for row in rows:
                eligible = is_sector_eligible(source_name, str(row["sector_family"]))
                self.conn.execute(
                    """INSERT INTO enrichment_targets(
                           validation_label, source_name, dife_public_id,
                           eligible, status, planned_at
                       ) VALUES(?,?,?,?,?,?)
                       ON CONFLICT(validation_label, source_name, dife_public_id)
                       DO UPDATE SET
                         eligible=excluded.eligible,
                         status=CASE
                           WHEN enrichment_targets.status IN ('STAGED','REVIEWED')
                             THEN enrichment_targets.status
                           ELSE excluded.status
                         END,
                         planned_at=excluded.planned_at""",
                    (
                        validation_label,
                        source_name.upper(),
                        int(row["dife_public_id"]),
                        int(eligible),
                        "PENDING" if eligible else "OUT_OF_SCOPE",
                        planned_at,
                    ),
                )
        counts = self.conn.execute(
            """SELECT
                 SUM(CASE WHEN eligible=1 THEN 1 ELSE 0 END) AS eligible_n,
                 SUM(CASE WHEN eligible=0 THEN 1 ELSE 0 END) AS out_scope_n
               FROM enrichment_targets
               WHERE validation_label=? AND source_name=?""",
            (validation_label, source_name.upper()),
        ).fetchone()
        return {
            "eligible": int(counts["eligible_n"] or 0),
            "out_of_scope": int(counts["out_scope_n"] or 0),
        }

    def ingest_external_record_html(
        self,
        source_name: str,
        html: str,
        *,
        source_url: str,
        retrieved_at: str,
    ) -> dict[str, object]:
        """Stage a public external record and append a content-addressed version."""
        self._ensure_external_source_profile(source_name)
        payload = parse_external_record(source_name, html, source_url)
        content_hash = sha256_text(html)

        with self.conn:
            self.conn.execute(
                """INSERT INTO external_source_records(
                       source_name, external_key, source_url, entity_name,
                       site_text, district, upazila, first_retrieved_at
                   ) VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(source_name, external_key) DO UPDATE SET
                     source_url=excluded.source_url,
                     entity_name=excluded.entity_name,
                     site_text=excluded.site_text,
                     district=excluded.district,
                     upazila=excluded.upazila""",
                (
                    payload.source_name,
                    payload.external_key,
                    payload.source_url,
                    payload.entity_name,
                    payload.site_text,
                    payload.district,
                    payload.upazila,
                    retrieved_at,
                ),
            )
            external_record_id = int(
                self.conn.execute(
                    """SELECT external_record_id FROM external_source_records
                       WHERE source_name=? AND external_key=?""",
                    (payload.source_name, payload.external_key),
                ).fetchone()[0]
            )
            self.conn.execute(
                """INSERT OR IGNORE INTO external_record_versions(
                       external_record_id, content_sha256, entity_name, site_text,
                       district, upazila, source_updated_at_raw,
                       source_fields_json, observed_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    external_record_id,
                    content_hash,
                    payload.entity_name,
                    payload.site_text,
                    payload.district,
                    payload.upazila,
                    payload.source_updated_at_raw,
                    json.dumps(payload.source_fields, ensure_ascii=False, sort_keys=True),
                    retrieved_at,
                ),
            )
        version_id = int(
            self.conn.execute(
                """SELECT external_version_id FROM external_record_versions
                   WHERE external_record_id=? AND content_sha256=?""",
                (external_record_id, content_hash),
            ).fetchone()[0]
        )

        typed_observations = extract_typed_observations(payload)
        with self.conn:
            for observation in typed_observations:
                fingerprint = {
                    "observation_type": observation.observation_type,
                    "scope": str(observation.scope),
                    "value_text": observation.value_text,
                    "value_numeric": observation.value_numeric,
                    "unit": observation.unit,
                    "raw_label": observation.raw_label,
                    "raw_value": observation.raw_value,
                }
                observation_hash = sha256_text(
                    json.dumps(
                        fingerprint,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                self.conn.execute(
                    """INSERT OR IGNORE INTO external_typed_observations(
                           external_version_id, source_name, observation_type, scope,
                           value_text, value_numeric, unit, raw_label, raw_value,
                           source_updated_at_raw, observed_at, observation_sha256
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        version_id,
                        payload.source_name,
                        observation.observation_type,
                        str(observation.scope),
                        observation.value_text,
                        observation.value_numeric,
                        observation.unit,
                        observation.raw_label,
                        observation.raw_value,
                        payload.source_updated_at_raw,
                        retrieved_at,
                        observation_hash,
                    ),
                )

        typed_count = int(
            self.conn.execute(
                """SELECT COUNT(*) FROM external_typed_observations
                   WHERE external_version_id=?""",
                (version_id,),
            ).fetchone()[0]
        )
        return {
            "external_record_id": external_record_id,
            "external_version_id": version_id,
            "source_name": payload.source_name,
            "external_key": payload.external_key,
            "content_sha256": content_hash,
            "typed_observations": typed_count,
        }

    def _dife_match_record(
        self,
        validation_label: str,
        dife_public_id: int,
    ) -> DifeMatchRecord:
        row = self.conn.execute(
            """WITH latest_list AS (
                   SELECT eo.*,
                          ROW_NUMBER() OVER(
                              PARTITION BY eo.dife_public_id
                              ORDER BY eo.observed_at DESC, eo.observation_id DESC
                          ) AS rn
                   FROM establishment_observations eo
               ),
               latest_detail AS (
                   SELECT d.*,
                          ROW_NUMBER() OVER(
                              PARTITION BY d.validation_label, d.dife_public_id
                              ORDER BY d.observed_at DESC, d.detail_observation_id DESC
                          ) AS rn
                   FROM detail_observations d
                   WHERE d.validation_label=?
               )
               SELECT
                   v.dife_public_id,
                   v.sector_family,
                   COALESCE(ld.name_en, ld.name_bn, ll.name) AS match_name,
                   ld.address AS match_address,
                   COALESCE(ld.district, ll.district) AS match_district,
                   COALESCE(ld.upazila, ll.upazila) AS match_upazila
               FROM validation_sample v
               LEFT JOIN latest_list ll
                 ON ll.dife_public_id=v.dife_public_id AND ll.rn=1
               LEFT JOIN latest_detail ld
                 ON ld.dife_public_id=v.dife_public_id AND ld.rn=1
               WHERE v.validation_label=? AND v.dife_public_id=?""",
            (validation_label, validation_label, dife_public_id),
        ).fetchone()
        if row is None:
            raise KeyError(
                f"DIFE validation record not found: {validation_label} {dife_public_id}"
            )
        return DifeMatchRecord(
            public_id=int(row["dife_public_id"]),
            name=row["match_name"],
            address=row["match_address"],
            district=row["match_district"],
            upazila=row["match_upazila"],
            sector_family=str(row["sector_family"]),
        )

    def _external_payload(self, external_record_id: int) -> ExternalRecordPayload:
        row = self.conn.execute(
            """SELECT r.source_name, r.external_key, r.source_url,
                      v.entity_name, v.site_text, v.district, v.upazila,
                      v.source_updated_at_raw, v.source_fields_json
               FROM external_source_records r
               JOIN external_record_versions v
                 ON v.external_record_id=r.external_record_id
               WHERE r.external_record_id=?
               ORDER BY v.observed_at DESC, v.external_version_id DESC
               LIMIT 1""",
            (external_record_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"external record not found: {external_record_id}")
        return ExternalRecordPayload(
            source_name=str(row["source_name"]),
            external_key=str(row["external_key"]),
            entity_name=str(row["entity_name"]),
            site_text=row["site_text"],
            district=row["district"],
            upazila=row["upazila"],
            source_url=str(row["source_url"]),
            source_updated_at_raw=row["source_updated_at_raw"],
            source_fields=json.loads(str(row["source_fields_json"])),
        )

    def _attach_typed_observations_to_link(
        self,
        entity_link_id: int,
        *,
        validation_label: str,
        dife_public_id: int,
        external_record_id: int,
        match_type: str,
        site_level_match: bool,
        linked_at: str,
    ) -> int:
        """Attach only typed observations permitted by the validated linkage scope."""
        if match_type not in {"EXACT_SITE", "PROBABLE_SITE", "ORGANIZATION_ONLY"}:
            return 0

        latest = self.conn.execute(
            """SELECT external_version_id
               FROM external_record_versions
               WHERE external_record_id=?
               ORDER BY observed_at DESC, external_version_id DESC
               LIMIT 1""",
            (external_record_id,),
        ).fetchone()
        if latest is None:
            return 0

        rows = self.conn.execute(
            """SELECT typed_observation_id, scope
               FROM external_typed_observations
               WHERE external_version_id=?
               ORDER BY typed_observation_id""",
            (int(latest["external_version_id"]),),
        ).fetchall()

        linked = 0
        for row in rows:
            scope = str(row["scope"])
            if scope == str(ObservationScope.SITE) and not site_level_match:
                continue
            before = self.conn.total_changes
            self.conn.execute(
                """INSERT OR IGNORE INTO linked_intelligence_observations(
                       entity_link_id, typed_observation_id, validation_label,
                       dife_public_id, display_scope, site_attributable, linked_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                (
                    entity_link_id,
                    int(row["typed_observation_id"]),
                    validation_label,
                    dife_public_id,
                    scope,
                    int(scope == str(ObservationScope.SITE) and site_level_match),
                    linked_at,
                ),
            )
            if self.conn.total_changes > before:
                linked += 1
        return linked

    def intelligence_for_establishment(
        self,
        validation_label: str,
        dife_public_id: int,
    ) -> list[dict[str, object]]:
        """Return typed intelligence from the latest validated link per source."""
        rows = self.conn.execute(
            """WITH latest_links AS (
                   SELECT el.*,
                          ROW_NUMBER() OVER(
                              PARTITION BY el.validation_label, el.dife_public_id, el.source_name
                              ORDER BY el.created_at DESC, el.entity_link_id DESC
                          ) AS rn
                   FROM entity_links el
                   WHERE el.validation_label=? AND el.dife_public_id=?
               )
               SELECT
                   li.linked_intelligence_id,
                   ll.source_name,
                   ll.match_type,
                   ll.site_level_match,
                   t.observation_type,
                   t.scope AS source_scope,
                   li.display_scope,
                   li.site_attributable,
                   t.value_text,
                   t.value_numeric,
                   t.unit,
                   t.raw_label,
                   t.raw_value,
                   t.source_updated_at_raw,
                   t.observed_at
               FROM latest_links ll
               JOIN linked_intelligence_observations li
                 ON li.entity_link_id=ll.entity_link_id
               JOIN external_typed_observations t
                 ON t.typed_observation_id=li.typed_observation_id
               WHERE ll.rn=1
               ORDER BY ll.source_name, t.observation_type, t.typed_observation_id""",
            (validation_label, dife_public_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def establishment_intelligence_profile(
        self,
        validation_label: str,
        dife_public_id: int,
    ) -> dict[str, object]:
        dife = self._dife_match_record(validation_label, dife_public_id)
        observations = self.intelligence_for_establishment(
            validation_label,
            dife_public_id,
        )
        grouped: dict[str, list[dict[str, object]]] = {}
        for observation in observations:
            grouped.setdefault(str(observation["observation_type"]), []).append(observation)
        return {
            "dife_public_id": dife.public_id,
            "name": dife.name,
            "address": dife.address,
            "district": dife.district,
            "upazila": dife.upazila,
            "sector_family": dife.sector_family,
            "intelligence": grouped,
        }

    def _product_base_record(
        self,
        validation_label: str,
        dife_public_id: int,
    ) -> ProductBaseRecord:
        row = self.conn.execute(
            """WITH latest_list AS (
                   SELECT eo.*,
                          ROW_NUMBER() OVER(
                              PARTITION BY eo.dife_public_id
                              ORDER BY eo.observed_at DESC, eo.observation_id DESC
                          ) AS rn
                   FROM establishment_observations eo
               ),
               latest_detail AS (
                   SELECT d.*,
                          ROW_NUMBER() OVER(
                              PARTITION BY d.validation_label, d.dife_public_id
                              ORDER BY d.observed_at DESC, d.detail_observation_id DESC
                          ) AS rn
                   FROM detail_observations d
                   WHERE d.validation_label=?
               )
               SELECT
                   v.dife_public_id,
                   COALESCE(ld.name_en, ld.name_bn, ll.name, e.canonical_name) AS product_name,
                   ld.address AS product_address,
                   COALESCE(ld.upazila, ll.upazila) AS product_upazila,
                   COALESCE(ld.district, ll.district) AS product_district,
                   COALESCE(ld.division, ll.division) AS product_division,
                   COALESCE(ld.status, ll.status) AS product_status,
                   COALESCE(ld.sector, ll.sector) AS product_sector,
                   ld.establishment_type,
                   COALESCE(ld.licence_class, ll.licence_class) AS product_class,
                   ld.licence_expiry_raw,
                   ld.worker_total,
                   COALESCE(ld.observed_at, ll.observed_at) AS product_observed_at
               FROM validation_sample v
               JOIN establishments e ON e.dife_public_id=v.dife_public_id
               LEFT JOIN latest_list ll
                 ON ll.dife_public_id=v.dife_public_id AND ll.rn=1
               LEFT JOIN latest_detail ld
                 ON ld.dife_public_id=v.dife_public_id AND ld.rn=1
               WHERE v.validation_label=? AND v.dife_public_id=?""",
            (validation_label, validation_label, dife_public_id),
        ).fetchone()
        if row is None:
            raise KeyError(
                f"validation establishment not found: {validation_label} {dife_public_id}"
            )
        return ProductBaseRecord(
            public_id=int(row["dife_public_id"]),
            name=row["product_name"],
            address=row["product_address"],
            upazila=row["product_upazila"],
            district=row["product_district"],
            division=row["product_division"],
            official_status=row["product_status"],
            industrial_sector=row["product_sector"],
            establishment_type=row["establishment_type"],
            licence_class=row["product_class"],
            licence_expiry_raw=row["licence_expiry_raw"],
            worker_total=row["worker_total"],
            observed_at=row["product_observed_at"],
        )

    def intelligence_history_for_establishment(
        self,
        validation_label: str,
        dife_public_id: int,
    ) -> list[dict[str, object]]:
        """Return all linked typed observations retained for analytical history."""
        rows = self.conn.execute(
            """SELECT
                   el.source_name,
                   el.match_type,
                   el.site_level_match,
                   t.observation_type,
                   t.scope AS source_scope,
                   li.display_scope,
                   li.site_attributable,
                   t.value_text,
                   t.value_numeric,
                   t.unit,
                   t.source_updated_at_raw,
                   t.observed_at,
                   el.created_at AS linked_at
               FROM entity_links el
               JOIN linked_intelligence_observations li
                 ON li.entity_link_id=el.entity_link_id
               JOIN external_typed_observations t
                 ON t.typed_observation_id=li.typed_observation_id
               WHERE el.validation_label=? AND el.dife_public_id=?
               ORDER BY t.observed_at, el.source_name, t.observation_type,
                        li.linked_intelligence_id""",
            (validation_label, dife_public_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def validation_sample_cluster_context(
        self,
        validation_label: str,
        dife_public_id: int,
    ) -> dict[str, object]:
        """Descriptive sample context only; never a national-cluster claim."""
        target = self.conn.execute(
            """WITH latest_list AS (
                   SELECT eo.*,
                          ROW_NUMBER() OVER(
                              PARTITION BY eo.dife_public_id
                              ORDER BY eo.observed_at DESC, eo.observation_id DESC
                          ) AS rn
                   FROM establishment_observations eo
               )
               SELECT v.sector_family, ll.district
               FROM validation_sample v
               LEFT JOIN latest_list ll
                 ON ll.dife_public_id=v.dife_public_id AND ll.rn=1
               WHERE v.validation_label=? AND v.dife_public_id=?""",
            (validation_label, dife_public_id),
        ).fetchone()
        if target is None:
            raise KeyError(
                f"validation establishment not found: {validation_label} {dife_public_id}"
            )

        rows = self.conn.execute(
            """WITH latest_list AS (
                   SELECT eo.*,
                          ROW_NUMBER() OVER(
                              PARTITION BY eo.dife_public_id
                              ORDER BY eo.observed_at DESC, eo.observation_id DESC
                          ) AS rn
                   FROM establishment_observations eo
               )
               SELECT v.sector_family, ll.district
               FROM validation_sample v
               LEFT JOIN latest_list ll
                 ON ll.dife_public_id=v.dife_public_id AND ll.rn=1
               WHERE v.validation_label=?""",
            (validation_label,),
        ).fetchall()
        universe = [
            {
                "sector_family": str(row["sector_family"]),
                "district": row["district"],
            }
            for row in rows
        ]
        return cluster_context(
            universe,
            district=target["district"],
            sector_family=str(target["sector_family"]),
            universe_label=validation_label,
            universe_kind=UniverseKind.VALIDATION_SAMPLE,
        )

    def product_establishment_payload(
        self,
        validation_label: str,
        dife_public_id: int,
        *,
        generated_at: str,
    ) -> dict[str, object]:
        """Build the safe v1 product representation for one establishment."""
        base = self._product_base_record(validation_label, dife_public_id)
        observations = self.intelligence_for_establishment(
            validation_label,
            dife_public_id,
        )
        history = self.intelligence_history_for_establishment(
            validation_label,
            dife_public_id,
        )
        sample_cluster = self.validation_sample_cluster_context(
            validation_label,
            dife_public_id,
        )
        return build_product_payload(
            base,
            observations,
            generated_at=generated_at,
            history=history,
            cluster_context=sample_cluster,
        )

    def product_validation_feed(
        self,
        validation_label: str,
        *,
        generated_at: str,
    ) -> list[dict[str, object]]:
        """Build a safe product feed without exposing internal database identifiers."""
        rows = self.conn.execute(
            """SELECT dife_public_id
               FROM validation_sample
               WHERE validation_label=?
               ORDER BY dife_public_id""",
            (validation_label,),
        ).fetchall()
        if not rows:
            raise ValueError(f"validation sample not found: {validation_label!r}")
        return [
            self.product_establishment_payload(
                validation_label,
                int(row["dife_public_id"]),
                generated_at=generated_at,
            )
            for row in rows
        ]

    def review_external_link(
        self,
        validation_label: str,
        dife_public_id: int,
        external_record_id: int,
        *,
        reviewed_at: str,
        multiple_candidates: bool = False,
        rule_version: str = "1.3",
    ) -> dict[str, object]:
        dife = self._dife_match_record(validation_label, dife_public_id)
        external = self._external_payload(external_record_id)
        target = self.conn.execute(
            """SELECT eligible FROM enrichment_targets
               WHERE validation_label=? AND source_name=? AND dife_public_id=?""",
            (validation_label, external.source_name, dife_public_id),
        ).fetchone()
        if target is None:
            raise ValueError(
                "enrichment target must be planned before a source record can be reviewed"
            )

        decision = decide_external_link(
            dife,
            external,
            multiple_candidates=multiple_candidates,
        )

        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO entity_links(
                       validation_label, dife_public_id, source_name,
                       external_record_id, match_type, site_level_match,
                       rule_version, created_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    validation_label,
                    dife_public_id,
                    external.source_name,
                    external_record_id,
                    str(decision.match_type),
                    int(decision.site_level_match),
                    rule_version,
                    reviewed_at,
                ),
            )
            link_id = int(cursor.lastrowid)
            self.conn.executemany(
                """INSERT INTO match_evidence(
                       entity_link_id, evidence_type, dife_value,
                       external_value, result, note
                   ) VALUES(?,?,?,?,?,?)""",
                [
                    (
                        link_id,
                        component.evidence_type,
                        component.dife_value,
                        component.external_value,
                        component.result,
                        component.note,
                    )
                    for component in decision.evidence
                ],
            )
            self.conn.execute(
                """UPDATE enrichment_targets
                   SET status='REVIEWED'
                   WHERE validation_label=? AND source_name=? AND dife_public_id=?""",
                (validation_label, external.source_name, dife_public_id),
            )
            typed_linked = self._attach_typed_observations_to_link(
                link_id,
                validation_label=validation_label,
                dife_public_id=dife_public_id,
                external_record_id=external_record_id,
                match_type=str(decision.match_type),
                site_level_match=decision.site_level_match,
                linked_at=reviewed_at,
            )
        return {
            "entity_link_id": link_id,
            "match_type": str(decision.match_type),
            "site_level_match": decision.site_level_match,
            "typed_observations_linked": typed_linked,
        }

    def enrichment_coverage(
        self,
        validation_label: str,
        source_name: str,
    ) -> EnrichmentCoverage:
        source_name = source_name.upper()
        target = self.conn.execute(
            """SELECT COUNT(*) AS n
               FROM enrichment_targets
               WHERE validation_label=? AND source_name=? AND eligible=1""",
            (validation_label, source_name),
        ).fetchone()
        eligible = int(target["n"] if target else 0)

        staged = int(
            self.conn.execute(
                """SELECT COUNT(DISTINCT external_record_id)
                   FROM entity_links
                   WHERE validation_label=? AND source_name=?""",
                (validation_label, source_name),
            ).fetchone()[0]
        )

        rows = self.conn.execute(
            """WITH latest_link AS (
                   SELECT el.*,
                          ROW_NUMBER() OVER(
                              PARTITION BY el.validation_label, el.dife_public_id, el.source_name
                              ORDER BY el.created_at DESC, el.entity_link_id DESC
                          ) AS rn
                   FROM entity_links el
                   WHERE el.validation_label=? AND el.source_name=?
               )
               SELECT match_type, COUNT(*) AS n
               FROM latest_link
               WHERE rn=1
               GROUP BY match_type""",
            (validation_label, source_name),
        ).fetchall()
        counts = {str(row["match_type"]): int(row["n"]) for row in rows}
        return EnrichmentCoverage(
            source_name=source_name,
            eligible=eligible,
            staged_records=staged,
            exact_site=counts.get("EXACT_SITE", 0),
            probable_site=counts.get("PROBABLE_SITE", 0),
            organization_only=counts.get("ORGANIZATION_ONLY", 0),
            ambiguous=counts.get("AMBIGUOUS", 0),
            no_match=counts.get("NO_MATCH", 0),
            feasibility_only=counts.get("SOURCE_FEASIBILITY_ONLY", 0),
        )

    def generate_enrichment_report(
        self,
        validation_label: str,
        source_name: str,
        *,
        generated_at: str,
    ) -> tuple[int, EnrichmentCoverage]:
        coverage = self.enrichment_coverage(validation_label, source_name)
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO enrichment_reports(
                       validation_label, source_name, generated_at, coverage_json
                   ) VALUES(?,?,?,?)""",
                (
                    validation_label,
                    source_name.upper(),
                    generated_at,
                    json.dumps(asdict(coverage), sort_keys=True),
                ),
            )
        return int(cursor.lastrowid), coverage


    def _candidate_records_for_source(
        self,
        source_name: str,
    ) -> list[CandidateRecord]:
        rows = self.conn.execute(
            """SELECT external_record_id
               FROM external_source_records
               WHERE source_name=?
               ORDER BY external_record_id""",
            (source_name.upper(),),
        ).fetchall()
        return [
            CandidateRecord(
                external_record_id=int(row["external_record_id"]),
                payload=self._external_payload(int(row["external_record_id"])),
            )
            for row in rows
        ]

    def generate_external_candidates(
        self,
        validation_label: str,
        source_name: str,
        *,
        generated_at: str,
        max_candidates: int = 5,
    ) -> dict[str, int]:
        """Shortlist and resolve candidates from the currently staged source index.

        An empty shortlist is recorded as NO_STAGED_CANDIDATE and never converted
        into a negative business fact.
        """
        if max_candidates <= 0:
            raise ValueError("max_candidates must be positive")
        source_name = source_name.upper()
        self._ensure_external_source_profile(source_name)

        targets = self.conn.execute(
            """SELECT dife_public_id
               FROM enrichment_targets
               WHERE validation_label=? AND source_name=? AND eligible=1
               ORDER BY dife_public_id""",
            (validation_label, source_name),
        ).fetchall()
        if not targets:
            raise ValueError(
                f"no eligible enrichment targets planned for {validation_label!r} {source_name}"
            )

        source_records = self._candidate_records_for_source(source_name)
        block_index = CandidateBlockIndex.build(source_records)
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO external_candidate_runs(
                       validation_label, source_name, generated_at, max_candidates,
                       staged_source_records, targets_considered, candidates_generated,
                       auto_selected, ambiguous, review_required, no_staged_candidate
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    validation_label,
                    source_name,
                    generated_at,
                    max_candidates,
                    len(source_records),
                    len(targets),
                    0, 0, 0, 0, 0,
                ),
            )
            run_id = int(cursor.lastrowid)

        total_candidates = 0
        outcome_counts = {
            "AUTO_SELECTED": 0,
            "AMBIGUOUS": 0,
            "REVIEW_REQUIRED": 0,
            "NO_STAGED_CANDIDATE": 0,
        }

        source_by_id = {
            record.external_record_id: record
            for record in source_records
        }

        for target in targets:
            dife_public_id = int(target["dife_public_id"])
            dife = self._dife_match_record(validation_label, dife_public_id)
            blocked_records = block_index.records_for(dife)
            signals = shortlist_candidates(
                dife,
                blocked_records,
                max_candidates=max_candidates,
            )
            shortlisted = [
                source_by_id[signal.external_record_id]
                for signal in signals
            ]
            resolution = resolve_shortlist(dife, shortlisted)
            outcome_counts[str(resolution.outcome)] += 1
            total_candidates += len(signals)

            with self.conn:
                self.conn.executemany(
                    """INSERT INTO external_match_candidates(
                           run_id, validation_label, dife_public_id, source_name,
                           external_record_id, shortlist_position, priority_class,
                           name_strength, name_token_overlap, district_result,
                           upazila_result, address_result, address_overlap
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [
                        (
                            run_id,
                            validation_label,
                            dife_public_id,
                            source_name,
                            signal.external_record_id,
                            position,
                            str(signal.priority),
                            signal.name_strength,
                            signal.name_token_overlap,
                            signal.district_result,
                            signal.upazila_result,
                            signal.address_result,
                            signal.address_overlap,
                        )
                        for position, signal in enumerate(signals, start=1)
                    ],
                )
                self.conn.execute(
                    """INSERT INTO external_resolution_outcomes(
                           run_id, validation_label, dife_public_id, source_name,
                           outcome, candidate_count, selected_external_record_id,
                           selected_match_type, note
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        run_id,
                        validation_label,
                        dife_public_id,
                        source_name,
                        str(resolution.outcome),
                        resolution.candidate_count,
                        resolution.selected_external_record_id,
                        (
                            None
                            if resolution.selected_match_type is None
                            else str(resolution.selected_match_type)
                        ),
                        resolution.note,
                    ),
                )
                if signals:
                    self.conn.execute(
                        """UPDATE enrichment_targets
                           SET status=CASE
                               WHEN status='PENDING' THEN 'STAGED'
                               ELSE status
                           END
                           WHERE validation_label=? AND source_name=? AND dife_public_id=?""",
                        (validation_label, source_name, dife_public_id),
                    )

        with self.conn:
            self.conn.execute(
                """UPDATE external_candidate_runs
                   SET candidates_generated=?, auto_selected=?, ambiguous=?,
                       review_required=?, no_staged_candidate=?
                   WHERE run_id=?""",
                (
                    total_candidates,
                    outcome_counts["AUTO_SELECTED"],
                    outcome_counts["AMBIGUOUS"],
                    outcome_counts["REVIEW_REQUIRED"],
                    outcome_counts["NO_STAGED_CANDIDATE"],
                    run_id,
                ),
            )

        return {
            "run_id": run_id,
            "targets_considered": len(targets),
            "staged_source_records": len(source_records),
            "candidates_generated": total_candidates,
            "auto_selected": outcome_counts["AUTO_SELECTED"],
            "ambiguous": outcome_counts["AMBIGUOUS"],
            "review_required": outcome_counts["REVIEW_REQUIRED"],
            "no_staged_candidate": outcome_counts["NO_STAGED_CANDIDATE"],
        }

    def candidate_run_outcomes(
        self,
        run_id: int,
    ) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """SELECT dife_public_id, source_name, outcome, candidate_count,
                      selected_external_record_id, selected_match_type, note,
                      applied_entity_link_id
               FROM external_resolution_outcomes
               WHERE run_id=?
               ORDER BY dife_public_id""",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def candidates_for_target(
        self,
        run_id: int,
        dife_public_id: int,
    ) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """SELECT c.shortlist_position, c.priority_class, c.name_strength,
                      c.name_token_overlap, c.district_result, c.upazila_result,
                      c.address_result, c.address_overlap, c.external_record_id,
                      r.external_key, r.entity_name, r.site_text, r.district, r.upazila
               FROM external_match_candidates c
               JOIN external_source_records r
                 ON r.external_record_id=c.external_record_id
               WHERE c.run_id=? AND c.dife_public_id=?
               ORDER BY c.shortlist_position""",
            (run_id, dife_public_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def apply_auto_resolutions(
        self,
        run_id: int,
        *,
        applied_at: str,
        rule_version: str = "1.4",
    ) -> int:
        """Create entity links only for unambiguous AUTO_SELECTED outcomes."""
        rows = self.conn.execute(
            """SELECT outcome_id, validation_label, dife_public_id,
                      selected_external_record_id
               FROM external_resolution_outcomes
               WHERE run_id=? AND outcome='AUTO_SELECTED'
                 AND applied_entity_link_id IS NULL
               ORDER BY dife_public_id""",
            (run_id,),
        ).fetchall()

        applied = 0
        for row in rows:
            external_record_id = row["selected_external_record_id"]
            if external_record_id is None:
                raise RuntimeError("AUTO_SELECTED outcome is missing its external record")
            link = self.review_external_link(
                str(row["validation_label"]),
                int(row["dife_public_id"]),
                int(external_record_id),
                reviewed_at=applied_at,
                multiple_candidates=False,
                rule_version=rule_version,
            )
            with self.conn:
                self.conn.execute(
                    """UPDATE external_resolution_outcomes
                       SET applied_entity_link_id=?
                       WHERE outcome_id=?""",
                    (int(link["entity_link_id"]), int(row["outcome_id"])),
                )
            applied += 1
        return applied


    def create_external_index_run(
        self,
        source_name: str,
        *,
        seed_url: str,
        started_at: str,
        notes: str | None = None,
    ) -> int:
        """Create a source-index run with only the seed page authorized initially."""
        source_name = source_name.upper()
        if source_name not in {"BGMEA", "EPB"}:
            raise ValueError("v1.5 source-index discovery currently supports BGMEA and EPB")
        self._ensure_external_source_profile(source_name)
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO external_index_runs(
                       source_name, seed_url, started_at, status, pages_planned, notes
                   ) VALUES(?,?,?,?,?,?)""",
                (source_name, seed_url, started_at, "RUNNING", 1, notes),
            )
            run_id = int(cursor.lastrowid)
            self.conn.execute(
                """INSERT INTO external_index_pages(
                       run_id, page, source_url, reason, status, planned_at
                   ) VALUES(?,?,?,?,?,?)""",
                (run_id, 1, seed_url, "INDEX_SEED", "PLANNED", started_at),
            )
        return run_id

    def external_index_requests(
        self,
        run_id: int,
        *,
        status: str = "PLANNED",
    ) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """SELECT index_page_id, page, source_url, reason, status
               FROM external_index_pages
               WHERE run_id=? AND status=?
               ORDER BY page""",
            (run_id, status),
        ).fetchall()
        return [dict(row) for row in rows]

    def ingest_external_index_page(
        self,
        run_id: int,
        payload: str | bytes,
        *,
        source_url: str,
        retrieved_at: str,
        content_format: str = "html",
        raw_payload_path: str | None = None,
        parser_version: str = "1.5",
    ) -> dict[str, object]:
        """Stage one BGMEA/EPB directory page and append structured record versions."""
        run = self.conn.execute(
            """SELECT source_name, status FROM external_index_runs WHERE run_id=?""",
            (run_id,),
        ).fetchone()
        if run is None:
            raise KeyError(f"external index run not found: {run_id}")
        if run["status"] != "RUNNING":
            raise ValueError("external index run is not RUNNING")

        page_row = self.conn.execute(
            """SELECT index_page_id, page, status
               FROM external_index_pages
               WHERE run_id=? AND source_url=?""",
            (run_id, source_url),
        ).fetchone()
        if page_row is None:
            raise ValueError("index page was not pre-planned for this run")
        if page_row["status"] == "STAGED":
            raise ValueError("index page is already STAGED")

        source_name = str(run["source_name"])
        if isinstance(payload, bytes):
            payload_bytes = payload
            payload_text = payload.decode("utf-8", errors="replace")
        else:
            payload_text = payload
            payload_bytes = payload.encode("utf-8")

        fmt = content_format.lower()
        if source_name == "BGMEA":
            if fmt != "html":
                raise ValueError("BGMEA index parser currently expects HTML")
            metadata, records = parse_bgmea_member_index(payload_text, source_url=source_url)
        elif source_name == "EPB":
            if fmt == "json":
                metadata, records = parse_epb_exporter_index_json(payload_text, source_url=source_url)
            elif fmt == "html":
                metadata, records = parse_epb_exporter_index_html(payload_text, source_url=source_url)
            else:
                raise ValueError("EPB index format must be html or json")
        else:
            raise ValueError(f"unsupported index source: {source_name}")

        content_hash = sha256_text(payload_text)
        with self.conn:
            self.conn.execute(
                """INSERT OR IGNORE INTO source_snapshots(
                       source_name, source_url, retrieved_at, source_reported_at_raw,
                       source_total_records, content_sha256, raw_payload_path, parser_version
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    f"{source_name} INDEX",
                    source_url,
                    retrieved_at,
                    None,
                    metadata.total_records,
                    content_hash,
                    raw_payload_path,
                    parser_version,
                ),
            )
            snapshot_id = int(
                self.conn.execute(
                    """SELECT snapshot_id FROM source_snapshots
                       WHERE source_name=? AND source_url=? AND content_sha256=?""",
                    (f"{source_name} INDEX", source_url, content_hash),
                ).fetchone()[0]
            )
            index_page_id = int(page_row["index_page_id"])
            self.conn.execute(
                """UPDATE external_index_pages
                   SET status='STAGED', staged_at=?, snapshot_id=?, content_format=?,
                       records_parsed=?, source_reported_total=?,
                       source_reported_last_page=?, error_message=NULL
                   WHERE index_page_id=?""",
                (
                    retrieved_at,
                    snapshot_id,
                    fmt,
                    len(records),
                    metadata.total_records,
                    metadata.last_page,
                    index_page_id,
                ),
            )

            for record in records:
                self.conn.execute(
                    """INSERT INTO external_index_records(
                           source_name, source_key, entity_name, detail_url,
                           registration_no, district, upazila, office_address,
                           factory_address, first_seen_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(source_name, source_key) DO UPDATE SET
                         entity_name=excluded.entity_name,
                         detail_url=excluded.detail_url,
                         registration_no=excluded.registration_no,
                         district=excluded.district,
                         upazila=excluded.upazila,
                         office_address=excluded.office_address,
                         factory_address=excluded.factory_address""",
                    (
                        record.source_name,
                        record.source_key,
                        record.entity_name,
                        record.detail_url,
                        record.registration_no,
                        record.district,
                        record.upazila,
                        record.office_address,
                        record.factory_address,
                        retrieved_at,
                    ),
                )
                index_record_id = int(
                    self.conn.execute(
                        """SELECT index_record_id FROM external_index_records
                           WHERE source_name=? AND source_key=?""",
                        (record.source_name, record.source_key),
                    ).fetchone()[0]
                )
                row_hash = sha256_text(
                    json.dumps(asdict(record), ensure_ascii=False, sort_keys=True)
                )
                self.conn.execute(
                    """INSERT OR IGNORE INTO external_index_record_versions(
                           index_record_id, run_id, index_page_id, row_sha256,
                           entity_name, detail_url, registration_no, district,
                           upazila, office_address, factory_address, observed_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        index_record_id,
                        run_id,
                        index_page_id,
                        row_hash,
                        record.entity_name,
                        record.detail_url,
                        record.registration_no,
                        record.district,
                        record.upazila,
                        record.office_address,
                        record.factory_address,
                        retrieved_at,
                    ),
                )

            current_total = self.conn.execute(
                """SELECT COALESCE(SUM(records_parsed),0)
                   FROM external_index_pages
                   WHERE run_id=? AND status='STAGED'""",
                (run_id,),
            ).fetchone()[0]
            unique_keys = self.conn.execute(
                """SELECT COUNT(DISTINCT index_record_id)
                   FROM external_index_record_versions
                   WHERE run_id=?""",
                (run_id,),
            ).fetchone()[0]
            self.conn.execute(
                """UPDATE external_index_runs
                   SET source_reported_total=COALESCE(?, source_reported_total),
                       source_reported_last_page=COALESCE(?, source_reported_last_page),
                       pages_staged=(
                         SELECT COUNT(*) FROM external_index_pages
                         WHERE run_id=? AND status='STAGED'
                       ),
                       records_discovered=?,
                       unique_keys=?
                   WHERE run_id=?""",
                (
                    metadata.total_records,
                    metadata.last_page,
                    run_id,
                    int(current_total),
                    int(unique_keys),
                    run_id,
                ),
            )

        return {
            "run_id": run_id,
            "page": int(page_row["page"]),
            "snapshot_id": snapshot_id,
            "records_parsed": len(records),
            "source_reported_total": metadata.total_records,
            "source_reported_last_page": metadata.last_page,
            "content_sha256": content_hash,
        }

    def expand_external_index_run(
        self,
        run_id: int,
        *,
        planned_at: str,
        max_pages: int | None = None,
    ) -> int:
        """Expand from the staged seed page only when the source exposes page bounds."""
        run = self.conn.execute(
            """SELECT source_name, seed_url, source_reported_total,
                      source_reported_last_page, status
               FROM external_index_runs WHERE run_id=?""",
            (run_id,),
        ).fetchone()
        if run is None:
            raise KeyError(f"external index run not found: {run_id}")
        if run["status"] != "RUNNING":
            raise ValueError("external index run is not RUNNING")

        seed = self.conn.execute(
            """SELECT status, records_parsed FROM external_index_pages
               WHERE run_id=? AND page=1""",
            (run_id,),
        ).fetchone()
        if seed is None or seed["status"] != "STAGED":
            raise ValueError("seed index page must be STAGED before expansion")

        from .source_index import SourceIndexMetadata
        metadata = SourceIndexMetadata(
            source_name=str(run["source_name"]),
            total_records=run["source_reported_total"],
            current_page=1,
            last_page=run["source_reported_last_page"],
            records_on_page=int(seed["records_parsed"] or 0),
            has_next=(
                None
                if run["source_reported_last_page"] is None
                else int(run["source_reported_last_page"]) > 1
            ),
        )
        requests = plan_index_requests(
            str(run["source_name"]),
            first_page_url=str(run["seed_url"]),
            metadata=metadata,
            max_pages=max_pages,
        )
        with self.conn:
            for request in requests:
                if request.page == 1:
                    continue
                self.conn.execute(
                    """INSERT OR IGNORE INTO external_index_pages(
                           run_id, page, source_url, reason, status, planned_at
                       ) VALUES(?,?,?,?,?,?)""",
                    (
                        run_id,
                        request.page,
                        request.source_url,
                        request.reason,
                        "PLANNED",
                        planned_at,
                    ),
                )
            pages_planned = int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM external_index_pages WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
            )
            self.conn.execute(
                "UPDATE external_index_runs SET pages_planned=? WHERE run_id=?",
                (pages_planned, run_id),
            )
        return pages_planned

    def mark_external_index_page_failed(
        self,
        run_id: int,
        source_url: str,
        *,
        failed_at: str,
        error_message: str,
    ) -> None:
        cursor = self.conn.execute(
            """UPDATE external_index_pages
               SET status='FAILED', staged_at=?, error_message=?
               WHERE run_id=? AND source_url=? AND status='PLANNED'""",
            (failed_at, error_message, run_id, source_url),
        )
        if cursor.rowcount != 1:
            raise ValueError("planned external index page not found")
        self.conn.commit()

    def finalize_external_index_run(
        self,
        run_id: int,
        *,
        completed_at: str,
    ) -> dict[str, object]:
        """Finalize only after every planned page has resolved."""
        unresolved = int(
            self.conn.execute(
                """SELECT COUNT(*) FROM external_index_pages
                   WHERE run_id=? AND status='PLANNED'""",
                (run_id,),
            ).fetchone()[0]
        )
        if unresolved:
            raise ValueError(f"external index run has {unresolved} unresolved page(s)")

        run = self.conn.execute(
            "SELECT source_name FROM external_index_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise KeyError(f"external index run not found: {run_id}")

        rows = self.conn.execute(
            """SELECT r.source_name, r.source_key, v.entity_name, v.detail_url,
                      v.registration_no, v.district, v.upazila,
                      v.office_address, v.factory_address
               FROM external_index_record_versions v
               JOIN external_index_records r ON r.index_record_id=v.index_record_id
               WHERE v.run_id=?
               ORDER BY v.index_version_id""",
            (run_id,),
        ).fetchall()
        records = [
            SourceIndexRecord(
                source_name=str(row["source_name"]),
                source_key=str(row["source_key"]),
                entity_name=str(row["entity_name"]),
                detail_url=str(row["detail_url"]),
                registration_no=row["registration_no"],
                district=row["district"],
                upazila=row["upazila"],
                office_address=row["office_address"],
                factory_address=row["factory_address"],
            )
            for row in rows
        ]
        expected_segment = "member" if str(run["source_name"]) == "BGMEA" else "exporter"
        quality = assess_index_quality(records, expected_segment=expected_segment)

        page_counts = self.conn.execute(
            """SELECT status, COUNT(*) AS n
               FROM external_index_pages
               WHERE run_id=? GROUP BY status""",
            (run_id,),
        ).fetchall()
        status_counts = {str(row["status"]): int(row["n"]) for row in page_counts}
        quality_dict = asdict(quality)
        quality_dict["page_status_counts"] = status_counts

        with self.conn:
            self.conn.execute(
                """UPDATE external_index_runs
                   SET completed_at=?, status=?, quality_json=?,
                       pages_staged=COALESCE(?, pages_staged),
                       records_discovered=?,
                       unique_keys=?
                   WHERE run_id=?""",
                (
                    completed_at,
                    "COMPLETED" if quality.valid and not status_counts.get("FAILED", 0) else "FAILED",
                    json.dumps(quality_dict, sort_keys=True),
                    status_counts.get("STAGED", 0),
                    len(records),
                    len({record.source_key for record in records}),
                    run_id,
                ),
            )
        return {
            "run_id": run_id,
            "source_name": str(run["source_name"]),
            "quality": quality_dict,
            "status": (
                "COMPLETED"
                if quality.valid and not status_counts.get("FAILED", 0)
                else "FAILED"
            ),
        }

    def _index_candidate_records(
        self,
        source_name: str,
        run_id: int,
    ) -> list[CandidateRecord]:
        rows = self.conn.execute(
            """WITH latest AS (
                   SELECT v.*,
                          ROW_NUMBER() OVER(
                              PARTITION BY v.index_record_id
                              ORDER BY v.observed_at DESC, v.index_version_id DESC
                          ) AS rn
                   FROM external_index_record_versions v
                   WHERE v.run_id=?
               )
               SELECT r.index_record_id, r.source_name, r.source_key,
                      l.entity_name, l.detail_url, l.district, l.upazila,
                      l.factory_address
               FROM latest l
               JOIN external_index_records r ON r.index_record_id=l.index_record_id
               WHERE l.rn=1 AND r.source_name=?
               ORDER BY r.index_record_id""",
            (run_id, source_name.upper()),
        ).fetchall()
        return [
            CandidateRecord(
                external_record_id=int(row["index_record_id"]),
                payload=ExternalRecordPayload(
                    source_name=str(row["source_name"]),
                    external_key=str(row["source_key"]),
                    entity_name=str(row["entity_name"]),
                    site_text=row["factory_address"],
                    district=row["district"],
                    upazila=row["upazila"],
                    source_url=str(row["detail_url"]),
                    source_updated_at_raw=None,
                    source_fields={},
                ),
            )
            for row in rows
        ]

    def plan_external_detail_requests_from_index(
        self,
        validation_label: str,
        source_name: str,
        run_id: int,
        *,
        planned_at: str,
        max_candidates: int = 5,
    ) -> dict[str, int]:
        """Use the staged directory index to fetch only plausible detail records."""
        source_name = source_name.upper()
        run = self.conn.execute(
            """SELECT source_name, status FROM external_index_runs WHERE run_id=?""",
            (run_id,),
        ).fetchone()
        if run is None or str(run["source_name"]) != source_name:
            raise ValueError("source-index run does not match requested source")
        if run["status"] != "COMPLETED":
            raise ValueError("source-index run must pass QC before detail requests are planned")

        targets = self.conn.execute(
            """SELECT dife_public_id
               FROM enrichment_targets
               WHERE validation_label=? AND source_name=? AND eligible=1
               ORDER BY dife_public_id""",
            (validation_label, source_name),
        ).fetchall()
        if not targets:
            raise ValueError("no eligible enrichment targets are planned")

        index_records = self._index_candidate_records(source_name, run_id)
        block_index = CandidateBlockIndex.build(index_records)
        by_id = {record.external_record_id: record for record in index_records}

        total_target_links = 0
        unique_request_ids: set[int] = set()
        no_candidate_targets = 0

        for target in targets:
            public_id = int(target["dife_public_id"])
            dife = self._dife_match_record(validation_label, public_id)
            blocked = block_index.records_for(dife)
            signals = shortlist_candidates(
                dife,
                blocked,
                max_candidates=max_candidates,
            )
            if not signals:
                no_candidate_targets += 1
                continue

            with self.conn:
                for position, signal in enumerate(signals, start=1):
                    record = by_id[signal.external_record_id]
                    self.conn.execute(
                        """INSERT INTO external_detail_requests(
                               source_name, source_key, detail_url, status, planned_at
                           ) VALUES(?,?,?,?,?)
                           ON CONFLICT(source_name, source_key, detail_url)
                           DO NOTHING""",
                        (
                            source_name,
                            record.payload.external_key,
                            record.payload.source_url,
                            "PLANNED",
                            planned_at,
                        ),
                    )
                    request_id = int(
                        self.conn.execute(
                            """SELECT request_id FROM external_detail_requests
                               WHERE source_name=? AND source_key=? AND detail_url=?""",
                            (
                                source_name,
                                record.payload.external_key,
                                record.payload.source_url,
                            ),
                        ).fetchone()[0]
                    )
                    self.conn.execute(
                        """INSERT OR REPLACE INTO external_detail_request_targets(
                               request_id, validation_label, dife_public_id,
                               index_record_id, shortlist_position, priority_class
                           ) VALUES(?,?,?,?,?,?)""",
                        (
                            request_id,
                            validation_label,
                            public_id,
                            signal.external_record_id,
                            position,
                            str(signal.priority),
                        ),
                    )
                    unique_request_ids.add(request_id)
                    total_target_links += 1

        return {
            "eligible_targets": len(targets),
            "index_records": len(index_records),
            "unique_detail_requests": len(unique_request_ids),
            "target_candidate_links": total_target_links,
            "no_candidate_targets": no_candidate_targets,
        }

    def external_detail_requests(
        self,
        source_name: str,
        *,
        status: str = "PLANNED",
    ) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """SELECT request_id, source_name, source_key, detail_url, status,
                      planned_at, resolved_at, external_record_id, error_message
               FROM external_detail_requests
               WHERE source_name=? AND status=?
               ORDER BY request_id""",
            (source_name.upper(), status),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_external_detail_fetched(
        self,
        request_id: int,
        *,
        external_record_id: int,
        resolved_at: str,
    ) -> None:
        cursor = self.conn.execute(
            """UPDATE external_detail_requests
               SET status='FETCHED', resolved_at=?, external_record_id=?,
                   error_message=NULL
               WHERE request_id=? AND status='PLANNED'""",
            (resolved_at, external_record_id, request_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("external detail request is not PLANNED")
        self.conn.commit()


    def mark_external_detail_failed(
        self,
        request_id: int,
        *,
        resolved_at: str,
        error_message: str,
    ) -> None:
        cursor = self.conn.execute(
            """UPDATE external_detail_requests
               SET status='FAILED', resolved_at=?, external_record_id=NULL,
                   error_message=?
               WHERE request_id=? AND status='PLANNED'""",
            (resolved_at, error_message, request_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("external detail request is not PLANNED")
        self.conn.commit()

    def external_detail_target_status_counts(
        self,
        validation_label: str,
        source_name: str,
    ) -> dict[str, int]:
        rows = self.conn.execute(
            """SELECT r.status, COUNT(DISTINCT r.request_id) AS n
               FROM external_detail_requests r
               JOIN external_detail_request_targets t
                 ON t.request_id=r.request_id
               WHERE t.validation_label=? AND r.source_name=?
               GROUP BY r.status
               ORDER BY r.status""",
            (validation_label, source_name.upper()),
        ).fetchall()
        return {str(row["status"]): int(row["n"]) for row in rows}


    def create_national_universe_run(
        self,
        universe_label: str,
        *,
        seed_url: str,
        started_at: str,
        page_size: int = 30,
        notes: str | None = None,
    ) -> int:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO national_universe_runs(
                       universe_label, seed_url, page_size, started_at, status,
                       pages_planned, notes
                   ) VALUES(?,?,?,?,?,?,?)""",
                (universe_label, seed_url, page_size, started_at, "RUNNING", 1, notes),
            )
            universe_id = int(cursor.lastrowid)
            self.conn.execute(
                """INSERT INTO national_universe_pages(
                       universe_id, page, source_url, status, planned_at
                   ) VALUES(?,?,?,?,?)""",
                (universe_id, 1, seed_url, "PLANNED", started_at),
            )
        return universe_id

    def national_universe_requests(
        self,
        universe_id: int,
        *,
        status: str = "PLANNED",
    ) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """SELECT page, source_url, status, planned_at, staged_at,
                      records_parsed, source_reported_total, error_message
               FROM national_universe_pages
               WHERE universe_id=? AND status=?
               ORDER BY page""",
            (universe_id, status),
        ).fetchall()
        return [dict(row) for row in rows]

    def ingest_national_universe_page(
        self,
        universe_id: int,
        html: str,
        *,
        source_url: str,
        retrieved_at: str,
        raw_payload_path: str | None = None,
        parser_version: str = "2.0",
    ) -> dict[str, object]:
        run = self.conn.execute(
            """SELECT status, expected_total FROM national_universe_runs
               WHERE universe_id=?""",
            (universe_id,),
        ).fetchone()
        if run is None:
            raise KeyError(f"national universe not found: {universe_id}")
        if run["status"] != "RUNNING":
            raise ValueError("national universe run is not RUNNING")

        page_row = self.conn.execute(
            """SELECT page, status FROM national_universe_pages
               WHERE universe_id=? AND source_url=?""",
            (universe_id, source_url),
        ).fetchone()
        if page_row is None or page_row["status"] != "PLANNED":
            raise ValueError("national page was not pre-planned or is already resolved")

        metadata, records = parse_dife_list_page(html)
        staged = self.ingest_dife_list_html(
            html,
            source_url=source_url,
            retrieved_at=retrieved_at,
            raw_payload_path=raw_payload_path,
            parser_version=parser_version,
        )
        snapshot_id = int(staged["snapshot_id"])
        page = int(page_row["page"])

        with self.conn:
            self.conn.execute(
                """UPDATE national_universe_pages
                   SET status='STAGED', staged_at=?, snapshot_id=?,
                       records_parsed=?, source_reported_total=?, error_message=NULL
                   WHERE universe_id=? AND page=?""",
                (
                    retrieved_at,
                    snapshot_id,
                    len(records),
                    metadata.total_records,
                    universe_id,
                    page,
                ),
            )
            for record in records:
                obs = self.conn.execute(
                    """SELECT observation_id
                       FROM establishment_observations
                       WHERE snapshot_id=? AND dife_public_id=?
                       ORDER BY observation_id DESC LIMIT 1""",
                    (snapshot_id, record.public_id),
                ).fetchone()
                if obs is None:
                    raise RuntimeError("staged DIFE observation not found")
                self.conn.execute(
                    """INSERT OR IGNORE INTO national_universe_page_members(
                           universe_id, page, dife_public_id, observation_id, snapshot_id
                       ) VALUES(?,?,?,?,?)""",
                    (
                        universe_id,
                        page,
                        record.public_id,
                        int(obs["observation_id"]),
                        snapshot_id,
                    ),
                )
            if run["expected_total"] is None and page == 1:
                self.conn.execute(
                    """UPDATE national_universe_runs
                       SET expected_total=?
                       WHERE universe_id=?""",
                    (metadata.total_records, universe_id),
                )
            self.conn.execute(
                """UPDATE national_universe_runs
                   SET pages_staged=(
                     SELECT COUNT(*) FROM national_universe_pages
                     WHERE universe_id=? AND status='STAGED'
                   )
                   WHERE universe_id=?""",
                (universe_id, universe_id),
            )
        return {
            "universe_id": universe_id,
            "page": page,
            "snapshot_id": snapshot_id,
            "records_parsed": len(records),
            "source_reported_total": metadata.total_records,
        }

    def expand_national_universe_run(
        self,
        universe_id: int,
        *,
        planned_at: str,
    ) -> int:
        run = self.conn.execute(
            """SELECT seed_url, page_size, expected_total, status
               FROM national_universe_runs WHERE universe_id=?""",
            (universe_id,),
        ).fetchone()
        if run is None:
            raise KeyError(f"national universe not found: {universe_id}")
        if run["status"] != "RUNNING":
            raise ValueError("national universe run is not RUNNING")
        seed = self.conn.execute(
            """SELECT status FROM national_universe_pages
               WHERE universe_id=? AND page=1""",
            (universe_id,),
        ).fetchone()
        if seed is None or seed["status"] != "STAGED":
            raise ValueError("seed page must be STAGED before expansion")
        expected_total = run["expected_total"]
        if expected_total is None or int(expected_total) <= 0:
            raise ValueError("seed page did not expose a positive source total")

        requests = plan_national_pages(
            int(expected_total),
            first_page_url=str(run["seed_url"]),
            page_size=int(run["page_size"]),
        )
        with self.conn:
            for request in requests:
                if request.page == 1:
                    continue
                self.conn.execute(
                    """INSERT OR IGNORE INTO national_universe_pages(
                           universe_id, page, source_url, status, planned_at
                       ) VALUES(?,?,?,?,?)""",
                    (
                        universe_id,
                        request.page,
                        request.source_url,
                        "PLANNED",
                        planned_at,
                    ),
                )
            pages_planned = int(
                self.conn.execute(
                    """SELECT COUNT(*) FROM national_universe_pages
                       WHERE universe_id=?""",
                    (universe_id,),
                ).fetchone()[0]
            )
            self.conn.execute(
                """UPDATE national_universe_runs
                   SET pages_planned=? WHERE universe_id=?""",
                (pages_planned, universe_id),
            )
        return pages_planned

    def mark_national_universe_page_failed(
        self,
        universe_id: int,
        source_url: str,
        *,
        failed_at: str,
        error_message: str,
    ) -> None:
        cursor = self.conn.execute(
            """UPDATE national_universe_pages
               SET status='FAILED', staged_at=?, error_message=?
               WHERE universe_id=? AND source_url=? AND status='PLANNED'""",
            (failed_at, error_message, universe_id, source_url),
        )
        if cursor.rowcount != 1:
            raise ValueError("planned national page not found")
        self.conn.commit()

    def finalize_national_universe_run(
        self,
        universe_id: int,
        *,
        completed_at: str,
    ) -> dict[str, object]:
        run = self.conn.execute(
            """SELECT universe_label, expected_total, status
               FROM national_universe_runs WHERE universe_id=?""",
            (universe_id,),
        ).fetchone()
        if run is None:
            raise KeyError(f"national universe not found: {universe_id}")
        if run["status"] != "RUNNING":
            raise ValueError("national universe run is not RUNNING")

        unresolved = int(
            self.conn.execute(
                """SELECT COUNT(*) FROM national_universe_pages
                   WHERE universe_id=? AND status='PLANNED'""",
                (universe_id,),
            ).fetchone()[0]
        )
        if unresolved:
            raise ValueError(f"national universe has {unresolved} unresolved page(s)")

        page_rows = self.conn.execute(
            """SELECT page, status, records_parsed, source_reported_total
               FROM national_universe_pages
               WHERE universe_id=? ORDER BY page""",
            (universe_id,),
        ).fetchall()
        member_rows = self.conn.execute(
            """SELECT dife_public_id
               FROM national_universe_page_members
               WHERE universe_id=? ORDER BY page, dife_public_id""",
            (universe_id,),
        ).fetchall()
        quality = assess_national_universe_quality(
            [
                NationalPageStatus(
                    page=int(row["page"]),
                    status=str(row["status"]),
                    records_parsed=row["records_parsed"],
                    source_reported_total=row["source_reported_total"],
                )
                for row in page_rows
            ],
            [int(row["dife_public_id"]) for row in member_rows],
            expected_total=(
                None if run["expected_total"] is None else int(run["expected_total"])
            ),
        )
        qc = asdict(quality)
        final_status = "COMPLETED" if quality.eligible_for_national_analysis else "FAILED"
        with self.conn:
            self.conn.execute(
                """UPDATE national_universe_runs
                   SET completed_at=?, status=?, pages_staged=?,
                       unique_public_ids=?, duplicate_public_ids=?,
                       eligible_for_national_analysis=?, qc_json=?
                   WHERE universe_id=?""",
                (
                    completed_at,
                    final_status,
                    quality.pages_staged,
                    quality.unique_public_ids,
                    quality.duplicate_public_ids,
                    int(quality.eligible_for_national_analysis),
                    json.dumps(qc, sort_keys=True),
                    universe_id,
                ),
            )
        return {
            "universe_id": universe_id,
            "universe_label": str(run["universe_label"]),
            "status": final_status,
            "quality": qc,
        }

    def national_universe_records(
        self,
        universe_label: str,
        *,
        require_eligible: bool = True,
    ) -> list[dict[str, object]]:
        run = self.conn.execute(
            """SELECT universe_id, eligible_for_national_analysis
               FROM national_universe_runs
               WHERE universe_label=?""",
            (universe_label,),
        ).fetchone()
        if run is None:
            raise KeyError(f"national universe not found: {universe_label}")
        if require_eligible and not bool(run["eligible_for_national_analysis"]):
            raise ValueError("national universe is not eligible for national analysis")

        rows = self.conn.execute(
            """SELECT
                   m.dife_public_id,
                   o.name,
                   o.sector AS sector_label,
                   o.district,
                   o.division,
                   o.status,
                   o.licence_class,
                   o.observed_at
               FROM national_universe_page_members m
               JOIN establishment_observations o
                 ON o.observation_id=m.observation_id
               WHERE m.universe_id=?
               ORDER BY m.dife_public_id""",
            (int(run["universe_id"]),),
        ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            source_sector = row["sector_label"]
            result.append({
                "dife_public_id": int(row["dife_public_id"]),
                "name": row["name"],
                "sector_label": source_sector,
                "sector_family": explicit_sector_family(source_sector) or "UNCLASSIFIED",
                "district": row["district"],
                "division": row["division"],
                "status": row["status"],
                "licence_class": row["licence_class"],
                "observed_at": row["observed_at"],
            })
        return result

    def national_universe_rollups(
        self,
        universe_label: str,
    ) -> dict[str, object]:
        records = self.national_universe_records(universe_label, require_eligible=True)
        return build_national_rollups(records, universe_label=universe_label)

    def national_cluster_context(
        self,
        universe_label: str,
        dife_public_id: int,
    ) -> dict[str, object]:
        records = self.national_universe_records(universe_label, require_eligible=True)
        target = next(
            (row for row in records if int(row["dife_public_id"]) == dife_public_id),
            None,
        )
        if target is None:
            raise KeyError(
                f"establishment {dife_public_id} is not a member of {universe_label}"
            )
        universe = [
            {
                "district": row["district"],
                "sector_family": row["sector_family"],
            }
            for row in records
        ]
        return cluster_context(
            universe,
            district=target["district"],
            sector_family=target["sector_family"],
            universe_label=universe_label,
            universe_kind=UniverseKind.NATIONAL_REGISTRY,
        )

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
