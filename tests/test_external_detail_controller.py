from pathlib import Path

from bii.collector import FetchResult
from bii.external_detail_controller import run_external_enrichment_cycle
from bii.hashutil import sha256_text
from bii.local_store import LocalValidationStore
from bii.policy import AccessDecision, SourceAccessPolicy


class FakeCollector:
    def __init__(self):
        self.policy = SourceAccessPolicy(
            source_name="BGMEA",
            decision=AccessDecision.REVIEWED_ALLOWED,
            reviewed_at="2026-09-24T00:10:00+06:00",
            review_note="Synthetic test approval only.",
            allowed_hosts=("www.bgmea.com.bd",),
            allowed_path_prefixes=("/",),
            requests_per_minute=60,
            max_retries=1,
            timeout_seconds=10,
        )
        self.counter = 0

    def now_iso(self):
        self.counter += 1
        return f"2026-09-24T00:10:{self.counter:02d}+06:00"

    def fetch_text(self, url: str):
        text = """
        <h2>Example Garments Ltd.</h2>
        <table>
          <tr><th>Factory Address</th><td>Tongi Industrial Area, Gazipur</td></tr>
          <tr><th>District</th><td>গাজীপুর</td></tr>
          <tr><th>Upazila</th><td>টঙ্গী</td></tr>
          <tr><th>Employees</th><td>750</td></tr>
        </table>
        """
        return FetchResult(
            url=url,
            http_status=200,
            text=text,
            retrieved_at=self.now_iso(),
            content_sha256=sha256_text(text),
            attempts=1,
        )


def _prepare(store: LocalValidationStore) -> None:
    html = """
    <html><body>
      <div>প্রাপ্ত তথ্য : ১ টি</div>
      <div>দেখাচ্ছে : ১ টি</div>
      <table><tbody>
        <tr>
          <td><a href="/public-report/establishment/101">Example Garments Ltd.</a></td>
          <td>গার্মেন্টস/তৈরি পোশাক (নীট)</td>
          <td>টঙ্গী, গাজীপুর, ঢাকা</td><td>এ</td><td>নিবন্ধিত</td>
        </tr>
      </tbody></table>
    </body></html>
    """
    store.ingest_dife_list_html(
        html,
        source_url="https://example.invalid/dife",
        retrieved_at="2026-09-24T00:00:00+06:00",
    )
    store.freeze_validation_sample(
        "demo",
        selected_at="2026-09-24T00:01:00+06:00",
        sector_targets={"RMG_TEXTILE": 1},
        geography_targets={"CORE_DHAKA": 1},
    )
    store.plan_enrichment_targets(
        "demo",
        "BGMEA",
        planned_at="2026-09-24T00:02:00+06:00",
    )

    # The source-index layer has already shortlisted this member for the DIFE site.
    store.register_external_source_profile("BGMEA")
    with store.conn:
        store.conn.execute(
            """INSERT INTO external_index_records(
                   source_name, source_key, entity_name, detail_url,
                   first_seen_at
               ) VALUES(?,?,?,?,?)""",
            (
                "BGMEA",
                "7001",
                "Example Garments Ltd.",
                "https://www.bgmea.com.bd/member/7001",
                "2026-09-24T00:03:00+06:00",
            ),
        )
        index_record_id = int(store.conn.execute(
            "SELECT index_record_id FROM external_index_records"
        ).fetchone()[0])
        store.conn.execute(
            """INSERT INTO external_detail_requests(
                   source_name, source_key, detail_url, status, planned_at
               ) VALUES(?,?,?,?,?)""",
            (
                "BGMEA",
                "7001",
                "https://www.bgmea.com.bd/member/7001",
                "PLANNED",
                "2026-09-24T00:04:00+06:00",
            ),
        )
        request_id = int(store.conn.execute(
            "SELECT request_id FROM external_detail_requests"
        ).fetchone()[0])
        store.conn.execute(
            """INSERT INTO external_detail_request_targets(
                   request_id, validation_label, dife_public_id, index_record_id,
                   shortlist_position, priority_class
               ) VALUES(?,?,?,?,?,?)""",
            (
                request_id,
                "demo",
                101,
                index_record_id,
                1,
                "P1_EXACT_NAME_SITE",
            ),
        )


def test_cycle_fetches_resolves_and_applies_unique_match(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        result = run_external_enrichment_cycle(
            store,
            FakeCollector(),
            validation_label="demo",
            source_name="BGMEA",
            raw_root=tmp_path / "raw",
        )
        assert result.collection.fetched == 1
        assert result.status_counts == {"FETCHED": 1}
        assert result.candidate_run_id is not None
        assert result.auto_selected == 1
        assert result.auto_links_applied == 1

        link = store.conn.execute(
            """SELECT match_type, site_level_match
               FROM entity_links
               WHERE validation_label='demo' AND dife_public_id=101
               ORDER BY entity_link_id DESC LIMIT 1"""
        ).fetchone()
        assert link["match_type"] in {"EXACT_SITE", "PROBABLE_SITE"}
        assert link["site_level_match"] == 1
