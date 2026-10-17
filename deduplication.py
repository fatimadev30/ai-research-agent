"""Deduplication service — removes duplicate records across batches.

Uses normalized dedup keys to identify duplicates. The first occurrence wins.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

WHITESPACE_PATTERN = re.compile(r"\s+")


def compute_dedup_key(fields: dict[str, Any], dedup_keys: list[str]) -> str:
    """Compute a normalized dedup key from the specified field(s)."""
    parts: list[str] = []
    for key in dedup_keys:
        val = fields.get(key)
        if val:
            parts.append(_normalize(str(val)))
    if not parts:
        # Fall back to a hash of all field values.
        all_vals = sorted(str(v) for v in fields.values() if v)
        return hashlib.sha256("|".join(all_vals).encode()).hexdigest()[:16]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def is_duplicate(dedup_key: str, seen_keys: set[str]) -> bool:
    return dedup_key in seen_keys


def _normalize(value: str) -> str:
    """Normalize a value for dedup comparison."""
    return WHITESPACE_PATTERN.sub("", value.strip().lower())


def deduplicate_records(records: list[dict[str, Any]], dedup_keys: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Deduplicate a list of records. Returns (unique_records, duplicates_removed_count)."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    dup_count = 0
    for record in records:
        key = compute_dedup_key(record.get("fields", record), dedup_keys)
        if key in seen:
            dup_count += 1
            continue
        seen.add(key)
        if "fields" in record:
            record["dedup_key"] = key
        else:
            record["_dedup_key"] = key
        unique.append(record)
    return unique, dup_count
