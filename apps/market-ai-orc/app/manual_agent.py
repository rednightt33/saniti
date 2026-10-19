"""EXEC-MANUAL (user 2026-10-17, "buat nomor satu ya, saklar yang aktif. Ini hanya untuk mode troubleshooting aja ...
Ensure ada jalur fallback"): Claude answers a run's model calls itself, under the same constraints as the model.

A run whose message chose MANUAL_MODEL sends its agent-loop calls here instead of to OpenRouter: each call waits as a
step (the exact payload the model would get) until a reply in the model's response shape is posted, and orc goes on
with that reply as with a model's (the same tools, gates, data approvals and final check). Every other call (the
routers, follow-up suggestions, other models) goes to OpenRouter unchanged.

Fallback: a step with no reply within AI_MANUAL_AGENT_WAIT_SECONDS is sent to AI_MODEL at the server's reasoning
level, and the rest of that run follows it; the stop button ends a wait. Switched off (AI_ENABLE_MANUAL_AGENT), the
model is not offered and nothing comes here. The service runs one replica (railway.ts), so the steps live in memory.
"""
from __future__ import annotations

import copy
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import stop
from .model_choices import MANUAL_OPTION
from .tools.request_data import current_request_id

MANUAL_MODEL = MANUAL_OPTION.model
POLL_SECONDS = 1.0
KEEP_FALLEN = 200  # requests remembered as fallen back (a run's later calls skip the wait)


@dataclass
class Step:
    step_id: str
    request_id: str
    payload: dict[str, Any]
    created_at: float
    done: threading.Event = field(default_factory=threading.Event)
    reply: dict[str, Any] | None = None


class ManualAgent:
    """Wraps the OpenRouter client; everything but a MANUAL_MODEL call passes through to it."""

    def __init__(self, real: Any, settings: Any, *, log: Any = None, clock: Any = time.monotonic,
                 poll_seconds: float = POLL_SECONDS) -> None:
        self.real, self.settings, self.log = real, settings, log or (lambda *a, **k: None)
        self.clock, self.poll_seconds = clock, poll_seconds
        self._lock = threading.Lock()
        self._steps: dict[str, Step] = {}
        self._fallen: list[str] = []

    def __getattr__(self, name: str) -> Any:  # key reads, endpoints, prices: the real client's
        return getattr(self.real, name)

    def create(self, payload: dict[str, Any], *, timeout: float | None = None,
               attempts: int | None = None) -> dict[str, Any]:
        if payload.get("model") != MANUAL_MODEL:
            return self.real.create(payload, timeout=timeout, attempts=attempts)
        request_id = current_request_id.get() or "unknown"
        with self._lock:
            fallen = request_id in self._fallen
        if fallen:
            return self._fallback(payload, request_id, "EARLIER_STEP")
        # a copy: the run keeps adding to its input list, the step shows the call as it was sent
        step = Step(uuid.uuid4().hex[:16], request_id, copy.deepcopy(payload), time.time())
        with self._lock:
            self._steps[step.step_id] = step
        self.log("manual_agent_step_waiting", request_id=request_id, step_id=step.step_id)
        deadline = self.clock() + self.settings.ai_manual_agent_wait_seconds
        try:
            while not step.done.wait(self.poll_seconds):
                if stop.requested():
                    # an empty turn: the loop sees the stop flag before its next call and ends as STOPPED_BY_USER
                    self.log("manual_agent_step_stopped", request_id=request_id, step_id=step.step_id)
                    return {"id": f"manual-{step.step_id}", "model": MANUAL_MODEL, "output": [], "usage": {}}
                if self.clock() >= deadline:
                    with self._lock:
                        self._fallen = (self._fallen + [request_id])[-KEEP_FALLEN:]
                    return self._fallback(payload, request_id, "NO_REPLY")
        finally:
            with self._lock:
                self._steps.pop(step.step_id, None)
        reply = dict(step.reply or {})
        reply.pop("_executor_settings", None)
        reply.setdefault("id", f"manual-{step.step_id}")
        reply.setdefault("model", MANUAL_MODEL)
        reply.setdefault("usage", {})
        self.log("manual_agent_step_answered", request_id=request_id, step_id=step.step_id,
                 seconds=round(time.time() - step.created_at, 1), items=len(reply.get("output") or []))
        return reply

    def _fallback(self, payload: dict[str, Any], request_id: str, reason: str) -> dict[str, Any]:
        """The way back: the same call on AI_MODEL at the server's reasoning level."""
        model = self.settings.ai_model
        self.log("manual_agent_fallback", request_id=request_id, reason=reason, model=model)
        sent = {**payload, "model": model, "reasoning": self.settings.reasoning(self.settings.ai_reasoning_effort)}
        from .openrouter_client import ProviderError
        try:
            reply = self.real.create(sent)
        except ProviderError as exc:
            exc.sent_settings = {"model":model, "reasoning":sent["reasoning"], "fallback_reason":"MANUAL_" + reason}
            raise
        return {**reply, "_executor_settings": {"model": model, "reasoning": sent["reasoning"],
                                                "fallback_reason": "MANUAL_" + reason}}

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            steps = sorted(self._steps.values(), key=lambda s: s.created_at)
        return [{"step_id": s.step_id, "request_id": s.request_id, "created_at": s.created_at,
                 "waited_seconds": round(time.time() - s.created_at, 1), "payload": s.payload} for s in steps]

    def answer(self, step_id: str, reply: Any) -> str:
        """ANSWERED, NOT_WAITING (unknown or already answered or fallen back), or INVALID (not a model response)."""
        if not isinstance(reply, dict) or not isinstance(reply.get("output"), list):
            return "INVALID"
        with self._lock:
            step = self._steps.get(step_id)
            if step is None or step.done.is_set():
                return "NOT_WAITING"
            step.reply = reply
            step.done.set()
        return "ANSWERED"
