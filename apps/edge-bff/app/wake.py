"""EXEC-U4-WORKERS (user go 2026-11-02: "Jalankan U4 sekarang"): a worker that sleeps when idle is woken by the request
that needs it. The rule is market-ai-orc's app/wake.py (EXEC-U4, 2026-10-29), for edge-bff's sync and async clients.

Railway puts a service with app sleeping to sleep about 10 minutes after its last outbound traffic and starts it again on
the next request over the private network; that first request can fail at the connection (telegram-monitor,
2026-10-27: URLError, the retry 4 s later passed). A request whose connection was refused never reached the service, so
it is safe to send again whatever its method: the transport asks GET `probe_path` (an unauthenticated route the worker
answers from memory) until any answer comes, then sends the request once more. A GET answered 502 is treated the same
way. Any other answer is returned as it is, so a request the worker received is never sent twice and the warm path costs
nothing. A worker that is up but still loading answers as it always does (screener: 503 SCREENER_NOT_READY)."""
from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)
# uvicorn sets up only its own loggers, so an INFO line here found no handler and was dropped (logging.lastResort writes
# WARNING and up): the downstream_wake lines never reached the log (EXEC-U4-WORKERS live check 2026-11-02). The rule of
# app/backtest.py: a handler to stderr when none is set up at import; a logging set-up made before is left alone.
if not logger.hasHandlers():
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

# Wake-ups seen on telegram-monitor: 0.2-9 s from Starting Container to the server answering; the waits add up to 23 s.
DELAYS = (1.0, 2.0, 4.0, 8.0, 8.0)
NOT_STARTED = (httpx.ConnectError, httpx.ConnectTimeout)
PROBE_TIMEOUT = httpx.Timeout(5.0)


def _probe_request(request: httpx.Request, probe_path: str) -> httpx.Request:
    return httpx.Request('GET', request.url.copy_with(path=probe_path, query=None),
                         extensions={'timeout': PROBE_TIMEOUT.as_dict()})


def _log(service, outcome, attempts, started, request):
    logger.info(json.dumps({'event': 'downstream_wake', 'service': service, 'outcome': outcome, 'attempts': attempts,
                            'seconds': round(time.monotonic() - started, 1), 'method': request.method,
                            'path': request.url.path}))


class WakeTransport(httpx.BaseTransport):
    """The sync transport (backtest WorkerClient.client, the job loop's calls in a thread)."""

    def __init__(self, inner: httpx.BaseTransport, service: str, probe_path: str = '/health',
                 delays: tuple[float, ...] = DELAYS, sleep=time.sleep) -> None:
        self.inner, self.service, self.probe_path, self.delays, self.sleep = inner, service, probe_path, delays, sleep

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            response = self.inner.handle_request(request)
        except NOT_STARTED:
            if not self._wake(request):
                raise
            return self.inner.handle_request(request)          # it never reached the worker: sent once more
        if response.status_code != 502 or request.method != 'GET':
            return response
        response.close()
        self._wake(request)
        return self.inner.handle_request(request)              # a GET, safe to repeat

    def _wake(self, request: httpx.Request) -> bool:
        started = time.monotonic()
        for attempts, delay in enumerate(self.delays, 1):
            self.sleep(delay)
            try:
                answer = self.inner.handle_request(_probe_request(request, self.probe_path))
                answer.close()
            except httpx.HTTPError:
                continue
            if answer.status_code != 502:
                _log(self.service, 'WOKEN', attempts, started, request)
                return True
        _log(self.service, 'NOT_READY', len(self.delays), started, request)
        return False

    def close(self) -> None:
        self.inner.close()


class AsyncWakeTransport(httpx.AsyncBaseTransport):
    """The async transport (screener ScreenerWorker, backtest WorkerClient.relay), awaited on the event loop."""

    def __init__(self, inner: httpx.AsyncBaseTransport, service: str, probe_path: str = '/health',
                 delays: tuple[float, ...] = DELAYS, sleep=asyncio.sleep) -> None:
        self.inner, self.service, self.probe_path, self.delays, self.sleep = inner, service, probe_path, delays, sleep

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            response = await self.inner.handle_async_request(request)
        except NOT_STARTED:
            if not await self._wake(request):
                raise
            return await self.inner.handle_async_request(request)
        if response.status_code != 502 or request.method != 'GET':
            return response
        await response.aclose()
        await self._wake(request)
        return await self.inner.handle_async_request(request)

    async def _wake(self, request: httpx.Request) -> bool:
        started = time.monotonic()
        for attempts, delay in enumerate(self.delays, 1):
            await self.sleep(delay)
            try:
                answer = await self.inner.handle_async_request(_probe_request(request, self.probe_path))
                await answer.aclose()
            except httpx.HTTPError:
                continue
            if answer.status_code != 502:
                _log(self.service, 'WOKEN', attempts, started, request)
                return True
        _log(self.service, 'NOT_READY', len(self.delays), started, request)
        return False

    async def aclose(self) -> None:
        await self.inner.aclose()


def transport(service: str, **kwargs) -> WakeTransport:
    return WakeTransport(httpx.HTTPTransport(**kwargs), service)


def async_transport(service: str, **kwargs) -> AsyncWakeTransport:
    return AsyncWakeTransport(httpx.AsyncHTTPTransport(**kwargs), service)
