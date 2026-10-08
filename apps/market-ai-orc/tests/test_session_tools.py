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
                                            "label": "DATA_COVERAGE_VERIFIED",
                                            "rows": [{"ticker": "BBCA", "ret": 0.12}], "row_count": 1,
                                            "truncated": False}]
    assert [c["path"] for c in fake.calls] == [f"/v1/sessions/{SESSION}/complete",
                                               f"/v1/sessions/{SESSION}/outputs/{table}"]


def period_return_rows(count: int) -> list[dict[str, Any]]:
    """Rows shaped like saniti.period_return's frame (11 columns, full precision): 200 of them take about 57 KB."""
    return [{"entity": f"T{i:03d}X", "base_date": "2024-12-30", "base_value": 1315.0 + i, "end_date": "2025-12-30",
             "end_value": 5575.0 - i, "return_decimal": 3.2395437262357416 - i / 997, "return_pct":
             323.95437262357416 - i / 9.97, "calculation_status": "COMPLETE", "range_id": "data_request_1_A_r1",
             "period_start": "2025-01-01", "period_end": "2025-12-31"} for i in range(count)]


def test_a_wide_released_table_is_cut_to_fit_the_result_limit_instead_of_hiding_the_completion() -> None:
    table, summary = "out_" + "1" * 24, "out_" + "2" * 24
    rows = period_return_rows(200)
    assert len(json.dumps(rows, separators=(",", ":")).encode()) > 40000  # the dev failure: TOOL_RESULT_TOO_LARGE
    fake = FakeSandbox({
        f"/v1/sessions/{SESSION}/complete": (200, {
            "status": "COMPLETED", "final_status": {"evidence_label": "DATA_COVERAGE_VERIFIED"},
            "released_outputs": [{"output_id": table, "name": "returns", "type": "TABLE"},
                                 {"output_id": summary, "name": "summary", "type": "JSON"}]}),
        f"/v1/sessions/{SESSION}/outputs/{table}": (200, {"released": True, "rows": rows, "row_count": 835,
                                                          "next_offset": 200}),
        f"/v1/sessions/{SESSION}/outputs/{summary}": (200, {"released": True, "content": {"up": 586, "down": 210},
                                                            "next_offset": None})})
    outcome = call(registry(fake), "complete_analysis", {"session_id": SESSION})
    assert outcome.ok, outcome.output
    assert len(json.dumps(outcome.output, separators=(",", ":"), ensure_ascii=False).encode()) <= 40000
    first, second = outcome.output["result"]["released_contents"]
    assert 0 < len(first["rows"]) < 200 and first["rows"] == rows[:len(first["rows"])]
    assert first["row_count"] == 835 and first["truncated"] is True and "get_session_output" in first["note"]
    assert not any(ch.isdigit() for ch in first["note"])  # provenance reads the numbers of released content
    # the small summary is kept whole; the wide table takes what is left
    assert second == {"output_id": summary, "name": "summary", "type": "JSON", "label": "DATA_COVERAGE_VERIFIED",
                      "content": {"up": 586, "down": 210}, "truncated": False}


def test_two_wide_tables_share_the_result_budget() -> None:
    first_id, second_id = "out_" + "4" * 24, "out_" + "5" * 24
    rows = period_return_rows(200)
    fake = FakeSandbox({
        f"/v1/sessions/{SESSION}/complete": (200, {
            "status": "COMPLETED", "final_status": {"evidence_label": "DATA_COVERAGE_VERIFIED"},
            "released_outputs": [{"output_id": first_id, "name": "a", "type": "TABLE"},
                                 {"output_id": second_id, "name": "b", "type": "TABLE"}]}),
        f"/v1/sessions/{SESSION}/outputs/{first_id}": (200, {"released": True, "rows": rows, "row_count": 200,
                                                             "next_offset": None}),
        f"/v1/sessions/{SESSION}/outputs/{second_id}": (200, {"released": True, "rows": rows, "row_count": 200,
                                                              "next_offset": None})})
    outcome = call(registry(fake), "complete_analysis", {"session_id": SESSION})
    assert outcome.ok
    a, b = outcome.output["result"]["released_contents"]
    assert a["truncated"] and b["truncated"] and abs(len(a["rows"]) - len(b["rows"])) <= 1 and len(b["rows"]) > 20


def test_a_released_json_too_large_for_the_result_is_left_to_get_session_output() -> None:
    blob = "out_" + "3" * 24
    fake = FakeSandbox({
        f"/v1/sessions/{SESSION}/complete": (200, {
            "status": "COMPLETED", "final_status": {"evidence_label": "DATA_COVERAGE_VERIFIED"},
            "released_outputs": [{"output_id": blob, "name": "blob", "type": "JSON"}]}),
        f"/v1/sessions/{SESSION}/outputs/{blob}": (200, {"released": True, "content": {"x": ["y" * 100] * 600},
                                                         "next_offset": None})})
    outcome = call(registry(fake), "complete_analysis", {"session_id": SESSION})
    assert outcome.ok
    (entry,) = outcome.output["result"]["released_contents"]
    assert entry["content"] is None and entry["truncated"] is True and "get_session_output" in entry["note"]


def test_an_incomplete_analysis_fetches_nothing() -> None:
    fake = FakeSandbox({f"/v1/sessions/{SESSION}/complete": (200, {
        "status": "INCOMPLETE", "released_outputs": [], "next_action": "RUN_PYTHON"})})
    result = call(registry(fake), "complete_analysis", {"session_id": SESSION}).output["result"]
    assert "released_contents" not in result and len(fake.calls) == 1


# --- S05: capacity refusals and closing the sessions a run leaves open --------------------------------------------

def test_a_capacity_refusal_pauses_the_answer_instead_of_forbidding_a_retry() -> None:
    """EXEC-W A5 (user decision 2026-10-08): the backend did the waiting; the model hears what happened and that the
    answer pauses with a question (no "do not retry")."""
    fake = FakeSandbox({"/v1/sessions": (429, {
        "status": "REJECTED", "error": {"code": "SESSION_CAPACITY_EXCEEDED", "message": "Every slot is in use.",
                                        "retry_after_seconds": 30}, "next_action": "RETRY_LATER"})})
    result = call(registry(fake), "open_analysis_session", {"input_bundle_id": BUNDLE}).output["result"]
    assert result["code"] == "SESSION_CAPACITY_EXCEEDED" and result["next_action"] == "PAUSE_ANSWER"
    assert "retry_after_seconds" not in result and "Do not retry" not in result["message"]
    assert "waited and retried" in result["message"] and "pauses" in result["message"]
    assert not any(ch.isdigit() for ch in result["message"])  # provenance reads the numbers of tool results


def test_the_backend_waits_for_a_slot_while_the_answer_has_time() -> None:
    from app.tools.request_data import current_run_deadline
    from app.tools.session import BUSY_RESERVE_SECONDS, open_with_wait

    busy = (429, {"status": "REJECTED", "error": {"code": "SESSION_CAPACITY_EXCEEDED", "message": "busy"}})
    replies = [busy, busy, (200, {"session_id": SESSION, "status": "ACTIVE"})]
    fake = FakeSandbox({})
    fake.handler = lambda request: (fake.calls.append({"path": request.url.path}) or
                                    httpx.Response(replies[min(len(fake.calls) - 1, 2)][0],
                                                   json=replies[min(len(fake.calls) - 1, 2)][1]))
    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    sandbox.open_wait_seconds = 60
    now, slept = [1000.0], []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    token = current_run_deadline.set(1000.0 + BUSY_RESERVE_SECONDS + 600)
    try:
        opened = open_with_wait(sandbox, {"request_id": "run-1", "bundle_id": BUNDLE}, 10,
                                clock=lambda: now[0], sleep=sleep)
        assert opened["session_id"] == SESSION and opened["open_attempts"] == 3 and len(fake.calls) == 3
        assert slept == [60, 60]  # instant refusals are paced at the sandbox's own hold
        # with no time left in the answer, it stops at once and pauses
        replies[2] = busy
        fake.calls.clear()
        current_run_deadline.set(now[0] + BUSY_RESERVE_SECONDS + 30)
        stopped = open_with_wait(sandbox, {"request_id": "run-1", "bundle_id": BUNDLE}, 10,
                                 clock=lambda: now[0], sleep=sleep)
        assert stopped["next_action"] == "PAUSE_ANSWER" and len(fake.calls) == 1
    finally:
        current_run_deadline.reset(token)


def test_close_sessions_closes_each_session_of_the_request_and_never_raises() -> None:
    from app.tools.session import close_sessions

    other = "sess_" + "d" * 24
    fake = FakeSandbox({
        f"/v1/sessions/{SESSION}/close": (200, {"session_id": SESSION, "status": "CLOSED",
                                               "close_reason": "CLOSED_BY_CALLER"}),
        f"/v1/sessions/{other}/close": (404, {"status": "REJECTED", "error": {"code": "SESSION_NOT_FOUND",
                                                                              "message": "no"}})})
    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    assert close_sessions(sandbox, "run-1", [SESSION, other]) == {SESSION: "CLOSED_BY_CALLER",
                                                                  other: "SESSION_NOT_FOUND"}
    assert [c["body"] for c in fake.calls] == [{"request_id": "run-1"}] * 2
    down = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(
        lambda r: httpx.Response(502, text="bad gateway")))
    assert close_sessions(down, "run-1", [SESSION]) == {SESSION: "CLOSE_FAILED"}


def test_s28_release_and_the_capacity_wait() -> None:
    """S28: the answer's end posts the request's release; an open after the sandbox's wait says how long it waited
    and still tells the model to report the limitation."""
    import httpx

    from app.tools.analysis import SandboxClient
    from app.tools.session import release_request, session_specs

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.extensions.get("timeout")))
        if request.url.path.endswith("/release"):
            return httpx.Response(200, json={"request_id": "r1", "sessions": [
                {"session_id": "sess_" + "a" * 24, "status": "WARM_IDLE"}]})
        return httpx.Response(429, json={"status": "REJECTED", "error": {
            "code": "SESSION_CAPACITY_EXCEEDED", "message": "busy", "waited_seconds": 60, "retry_after_seconds": 15}})

    client = SandboxClient("http://s", "s" * 40, 45, 20, transport=httpx.MockTransport(handler))
    assert release_request(client, "r1") == [{"session_id": "sess_" + "a" * 24, "status": "WARM_IDLE"}]
    client.open_wait_seconds = 60
    specs = {s.name: s for s in session_specs(client, timeout_seconds=45, execution_timeout_seconds=150,
                                                    max_result_bytes=60_000)}
    import time

    from app.tools.request_data import current_run_deadline
    from app.tools.session import BUSY_RESERVE_SECONDS
    token = current_run_deadline.set(time.monotonic() + BUSY_RESERVE_SECONDS + 30)  # no time left for another try
    try:
        result = specs["open_analysis_session"].handler(
            specs["open_analysis_session"].arguments_model.model_validate({"input_bundle_id": "bundle_" + "1" * 24}))
    finally:
        current_run_deadline.reset(token)
    assert result["code"] == "SESSION_CAPACITY_EXCEEDED" and result["next_action"] == "PAUSE_ANSWER"
    assert result["waited_seconds"] == 60 and result["open_attempts"] == 1 and "retry_after_seconds" not in result
    assert seen[-1][2]["read"] == 105  # the request timeout plus the sandbox's wait


def test_r_store_file_copy_restore_upload_and_the_open_hook() -> None:
    """R-STORE: a released file is copied only when its checksum matches; a stored table is uploaded with its
    metadata in a base64url header; a session that opens gets the conversation's missing tables back and says so."""
    import base64
    import hashlib
    import json

    import httpx
    import pytest

    from app.tools.analysis import SandboxClient
    from app.tools.registry import ToolError
    from app.tools.session import current_carried_restorer, output_file, restore_carried, restore_into

    data, seen = b"PAR1 table", {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            checksum = hashlib.sha256(data).hexdigest() if "good" in request.url.path else "0" * 64
            return httpx.Response(200, content=data, headers={"X-Saniti-Checksum-Sha256": checksum})
        meta = request.headers["X-Saniti-Output-Meta"]
        seen["meta"] = json.loads(base64.urlsafe_b64decode(meta + "==="))
        seen["body"] = request.content
        return httpx.Response(200, json={"output_id": seen["meta"]["output_id"], "status": "RESTORED"})

    client = SandboxClient("http://s", "s" * 40, 45, 20, transport=httpx.MockTransport(handler))
    assert output_file(client, "sess_" + "a" * 24, "out_good", "r1") == data
    with pytest.raises(ToolError):
        output_file(client, "sess_" + "a" * 24, "out_bad", "r1")
    answer = restore_carried(client, "sess_" + "a" * 24, "r1", {"output_id": "out_" + "1" * 24, "name": "t"}, data)
    assert answer["status"] == "RESTORED" and seen["body"] == data and seen["meta"]["name"] == "t"

    view = {"session_id": "sess_" + "a" * 24}
    token = current_carried_restorer.set(lambda sid, v, allowed: [{"output_id": "out_" + "1" * 24, "name": "t",
                                                                   "status": "RESTORED", "allowed": allowed}])
    try:
        restore_into(view, None)
    finally:
        current_carried_restorer.reset(token)
    assert view["restored_outputs"] == [{"output_id": "out_" + "1" * 24, "name": "t", "status": "RESTORED"}]
    assert "load_output" in view["restored_note"]
    rejected = {"status": "REJECTED"}
    restore_into(rejected, None)  # no session, no restorer: unchanged
    assert rejected == {"status": "REJECTED"}


# --- EXEC-V 2026-10-08: several sessions per answer, the limit known to the model, clear refusals -----------------

def limited_registry(fake: FakeSandbox, limit: int | None):
    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    return build_default_registry(sandbox_client=sandbox, governor_client=governor, dataneed_enabled=True,
                                  session_timeout_seconds=200, session_limit=limit)


def test_the_model_reads_the_answers_session_limit_in_words_and_the_close_argument_only_with_it() -> None:
    described = {d["name"]: d for d in limited_registry(FakeSandbox(), 4).definitions()}["open_analysis_session"]
    assert "up to four sessions open at once" in described["description"]
    assert "opening one never closes another" in described["description"]
    assert "SESSION_LIMIT_PER_REQUEST" in described["description"]
    assert "close_session_id" in described["parameters"]["properties"]
    plain = {d["name"]: d for d in limited_registry(FakeSandbox(), None).definitions()}["open_analysis_session"]
    assert "close_session_id" not in plain["parameters"]["properties"] and "four" not in plain["description"]


def test_the_refusal_beyond_the_limit_reaches_the_model_with_the_open_sessions() -> None:
    listed = [{"session_id": SESSION, "bundle_id": BUNDLE, "need_id": "need_1", "status": "ACTIVE", "executions": 3,
               "completed": True}]
    fake = FakeSandbox({"/v1/sessions": (409, {
        "status": "REJECTED", "next_action": "USE_OPEN_SESSION",
        "error": {"code": "SESSION_LIMIT_PER_REQUEST", "message": "This answer already has 4 of its 4 analysis "
                  "sessions open, and opening a session never closes another.", "open_sessions": listed,
                  "max_sessions_per_request": 4}})})
    result = call(limited_registry(fake, 4), "open_analysis_session", {"input_bundle_id": BUNDLE}).output["result"]
    assert result["code"] == "SESSION_LIMIT_PER_REQUEST" and result["next_action"] == "USE_OPEN_SESSION"
    assert result["open_sessions"] == listed and result["max_sessions_per_request"] == 4
    assert "never closes another" in result["message"]


def test_close_session_id_closes_the_models_choice_then_opens() -> None:
    other = "sess_" + "e" * 24
    fake = FakeSandbox({
        f"/v1/sessions/{SESSION}/close": (200, {"session_id": SESSION, "status": "CLOSED",
                                               "close_reason": "CLOSED_BY_CALLER"}),
        "/v1/sessions": (200, {"session_id": other, "status": "ACTIVE", "bundle_id": BUNDLE})})
    result = call(limited_registry(fake, 4), "open_analysis_session",
                  {"input_bundle_id": BUNDLE, "close_session_id": SESSION}).output["result"]
    assert [c["path"] for c in fake.calls] == [f"/v1/sessions/{SESSION}/close", "/v1/sessions"]
    assert result["session_id"] == other and result["closed_session"]["close_reason"] == "CLOSED_BY_CALLER"
    refused = FakeSandbox({f"/v1/sessions/{SESSION}/close": (404, {
        "status": "REJECTED", "error": {"code": "SESSION_NOT_FOUND", "message": "No session with this id."}})})
    result = call(limited_registry(refused, 4), "open_analysis_session",
                  {"input_bundle_id": BUNDLE, "close_session_id": SESSION}).output["result"]
    assert result["code"] == "SESSION_NOT_FOUND" and [c["path"] for c in refused.calls] == [
        f"/v1/sessions/{SESSION}/close"]  # nothing opened when the close was refused


def test_a_capacity_refusal_with_the_answers_own_sessions_points_at_them() -> None:
    listed = [{"session_id": SESSION, "bundle_id": BUNDLE, "need_id": "need_1", "status": "ACTIVE", "executions": 1,
               "completed": False}]
    fake = FakeSandbox({"/v1/sessions": (429, {
        "status": "REJECTED", "next_action": "USE_OPEN_SESSION",
        "error": {"code": "SESSION_CAPACITY_EXCEEDED", "message": "busy", "open_sessions": listed,
                  "retry_after_seconds": 15}})})
    result = call(limited_registry(fake, 4), "open_analysis_session", {"input_bundle_id": BUNDLE}).output["result"]
    assert result["next_action"] == "USE_OPEN_SESSION" and result["open_sessions"] == listed
    assert "own sessions stay open" in result["message"] and not any(ch.isdigit() for ch in result["message"])
