from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

from .product_view import assert_product_payload_safe


def write_product_json(
    payloads: Iterable[Mapping[str, object]],
    path: str | Path,
) -> Path:
    """Write an approved product feed as a JSON array."""
    destination = Path(path)
    rows = [dict(payload) for payload in payloads]
    for payload in rows:
        assert_product_payload_safe(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return destination


def write_product_jsonl(
    payloads: Iterable[Mapping[str, object]],
    path: str | Path,
) -> Path:
    """Write one safe product payload per line for streaming/import workflows."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for payload in payloads:
        row = dict(payload)
        assert_product_payload_safe(row)
        lines.append(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    destination.write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )
    return destination
