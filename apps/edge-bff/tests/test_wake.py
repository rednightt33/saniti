"""EXEC-U4-WORKERS (user go 2026-11-02): a sleeping worker is woken by the request that needs it (app/wake.py)."""
import asyncio

import httpx
import pytest

from app import wake


class Script(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """Answers from a list: an exception is raised, an int becomes a response with that status."""

    def __init__(self, steps):
        self.steps, self.seen = list(steps), []

    def _next(self, request):
        self.seen.append((request.method, request.url.path))
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return httpx.Response(step, request=request)

    def handle_request(self, request):
        return self._next(request)

    async def handle_async_request(self, request):
        return self._next(request)


REFUSED = httpx.ConnectError('refused')


def sync_client(steps):
    inner = Script(steps)
    return httpx.Client(base_url='http://w', transport=wake.WakeTransport(inner, 'w', delays=(0, 0, 0), sleep=lambda s: None)), inner


def async_client(steps):
    inner = Script(steps)
    async def nap(s):
        return None
    return httpx.AsyncClient(base_url='http://w', transport=wake.AsyncWakeTransport(inner, 'w', delays=(0, 0, 0), sleep=nap)), inner


def test_warm_path_is_one_request():
    c, inner = sync_client([200])
    assert c.post('/v1/run').status_code == 200
    assert inner.seen == [('POST', '/v1/run')]


def test_refused_connection_wakes_then_sends_once_more_whatever_the_method():
    c, inner = sync_client([REFUSED, REFUSED, 200, 201])
    assert c.post('/v1/run').status_code == 201
    assert inner.seen == [('POST', '/v1/run'), ('GET', '/health'), ('GET', '/health'), ('POST', '/v1/run')]


def test_an_answered_request_is_never_repeated():
    c, inner = sync_client([500])
    assert c.post('/v1/run').status_code == 500           # the worker received it: returned as it is
    assert inner.seen == [('POST', '/v1/run')]
    c, inner = sync_client([502])
    assert c.post('/v1/run').status_code == 502           # a POST answered 502 is not sent twice
    assert len(inner.seen) == 1


def test_a_get_answered_502_is_repeated_after_the_wake():
    c, inner = sync_client([502, 200, 200])
    assert c.get('/v1/catalog').status_code == 200
    assert inner.seen == [('GET', '/v1/catalog'), ('GET', '/health'), ('GET', '/v1/catalog')]


def test_a_worker_that_never_answers_raises_the_connection_error():
    c, _ = sync_client([REFUSED, REFUSED, REFUSED, REFUSED])
    with pytest.raises(httpx.ConnectError):
        c.get('/v1/catalog')


def test_async_refused_then_woken():
    async def go():
        c, inner = async_client([REFUSED, 200, 200])
        r = await c.post('/v1/validate')
        return r.status_code, inner.seen
    status, seen = asyncio.run(go())
    assert status == 200 and seen == [('POST', '/v1/validate'), ('GET', '/health'), ('POST', '/v1/validate')]


def test_a_loading_screener_answers_as_it_always_does():
    async def go():
        c, inner = async_client([REFUSED, 503, 503])          # up, still loading its snapshot
        r = await c.get('/v1/catalog')
        return r.status_code, inner.seen
    status, seen = asyncio.run(go())
    assert status == 503 and seen == [('GET', '/v1/catalog'), ('GET', '/health'), ('GET', '/v1/catalog')]


def test_the_edge_bff_clients_use_the_wake_transport():
    from types import SimpleNamespace
    from app.backtest import WorkerClient
    from app.screener import ScreenerWorker
    s = SimpleNamespace(backtest_worker_url='http://backtest-worker.railway.internal:8080', backtest_worker_key='k',
                        screener_worker_url='http://screener-worker.railway.internal:8080')
    assert isinstance(WorkerClient(s).client._transport, wake.WakeTransport)
    assert isinstance(ScreenerWorker(s).connection()._transport, wake.AsyncWakeTransport)
