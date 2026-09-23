from bii.external_sources import ExternalRecordPayload
from bii.intelligence_observations import (
    ObservationScope,
    extract_typed_observations,
)


def _payload(source_name: str, fields: dict[str, str]) -> ExternalRecordPayload:
    return ExternalRecordPayload(
        source_name=source_name,
        external_key="1",
        entity_name="Example Ltd.",
        site_text="Gazipur",
        district="Gazipur",
        upazila="Tongi",
        source_url="https://example.invalid/1",
        source_updated_at_raw="2026-09-01",
        source_fields=fields,
    )


def test_bgmea_extracts_site_and_organization_observations():
    observations = extract_typed_observations(
        _payload(
            "BGMEA",
            {
                "employees": "1,250",
                "machines": "300",
                "production capacity": "2.5 million pcs/year",
                "principal products": "T-shirts; Polo shirts",
                "export markets": "EU; USA",
                "certifications": "LEED; WRAP",
                "bgmea reg no": "BG-123",
                "epb reg no": "EPB-456",
            },
        )
    )
    by_type = {}
    for observation in observations:
        by_type.setdefault(observation.observation_type, []).append(observation)

    assert by_type["EMPLOYMENT_COUNT"][0].value_numeric == 1250
    assert by_type["EMPLOYMENT_COUNT"][0].scope == ObservationScope.SITE
    assert by_type["MACHINE_COUNT"][0].value_numeric == 300
    assert by_type["PRODUCTION_CAPACITY"][0].value_numeric == 2_500_000
    assert by_type["PRODUCTION_CAPACITY"][0].unit == "pcs/year"
    assert {item.value_text for item in by_type["PRINCIPAL_PRODUCT"]} == {
        "T-shirts",
        "Polo shirts",
    }
    assert {item.value_text for item in by_type["EXPORT_MARKET"]} == {"EU", "USA"}
    assert by_type["ASSOCIATION_REGISTRATION"][0].scope == ObservationScope.ORGANIZATION
    assert by_type["ASSOCIATION_MEMBERSHIP_RECORD"][0].value_text == "present"


def test_epb_hs_codes_and_exporter_presence_are_organization_scoped():
    observations = extract_typed_observations(
        _payload(
            "EPB",
            {
                "hs code": "6109, 6110; 6203",
                "products": "Knit shirts; Sweaters",
                "export markets": "Germany; Canada",
                "association": "BGMEA",
                "epb registration no": "EPB-777",
                "exporter category": "Direct Exporter",
            },
        )
    )
    hs = [item for item in observations if item.observation_type == "HS_CODE"]
    assert [item.value_text for item in hs] == ["6109", "6110", "6203"]
    assert all(item.scope == ObservationScope.ORGANIZATION for item in hs)

    exporter = [
        item for item in observations
        if item.observation_type == "EXPORTER_DATABASE_RECORD"
    ]
    assert len(exporter) == 1
    assert exporter[0].scope == ObservationScope.ORGANIZATION


def test_unknown_source_does_not_invent_typed_observations():
    assert extract_typed_observations(_payload("DOE", {"employees": "500"})) == []
