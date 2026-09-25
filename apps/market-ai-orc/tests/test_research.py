"""Research AI in the orchestrator: research specs cross the tool boundary unchanged, evidence assessments drive
the answer contract (claims, reporting constraints), experiments are summarised, and every run is audited."""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.audit import RunAuditor, build_report
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest
from app.tools import build_default_registry
from app.tools.analysis import CreateAnalysisSpecArgs
from conftest import ScriptedClient, final_response, make_settings, tool_call_response
from test_analysis_tools import (ANA, AnyRunBundles, ANA2, REFERENCE, SPEC, approved, completed, mock_sandbox, run_args,
                                 sandbox_module, spec_args)
from test_provenance import answer, governor

SPEC2 = "spec_" + "2" * 24
RESEARCH = {"evidence_standard": "HISTORICAL_PATTERN", "objective": "Is weakness followed by recovery?",
            "hypothesis": {"id": "H1", "statement": "Deep z-scores precede above-baseline returns."},
            "method_ref": "event_study", "followup_of": None, "candidates": None, "holdout": None,
            "design_type": "EVENT_STUDY", "primary_metric": None, "observation_unit": None, "comparator": None,
            "multiple_testing_policy": None}


def assessment(claim: str = "HISTORICAL_PATTERN", decision: str = "PARTIALLY_SUPPORTED", level: str = "PATTERN",
               **extra: Any) -> dict[str, Any]:
    return {"claim_type": claim, "decision": decision, "evidence_level": level, "checks": {"minimum_sample": "PASS"},
            "reporting_constraints": ["Describe the result as a historical association, not causation.",
                                      "Report the event count, the baseline, and the difference with its uncertainty."],
            "statistics": {"segments": {"ALL": {"event_count": 143, "delta_mean": 0.0123,
                                                "delta_ci95": [0.0031, 0.0215]}}, "confidence_level": 0.95},
            "source": "VALIDATOR", **extra}


def run(script: list, message: str, sandbox: dict, *, auditor=None):
    registry = build_default_registry(None, bundles=AnyRunBundles(), governor_client=governor(),
                                      sandbox_client=mock_sandbox(sandbox),
                                      sandbox_timeout_seconds=5)
    scripted = ScriptedClient(script)
    result = AgentOrchestrator(make_settings(), scripted, registry, wall_clock=lambda: REFERENCE,
                               auditor=auditor).run(AgentRunRequest(request_id="research", message=message))
    return result, scripted


def study_calls(spec_id: str = SPEC, research: dict | None = None) -> list:
    return [tool_call_response("create_analysis_spec", json.dumps(spec_args(research=research or RESEARCH)),
                               call_id=f"s-{spec_id[-1]}"),
            tool_call_response("run_python_analysis", json.dumps(run_args(spec_id=spec_id)), call_id=f"r-{spec_id[-1]}")]


def study_result(analysis_id: str = ANA, spec_id: str = SPEC, **evidence: Any) -> dict[str, Any]:
    return completed(analysis_id=analysis_id, spec_id=spec_id, evidence_assessment=assessment(**evidence),
                     outputs=[{"type": "TABLE", "name": "summary", "row_count": 1,
                               "preview_rows": [["ALL", 143, 0.0187, 0.0064]]}],
                     warnings=[{"code": "CORPORATE_ACTIONS_NOT_ADJUSTED", "message": "m"}])


def sandbox_for(*results: dict[str, Any], reviews: list | None = None) -> dict:
    return {("POST", "/v1/specs"): [(200, r) for r in (reviews or [approved(governor={"decision": "APPROVED"})])],
            ("POST", "/v1/analyses"): [(200, r) for r in results]}


# ---------------------------------------------------------------- contract

def test_research_specs_cross_the_tool_boundary_unchanged() -> None:
    args = CreateAnalysisSpecArgs.model_validate(spec_args(research={**RESEARCH, "holdout": {
        "start": "2026-01-02", "end": None}, "evidence_standard": "PREDICTIVE", "candidates": 3}))
    request = sandbox_module("spec_v2").SpecRequestAny.model_validate({
        "request_id": "r", "reference_time": REFERENCE.isoformat(), "timezone": "Asia/Jakarta",
        "user_messages": [{"role": "user", "content": "x"}], "spec": args.model_dump(mode="json")})
    assert request.spec.research.holdout.start.isoformat() == "2026-01-02"
    assert request.spec.research.candidates == 3
    with pytest.raises(ValueError):
        CreateAnalysisSpecArgs.model_validate(spec_args(research={**RESEARCH, "evidence_standard": "PROVEN"}))


def test_a_governor_decision_is_returned_to_the_model() -> None:
    review = {"status": "REPLAN_REQUIRED", "next_action": "REVISE_SPEC",
              "governor": {"decision": "REPLAN_REQUIRED", "reason_code": "MISSING_BASELINE_DEFINITION",
                           "message": "add an EVENT_STUDY", "budget_before": {"experiments_remaining": 6}}}
    seen: list = []
    registry = build_default_registry(None, sandbox_client=mock_sandbox({("POST", "/v1/specs"): (200, review)}, seen),
                                      sandbox_timeout_seconds=5)
    from app.tools.analysis import current_run_context, run_context

    token = current_run_context.set(run_context(REFERENCE, "Asia/Jakarta", [], "Is X followed by Y?"))
    try:
        outcome = registry.execute("c1", "create_analysis_spec", json.dumps(spec_args(research=RESEARCH)))
    finally:
        current_run_context.reset(token)
    assert outcome.output["result"]["governor"]["reason_code"] == "MISSING_BASELINE_DEFINITION"
    assert seen[0]["body"]["spec"]["research"]["hypothesis"]["id"] == "H1"


# ---------------------------------------------------------------- claims (37) and reporting constraints

def test_causal_wording_is_rejected_once_then_forces_a_limitation() -> None:
    script = [*study_calls(), final_response(answer("Foreign buying causes the rebound: 143 events.")),
              final_response(answer("Foreign buying causes the rebound: 143 events."))]
    result, scripted = run(script, "Is foreign buying followed by a rebound?", sandbox_for(study_result()))
    assert result.response.response_type == "LIMITATION" and result.evidence_label == "NOT_VALIDATED"
    assert any("causal wording" in line for line in result.response.limitations)
    rejection = [i["content"] for p in scripted.payloads for i in p["input"] if i.get("role") == "user"]
    assert any("association, not a cause" in text for text in rejection)


def test_negated_or_constrained_wording_is_not_a_claim() -> None:
    text = ("Historically, 143 events had a mean excess return of 1.23% over the baseline (95% interval 0.31%-2.15%). "
            "This is an association, not causation, and not a prediction.")
    result, _ = run([*study_calls(), final_response(answer(text))], "Is weakness followed by recovery?",
                    sandbox_for(study_result()))
    assert result.response.response_type == "ANSWER" and result.execution.validation_gate == "ANNOTATED"
    limitations = " ".join(result.response.limitations)
    assert "HISTORICAL_PATTERN" in limitations and "not causation" in limitations
    assert "not dividend-adjusted" in limitations  # corporate-action disclosure
    assert result.execution.number_provenance.unsupported == []  # interval bounds come from the validator


def test_predictive_wording_needs_a_supported_predictive_assessment() -> None:
    text = "Stocks with this signal will rise over the next 5 days."
    result, _ = run([*study_calls(), final_response(answer(text)), final_response(answer(text))],
                    "Is weakness predictive of a rebound?", sandbox_for(study_result()))
    assert result.response.response_type == "LIMITATION"
    supported = study_result(claim="PREDICTIVE", decision="SUPPORTED", level="PREDICTIVE_SIGNAL")
    result, _ = run([*study_calls(research={**RESEARCH, "evidence_standard": "PREDICTIVE"}),
                     final_response(answer(text))], "Is weakness predictive of a rebound?", sandbox_for(supported))
    assert result.response.response_type == "ANSWER"


# ---------------------------------------------------------------- experiments and follow-ups (50)

def test_experiments_are_summarised_with_follow_ups_and_retention() -> None:
    follow_research = {**RESEARCH, "followup_of": SPEC}
    first = study_result()
    second = study_result(ANA2, SPEC2)
    second["outputs"][0]["preview_rows"] = [["ALL", 57, 0.0311, 0.0042]]
    script = [*study_calls(), *study_calls(SPEC2, follow_research),
              final_response(answer("The follow-up found 57 events with a mean of 3.11%. An association only."))]
    result, _ = run(script, "Is weakness followed by recovery, and in which regime?", sandbox_for(
        first, second, reviews=[approved(governor={"decision": "APPROVED"}),
                                approved(spec_id=SPEC2, governor={"decision": "APPROVED"})]))
    experiments = {e.spec_id: e for e in result.execution.research.experiments}
    assert experiments[SPEC].retained == "FOLLOWED_UP" and experiments[SPEC2].retained == "RETAINED"
    assert experiments[SPEC2].followup_of == SPEC and experiments[SPEC2].evidence_standard == "HISTORICAL_PATTERN"
    assert experiments[SPEC].governor_decision == "APPROVED"


def test_a_plain_calculation_has_no_research_block_but_is_listed() -> None:
    result, _ = run([tool_call_response("create_analysis_spec", json.dumps(spec_args())),
                     tool_call_response("run_python_analysis", json.dumps(run_args())),
                     final_response(answer("Done."))], "Hitung z-score 20 hari BBCA",
                    sandbox_for(completed(), reviews=[approved()]))
    [experiment] = result.execution.research.experiments
    assert experiment.evidence_standard == "CALCULATION" and experiment.hypothesis_id is None


# ---------------------------------------------------------------- audit (53)

class FakeSandbox:
    def __init__(self, fail: bool = False) -> None:
        self.reports: list = []
        self.fail = fail

    def put_report(self, request_id: str, report: dict) -> dict:
        if self.fail:
            raise RuntimeError("sandbox down")
        self.reports.append((request_id, report))
        return {"stored": True}

    def run_summary(self, request_id: str) -> dict:
        return {"status": "REPORTED", "analyses": [{"analysis_id": ANA, "code_sha256": "c" * 64,
                                                    "dataset_ids": ["ds_" + "a" * 24], "leakage_check": None,
                                                    "cpu_seconds": 1.5, "datasets": {
                                                        "ds_" + "a" * 24: {"checksum_sha256": "d" * 64}}}],
                "budget": {"analyses": {"used": 1, "max": 6}}}


def test_every_run_is_reported_to_the_sandbox_without_changing_the_response() -> None:
    sandbox = FakeSandbox()
    text = "Historically, 143 events; an association, not causation."
    result, _ = run([*study_calls(), final_response(answer(text))], "Is weakness followed by recovery?",
                    sandbox_for(study_result()), auditor=RunAuditor(sandbox, None))
    [(request_id, report)] = sandbox.reports
    assert request_id == "research" and report["answer"] == result.response.answer
    assert report["experiments"][0]["retained"] == "RETAINED" and report["validation_gate"] == "ANNOTATED"
    broken = RunAuditor(FakeSandbox(fail=True), None)
    again, _ = run([*study_calls(), final_response(answer(text))], "Is weakness followed by recovery?",
                   sandbox_for(study_result()), auditor=broken)
    assert again.response.answer == result.response.answer  # auditing failures never change the run


def test_the_report_holds_hashes_and_no_hidden_reasoning() -> None:
    result, _ = run([final_response(answer("Hello."))], "Hi", {})
    report = build_report("Hi", result, [])
    assert len(report["question_sha256"]) == 64 and len(report["answer_sha256"]) == 64
    assert "reasoning" not in json.dumps(report).lower()
