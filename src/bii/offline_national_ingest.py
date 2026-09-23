from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .local_store import LocalValidationStore


class OfflineNationalIngestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArchivePage:
    page: int
    file: str
    retrieved_at: str
    sha256: str | None = None


@dataclass(frozen=True)
class ArchiveManifest:
    format_version: str
    universe_label: str
    seed_url: str
    page_size: int
    created_at: str
    pages: tuple[ArchivePage, ...]


NORMALIZED_BULK_COLUMNS = (
    "dife_public_id",
    "name",
    "sector",
    "location",
    "upazila",
    "district",
    "division",
    "licence_class",
    "status",
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise OfflineNationalIngestError(
            f"archive page escapes the archive directory: {relative!r}"
        )
    if not candidate.is_file():
        raise OfflineNationalIngestError(f"archive page not found: {relative!r}")
    return candidate


def load_archive_manifest(path: str | Path) -> ArchiveManifest:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("format_version") != "1.0":
        raise OfflineNationalIngestError("unsupported archive manifest format_version")
    pages = tuple(
        ArchivePage(
            page=int(item["page"]),
            file=str(item["file"]),
            retrieved_at=str(item["retrieved_at"]),
            sha256=None if item.get("sha256") is None else str(item["sha256"]),
        )
        for item in data.get("pages", [])
    )
    if not pages:
        raise OfflineNationalIngestError("archive manifest must contain at least one page")
    page_numbers = [item.page for item in pages]
    if len(page_numbers) != len(set(page_numbers)):
        raise OfflineNationalIngestError("archive manifest contains duplicate page numbers")
    if min(page_numbers) != 1:
        raise OfflineNationalIngestError("archive manifest must include page 1")
    page_size = int(data["page_size"])
    if page_size <= 0:
        raise OfflineNationalIngestError("page_size must be positive")
    return ArchiveManifest(
        format_version="1.0",
        universe_label=str(data["universe_label"]),
        seed_url=str(data["seed_url"]),
        page_size=page_size,
        created_at=str(data["created_at"]),
        pages=tuple(sorted(pages, key=lambda item: item.page)),
    )


def ingest_staged_html_archive(
    store: LocalValidationStore,
    archive_dir: str | Path,
    *,
    manifest_name: str = "manifest.json",
) -> dict[str, object]:
    """Create and finalize a national universe from a fixed private HTML archive."""
    root = Path(archive_dir)
    manifest_path = _safe_child(root, manifest_name)
    manifest_bytes = manifest_path.read_bytes()
    manifest = load_archive_manifest(manifest_path)

    universe_id = store.create_national_universe_run(
        manifest.universe_label,
        seed_url=manifest.seed_url,
        started_at=manifest.created_at,
        page_size=manifest.page_size,
        notes="Offline staged HTML archive import; no live HTTP collection.",
    )
    store.record_national_ingest_source(
        universe_id,
        ingest_mode="STAGED_HTML_ARCHIVE",
        artifact_path=str(root.resolve()),
        artifact_sha256=_sha256_bytes(manifest_bytes),
        manifest_json=manifest_bytes.decode("utf-8"),
        imported_at=manifest.created_at,
    )

    pages_by_number = {item.page: item for item in manifest.pages}
    page_one = pages_by_number[1]
    page_one_path = _safe_child(root, page_one.file)
    page_one_bytes = page_one_path.read_bytes()
    page_one_hash = _sha256_bytes(page_one_bytes)
    if page_one.sha256 and page_one.sha256.lower() != page_one_hash:
        store.abort_national_universe_run(
            universe_id,
            aborted_at=manifest.created_at,
            reason="archive page 1 hash does not match manifest",
        )
        raise OfflineNationalIngestError("archive page 1 hash mismatch")

    try:
        store.ingest_national_universe_page(
            universe_id,
            page_one_bytes.decode("utf-8", errors="replace"),
            source_url=manifest.seed_url,
            retrieved_at=page_one.retrieved_at,
            raw_payload_path=str(page_one_path),
            parser_version="offline-html-1.0",
        )
        store.expand_national_universe_run(
            universe_id,
            planned_at=manifest.created_at,
        )

        planned = store.conn.execute(
            """SELECT page, source_url
               FROM national_universe_pages
               WHERE universe_id=?
               ORDER BY page""",
            (universe_id,),
        ).fetchall()
        planned_pages = {int(row["page"]): str(row["source_url"]) for row in planned}
        manifest_pages = set(pages_by_number)
        if manifest_pages != set(planned_pages):
            reason = (
                f"archive manifest page set {sorted(manifest_pages)} does not match "
                f"source-derived page set {sorted(planned_pages)}"
            )
            store.abort_national_universe_run(
                universe_id,
                aborted_at=manifest.created_at,
                reason=reason,
            )
            raise OfflineNationalIngestError(reason)

        for page in sorted(manifest_pages - {1}):
            item = pages_by_number[page]
            path = _safe_child(root, item.file)
            payload = path.read_bytes()
            digest = _sha256_bytes(payload)
            if item.sha256 and item.sha256.lower() != digest:
                raise OfflineNationalIngestError(
                    f"archive page {page} hash does not match manifest"
                )
            store.ingest_national_universe_page(
                universe_id,
                payload.decode("utf-8", errors="replace"),
                source_url=planned_pages[page],
                retrieved_at=item.retrieved_at,
                raw_payload_path=str(path),
                parser_version="offline-html-1.0",
            )
    except Exception as exc:
        run = store.national_universe_run(universe_id)
        if run["status"] == "RUNNING":
            store.abort_national_universe_run(
                universe_id,
                aborted_at=manifest.created_at,
                reason=f"offline archive import failed: {type(exc).__name__}: {exc}",
            )
        raise

    finalized = store.finalize_national_universe_run(
        universe_id,
        completed_at=max(item.retrieved_at for item in manifest.pages),
    )
    return {
        "universe_id": universe_id,
        "universe_label": manifest.universe_label,
        "ingest_mode": "STAGED_HTML_ARCHIVE",
        "status": finalized["status"],
        "quality": finalized["quality"],
    }


def load_normalized_bulk_csv(path: str | Path) -> list[dict[str, object]]:
    """Read the canonical normalized bulk intermediary; no source columns are guessed."""
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise OfflineNationalIngestError("bulk CSV has no header")
        missing = [column for column in NORMALIZED_BULK_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise OfflineNationalIngestError(
                "bulk CSV is missing required canonical columns: " + ", ".join(missing)
            )

        records: list[dict[str, object]] = []
        for line_no, row in enumerate(reader, start=2):
            raw_id = (row.get("dife_public_id") or "").strip()
            name = (row.get("name") or "").strip()
            if not raw_id.isdigit() or int(raw_id) <= 0:
                raise OfflineNationalIngestError(
                    f"invalid dife_public_id at CSV line {line_no}"
                )
            if not name:
                raise OfflineNationalIngestError(
                    f"blank establishment name at CSV line {line_no}"
                )
            records.append({
                "dife_public_id": int(raw_id),
                "name": name,
                "sector": (row.get("sector") or "").strip() or None,
                "location": (row.get("location") or "").strip() or None,
                "upazila": (row.get("upazila") or "").strip() or None,
                "district": (row.get("district") or "").strip() or None,
                "division": (row.get("division") or "").strip() or None,
                "licence_class": (row.get("licence_class") or "").strip() or None,
                "status": (row.get("status") or "").strip() or None,
            })
    return records


def ingest_normalized_bulk_csv(
    store: LocalValidationStore,
    csv_path: str | Path,
    *,
    universe_label: str,
    source_url: str,
    retrieved_at: str,
    declared_total: int,
    transform_note: str,
) -> dict[str, object]:
    """Create a national universe from a normalized lawful bulk export.

    declared_total must come from the source/export manifest, not from len(records).
    """
    if declared_total <= 0:
        raise OfflineNationalIngestError("declared_total must be positive")
    if not transform_note.strip():
        raise OfflineNationalIngestError("transform_note is required for bulk provenance")

    path = Path(csv_path)
    payload = path.read_bytes()
    records = load_normalized_bulk_csv(path)

    universe_id = store.create_national_universe_run(
        universe_label,
        seed_url=source_url,
        started_at=retrieved_at,
        page_size=declared_total,
        notes="Normalized lawful bulk export import; no live HTTP collection.",
    )
    manifest = {
        "format_version": "1.0",
        "declared_total": declared_total,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "canonical_columns": list(NORMALIZED_BULK_COLUMNS),
        "transform_note": transform_note,
    }
    store.record_national_ingest_source(
        universe_id,
        ingest_mode="NORMALIZED_BULK_EXPORT",
        artifact_path=str(path.resolve()),
        artifact_sha256=_sha256_bytes(payload),
        manifest_json=json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        imported_at=retrieved_at,
    )

    try:
        store.ingest_normalized_national_records(
            universe_id,
            records,
            source_url=source_url,
            retrieved_at=retrieved_at,
            declared_total=declared_total,
            artifact_sha256=_sha256_bytes(payload),
            raw_payload_path=str(path.resolve()),
            transform_note=transform_note,
        )
    except Exception as exc:
        run = store.national_universe_run(universe_id)
        if run["status"] == "RUNNING":
            store.abort_national_universe_run(
                universe_id,
                aborted_at=retrieved_at,
                reason=f"normalized bulk import failed: {type(exc).__name__}: {exc}",
            )
        raise

    finalized = store.finalize_national_universe_run(
        universe_id,
        completed_at=retrieved_at,
    )
    return {
        "universe_id": universe_id,
        "universe_label": universe_label,
        "ingest_mode": "NORMALIZED_BULK_EXPORT",
        "status": finalized["status"],
        "quality": finalized["quality"],
    }
