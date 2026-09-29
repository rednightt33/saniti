"""Multi-Angle Research data planning (AI_ENABLE_MULTI_ANGLE_RESEARCH): check_research_feasibility.

Each angle of a v2 Research Plan declares its own data requirement (DataNeedSpec v2 requests and relationships in the
angle's own ids). The planner, deterministically:

1. normalizes each request to a key (table, entity and time columns, canonical scope, frequencies, resample and its
   INNER restrictions with their own keys; ranges, columns, buffers and ordering are not part of the key) and merges
   equal keys across angles: columns united, ranges united by dates, buffers widened to the larger span;
2. tries one bundle group (one DataNeedSpec, one session); when the merged spec has more requests than a DataNeedSpec
   holds or its estimate exceeds the sandbox bundle limits, packs the angles in plan order into groups (never
   splitting an angle), up to AI_RESEARCH_MAX_BUNDLE_GROUPS;
3. validates every group with the sandbox (a feasibility draft) and estimates it with the Execution Planner, so a
   FEASIBLE group is one whose parts the Governor accepts;
4. returns research_data_plan/v1: the strategy (SINGLE_BUNDLE, MULTI_BUNDLE or INFEASIBLE), the groups with their
   drafts and spec hashes, the angle to group mapping, the per-angle requirements and merge decisions, every angle's
   angle_data_contract/v1 (the datasets, columns and ranges it may use) and the plan hash.

Nothing is extracted and no revision is consumed. The full data plan stays with the orchestrator (it is bound to the
plan's rpc2 continuation); the model sees a compact view.
"""
from __future__ import annotations

import copy
import string
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..research_plan_v2 import CONTRACT_VERSION, DATA_PLAN_VERSION, contract_sha256, data_plan_sha256, sha256_json
from .analysis import current_run_context
from .data_need import DataRequest, RelationshipV2, Subject, argument_issues
from .registry import ToolError, ToolSpec

MAX_REQUESTS_PER_SPEC = 8
MAX_RELATIONSHIPS_PER_SPEC = 8
IDENTIFIER = r"^[a-z][a-z0-9_]{0,39}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AngleRequirement(Strict):
    angle_id: str = Field(description="The angle_id the Research Plan will use for this angle.")
    data_requests: list[DataRequest] = Field(description="1-8 requests this angle reads, in this angle's own ids "
                                                         "(for example angle_one_A); the backend merges equal "
                                                         "requests of different angles.")
    relationships: list[RelationshipV2] = Field(description="Catalog relationships between this angle's requests "
                                                            "([] for none).")


class ResearchFeasibilityArgs(Strict):
    spec_version: Literal["data_need_spec/v2"]
    question: str = Field(description="The user's question, restated.")
    subject: Subject
    angles: list[AngleRequirement] = Field(description="One data requirement per angle of the planned Research Plan.")


TIME_BASIS = Literal["HISTORICAL_DESCRIPTIVE", "POINT_IN_TIME"]


class ResearchFeasibilityArgsPIT(ResearchFeasibilityArgs):
    time_basis: TIME_BASIS = Field(description="HISTORICAL_DESCRIPTIVE (normal) or POINT_IN_TIME (as known then).")


def _calendar_days(buffer: dict[str, Any] | None) -> int:
    if not buffer:
        return 0
    value = int(buffer.get("value") or 0)
    if buffer.get("unit") == "TRADING_OBSERVATIONS":
        return 0 if value <= 0 else -(-(value * 7 * 11) // 50) + 10  # the sandbox's conservative rule
    return value


def _wider(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any] | None:
    if not a or not b:
        return copy.deepcopy(a or b)
    if a.get("unit") == b.get("unit"):
        return {"value": max(int(a["value"]), int(b["value"])), "unit": a["unit"]}
    return {"value": max(_calendar_days(a), _calendar_days(b)), "unit": "CALENDAR_DAYS"}


class ResearchDataPlanner:
    def __init__(self, client: Any, planner: Any, *, max_groups: int = 3, min_angles: int = 3, max_angles: int = 6,
                 limits: dict[str, Any] | None = None) -> None:
        self.client = client
        self.planner = planner
        self.max_groups = max_groups
        self.min_angles = min_angles
        self.max_angles = max_angles
        limits = limits or {}
        self.max_rows = int(limits.get("bundle_max_rows") or 2_000_000)
        self.max_parts = int(limits.get("bundle_max_parts") or 128)
        self.max_requests = min(int(limits.get("max_requests_per_spec") or MAX_REQUESTS_PER_SPEC),
                                MAX_REQUESTS_PER_SPEC)

    # ------------------------------------------------------------------------------------------ structure

    def _structure(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []

        def add(angle_id: Any, code: str, path: str, value: Any) -> None:
            issues.append({"angle_id": angle_id, "data_request_id": None, "code": code, "field_path": path,
                           "rejected_value": value if not isinstance(value, (dict, list)) else str(value)[:200]})

        import re

        angles = args["angles"]
        if not self.min_angles <= len(angles) <= self.max_angles:
            add(None, "ANGLE_COUNT_INVALID", "angles", len(angles))
        seen = set()
        for index, angle in enumerate(angles):
            angle_id = angle["angle_id"]
            if not re.fullmatch(IDENTIFIER, angle_id) or angle_id in seen:
                add(angle_id, "INVALID_ANGLE_ID", f"angles[{index}].angle_id", angle_id)
            seen.add(angle_id)
            requests = angle["data_requests"]
            if not 1 <= len(requests) <= MAX_REQUESTS_PER_SPEC:
                add(angle_id, "REQUEST_COUNT_INVALID", f"angles[{index}].data_requests", len(requests))
            ids = [r["data_request_id"] for r in requests]
            if len(set(ids)) != len(ids):
                add(angle_id, "DUPLICATE_REQUEST_ID", f"angles[{index}].data_requests", ids)
            for r_index, request in enumerate(requests):
                if request.get("sampling_allowed"):
                    add(angle_id, "SAMPLING_NOT_ALLOWED", f"angles[{index}].data_requests[{r_index}].sampling_allowed",
                        True)
            for r_index, rel in enumerate(angle["relationships"]):
                for side in ("left_request_id", "right_request_id"):
                    if rel[side] not in ids:
                        add(angle_id, "UNKNOWN_REQUEST", f"angles[{index}].relationships[{r_index}].{side}",
                            rel[side])
        return issues

    # ------------------------------------------------------------------------------------------ merge

    @staticmethod
    def _key(angle: dict[str, Any], local_id: str, stack: tuple[str, ...] = ()) -> str:
        request = next(r for r in angle["data_requests"] if r["data_request_id"] == local_id)
        restrictions = []
        if local_id not in stack:
            for rel in angle["relationships"]:
                if rel["left_request_id"] == local_id and rel["join_type"] == "INNER":
                    restrictions.append({k: rel[k] for k in rel if k not in ("left_request_id", "right_request_id")}
                                        | {"right": ResearchDataPlanner._key(angle, rel["right_request_id"],
                                                                             stack + (local_id,))})
        return sha256_json({k: request.get(k) for k in ("source_table", "entity_column", "time_column", "scope",
                                                        "source_frequency", "analysis_frequency", "resample")}
                           | {"restrictions": sorted(restrictions, key=sha256_json)})

    def _merge(self, angles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]],
                                                              list[dict[str, Any]]]:
        """(merged requests in first-seen order, per-angle mapping, merge decisions). A merged request carries the
        union of columns and ranges; each angle keeps its own columns and ranges in its contract."""
        merged: list[dict[str, Any]] = []
        by_key: dict[str, int] = {}
        mapping: dict[str, dict[str, Any]] = {}
        for angle in angles:
            local: dict[str, int] = {}
            for request in angle["data_requests"]:
                key = self._key(angle, request["data_request_id"])
                if key not in by_key:
                    by_key[key] = len(merged)
                    merged.append({"key": key, "base": copy.deepcopy(request), "columns": [], "ranges": [],
                                   "history_buffer": None, "future_buffer": None, "sources": []})
                entry = merged[by_key[key]]
                entry["columns"] = sorted(set(entry["columns"]) | set(request["columns"]))
                entry["history_buffer"] = _wider(entry["history_buffer"], request.get("history_buffer"))
                entry["future_buffer"] = _wider(entry["future_buffer"], request.get("future_buffer"))
                entry["sources"].append({"angle_id": angle["angle_id"], "data_request_id": request["data_request_id"]})
                ranges = {}
                for window in request.get("time_ranges") or []:
                    dates = (window["start"], window["end"])
                    existing = next((r for r in entry["ranges"] if (r["start"], r["end"]) == dates), None)
                    if existing is None:
                        name = window["range_id"]
                        taken = {r["range_id"] for r in entry["ranges"]}
                        suffix = 2
                        while name in taken:
                            name, suffix = f"{window['range_id']}_{suffix}", suffix + 1
                        existing = {"range_id": name, "start": dates[0], "end": dates[1]}
                        entry["ranges"].append(existing)
                    ranges[window["range_id"]] = existing["range_id"]
                local[request["data_request_id"]] = by_key[key]
                mapping.setdefault(angle["angle_id"], {"requests": {}, "ranges": {}, "columns": {}})
                mapping[angle["angle_id"]]["requests"][request["data_request_id"]] = by_key[key]
                mapping[angle["angle_id"]]["ranges"][request["data_request_id"]] = ranges
                mapping[angle["angle_id"]]["columns"][request["data_request_id"]] = list(request["columns"])
        decisions = [{"merged_index": i, "source_table": m["base"]["source_table"],
                      "merged_from": m["sources"], "columns": m["columns"],
                      "ranges": [{"start": r["start"], "end": r["end"]} for r in m["ranges"]]}
                     for i, m in enumerate(merged) if len(m["sources"]) > 1]
        return merged, mapping, decisions

    # ------------------------------------------------------------------------------------------ groups

    @staticmethod
    def _closure(mapping: dict[str, Any], angle_id: str) -> set[int]:
        return set(mapping[angle_id]["requests"].values())

    def _pack(self, order: list[str], mapping: dict[str, Any], rows: dict[int, int]) -> list[list[str]]:
        groups: list[list[str]] = []
        current: list[str] = []
        used: set[int] = set()
        for angle_id in order:
            need = self._closure(mapping, angle_id)
            union = used | need
            too_many = len(union) > self.max_requests
            too_large = sum(rows.get(i, 0) for i in union) > self.max_rows
            if current and (too_many or too_large):
                groups.append(current)
                current, used = [angle_id], set(need)
            else:
                current.append(angle_id)
                used = union
        if current:
            groups.append(current)
        return groups

    def _group_spec(self, args: dict[str, Any], angles: list[dict[str, Any]], merged: list[dict[str, Any]],
                    mapping: dict[str, Any], group_id: str, request_group_id: str, members: list[str]
                    ) -> tuple[dict[str, Any], dict[int, str]]:
        indexes = sorted(set().union(*(self._closure(mapping, a) for a in members)))
        letters = {index: f"{request_group_id}_{string.ascii_uppercase[n]}" for n, index in enumerate(indexes)}
        names: dict[str, int] = {}
        requests = []
        for index in indexes:
            entry = merged[index]
            base = copy.deepcopy(entry["base"])
            name = base["logical_name"]
            if name in names:
                names[name] += 1
                name = f"{name}_{names[name]}"[:40]
            names.setdefault(base["logical_name"], 1)
            base.update(data_request_id=letters[index], logical_name=name, columns=entry["columns"],
                        time_ranges=[{"range_id": r["range_id"], "start": r["start"], "end": r["end"]}
                                     for r in entry["ranges"]],
                        history_buffer=entry["history_buffer"], future_buffer=entry["future_buffer"],
                        sampling_allowed=False)
            requests.append(base)
        relationships, seen = [], set()
        for angle in angles:
            if angle["angle_id"] not in members:
                continue
            local = mapping[angle["angle_id"]]["requests"]
            for rel in angle["relationships"]:
                mapped = {**rel, "left_request_id": letters[local[rel["left_request_id"]]],
                          "right_request_id": letters[local[rel["right_request_id"]]]}
                key = sha256_json(mapped)
                if key not in seen:
                    seen.add(key)
                    relationships.append(mapped)
        spec = {"spec_version": "data_need_spec/v2", "request_group_id": request_group_id, "revision": 1,
                "mode": "RESEARCH", "question": args["question"], "subject": args["subject"],
                "data_requests": requests, "relationships": relationships}
        if args.get("time_basis"):
            spec["time_basis"] = args["time_basis"]
        return spec, letters

    def _check(self, spec: dict[str, Any]) -> dict[str, Any]:
        context = current_run_context.get()
        if context is None:
            raise ToolError("No user request is available to anchor the data need's reference date.")
        body = {"request_id": self.client._request_id(), "reference_time": context.reference_time.isoformat(),
                "timezone": context.timezone, "spec": spec}
        checked = self.client.check_data_need(body)
        if checked.get("status") != "APPROVED" or not checked.get("draft_id"):
            return {"status": checked.get("status") or "REJECTED", "issues": checked.get("issues") or [],
                    "error": checked.get("error")}
        draft = self.client.get_draft(checked["draft_id"])
        if draft is None:
            raise ToolError("The feasibility draft could not be read back from the Python sandbox.")
        estimate = self.planner.estimate(draft)
        rows = sum(int(r.get("estimated_rows") or 0) for r in estimate["requests"])
        parts = sum(int(r.get("extraction_parts") or 0) for r in estimate["requests"])
        return {"status": "APPROVED", "draft": draft, "draft_id": checked["draft_id"], "estimate": estimate,
                "rows": rows, "parts": parts, "warnings": checked.get("warnings") or []}

    # ------------------------------------------------------------------------------------------ plan

    def plan(self, args: dict[str, Any]) -> dict[str, Any]:
        """{status, data_plan (full, or None), view (for the model)}."""
        issues = self._structure(args)
        if issues:
            return self._outcome("REVISION_REQUIRED", None, issues=issues)
        angles = args["angles"]
        order = [a["angle_id"] for a in angles]
        merged, mapping, decisions = self._merge(angles)
        prefix = "mar" + sha256_json(args)[:8]
        rows: dict[int, int] = {}
        attempts: list[dict[str, Any]] = []
        groups = [order] if len({i for a in order for i in self._closure(mapping, a)}) <= self.max_requests \
            else self._pack(order, mapping, rows)
        checked: list[dict[str, Any]] = []
        for _ in range(self.max_groups + 2):
            if len(groups) > self.max_groups:
                return self._outcome("NOT_FEASIBLE", None, strategy="INFEASIBLE", uncovered=order, issues=[{
                    "angle_id": None, "code": "TOO_MANY_BUNDLE_GROUPS",
                    "message": f"The angles need {len(groups)} bundle groups; at most {self.max_groups} run in one "
                               "request. Narrow the data or use fewer angles."}], attempts=attempts)
            checked = []
            repack = False
            for n, members in enumerate(groups, start=1):
                group_id = f"g{n}"
                spec, letters = self._group_spec(args, angles, merged, mapping, group_id, f"{prefix}_g{n}", members)
                result = self._check(spec)
                attempts.append({"bundle_group_id": group_id, "angle_ids": members, "status": result["status"],
                                 "rows": result.get("rows"), "parts": result.get("parts")})
                if result["status"] != "APPROVED":
                    reverse = {v: k for k, v in letters.items()}
                    issues = []
                    for issue in result.get("issues") or []:
                        index = reverse.get(issue.get("data_request_id"))
                        owners = [s for s in (merged[index]["sources"] if index is not None else [])
                                  if s["angle_id"] in members]
                        issues.append({**issue, "angle_ids": sorted({s["angle_id"] for s in owners}) or members,
                                       "angle_request_ids": [s["data_request_id"] for s in owners]})
                    if not issues and result.get("error"):
                        issues.append({"angle_ids": members, "code": (result["error"] or {}).get("code"),
                                       "message": (result["error"] or {}).get("message")})
                    return self._outcome("REVISION_REQUIRED", None, issues=issues, attempts=attempts)
                estimate = result["estimate"]
                refused = [r for r in estimate["requests"] if r.get("governor_status") not in ("WITHIN_LIMITS",
                                                                                               "NEEDS_PARTITIONING")]
                if refused:
                    reverse = {v: k for k, v in letters.items()}
                    uncovered = sorted({s["angle_id"] for r in refused
                                        for s in merged[reverse[r["data_request_id"]]]["sources"]
                                        if s["angle_id"] in members})
                    return self._outcome("NOT_FEASIBLE", None, strategy="INFEASIBLE", uncovered=uncovered,
                                         issues=[{"angle_ids": uncovered, "code": r.get("code"),
                                                  "governor_status": r.get("governor_status"),
                                                  "message": r.get("message"), "source_table": r.get("source_table")}
                                                 for r in refused], attempts=attempts)
                for request in estimate["requests"]:
                    index = {v: k for k, v in letters.items()}.get(request["data_request_id"])
                    if index is not None:
                        rows[index] = max(rows.get(index, 0), int(request.get("estimated_rows") or 0))
                if (result["rows"] > self.max_rows or result["parts"] > self.max_parts) and len(members) > 1:
                    repack = True
                elif result["rows"] > self.max_rows or result["parts"] > self.max_parts:
                    return self._outcome("NOT_FEASIBLE", None, strategy="INFEASIBLE", uncovered=members, issues=[{
                        "angle_ids": members, "code": "ANGLE_EXCEEDS_BUNDLE_LIMITS",
                        "message": f"This angle's data alone needs about {result['rows']} rows in {result['parts']} "
                                   f"parts; one bundle holds {self.max_rows} rows in {self.max_parts} parts."}],
                        attempts=attempts)
                checked.append({"bundle_group_id": group_id, "members": members, "spec": spec, "letters": letters,
                                **result})
            if not repack:
                break
            groups = self._pack(order, mapping, rows)
            if all(len(g) == 1 for g in groups) and len(groups) > self.max_groups:
                continue
        else:
            return self._outcome("NOT_FEASIBLE", None, strategy="INFEASIBLE", uncovered=order, issues=[{
                "angle_ids": order, "code": "NO_BOUNDED_GROUPING",
                "message": "No grouping of the angles fits the bundle limits."}], attempts=attempts)
        data_plan = self._data_plan(args, merged, mapping, decisions, checked)
        return self._outcome("FEASIBLE", data_plan, strategy=data_plan["strategy"], attempts=attempts)

    def _data_plan(self, args: dict[str, Any], merged: list[dict[str, Any]], mapping: dict[str, Any],
                   decisions: list[dict[str, Any]], checked: list[dict[str, Any]]) -> dict[str, Any]:
        groups, contracts, to_group, requirements = [], {}, {}, {}
        for group in checked:
            draft, letters = group["draft"], group["letters"]
            approved = draft["requests"]
            groups.append({"bundle_group_id": group["bundle_group_id"],
                           "request_group_id": group["spec"]["request_group_id"], "angle_ids": group["members"],
                           "draft_id": group["draft_id"], "spec_sha256": sha256_json(group["spec"]),
                           "data_contract_sha256": draft.get("contract_sha256"),
                           "data_request_ids": sorted(letters.values()),
                           "estimates": {"rows": group["rows"], "parts": group["parts"],
                                         "logical_datasets": len(letters),
                                         "requests": [{k: r.get(k) for k in ("data_request_id", "estimated_rows",
                                                                             "extraction_parts", "governor_status")}
                                                      for r in group["estimate"]["requests"]]}})
            for angle_id in group["members"]:
                to_group[angle_id] = group["bundle_group_id"]
                own = mapping[angle_id]
                datasets, local_requests, local_ranges, required = [], {}, {}, []
                for local_id, index in own["requests"].items():
                    bundle_id = letters[index]
                    entry = approved[bundle_id]
                    keys = {entry.get("entity_column"), entry.get("time_column")}
                    ranges = [r for r in merged[index]["ranges"] if r["range_id"] in own["ranges"][local_id].values()]
                    datasets.append({"data_request_id": bundle_id, "logical_name": entry["logical_name"],
                                     "source_table": entry["source_table"],
                                     "columns": [c for c in own["columns"][local_id] if c not in keys],
                                     "ranges": [{"range_id": r["range_id"], "start": r["start"], "end": r["end"]}
                                                for r in ranges],
                                     "history_buffer": entry.get("history_buffer"),
                                     "future_buffer": entry.get("future_buffer"),
                                     "entity_column": entry.get("entity_column"),
                                     "time_column": entry.get("time_column"), "scope_sha256": entry.get("scope_sha256"),
                                     "source_frequency": entry.get("source_frequency"),
                                     "analysis_frequency": entry.get("analysis_frequency"),
                                     "resample": entry.get("resample"),
                                     "resample_rules": entry.get("resample_rules") or {}})
                    local_requests[local_id] = bundle_id
                    for local_range, bundle_range in own["ranges"][local_id].items():
                        local_ranges[f"{local_id}:{local_range}"] = bundle_range
                    required.append({"angle_request_id": local_id, "data_request_id": bundle_id,
                                     "source_table": entry["source_table"], "columns": own["columns"][local_id],
                                     "ranges": [r["range_id"] for r in ranges]})
                datasets.sort(key=lambda d: d["data_request_id"])
                relationships = sorted({rel["relationship_id"] for rel in group["spec"]["relationships"]
                                        if rel["left_request_id"] in local_requests.values()
                                        and rel["right_request_id"] in local_requests.values()})
                body = {"contract_version": CONTRACT_VERSION, "angle_id": angle_id,
                        "bundle_group_id": group["bundle_group_id"],
                        "data_request_ids": [d["data_request_id"] for d in datasets], "datasets": datasets,
                        "relationships": relationships,
                        "time_basis": draft.get("time_basis") or "HISTORICAL_DESCRIPTIVE",
                        "local_request_ids": local_requests, "local_range_ids": local_ranges,
                        "data_contract_sha256": draft.get("contract_sha256")}
                contracts[angle_id] = {**body, "angle_data_contract_sha256": contract_sha256(body)}
                requirements[angle_id] = required
        plan = {"data_plan_version": DATA_PLAN_VERSION,
                "strategy": "SINGLE_BUNDLE" if len(groups) == 1 else "MULTI_BUNDLE",
                "spec_version": "data_need_spec/v2", "time_basis": args.get("time_basis") or "HISTORICAL_DESCRIPTIVE",
                "bundle_groups": groups, "angle_to_bundle_group": dict(sorted(to_group.items())),
                "angle_input_requirements": requirements, "merge_decisions": decisions, "uncovered_angle_ids": [],
                "conflicts": [], "angle_data_contracts": contracts,
                "totals": {"rows": sum(g["estimates"]["rows"] for g in groups),
                           "parts": sum(g["estimates"]["parts"] for g in groups)}}
        plan["research_data_plan_sha256"] = data_plan_sha256(plan)
        return plan

    @staticmethod
    def _outcome(status: str, data_plan: dict[str, Any] | None, *, strategy: str | None = None,
                 uncovered: list[str] | None = None, issues: list[dict[str, Any]] | None = None,
                 attempts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        view: dict[str, Any] = {"status": status, "strategy": strategy, "issues": (issues or [])[:20],
                                "uncovered_angle_ids": uncovered or [], "group_attempts": (attempts or [])[:12]}
        if data_plan is not None:
            view.update(
                research_data_plan_sha256=data_plan["research_data_plan_sha256"],
                bundle_groups=[{k: g[k] for k in ("bundle_group_id", "angle_ids", "draft_id")}
                               | {"estimated_rows": g["estimates"]["rows"], "extraction_parts": g["estimates"]["parts"]}
                               for g in data_plan["bundle_groups"]],
                angles={angle_id: {"bundle_group_id": c["bundle_group_id"],
                                   "requests": c["local_request_ids"], "ranges": c["local_range_ids"],
                                   "datasets": [{"data_request_id": d["data_request_id"],
                                                 "logical_name": d["logical_name"], "columns": d["columns"],
                                                 "ranges": [r["range_id"] for r in d["ranges"]]}
                                                for d in c["datasets"]]}
                        for angle_id, c in data_plan["angle_data_contracts"].items()},
                merge_decisions=len(data_plan["merge_decisions"]))
        view["next_action"] = {"FEASIBLE": "PRESENT_RESEARCH_PLAN", "REVISION_REQUIRED": "REVISE_ANGLE_REQUIREMENTS",
                               "NOT_FEASIBLE": "NARROW_THE_PLAN_OR_REPORT_LIMITATION"}[status]
        return {"status": status, "data_plan": data_plan, "view": view}


CHECK_RESEARCH_FEASIBILITY_DESCRIPTION = (
    "Before presenting a multi-angle Research Plan, check that every angle's data exists, joins and fits. Send one "
    "data requirement per planned angle (angle_id, its DataNeedSpec v2 data_requests and relationships, in the "
    "angle's own ids); the backend merges equal requests of different angles into one bundle when they fit, splits "
    "the angles into a few bundle groups only when they do not, validates each group and estimates its extraction "
    "without reading data. Returns FEASIBLE with the bundle groups, each angle's bundle request and range ids and the "
    "columns it may use (its data contract); NOT_FEASIBLE naming the angles that cannot be served; or "
    "REVISION_REQUIRED with issues by angle. Present the plan only after FEASIBLE, with exactly the angles checked.")


def research_feasibility_spec(planner: ResearchDataPlanner, *, timeout_seconds: float, max_result_bytes: int,
                              point_in_time: bool = False, on_result: Any = None) -> ToolSpec:
    model = ResearchFeasibilityArgsPIT if point_in_time else ResearchFeasibilityArgs

    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, (ResearchFeasibilityArgs, ResearchFeasibilityArgsPIT))
        outcome = planner.plan(arguments.model_dump(mode="json"))
        if on_result is not None:
            on_result(outcome)
        return outcome["view"]

    return ToolSpec(name="check_research_feasibility", description=CHECK_RESEARCH_FEASIBILITY_DESCRIPTION,
                    arguments_model=model, handler=handler, timeout_seconds=timeout_seconds,
                    max_result_bytes=max_result_bytes, argument_errors=argument_issues)
