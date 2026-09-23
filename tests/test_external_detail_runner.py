from pathlib import Path

from bii.collector import CollectionError, FetchResult
from bii.external_detail_runner import run_external_detail_requests
from bii.hashutil import sha256_text
from bii.local_store import LocalValidationStore
from bii.policy import AccessDecision, SourceAccessPolicy


def _policy(source_name: str):
    host = "www.bgmea.com.bd" if source_name == "BGMEA" else "edb.epb.gov.bd"
    return SourceAccessPolicy(
        source_name=source_name,
        decision=AccessDecision.REVIEWED_ALLOWED,
        reviewed_at="2026-09-23T23:55:00+06:00",
        review_note="Synthetic test approval only.",
        allowed_hosts=(host,),
        allowed_path_prefixes=("/",),
        requests_per_minute=60,
        max_retries=1,
        timeout_seconds=10,
    )


class FakeCollector:
    def __init__(self, source_name: str, *, fail: bool = False):
        self.policy = _policy(source_name)
        self.fail = fail
        self.counter = 0

    def now_iso(self):
        self.counter += 1
        return f"2026-09-23T23:55:{self.counter:02d}+06:00"

    def fetch_text(self, url: str):
        if self.fail:
            raise CollectionError(url, "synthetic failure", retryable=True)
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


def _prepare_request(store: LocalValidationStore) -> int:
    store.register_external_source_profile("BGMEA")
    with store.conn:
        store.conn.execute(
            """INSERT INTO external_detail_requests(
                   source_name, source_key, detail_url, status, planned_at
               ) VALUES(?,?,?,?,?)""",
            (
                "BGMEA",
                "7001",
                "https://www.bgmea.com.bd/member/7001",
                "PLANNED",
                "2026-09-23T23:54:00+06:00",
            ),
        )
    return int(store.conn.execute(
        "SELECT request_id FROM external_detail_requests"
    ).fetchone()[0])


def test_external_detail_runner_fetches_once_and_versions_profile(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        request_id = _prepare_request(store)
        summary = run_external_detail_requests(
            store,
            FakeCollector("BGMEA"),
            source_name="BGMEA",
            raw_root=tmp_path / "raw",
        )
        assert summary.attempted == 1
        assert summary.fetched == 1
        assert summary.failed == 0
        assert list(Path(summary.raw_directory).glob("7001_*.html"))

        row = store.conn.execute(
            """SELECT status, external_record_id
               FROM external_detail_requests WHERE request_id=?""",
            (request_id,),
        ).fetchone()
        assert row["status"] == "FETCHED"
        assert row["external_record_id"] is not None

        assert store.conn.execute(
            "SELECT COUNT(*) FROM external_record_versions"
        ).fetchone()[0] == 1


def test_external_detail_runner_records_failure(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        request_id = _prepare_request(store)
        summary = run_external_detail_requests(
            store,
            FakeCollector("BGMEA", fail=True),
            source_name="BGMEA",
            raw_root=tmp_path / "raw",
        )
        assert summary.failed == 1
        row = store.conn.execute(
            """SELECT status, error_message
               FROM external_detail_requests WHERE request_id=?""",
            (request_id,),
        ).fetchone()
        assert row["status"] == "FAILED"
        assert "synthetic failure" in row["error_message"]
