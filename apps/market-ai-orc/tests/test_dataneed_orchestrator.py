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
    # M25: both completions of the run are kept, in order; the latest stays analysis_final_status
    statuses = result.execution.analysis_final_statuses
    assert [s["status"] for s in statuses][-1] == "COMPLETED" and len(statuses) == 2
    assert statuses[-1] == result.execution.analysis_final_status
    assert "analysis_final_statuses" in result.execution.model_dump(mode="json")


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


def test_causal_and_predictive_claims_are_marked_even_for_research() -> None:
    # P17 (user decision 2026-10-01): the answer is kept and the claim marked in italics, with an annotation
    claim = answer("RSI di bawah 30 memprediksi kenaikan 12,35% sebulan kemudian.")
    result, scripted = run([*flow("RESEARCH"), final_response(claim)],
                           Tools([completed(research_governance="APPROVED")], mode="RESEARCH"),
                           message="Apakah RSI di bawah 30 diikuti kenaikan harga?")
    assert result.response.response_type == "ANSWER" and result.execution.validation_gate == "ANNOTATED"
    assert "*RSI di bawah 30 memprediksi kenaikan 12,35% sebulan kemudian*" in result.response.answer
    assert [a.kind for a in result.annotations] == ["PREDICTIVE"]
    assert any("bercetak miring" in line for line in result.response.limitations)


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


def test_saying_the_calculation_was_verified_is_marked() -> None:
    claim = answer("Return YTD BBCA 12,35%; perhitungan ini telah diverifikasi.")
    result, scripted = run([*flow(), final_response(claim)], Tools([completed()]))
    assert result.response.response_type == "ANSWER"
    assert [a.kind for a in result.annotations] == ["VERIFIED_CALCULATION"]
    honest = answer("Return YTD BBCA 12,35%. Cakupan data terverifikasi; perhitungan tidak diverifikasi "
                    "secara independen.")
    result, _ = run([*flow(), final_response(honest)], Tools([completed()]))
    assert result.response.response_type == "ANSWER" and result.annotations is None


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


# --- named-period returns (AI_ENABLE_STANDARD_PERIOD_RETURN) ------------------------------------------------------

def test_the_period_return_convention_is_taught_only_behind_its_flag() -> None:
    from app.orchestrator import PERIOD_RETURN_RULES
    from app.tools.session import PERIOD_RETURN_SENTENCE

    sandbox = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))

    def run_python(flag: bool) -> str:
        registry = build_default_registry(sandbox_client=sandbox, governor_client=governor, dataneed_enabled=True,
                                          standard_period_return=flag)
        return next(d["description"] for d in registry.definitions() if d["name"] == "run_python")

    assert "period_return" not in run_python(False) and run_python(True).endswith(PERIOD_RETURN_SENTENCE)
    off, on = build_system_prompt(False, True), build_system_prompt(False, True, period_return=True)
    assert "NAMED-PERIOD RETURNS" not in off and on == off + PERIOD_RETURN_RULES
    # the convention: base strictly before the start, end on or before the end, a declared history buffer
    assert "last valid value strictly before the period start" in on.replace("\n", " ")
    assert "history_buffer 1 TRADING_OBSERVATIONS" in on.replace("\n", " ")
    assert "Never use the first observation inside the period as the base" in on.replace("\n", " ")
    # explicit date-to-date formulas, event forward, rolling and intraday returns are not routed to it
    for excluded in ("date-to-date formula", "event forward returns", "rolling returns", "intraday open-to-close"):
        assert excluded in on.replace("\n", " ")
    # the Analysis Spec path (DataNeed off) never carries it
    assert "NAMED-PERIOD RETURNS" not in build_system_prompt(False, False, period_return=True)
    scripted = ScriptedClient([final_response(answer("Halo."))])
    AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true", AI_ENABLE_STANDARD_PERIOD_RETURN="true"), scripted,
                      Tools([]).registry()).run(AgentRunRequest(request_id="pr", message="Halo"))
    assert "NAMED-PERIOD RETURNS" in scripted.payloads[0]["instructions"]


# --- S05: sessions a run leaves open are closed; capacity refusals are bounded --------------------------------------

class Closer:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.fail = fail

    def __call__(self, request_id: str, session_ids: list[str]) -> dict[str, str]:
        self.calls.append((request_id, list(session_ids)))
        if self.fail:
            raise RuntimeError("sandbox down")
        return {s: "CLOSED_BY_CALLER" for s in session_ids}


def closing_run(script: list, tools: Tools, closer: Closer, **settings: str):
    scripted = ScriptedClient(script)
    orchestrator = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true", **settings), scripted,
                                     tools.registry(), session_closer=closer)
    closing_run.scripted = scripted
    return orchestrator.run(AgentRunRequest(request_id="dn", message="Berapa return YTD BBCA dan BBRI?"))


def test_a_session_left_incomplete_is_closed_when_the_run_ends() -> None:
    closer = Closer()
    result = closing_run([*flow(), final_response(answer("x", "LIMITATION"))], Tools([incomplete()]), closer)
    assert result.response.response_type == "LIMITATION" and closer.calls == [("dn", [SESSION])]


def test_a_session_opened_but_never_run_is_closed_and_a_completed_one_is_not() -> None:
    closer = Closer()
    closing_run([*flow(run=False, complete=False), final_response(answer("x", "LIMITATION"))], Tools([]), closer)
    assert closer.calls == [("dn", [SESSION])]
    closer = Closer()
    result = closing_run([*flow(), final_response(answer("Return YTD BBCA 12,35%."))], Tools([completed()]), closer)
    assert result.evidence_label == "DATA_COVERAGE_VERIFIED" and closer.calls == []


def test_a_failed_close_or_a_failed_run_still_returns_the_response() -> None:
    closer = Closer(fail=True)
    result = closing_run([*flow(complete=False), final_response(answer("x", "LIMITATION"))], Tools([]), closer)
    assert result.response.response_type == "LIMITATION" and closer.calls == [("dn", [SESSION])]
    closer = Closer()
    # the provider script ends after the session opened: the run fails, the session is still closed
    result = closing_run(flow(run=False, complete=False), Tools([]), closer)
    assert result.status == "FAILED" and closer.calls == [("dn", [SESSION])]


def test_capacity_refusals_are_bounded_by_the_repair_budget() -> None:
    class Busy(Tools):
        def registry(self) -> ToolRegistry:
            registry = super().registry()
            spec = registry._tools["open_analysis_session"]
            registry._tools["open_analysis_session"] = ToolSpec(
                name=spec.name, description=spec.description, arguments_model=spec.arguments_model,
                handler=lambda a: {"status": "REJECTED", "code": "SESSION_CAPACITY_EXCEEDED", "message": "busy",
                                   "next_action": "REPORT_LIMITATION"})
            return registry

    bundles = ["bundle_" + str(i) * 24 for i in range(5, 10)]
    script = [call("submit_data_need_spec", {"mode": "ANALYSIS", "research_governance": None}, "c1")]
    for i, bundle in enumerate(bundles):  # distinct bundles, so the identical-call guard does not apply
        script.append(call("open_analysis_session", {"input_bundle_id": bundle}, f"o{i}"))
    script.append(final_response(answer("x", "LIMITATION")))
    closing_run(script, Busy([]), Closer(), AI_MAX_TOOL_ITERATIONS="12")
    outputs = [json.loads(item["output"]) for item in closing_run.scripted.payloads[-1]["input"]
               if item.get("type") == "function_call_output"][1:]
    codes = [o["result"]["code"] if o["ok"] else o["error"]["code"] for o in outputs]
    # AI_MAX_REPAIR_ATTEMPTS (default 3) refusals reach the model, then the budget stops the retries
    assert codes == ["SESSION_CAPACITY_EXCEEDED"] * 3 + ["REPAIR_BUDGET_EXHAUSTED"] * 2


# --- S08: one open analysis session per run ------------------------------------------------------------------------

SESSION_2 = "sess_" + "4" * 24


class TwoSessions(Tools):
    """open_analysis_session hands out SESSION, then SESSION_2; run_python answers with the given statuses in order."""

    def __init__(self, completions: list[dict[str, Any]], statuses: list[str]) -> None:
        super().__init__(completions)
        self.opened = [SESSION, SESSION_2]
        self.statuses = list(statuses)

    def registry(self) -> ToolRegistry:
        registry = super().registry()
        for name, handler in (
                ("open_analysis_session", lambda a: {"session_id": self.opened.pop(0), "status": "ACTIVE",
                                                     "bundle_id": BUNDLE, "need_id": NEED}),
                ("run_python", lambda a: {"execution_id": "exe_" + str(len(self.statuses)), "session_id": a.session_id,
                                          "status": self.statuses.pop(0), "stdout": "", "outputs": []})):
            spec = registry._tools[name]
            registry._tools[name] = ToolSpec(name=spec.name, description=spec.description,
                                             arguments_model=spec.arguments_model, handler=handler)
        return registry


def outputs_of(scripted: ScriptedClient) -> dict[str, dict[str, Any]]:
    return {item["call_id"]: json.loads(item["output"]) for item in scripted.payloads[-1]["input"]
            if item.get("type") == "function_call_output"}


def test_a_second_open_waits_until_a_session_with_results_is_completed() -> None:
    closer = Closer()
    script = [*flow(complete=False), call("open_analysis_session", {"input_bundle_id": BUNDLE}, "o2"),
              call("complete_analysis", {"session_id": SESSION}, "c5"),
              final_response(answer("Return YTD BBCA 12,35%."))]
    result = closing_run(script, TwoSessions([completed()], ["OK"]), closer)
    refused = outputs_of(closing_run.scripted)["o2"]
    assert refused["ok"] is False and refused["error"]["code"] == "ANALYSIS_SESSION_ALREADY_OPEN"
    assert refused["error"]["open_session_id"] == SESSION and "complete_analysis" in refused["error"]["message"]
    # the sandbox was not asked for a second slot, nothing was closed, and the completed analysis answers
    assert closer.calls == [] and result.evidence_label == "DATA_COVERAGE_VERIFIED"


def test_a_session_without_a_successful_execution_is_closed_before_another_opens() -> None:
    closer = Closer()
    script = [*flow(complete=False), call("open_analysis_session", {"input_bundle_id": BUNDLE}, "o2"),
              call("run_python", {"session_id": SESSION_2}, "r2"),
              call("complete_analysis", {"session_id": SESSION_2}, "c6"),
              final_response(answer("Return YTD BBCA 12,35%."))]
    result = closing_run(script, TwoSessions([{**completed(), "session_id": SESSION_2}], ["FAILED", "OK"]), closer)
    assert outputs_of(closing_run.scripted)["o2"]["result"]["session_id"] == SESSION_2
    # closed once, before the second open; not again at the end of the run; it does not block the answer
    assert closer.calls == [("dn", [SESSION])]
    assert result.response.response_type == "ANSWER" and result.evidence_label == "DATA_COVERAGE_VERIFIED"


def test_both_number_rules_allow_display_rounding_without_adding_number_sources() -> None:
    # P03: the model showed full precision, believing rounding fails the provenance gate; it does not
    sentence = ("Round figures for display as a reader needs: a source value shown with fewer decimals, rounded "
                "(not truncated) to the decimals shown, or a decimal shown as a percentage, still matches its source.")
    for dataneed in (False, True):
        assert sentence in " ".join(build_system_prompt(False, dataneed).split())
    # the system prompt is a number source (CONTEXT), so the rule carries no digits
    assert not any(ch.isdigit() for ch in sentence)


def test_every_completion_of_a_session_stays_a_source() -> None:
    # conversation reuse: code run after a passed completion starts a new epoch of the same session, whose completion
    # must not replace the released values of the first one (found in the 2026-09-27 reuse PoC)
    second = completed(rows=[{"ticker": "BBCA", "gaps": 7}])
    second["completion_id"] = "cmp_2"
    script = [*flow(), call("run_python", {"session_id": SESSION}, "c6"), call("complete_analysis",
                                                                                 {"session_id": SESSION}, "c7"),
              final_response(answer("Return YTD BBCA 12,35% dan BBRI -4,32%; BBCA punya 7 celah."))]
    result, _ = run(script, Tools([completed(), second]), AI_MAX_TOOL_ITERATIONS="12")
    assert result.response.response_type == "ANSWER", result.response
    assert result.execution.number_provenance.unsupported == []


# --- G2: event-study tables the sandbox recomputed are CALCULATION_VERIFIED -----------------------------------------

STUDY = "out_" + "6" * 24


def studied(**final: Any) -> dict[str, Any]:
    """A completion with an event-study summary the sandbox recomputed (STUDY) and a table it did not (OUTPUT)."""
    base = completed(**{"calculation_validation": "PARTIAL", "verified_output_ids": [STUDY],
                        "event_studies": [{"name": "drops", "status": "PASS", "reason": None,
                                           "summary_output_id": STUDY, "events_output_id": None}], **final})
    base["released_outputs"].append({"output_id": STUDY, "name": "drops", "type": "TABLE"})
    base["released_contents"].append({"output_id": STUDY, "name": "drops", "type": "TABLE", "row_count": 1,
                                      "rows": [{"segment": "ALL", "event_count": 41, "mean": -1.23456,
                                                "delta_mean": -0.98765}], "truncated": False})
    return base


def test_an_answer_from_a_recomputed_event_study_is_calculation_verified() -> None:
    result, _ = run([*flow(), final_response(answer("Setelah turun, rata-rata return 3 hari -1,23% (41 event)."))],
                    Tools([studied()]), message="Berapa return 3 hari setelah saham turun 1%?")
    assert result.status == "COMPLETED" and result.execution.number_provenance.unsupported == []
    assert result.evidence_label == "CALCULATION_VERIFIED"
    limitations = " ".join(result.response.limitations)
    assert "event studies drops were recomputed independently" in limitations
    assert "calculation_validation NOT_PERFORMED" not in limitations
    assert result.execution.analysis_final_status["calculation_validation"] == "PARTIAL"


def test_an_answer_that_also_cites_a_table_not_recomputed_takes_the_weaker_label() -> None:
    result, _ = run([*flow(), final_response(answer("Rata-rata -1,23% setelah event; return YTD BBCA 12,35%."))],
                    Tools([studied()]), message="Berapa return 3 hari setelah saham turun 1%?")
    assert result.status == "COMPLETED" and result.evidence_label == "DATA_COVERAGE_VERIFIED"


def test_a_reference_to_a_recomputed_event_study_carries_its_label() -> None:
    result, _ = run([*flow(), final_response(answer(
        "Rata-rata {{out.o2.rows[segment=ALL].mean|dec:2}}% dari {{out.o2.rows[segment=ALL].event_count}} event."))],
        Tools([studied()]), message="Berapa return 3 hari setelah saham turun 1%?", AI_ENABLE_VALUE_REFERENCES="true")
    assert result.status == "COMPLETED", result.response
    assert "\u22121,23%" in result.response.answer and "41 event" in result.response.answer
    assert result.evidence_label == "CALCULATION_VERIFIED"


def test_an_event_study_the_backend_could_not_recompute_is_disclosed() -> None:
    result, _ = run([*flow(), final_response(answer("Return YTD BBCA 12,35%."))],
                    Tools([completed(event_studies=[{"name": "drops", "status": "INVALID",
                                                     "reason": "REBUILD_FAILED: ValueError"}])]))
    limitations = " ".join(result.response.limitations)
    assert "could not recompute: drops (REBUILD_FAILED: ValueError)" in limitations
    assert result.evidence_label == "DATA_COVERAGE_VERIFIED"


def test_the_event_study_is_described_only_behind_its_flag() -> None:
    from app.tools.session import COMPLETE_EVENT_STUDY_SENTENCE, EVENT_STUDY_SENTENCE

    sandbox = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))

    def described(flag: bool) -> dict[str, str]:
        registry = build_default_registry(sandbox_client=sandbox, governor_client=governor, dataneed_enabled=True,
                                          event_study=flag)
        return {d["name"]: d["description"] for d in registry.definitions()}

    off, on = described(False), described(True)
    assert "event_study" not in off["run_python"] and "event_study" not in off["complete_analysis"]
    assert on["run_python"].endswith(EVENT_STUDY_SENTENCE)
    assert on["complete_analysis"].endswith(COMPLETE_EVENT_STUDY_SENTENCE)
    assert "forward_return" in EVENT_STUDY_SENTENCE and "never overwrite" in EVENT_STUDY_SENTENCE


def test_saying_a_recomputed_event_study_was_verified_is_not_marked_but_mixing_in_other_figures_is() -> None:
    claim = answer("Hasil event study ini telah diverifikasi: rata-rata -1,23% dari 41 event.")
    result, _ = run([*flow(), final_response(claim)], Tools([studied()]))
    assert result.annotations is None and result.evidence_label == "CALCULATION_VERIFIED"
    mixed = answer("Hasil ini telah diverifikasi: rata-rata -1,23%, return YTD BBCA 12,35%.")
    result, _ = run([*flow(), final_response(mixed)], Tools([studied()]))
    assert [a.kind for a in result.annotations] == ["VERIFIED_CALCULATION"]
