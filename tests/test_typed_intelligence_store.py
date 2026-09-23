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


def _prepare(store: LocalValidationStore, source_name: str = "BGMEA") -> None:
    store.ingest_dife_list_html(
        _list_html(),
        source_url="https://example.invalid/dife",
        retrieved_at="2026-09-24T00:20:00+06:00",
    )
    store.freeze_validation_sample(
        "demo",
        selected_at="2026-09-24T00:21:00+06:00",
        sector_targets={"RMG_TEXTILE": 1},
        geography_targets={"CORE_DHAKA": 1},
    )
    store.plan_enrichment_targets(
        "demo",
        source_name,
        planned_at="2026-09-24T00:22:00+06:00",
    )


def _bgmea_html(district: str = "গাজীপুর", upazila: str = "টঙ্গী") -> str:
    return f"""
    <h2>Example Garments Ltd.</h2>
    <table>
      <tr><th>Factory Address</th><td>Tongi Industrial Area, Gazipur</td></tr>
      <tr><th>District</th><td>{district}</td></tr>
      <tr><th>Upazila</th><td>{upazila}</td></tr>
      <tr><th>Employees</th><td>1,250</td></tr>
      <tr><th>Machines</th><td>300</td></tr>
      <tr><th>Production Capacity</th><td>2.5 million pcs/year</td></tr>
      <tr><th>Principal Products</th><td>T-shirts; Polo shirts</td></tr>
      <tr><th>Export Markets</th><td>EU; USA</td></tr>
      <tr><th>Certifications</th><td>LEED; WRAP</td></tr>
      <tr><th>BGMEA Reg No</th><td>BG-123</td></tr>
      <tr><th>EPB Reg No</th><td>EPB-456</td></tr>
      <tr><th>Updated</th><td>2026-09-01</td></tr>
    </table>
    """


def test_ingest_creates_typed_observations_and_is_idempotent(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        first = store.ingest_external_record_html(
            "BGMEA",
            _bgmea_html(),
            source_url="https://www.bgmea.com.bd/member/7001",
            retrieved_at="2026-09-24T00:23:00+06:00",
        )
        second = store.ingest_external_record_html(
            "BGMEA",
            _bgmea_html(),
            source_url="https://www.bgmea.com.bd/member/7001",
            retrieved_at="2026-09-24T00:24:00+06:00",
        )
        assert first["external_version_id"] == second["external_version_id"]
        assert first["typed_observations"] == second["typed_observations"]
        assert first["typed_observations"] >= 10

        rows = store.conn.execute(
            """SELECT observation_type, scope, value_numeric, unit
               FROM external_typed_observations
               WHERE external_version_id=?""",
            (first["external_version_id"],),
        ).fetchall()
        employment = next(row for row in rows if row["observation_type"] == "EMPLOYMENT_COUNT")
        assert employment["scope"] == "SITE"
        assert employment["value_numeric"] == 1250
        capacity = next(row for row in rows if row["observation_type"] == "PRODUCTION_CAPACITY")
        assert capacity["value_numeric"] == 2_500_000
        assert capacity["unit"] == "pcs/year"


def test_site_link_exposes_site_and_organization_intelligence_with_scope(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        staged = store.ingest_external_record_html(
            "BGMEA",
            _bgmea_html(),
            source_url="https://www.bgmea.com.bd/member/7001",
            retrieved_at="2026-09-24T00:23:00+06:00",
        )
        link = store.review_external_link(
            "demo",
            101,
            int(staged["external_record_id"]),
            reviewed_at="2026-09-24T00:24:00+06:00",
        )
        assert link["site_level_match"] is True
        assert link["typed_observations_linked"] > 0

        profile = store.establishment_intelligence_profile("demo", 101)
        assert profile["name"] == "Example Garments Ltd."
        employment = profile["intelligence"]["EMPLOYMENT_COUNT"][0]
        assert employment["display_scope"] == "SITE"
        assert employment["site_attributable"] == 1
        assert employment["value_numeric"] == 1250

        markets = profile["intelligence"]["EXPORT_MARKET"]
        assert {item["value_text"] for item in markets} == {"EU", "USA"}
        assert all(item["display_scope"] == "ORGANIZATION" for item in markets)
        assert all(item["site_attributable"] == 0 for item in markets)


def test_organization_only_link_blocks_bgmea_site_attributes(tmp_path):
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store)
        staged = store.ingest_external_record_html(
            "BGMEA",
            _bgmea_html(district="ঢাকা", upazila="তেজগাঁও"),
            source_url="https://www.bgmea.com.bd/member/7001",
            retrieved_at="2026-09-24T00:23:00+06:00",
        )
        link = store.review_external_link(
            "demo",
            101,
            int(staged["external_record_id"]),
            reviewed_at="2026-09-24T00:24:00+06:00",
        )
        assert link["match_type"] == "ORGANIZATION_ONLY"
        assert link["site_level_match"] is False

        profile = store.establishment_intelligence_profile("demo", 101)
        intelligence = profile["intelligence"]
        assert "EMPLOYMENT_COUNT" not in intelligence
        assert "MACHINE_COUNT" not in intelligence
        assert "PRODUCTION_CAPACITY" not in intelligence
        assert "CERTIFICATION" not in intelligence
        assert "ASSOCIATION_MEMBERSHIP_RECORD" in intelligence
        assert "ASSOCIATION_REGISTRATION" in intelligence
        assert all(
            item["display_scope"] == "ORGANIZATION"
            for rows in intelligence.values()
            for item in rows
        )


def test_epb_hs_codes_remain_organization_evidence(tmp_path):
    epb_html = """
    <h2>Example Garments Ltd.</h2>
    <table>
      <tr><th>Factory Address</th><td>Tongi Industrial Area, Gazipur</td></tr>
      <tr><th>District</th><td>গাজীপুর</td></tr>
      <tr><th>Thana</th><td>টঙ্গী</td></tr>
      <tr><th>HS Code</th><td>6109, 6110; 6203</td></tr>
      <tr><th>Products</th><td>Knit shirts; Sweaters</td></tr>
      <tr><th>Export Markets</th><td>Germany; Canada</td></tr>
      <tr><th>EPB Registration No</th><td>EPB-777</td></tr>
      <tr><th>Exporter Category</th><td>Direct Exporter</td></tr>
    </table>
    """
    with LocalValidationStore(tmp_path / "validation.sqlite") as store:
        _prepare(store, "EPB")
        staged = store.ingest_external_record_html(
            "EPB",
            epb_html,
            source_url="https://edb.epb.gov.bd/exporter/3701/example-garments",
            retrieved_at="2026-09-24T00:23:00+06:00",
        )
        link = store.review_external_link(
            "demo",
            101,
            int(staged["external_record_id"]),
            reviewed_at="2026-09-24T00:24:00+06:00",
        )
        assert link["site_level_match"] is True

        profile = store.establishment_intelligence_profile("demo", 101)
        hs = profile["intelligence"]["HS_CODE"]
        assert {item["value_text"] for item in hs} == {"6109", "6110", "6203"}
        assert all(item["display_scope"] == "ORGANIZATION" for item in hs)
        assert all(item["site_attributable"] == 0 for item in hs)
