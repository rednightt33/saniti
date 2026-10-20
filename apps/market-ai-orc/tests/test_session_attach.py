"""PLAN 14 (user 2026-10-15, go "Ok jalankan"): a later data need of the same answer joins its open analysis session.
With merged steps, a need sent with attach_to_session_id is prepared and its bundle attached to that session instead
of a new one; a refused attach falls back to a session of its own with the reason; an id that is not an open session
of this answer opens a new session as before; an attached need the analysis never read leaves the data record; the
switch off (no attach_data_bundle registered) keeps the old flow; a research desk never offers the tool."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from app import data_record as records
from app import tool_desks
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest
from app.tools import ToolRegistry
from app.tools.data_need import SubmitDataNeedSpecArgs, with_attach
from app.tools.registry import ToolSpec
from conftest import ScriptedClient, final_response, make_settings
from test_dataneed_orchestrator import SESSION, answer, call, completed

MERGED = {"AI_ENABLE_DATANEED": "true", "AI_ENABLE_MERGED_STEPS": "true", "AI_ENABLE_SESSION_ATTACH": "true"}
NEEDS = ["need_" + "1" * 24, "need_" + "6" * 24]
BUNDLES = ["bundle_" + "2" * 24, "bundle_" + "7" * 24]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpecArgs(Strict):
    mode: str
    research_governance: None
    attach_to_session_id: str | None


class NeedArgs(Strict):
    need_id: str


class BundleArgs(Strict):
    input_bundle_id: str


class SessionArgs(Strict):
    session_id: str


class AttachArgs(Strict):
    session_id: str
    input_bundle_id: str


class AttachTools:
    def __init__(self, attach: dict[str, Any] | None = None, completion: dict[str, Any] | None = None,
                 offer_attach: bool = True) -> None:
        self.attach = attach
        self.completion = completion or completed()
        self.offer_attach = offer_attach
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.submitted = 0
        self.opened = 0

    def registry(self) -> ToolRegistry:
        def submit(a):
            self.submitted += 1
            return {"status": "APPROVED", "need_id": NEEDS[self.submitted - 1], "revision": 1,
                    "research_governance": None}

        def prepare(a):
            return {"status": "READY", "input_bundle_id": BUNDLES[NEEDS.index(a.need_id)],
                    "datasets": [{"data_request_id": f"data_request_{NEEDS.index(a.need_id) + 1}", "rows": 10}]}

        def open_session(a):
            self.opened += 1
            return {"session_id": SESSION if self.opened == 1 else "sess_" + "8" * 24, "status": "ACTIVE",
                    "bundle_id": a.input_bundle_id, "need_id": NEEDS[BUNDLES.index(a.input_bundle_id)]}

        def attach(a):
            return self.attach or {"session_id": a.session_id, "status": "ACTIVE", "attached": True,
                                   "bundle_id": a.input_bundle_id, "need_id": NEEDS[1], "attachments": 1,
                                   "max_attachments": 2}

        specs = [("submit_data_need_spec", SpecArgs, submit, "FETCHES_DATA"),
                 ("prepare_data_bundle", NeedArgs, prepare, "FETCHES_DATA"),
                 ("open_analysis_session", BundleArgs, open_session, "COMPUTES"),
                 ("run_python", SessionArgs, lambda a: {"execution_id": "exe_1", "session_id": a.session_id,
                                                        "status": "OK", "stdout": "", "outputs": []}, "COMPUTES"),
                 ("complete_analysis", SessionArgs, lambda a: self.completion, "COMPUTES")]
        if self.offer_attach:
            specs.append(("attach_data_bundle", AttachArgs, attach, "COMPUTES"))
        registry = ToolRegistry()
        for name, model, handler, effect in specs:
            def counted(arguments: BaseModel, name: str = name, handler: Any = handler) -> dict[str, Any]:
                self.calls.append((name, arguments.model_dump()))
                return handler(arguments)
            registry.register(ToolSpec(name=name, description=name, arguments_model=model, handler=counted,
                                       effect=effect))
        return registry


def run(script: list, tools: AttachTools, **env: str):
    scripted = ScriptedClient(script)
    orchestrator = AgentOrchestrator(make_settings(**{**MERGED, **env}), scripted, tools.registry())
    result = orchestrator.run(AgentRunRequest(request_id="att", message="Akumulasi broker BBRI dan harganya?"))
    return result, scripted, orchestrator


def outputs(scripted: ScriptedClient) -> list[dict[str, Any]]:
    return [json.loads(i["output"]) for i in scripted.payloads[-1]["input"] if i.get("type") == "function_call_output"]


def need(attach: str | None) -> dict[str, Any]:
    return {"mode": "ANALYSIS", "research_governance": None, "attach_to_session_id": attach}


def test_a_later_need_joins_the_open_session_instead_of_a_new_one() -> None:
    tools = AttachTools()
    script = [call("submit_data_need_spec", need(None), "c1"),
              call("submit_data_need_spec", need(SESSION), "c2"),
              final_response(answer("Belum selesai.", "LIMITATION", ["x"]))]
    run(script, tools)
    names = [n for n, _ in tools.calls]
    assert names == ["submit_data_need_spec", "prepare_data_bundle", "open_analysis_session",
                     "submit_data_need_spec", "prepare_data_bundle", "attach_data_bundle"]
    assert tools.calls[-1][1] == {"session_id": SESSION, "input_bundle_id": BUNDLES[1]}
    assert tools.opened == 1


def test_a_refused_attach_opens_a_session_of_its_own_with_the_reason() -> None:
    refused = {"status": "REJECTED", "code": "ATTACH_TOO_LARGE", "message": "too large",
               "next_action": "OPEN_ANALYSIS_SESSION"}
    tools = AttachTools(attach=refused)
    script = [call("submit_data_need_spec", need(None), "c1"),
              call("submit_data_need_spec", need(SESSION), "c2"),
              final_response(answer("Belum selesai.", "LIMITATION", ["x"]))]
    _, scripted, _ = run(script, tools)
    assert [n for n, _ in tools.calls][-2:] == ["attach_data_bundle", "open_analysis_session"]
    merged = outputs(scripted)[1]["merged_steps"]
    assert [m["tool"] for m in merged] == ["prepare_data_bundle", "attach_data_bundle", "open_analysis_session"]
    assert "ATTACH_TOO_LARGE" in merged[1]["attach_note"] and "new session" in merged[1]["attach_note"]


def test_an_id_that_is_not_an_open_session_of_this_answer_opens_a_new_session() -> None:
    tools = AttachTools()
    other = "sess_" + "9" * 24
    script = [call("submit_data_need_spec", need(other), "c1"),
              final_response(answer("Belum selesai.", "LIMITATION", ["x"]))]
    _, scripted, _ = run(script, tools)
    assert [n for n, _ in tools.calls] == ["submit_data_need_spec", "prepare_data_bundle", "open_analysis_session"]
    merged = outputs(scripted)[0]["merged_steps"]
    assert other in merged[0]["attach_note"]


def test_without_the_attach_tool_the_old_flow_runs() -> None:
    tools = AttachTools(offer_attach=False)
    script = [call("submit_data_need_spec", need(None), "c1"),
              call("submit_data_need_spec", need(SESSION), "c2"),
              final_response(answer("Belum selesai.", "LIMITATION", ["x"]))]
    run(script, tools)
    assert [n for n, _ in tools.calls] == ["submit_data_need_spec", "prepare_data_bundle", "open_analysis_session"] * 2


def test_an_attached_need_never_read_leaves_the_data_record(monkeypatch) -> None:
    completion = completed(attachments=[{"need_id": NEEDS[1], "bundle_id": BUNDLES[1], "status": "UNUSED"}])
    tools = AttachTools(completion=completion)
    script = [call("submit_data_need_spec", need(None), "c1"),
              call("submit_data_need_spec", need(SESSION), "c2"),
              call("complete_analysis", {"session_id": SESSION}, "c3"),
              final_response(answer("BBRI naik."))]
    record = records.empty()
    for need_id in NEEDS:
        records.add_need(record, "att", {"need_id": need_id, "approved": {"requests": []}})
    records.drop_need(record, NEEDS[1])
    assert [n["need_id"] for n in record["needs"]] == [NEEDS[0]]
    dropped: list[str] = []
    original = records.drop_need
    monkeypatch.setattr(records, "drop_need", lambda rec, need_id: (dropped.append(need_id), original(rec, need_id)))
    result, _, _ = run(script, tools)
    assert result.status == "COMPLETED" and dropped == [NEEDS[1]]


def test_the_attach_argument_and_tool_exist_only_with_the_switch_and_never_on_a_research_desk() -> None:
    attached = with_attach(SubmitDataNeedSpecArgs)
    assert "attach_to_session_id" in attached.model_json_schema()["properties"]
    assert "attach_to_session_id" not in SubmitDataNeedSpecArgs.model_json_schema()["properties"]
    registered = frozenset({"attach_data_bundle", "open_analysis_session", "submit_data_need_spec", "run_python",
                            "prepare_data_bundle", "complete_analysis"})
    effect = {"attach_data_bundle": "COMPUTES"}.get
    for desk in ("FASTLANE", "ANALYSIS", "CONTINUE"):
        assert "attach_data_bundle" in tool_desks.tools(desk, registered, effect)
    for desk in ("RESEARCH_V1", "RESEARCH_V2", "PLAN", "CHAT", "FACT", "READ"):
        assert "attach_data_bundle" not in tool_desks.tools(desk, registered, effect)


def test_attaching_keeps_research_findings_and_the_hypothesis_plan_detected() -> None:
    """Live 2026-10-15 (orc `bb3738ea`): turning AI_ENABLE_SESSION_ATTACH on logged hypothesis_plan_inactive, because
    findings v1 was detected from the submit arguments' class name, which with_attach renames (…FindingsAttach). It is
    read from the governance field now, whatever wraps the arguments."""
    from app.tools.data_need import (SubmitDataNeedSpecArgsFindings, SubmitDataNeedSpecArgsPITFindings,
                                     SubmitDataNeedSpecArgsV2Findings, declares_findings)
    for model in (SubmitDataNeedSpecArgsFindings, SubmitDataNeedSpecArgsV2Findings, SubmitDataNeedSpecArgsPITFindings):
        assert declares_findings(model) and declares_findings(with_attach(model))
    assert not declares_findings(SubmitDataNeedSpecArgs) and not declares_findings(with_attach(SubmitDataNeedSpecArgs))


def test_with_the_tool_envelope_the_note_reaches_the_model_as_a_warning() -> None:
    """M193 (user 2026-10-19 "OK masukan exec"; sanity run edge_43d32073…-m4n): the envelope rebuilt each merged step
    from its result and dropped attach_note, so the model never learnt the data went to a new session."""
    tools = AttachTools()
    other = "sess_" + "9" * 24
    script = [call("submit_data_need_spec", need(other), "c1"),
              final_response(answer("Belum selesai.", "LIMITATION", ["x"]))]
    _, scripted, _ = run(script, tools, AI_ENABLE_TOOL_ENVELOPE="true")
    merged = outputs(scripted)[0]["merged_steps"]
    warnings = [w for step in merged for w in step.get("warnings") or []]
    assert any(w["code"] == "SESSION_NOT_ATTACHED" and other in w["message"] for w in warnings), merged
