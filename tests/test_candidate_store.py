from bii.local_store import LocalValidationStore


def _list_html() -> str:
    return """
    <html><body>
      <div>প্রাপ্ত তথ্য : ১ টি</div>
      <div>দেখাচ্ছে : ১ টি</div>
      <table><tbody>
        <tr>
          <td><a href="/public-report/establishment/101">Example Garments Ltd.</a></td>
          <td>গার্মেন্টস/তৈরি পোশাক (নীট)</td>
          <td>টঙ্গী, গাজীপুর, ঢাকা</td>
          <td>এ</td><td>নিবন্ধিত</td>
        </tr>
      </tbody></table>
    </body></html>
    """


def _prepare(store: LocalValidationStore) -> None:
    store.ingest_dife_list_html(
        _list_html(),
        source_url="https://example.invalid/dife/list",
        retrieved_at="2026-09-23T23:20:00+06:00",
    )
    store.freeze_validation_sample(
        "demo",
        selected_at="2026-09-23T23:21:00+06:00",
        sector_targets={"RMG_TEXTILE": 1},
        geography_targets={"CORE_DHAKA": 1},
    )
    store.plan_enrichment_targets(
        "demo",
        "BGMEA",
        planned_at="2026-09-23T23:22:00+06:00",
    )


def _bgmea_html(name: str, district: str, upazila: str, address: str) -> str:
    return f"""
    <h2>{name}</h2>
    <table>
      <tr><th>Factory Address</th><td>{address}</td></tr>
      <tr><th>District</th><td>{district}</td></tr>
      <tr><th>Upazila</th><td>{upazila}</td></tr>
      <tr><th>BGMEA Reg No</th><td>BG-101</td></tr>
    </table>
    """


def test_unique_site_candidate_is_auto_selected_and_can_be_applied(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)

        exact = store.ingest_external_record_html(
            "BGMEA",
            _bgmea_html(
                "Example Garments Ltd.",
                "গাজীপুর",
                "টঙ্গী",
                "Tongi Industrial Area, Gazipur",
            ),
            source_url="https://www.bgmea.com.bd/member/7001",
            retrieved_at="2026-09-23T23:23:00+06:00",
        )
        store.ingest_external_record_html(
            "BGMEA",
            _bgmea_html(
                "Example Garments Unit 2",
                "ঢাকা",
                "তেজগাঁও",
                "Tejgaon, Dhaka",
            ),
            source_url="https://www.bgmea.com.bd/member/7002",
            retrieved_at="2026-09-23T23:24:00+06:00",
        )

        run = store.generate_external_candidates(
            "demo",
            "BGMEA",
            generated_at="2026-09-23T23:25:00+06:00",
            max_candidates=5,
        )
        assert run["targets_considered"] == 1
        assert run["auto_selected"] == 1
        assert run["ambiguous"] == 0

        outcomes = store.candidate_run_outcomes(int(run["run_id"]))
        assert outcomes[0]["outcome"] == "AUTO_SELECTED"
        assert outcomes[0]["selected_external_record_id"] == exact["external_record_id"]

        candidates = store.candidates_for_target(int(run["run_id"]), 101)
        assert candidates[0]["external_record_id"] == exact["external_record_id"]
        assert candidates[0]["priority_class"] == "P1_EXACT_NAME_SITE"

        applied = store.apply_auto_resolutions(
            int(run["run_id"]),
            applied_at="2026-09-23T23:26:00+06:00",
        )
        assert applied == 1
        assert store.apply_auto_resolutions(
            int(run["run_id"]),
            applied_at="2026-09-23T23:27:00+06:00",
        ) == 0

        link = store.conn.execute(
            """SELECT match_type, site_level_match
               FROM entity_links
               WHERE validation_label='demo' AND dife_public_id=101
               ORDER BY entity_link_id DESC LIMIT 1"""
        ).fetchone()
        assert link["match_type"] in {"EXACT_SITE", "PROBABLE_SITE"}
        assert link["site_level_match"] == 1

        target = store.conn.execute(
            """SELECT status FROM enrichment_targets
               WHERE validation_label='demo'
                 AND source_name='BGMEA'
                 AND dife_public_id=101"""
        ).fetchone()
        assert target["status"] == "REVIEWED"


def test_two_site_candidates_remain_ambiguous_and_are_not_auto_applied(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        for member_id in (7101, 7102):
            store.ingest_external_record_html(
                "BGMEA",
                _bgmea_html(
                    "Example Garments Ltd.",
                    "গাজীপুর",
                    "টঙ্গী",
                    "Tongi Industrial Area, Gazipur",
                ),
                source_url=f"https://www.bgmea.com.bd/member/{member_id}",
                retrieved_at=f"2026-09-23T23:{member_id % 60:02d}:00+06:00",
            )

        run = store.generate_external_candidates(
            "demo",
            "BGMEA",
            generated_at="2026-09-23T23:30:00+06:00",
        )
        assert run["ambiguous"] == 1
        assert run["auto_selected"] == 0

        outcome = store.candidate_run_outcomes(int(run["run_id"]))[0]
        assert outcome["outcome"] == "AMBIGUOUS"
        assert outcome["selected_external_record_id"] is None
        assert store.apply_auto_resolutions(
            int(run["run_id"]),
            applied_at="2026-09-23T23:31:00+06:00",
        ) == 0

        assert store.conn.execute("SELECT COUNT(*) FROM entity_links").fetchone()[0] == 0


def test_empty_staged_index_is_not_no_match(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        run = store.generate_external_candidates(
            "demo",
            "BGMEA",
            generated_at="2026-09-23T23:30:00+06:00",
        )
        assert run["no_staged_candidate"] == 1
        assert run["candidates_generated"] == 0

        outcome = store.candidate_run_outcomes(int(run["run_id"]))[0]
        assert outcome["outcome"] == "NO_STAGED_CANDIDATE"
        assert outcome["selected_match_type"] is None

        target = store.conn.execute(
            """SELECT status FROM enrichment_targets
               WHERE validation_label='demo'
                 AND source_name='BGMEA'
                 AND dife_public_id=101"""
        ).fetchone()
        assert target["status"] == "PENDING"


def test_candidate_run_is_append_only_and_reproducible(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        store.ingest_external_record_html(
            "BGMEA",
            _bgmea_html(
                "Example Garments Ltd.",
                "গাজীপুর",
                "টঙ্গী",
                "Tongi Industrial Area, Gazipur",
            ),
            source_url="https://www.bgmea.com.bd/member/7201",
            retrieved_at="2026-09-23T23:23:00+06:00",
        )
        first = store.generate_external_candidates(
            "demo", "BGMEA", generated_at="2026-09-23T23:24:00+06:00"
        )
        second = store.generate_external_candidates(
            "demo", "BGMEA", generated_at="2026-09-23T23:25:00+06:00"
        )
        assert second["run_id"] > first["run_id"]
        assert first["candidates_generated"] == second["candidates_generated"]
        first_candidates = store.candidates_for_target(int(first["run_id"]), 101)
        second_candidates = store.candidates_for_target(int(second["run_id"]), 101)
        assert first_candidates[0]["external_record_id"] == second_candidates[0]["external_record_id"]
