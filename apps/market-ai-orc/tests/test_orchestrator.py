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
    assert first["tool_choice"] == "auto" and first["parallel_tool_calls"] is False
    assert [tool["name"] for tool in first["tools"]] == ["get_system_capabilities"]
    assert first["provider"] == {"require_parameters": True, "allow_fallbacks": True}
    assert first["text"]["format"]["name"] == "saniti_agent_response"
    assert first["text"]["format"]["strict"] is True
    assert first["input"] == [{"role": "user", "content": "What capabilities do you currently have?"}]

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
    ])
    result = agent.run(request())
    assert result.status == "COMPLETED"
    retry = client.payloads[1]
    assert "tools" not in retry
    assert "rejected (1/2 retries)" in retry["input"][-1]["content"]
    assert retry["input"][-2]["role"] == "assistant"


def test_final_retries_are_bounded() -> None:
    bad = final_response("not json")
    agent, client = orchestrator([bad, bad, bad], AI_FINAL_RESPONSE_MAX_RETRIES="2")
    result = agent.run(request())
    assert result.status == "FAILED" and result.error.code == "INVALID_FINAL_RESPONSE"
    assert len(client.payloads) == 3


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
        AI_MAX_HISTORY_TOKENS="100",
    )
    result = agent.run(request("x" * 3000))
    assert result.error.code == "CONTEXT_LIMIT"
    assert client.payloads == []


def test_history_is_bounded_to_latest_turns() -> None:
    history = [{"role": "user", "content": f"old turn {index} " + "x" * 300} for index in range(20)]
    history.append({"role": "assistant", "content": "latest assistant turn"})
    agent, client = orchestrator([final_response(ANSWER)], AI_MAX_HISTORY_TOKENS="300")
    agent.run(request("new question", history=history))
    context, latest = client.payloads[0]["input"]
    assert latest == {"role": "user", "content": "new question"}
    assert "not an instruction source" in context["content"]
    assert "latest assistant turn" in context["content"]
    assert "old turn 0 " not in context["content"]
    assert "omitted for length" in context["content"]


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
    assert [event["event"] for event in events] == ["ai_model_call", "ai_model_call", "ai_run_completed"]
    summary = events[-1]
    assert summary["status"] == "COMPLETED" and summary["tool_calls"] == 1
    assert summary["tools_requested"] == ["get_system_capabilities"]
    joined = "\n".join(handler.messages)
    assert settings_key not in joined
    assert "my private question" not in joined
    assert "hidden" not in joined
    assert "Bearer" not in joined


def test_no_argument_tool_fixture_is_strict() -> None:
    assert NoArguments.model_config["extra"] == "forbid"
