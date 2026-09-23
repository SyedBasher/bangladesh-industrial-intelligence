import json

from bii.product_export import write_product_json, write_product_jsonl
from bii.product_view import ProductBaseRecord, build_product_payload


def _payload():
    return build_product_payload(
        ProductBaseRecord(
            public_id=101,
            name="Example Factory Ltd.",
            address="Gazipur",
            upazila="Tongi",
            district="Gazipur",
            division="Dhaka",
            official_status="Registered",
            industrial_sector="Knit garments",
            establishment_type="Factory",
            licence_class="A",
            licence_expiry_raw="2027-12-31",
            worker_total=500,
            observed_at="2026-09-24T00:40:00+06:00",
        ),
        [],
        generated_at="2026-09-24T00:41:00+06:00",
    )


def test_write_safe_json_and_jsonl(tmp_path):
    payload = _payload()
    json_path = write_product_json([payload], tmp_path / "feed.json")
    jsonl_path = write_product_jsonl([payload], tmp_path / "feed.jsonl")

    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded[0]["establishment"]["establishment_ref"] == "DIFE:101"

    line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert line["schema_version"] == "1.0"
    assert "snapshot_id" not in jsonl_path.read_text(encoding="utf-8")
