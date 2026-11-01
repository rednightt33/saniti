"""M308: a key the account refuses (401/402) is told apart from a refused request, logged with its HTTP status, found
by the key check before a reader meets it, and a lookup in which no search could run says UNAVAILABLE, not
NOT_FOUND (research_web and find_web_fact alike)."""
from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.config import Settings
from app.fact import FactRequest, FactService
from app.orc_web import OrcWebRequest, OrcWebService
from app.provider import KeyMonitor, OpenRouterProvider, ProviderError, search_unavailable
from conftest import API_KEY, make_settings

SECRET = "sk-or-test-secret-0123456789"


def settings(tmp_path, **env) -> Settings:
    return Settings.from_env({"WEB_GOVERNOR_API_KEY": API_KEY, "OPENROUTER_API_KEY": SECRET,
                              "WEB_GOVERNOR_STORE_PATH": str(tmp_path / "s.db"), "WEB_OPENROUTER_MODEL": "test/model",
                              **env})


def provider_answering(tmp_path, status: int, body: dict) -> tuple[OpenRouterProvider, list]:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(status, request=request, json=body)

    return OpenRouterProvider(settings(tmp_path), client=httpx.Client(transport=httpx.MockTransport(handler))), calls


@pytest.fixture()
def events(caplog):
    """The service logger's records, whether or not the app has already set it not to propagate."""
    logger = logging.getLogger("market_web_governor")
    propagate, level = logger.propagate, logger.level
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(caplog.handler)
    yield lambda: [json.loads(r.getMessage()) for r in caplog.records if r.getMessage().startswith("{")]
    logger.removeHandler(caplog.handler)
    logger.propagate, logger.level = propagate, level


@pytest.mark.parametrize("status", [401, 402])
def test_an_account_refusal_has_its_own_code_is_not_retried_and_is_logged(tmp_path, events, status) -> None:
    provider, calls = provider_answering(tmp_path, status, {"error": {"message": f"Key limit exceeded {SECRET}"}})
    with pytest.raises(ProviderError) as refused:
        provider.respond({"model": "test/model", "input": "x"})
    assert refused.value.code == "PROVIDER_ACCOUNT_BLOCKED" and refused.value.status_code == status
    assert len(calls) == 1
    logged = [e for e in events() if e["event"] == "web_provider_refused"]
    assert logged == [{"event": "web_provider_refused", "code": "PROVIDER_ACCOUNT_BLOCKED", "status_code": status,
                       "retriable": False, "reason": "Key limit exceeded <key>"}]


def test_a_refused_request_keeps_its_code(tmp_path) -> None:
    """Not applicable to the account rule: a 400 is about this request; other requests may pass."""
    provider, _ = provider_answering(tmp_path, 400, {"error": {"message": "bad tool"}})
    with pytest.raises(ProviderError) as refused:
        provider.respond({"model": "test/model", "input": "x"})
    assert refused.value.code == "PROVIDER_REJECTED"


class Refusing:
    """Every Responses call refused the way the stale key was (M308)."""

    def __init__(self, code="PROVIDER_ACCOUNT_BLOCKED", status=402):
        self.code, self.status = code, status

    def respond(self, payload, attempts=None):
        raise ProviderError(self.code, f"OpenRouter returned HTTP {self.status}", status_code=self.status)

    def close(self):
        pass


class Empty:
    """Every search answers, with no result."""

    def respond(self, payload, attempts=None):
        return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "OK", "annotations": []}]}],
                "usage": {"cost": 0.001}}

    def close(self):
        pass


def web_request() -> OrcWebRequest:
    return OrcWebRequest(request_id="r1", budget_key="turn-1", need="agenda ekonomi minggu depan", purpose="CITE")


def test_research_web_with_no_search_run_is_unavailable(tmp_path) -> None:
    result = OrcWebService(settings(tmp_path), Refusing()).answer(web_request())
    assert result["status"] == "UNAVAILABLE"
    assert {"code": "SEARCH_FAILED", "message": "PROVIDER_ACCOUNT_BLOCKED HTTP 402"} in result["warnings"]


def test_research_web_whose_searches_ran_and_found_nothing_stays_not_found(tmp_path) -> None:
    assert OrcWebService(settings(tmp_path), Empty()).answer(web_request())["status"] == "NOT_FOUND"


def test_find_web_fact_with_no_search_run_is_unavailable(tmp_path) -> None:
    """The same mechanism on the other web lookup (an outage after every retry, not the key)."""
    service = FactService(make_settings(str(tmp_path / "s.db")), Refusing("PROVIDER_UNREACHABLE", None))
    result = service.fact(FactRequest(request_id="r1", subject="BI", attribute="BI-Rate terakhir"))
    assert result["status"] == "UNAVAILABLE"


def test_a_search_that_answered_is_never_unavailable() -> None:
    failed = [{"code": "SEARCH_FAILED", "message": "PROVIDER_ACCOUNT_BLOCKED HTTP 402"}]
    assert search_unavailable(failed, 0) and not search_unavailable(failed, 1)
    assert not search_unavailable([{"code": "SEARCH_FAILED", "message": "ValueError"}], 0)


@pytest.mark.parametrize("status, data, state, event", [
    (200, {"limit": 10, "limit_remaining": 7.5}, "OK", "web_provider_credit"),
    (200, {"limit": 10, "limit_remaining": 1.0}, "LOW", "web_provider_credit"),
    (200, {"limit": 41, "limit_remaining": 0}, "INVALID", "web_provider_key_invalid"),
    (401, {}, "INVALID", "web_provider_key_invalid"),
    (503, {}, "UNKNOWN", "web_provider_key_unknown"),
])
def test_the_key_check_names_a_stale_or_spent_key(tmp_path, events, status, data, state, event) -> None:
    provider, calls = provider_answering(tmp_path, status, {"data": data} if data else {"error": {}})
    assert KeyMonitor(provider, 900, 2).check() == state
    assert calls == ["/api/v1/key"]
    logged = [e for e in events() if e["event"].startswith("web_provider_")]
    assert [e["event"] for e in logged] == [event] and logged[0]["status_code"] == status
    assert SECRET not in json.dumps(logged)
