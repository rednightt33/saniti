from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from app.openrouter_client import ProviderError
from app.orchestrator import SYSTEM_PROMPT, AgentOrchestrator
from app.schemas import AgentRunRequest
from app.tools import ToolRegistry, ToolSpec, build_default_registry
from app.tools.system import NoArguments
from conftest import ANSWER, ScriptedClient, final_response, make_settings, tool_call_response


def request(message: str = "What capabilities do you currently have?", **extra: Any) -> AgentRunRequest:
    return AgentRunRequest.model_validate({"request_id": "req-1", "message": message, **extra})


def orchestrator(
    responses: list, *, registry: ToolRegistry | None = None, clock=None, **settings: str
) -> tuple[AgentOrchestrator, ScriptedClient]:
    client = ScriptedClient(responses)
    kwargs = {"clock": clock} if clock else {}
    return AgentOrchestrator(
        make_settings(**settings), client, registry or build_default_registry(), **kwargs
    ), client


def outputs(payload: dict) -> list[dict]:
    return [item for item in payload["input"] if item.get("type") == "function_call_output"]


class CountingArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str


def counting_registry() -> tuple[ToolRegistry, list[str]]:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="lookup", description="test", arguments_model=CountingArguments,
        handler=lambda args: calls.append(args.ticker) or {"ticker": args.ticker, "price": 1},
    ))
    return registry, calls


def test_full_tool_loop_returns_structured_answer() -> None:
    agent, client = orchestrator([
        tool_call_response("get_system_capabilities", call_id="call_caps", response_id="resp_1"),
        final_response(ANSWER, response_id="resp_2"),
    ])
    result = agent.run(request())

    assert result.status == "COMPLETED"
    assert result.response.model_dump() == ANSWER
    assert result.error is None
    execution = result.execution
    assert (execution.provider, execution.iterations, execution.tool_call_count) == ("openrouter", 2, 1)
    assert execution.provider_response_id == "resp_2"
    assert (execution.input_tokens, execution.output_tokens) == (200, 40)
    assert (execution.reasoning_tokens, execution.total_tokens) == (10, 240)

    first, second = client.payloads
    assert first["instructions"] == SYSTEM_PROMPT
    assert first["store"] is False
    assert first["tool_choice"] == "auto"
    assert "parallel_tool_calls" not in first
    assert [tool["name"] for tool in first["tools"]] == ["get_system_capabilities"]
    assert first["provider"] == {"require_parameters": True, "allow_fallbacks": True}
    assert "text" not in first and "text" not in second
    run_context, question = first["input"]
    assert question == {"role": "user", "content": "What capabilities do you currently have?"}
    assert run_context["role"] == "user" and "reference date" in run_context["content"]

    call_items = [item for item in second["input"] if item.get("type") == "function_call"]
    assert call_items == [{
        "type": "function_call", "call_id": "call_caps",
        "name": "get_system_capabilities", "arguments": "{}",
    }]
    [output] = outputs(second)
    assert output["call_id"] == "call_caps"
    assert json.loads(output["output"])["result"]["database_query"] is False
    assert not any(item.get("type") == "reasoning" for item in second["input"])


def test_direct_answer_without_tool() -> None:
    agent, client = orchestrator([final_response(ANSWER)])
    result = agent.run(request("Say hello"))
    assert result.status == "COMPLETED"
    assert result.execution.iterations == 1 and result.execution.tool_call_count == 0
    assert len(client.payloads) == 1


def test_no_registered_tools_means_no_tool_fields() -> None:
    agent, client = orchestrator([final_response(ANSWER)], registry=ToolRegistry())
    agent.run(request())
    payload = client.payloads[0]
    assert "tools" not in payload and "tool_choice" not in payload and "parallel_tool_calls" not in payload
    assert payload["text"]["format"]["name"] == "saniti_agent_response"
    assert payload["text"]["format"]["strict"] is True


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"response_type": "CLARIFICATION", "answer": "", "clarification_question": "Which ticker?",
          "assumptions": [], "limitations": []}, "NEEDS_CLARIFICATION"),
        ({"response_type": "LIMITATION", "answer": "Only capabilities can be reported.",
          "clarification_question": None, "assumptions": [],
          "limitations": ["Required capability is not currently available."]}, "LIMITED"),
    ],
)
def test_status_is_mapped_from_response_type(body: dict, status: str) -> None:
    agent, _ = orchestrator([final_response(body)])
    assert agent.run(request()).status == status


def test_repeated_identical_tool_calls_hit_guard() -> None:
    registry, executed = counting_registry()
    same = '{"ticker": "BBCA"}'
    agent, client = orchestrator([
        tool_call_response("lookup", same, call_id="c1"),
        tool_call_response("lookup", same, call_id="c2"),
        tool_call_response("lookup", same, call_id="c3"),
        final_response(ANSWER),
    ], registry=registry)
    result = agent.run(request())

    assert result.status == "COMPLETED"
    assert executed == ["BBCA", "BBCA"]
    last = json.loads(outputs(client.payloads[-1])[-1]["output"])
    assert last["error"]["code"] == "REPEATED_TOOL_CALL"


def test_different_arguments_are_not_treated_as_repeats() -> None:
    registry, executed = counting_registry()
    agent, _ = orchestrator([
        tool_call_response("lookup", '{"ticker": "BBCA"}', call_id="c1"),
        tool_call_response("lookup", '{"ticker": "BBRI"}', call_id="c2"),
        tool_call_response("lookup", '{ "ticker" : "BBCA" }', call_id="c3"),
        final_response(ANSWER),
    ], registry=registry)
    agent.run(request())
    assert executed == ["BBCA", "BBRI", "BBCA"]


def test_max_iterations_is_enforced() -> None:
    registry, _ = counting_registry()
    responses = [
        tool_call_response("lookup", json.dumps({"ticker": f"T{index}"}), call_id=f"c{index}")
        for index in range(10)
    ]
    agent, client = orchestrator(responses, registry=registry, AI_MAX_TOOL_ITERATIONS="3")
    result = agent.run(request())
    assert result.status == "FAILED" and result.response is None
    assert result.error.code == "MAX_ITERATIONS"
    assert len(client.payloads) == 3 and result.execution.iterations == 3


def test_tool_budget_exhaustion_locks_tools() -> None:
    registry, executed = counting_registry()
    agent, client = orchestrator([
        tool_call_response("lookup", '{"ticker": "A"}', call_id="c1"),
        tool_call_response("lookup", '{"ticker": "B"}', call_id="c2"),
        final_response(ANSWER),
    ], registry=registry, AI_MAX_TOOL_CALLS="1")
    result = agent.run(request())
    assert result.status == "COMPLETED"
    assert executed == ["A"]
    assert json.loads(outputs(client.payloads[2])[-1]["output"])["error"]["code"] == "TOOL_BUDGET_EXHAUSTED"
    assert "tools" not in client.payloads[2]
    assert result.execution.tools_withdrawn_reason == "TOOL_CALL_BUDGET"


def test_unknown_tool_request_returns_error_to_model() -> None:
    agent, client = orchestrator([
        tool_call_response("drop_database", "{}", call_id="c1"),
        final_response(ANSWER),
    ])
    assert agent.run(request()).status == "COMPLETED"
    assert json.loads(outputs(client.payloads[1])[0]["output"])["error"]["code"] == "UNKNOWN_TOOL"


def test_malformed_tool_arguments_return_bounded_error() -> None:
    registry, executed = counting_registry()
    agent, client = orchestrator([
        tool_call_response("lookup", '{"ticker": "BB', call_id="c1"),
        final_response(ANSWER),
    ], registry=registry)
    assert agent.run(request()).status == "COMPLETED"
    assert executed == []
    assert json.loads(outputs(client.payloads[1])[0]["output"])["error"]["code"] == "INVALID_ARGUMENTS"


def test_invalid_final_is_retried_without_tools() -> None:
    agent, client = orchestrator([
        final_response({**ANSWER, "confidence": "HIGH"}),
        final_response(ANSWER),
    ], registry=ToolRegistry())
    result = agent.run(request())
    assert result.status == "COMPLETED"
    retry = client.payloads[1]
    assert "tools" not in retry
    assert "rejected (1/2 retries)" in retry["input"][-1]["content"]
    assert retry["input"][-2]["role"] == "assistant"


def test_final_retries_are_bounded() -> None:
    bad = final_response("not json")
    agent, client = orchestrator([bad, bad, bad], registry=ToolRegistry(), AI_FINAL_RESPONSE_MAX_RETRIES="2")
    result = agent.run(request())
    assert result.status == "FAILED" and result.error.code == "INVALID_FINAL_RESPONSE"
    assert len(client.payloads) == 3


def test_prose_answer_on_tool_turn_is_finalized_under_strict_schema() -> None:
    agent, client = orchestrator([
        tool_call_response("get_system_capabilities", call_id="call_caps"),
        final_response("Only get_system_capabilities is available; no database or Python yet."),
        final_response(ANSWER),
    ], AI_FINAL_RESPONSE_MAX_RETRIES="0")
    result = agent.run(request())

    assert result.status == "COMPLETED" and result.response.model_dump() == ANSWER
    assert result.execution.iterations == 3 and result.execution.tool_call_count == 1
    finalize = client.payloads[2]
    # the re-ask keeps the tool-turn request (same prefix and provider); the JSON contract is in the instruction
    assert finalize["tools"] == client.payloads[1]["tools"] and "text" not in finalize
    assert finalize["input"][-2] == {
        "role": "assistant",
        "content": "Only get_system_capabilities is available; no database or Python yet.",
    }
    assert "never ask the user about it" in finalize["input"][-1]["content"]


def test_invalid_output_after_finalization_uses_bounded_retries() -> None:
    agent, client = orchestrator([
        final_response("draft prose"),
        final_response("still not json"),
        final_response("again not json"),
        final_response("and again not json"),
    ], AI_FINAL_RESPONSE_MAX_RETRIES="1")
    result = agent.run(request())
    assert result.error.code == "INVALID_FINAL_RESPONSE"
    assert len(client.payloads) == 4
    # first re-ask as a tool turn, then the strict schema without tools for the bounded retries
    assert "tools" in client.payloads[1] and "text" not in client.payloads[1]
    assert all("tools" not in p and p["text"]["format"]["strict"] for p in client.payloads[2:])


def test_tool_call_during_finalization_is_not_executed() -> None:
    registry, executed = counting_registry()
    agent, client = orchestrator([
        final_response("draft prose"),
        tool_call_response("lookup", '{"ticker": "BBCA"}', call_id="late"),
        final_response(ANSWER),
    ], registry=registry)
    assert agent.run(request()).status == "COMPLETED"
    assert executed == []
    assert json.loads(outputs(client.payloads[2])[-1]["output"])["error"]["code"] == "TOOLS_NOT_AVAILABLE"
    assert "tools" not in client.payloads[2]


def test_markdown_fenced_final_is_accepted() -> None:
    agent, _ = orchestrator([final_response("```json\n" + json.dumps(ANSWER) + "\n```")])
    assert agent.run(request()).status == "COMPLETED"


def test_provider_failure_is_normalized() -> None:
    agent, _ = orchestrator([ProviderError("openrouter HTTP 429: no credit", code="PROVIDER_QUOTA_EXHAUSTED")])
    result = agent.run(request())
    assert result.status == "FAILED" and result.error.code == "PROVIDER_QUOTA_EXHAUSTED"


def test_unexpected_error_does_not_leak_detail() -> None:
    agent, _ = orchestrator([RuntimeError("secret internal detail")])
    result = agent.run(request())
    assert result.error.code == "INTERNAL_ERROR"
    assert "secret internal detail" not in result.error.message


def test_missing_call_id_fails_closed() -> None:
    response = tool_call_response("get_system_capabilities")
    del response["output"][1]["call_id"]
    agent, _ = orchestrator([response])
    assert agent.run(request()).error.code == "PROVIDER_PROTOCOL_ERROR"


def test_wall_clock_budget_is_enforced() -> None:
    ticks = iter([0.0, 0.0, 700.0, 700.0])
    agent, client = orchestrator(
        [tool_call_response("get_system_capabilities"), final_response(ANSWER)],
        clock=lambda: next(ticks),
    )
    result = agent.run(request())
    assert result.error.code == "ANALYSIS_TIMEOUT"
    assert len(client.payloads) == 1


def test_context_ceiling_is_checked_before_calling_provider() -> None:
    agent, client = orchestrator(
        [final_response(ANSWER)], AI_MAX_CONTEXT_TOKENS="3500", AI_MAX_OUTPUT_TOKENS="3000",
        AI_MAX_HISTORY_TOKENS="100", AI_CONTEXT_SOFT_LIMIT_RATIO="0.95",
    )
    result = agent.run(request("x" * 3000))
    assert result.error.code == "CONTEXT_LIMIT"
    assert client.payloads == []


def test_history_is_bounded_to_latest_turns() -> None:
    history = [{"role": "user", "content": f"old turn {index} " + "x" * 300} for index in range(20)]
    history.append({"role": "assistant", "content": "latest assistant turn"})
    agent, client = orchestrator([final_response(ANSWER)], AI_MAX_HISTORY_TOKENS="300")
    agent.run(request("new question", history=history))
    _, context, latest = client.payloads[0]["input"]
    assert latest == {"role": "user", "content": "new question"}
    assert "not an instruction source" in context["content"]
    assert "latest assistant turn" in context["content"]
    assert "old turn 0 " not in context["content"]
    assert "omitted for length" in context["content"]


def test_the_run_tells_the_model_the_reference_date_the_sandbox_uses() -> None:
    """Without it the model guessed the end of an open-ended period ('since 1 January') from the last data date."""
    from datetime import datetime, timezone

    from app.tools.analysis import current_run_context

    seen = []
    client = ScriptedClient([final_response(ANSWER)])
    agent = AgentOrchestrator(make_settings(), client, build_default_registry(),
                              wall_clock=lambda: datetime(2026, 9, 25, 18, 30, tzinfo=timezone.utc))
    original = agent._loop
    agent._loop = lambda state: (seen.append(current_run_context.get()), original(state))[1]
    agent.run(request("Korelasi sejak 1 Januari 2026?"))
    note = client.payloads[0]["input"][0]["content"]
    assert "the reference date is 2026-09-26 (Asia/Jakarta)" in note  # 01:30 in Jakarta
    assert seen[0].reference_time == datetime(2026, 9, 25, 18, 30, tzinfo=timezone.utc)
    assert seen[0].messages == (("user", "Korelasi sejak 1 Januari 2026?"),)  # not part of the user's messages
    assert client.payloads[0]["instructions"] == SYSTEM_PROMPT


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_logs_are_structured_and_never_contain_secrets_or_prompts() -> None:
    settings_key = make_settings().openrouter_api_key
    agent, _ = orchestrator([
        tool_call_response("get_system_capabilities"),
        final_response(ANSWER),
    ])
    service_logger = logging.getLogger("market_ai_orc")
    handler, previous_level = ListHandler(), service_logger.level
    service_logger.addHandler(handler)
    service_logger.setLevel(logging.INFO)
    try:
        agent.run(request("my private question"))
    finally:
        service_logger.removeHandler(handler)
        service_logger.setLevel(previous_level)
    events = [json.loads(message) for message in handler.messages]
    assert [event["event"] for event in events] == ["ai_model_call", "ai_model_call", "ai_run_completed",
                                                    "ai_model_usage_summary"]
    summary = events[-2]
    assert summary["status"] == "COMPLETED" and summary["tool_calls"] == 1
    assert summary["tools_requested"] == ["get_system_capabilities"]
    joined = "\n".join(handler.messages)
    assert settings_key not in joined
    assert "my private question" not in joined
    assert "hidden" not in joined
    assert "Bearer" not in joined


def test_no_argument_tool_fixture_is_strict() -> None:
    assert NoArguments.model_config["extra"] == "forbid"


# --- Context budget: graceful degradation before the hard ceiling ---------------------------------

class BlobArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: int


def blob_registry() -> ToolRegistry:
    registry = ToolRegistry(max_result_bytes=200_000)
    registry.register(ToolSpec(
        name="read_blob", description="test", arguments_model=BlobArguments,
        handler=lambda args: {"blob": "x" * args.size},
    ))
    return registry


# About 1.7k tokens of instructions/tools/schema; each 21,000-byte result adds ~7k tokens.
BUDGET = {"AI_MAX_CONTEXT_TOKENS": "20000", "AI_MAX_OUTPUT_TOKENS": "1000"}
LIMITATION = {
    "response_type": "LIMITATION",
    "answer": "Only part of the requested records could be read.",
    "clarification_question": None,
    "assumptions": [],
    "limitations": ["Tool access ended at the context budget; pages 1-2 were read, the rest is unread."],
}


def blob_call(size: int, call_id: str) -> dict:
    return tool_call_response("read_blob", json.dumps({"size": size}), call_id=call_id)


def test_soft_context_limit_withdraws_tools_and_finalizes_instead_of_failing() -> None:
    agent, client = orchestrator([
        blob_call(21000, "c1"),
        blob_call(21001, "c2"),
        final_response(LIMITATION),
    ], registry=blob_registry(), **BUDGET)
    service_logger = logging.getLogger("market_ai_orc")
    handler, previous_level = ListHandler(), service_logger.level
    service_logger.addHandler(handler)
    service_logger.setLevel(logging.INFO)
    try:
        result = agent.run(request("Read every page."))
    finally:
        service_logger.removeHandler(handler)
        service_logger.setLevel(previous_level)

    assert result.status == "LIMITED" and result.error is None
    assert result.response.model_dump() == LIMITATION
    assert result.execution.tools_withdrawn_reason == "CONTEXT_BUDGET"
    assert result.execution.tool_call_count == 2 and result.execution.iterations == 3
    assert "tools" in client.payloads[1] and "text" not in client.payloads[1]
    final = client.payloads[2]
    assert "tools" not in final and final["text"]["format"]["strict"] is True
    assert final["input"][-1]["role"] == "user"
    assert "context budget" in final["input"][-1]["content"]
    # Prior tool outputs are kept verbatim: nothing is dropped, summarized, or truncated.
    blobs = [json.loads(item["output"])["result"]["blob"] for item in outputs(final)]
    assert [len(blob) for blob in blobs] == [21000, 21001]
    events = [json.loads(message) for message in handler.messages]
    assert events[-2]["event"] == "ai_run_completed"
    assert events[-2]["tools_withdrawn_reason"] == "CONTEXT_BUDGET"
    assert not any("xxxxxxxx" in message or "context budget" in message for message in handler.messages)


def test_context_budget_answer_with_limitations_completes() -> None:
    answer = {**ANSWER, "limitations": ["Tool access ended at the context budget after page 2."]}
    agent, _ = orchestrator([blob_call(21000, "c1"), blob_call(21001, "c2"), final_response(answer)],
                            registry=blob_registry(), **BUDGET)
    result = agent.run(request("Read every page."))
    assert result.status == "COMPLETED" and result.response.limitations == answer["limitations"]
    assert result.execution.tools_withdrawn_reason == "CONTEXT_BUDGET"


def test_context_budget_answer_without_limitations_is_rejected_then_corrected() -> None:
    agent, client = orchestrator([
        blob_call(21000, "c1"), blob_call(21001, "c2"), final_response(ANSWER), final_response(LIMITATION),
    ], registry=blob_registry(), **BUDGET)
    result = agent.run(request("Read every page."))
    assert result.status == "LIMITED" and result.execution.iterations == 4
    assert "what remains unread" in client.payloads[3]["input"][-1]["content"]
    assert "tools" not in client.payloads[3]


def test_below_soft_limit_behaves_exactly_as_before() -> None:
    agent, client = orchestrator([blob_call(100, "c1"), blob_call(101, "c2"), final_response(ANSWER)],
                                 registry=blob_registry(), **BUDGET)
    result = agent.run(request("Read two small pages."))
    assert result.status == "COMPLETED" and result.execution.tools_withdrawn_reason is None
    assert all("tools" in payload and "text" not in payload for payload in client.payloads)
    assert not any(item.get("role") == "user" and "context budget" in str(item.get("content"))
                   for item in client.payloads[-1]["input"])


def test_hard_context_limit_remains_when_even_finalization_cannot_fit() -> None:
    agent, client = orchestrator([blob_call(21000, "c1"), blob_call(45000, "c2"), final_response(LIMITATION)],
                                 registry=blob_registry(), **BUDGET)
    result = agent.run(request("Read every page."))
    assert result.status == "FAILED" and result.error.code == "CONTEXT_LIMIT"
    assert result.execution.tools_withdrawn_reason == "CONTEXT_BUDGET"
    assert len(client.payloads) == 2  # the finalization turn was never sent


def test_oversized_initial_request_still_fails_with_context_limit() -> None:
    agent, client = orchestrator([final_response(ANSWER)], registry=blob_registry(),
                                 AI_MAX_CONTEXT_TOKENS="6000", AI_MAX_OUTPUT_TOKENS="1000",
                                 AI_MAX_HISTORY_TOKENS="100")
    result = agent.run(request("y" * 15000))
    assert result.error.code == "CONTEXT_LIMIT" and client.payloads == []


def test_a_tool_call_cut_off_at_the_output_limit_is_not_run() -> None:
    """OpenRouter closes a truncated call's JSON and reports it completed; reaching max_output_tokens is the signal."""
    registry, calls = counting_registry()
    truncated = tool_call_response("lookup", '{"ticker": "BB"}', call_id="call_cut", response_id="resp_1")
    truncated["usage"] = {**truncated["usage"], "output_tokens": 8000}
    complete = tool_call_response("lookup", '{"ticker": "BBCA"}', call_id="call_ok", response_id="resp_2")
    agent, client = orchestrator([truncated, complete, final_response(ANSWER, response_id="resp_3")],
                                 registry=registry)
    result = agent.run(request())
    assert result.status == "COMPLETED"
    assert calls == ["BBCA"]  # the truncated call never reached the tool
    cut = json.loads(outputs(client.payloads[1])[0]["output"])
    assert cut["error"]["code"] == "MODEL_OUTPUT_TRUNCATED" and "8000" in cut["error"]["message"]
    assert client.payloads[0]["max_output_tokens"] == 8000
