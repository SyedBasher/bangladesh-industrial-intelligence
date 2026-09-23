from __future__ import annotations

import hashlib


def sha256_text(value: str) -> str:
    """Return a stable SHA-256 hex digest for UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
