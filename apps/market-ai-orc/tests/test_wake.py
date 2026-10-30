"""EXEC-U4 (user go 2026-10-29): the sandbox sleeps when idle. A request whose connection is refused never reached it,
so orc's transport wakes it (GET /ready until it answers) and sends that request once more; a GET answered 502 is
treated the same way. Any other answer is returned as it is: a request the service received is never sent twice, and
a service that answers costs no extra request."""
from __future__ import annotations

import json

import httpx
import pytest

from app import wake
from app.tools.analysis import SandboxClient
from app.tools.registry import ToolError
from app.tools.web_research import WebResearchClient


def sandbox(down: int, failure: str = "connect") -> tuple[SandboxClient, list[str]]:
    """A sandbox asleep for its first `down` requests (a refused connection, or a 502 from the platform)."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if len(seen) <= down:
            if failure == "connect":
                raise httpx.ConnectError("connection refused", request=request)
            return httpx.Response(502)
        if request.url.path == "/ready":
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(200, json={"status": "OK"})
    return SandboxClient("http://sandbox.internal", "k", 30, 5, transport=httpx.MockTransport(handler)), seen


def test_a_refused_post_wakes_the_sandbox_and_is_sent_once_more(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr(wake, "pause", waits.append)
    client, seen = sandbox(down=3)
    assert client._call("POST", "/v1/sessions/s/execute", json={"code": "x"}).status_code == 200
    # the refused POST, two refused probes, the probe that answers, the POST again (it never reached the service)
    assert seen == ["POST /v1/sessions/s/execute", "GET /ready", "GET /ready", "GET /ready",
                    "POST /v1/sessions/s/execute"]
    assert waits == [1.0, 2.0, 4.0]


def test_a_get_answered_502_by_the_platform_is_asked_again_after_the_wake() -> None:
    client, seen = sandbox(down=1, failure="502")
    assert client.ready() is True
    assert seen == ["GET /ready", "GET /ready", "GET /ready"]


def test_a_post_answered_502_is_never_sent_twice() -> None:
    client, seen = sandbox(down=1, failure="502")
    # the service may have received it: the 502 is the answer (the tool reports the sandbox unavailable)
    assert client._call("POST", "/v1/specs", json={}).status_code == 502
    assert seen == ["POST /v1/specs"]


def test_an_awake_sandbox_gets_no_extra_request() -> None:
    client, seen = sandbox(down=0)
    client._call("GET", "/v1/runtime")
    client._call("POST", "/v1/specs", json={})
    assert seen == ["GET /v1/runtime", "POST /v1/specs"]


def test_a_sandbox_that_stays_down_is_the_same_named_error_as_before(caplog: pytest.LogCaptureFixture) -> None:
    client, seen = sandbox(down=99)
    with caplog.at_level("INFO", logger="app.wake"), pytest.raises(ToolError, match="sandbox is unreachable"):
        client._call("POST", "/v1/specs", json={})
    assert seen.count("POST /v1/specs") == 1 and seen.count("GET /ready") == len(wake.DELAYS)
    logged = [json.loads(r.message) for r in caplog.records if r.name == "app.wake"]
    assert logged == [{"event": "downstream_wake", "service": "Python sandbox", "outcome": "NOT_READY",
                       "attempts": len(wake.DELAYS), "seconds": logged[0]["seconds"], "method": "POST",
                       "path": "/v1/specs"}]


def test_the_web_governor_client_is_woken_the_same_way() -> None:
    """A second client of the same transport (the web governor stays on today; the transport costs nothing awake)."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if len(seen) == 1:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={"status": "OK"})
    client = WebResearchClient("http://web.internal", "k", transport=httpx.MockTransport(handler))
    assert client.research({"q": 1}) == {"status": "OK"}
    assert seen == ["/v1/orc/web", "/ready", "/v1/orc/web"]
