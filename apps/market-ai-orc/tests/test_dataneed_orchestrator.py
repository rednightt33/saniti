"""The orchestrator in DataNeed mode (AI_ENABLE_DATANEED): exclusive tools and prompt, the completion gate, routing,
released-output provenance (DATA_COVERAGE_VERIFIED), claims that are never allowed, and the final status."""
from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app.orchestrator import DATANEED_RULES, WARNING_LINES, AgentOrchestrator, build_system_prompt
from app.schemas import AgentRunRequest
from app.tools import ToolRegistry, ToolSpec, build_default_registry
from app.tools.analysis import SandboxClient
from app.tools.request_data import GovernorClient
from conftest import ScriptedClient, final_response, make_settings, tool_call_response

NEED = "need_" + "1" * 24
BUNDLE = "bundle_" + "2" * 24
SESSION = "sess_" + "3" * 24
OUTPUT = "out_" + "4" * 24
HIDDEN = "out_" + "5" * 24


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Governance(Strict):
    hypothesis_id: str


class SpecArgs(Strict):
    mode: str
    research_governance: Governance | None


class NeedArgs(Strict):
    need_id: str


class BundleArgs(Strict):
    input_bundle_id: str


class SessionArgs(Strict):
    session_id: str


class OutputArgs(Strict):
    session_id: str
    output_id: str


def final_status(**overrides: Any) -> dict[str, Any]:
    return {"data_need_validation": "PASS", "research_governance": "NOT_APPLICABLE", "sql_governance": "PASS",
            "data_quality_profiling": "COMPLETE", "data_coverage": "PASS", "sandbox_execution": "SUCCESS",
            "calculation_validation": "NOT_PERFORMED", "data_complete": True, "execution_complete": True,
            "evidence_label": "DATA_COVERAGE_VERIFIED", "warnings": [], "claims_allowed": [],
            "claims_forbidden": ["the calculation was independently verified"], **overrides}


def completed(rows: list[dict[str, Any]] | None = None, **final: Any) -> dict[str, Any]:
    return {"status": "COMPLETED", "completion_id": "cmp_1", "session_id": SESSION, "need_id": NEED,
            "final_status": final_status(**final), "coverage": {"coverage_status": "PASS"},
            "next_action": "ANSWER_FROM_RELEASED_OUTPUTS",
            "released_outputs": [{"output_id": OUTPUT, "name": "ytd", "type": "TABLE"}],
            "released_contents": [{"output_id": OUTPUT, "name": "ytd", "type": "TABLE", "row_count": 2,
                                   "rows": rows if rows is not None else [{"ticker": "BBCA", "ytd_return": 0.123456},
                                                                          {"ticker": "BBRI", "ytd_return": -0.04321}],
                                   "truncated": False}]}


def incomplete() -> dict[str, Any]:
    return {"status": "INCOMPLETE", "completion_id": "cmp_0", "session_id": SESSION, "need_id": NEED,
            "final_status": final_status(data_coverage="FAIL", evidence_label="NOT_VALIDATED",
                                         execution_complete=False),
            "coverage": {"coverage_status": "FAIL"}, "released_outputs": [], "next_action": "RUN_PYTHON",
            "message": "Not processed: prices:previous_comparable"}


class Tools:
    """Fake DataNeed tools with the result shapes of the sandbox and planner; complete_analysis answers in order."""

    def __init__(self, completions: list[dict[str, Any]], mode: str = "ANALYSIS", stdout: str = "") -> None:
        self.completions = list(completions)
        self.mode = mode
        self.stdout = stdout

    def registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        specs = [
            ("submit_data_need_spec", SpecArgs, lambda a: {"status": "APPROVED", "need_id": NEED, "revision": 1,
                                                           "research_governance": {"decision": "APPROVED"}
                                                           if a.mode == "RESEARCH" else None}),
            ("prepare_data_bundle", NeedArgs, lambda a: {
                "status": "READY", "input_bundle_id": BUNDLE,
                "datasets": [{"data_request_id": "data_request_1", "rows": 358, "entities": 2}],
                "relationship_warnings": [{"code": "HISTORICAL_REFERENCE_USES_CURRENT_STATE"}]}),
            ("open_analysis_session", BundleArgs, lambda a: {"session_id": SESSION, "status": "ACTIVE",
                                                             "bundle_id": BUNDLE, "need_id": NEED}),
            ("run_python", SessionArgs, lambda a: {"execution_id": "exe_1", "session_id": SESSION, "status": "OK",
                                                   "stdout": self.stdout, "outputs": []}),
            ("get_session_output", OutputArgs, lambda a: {
                "output_id": a.output_id, "released": a.output_id == OUTPUT,
                "rows": [{"ticker": "BBCA", "note": "tertinggi 9.875"}] if a.output_id == OUTPUT
                else [{"ticker": "BBCA", "draft": 0.5555}]}),
            ("complete_analysis", SessionArgs, lambda a: self.completions.pop(0)),
        ]
        for name, model, handler in specs:
            registry.register(ToolSpec(name=name, description=name, arguments_model=model, handler=handler))
        return registry


def call(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    return tool_call_response(name, json.dumps(arguments), call_id=call_id)


def flow(mode: str = "ANALYSIS", *, run: bool = True, complete: bool = True) -> list[dict[str, Any]]:
    steps = [call("submit_data_need_spec", {"mode": mode, "research_governance": {"hypothesis_id": "h1"}
                                            if mode == "RESEARCH" else None}, "c1"),
             call("prepare_data_bundle", {"need_id": NEED}, "c2"),
             call("open_analysis_session", {"input_bundle_id": BUNDLE}, "c3")]
    if run:
        steps.append(call("run_python", {"session_id": SESSION}, "c4"))
    if complete:
        steps.append(call("complete_analysis", {"session_id": SESSION}, "c5"))
    return steps


def answer(text: str, kind: str = "ANSWER", limitations: list[str] | None = None) -> dict[str, Any]:
    return {"response_type": kind, "answer": text, "clarification_question": None, "assumptions": [],
            "limitations": limitations if limitations is not None else ([] if kind == "ANSWER" else ["x"])}


def run(script: list, tools: Tools, message: str = "Berapa return YTD BBCA dan BBRI?", **settings: str):
    scripted = ScriptedClient(script)
    orchestrator = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true", **settings), scripted,
                                     tools.registry())
    return orchestrator.run(AgentRunRequest(request_id="dn", message=message)), scripted


# --- tools and prompt --------------------------------------------------------------------------------------------

def test_the_dataneed_registry_replaces_the_analysis_spec_path() -> None:
    sandbox = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    names = set(build_default_registry(sandbox_client=sandbox, governor_client=governor, dataneed_enabled=True,
                                       lookup_fact_enabled=False).names())
    assert names == {"get_system_capabilities", "get_dimension_values", "submit_data_need_spec",
                     "prepare_data_bundle", "open_analysis_session", "run_python", "inspect_session",
                     "get_session_output", "complete_analysis"}
    legacy = set(build_default_registry(sandbox_client=sandbox, governor_client=governor).names())
    assert {"create_analysis_spec", "prepare_analysis_data", "run_python_analysis", "get_analysis_result",
            "get_dataset_manifest"} <= legacy and not names & {"create_analysis_spec", "run_python_analysis"}


def test_the_dataneed_prompt_replaces_the_analysis_spec_rules() -> None:
    prompt = build_system_prompt(lookup_fact=False, dataneed=True)
    assert "DATA NEED RULES" in prompt and "DATA QUERY RULES" not in prompt
    assert "create_analysis_spec" not in prompt and "lookup_fact" not in prompt and "{" not in prompt
    assert prompt.startswith(build_system_prompt(lookup_fact=False).split("DATA QUERY RULES\n")[0])
    with_lookup = build_system_prompt(lookup_fact=True, dataneed=True)
    assert "Use lookup_fact only for a specific source fact" in with_lookup and "a lookup_fact result, " in with_lookup
    assert "never calculate\nthem yourself" in DATANEED_RULES
    _, scripted = run([final_response(answer("Halo."))], Tools([]), message="Halo")
    assert "DATA NEED RULES" in json.dumps(scripted.payloads[0])


# --- the gate ----------------------------------------------------------------------------------------------------

def test_released_outputs_are_the_source_of_an_answer_labelled_data_coverage_verified() -> None:
    result, _ = run([*flow(), final_response(answer("Return YTD BBCA 12,35% dan BBRI turun 4,32%."))],
                    Tools([completed()]))
    assert result.status == "COMPLETED" and result.response.response_type == "ANSWER"
    assert result.evidence_label == "DATA_COVERAGE_VERIFIED"
    assert result.execution.number_provenance.unsupported == []
    status = result.execution.analysis_final_status
    assert status["completion_id"] == "cmp_1" and status["data_coverage"] == "PASS"
    assert status["calculation_validation"] == "NOT_PERFORMED" and status["status"] == "COMPLETED"
    limitations = result.response.limitations
    assert any("calculation_validation NOT_PERFORMED" in line for line in limitations)
    assert result.execution.validation_gate == "ANNOTATED"


def test_quality_warnings_of_the_final_status_are_disclosed() -> None:
    result, _ = run([*flow(), final_response(answer("Return YTD BBCA 12,35%."))],
                    Tools([completed(warnings=["HISTORICAL_REFERENCE_USES_CURRENT_STATE", "HISTORY_BUFFER_SHORTFALL",
                                               "UNKNOWN_CODE"])]))
    limitations = result.response.limitations
    assert WARNING_LINES["HISTORICAL_REFERENCE_USES_CURRENT_STATE"] in limitations
    assert WARNING_LINES["HISTORY_BUFFER_SHORTFALL"] in limitations


def test_an_analysis_that_was_run_but_not_completed_cannot_support_an_answer() -> None:
    tools = Tools([], stdout="BBCA 0.123456")
    result, scripted = run([*flow(complete=False), final_response(answer("Return YTD BBCA 12,35%.")),
                            final_response(answer("Return YTD BBCA 12,35%."))], tools)
    rejection = scripted.payloads[-1]["input"][-1]["content"]
    assert "did not complete" in rejection and "complete_analysis" in rejection
    assert result.response.response_type == "LIMITATION" and result.evidence_label == "NOT_VALIDATED"
    assert result.execution.validation_gate == "FORCED_LIMITATION"
    assert result.response.answer.startswith("The data analysis behind this response did not complete")
    assert any(f"Analysis session {SESSION} was not completed" in line for line in result.response.limitations)


def test_an_incomplete_analysis_is_rejected_until_it_completes() -> None:
    script = [*flow(), final_response(answer("Return YTD BBCA 12,35%.")),
              call("run_python", {"session_id": SESSION}, "c6"), call("complete_analysis", {"session_id": SESSION}, "c7"),
              final_response(answer("Return YTD BBCA 12,35%."))]
    result, scripted = run(script, Tools([incomplete(), completed()]), AI_MAX_TOOL_ITERATIONS="12")
    first_rejection = [i for i in scripted.payloads[6]["input"] if i.get("role") == "user"][-1]["content"]
    assert "INCOMPLETE (data_coverage FAIL" in first_rejection
    assert result.response.response_type == "ANSWER" and result.evidence_label == "DATA_COVERAGE_VERIFIED"
    assert result.execution.analysis_final_status["completion_id"] == "cmp_1"


def test_stdout_and_unreleased_outputs_are_not_sources() -> None:
    script = [*flow(), call("get_session_output", {"session_id": SESSION, "output_id": HIDDEN}, "c6"),
              final_response(answer("Return YTD BBCA 12,35%, draf 55,55%, cetak 7,77.")),
              final_response(answer("Return YTD BBCA 12,35%, draf 55,55%, cetak 7,77."))]
    result, scripted = run(script, Tools([completed()], stdout="7.77"))
    assert "55,55%" in scripted.payloads[-1]["input"][-1]["content"]
    assert result.response.response_type == "LIMITATION"
    assert result.execution.number_provenance.unsupported == ["55,55%", "7,77"]


def test_a_released_output_read_back_page_by_page_is_a_source() -> None:
    script = [*flow(), call("get_session_output", {"session_id": SESSION, "output_id": OUTPUT}, "c6"),
              final_response(answer("Harga tertinggi BBCA 9.875."))]
    result, _ = run(script, Tools([completed(rows=[])]), message="Harga tertinggi BBCA tahun ini?")
    assert result.response.response_type == "ANSWER" and result.evidence_label == "DATA_COVERAGE_VERIFIED"


def test_a_statistic_needs_a_completed_analysis() -> None:
    result, scripted = run([final_response(answer("Korelasinya sekitar 0,5.")),
                            final_response(answer("Korelasi tidak dihitung.", kind="LIMITATION"))],
                           Tools([]), message="Berapa korelasi return BBCA dan BBRI?")
    rejection = scripted.payloads[-1]["input"][-1]["content"]
    assert "submit_data_need_spec" in rejection and "CORRELATION" in rejection
    assert "create_analysis_spec" not in rejection
    assert result.response.response_type == "LIMITATION"


def test_causal_and_predictive_claims_are_blocked_even_for_research() -> None:
    claim = answer("RSI di bawah 30 memprediksi kenaikan 12,35% sebulan kemudian.")
    result, scripted = run([*flow("RESEARCH"), final_response(claim), final_response(claim)],
                           Tools([completed(research_governance="APPROVED")], mode="RESEARCH"),
                           message="Apakah RSI di bawah 30 diikuti kenaikan harga?")
    assert "never evidence of a cause, a prediction" in scripted.payloads[-1]["input"][-1]["content"]
    assert result.response.response_type == "LIMITATION"
    assert any("Unsupported claim: predictive wording" in line for line in result.response.limitations)


def test_a_research_answer_reports_a_historical_pattern() -> None:
    text = "Secara historis (pola historis), setelah RSI di bawah 30 return 20 hari rata-rata 12,35%."
    result, _ = run([*flow("RESEARCH"), final_response(answer(text))],
                    Tools([completed(research_governance="APPROVED")], mode="RESEARCH"),
                    message="Apakah RSI di bawah 30 diikuti kenaikan harga?")
    assert result.response.response_type == "ANSWER" and result.evidence_label == "DATA_COVERAGE_VERIFIED"
    assert any("historical pattern only" in line for line in result.response.limitations)
    [experiment] = result.execution.research.experiments
    assert experiment.spec_id == NEED and experiment.evidence_standard == "HISTORICAL_PATTERN"
    assert experiment.hypothesis_id == "h1" and experiment.analysis_id == SESSION
    assert experiment.validation_level == "DATA_COVERAGE_VERIFIED" and experiment.retained == "RETAINED"


def test_saying_the_calculation_was_verified_is_blocked() -> None:
    claim = answer("Return YTD BBCA 12,35%; perhitungan ini telah diverifikasi.")
    result, scripted = run([*flow(), final_response(claim), final_response(claim)], Tools([completed()]))
    assert "verification wording" in scripted.payloads[-1]["input"][-1]["content"]
    assert result.response.response_type == "LIMITATION"
    honest = answer("Return YTD BBCA 12,35%. Cakupan data terverifikasi; perhitungan tidak diverifikasi "
                    "secara independen.")
    result, _ = run([*flow(), final_response(honest)], Tools([completed()]))
    assert result.response.response_type == "ANSWER"


def test_without_the_flag_the_analysis_spec_gate_is_unchanged() -> None:
    scripted = ScriptedClient([final_response(answer("Halo."))])
    result = AgentOrchestrator(make_settings(), scripted, Tools([]).registry()).run(
        AgentRunRequest(request_id="dn", message="Halo"))
    assert "DATA QUERY RULES" in json.dumps(scripted.payloads[0]) and result.execution.analysis_final_status is None


class Auditor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record(self, request_id: str, question: str, result: Any, experiments: list, used_sandbox: bool) -> dict:
        self.calls.append({"request_id": request_id, "used_sandbox": used_sandbox, "experiments": experiments})
        return {}


def test_a_dataneed_run_is_audited_with_its_final_report() -> None:
    auditor = Auditor()
    scripted = ScriptedClient([*flow("RESEARCH"), final_response(answer("Pola historis: rata-rata 12,35%."))])
    AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), scripted,
                      Tools([completed(research_governance="APPROVED")], mode="RESEARCH").registry(),
                      auditor=auditor).run(AgentRunRequest(request_id="dn", message="Pola RSI < 30?"))
    [record] = auditor.calls
    assert record["used_sandbox"] is True and record["experiments"][0]["spec_id"] == NEED
