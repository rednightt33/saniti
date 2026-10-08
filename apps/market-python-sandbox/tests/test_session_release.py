"""S28 (golden test ma-golden-20261002c, round 2026-10-03 C1): a request's sessions are released when its answer ends
(WARM_IDLE when completed, else closed), and opening a session waits for a slot in arrival order before
SESSION_CAPACITY_EXCEEDED. EXEC-V 2026-10-08 ("membuka 1 tidak menutup yang lain"): a request holds up to
max_sessions_per_request open sessions, opening one never closes another, the open beyond the limit is refused with
the open sessions listed, activity in one keeps all of them alive, and code run after a passed completion in the same
answer stays in its epoch (M114)."""
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


def test_opening_another_session_closes_none_and_the_one_beyond_the_limit_is_refused_with_the_list(reuse) -> None:
    sessions = reuse["dataneed"].sessions
    assert sessions.settings.max_sessions_per_request == sessions.settings.max_sessions == 2
    one = first_turn(reuse)  # turn 1 ended: WARM_IDLE, an earlier answer's
    bundle = bundle_for(reuse, "req_turn_2")
    first = open_in(reuse, "req_turn_2", bundle).json()["session_id"]
    assert execute(reuse, first, "req_turn_2", YTD)["status"] == "OK"
    assert complete(reuse, first, "req_turn_2")["session_status"] == "ACTIVE"  # open until the answer ends
    second = open_in(reuse, "req_turn_2", bundle)
    assert second.status_code == 200, second.text  # the WARM_IDLE session of turn 1 gave its slot
    assert status(reuse, one["session_id"]) == ("CLOSED", "EVICTED")
    assert status(reuse, first)[0] == "ACTIVE"  # completed, still open: opening another closed nothing
    third = open_in(reuse, "req_turn_2", bundle)
    assert third.status_code == 409, third.text
    body = third.json()
    assert body["error"]["code"] == "SESSION_LIMIT_PER_REQUEST" and body["next_action"] == "USE_OPEN_SESSION"
    assert body["error"]["max_sessions_per_request"] == 2
    listed = {s["session_id"]: s for s in body["error"]["open_sessions"]}
    assert set(listed) == {first, second.json()["session_id"]}
    assert listed[first]["completed"] is True and listed[second.json()["session_id"]]["completed"] is False
    assert "never closes another" in body["error"]["message"]
    assert status(reuse, first)[0] == "ACTIVE" and status(reuse, second.json()["session_id"])[0] == "ACTIVE"
    # the caller closes one it no longer needs, then the open succeeds
    post(reuse, f"/v1/sessions/{first}/close", {"request_id": "req_turn_2"})
    assert open_in(reuse, "req_turn_2", bundle).status_code == 200


def test_with_no_slot_a_session_of_the_same_request_is_never_replaced(reuse) -> None:
    """g7 (2026-10-02) closed the request's own session; EXEC-V 2026-10-08 keeps it and refuses the open clearly."""
    one_slot(reuse)
    reuse["dataneed"].sessions.settings.__dict__["max_sessions_per_request"] = 1
    bundle = bundle_for(reuse, "req_turn_1")
    first = open_in(reuse, "req_turn_1", bundle).json()["session_id"]
    second = open_in(reuse, "req_turn_1", bundle)
    assert second.status_code == 409 and second.json()["error"]["code"] == "SESSION_LIMIT_PER_REQUEST"
    assert status(reuse, first) == ("ACTIVE", None)


def test_capacity_refusal_names_the_answers_own_open_sessions(reuse) -> None:
    one_slot(reuse, wait=0)
    reuse["dataneed"].sessions.settings.__dict__["max_sessions_per_request"] = 1
    held = open_in(reuse, "req_turn_1", bundle_for(reuse, "req_turn_1")).json()["session_id"]
    other = bundle_for(reuse, "req_other", key=OTHER)
    refused = open_in(reuse, "req_other", other, key=OTHER)
    assert refused.status_code == 429 and refused.json()["error"]["open_sessions"] == []
    assert refused.json()["next_action"] == "RETRY_LATER"
    assert status(reuse, held)[0] == "ACTIVE"


def test_activity_in_one_session_keeps_every_session_of_the_answer_alive(reuse) -> None:
    bundle = bundle_for(reuse, "req_turn_1")
    first = open_in(reuse, "req_turn_1", bundle).json()["session_id"]
    second = open_in(reuse, "req_turn_1", bundle).json()["session_id"]
    store, idle = reuse["dataneed"].store, reuse["service"].settings.session_idle_seconds
    old = (datetime.now(timezone.utc) - timedelta(seconds=idle - 2)).isoformat()
    store.update_session(first, last_active_at=old)
    store.update_session(second, last_active_at=old)
    assert execute(reuse, second, "req_turn_1", "x = 1")["status"] == "OK"
    later = datetime.now(timezone.utc) + timedelta(seconds=10)
    reuse["dataneed"].sessions.sweep(now=later)
    assert status(reuse, first)[0] == "ACTIVE"  # untouched itself, kept alive by the answer's activity


def test_code_after_a_passed_completion_stays_in_its_epoch_and_completing_again_releases_it(reuse) -> None:
    """M114 (golden test ma-qa-variant-20261007a): an execution after complete_analysis passed opened epoch 2 in the
    same answer, so the completed findings were MISSING from every later completion."""
    bundle = bundle_for(reuse, "req_turn_1")
    session_id = open_in(reuse, "req_turn_1", bundle).json()["session_id"]
    assert execute(reuse, session_id, "req_turn_1", YTD)["status"] == "OK"
    first = complete(reuse, session_id, "req_turn_1")
    assert first["status"] == "COMPLETED" and first["epoch"] == 1
    assert complete(reuse, session_id, "req_turn_1")["replayed"] is True  # nothing new: replayed
    more = execute(reuse, session_id, "req_turn_1",
                   "emit_json('count', {'n': int(len(last))}, definition={})")
    assert more["status"] == "OK"
    record = reuse["dataneed"].store.get_session(session_id)
    assert record["epoch"] == 1 and record["status"] == "ACTIVE"
    again = complete(reuse, session_id, "req_turn_1")
    assert again["status"] == "COMPLETED" and again["epoch"] == 1 and not again.get("replayed")
    assert again["previous_completion_id"] == first["completion_id"]
    assert {o["name"] for o in again["released_outputs"]} == {"last_close", "count"}
    # a session put back to WARM_IDLE by the caller in the same request also stays in its epoch
    reuse["dataneed"].store.update_session(session_id, status="WARM_IDLE")
    assert execute(reuse, session_id, "req_turn_1", "y = 2")["status"] == "OK"
    assert reuse["dataneed"].store.get_session(session_id)["epoch"] == 1


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
    assert runtime["session_release"] == {"enabled": True, "version": 2, "open_wait_seconds": 0, "max_sessions": 2,
                                          "max_sessions_per_request": 2}
