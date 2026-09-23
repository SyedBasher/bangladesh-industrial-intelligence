import pytest

from bii.external_sources import (
    is_sector_eligible,
    parse_bepza_record,
    parse_bgmea_record,
    parse_bkmea_record,
    parse_doe_record,
    parse_epb_record,
)


def test_epb_uses_numeric_exporter_id_not_slug():
    html = """
    <h2>Example Exporter Ltd.</h2>
    <table>
      <tr><th>Factory Address</th><td>Gazipur Industrial Area</td></tr>
      <tr><th>District</th><td>Gazipur</td></tr>
      <tr><th>Thana</th><td>Gazipur Sadar</td></tr>
      <tr><th>HS Code</th><td>6109</td></tr>
      <tr><th>Updated</th><td>2026-09-01</td></tr>
    </table>
    """
    record = parse_epb_record(
        html,
        "https://example.epb.gov.bd/exporter/3701/example-exporter",
    )
    assert record.external_key == "3701"
    assert record.entity_name == "Example Exporter Ltd."
    assert record.district == "Gazipur"
    assert record.source_fields["hs code"] == "6109"


def test_bgmea_parses_factory_specific_fields():
    html = """
    <h2>Example Garments Ltd.</h2>
    <table>
      <tr><th>Factory Address</th><td>Tongi, Gazipur</td></tr>
      <tr><th>District</th><td>Gazipur</td></tr>
      <tr><th>BGMEA Reg No</th><td>1234</td></tr>
      <tr><th>Employees</th><td>750</td></tr>
      <tr><th>Machines</th><td>300</td></tr>
    </table>
    """
    record = parse_bgmea_record(html, "https://www.bgmea.com.bd/member/1234")
    assert record.external_key == "1234"
    assert record.site_text == "Tongi, Gazipur"
    assert record.source_fields["machines"] == "300"


def test_bkmea_membership_number_is_stable_key_and_scope_is_org_default():
    html = """
    <h2>Example Knit Ltd.</h2>
    <table>
      <tr><th>Membership No</th><td>BK-0099</td></tr>
      <tr><th>Member Type</th><td>Ordinary</td></tr>
    </table>
    """
    record = parse_bkmea_record(html, "https://www.bkmea.com/member/example")
    assert record.external_key == "bk 0099"
    assert is_sector_eligible("BKMEA", "RMG_TEXTILE") is True
    assert is_sector_eligible("BKMEA", "FOOD_AGRO") is False


def test_bepza_requires_zone_plus_enterprise_for_key():
    html = """
    <table>
      <tr><th>Enterprise</th><td>Example Electronics Ltd.</td></tr>
      <tr><th>Zone</th><td>Dhaka EPZ</td></tr>
      <tr><th>Products</th><td>Electronic components</td></tr>
    </table>
    """
    record = parse_bepza_record(html, "https://www.bepza.gov.bd/investors/dhaka-epz")
    assert record.external_key.startswith("dhaka epz::example electronics")


def test_doe_client_id_is_preserved_and_search_hit_is_not_certificate_claim():
    html = """
    <table>
      <tr><th>Client ID</th><td>DOE-7788</td></tr>
      <tr><th>Project/Industry</th><td>Example Chemical Industries</td></tr>
      <tr><th>Address</th><td>Narayanganj</td></tr>
      <tr><th>Environmental Category</th><td>Red</td></tr>
    </table>
    """
    record = parse_doe_record(html, "https://ecc.doe.gov.bd/search")
    assert record.external_key == "doe 7788"
    assert record.source_fields["environmental category"] == "Red"


def test_epb_rejects_slug_without_numeric_key():
    with pytest.raises(ValueError):
        parse_epb_record("<h2>Example</h2>", "https://example.com/exporter/example")
