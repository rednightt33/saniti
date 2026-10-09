"""The stop button (user decision 2026-10-09: "kita jg perlu tambah stop button, which fungsinya kaya stop ai
processing"; EXEC.md EXEC-X).

A run registers under its request id while it runs; POST /v1/agent/run/{request_id}/stop sets its flag. The flag is
read where the run already stops for its time limit (the start of each step of the loop, and before each mode 4 step),
so no new paid model call starts after it; the call in flight finishes. The run then ends like a run whose time ran
out: its last draft goes through every gate and reaches the user as a limitation, or a plain "stopped" line. The
service runs one replica (railway.ts), so the registry lives in memory.
"""
from __future__ import annotations

import contextvars
import threading
from typing import Any

_lock = threading.Lock()
_running: dict[str, tuple[str | None, threading.Event]] = {}
current_stop: contextvars.ContextVar[threading.Event | None] = contextvars.ContextVar("current_stop", default=None)


class running:
    """`with running(request_id, owner):` registers the run and makes its flag the current one."""

    def __init__(self, request_id: str, owner: str | None) -> None:
        self.request_id, self.owner, self.token = request_id, owner, None

    def __enter__(self) -> threading.Event:
        event = threading.Event()
        with _lock:
            _running[self.request_id] = (self.owner, event)
        self.token = current_stop.set(event)
        return event

    def __exit__(self, *_: Any) -> None:
        current_stop.reset(self.token)
        with _lock:
            _running.pop(self.request_id, None)


def stop(request_id: str, owner: str | None) -> str:
    """STOPPING, or NOT_RUNNING (unknown, finished, or another owner's run: never told apart, so no run is revealed)."""
    with _lock:
        found = _running.get(request_id)
    if found is None or (found[0] is not None and found[0] != owner):
        return "NOT_RUNNING"
    found[1].set()
    return "STOPPING"


def requested() -> bool:
    event = current_stop.get()
    return bool(event is not None and event.is_set())
