from pathlib import Path

import pytest

from bii.admin_geography import (
    AdministrativeGeographyCrosswalk,
    ddm_aware_default_aliases,
    load_normalized_bbs_geocode_csv,
)
from bii.ddm_aware import (
    DDM_AWARE_SOURCE_NAME,
    ddm_records_to_exposure_observations,
    parse_ddm_aware_risk_html,
)
from bii.spatial_exposure import link_exposure_observations


ROOT = Path(__file__).parent
GEO = ROOT / "fixtures" / "bbs_geocode_minimal.csv"
DDM = ROOT / "fixtures" / "ddm_aware_risk_minimal.html"


def _crosswalk():
    units = load_normalized_bbs_geocode_csv(
        GEO,
        source_vintage="synthetic-test",
    )
    return AdministrativeGeographyCrosswalk(
        units,
        ddm_aware_default_aliases(units),
    )


def test_parse_ddm_aware_public_table_shape():
    records = parse_ddm_aware_risk_html(
        DDM.read_text(encoding="utf-8")
    )
    assert len(records) == 3
    assert records[0].district == "Gazipur"
    assert records[0].hazard_exposure == "Very Low"
    assert records[1].district == "Nawabganj"
    assert records[1].risk == "Medium"


def test_ddm_conversion_preserves_source_categories_and_reports_unresolved():
    result = ddm_records_to_exposure_observations(
        parse_ddm_aware_risk_html(DDM.read_text(encoding="utf-8")),
        _crosswalk(),
        source_vintage="2026-09-24",
        observed_at="2026-09-24T06:30:00+06:00",
    )

    assert result.source_records == 3
    assert result.mapped_districts == 2
    assert len(result.observations) == 10
    assert len(result.unresolved) == 1
    assert result.unresolved[0].district == "Not A District"

    gazipur = [
        row for row in result.observations
        if row["district"] == "Gazipur"
        and row["metric_code"] == "DDM_HAZARD_EXPOSURE"
    ][0]
    assert gazipur["value_text"] == "Very Low"
    assert gazipur["value_numeric"] is None
    assert gazipur["domain"] == "DISASTER_RISK"
    assert gazipur["canonical_geo_ref"] == "BBS:DIST:30:33"
    assert gazipur["geography_match_type"] == "EXACT_NAME"

    nawabganj = [
        row for row in result.observations
        if row["district"] == "Chapai Nawabganj"
        and row["metric_code"] == "DDM_RISK_CATEGORY"
    ][0]
    assert nawabganj["value_text"] == "Medium"
    assert nawabganj["geography_match_type"] == "APPROVED_ALIAS"


def test_canonical_geography_links_english_ddm_to_bangla_registry():
    converted = ddm_records_to_exposure_observations(
        parse_ddm_aware_risk_html(DDM.read_text(encoding="utf-8")),
        _crosswalk(),
        source_vintage="2026-09-24",
        observed_at="2026-09-24T06:30:00+06:00",
    )
    registry = [
        {
            "establishment_ref": "DIFE:101",
            "name": "Factory A",
            "division": "ঢাকা",
            "district": "গাজীপুর",
            "upazila": "টঙ্গী",
            "sector_family": "RMG_TEXTILE",
        }
    ]
    gazipur_observations = [
        row for row in converted.observations
        if row["canonical_geo_ref"] == "BBS:DIST:30:33"
    ]
    links = link_exposure_observations(
        registry,
        gazipur_observations,
        geography_crosswalk=_crosswalk(),
    )
    assert len(links) == 5
    assert {row["establishment_ref"] for row in links} == {"DIFE:101"}
    assert {row["attribution"] for row in links} == {"DISTRICT_CONTEXT"}
    assert {row["canonical_geo_ref"] for row in links} == {"BBS:DIST:30:33"}


def test_ddm_parser_rejects_unknown_ordinal_category():
    html = DDM.read_text(encoding="utf-8").replace(
        "<td>Very Low</td><td>Very Low</td><td>Medium</td><td>Low</td>",
        "<td>Extreme</td><td>Very Low</td><td>Medium</td><td>Low</td>",
        1,
    )
    with pytest.raises(ValueError):
        parse_ddm_aware_risk_html(html)
