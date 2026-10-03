"""R-STORE (round 2026-10-03 C2c-C2e): a released output's file for the orchestrator's durable copy, the data date
of its bundle in the lineage, a stored table uploaded back into a later session of the same conversation, and a range
ending LATEST bound to the conversation's data date."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date

from app.data_need import validate
from conftest import requires_root
from dataneed_fixtures import classification, prices, subset, data_need_catalog, ytd_spec
from test_conversation_reuse import KEY, OTHER, approve, attach, execute, first_turn, headers, post, reuse  # noqa: F401
from test_dataneed_bundles import HEADERS

pytestmark = requires_root


def file_of(env, session_id: str, output_id: str, request_id: str, key: str | None = KEY):
    return env["api"].get(f"/v1/sessions/{session_id}/outputs/{output_id}/file", params={"request_id": request_id},
                          headers=headers(key))


def restore(env, session_id: str, request_id: str, meta: dict, data: bytes, key: str | None = KEY):
    encoded = base64.urlsafe_b64encode(json.dumps(meta).encode()).decode().rstrip("=")
    return env["api"].post(f"/v1/sessions/{session_id}/carried", params={"request_id": request_id}, content=data,
                           headers={**headers(key), "X-Saniti-Output-Meta": encoded,
                                    "Content-Type": "application/octet-stream"})


def test_a_released_file_is_copied_with_its_checksum_and_data_date(reuse) -> None:
    one = first_turn(reuse)
    got = file_of(reuse, one["session_id"], one["output_id"], "req_turn_1")
    assert got.status_code == 200
    assert hashlib.sha256(got.content).hexdigest() == got.headers["X-Saniti-Checksum-Sha256"]
    assert got.headers["X-Saniti-Format"] == "PARQUET"
    # another conversation never reads it
    assert file_of(reuse, one["session_id"], one["output_id"], "req_x", key=OTHER).status_code == 404
    completion = reuse["dataneed"].store.passed_completions(one["session_id"])[-1]["final_status"]
    [released] = completion["released_outputs"]
    assert released["lineage"]["data_as_of"] <= released["lineage"]["reference_date"]


def test_an_expired_table_is_restored_into_a_later_session(reuse) -> None:
    one = first_turn(reuse)
    data = file_of(reuse, one["session_id"], one["output_id"], "req_turn_1").content
    store, sessions = reuse["dataneed"].store, reuse["dataneed"].sessions
    output = store.get_output(one["output_id"])
    (sessions.outputs_root / output["relative_path"]).unlink()  # the sandbox's copy expired
    store.delete_output(one["output_id"])
    _, opened = attach(reuse, "req_turn_2")
    meta = {"output_id": one["output_id"], "name": "last_close", "format": "PARQUET",
            "checksum_sha256": hashlib.sha256(data).hexdigest(), "definition": {"filters": [], "notes": "x"},
            "data_as_of": "2026-09-25", "origin": {"evidence_label": "DATA_COVERAGE_VERIFIED",
                                                   "request_id": "req_turn_1"}}
    bad = restore(reuse, opened["session_id"], "req_turn_2", {**meta, "checksum_sha256": "0" * 64}, data)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "RESTORE_CHECKSUM_MISMATCH"
    assert restore(reuse, opened["session_id"], "req_turn_2", meta, data, key=OTHER).status_code == 409
    done = restore(reuse, opened["session_id"], "req_turn_2", meta, data)
    assert done.status_code == 200 and done.json()["status"] == "RESTORED", done.text
    assert restore(reuse, opened["session_id"], "req_turn_2", meta, data).json()["status"] == "ALREADY_PRESENT"
    ran = execute(reuse, opened["session_id"], "req_turn_2",
                  f"t = load_output('{one['output_id']}')\n"
                  f"entry = [c for c in carried() if c['output_id'] == '{one['output_id']}'][0]\n"
                  "print(len(t), entry['restored'], entry['data_as_of'], entry['label'])")
    assert ran["status"] == "OK", ran
    assert "True 2026-09-25 DATA_COVERAGE_VERIFIED" in ran["stdout"]


def test_the_runtime_reports_the_result_store_capability(reuse) -> None:
    runtime = reuse["api"].get("/v1/runtime", headers=HEADERS).json()
    assert runtime["result_store"]["enabled"] is True and runtime["result_store"]["version"] == 1


def test_latest_is_bound_to_the_conversation_data_date() -> None:
    spec = ytd_spec(data_requests=[prices(time_ranges=[
        {"range_id": "current_ytd", "start": "2026-01-01", "end": "LATEST"}]), classification()])
    catalog = subset(data_need_catalog(), ["IDX_Stock_Universe", "Price_Stock_Indonesia_IDX"])
    pinned = validate(spec, catalog, date(2026, 9, 25), latest_bound=date(2026, 9, 20))
    [window] = pinned.approved["requests"]["data_request_1_A"]["windows"]
    assert window["end"] == "2026-09-20" and window["as_of_date"] == "2026-09-20"
    later = validate(spec, catalog, date(2026, 9, 25), latest_bound=date(2026, 9, 30))  # never after today
    [window] = later.approved["requests"]["data_request_1_A"]["windows"]
    assert window["end"] == "2026-09-25" and "as_of_date" not in window
