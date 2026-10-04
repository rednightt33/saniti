"""M78 (ma-qa-20261004a q2): the provider stopped after the reasoning, so the turn had neither text nor a tool call; the
orchestrator asked for the final response without tools and the run ended LIMITED with no data read. An empty turn is
now retried with the same tools (at most MAX_EMPTY_TURN_RETRIES), at the first step or in the middle of a tool loop."""
from __future__ import annotations

from app.orchestrator import EMPTY_TURN_NOTE, FINALIZE_PREFIX, MAX_EMPTY_TURN_RETRIES
from conftest import ANSWER, final_response, tool_call_response, usage
from test_orchestrator import orchestrator, request


def empty_response() -> dict:
    return {"id": "resp_empty", "output": [{"type": "reasoning", "summary": [{"type": "summary_text",
                                                                              "text": "Let me discover"}]}],
            "usage": usage(output_tokens=150)}


def last_user_text(payload: dict) -> str:
    return next(i["content"] for i in reversed(payload["input"]) if i.get("role") == "user")


def test_an_empty_first_turn_is_retried_with_its_tools() -> None:
    agent, client = orchestrator([empty_response(), tool_call_response("get_system_capabilities"),
                                  final_response(ANSWER)])
    result = agent.run(request())
    assert result.status == "COMPLETED"
    retry = client.payloads[1]
    assert retry["tools"] and last_user_text(retry) == EMPTY_TURN_NOTE
    assert not any(FINALIZE_PREFIX in str(i.get("content")) for i in retry["input"])


def test_an_empty_turn_inside_a_tool_loop_is_retried_too() -> None:
    agent, client = orchestrator([tool_call_response("get_system_capabilities"), empty_response(),
                                  final_response(ANSWER)])
    assert agent.run(request()).status == "COMPLETED"
    assert client.payloads[2]["tools"] and last_user_text(client.payloads[2]) == EMPTY_TURN_NOTE


def test_retries_are_bounded_then_the_final_response_is_asked_for() -> None:
    responses = [empty_response()] * (MAX_EMPTY_TURN_RETRIES + 1) + [final_response(ANSWER)]
    agent, client = orchestrator(responses)
    assert agent.run(request()).status == "COMPLETED"
    assert FINALIZE_PREFIX in last_user_text(client.payloads[MAX_EMPTY_TURN_RETRIES + 1])
