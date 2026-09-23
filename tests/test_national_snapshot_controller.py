from pathlib import Path

from bii.collector import CollectionError, FetchResult
from bii.hashutil import sha256_text
from bii.local_store import LocalValidationStore
from bii.national_snapshot_controller import run_national_snapshot_batch
from bii.policy import AccessDecision, SourceAccessPolicy


def _policy():
    return SourceAccessPolicy(
        source_name="DIFE/LIMA",
        decision=AccessDecision.REVIEWED_ALLOWED,
        reviewed_at="2026-09-24T02:00:00+06:00",
        review_note="Synthetic national snapshot test approval only.",
        allowed_hosts=("lima.dife.gov.bd",),
        allowed_path_prefixes=("/public-report/",),
        requests_per_minute=60,
        max_retries=1,
        timeout_seconds=10,
    )


def _page(total, rows):
    html_rows = "".join(
        f"""
        <tr>
          <td><a href="/public-report/establishment/{public_id}">{name}</a></td>
          <td>{sector}</td>
          <td>{location}</td><td>এ</td><td>নিবন্ধিত</td>
        </tr>
        """
        for public_id, name, sector, location in rows
    )
    return f"""
    <html><body>
      <div>প্রাপ্ত তথ্য : {total} টি</div>
      <div>দেখাচ্ছে : {len(rows)} টি</div>
      <table><tbody>{html_rows}</tbody></table>
    </body></html>
    """


PAGES = {
    1: _page(5, [
        (101, "A", "গার্মেন্টস/তৈরি পোশাক (নীট)", "টঙ্গী, গাজীপুর, ঢাকা"),
        (102, "B", "গার্মেন্টস/তৈরি পোশাক (নীট)", "গাজীপুর সদর, গাজীপুর, ঢাকা"),
    ]),
    2: _page(5, [
        (103, "C", "ফুড ইন্ডাষ্ট্রিজ", "তেজগাঁও, ঢাকা, ঢাকা"),
        (104, "D", "ফুটওয়্যার", "কালিয়াকৈর, গাজীপুর, ঢাকা"),
    ]),
    3: _page(5, [
        (105, "E", "ফুড ইন্ডাষ্ট্রিজ", "সাভার, ঢাকা, ঢাকা"),
    ]),
}


class FakeCollector:
    def __init__(self, pages=None, fail_pages=None):
        self.policy = _policy()
        self.pages = dict(PAGES if pages is None else pages)
        self.fail_pages = set(fail_pages or [])
        self.counter = 0
        self.calls = []

    def now_iso(self):
        self.counter += 1
        return f"2026-09-24T02:00:{self.counter:02d}+06:00"

    def fetch_text(self, url):
        page = int(url.split("page=")[-1])
        self.calls.append(page)
        if page in self.fail_pages:
            raise CollectionError(url, f"synthetic failure page {page}", retryable=True)
        text = self.pages[page]
        return FetchResult(
            url=url,
            http_status=200,
            text=text,
            retrieved_at=self.now_iso(),
            content_sha256=sha256_text(text),
            attempts=1,
        )


def _run(store, label="national_demo"):
    return store.create_national_universe_run(
        label,
        seed_url="https://lima.dife.gov.bd/public-report/establishment-list?page=1",
        started_at="2026-09-24T02:00:00+06:00",
        page_size=2,
    )


def test_bounded_batches_resume_without_refetching_staged_pages(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        universe_id = _run(store)
        first_collector = FakeCollector()
        first = run_national_snapshot_batch(
            store,
            first_collector,
            universe_id=universe_id,
            raw_root=tmp_path / "raw",
            max_pages=2,
        )
        assert first.staged == 2
        assert first.pages_remaining == 1
        assert first.universe_status == "RUNNING"
        assert first.stop_reason == "BATCH_LIMIT_REACHED"
        assert first_collector.calls == [1, 2]

        second_collector = FakeCollector()
        second = run_national_snapshot_batch(
            store,
            second_collector,
            universe_id=universe_id,
            raw_root=tmp_path / "raw",
            max_pages=2,
        )
        assert second_collector.calls == [3]
        assert second.finalized is True
        assert second.universe_status == "COMPLETED"
        assert second.eligible_for_national_analysis is True
        assert second.stop_reason == "NATIONAL_SNAPSHOT_COMPLETED"

        raw_files = list(Path(first.raw_directory).glob("page_*.html"))
        assert len(raw_files) == 3


def test_collection_failure_requires_explicit_requeue_then_resumes(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        universe_id = _run(store)
        failed = run_national_snapshot_batch(
            store,
            FakeCollector(fail_pages={2}),
            universe_id=universe_id,
            raw_root=tmp_path / "raw",
            max_pages=5,
        )
        assert failed.universe_status == "RUNNING"
        assert failed.failed_pages_remaining == 1
        assert failed.stop_reason == "COLLECTION_FAILURE_REQUIRES_REQUEUE"

        assert store.requeue_failed_national_pages(
            universe_id,
            requeued_at="2026-09-24T02:10:00+06:00",
            reason="Transient synthetic network failure cleared.",
            pages=[2],
        ) == 1

        resumed_collector = FakeCollector()
        resumed = run_national_snapshot_batch(
            store,
            resumed_collector,
            universe_id=universe_id,
            raw_root=tmp_path / "raw",
            max_pages=5,
        )
        assert resumed_collector.calls == [2, 3]
        assert resumed.universe_status == "COMPLETED"
        assert resumed.eligible_for_national_analysis is True

        attempts = store.conn.execute(
            """SELECT page, status FROM national_snapshot_page_attempts
               WHERE universe_id=? ORDER BY attempt_id""",
            (universe_id,),
        ).fetchall()
        page2 = [row["status"] for row in attempts if row["page"] == 2]
        assert page2 == ["COLLECTION_FAILED", "FETCHED_STAGED"]


def test_source_total_drift_aborts_and_restart_is_fresh(tmp_path):
    drift_pages = dict(PAGES)
    drift_pages[2] = _page(6, [
        (103, "C", "ফুড ইন্ডাষ্ট্রিজ", "তেজগাঁও, ঢাকা, ঢাকা"),
        (104, "D", "ফুটওয়্যার", "কালিয়াকৈর, গাজীপুর, ঢাকা"),
    ])
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        universe_id = _run(store, "drift_parent")
        result = run_national_snapshot_batch(
            store,
            FakeCollector(pages=drift_pages),
            universe_id=universe_id,
            raw_root=tmp_path / "raw",
            max_pages=5,
        )
        assert result.universe_status == "FAILED"
        assert result.stop_reason.startswith("INTEGRITY_ABORT")
        assert result.eligible_for_national_analysis is False

        page2_members = store.conn.execute(
            """SELECT COUNT(*) FROM national_universe_page_members
               WHERE universe_id=? AND page=2""",
            (universe_id,),
        ).fetchone()[0]
        assert page2_members == 0

        child = store.restart_national_universe_run(
            universe_id,
            new_universe_label="drift_restart",
            started_at="2026-09-24T02:20:00+06:00",
            reason="Registry total changed during parent run.",
        )
        child_progress = store.national_universe_progress(child)
        assert child_progress["status"] == "RUNNING"
        assert child_progress["page_status_counts"] == {"PLANNED": 1}
        assert child_progress["expected_total"] is None


def test_duplicate_id_against_earlier_page_aborts_before_membership(tmp_path):
    duplicate_pages = dict(PAGES)
    duplicate_pages[2] = _page(5, [
        (102, "B duplicate", "গার্মেন্টস/তৈরি পোশাক (নীট)", "গাজীপুর সদর, গাজীপুর, ঢাকা"),
        (104, "D", "ফুটওয়্যার", "কালিয়াকৈর, গাজীপুর, ঢাকা"),
    ])
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        universe_id = _run(store, "duplicate_parent")
        result = run_national_snapshot_batch(
            store,
            FakeCollector(pages=duplicate_pages),
            universe_id=universe_id,
            raw_root=tmp_path / "raw",
            max_pages=5,
        )
        assert result.universe_status == "FAILED"
        assert result.stop_reason.startswith("INTEGRITY_ABORT")
        assert store.conn.execute(
            """SELECT COUNT(*) FROM national_universe_page_members
               WHERE universe_id=? AND page=2""",
            (universe_id,),
        ).fetchone()[0] == 0


def test_wrong_page_cardinality_aborts_snapshot(tmp_path):
    bad_pages = dict(PAGES)
    bad_pages[2] = _page(5, [
        (103, "C", "ফুড ইন্ডাষ্ট্রিজ", "তেজগাঁও, ঢাকা, ঢাকা"),
    ])
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        universe_id = _run(store, "cardinality_parent")
        result = run_national_snapshot_batch(
            store,
            FakeCollector(pages=bad_pages),
            universe_id=universe_id,
            raw_root=tmp_path / "raw",
            max_pages=5,
        )
        assert result.universe_status == "FAILED"
        assert "INTEGRITY_ABORT" in result.stop_reason


def test_controller_rejects_non_dife_policy_before_collection(tmp_path):
    collector = FakeCollector()
    collector.policy = SourceAccessPolicy(
        source_name="BGMEA",
        decision=AccessDecision.REVIEWED_ALLOWED,
        reviewed_at="2026-09-24T02:00:00+06:00",
        review_note="Synthetic only.",
        allowed_hosts=("lima.dife.gov.bd",),
        allowed_path_prefixes=("/public-report/",),
    )
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        universe_id = _run(store)
        try:
            run_national_snapshot_batch(
                store,
                collector,
                universe_id=universe_id,
                raw_root=tmp_path / "raw",
            )
        except ValueError as exc:
            assert "DIFE/LIMA" in str(exc)
        else:
            raise AssertionError("expected controller to reject non-DIFE policy")
