"""Stable identifiers and canonical digest helpers."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


def compact_timestamp(dt: datetime | None = None) -> str:
    """Return an ID-safe UTC timestamp."""
    value = dt or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def new_run_id() -> str:
    """Create a readable, collision-resistant run id."""
    return f"run-{compact_timestamp()}-{secrets.token_hex(4)}"


def safe_path_segment(value: str) -> str:
    """Convert an arbitrary id into a safe relative path segment."""
    safe = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value).strip("-.")
    return safe or "unknown"


def canonical_data(value: Any) -> Any:
    """Convert models and containers into JSON-canonical data."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=False)
    if isinstance(value, dict):
        return {str(k): canonical_data(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [canonical_data(v) for v in value]
    if isinstance(value, tuple):
        return [canonical_data(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    """Serialize using stable JSON rules for hashing and fixtures."""
    return json.dumps(canonical_data(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    """Hash text as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Hash bytes."""
    return hashlib.sha256(data).hexdigest()


def looks_binary(data: bytes) -> bool:
    """Return True if *data* should be treated as binary (a NUL byte anywhere).

    Single source of truth for the binary heuristic so the adapter (which
    decides whether to skip text redaction) and the artifact store (which
    decides media type and the ``redacted`` flag) classify the same bytes
    identically. The whole buffer is scanned — a prefix-only check could
    misclassify a binary file as text and attempt (or claim) text redaction on
    it (#12).
    """
    return b"\x00" in data


def canonical_digest(value: Any) -> str:
    """Hash canonical JSON data."""
    return sha256_text(canonical_json(value))
