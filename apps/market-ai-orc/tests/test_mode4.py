"""Mode 4 (user decision 2026-09-30, app/mode4.py): the analysis answers first, research of at least two angles built
on it runs at once, and one follow-up angle is proposed; an approval runs it and proposes the next one. A new
question cancels a pending suggestion; an explicit count is obeyed; ANALYSIS and RESEARCH are unchanged."""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.config import ConfigError
from app.conversation_plans import advance
from app.mode4 import Mode4Orchestrator, requested_count
from app.orchestrator import AgentOrchestrator
from app.research_plan_v2 import ContinuationInV2, ContinuationOutV2, ResearchPlanV2, current_angle_bounds
from app.schemas import (AgentRunRequest, AgentRunResponse, AnalysisPathExecution, ExecutionMetadata, FinalResponse,
                         ResearchPlanExecution)
from conftest import ScriptedClient, final_response, make_settings
from test_multi_angle import (MA, QUESTION, RUN_SCRIPT, Clock, RunSandbox, angles, call, feasibility_args,
                              findings_answer, ma_registry, plan_response, plan_v2, request, requirement)

MODE4 = {**MA, "AI_ENABLE_ANALYSIS_PATH": "true", "AI_ENABLE_MODE4": "true"}
ANALYSIS = {"response_type": "ANSWER", "answer": "Broker yang paling sering membeli saham bank saat pasar turun "
            "tajam adalah broker asing besar.", "clarification_question": None, "assumptions": ["Hari crash."],
            "limitations": ["Deskriptif."], "research_plan": None, "research_findings": None}


BROKER = "Siapa broker yang konsisten membeli saham bank ketika pasar jatuh?"


def one_angle_feasibility() -> dict[str, Any]:
    return feasibility_args([requirement("a_fall", request("a_fall_A", columns=("ticker", "date", "close")))])


def suggestion_plan() -> dict[str, Any]:
    return {**plan_response(angles=angles()[:1]), "answer": "Usulan: uji satu sudut, penurunan besar. Setujui?"}


def mode4_agent(script: list, sandbox_min: int = 1) -> tuple[Mode4Orchestrator, ScriptedClient, RunSandbox]:
    run_sandbox = RunSandbox()
    registry = ma_registry(run_sandbox)
    registry.multi_angle["sandbox_min_angles"] = sandbox_min
    scripted = ScriptedClient(script)
    inner = AgentOrchestrator(make_settings(**MODE4), scripted, registry, wall_clock=Clock(),
                              draft_reader=lambda draft_id: None)
    return Mode4Orchestrator(inner), scripted, run_sandbox


FIRST_ROUND = [final_response(ANALYSIS),                                                      # A
               call("check_research_feasibility", feasibility_args(), "b1"), final_response(plan_response()),  # B
               *RUN_SCRIPT, final_response(findings_answer()),                                 # C
               call("check_research_feasibility", one_angle_feasibility(), "d1"),              # D
               final_response(suggestion_plan())]


def test_the_first_round_answers_runs_research_at_once_and_proposes_one_angle() -> None:
    runner, scripted, sandbox = mode4_agent(FIRST_ROUND)
    result = runner.run(AgentRunRequest(request_id="q1", conversation_id="conv_1", message=BROKER))
    assert scripted.responses == []
    steps = result.mode4["steps"]
    assert [(s["step"], s["request_id"], s["status"]) for s in steps] == [
        ("analysis", "q1-m4a", "COMPLETED"), ("research_plan", "q1-m4b", "AWAITING_CONFIRMATION"),
        ("research", "q1-m4c", "COMPLETED"), ("suggestion", "q1-m4d", "AWAITING_CONFIRMATION")]
    # the analysis request was fixed to ANALYSIS, the plan requests to RESEARCH with the analysis as context
    assert "ANALYSIS path" in str(scripted.payloads[0]["input"])
    assert "broker asing besar" in str(scripted.payloads[1]["input"]) and "RESEARCH path" in \
        str(scripted.payloads[1]["input"])
    # B's plan was approved by the backend at once and ran through the executor
    assert sandbox.governance is not None and len(sandbox.governance["angles"]) == 3
    assert steps[2]["turn"] == "EXECUTE_APPROVED"
    # D proposed exactly one angle, and the note told the model so
    assert "exactly one angle" in str(scripted.payloads[-2]["input"])
    assert result.status == "AWAITING_CONFIRMATION" and result.request_id == "q1"
    response = result.response
    assert response.response_type == "RESEARCH_PLAN_CONFIRMATION" and len(response.research_plan.angles) == 1
    assert response.answer.index("**Jawaban**") < response.answer.index("**Hasil riset**") \
        < response.answer.index("**Usulan riset berikutnya**")
    assert "broker asing besar" in response.answer and "hanya a_fall mendukung" in response.answer
    assert result.continuation.plan_id == steps[3]["plan_id"] and result.continuation.origin_request_id == "q1-m4d"
    assert result.mode4["research"]["research_findings"][0]["angle_id"] == "a_fall"
    execution = result.execution
    assert execution.analysis_path.requested == "MODE4" and execution.research_plan.turn == "PROPOSE"
    assert execution.research_plan.issued_plan_id == result.continuation.plan_id
    assert execution.iterations == len(scripted.payloads) and execution.cost is None  # the script reports no cost
    dumped = result.model_dump(mode="json")
    assert dumped["mode4"]["round"] == "FIRST" and "mode4" in dumped
    # SERVER mode keeps the suggestion pending
    state = advance({}, result, "q1", 0)
    assert state["research_plan"]["status"] == "PENDING" and state["research_plan"]["plan_id"] == \
        result.continuation.plan_id


def test_a_one_angle_plan_is_refused_without_the_mode4_bounds() -> None:
    script = [call("check_research_feasibility", one_angle_feasibility(), "c1"), *[final_response(suggestion_plan())] * 3]
    runner, scripted, _ = mode4_agent(script)
    result = runner.run(AgentRunRequest(request_id="q3", conversation_id="conv_1", message=BROKER,
                                        analysis_path="RESEARCH"))
    assert "ANGLE_COUNT_INVALID" in str(scripted.payloads[1]["input"])
    assert result.continuation is None and result.mode4 is None


def test_the_analysis_path_and_research_path_skip_mode4() -> None:
    runner, scripted, _ = mode4_agent([final_response(ANALYSIS)])
    result = runner.run(AgentRunRequest(request_id="q2", message=QUESTION, analysis_path="ANALYSIS"))
    assert result.mode4 is None and "mode4" not in result.model_dump(mode="json")
    assert result.execution.analysis_path.requested == "ANALYSIS"


# ------------------------------------------------------------------------------------------------ pipeline routing


def response(response_type: str, answer: str = "Jawaban.", **extra: Any) -> FinalResponse:
    body = {"response_type": response_type, "answer": answer, "assumptions": [], "limitations": [], **extra}
    if response_type == "CLARIFICATION":
        body["clarification_question"] = "Yang mana?"
    if response_type == "LIMITATION":
        body["limitations"] = ["Data tidak cukup."]
    return FinalResponse.model_validate(body)


def issued(plan_id: str, origin: str) -> ContinuationOutV2:
    return ContinuationOutV2.model_construct(kind="RESEARCH_PLAN", plan_version="research_plan/v2", plan_id=plan_id,
                                             origin_request_id=origin, conversation_id=None, token="t",
                                             expires_at="2026-10-01T00:00:00+00:00", research_data_plan={})


class FakeInner:
    """Stands in for AgentOrchestrator: answers each sub-run from a script keyed by the request_id suffix."""

    def __init__(self, script: dict[str, Any], classify: str = "APPROVE", sandbox_min: int = 1) -> None:
        self.script, self.classify_action = script, classify
        self.requests: list[AgentRunRequest] = []
        self.bounds: list[Any] = []
        self.settings = make_settings(**MODE4)
        self.research_limits = {"min_angles": 2, "max_angles": 6, "sandbox_min_angles": sandbox_min}
        self.analysis_path = True
        self.time = 0.0

    def clock(self) -> float:
        return self.time

    def classify_reply(self, request_id: str, message: str, plan: Any):
        return self.classify_action, None, {"status": "COMPLETED", "input_tokens": 10, "output_tokens": 2,
                                            "cost": 0.001, "latency_ms": 5}

    def run(self, request: AgentRunRequest, conversation_key: str | None = None) -> AgentRunResponse:
        self.requests.append(request)
        self.bounds.append(current_angle_bounds.get())
        suffix = request.request_id.rsplit("-", 1)[-1]
        item = self.script[suffix]
        self.time += 100
        return item(request) if callable(item) else item

    def _failed(self, state, code, message):
        return AgentRunResponse(request_id=state.request_id, status="FAILED", response=None,
                                execution=ExecutionMetadata(model="m"), error={"code": code, "message": message})


def run_result(rid: str, final: FinalResponse | None, *, status: str | None = None, turn: str | None = None,
               plan_id: str | None = None, approved: str | None = None, cost: float = 0.01) -> AgentRunResponse:
    status = status or {"ANSWER": "COMPLETED", "RESEARCH_PLAN_CONFIRMATION": "AWAITING_CONFIRMATION",
                        "LIMITATION": "LIMITED", "CLARIFICATION": "NEEDS_CLARIFICATION"}[final.response_type]
    plan_exec = ResearchPlanExecution(turn=turn, verification="VERIFIED" if turn == "EXECUTE_APPROVED"
                                      else "NOT_PRESENTED", issued_plan_id=plan_id, approved_plan_id=approved,
                                      research_submitted=True if turn == "EXECUTE_APPROVED" else None) \
        if turn else None
    return AgentRunResponse(request_id=rid, status=status, response=final,
                            execution=ExecutionMetadata(model="m", iterations=2, input_tokens=100, output_tokens=10,
                                                        total_tokens=110, cost=cost, duration_ms=1000,
                                                        research_plan=plan_exec,
                                                        analysis_path=AnalysisPathExecution(requested="ANALYSIS")),
                            evidence_label="DATA_COVERAGE_VERIFIED" if final and final.response_type == "ANSWER"
                            else None,
                            continuation=issued(plan_id, rid) if plan_id else None)


PLAN3 = ResearchPlanV2.model_validate(plan_v2())
PLAN1 = ResearchPlanV2.model_validate(plan_v2(angles=angles()[:1]))


def plan_final(plan: ResearchPlanV2, answer: str = "Usulan: satu sudut. Setujui?") -> FinalResponse:
    return response("RESEARCH_PLAN_CONFIRMATION", answer, research_plan=plan.model_dump(mode="json"))


def stub(script: dict[str, Any], **kwargs: Any) -> tuple[Mode4Orchestrator, FakeInner]:
    inner = FakeInner(script, **kwargs)
    wrapper = Mode4Orchestrator.__new__(Mode4Orchestrator)
    wrapper.inner, wrapper.min_angles, wrapper.max_angles, wrapper.sandbox_min = inner, 2, 6, \
        inner.research_limits["sandbox_min_angles"]
    return wrapper, inner


def first_round_script(**overrides: Any) -> dict[str, Any]:
    script = {
        "m4a": run_result("q-m4a", response("ANSWER", "Analisis: broker ZP.")),
        "m4b": run_result("q-m4b", plan_final(PLAN3, "Rencana tiga sudut."), turn="PROPOSE", plan_id="rp_b"),
        "m4c": run_result("q-m4c", response("ANSWER", "Riset: a_fall mendukung."), turn="EXECUTE_APPROVED",
                          approved="rp_b"),
        "m4d": run_result("q-m4d", plan_final(PLAN1), turn="PROPOSE", plan_id="rp_d"),
    }
    script.update(overrides)
    return script


def fake_continuation(action: str | None = None) -> ContinuationInV2:
    return ContinuationInV2.model_construct(kind="RESEARCH_PLAN", plan_id="rp_d", origin_request_id="q-m4d",
                                            plan=PLAN1, research_data_plan={}, token="t", action=action,
                                            revision_instruction=None)


def test_the_approval_of_step_c_is_explicit_and_carries_b_plan() -> None:
    captured = {}

    def research(request: AgentRunRequest) -> AgentRunResponse:
        captured["continuation"] = request.continuation
        return first_round_script()["m4c"]

    wrapper, inner = stub(first_round_script(m4c=research))
    result = wrapper.run(AgentRunRequest(request_id="q", conversation_id="conv", message="Siapa broker?"))
    c = captured["continuation"]
    assert c.action == "APPROVE" and c.plan_id == "rp_b" and c.origin_request_id == "q-m4b"
    assert [r.analysis_path for r in inner.requests] == ["ANALYSIS", "RESEARCH", None, "RESEARCH"]
    assert inner.bounds == [None, (2, 6), None, (1, 1)]
    assert all(r.conversation_id == "conv" for r in inner.requests)
    assert result.status == "AWAITING_CONFIRMATION" and result.execution.cost == pytest.approx(0.04)
    assert result.execution.iterations == 8 and result.execution.duration_ms == 400_000
    assert result.evidence_label == "DATA_COVERAGE_VERIFIED"


@pytest.mark.parametrize("message,kind,count", [
    ("cari 2 angle lain", "ANGLE", 2), ("kasih tiga opsi riset", "SUGGESTION", 3), ("pakai 9 sudut", "ANGLE", 6),
    ("Siapa broker yang membeli saham bank?", None, None), ("give me two more suggestions", "SUGGESTION", 2)])
def test_an_explicit_count_is_read_from_the_message(message, kind, count) -> None:
    assert requested_count(message) == ((kind, count) if kind else None)


def test_an_explicit_count_sets_the_research_or_the_suggestion() -> None:
    wrapper, inner = stub(first_round_script())
    wrapper.run(AgentRunRequest(request_id="q", message="Siapa broker? Pakai 4 angle."))
    assert inner.bounds[1] == (4, 4) and inner.bounds[3] == (1, 1)
    wrapper, inner = stub(first_round_script())
    wrapper.run(AgentRunRequest(request_id="q", message="Siapa broker? Beri 3 usulan."))
    assert inner.bounds[1] == (2, 6) and inner.bounds[3] == (3, 3)


def test_a_one_angle_suggestion_needs_the_sandbox_minimum() -> None:
    wrapper, inner = stub(first_round_script(), sandbox_min=2)
    result = wrapper.run(AgentRunRequest(request_id="q", message="Siapa broker?"))
    assert inner.bounds[3] == (2, 2)
    assert any("batas minimum sandbox" in n for n in result.mode4["notes"])


def test_an_analysis_that_does_not_answer_ends_the_round() -> None:
    wrapper, inner = stub(first_round_script(m4a=run_result("q-m4a", response("CLARIFICATION"))))
    result = wrapper.run(AgentRunRequest(request_id="q", message="Siapa broker?"))
    assert len(inner.requests) == 1 and result.status == "NEEDS_CLARIFICATION"
    assert result.response.clarification_question == "Yang mana?" and result.mode4["round"] == "FIRST"


def test_a_failed_research_keeps_the_answer_and_still_suggests() -> None:
    failed = AgentRunResponse(request_id="q-m4c", status="FAILED", response=None,
                              execution=ExecutionMetadata(model="m"), error={"code": "ANALYSIS_TIMEOUT",
                                                                             "message": "x"})
    wrapper, inner = stub(first_round_script(m4c=failed))
    result = wrapper.run(AgentRunRequest(request_id="q", message="Siapa broker?"))
    assert result.status == "AWAITING_CONFIRMATION" and len(inner.requests) == 4
    assert "Analisis: broker ZP." in result.response.answer
    assert "Riset tidak dapat diselesaikan: ANALYSIS_TIMEOUT." in result.response.answer
    assert "the research could not be completed" in inner.requests[3].message


def test_a_plan_that_is_not_issued_skips_the_execution_and_a_missing_suggestion_is_said() -> None:
    wrapper, inner = stub(first_round_script(m4b=run_result("q-m4b", response("CLARIFICATION")),
                                             m4d=run_result("q-m4d", response("LIMITATION"))))
    result = wrapper.run(AgentRunRequest(request_id="q", message="Siapa broker?"))
    assert [r.request_id for r in inner.requests] == ["q-m4a", "q-m4b", "q-m4d"]
    assert result.status == "COMPLETED" and result.response.response_type == "ANSWER"
    assert result.continuation is None
    assert "Riset tidak dijalankan: model meminta klarifikasi: Yang mana?" in result.response.answer
    assert "Tidak ada usulan riset berikutnya: Data tidak cukup." in result.response.answer


def test_the_time_budget_skips_the_steps_it_cannot_start() -> None:
    wrapper, inner = stub(first_round_script())
    inner.settings = make_settings(**{**MODE4, "AI_MODE4_MAX_SECONDS": "250"})
    result = wrapper.run(AgentRunRequest(request_id="q", message="Siapa broker?"))
    assert [s["status"] for s in result.mode4["steps"]] == ["COMPLETED", "AWAITING_CONFIRMATION", "SKIPPED",
                                                            "SKIPPED"]
    assert result.response.response_type == "ANSWER" and "waktu mode 4 habis" in result.response.answer


def follow_up_script(**overrides: Any) -> dict[str, Any]:
    script = {"m4c": run_result("q2-m4c", response("ANSWER", "Riset sudut a_fall: mendukung."),
                                turn="EXECUTE_APPROVED", approved="rp_d"),
              "m4d": run_result("q2-m4d", plan_final(PLAN1, "Usulan berikutnya."), turn="PROPOSE", plan_id="rp_e")}
    script.update(overrides)
    return script


def test_an_approval_runs_the_suggestion_and_proposes_the_next_one() -> None:
    wrapper, inner = stub(follow_up_script())
    result = wrapper.run(AgentRunRequest(request_id="q2", conversation_id="conv", message="ok lanjut",
                                         continuation=fake_continuation()))
    assert [r.request_id for r in inner.requests] == ["q2-m4c", "q2-m4d"]
    assert inner.requests[0].continuation.action == "APPROVE"
    assert "a_fall: Do large falls" in inner.requests[1].message  # the angle that ran is named
    assert result.status == "AWAITING_CONFIRMATION" and "**Jawaban**" not in result.response.answer
    assert result.response.answer.startswith("**Hasil riset**")
    plan_exec = result.execution.research_plan
    assert (plan_exec.turn, plan_exec.approved_plan_id, plan_exec.issued_plan_id, plan_exec.action_source) == \
        ("EXECUTE_APPROVED", "rp_d", "rp_e", "CLASSIFIER")
    assert plan_exec.classifier.cost == 0.001 and result.execution.cost == pytest.approx(0.021)
    # the conversation store retires the approved suggestion as EXECUTED and keeps the new one pending
    state = advance({"research_plan": {"plan_id": "rp_d", "status": "PENDING"}}, result, "q2", 2)
    assert state["research_plan"]["plan_id"] == "rp_e" and state["research_plan"]["status"] == "PENDING"
    assert state["earlier_plans"][-1] == {"plan_id": "rp_d", "status": "EXECUTED", "closed_request_id": "q2"}


def test_a_new_question_cancels_the_suggestion_and_starts_a_first_round() -> None:
    new_plan = run_result("q-m4d", plan_final(PLAN1), turn="PROPOSE", plan_id="rp_g")
    wrapper, inner = stub(first_round_script(m4d=new_plan), classify="UNRELATED")
    result = wrapper.run(AgentRunRequest(request_id="q", conversation_id="conv", message="Bagaimana dengan BBCA?",
                                         continuation=fake_continuation()))
    assert [r.request_id for r in inner.requests] == ["q-m4a", "q-m4b", "q-m4c", "q-m4d"]
    assert inner.requests[0].continuation is None
    assert result.mode4["cancelled_plan_id"] == "rp_d" and result.mode4["round"] == "FIRST"
    state = advance({"research_plan": {"plan_id": "rp_d", "status": "PENDING"}}, result, "q", 2)
    assert state["earlier_plans"][-1]["status"] == "CANCELLED"
    # with no new suggestion the cancelled plan stays the latest, CANCELLED
    wrapper, inner = stub(first_round_script(m4d=run_result("q-m4d", response("LIMITATION"))), classify="UNRELATED")
    result = wrapper.run(AgentRunRequest(request_id="q", message="Bagaimana dengan BBCA?",
                                         continuation=fake_continuation()))
    state = advance({"research_plan": {"plan_id": "rp_d", "status": "PENDING"}}, result, "q", 2)
    assert state["research_plan"]["status"] == "CANCELLED"


def test_a_revision_obeys_the_count_and_a_cancel_passes_through() -> None:
    revised = run_result("q2-m4c", plan_final(ResearchPlanV2.model_validate(plan_v2(angles=angles()[:2]))),
                         turn="REVISE", plan_id="rp_f")
    wrapper, inner = stub(follow_up_script(m4c=revised), classify="REVISE")
    result = wrapper.run(AgentRunRequest(request_id="q2", message="cari 2 angle lain",
                                         continuation=fake_continuation()))
    assert inner.bounds == [(2, 2)] and len(inner.requests) == 1
    assert result.status == "AWAITING_CONFIRMATION" and result.continuation.plan_id == "rp_f"
    cancel = run_result("q2-m4c", response("ANSWER", "Dibatalkan."), turn="CANCEL")
    wrapper, inner = stub(follow_up_script(m4c=cancel), classify="CANCEL")
    result = wrapper.run(AgentRunRequest(request_id="q2", message="batal", continuation=fake_continuation()))
    assert len(inner.requests) == 1 and result.response.answer == "Dibatalkan."
    assert result.execution.research_plan.turn == "CANCEL"


def test_an_explicit_plan_reply_skips_the_classifier() -> None:
    wrapper, inner = stub(follow_up_script(), classify="UNRELATED")
    result = wrapper.run(AgentRunRequest(request_id="q2", message="Setuju.",
                                         continuation=fake_continuation("APPROVE")))
    assert len(inner.requests) == 2 and result.execution.research_plan.classifier is None


def test_mode4_settings() -> None:
    settings = make_settings(**MODE4)
    assert settings.ai_enable_mode4 and settings.ai_mode4_max_seconds == 3600
    assert settings.conversation_lease_seconds == 3720
    assert make_settings().conversation_lease_seconds == make_settings().ai_max_analysis_seconds + 120
    with pytest.raises(ConfigError, match="AI_MODE4_MAX_SECONDS"):
        make_settings(**MODE4, AI_CONVERSATION_LEASE_SECONDS="1000")


def test_the_api_wraps_the_orchestrator_only_when_mode4_can_run() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from test_analysis_path import AUTH

    runner, scripted, _ = mode4_agent([final_response(ANALYSIS)])
    inner = runner.inner
    app = create_app(make_settings(**MODE4), orchestrator=inner)
    assert isinstance(app.state.orchestrator, Mode4Orchestrator) and app.state.orchestrator.inner is inner
    with TestClient(app) as client:
        body = {"request_id": "a1", "message": BROKER, "analysis_path": "ANALYSIS"}
        response = client.post("/v1/agent/run", json=body, headers=AUTH)
        assert response.status_code == 200 and "mode4" not in response.json()
    # the flag off (or a deployment without the paths) keeps the orchestrator and refuses MODE4
    off = AgentOrchestrator(make_settings(), ScriptedClient([]), ma_registry(RunSandbox()))
    app = create_app(make_settings(), orchestrator=off)
    assert app.state.orchestrator is off
    with TestClient(app) as client:
        response = client.post("/v1/agent/run", json={"request_id": "a2", "message": "x", "analysis_path": "MODE4"},
                               headers=AUTH)
        assert response.status_code == 400
        assert response.json()["detail"]["code"] in ("ANALYSIS_PATH_UNAVAILABLE", "MODE4_UNAVAILABLE")
    no_paths = AgentOrchestrator(make_settings(**MA), ScriptedClient([]), ma_registry(RunSandbox()),
                                 wall_clock=Clock(), draft_reader=lambda draft_id: None)
    assert create_app(make_settings(**{**MODE4, "AI_ENABLE_ANALYSIS_PATH": "false"}),
                      orchestrator=no_paths).state.orchestrator is no_paths
