"""EXEC-V stage 2 (M110, user decision 2026-10-07: "1 data ... tidak perlu lagi request data"): the request ids,
logical names and range ids of a DataNeedSpec are labels the model chose; identical data asked under other labels is
recognised by its content (contract_alias), the earlier bundle is reused without an extraction, and the session sees
it under the later need's labels (aliased_manifest). Several needs of one request that share a bundle are served in
the order they were prepared."""
from __future__ import annotations

import copy
from datetime import date

from app.data_need import aliased_manifest, contract_alias, contract_covers, data_contract_sha256, validate
from conftest import requires_root
from dataneed_fixtures import classification, current_state, data_need_catalog, prices, subset, ytd_spec
from test_conversation_reuse import reuse  # noqa: F401 - the conversation-reuse sandbox fixture

REF = date(2026, 9, 25)
TABLES = ["Price_Stock_Indonesia_IDX", "IDX_Stock_Universe"]


def relabelled(group: str = "exp_two", **overrides) -> dict:
    """ytd_spec's data under other labels, with the requests listed in the other order."""
    px = prices(f"{group}_A", logical_name="px", time_ranges=[
        {"range_id": "before", "start": "2025-01-01", "end": "2025-09-25"},
        {"range_id": "now", "start": "2026-01-01", "end": "2026-09-25"}])
    banks = classification(f"{group}_B", logical_name="banks")
    spec = ytd_spec(request_group_id=group, data_requests=[banks, px],
                    relationships=[current_state(left_request_id=f"{group}_A", right_request_id=f"{group}_B")])
    spec.update(overrides)
    return spec


def approved(spec: dict) -> dict:
    outcome = validate(spec, subset(data_need_catalog(), TABLES), REF)
    assert outcome.status == "APPROVED", outcome.issues
    return outcome.approved


def test_the_same_data_under_other_labels_is_paired_by_content() -> None:
    earlier, later = approved(ytd_spec()), approved(relabelled())
    alias, difference = contract_alias(earlier, later)
    assert difference is None and contract_covers(earlier, later) is None
    assert alias["requests"]["data_request_1_A"] == {
        "data_request_id": "exp_two_A", "logical_name": "px",
        "ranges": {"current_ytd": "now", "previous_comparable": "before"}}
    assert alias["requests"]["data_request_1_B"]["logical_name"] == "banks"
    # the stored contract hash keeps the labels (audit and earlier bundles unchanged); the match no longer needs it
    assert data_contract_sha256(earlier) != data_contract_sha256(later)
    # equal labels give an empty alias (nothing to rename)
    assert contract_alias(earlier, approved(ytd_spec())) == ({}, None)


def test_other_data_is_never_paired_whatever_the_labels() -> None:
    earlier = approved(ytd_spec())
    window = relabelled()
    window["data_requests"][1]["time_ranges"][0]["start"] = "2025-02-03"
    assert contract_alias(earlier, approved(window))[0] is None  # another window
    scope = relabelled()
    scope["data_requests"][0]["scope"]["value"] = "Insurance"
    assert contract_covers(earlier, approved(scope)) is not None  # another scope
    narrow = ytd_spec()
    narrow["data_requests"][0]["columns"] = ["ticker", "date", "close"]
    assert contract_covers(approved(narrow), approved(relabelled())) is not None  # columns the earlier data lacks
    alone = relabelled(relationships=[])
    assert contract_covers(earlier, approved(alone)) is not None  # the earlier data was restricted by a join
    basis = copy.deepcopy(approved(relabelled()))
    basis["time_basis"] = "POINT_IN_TIME"
    assert contract_covers(earlier, basis) == "time_basis"  # point-in-time never reuses descriptive data
    fewer = relabelled(data_requests=[relabelled()["data_requests"][1]], relationships=[])
    assert contract_covers(earlier, approved(fewer)) == "requests"


def test_a_narrower_need_under_other_labels_is_served() -> None:
    narrow = relabelled()
    narrow["data_requests"][1]["columns"] = ["ticker", "date", "close"]
    alias, difference = contract_alias(approved(ytd_spec()), approved(narrow))
    assert difference is None and alias["requests"]["data_request_1_A"]["logical_name"] == "px"


def test_the_manifest_is_renamed_everywhere_and_its_files_are_not() -> None:
    alias, _ = contract_alias(approved(ytd_spec()), approved(relabelled()))
    manifest = {
        "input_bundle_id": "bundle_1", "need_id": "need_1", "checksum_sha256": "c" * 64,
        "datasets": [{"data_request_id": "data_request_1_A", "logical_name": "prices",
                      "partitions": [{"partition_id": "data_request_1_A__p1", "file": "data_request_1_A/p1.parquet",
                                      "checksum_sha256": "a" * 64}],
                      "ranges": [{"range_id": "current_ytd"}],
                      "quality": {"requested_ranges": [{"range_id": "previous_comparable", "rows": 3}]}},
                     {"data_request_id": "data_request_1_B", "logical_name": "stock_classification",
                      "partitions": [], "ranges": []}],
        "relationships": [{"relationship_id": 2, "left_request_id": "data_request_1_A",
                           "right_request_id": "data_request_1_B"}],
        "coverage": {"coverage_status": "PASS", "requests": [
            {"data_request_id": "data_request_1_A", "status": "PASS",
             "ranges": [{"range_id": "current_ytd", "status": "PASS"}]}]}}
    renamed = aliased_manifest(manifest, alias)
    prices_, banks = renamed["datasets"]
    assert (prices_["data_request_id"], prices_["logical_name"]) == ("exp_two_A", "px")
    assert banks["logical_name"] == "banks" and prices_["ranges"] == [{"range_id": "now"}]
    assert prices_["quality"]["requested_ranges"][0]["range_id"] == "before"
    assert prices_["partitions"] == manifest["datasets"][0]["partitions"]  # files and checksums unchanged
    assert renamed["relationships"][0]["left_request_id"] == "exp_two_A"
    assert renamed["coverage"]["requests"][0]["ranges"][0]["range_id"] == "now"
    assert renamed["input_bundle_id"] == "bundle_1" and renamed["checksum_sha256"] == "c" * 64
    assert {(a["data_request_id"], a["bundle_data_request_id"]) for a in renamed["aliases"]} == {
        ("exp_two_A", "data_request_1_A"), ("exp_two_B", "data_request_1_B")}
    assert manifest["datasets"][0]["logical_name"] == "prices"  # the stored manifest is not changed
    assert aliased_manifest(manifest, {}) is manifest


# ------------------------------------------------------------------------------------------------ sandbox (root)

RELABELLED_CODE = """
px = load_range('px', 'now')
banks = load('banks')
last = px.groupby('ticker', as_index=False)['close'].last()
before = load_range('px', 'before')
emit_table('last_close', last, definition={})
"""


@requires_root
def test_a_follow_up_under_other_labels_reuses_the_bundle_in_a_new_session(reuse) -> None:
    from test_conversation_reuse import approve, complete, execute, first_turn, post

    one = first_turn(reuse)
    extracted = len(reuse["governor"].datasets)
    need = approve(reuse, "req_turn_2", spec=relabelled())
    reused = post(reuse, "/v1/bundles/reuse", {"request_id": "req_turn_2", "need_id": need["need_id"]}).json()
    assert reused["status"] == "READY" and reused["input_bundle_id"] == one["bundle_id"], reused
    assert len(reuse["governor"].datasets) == extracted  # no new extraction
    assert {d["logical_name"] for d in reused["datasets"]} == {"px", "banks"}
    assert "other request labels" in reused["note"] and len(reused["aliases"]) == 2
    opened = post(reuse, "/v1/sessions", {"request_id": "req_turn_2", "bundle_id": one["bundle_id"]}).json()
    # the warm worker knows the earlier labels, so the same files open in a new worker under the new ones
    assert opened["session_id"] != one["session_id"] and not opened.get("reused_session"), opened
    assert opened["need_id"] == need["need_id"] and {d["logical_name"] for d in opened["datasets"]} == {"px", "banks"}
    ran = execute(reuse, opened["session_id"], "req_turn_2", RELABELLED_CODE)
    assert ran["status"] == "OK", ran
    done = complete(reuse, opened["session_id"], "req_turn_2")
    assert done["status"] == "COMPLETED", done
    assert {r["data_request_id"] for r in done["coverage"]["requests"]} == {"exp_two_A", "exp_two_B"}
    assert reuse["dataneed"].store.get_session(one["session_id"])["status"] == "WARM_IDLE"


@requires_root
def test_needs_of_one_request_that_share_a_bundle_are_served_in_order(reuse) -> None:
    from test_conversation_reuse import YTD, approve, complete, execute, post
    from test_dataneed_bundles import build, ytd_parts

    first = approve(reuse, "req_one")
    bundle = build(reuse, first, ytd_parts(reuse, first), request_id="req_one").json()
    second = approve(reuse, "req_one", spec=relabelled())
    reused = post(reuse, "/v1/bundles/reuse", {"request_id": "req_one", "need_id": second["need_id"]}).json()
    assert reused["input_bundle_id"] == bundle["input_bundle_id"] and reused["reused"] is True, reused
    # the bundle's own need first: it was prepared first and has no result yet
    opened = post(reuse, "/v1/sessions", {"request_id": "req_one", "bundle_id": bundle["input_bundle_id"]}).json()
    assert opened["need_id"] == first["need_id"] and "aliases" not in opened
    assert execute(reuse, opened["session_id"], "req_one", YTD)["status"] == "OK"
    assert complete(reuse, opened["session_id"], "req_one")["status"] == "COMPLETED"
    # then the need that asked the same data under other labels
    again = post(reuse, "/v1/sessions", {"request_id": "req_one", "bundle_id": bundle["input_bundle_id"]}).json()
    assert again["need_id"] == second["need_id"] and {d["logical_name"] for d in again["datasets"]} == {"px", "banks"}
    assert execute(reuse, again["session_id"], "req_one", RELABELLED_CODE)["status"] == "OK"
    done = complete(reuse, again["session_id"], "req_one")
    assert done["status"] == "COMPLETED" and done["need_id"] == second["need_id"], done


@requires_root
def test_a_research_need_under_other_labels_runs_its_event_study_on_the_reused_bundle(make_service, governor) -> None:
    """Research in a later message: the data is reused, the workspace is new (user decision 2026-10-07), and the
    backend's event study and verdict read the bundle under the research need's labels."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from test_conversation_reuse import first_turn, post
    from test_research_findings_session import CODE, GOVERNANCE
    from test_dataneed_bundles import REFERENCE

    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true", PY_SANDBOX_RESEARCH_FINDINGS_ENABLED="true",
                           PY_SANDBOX_ENABLE_CONVERSATION_REUSE="true", PY_SANDBOX_SESSION_EXECUTION_SECONDS="5")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    try:
        one = first_turn(env)
        extracted = len(governor.datasets)
        body = {"request_id": "req_turn_2", "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
                "spec": relabelled(mode="RESEARCH"), "research_governance": GOVERNANCE}
        need = post(env, "/v1/data-needs", body).json()
        assert need["status"] == "APPROVED", need
        reused = post(env, "/v1/bundles/reuse", {"request_id": "req_turn_2", "need_id": need["need_id"]}).json()
        assert reused["input_bundle_id"] == one["bundle_id"] and len(governor.datasets) == extracted, reused
        opened = post(env, "/v1/sessions", {"request_id": "req_turn_2", "bundle_id": one["bundle_id"]}).json()
        assert opened["session_id"] != one["session_id"] and opened["need_id"] == need["need_id"], opened
        code = CODE.replace("load('stock_classification')", "load('banks')").replace("load('prices')", "load('px')")
        ran = post(env, f"/v1/sessions/{opened['session_id']}/execute", {"request_id": "req_turn_2", "code": code}).json()
        assert ran["status"] == "OK", ran
        done = post(env, f"/v1/sessions/{opened['session_id']}/complete", {"request_id": "req_turn_2"}).json()
        assert done["status"] == "COMPLETED", done
        assert [f["hypothesis_id"] for f in done["final_status"]["research_findings"]] == ["bank_gain"]
    finally:
        env["dataneed"].sessions.stop()
