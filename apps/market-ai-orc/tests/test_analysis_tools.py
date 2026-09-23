"""get_dataset_manifest, run_python_analysis, get_analysis_result: schemas, contracts, and pass-through."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import ConfigError
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest
from app.tools import build_default_registry
from app.tools.analysis import RunPythonAnalysisArgs, SandboxClient
from app.tools.request_data import GovernorClient, current_request_id
from conftest import ScriptedClient, final_response, make_settings, tool_call_response

SANDBOX_ROOT = Path(__file__).resolve().parents[2] / "market-python-sandbox"
DS, DS2 = "ds_" + "a" * 24, "ds_" + "b" * 24
ANA = "ana_" + "c" * 24
SANDBOX_KEY = "s" * 40


def sandbox_models():
    """Import apps/market-python-sandbox/app/models.py (both services name their package 'app')."""
    name = "sandbox_app_models"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, SANDBOX_ROOT / "app/models.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def completed(**overrides: Any) -> dict[str, Any]:
    return {
        "analysis_id": ANA, "status": "COMPLETED", "next_action": "USE_ANALYSIS_RESULT", "request_id": "r",
        "purpose": "screen", "dataset_ids": [DS], "expected_outputs": ["TABLE"], "created_at": "2026-09-23T00:00:00+00:00",
        "runtime_ms": 3200, "retry_after_seconds": None,
        "outputs": [{"type": "TABLE", "name": "screen_result", "row_count": 27, "columns": [{"name": "ticker",
                     "type": "string"}], "preview_rows": [["AAAA"]], "preview_row_count": 1, "preview_truncated": True,
                     "result_id": "res_" + "d" * 24}],
        "warnings": [{"code": "NUMERIC_AS_FLOAT64", "message": "float64"}], "error": None,
        "diagnostics": {"stdout_tail": "x" * 5000},
        "lineage": {"runtime_version": "market-python-sandbox/v1", "code_sha256": "e" * 64, "seed": 0,
                    "library_versions": {"talib": "0.8.1"}, "limits": {"max_runtime_seconds": 120},
                    "deployment_id": "dep-1", "datasets": {DS: {"checksum_sha256": "f" * 64}}},
        "resource_usage": {"cpu_seconds": 1.0}, "outputs_expire_at": "2026-09-24T00:00:00+00:00", **overrides}


def mock_sandbox(responses: dict[tuple[str, str], tuple[int, dict]], seen: list | None = None) -> SandboxClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append({"method": request.method, "path": request.url.path, "params": dict(request.url.params),
                         "auth": request.headers.get("authorization"),
                         "body": json.loads(request.content) if request.content else None})
        status, body = responses.get((request.method, request.url.path), (404, {"detail": "Not Found"}))
        return httpx.Response(status, json=body)
    return SandboxClient("http://sandbox.test", SANDBOX_KEY, 5, 20, transport=httpx.MockTransport(handler))


def mock_governor(status: int, body: dict) -> GovernorClient:
    return GovernorClient("http://governor.test", "g" * 40, 5,
                          transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)))


def registry(sandbox: SandboxClient | None = None, governor: GovernorClient | None = None):
    return build_default_registry(None, governor_client=governor, sandbox_client=sandbox, sandbox_timeout_seconds=5)


def run_args(**overrides: Any) -> dict[str, Any]:
    return {"purpose": "Screen RSI < 30", "dataset_ids": [DS], "python_code": "print(1)",
            "expected_outputs": ["TABLE", "METRICS"], **overrides}


# --- schemas and contract ------------------------------------------------------------------------

def test_tool_schemas_are_strict_and_expose_no_limits_or_paths() -> None:
    definitions = {d["name"]: d for d in registry(mock_sandbox({}), mock_governor(200, {})).definitions()}
    expected = {"get_dataset_manifest": {"dataset_id"}, "get_analysis_result": {"analysis_id"},
                "run_python_analysis": {"purpose", "dataset_ids", "python_code", "expected_outputs"}}
    for name, fields in expected.items():
        params = definitions[name]["parameters"]
        assert definitions[name]["strict"] is True and set(params["properties"]) == fields
        assert params["additionalProperties"] is False and params["required"] == list(params["properties"])
    outputs = definitions["run_python_analysis"]["parameters"]["properties"]["expected_outputs"]
    assert outputs["items"]["enum"] == ["TABLE", "METRICS", "CHART", "ARTIFACT"]
    text = json.dumps([definitions[name] for name in expected])
    for forbidden in ("max_runtime", "memory", "timeout", "bucket", "railway", "http", "file_path", "postgres"):
        assert forbidden not in text.lower().replace("python_code", ""), forbidden


@pytest.mark.parametrize("bad", [
    {"dataset_ids": []}, {"dataset_ids": [DS, DS]}, {"dataset_ids": ["ds_1"]},
    {"dataset_ids": [DS, DS2, "ds_" + "c" * 24, "ds_" + "d" * 24, "ds_" + "e" * 24]},
    {"python_code": "x" * 20001}, {"purpose": "x" * 1001}, {"expected_outputs": ["TEXT"]},
    {"expected_outputs": ["TABLE", "TABLE"]}, {"max_runtime_seconds": 900}, {"memory_mb": 8192},
])
def test_run_python_analysis_rejects_invalid_or_limit_raising_arguments(bad: dict) -> None:
    seen: list = []
    outcome = registry(mock_sandbox({}, seen)).execute("c1", "run_python_analysis", json.dumps(run_args(**bad)))
    assert not outcome.ok and outcome.error_code == "INVALID_ARGUMENTS" and seen == []


def test_request_model_matches_the_sandbox_contract() -> None:
    sandbox = sandbox_models().AnalysisRequest
    assert set(sandbox.model_fields) - {"request_id"} == set(RunPythonAnalysisArgs.model_fields)
    for args in (run_args(), run_args(dataset_ids=[DS, DS2], expected_outputs=["CHART", "ARTIFACT"])):
        sandbox.model_validate({"request_id": "r1", **RunPythonAnalysisArgs.model_validate(args).model_dump()})


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
    bad = registry(governor=mock_governor(200, {})).execute("c1", "get_dataset_manifest", '{"dataset_id": "x"}')
    assert bad.error_code == "INVALID_ARGUMENTS"


# --- run_python_analysis / get_analysis_result -----------------------------------------------------

def test_submission_forwards_request_id_and_returns_a_compact_model_view() -> None:
    seen: list = []
    sandbox = mock_sandbox({("POST", "/v1/analyses"): (200, completed())}, seen)
    token = current_request_id.set("agent-run-7")
    try:
        outcome = registry(sandbox).execute("c1", "run_python_analysis", json.dumps(run_args()))
    finally:
        current_request_id.reset(token)
    assert seen[0]["auth"] == f"Bearer {SANDBOX_KEY}" and seen[0]["body"] == {"request_id": "agent-run-7", **run_args()}
    result = outcome.output["result"]
    assert result["status"] == "COMPLETED" and result["outputs"][0]["result_id"].startswith("res_")
    assert "limits" not in result["lineage"] and "deployment_id" not in result["lineage"]
    assert "resource_usage" not in result and len(result["diagnostics"]["stdout_tail"]) == 1000


def test_running_results_are_polled_with_a_bounded_wait() -> None:
    seen: list = []
    running = completed(status="RUNNING", next_action="GET_ANALYSIS_RESULT", retry_after_seconds=15, outputs=[],
                        diagnostics=None)
    sandbox = mock_sandbox({("GET", f"/v1/analyses/{ANA}"): (200, running)}, seen)
    outcome = registry(sandbox).execute("c1", "get_analysis_result", json.dumps({"analysis_id": ANA}))
    assert outcome.output["result"]["status"] == "RUNNING" and outcome.output["result"]["retry_after_seconds"] == 15
    assert seen[0]["params"] == {"wait_seconds": "20"}
    missing = registry(mock_sandbox({})).execute("c1", "get_analysis_result", json.dumps({"analysis_id": ANA}))
    assert missing.output["result"]["status"] == "NOT_FOUND"
    assert registry(sandbox).execute("c1", "get_analysis_result", '{"analysis_id": "ana_1"}').error_code == \
        "INVALID_ARGUMENTS"


@pytest.mark.parametrize(("status", "code", "action"), [
    (429, "QUEUE_FULL", "RETRY_LATER"), (503, "SANDBOX_ISOLATION_UNAVAILABLE", "REPORT_LIMITATION"),
    (422, "INVALID_REQUEST", "REVISE_ANALYSIS"),
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
    with_governor = capabilities(registry(governor=mock_governor(200, {})))
    assert with_governor["python_analysis"] is False and "get_dataset_manifest" in with_governor["available_tools"]
    full = capabilities(registry(mock_sandbox({}), mock_governor(200, {})))
    assert full["python_analysis"] is True
    assert {"run_python_analysis", "get_analysis_result", "get_dataset_manifest"} <= set(full["available_tools"])


def test_startup_registers_analysis_tools_only_when_the_sandbox_is_ready(monkeypatch) -> None:
    from app import main

    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    env = {"PY_SANDBOX_URL": "http://sandbox.test", "PY_SANDBOX_API_KEY": SANDBOX_KEY}
    for ready, expected in ((False, False), (True, True)):
        monkeypatch.setattr(SandboxClient, "ready", lambda self, value=ready: value)
        app = main.create_app(make_settings(**env))
        caps = app.state.orchestrator.registry.execute("c1", "get_system_capabilities", "{}").output["result"]
        assert caps["python_analysis"] is expected
    assert capabilities(main.create_app(make_settings()).state.orchestrator.registry)["python_analysis"] is False


@pytest.mark.parametrize(("overrides", "message"), [
    ({"PY_SANDBOX_URL": "http://sandbox.test"}, "PY_SANDBOX_API_KEY"),
    ({"PY_SANDBOX_URL": "ftp://x", "PY_SANDBOX_API_KEY": SANDBOX_KEY}, "http"),
    ({"PY_SANDBOX_POLL_WAIT_SECONDS": "40", "PY_SANDBOX_REQUEST_TIMEOUT_SECONDS": "45"}, "10 s below"),
])
def test_sandbox_configuration_is_validated(overrides: dict, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        make_settings(**overrides)


# --- agent loop ------------------------------------------------------------------------------------

def test_agent_runs_manifest_then_analysis_then_result() -> None:
    manifest = {"status": "AVAILABLE", "dataset_id": DS, "row_count": 214023, "entities_present_count": 844}
    sandbox = mock_sandbox({
        ("POST", "/v1/analyses"): (200, completed(status="RUNNING", next_action="GET_ANALYSIS_RESULT", outputs=[],
                                                  retry_after_seconds=15)),
        ("GET", f"/v1/analyses/{ANA}"): (200, completed())})
    answer = {"response_type": "ANSWER", "answer": "27 saham memenuhi kriteria.", "clarification_question": None,
              "assumptions": [], "limitations": ["numeric stored as float64"]}
    scripted = ScriptedClient([
        tool_call_response("get_dataset_manifest", json.dumps({"dataset_id": DS}), call_id="c1"),
        tool_call_response("run_python_analysis", json.dumps(run_args()), call_id="c2"),
        tool_call_response("get_analysis_result", json.dumps({"analysis_id": ANA}), call_id="c3"),
        final_response(answer)])
    result = AgentOrchestrator(make_settings(), scripted, registry(sandbox, mock_governor(200, manifest))).run(
        AgentRunRequest(request_id="acc-a", message="Screen RSI < 30 and bullish engulfing."))
    assert result.status == "COMPLETED" and result.execution.tool_call_count == 3
    outputs = [json.loads(i["output"]) for i in scripted.payloads[-1]["input"] if i.get("type") == "function_call_output"]
    assert [o["result"]["status"] for o in outputs] == ["AVAILABLE", "RUNNING", "COMPLETED"]
    assert SANDBOX_KEY not in json.dumps(scripted.payloads)
