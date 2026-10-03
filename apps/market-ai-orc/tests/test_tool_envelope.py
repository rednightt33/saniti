"""ENV (round 2026-10-03, ROUND_PLAN_2026-10-03.md A2): the standard envelope of tool results, and a next action for
every error code the orchestrator can raise (derived from the code, so a new code without an entry fails here)."""
from __future__ import annotations

import ast
from pathlib import Path

from app.tools.envelope import ERROR_ACTIONS, envelope
from app.tools.registry import ToolOutcome, error_outcome

APP = Path(__file__).resolve().parents[1] / "app"


def _raised_codes() -> set[str]:
    codes: set[str] = {"TOOL_ERROR"}
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "error_outcome" and len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
                codes.add(node.args[2].value)
            if name == "ToolError":
                codes.update(k.value.value for k in node.keywords
                             if k.arg == "code" and isinstance(k.value, ast.Constant))
    return codes


def test_every_error_code_the_orchestrator_raises_has_a_next_action() -> None:
    missing = sorted(_raised_codes() - set(ERROR_ACTIONS))
    assert not missing, f"add these codes to ERROR_ACTIONS: {missing}"


def test_a_registry_error_becomes_an_error_with_its_next_action() -> None:
    view = envelope(error_outcome("c1", "run_python", "INVALID_ARGUMENTS", "code is required"), duration_ms=3)
    assert view["status"] == "ERROR" and view["data"] is None
    assert view["errors"] == [{"code": "INVALID_ARGUMENTS", "message": "code is required", "retryable": True,
                               "next_action": "FIX_ARGUMENTS"}]
    assert view["meta"] == {"call_id": "c1", "duration_ms": 3, "truncated": False}


def test_a_rejection_inside_a_result_keeps_the_tools_own_next_action() -> None:
    result = {"status": "REJECTED", "error": {"code": "SESSION_CAPACITY_EXCEEDED", "message": "full"},
              "next_action": "REPORT_LIMITATION"}
    view = envelope(ToolOutcome("c2", "open_analysis_session", True, {"ok": True, "tool": "x", "result": result}))
    assert view["status"] == "REJECTED" and view["data"] == result
    assert view["errors"][0]["next_action"] == "REPORT_LIMITATION" and view["errors"][0]["retryable"] is True


def test_a_plain_result_is_ok_and_a_cut_preview_is_partial() -> None:
    ok = envelope(ToolOutcome("c3", "discover_catalog", True, {"ok": True, "tool": "x", "result": {"items": []}}))
    assert ok["status"] == "OK" and ok["errors"] == [] and ok["meta"]["truncated"] is False
    cut = {"outputs": [{"output_id": "out_1", "rows": [], "rows_truncated": True}]}
    part = envelope(ToolOutcome("c4", "complete_analysis", True, {"ok": True, "tool": "x", "result": cut}))
    assert part["status"] == "PARTIAL" and part["meta"]["truncated"] is True


def test_registry_extras_become_warnings() -> None:
    output = {"ok": True, "tool": "x", "result": {}, "ignored_arguments": ["dummy"]}
    view = envelope(ToolOutcome("c5", "get_system_capabilities", True, output))
    assert view["warnings"] == [{"code": "IGNORED_ARGUMENTS", "fields": ["dummy"]}]


def test_an_unknown_capacity_code_is_retryable() -> None:
    result = {"status": "REJECTED", "error": {"code": "QUEUE_FULL_SOMEWHERE", "message": "later"}}
    view = envelope(ToolOutcome("c6", "x", True, {"ok": True, "tool": "x", "result": result}))
    assert view["errors"][0]["retryable"] is True and view["errors"][0]["next_action"] == "WAIT_AND_RETRY"


def test_the_model_reads_enveloped_results_and_the_rule_when_the_flag_is_on() -> None:
    import json

    from conftest import ScriptedClient, final_response, make_settings, tool_call_response

    from app.orchestrator import TOOL_ENVELOPE_RULE, AgentOrchestrator
    from app.schemas import AgentRunRequest
    from app.tools import build_default_registry

    answer = {"response_type": "LIMITATION", "answer": "No data tools.", "clarification_question": None,
              "assumptions": [], "limitations": ["none"]}
    client = ScriptedClient([tool_call_response("get_system_capabilities", "{}", call_id="c1"),
                             tool_call_response("no_such_tool", "{}", call_id="c2"), final_response(answer)])
    agent = AgentOrchestrator(make_settings(AI_ENABLE_TOOL_ENVELOPE="true"), client, build_default_registry())
    agent.run(AgentRunRequest(request_id="r_env", message="What can you do?"))
    assert TOOL_ENVELOPE_RULE in client.payloads[0]["instructions"]
    outputs = [json.loads(i["output"]) for i in client.payloads[2]["input"] if i.get("type") == "function_call_output"]
    assert outputs[0]["status"] == "OK" and outputs[0]["tool"] == "get_system_capabilities" and "data" in outputs[0]
    assert outputs[1]["status"] == "ERROR" and outputs[1]["errors"][0]["code"] == "UNKNOWN_TOOL"
    assert outputs[1]["errors"][0]["next_action"] == "USE_LISTED_TOOLS"
