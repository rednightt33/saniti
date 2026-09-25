"""Analysis session tools: registration behind the flag, request shapes, per-call timeouts and rejections."""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.tools import build_default_registry
from app.tools.analysis import SandboxClient
from app.tools.request_data import GovernorClient, current_request_id
from test_analysis_tools import SANDBOX_KEY, sandbox_module

SESSION = "sess_" + "a" * 24
BUNDLE = "bundle_" + "b" * 24
OUTPUT = "out_" + "c" * 24


class FakeSandbox:
    def __init__(self, answers: dict[str, tuple[int, dict]] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append({"method": request.method, "path": request.url.path, "body": body,
                           "params": dict(request.url.params), "timeout": request.extensions.get("timeout")})
        status, payload = self.answers.get(request.url.path, (200, {"status": "OK", "path": request.url.path}))
        return httpx.Response(status, json=payload)


def registry(fake: FakeSandbox, enabled: bool = True):
    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    return build_default_registry(sandbox_client=sandbox, governor_client=governor, dataneed_enabled=enabled,
                                  session_timeout_seconds=200)


def call(reg, name: str, arguments: dict[str, Any]):
    token = current_request_id.set("run-session-1")
    try:
        return reg.execute("c1", name, arguments)
    finally:
        current_request_id.reset(token)


TOOLS = {"open_analysis_session", "run_python", "inspect_session", "get_session_output", "complete_analysis"}


def test_the_session_tools_exist_only_behind_the_flag() -> None:
    assert TOOLS <= set(registry(FakeSandbox()).names())
    assert not TOOLS & set(registry(FakeSandbox(), enabled=False).names())


def test_requests_carry_the_run_request_id_and_run_python_waits_longer() -> None:
    fake = FakeSandbox()
    reg = registry(fake)
    assert call(reg, "open_analysis_session", {"input_bundle_id": BUNDLE}).ok
    assert call(reg, "run_python", {"session_id": SESSION, "code": "x = 1"}).ok
    assert call(reg, "inspect_session", {"session_id": SESSION, "names": ["x"], "max_rows": None}).ok
    assert call(reg, "get_session_output", {"session_id": SESSION, "output_id": OUTPUT, "offset": None,
                                            "limit": 20}).ok
    opened, run, inspect, output = fake.calls
    assert opened["body"] == {"request_id": "run-session-1", "bundle_id": BUNDLE}
    assert run["path"] == f"/v1/sessions/{SESSION}/execute" and run["body"]["code"] == "x = 1"
    assert run["timeout"]["read"] == 200 and opened["timeout"]["read"] < 200
    assert inspect["body"] == {"request_id": "run-session-1", "max_rows": 5, "names": ["x"]}
    assert output["params"] == {"request_id": "run-session-1", "offset": "0", "limit": "20"}


def test_a_closed_session_is_a_structured_rejection() -> None:
    fake = FakeSandbox({f"/v1/sessions/{SESSION}/execute": (409, {
        "status": "REJECTED", "error": {"code": "SESSION_CLOSED", "message": "closed", "close_reason": "SESSION_IDLE"},
        "next_action": "OPEN_ANALYSIS_SESSION"})})
    outcome = call(registry(fake), "run_python", {"session_id": SESSION, "code": "print(1)"})
    assert outcome.ok and outcome.output["result"] == {"status": "REJECTED", "code": "SESSION_CLOSED",
                                                       "message": "closed", "next_action": "OPEN_ANALYSIS_SESSION",
                                                       "close_reason": "SESSION_IDLE"}


def test_an_unavailable_sandbox_is_a_tool_error() -> None:
    fake = FakeSandbox({"/v1/sessions": (502, {"detail": "bad gateway"})})
    outcome = call(registry(fake), "open_analysis_session", {"input_bundle_id": BUNDLE})
    assert not outcome.ok and outcome.error_code == "TOOL_ERROR"


def test_the_code_limit_equals_the_sandbox_limit() -> None:
    config = sandbox_module("config")
    settings = config.Settings.from_env({"PY_SANDBOX_API_KEY": "k" * 40, "SQL_GOVERNOR_URL": "http://g",
                                         "SQL_GOVERNOR_DATASET_ACCESS_KEY": "a" * 40})
    from app.tools.session import RunPythonArgs

    assert RunPythonArgs.model_fields["code"].metadata[1].max_length == settings.max_code_chars


def test_complete_analysis_attaches_the_released_contents() -> None:
    table, chart = "out_" + "1" * 24, "out_" + "2" * 24
    fake = FakeSandbox({
        f"/v1/sessions/{SESSION}/complete": (200, {
            "status": "COMPLETED", "final_status": {"evidence_label": "DATA_COVERAGE_VERIFIED"},
            "released_outputs": [{"output_id": table, "name": "t", "type": "TABLE"},
                                 {"output_id": chart, "name": "c", "type": "CHART"}]}),
        f"/v1/sessions/{SESSION}/outputs/{table}": (200, {"released": True, "rows": [{"ticker": "BBCA", "ret": 0.12}],
                                                          "row_count": 1, "next_offset": None})})
    outcome = call(registry(fake), "complete_analysis", {"session_id": SESSION})
    result = outcome.output["result"]
    assert result["released_contents"] == [{"output_id": table, "name": "t", "type": "TABLE",
                                            "rows": [{"ticker": "BBCA", "ret": 0.12}], "row_count": 1,
                                            "truncated": False}]
    assert [c["path"] for c in fake.calls] == [f"/v1/sessions/{SESSION}/complete",
                                               f"/v1/sessions/{SESSION}/outputs/{table}"]


def test_an_incomplete_analysis_fetches_nothing() -> None:
    fake = FakeSandbox({f"/v1/sessions/{SESSION}/complete": (200, {
        "status": "INCOMPLETE", "released_outputs": [], "next_action": "RUN_PYTHON"})})
    result = call(registry(fake), "complete_analysis", {"session_id": SESSION}).output["result"]
    assert "released_contents" not in result and len(fake.calls) == 1
