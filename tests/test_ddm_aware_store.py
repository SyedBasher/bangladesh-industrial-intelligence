import csv
import json
from pathlib import Path

from bii.admin_geography import (
    ddm_aware_default_aliases,
    load_normalized_bbs_geocode_csv,
)
from bii.ddm_aware import DDM_AWARE_RISK_URL
from bii.local_store import LocalValidationStore
from bii.offline_national_ingest import ingest_normalized_bulk_csv


ROOT = Path(__file__).parent
GEO = ROOT / "fixtures" / "bbs_geocode_minimal.csv"
DDM = ROOT / "fixtures" / "ddm_aware_risk_minimal.html"


def _write_bulk(path):
    columns = [
        "dife_public_id","name","sector","location","upazila",
        "district","division","licence_class","status",
    ]
    rows = [
        {
            "dife_public_id": 101,
            "name": "Bangla Geography Factory",
            "sector": "গার্মেন্টস/তৈরি পোশাক (নীট)",
            "location": "টঙ্গী, গাজীপুর, ঢাকা",
            "upazila": "টঙ্গী",
            "district": "গাজীপুর",
            "division": "ঢাকা",
            "licence_class": "এ",
            "status": "নিবন্ধিত",
        },
        {
            "dife_public_id": 102,
            "name": "Dhaka Factory",
            "sector": "ফুড ইন্ডাষ্ট্রিজ",
            "location": "তেজগাঁও, ঢাকা, ঢাকা",
            "upazila": "তেজগাঁও",
            "district": "ঢাকা",
            "division": "ঢাকা",
            "licence_class": "এ",
            "status": "নিবন্ধিত",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _prepare(store, tmp_path):
    bulk = tmp_path / "bulk.csv"
    _write_bulk(bulk)
    ingest_normalized_bulk_csv(
        store,
        bulk,
        universe_label="ddm_geo_demo",
        source_url="https://example.invalid/dife-bulk.csv",
        retrieved_at="2026-09-24T07:00:00+06:00",
        declared_total=2,
        transform_note="Synthetic national fixture with Bangla admin names.",
    )

    units = load_normalized_bbs_geocode_csv(
        GEO,
        source_vintage="synthetic-test",
    )
    aliases = ddm_aware_default_aliases(units)
    result = store.ingest_admin_geography(units, aliases)
    assert result["units"] >= 5
    assert result["aliases"] >= 1


def test_store_ingests_staged_ddm_and_links_to_bangla_dife_geography(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        _prepare(store, tmp_path)
        imported = store.ingest_ddm_aware_risk_html(
            DDM.read_text(encoding="utf-8"),
            source_vintage="2026-09-24",
            observed_at="2026-09-24T07:05:00+06:00",
            imported_at="2026-09-24T07:06:00+06:00",
            source_reference=DDM_AWARE_RISK_URL,
        )
        assert imported["source_records"] == 3
        assert imported["mapped_districts"] == 2
        assert imported["observations_generated"] == 10
        assert imported["observations_staged"] == 10
        assert imported["unresolved"] == [
            {
                "district": "Not A District",
                "division": "Dhaka",
                "status": "NO_MATCH",
            }
        ]

        links = store.national_exposure_links(
            "ddm_geo_demo",
            generated_at="2026-09-24T07:10:00+06:00",
        )
        gazipur = [
            row for row in links
            if row["establishment_ref"] == "DIFE:101"
        ]
        assert len(gazipur) == 5
        assert {row["domain"] for row in gazipur} == {"DISASTER_RISK"}
        assert {row["canonical_geo_ref"] for row in gazipur} == {
            "BBS:DIST:30:33"
        }
        assert {row["attribution"] for row in gazipur} == {
            "DISTRICT_CONTEXT"
        }

        dhaka = [
            row for row in links
            if row["establishment_ref"] == "DIFE:102"
        ]
        assert dhaka == []

        serialized = json.dumps(links, ensure_ascii=False)
        assert DDM_AWARE_RISK_URL not in serialized
        assert "source_reference" not in serialized
        assert "exposure_observation_id" not in serialized


def test_ddm_district_profile_remains_context_not_site_claim(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        _prepare(store, tmp_path)
        store.ingest_ddm_aware_risk_html(
            DDM.read_text(encoding="utf-8"),
            source_vintage="2026-09-24",
            observed_at="2026-09-24T07:05:00+06:00",
            imported_at="2026-09-24T07:06:00+06:00",
            source_reference=DDM_AWARE_RISK_URL,
        )
        profile = store.national_establishment_exposure_profile(
            "ddm_geo_demo",
            "DIFE:101",
            generated_at="2026-09-24T07:10:00+06:00",
        )
        assert profile["coverage"]["has_site_specific_evidence"] is False
        assert profile["coverage"]["has_area_context_evidence"] is True
        assert {
            row["metric_code"] for row in profile["exposures"]
        } == {
            "DDM_HAZARD_EXPOSURE",
            "DDM_VULNERABILITY",
            "DDM_LACK_COPING_CAPACITY",
            "DDM_RISK_CATEGORY",
            "DDM_CLIMATE_ZONE",
        }
        assert all(
            row["direction"] == "CONTEXT_ONLY"
            for row in profile["exposures"]
        )
