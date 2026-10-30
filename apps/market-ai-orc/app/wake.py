"""EXEC-U4 (user go 2026-10-29): a service that sleeps when idle is woken by the request that needs it.

Railway puts a service with app sleeping to sleep 5-10 minutes after its last outbound traffic and starts it again on
the next request; that first request can fail at the connection (telegram-monitor, 2026-10-27 14:53: the first /notify
failed with URLError, the retry 4 s later passed). WakeTransport wraps a client's transport, so every request of the
client is covered without listing its call sites. A request whose connection is refused never reached the service,
so it is safe to send again, whatever its method: the transport then asks GET /ready until the service answers and
sends the request once more. A GET answered 502 is treated the same way; any other answer is returned as it is, so a
request the service received is never sent twice and the warm path costs nothing."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from . import progress, user_texts

logger = logging.getLogger(__name__)

# Wake-ups seen on telegram-monitor: 0.2-9 s from Starting Container to the server answering. The waits add up to 23 s.
DELAYS = (1.0, 2.0, 4.0, 8.0, 8.0)
PROBE_PATH = "/ready"
NOT_STARTED = (httpx.ConnectError, httpx.ConnectTimeout)
PROBE_TIMEOUT = {"connect": 5.0, "read": 5.0, "write": 5.0, "pool": 5.0}


def pause(seconds: float) -> None:
    time.sleep(seconds)


class WakeTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport, service: str, delays: tuple[float, ...] = DELAYS) -> None:
        self.inner, self.service, self.delays = inner, service, delays

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            response = self.inner.handle_request(request)
        except NOT_STARTED:
            if not self._wake(request):
                raise
            return self.inner.handle_request(request)  # it never reached the service: sent once more
        if response.status_code != 502 or request.method != "GET":
            return response
        response.close()
        self._wake(request)
        return self.inner.handle_request(request)  # a GET, safe to repeat; a 502 that stays is the answer

    def _wake(self, request: httpx.Request) -> bool:
        """GET /ready on the same service until it answers below 500; True when it did within the waits."""
        started, attempts = time.monotonic(), 0
        with progress.step(user_texts.PROGRESS_SERVICES_WAIT) as mark:
            for delay in self.delays:
                pause(delay)
                attempts += 1
                probe = httpx.Request("GET", request.url.copy_with(path=PROBE_PATH, query=None),
                                      extensions={"timeout": PROBE_TIMEOUT})
                try:
                    answer = self.inner.handle_request(probe)
                    answer.close()
                except httpx.HTTPError:
                    continue
                if answer.status_code < 500:
                    self._log("WOKEN", attempts, started, request)
                    return True
            mark("failed")
        self._log("NOT_READY", attempts, started, request)
        return False

    def _log(self, outcome: str, attempts: int, started: float, request: httpx.Request) -> None:
        logger.info(json.dumps({"event": "downstream_wake", "service": self.service, "outcome": outcome,
                                "attempts": attempts, "seconds": round(time.monotonic() - started, 1),
                                "method": request.method, "path": request.url.path}))

    def close(self) -> None:
        self.inner.close()


def transport(service: str, inner: httpx.BaseTransport | None = None, **kwargs: Any) -> WakeTransport:
    """The transport a client of a service that may sleep is built with (its own transport, or the default one)."""
    return WakeTransport(inner if inner is not None else httpx.HTTPTransport(**kwargs), service)
