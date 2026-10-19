"""Internal, owner-fenced presentation recovery. No provider reasoning or raw datasets are checkpointed."""
from __future__ import annotations

import contextvars
import json
from dataclasses import dataclass
from typing import Any, Callable

from .model_choices import BY_MODEL

MAX_BYTES = 256 * 1024
VERSION = 1


@dataclass(frozen=True)
class Context:
    request_id: str  # the durable root turn, shared by its Mode4 sub-runs
    write: Callable[[str, dict[str, Any]], bool]


current: contextvars.ContextVar[Context | None] = contextvars.ContextVar("presentation_checkpoint", default=None)
resume: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("presentation_resume", default=None)


def bounded(document: dict[str, Any]) -> bool:
    # PostgreSQL jsonb text adds spaces; keep a margin for its representation and wrapper/step ids.
    try:
        return len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode()) <= MAX_BYTES - 4096
    except (ValueError, TypeError):
        return False


def choices(document: dict[str, Any] | None, request_id: str) -> list[dict[str, Any]]:
    if not isinstance(document, dict) or document.get("version") != VERSION:
        return []
    return [{"presentation_retry_of": request_id, "presentation_retry_step": step,
             "model": item.get("model"), "model_label": BY_MODEL[item["model"]].label
             if item.get("model") in BY_MODEL else item.get("model"), "reasoning_level": item.get("reasoning_level"),
             "scope": "saved_computation"}
            for step, item in (document.get("steps") or {}).items()
            if isinstance(item, dict) and item.get("phase") == "READY_FOR_PRESENTATION"]
