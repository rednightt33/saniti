"""Run progress for EDGE (EXEC-IMPL-1016 Fase 4.3, UI-1015B; user 2026-10-15 go "Next lanjutkan").

A run registers under its request id while it runs, like the stop button (app/stop.py), and records each step as it
starts and ends: understanding the question (the routers), each model call, each tool call. GET
/v1/agent/requests/{request_id}/progress returns the steps in plain words (app/user_texts.py), so EDGE shows what the
run is doing while it runs. Labels only, never arguments, values or model text. A finished run stays readable for
KEEP_SECONDS, so the last poll sees its last step. The service runs one replica (railway.ts): the registry lives in
memory, and a restart loses only the progress, never the run's answer.
"""
from __future__ import annotations

import contextvars
import threading
import time
from typing import Any

from . import user_texts

KEEP_SECONDS = 600.0
MAX_RUNS = 200
MAX_STEPS = 60  # the newest steps of a long run; the count of earlier ones is reported

_lock = threading.Lock()
_runs: dict[str, "Run"] = {}
current_run: contextvars.ContextVar["Run | None"] = contextvars.ContextVar("current_progress", default=None)


class Run:
    def __init__(self, owner: str | None) -> None:
        self.owner, self.started, self.finished = owner, time.monotonic(), None
        self.steps: list[dict[str, Any]] = []
        self.dropped = 0

    def begin(self, label: str) -> dict[str, Any]:
        step = {"label": label, "state": "running", "started": time.monotonic(), "ended": None}
        with _lock:
            self.steps.append(step)
            if len(self.steps) > MAX_STEPS:
                self.dropped += len(self.steps) - MAX_STEPS
                del self.steps[:len(self.steps) - MAX_STEPS]
        return step

    def view(self) -> dict[str, Any]:
        now = time.monotonic()
        with _lock:
            steps = [{"label": s["label"], "state": s["state"],
                      "started_ms": int((s["started"] - self.started) * 1000),
                      "duration_ms": int(((s["ended"] or now) - s["started"]) * 1000)} for s in self.steps]
        return {"status": "FINISHED" if self.finished else "RUNNING",
                "elapsed_ms": int(((self.finished or now) - self.started) * 1000),
                "steps": steps, "earlier_steps": self.dropped}


class tracking:
    """`with tracking(request_id, owner):` registers the run and makes it the current one."""

    def __init__(self, request_id: str, owner: str | None) -> None:
        self.request_id, self.owner, self.token = request_id, owner, None

    def __enter__(self) -> Run:
        run = Run(self.owner)
        now = time.monotonic()
        with _lock:
            for key in [k for k, r in _runs.items() if r.finished and now - r.finished > KEEP_SECONDS]:
                _runs.pop(key, None)
            while len(_runs) >= MAX_RUNS:
                _runs.pop(next(iter(_runs)))
            _runs[self.request_id] = run
        self.token = current_run.set(run)
        return run

    def __exit__(self, *_: Any) -> None:
        run = current_run.get()
        current_run.reset(self.token)
        if run is not None:
            with _lock:
                for step in run.steps:
                    if step["state"] == "running":
                        step.update(state="done", ended=time.monotonic())
            run.finished = time.monotonic()


class step:
    """`with step(label) as done:` records one step of the current run (nothing when no run is tracked); call
    done("refused") or done("failed") to end it otherwise than done."""

    def __init__(self, label: str) -> None:
        self.label, self.record, self.outcome = label, None, "done"

    def __enter__(self):
        run = current_run.get()
        if run is not None:
            self.record = run.begin(self.label)
        return self.mark

    def mark(self, outcome: str) -> None:
        self.outcome = outcome

    def __exit__(self, kind: Any, *_: Any) -> None:
        if self.record is not None:
            with _lock:
                self.record.update(state="failed" if kind is not None else self.outcome, ended=time.monotonic())


def snapshot(request_id: str, owner: str | None) -> dict[str, Any] | None:
    """The run's progress, or None (unknown, expired, or another owner's run: never told apart)."""
    with _lock:
        run = _runs.get(request_id)
    if run is None or (run.owner is not None and run.owner != owner):
        return None
    return run.view()


def tool_label(name: str, effect: str | None) -> str:
    """A tool's step in plain words: its own label when user_texts names it, else the label of what it does."""
    return user_texts.HURDLE_STEPS.get(name) or user_texts.PROGRESS_EFFECTS.get(str(effect or ""),
                                                                                user_texts.HURDLE_TOOL_STEP)
