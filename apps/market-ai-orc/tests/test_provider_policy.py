"""Provider exclusion derived from OpenRouter endpoint pricing (AI_PROVIDER_MAX_CACHE_PRICE_RATIO, 2026-10-04)."""
from __future__ import annotations

import httpx
import pytest

from app.config import ConfigError
from app.openrouter_client import OpenRouterClient
from app.provider_policy import CachePricePolicy, cache_price_ratio, excluded_providers
from conftest import ANSWER, final_response, make_settings
from test_orchestrator import orchestrator, request


def endpoint(tag: str, prompt: str, cache: str | None) -> dict:
    pricing = {"prompt": prompt, "completion": "0.00000028"}
    if cache is not None:
        pricing["input_cache_read"] = cache
    return {"tag": tag, "provider_name": tag.split("/")[0], "pricing": pricing}


# The 2026-10-04 endpoints of xiaomi/mimo-v2.6-flash (abridged): one provider barely discounts cache reads.
MIMO = [endpoint("inference-net/fp8", "0.000000115", "0.00000011"),
        endpoint("io-net/fp8", "0.000000118", "0.0000000025"),
        endpoint("xiaomi/fp8", "0.00000014", "0.0000000028")]
# deepseek/deepseek-v4.1-flash (abridged): a second model with a different set of such providers.
DEEPSEEK = [endpoint("relace", "0.0000002", "0.0000002"), endpoint("wafer", "0.0000001", "0.000000096"),
            endpoint("inference-net", "0.0000002", "0.0000001"), endpoint("deepseek", "0.00000015", "0.000000003")]


class Source:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def model_endpoints(self, model: str):
        self.calls += 1
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_ratio_is_derived_from_published_prices() -> None:
    assert cache_price_ratio(MIMO[0]) == pytest.approx(0.957, abs=0.001)
    assert cache_price_ratio(MIMO[1]) == pytest.approx(0.021, abs=0.001)
    assert cache_price_ratio(endpoint("x", "0.0000001", None)) == 1.0  # no cache price: no discount
    assert cache_price_ratio(endpoint("x", "0", "0")) is None  # nothing to compare


def test_each_model_gets_its_own_list_from_its_own_endpoints() -> None:
    assert excluded_providers(MIMO, 0.25)[0] == ["inference-net"]
    assert excluded_providers(DEEPSEEK, 0.25)[0] == ["inference-net", "relace", "wafer"]
    # a looser threshold keeps the provider at a 50% discount
    assert excluded_providers(DEEPSEEK, 0.5)[0] == ["relace", "wafer"]


def test_a_provider_is_kept_while_any_of_its_endpoints_qualifies() -> None:
    endpoints = [endpoint("fireworks", "0.0000002", "0.0000002"), endpoint("fireworks/us", "0.0000002", "0.000000004"),
                 endpoint("deepinfra/fp8", "0.0000002", "0.000000004")]
    assert excluded_providers(endpoints, 0.25)[0] == []


def test_nothing_is_ignored_when_every_endpoint_would_be(caplog=None) -> None:
    ignored, ratios, all_excluded = excluded_providers([endpoint("a", "0.0000001", None),
                                                        endpoint("b", "0.0000001", "0.0000001")], 0.25)
    assert ignored == [] and all_excluded and set(ratios) == {"a", "b"}


def test_policy_refreshes_after_its_ttl_and_keeps_the_last_list_on_failure() -> None:
    now = [0.0]
    events = []
    source = Source(MIMO, RuntimeError("down"), DEEPSEEK)
    policy = CachePricePolicy(source, "m", 0.25, ttl_seconds=60, clock=lambda: now[0],
                              log=lambda event, **fields: events.append(fields))
    assert policy.ignored() == []  # before the first read: OpenRouter's default routing
    policy.refresh()
    assert policy.ignored() == ["inference-net"]
    now[0] = 30.0
    policy.ignored()
    assert source.calls == 1  # fresh: no re-read
    policy.refresh()  # the metadata is unavailable
    assert policy.ignored() == ["inference-net"] and events[-1]["status"] == "METADATA_UNAVAILABLE"
    policy.refresh()
    assert policy.ignored() == ["inference-net", "relace", "wafer"] and events[-1]["changed"]


def test_a_stale_list_starts_one_background_refresh(monkeypatch) -> None:
    now = [0.0]
    started = []
    policy = CachePricePolicy(Source(MIMO), "m", 0.25, ttl_seconds=60, clock=lambda: now[0])
    policy.refresh()
    monkeypatch.setattr(policy, "_start_refresh", lambda: started.append(1))
    now[0] = 61.0
    assert policy.ignored() == ["inference-net"]  # the stale list is used, never blocking the call
    assert started == [1]


def test_setting_is_off_by_default_and_validated() -> None:
    assert make_settings().ai_provider_max_cache_price_ratio is None
    assert make_settings(AI_PROVIDER_MAX_CACHE_PRICE_RATIO="0.25").ai_provider_max_cache_price_ratio == 0.25
    with pytest.raises(ConfigError, match="AI_PROVIDER_MAX_CACHE_PRICE_RATIO"):
        make_settings(AI_PROVIDER_MAX_CACHE_PRICE_RATIO="1.5")


def test_ignore_reaches_the_model_call_and_is_absent_without_the_policy() -> None:
    agent, client = orchestrator([final_response(ANSWER)])
    policy = CachePricePolicy(Source(MIMO), "m", 0.25)
    policy.refresh()
    agent.provider_policy = policy
    agent.run(request())
    assert client.payloads[0]["provider"] == {"require_parameters": True, "allow_fallbacks": True,
                                              "ignore": ["inference-net"]}
    plain, plain_client = orchestrator([final_response(ANSWER)])
    plain.run(request())
    assert "ignore" not in plain_client.payloads[0]["provider"]


def test_client_reads_the_endpoints_and_returns_none_on_failure() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models/xiaomi/mimo-v2.6-flash/endpoints"):
            return httpx.Response(200, json={"data": {"endpoints": MIMO}})
        return httpx.Response(500, json={"error": {"message": "no"}})
    client = OpenRouterClient("k", 5, transport=httpx.MockTransport(handler))
    assert [e["tag"] for e in client.model_endpoints("xiaomi/mimo-v2.6-flash")] == [e["tag"] for e in MIMO]
    assert client.model_endpoints("other/model") is None
