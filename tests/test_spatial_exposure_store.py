import csv
import json

from bii.local_store import LocalValidationStore
from bii.offline_national_ingest import ingest_normalized_bulk_csv


def _write_bulk(path):
    columns = [
        "dife_public_id","name","sector","location","upazila",
        "district","division","licence_class","status",
    ]
    rows = [
        {
            "dife_public_id": 101,
            "name": "Factory A",
            "sector": "গার্মেন্টস/তৈরি পোশাক (নীট)",
            "location": "টঙ্গী, গাজীপুর, ঢাকা",
            "upazila": "Tongi",
            "district": "Gazipur",
            "division": "Dhaka",
            "licence_class": "A",
            "status": "Registered",
        },
        {
            "dife_public_id": 102,
            "name": "Factory B",
            "sector": "গার্মেন্টস/তৈরি পোশাক (নীট)",
            "location": "কালিয়াকৈর, গাজীপুর, ঢাকা",
            "upazila": "Kaliakair",
            "district": "Gazipur",
            "division": "Dhaka",
            "licence_class": "A",
            "status": "Registered",
        },
        {
            "dife_public_id": 103,
            "name": "Factory C",
            "sector": "ফুড ইন্ডাষ্ট্রিজ",
            "location": "তেজগাঁও, ঢাকা, ঢাকা",
            "upazila": "Tejgaon",
            "district": "Dhaka",
            "division": "Dhaka",
            "licence_class": "A",
            "status": "Registered",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _prepare(store, tmp_path):
    csv_path = tmp_path / "bulk.csv"
    _write_bulk(csv_path)
    ingest_normalized_bulk_csv(
        store,
        csv_path,
        universe_label="exposure_demo",
        source_url="https://example.invalid/dife-bulk.csv",
        retrieved_at="2026-09-24T06:10:00+06:00",
        declared_total=3,
        transform_note="Synthetic canonical bulk fixture.",
    )
    store.record_spatial_exposure_source(
        "Synthetic Exposure Source",
        authority="Synthetic authority for tests",
        methodology_note="Synthetic test observations only.",
        source_reference="private://exposure/source/file",
        imported_at="2026-09-24T06:20:00+06:00",
    )
    inserted = store.ingest_spatial_exposure_observations(
        "Synthetic Exposure Source",
        [
            {
                "domain": "CLIMATE_HAZARD",
                "metric_code": "FLOOD_CONTEXT",
                "metric_label": "Flood-context class",
                "spatial_scope": "DISTRICT",
                "district": "Gazipur",
                "value_text": "Elevated",
                "direction": "CONTEXT_ONLY",
                "source_vintage": "2026",
                "observed_at": "2026-09-24",
            },
            {
                "domain": "POWER_SYSTEM",
                "metric_code": "OUTAGE_HOURS",
                "metric_label": "Reported outage hours",
                "spatial_scope": "UPAZILA",
                "district": "Gazipur",
                "upazila": "Tongi",
                "value_numeric": 4.5,
                "unit": "hours/month",
                "direction": "HIGHER_MEANS_MORE_EXPOSURE",
                "source_vintage": "2026-08",
                "observed_at": "2026-09-24",
            },
            {
                "domain": "TRANSPORT_ACCESS",
                "metric_code": "PORT_TRAVEL_TIME",
                "metric_label": "Travel time to port",
                "spatial_scope": "SITE",
                "establishment_ref": "DIFE:102",
                "value_numeric": 90,
                "unit": "minutes",
                "direction": "HIGHER_MEANS_MORE_EXPOSURE",
                "source_vintage": "2026-09",
                "observed_at": "2026-09-24",
            },
        ],
    )
    assert inserted == 3


def test_store_generates_scope_aware_exposure_links(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        _prepare(store, tmp_path)
        links = store.national_exposure_links(
            "exposure_demo",
            generated_at="2026-09-24T06:30:00+06:00",
        )
        assert len(links) == 4
        assert {
            row["establishment_ref"]
            for row in links
            if row["metric_code"] == "FLOOD_CONTEXT"
        } == {"DIFE:101", "DIFE:102"}

        serialized = json.dumps(links)
        assert "private://exposure/source/file" not in serialized
        assert "source_reference" not in serialized
        assert "exposure_observation_id" not in serialized


def test_store_establishment_exposure_profile_preserves_context_scope(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        _prepare(store, tmp_path)
        profile = store.national_establishment_exposure_profile(
            "exposure_demo",
            "DIFE:101",
            generated_at="2026-09-24T06:30:00+06:00",
        )
        assert profile["coverage"]["linked_observations"] == 2
        assert profile["coverage"]["has_site_specific_evidence"] is False
        assert profile["coverage"]["has_area_context_evidence"] is True
        assert {
            row["attribution"] for row in profile["exposures"]
        } == {"DISTRICT_CONTEXT", "UPAZILA_CONTEXT"}


def test_store_district_and_sector_exposure_profiles_are_coverage_aware(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        _prepare(store, tmp_path)
        district = store.national_district_exposure_profile(
            "exposure_demo",
            "Gazipur",
            generated_at="2026-09-24T06:30:00+06:00",
        )
        sector = store.national_sector_exposure_profile(
            "exposure_demo",
            "RMG_TEXTILE",
            generated_at="2026-09-24T06:30:00+06:00",
        )

        assert district["district"]["establishments"] == 2
        assert district["coverage"]["coverage_pct"] == 100.0
        assert district["method"]["weighting"] == "ESTABLISHMENT_COUNT"

        assert sector["sector"]["establishments"] == 2
        assert sector["coverage"]["coverage_pct"] == 100.0
        assert sector["method"]["no_supply_chain_inference"] is True
        assert sector["method"]["no_composite_score"] is True


def test_exposure_observation_ingestion_is_deduplicated(tmp_path):
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        _prepare(store, tmp_path)
        again = store.ingest_spatial_exposure_observations(
            "Synthetic Exposure Source",
            [{
                "domain": "CLIMATE_HAZARD",
                "metric_code": "FLOOD_CONTEXT",
                "metric_label": "Flood-context class",
                "spatial_scope": "DISTRICT",
                "district": "Gazipur",
                "value_text": "Elevated",
                "direction": "CONTEXT_ONLY",
                "source_vintage": "2026",
                "observed_at": "2026-09-24",
            }],
        )
        assert again == 0
