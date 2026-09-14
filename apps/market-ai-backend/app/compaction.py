from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


DECISIVE_TOP_LEVEL_KEYS = (
    "table", "columns", "total_rows", "returned_rows", "classification",
    "row_count", "null_counts", "warnings", "anomaly_flags",
    "analysis_ready_date", "query_hash", "selection", "completion_policy",
    "evidence_id", "recorded", "completion_accepted", "next_action",
    "quality_blocks_finalization", "analysis_may_continue",
    "job_id", "job_label", "status", "snapshot_id", "snapshot_sha256",
    "input_rows", "input_bytes", "source_tables", "component_query_hashes",
    "method", "method_version", "result_metadata", "worker_boundary",
    "error_class", "error_message",
)


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
    # Preserve at least the first and last decisive observations. Shrink counts
    # and statistics before removing evidence-bearing rows.
    while (
        len(dumps(compact).encode("utf-8")) > max_bytes
        or estimate_tokens(compact) > max_tokens
    ) and (
        len(compact.get("top_observations") or []) > 1
        or len(compact.get("bottom_observations") or []) > 1
    ):
        top = compact.get("top_observations") or []
        bottom = compact.get("bottom_observations") or []
        if len(bottom) >= len(top) and len(bottom) > 1:
            compact["bottom_observations"] = bottom[:-1]
        elif len(top) > 1:
            compact["top_observations"] = top[:-1]
    if len(dumps(compact).encode("utf-8")) > max_bytes or estimate_tokens(compact) > max_tokens:
        compact.pop("summary_statistics", None)
    if len(dumps(compact).encode("utf-8")) > max_bytes or estimate_tokens(compact) > max_tokens:
        compact = {
            key: compact[key]
            for key in DECISIVE_TOP_LEVEL_KEYS
            if key in compact
        } | {
            "top_observations": (compact.get("top_observations") or [])[:1],
            "bottom_observations": (compact.get("bottom_observations") or [])[-1:],
            "selection": {
                "method": "decisive_minimum",
                "source_rows": len(rows),
                "reason": "LLM-facing byte/token budget",
            },
        }
    return compact, estimate_tokens(compact), True


def decisive_digest(
    tool_name: str, payload: dict[str, Any], query_digest: str | None = None
) -> dict[str, Any]:
    """Build the durable/context digest without discarding decisive values."""
    digest: dict[str, Any] = {"tool": tool_name}
    effective_hash = query_digest or payload.get("query_hash")
    if isinstance(effective_hash, list):
        digest["query_hashes"] = [str(item) for item in effective_hash if item]
    elif effective_hash:
        digest["query_hash"] = str(effective_hash)
    for key in DECISIVE_TOP_LEVEL_KEYS:
        if key in payload and key != "query_hash":
            digest[key] = payload[key]

    rows = list(payload.get("rows") or [])
    top = list(payload.get("top_observations") or [])
    bottom = list(payload.get("bottom_observations") or [])
    if rows:
        if len(rows) <= 10:
            digest["decisive_observations"] = rows
        else:
            digest["top_observations"] = rows[:5]
            digest["bottom_observations"] = rows[-5:]
    else:
        if top:
            digest["top_observations"] = top[:5]
        if bottom:
            digest["bottom_observations"] = bottom[-5:]
    if payload.get("summary_statistics"):
        digest["summary_statistics"] = payload["summary_statistics"]
    return digest
