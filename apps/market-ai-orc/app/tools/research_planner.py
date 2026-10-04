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
   angle_data_contract/v1 (the datasets, columns and ranges it may use), the hash of every angle's checked design and
   the plan hash.

Before any of this (M38, suite20 2026-09-29), each angle's design (method, parameters, horizon, unit, comparisons,
holdout and the price column of a forward-return outcome) is checked against the rules the final plan enforces and
the research library's data requirements, so a FEASIBLE check is never followed by a plan refused for a method rule.
The check reads metadata only (user decision 2026-09-29); what needs data surfaces in the run.

Nothing is extracted and no revision is consumed. The full data plan stays with the orchestrator (it is bound to the
plan's rpc2 continuation); the model sees a compact view.
"""
from __future__ import annotations

import copy
import re
import string
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..research_library import by_method
from ..research_plan_v2 import (CONTRACT_VERSION, DATA_PLAN_VERSION, MAX_CANDIDATES_PER_ANGLE, MAX_PAIRWISE_PER_ANGLE,
                                USES, AngleParameters, MethodId, OutcomeUnit, Policy, contract_sha256, data_plan_sha256,
                                current_angle_bounds, design_sha256, family_count, holdout_start, parameter_problems,
                                sha256_json)
from .analysis import current_run_context, take_data_date_policy
from .data_need import DataRequest, RelationshipV2, Subject, argument_issues
from .data_planner import empty_requests
from .registry import ToolError, ToolSpec

MAX_REQUESTS_PER_SPEC = 8
MAX_RELATIONSHIPS_PER_SPEC = 8
IDENTIFIER = r"^[a-z][a-z0-9_]{0,39}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutcomePrice(Strict):
    data_request_id: str = Field(description="The angle's own request id (one of its data_requests) that holds the "
                                             "price column.")
    column: str = Field(description="The numeric price-level column (for example close) the backend computes the "
                                    "forward return from; never a return column.")


class AngleDesign(Strict):
    """The analytical design the Research Plan will give this angle; the plan must repeat it unchanged."""

    method_id: MethodId = Field(description="A method of the research library (get_research_library).")
    parameters: AngleParameters
    outcome_horizon_periods: int = Field(ge=1, le=260, description="Analysis periods one outcome spans.")
    outcome_unit: OutcomeUnit
    candidate_count: int = Field(ge=1, le=MAX_CANDIDATES_PER_ANGLE,
                                 description="Thresholds, lags, lengths or conditions evaluated inside this angle.")
    pairwise_comparisons: int = Field(ge=0, le=MAX_PAIRWISE_PER_ANGLE)
    multiple_testing_policy: Policy = Field(description="NONE only for a single comparison.")
    holdout_required: bool = Field(description="True when the latest range is kept as a holdout (the angle's "
                                               "requests then need at least two ranges).")
    outcome_price: OutcomePrice | None = Field(description="For a forward-return outcome (PERCENT or DECIMAL): the "
                                                           "request and price column it is computed from; else null.")

    @model_validator(mode="before")
    @classmethod
    def _unused_parameters_are_null(cls, data: Any) -> Any:
        # as ResearchAngle: a parameter the method does not use carries no meaning for it
        if isinstance(data, dict) and isinstance(data.get("parameters"), dict) and data.get("method_id") in USES:
            used = USES[data["method_id"]]
            data = {**data, "parameters": {key: (value if key in used else None)
                                           for key, value in data["parameters"].items()}}
        return data


class BroadScope(Strict):
    data_request_id: str = Field(description="One of this angle's own request ids.")
    reason: str = Field(min_length=10, max_length=300,
                        description="Why this request must read every entity (for example a market benchmark or a "
                                    "cross-section the angle compares against).")


class AngleRequirement(Strict):
    angle_id: str = Field(description="The angle_id the Research Plan will use for this angle.")
    design: AngleDesign
    data_requests: list[DataRequest] = Field(description="1-8 requests this angle reads, in this angle's own ids "
                                                         "(for example angle_one_A); the backend merges equal "
                                                         "requests of different angles.")
    relationships: list[RelationshipV2] = Field(description="Catalog relationships between this angle's requests "
                                                            "([] for none).")
    # G13 (suite20d e02, 2026-09-30): a question about BBCA read every stock (2.6 million rows)
    broad_scope: list[BroadScope] | None = Field(
        description="Requests of this angle that read every entity although the question names specific ones, each "
                    "with the reason (null for none). Without it such a request is refused "
                    "(SCOPE_WIDER_THAN_QUESTION).")


class ResearchFeasibilityArgs(Strict):
    spec_version: Literal["data_need_spec/v2"]
    question: str = Field(description="The user's question, restated.")
    subject: Subject
    angles: list[AngleRequirement] = Field(description="One data requirement per angle of the planned Research Plan.")
    data_as_of_policy: Literal["CONVERSATION", "NEWEST"] | None = Field(
        description="Null or CONVERSATION: a range ending LATEST ends at the conversation's data date. NEWEST only "
                    "when the user asks for newer data; the answer then states both dates.")

    @model_validator(mode="before")
    @classmethod
    def _policy_absent_is_null(cls, data: Any) -> Any:
        if isinstance(data, dict) and "data_as_of_policy" not in data:
            return {**data, "data_as_of_policy": None}
        return data


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


# trading observations per analysis period, to size a forward return's future buffer (conservative)
PERIOD_OBSERVATIONS = {None: 1, "DAILY": 1, "WEEKLY": 5, "MONTHLY": 23, "QUARTERLY": 66, "YEARLY": 262}
MAX_BUFFER_OBSERVATIONS = 5000  # the sandbox's DataNeedSpec limit


def _wider(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any] | None:
    if not a or not b:
        return copy.deepcopy(a or b)
    if a.get("unit") == b.get("unit"):
        return {"value": max(int(a["value"]), int(b["value"])), "unit": a["unit"]}
    return {"value": max(_calendar_days(a), _calendar_days(b)), "unit": "CALENDAR_DAYS"}


ENTITY_TOKEN = re.compile(r"\b[A-Z]{4,6}\b")
# capitalised words that are not stock codes (market, currency and ratio names)
NOT_ENTITIES = {"IHSG", "IDX", "BEI", "JCI", "LQ45", "IDR", "USD", "YTD", "MTD", "QTD", "ROE", "ROA", "EPS", "PER",
                "PBV", "BUMN", "ARA", "ARB", "RUPS", "NULL", "TRUE", "FALSE", "ANSWER"}


def _filters(scope: Any, column: str) -> bool:
    """Whether a scope tree has a predicate on the column anywhere (NOT included: it still names entities)."""
    if not isinstance(scope, dict):
        return False
    if scope.get("type") == "PREDICATE":
        return scope.get("column") == column
    return any(_filters(child, column) for child in (scope.get("children") or []) + [scope.get("child")])


class ResearchDataPlanner:
    def __init__(self, client: Any, planner: Any, *, max_groups: int = 3, min_angles: int = 2, max_angles: int = 6,
                 limits: dict[str, Any] | None = None, min_families: int = 0,
                 entity_checker: Callable[[str, str, str], bool] | None = None) -> None:
        self.client = client
        self.planner = planner
        # G13: (table, entity column, token) -> whether the token is an entity of that table (Governor dimension
        # values); None skips the scope check
        self.entity_checker = entity_checker
        self._entity_cache: dict[tuple[str, str, str], bool] = {}
        self.max_groups = max_groups
        self.min_angles = min_angles
        self.max_angles = max_angles
        self.min_families = min_families
        limits = limits or {}
        self.max_rows = int(limits.get("bundle_max_rows") or 2_000_000)
        self.max_parts = int(limits.get("bundle_max_parts") or 128)
        self.max_requests = min(int(limits.get("max_requests_per_spec") or MAX_REQUESTS_PER_SPEC),
                                MAX_REQUESTS_PER_SPEC)

    # ------------------------------------------------------------------------------------------ scope (G13)

    def _named_entities(self, table: str, column: str, text: str) -> list[str]:
        """The tokens of the question that are entities of this table (four to six capital letters, e.g. BBCA),
        checked with the Governor; a failed check names nothing (the scope check then does not apply)."""
        found = []
        for token in dict.fromkeys(ENTITY_TOKEN.findall(text)):
            if token in NOT_ENTITIES:
                continue
            key = (table, column, token)
            if key not in self._entity_cache:
                try:
                    self._entity_cache[key] = bool(self.entity_checker(table, column, token))
                except Exception:  # noqa: BLE001 - the check is advisory; the Governor still bounds extraction
                    self._entity_cache[key] = False
            if self._entity_cache[key]:
                found.append(token)
        return found

    def _scope_issues(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        """G13: when the question names specific entities (BBCA), a request that reads every entity of its table is
        refused unless the angle declares it in broad_scope with a reason."""
        if self.entity_checker is None:
            return []
        context = current_run_context.get()
        text = " ".join([str(args.get("question") or "")]
                        + ([context.messages[-1][1]] if context is not None and context.messages else []))
        issues = []
        for index, angle in enumerate(args["angles"]):
            declared = {b["data_request_id"] for b in angle.get("broad_scope") or []}
            for r_index, request in enumerate(angle["data_requests"]):
                column = request.get("entity_column")
                if not column or request["data_request_id"] in declared or _filters(request.get("scope"), column):
                    continue
                named = self._named_entities(request["source_table"], column, text)
                if named:
                    issues.append({
                        "angle_id": angle["angle_id"], "data_request_id": request["data_request_id"],
                        "code": "SCOPE_WIDER_THAN_QUESTION", "field_path": f"angles[{index}].data_requests[{r_index}]"
                                                                           ".scope",
                        "rejected_value": f"every {column} of {request['source_table']}",
                        "message": f"The question names {', '.join(named)}, but {request['data_request_id']} reads "
                                   f"every {column} of {request['source_table']}. Add a scope predicate on {column} "
                                   f"(for example IN {named}), or declare the request in this angle's broad_scope "
                                   "with the reason it needs every entity."})
        return issues

    # ------------------------------------------------------------------------------------------ structure

    def _structure(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []

        def add(angle_id: Any, code: str, path: str, value: Any) -> None:
            issues.append({"angle_id": angle_id, "data_request_id": None, "code": code, "field_path": path,
                           "rejected_value": value if not isinstance(value, (dict, list)) else str(value)[:200]})

        import re

        angles = args["angles"]
        low, high = current_angle_bounds.get() or (self.min_angles, self.max_angles)  # mode 4 sets the request's count
        if not low <= len(angles) <= high:
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
            issues += self._design_issues(index, angle)
        if self.min_families and family_count([a["design"]["method_id"] for a in angles]) < self.min_families:
            issues.append({"angle_id": None, "data_request_id": None, "code": "FAMILY_COVERAGE",
                           "field_path": "angles", "rejected_value": family_count([a["design"]["method_id"]
                                                                                   for a in angles]),
                           "message": f"This deployment needs angles from at least {self.min_families} method "
                                      "families (get_research_library lists each method's family)."})
        return issues

    @staticmethod
    def _design_issues(index: int, angle: dict[str, Any]) -> list[dict[str, Any]]:
        """M38: the rules the final plan enforces (parameters, multiple testing, holdout ranges) and the research
        library's data requirements (entity column, forward-return price column), checked on metadata only."""
        angle_id, design = angle["angle_id"], angle["design"]
        path = f"angles[{index}].design"
        issues: list[dict[str, Any]] = []

        def add(code: str, field: str, value: Any, message: str) -> None:
            issues.append({"angle_id": angle_id, "data_request_id": None, "code": code,
                           "field_path": f"{path}.{field}" if field else path,
                           "rejected_value": value if not isinstance(value, (dict, list)) else str(value)[:200],
                           "message": message})

        method = design["method_id"]
        for problem in parameter_problems(method, design["parameters"], design["candidate_count"],
                                          design["pairwise_comparisons"]):
            add("DESIGN_PARAMETERS", "parameters", None, problem)
        if design["multiple_testing_policy"] == "NONE" \
                and max(design["candidate_count"], design["pairwise_comparisons"]) > 1:
            add("MULTIPLE_TESTING_POLICY_REQUIRED", "multiple_testing_policy", "NONE",
                "more than one comparison needs a multiple_testing_policy other than NONE")
        requests = {r["data_request_id"]: r for r in angle["data_requests"]}
        if design["holdout_required"] and holdout_start(
                {"datasets": [{"ranges": r.get("time_ranges") or []} for r in requests.values()]}) is None:
            add("HOLDOUT_NEEDS_TWO_RANGES", "holdout_required", True,
                "a holdout keeps the latest range apart: give the angle's requests a separate later range, or set "
                "holdout_required false")
        library = by_method().get(method) or {}
        requirements = library.get("data_requirements") or {}
        if requirements.get("entity_column") == "REQUIRED" and not any(r.get("entity_column")
                                                                       for r in requests.values()):
            add("ENTITY_COLUMN_REQUIRED", "method_id", method,
                f"{method} compares entities, so the angle needs a request with an entity column")
        price = design.get("outcome_price")
        wants_return = requirements.get("outcome") == "FORWARD_RETURN" and design["outcome_unit"] in ("PERCENT",
                                                                                                     "DECIMAL")
        if wants_return and price is None:
            add("OUTCOME_PRICE_REQUIRED", "outcome_price", None,
                "a forward-return outcome needs outcome_price: the angle's request and the price-level column the "
                "backend computes the return from")
        if price is not None:
            request = requests.get(price["data_request_id"])
            if request is None:
                add("OUTCOME_PRICE_REQUEST_UNKNOWN", "outcome_price.data_request_id", price["data_request_id"],
                    "outcome_price names a request this angle does not read")
            elif price["column"] not in request["columns"] \
                    or price["column"] in (request.get("entity_column"), request.get("time_column")):
                add("OUTCOME_PRICE_COLUMN_MISSING", "outcome_price.column", price["column"],
                    f"{price['column']} is not a value column of request {price['data_request_id']}; add the price "
                    "column to its columns")
        return issues

    @staticmethod
    def _widen_future_buffers(angles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """A forward return needs a future buffer of at least its horizon on the price request; a shorter one is
        widened (in trading observations of the analysis frequency) and reported, never refused."""
        adjustments = []
        for angle in angles:
            price = angle["design"].get("outcome_price")
            request = next((r for r in angle["data_requests"]
                            if price is not None and r["data_request_id"] == price["data_request_id"]), None)
            if request is None:
                continue
            need = min(angle["design"]["outcome_horizon_periods"]
                       * PERIOD_OBSERVATIONS.get(request.get("resample"), 1), MAX_BUFFER_OBSERVATIONS)
            buffer = request.get("future_buffer")
            wanted = {"value": need, "unit": "TRADING_OBSERVATIONS"}
            if buffer is None or _calendar_days(buffer) < _calendar_days(wanted) \
                    or (buffer.get("unit") == "TRADING_OBSERVATIONS" and int(buffer.get("value") or 0) < need):
                request["future_buffer"] = wanted
                adjustments.append({"angle_id": angle["angle_id"], "data_request_id": request["data_request_id"],
                                    "future_buffer": wanted, "previous": buffer,
                                    "reason": "a forward return needs a future buffer of at least its horizon"})
        return adjustments

    # ------------------------------------------------------------------------------------------ merge

    @staticmethod
    def _key(angle: dict[str, Any], local_id: str, stack: tuple[str, ...] = ()) -> str:
        """What makes two angles' requests the same request: the request's own fields plus every INNER relationship
        that touches it, on either side, with the key of the request at the other end (recursively; a request already
        on the path is not followed again). G19 (2026-10-03): the key held only the relationships where the request
        was the LEFT side, so a flow or price request restricted to BUMN banks and the same request restricted to
        non-BUMN banks (both the RIGHT side of the universe relationship) got one key, were merged, and the merged
        request carried both restrictions: 0 rows."""
        request = next(r for r in angle["data_requests"] if r["data_request_id"] == local_id)
        restrictions = []
        if local_id not in stack:
            for rel in angle["relationships"]:
                if rel["join_type"] != "INNER" or local_id not in (rel["left_request_id"], rel["right_request_id"]):
                    continue
                side = "left" if rel["left_request_id"] == local_id else "right"
                other = rel["right_request_id"] if side == "left" else rel["left_request_id"]
                restrictions.append({k: rel[k] for k in rel if k not in ("left_request_id", "right_request_id")}
                                    | {"side": side,
                                       "other": ResearchDataPlanner._key(angle, other, stack + (local_id,))})
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
        issues = self._structure(args) or self._scope_issues(args)
        if issues:
            return self._outcome("REVISION_REQUIRED", None, issues=issues)
        args = copy.deepcopy(args)
        angles = args["angles"]
        adjustments = self._widen_future_buffers(angles)
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
                empty = empty_requests(result["draft"], estimate)
                if empty:
                    reverse = {v: k for k, v in letters.items()}
                    for issue in empty:
                        owners = [s for s in merged[reverse[issue["data_request_id"]]]["sources"]
                                  if s["angle_id"] in members] if issue["data_request_id"] in reverse else []
                        issue.update(angle_ids=sorted({s["angle_id"] for s in owners}) or members,
                                     angle_request_ids=[s["data_request_id"] for s in owners])
                    return self._outcome("REVISION_REQUIRED", None, issues=empty, attempts=attempts)
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
        outcome = self._outcome("FEASIBLE", data_plan, strategy=data_plan["strategy"], attempts=attempts,
                                adjustments=adjustments)
        outcome["designs"] = {a["angle_id"]: a["design"] for a in angles}
        return outcome

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
                                                                             "extraction_parts", "governor_status",
                                                                             "row_basis") if k in r}
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
        broad = {a["angle_id"]: a["broad_scope"] for a in args["angles"] if a.get("broad_scope")}
        plan = {"data_plan_version": DATA_PLAN_VERSION,
                "strategy": "SINGLE_BUNDLE" if len(groups) == 1 else "MULTI_BUNDLE",
                "spec_version": "data_need_spec/v2", "time_basis": args.get("time_basis") or "HISTORICAL_DESCRIPTIVE",
                "bundle_groups": groups, "angle_to_bundle_group": dict(sorted(to_group.items())),
                "angle_input_requirements": requirements, "merge_decisions": decisions, "uncovered_angle_ids": [],
                "conflicts": [], "angle_data_contracts": contracts,
                # M38: the plan must carry exactly these checked designs (hashes only: strings survive any client)
                "angle_design_sha256s": {a["angle_id"]: design_sha256(a["design"]) for a in args["angles"]},
                "totals": {"rows": sum(g["estimates"]["rows"] for g in groups),
                           "parts": sum(g["estimates"]["parts"] for g in groups)}}
        if broad:
            plan["broad_scope"] = broad  # G13: the requests kept on every entity, with the model's reasons
        plan["research_data_plan_sha256"] = data_plan_sha256(plan)
        return plan

    @staticmethod
    def _outcome(status: str, data_plan: dict[str, Any] | None, *, strategy: str | None = None,
                 uncovered: list[str] | None = None, issues: list[dict[str, Any]] | None = None,
                 attempts: list[dict[str, Any]] | None = None,
                 adjustments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        view: dict[str, Any] = {"status": status, "strategy": strategy, "issues": (issues or [])[:20],
                                "uncovered_angle_ids": uncovered or [], "group_attempts": (attempts or [])[:12]}
        if adjustments:
            view["adjustments"] = adjustments[:12]
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
    "Before presenting a multi-angle Research Plan, check every angle's design and data. Send one entry per planned "
    "angle: angle_id, its design (method from get_research_library, parameters, horizon, unit, comparisons, "
    "multiple-testing policy, holdout, and for a forward-return outcome the request and price column) and its "
    "DataNeedSpec v2 data_requests and relationships in the angle's own ids. The backend checks each design against "
    "the method's rules and data requirements, merges equal requests of different angles into one bundle when they "
    "fit, splits the angles into a few bundle groups only when they do not, validates each group and estimates its "
    "extraction without reading data. Returns FEASIBLE with the bundle groups, each angle's bundle request and range "
    "ids and the columns it may use (its data contract); NOT_FEASIBLE naming the angles that cannot be served; or "
    "REVISION_REQUIRED with issues by angle. When the question names specific entities (for example BBCA), each "
    "request reads only those entities (a scope predicate on its entity column); a request that must read every "
    "entity (a market benchmark, a cross-section) is declared in that angle's broad_scope with the reason. Present "
    "the plan only after FEASIBLE, with exactly the angles and designs checked.")


def research_feasibility_spec(planner: ResearchDataPlanner, *, timeout_seconds: float, max_result_bytes: int,
                              point_in_time: bool = False, on_result: Any = None) -> ToolSpec:
    model = ResearchFeasibilityArgsPIT if point_in_time else ResearchFeasibilityArgs

    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, (ResearchFeasibilityArgs, ResearchFeasibilityArgsPIT))
        args = arguments.model_dump(mode="json")
        take_data_date_policy(args)  # R-STORE: the pin applies to the planner's checks below
        outcome = planner.plan(args)
        if on_result is not None:
            on_result(outcome)
        return outcome["view"]

    return ToolSpec(name="check_research_feasibility", effect="FETCHES_DATA", description=CHECK_RESEARCH_FEASIBILITY_DESCRIPTION,
                    arguments_model=model, handler=handler, timeout_seconds=timeout_seconds,
                    max_result_bytes=max_result_bytes, argument_errors=argument_issues)
