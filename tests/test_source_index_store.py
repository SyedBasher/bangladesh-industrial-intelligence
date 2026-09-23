import json

import pytest

from bii.local_store import LocalValidationStore


def _dife_list_html() -> str:
    return """
    <html><body>
      <div>প্রাপ্ত তথ্য : ২ টি</div>
      <div>দেখাচ্ছে : ২ টি</div>
      <table><tbody>
        <tr>
          <td><a href="/public-report/establishment/101">Example Garments Ltd.</a></td>
          <td>গার্মেন্টস/তৈরি পোশাক (নীট)</td>
          <td>টঙ্গী, গাজীপুর, ঢাকা</td><td>এ</td><td>নিবন্ধিত</td>
        </tr>
        <tr>
          <td><a href="/public-report/establishment/102">Example Garments Unit 2</a></td>
          <td>গার্মেন্টস/তৈরি পোশাক (নীট)</td>
          <td>টঙ্গী, গাজীপুর, ঢাকা</td><td>এ</td><td>নিবন্ধিত</td>
        </tr>
      </tbody></table>
    </body></html>
    """


def _prepare_validation(store: LocalValidationStore) -> None:
    store.ingest_dife_list_html(
        _dife_list_html(),
        source_url="https://example.invalid/dife",
        retrieved_at="2026-09-23T23:40:00+06:00",
    )
    store.freeze_validation_sample(
        "demo",
        selected_at="2026-09-23T23:41:00+06:00",
        sector_targets={"RMG_TEXTILE": 2},
        geography_targets={"CORE_DHAKA": 2},
    )
    store.plan_enrichment_targets(
        "demo",
        "BGMEA",
        planned_at="2026-09-23T23:42:00+06:00",
    )


def _bgmea_page(page: int) -> str:
    if page == 1:
        rows = """
        <tr><td>Example Garments Ltd.</td><td>7001</td>
            <td><a href="/member/5001">Details</a></td></tr>
        <tr><td>Unrelated Apparel Ltd.</td><td>7002</td>
            <td><a href="/member/5002">Details</a></td></tr>
        """
    else:
        rows = """
        <tr><td>Another Company Ltd.</td><td>7003</td>
            <td><a href="/member/5003">Details</a></td></tr>
        <tr><td>Example Garments Ltd. Unit 2</td><td>7004</td>
            <td><a href="/member/5004">Details</a></td></tr>
        """
    return f"""
    <html><body>
      <div>Total 4 Member(s) Found</div>
      <table>{rows}</table>
      <a href="/page/member-list?page=1">1</a>
      <a href="/page/member-list?page=2">2</a>
    </body></html>
    """


def test_bgmea_index_run_seed_expand_finalize_and_plan_details(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare_validation(store)
        run_id = store.create_external_index_run(
            "BGMEA",
            seed_url="https://bgmea.com.bd/page/member-list?page=1",
            started_at="2026-09-23T23:43:00+06:00",
        )
        assert len(store.external_index_requests(run_id)) == 1

        store.ingest_external_index_page(
            run_id,
            _bgmea_page(1),
            source_url="https://bgmea.com.bd/page/member-list?page=1",
            retrieved_at="2026-09-23T23:44:00+06:00",
        )
        pages = store.expand_external_index_run(
            run_id,
            planned_at="2026-09-23T23:45:00+06:00",
        )
        assert pages == 2

        pending = store.external_index_requests(run_id)
        assert len(pending) == 1
        assert pending[0]["page"] == 2

        store.ingest_external_index_page(
            run_id,
            _bgmea_page(2),
            source_url="https://bgmea.com.bd/page/member-list?page=2",
            retrieved_at="2026-09-23T23:46:00+06:00",
        )
        finalized = store.finalize_external_index_run(
            run_id,
            completed_at="2026-09-23T23:47:00+06:00",
        )
        assert finalized["status"] == "COMPLETED"
        assert finalized["quality"]["records"] == 4
        assert finalized["quality"]["duplicate_keys"] == 0

        plan = store.plan_external_detail_requests_from_index(
            "demo",
            "BGMEA",
            run_id,
            planned_at="2026-09-23T23:48:00+06:00",
        )
        assert plan["eligible_targets"] == 2
        assert plan["index_records"] == 4
        assert plan["unique_detail_requests"] >= 1
        assert plan["unique_detail_requests"] <= plan["target_candidate_links"]

        requests = store.external_detail_requests("BGMEA")
        assert len(requests) == plan["unique_detail_requests"]


def test_same_bgmea_member_is_fetched_once_for_multiple_dife_targets(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare_validation(store)
        run_id = store.create_external_index_run(
            "BGMEA",
            seed_url="https://bgmea.com.bd/page/member-list?page=1",
            started_at="2026-09-23T23:43:00+06:00",
        )
        one_record = """
        <html><body>
          <div>Total 1 Member(s) Found</div>
          <table>
            <tr><td>Example Garments Ltd.</td><td>7001</td>
                <td><a href="/member/5001">Details</a></td></tr>
          </table>
        </body></html>
        """
        store.ingest_external_index_page(
            run_id,
            one_record,
            source_url="https://bgmea.com.bd/page/member-list?page=1",
            retrieved_at="2026-09-23T23:44:00+06:00",
        )
        finalized = store.finalize_external_index_run(
            run_id,
            completed_at="2026-09-23T23:45:00+06:00",
        )
        assert finalized["status"] == "COMPLETED"

        plan = store.plan_external_detail_requests_from_index(
            "demo",
            "BGMEA",
            run_id,
            planned_at="2026-09-23T23:46:00+06:00",
        )
        assert plan["unique_detail_requests"] == 1
        assert plan["target_candidate_links"] >= 1

        request_id = store.external_detail_requests("BGMEA")[0]["request_id"]
        target_count = store.conn.execute(
            """SELECT COUNT(*) FROM external_detail_request_targets
               WHERE request_id=?""",
            (request_id,),
        ).fetchone()[0]
        assert target_count == plan["target_candidate_links"]


def test_index_run_refuses_finalize_with_unresolved_pages(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        run_id = store.create_external_index_run(
            "BGMEA",
            seed_url="https://bgmea.com.bd/page/member-list?page=1",
            started_at="2026-09-23T23:43:00+06:00",
        )
        with pytest.raises(ValueError):
            store.finalize_external_index_run(
                run_id,
                completed_at="2026-09-23T23:44:00+06:00",
            )


def test_duplicate_member_across_pages_fails_index_qc(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        run_id = store.create_external_index_run(
            "BGMEA",
            seed_url="https://bgmea.com.bd/page/member-list?page=1",
            started_at="2026-09-23T23:43:00+06:00",
        )
        seed = """
        <div>Total 2 Member(s) Found</div>
        <table><tr><td>Example Ltd.</td><td>1</td>
        <td><a href="/member/5001">Details</a></td></tr></table>
        <a href="?page=2">2</a>
        """
        store.ingest_external_index_page(
            run_id,
            seed,
            source_url="https://bgmea.com.bd/page/member-list?page=1",
            retrieved_at="2026-09-23T23:44:00+06:00",
        )
        store.expand_external_index_run(
            run_id,
            planned_at="2026-09-23T23:45:00+06:00",
        )
        duplicate = """
        <div>Total 2 Member(s) Found</div>
        <table><tr><td>Example Ltd.</td><td>1</td>
        <td><a href="/member/5001">Details</a></td></tr></table>
        """
        store.ingest_external_index_page(
            run_id,
            duplicate,
            source_url="https://bgmea.com.bd/page/member-list?page=2",
            retrieved_at="2026-09-23T23:46:00+06:00",
        )
        result = store.finalize_external_index_run(
            run_id,
            completed_at="2026-09-23T23:47:00+06:00",
        )
        assert result["status"] == "FAILED"
        assert result["quality"]["duplicate_keys"] == 1


def test_epb_json_seed_can_expand_when_pagination_metadata_is_available(tmp_path):
    payload = {
        "data": {
            "data": [
                {
                    "id": 3701,
                    "name": "Apex Footwear Ltd.",
                    "slug": "apex-footwear-ltd",
                    "factory_address": "Shafipur, Kaliakoir",
                    "factory_thana": {"name": "Kaliakoir"},
                    "factory_district": {"name": "Gazipur"},
                }
            ],
            "current_page": 1,
            "last_page": 3,
            "total": 3,
        }
    }
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        run_id = store.create_external_index_run(
            "EPB",
            seed_url="https://edb.epb.gov.bd/exporters?page=1",
            started_at="2026-09-23T23:43:00+06:00",
        )
        store.ingest_external_index_page(
            run_id,
            json.dumps(payload),
            source_url="https://edb.epb.gov.bd/exporters?page=1",
            retrieved_at="2026-09-23T23:44:00+06:00",
            content_format="json",
        )
        assert store.expand_external_index_run(
            run_id,
            planned_at="2026-09-23T23:45:00+06:00",
        ) == 3
        assert [row["page"] for row in store.external_index_requests(run_id)] == [2, 3]
