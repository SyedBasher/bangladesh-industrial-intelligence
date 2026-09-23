from bii.local_store import LocalValidationStore


def _prepare(store: LocalValidationStore) -> None:
    list_html = """
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
    store.ingest_dife_list_html(
        list_html,
        source_url="https://example.invalid/dife",
        retrieved_at="2026-09-24T00:45:00+06:00",
    )
    store.freeze_validation_sample(
        "demo",
        selected_at="2026-09-24T00:46:00+06:00",
        sector_targets={"RMG_TEXTILE": 1},
        geography_targets={"CORE_DHAKA": 1},
    )
    store.plan_enrichment_targets(
        "demo",
        "BGMEA",
        planned_at="2026-09-24T00:47:00+06:00",
    )

    bgmea_html = """
    <h2>Example Garments Ltd.</h2>
    <table>
      <tr><th>Factory Address</th><td>Tongi Industrial Area, Gazipur</td></tr>
      <tr><th>District</th><td>গাজীপুর</td></tr>
      <tr><th>Upazila</th><td>টঙ্গী</td></tr>
      <tr><th>Employees</th><td>1,250</td></tr>
      <tr><th>Machines</th><td>300</td></tr>
      <tr><th>Production Capacity</th><td>2.5 million pcs/year</td></tr>
      <tr><th>Principal Products</th><td>T-shirts; Polo shirts</td></tr>
      <tr><th>Export Markets</th><td>EU; USA</td></tr>
    </table>
    """
    staged = store.ingest_external_record_html(
        "BGMEA",
        bgmea_html,
        source_url="https://www.bgmea.com.bd/member/7001",
        retrieved_at="2026-09-24T00:48:00+06:00",
    )
    store.review_external_link(
        "demo",
        101,
        int(staged["external_record_id"]),
        reviewed_at="2026-09-24T00:49:00+06:00",
    )


def test_private_store_generates_safe_product_payload(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        payload = store.product_establishment_payload(
            "demo",
            101,
            generated_at="2026-09-24T00:50:00+06:00",
        )

        assert payload["establishment"]["establishment_ref"] == "DIFE:101"
        assert payload["facts"]["machines"][0]["numeric_value"] == 300
        assert payload["facts"]["production_capacity"][0]["numeric_value"] == 2_500_000
        assert payload["calculated"]["employment_scale_band"]["value"] == "1000_PLUS"
        assert payload["calculated"]["evidence_freshness"]["origin"] == "CALCULATED"
        assert payload["calculated"]["cluster_context"]["universe_kind"] == "VALIDATION_SAMPLE"
        assert payload["calculated"]["cluster_context"]["suitable_for_national_cluster_claim"] is False

        serialized = str(payload)
        for forbidden in (
            "snapshot_id",
            "external_record_id",
            "external_version_id",
            "entity_link_id",
            "raw_payload_path",
            "source_url",
            "raw_label",
            "raw_value",
        ):
            assert forbidden not in serialized


def test_validation_feed_contains_only_product_contracts(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        feed = store.product_validation_feed(
            "demo",
            generated_at="2026-09-24T00:50:00+06:00",
        )
        assert len(feed) == 1
        assert feed[0]["schema_version"] == "1.1"
        assert set(feed[0]) == {
            "schema_version",
            "generated_at",
            "establishment",
            "facts",
            "calculated",
            "evidence",
        }


def test_refreshed_external_version_creates_change_signal_only_after_relink(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)

        changed_html = """
        <h2>Example Garments Ltd.</h2>
        <table>
          <tr><th>Factory Address</th><td>Tongi Industrial Area, Gazipur</td></tr>
          <tr><th>District</th><td>গাজীপুর</td></tr>
          <tr><th>Upazila</th><td>টঙ্গী</td></tr>
          <tr><th>Employees</th><td>1,500</td></tr>
          <tr><th>Machines</th><td>320</td></tr>
          <tr><th>Production Capacity</th><td>2.8 million pcs/year</td></tr>
        </table>
        """
        staged = store.ingest_external_record_html(
            "BGMEA",
            changed_html,
            source_url="https://www.bgmea.com.bd/member/7001",
            retrieved_at="2027-09-24T00:48:00+06:00",
        )

        before_relink = store.product_establishment_payload(
            "demo",
            101,
            generated_at="2027-09-24T00:49:00+06:00",
        )
        employment_before = [
            item for item in before_relink["calculated"]["change_signals"]
            if item["observation_type"] == "EMPLOYMENT_COUNT"
        ]
        assert employment_before == []

        store.review_external_link(
            "demo",
            101,
            int(staged["external_record_id"]),
            reviewed_at="2027-09-24T00:50:00+06:00",
        )
        after_relink = store.product_establishment_payload(
            "demo",
            101,
            generated_at="2027-09-24T00:51:00+06:00",
        )
        employment_after = [
            item for item in after_relink["calculated"]["change_signals"]
            if item["observation_type"] == "EMPLOYMENT_COUNT"
        ]
        assert len(employment_after) == 1
        assert employment_after[0]["first_value"] == 1250
        assert employment_after[0]["latest_value"] == 1500
        assert employment_after[0]["percent_change"] == 20.0
