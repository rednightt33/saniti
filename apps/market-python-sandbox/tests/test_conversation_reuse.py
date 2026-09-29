"""Conversation reuse (PY_SANDBOX_ENABLE_CONVERSATION_REUSE; implementation plan 2026-09-27, phases S1/S2): an
earlier bundle bound to a later request's own approved need with the same data contract, a WARM_IDLE session attached
with a new epoch and per-epoch completion, inherited coverage, released outputs read across requests of one
conversation, eviction, detach, and the versioned SQLite upgrade."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.dataneed_store import SCHEMA, SCHEMA_VERSION, DataNeedStore
from app.main import create_app
from conftest import requires_root
from dataneed_fixtures import data_need_catalog, ytd_spec
from test_dataneed_bundles import HEADERS, REFERENCE, build, ytd_parts

pytestmark = requires_root
KEY = "ck_" + "a" * 32
OTHER = "ck_" + "b" * 32
YTD = """
prices = load('prices')
banks = load('stock_classification')
last = prices.groupby('ticker', as_index=False)['close'].last()
emit_table('last_close', last)
"""


def headers(key: str | None = KEY) -> dict[str, str]:
    return {**HEADERS, **({"X-Saniti-Conversation-Key": key} if key else {})}


@pytest.fixture
def reuse(make_service, governor):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true",
                           PY_SANDBOX_ENABLE_CONVERSATION_REUSE="true", PY_SANDBOX_SESSION_EXECUTION_SECONDS="5")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    yield env
    env["dataneed"].sessions.stop()


def approve(env, request_id: str, key: str | None = KEY, spec=None) -> dict:
    body = {"request_id": request_id, "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
            "spec": spec or ytd_spec()}
    result = env["api"].post("/v1/data-needs", json=body, headers=headers(key)).json()
    assert result["status"] == "APPROVED", result
    return env["dataneed"].get_need(result["need_id"])


def post(env, path: str, body: dict, key: str | None = KEY):
    return env["api"].post(path, json=body, headers=headers(key))


def execute(env, session_id: str, request_id: str, code: str) -> dict:
    return post(env, f"/v1/sessions/{session_id}/execute", {"request_id": request_id, "code": code}).json()


def complete(env, session_id: str, request_id: str) -> dict:
    return post(env, f"/v1/sessions/{session_id}/complete", {"request_id": request_id}).json()


def first_turn(env) -> dict:
    """Turn 1 of a conversation: approve, extract, open, compute, complete. The session stays WARM_IDLE."""
    need = approve(env, "req_turn_1")
    bundle = build(env, need, ytd_parts(env, need), request_id="req_turn_1").json()
    assert bundle["status"] == "READY", bundle
    opened = post(env, "/v1/sessions", {"request_id": "req_turn_1", "bundle_id": bundle["input_bundle_id"]}).json()
    table = execute(env, opened["session_id"], "req_turn_1", YTD)["outputs"][0]
    done = complete(env, opened["session_id"], "req_turn_1")
    assert done["status"] == "COMPLETED" and done["session_status"] == "WARM_IDLE", done
    return {"need": need, "bundle_id": bundle["input_bundle_id"], "session_id": opened["session_id"],
            "output_id": table["output_id"], "completion_id": done["completion_id"]}


def attach(env, request_id: str) -> tuple[dict, dict]:
    need = approve(env, request_id)
    reused = post(env, "/v1/bundles/reuse", {"request_id": request_id, "need_id": need["need_id"]}).json()
    assert reused["status"] == "READY" and reused["reused"] is True, reused
    opened = post(env, "/v1/sessions", {"request_id": request_id, "bundle_id": reused["input_bundle_id"]}).json()
    return reused, opened


def test_a_follow_up_reuses_the_bundle_and_the_warm_session_with_a_new_epoch(reuse) -> None:
    one = first_turn(reuse)
    extracted = len(reuse["governor"].datasets)
    reused, opened = attach(reuse, "req_turn_2")
    assert reused["input_bundle_id"] == one["bundle_id"] and reused["reused_from"]["request_id"] == "req_turn_1"
    assert len(reuse["governor"].datasets) == extracted  # no new extraction
    assert opened["session_id"] == one["session_id"] and opened["reused_session"] is True and opened["epoch"] == 2
    assert {v["name"] for v in opened["variables"]} >= {"prices", "banks", "last"}
    assert opened["parent_completion_id"] == one["completion_id"]
    assert opened["session_budget"]["executions_used"] == 1  # counters are cumulative, never reset
    # the earlier request lost the session: only the current binding may run code in it
    stale = post(reuse, f"/v1/sessions/{one['session_id']}/execute", {"request_id": "req_turn_1", "code": "x = 1"})
    assert stale.status_code == 404 and stale.json()["error"]["code"] == "SESSION_NOT_FOUND"
    # filter the earlier DataFrame without reading the data again
    body = execute(reuse, one["session_id"], "req_turn_2",
                   "high = last[last['close'] >= last['close'].median()]\nemit_table('high_close', high)")
    assert body["status"] == "OK" and body["session"]["executions_used"] == 2
    done = complete(reuse, one["session_id"], "req_turn_2")
    assert done["status"] == "COMPLETED" and done["epoch"] == 2 and done["need_id"] != one["need"]["need_id"]
    assert [o["name"] for o in done["released_outputs"]] == ["high_close"]
    assert {r["processing"] for r in done["coverage"]["requests"]} == {"INHERITED"}
    inherited = done["final_status"]["inherited_coverage"]
    assert inherited["parent_completion_id"] == one["completion_id"] and inherited["parent_request_id"] == "req_turn_1"
    # the earlier completion is untouched, and each epoch keeps its own completion
    store = reuse["dataneed"].store
    assert [c["epoch"] for c in store.passed_completions(one["session_id"])] == [1, 2]
    assert [(e["epoch"], e["request_id"]) for e in store.epochs_for(one["session_id"])] == [
        (1, "req_turn_1"), (2, "req_turn_2")]
    assert complete(reuse, one["session_id"], "req_turn_2")["replayed"] is True


def test_an_earlier_pass_never_completes_a_later_epoch(reuse) -> None:
    one = first_turn(reuse)
    _, opened = attach(reuse, "req_turn_2")
    nothing = complete(reuse, opened["session_id"], "req_turn_2")
    assert nothing["status"] == "INCOMPLETE" and nothing["final_status"]["sandbox_execution"] == "NO_EXECUTION"
    failed = execute(reuse, one["session_id"], "req_turn_2", "missing_name + 1")
    assert failed["status"] == "SCRIPT_ERROR"
    after = complete(reuse, one["session_id"], "req_turn_2")
    assert after["status"] == "INCOMPLETE" and after["released_outputs"] == []
    assert not after.get("replayed")


def test_released_outputs_are_read_across_requests_of_the_conversation_only(reuse) -> None:
    one = first_turn(reuse)
    path = f"/v1/sessions/{one['session_id']}/outputs/{one['output_id']}"
    params = {"request_id": "req_turn_3"}
    page = reuse["api"].get(path, params=params, headers=headers()).json()
    assert page["released"] is True and page["read_mode"] == "READ_RELEASED" and len(page["rows"]) == 3
    assert page["origin"]["completion_id"] == one["completion_id"]
    assert page["origin"]["evidence_label"] == "DATA_COVERAGE_VERIFIED"  # never raised
    assert reuse["api"].get(path, params=params, headers=headers(None)).status_code == 404
    assert reuse["api"].get(path, params=params, headers=headers(OTHER)).status_code == 404
    # an output of a later epoch is not readable by another request until that epoch completes
    attach(reuse, "req_turn_2")
    draft = execute(reuse, one["session_id"], "req_turn_2", "emit_json('draft', {'n': 1})")["outputs"][0]
    hidden = reuse["api"].get(f"/v1/sessions/{one['session_id']}/outputs/{draft['output_id']}",
                              params={"request_id": "req_turn_3"}, headers=headers())
    assert hidden.status_code == 404


def test_a_different_data_contract_is_not_reused(reuse) -> None:
    first_turn(reuse)
    spec = ytd_spec()
    spec["data_requests"][0]["columns"] = [c for c in spec["data_requests"][0]["columns"] if c != "volume"]
    need = approve(reuse, "req_turn_2", spec=spec)
    result = post(reuse, "/v1/bundles/reuse", {"request_id": "req_turn_2", "need_id": need["need_id"]}).json()
    assert result == {"status": "NO_MATCH", "reason": "NO_EQUAL_CONTRACT"}
    other = approve(reuse, "req_other", key=OTHER)
    elsewhere = post(reuse, "/v1/bundles/reuse", {"request_id": "req_other", "need_id": other["need_id"]},
                     key=OTHER).json()
    assert elsewhere["status"] == "NO_MATCH"  # another conversation never sees this one's bundles


def test_close_without_running_detaches_and_eviction_frees_a_slot(reuse) -> None:
    one = first_turn(reuse)
    _, opened = attach(reuse, "req_turn_2")
    detached = post(reuse, f"/v1/sessions/{opened['session_id']}/close", {"request_id": "req_turn_2"}).json()
    assert detached["status"] == "WARM_IDLE" and detached["close_reason"] == "DETACHED_UNCHANGED"
    _, again = attach(reuse, "req_turn_3")
    assert again["session_id"] == one["session_id"] and again["epoch"] == 3
    execute(reuse, one["session_id"], "req_turn_3", "print(len(last))")
    closed = post(reuse, f"/v1/sessions/{one['session_id']}/close", {"request_id": "req_turn_3"}).json()
    assert closed["status"] == "CLOSED"  # it ran code in this epoch: closed, not detached


def test_resources_list_the_bundle_spec_the_warm_session_and_released_outputs(reuse) -> None:
    one = first_turn(reuse)
    listed = reuse["api"].get(f"/v1/conversations/{KEY}/resources", headers=HEADERS).json()
    [bundle] = listed["bundles"]
    assert bundle["bundle_id"] == one["bundle_id"] and bundle["warm_session"]["session_id"] == one["session_id"]
    assert bundle["data_need_spec"]["data_requests"][0]["logical_name"] == "prices"
    [output] = listed["released_outputs"]
    assert output["output_id"] == one["output_id"] and output["completion_id"] == one["completion_id"]
    assert reuse["api"].get(f"/v1/conversations/{OTHER}/resources", headers=HEADERS).json()["bundles"] == []


def test_an_interrupted_execution_keeps_the_session_out_of_reuse(reuse) -> None:
    need = approve(reuse, "req_turn_1")
    bundle = build(reuse, need, ytd_parts(reuse, need), request_id="req_turn_1").json()
    opened = post(reuse, "/v1/sessions", {"request_id": "req_turn_1", "bundle_id": bundle["input_bundle_id"]}).json()
    assert execute(reuse, opened["session_id"], "req_turn_1", "import time\ntime.sleep(20)")["status"] == "TIMEOUT"
    execute(reuse, opened["session_id"], "req_turn_1", YTD)
    done = complete(reuse, opened["session_id"], "req_turn_1")
    assert done["status"] == "COMPLETED" and done["session_status"] == "CLOSED"


def test_without_the_flag_the_header_is_ignored(make_service, governor) -> None:
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    try:
        need = approve(env, "req_turn_1")
        assert env["dataneed"].store.get_need(need["need_id"])["conversation_key"] is None
        bundle = build(env, need, ytd_parts(env, need), request_id="req_turn_1").json()
        opened = post(env, "/v1/sessions", {"request_id": "req_turn_1", "bundle_id": bundle["input_bundle_id"]}).json()
        execute(env, opened["session_id"], "req_turn_1", YTD)
        done = complete(env, opened["session_id"], "req_turn_1")
        assert done["status"] == "COMPLETED" and "session_status" not in done and "epoch" not in done
        state = client.get(f"/v1/sessions/{opened['session_id']}", params={"request_id": "req_turn_1"},
                           headers=HEADERS).json()
        assert state["status"] == "CLOSED" and state["close_reason"] == "COMPLETED"
        refused = post(env, "/v1/bundles/reuse", {"request_id": "req_turn_1", "need_id": need["need_id"]})
        assert refused.status_code == 404 and refused.json()["error"]["code"] == "REUSE_UNAVAILABLE"
        assert client.get("/v1/runtime", headers=HEADERS).json()["conversation_reuse"]["enabled"] is False
    finally:
        env["dataneed"].sessions.stop()


def test_the_sqlite_upgrade_keeps_legacy_rows(tmp_path) -> None:
    path = tmp_path / "dataneed.sqlite3"
    legacy = sqlite3.connect(path)
    legacy.executescript(SCHEMA)
    legacy.execute("INSERT INTO sessions (session_id, request_id, bundle_id, status, created_at, last_active_at, "
                   "expires_at) VALUES ('sess_old', 'req_old', 'bundle_old', 'CLOSED', 't', 't', 't')")
    legacy.execute("INSERT INTO completions (completion_id, session_id, request_id, bundle_id, need_id, "
                   "coverage_status, execution_manifest, coverage, final_status, created_at) VALUES "
                   "('cmp_old', 'sess_old', 'req_old', 'bundle_old', 'need_old', 'PASS', '{}', '{}', '{}', 't')")
    legacy.commit()
    legacy.close()
    store = DataNeedStore(path)
    assert store.schema_version == SCHEMA_VERSION == 4
    assert store.get_draft("draft_none") is None  # version 2 adds the feasibility drafts
    assert store.research_runs_for("req_old") == []  # version 4 adds the multi-angle research tables
    session = store.get_session("sess_old")
    assert (session["epoch"], session["epoch_start_seq"], session["conversation_key"]) == (1, 0, None)
    assert store.completion_for_epoch("sess_old", 1)["completion_id"] == "cmp_old"
    store.close()
    assert DataNeedStore(path).schema_version == SCHEMA_VERSION  # idempotent on reopen


def test_coverage_is_inherited_from_every_earlier_passed_epoch(reuse) -> None:
    # S07 (the 2026-09-27 PoC): epoch 2 only reused variables, so it read nothing itself; epoch 3 must still inherit
    # the data epoch 1 read in full in the same namespace
    one = first_turn(reuse)
    attach(reuse, "req_turn_2")
    execute(reuse, one["session_id"], "req_turn_2", "emit_json('count', {'n': int(len(last))})")
    assert complete(reuse, one["session_id"], "req_turn_2")["status"] == "COMPLETED"
    attach(reuse, "req_turn_3")
    execute(reuse, one["session_id"], "req_turn_3", "emit_json('top', {'close': float(last['close'].max())})")
    done = complete(reuse, one["session_id"], "req_turn_3")
    assert done["status"] == "COMPLETED", done
    assert {r["processing"] for r in done["coverage"]["requests"]} == {"INHERITED"}
    assert done["final_status"]["inherited_coverage"]["ancestor_completion_ids"][0] == one["completion_id"]
