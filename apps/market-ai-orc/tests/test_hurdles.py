"""EXEC-FRICTION (M142): one rule for what a tool outcome counts as refused or failed (friction.refusal), and the
run's hurdles in plain words (execution.hurdles), whether or not run memory is on."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app import friction
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest
from app.tools import ToolRegistry, ToolSpec
from app.tools.registry import ToolOutcome, error_outcome
from conftest import ANSWER, ScriptedClient, final_response, make_settings, tool_call_response


class Code(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str


def ok(name: str, result: dict) -> ToolOutcome:
    return ToolOutcome(call_id="c", name=name, ok=True, output={"ok": True, "tool": name, "result": result})


def test_refusal_names_a_refused_data_need_by_its_issue_codes() -> None:
    found = friction.refusal(ok("submit_data_need_spec", {"status": "REVISION_REQUIRED", "issues": [
        {"code": "RELATIONSHIP_KEY_MISMATCH", "field_path": "relationships[0].left_columns"},
        {"code": "INVALID_REQUEST_ID", "field_path": "data_requests[0].data_request_id"}]}))
    assert found["kind"] == "REJECTED" and found["code"] == "RELATIONSHIP_KEY_MISMATCH, INVALID_REQUEST_ID"
    assert "RELATIONSHIP_KEY_MISMATCH" in found["message"]


def test_refusal_tells_a_failed_execution_from_a_rejection_and_ignores_success() -> None:
    assert friction.refusal(ok("run_python", {"status": "SCRIPT_ERROR"}))["kind"] == "FAILED_EXECUTION"
    assert friction.refusal(error_outcome("c", "lookup", "INVALID_ARGUMENTS", "bad"))["code"] == "INVALID_ARGUMENTS"
    assert friction.refusal(ok("run_python", {"status": "OK"})) is None
    assert friction.refusal(ok("submit_data_need_spec", {"status": "APPROVED", "need_id": "n"})) is None


def registry(results: dict[str, list[dict]]) -> ToolRegistry:
    reg = ToolRegistry()
    for name, queue in results.items():
        reg.register(ToolSpec(name=name, description="test", arguments_model=Code,
                              handler=lambda args, queue=queue: queue.pop(0)))
    return reg


def run(script: list, results: dict[str, list[dict]]):
    agent = AgentOrchestrator(make_settings(), ScriptedClient(script), registry(results))
    return agent.run(AgentRunRequest.model_validate({"request_id": "req-h", "message": "Hitung sesuatu"}))


def test_a_failed_run_that_later_succeeds_is_a_hurdle_overcome() -> None:
    result = run([tool_call_response("run_python", '{"code": "x"}', call_id="a", response_id="r1"),
                  tool_call_response("run_python", '{"code": "y"}', call_id="b", response_id="r2"),
                  final_response(ANSWER)],
                 {"run_python": [{"status": "SCRIPT_ERROR", "error_type": "KeyError"}, {"status": "OK"}]})
    hurdles = result.execution.hurdles
    assert [(h["stage"], h["name"], h["code"], h["outcome"], h["overcome"]) for h in hurdles] == [
        ("TOOL", "run_python", "SCRIPT_ERROR", "FAILED", True)]
    assert hurdles[0]["text"] == "Kode analisis gagal dijalankan (kode berhenti karena galat), lalu diperbaiki."
    assert result.execution.friction["failed_executions"] == 1


def test_a_refused_data_need_is_a_hurdle_even_without_run_memory() -> None:
    result = run([tool_call_response("submit_data_need_spec", '{"code": "x"}', call_id="a", response_id="r1"),
                  final_response(ANSWER)],
                 {"submit_data_need_spec": [{"status": "REVISION_REQUIRED", "issues": [
                     {"code": "RELATIONSHIP_KEY_MISMATCH", "field_path": "relationships[0].left_columns"}]}]})
    (hurdle,) = result.execution.hurdles
    assert hurdle["code"] == "RELATIONSHIP_KEY_MISMATCH" and hurdle["overcome"] is False
    assert hurdle["text"] == "Permintaan data ditolak (kunci penggabungan tabel tidak sesuai), belum teratasi."


def test_a_run_without_refusals_has_no_hurdles() -> None:
    result = run([tool_call_response("run_python", '{"code": "x"}', call_id="a", response_id="r1"),
                  final_response(ANSWER)], {"run_python": [{"status": "OK"}]})
    assert result.execution.hurdles is None
    assert "hurdles" not in result.execution.model_dump()


def test_a_bare_status_is_not_shown_as_the_reason() -> None:
    """Run A 2026-10-12: a lookup refused with only the status REJECTED read "ditolak (rejected)"."""
    from app.user_texts import hurdle_text
    assert hurdle_text("TOOL", "get_dimension_values", "REJECTED", "REFUSED", False) == \
        "Satu langkah kerja ditolak, belum teratasi."
    assert hurdle_text("TOOL", "submit_data_need_spec", "RELATIONSHIP_KEY_MISMATCH", "REFUSED", True) == \
        "Permintaan data ditolak (kunci penggabungan tabel tidak sesuai), lalu diperbaiki."
