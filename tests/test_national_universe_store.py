import pytest

from bii.local_store import LocalValidationStore


def _page(total: int, rows: list[tuple[int, str, str, str, str]]) -> str:
    body = []
    for public_id, name, sector, location, status in rows:
        body.append(
            f"""
            <tr>
              <td><a href="/public-report/establishment/{public_id}">{name}</a></td>
              <td>{sector}</td>
              <td>{location}</td>
              <td>এ</td>
              <td>{status}</td>
            </tr>
            """
        )
    return f"""
    <html><body>
      <div>প্রাপ্ত তথ্য : {total} টি</div>
      <div>দেখাচ্ছে : {len(rows)} টি</div>
      <table><tbody>{''.join(body)}</tbody></table>
    </body></html>
    """


def _stage_complete_demo(store: LocalValidationStore) -> int:
    run_id = store.create_national_universe_run(
        "dife_demo_complete",
        seed_url="https://lima.dife.gov.bd/public-report/establishment-list?page=1",
        started_at="2026-09-24T01:00:00+06:00",
        page_size=2,
    )
    store.ingest_national_universe_page(
        run_id,
        _page(
            5,
            [
                (101, "Garments A", "গার্মেন্টস/তৈরি পোশাক (নীট)", "টঙ্গী, গাজীপুর, ঢাকা", "নিবন্ধিত"),
                (102, "Garments B", "গার্মেন্টস/তৈরি পোশাক (নীট)", "গাজীপুর সদর, গাজীপুর, ঢাকা", "নিবন্ধিত"),
            ],
        ),
        source_url="https://lima.dife.gov.bd/public-report/establishment-list?page=1",
        retrieved_at="2026-09-24T01:01:00+06:00",
    )
    assert store.expand_national_universe_run(
        run_id,
        planned_at="2026-09-24T01:02:00+06:00",
    ) == 3

    store.ingest_national_universe_page(
        run_id,
        _page(
            5,
            [
                (103, "Food A", "ফুড ইন্ডাষ্ট্রিজ", "তেজগাঁও, ঢাকা, ঢাকা", "নিবন্ধিত"),
                (104, "Unknown A", "একটি নতুন অজানা খাত", "তেজগাঁও, ঢাকা, ঢাকা", "বাতিল"),
            ],
        ),
        source_url="https://lima.dife.gov.bd/public-report/establishment-list?page=2",
        retrieved_at="2026-09-24T01:03:00+06:00",
    )
    store.ingest_national_universe_page(
        run_id,
        _page(
            5,
            [
                (105, "Footwear A", "ফুটওয়্যার", "কালিয়াকৈর, গাজীপুর, ঢাকা", "নিবন্ধিত"),
            ],
        ),
        source_url="https://lima.dife.gov.bd/public-report/establishment-list?page=3",
        retrieved_at="2026-09-24T01:04:00+06:00",
    )
    return run_id


def test_complete_national_snapshot_becomes_eligible(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        run_id = _stage_complete_demo(store)
        result = store.finalize_national_universe_run(
            run_id,
            completed_at="2026-09-24T01:05:00+06:00",
        )
        assert result["status"] == "COMPLETED"
        assert result["quality"]["eligible_for_national_analysis"] is True
        assert result["quality"]["unique_public_ids"] == 5

        records = store.national_universe_records("dife_demo_complete")
        assert len(records) == 5
        unknown = next(row for row in records if row["dife_public_id"] == 104)
        assert unknown["sector_family"] == "UNCLASSIFIED"

        rollups = store.national_universe_rollups("dife_demo_complete")
        assert rollups["summary"]["establishments"] == 5
        assert rollups["summary"]["unclassified_sector_records"] == 1
        gazipur = next(row for row in rollups["districts"] if row["district"] == "গাজীপুর")
        assert gazipur["establishments"] == 3


def test_national_cluster_context_uses_eligible_national_universe(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        run_id = _stage_complete_demo(store)
        store.finalize_national_universe_run(
            run_id,
            completed_at="2026-09-24T01:05:00+06:00",
        )
        context = store.national_cluster_context("dife_demo_complete", 101)
        assert context["universe_kind"] == "NATIONAL_REGISTRY"
        assert context["suitable_for_national_cluster_claim"] is True
        assert context["district_sector_establishments"] == 2


def test_total_drift_blocks_national_analysis(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        run_id = store.create_national_universe_run(
            "drift_demo",
            seed_url="https://lima.dife.gov.bd/public-report/establishment-list?page=1",
            started_at="2026-09-24T01:00:00+06:00",
            page_size=2,
        )
        store.ingest_national_universe_page(
            run_id,
            _page(3, [(1, "A", "ফুড ইন্ডাষ্ট্রিজ", "ঢাকা, ঢাকা, ঢাকা", "নিবন্ধিত"),
                      (2, "B", "ফুড ইন্ডাষ্ট্রিজ", "ঢাকা, ঢাকা, ঢাকা", "নিবন্ধিত")]),
            source_url="https://lima.dife.gov.bd/public-report/establishment-list?page=1",
            retrieved_at="2026-09-24T01:01:00+06:00",
        )
        store.expand_national_universe_run(
            run_id,
            planned_at="2026-09-24T01:02:00+06:00",
        )
        store.ingest_national_universe_page(
            run_id,
            _page(4, [(3, "C", "ফুড ইন্ডাষ্ট্রিজ", "ঢাকা, ঢাকা, ঢাকা", "নিবন্ধিত")]),
            source_url="https://lima.dife.gov.bd/public-report/establishment-list?page=2",
            retrieved_at="2026-09-24T01:03:00+06:00",
        )
        result = store.finalize_national_universe_run(
            run_id,
            completed_at="2026-09-24T01:04:00+06:00",
        )
        assert result["status"] == "FAILED"
        assert result["quality"]["source_total_stable"] is False
        with pytest.raises(ValueError):
            store.national_universe_records("drift_demo")


def test_duplicate_across_pages_blocks_national_analysis(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        run_id = store.create_national_universe_run(
            "duplicate_demo",
            seed_url="https://lima.dife.gov.bd/public-report/establishment-list?page=1",
            started_at="2026-09-24T01:00:00+06:00",
            page_size=2,
        )
        store.ingest_national_universe_page(
            run_id,
            _page(3, [(1, "A", "ফুড ইন্ডাষ্ট্রিজ", "ঢাকা, ঢাকা, ঢাকা", "নিবন্ধিত"),
                      (2, "B", "ফুড ইন্ডাষ্ট্রিজ", "ঢাকা, ঢাকা, ঢাকা", "নিবন্ধিত")]),
            source_url="https://lima.dife.gov.bd/public-report/establishment-list?page=1",
            retrieved_at="2026-09-24T01:01:00+06:00",
        )
        store.expand_national_universe_run(
            run_id,
            planned_at="2026-09-24T01:02:00+06:00",
        )
        store.ingest_national_universe_page(
            run_id,
            _page(3, [(2, "B", "ফুড ইন্ডাষ্ট্রিজ", "ঢাকা, ঢাকা, ঢাকা", "নিবন্ধিত")]),
            source_url="https://lima.dife.gov.bd/public-report/establishment-list?page=2",
            retrieved_at="2026-09-24T01:03:00+06:00",
        )
        result = store.finalize_national_universe_run(
            run_id,
            completed_at="2026-09-24T01:04:00+06:00",
        )
        assert result["status"] == "FAILED"
        assert result["quality"]["duplicate_public_ids"] == 1


def test_unresolved_page_prevents_finalize(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        run_id = store.create_national_universe_run(
            "unresolved_demo",
            seed_url="https://lima.dife.gov.bd/public-report/establishment-list?page=1",
            started_at="2026-09-24T01:00:00+06:00",
            page_size=2,
        )
        with pytest.raises(ValueError):
            store.finalize_national_universe_run(
                run_id,
                completed_at="2026-09-24T01:01:00+06:00",
            )


def test_product_profile_can_use_eligible_national_cluster_context(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        run_id = _stage_complete_demo(store)
        store.finalize_national_universe_run(
            run_id,
            completed_at="2026-09-24T01:05:00+06:00",
        )
        store.freeze_validation_sample(
            "one_record_validation",
            selected_at="2026-09-24T01:06:00+06:00",
            sector_targets={"RMG_TEXTILE": 1},
            geography_targets={"CORE_DHAKA": 1},
        )
        selected_id = int(store.conn.execute(
            """SELECT dife_public_id FROM validation_sample
               WHERE validation_label='one_record_validation'"""
        ).fetchone()[0])

        payload = store.product_establishment_payload(
            "one_record_validation",
            selected_id,
            generated_at="2026-09-24T01:07:00+06:00",
            national_universe_label="dife_demo_complete",
        )
        cluster = payload["calculated"]["cluster_context"]
        assert cluster["universe_kind"] == "NATIONAL_REGISTRY"
        assert cluster["suitable_for_national_cluster_claim"] is True
