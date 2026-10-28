"""Deterministic merge for checkpointed workflow records."""

from typing import Any


def merge_records(
    existing: list[dict[str, Any]], updates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in [*existing, *updates]:
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("record requires a nonempty string id")
        if record_id in merged and merged[record_id] != record:
            raise ValueError(f"conflicting record id: {record_id}")
        merged[record_id] = record
    return list(merged.values())
