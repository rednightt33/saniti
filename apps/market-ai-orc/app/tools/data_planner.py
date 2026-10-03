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

import contextvars
import hashlib
import json
import math
import secrets
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .registry import ToolError, ToolSpec
from .analysis import current_conversation_key, current_run_context
from .request_data import current_request_id

NEED_ID_PATTERN = r"^need_[0-9a-f]{24}$"
MAX_PARTS_PER_REQUEST = 64
# A0 (AI_ENABLE_PREFLIGHT_PARTS): the date-part counts tried for one envelope, fewest first. The planner cost is not
# monotonic in the window (A4, 2026-09-29: broker x banks cost 40k for a day, 228k for a week, 37k for a month), so a
# finer split is not assumed to be cheaper: each count is estimated part by part and the first that fits is used.
PREFLIGHT_COUNTS = (2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64)
PREFLIGHT_MAX_ESTIMATES = 256
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


class PlanBudget:
    """One plan's budgets: the preflight estimates left, and (G14) the bundle's row limit spent part by part. The rows
    of a window add up to the same total however it is split, so a running total above the limit means the data
    cannot fit one bundle, before or during extraction. Per call, never shared between requests."""

    def __init__(self, max_rows: int | None = None, estimates: int = PREFLIGHT_MAX_ESTIMATES) -> None:
        self.estimates = estimates
        self.max_rows = max_rows or None
        self.rows = 0
        self.by_request: dict[str, int] = {}
        self.basis: set[str] = set()

    def over(self, extra: int) -> bool:
        return self.max_rows is not None and self.rows + extra > self.max_rows

    def spend(self, rid: str, rows: int) -> None:
        self.rows += rows
        self.by_request[rid] = self.by_request.get(rid, 0) + rows

    def count_cap(self) -> int | None:
        """G15: the Governor's count of a part need not go past one row over what the bundle can still hold."""
        return None if self.max_rows is None else max(0, self.max_rows - self.rows) + 1


def summary_hint(need: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    """G18: a data need too large for one bundle names the raw ANALYSIS requests whose columns add up across entities
    (the approved aggregation_rules, from the catalog), so the next step can be a warehouse summary instead of a
    narrower question."""
    if outcome.get("code") != "BUNDLE_TOO_LARGE" or need.get("mode") != "ANALYSIS":
        return {}
    found = {rid: sorted(c for c, rule in (entry.get("aggregation_rules") or {}).items() if rule == "SUM")
             for rid, entry in (need.get("requests") or {}).items() if not entry.get("aggregate")}
    found = {rid: columns for rid, columns in found.items() if columns}
    if not found:
        return {}
    return {"summary_available": found,
            "summary_note": ("These requests have columns that add up across entities: when the answer needs totals "
                             "or counts per group, resubmit the request with an aggregate (group_by keeps the time "
                             "column) and the warehouse returns one row per group instead of every raw row."),
            "allowed_actions": ["REVISE_DATA_NEED_SPEC_WITH_AGGREGATE", *outcome.get("allowed_actions", [])]}


def extraction_spec(entry: dict[str, Any], part: Part) -> dict[str, Any]:
    return {"extraction_version": "extraction_spec/v1", "data_request_id": entry["data_request_id"],
            "source_table": entry["source_table"], "columns": list(entry["extract_columns"]),
            "scope": entry["scope"], "restrictions": [dict(r) for r in entry.get("restrictions") or []],
            "window": part.window, "entity_partition": part.entity_partition,
            "order_by": [dict(o) for o in entry.get("ordering") or []],
            # G18: a summary the warehouse computes (absent for raw rows, so their spec and hashes are unchanged)
            **({"aggregate": entry["aggregate"]} if entry.get("aggregate") else {})}


class ExecutionPlanner:
    def __init__(self, sandbox: Any, governor: Any, max_parts: int = MAX_PARTS_PER_REQUEST,
                 preflight: bool = False, limits: dict[str, Any] | None = None, parallel_parts: int = 1) -> None:
        self.sandbox = sandbox
        self.governor = governor
        self.max_parts = max_parts
        # A0/A2 (AI_ENABLE_PREFLIGHT_PARTS): every part is estimated before the first extraction
        self.preflight = preflight
        # G14: the sandbox's bundle row limit (GET /v1/runtime limits); None keeps the check to the sandbox alone
        self.max_bundle_rows = int((limits or {}).get("bundle_max_rows") or 0) or None
        # G15 (AI_PLANNER_PARALLEL_PARTS): chosen parts extracted at the same time; 1 = one after the other
        self.parallel_parts = max(1, int(parallel_parts or 1))

    def prepare(self, need_id: str) -> dict[str, Any]:
        request_id = current_request_id.get() or ""
        need = self.sandbox.get_need(need_id)
        if need is None or need.get("request_id") != request_id:
            return {"status": "REJECTED", "code": "NEED_NOT_FOUND", "next_action": "SUBMIT_DATA_NEED_SPEC",
                    "message": "No approved data need with this need_id exists for this request."}
        if current_conversation_key.get() and hasattr(self.sandbox, "reuse_bundle"):
            # conversation reuse (S1): an earlier bundle of this conversation with exactly the same data contract
            reused = self.sandbox.reuse_bundle(request_id, need_id)
            if reused is not None:
                return {**reused, "plan": {"reused": True, "extractions": 0}}
        plan_id = f"plan_{secrets.token_hex(12)}"
        planned, decisions = [], []
        try:
            chosen: dict[str, list[Part]] = {}
            if self.preflight:
                # A2: every part of every request fits by estimate before any row is read; G14: and all of them
                # together fit one bundle
                budget = PlanBudget(self.max_bundle_rows)
                for rid in sorted(need["requests"]):
                    chosen[rid] = self._preflight(need, plan_id, need["requests"][rid], budget)[0]
            extracted = PlanBudget(self.max_bundle_rows)  # G14: real rows, for parts whose count was uncertain
            for rid in sorted(need["requests"]):
                entry = need["requests"][rid]
                parts, envelopes = self._extract_chosen(need, plan_id, entry, chosen[rid], extracted) \
                    if self.preflight else self._request_parts(need, plan_id, entry, extracted)
                planned.append({"data_request_id": rid, "envelopes": envelopes, "parts": parts})
                decisions += self._decisions(entry, envelopes, parts)
        except PlanStop as stop:
            return {**stop.outcome, **summary_hint(need, stop.outcome), "need_id": need_id, "plan_id": plan_id,
                    "extracted_requests": [p["data_request_id"] for p in planned]}
        bundle = self.sandbox.build_bundle(request_id, need_id, {"plan_id": plan_id, "requests": planned,
                                                                 "decisions": decisions})
        bundle["plan"] = {"plan_id": plan_id, "requests": [
            {"data_request_id": p["data_request_id"], "envelopes": len(p["envelopes"]) or None,
             "partitions": len(p["parts"])} for p in planned],
            "decisions": sorted({d["kind"] for d in decisions})}
        return bundle

    def estimate(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Research Plan feasibility: every extraction envelope of a validated draft goes to the Governor as an
        estimate-only extraction (its checks and EXPLAIN, no rows read). Feasible when every envelope is WITHIN_LIMITS
        or needs a partitioning whose parts fit the per-request budget; a REJECTED_* status names the request."""
        plan_id = f"plan_{secrets.token_hex(12)}"
        requests, feasible = [], True
        if self.preflight:
            return self._estimate_parts(draft, plan_id)
        for rid in sorted(draft["requests"]):
            entry = draft["requests"][rid]
            self._bases = []
            envelopes = merge_windows(entry.get("windows") or []) if entry.get("time_column") else []
            summary: dict[str, Any] = {"data_request_id": rid, "source_table": entry["source_table"],
                                       "envelopes": len(envelopes) or None, "estimated_rows": 0,
                                       "extraction_parts": 0, "governor_status": "WITHIN_LIMITS"}
            for envelope in envelopes or [None]:
                part = Part({"from": envelope["from"], "to": envelope["to"]} if envelope else None, None, envelope)
                spec = extraction_spec(entry, part)
                lineage = {"need_id": draft["need_id"], "spec_sha256": draft["spec_sha256"],
                           "request_group_id": draft["request_group_id"], "revision": draft["revision"],
                           "data_request_id": rid, "logical_name": entry["logical_name"],
                           "scope_sha256": entry["scope_sha256"], "restriction_sha256": entry["restriction_sha256"],
                           "plan_id": plan_id, "part_key": part_key(part.window, part.entity_partition),
                           "envelope": part.envelope, "catalog_sha256": draft.get("catalog_sha256"),
                           "extraction_sha256": sha256_json(spec)}
                response = self.governor.extract(spec, lineage, planned_parts=1, estimate_only=True)
                self._note_basis(response)
                status = response.get("status")
                rows = (response.get("estimates") or {}).get("result_rows") or 0
                summary["estimated_rows"] += int(rows)
                if status == "WITHIN_LIMITS":
                    summary["extraction_parts"] += 1
                elif status == "APPROVED_WITH_PARTITIONING":
                    summary["extraction_parts"] += int((response.get("partitioning") or {}).get("parts") or 2)
                    summary["governor_status"] = "NEEDS_PARTITIONING"
                else:
                    feasible = False
                    summary.update(governor_status=status or "REJECTED_POLICY", code=response.get("code"),
                                   message=str(response.get("message") or "")[:400])
                    break
            self._set_basis(summary)
            if summary["extraction_parts"] > self.max_parts:
                feasible = False
                summary.update(governor_status="REJECTED_ROW_LIMIT", code="TOO_MANY_PARTS",
                               message=f"The data would need {summary['extraction_parts']} extraction parts; at most "
                                       f"{self.max_parts} fit one request.")
            requests.append(summary)
        return {"feasible": feasible, "requests": requests}

    def _estimate_parts(self, draft: dict[str, Any], plan_id: str) -> dict[str, Any]:
        """A0 feasibility: the same part-by-part estimate the extraction will use, so FEASIBLE means every part fits
        (G10: the envelope estimate alone approved plans whose parts the Governor then refused)."""
        # no row limit here: a feasibility check reports every request's rows and its caller judges the total
        requests, feasible, budget = [], True, PlanBudget()
        for rid in sorted(draft["requests"]):
            entry = draft["requests"][rid]
            envelopes = merge_windows(entry.get("windows") or []) if entry.get("time_column") else []
            summary: dict[str, Any] = {"data_request_id": rid, "source_table": entry["source_table"],
                                       "envelopes": len(envelopes) or None, "estimated_rows": 0,
                                       "extraction_parts": 0, "governor_status": "WITHIN_LIMITS"}
            self._bases = []
            try:
                parts, rows = self._preflight(draft, plan_id, entry, budget)
                summary.update(estimated_rows=rows, extraction_parts=len(parts))
                self._set_basis(summary)
                if len(parts) > max(1, len(envelopes)):
                    summary["governor_status"] = "NEEDS_PARTITIONING"
            except PlanStop as stop:
                feasible = False
                outcome = stop.outcome
                summary.update(governor_status=outcome.get("governor_status") or "REJECTED_POLICY",
                               code=outcome.get("code"), message=outcome.get("message"),
                               **({"failing_window": outcome["failing_window"]} if outcome.get("failing_window")
                                  else {}))
            requests.append(summary)
        return {"feasible": feasible, "requests": requests}

    def _lineage(self, source: dict[str, Any], plan_id: str, entry: dict[str, Any], part: Part,
                 spec: dict[str, Any]) -> dict[str, Any]:
        return {"need_id": source["need_id"], "spec_sha256": source["spec_sha256"],
                "request_group_id": source["request_group_id"], "revision": source["revision"],
                "data_request_id": entry["data_request_id"], "logical_name": entry["logical_name"],
                "scope_sha256": entry["scope_sha256"], "restriction_sha256": entry["restriction_sha256"],
                "plan_id": plan_id, "part_key": part_key(part.window, part.entity_partition),
                "envelope": part.envelope, "catalog_sha256": source.get("catalog_sha256"),
                "extraction_sha256": sha256_json(spec)}

    def _estimate(self, source: dict[str, Any], plan_id: str, entry: dict[str, Any], part: Part, planned: int,
                  budget: PlanBudget) -> dict[str, Any]:
        if budget.estimates <= 0:
            raise PlanStop({**self._rejection(entry["data_request_id"], {
                "status": "REJECTED_TIMEOUT_RISK", "code": "PREFLIGHT_ESTIMATE_BUDGET",
                "message": f"The parts could not be planned within {PREFLIGHT_MAX_ESTIMATES} estimates; narrow the "
                           "period or the universe."}, planned)})
        budget.estimates -= 1
        spec = extraction_spec(entry, part)
        cap = budget.count_cap()
        response = self.governor.extract(spec, self._lineage(source, plan_id, entry, part, spec),
                                         planned_parts=planned, estimate_only=True,
                                         **({"count_cap": cap} if cap is not None else {}))
        self._note_basis(response)
        basis = (response.get("estimates") or {}).get("row_basis")
        if basis and response.get("status") == "WITHIN_LIMITS":
            budget.basis.add(basis)
        return response

    def _note_basis(self, response: dict[str, Any]) -> None:
        """G13: whether the Governor counted a part's rows (COUNTED) or estimated them (PLANNER); absent when its
        counting is off."""
        basis = (response.get("estimates") or {}).get("row_basis")
        if basis and response.get("status") == "WITHIN_LIMITS":
            getattr(self, "_bases", []).append(basis)

    def _set_basis(self, summary: dict[str, Any]) -> None:
        bases = getattr(self, "_bases", [])
        if bases:  # COUNTED only when every part was counted
            summary["row_basis"] = "COUNTED" if all(b == "COUNTED" for b in bases) else "PLANNER"

    def _preflight(self, source: dict[str, Any], plan_id: str, entry: dict[str, Any], budget: PlanBudget
                   ) -> tuple[list[Part], int]:
        """A0: the parts of one request, each estimated WITHIN_LIMITS (EXPLAIN only, no row read), and their estimated
        rows. A dated envelope takes the fewest equal date parts of PREFLIGHT_COUNTS (from the Governor's own count)
        whose every part fits; an entity split, or an envelope without a window, follows the Governor's partitioning
        part by part. The first part that fits nowhere stops the plan with its window and estimates."""
        rid = entry["data_request_id"]
        envelopes = merge_windows(entry.get("windows") or []) if entry.get("time_column") else []
        chosen: list[Part] = []
        rows = 0
        for envelope in envelopes or [None]:
            whole = Part({"from": envelope["from"], "to": envelope["to"]} if envelope else None, None, envelope)
            response = self._estimate(source, plan_id, entry, whole, len(chosen) + 1, budget)
            status = response.get("status")
            if status == "WITHIN_LIMITS":
                found = int((response.get("estimates") or {}).get("result_rows") or 0)
                self._check_bundle(rid, budget, found)
                chosen.append(whole)
                rows += found
                budget.spend(rid, found)
                continue
            if status != "APPROVED_WITH_PARTITIONING":
                raise PlanStop({**self._rejection(rid, response, len(chosen) + 1), "failing_window": whole.window})
            how = response.get("partitioning") or {}
            if how.get("kind") == "DATE" and whole.window is not None:
                parts, found = self._fewest_date_parts(source, plan_id, entry, whole, int(how.get("parts") or 2),
                                                       len(chosen), budget)
            else:
                parts, found = self._governor_parts(source, plan_id, entry, whole, response, len(chosen), budget)
            chosen += parts
            rows += found
            budget.spend(rid, found)
        return chosen, rows

    def _fewest_date_parts(self, source: dict[str, Any], plan_id: str, entry: dict[str, Any], whole: Part,
                           first: int, done: int, budget: PlanBudget) -> tuple[list[Part], int]:
        rid = entry["data_request_id"]
        start, end = date.fromisoformat(whole.window["from"]), date.fromisoformat(whole.window["to"])
        days = (end - start).days + 1
        counts = sorted({n for n in (first, *PREFLIGHT_COUNTS) if first <= n <= days and done + n <= self.max_parts})
        failure: dict[str, Any] | None = None
        for count in counts:
            parts = [Part(w, None, whole.envelope) for w in split_window(whole.window, count)]
            rows, fits = 0, True
            for part in parts:
                response = self._estimate(source, plan_id, entry, part, done + len(parts), budget)
                if response.get("status") != "WITHIN_LIMITS":
                    fits = False
                    failure = {**response, "window": part.window, "parts": count}
                    break
                rows += int((response.get("estimates") or {}).get("result_rows") or 0)
                self._check_bundle(rid, budget, rows)  # this window's rows are the same in any split
            if fits:
                return parts, rows
        if failure is None:  # no count fits the part limit
            failure = {"status": "REJECTED_ROW_LIMIT", "code": "TOO_MANY_PARTS", "window": whole.window,
                       "message": f"The data would need more than {self.max_parts - done} extraction parts."}
        status = failure.get("status")
        if status == "APPROVED_WITH_PARTITIONING":  # the finest split tried still needs splitting
            failure = {**failure, "status": {"COST_LIMIT": "REJECTED_JOIN_COST" if entry.get("restrictions")
                                             else "REJECTED_COMPUTE_COST", "SCAN_LIMIT": "REJECTED_SCAN_SIZE"}.get(
                failure.get("code"), "REJECTED_ROW_LIMIT")}
        raise PlanStop({**self._rejection(rid, failure, failure.get("parts") or len(counts)),
                        "failing_window": failure.get("window")})

    def _governor_parts(self, source: dict[str, Any], plan_id: str, entry: dict[str, Any], whole: Part,
                        response: dict[str, Any], done: int, budget: PlanBudget) -> tuple[list[Part], int]:
        """Entity (or window-less) partitioning as the Governor says, every piece estimated before it is kept."""
        rid = entry["data_request_id"]
        queue, kept, rows = self._split(rid, whole, response, done + 1), [], 0
        while queue:
            part = queue.pop(0)
            total = done + len(kept) + len(queue) + 1
            answer = self._estimate(source, plan_id, entry, part, total, budget)
            status = answer.get("status")
            if status == "WITHIN_LIMITS":
                kept.append(part)
                rows += int((answer.get("estimates") or {}).get("result_rows") or 0)
                self._check_bundle(rid, budget, rows)
            elif status == "APPROVED_WITH_PARTITIONING":
                queue = self._split(rid, part, answer, total) + queue
            else:
                raise PlanStop({**self._rejection(rid, answer, total), "failing_window": part.window})
        return kept, rows

    def _extract_chosen(self, need: dict[str, Any], plan_id: str, entry: dict[str, Any], chosen: list[Part],
                        extracted: PlanBudget | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """A2: extract the parts the preflight chose. The Governor still checks each one; a part whose estimate
        changed in between is split as before. G15: up to parallel_parts parts are extracted at the same time, in
        waves; the answers are taken in part order, so the bundle and every stop are the same as one at a time (a
        stop can leave at most parallel_parts - 1 extra datasets unused, which expire with the Governor's storage)."""
        rid = entry["data_request_id"]
        envelopes = merge_windows(entry.get("windows") or []) if entry.get("time_column") else []
        queue, done = list(chosen), []
        while queue:
            wave, queue = queue[:self.parallel_parts], queue[self.parallel_parts:]
            requeue: list[Part] = []
            for i, (part, response) in enumerate(zip(wave, self._extract_wave(need, plan_id, entry, wave,
                                                                            len(done) + len(wave) + len(queue)))):
                total = len(done) + len(requeue) + len(wave) - i + len(queue)
                status = response.get("status")
                if status == "APPROVED":
                    part.dataset = response.get("dataset") or {}
                    self._spend_extracted(rid, extracted, part.dataset)
                    done.append(part)
                elif status == "APPROVED_WITH_PARTITIONING":
                    requeue += self._split(rid, part, response, total)
                else:
                    raise PlanStop(self._rejection(rid, response, total))
            queue = requeue + queue
        return self._name(rid, done), envelopes

    def _extract_wave(self, need: dict[str, Any], plan_id: str, entry: dict[str, Any], wave: list[Part],
                      total: int) -> list[dict[str, Any]]:
        def one(part: Part) -> dict[str, Any]:
            spec = extraction_spec(entry, part)
            return self.governor.extract(spec, self._lineage(need, plan_id, entry, part, spec), planned_parts=total)

        if len(wave) == 1:
            return [one(wave[0])]
        # each worker runs in a copy of this context: the request id and run context travel with the call
        with ThreadPoolExecutor(max_workers=len(wave), thread_name_prefix="planner-part") as pool:
            futures = [pool.submit(contextvars.copy_context().run, one, part) for part in wave]
            return [future.result() for future in futures]

    def _request_parts(self, need: dict[str, Any], plan_id: str, entry: dict[str, Any],
                       extracted: PlanBudget | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
                    self._spend_extracted(rid, extracted, part.dataset)
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

    def _check_bundle(self, rid: str, budget: PlanBudget, extra: int) -> None:
        """G14: stop before the first extraction once the estimated rows exceed one bundle."""
        if budget.over(extra):
            raise PlanStop(self._too_large(rid, budget.rows + extra, budget, "PREFLIGHT",
                                           {**budget.by_request, rid: budget.by_request.get(rid, 0) + extra}))

    def _spend_extracted(self, rid: str, extracted: PlanBudget | None, dataset: dict[str, Any]) -> None:
        """G14: the real rows of each extracted part; stop at the first part that takes the bundle over its limit."""
        if extracted is None:
            return
        rows = int(dataset.get("row_count") or 0)
        if extracted.over(rows):
            raise PlanStop(self._too_large(rid, extracted.rows + rows, extracted, "EXTRACTION",
                                           {**extracted.by_request, rid: extracted.by_request.get(rid, 0) + rows}))
        extracted.spend(rid, rows)

    @staticmethod
    def _too_large(rid: str, rows: int, budget: PlanBudget, stage: str, by_request: dict[str, int]
                   ) -> dict[str, Any]:
        counted = bool(budget.basis) and budget.basis <= {"COUNTED", "AT_LEAST"}  # G15: AT_LEAST is a bounded count
        basis = "counted" if counted else "estimated" if stage == "PREFLIGHT" else "extracted"
        return {"status": "REJECTED", "stage": stage, "code": "BUNDLE_TOO_LARGE", "data_request_id": rid,
                "message": (f"The data of this need holds at least {rows} rows ({basis}) and one bundle holds at "
                            f"most {budget.max_rows}; " + ("nothing was extracted. " if stage == "PREFLIGHT" else
                                                           "extraction stopped at that part. ")
                            + "Revise the DataNeedSpec (scope, ranges or columns) within the user's question, or "
                              "report the limitation.")[:400],
                "next_action": "REVISE_DATA_NEED_SPEC",
                "details": {"rows_at_least": rows, "limit_rows": budget.max_rows, "rows_by_request": by_request,
                            "row_basis": sorted(budget.basis) or None},
                "allowed_actions": ["REVISE_DATA_NEED_SPEC", "ASK_USER_TO_NARROW_THE_SCOPE", "REPORT_LIMITATION"],
                "forbidden_actions": FORBIDDEN_ACTIONS}

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
                **({"window": response["window"]} if response.get("window") else {}),
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


CHECK_FEASIBILITY_DESCRIPTION = (
    "Before presenting a Research Plan, check that its data exists, joins and fits: send the DataNeedSpec the plan "
    "will need (the same fields as submit_data_need_spec, without research_governance). The validator checks tables, "
    "columns, scopes, periods and catalog relationships, and the SQL Governor estimates each extraction without "
    "reading data. Returns FEASIBLE with draft_id and, per data request, the estimated rows and extraction parts; "
    "NOT_FEASIBLE naming the request whose data is too large or refused (narrow the period or universe, or report "
    "the limitation with alternatives); or REVISION_REQUIRED with issues (fix them, or report that the catalog "
    "offers no path, for example no documented relationship between two tables). Nothing is extracted and no "
    "revision is consumed. A Research Plan is presented only after a FEASIBLE check."
)


def empty_requests(draft: dict[str, Any], estimate: dict[str, Any]) -> list[dict[str, Any]]:
    """G19 (2026-10-03): the requests the Governor COUNTED at 0 rows. A counted 0 is not an estimate: the request's
    scope, or its restriction to another request, matches no data (g5 turns 5-8: BUMN AND NOT BUMN), so a plan built
    on it would run on nothing. One issue per request, with its table, scope and restrictions in readable form."""
    from ..data_record import scope_text

    issues = []
    for request in estimate.get("requests") or []:
        if request.get("row_basis") != "COUNTED" or int(request.get("estimated_rows") or 0) != 0:
            continue
        entry = (draft.get("requests") or {}).get(request["data_request_id"]) or {}
        restrictions = [f"{r.get('right_table')}: {scope_text(r.get('right_scope'))}"
                        for r in entry.get("restrictions") or [] if isinstance(r, dict)]
        issues.append({
            "code": "EMPTY_REQUEST", "data_request_id": request["data_request_id"],
            "source_table": request.get("source_table"), "scope": scope_text(entry.get("scope")),
            "restrictions": restrictions,
            "message": "Counted at 0 rows: its scope or its restriction to another request matches no data. Check the "
                       "stored values (get_dimension_values) and that the requests of different groups are not "
                       "restricted to each other's groups. When no data is the answer (for example a broker that never "
                       "traded these stocks), report it as a finding instead of an angle or experiment."})
    return issues


def check_feasibility(client: Any, planner: ExecutionPlanner, arguments: BaseModel) -> dict[str, Any]:
    context = current_run_context.get()
    if context is None:
        raise ToolError("No user request is available to anchor the data need's reference date.")
    body = {"request_id": client._request_id(), "reference_time": context.reference_time.isoformat(),
            "timezone": context.timezone, "spec": arguments.model_dump(mode="json")}
    checked = client.check_data_need(body)
    if checked.get("status") != "APPROVED" or not checked.get("draft_id"):
        return {"status": checked.get("status") or "REJECTED", "draft_id": None,
                "issues": checked.get("issues") or [], "warnings": checked.get("warnings") or [],
                **({"error": checked["error"]} if checked.get("error") else {}),
                "next_action": "REVISE_DATA_NEED_SPEC_OR_REPORT_LIMITATION"}
    draft = client.get_draft(checked["draft_id"])
    if draft is None:
        raise ToolError("The feasibility draft could not be read back from the Python sandbox.")
    estimate = planner.estimate(draft)
    # G14: every request may fit on its own while all of them together exceed one bundle
    total = sum(int(r.get("estimated_rows") or 0) for r in estimate["requests"])
    limit = planner.max_bundle_rows
    too_large = limit is not None and total > limit
    feasible = estimate["feasible"] and not too_large
    empty = empty_requests(draft, estimate) if feasible else []
    if empty:
        return {"status": "REVISION_REQUIRED", "draft_id": None, "requests": estimate["requests"],
                "issues": empty, "warnings": checked.get("warnings") or [],
                "next_action": "REVISE_DATA_NEED_SPEC_OR_REPORT_LIMITATION"}
    return {"status": "FEASIBLE" if feasible else "NOT_FEASIBLE", "draft_id": checked["draft_id"],
            "requests": estimate["requests"], "warnings": checked.get("warnings") or [],
            **({"bundle": {"code": "BUNDLE_TOO_LARGE", "estimated_rows": total, "limit_rows": limit,
                           "message": f"Together the requests need about {total} rows; one bundle holds at most "
                                      f"{limit}."}} if too_large else {}),
            "next_action": "PRESENT_RESEARCH_PLAN" if feasible else "NARROW_THE_PLAN_OR_REPORT_LIMITATION"}


def feasibility_spec(client: Any, planner: ExecutionPlanner, *, timeout_seconds: float,
                     max_result_bytes: int, composite_keys: bool = False, point_in_time: bool = False) -> ToolSpec:
    from .data_need import (CheckDataFeasibilityArgs, CheckDataFeasibilityArgsPIT, CheckDataFeasibilityArgsV2,
                            argument_issues)

    model = (CheckDataFeasibilityArgsPIT if point_in_time else CheckDataFeasibilityArgsV2) if composite_keys \
        else CheckDataFeasibilityArgs

    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, (CheckDataFeasibilityArgs, CheckDataFeasibilityArgsV2,
                                      CheckDataFeasibilityArgsPIT))
        return check_feasibility(client, planner, arguments)

    return ToolSpec(name="check_data_feasibility", description=CHECK_FEASIBILITY_DESCRIPTION,
                    arguments_model=model, handler=handler, timeout_seconds=timeout_seconds,
                    max_result_bytes=max_result_bytes, argument_errors=argument_issues,
                    envelope_key="data_need_spec")


def prepare_bundle_spec(planner: ExecutionPlanner, *, timeout_seconds: float, max_result_bytes: int) -> ToolSpec:
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, PrepareDataBundleArgs)
        return planner.prepare(arguments.need_id)

    return ToolSpec(name="prepare_data_bundle", description=PREPARE_BUNDLE_DESCRIPTION,
                    arguments_model=PrepareDataBundleArgs, handler=handler, timeout_seconds=timeout_seconds,
                    max_result_bytes=max_result_bytes)


__all__ = ["ExecutionPlanner", "PrepareDataBundleArgs", "feasibility_spec", "merge_windows", "part_key", "prepare_bundle_spec",
           "split_entities", "split_window"]
