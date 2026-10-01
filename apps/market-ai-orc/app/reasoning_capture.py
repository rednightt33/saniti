"""AI_CAPTURE_REASONING (user decision 2026-10-01, dev only): log what the model thought on each call.

Run time is 60% model time and most of it is reasoning (m01 2026-10-01: about 100k output tokens, one 47 s call with
11,947 reasoning tokens), but the run kept only the token count, so a bottleneck could not be read. With the switch on,
the reasoning text OpenRouter returns for a call is written to the service log as ai_model_reasoning events, in parts
of PART_CHARS characters (a Railway log line stays readable), at most MAX_CHARS per call.

Where it goes, and where it never goes:
- the service log only. The audit outbox and market-audit-store keep refusing reasoning (audit_outbox.FORBIDDEN,
  market-audit-store models.FORBIDDEN_KEYS): the durable store stays reasoning-free, and the log follows Railway's
  log retention;
- never back to the model: provider reasoning items are not replayed (orchestrator, as before).

The switch is off by default and meant for dev measurement runs. Turning it on changes no request sent to the
provider, so run behaviour and timing are unchanged except for the log lines.
"""
from __future__ import annotations

from typing import Any, Callable

PART_CHARS = 4000
MAX_CHARS = 200_000


def reasoning_text(response: dict[str, Any]) -> tuple[str, str]:
    """The reasoning text of one provider response and its form: TEXT (full reasoning), SUMMARY (only a summary was
    returned), ENCRYPTED (reasoning exists but is not readable) or NONE."""
    texts: list[str] = []
    summaries: list[str] = []
    encrypted = False
    for item in response.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "reasoning":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                texts.append(part["text"])
        for part in item.get("summary") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                summaries.append(part["text"])
            elif isinstance(part, str):
                summaries.append(part)
        encrypted = encrypted or bool(item.get("encrypted_content"))
    for choice in response.get("choices") or []:  # Chat Completions shape
        message = choice.get("message") if isinstance(choice, dict) else None
        if isinstance(message, dict) and isinstance(message.get("reasoning"), str):
            texts.append(message["reasoning"])
    if any(t.strip() for t in texts):
        return "\n".join(texts), "TEXT"
    if any(s.strip() for s in summaries):
        return "\n".join(summaries), "SUMMARY"
    return "", "ENCRYPTED" if encrypted else "NONE"


def log_reasoning(log: Callable[..., None], response: dict[str, Any], *, request_id: str, iteration: int,
                  tools_requested: list[str], reasoning_tokens: int) -> None:
    """Write one call's reasoning as ai_model_reasoning events (part 1..parts). A call without readable reasoning
    still gets one event with its form, so a missing text is visible, not silent."""
    text, form = reasoning_text(response)
    total = len(text)
    kept = text[:MAX_CHARS]
    pieces = [kept[i:i + PART_CHARS] for i in range(0, len(kept), PART_CHARS)] or [""]
    for number, piece in enumerate(pieces, 1):
        log("ai_model_reasoning", request_id=request_id, iteration=iteration, form=form, part=number,
            parts=len(pieces), chars=total, truncated=total > MAX_CHARS, reasoning_tokens=reasoning_tokens,
            tools_requested=tools_requested, text=piece)
