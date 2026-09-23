import json

from bii.source_index import (
    assess_index_quality,
    parse_bgmea_member_index,
    parse_epb_exporter_index_html,
    parse_epb_exporter_index_json,
    plan_index_requests,
)


def test_bgmea_index_uses_member_detail_id_and_source_total():
    html = """
    <html><body>
      <div>General Members</div>
      <div>Total 4,291 Member(s) Found</div>
      <table>
        <tr><th>Member/Company Name</th><th>BGMEA Reg No</th><th>Details</th></tr>
        <tr>
          <td>Example Garments Ltd.</td><td>7189</td>
          <td><a href="/member/5276">Details</a></td>
        </tr>
        <tr>
          <td>Another Apparel Ltd.</td><td>7190</td>
          <td><a href="/member/5277">Details</a></td>
        </tr>
      </table>
      <a href="/page/member-list?page=2">2</a>
      <a href="/page/member-list?page=215">215</a>
    </body></html>
    """
    meta, records = parse_bgmea_member_index(
        html,
        source_url="https://bgmea.com.bd/page/member-list?page=1",
    )
    assert meta.total_records == 4291
    assert meta.current_page == 1
    assert meta.last_page == 215
    assert records[0].source_key == "5276"
    assert records[0].registration_no == "7189"
    assert records[0].detail_url.endswith("/member/5276")


def test_bgmea_request_plan_covers_known_pages():
    html = """
    <div>Total 40 Member(s) Found</div>
    <table>
      <tr><td>A Ltd.</td><td>1</td><td><a href="/member/1">Details</a></td></tr>
      <tr><td>B Ltd.</td><td>2</td><td><a href="/member/2">Details</a></td></tr>
    </table>
    <a href="?page=2">2</a>
    """
    meta, _ = parse_bgmea_member_index(
        html,
        source_url="https://bgmea.com.bd/page/member-list?page=1",
    )
    requests = plan_index_requests(
        "BGMEA",
        first_page_url="https://bgmea.com.bd/page/member-list?page=1",
        metadata=meta,
    )
    assert [request.page for request in requests] == [1, 2]


def test_epb_json_index_preserves_numeric_id_and_factory_geography():
    payload = {
        "data": {
            "data": [
                {
                    "id": 3701,
                    "name": "Apex Footwear Ltd.",
                    "slug": "apex-footwear-ltd",
                    "factory_address": "Shafipur, Kaliakoir",
                    "factory_thana": {"name": "Kaliakoir"},
                    "factory_district": {"name": "Gazipur"},
                }
            ],
            "current_page": 1,
            "last_page": 10,
            "total": 197,
        }
    }
    meta, records = parse_epb_exporter_index_json(
        json.dumps(payload),
        source_url="https://edb.epb.gov.bd/exporters?page=1",
    )
    assert meta.total_records == 197
    assert meta.last_page == 10
    assert records[0].source_key == "3701"
    assert records[0].district == "Gazipur"
    assert records[0].detail_url.endswith("/exporter/3701/apex-footwear-ltd")


def test_epb_html_never_uses_slug_as_identity():
    html = """
    <div class="card">
      <h3>Apex Footwear Ltd.</h3>
      <a href="/exporter/3701/wrong-changing-slug">Apex Footwear Ltd.</a>
    </div>
    """
    _, records = parse_epb_exporter_index_html(html)
    assert len(records) == 1
    assert records[0].source_key == "3701"


def test_unknown_epb_page_bound_only_plans_seed():
    meta, _ = parse_epb_exporter_index_html(
        '<a href="/exporter/3701/apex-footwear">Apex Footwear Ltd.</a>',
        source_url="https://edb.epb.gov.bd/exporters",
    )
    requests = plan_index_requests(
        "EPB",
        first_page_url="https://edb.epb.gov.bd/exporters",
        metadata=meta,
    )
    assert len(requests) == 1
    assert requests[0].reason == "INDEX_SEED"


def test_index_quality_detects_wrong_url_key():
    from bii.source_index import SourceIndexRecord
    records = [
        SourceIndexRecord(
            "BGMEA", "10", "A Ltd.", "https://bgmea.com.bd/member/10"
        ),
        SourceIndexRecord(
            "BGMEA", "11", "B Ltd.", "https://bgmea.com.bd/member/12"
        ),
    ]
    quality = assess_index_quality(records, expected_segment="member")
    assert quality.records == 2
    assert quality.invalid_detail_urls == 1
    assert quality.valid is False
