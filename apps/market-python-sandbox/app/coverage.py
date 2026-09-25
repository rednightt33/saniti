"""Coverage Validator (standalone): does what was delivered match the approved DataNeedSpec?

It compares four independent records and trusts none of them alone:

    approved DataNeedSpec contract (sandbox, at approval)
    SQL execution manifests        (Governor: lineage + executed scope derived from the compiled SQL)
    Data Quality Manifests         (profiler: what the delivered files actually hold)
    delivered bundle               (the verified files and the planner's partition list)

Delivery coverage (this module, at bundle creation) checks, per data request:

- every approved data_request_id is delivered, and nothing else is;
- every part's lineage names this need, plan, request and part, and its executed scope equals the approved scope,
  restrictions, columns and table, with no sampling and no truncation;
- the catalog version each part ran under equals the one the spec was approved against;
- the partitions tile every approved extraction window: on every date of every window each entity residue is
  covered exactly once (a gap is MISSING_PARTITION, a double cover OVERLAPPING_PARTITIONS);
- every part's delivered rows and entity set equal its SQL manifest (an entity present in SQL but missing
  downstream fails coverage);
- per range: the delivered windows cover it (PASS) or not (FAIL).

It never recalculates a formula: quality findings (empty ranges, gaps, buffer shortfalls, empty entities) are
reported by the profiler as flags, not as coverage failures. Processing coverage (was every approved request and
range read in the session) is checked at completion from the ExecutionManifest.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, timedelta
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def part_key(window: dict[str, str] | None, entity_partition: dict[str, int] | None) -> str:
    """Identity of one physical part; equals apps/market-sql-governor/app/extract.py part_key."""
    return sha256_json({"window": window, "entity_partition": entity_partition})


def entities_sha256(entities: list[str]) -> str:
    return sha256_json(sorted(entities))


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def check_part(approved: dict[str, Any], request: dict[str, Any], plan_id: str, need: dict[str, Any],
               part: dict[str, Any], validator: dict[str, Any]) -> list[dict[str, Any]]:
    """Lineage and executed scope of one delivered part against the approved request."""
    issues: list[dict[str, Any]] = []
    lineage = validator.get("lineage") or {}
    executed = validator.get("executed_scope") or {}
    pid = part["partition_id"]
    expected = {"need_id": need["need_id"], "spec_sha256": approved["spec_sha256"], "plan_id": plan_id,
                "request_group_id": approved["request_group_id"], "revision": approved["revision"],
                "data_request_id": request["data_request_id"], "scope_sha256": request["scope_sha256"],
                "restriction_sha256": request["restriction_sha256"], "part_key": part["part_key"]}
    for key, value in expected.items():
        if lineage.get(key) != value:
            issues.append(_issue("LINEAGE_MISMATCH", f"{pid}: lineage {key} does not match the approved need.",
                                 partition_id=pid, field=key))
    window = part.get("window")
    checks = {"version": "extract/v1", "data_request_id": request["data_request_id"],
              "source_table": request["source_table"], "columns": request["extract_columns"],
              "scope_sha256": request["scope_sha256"], "restriction_sha256": request["restriction_sha256"],
              "entity_partition": part.get("entity_partition"), "part_key": part["part_key"],
              "sampling": False, "truncation": False}
    for key, value in checks.items():
        if executed.get(key) != value:
            code = {"sampling": "SAMPLING_DETECTED", "truncation": "TRUNCATION_DETECTED"}.get(
                key, "EXECUTED_SCOPE_MISMATCH")
            issues.append(_issue(code, f"{pid}: the executed {key} differs from the approved request.",
                                 partition_id=pid, field=key))
    executed_window = executed.get("window")
    if (executed_window is None) != (window is None) or (window is not None and (
            executed_window.get("from"), executed_window.get("to")) != (window["from"], window["to"])):
        issues.append(_issue("EXECUTED_SCOPE_MISMATCH", f"{pid}: the executed window differs from the part.",
                             partition_id=pid, field="window"))
    if part_key(window, part.get("entity_partition")) != part["part_key"]:
        issues.append(_issue("LINEAGE_MISMATCH", f"{pid}: part_key does not describe the part.", partition_id=pid,
                             field="part_key"))
    contract = (validator.get("source_contracts") or {}).get(request["source_table"]) or {}
    if request.get("catalog_table_sha256") and contract.get("catalog_table_sha256") != request["catalog_table_sha256"]:
        issues.append(_issue("CATALOG_CHANGED_SINCE_APPROVAL", f"{pid}: {request['source_table']} was extracted "
                                                                 "under a different catalog version than approved.",
                             partition_id=pid))
    return issues


def _residues(partition: dict[str, int] | None, modulus: int) -> list[int]:
    if partition is None:
        return list(range(modulus))
    step = partition["modulus"]
    return [r for r in range(modulus) if r % step == partition["remainder"]]


def tiling(parts: list[dict[str, Any]], required: list[tuple[date, date]] | None) -> list[dict[str, Any]]:
    """Do the parts cover every date of the required windows (None: a static table) exactly once per entity
    residue? Returns the gaps and overlaps found."""
    issues: list[dict[str, Any]] = []
    moduli = [p["entity_partition"]["modulus"] for p in parts if p.get("entity_partition")]
    modulus = math.lcm(*moduli) if moduli else 1
    if modulus > 4096:
        return [_issue("PARTITION_LAYOUT_INVALID", "The entity partitions use incompatible moduli.")]
    if required is None:
        counts = [0] * modulus
        for p in parts:
            for r in _residues(p.get("entity_partition"), modulus):
                counts[r] += 1
        if any(c == 0 for c in counts):
            issues.append(_issue("MISSING_PARTITION", "Some entities of the static request are in no partition."))
        if any(c > 1 for c in counts):
            issues.append(_issue("OVERLAPPING_PARTITIONS", "Some entities are delivered by more than one partition."))
        return issues
    windows = [(date.fromisoformat(p["window"]["from"]), date.fromisoformat(p["window"]["to"]), p) for p in parts
               if p.get("window")]
    if len(windows) != len(parts):
        return [_issue("EXECUTED_SCOPE_MISMATCH", "A part of a dated request has no window.")]
    points = sorted({d for start, end, _ in windows for d in (start, end + timedelta(days=1))} |
                    {d for start, end in required for d in (start, end + timedelta(days=1))})
    for low, high in zip(points, points[1:]):
        last = high - timedelta(days=1)
        if not any(start <= low and last <= end for start, end in required):
            continue  # elementary interval outside every required window
        counts = [0] * modulus
        for start, end, p in windows:
            if start <= low and last <= end:
                for r in _residues(p.get("entity_partition"), modulus):
                    counts[r] += 1
        if any(c == 0 for c in counts):
            issues.append(_issue("MISSING_PARTITION", f"No partition delivers {low.isoformat()} to "
                                                      f"{last.isoformat()} for every entity.",
                                 **{"from": low.isoformat(), "to": last.isoformat()}))
        if any(c > 1 for c in counts):
            issues.append(_issue("OVERLAPPING_PARTITIONS", f"{low.isoformat()} to {last.isoformat()} is delivered "
                                                           "more than once.",
                                 **{"from": low.isoformat(), "to": last.isoformat()}))
    return issues


def delivery_coverage(approved: dict[str, Any], need: dict[str, Any], plan: dict[str, Any],
                      delivered: dict[str, dict[str, Any]], quality: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """delivered: partition_id -> {"validator": validator manifest, "row_count", "entities_present"}.
    quality: data_request_id -> Data Quality Manifest (profiler)."""
    requests_out = []
    planned = {r["data_request_id"]: r for r in plan["requests"]}
    global_issues = []
    for extra in sorted(set(planned) - set(approved["requests"])):
        global_issues.append(_issue("UNAPPROVED_REQUEST", f"{extra} is not a request of the approved need."))
    seen_keys: dict[str, str] = {}
    for rid in sorted(approved["requests"]):
        request = approved["requests"][rid]
        issues: list[dict[str, Any]] = []
        parts = (planned.get(rid) or {}).get("parts") or []
        if not parts:
            issues.append(_issue("MISSING_REQUEST", f"{rid} was not delivered."))
        for part in parts:
            key = (rid, part["part_key"])
            if canonical_json(key) in seen_keys:
                issues.append(_issue("DUPLICATE_PARTITIONS", f"{part['partition_id']} repeats "
                                                             f"{seen_keys[canonical_json(key)]}."))
            seen_keys[canonical_json(key)] = part["partition_id"]
            found = delivered.get(part["partition_id"])
            if found is None:
                issues.append(_issue("MISSING_PARTITION", f"{part['partition_id']} was not delivered.",
                                     partition_id=part["partition_id"]))
                continue
            issues += check_part(approved, request, plan["plan_id"], need, part, found["validator"])
            profile = next((p for p in (quality.get(rid) or {}).get("partitions") or []
                            if p["partition_id"] == part["partition_id"]), None)
            if profile is None or profile["rows"] != found["row_count"]:
                issues.append(_issue("ROW_COUNT_MISMATCH", f"{part['partition_id']}: delivered rows differ from "
                                                           "the SQL manifest.", partition_id=part["partition_id"]))
            sql_entities = found.get("entities_present")
            if profile is not None and sql_entities is not None and profile.get("entities_sha256") is not None \
                    and profile["entities_sha256"] != entities_sha256([str(e) for e in sql_entities]):
                issues.append(_issue("ENTITY_MISSING_DOWNSTREAM", f"{part['partition_id']}: the delivered entities "
                                                                  "differ from those the SQL extraction returned.",
                                     partition_id=part["partition_id"],
                                     sql_entities=len(sql_entities), delivered_entities=profile.get("entities")))
        windows = request.get("windows") or []
        required = [(date.fromisoformat(w["extract_from"]), date.fromisoformat(w["extract_to"])) for w in windows] \
            if request.get("time_column") else None
        if parts:
            issues += tiling(parts, required)
        ranges = []
        for w in windows:
            start, end = date.fromisoformat(w["extract_from"]), date.fromisoformat(w["extract_to"])
            gap = any(i["code"] in ("MISSING_PARTITION", "OVERLAPPING_PARTITIONS") and "from" in i
                      and date.fromisoformat(i["from"]) <= end and date.fromisoformat(i["to"]) >= start
                      for i in issues)
            ranges.append({"range_id": w["range_id"], "status": "FAIL" if gap or not parts else "PASS"})
        requests_out.append({
            "data_request_id": rid, "status": "FAIL" if issues else "PASS", "ranges": ranges,
            "partitions_expected": len(parts),
            "partitions_delivered": sum(1 for p in parts if p["partition_id"] in delivered),
            "sampling": any(i["code"] == "SAMPLING_DETECTED" for i in issues),
            "truncation": any(i["code"] == "TRUNCATION_DETECTED" for i in issues),
            "issues": issues[:25]})
    status = "PASS" if not global_issues and all(r["status"] == "PASS" for r in requests_out) else "FAIL"
    return {"coverage_status": status, "stage": "DELIVERY", "requests": requests_out, "issues": global_issues}


# ---------------------------------------------------------------- processing coverage (at completion)

FULL_READS = ("load", "sql", "relation")


def execution_manifest(session: dict[str, Any], bundle: dict[str, Any], executions: list[dict[str, Any]],
                       outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """What the session did: every execution (code hash, status, what the helpers read, outputs) and every output
    with its checksum. Built by the harness from its own records, never from anything the code reported."""
    reads: dict[str, dict[str, Any]] = {}
    for execution in executions:
        if execution["status"] != "OK":
            continue  # a failed execution produced nothing that can be relied on
        for entry in execution.get("access") or []:
            rid = entry.get("data_request_id")
            if not rid:
                continue
            record = reads.setdefault(rid, {"full_reads": 0, "ranges": {}, "rows_read": 0})
            record["rows_read"] += int(entry.get("rows") or 0)
            if entry.get("call") in FULL_READS:
                record["full_reads"] += 1
            elif entry.get("call") == "range":
                ranges = record["ranges"].setdefault(entry["range_id"], {"reads": 0, "include_buffers": False})
                ranges["reads"] += 1
                ranges["include_buffers"] = ranges["include_buffers"] or bool(entry.get("include_buffers"))
    return {
        "execution_manifest_version": "v1", "session_id": session["session_id"], "bundle_id": bundle["input_bundle_id"],
        "need_id": bundle["need_id"], "request_group_id": bundle["request_group_id"], "revision": bundle["revision"],
        "executions": [{k: e.get(k) for k in ("execution_id", "seq", "status", "code_sha256", "runtime_ms",
                                              "cpu_seconds", "outputs")} for e in executions],
        "reads": reads,
        "outputs": [{k: o.get(k) for k in ("output_id", "execution_id", "name", "type", "format", "row_count",
                                           "columns", "byte_count", "checksum_sha256")} for o in outputs]}


def processing_coverage(approved: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Was every approved request and range read in full through the helpers in a successful execution?
    A full read (load, sql, relation, or join on the whole datasets) covers every range; range() covers one."""
    out = []
    for rid in sorted(approved["requests"]):
        request = approved["requests"][rid]
        reads = manifest["reads"].get(rid) or {"full_reads": 0, "ranges": {}}
        full = reads["full_reads"] > 0
        ranges = [{"range_id": w["range_id"],
                   "status": "PROCESSED" if full or w["range_id"] in reads["ranges"] else "NOT_PROCESSED"}
                  for w in request.get("windows") or []]
        processed = full or (bool(ranges) and all(r["status"] == "PROCESSED" for r in ranges))
        out.append({"data_request_id": rid, "logical_name": request["logical_name"],
                    "status": "PROCESSED" if processed else "NOT_PROCESSED", "ranges": ranges})
    return out
