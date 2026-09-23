from pathlib import Path

from bii.collector import CollectionError, FetchResult
from bii.hashutil import sha256_text
from bii.local_store import LocalValidationStore
from bii.policy import AccessDecision, SourceAccessPolicy
from bii.validation_controller import run_progressive_detail_validation


def _list_html(n: int) -> str:
    rows = []
    for i in range(1, n + 1):
        public_id = 12000 + i
        rows.append(
            f"""
            <tr>
              <td><a href="/public-report/establishment/{public_id}">Example Factory {i} Ltd.</a></td>
              <td>গার্মেন্টস/তৈরি পোশাক (নীট)</td>
              <td>গাজীপুর সদর, গাজীপুর, ঢাকা</td>
              <td>এ</td><td>নিবন্ধিত</td>
            </tr>
            """
        )
    return f"""
    <html><body>
      <div>প্রাপ্ত তথ্য : {n} টি</div>
      <div>দেখাচ্ছে : {n} টি</div>
      <table><tbody>{''.join(rows)}</tbody></table>
    </body></html>
    """


def _detail_html(name: str) -> str:
    return f"""
    <html><body>
      <h2>{name}</h2>
      <div>পূর্ণ ঠিকানা</div><div>শিল্প এলাকা, গাজীপুর</div>
      <div>উপজেলা : গাজীপুর সদর, জেলা : গাজীপুর, বিভাগ : ঢাকা</div>
      <div>বর্তমান অবস্থা</div><div>নিবন্ধিত</div>
      <div>মেয়াদ</div><div>৩১-১২-২০২৭</div>
      <div>ইন্ডাস্ট্রিয়াল সেক্টর:</div><div>গার্মেন্টস/তৈরি পোশাক (নীট)</div>
      <div>লাইসেন্স নম্বর:</div><div>লাই-১২৩</div>
      <div>রেজিস্ট্রেশন নম্বর:</div><div>রেজি-৪৫৬</div>
      <div>শ্রেণী:</div><div>এ (কারখানা)</div>
      <div>মোট শ্রমিকের সংখ্যা:</div><div>১২ + ৮ = ২০</div>
    </body></html>
    """


def _policy():
    return SourceAccessPolicy(
        source_name="DIFE/LIMA",
        decision=AccessDecision.REVIEWED_ALLOWED,
        reviewed_at="2026-09-23T22:30:00+06:00",
        review_note="Synthetic test approval only.",
        allowed_hosts=("lima.dife.gov.bd",),
        allowed_path_prefixes=("/public-report/",),
        requests_per_minute=20,
        max_retries=1,
        timeout_seconds=20,
    )


class FakeCollector:
    def __init__(self, fail_public_id: int | None = None):
        self.policy = _policy()
        self.fail_public_id = fail_public_id
        self.counter = 0

    def now_iso(self):
        self.counter += 1
        return f"2026-09-23T22:30:{self.counter:02d}+06:00"

    def fetch_text(self, url: str):
        public_id = int(url.rstrip("/").split("/")[-1])
        if self.fail_public_id == public_id:
            raise CollectionError(url, "synthetic failure", retryable=True)
        text = _detail_html(f"Example Factory {public_id - 12000} Ltd.")
        return FetchResult(
            url=url,
            http_status=200,
            text=text,
            retrieved_at=self.now_iso(),
            content_sha256=sha256_text(text),
            attempts=1,
        )


def _prepare(store: LocalValidationStore, n: int = 3):
    store.ingest_dife_list_html(
        _list_html(n),
        source_url="https://example.invalid/list",
        retrieved_at="2026-09-23T22:00:00+06:00",
    )
    store.freeze_validation_sample(
        "demo",
        selected_at="2026-09-23T22:01:00+06:00",
        sector_targets={"RMG_TEXTILE": n},
        geography_targets={"CORE_DHAKA": n},
    )
    store.plan_detail_validation(
        "demo",
        planned_at="2026-09-23T22:02:00+06:00",
        checkpoints=(1, 2, 3),
    )


def test_controller_runs_all_checkpoints_without_manual_pause(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store, 3)
        result = run_progressive_detail_validation(
            store,
            FakeCollector(),
            validation_label="demo",
            raw_root=tmp_path / "raw",
        )
        assert result.all_passed is True
        assert result.completed_checkpoints == (1, 2, 3)
        assert result.stopped_at is None
        assert [stage.collection.attempted for stage in result.stages] == [1, 1, 1]
        assert store.detail_checkpoint_states("demo") == {
            1: "PASSED",
            2: "PASSED",
            3: "PASSED",
        }


def test_controller_stops_at_first_failed_gate(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store, 3)
        first = store.detail_requests_for_checkpoint("demo", 1)[0]
        fail_id = int(first["dife_public_id"])
        result = run_progressive_detail_validation(
            store,
            FakeCollector(fail_public_id=fail_id),
            validation_label="demo",
            raw_root=tmp_path / "raw",
        )
        assert result.all_passed is False
        assert result.completed_checkpoints == ()
        assert result.stopped_at == 1
        assert len(result.stages) == 1
        assert store.detail_checkpoint_states("demo") == {
            1: "FAILED",
            2: "LOCKED",
            3: "LOCKED",
        }
