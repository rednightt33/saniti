"""get_dataset_manifest, create_analysis_spec, run_python_analysis, get_analysis_result, and the validation gate."""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import ConfigError
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest, HistoryMessage
from app.tools import build_default_registry
from app.tools.analysis import (CreateAnalysisSpecArgs, RunPythonAnalysisArgs, SandboxClient, current_run_context,
                                run_context)
from app.tools.data_compiler import Bundle, BundleStore
from app.tools.request_data import GovernorClient, current_request_id
from conftest import ScriptedClient, final_response, make_settings, tool_call_response

SANDBOX_ROOT = Path(__file__).resolve().parents[2] / "market-python-sandbox"
DS, DS2 = "ds_" + "a" * 24, "ds_" + "b" * 24
ANA, ANA2 = "ana_" + "c" * 24, "ana_" + "9" * 24
SPEC = "spec_" + "1" * 24
SANDBOX_KEY = "s" * 40
REFERENCE = datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc)


def sandbox_module(name: str):
    """Import a module of apps/market-python-sandbox/app (both services name their package 'app')."""
    if "sandbox_app" not in sys.modules:
        spec = importlib.machinery.ModuleSpec("sandbox_app", None, is_package=True)
        spec.submodule_search_locations = [str(SANDBOX_ROOT / "app")]
        sys.modules["sandbox_app"] = importlib.util.module_from_spec(spec)
    return importlib.import_module(f"sandbox_app.{name}")


def spec_args(**overrides: Any) -> dict[str, Any]:
    base = {
        "spec_version": "2.0", "analysis_type": "RESEARCH" if overrides.get("research") else "ANALYSIS",
        "question": "Rolling 20-day z-scores for all IDX stocks over the last three months.",
        "subject": {"data_domain": "MARKET", "entity_type": "STOCK", "asset_type": "IDX_EQUITY"},
        "inputs": [{"name": "prices", "source_table": "Price_Stock_Indonesia_IDX", "role": "PRIMARY_DATA",
                    "entity_column": "ticker", "date_column": "date", "columns": ["ticker", "date", "close"]}],
        "relationships": [],
        "scope": {"selection_type": "ALL_ELIGIBLE", "entities": None, "predicates": None,
                  "provenance": "USER_EXPLICIT", "default_id": "DEFAULT_UNIVERSE_ALL_IN_SOURCE"},
        "time_scope": {"mode": "TRAILING", "start": None, "end": None, "unit": "MONTH", "count": 3, "frequency": "1D",
                       "provenance": "USER_EXPLICIT", "default_id": "DEFAULT_TRAILING_CALENDAR_WINDOW"},
        "calculations": [{"id": "z20", "method": "ROLLING_ZSCORE", "dataset": "prices", "columns": ["close"],
                          "input_calculation": None,
                          "params": [{"name": "window", "value": 20, "provenance": "USER_EXPLICIT",
                                      "default_id": None}],
                          "output_column": "zscore_20", "formula": None, "time_alignment": None, "covers": None,
                          "signal": None, "expression": None, "formula_refs": None, "meaning": None, "unit": None,
                          "data_policies": None, "group_by": None, "segments": None, "provenance": "USER_EXPLICIT",
                          "default_id": None}],
        "outputs": [{"name": "zscores", "grain": "ENTITY_DATE", "coverage": "FULL", "calculations": ["z20"],
                     "selection": None, "entity_column": None, "date_column": None, "pair_columns": None,
                     "key_columns": None, "ranking": None}],
        "exclusion_rules": [],
        "research": None,
    }
    return {**base, **overrides}


BUNDLE = "bundle_" + "e" * 24


class AnyRunBundles(BundleStore):
    """Test double: BUNDLE resolves for any request and spec, bound to one prices dataset."""

    def resolve(self, bundle_id: str, request_id: str, spec_id: str) -> Bundle | None:
        if bundle_id != BUNDLE:
            return None
        return Bundle(BUNDLE, request_id, spec_id, "plan_" + "0" * 24, {"prices": [DS]})


def completed(**overrides: Any) -> dict[str, Any]:
    return {
        "analysis_id": ANA, "spec_id": SPEC, "execution_status": "COMPLETED", "validation_status": "PASS",
        "validation_level": "CALCULATION_VERIFIED", "reason_codes": [], "next_action": "USE_ANALYSIS_RESULT",
        "request_id": "r", "question": "screen", "inputs": {"prices": [DS]}, "dataset_ids": [DS],
        "expected_outputs": ["TABLE"], "created_at": "2026-09-23T00:00:00+00:00", "runtime_ms": 3200,
        "retry_after_seconds": None,
        "expected_scope": {"analysis_start": "2026-06-24", "analysis_end": "2026-09-23", "expected_entities": 844},
        "actual_scope": {"outputs": [{"name": "zscores", "entities": 844}]},
        "outputs": [{"type": "TABLE", "name": "zscores", "row_count": 27, "columns": [{"name": "ticker",
                     "type": "string"}], "preview_rows": [["AAAA"]], "preview_row_count": 1, "preview_truncated": True,
                     "result_id": "res_" + "d" * 24}],
        "warnings": [{"code": "NUMERIC_AS_FLOAT64", "message": "float64"}], "error": None,
        "validation_evidence": [{"check": "calculation.z20.zscores", "result": "FAIL", "code": "CALCULATION_MISMATCH",
                                 "examples": [{"entity": "A"}] * 5}],
        "diagnostics": {"stdout_tail": "x" * 5000},
        "derived_features": [{"name": "zscore_20", "method": "ROLLING_ZSCORE", "parameters": {"window": 20},
                              "formula": "long text", "status": "EXPLORATORY_UNVALIDATED",
                              "independent_check_result": "RECALCULATED_MATCH"}],
        "self_reported": {"access_log": []},
        "lineage": {"runtime_version": "market-python-sandbox/v2", "code_sha256": "e" * 64, "seed": 0,
                    "library_versions": {"talib": "0.8.1"}, "limits": {"max_runtime_seconds": 120},
                    "deployment_id": "dep-1", "datasets": {DS: {"checksum_sha256": "f" * 64}}},
        "resource_usage": {"cpu_seconds": 1.0}, "outputs_expire_at": "2026-09-24T00:00:00+00:00", **overrides}


def approved(**overrides: Any) -> dict[str, Any]:
    return {"status": "APPROVED", "spec_id": SPEC, "spec_sha256": "a" * 64,
            "reference": {"date": "2026-09-23", "timezone": "Asia/Jakarta"},
            "resolved_period": {"mode": "TRAILING", "start": "2026-06-24", "end": "2026-09-23"},
            "required_input": {"prices": {"minimum_warmup_observations": 19,
                                          "recommended_request_date_range": {"from": "2026-05-15"}}},
            "checks": [{"requirement": "universe", "result": "MATCH"}] * 10, "mismatches": [],
            "unverified_requirements": [], "clarification_needed": [], "expected_requirements": {"x": 1},
            "output_contract": [{"name": "zscores", "grain": "ENTITY_DATE", "key_columns": ["ticker", "date"],
                                 "value_columns": ["zscore_20"], "coverage": "FULL", "emit": "emit_table"}],
            "derived_features": [{"name": "zscore_20"}], "next_action": "REQUEST_DATA_THEN_RUN_ANALYSIS", **overrides}


def mock_sandbox(responses: dict[tuple[str, str], Any], seen: list | None = None) -> SandboxClient:
    """responses map (method, path) to (status, body) or to a list of them served in order."""
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append({"method": request.method, "path": request.url.path, "params": dict(request.url.params),
                         "auth": request.headers.get("authorization"),
                         "body": json.loads(request.content) if request.content else None})
        answer = responses.get((request.method, request.url.path), (404, {"detail": "Not Found"}))
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        return httpx.Response(answer[0], json=answer[1])
    return SandboxClient("http://sandbox.test", SANDBOX_KEY, 5, 20, transport=httpx.MockTransport(handler))


def mock_governor(status: int, body: dict) -> GovernorClient:
    return GovernorClient("http://governor.test", "g" * 40, 5,
                          transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)))


def registry(sandbox: SandboxClient | None = None, governor: GovernorClient | None = None):
    return build_default_registry(None, governor_client=governor, sandbox_client=sandbox, sandbox_timeout_seconds=5,
                                  bundles=AnyRunBundles())


def run_args(**overrides: Any) -> dict[str, Any]:
    return {"spec_id": SPEC, "input_bundle_id": BUNDLE, "python_code": "print(1)",
            "expected_outputs": ["TABLE", "METRICS"], **overrides}


# --- schemas and contracts ---------------------------------------------------------------------------

def test_tool_schemas_are_strict_and_expose_no_limits_paths_or_user_context() -> None:
    definitions = {d["name"]: d for d in registry(mock_sandbox({}), mock_governor(200, {})).definitions()}
    expected = {"get_dataset_manifest": {"dataset_id"}, "get_analysis_result": {"analysis_id"},
                "run_python_analysis": {"spec_id", "input_bundle_id", "python_code", "expected_outputs"},
                "prepare_analysis_data": {"spec_id"},
                "create_analysis_spec": {"spec_version", "analysis_type", "question", "subject", "inputs",
                                         "relationships", "scope", "time_scope", "calculations", "outputs",
                                         "exclusion_rules", "research"}}
    for name, fields in expected.items():
        params = definitions[name]["parameters"]
        assert definitions[name]["strict"] is True and set(params["properties"]) == fields
        assert params["additionalProperties"] is False and params["required"] == list(params["properties"])
    spec_text = json.dumps(definitions["create_analysis_spec"]["parameters"])
    for context in ("reference_time", "user_messages", "timezone", "request_id"):
        assert context not in spec_text  # the orchestrator supplies these; the model cannot
    text = json.dumps([definitions[name] for name in expected])
    for forbidden in ("max_runtime", "memory_mb", "timeout", "bucket", "railway", "http", "file_path", "postgres"):
        assert forbidden not in text.lower(), forbidden


@pytest.mark.parametrize("bad", [
    {"input_bundle_id": "bundle_1"}, {"spec_id": "spec_1"}, {"input_bundle_id": DS},
    {"inputs": [{"name": "prices", "dataset_ids": [DS], "duplicate_policy": "ERROR_ON_CONFLICT"}]},
    {"python_code": "x" * 20001}, {"expected_outputs": ["TEXT"]}, {"expected_outputs": ["TABLE", "TABLE"]},
    {"max_runtime_seconds": 900}, {"purpose": "old contract"},
])
def test_run_python_analysis_rejects_invalid_or_limit_raising_arguments(bad: dict) -> None:
    seen: list = []
    outcome = registry(mock_sandbox({}, seen)).execute("c1", "run_python_analysis", json.dumps(run_args(**bad)))
    assert not outcome.ok and outcome.error_code == "INVALID_ARGUMENTS" and seen == []


def test_request_models_match_the_sandbox_contract() -> None:
    sandbox_request = sandbox_module("models").AnalysisRequest
    # the model names a prepared bundle; the backend sends the sandbox the bundle's input bindings
    assert set(sandbox_request.model_fields) - {"request_id", "inputs"} == \
        set(RunPythonAnalysisArgs.model_fields) - {"input_bundle_id"}
    payload = {k: v for k, v in RunPythonAnalysisArgs.model_validate(run_args()).model_dump().items()
               if k != "input_bundle_id"}
    sandbox_request.model_validate({"request_id": "r1", **payload, "inputs": [
        {"name": "prices", "dataset_ids": [DS], "duplicate_policy": "ERROR_ON_CONFLICT"}]})
    spec_request = sandbox_module("spec_v2").SpecRequestAny
    args = CreateAnalysisSpecArgs.model_validate(spec_args()).model_dump(mode="json")
    parsed = spec_request.model_validate({"request_id": "r1", "reference_time": REFERENCE.isoformat(),
                                          "timezone": "Asia/Jakarta", "user_messages": [{"role": "user",
                                                                                         "content": "x"}],
                                          "spec": args})
    assert type(parsed.spec).__name__ == "AnalysisSpecV2"
    assert set(sandbox_module("spec_v2").AnalysisSpecV2.model_fields) == set(CreateAnalysisSpecArgs.model_fields)
    sandbox_spec = sandbox_module("spec")
    assert set(sandbox_spec.Calculation.model_fields) == set(CreateAnalysisSpecArgs.model_fields["calculations"]
                                                            .annotation.__args__[0].model_fields)


def test_segments_period_statistics_and_group_pairs_reach_the_sandbox_unchanged() -> None:
    base = spec_args()["calculations"][0]
    segment = {"label": "banks", "predicates": [{"input": "universe", "column": "Industry", "operator": "EQ",
                                                 "value": "Banks"}],
               "provenance": "CATALOG_RESOLVED", "user_text": "perbankan"}
    calcs = [
        {**base, "id": "r1", "method": "RETURN", "params": []},
        {**base, "id": "vol", "method": "PERIOD_STAT", "columns": [], "input_calculation": "r1", "output_column": "vol",
         "params": [{"name": "function", "value": "STD", "provenance": "USER_EXPLICIT", "default_id": None}]},
        {**base, "id": "series", "method": "GROUP_AGGREGATE", "columns": [], "input_calculation": "r1",
         "output_column": "series", "segments": [segment],
         "params": [{"name": "function", "value": "AVG", "provenance": "USER_EXPLICIT", "default_id": None},
                    {"name": "per_date", "value": True, "provenance": "USER_EXPLICIT", "default_id": None}]},
        {**base, "id": "corr", "method": "GROUP_CORRELATION", "columns": [], "input_calculation": "series",
         "output_column": "corr", "params": []},
    ]
    output = {**spec_args()["outputs"][0], "name": "pairs", "grain": "GROUP_PAIR", "calculations": ["corr"],
              "key_columns": ["segment_a", "segment_b"]}
    args = CreateAnalysisSpecArgs.model_validate(spec_args(calculations=calcs, outputs=[output])).model_dump(mode="json")
    parsed = sandbox_module("spec_v2").AnalysisSpecV2.model_validate(args).model_dump(mode="json")
    assert parsed["calculations"][2]["segments"] == [segment]
    assert parsed["outputs"][0]["grain"] == "GROUP_PAIR"


# --- get_dataset_manifest ----------------------------------------------------------------------------

@pytest.mark.parametrize(("status", "body"), [
    (200, {"status": "AVAILABLE", "dataset_id": DS, "row_count": 214023, "columns": []}),
    (410, {"status": "DATASET_EXPIRED", "dataset_id": DS, "expires_at": "2026-09-30T00:00:00+00:00", "message": "m"}),
    (404, {"status": "DATASET_NOT_FOUND", "dataset_id": DS, "message": "m"}),
])
def test_manifest_statuses_are_returned_explicitly(status: int, body: dict) -> None:
    outcome = registry(governor=mock_governor(status, body)).execute("c1", "get_dataset_manifest",
                                                                    json.dumps({"dataset_id": DS}))
    assert outcome.ok and outcome.output["result"] == body


def test_manifest_service_errors_are_tool_errors() -> None:
    outcome = registry(governor=mock_governor(503, {"status": "DATASET_STORAGE_UNAVAILABLE"})).execute(
        "c1", "get_dataset_manifest", json.dumps({"dataset_id": DS}))
    assert not outcome.ok and outcome.error_code == "TOOL_ERROR"


# --- create_analysis_spec --------------------------------------------------------------------------------

def test_spec_review_gets_the_real_user_messages_and_reference_time_from_the_run() -> None:
    seen: list = []
    sandbox = mock_sandbox({("POST", "/v1/specs"): (200, approved())}, seen)
    history = [("user", "Hitung z-score semua saham"), ("assistant", "Periode berapa lama?")]
    tokens = (current_request_id.set("run-9"),
              current_run_context.set(run_context(REFERENCE, "Asia/Jakarta", history, "3 bulan terakhir")))
    try:
        outcome = registry(sandbox).execute("c1", "create_analysis_spec", json.dumps(spec_args()))
    finally:
        current_request_id.reset(tokens[0])
        current_run_context.reset(tokens[1])
    body = seen[0]["body"]
    assert body["request_id"] == "run-9" and body["timezone"] == "Asia/Jakarta"
    assert body["reference_time"] == REFERENCE.isoformat()
    assert body["user_messages"] == [{"role": "user", "content": "Hitung z-score semua saham"},
                                     {"role": "assistant", "content": "Periode berapa lama?"},
                                     {"role": "user", "content": "3 bulan terakhir"}]
    result = outcome.output["result"]
    assert result["spec_id"] == SPEC and result["required_input"]["prices"]["minimum_warmup_observations"] == 19
    assert "checks" not in result and "expected_requirements" not in result  # compact model view
    assert result["output_contract"][0]["key_columns"] == ["ticker", "date"]  # what the code must emit


def test_spec_review_without_a_run_context_is_refused() -> None:
    outcome = registry(mock_sandbox({})).execute("c1", "create_analysis_spec", json.dumps(spec_args()))
    assert not outcome.ok and outcome.error_code == "TOOL_ERROR"


def test_spec_mismatch_and_invalid_arguments_are_returned_to_the_model() -> None:
    mismatch = approved(status="ANALYSIS_SPEC_MISMATCH", spec_id=None, next_action="REVISE_SPEC_TO_MATCH_REQUEST",
                        mismatches=[{"requirement": "analysis_period", "expected": {"count": 3},
                                     "proposed": {"count": 2}, "code": "ANALYSIS_SCOPE_MISMATCH"}])
    token = current_run_context.set(run_context(REFERENCE, "Asia/Jakarta", [], "3 months"))
    try:
        outcome = registry(mock_sandbox({("POST", "/v1/specs"): (200, mismatch)})).execute(
            "c1", "create_analysis_spec", json.dumps(spec_args()))
        invalid = registry(mock_sandbox({("POST", "/v1/specs"): (422, {"status": "REJECTED", "error": {
            "code": "INVALID_REQUEST", "message": "m", "details": [{"loc": "spec.x", "msg": "bad"}]}})})).execute(
            "c1", "create_analysis_spec", json.dumps(spec_args()))
    finally:
        current_run_context.reset(token)
    assert outcome.output["result"]["status"] == "ANALYSIS_SPEC_MISMATCH"
    assert outcome.output["result"]["mismatches"][0]["proposed"] == {"count": 2}
    assert invalid.output["result"]["error"]["details"] == [{"loc": "spec.x", "msg": "bad"}]


# --- run_python_analysis / get_analysis_result -----------------------------------------------------

def test_submission_forwards_request_id_and_returns_both_statuses_compactly() -> None:
    seen: list = []
    sandbox = mock_sandbox({("POST", "/v1/analyses"): (200, completed())}, seen)
    token = current_request_id.set("agent-run-7")
    try:
        outcome = registry(sandbox).execute("c1", "run_python_analysis", json.dumps(run_args()))
    finally:
        current_request_id.reset(token)
    expected = {k: v for k, v in run_args().items() if k != "input_bundle_id"}
    assert seen[0]["auth"] == f"Bearer {SANDBOX_KEY}" and seen[0]["body"] == {
        "request_id": "agent-run-7", **expected,
        "inputs": [{"name": "prices", "dataset_ids": [DS], "duplicate_policy": "ERROR_ON_CONFLICT"}]}
    result = outcome.output["result"]
    assert (result["execution_status"], result["validation_status"], result["validation_level"]) == (
        "COMPLETED", "PASS", "CALCULATION_VERIFIED")
    assert result["outputs"][0]["result_id"].startswith("res_") and result["expected_scope"]["expected_entities"] == 844
    assert "limits" not in result["lineage"] and "deployment_id" not in result["lineage"]
    assert "resource_usage" not in result and "self_reported" not in result
    assert len(result["diagnostics"]["stdout_tail"]) == 1000
    assert len(result["validation_evidence"][0]["examples"]) == 3
    assert "formula" not in result["derived_features"][0]


def test_running_results_are_polled_with_a_bounded_wait() -> None:
    seen: list = []
    running = completed(execution_status="RUNNING", validation_status="PENDING", next_action="GET_ANALYSIS_RESULT",
                        retry_after_seconds=15, outputs=[], diagnostics=None)
    sandbox = mock_sandbox({("GET", f"/v1/analyses/{ANA}"): (200, running)}, seen)
    outcome = registry(sandbox).execute("c1", "get_analysis_result", json.dumps({"analysis_id": ANA}))
    assert outcome.output["result"]["execution_status"] == "RUNNING"
    assert outcome.output["result"]["retry_after_seconds"] == 15 and seen[0]["params"] == {"wait_seconds": "20"}
    missing = registry(mock_sandbox({})).execute("c1", "get_analysis_result", json.dumps({"analysis_id": ANA}))
    assert missing.output["result"]["execution_status"] == "NOT_FOUND"


@pytest.mark.parametrize(("status", "code", "action"), [
    (429, "QUEUE_FULL", "RETRY_LATER"), (503, "SANDBOX_ISOLATION_UNAVAILABLE", "REPORT_LIMITATION"),
    (422, "INVALID_REQUEST", "REVISE_ANALYSIS"), (422, "SPEC_NOT_FOUND", "CREATE_ANALYSIS_SPEC"),
    (429, "REQUEST_BUDGET_EXCEEDED", "REPORT_LIMITATION"),
])
def test_sandbox_rejections_are_structured(status: int, code: str, action: str) -> None:
    body = {"status": "REJECTED", "error": {"code": code, "message": "m"}, "retry_after_seconds": 15}
    outcome = registry(mock_sandbox({("POST", "/v1/analyses"): (status, body)})).execute(
        "c1", "run_python_analysis", json.dumps(run_args()))
    assert outcome.ok and outcome.output["result"]["error"]["code"] == code
    assert outcome.output["result"]["next_action"] == action


def test_unexpected_sandbox_failures_are_tool_errors_without_secrets() -> None:
    outcome = registry(mock_sandbox({("POST", "/v1/analyses"): (401, {"detail": "Unauthorized"})})).execute(
        "c1", "run_python_analysis", json.dumps(run_args()))
    assert not outcome.ok and outcome.error_code == "TOOL_ERROR" and SANDBOX_KEY not in json.dumps(outcome.output)


# --- capabilities and startup gating --------------------------------------------------------------

def capabilities(reg) -> dict[str, Any]:
    return reg.execute("c1", "get_system_capabilities", "{}").output["result"]


def test_python_analysis_capability_follows_the_registry() -> None:
    assert capabilities(registry())["python_analysis"] is False
    full = capabilities(registry(mock_sandbox({}), mock_governor(200, {})))
    assert full["python_analysis"] is True
    assert {"create_analysis_spec", "run_python_analysis", "get_analysis_result", "get_dataset_manifest"} <= set(
        full["available_tools"])


def test_startup_registers_analysis_tools_only_when_the_sandbox_is_ready(monkeypatch) -> None:
    from app import main

    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    env = {"PY_SANDBOX_URL": "http://sandbox.test", "PY_SANDBOX_API_KEY": SANDBOX_KEY}
    for ready, expected in ((False, False), (True, True)):
        monkeypatch.setattr(SandboxClient, "ready", lambda self, value=ready: value)
        app = main.create_app(make_settings(**env))
        caps = app.state.orchestrator.registry.execute("c1", "get_system_capabilities", "{}").output["result"]
        assert caps["python_analysis"] is expected


@pytest.mark.parametrize(("overrides", "message"), [
    ({"PY_SANDBOX_URL": "http://sandbox.test"}, "PY_SANDBOX_API_KEY"),
    ({"PY_SANDBOX_URL": "ftp://x", "PY_SANDBOX_API_KEY": SANDBOX_KEY}, "http"),
    ({"PY_SANDBOX_POLL_WAIT_SECONDS": "40", "PY_SANDBOX_REQUEST_TIMEOUT_SECONDS": "45"}, "10 s below"),
    ({"ANALYSIS_TIMEZONE": "Mars/Olympus"}, "ANALYSIS_TIMEZONE"),
])
def test_sandbox_configuration_is_validated(overrides: dict, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        make_settings(**overrides)


# --- agent loop and the validation gate -------------------------------------------------------------

ANSWER = {"response_type": "ANSWER", "answer": "27 saham memenuhi kriteria.", "clarification_question": None,
          "assumptions": [], "limitations": ["numeric stored as float64"]}


def orchestrate(responses: dict, script: list, message: str = "Hitung z-score 20 hari semua saham 3 bulan terakhir",
                history: list[HistoryMessage] | None = None):
    scripted = ScriptedClient(script)
    orchestrator = AgentOrchestrator(make_settings(), scripted, registry(mock_sandbox(responses)),
                                     wall_clock=lambda: REFERENCE)
    result = orchestrator.run(AgentRunRequest(request_id="gate", message=message, history=history or []))
    return result, scripted


def test_agent_runs_spec_then_analysis_then_result_and_reports_both_statuses() -> None:
    seen: list = []
    sandbox_responses = {
        ("POST", "/v1/specs"): (200, approved()),
        ("POST", "/v1/analyses"): (200, completed(execution_status="RUNNING", validation_status="PENDING",
                                                  next_action="GET_ANALYSIS_RESULT", outputs=[])),
        ("GET", f"/v1/analyses/{ANA}"): (200, completed())}
    scripted = ScriptedClient([
        tool_call_response("create_analysis_spec", json.dumps(spec_args()), call_id="c1"),
        tool_call_response("run_python_analysis", json.dumps(run_args()), call_id="c2"),
        tool_call_response("get_analysis_result", json.dumps({"analysis_id": ANA}), call_id="c3"),
        final_response(ANSWER)])
    result = AgentOrchestrator(make_settings(), scripted, registry(mock_sandbox(sandbox_responses, seen)),
                               wall_clock=lambda: REFERENCE).run(
        AgentRunRequest(request_id="acc", message="Hitung z-score 20 hari semua saham 3 bulan terakhir"))
    assert result.status == "COMPLETED" and result.response.response_type == "ANSWER"
    assert [(a.execution_status, a.validation_status, a.validation_level) for a in result.execution.analyses] == [
        ("COMPLETED", "PASS", "CALCULATION_VERIFIED")]
    assert result.execution.validation_gate == "PASSED"
    assert seen[0]["body"]["user_messages"][-1]["content"].startswith("Hitung z-score")
    assert SANDBOX_KEY not in json.dumps(scripted.payloads)


def test_gate_rejects_an_answer_on_a_failed_validation_once_then_forces_limitation() -> None:
    failed = completed(validation_status="FAILED", validation_level="EXECUTION_ONLY",
                       reason_codes=["ANALYSIS_SCOPE_MISMATCH"], next_action="REVISE_ANALYSIS")
    result, scripted = orchestrate({("POST", "/v1/analyses"): (200, failed)}, [
        tool_call_response("run_python_analysis", json.dumps(run_args()), call_id="c1"),
        final_response(ANSWER, response_id="r1"), final_response(ANSWER, response_id="r2")])
    rejection = [i["content"] for i in scripted.payloads[-1]["input"] if i.get("role") == "user"][-1]
    assert "did not pass validation" in rejection and "ANALYSIS_SCOPE_MISMATCH" in rejection
    assert scripted.payloads[-1].get("tools")  # the model may still repair the analysis
    assert result.status == "LIMITED" and result.response.response_type == "LIMITATION"
    assert result.response.answer.startswith("Validation did not pass")
    assert any("validation FAILED (ANALYSIS_SCOPE_MISMATCH)" in line for line in result.response.limitations)
    assert result.execution.validation_gate == "FORCED_LIMITATION"


def test_gate_accepts_a_repaired_rerun_and_annotates_the_validation_level() -> None:
    failed = completed(validation_status="FAILED", reason_codes=["CALCULATION_MISMATCH"], validation_level="SCOPE_VERIFIED")
    fixed = completed(analysis_id=ANA2, validation_status="PASS", validation_level="SCOPE_VERIFIED")
    result, _ = orchestrate({("POST", "/v1/analyses"): [(200, failed), (200, fixed)]}, [
        tool_call_response("run_python_analysis", json.dumps(run_args()), call_id="c1"),
        final_response(ANSWER, response_id="r1"),
        tool_call_response("run_python_analysis", json.dumps(run_args(python_code="print(2)")), call_id="c2"),
        final_response(ANSWER, response_id="r2")])
    assert result.status == "COMPLETED" and result.response.response_type == "ANSWER"
    assert any("level SCOPE_VERIFIED" in line for line in result.response.limitations)
    assert [a.validation_status for a in result.execution.analyses] == ["FAILED", "PASS"]
    assert result.execution.validation_gate == "ANNOTATED"


@pytest.mark.parametrize(("overrides", "expected"), [
    ({"validation_status": "UNVERIFIED", "validation_level": "EXECUTION_ONLY"}, "validation UNVERIFIED"),
    ({"execution_status": "FAILED", "validation_status": "UNVERIFIED",
      "error": {"code": "INPUT_VALIDATION_FAILED", "message": "m"}}, "did not complete (INPUT_VALIDATION_FAILED)"),
])
def test_gate_annotates_unverified_and_blocks_failed_executions(overrides: dict, expected: str) -> None:
    result, _ = orchestrate({("POST", "/v1/analyses"): (200, completed(**overrides))}, [
        tool_call_response("run_python_analysis", json.dumps(run_args()), call_id="c1"),
        final_response(ANSWER, response_id="r1"), final_response(ANSWER, response_id="r2")])
    assert any(expected in line for line in result.response.limitations)
    if overrides.get("execution_status") == "FAILED":
        assert result.response.response_type == "LIMITATION"
    else:
        assert result.response.response_type == "ANSWER" and result.execution.validation_gate == "ANNOTATED"


def test_gate_discloses_unverified_spec_requirements() -> None:
    spec = approved(status="APPROVED_WITH_UNVERIFIED", unverified_requirements=[
        {"requirement": "calculation.z20.window", "result": "UNVERIFIED"}])
    result, _ = orchestrate({("POST", "/v1/specs"): (200, spec), ("POST", "/v1/analyses"): (200, completed())}, [
        tool_call_response("create_analysis_spec", json.dumps(spec_args()), call_id="c1"),
        tool_call_response("run_python_analysis", json.dumps(run_args()), call_id="c2"),
        final_response(ANSWER)])
    assert result.response.response_type == "ANSWER"
    assert any("calculation.z20.window" in line for line in result.response.limitations)


def test_clarification_is_never_blocked_by_the_gate() -> None:
    failed = completed(validation_status="FAILED", reason_codes=["UNIVERSE_MISMATCH"])
    clarification = {"response_type": "CLARIFICATION", "answer": "", "clarification_question": "Which period?",
                     "assumptions": [], "limitations": []}
    result, _ = orchestrate({("POST", "/v1/analyses"): (200, failed)}, [
        tool_call_response("run_python_analysis", json.dumps(run_args()), call_id="c1"),
        final_response(clarification)])
    assert result.status == "NEEDS_CLARIFICATION"
