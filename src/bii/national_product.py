from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping


NATIONAL_DASHBOARD_SCHEMA_VERSION = "1.0"
NATIONAL_REGISTRY_SCHEMA_VERSION = "1.0"

_FORBIDDEN_KEYS = frozenset({
    "artifact_path",
    "raw_payload_path",
    "manifest_json",
    "seed_url",
    "source_url",
    "snapshot_id",
    "universe_id",
    "observation_id",
    "content_sha256",
    "artifact_sha256",
    "qc_json",
})


def _assert_safe(value: object, path: str = "$") -> None:
    violations: list[str] = []

    def walk(item: object, current: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                text = str(key)
                if text in _FORBIDDEN_KEYS:
                    violations.append(f"{current}.{text}")
                if text.endswith("_id"):
                    violations.append(f"{current}.{text}")
                walk(child, f"{current}.{text}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{current}[{index}]")

    walk(value, path)
    if violations:
        raise ValueError(
            "national product payload contains forbidden internal/private fields: "
            + ", ".join(sorted(set(violations)))
        )


def build_national_dashboard_payload(
    rollups: Mapping[str, object],
    *,
    universe_label: str,
    generated_at: str,
    completed_at: str | None,
    expected_total: int,
    unique_public_ids: int,
    ingest_mode: str,
) -> dict[str, object]:
    if rollups.get("universe_kind") != "NATIONAL_REGISTRY":
        raise ValueError("dashboard requires a NATIONAL_REGISTRY rollup")
    if expected_total <= 0 or unique_public_ids != expected_total:
        raise ValueError("dashboard requires exact eligible national coverage")

    payload = {
        "schema_version": NATIONAL_DASHBOARD_SCHEMA_VERSION,
        "generated_at": generated_at,
        "universe": {
            "label": universe_label,
            "kind": "NATIONAL_REGISTRY",
            "source": "DIFE",
            "completed_at": completed_at,
            "expected_total": expected_total,
            "unique_public_ids": unique_public_ids,
            "ingest_mode": ingest_mode,
            "eligible_for_national_analysis": True,
        },
        "summary": dict(rollups["summary"]),
        "districts": [dict(row) for row in rollups["districts"]],
        "divisions": [dict(row) for row in rollups["divisions"]],
        "sector_families": [dict(row) for row in rollups["sector_families"]],
        "district_sector_cells": [
            dict(row) for row in rollups["district_sector_cells"]
        ],
        "statuses": [dict(row) for row in rollups["statuses"]],
        "source_sector_labels": [
            dict(row) for row in rollups["source_sector_labels"]
        ],
        "method": dict(rollups["method"]),
    }
    _assert_safe(payload)
    return payload


def build_national_registry_rows(
    records: Iterable[Mapping[str, object]],
    *,
    universe_label: str,
    generated_at: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[int] = set()
    for record in records:
        public_id = int(record["dife_public_id"])
        if public_id in seen:
            raise ValueError(f"duplicate DIFE public ID in product feed: {public_id}")
        seen.add(public_id)
        row = {
            "schema_version": NATIONAL_REGISTRY_SCHEMA_VERSION,
            "generated_at": generated_at,
            "universe_label": universe_label,
            "establishment_ref": f"DIFE:{public_id}",
            "name": record.get("name"),
            "location": record.get("location"),
            "upazila": record.get("upazila"),
            "district": record.get("district"),
            "division": record.get("division"),
            "source_sector_label": record.get("sector_label"),
            "sector_family": record.get("sector_family"),
            "official_status": record.get("status"),
            "licence_class": record.get("licence_class"),
            "observed_at": record.get("observed_at"),
            "source": "DIFE",
        }
        _assert_safe(row)
        rows.append(row)
    rows.sort(key=lambda item: int(str(item["establishment_ref"]).split(":")[1]))
    return rows


def write_national_dashboard_json(
    payload: Mapping[str, object],
    path: str | Path,
) -> Path:
    _assert_safe(payload)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return destination


def write_national_registry_jsonl(
    rows: Iterable[Mapping[str, object]],
    path: str | Path,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized: list[str] = []
    for row in rows:
        item = dict(row)
        _assert_safe(item)
        serialized.append(
            json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    destination.write_text(
        "\n".join(serialized) + ("\n" if serialized else ""),
        encoding="utf-8",
    )
    return destination
