import pytest

from bii.product_view import (
    ProductBaseRecord,
    assert_product_payload_safe,
    build_product_payload,
)


def _base(worker_total=1000):
    return ProductBaseRecord(
        public_id=101,
        name="Example Garments Ltd.",
        address="Tongi, Gazipur",
        upazila="Tongi",
        district="Gazipur",
        division="Dhaka",
        official_status="Registered",
        industrial_sector="Knit garments",
        establishment_type="Factory",
        licence_class="A",
        licence_expiry_raw="2027-12-31",
        worker_total=worker_total,
        observed_at="2026-09-24T00:30:00+06:00",
    )


def _observations():
    return [
        {
            "source_name": "BGMEA",
            "match_type": "PROBABLE_SITE",
            "display_scope": "SITE",
            "site_attributable": 1,
            "observation_type": "EMPLOYMENT_COUNT",
            "value_text": "1,080",
            "value_numeric": 1080,
            "unit": None,
            "source_updated_at_raw": "2026-08-01",
            "observed_at": "2026-09-24T00:31:00+06:00",
            "raw_label": "Employees",
            "raw_value": "1,080",
            "external_record_id": 99,
        },
        {
            "source_name": "BGMEA",
            "match_type": "PROBABLE_SITE",
            "display_scope": "SITE",
            "site_attributable": 1,
            "observation_type": "MACHINE_COUNT",
            "value_text": "300",
            "value_numeric": 300,
            "unit": None,
            "source_updated_at_raw": "2026-08-01",
            "observed_at": "2026-09-24T00:31:00+06:00",
        },
        {
            "source_name": "EPB",
            "match_type": "ORGANIZATION_ONLY",
            "display_scope": "ORGANIZATION",
            "site_attributable": 0,
            "observation_type": "HS_CODE",
            "value_text": "6109",
            "value_numeric": None,
            "unit": None,
            "source_updated_at_raw": "2026-09-01",
            "observed_at": "2026-09-24T00:32:00+06:00",
        },
        {
            "source_name": "EPB",
            "match_type": "ORGANIZATION_ONLY",
            "display_scope": "ORGANIZATION",
            "site_attributable": 0,
            "observation_type": "EXPORTER_DATABASE_RECORD",
            "value_text": "present",
            "value_numeric": None,
            "unit": None,
            "source_updated_at_raw": "2026-09-01",
            "observed_at": "2026-09-24T00:32:00+06:00",
        },
    ]


def test_product_payload_is_allowlisted_and_does_not_leak_internal_fields():
    payload = build_product_payload(
        _base(),
        _observations(),
        generated_at="2026-09-24T00:33:00+06:00",
    )
    assert payload["schema_version"] == "1.0"
    assert payload["establishment"]["establishment_ref"] == "DIFE:101"
    assert "external_record_id" not in str(payload)
    assert "raw_label" not in str(payload)
    assert "raw_value" not in str(payload)
    assert payload["facts"]["hs_codes"][0]["scope"] == "ORGANIZATION"


def test_calculated_indicators_are_explicitly_calculated():
    payload = build_product_payload(
        _base(),
        _observations(),
        generated_at="2026-09-24T00:33:00+06:00",
    )
    calculated = payload["calculated"]
    assert calculated["employment_scale_band"]["value"] == "1000_PLUS"
    assert calculated["employment_scale_band"]["origin"] == "CALCULATED"
    assert calculated["export_evidence_breadth"]["value"] == 1
    assert calculated["export_evidence_breadth"]["label"] == "SINGLE_SOURCE"
    assert calculated["employment_consistency"]["value"] == "CONSISTENT_WITHIN_10_PERCENT"
    assert calculated["employment_consistency"]["comparisons"][0]["absolute_difference_pct"] == 8.0


def test_employment_band_is_neutral_analytical_band_not_official_classification():
    payload = build_product_payload(
        _base(worker_total=249),
        [],
        generated_at="2026-09-24T00:33:00+06:00",
    )
    band = payload["calculated"]["employment_scale_band"]
    assert band["value"] == "50_249"
    assert "not an official" in band["rule"].lower()


def test_product_safety_checker_fails_closed_on_private_fields():
    with pytest.raises(ValueError):
        assert_product_payload_safe({
            "schema_version": "1.0",
            "source_url": "https://private.example",
            "nested": {"snapshot_id": 10},
        })


def test_unapproved_observation_type_is_not_exported():
    rows = _observations() + [{
        "source_name": "BGMEA",
        "match_type": "PROBABLE_SITE",
        "display_scope": "SITE",
        "site_attributable": 1,
        "observation_type": "INTERNAL_REVIEW_NOTE",
        "value_text": "do not publish",
        "value_numeric": None,
        "unit": None,
        "source_updated_at_raw": None,
        "observed_at": "2026-09-24T00:31:00+06:00",
    }]
    payload = build_product_payload(
        _base(),
        rows,
        generated_at="2026-09-24T00:33:00+06:00",
    )
    assert all(item["type"] != "INTERNAL_REVIEW_NOTE" for item in payload["evidence"])
