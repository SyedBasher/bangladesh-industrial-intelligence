import csv
import hashlib
import json

import pytest

from bii.local_store import LocalValidationStore
from bii.offline_national_ingest import (
    OfflineNationalIngestError,
    ingest_normalized_bulk_csv,
    ingest_staged_html_archive,
)


def _page(total, rows):
    html_rows = "".join(
        f"""
        <tr>
          <td><a href="/public-report/establishment/{public_id}">{name}</a></td>
          <td>{sector}</td><td>{location}</td><td>এ</td><td>{status}</td>
        </tr>
        """
        for public_id, name, sector, location, status in rows
    )
    return f"""
    <html><body>
      <div>প্রাপ্ত তথ্য : {total} টি</div>
      <div>দেখাচ্ছে : {len(rows)} টি</div>
      <table><tbody>{html_rows}</tbody></table>
    </body></html>
    """


def _write_archive(root):
    pages = {
        1: _page(3, [
            (101, "A", "গার্মেন্টস/তৈরি পোশাক (নীট)", "টঙ্গী, গাজীপুর, ঢাকা", "নিবন্ধিত"),
            (102, "B", "ফুড ইন্ডাষ্ট্রিজ", "তেজগাঁও, ঢাকা, ঢাকা", "নিবন্ধিত"),
        ]),
        2: _page(3, [
            (103, "C", "ফুটওয়্যার", "কালিয়াকৈর, গাজীপুর, ঢাকা", "নিবন্ধিত"),
        ]),
    }
    entries = []
    for page, text in pages.items():
        filename = f"page_{page:05d}.html"
        payload = text.encode("utf-8")
        (root / filename).write_bytes(payload)
        entries.append({
            "page": page,
            "file": filename,
            "retrieved_at": f"2026-09-24T03:0{page}:00+06:00",
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    manifest = {
        "format_version": "1.0",
        "universe_label": "offline_archive_demo",
        "seed_url": "https://lima.dife.gov.bd/public-report/establishment-list?page=1",
        "page_size": 2,
        "created_at": "2026-09-24T03:00:00+06:00",
        "pages": entries,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )


def test_fixed_html_archive_builds_eligible_national_universe_without_policy(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    _write_archive(archive)

    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        result = ingest_staged_html_archive(store, archive)
        assert result["status"] == "COMPLETED"
        assert result["quality"]["eligible_for_national_analysis"] is True
        assert len(store.national_universe_records("offline_archive_demo")) == 3

        provenance = store.national_ingest_source(result["universe_id"])
        assert provenance["ingest_mode"] == "STAGED_HTML_ARCHIVE"
        assert provenance["artifact_sha256"]
        assert store.conn.execute(
            "SELECT COUNT(*) FROM access_policy_reviews"
        ).fetchone()[0] == 0


def test_archive_manifest_must_cover_exact_source_derived_pages(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    _write_archive(archive)
    manifest_path = archive / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"] = manifest["pages"][:1]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        with pytest.raises(OfflineNationalIngestError):
            ingest_staged_html_archive(store, archive)
        run = store.conn.execute(
            "SELECT status, eligible_for_national_analysis FROM national_universe_runs"
        ).fetchone()
        assert run["status"] == "FAILED"
        assert run["eligible_for_national_analysis"] == 0


def _write_bulk_csv(path, rows):
    columns = [
        "dife_public_id","name","sector","location","upazila",
        "district","division","licence_class","status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_normalized_bulk_export_requires_declared_total_and_finalizes(tmp_path):
    csv_path = tmp_path / "bulk.csv"
    _write_bulk_csv(csv_path, [
        {
            "dife_public_id": 201,
            "name": "Bulk Garments",
            "sector": "গার্মেন্টস/তৈরি পোশাক (নীট)",
            "location": "টঙ্গী, গাজীপুর, ঢাকা",
            "upazila": "টঙ্গী",
            "district": "গাজীপুর",
            "division": "ঢাকা",
            "licence_class": "এ",
            "status": "নিবন্ধিত",
        },
        {
            "dife_public_id": 202,
            "name": "Bulk Food",
            "sector": "ফুড ইন্ডাষ্ট্রিজ",
            "location": "তেজগাঁও, ঢাকা, ঢাকা",
            "upazila": "তেজগাঁও",
            "district": "ঢাকা",
            "division": "ঢাকা",
            "licence_class": "এ",
            "status": "নিবন্ধিত",
        },
    ])
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        result = ingest_normalized_bulk_csv(
            store,
            csv_path,
            universe_label="bulk_demo",
            source_url="https://example.gov.bd/dife-bulk-export-2026-09.csv",
            retrieved_at="2026-09-24T03:20:00+06:00",
            declared_total=2,
            transform_note="Mapped documented bulk export columns to canonical v1 fields.",
        )
        assert result["status"] == "COMPLETED"
        assert result["quality"]["unique_public_ids"] == 2
        rows = store.national_universe_records("bulk_demo")
        assert {row["dife_public_id"] for row in rows} == {201, 202}
        provenance = store.national_ingest_source(result["universe_id"])
        assert provenance["ingest_mode"] == "NORMALIZED_BULK_EXPORT"


def test_bulk_row_count_cannot_define_its_own_completeness(tmp_path):
    csv_path = tmp_path / "bulk.csv"
    _write_bulk_csv(csv_path, [{
        "dife_public_id": 201,
        "name": "Only Row",
        "sector": "ফুড ইন্ডাষ্ট্রিজ",
        "location": "ঢাকা, ঢাকা, ঢাকা",
        "upazila": "ঢাকা",
        "district": "ঢাকা",
        "division": "ঢাকা",
        "licence_class": "এ",
        "status": "নিবন্ধিত",
    }])
    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        with pytest.raises(ValueError):
            ingest_normalized_bulk_csv(
                store,
                csv_path,
                universe_label="incomplete_bulk",
                source_url="https://example.gov.bd/export.csv",
                retrieved_at="2026-09-24T03:20:00+06:00",
                declared_total=2,
                transform_note="One row missing from source export.",
            )
        run = store.conn.execute(
            "SELECT status, eligible_for_national_analysis FROM national_universe_runs"
        ).fetchone()
        assert run["status"] == "FAILED"
        assert run["eligible_for_national_analysis"] == 0


def test_offline_universe_generates_safe_dashboard_and_registry_products(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    _write_archive(archive)

    with LocalValidationStore(tmp_path / "national.sqlite") as store:
        result = ingest_staged_html_archive(store, archive)
        dashboard = store.national_dashboard_payload(
            "offline_archive_demo",
            generated_at="2026-09-24T03:10:00+06:00",
        )
        registry = store.national_registry_product_rows(
            "offline_archive_demo",
            generated_at="2026-09-24T03:10:00+06:00",
        )

        assert dashboard["universe"]["ingest_mode"] == "STAGED_HTML_ARCHIVE"
        assert dashboard["universe"]["expected_total"] == 3
        assert dashboard["summary"]["establishments"] == 3
        assert len(registry) == 3
        assert {row["establishment_ref"] for row in registry} == {
            "DIFE:101", "DIFE:102", "DIFE:103"
        }

        serialized = json.dumps(
            {"dashboard": dashboard, "registry": registry},
            ensure_ascii=False,
        )
        assert str(archive.resolve()) not in serialized
        assert "manifest_json" not in serialized
        assert "artifact_path" not in serialized
        assert "source_url" not in serialized
