"""Prompt-caching-aware model calls: one OpenRouter session per run, a byte-stable reusable prefix, and
usage observability that separates cached from fresh prompt tokens. No prompt cache is kept here: DeepSeek
caches implicitly on the provider side, and these tests only prove the requests make that possible."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.orchestrator import SYSTEM_PROMPT, static_prefix_hash
from app.tools import build_default_registry
from conftest import ANSWER, final_response, make_settings, tool_call_response
from test_orchestrator import BUDGET, LIMITATION, ListHandler, blob_call, blob_registry, orchestrator, request


def cached(response: dict[str, Any], prompt: int, cached_tokens: int, cost: float | None = 0.0001,
           write: int = 0) -> dict[str, Any]:
    usage: dict[str, Any] = {"input_tokens": prompt, "output_tokens": 20, "total_tokens": prompt + 20,
                             "output_tokens_details": {"reasoning_tokens": 5},
                             "input_tokens_details": {"cached_tokens": cached_tokens, "cache_write_tokens": write}}
    if cost is not None:
        usage["cost"] = cost
    return {**response, "usage": usage, "model": "deepseek/deepseek-v4.1-flash", "provider": "DeepSeek"}


def run_logged(agent, message: str = "What capabilities do you currently have?", request_id: str = "req-1"):
    service_logger = logging.getLogger("market_ai_orc")
    handler, previous = ListHandler(), service_logger.level
    service_logger.addHandler(handler)
    service_logger.setLevel(logging.INFO)
    try:
        result = agent.run(request(message).model_copy(update={"request_id": request_id}))
    finally:
        service_logger.removeHandler(handler)
        service_logger.setLevel(previous)
    return result, [json.loads(m) for m in handler.messages]


def three_turns() -> list[dict[str, Any]]:
    return [cached(tool_call_response("get_system_capabilities", call_id="c1"), 8892, 0, write=0),
            cached(tool_call_response("get_system_capabilities", call_id="c2", response_id="resp_2"), 10420, 8500),
            cached(final_response(ANSWER), 12750, 10240)]


def test_every_call_of_a_run_carries_the_same_session_id_and_a_new_run_gets_a_new_one() -> None:
    agent, client = orchestrator(three_turns())
    run_logged(agent, request_id="research-run-abc123")
    assert [p["session_id"] for p in client.payloads] == ["research-run-abc123"] * 3
    agent, other = orchestrator(three_turns())
    run_logged(agent, request_id="research-run-def456")
    assert {p["session_id"] for p in other.payloads} == {"research-run-def456"}


def test_the_reusable_prefix_is_byte_identical_across_tool_turns() -> None:
    agent, client = orchestrator(three_turns())
    run_logged(agent)
    first, second, final = client.payloads
    assert first["instructions"] == second["instructions"] == SYSTEM_PROMPT
    assert json.dumps(first["tools"]) == json.dumps(second["tools"])  # same tools, same order, same schemas
    assert [t["name"] for t in first["tools"]] == [t["name"] for t in build_default_registry().definitions()]
    assert static_prefix_hash(first) == static_prefix_hash(second)
    # the conversation only grows at the end: earlier items are never rewritten
    assert second["input"][:len(first["input"])] == first["input"]
    assert final["input"][:len(second["input"])] == second["input"]


def test_tool_definitions_serialize_deterministically() -> None:
    one = json.dumps(build_default_registry().definitions())
    two = json.dumps(build_default_registry().definitions())
    assert one == two


def test_withdrawing_tools_is_the_only_prefix_change_and_it_is_visible() -> None:
    agent, client = orchestrator([blob_call(21000, "c1"), blob_call(21001, "c2"), final_response(LIMITATION)],
                                 registry=blob_registry(), **BUDGET)
    _, events = run_logged(agent, "Read every page.")
    calls = [e for e in events if e["event"] == "ai_model_call"]
    assert calls[0]["static_prefix_sha256"] == calls[1]["static_prefix_sha256"]
    assert calls[2]["static_prefix_sha256"] != calls[1]["static_prefix_sha256"]  # tools withdrawn, JSON format
    summary = [e for e in events if e["event"] == "ai_model_usage_summary"][0]
    assert summary["distinct_static_prefixes"] == 2


def test_each_call_logs_cached_fresh_and_cost_and_the_run_summarizes_them() -> None:
    agent, _ = orchestrator(three_turns())
    result, events = run_logged(agent, request_id="research-123")
    calls = [e for e in events if e["event"] == "ai_model_call"]
    assert [(c["iteration"], c["input_tokens"], c["cached_input_tokens"], c["fresh_input_tokens"]) for c in calls] == [
        (1, 8892, 0, 8892), (2, 10420, 8500, 1920), (3, 12750, 10240, 2510)]
    first = calls[0]
    assert first["session_id"] == "research-123" and first["provider"] == "DeepSeek"
    assert first["model"] == "deepseek/deepseek-v4.1-flash" and first["cost"] == 0.0001
    assert first["cache_metrics_reported"] is True and isinstance(first["latency_ms"], int)
    summary = [e for e in events if e["event"] == "ai_model_usage_summary"][0]
    assert summary["prompt_tokens"] == 32062 and summary["cached_input_tokens"] == 18740
    assert summary["fresh_input_tokens"] == 13322 and summary["completion_tokens"] == 60
    assert summary["cache_ratio"] == round(18740 / 32062, 4)
    assert summary["cost"] == 0.0003 and summary["cost_reported_calls"] == 3 and summary["model_calls"] == 3
    execution = result.execution
    assert (execution.cached_input_tokens, execution.cost) == (18740, 0.0003)


def test_missing_cache_and_cost_fields_are_reported_as_missing_not_as_zero_cost() -> None:
    agent, _ = orchestrator([final_response(ANSWER)])  # conftest usage has no cache details and no cost
    result, events = run_logged(agent)
    summary = [e for e in events if e["event"] == "ai_model_usage_summary"][0]
    assert summary["cache_metrics_reported_calls"] == 0 and summary["cached_input_tokens"] == 0
    assert summary["cost"] is None and result.execution.cost is None


def test_cache_ratio_handles_a_run_without_prompt_tokens() -> None:
    agent, _ = orchestrator([cached(final_response(ANSWER), 0, 0, cost=None)])
    _, events = run_logged(agent)
    summary = [e for e in events if e["event"] == "ai_model_usage_summary"][0]
    assert summary["cache_ratio"] is None and summary["prompt_tokens"] == 0


def test_model_behavior_settings_are_unchanged() -> None:
    agent, client = orchestrator(three_turns())
    run_logged(agent)
    tool_turn, final = client.payloads[0], client.payloads[2]
    assert tool_turn["reasoning"] == {"effort": make_settings().ai_reasoning_effort}
    assert tool_turn["max_output_tokens"] == make_settings().ai_max_output_tokens
    assert tool_turn["store"] is False and tool_turn["tool_choice"] == "auto"
    assert tool_turn["provider"] == {"require_parameters": True, "allow_fallbacks": True}
    assert "parallel_tool_calls" not in tool_turn and "prompt_cache_key" not in tool_turn
    assert "cache_control" not in json.dumps(client.payloads)
    assert "text" not in tool_turn and "tools" in tool_turn


def test_the_final_reask_keeps_the_tool_turn_prefix_so_it_stays_on_the_cached_provider() -> None:
    """A prose draft on a tool turn is re-asked with the same tools and no text.format: the static prefix is
    byte-identical, so the call stays on the provider that holds the run's cache (verified live 2026-09-24: 5/5 on
    the same provider with ~93% cached, where the strict-format turn moved to another provider with no cache)."""
    agent, client = orchestrator([
        cached(tool_call_response("get_system_capabilities", call_id="c1"), 9000, 0),
        cached(final_response("Here is what I can do: catalog discovery and Python analysis."), 9500, 8960),
        cached(final_response(ANSWER), 9800, 9472),
    ])
    result, events = run_logged(agent)
    assert result.status == "COMPLETED" and len(client.payloads) == 3
    assert static_prefix_hash(client.payloads[2]) == static_prefix_hash(client.payloads[0])
    assert "text" not in client.payloads[2] and client.payloads[2]["tool_choice"] == "auto"
    summary = [e for e in events if e["event"] == "ai_model_usage_summary"][0]
    assert summary["distinct_static_prefixes"] == 1
