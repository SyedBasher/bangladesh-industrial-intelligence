from pathlib import Path

from bii.collector import CollectionError, FetchResult
from bii.detail_runner import run_ready_detail_checkpoint
from bii.hashutil import sha256_text
from bii.local_store import LocalValidationStore
from bii.policy import AccessDecision, SourceAccessPolicy


def _list_html() -> str:
    return """
    <html><body>
    <div>প্রাপ্ত তথ্য : ১ টি</div>
    <div>দেখাচ্ছে : ১ টি</div>
    <table><tbody>
      <tr>
        <td><a href="/public-report/establishment/12345">Example Factory Ltd.</a></td>
        <td>গার্মেন্টস/তৈরি পোশাক (নীট)</td>
        <td>গাজীপুর সদর, গাজীপুর, ঢাকা</td>
        <td>এ</td><td>নিবন্ধিত</td>
      </tr>
    </tbody></table>
    </body></html>
    """


def _detail_html() -> str:
    return Path("tests/fixtures/dife_detail_minimal.html").read_text(encoding="utf-8")


def _policy() -> SourceAccessPolicy:
    return SourceAccessPolicy(
        source_name="DIFE/LIMA",
        decision=AccessDecision.REVIEWED_ALLOWED,
        reviewed_at="2026-09-23T22:15:00+06:00",
        review_note="Synthetic test approval only.",
        allowed_hosts=("lima.dife.gov.bd",),
        allowed_path_prefixes=("/public-report/",),
        requests_per_minute=20.0,
        max_retries=2,
        timeout_seconds=20.0,
    )


class FakeCollector:
    def __init__(self, *, fail: bool = False):
        self.policy = _policy()
        self.fail = fail
        self.counter = 0

    def now_iso(self) -> str:
        self.counter += 1
        return f"2026-09-23T22:15:{self.counter:02d}+06:00"

    def fetch_text(self, url: str) -> FetchResult:
        if self.fail:
            raise CollectionError(url, "synthetic failure", retryable=True)
        text = _detail_html()
        return FetchResult(
            url=url,
            http_status=200,
            text=text,
            retrieved_at=self.now_iso(),
            content_sha256=sha256_text(text),
            attempts=1,
        )


def _prepare(store: LocalValidationStore) -> None:
    store.ingest_dife_list_html(
        _list_html(),
        source_url="https://example.invalid/list",
        retrieved_at="2026-09-23T22:00:00+06:00",
    )
    store.freeze_validation_sample(
        "validation_demo",
        selected_at="2026-09-23T22:01:00+06:00",
        sector_targets={"RMG_TEXTILE": 1},
        geography_targets={"CORE_DHAKA": 1},
    )
    store.plan_detail_validation(
        "validation_demo",
        planned_at="2026-09-23T22:02:00+06:00",
        checkpoints=(1,),
    )


def test_private_runner_records_policy_run_and_raw_snapshot(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        summary = run_ready_detail_checkpoint(
            store,
            FakeCollector(),
            validation_label="validation_demo",
            checkpoint_n=1,
            raw_root=tmp_path / "raw",
        )
        assert summary.attempted == 1
        assert summary.parsed == 1
        assert summary.failed == 0
        assert list(Path(summary.raw_directory).glob("12345_*.html"))

        run = store.detail_collection_run(summary.run_id)
        assert run["status"] == "COMPLETED"
        assert run["decision"] == "REVIEWED_ALLOWED"
        assert run["source_name"] == "DIFE/LIMA"
        assert run["requests_per_minute"] == 20.0
        assert run["attempted"] == 1
        assert run["parsed"] == 1


def test_private_runner_records_collection_failure_without_unlocking_gate(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        summary = run_ready_detail_checkpoint(
            store,
            FakeCollector(fail=True),
            validation_label="validation_demo",
            checkpoint_n=1,
            raw_root=tmp_path / "raw",
        )
        assert summary.attempted == 1
        assert summary.parsed == 0
        assert summary.failed == 1

        run = store.detail_collection_run(summary.run_id)
        assert run["status"] == "COMPLETED"
        assert run["failed"] == 1

        metrics, decision = store.evaluate_detail_checkpoint(
            "validation_demo",
            1,
            evaluated_at="2026-09-23T22:20:00+06:00",
        )
        assert metrics.retrieval_success_rate == 0.0
        assert decision.passed is False
