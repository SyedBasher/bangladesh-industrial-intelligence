from pathlib import Path

import pytest

from bii.detail_validation import CheckpointPolicy
from bii.local_store import LocalValidationStore


def _two_row_list_html() -> str:
    return """
    <html><body>
    <div>প্রাপ্ত তথ্য : ২ টি</div>
    <div>দেখাচ্ছে : ২ টি</div>
    <div>প্রতিবেদন তৈরির তারিখ এবং সময় : ২৩-০৯-২০২৬ ২২:০০</div>
    <table><tbody>
      <tr>
        <td><a href="/public-report/establishment/12345">Example Factory One Ltd.</a></td>
        <td>গার্মেন্টস/তৈরি পোশাক (নীট)</td>
        <td>গাজীপুর সদর, গাজীপুর, ঢাকা</td>
        <td>এ</td><td>নিবন্ধিত</td>
      </tr>
      <tr>
        <td><a href="/public-report/establishment/12346">Example Factory Two Ltd.</a></td>
        <td>গার্মেন্টস/তৈরি পোশাক (নীট)</td>
        <td>গাজীপুর সদর, গাজীপুর, ঢাকা</td>
        <td>এ</td><td>নিবন্ধিত</td>
      </tr>
    </tbody></table>
    </body></html>
    """


def _detail_html(name: str) -> str:
    template = Path("tests/fixtures/dife_detail_minimal.html").read_text(encoding="utf-8")
    return template.replace("Example Factory Ltd.", name)


def _prepare_two_record_frozen_sample(store: LocalValidationStore) -> None:
    store.ingest_dife_list_html(
        _two_row_list_html(),
        source_url="https://example.invalid/dife?industry_id=1&page=1",
        retrieved_at="2026-09-23T22:00:00+06:00",
    )
    n = store.freeze_validation_sample(
        "validation_demo",
        selected_at="2026-09-23T22:01:00+06:00",
        sector_targets={"RMG_TEXTILE": 2},
        geography_targets={"CORE_DHAKA": 2},
    )
    assert n == 2


def test_detail_checkpoints_unlock_only_after_prior_gate_passes(tmp_path):
    db_path = tmp_path / "validation.sqlite"
    with LocalValidationStore(db_path) as store:
        _prepare_two_record_frozen_sample(store)
        planned = store.plan_detail_validation(
            "validation_demo",
            planned_at="2026-09-23T22:02:00+06:00",
            checkpoints=(1, 2),
        )
        assert planned == 2
        assert store.detail_checkpoint_states("validation_demo") == {
            1: "READY",
            2: "LOCKED",
        }

        first = store.detail_requests_for_checkpoint("validation_demo", 1)
        assert len(first) == 1
        first_id = int(first[0]["dife_public_id"])
        store.ingest_dife_detail_html(
            "validation_demo",
            first_id,
            _detail_html("Example Factory One Ltd."),
            source_url=str(first[0]["source_url"]),
            retrieved_at="2026-09-23T22:03:00+06:00",
        )

        metrics, decision = store.evaluate_detail_checkpoint(
            "validation_demo",
            1,
            evaluated_at="2026-09-23T22:04:00+06:00",
        )
        assert decision.passed is True
        assert metrics.retrieval_success_rate == 1.0
        assert metrics.parser_valid_rate == 1.0
        assert metrics.provenance_complete_rate == 1.0
        assert store.detail_checkpoint_states("validation_demo") == {
            1: "PASSED",
            2: "READY",
        }

        second = store.detail_requests_for_checkpoint("validation_demo", 2)
        assert len(second) == 1
        assert int(second[0]["dife_public_id"]) != first_id


def test_failed_checkpoint_does_not_unlock_next_stage_and_can_be_retried(tmp_path):
    db_path = tmp_path / "validation.sqlite"
    with LocalValidationStore(db_path) as store:
        _prepare_two_record_frozen_sample(store)
        store.plan_detail_validation(
            "validation_demo",
            planned_at="2026-09-23T22:02:00+06:00",
            checkpoints=(1, 2),
        )
        first = store.detail_requests_for_checkpoint("validation_demo", 1)[0]
        public_id = int(first["dife_public_id"])

        store.mark_detail_request_failed(
            "validation_demo",
            public_id,
            resolved_at="2026-09-23T22:03:00+06:00",
            error_message="synthetic retrieval failure",
        )
        _, decision = store.evaluate_detail_checkpoint(
            "validation_demo",
            1,
            evaluated_at="2026-09-23T22:04:00+06:00",
        )
        assert decision.passed is False
        assert store.detail_checkpoint_states("validation_demo") == {
            1: "FAILED",
            2: "LOCKED",
        }

        store.reset_failed_detail_request("validation_demo", public_id)
        store.ingest_dife_detail_html(
            "validation_demo",
            public_id,
            _detail_html("Example Factory One Ltd."),
            source_url=str(first["source_url"]),
            retrieved_at="2026-09-23T22:05:00+06:00",
        )
        _, retry_decision = store.evaluate_detail_checkpoint(
            "validation_demo",
            1,
            evaluated_at="2026-09-23T22:06:00+06:00",
        )
        assert retry_decision.passed is True
        assert store.detail_checkpoint_states("validation_demo")[2] == "READY"


def test_detail_source_url_is_bound_to_frozen_manifest(tmp_path):
    db_path = tmp_path / "validation.sqlite"
    with LocalValidationStore(db_path) as store:
        _prepare_two_record_frozen_sample(store)
        store.plan_detail_validation(
            "validation_demo",
            planned_at="2026-09-23T22:02:00+06:00",
            checkpoints=(1, 2),
        )
        first = store.detail_requests_for_checkpoint("validation_demo", 1)[0]
        with pytest.raises(ValueError):
            store.ingest_dife_detail_html(
                "validation_demo",
                int(first["dife_public_id"]),
                _detail_html("Example Factory One Ltd."),
                source_url="https://lima.dife.gov.bd/public-report/establishment/99999",
                retrieved_at="2026-09-23T22:03:00+06:00",
            )


def test_core_threshold_can_block_valid_parser_pages(tmp_path):
    db_path = tmp_path / "validation.sqlite"
    with LocalValidationStore(db_path) as store:
        _prepare_two_record_frozen_sample(store)
        store.plan_detail_validation(
            "validation_demo",
            planned_at="2026-09-23T22:02:00+06:00",
            checkpoints=(1, 2),
        )
        first = store.detail_requests_for_checkpoint("validation_demo", 1)[0]
        public_id = int(first["dife_public_id"])

        html = """
        <html><body>
          <h2>Example Factory One Ltd.</h2>
          <div>বর্তমান অবস্থা</div><div>নিবন্ধিত</div>
        </body></html>
        """
        result = store.ingest_dife_detail_html(
            "validation_demo",
            public_id,
            html,
            source_url=str(first["source_url"]),
            retrieved_at="2026-09-23T22:03:00+06:00",
        )
        assert result["parser_valid"] is True
        assert result["core_complete"] is False

        strict = CheckpointPolicy(min_core_complete_rate=1.0)
        _, decision = store.evaluate_detail_checkpoint(
            "validation_demo",
            1,
            evaluated_at="2026-09-23T22:04:00+06:00",
            policy=strict,
        )
        assert decision.passed is False
        assert any("core completeness" in reason for reason in decision.reasons)
