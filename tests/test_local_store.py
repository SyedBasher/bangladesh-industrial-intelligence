from pathlib import Path

import pytest

from bii.discovery import DiscoveryRequest
from bii.local_store import LocalValidationStore


def test_local_store_ingests_staged_html_without_network(tmp_path):
    html = Path("tests/fixtures/dife_list_metadata_minimal.html").read_text(encoding="utf-8")
    db_path = tmp_path / "private" / "validation.sqlite"

    with LocalValidationStore(db_path) as store:
        result = store.ingest_dife_list_html(
            html,
            source_url="https://example.invalid/dife?page=1",
            retrieved_at="2026-09-23T20:30:00+06:00",
        )
        assert result["records_parsed"] == 1
        assert result["source_total_records"] == 1200
        assert store.counts() == {
            "source_snapshots": 1,
            "establishments": 1,
            "establishment_observations": 1,
            "validation_sample": 0,
        }
        assert store.integrity_check() == "ok"


def test_identical_snapshot_does_not_duplicate_source_snapshot(tmp_path):
    html = Path("tests/fixtures/dife_list_metadata_minimal.html").read_text(encoding="utf-8")
    db_path = tmp_path / "validation.sqlite"

    with LocalValidationStore(db_path) as store:
        for minute in (30, 31):
            store.ingest_dife_list_html(
                html,
                source_url="https://example.invalid/dife?page=1",
                retrieved_at=f"2026-09-23T20:{minute}:00+06:00",
            )
        assert store.counts()["source_snapshots"] == 1
        assert store.counts()["establishment_observations"] == 1


def test_validation_sample_can_be_frozen_locally(tmp_path):
    html = Path("tests/fixtures/dife_list_metadata_minimal.html").read_text(encoding="utf-8")
    db_path = tmp_path / "validation.sqlite"

    with LocalValidationStore(db_path) as store:
        store.ingest_dife_list_html(
            html,
            source_url="https://example.invalid/dife?page=1",
            retrieved_at="2026-09-23T20:30:00+06:00",
        )
        n = store.freeze_validation_sample(
            "validation_demo",
            selected_at="2026-09-23T20:35:00+06:00",
            target_n=2000,
        )
        assert n == 1
        assert store.counts()["validation_sample"] == 1


def test_discovery_manifest_is_recorded_before_staging(tmp_path):
    db_path = tmp_path / "validation.sqlite"
    request = DiscoveryRequest(
        "RMG_TEXTILE",
        "1",
        "গার্মেন্টস/তৈরি পোশাক (নীট)",
        1,
        "https://example.invalid/dife?industry_id=1&page=1",
        "UNIVERSE_SEED",
    )

    with LocalValidationStore(db_path) as store:
        count = store.record_discovery_requests(
            "seed_2026_09_23",
            [request],
            planned_at="2026-09-23T21:00:00+06:00",
        )
        assert count == 1
        assert store.discovery_status_counts("seed_2026_09_23") == {"PLANNED": 1}

        html = Path("tests/fixtures/dife_list_metadata_minimal.html").read_text(encoding="utf-8")
        result = store.ingest_dife_list_html(
            html,
            source_url=request.source_url,
            retrieved_at="2026-09-23T21:01:00+06:00",
        )
        store.mark_discovery_request(
            "seed_2026_09_23",
            request.source_url,
            status="STAGED",
            snapshot_id=int(result["snapshot_id"]),
        )
        assert store.discovery_status_counts("seed_2026_09_23") == {"STAGED": 1}


def test_staged_discovery_requires_snapshot_id(tmp_path):
    db_path = tmp_path / "validation.sqlite"
    request = DiscoveryRequest(
        "RMG_TEXTILE", "1", "Knit", 1, "https://example.invalid/1", "UNIVERSE_SEED"
    )
    with LocalValidationStore(db_path) as store:
        store.record_discovery_requests(
            "plan",
            [request],
            planned_at="2026-09-23T21:00:00+06:00",
        )
        with pytest.raises(ValueError):
            store.mark_discovery_request("plan", request.source_url, status="STAGED")


def test_candidate_pool_health_uses_staged_observations(tmp_path):
    html = Path("tests/fixtures/dife_list_metadata_minimal.html").read_text(encoding="utf-8")
    db_path = tmp_path / "validation.sqlite"
    with LocalValidationStore(db_path) as store:
        store.ingest_dife_list_html(
            html,
            source_url="https://example.invalid/dife?page=1",
            retrieved_at="2026-09-23T20:30:00+06:00",
        )
        health = store.candidate_pool_health()
        assert health["unique_candidates"] == 1
        assert health["ready_for_2000_freeze"] is False
