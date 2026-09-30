"""S16 (suite20b r09, 2026-09-29): code that changes the session worker's own state.

A session worker died after the model's code changed the sandbox's internals, and the harness labelled it
WORKER_UNRESPONSIVE. Each case below was first reproduced against the unhardened worker; the worker now answers a
broken bookkeeping as SESSION_STATE_CORRUPTED, keeps its protocol on private pipes, and the harness waits for the
exit before it labels a crash."""
from __future__ import annotations

import hashlib
import logging

import pytest

from conftest import requires_root
from test_audit_sandbox import audited, execute  # noqa: F401 - fixture
from test_dataneed_sessions import run, session  # noqa: F401 - fixture
from test_dataneed_bundles import env  # noqa: F401 - fixture

pytestmark = requires_root

TAMPERING = {
    "done_to_list": "import saniti_session\nsaniti_session._RESEARCH_DONE = []",
    "pending_to_none": "import saniti_session\nsaniti_session._RESEARCH_PENDING = None",
    "access_to_none": "import saniti_session\nsaniti_session._ACCESS = None",
    "settle_replaced": "import saniti_session\nsaniti_session._research_settle = None",
}


def ended(response) -> dict:
    assert response.status_code == 409, response.text
    return response.json()["error"]


@pytest.mark.parametrize("label", list(TAMPERING))
def test_code_that_breaks_the_bookkeeping_ends_the_session_with_a_clear_reason(session, label) -> None:  # noqa: F811
    error = ended(run(session, TAMPERING[label]))
    assert error["code"] == "SESSION_ENDED" and error["close_reason"] == "SESSION_STATE_CORRUPTED", error
    assert "Do not import or modify" in error["message"]
    execution = session["dataneed"].store.executions_for(session["session_id"])[-1]
    assert execution["status"] == "SESSION_ENDED" and execution["error"]["code"] == "SESSION_STATE_CORRUPTED"
    assert execution["error"]["error_type"] == "SessionStateCorrupted" and execution["error"]["cause"]
    assert ended(run(session, "print(1)"))["close_reason"] == "SESSION_STATE_CORRUPTED"


def test_harmless_changes_to_the_recorded_angles_leave_the_session_alive(session) -> None:  # noqa: F811
    for code in ("import saniti_session\nsaniti_session._RESEARCH_DONE.discard('x')",
                 "import saniti_session\nsaniti_session._RESEARCH_DONE = set()"):
        assert run(session, code).json()["status"] == "OK"
    assert run(session, "print(1)").json()["stdout"].strip() == "1"


def test_closing_stdin_or_the_named_fd_no_longer_ends_the_session(session) -> None:  # noqa: F811
    body = run(session, "import sys\nsys.stdin.close()\nprint(sys.argv)").json()
    assert body["status"] == "OK" and body["stdout"].strip().endswith("']"), body  # argv names no fd any more
    assert "'" in body["stdout"] and body["stdout"].count(",") == 0
    assert run(session, "import os\nos.close(0)").json()["status"] == "OK"
    assert run(session, "x = 41\nprint(x + 1)").json()["stdout"].strip() == "42"


def test_writing_to_the_protocol_pipe_is_a_protocol_error(session) -> None:  # noqa: F811
    code = ("import os\n"
            "for fd in sorted(int(n) for n in os.listdir('/proc/self/fd'))[3:]:\n"
            "    try:\n"
            "        os.write(fd, b'not json\\n')\n"
            "    except OSError:\n"
            "        pass\n")
    error = ended(run(session, code))
    assert error["close_reason"] in ("PROTOCOL_ERROR", "WORKER_CRASHED"), error


def test_a_crash_is_labelled_after_the_process_exits(session, caplog) -> None:  # noqa: F811
    caplog.set_level(logging.INFO, logger="market_python_sandbox")
    code = "import sys\nprint('boom', file=sys.__stderr__, flush=True)\nimport os\nos._exit(7)"
    error = ended(run(session, code))
    assert error["close_reason"] == "WORKER_CRASHED", error
    ended_logs = [r.getMessage() for r in caplog.records if '"session_worker_ended"' in r.getMessage()]
    assert ended_logs and '"exit_code":7' in ended_logs[-1] and "boom" in ended_logs[-1]


def test_a_script_error_and_sys_exit_still_keep_the_session(session) -> None:  # noqa: F811
    assert run(session, "import sys\nsys.exit(1)").json()["status"] == "SCRIPT_ERROR"
    assert run(session, "print(2)").json()["stdout"].strip() == "2"


def test_the_code_that_ended_a_session_is_archived_byte_for_byte(audited) -> None:  # noqa: F811
    code = "import saniti_session\nsaniti_session._ACCESS = None\n"
    body = execute(audited, code)
    assert body["error"]["close_reason"] == "SESSION_STATE_CORRUPTED", body
    outbox, fake = audited["dataneed"].audit, audited["fake"]
    outbox.drain()
    [record] = fake.posted("/v1/internal/executions")
    assert record["status"] == "SESSION_ENDED"
    assert record["source_sha256"] == hashlib.sha256(code.encode()).hexdigest()
    assert code.encode() in fake.uploads.values()
