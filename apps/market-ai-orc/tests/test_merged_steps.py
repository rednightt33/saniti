"""EXEC-P5 (user approval 2026-10-06, AI_ENABLE_MERGED_STEPS): the DataNeed flow's mechanical steps run in the turn of
the call that makes them due: an APPROVED data need is followed by prepare_data_bundle and open_analysis_session, and
run_python with complete=true by complete_analysis. Each runs through the same gates, budgets and tracking as a call of
the model, and is returned with the call that caused it (merged_steps)."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.orchestrator import MERGED_DONE, MERGED_STEPS_NOTE, AgentOrchestrator, build_system_prompt
from app.schemas import AgentRunRequest
from app.tools import ToolRegistry
from app.tools.registry import ToolSpec
from conftest import ScriptedClient, final_response, make_settings
from test_dataneed_orchestrator import NEED, SESSION, Tools, answer, call, completed

MERGED = {"AI_ENABLE_DATANEED": "true", "AI_ENABLE_MERGED_STEPS": "true"}


class RunArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    complete: bool | None


class MergedTools(Tools):
    """The fake DataNeed tools with run_python's complete argument; every call is counted by name."""

    def __init__(self, completions: list[dict[str, Any]], prepare: dict[str, Any] | None = None) -> None:
        super().__init__(completions)
        self.prepare = prepare
        self.calls: list[str] = []

    def registry(self) -> ToolRegistry:
        base = super().registry()
        registry = ToolRegistry()
        for name in base.names():
            spec = base.get(name)
            handler = spec.handler
            if name == "run_python":
                spec = ToolSpec(name=name, description=name, arguments_model=RunArgs, effect="COMPUTES",
                                handler=lambda a: {"execution_id": "exe_1", "session_id": SESSION, "status": "OK",
                                                   "stdout": "", "outputs": []})
                handler = spec.handler
            if name == "prepare_data_bundle" and self.prepare is not None:
                handler = lambda a, result=self.prepare: result  # noqa: E731

            def counted(arguments: BaseModel, name: str = name, handler: Any = handler) -> dict[str, Any]:
                self.calls.append(name)
                return handler(arguments)
            registry.register(ToolSpec(name=name, description=spec.description, arguments_model=spec.arguments_model,
                                       handler=counted, effect=spec.effect))
        return registry


def run(script: list, tools: MergedTools, **env: str):
    scripted = ScriptedClient(script)
    orchestrator = AgentOrchestrator(make_settings(**{**MERGED, **env}), scripted, tools.registry())
    return orchestrator.run(AgentRunRequest(request_id="dn", message="Berapa return YTD BBCA dan BBRI?")), scripted


def outputs(scripted: ScriptedClient) -> list[dict[str, Any]]:
    return [json.loads(i["output"]) for i in scripted.payloads[-1]["input"] if i.get("type") == "function_call_output"]


def test_an_approved_need_opens_the_session_and_complete_true_releases_the_results() -> None:
    tools = MergedTools([completed()])
    script = [call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None}, "c1"),
              call("run_python", {"session_id": SESSION, "complete": True}, "c2"),
              final_response(answer("BBCA naik lebih tinggi dari BBRI."))]
    result, scripted = run(script, tools)
    assert result.status == "COMPLETED"
    assert tools.calls == ["submit_data_need_spec", "prepare_data_bundle", "open_analysis_session", "run_python",
                           "complete_analysis"]
    assert result.execution.iterations == 3  # was 6: prepare, open and complete were turns of their own
    submitted, ran = outputs(scripted)
    assert [m["tool"] for m in submitted["merged_steps"]] == ["prepare_data_bundle", "open_analysis_session"]
    assert submitted["merged_steps"][1]["result"]["session_id"] == SESSION
    assert submitted["merged_note"] == MERGED_STEPS_NOTE
    assert [m["tool"] for m in ran["merged_steps"]] == ["complete_analysis"]
    assert ran["merged_steps"][0]["result"]["status"] == "COMPLETED"


def test_without_complete_the_session_stays_open_for_more_code() -> None:
    tools = MergedTools([completed()])
    script = [call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None}, "c1"),
              call("run_python", {"session_id": SESSION, "complete": None}, "c2"),
              call("complete_analysis", {"session_id": SESSION}, "c3"),
              final_response(answer("BBCA naik lebih tinggi dari BBRI."))]
    result, _ = run(script, tools)
    assert result.status == "COMPLETED" and tools.calls.count("complete_analysis") == 1
    assert tools.calls[-1] == "complete_analysis"


def test_a_bundle_that_is_not_ready_stops_the_chain_and_the_tool_stays_to_retry() -> None:
    rejected = {"status": "REJECTED", "stage": "SQL_GOVERNOR", "code": "COST_LIMIT", "next_action": "RETRY"}
    tools = MergedTools([completed()], prepare=rejected)
    script = [call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None}, "c1"),
              final_response(answer("Datanya belum bisa diambil.", "LIMITATION", ["COST_LIMIT"]))]
    result, scripted = run(script, tools)
    assert tools.calls == ["submit_data_need_spec", "prepare_data_bundle"]  # no session on a bundle that failed
    merged = outputs(scripted)[0]["merged_steps"]
    assert [m["tool"] for m in merged] == ["prepare_data_bundle"] and merged[0]["result"]["code"] == "COST_LIMIT"
    assert result.status == "LIMITED"


def test_a_second_need_while_a_session_is_open_is_prepared_but_not_opened() -> None:
    """M102 (golden test 2026-10-07, variant_bbca turn 2): four needs submitted one after another each opened a session,
    and each open closed the session of the need before (one open session per run, S08)."""
    tools = MergedTools([completed()])
    script = [call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None}, "c1"),
              call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None}, "c2"),
              final_response(answer("BBCA naik lebih tinggi dari BBRI.", "LIMITATION", ["belum selesai"]))]
    _, scripted = run(script, tools)
    assert tools.calls == ["submit_data_need_spec", "prepare_data_bundle", "open_analysis_session",
                           "submit_data_need_spec", "prepare_data_bundle"]
    assert [m["tool"] for m in outputs(scripted)[1]["merged_steps"]] == ["prepare_data_bundle"]


def test_the_switch_off_keeps_every_step_a_turn_of_its_own() -> None:
    tools = MergedTools([completed()])
    script = [call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None}, "c1"),
              final_response(answer("BBCA naik.", "LIMITATION", ["belum selesai"]))]
    run(script, tools, AI_ENABLE_MERGED_STEPS="false")
    assert tools.calls == ["submit_data_need_spec"]


class SandboxNextActions(MergedTools):
    """The fake results with the next_action the sandbox writes into each of them."""
    NEXT = {"submit_data_need_spec": "PREPARE_DATA_BUNDLE", "prepare_data_bundle": "OPEN_ANALYSIS_SESSION",
            "open_analysis_session": "RUN_PYTHON", "run_python": "RUN_PYTHON_OR_COMPLETE_ANALYSIS"}

    def registry(self) -> ToolRegistry:
        base = super().registry()
        registry = ToolRegistry()
        for name in base.names():
            spec = base.get(name)

            def handler(arguments: BaseModel, name: str = name, inner: Any = spec.handler) -> dict[str, Any]:
                result = inner(arguments)
                return {**result, "next_action": self.NEXT[name]} if name in self.NEXT else result
            registry.register(ToolSpec(name=name, description=spec.description, arguments_model=spec.arguments_model,
                                       handler=handler, effect=spec.effect))
        return registry


def test_with_the_envelope_the_model_sees_the_merged_steps_and_no_step_points_back_at_itself() -> None:
    """M101 (golden test 2026-10-07): the envelope showed only the caller's result, whose next_action still named the
    step the backend had just run, and the model called every merged step again."""
    tools = SandboxNextActions([completed()])
    script = [call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None}, "c1"),
              call("run_python", {"session_id": SESSION, "complete": True}, "c2"),
              final_response(answer("BBCA naik lebih tinggi dari BBRI."))]
    result, scripted = run(script, tools, AI_ENABLE_TOOL_ENVELOPE="true")
    assert result.status == "COMPLETED"
    submitted, ran = outputs(scripted)
    assert submitted["data"]["next_action"] == "RUN_PYTHON"  # the open session's, not PREPARE_DATA_BUNDLE
    assert [m["tool"] for m in submitted["merged_steps"]] == ["prepare_data_bundle", "open_analysis_session"]
    assert submitted["merged_steps"][0]["data"]["next_action"] == MERGED_DONE
    assert submitted["merged_steps"][1]["data"]["session_id"] == SESSION
    assert submitted["merged_note"] == MERGED_STEPS_NOTE
    assert ran["data"]["next_action"] == "ANSWER_FROM_RELEASED_OUTPUTS"  # complete_analysis's own
    assert [m["tool"] for m in ran["merged_steps"]] == ["complete_analysis"]
    assert all(m["status"] == "OK" and "meta" not in m for m in submitted["merged_steps"] + ran["merged_steps"])


def test_the_prompt_and_the_tools_describe_the_merged_steps_only_with_the_switch() -> None:
    on = build_system_prompt(False, dataneed=True, merged_steps=True)
    off = build_system_prompt(False, dataneed=True)
    assert "merged_steps" in on and "merged_steps" not in off
    assert "complete true on the last" in on
    from app.tools.data_need import MERGED_APPROVAL, data_need_specs
    from app.tools.session import session_specs

    class Client:  # never called while the specs are built
        pass

    merged = {s.name: s for s in session_specs(Client(), timeout_seconds=1, execution_timeout_seconds=1,
                                               max_result_bytes=1000, merged_steps=True)}
    plain = {s.name: s for s in session_specs(Client(), timeout_seconds=1, execution_timeout_seconds=1,
                                              max_result_bytes=1000)}
    assert "complete" in merged["run_python"].arguments_model.model_fields
    assert "complete" not in plain["run_python"].arguments_model.model_fields
    assert MERGED_APPROVAL in data_need_specs(Client(), timeout_seconds=1, max_result_bytes=1000,
                                              merged_steps=True)[0].description
    assert NEED  # the fake flow's need id is what the backend passes to prepare_data_bundle
