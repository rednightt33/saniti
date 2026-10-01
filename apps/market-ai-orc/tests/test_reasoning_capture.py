"""AI_CAPTURE_REASONING (user decision 2026-10-01): the model's reasoning text in the service log, never elsewhere."""
from __future__ import annotations

import json
import logging

from app import reasoning_capture
from app.audit_outbox import sanitize
from conftest import ANSWER, final_response, tool_call_response
from test_orchestrator import ListHandler, orchestrator, request


def run_logged(responses: list, **settings: str) -> tuple[list[dict], list[dict]]:
    agent, client = orchestrator(responses, **settings)
    service_logger = logging.getLogger("market_ai_orc")
    handler, previous = ListHandler(), service_logger.level
    service_logger.addHandler(handler)
    service_logger.setLevel(logging.INFO)
    try:
        agent.run(request("question"))
    finally:
        service_logger.removeHandler(handler)
        service_logger.setLevel(previous)
    return [json.loads(m) for m in handler.messages], client.payloads


def with_reasoning(response: dict, text: str) -> dict:
    response["output"].insert(0, {"type": "reasoning", "content": [{"type": "reasoning_text", "text": text}],
                                  "summary": []})
    return response


def test_off_by_default_logs_no_reasoning() -> None:
    events, _ = run_logged([tool_call_response("get_system_capabilities"), final_response(ANSWER)])
    assert not [e for e in events if e["event"] == "ai_model_reasoning"]
    assert "hidden" not in json.dumps(events)


def test_on_logs_each_call_with_its_form_and_tools() -> None:
    events, payloads = run_logged([tool_call_response("get_system_capabilities"),
                                   with_reasoning(final_response(ANSWER), "Saya cek kolom net_value_1d dulu.")],
                                  AI_CAPTURE_REASONING="true")
    logged = [e for e in events if e["event"] == "ai_model_reasoning"]
    assert [(e["iteration"], e["form"], e["text"]) for e in logged] == [
        (1, "SUMMARY", "hidden"), (2, "TEXT", "Saya cek kolom net_value_1d dulu.")]
    assert logged[0]["tools_requested"] == ["get_system_capabilities"] and logged[1]["tools_requested"] == []
    assert logged[0]["reasoning_tokens"] == 5
    # the reasoning is never replayed to the model
    assert all("hidden" not in json.dumps(p["input"]) for p in payloads)


def test_long_reasoning_is_split_and_capped() -> None:
    lines: list[dict] = []
    text = "x" * (reasoning_capture.MAX_CHARS + 10)
    reasoning_capture.log_reasoning(lambda event, **f: lines.append(f), with_reasoning(final_response(ANSWER), text),
                                    request_id="r", iteration=1, tools_requested=[], reasoning_tokens=0)
    assert len(lines) == reasoning_capture.MAX_CHARS // reasoning_capture.PART_CHARS
    assert all(len(line["text"]) <= reasoning_capture.PART_CHARS for line in lines)
    assert lines[0]["truncated"] is True and lines[0]["chars"] == len(text)
    assert [line["part"] for line in lines] == list(range(1, len(lines) + 1))


def test_forms_without_readable_text_are_still_logged() -> None:
    assert reasoning_capture.reasoning_text({"output": [{"type": "reasoning", "encrypted_content": "e"}]}) == (
        "", "ENCRYPTED")
    assert reasoning_capture.reasoning_text(final_response(ANSWER)) == ("", "NONE")
    chat = {"choices": [{"message": {"content": "{}", "reasoning": "pikir"}}]}
    assert reasoning_capture.reasoning_text(chat) == ("pikir", "TEXT")
    lines: list[dict] = []
    reasoning_capture.log_reasoning(lambda event, **f: lines.append(f), final_response(ANSWER), request_id="r",
                                    iteration=3, tools_requested=[], reasoning_tokens=0)
    assert lines == [{"request_id": "r", "iteration": 3, "form": "NONE", "part": 1, "parts": 1, "chars": 0,
                      "truncated": False, "reasoning_tokens": 0, "tools_requested": [], "text": ""}]


def test_the_audit_payload_still_drops_reasoning() -> None:
    assert sanitize({"reasoning": "x", "ok": 1}) == {"ok": 1}
