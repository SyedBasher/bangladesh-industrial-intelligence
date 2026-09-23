from bii.analytical_intelligence import (
    ConsistencyBand,
    FreshnessBand,
    UniverseKind,
    cluster_context,
    evidence_freshness,
    export_product_breadth,
    numeric_change_signals,
    numeric_source_consistency,
)


def test_freshness_prefers_source_vintage_and_is_explicit():
    result = evidence_freshness(
        [
            {
                "source": "BGMEA",
                "source_vintage": "2026-08-01",
                "observed_at": "2026-09-20T00:00:00+06:00",
            },
            {
                "source": "EPB",
                "source_vintage": "2026-09-01",
                "observed_at": "2026-09-21T00:00:00+06:00",
            },
        ],
        as_of="2026-09-23T23:00:00+06:00",
    )
    assert result["band"] == FreshnessBand.CURRENT
    assert result["basis_field"] == "source_vintage"
    assert result["source"] == "EPB"
    assert result["origin"] == "CALCULATED"


def test_freshness_falls_back_to_observation_time():
    result = evidence_freshness(
        [{"source": "BGMEA", "source_vintage": None, "observed_at": "2025-01-01"}],
        as_of="2026-09-23",
    )
    assert result["band"] == FreshnessBand.STALE
    assert result["basis_field"] == "observed_at"


def test_export_breadth_counts_distinct_organization_evidence():
    result = export_product_breadth(
        [
            {"type": "HS_CODE", "scope": "ORGANIZATION", "value": "6109", "source": "EPB"},
            {"type": "HS_CODE", "scope": "ORGANIZATION", "value": "6109", "source": "EPB"},
            {"type": "HS_CODE", "scope": "ORGANIZATION", "value": "6110", "source": "EPB"},
            {"type": "PRINCIPAL_PRODUCT", "scope": "ORGANIZATION", "value": "T-shirts", "source": "EPB"},
            {"type": "EXPORT_MARKET", "scope": "ORGANIZATION", "value": "Germany", "source": "EPB"},
            {"type": "EXPORTER_DATABASE_RECORD", "scope": "ORGANIZATION", "value": "present", "source": "EPB"},
            {"type": "PRINCIPAL_PRODUCT", "scope": "SITE", "value": "T-shirts", "source": "BGMEA"},
        ]
    )
    assert result["hs_code_count"] == 2
    assert result["product_count"] == 1
    assert result["market_count"] == 1
    assert result["evidence_source_count"] == 1


def test_numeric_consistency_requires_two_site_sources():
    one = numeric_source_consistency(
        [
            {
                "type": "EMPLOYMENT_COUNT",
                "site_attributable": True,
                "numeric_value": 1000,
                "source": "BGMEA",
            }
        ],
        "EMPLOYMENT_COUNT",
    )
    assert one["band"] == ConsistencyBand.NOT_CHECKED

    two = numeric_source_consistency(
        [
            {
                "type": "EMPLOYMENT_COUNT",
                "site_attributable": True,
                "numeric_value": 1000,
                "source": "BGMEA",
            },
            {
                "type": "EMPLOYMENT_COUNT",
                "site_attributable": True,
                "numeric_value": 1080,
                "source": "OTHER",
            },
        ],
        "EMPLOYMENT_COUNT",
    )
    assert two["band"] == ConsistencyBand.CONSISTENT
    assert two["source_count"] == 2


def test_numeric_change_signal_does_not_call_change_growth():
    result = numeric_change_signals(
        [
            {
                "observation_type": "EMPLOYMENT_COUNT",
                "source_name": "BGMEA",
                "site_attributable": 1,
                "value_numeric": 1000,
                "unit": None,
                "observed_at": "2025-09-01",
            },
            {
                "observation_type": "EMPLOYMENT_COUNT",
                "source_name": "BGMEA",
                "site_attributable": 1,
                "value_numeric": 1200,
                "unit": None,
                "observed_at": "2026-09-01",
            },
        ]
    )
    assert result[0]["absolute_change"] == 200
    assert result[0]["percent_change"] == 20.0
    assert "not automatically interpreted" in result[0]["rule"].lower()


def test_validation_sample_cluster_context_refuses_national_claim():
    records = [
        {"district": "Gazipur", "sector_family": "RMG_TEXTILE"},
        {"district": "Gazipur", "sector_family": "RMG_TEXTILE"},
        {"district": "Gazipur", "sector_family": "FOOD_AGRO"},
        {"district": "Dhaka", "sector_family": "RMG_TEXTILE"},
    ]
    result = cluster_context(
        records,
        district="Gazipur",
        sector_family="RMG_TEXTILE",
        universe_label="validation_demo",
        universe_kind=UniverseKind.VALIDATION_SAMPLE,
    )
    assert result["district_sector_establishments"] == 2
    assert result["district_sector_share_of_district"] == 66.67
    assert result["district_sector_share_of_sector"] == 66.67
    assert result["suitable_for_national_cluster_claim"] is False


def test_national_registry_cluster_context_marks_universe_as_suitable():
    result = cluster_context(
        [{"district": "Gazipur", "sector_family": "RMG_TEXTILE"}],
        district="Gazipur",
        sector_family="RMG_TEXTILE",
        universe_label="dife_national_snapshot_2026_09",
        universe_kind=UniverseKind.NATIONAL_REGISTRY,
    )
    assert result["suitable_for_national_cluster_claim"] is True
