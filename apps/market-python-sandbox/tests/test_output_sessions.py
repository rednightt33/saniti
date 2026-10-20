"""EXEC-OUTPUT-REUSE (PY_SANDBOX_OUTPUT_SESSIONS; user 2026-10-20: "menjawab pertanyaan tsb tidak perlu data request
sebenarnya ... tinggal olah data yang ada di sandbox", "hanya berlaku di same conversation ID"): a later message of the
same conversation runs code in the conversation's warm session, or opens a session on its released tables without a
bundle, without a data need of its own; another conversation's session, bundle or tables stay out of reach, and every
refusal says what is wrong and the one step that fixes it."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import requires_root
from dataneed_fixtures import data_need_catalog
from test_conversation_reuse import KEY, OTHER, complete, execute, first_turn, post

pytestmark = requires_root
FILTER = ("high = last[last['close'] >= last['close'].median()]\n"
          "emit_table('high_close', high, definition={'filters': [{'column': 'close', 'operator': 'GTE', "
          "'value': 'median'}]})")


@pytest.fixture
def outputs(make_service, governor):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true",
                           PY_SANDBOX_ENABLE_CONVERSATION_REUSE="true", PY_SANDBOX_OUTPUT_SESSIONS="true",
                           PY_SANDBOX_SESSION_EXECUTION_SECONDS="5")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    yield env
    env["dataneed"].sessions.stop()


def close_warm(env, one: dict) -> None:
    closed = post(env, f"/v1/sessions/{one['session_id']}/close", {"request_id": "req_turn_1"}).json()
    assert closed.get("status") == "CLOSED", closed


def test_a_follow_up_runs_code_in_the_warm_session_without_a_data_need(outputs) -> None:
    one = first_turn(outputs)
    extracted = len(outputs["governor"].datasets)
    body = execute(outputs, one["session_id"], "req_turn_2", FILTER)
    assert body["status"] == "OK", body
    done = complete(outputs, one["session_id"], "req_turn_2")
    assert done["status"] == "COMPLETED" and done["epoch"] == 2, done
    assert {r["processing"] for r in done["coverage"]["requests"]} == {"INHERITED"}
    assert done["final_status"]["conversation_reuse"]["kind"] == "OUTPUTS"
    assert [o["name"] for o in done["released_outputs"]] == ["high_close"]
    assert len(outputs["governor"].datasets) == extracted  # nothing read from the database again
    epochs = outputs["dataneed"].store.epochs_for(one["session_id"])
    assert [(e["epoch"], e["request_id"], e["kind"]) for e in epochs] == [(1, "req_turn_1", None),
                                                                          (2, "req_turn_2", "OUTPUTS")]


def test_another_conversation_never_reaches_the_session_and_is_told_what_to_do(outputs) -> None:
    one = first_turn(outputs)
    refused = post(outputs, f"/v1/sessions/{one['session_id']}/execute",
                   {"request_id": "req_other_1", "code": "x = 1"}, key=OTHER)
    assert refused.status_code == 404, refused.json()
    error = refused.json()["error"]
    assert error["code"] == "SESSION_NOT_FOUND"
    assert "another message or conversation" in error["message"] and "without a bundle" in error["message"]
    assert outputs["dataneed"].store.get_session(one["session_id"])["request_id"] == "req_turn_1"  # untouched


def test_a_session_without_a_bundle_takes_over_the_warm_session(outputs) -> None:
    one = first_turn(outputs)
    opened = post(outputs, "/v1/sessions", {"request_id": "req_turn_2"}).json()
    assert opened["session_id"] == one["session_id"] and opened["reused_session"] is True, opened
    assert opened["conversation_session"] is True and opened["epoch"] == 2


def test_with_the_warm_session_gone_a_session_on_the_released_tables_opens(outputs) -> None:
    one = first_turn(outputs)
    close_warm(outputs, one)
    extracted = len(outputs["governor"].datasets)
    opened = post(outputs, "/v1/sessions", {"request_id": "req_turn_2"}).json()
    assert opened["session_id"] != one["session_id"] and opened["outputs_only"] is True, opened
    assert opened["datasets"] == [] and one["output_id"] in opened["carried_output_ids"]
    code = (f"last = load_output('{one['output_id']}')\n" + FILTER)
    assert execute(outputs, opened["session_id"], "req_turn_2", code)["status"] == "OK"
    done = complete(outputs, opened["session_id"], "req_turn_2")
    assert done["status"] == "COMPLETED", done
    reuse = done["final_status"]["conversation_reuse"]
    assert reuse == {"kind": "OUTPUTS", "outputs_only": True, "released_tables_read": [one["output_id"]]}
    assert done["final_status"]["evidence_label"] == "DATA_COVERAGE_VERIFIED"
    assert done["final_status"]["carried_inputs"][0]["output_id"] == one["output_id"]
    assert len(outputs["governor"].datasets) == extracted


def test_a_session_without_a_bundle_that_reads_no_released_table_cannot_complete(outputs) -> None:
    one = first_turn(outputs)
    close_warm(outputs, one)
    opened = post(outputs, "/v1/sessions", {"request_id": "req_turn_2"}).json()
    code = "import pandas as pd\nemit_table('made_up', pd.DataFrame({'a': [1]}), definition={})"
    assert execute(outputs, opened["session_id"], "req_turn_2", code)["status"] == "OK"
    done = complete(outputs, opened["session_id"], "req_turn_2")
    assert done["status"] == "INCOMPLETE" and done["released_outputs"] == []
    assert "load_output" in done["message"] and "data need" in done["message"]


def test_another_conversation_sees_none_of_the_tables(outputs) -> None:
    one = first_turn(outputs)
    opened = post(outputs, "/v1/sessions", {"request_id": "req_other_1"}, key=OTHER).json()
    assert opened["outputs_only"] is True and one["output_id"] not in opened["carried_output_ids"]


def test_a_bundle_of_an_earlier_message_opens_a_session_on_its_data(outputs) -> None:
    one = first_turn(outputs)
    close_warm(outputs, one)
    opened = post(outputs, "/v1/sessions", {"request_id": "req_turn_2", "bundle_id": one["bundle_id"]}).json()
    assert opened["bundle_id"] == one["bundle_id"] and opened["conversation_session"] is True, opened
    assert [d["data_request_id"] for d in opened["datasets"]]
    # another conversation naming the same bundle is refused, plainly
    other = post(outputs, "/v1/sessions", {"request_id": "req_other_1", "bundle_id": one["bundle_id"]}, key=OTHER)
    assert other.status_code == 404 and "another message or conversation" in other.json()["error"]["message"]


def test_without_a_conversation_key_a_bundle_is_still_required(outputs) -> None:
    missing = post(outputs, "/v1/sessions", {"request_id": "req_turn_1"}, key=None)
    assert missing.json()["error"]["code"] == "BUNDLE_REQUIRED"
    assert "prepare the data need's bundle first" in missing.json()["error"]["message"]


def test_the_runtime_lists_output_sessions(outputs) -> None:
    from test_dataneed_bundles import HEADERS
    runtime = outputs["api"].get("/v1/runtime", headers=HEADERS).json()
    assert runtime["output_sessions"]["enabled"] is True
