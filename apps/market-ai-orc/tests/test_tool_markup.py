"""M146 (EXEC-M146, user go 2026-10-13): deepseek-v4.1-flash sometimes wrote its tool call as DSML markup in the text
("<｜DSML｜ calls><｜DSML｜ invoke name=...>") and the provider passed it on with no tool call (ab5 in the EXEC-TABLE
A/B, ON and OFF). The orchestrator took it for a malformed final answer, asked for the final response, and the run
ended as a LIMITATION without its data request ever running. Such a turn is now asked again with the same tools."""
from __future__ import annotations

from app import user_texts as texts
from app.orchestrator import FINALIZE_PREFIX, MAX_TOOL_MARKUP_RETRIES, TOOL_MARKUP_NOTE
from conftest import ANSWER, final_response, tool_call_response
from test_empty_turn import last_user_text
from test_orchestrator import orchestrator, request

DSML = ('<｜DSML｜ calls>\n<｜DSML｜ invoke name="get_system_capabilities">\n<｜DSML｜ parameter name="x" '
        'string="true">1</｜DSML｜ parameter>\n</｜DSML｜ invoke>\n</｜DSML｜ calls>')


def markup_response(text: str = DSML) -> dict:
    return final_response(text, response_id="resp_markup")


def test_a_tool_call_written_as_text_is_asked_again_with_its_tools() -> None:
    agent, client = orchestrator([markup_response(), tool_call_response("get_system_capabilities"),
                                  final_response(ANSWER)])
    result = agent.run(request())
    assert result.status == "COMPLETED" and result.response.response_type == "ANSWER"
    retry = client.payloads[1]
    assert retry["tools"] and last_user_text(retry) == TOOL_MARKUP_NOTE.format(tool="get_system_capabilities")
    assert not any(FINALIZE_PREFIX in str(i.get("content")) for i in retry["input"])
    hurdles = result.execution.hurdles or []
    assert any(h["name"] == "TOOL_MARKUP" and h["overcome"] for h in hurdles)
    assert "a tool call was written as text" in texts.hurdle_text("FORMAT", "TOOL_MARKUP", None, "ASKED_AGAIN",
                                                                         True)


def test_retries_are_bounded_then_the_final_response_is_asked_for() -> None:
    responses = [markup_response()] * (MAX_TOOL_MARKUP_RETRIES + 1) + [final_response(ANSWER)]
    agent, client = orchestrator(responses)
    agent.run(request())
    assert FINALIZE_PREFIX in last_user_text(client.payloads[MAX_TOOL_MARKUP_RETRIES + 1])


def test_text_that_only_mentions_invoke_is_a_draft_answer_as_before() -> None:
    agent, client = orchestrator([markup_response('The broker will invoke name="x" later.'), final_response(ANSWER)])
    agent.run(request())
    assert FINALIZE_PREFIX in last_user_text(client.payloads[1])
