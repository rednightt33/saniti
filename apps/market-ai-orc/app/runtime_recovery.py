"""One-time, request-driven initialization after a dependency missed startup.

The HTTP app stays available to its durable BFF queue. No model may run against a
partially negotiated registry. Only a complete runtime is published; there is no
mutation of tools or callbacks of an in-flight agent.
"""
from __future__ import annotations

import threading
import time
import logging
from collections.abc import Callable
from typing import Any

from . import progress, user_texts

logger = logging.getLogger("market_ai_orc")


class RuntimeRecovery:
    def __init__(self, build: Callable, sandbox: Any, *, initial: Any = None,
                 clock: Callable[[], float] = time.monotonic, retry_seconds: float = 5.0) -> None:
        self.build, self.sandbox, self.value = build, sandbox, initial
        self.clock, self.retry_seconds, self.retry_at = clock, retry_seconds, 0.0
        self.lock = threading.Lock()

    def get(self) -> Any:
        if self.value is not None:
            return self.value
        # Concurrent submissions do not start duplicate factories or wait behind an
        # unbounded lock. The existing BFF reconciles and retries the same request ID.
        if not self.lock.acquire(blocking=False):
            return None
        try:
            if self.value is not None:
                return self.value
            if self.clock() < self.retry_at:
                return None
            with progress.step(user_texts.PROGRESS_SERVICES_WAIT) as mark:
                self.retry_at = self.clock() + self.retry_seconds
                if self.sandbox is not None:
                    if not self.sandbox.ready():
                        logger.warning('{"event":"sandbox_runtime_waiting","reason":"not_ready"}')
                        mark("failed")
                        return None
                    snapshot = self.sandbox.runtime()
                    if not (isinstance(snapshot, dict) and isinstance(snapshot.get("versions"), dict)
                            and isinstance(snapshot.get("isolation"), dict)
                            and snapshot["isolation"].get("isolation_enforced") is True):
                        logger.warning('{"event":"sandbox_runtime_waiting","reason":"invalid_runtime"}')
                        mark("failed")
                        return None
                    # Cache only a successful handshake. Every startup feature and
                    # callback reads this same snapshot, never a transient {}.
                    self.sandbox.runtime_snapshot = snapshot
                self.value = self.build(self.sandbox)
                logger.info('{"event":"sandbox_runtime_initialized"}')
                return self.value
        finally:
            self.lock.release()
