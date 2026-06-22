"""Structure detector — JSON, CSV, key=value, table, YAML-like detection.

Ported from neural-memory v4.58.0 extraction/structure_detector.py.
Detects structured content patterns for better entity extraction.
"""

from __future__ import annotations

__all__ = ["StructuredContent", "detect_structure"]
import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class StructuredContent:
    format: str
    fields: list[dict[str, Any]]
    row_count: int
    preview: str


def detect_structure(content: str) -> StructuredContent | None:
    """Detect structured content format.

    Returns StructuredContent or None if no structure detected.
    """
    if not content or len(content) < 10:
        return None
    # JSON object
    result = _detect_json_object(content)
    if result: return result
    # Key=value pairs
    result = _detect_key_value(content)
    if result: return result
    # Table rows
    result = _detect_table_row(content)
    if result: return result
    # CSV-like
    result = _detect_csv_row(content)
    if result: return result
    return None


def _detect_json_object(content: str) -> StructuredContent | None:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            fields = [{"name": k, "type": _detect_field_type(str(v)), "sample": str(v)[:50]} for k, v in list(parsed.items())[:20]]
            return StructuredContent("json", fields, 1, content[:100])
        elif isinstance(parsed, list) and len(parsed) > 0:
            item = parsed[0] if isinstance(parsed[0], dict) else {}
            fields = [{"name": k, "type": _detect_field_type(str(v)), "sample": str(v)[:50]} for k, v in list(item.items())[:20]]
            return StructuredContent("json_array", fields, len(parsed), content[:100])
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _detect_key_value(content: str) -> StructuredContent | None:
    lines = content.strip().split("\n")
    kvs = []
    for line in lines[:30]:
        line = line.strip()
        m = re.match(r'^["\']?(\w+(?:[_\s]\w+)*)["\']?\s*[:=]\s*(.+)$', line)
        if m:
            kvs.append({"name": m.group(1).strip(), "value": m.group(2).strip()[:50]})
    if len(kvs) >= 3:
        return StructuredContent("key_value", kvs, len(kvs), content[:100])
    return None


def _detect_table_row(content: str) -> StructuredContent | None:
    lines = [l.strip() for l in content.strip().split("\n") if l.strip()]
    if len(lines) < 3:
        return None
    # Check for pipe-delimited table
    if lines[0].startswith("|") and "|" in lines[0]:
        headers = [h.strip() for h in lines[0].strip("|").split("|")]
        data_rows = [l for l in lines[2:] if l.startswith("|")][:10]
        fields = [{"name": h, "type": "string"} for h in headers[:10]]
        return StructuredContent("table", fields, len(data_rows), content[:100])
    return None


def _detect_csv_row(content: str) -> StructuredContent | None:
    lines = [l.strip() for l in content.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return None
    # Check for comma-separated
    cols = lines[0].split(",")
    if len(cols) >= 3 and len(lines) >= 2:
        fields = [{"name": c.strip(), "type": "string"} for c in cols[:10]]
        return StructuredContent("csv", fields, len(lines) - 1, content[:100])
    return None


def _detect_field_type(value: str) -> str:
    if value in ("true", "false", "True", "False"):
        return "boolean"
    try:
        int(value)
        return "integer"
    except ValueError:
        pass
    try:
        float(value)
        return "float"
    except ValueError:
        pass
    if value.startswith("[") and value.endswith("]"):
        return "array"
    if value.startswith("{") and value.endswith("}"):
        return "object"
    if value.startswith("20") and len(value) >= 8:
        return "date"
    return "string"