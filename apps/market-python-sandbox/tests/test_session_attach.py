"""PLAN 14 (user 2026-10-15, go "Ok jalankan"): a READY bundle of a later data need of the same answer joins its open
analysis session. The variables stay and the new request loads at once; a name already in the session, a third
attachment, a session of another request, a research session and a bundle over the combined size limit are refused
with the reason and OPEN_ANALYSIS_SESSION; an attached need never read is UNUSED and does not fail the completion,
while one read is checked like any other; a column no request holds gets a hint."""
from __future__ import annotations

import pandas as pd
import pytest

from conftest import requires_root
from dataneed_fixtures import classification
from test_dataneed_bundles import HEADERS, PLAN, approve, extract_part  # noqa: F401
from test_dataneed_bundles import env  # noqa: F401 - fixture
from test_dataneed_sessions import ok, run, session  # noqa: F401 - fixture

pytestmark = requires_root


def extra_spec(group: str, rid: str, logical: str, **overrides) -> dict:
    spec = {"spec_version": "data_need_spec/v1", "request_group_id": group, "revision": 1, "mode": "ANALYSIS",
            "question": "Daftar sektor saham bank.",
            "subject": {"data_domain": "MARKET", "entity_type": "STOCK", "asset_type": "IDX_EQUITY"},
            "data_requests": [classification(rid, logical_name=logical)], "relationships": []}
    spec.update(overrides)
    return spec


def extra_bundle(env, group: str, rid: str, logical: str, request_id: str = "req_bundle_1") -> str:
    need = approve(env, extra_spec(group, rid, logical), request_id=request_id)
    frame = pd.DataFrame([{"Ticker": t, "Sector": "Financials", "Industry": "Banks"} for t in ("BBCA", "BBRI")])
    parts = [{"data_request_id": rid, "envelopes": [],
              "parts": [extract_part(env, need, rid, frame, f"{rid}__static__part_001")]}]
    body = {"request_id": request_id, "need_id": need["need_id"],
            "plan": {"plan_id": PLAN, "requests": parts, "decisions": []}}
    built = env["api"].post("/v1/bundles", json=body, headers=HEADERS).json()
    assert built["status"] == "READY", built
    return built["input_bundle_id"]


def attach(env, bundle_id: str, request_id: str = "req_bundle_1"):
    return env["api"].post(f"/v1/sessions/{env['session_id']}/attach",
                           json={"request_id": request_id, "bundle_id": bundle_id}, headers=HEADERS)


def complete(env) -> dict:
    response = env["api"].post(f"/v1/sessions/{env['session_id']}/complete", json={"request_id": "req_bundle_1"},
                               headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


FULL_BASE = ("p = load('prices')\nc = load('stock_classification')\n"
             "emit_table('t', p.groupby('ticker', as_index=False)['close'].last(), definition={})")


def test_an_attached_bundle_joins_the_session_and_its_variables_stay(session) -> None:
    ok(session, "kept = 41")
    bundle = extra_bundle(session, "data_request_2", "data_request_2_A", "bank_sectors")
    response = attach(session, bundle)
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["attached"] is True and view["attachments"] == 1 and view["max_attachments"] == 2
    assert [d["logical_name"] for d in view["datasets"]] == ["bank_sectors"]
    body = ok(session, "s = load('bank_sectors')\nprint(kept + 1, len(s))")
    assert body["stdout"].strip() == "42 2"
    assert session["api"].get("/v1/runtime", headers=HEADERS).json()["session_attach"] == {
        "enabled": True, "version": 1, "max_attachments": 2}


def test_unused_attached_data_does_not_fail_the_completion(session) -> None:
    bundle = extra_bundle(session, "data_request_2", "data_request_2_A", "bank_sectors")
    assert attach(session, bundle).status_code == 200
    ok(session, FULL_BASE)
    unused = complete(session)
    assert unused["status"] == "COMPLETED", unused
    assert [a["status"] for a in unused["final_status"]["attachments"]] == ["UNUSED"]
    assert {r["data_request_id"] for r in unused["coverage"]["requests"]} == {"data_request_1_A", "data_request_1_B"}


def test_read_attached_data_is_checked_and_named_in_the_lineage(session) -> None:
    bundle = extra_bundle(session, "data_request_2", "data_request_2_A", "bank_sectors")
    assert attach(session, bundle).status_code == 200
    ok(session, FULL_BASE + "\ns = load('bank_sectors')\nemit_table('t2', s, definition={})")
    used = complete(session)
    assert used["status"] == "COMPLETED", used
    assert [a["status"] for a in used["final_status"]["attachments"]] == ["USED"]
    assert "data_request_2_A" in {r["data_request_id"] for r in used["coverage"]["requests"]}
    lineage = [o["lineage"] for o in used["released_outputs"]]
    assert all(entry.get("attached_need_ids") for entry in lineage)


def test_names_limits_and_ownership_are_refused_with_the_way_out(session) -> None:
    same = extra_bundle(session, "data_request_3", "data_request_3_A", "stock_classification")
    taken = attach(session, same)
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "ATTACH_NAME_TAKEN"
    for i, name in ((4, "s4"), (5, "s5")):
        assert attach(session, extra_bundle(session, f"data_request_{i}", f"data_request_{i}_A", name)).status_code \
            == 200
    third = attach(session, extra_bundle(session, "data_request_6", "data_request_6_A", "s6"))
    assert third.status_code == 409 and third.json()["error"]["code"] == "ATTACH_LIMIT"
    assert third.json()["next_action"] == "OPEN_ANALYSIS_SESSION"
    other = attach(session, extra_bundle(session, "data_request_7", "data_request_7_A", "s7", request_id="req_other"),
                   request_id="req_other")
    assert other.status_code == 404  # the session belongs to req_bundle_1


def test_the_combined_size_limit_is_checked(session) -> None:
    session["dataneed"].sessions.settings.__dict__["bundle_max_rows"] = 10  # the base bundle alone holds more
    bundle = extra_bundle(session, "data_request_2", "data_request_2_A", "bank_sectors")
    refused = attach(session, bundle)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "ATTACH_TOO_LARGE"
    assert "rows_left" in refused.json()["error"]


def test_a_missing_column_gets_a_hint(session) -> None:
    body = run(session, "p = load('prices')\np['foreign_net_value'].sum()").json()
    assert body["status"] == "SCRIPT_ERROR"
    assert "foreign_net_value" in body["missing_data_hint"]


@pytest.mark.parametrize("value", ["0"])
def test_attaching_switched_off_is_refused(session, value) -> None:
    session["dataneed"].sessions.settings.__dict__["max_attachments"] = int(value)
    bundle = extra_bundle(session, "data_request_2", "data_request_2_A", "bank_sectors")
    refused = attach(session, bundle)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "ATTACH_DISABLED"


def test_a_research_session_never_takes_an_attachment(session, monkeypatch) -> None:
    store = session["dataneed"].sessions.store
    base_need = store.get_session(session["session_id"])["need_id"]
    original = store.get_need
    monkeypatch.setattr(store, "get_need", lambda need_id: {**(original(need_id) or {}), "mode": "RESEARCH"}
                        if need_id == base_need else original(need_id))
    refused = attach(session, extra_bundle(session, "data_request_2", "data_request_2_A", "bank_sectors"))
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "ATTACH_RESEARCH_SESSION"
