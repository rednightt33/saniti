"""Which provider served each model call (AI_LOG_PROVIDER).

The Responses API returns neither the provider name nor its generation speed, and the 2026-09-26 stress test showed
that the provider OpenRouter picks is the largest single factor in run time (one provider served half the calls at a
quarter of the speed of another). After a run, its generation ids are looked up on OpenRouter's /generation endpoint
in a background thread, so the response is never delayed, and each is logged as ai_model_call_provider. OpenRouter
publishes a record a few seconds after the call, so a lookup that is not ready yet is retried with backoff; one that
never becomes ready is logged as not found. A failed lookup changes nothing but the log.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Protocol

from .compaction import dumps

logger = logging.getLogger("market_ai_orc")

RETRY_DELAYS_SECONDS = (5.0, 10.0, 20.0, 40.0)
MAX_CALLS_PER_RUN = 100


class GenerationSource(Protocol):
    def generation(self, generation_id: str) -> dict[str, Any] | None: ...


def provider_fields(record: dict[str, Any]) -> dict[str, Any]:
    """The routing and speed facts of one /generation record; no prompt or output content."""
    generation_ms = record.get("generation_time")
    completion = record.get("native_tokens_completion")
    attempts = [a for a in record.get("provider_responses") or [] if isinstance(a, dict)]
    speed = None
    if isinstance(generation_ms, (int, float)) and generation_ms > 0 and isinstance(completion, (int, float)):
        speed = round(completion / (generation_ms / 1000), 1)
    return {
        "provider": record.get("provider_name"),
        "model_version": record.get("model"),
        "provider_attempts": len(attempts) or None,
        "failed_providers": [a.get("provider_name") for a in attempts if a.get("status") != 200] or None,
        "first_token_ms": record.get("latency"),
        "generation_time_ms": generation_ms,
        "native_output_tokens": completion,
        "native_cached_tokens": record.get("native_tokens_cached"),
        "output_tokens_per_second": speed,
        "finish_reason": record.get("finish_reason"),
        "total_cost": record.get("total_cost"),
    }


class ProviderLogger:
    """Looks up a run's generations after the run, in one background worker."""

    def __init__(self, source: GenerationSource, *, delays: tuple[float, ...] = RETRY_DELAYS_SECONDS,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.source = source
        self.delays = delays
        self.sleep = sleep
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="provider-log")

    def submit(self, request_id: str, calls: list[dict[str, Any]]) -> None:
        calls = [c for c in calls if c.get("provider_response_id")][:MAX_CALLS_PER_RUN]
        if calls:
            self.executor.submit(self.lookup, request_id, calls)

    def lookup(self, request_id: str, calls: list[dict[str, Any]]) -> None:
        pending = list(calls)
        for delay in self.delays:
            self.sleep(delay)
            waiting = []
            for call in pending:
                try:
                    record = self.source.generation(call["provider_response_id"])
                except Exception:  # noqa: BLE001 - logging never fails a run
                    record = None
                if record is None:
                    waiting.append(call)
                    continue
                logger.info(dumps({"event": "ai_model_call_provider", "request_id": request_id, **call,
                                   **provider_fields(record)}))
            pending = waiting
            if not pending:
                return
        for call in pending:
            logger.info(dumps({"event": "ai_model_call_provider", "request_id": request_id, **call,
                               "provider": None, "lookup": "NOT_FOUND"}))

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
