"""S16 (suite20b r09, 2026-09-29; user decision 2026-09-30): a group's session that ends during the run.

A crash (WORKER_CRASHED, SESSION_STATE_CORRUPTED, PROTOCOL_ERROR) reopens a new session at the next run_research_code
within AI_RESEARCH_MAX_SESSION_RESTARTS; a session limit or any other reason closes the group; a finalize that cannot
complete the open group closes it, so the run always reaches a terminal state."""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.config import ConfigError
from app.research_run_executor import ResearchRunExecutor
from app.tools.request_data import current_request_id
from conftest import make_settings
from test_multi_angle import RunSandbox, executor, two_groups


class EndingSandbox(RunSandbox):
    """Ends the session of the next executions with the given close reasons."""

    def __init__(self, reasons: list[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.reasons = list(reasons)
        self.coverage = "PASS"

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/execute") and self.reasons:
            self.calls.append((request.method, path, None))
            reason = self.reasons.pop(0)
            return httpx.Response(409, json={"error": {"code": "SESSION_ENDED", "message": f"ended ({reason})",
                                                       "close_reason": reason, "execution_id": "exe_x"}})
        if path.endswith("/complete") and self.coverage != "PASS":
            self.calls.append((request.method, path, None))
            return httpx.Response(200, json={"status": "INCOMPLETE", "completion_id": "cmp_1",
                                             "final_status": {"data_coverage": "FAIL", "sandbox_execution": "SUCCESS",
                                                              "research_group": {"missing": ["a_fall"]}},
                                             "released_outputs": [], "message": "Not processed: universe_2"})
        return super().handler(request)


def closes(sandbox: RunSandbox) -> list[tuple[str, str]]:
    return [(path.split("/")[-2], body["reason"]) for method, path, body in sandbox.calls if path.endswith("/close")]


def with_run(sandbox: RunSandbox, restarts: int = 1) -> ResearchRunExecutor:
    run = executor(sandbox, dp=two_groups())
    run.max_session_restarts = restarts
    return run


def test_a_crashed_session_reopens_once_then_the_group_closes() -> None:
    sandbox = EndingSandbox(["WORKER_CRASHED", "SESSION_STATE_CORRUPTED"])
    run = with_run(sandbox)
    token = current_request_id.set("run_002")
    try:
        run.start()
        first = run.run("g1", "x")
        recovery = first["session_recovery"]
        assert recovery["action"] == "REOPEN_ON_NEXT_RUN" and recovery["restarts_left"] == 0
        assert recovery["angles_to_record"] == ["a_fall", "a_rank"] and first["next_action"] == "RUN_RESEARCH_CODE"
        assert "Do not import or modify" in recovery["message"]
        assert run.groups["g1"]["status"] == "READY" and run.groups["g1"]["session_id"] is None
        second = run.run("g1", "x")  # a new session on the same bundle, which ends again
        assert sandbox.sessions == 2
        assert second["session_recovery"]["action"] == "GROUP_CLOSED"
        assert run.groups["g1"]["status"] == "FAILED"
        assert closes(sandbox) == [("g1", "SESSION_ENDED_SESSION_STATE_CORRUPTED")]
        # the closed group is terminal; the other group still runs
        assert run.run("g1", "x")["code"] == "BUNDLE_GROUP_TERMINAL"
        assert run.run("g2", "y")["status"] == "OK"
        done = run.complete(True)
        done = done if done["status"] == "COMPLETED" else run.complete(True)
    finally:
        current_request_id.reset(token)
    assert done["status"] == "COMPLETED"


@pytest.mark.parametrize("reason", ["CPU_BUDGET_EXCEEDED", "MEMORY_LIMIT_EXCEEDED", "DISK_LIMIT_EXCEEDED",
                                    "EXECUTION_TIMEOUT_UNINTERRUPTIBLE", "FORBIDDEN_OPERATION", "SESSION_IDLE"])
def test_a_session_limit_never_reopens_a_session(reason: str) -> None:
    sandbox = EndingSandbox([reason])
    run = with_run(sandbox)
    token = current_request_id.set("run_002")
    try:
        run.start()
        ended = run.run("g1", "x")
    finally:
        current_request_id.reset(token)
    assert ended["session_recovery"]["action"] == "GROUP_CLOSED" and sandbox.sessions == 1
    assert closes(sandbox) == [("g1", f"SESSION_ENDED_{reason}")]
    assert ended["next_action"] == "RUN_RESEARCH_CODE"  # g2 remains to run


def test_zero_restarts_closes_the_group_at_once() -> None:
    sandbox = EndingSandbox(["WORKER_CRASHED"])
    run = with_run(sandbox, restarts=0)
    token = current_request_id.set("run_002")
    try:
        run.start()
        ended = run.run("g1", "x")
    finally:
        current_request_id.reset(token)
    assert ended["session_recovery"]["action"] == "GROUP_CLOSED" and sandbox.sessions == 1


def test_a_finalize_that_cannot_complete_the_open_group_closes_it() -> None:
    sandbox = EndingSandbox([])
    sandbox.coverage = "FAIL"
    run = with_run(sandbox)
    token = current_request_id.set("run_002")
    try:
        run.start()
        assert run.run("g1", "x")["status"] == "OK"
        assert run.complete(False)["status"] == "INCOMPLETE"  # without finalize nothing is closed
        assert closes(sandbox) == []
        early = run.complete(True)  # M36: the first finalize names the missing angles
        assert early["code"] == "ANGLES_NOT_RECORDED"
        done = run.complete(True)
    finally:
        current_request_id.reset(token)
    assert ("g1", "COVERAGE_FAILED") in closes(sandbox) and ("g2", "NOT_RUN_BY_MODEL") in closes(sandbox)
    assert done["status"] == "COMPLETED" and run.open_group is None


def test_the_restart_setting_is_validated() -> None:
    assert make_settings().ai_research_max_session_restarts == 1
    assert make_settings(AI_RESEARCH_MAX_SESSION_RESTARTS="0").ai_research_max_session_restarts == 0
    for bad in ("4", "-1"):
        with pytest.raises(ConfigError):
            make_settings(AI_RESEARCH_MAX_SESSION_RESTARTS=bad)

