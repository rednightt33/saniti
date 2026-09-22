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
    # Conservative language-agnostic approximation; provider usage is authoritative.
    return max(1, (len(dumps(value).encode("utf-8")) + 2) // 3)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, default=json_default, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def trim_history(history: list[dict[str, str]], max_tokens: int) -> tuple[list[dict[str, str]], int]:
    """Keep the newest whole turns that fit the budget; never cut a turn mid-text."""
    kept: list[dict[str, str]] = []
    used = 0
    for turn in reversed(history):
        cost = estimate_tokens(turn)
        if used + cost > max_tokens:
            break
        kept.append(turn)
        used += cost
    kept.reverse()
    return kept, len(history) - len(kept)
