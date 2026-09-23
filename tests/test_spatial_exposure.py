import pytest

from bii.spatial_exposure import (
    build_district_exposure_profile,
    build_establishment_exposure_profile,
    build_sector_exposure_profile,
    exposure_link_coverage,
    link_exposure_observations,
    validate_exposure_observation,
)


def _registry():
    return [
        {
            "establishment_ref": "DIFE:101",
            "name": "Factory A",
            "district": "Gazipur",
            "upazila": "Tongi",
            "sector_family": "RMG_TEXTILE",
        },
        {
            "establishment_ref": "DIFE:102",
            "name": "Factory B",
            "district": "Gazipur",
            "upazila": "Kaliakair",
            "sector_family": "RMG_TEXTILE",
        },
        {
            "establishment_ref": "DIFE:103",
            "name": "Factory C",
            "district": "Dhaka",
            "upazila": "Tejgaon",
            "sector_family": "FOOD_AGRO",
        },
    ]


def _observations():
    return [
        {
            "source": "Synthetic Hazard Atlas",
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
            "source": "Synthetic Grid Source",
            "domain": "POWER_SYSTEM",
            "metric_code": "FEEDER_OUTAGE_HOURS",
            "metric_label": "Reported feeder outage hours",
            "spatial_scope": "UPAZILA",
            "district": "Gazipur",
            "upazila": "Tongi",
            "value_numeric": 6.5,
            "unit": "hours/month",
            "direction": "HIGHER_MEANS_MORE_EXPOSURE",
            "source_vintage": "2026-08",
            "observed_at": "2026-09-24",
        },
        {
            "source": "Synthetic Site Audit",
            "domain": "TRANSPORT_ACCESS",
            "metric_code": "PORT_TRAVEL_TIME",
            "metric_label": "Travel time to port",
            "spatial_scope": "SITE",
            "establishment_ref": "DIFE:102",
            "value_numeric": 95,
            "unit": "minutes",
            "direction": "HIGHER_MEANS_MORE_EXPOSURE",
            "source_vintage": "2026-09",
            "observed_at": "2026-09-24",
        },
    ]


def test_scope_validation_is_fail_closed():
    with pytest.raises(ValueError):
        validate_exposure_observation({
            "source": "X",
            "domain": "CLIMATE_HAZARD",
            "metric_code": "FLOOD",
            "metric_label": "Flood",
            "spatial_scope": "UPAZILA",
            "upazila": "Tongi",
        })
    with pytest.raises(ValueError):
        validate_exposure_observation({
            "source": "X",
            "domain": "CLIMATE_HAZARD",
            "metric_code": "FLOOD",
            "metric_label": "Flood",
            "spatial_scope": "SITE",
        })


def test_district_upazila_and_site_exposures_have_distinct_attribution():
    links = link_exposure_observations(_registry(), _observations())
    gazipur_flood = [
        row for row in links
        if row["metric_code"] == "FLOOD_CONTEXT"
    ]
    assert {row["establishment_ref"] for row in gazipur_flood} == {
        "DIFE:101", "DIFE:102"
    }
    assert {row["attribution"] for row in gazipur_flood} == {
        "DISTRICT_CONTEXT"
    }

    outage = [row for row in links if row["metric_code"] == "FEEDER_OUTAGE_HOURS"]
    assert [row["establishment_ref"] for row in outage] == ["DIFE:101"]
    assert outage[0]["attribution"] == "UPAZILA_CONTEXT"

    site = [row for row in links if row["metric_code"] == "PORT_TRAVEL_TIME"]
    assert [row["establishment_ref"] for row in site] == ["DIFE:102"]
    assert site[0]["attribution"] == "SITE_SPECIFIC"


def test_no_fuzzy_geography_inference():
    observations = [{
        "source": "X",
        "domain": "CLIMATE_HAZARD",
        "metric_code": "FLOOD",
        "metric_label": "Flood",
        "spatial_scope": "DISTRICT",
        "district": "Gazipur District",
        "value_text": "Context",
    }]
    assert link_exposure_observations(_registry(), observations) == []


def test_coverage_is_evidence_coverage_not_risk_prevalence():
    links = link_exposure_observations(_registry(), _observations())
    result = exposure_link_coverage(_registry(), links)
    assert result["registry_establishments"] == 3
    assert result["establishments_with_any_exposure_evidence"] == 2
    assert result["coverage_pct"] == 66.6667
    assert "not the share harmed or at risk" in result["note"].lower()


def test_establishment_profile_keeps_area_context_separate():
    links = link_exposure_observations(_registry(), _observations())
    profile = build_establishment_exposure_profile(
        _registry()[0],
        links,
        generated_at="2026-09-24T06:00:00+06:00",
    )
    assert profile["coverage"]["has_site_specific_evidence"] is False
    assert profile["coverage"]["has_area_context_evidence"] is True
    assert {
        row["attribution"] for row in profile["exposures"]
    } == {"DISTRICT_CONTEXT", "UPAZILA_CONTEXT"}
    assert profile["method"]["no_composite_score"] is True


def test_district_profile_uses_establishment_count_weighting_only():
    links = link_exposure_observations(_registry(), _observations())
    district_profile = {
        "district": {"name": "Gazipur", "establishments": 2}
    }
    profile = build_district_exposure_profile(
        district_profile,
        _registry(),
        links,
        generated_at="2026-09-24T06:00:00+06:00",
    )
    assert profile["district"]["establishments"] == 2
    assert profile["coverage"]["coverage_pct"] == 100.0
    assert profile["method"]["weighting"] == "ESTABLISHMENT_COUNT"
    assert "employment" in profile["method"]["note"].lower()
    flood = next(
        row for row in profile["conditions"]
        if row["metric_code"] == "FLOOD_CONTEXT"
    )
    assert flood["establishments_contextualized"] == 2


def test_sector_profile_does_not_infer_supply_chain_propagation():
    links = link_exposure_observations(_registry(), _observations())
    sector_profile = {
        "sector": {"sector_family": "RMG_TEXTILE", "establishments": 2}
    }
    profile = build_sector_exposure_profile(
        sector_profile,
        _registry(),
        links,
        generated_at="2026-09-24T06:00:00+06:00",
    )
    assert profile["sector"]["establishments"] == 2
    assert profile["coverage"]["coverage_pct"] == 100.0
    assert profile["method"]["no_supply_chain_inference"] is True
    assert profile["method"]["no_composite_score"] is True
