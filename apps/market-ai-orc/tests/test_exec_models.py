"""EXEC-MODELS (user 2026-10-13, "kita akan menambahkan model2 ini bisa di toggle model dan intellegence level di EDGE
(Default router tetap low)", "Ok, go defaultnya adalah deepseek V4.1 flash HIGH ya"): a message may choose the agent
loop's model and reasoning level from the offered models; the routers keep AI_MODEL with reasoning low; prices are read
from OpenRouter every hour; a message that chooses nothing runs exactly as before."""
from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import create_app
from app.model_choices import EDGE_DEFAULT, MODEL_CHOICES, ModelChoiceError, current_model_choice, resolve
from app.model_prices import ModelPrices
from app.openrouter_client import OpenRouterClient
from app.orchestrator import AgentOrchestrator
from app.tools import build_default_registry
from conftest import ANSWER, BASE_ENV, ScriptedClient, final_response, make_settings, tool_call_response
from test_mode4 import BROKER, FIRST_ROUND, m4, mode4_agent

AUTH = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}"}


# ---------------------------------------------------------------- the offered models and their levels

def test_the_five_offered_models_and_the_edge_default() -> None:
    # EXEC-LOGOS: MiMo V2.6 Pro is no longer offered (user: "Keluarin saja Mimo pro ya")
    # EXEC-SHARE-UI (user 2026-10-19): DeepSeek V4.1 Flash 1017 added beside V4.1 Flash
    assert [o.model for o in MODEL_CHOICES] == ["deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4.1-flash-1017",
                                                "z-ai/glm-5.3-flash", "xiaomi/mimo-v2.6-flash", "qwen/qwen3.8-flash"]
    assert EDGE_DEFAULT == {"model": "deepseek/deepseek-v4.1-flash", "reasoning_level": "high"}


@pytest.mark.parametrize("model,level,reasoning", [
    ("deepseek/deepseek-v4.1-flash", "high", {"effort": "high"}),
    ("deepseek/deepseek-v4.1-flash", "max", {"effort": "max"}),
    ("z-ai/glm-5.3-flash", "low", {"effort": "low"}),
    ("xiaomi/mimo-v2.6-flash", "on", {"enabled": True}),
    ("xiaomi/mimo-v2.6-flash", "off", {"enabled": False}),
    ("qwen/qwen3.8-flash", "on", {"max_tokens": 8000}),  # EXEC-LOGOS: Qwen's thinking has a budget
    ("qwen/qwen3.8-flash", "off", {"enabled": False}),
])
def test_each_model_takes_reasoning_in_its_own_form(model, level, reasoning) -> None:
    choice = resolve(model, level, make_settings())
    assert (choice.model, choice.reasoning, choice.level, choice.chosen) == (model, reasoning, level, True)


def test_no_choice_is_the_server_default_as_before() -> None:
    settings = make_settings(AI_REASONING_EFFORT="medium")
    choice = resolve(None, None, settings)
    assert (choice.model, choice.reasoning, choice.chosen) == (settings.ai_model, {"effort": "medium"}, False)


@pytest.mark.parametrize("model,level,code", [
    ("openai/gpt-x", "high", "MODEL_NOT_ALLOWED"),
    ("xiaomi/mimo-v2.6-pro", "on", "MODEL_NOT_ALLOWED"),
    ("xiaomi/mimo-v2.6-flash", "high", "REASONING_LEVEL_NOT_SUPPORTED"),
    ("z-ai/glm-5.3-flash", "medium", "REASONING_LEVEL_NOT_SUPPORTED"),  # OpenRouter lists max, high, low
    ("deepseek/deepseek-v4.1-flash", "on", "REASONING_LEVEL_NOT_SUPPORTED"),
])
def test_a_model_or_level_not_offered_is_refused(model, level, code) -> None:
    with pytest.raises(ModelChoiceError) as refused:
        resolve(model, level, make_settings())
    assert refused.value.code == code


# ---------------------------------------------------------------- the API and the agent loop

def api(script: list) -> tuple[TestClient, ScriptedClient]:
    settings = make_settings()
    scripted = ScriptedClient(script)
    return TestClient(create_app(settings, orchestrator=AgentOrchestrator(settings, scripted,
                                                                          build_default_registry()))), scripted


def test_the_chosen_model_runs_every_call_of_the_agent_loop_and_is_reported() -> None:
    client, scripted = api([tool_call_response("get_system_capabilities"), final_response(ANSWER)])
    with client:
        reply = client.post("/v1/agent/run", headers=AUTH, json={
            "request_id": "m1", "message": "Apa yang bisa kamu bantu?", "model": "z-ai/glm-5.3-flash",
            "reasoning_level": "low"})
    assert reply.status_code == 200
    assert [p["model"] for p in scripted.payloads] == ["z-ai/glm-5.3-flash"] * 2
    assert all(p["reasoning"] == {"effort": "low"} for p in scripted.payloads)
    execution = reply.json()["execution"]
    assert execution["model"] == "z-ai/glm-5.3-flash" and execution["reasoning_level"] == "low"


def test_the_api_takes_the_max_level() -> None:  # EXEC-LOGOS: Rendah / Tinggi / Maks
    client, scripted = api([final_response(ANSWER)])
    with client:
        reply = client.post("/v1/agent/run", headers=AUTH, json={
            "request_id": "m1x", "message": "Halo", "model": "deepseek/deepseek-v4.1-flash", "reasoning_level": "max"})
    assert reply.status_code == 200 and scripted.payloads[0]["reasoning"] == {"effort": "max"}


def test_a_message_without_a_choice_runs_as_before() -> None:
    client, scripted = api([tool_call_response("get_system_capabilities"), final_response(ANSWER)])
    with client:
        reply = client.post("/v1/agent/run", headers=AUTH, json={"request_id": "m2", "message": "Apa itu IHSG?"})
    settings = make_settings()
    assert [p["model"] for p in scripted.payloads] == [settings.ai_model] * 2
    assert all(p["reasoning"] == settings.reasoning(settings.ai_reasoning_effort) for p in scripted.payloads)
    assert "reasoning_level" not in reply.json()["execution"]


def test_a_model_not_offered_is_refused_before_anything_runs() -> None:
    client, scripted = api([final_response(ANSWER)])
    with client:
        reply = client.post("/v1/agent/run", headers=AUTH, json={
            "request_id": "m3", "message": "Halo", "model": "xiaomi/mimo-v2.6-flash", "reasoning_level": "high"})
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "REASONING_LEVEL_NOT_SUPPORTED"
    assert scripted.payloads == []


class _Reply(BaseModel):
    route: str = ""


def test_the_routers_keep_the_default_model_with_reasoning_low() -> None:
    settings = make_settings()
    scripted = ScriptedClient([final_response({"route": "CHAT"})])
    orc = AgentOrchestrator(settings, scripted, build_default_registry())
    token = current_model_choice.set(resolve("qwen/qwen3.8-flash", "on", settings))
    try:
        orc._router_call("r", "route", "Route it.", "Halo", "route", {"type": "object", "properties": {
            "route": {"type": "string"}}, "required": ["route"], "additionalProperties": False}, _Reply, "failed")
    finally:
        current_model_choice.reset(token)
    assert scripted.payloads[0]["model"] == settings.ai_model
    assert scripted.payloads[0]["reasoning"] == settings.reasoning("low")


def test_every_mode4_step_runs_the_chosen_model() -> None:
    agent, scripted, _ = mode4_agent(FIRST_ROUND)
    token = current_model_choice.set(resolve("xiaomi/mimo-v2.6-flash", "on", agent.inner.settings))
    try:
        result = agent.run(m4(request_id="m4m", message=BROKER))
    finally:
        current_model_choice.reset(token)
    loop_calls = [p for p in scripted.payloads if "tools" in p]
    assert loop_calls and {p["model"] for p in loop_calls} == {"xiaomi/mimo-v2.6-flash"}
    assert {str(p["reasoning"]) for p in loop_calls} == {str({"enabled": True})}
    assert result.execution.model == "xiaomi/mimo-v2.6-flash" and result.execution.reasoning_level == "on"


class _Policy:
    def __init__(self, ignored: list[str]) -> None:
        self._ignored = ignored

    def ignored(self) -> list[str]:
        return list(self._ignored)


def test_each_model_skips_its_own_providers() -> None:
    settings = make_settings()
    orc = AgentOrchestrator(settings, ScriptedClient([]), build_default_registry(), provider_policy=_Policy(["a"]),
                            provider_policies={"z-ai/glm-5.3-flash": _Policy(["b"])})
    assert orc._provider()["ignore"] == ["a"] and orc._provider(settings.ai_model)["ignore"] == ["a"]
    assert orc._provider("z-ai/glm-5.3-flash")["ignore"] == ["b"]
    assert "ignore" not in orc._provider("qwen/qwen3.8-flash")  # no list read: OpenRouter's default routing


# ---------------------------------------------------------------- prices every hour

LISTED = [{"id": "z-ai/glm-5.3-flash", "pricing": {"prompt": "0.0000000261", "completion": "0.0000009",
                                                   "input_cache_read": "0.0000000108"}},
          {"id": "other/model", "pricing": {"prompt": "1", "completion": "1"}}]


class _Source:
    def __init__(self, answers: list) -> None:
        self.answers = answers
        self.calls = 0

    def models(self):
        self.calls += 1
        return self.answers.pop(0) if self.answers else None


def test_prices_are_read_per_million_tokens_and_a_failed_read_keeps_them() -> None:
    now = [0.0]
    prices = ModelPrices(_Source([LISTED, None]), ttl_seconds=3600, clock=lambda: now[0])
    prices.refresh()
    table, fetched_at = prices.snapshot()
    assert table == {"z-ai/glm-5.3-flash": {"input_per_million": 0.0261, "output_per_million": 0.9,
                                           "cache_read_per_million": 0.0108}} and fetched_at
    prices.refresh()  # OpenRouter unavailable
    assert prices.snapshot() == (table, fetched_at)


def test_a_price_list_older_than_an_hour_is_read_again_in_the_background() -> None:
    now = [0.0]
    source = _Source([LISTED, LISTED])
    prices = ModelPrices(source, ttl_seconds=3600, clock=lambda: now[0])
    prices.refresh()
    started: list[bool] = []
    prices._start_refresh = lambda: started.append(True)  # the thread itself is the pattern of CachePricePolicy
    prices.snapshot()
    assert started == []
    now[0] = 3600.0
    prices.snapshot()
    assert started == [True]


def test_the_models_endpoint_lists_models_levels_prices_and_defaults() -> None:
    settings = make_settings()
    prices = ModelPrices(_Source([LISTED]))
    prices.refresh()
    app = create_app(settings, orchestrator=AgentOrchestrator(settings, ScriptedClient([]), build_default_registry()),
                     model_prices=prices)
    with TestClient(app) as client:
        assert client.get("/v1/models").status_code == 401
        body = client.get("/v1/models", headers=AUTH).json()
    glm = next(m for m in body["models"] if m["model"] == "z-ai/glm-5.3-flash")
    assert glm["reasoning_levels"] == ["low", "high", "max"] and glm["output_per_million"] == 0.9
    assert "xiaomi/mimo-v2.6-pro" not in [m["model"] for m in body["models"]]
    mimo = next(m for m in body["models"] if m["model"] == "xiaomi/mimo-v2.6-flash")
    assert mimo["reasoning_levels"] == ["off", "on"] and mimo["input_per_million"] is None  # not read yet
    assert body["edge_default"] == EDGE_DEFAULT and body["prices_fetched_at"]
    assert body["server_default"]["model"] == settings.ai_model


def test_the_client_reads_the_model_list_and_returns_none_on_failure() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": LISTED})
        return httpx.Response(500)
    assert OpenRouterClient("k", 5, transport=httpx.MockTransport(handler)).models() == LISTED
    broken = OpenRouterClient("k", 5, transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    assert broken.models() is None


def test_prices_are_read_again_every_ttl_without_any_request() -> None:
    import time as _time
    source = _Source([LISTED] * 50)
    prices = ModelPrices(source, ttl_seconds=0.05)
    prices.start()
    _time.sleep(0.3)
    prices.stop()
    assert source.calls >= 3 and prices.snapshot()[0]


# ---------------------------------------------------------------- M150: thinking that never ends (EXEC-LOGOS)

def runaway_response(cap: int) -> dict[str, Any]:
    """The live shape of request edge_7bc93daf… call 1: the whole output cap spent on reasoning, no text, no tool."""
    return {"id": "resp_runaway", "output": [{"type": "reasoning", "summary": [{"type": "summary_text",
                                                                                 "text": "Hmm, actually…"}]}],
            "usage": {"input_tokens": 100, "output_tokens": cap, "output_tokens_details": {"reasoning_tokens": cap - 1},
                      "total_tokens": 100 + cap}}


def chosen_run(model: str, level: str, script: list) -> tuple[ScriptedClient, Any]:
    settings = make_settings()
    scripted = ScriptedClient(script)
    orc = AgentOrchestrator(settings, scripted, build_default_registry())
    token = current_model_choice.set(resolve(model, level, settings))
    try:
        from test_orchestrator import request
        result = orc.run(request())
    finally:
        current_model_choice.reset(token)
    return scripted, result


def test_mimo_flash_on_has_a_lower_output_cap_per_call() -> None:
    scripted, _ = chosen_run("xiaomi/mimo-v2.6-flash", "on", [final_response(ANSWER)])
    assert scripted.payloads[0]["max_output_tokens"] == min(12000, make_settings().ai_max_output_tokens)
    scripted, _ = chosen_run("xiaomi/mimo-v2.6-flash", "off", [final_response(ANSWER)])
    assert scripted.payloads[0]["max_output_tokens"] == make_settings().ai_max_output_tokens


@pytest.mark.parametrize("model,level,lowered", [
    ("xiaomi/mimo-v2.6-flash", "on", {"enabled": False}),
    ("deepseek/deepseek-v4.1-flash", "max", {"effort": "low"}),
    ("z-ai/glm-5.3-flash", "high", {"effort": "low"}),  # GLM cannot turn thinking off
])
def test_a_runaway_call_is_asked_again_once_with_reasoning_lowered(model, level, lowered) -> None:
    cap = resolve(model, level, make_settings()).output_cap or make_settings().ai_max_output_tokens
    cap = min(cap, make_settings().ai_max_output_tokens)
    scripted, result = chosen_run(model, level, [runaway_response(cap), tool_call_response("get_system_capabilities"),
                                                 final_response(ANSWER)])
    assert result.status == "COMPLETED"
    chosen = resolve(model, level, make_settings()).reasoning
    assert [p["reasoning"] for p in scripted.payloads] == [chosen, lowered, chosen]  # one call only, then back
    assert scripted.payloads[1]["tools"]


def test_an_empty_turn_below_the_cap_is_not_a_runaway() -> None:
    from test_empty_turn import empty_response
    scripted, result = chosen_run("xiaomi/mimo-v2.6-flash", "on", [empty_response(), final_response(ANSWER)])
    assert result.status == "COMPLETED"
    assert [p["reasoning"] for p in scripted.payloads] == [{"enabled": True}] * 2


def test_a_second_runaway_falls_back_to_the_empty_turn_retry() -> None:
    cap = min(12000, make_settings().ai_max_output_tokens)
    scripted, result = chosen_run("xiaomi/mimo-v2.6-flash", "on", [runaway_response(cap), runaway_response(cap),
                                                                    final_response(ANSWER)])
    assert result.status == "COMPLETED"
    assert [p["reasoning"] for p in scripted.payloads] == [{"enabled": True}, {"enabled": False}, {"enabled": True}]


def test_without_a_choice_a_runaway_lowers_the_server_default_to_low() -> None:
    settings = make_settings()
    scripted = ScriptedClient([runaway_response(settings.ai_max_output_tokens), final_response(ANSWER)])
    from test_orchestrator import request
    AgentOrchestrator(settings, scripted, build_default_registry()).run(request())
    assert scripted.payloads[1]["reasoning"] == settings.reasoning("low")
    assert scripted.payloads[0]["reasoning"] == settings.reasoning(settings.ai_reasoning_effort)


MAX_ENV = {"AI_MAX_LEVEL_OUTPUT_TOKENS": "128000", "AI_MAX_LEVEL_REQUEST_TIMEOUT_SECONDS": "900",
           "AI_MAX_CONTEXT_TOKENS": "500000", "AI_MAX_OUTPUT_TOKENS": "24000", "AI_REQUEST_TIMEOUT_SECONDS": "600",
           "AI_MAX_ANALYSIS_SECONDS": "1800"}


class OptionsClient(ScriptedClient):
    def __init__(self, script: list) -> None:
        super().__init__(script)
        self.options: list[dict[str, Any]] = []

    def create(self, payload, **options):
        self.options.append(options)
        return super().create(payload, **options)


@pytest.mark.parametrize("level,cap,timeout", [("max", 128000, 900.0), ("high", 24000, None), ("low", 24000, None)])
def test_the_max_level_has_its_own_output_cap_and_call_limit(level, cap, timeout) -> None:
    """M (user 2026-10-20: "max 128K", option a): only the level max takes 128K tokens and a 900 s call limit."""
    settings = make_settings(**MAX_ENV)
    scripted = OptionsClient([final_response(ANSWER)])
    orc = AgentOrchestrator(settings, scripted, build_default_registry())
    token = current_model_choice.set(resolve("deepseek/deepseek-v4.1-flash", level, settings))
    try:
        from test_orchestrator import request
        assert orc.run(request()).status == "COMPLETED"
    finally:
        current_model_choice.reset(token)
    assert scripted.payloads[0]["max_output_tokens"] == cap
    assert scripted.options[0].get("timeout") == timeout


def test_the_max_level_settings_are_checked() -> None:
    from app.config import ConfigError
    with pytest.raises(ConfigError, match="AI_MAX_LEVEL_OUTPUT_TOKENS"):
        make_settings(**{**MAX_ENV, "AI_MAX_CONTEXT_TOKENS": "128000"})
    with pytest.raises(ConfigError, match="AI_MAX_LEVEL_REQUEST_TIMEOUT_SECONDS"):
        make_settings(**{**MAX_ENV, "AI_MAX_LEVEL_REQUEST_TIMEOUT_SECONDS": "2400"})
    assert make_settings().ai_max_level_output_tokens == 0  # unset: max runs like the other levels
