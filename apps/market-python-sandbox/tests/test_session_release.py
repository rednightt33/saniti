"""S28 (golden test ma-golden-20261002c, round 2026-10-03 C1): a request's sessions are released when its answer ends
(WARM_IDLE when completed, else closed), a request keeps one active session, and opening a session waits for a slot
in arrival order before SESSION_CAPACITY_EXCEEDED."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from conftest import requires_root
from test_conversation_reuse import (KEY, OTHER, YTD, approve, complete, execute, first_turn, post,  # noqa: F401
                                     reuse)
from test_dataneed_bundles import HEADERS, build, ytd_parts

pytestmark = requires_root


def one_slot(env, wait: int = 0) -> None:
    sessions = env["dataneed"].sessions
    sessions.settings.__dict__["max_sessions"] = 1
    sessions.settings.__dict__["open_wait_seconds"] = wait
    sessions.slots = sessions.slots[:1]


def bundle_for(env, request_id: str, key: str = KEY) -> str:
    need = approve(env, request_id, key=key)
    built = build(env, need, ytd_parts(env, need), request_id=request_id).json()
    assert built["status"] == "READY", built
    return built["input_bundle_id"]


def open_in(env, request_id: str, bundle_id: str, key: str = KEY):
    return post(env, "/v1/sessions", {"request_id": request_id, "bundle_id": bundle_id}, key=key)


def status(env, session_id: str) -> tuple[str, str | None]:
    record = env["dataneed"].store.get_session(session_id)
    return record["status"], record.get("close_reason")


def release(env, request_id: str) -> dict:
    return env["api"].post(f"/v1/requests/{request_id}/release", headers=HEADERS).json()


def test_a_completed_session_that_ran_again_is_released_warm_and_can_be_evicted(reuse) -> None:
    """The g7 path: complete, then run code again (back to ACTIVE); the answer's end makes it WARM_IDLE, so another
    conversation's open evicts it instead of waiting 15 minutes."""
    one = first_turn(reuse)
    assert execute(reuse, one["session_id"], "req_turn_1", "print(1)")["status"] == "OK"
    assert status(reuse, one["session_id"])[0] == "ACTIVE"
    released = release(reuse, "req_turn_1")
    assert released["sessions"] == [{"session_id": one["session_id"], "status": "WARM_IDLE"}]
    one_slot(reuse)
    other = bundle_for(reuse, "req_other", key=OTHER)
    opened = open_in(reuse, "req_other", other, key=OTHER)
    assert opened.status_code == 200, opened.text
    assert status(reuse, one["session_id"]) == ("CLOSED", "EVICTED")


def test_an_uncompleted_session_is_closed_at_release_and_release_is_idempotent(reuse) -> None:
    bundle = bundle_for(reuse, "req_turn_1")
    session_id = open_in(reuse, "req_turn_1", bundle).json()["session_id"]
    assert release(reuse, "req_turn_1")["sessions"] == [{"session_id": session_id, "status": "CLOSED"}]
    assert status(reuse, session_id) == ("CLOSED", "RELEASED")
    assert release(reuse, "req_turn_1")["sessions"] == []


def test_a_request_keeps_one_active_session(reuse) -> None:
    """A second open in the same request moves a completed session to WARM_IDLE (reusable or evictable)."""
    one = first_turn(reuse)
    execute(reuse, one["session_id"], "req_turn_1", "print(1)")  # back to ACTIVE
    open_in(reuse, "req_turn_1", one["bundle_id"])
    assert status(reuse, one["session_id"])[0] == "WARM_IDLE"


def test_with_no_slot_an_uncompleted_session_of_the_same_request_is_replaced(reuse) -> None:
    """g7: the model opened a new session in the same answer instead of finishing the first one."""
    one_slot(reuse)
    bundle = bundle_for(reuse, "req_turn_1")
    first = open_in(reuse, "req_turn_1", bundle).json()["session_id"]
    second = open_in(reuse, "req_turn_1", bundle)
    assert second.status_code == 200, second.text
    assert status(reuse, first) == ("CLOSED", "REPLACED_IN_REQUEST")


def test_open_waits_for_a_slot_freed_by_another_request(reuse) -> None:
    one_slot(reuse, wait=20)
    held = bundle_for(reuse, "req_turn_1")
    holder = open_in(reuse, "req_turn_1", held).json()["session_id"]
    other = bundle_for(reuse, "req_other", key=OTHER)
    result: dict = {}

    def waiting_open() -> None:
        started = time.monotonic()
        result["response"] = open_in(reuse, "req_other", other, key=OTHER)
        result["seconds"] = time.monotonic() - started

    thread = threading.Thread(target=waiting_open)
    thread.start()
    time.sleep(1.5)
    assert "response" not in result  # still waiting: the slot is held by an ACTIVE session of another request
    release(reuse, "req_turn_1")
    thread.join(30)
    assert result["response"].status_code == 200, result["response"].text
    assert 1 <= result["seconds"] < 20
    assert status(reuse, holder) == ("CLOSED", "RELEASED")


def test_open_refuses_after_the_wait(reuse) -> None:
    one_slot(reuse, wait=1)
    open_in(reuse, "req_turn_1", bundle_for(reuse, "req_turn_1"))
    other = bundle_for(reuse, "req_other", key=OTHER)
    started = time.monotonic()
    refused = open_in(reuse, "req_other", other, key=OTHER)
    assert refused.status_code == 429 and time.monotonic() - started >= 1
    error = refused.json()["error"]
    assert error["code"] == "SESSION_CAPACITY_EXCEEDED" and error["waited_seconds"] >= 1
    assert refused.headers["Retry-After"]


def test_the_idle_sweep_stays_the_safety_net(reuse) -> None:
    bundle = bundle_for(reuse, "req_turn_1")
    session_id = open_in(reuse, "req_turn_1", bundle).json()["session_id"]
    later = datetime.now(timezone.utc) + timedelta(seconds=reuse["service"].settings.session_idle_seconds + 5)
    assert reuse["dataneed"].sessions.sweep(now=later)["sessions_closed"] >= 1
    assert status(reuse, session_id) == ("CLOSED", "SESSION_IDLE")


def test_the_runtime_reports_the_release_capability(reuse) -> None:
    runtime = reuse["api"].get("/v1/runtime", headers=HEADERS).json()
    assert runtime["session_release"] == {"enabled": True, "version": 1, "open_wait_seconds": 0}
