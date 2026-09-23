from bii.local_store import LocalValidationStore


def _list_html() -> str:
    return """
    <html><body>
      <div>প্রাপ্ত তথ্য : ২ টি</div>
      <div>দেখাচ্ছে : ২ টি</div>
      <table><tbody>
        <tr>
          <td><a href="/public-report/establishment/101">Example Garments Ltd.</a></td>
          <td>গার্মেন্টস/তৈরি পোশাক (নীট)</td>
          <td>টঙ্গী, গাজীপুর, ঢাকা</td>
          <td>এ</td><td>নিবন্ধিত</td>
        </tr>
        <tr>
          <td><a href="/public-report/establishment/202">Example Foods Ltd.</a></td>
          <td>ফুড ইন্ডাষ্ট্রিজ</td>
          <td>গাজীপুর সদর, গাজীপুর, ঢাকা</td>
          <td>এ</td><td>নিবন্ধিত</td>
        </tr>
      </tbody></table>
    </body></html>
    """


def _prepare(store: LocalValidationStore) -> None:
    store.ingest_dife_list_html(
        _list_html(),
        source_url="https://example.invalid/dife/list",
        retrieved_at="2026-09-23T23:00:00+06:00",
    )
    store.freeze_validation_sample(
        "demo",
        selected_at="2026-09-23T23:01:00+06:00",
        sector_targets={"RMG_TEXTILE": 1, "FOOD_AGRO": 1},
        geography_targets={"CORE_DHAKA": 2},
    )


def test_source_target_planning_respects_sector_scope_without_negative_inference(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        counts = store.plan_enrichment_targets(
            "demo",
            "BGMEA",
            planned_at="2026-09-23T23:02:00+06:00",
        )
        assert counts == {"eligible": 1, "out_of_scope": 1}

        statuses = store.conn.execute(
            """SELECT dife_public_id, status
               FROM enrichment_targets
               WHERE validation_label='demo' AND source_name='BGMEA'
               ORDER BY dife_public_id"""
        ).fetchall()
        assert [(row["dife_public_id"], row["status"]) for row in statuses] == [
            (101, "PENDING"),
            (202, "OUT_OF_SCOPE"),
        ]


def test_bgmea_record_can_link_at_site_level_and_preserve_evidence(tmp_path):
    html = """
    <h2>Example Garments Ltd.</h2>
    <table>
      <tr><th>Factory Address</th><td>Tongi Industrial Area, Gazipur</td></tr>
      <tr><th>District</th><td>গাজীপুর</td></tr>
      <tr><th>Upazila</th><td>টঙ্গী</td></tr>
      <tr><th>BGMEA Reg No</th><td>BG-101</td></tr>
      <tr><th>Employees</th><td>750</td></tr>
    </table>
    """
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        store.plan_enrichment_targets(
            "demo", "BGMEA", planned_at="2026-09-23T23:02:00+06:00"
        )
        staged = store.ingest_external_record_html(
            "BGMEA",
            html,
            source_url="https://www.bgmea.com.bd/member/777",
            retrieved_at="2026-09-23T23:03:00+06:00",
        )
        link = store.review_external_link(
            "demo",
            101,
            int(staged["external_record_id"]),
            reviewed_at="2026-09-23T23:04:00+06:00",
        )
        assert link["match_type"] in {"EXACT_SITE", "PROBABLE_SITE"}
        assert link["site_level_match"] is True

        evidence = store.conn.execute(
            """SELECT evidence_type, result
               FROM match_evidence
               WHERE entity_link_id=?
               ORDER BY match_evidence_id""",
            (link["entity_link_id"],),
        ).fetchall()
        results = {row["evidence_type"]: row["result"] for row in evidence}
        assert results["NAME"] == "exact"
        assert results["DISTRICT"] == "match"

        coverage = store.enrichment_coverage("demo", "BGMEA")
        assert coverage.eligible == 1
        assert coverage.exact_site + coverage.probable_site == 1
        assert coverage.site_match_rate == 1.0


def test_bkmea_match_is_capped_at_organization_level(tmp_path):
    html = """
    <h2>Example Garments Ltd.</h2>
    <table>
      <tr><th>Membership No</th><td>BK-101</td></tr>
      <tr><th>District</th><td>গাজীপুর</td></tr>
      <tr><th>Upazila</th><td>টঙ্গী</td></tr>
      <tr><th>Factory Address</th><td>Tongi Industrial Area, Gazipur</td></tr>
    </table>
    """
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        store.plan_enrichment_targets(
            "demo", "BKMEA", planned_at="2026-09-23T23:02:00+06:00"
        )
        staged = store.ingest_external_record_html(
            "BKMEA",
            html,
            source_url="https://www.bkmea.com/member/example",
            retrieved_at="2026-09-23T23:03:00+06:00",
        )
        link = store.review_external_link(
            "demo",
            101,
            int(staged["external_record_id"]),
            reviewed_at="2026-09-23T23:04:00+06:00",
        )
        assert link["match_type"] == "ORGANIZATION_ONLY"
        assert link["site_level_match"] is False


def test_external_record_versions_are_content_addressed(tmp_path):
    html1 = """
    <h2>Example Garments Ltd.</h2>
    <table>
      <tr><th>Factory Address</th><td>Tongi, Gazipur</td></tr>
      <tr><th>District</th><td>গাজীপুর</td></tr>
      <tr><th>Employees</th><td>700</td></tr>
    </table>
    """
    html2 = html1.replace(">700<", ">750<")

    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        first = store.ingest_external_record_html(
            "BGMEA",
            html1,
            source_url="https://www.bgmea.com.bd/member/777",
            retrieved_at="2026-09-23T23:03:00+06:00",
        )
        again = store.ingest_external_record_html(
            "BGMEA",
            html1,
            source_url="https://www.bgmea.com.bd/member/777",
            retrieved_at="2026-09-23T23:04:00+06:00",
        )
        changed = store.ingest_external_record_html(
            "BGMEA",
            html2,
            source_url="https://www.bgmea.com.bd/member/777",
            retrieved_at="2026-09-23T23:05:00+06:00",
        )
        assert first["external_record_id"] == again["external_record_id"] == changed["external_record_id"]

        versions = store.conn.execute(
            """SELECT COUNT(*) FROM external_record_versions
               WHERE external_record_id=?""",
            (first["external_record_id"],),
        ).fetchone()[0]
        assert versions == 2


def test_coverage_does_not_turn_pending_targets_into_no_match(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        store.plan_enrichment_targets(
            "demo", "EPB", planned_at="2026-09-23T23:02:00+06:00"
        )
        coverage = store.enrichment_coverage("demo", "EPB")
        assert coverage.eligible == 2
        assert coverage.no_match == 0
        assert coverage.any_positive_link_rate == 0.0


def test_enrichment_report_is_append_only(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        store.plan_enrichment_targets(
            "demo", "EPB", planned_at="2026-09-23T23:02:00+06:00"
        )
        first_id, first = store.generate_enrichment_report(
            "demo", "EPB", generated_at="2026-09-23T23:03:00+06:00"
        )
        second_id, second = store.generate_enrichment_report(
            "demo", "EPB", generated_at="2026-09-23T23:04:00+06:00"
        )
        assert second_id > first_id
        assert first == second
