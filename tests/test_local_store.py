from pathlib import Path

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
