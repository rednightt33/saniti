from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def dumps(value: Any) -> str:
    return json.dumps(value, default=json_default, ensure_ascii=False, separators=(",", ":"))


def estimate_tokens(value: Any) -> int:
    # Conservative language-agnostic approximation; API usage is authoritative.
    return max(1, (len(dumps(value).encode("utf-8")) + 2) // 3)


def query_hash(statement: str, parameters: list[Any]) -> str:
    payload = dumps({"statement": statement, "parameters": parameters})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compact_result(
    payload: dict[str, Any], *, max_rows: int, max_bytes: int, max_tokens: int
) -> tuple[dict[str, Any], int, bool]:
    """Semantically compact rows; never silently cut arbitrary serialized bytes."""
    result = dict(payload)
    rows = list(result.get("rows") or [])
    result["total_rows"] = int(result.get("total_rows", len(rows)))
    result["returned_rows"] = len(rows)
    if len(rows) > max_rows:
        head_count = max(1, max_rows // 2)
        tail_count = max_rows - head_count
        result["rows"] = rows[:head_count] + rows[-tail_count:] if tail_count else rows[:head_count]
        result["selection"] = {
            "method": "ordered_top_and_bottom",
            "first_rows": head_count,
            "last_rows": tail_count,
            "omitted_rows": len(rows) - max_rows,
        }
    compacted = len(rows) > max_rows

    serialized = dumps(result)
    tokens = estimate_tokens(result)
    if len(serialized.encode("utf-8")) <= max_bytes and tokens <= max_tokens:
        return result, tokens, compacted

    visible = list(result.get("rows") or [])
    numeric_summary: dict[str, dict[str, float]] = {}
    for key in {key for row in rows if isinstance(row, dict) for key in row}:
        values = [float(row[key]) for row in rows if isinstance(row, dict) and isinstance(row.get(key), (int, float, Decimal))]
        if values:
            numeric_summary[key] = {
                "min": min(values), "max": max(values), "mean": sum(values) / len(values),
            }
    compact = {
        key: value for key, value in result.items()
        if key not in {"rows", "selection"}
    }
    compact.update({
        "summary_statistics": numeric_summary,
        "top_observations": visible[:5],
        "bottom_observations": visible[-5:] if len(visible) > 5 else [],
        "selection": {
            "method": "semantic_summary",
            "source_rows": len(rows),
            "reason": "LLM-facing byte/token budget",
        },
    })
    # Drop verbose optional fields in a deterministic order if still oversized.
    for key in ("bottom_observations", "top_observations", "summary_statistics"):
        if len(dumps(compact).encode("utf-8")) <= max_bytes and estimate_tokens(compact) <= max_tokens:
            break
        compact.pop(key, None)
    return compact, estimate_tokens(compact), True
