"""EXEC-V 2026-10-08 (option D, version (i), one conversation; M113): the identity of extracted data is the SQL the
Governor runs for it (data_sha256). A later need of the same conversation whose part has the same SQL, a date range
that ends before the reference date, a copy that has not expired and the same catalog reuses the earlier verified file
(reuse_of) instead of extracting it again, whatever its request labels; every other part is extracted, with the reason
named. The bundle builder checks a reused part itself (same conversation, same SQL, the fields that decide its rows)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from app.coverage import sha256_json
from conftest import requires_root
from dataneed_fixtures import classification, prices, ytd_spec
from test_conversation_reuse import KEY, OTHER, approve, complete, execute, post, reuse  # noqa: F401
from test_dataneed_bundles import HEADERS, build, extract_part, price_rows

pytestmark = requires_root
TICKERS = ["BBCA", "BBRI", "BMRI"]


def spec(group: str = "data_request_1", name: str = "prices", now: str = "current", before: str = "previous",
         end: str = "2026-09-01", static: bool = False) -> dict:
    """Daily prices of two closed ranges (both end before the reference date 2026-09-25) under the given labels."""
    px = prices(f"{group}_A", logical_name=name, time_ranges=[
        {"range_id": now, "start": "2026-08-03", "end": end},
        {"range_id": before, "start": "2025-08-01", "end": "2025-09-01"}])
    requests = [px] + ([classification(f"{group}_B")] if static else [])
    return ytd_spec(request_group_id=group, data_requests=requests, relationships=[])


def identity(request: dict, window: dict | None) -> str:
    """The Governor's data_sha256 stand-in: what decides the rows, no labels."""
    return sha256_json({"table": request["source_table"], "columns": request["extract_columns"],
                        "scope": request["scope_sha256"], "restrictions": request["restriction_sha256"],
                        "window": window, "order": request.get("ordering")})


def parts_of(env, need: dict) -> tuple[list[dict], list[dict]]:
    """Extract every range of every request as one part each (the Governor's validator carries data_sha256)."""
    plan, lookups = [], []
    for rid, request in sorted(need["requests"].items()):
        parts = []
        windows = [{"from": w["extract_from"], "to": w["extract_to"], "range_id": w["range_id"]}
                   for w in request.get("windows") or []] or [None]
        for w in windows:
            window = {"from": w["from"], "to": w["to"]} if w else None
            frame = price_rows(TICKERS, w["from"], w["to"]) if w else \
                __import__("test_dataneed_bundles").universe_rows()
            part = extract_part(env, need, rid, frame, f"{rid}__{w['range_id'] if w else 'static'}__part_001",
                                window=window)
            sha = identity(request, window)
            env["governor"].datasets[part["dataset_id"]]["manifest"]["validator_manifest"]["data_sha256"] = sha
            parts.append({**part, "data_sha256": sha})
            lookups.append({"data_request_id": rid, "part_key": part["part_key"], "data_sha256": sha,
                            "window": window})
        plan.append({"data_request_id": rid, "envelopes": [], "parts": [
            {k: v for k, v in p.items() if k != "data_sha256"} for p in parts]})
    return plan, lookups


def lookup(env, request_id: str, need: dict, items: list[dict], key: str = KEY) -> dict:
    return post(env, "/v1/parts/lookup", {"request_id": request_id, "need_id": need["need_id"], "parts": items},
                key=key).json()


def first_turn(env, **labels) -> dict:
    need = approve(env, "req_turn_1", spec=spec(**labels))
    plan, _ = parts_of(env, need)
    bundle = build(env, need, plan, request_id="req_turn_1").json()
    assert bundle["status"] == "READY", bundle
    env["api"].post("/v1/requests/req_turn_1/release", headers=HEADERS)
    return env["api"].get(f"/v1/bundles/{bundle['input_bundle_id']}", headers=HEADERS).json()


def wanted(need: dict) -> list[dict]:
    """The lookups of a later need, as the planner sends them after its estimates (data_sha256 from the Governor)."""
    items = []
    for rid, request in sorted(need["requests"].items()):
        for w in request.get("windows") or [None]:
            window = {"from": w["extract_from"], "to": w["extract_to"]} if w else None
            from app.coverage import part_key
            items.append({"data_request_id": rid, "part_key": part_key(window, None),
                          "data_sha256": identity(request, window), "window": window})
    return items


def reused_plan(need: dict, items: list[dict], found: dict) -> list[dict]:
    by_request: dict[str, list[dict]] = {}
    for item, match in zip(items, found["parts"]):
        rid = item["data_request_id"]
        range_id = next(w["range_id"] for w in need["requests"][rid]["windows"]
                        if w["extract_from"] == item["window"]["from"])
        by_request.setdefault(rid, []).append({
            "partition_id": f"{rid}__{range_id}__part_001", "dataset_id": match["dataset_id"],
            "part_key": item["part_key"], "window": item["window"], "entity_partition": None,
            "reuse_of": match["reuse_of"], "data_sha256": item["data_sha256"]})
    return [{"data_request_id": rid, "envelopes": [], "parts": parts} for rid, parts in by_request.items()]


def test_the_same_sql_under_other_labels_is_reused_without_an_extraction_and_runs_in_a_new_session(reuse) -> None:
    earlier = first_turn(reuse)
    need = approve(reuse, "req_turn_2", spec=spec("exp_two", "px", "now", "before"))
    items = wanted(need)
    found = lookup(reuse, "req_turn_2", need, items)
    assert [p["status"] for p in found["parts"]] == ["MATCH", "MATCH"], found
    assert {p["reuse_of"]["bundle_id"] for p in found["parts"]} == {earlier["input_bundle_id"]}
    assert all(p["request_id"] == "req_turn_1" and p["extracted_at"] for p in found["parts"])
    datasets, grants = len(reuse["governor"].datasets), len(reuse["governor"].calls)
    built = build(reuse, need, reused_plan(need, items, found), request_id="req_turn_2").json()
    assert built["status"] == "READY" and built["coverage_status"] == "PASS", built
    assert len(reuse["governor"].datasets) == datasets and len(reuse["governor"].calls) == grants  # no Governor call
    manifest = reuse["api"].get(f"/v1/bundles/{built['input_bundle_id']}", headers=HEADERS).json()
    [dataset] = manifest["datasets"]
    assert dataset["data_request_id"] == "exp_two_A" and dataset["logical_name"] == "px"
    assert {p["reused_from"]["bundle_id"] for p in dataset["partitions"]} == {earlier["input_bundle_id"]}
    old = {p["checksum_sha256"] for p in earlier["datasets"][0]["partitions"]}
    assert {p["checksum_sha256"] for p in dataset["partitions"]} == old  # the same verified files
    folder = reuse["dataneed"].bundles.path_of(built["input_bundle_id"], dataset["partitions"][0]["file"])
    assert os.stat(folder).st_nlink == 2  # linked, not copied
    # the later need's own labels in its own session
    opened = post(reuse, "/v1/sessions", {"request_id": "req_turn_2", "bundle_id": built["input_bundle_id"]}).json()
    assert opened["session_id"] and opened["datasets"][0]["data_request_id"] == "exp_two_A", opened
    code = ("px = load_range('px', 'now')\nold = load_range('px', 'before')\n"
            "emit_table('n', px.groupby('ticker', as_index=False)['close'].last(), definition={})")
    assert execute(reuse, opened["session_id"], "req_turn_2", code)["status"] == "OK"
    assert complete(reuse, opened["session_id"], "req_turn_2")["status"] == "COMPLETED"
    # a third need reuses the reused parts and keeps the first extraction time
    third = approve(reuse, "req_turn_3", spec=spec("exp_three", "q", "a", "b"))
    again = lookup(reuse, "req_turn_3", third, wanted(third))
    assert [p["status"] for p in again["parts"]] == ["MATCH", "MATCH"]
    assert {p["extracted_at"] for p in again["parts"]} == {p["extracted_at"] for p in found["parts"]}


def test_every_part_not_reused_names_its_reason(reuse) -> None:
    earlier = first_turn(reuse)
    # a range reaching the reference date (2026-09-25), and a static request: always extracted
    today = approve(reuse, "req_turn_2", spec=spec("exp_two", end="2026-09-25", static=True))
    reasons = {(p["data_sha256"] == identity(today["requests"]["exp_two_B"], None), p.get("reason"))
               for p in lookup(reuse, "req_turn_2", today, wanted(today))["parts"]}
    assert reasons == {(False, "RANGE_INCLUDES_TODAY"), (False, None), (True, "NO_DATE_RANGE")}
    listed = lookup(reuse, "req_turn_2", today, wanted(today))["parts"]
    assert all(p["message"] for p in listed if p["status"] == "NO_MATCH")
    # another conversation never sees this one's data
    other = approve(reuse, "req_other", key=OTHER, spec=spec("exp_four"))
    assert {p["reason"] for p in lookup(reuse, "req_other", other, wanted(other), key=OTHER)["parts"]} == {
        "NOT_EXTRACTED_IN_CONVERSATION"}
    # a changed catalog, then an expired copy
    store = reuse["dataneed"].store
    record = store.get_bundle(earlier["input_bundle_id"])
    manifest = record["manifest"]
    for partition in manifest["datasets"][0]["partitions"]:
        partition["validator"]["source_contracts"]["Price_Stock_Indonesia_IDX"]["catalog_table_sha256"] = "0" * 64
    store._update("bundles", "bundle_id", earlier["input_bundle_id"], {"manifest": manifest})
    later = approve(reuse, "req_turn_5", spec=spec("exp_five"))
    assert {p["reason"] for p in lookup(reuse, "req_turn_5", later, wanted(later))["parts"]} == {"CATALOG_CHANGED"}
    manifest["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    store._update("bundles", "bundle_id", earlier["input_bundle_id"], {"manifest": manifest})
    assert {p["reason"] for p in lookup(reuse, "req_turn_5", later, wanted(later))["parts"]} == {"EXPIRED"}


def test_the_builder_checks_a_reused_part_itself(reuse) -> None:
    first_turn(reuse)
    need = approve(reuse, "req_turn_2", spec=spec("exp_two"))
    items = wanted(need)
    found = lookup(reuse, "req_turn_2", need, items)
    # a planner that claims another SQL for the part is refused before anything is linked
    claimed = reused_plan(need, items, found)
    claimed[0]["parts"][0]["data_sha256"] = "f" * 64
    refused = build(reuse, need, claimed, request_id="req_turn_2")
    assert refused.status_code != 200 and refused.json()["error"]["code"] == "REUSE_NOT_ALLOWED", refused.text
    # a need whose rows differ (fewer columns) under the same claimed SQL fails coverage on the executed columns
    narrow = approve(reuse, "req_turn_3", spec=spec("exp_three"))
    narrow_items = wanted(narrow)
    plan = reused_plan(narrow, narrow_items, lookup(reuse, "req_turn_3", narrow, narrow_items))
    store = reuse["dataneed"].store
    record = store.get_need(narrow["need_id"])
    record["approved"]["requests"]["exp_three_A"]["extract_columns"] = ["ticker", "date", "close"]
    store._update("data_needs", "need_id", narrow["need_id"], {"approved": record["approved"]})
    bad = build(reuse, reuse["dataneed"].get_need(narrow["need_id"]), plan, request_id="req_turn_3").json()
    assert bad["status"] == "REJECTED" and "EXECUTED_SCOPE_MISMATCH" in str(bad["coverage_issues"]), bad


def test_the_runtime_reports_part_reuse(reuse) -> None:
    runtime = reuse["api"].get("/v1/runtime", headers=HEADERS).json()
    assert runtime["part_reuse"] == {"enabled": True, "version": 2}


def test_within_one_answer_a_range_up_to_today_and_current_state_data_are_read_once(reuse) -> None:
    """V-f (user decision 2026-10-08 "ambil jadi sekali saja", go 2026-10-09): GT1 (ma-qa-variant-20261008a) extracted
    the same BBCA data twice in one research answer. Within one answer (same request, same reference date) a later need
    reuses the parts of an earlier one even when the range reaches today or has no range; another answer of the
    conversation still extracts them (newer rows may have arrived)."""
    first = approve(reuse, "req_one", spec=spec("exp_a", end="2026-09-25", static=True))
    plan, _ = parts_of(reuse, first)
    assert build(reuse, first, plan, request_id="req_one").json()["status"] == "READY"
    second = approve(reuse, "req_one", spec=spec("exp_b", "px", "x", "y", end="2026-09-25", static=True))
    found = lookup(reuse, "req_one", second, wanted(second))["parts"]
    assert [p["status"] for p in found] == ["MATCH", "MATCH", "MATCH"], found
    assert all(p["same_answer"] for p in found)
    later = approve(reuse, "req_two", spec=spec("exp_c", end="2026-09-25", static=True))
    reasons = sorted(p.get("reason") or "MATCH" for p in lookup(reuse, "req_two", later, wanted(later))["parts"])
    assert reasons == ["MATCH", "NO_DATE_RANGE", "RANGE_INCLUDES_TODAY"]  # the closed range is reused across answers


def test_two_requests_of_one_plan_with_the_same_sql_are_extracted_once(reuse) -> None:
    """V-f within one plan: a second request whose part has the same Governor SQL names the first part (same_as);
    the builder links the stored file, coverage checks it on the fields that decide its rows, and a twin that claims
    another part key or a part that is itself a twin is refused."""
    from dataneed_fixtures import prices as price_request

    window_ranges = [{"range_id": "r", "start": "2026-08-03", "end": "2026-09-01"}]
    two = ytd_spec(request_group_id="twins", relationships=[], data_requests=[
        price_request("twins_A", logical_name="horizon_3", time_ranges=window_ranges),
        price_request("twins_B", logical_name="horizon_10", time_ranges=window_ranges)])
    need = approve(reuse, "req_twins", spec=two)
    a, b = need["requests"]["twins_A"], need["requests"]["twins_B"]
    window = {"from": a["windows"][0]["extract_from"], "to": a["windows"][0]["extract_to"]}
    assert identity(a, window) == identity(b, window)
    part = extract_part(reuse, need, "twins_A", price_rows(TICKERS, window["from"], window["to"]),
                        "twins_A__r__part_001", window=window)
    sha = identity(a, window)
    reuse["governor"].datasets[part["dataset_id"]]["manifest"]["validator_manifest"]["data_sha256"] = sha
    twin = {**part, "partition_id": "twins_B__r__part_001", "same_as": part["partition_id"], "data_sha256": sha}
    calls = len(reuse["governor"].calls)
    plan = [{"data_request_id": "twins_A", "envelopes": [], "parts": [part]},
            {"data_request_id": "twins_B", "envelopes": [], "parts": [twin]}]
    built = build(reuse, need, plan, request_id="req_twins").json()
    assert built["status"] == "READY" and built["coverage_status"] == "PASS", built
    assert len(reuse["governor"].calls) == calls + 1  # one grant for one dataset
    manifest = reuse["api"].get(f"/v1/bundles/{built['input_bundle_id']}", headers=HEADERS).json()
    by_request = {d["data_request_id"]: d for d in manifest["datasets"]}
    assert by_request["twins_B"]["partitions"][0]["same_as"] == "twins_A__r__part_001"
    assert by_request["twins_B"]["rows"] == by_request["twins_A"]["rows"] > 0
    assert by_request["twins_B"]["partitions"][0]["checksum_sha256"] == \
        by_request["twins_A"]["partitions"][0]["checksum_sha256"]
    for broken in ({**twin, "part_key": "0" * 64}, {**twin, "same_as": "twins_B__r__part_001"}):
        refused = build(reuse, need, [plan[0], {"data_request_id": "twins_B", "envelopes": [], "parts": [broken]}],
                        request_id="req_twins")
        assert refused.json().get("error", {}).get("code") == "INVALID_PLAN" or \
            refused.json().get("code") == "INVALID_PLAN", refused.text
