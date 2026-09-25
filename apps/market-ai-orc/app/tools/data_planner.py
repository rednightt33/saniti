"""prepare_data_bundle: the Execution Planner between an approved DataNeedSpec and a governed data bundle.

The model only names a need_id. Everything physical is decided here and checked again by the SQL Governor and the
sandbox, so a planner bug cannot silently change the data:

1. read the approved contract of the need from the sandbox (same request only);
2. per data request, merge the approved extraction windows of its ranges into envelopes: overlapping or adjacent
   windows become one extraction (the logical ranges keep their own ids and bounds), separate ones stay separate;
3. build one ExtractionSpec per envelope: the pruned columns (the request's columns plus its key columns), the
   canonical scope pushed down as a predicate tree, INNER relationships pushed down as point-in-time semi-joins,
   the envelope window, and the requested ordering (the Governor completes it with the key columns);
4. submit it to the Governor's /v1/extract with lineage (need, spec hash, scope and restriction hashes, plan id,
   part key, envelope, catalog hash, extraction hash). APPROVED_WITH_PARTITIONING splits the part by date or by
   entity hash as the Governor says and resubmits the pieces; a REJECTED_* status stops the plan and names the
   logical request; nothing is sampled, truncated, narrowed or re-scoped;
5. name every part deterministically (<data_request_id>__<range_id>__part_NNN for an envelope of one range,
   <data_request_id>__part_NNN for a merged envelope, <data_request_id>__static__part_NNN for a static table);
6. ask the sandbox for the bundle (POST /v1/bundles): it verifies every dataset, profiles it and checks delivery
   coverage before the bundle is READY.

Resampling is never pushed down: the approved catalog rules travel with the bundle and the session resamples.
"""
from __future__ import annotations

import hashlib
import json
import math
import secrets
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .registry import ToolSpec
from .request_data import current_request_id

NEED_ID_PATTERN = r"^need_[0-9a-f]{24}$"
MAX_PARTS_PER_REQUEST = 64
MAX_MODULUS = 4096
FORBIDDEN_ACTIONS = ["CHANGE_USER_SCOPE", "SAMPLE_WITHOUT_PERMISSION", "DROP_ENTITIES", "SHORTEN_PERIOD",
                     "CHANGE_FREQUENCY", "CHANGE_JOIN_SEMANTICS"]


class PrepareDataBundleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    need_id: str = Field(pattern=NEED_ID_PATTERN, description="need_id of an APPROVED DataNeedSpec.")


def canonical_json(value: Any) -> str:
    """Byte-identical to the Governor's and the sandbox's canonical_json (lineage hashes)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def part_key(window: dict[str, str] | None, entity_partition: dict[str, int] | None) -> str:
    return sha256_json({"window": window, "entity_partition": entity_partition})


def merge_windows(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Envelopes of overlapping or adjacent extraction windows; each keeps the range ids it serves."""
    ordered = sorted(windows, key=lambda w: (w["extract_from"], w["extract_to"]))
    envelopes: list[dict[str, Any]] = []
    for w in ordered:
        start, end = date.fromisoformat(w["extract_from"]), date.fromisoformat(w["extract_to"])
        if envelopes and start <= date.fromisoformat(envelopes[-1]["to"]) + timedelta(days=1):
            last = envelopes[-1]
            last["to"] = max(date.fromisoformat(last["to"]), end).isoformat()
            last["range_ids"].append(w["range_id"])
        else:
            envelopes.append({"from": start.isoformat(), "to": end.isoformat(), "range_ids": [w["range_id"]]})
    return envelopes


def split_window(window: dict[str, str], parts: int) -> list[dict[str, str]]:
    """Contiguous, non-overlapping windows covering the window exactly (same rule as the Governor)."""
    start, end = date.fromisoformat(window["from"]), date.fromisoformat(window["to"])
    days = (end - start).days + 1
    parts = max(1, min(parts, days))
    size = math.ceil(days / parts)
    out, cursor = [], start
    while cursor <= end:
        stop = min(end, cursor + timedelta(days=size - 1))
        out.append({"from": cursor.isoformat(), "to": stop.isoformat()})
        cursor = stop + timedelta(days=1)
    return out


def split_entities(partition: dict[str, int] | None, parts: int) -> list[dict[str, int]]:
    """Refine an entity partition into `parts` disjoint pieces that together equal it."""
    modulus, remainder = (partition["modulus"], partition["remainder"]) if partition else (1, 0)
    refined = modulus * parts
    if refined > MAX_MODULUS:
        raise ValueError("entity partition too fine")
    return [{"modulus": refined, "remainder": remainder + modulus * j} for j in range(parts)]


@dataclass
class Part:
    window: dict[str, str] | None
    entity_partition: dict[str, int] | None
    envelope: dict[str, Any] | None
    dataset: dict[str, Any] | None = None


class PlanStop(Exception):
    def __init__(self, outcome: dict[str, Any]) -> None:
        super().__init__(outcome.get("code"))
        self.outcome = outcome


def extraction_spec(entry: dict[str, Any], part: Part) -> dict[str, Any]:
    return {"extraction_version": "extraction_spec/v1", "data_request_id": entry["data_request_id"],
            "source_table": entry["source_table"], "columns": list(entry["extract_columns"]),
            "scope": entry["scope"], "restrictions": [dict(r) for r in entry.get("restrictions") or []],
            "window": part.window, "entity_partition": part.entity_partition,
            "order_by": [dict(o) for o in entry.get("ordering") or []]}


class ExecutionPlanner:
    def __init__(self, sandbox: Any, governor: Any, max_parts: int = MAX_PARTS_PER_REQUEST) -> None:
        self.sandbox = sandbox
        self.governor = governor
        self.max_parts = max_parts

    def prepare(self, need_id: str) -> dict[str, Any]:
        request_id = current_request_id.get() or ""
        need = self.sandbox.get_need(need_id)
        if need is None or need.get("request_id") != request_id:
            return {"status": "REJECTED", "code": "NEED_NOT_FOUND", "next_action": "SUBMIT_DATA_NEED_SPEC",
                    "message": "No approved data need with this need_id exists for this request."}
        plan_id = f"plan_{secrets.token_hex(12)}"
        planned, decisions = [], []
        try:
            for rid in sorted(need["requests"]):
                entry = need["requests"][rid]
                parts, envelopes = self._request_parts(need, plan_id, entry)
                planned.append({"data_request_id": rid, "envelopes": envelopes, "parts": parts})
                decisions += self._decisions(entry, envelopes, parts)
        except PlanStop as stop:
            return {**stop.outcome, "need_id": need_id, "plan_id": plan_id,
                    "extracted_requests": [p["data_request_id"] for p in planned]}
        bundle = self.sandbox.build_bundle(request_id, need_id, {"plan_id": plan_id, "requests": planned,
                                                                 "decisions": decisions})
        bundle["plan"] = {"plan_id": plan_id, "requests": [
            {"data_request_id": p["data_request_id"], "envelopes": len(p["envelopes"]) or None,
             "partitions": len(p["parts"])} for p in planned],
            "decisions": sorted({d["kind"] for d in decisions})}
        return bundle

    def _request_parts(self, need: dict[str, Any], plan_id: str, entry: dict[str, Any]
                       ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rid = entry["data_request_id"]
        envelopes = merge_windows(entry.get("windows") or []) if entry.get("time_column") else []
        done: list[Part] = []
        for envelope in envelopes or [None]:
            queue = [Part({"from": envelope["from"], "to": envelope["to"]} if envelope else None, None, envelope)]
            while queue:
                part = queue.pop(0)
                total = len(done) + len(queue) + 1
                spec = extraction_spec(entry, part)
                lineage = {"need_id": need["need_id"], "spec_sha256": need["spec_sha256"],
                           "request_group_id": need["request_group_id"], "revision": need["revision"],
                           "data_request_id": rid, "logical_name": entry["logical_name"],
                           "scope_sha256": entry["scope_sha256"], "restriction_sha256": entry["restriction_sha256"],
                           "plan_id": plan_id, "part_key": part_key(part.window, part.entity_partition),
                           "envelope": part.envelope, "catalog_sha256": need.get("catalog_sha256"),
                           "extraction_sha256": sha256_json(spec)}
                response = self.governor.extract(spec, lineage, planned_parts=total)
                status = response.get("status")
                if status == "APPROVED":
                    part.dataset = response.get("dataset") or {}
                    done.append(part)
                elif status == "APPROVED_WITH_PARTITIONING":
                    queue = self._split(rid, part, response, total) + queue
                else:
                    raise PlanStop(self._rejection(rid, response, total))
        return self._name(rid, done), envelopes

    def _split(self, rid: str, part: Part, response: dict[str, Any], total: int) -> list[Part]:
        how = response.get("partitioning") or {}
        pieces = int(how.get("parts") or 2)
        if total - 1 + pieces > self.max_parts:
            raise PlanStop(self._rejection(rid, {**response, "status": "REJECTED_ROW_LIMIT"}, total))
        try:
            if how.get("kind") == "DATE" and part.window is not None:
                return [Part(w, part.entity_partition, part.envelope) for w in split_window(part.window, pieces)]
            return [Part(part.window, p, part.envelope) for p in split_entities(part.entity_partition, pieces)]
        except ValueError:
            raise PlanStop(self._rejection(rid, {**response, "status": "REJECTED_ROW_LIMIT"}, total)) from None

    @staticmethod
    def _name(rid: str, parts: list[Part]) -> list[dict[str, Any]]:
        """Deterministic partition ids: per envelope, by window start, then entity residue."""
        groups: dict[str, list[Part]] = {}
        for part in parts:
            env = part.envelope
            prefix = f"{rid}__static" if env is None else (
                f"{rid}__{env['range_ids'][0]}" if len(env["range_ids"]) == 1 else rid)
            groups.setdefault(prefix, []).append(part)
        named = []
        for prefix, members in groups.items():
            members.sort(key=lambda p: ((p.window or {}).get("from") or "",
                                        (p.entity_partition or {}).get("modulus", 1),
                                        (p.entity_partition or {}).get("remainder", 0)))
            for index, part in enumerate(members, start=1):
                named.append({"partition_id": f"{prefix}__part_{index:03d}", "dataset_id": part.dataset["dataset_id"],
                              "part_key": part_key(part.window, part.entity_partition), "window": part.window,
                              "entity_partition": part.entity_partition})
        return named

    @staticmethod
    def _decisions(entry: dict[str, Any], envelopes: list[dict[str, Any]], parts: list[dict[str, Any]]
                   ) -> list[dict[str, Any]]:
        rid = entry["data_request_id"]
        out = [{"data_request_id": rid, "kind": "COLUMN_PRUNING",
                "detail": f"{len(entry['extract_columns'])} columns (requested plus key columns)"}]
        if entry["scope"].get("type") != "ALL":
            out.append({"data_request_id": rid, "kind": "PREDICATE_PUSHDOWN", "detail": "scope tree compiled to SQL"})
        for r in entry.get("restrictions") or []:
            out.append({"data_request_id": rid, "kind": "SEMI_JOIN_PUSHDOWN",
                        "detail": f"relationship {r['relationship_id']} {r['join_semantics']}"})
        windows = entry.get("windows") or []
        if envelopes and len(envelopes) < len(windows):
            out.append({"data_request_id": rid, "kind": "RANGE_MERGE",
                        "detail": f"{len(windows)} ranges in {len(envelopes)} extraction envelopes"})
        dated = [p for p in parts if p["window"] is not None]
        if len(dated) > max(1, len(envelopes)):
            out.append({"data_request_id": rid, "kind": "DATE_PARTITION", "detail": f"{len(parts)} partitions"})
        if any(p["entity_partition"] for p in parts):
            out.append({"data_request_id": rid, "kind": "ENTITY_PARTITION", "detail": f"{len(parts)} partitions"})
        if entry.get("resample"):
            out.append({"data_request_id": rid, "kind": "RESAMPLE_IN_SESSION",
                        "detail": f"delivered at {entry['source_frequency']}; resample to "
                                  f"{entry['analysis_frequency']} in the session"})
        return out

    @staticmethod
    def _rejection(rid: str, response: dict[str, Any], parts: int) -> dict[str, Any]:
        status = response.get("status") or "REJECTED_POLICY"
        policy = status == "REJECTED_POLICY"
        return {"status": "REJECTED", "stage": "SQL_GOVERNOR", "governor_status": status,
                "data_request_id": rid, "code": response.get("code"),
                "message": str(response.get("message") or "")[:400],
                "next_action": response.get("next_action") or (
                    "REVISE_DATA_NEED_SPEC" if policy else "REPLAN_OR_REVISE_DATA_NEED_SPEC"),
                "estimates": response.get("estimates"), "partitions_tried": parts,
                "allowed_actions": ["REVISE_DATA_NEED_SPEC_FROM_CATALOG"] if policy else [
                    "REPORT_LIMITATION", "ASK_USER_TO_NARROW_THE_SCOPE", "REVISE_DATA_NEED_SPEC"],
                "forbidden_actions": FORBIDDEN_ACTIONS}


PREPARE_BUNDLE_DESCRIPTION = (
    "Extract and deliver the data of an APPROVED DataNeedSpec as one governed data bundle. The backend plans the "
    "physical extractions (column pruning, scope and join pushdown, merged or separate range windows, date or entity "
    "partitions) and the SQL Governor checks and extracts each part; nothing is sampled, truncated or re-scoped. The "
    "sandbox verifies every part, profiles the data and checks coverage. Returns READY with input_bundle_id and, per "
    "data request, rows, entities, first/last date, each requested range with its actual bounds and status "
    "(OK, PARTIAL, EMPTY), quality_flags (e.g. NULL_VALUES, FREQUENCY_GAPS, HISTORY_BUFFER_SHORTFALL, EMPTY_ENTITY, "
    "DUPLICATE_KEYS) and relationship warnings; or REJECTED naming the data_request_id, the reason code and the next "
    "action. Quality flags are facts about the data to investigate and disclose, not failures. Never change the "
    "user's scope to pass a limit: revise the DataNeedSpec only when the rejection says so."
)


def prepare_bundle_spec(planner: ExecutionPlanner, *, timeout_seconds: float, max_result_bytes: int) -> ToolSpec:
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, PrepareDataBundleArgs)
        return planner.prepare(arguments.need_id)

    return ToolSpec(name="prepare_data_bundle", description=PREPARE_BUNDLE_DESCRIPTION,
                    arguments_model=PrepareDataBundleArgs, handler=handler, timeout_seconds=timeout_seconds,
                    max_result_bytes=max_result_bytes)


__all__ = ["ExecutionPlanner", "PrepareDataBundleArgs", "merge_windows", "part_key", "prepare_bundle_spec",
           "split_entities", "split_window"]
