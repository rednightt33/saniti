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
emit_table('last_close', last, definition={})
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
                   "high = last[last['close'] >= last['close'].median()]\nemit_table('high_close', high, definition={'filters': [{'column': 'close', 'operator': 'GTE', 'value': 'median'}]})")
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
    assert page["label"] == "DATA_COVERAGE_VERIFIED"  # P5
    assert reuse["api"].get(path, params=params, headers=headers(None)).status_code == 404
    assert reuse["api"].get(path, params=params, headers=headers(OTHER)).status_code == 404
    # an output of a later epoch is not readable by another request until that epoch completes
    attach(reuse, "req_turn_2")
    draft = execute(reuse, one["session_id"], "req_turn_2", "emit_json('draft', {'n': 1}, definition={})")["outputs"][0]
    hidden = reuse["api"].get(f"/v1/sessions/{one['session_id']}/outputs/{draft['output_id']}",
                              params={"request_id": "req_turn_3"}, headers=headers())
    assert hidden.status_code == 404
    own = reuse["api"].get(f"/v1/sessions/{one['session_id']}/outputs/{draft['output_id']}",
                           params={"request_id": "req_turn_2"}, headers=headers()).json()
    assert own["label"] == "NOT_RELEASED" and "may not be cited" in own["label_meaning"]  # P5


def test_a_contract_the_earlier_data_does_not_cover_is_not_reused(reuse) -> None:
    first_turn(reuse)
    spec = ytd_spec()
    spec["data_requests"][0]["time_ranges"][0]["start"] = "2026-02-02"  # a different window
    need = approve(reuse, "req_turn_2", spec=spec)
    result = post(reuse, "/v1/bundles/reuse", {"request_id": "req_turn_2", "need_id": need["need_id"]}).json()
    assert result == {"status": "NO_MATCH", "reason": "NO_COVERING_CONTRACT"}


def test_fewer_columns_or_another_mode_reuse_the_earlier_data(reuse) -> None:
    """2c (2026-10-02): the earlier bundle holds every column of a narrower need, in any mode."""
    one = first_turn(reuse)
    spec = ytd_spec()
    spec["data_requests"][0]["columns"] = [c for c in spec["data_requests"][0]["columns"] if c != "volume"]
    need = approve(reuse, "req_turn_2", spec=spec)
    reused = post(reuse, "/v1/bundles/reuse", {"request_id": "req_turn_2", "need_id": need["need_id"]}).json()
    assert reused["status"] == "READY" and reused["input_bundle_id"] == one["bundle_id"], reused
    from test_research_findings_session import GOVERNANCE

    governance = {k: v for k, v in GOVERNANCE.items() if k not in (
        "expected_direction", "outcome_horizon_periods", "outcome_unit", "success_definition")}
    governance["minimum_sample"] = {"value": 30, "unit": "EVENTS"}
    body = {"request_id": "req_turn_3", "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
            "spec": ytd_spec(mode="RESEARCH"), "research_governance": governance}
    research = post(reuse, "/v1/data-needs", body).json()
    assert research["status"] == "APPROVED" and research["need_id"], research
    result = post(reuse, "/v1/bundles/reuse", {"request_id": "req_turn_3", "need_id": research["need_id"]}).json()
    assert result["status"] == "READY" and result["input_bundle_id"] == one["bundle_id"], result
    # the research session starts a fresh worker: the analysis variables in the warm worker are not part of what the
    # research plan approved
    opened = post(reuse, "/v1/sessions", {"request_id": "req_turn_3", "bundle_id": one["bundle_id"]}).json()
    assert opened["session_id"] != one["session_id"] and not opened.get("reused_session"), opened
    assert reuse["dataneed"].store.get_session(one["session_id"])["status"] == "WARM_IDLE"
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
    execute(reuse, one["session_id"], "req_turn_2", "emit_json('count', {'n': int(len(last))}, definition={})")
    assert complete(reuse, one["session_id"], "req_turn_2")["status"] == "COMPLETED"
    attach(reuse, "req_turn_3")
    execute(reuse, one["session_id"], "req_turn_3", "emit_json('top', {'close': float(last['close'].max())}, definition={})")
    done = complete(reuse, one["session_id"], "req_turn_3")
    assert done["status"] == "COMPLETED", done
    assert {r["processing"] for r in done["coverage"]["requests"]} == {"INHERITED"}
    assert done["final_status"]["inherited_coverage"]["ancestor_completion_ids"][0] == one["completion_id"]


def test_a_recomputed_event_study_stays_labelled_in_later_turns_and_its_record_is_not_offered(reuse) -> None:
    """G2: the next message reads the event-study table as calculation_verified; the declaration record the backend
    recomputed from is released for the audit but never listed as a result."""
    need = approve(reuse, "req_turn_1")
    bundle = build(reuse, need, ytd_parts(reuse, need), request_id="req_turn_1").json()
    opened = post(reuse, "/v1/sessions", {"request_id": "req_turn_1", "bundle_id": bundle["input_bundle_id"]}).json()
    body = execute(reuse, opened["session_id"], "req_turn_1",
                   "event_study('prices', 'close / lag(close, 1) - 1 <= -0.01', {'forward_return': 'close'}, 3, "
                   "name='drops', min_events=1)\nbanks = load('stock_classification')\nemit_table('n', banks, definition={})")
    ids = {o["name"]: o["output_id"] for o in body["outputs"]}
    done = complete(reuse, opened["session_id"], "req_turn_1")
    assert done["status"] == "COMPLETED" and done["final_status"]["event_studies"][0]["status"] == "PASS", done
    listed = reuse["api"].get(f"/v1/conversations/{KEY}/resources", headers=HEADERS).json()
    offered = {o["name"]: o for o in listed["released_outputs"]}
    assert set(offered) == {"drops", "drops_events", "drops_baseline", "drops_flow", "n"}
    assert offered["drops"]["calculation_verified"] is True and "calculation_verified" not in offered["n"]
    page = reuse["api"].get(f"/v1/sessions/{opened['session_id']}/outputs/{ids['drops']}",
                            params={"request_id": "req_turn_2"}, headers=headers()).json()
    assert page["origin"]["calculation_verified"] is True
    assert page["origin"]["calculation_validation"] == "PARTIAL"


# ---------------------------------------------------------------- carried results and profiles (2026-10-02)

def second_bundle(env, request_id: str, mode: str = "ANALYSIS"):
    """A later message with a data need of its own (a different contract, so a new bundle and a new session)."""
    from dataneed_fixtures import ytd_spec

    spec = ytd_spec(mode=mode)
    spec["data_requests"][0]["columns"] = [c for c in spec["data_requests"][0]["columns"] if c != "volume"]
    body = {"request_id": request_id, "reference_time": REFERENCE, "timezone": "Asia/Jakarta", "spec": spec}
    if mode == "RESEARCH":
        from test_research_findings_session import GOVERNANCE

        body["research_governance"] = GOVERNANCE
    result = post(env, "/v1/data-needs", body).json()
    assert result["status"] == "APPROVED", result
    need = env["dataneed"].get_need(result["need_id"])
    bundle = build(env, need, ytd_parts(env, need), request_id=request_id).json()
    assert bundle["status"] == "READY", bundle
    return bundle["input_bundle_id"]


def test_a_released_table_is_carried_with_its_label_and_profile_into_a_later_session(reuse) -> None:
    one = first_turn(reuse)
    bundle = second_bundle(reuse, "req_turn_2")
    opened = post(reuse, "/v1/sessions", {"request_id": "req_turn_2", "bundle_id": bundle}).json()
    prices = next(d for d in opened["datasets"] if d["logical_name"] == "prices")
    assert prices["profile"]["rows"] == prices["rows"] and prices["profile"]["entities"] == 3  # P1
    assert prices["profile"]["columns"]["close"]["min"] is not None and len(prices["profile"]["sample"]) == 5
    [carried] = opened["carried_outputs"]  # P2, P5
    assert carried["output_id"] == one["output_id"] and carried["kind"] == "G1"
    assert carried["label"] == "DATA_COVERAGE_VERIFIED" and carried["origin"]["completion_id"] == one["completion_id"]
    body = execute(reuse, opened["session_id"], "req_turn_2", f"""
earlier = load_output({one['output_id']!r})
info = carried()[0]
print(len(earlier), earlier.attrs['label'], info['profile']['rows'])
load('prices'); load('stock_classification')
emit_table('built_on_earlier', earlier, definition={{}})""")
    assert body["status"] == "OK", body
    assert body["stdout"].split() == ["3", "DATA_COVERAGE_VERIFIED", "3"]
    done = complete(reuse, opened["session_id"], "req_turn_2")
    assert done["final_status"]["carried_inputs"] == [{"output_id": one["output_id"], "name": "last_close",
                                                       "kind": "G1", "label": "DATA_COVERAGE_VERIFIED",
                                                       "definition": {}}]
    # H1: the carried table brings its definition, and the new result states its own with its lineage
    released = {o["name"]: o for o in done["released_outputs"]}
    assert released["built_on_earlier"]["definition"] == {}
    assert released["built_on_earlier"]["lineage"]["execution_id"].startswith("exe_")
    assert released["built_on_earlier"]["lineage"]["code_sha256"]


def test_a_research_session_loads_only_the_tables_its_plan_names(make_service, governor) -> None:
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true", PY_SANDBOX_RESEARCH_FINDINGS_ENABLED="true",
                           PY_SANDBOX_ENABLE_CONVERSATION_REUSE="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    try:
        one = first_turn(env)
        bundle = second_bundle(env, "req_turn_2", mode="RESEARCH")
        closed = post(env, "/v1/sessions", {"request_id": "req_turn_2", "bundle_id": bundle}).json()
        assert "carried_outputs" not in closed  # the plan named none
        refused = execute(env, closed["session_id"], "req_turn_2", f"load_output({one['output_id']!r})")
        assert refused["status"] == "SCRIPT_ERROR" and "approved plan names" in str(refused)
        post(env, f"/v1/sessions/{closed['session_id']}/close", {"request_id": "req_turn_2"})
        named = post(env, "/v1/sessions", {"request_id": "req_turn_2", "bundle_id": bundle,
                                           "carried_outputs": [one["output_id"]]}).json()
        assert [c["output_id"] for c in named["carried_outputs"]] == [one["output_id"]]
        assert execute(env, named["session_id"], "req_turn_2",
                       f"print(len(load_output({one['output_id']!r})))")["stdout"].strip() == "3"
    finally:
        env["dataneed"].sessions.stop()
