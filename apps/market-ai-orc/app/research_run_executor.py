"""Multi-Angle Research run executor (AI_ENABLE_MULTI_ANGLE_RESEARCH; MULTI_ANGLE_RESEARCH.md).

After the user approved a research_plan/v2 (rpc2 verified), the model does not orchestrate bundle groups session by
session. It sees three tools, and this executor does the backend work behind them:

    start_research_run      promote the signed feasibility drafts (one approved RESEARCH need per bundle group, after
                            the Research Governor v2 approved the declaration this executor builds from the verified
                            plan), prepare every group's bundle, open the first group's session
    run_research_code       run the model's code in one group's session; moving to the next group completes the open
                            one first, so at most one session of the run is open (S08)
    complete_research_run   complete the open group, and finalize: groups never run and angles never recorded become
                            NOT_RUN, backend-authored; then return the grouped result: one finding per approved angle,
                            the angle completion counts, the weakest validation level and the synthesis map

A group whose bundle or session fails is closed in the sandbox (FAILED, its angles NOT_RUN), so no angle disappears.
S16 (suite20b r09, 2026-09-29; user decision 2026-09-30): when a group's session ends during the run, a crash
(RESTARTABLE_REASONS) reopens a new session on the same bundle at the next run_research_code, at most
AI_RESEARCH_MAX_SESSION_RESTARTS times per group; a governance limit (CPU, memory, disk, timeout, forbidden
operation) or any other reason closes the group, because the limits are per session and a new one would lift them.
A finalize that cannot complete the open group closes it as well, so a run always reaches a terminal state.
Groups run one after another (AI_RESEARCH_MAX_PARALLEL_GROUPS accepts only 1): the sandbox has few session slots for
every run together.
"""
from __future__ import annotations

import contextvars
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .research_plan import normalize_text
from .research_plan_v2 import FINDINGS_V2, VerifiedPlanV2, governance_v2
from .tools.registry import ToolSpec
from .tools.session import SESSION_PATTERN, _call, current_carried_outputs, released_contents, restore_into

LEVELS = ("EXECUTION_ONLY", "STATISTICS_VERIFIED", "FORMULA_AND_STATISTICS_VERIFIED")
SESSION_GONE = frozenset({"SESSION_ENDED", "SESSION_CLOSED"})
RESTARTABLE_REASONS = frozenset({"WORKER_CRASHED", "SESSION_STATE_CORRUPTED", "PROTOCOL_ERROR"})
INTERNALS_WARNING = "Do not import or modify the sandbox's internal modules (saniti_session, research_*)."
STATUS_KEYS = {"SUPPORTED": "supported", "PARTIALLY_SUPPORTED": "partially_supported",
               "INSUFFICIENT_EVIDENCE": "insufficient_evidence", "INVALID": "invalid", "NOT_RUN": "not_run"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartResearchRunArgs(Strict):
    """No arguments: the approved plan and its data plan are known to the backend."""


class RunResearchCodeArgs(Strict):
    bundle_group_id: str = Field(pattern=r"^g[1-9][0-9]?$", description="The bundle group whose session runs the "
                                                                        "code, e.g. g1.")
    code: str = Field(min_length=1, max_length=20000, description="Python for that group's session.")


class CompleteResearchRunArgs(Strict):
    finalize: bool = Field(description="false: complete and report what is missing. true: accept the result as it "
                                       "stands; angles without a record and groups never run become NOT_RUN, "
                                       "INVALID findings stay INVALID.")


@dataclass
class ResearchContext:
    """Per-run multi-angle state: the last FEASIBLE research data plan of the plan turn, and the executor of an
    approved plan."""

    feasible: dict[str, Any] | None = None
    # the checked design of every angle of that data plan (M38), for naming what a plan changed
    designs: dict[str, dict[str, Any]] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    executor: "ResearchRunExecutor | None" = None
    # tool calls this run may still make (set by the orchestrator); M36 refuses an early finalize only while the model
    # can still record the missing angles
    calls_left: Any = None


current_research_context: contextvars.ContextVar[ResearchContext | None] = contextvars.ContextVar(
    "current_research_context", default=None)


def remember_feasibility(outcome: dict[str, Any]) -> None:
    """check_research_feasibility's callback: the run's research context keeps the last FEASIBLE research data plan
    (the full plan stays with the orchestrator; the model sees a compact view)."""
    context = current_research_context.get()
    if context is None:
        return
    context.checks.append({k: outcome["view"].get(k) for k in ("status", "strategy", "uncovered_angle_ids")})
    if outcome["status"] == "FEASIBLE" and outcome["data_plan"] is not None:
        context.feasible = outcome["data_plan"]
        context.designs = dict(outcome.get("designs") or {})


def weakest(levels: list[str | None]) -> str | None:
    known = [level for level in levels if level in LEVELS]
    return min(known, key=LEVELS.index) if known else None


def synthesis_map(plan: Any, data_plan: dict[str, Any], findings: list[dict[str, Any]],
                  groups: list[dict[str, Any]]) -> dict[str, Any]:
    """An evidence map, never a vote: statuses by angle, direction conflicts between angles with comparable outcomes,
    the conditions under which results differ, shared data (dependent angles), bundle and session notes, and whether
    an agreement claim is allowed (at least two SUPPORTED angles of different method families)."""
    by_id = {f["angle_id"]: f for f in findings}
    angles = {a.angle_id: a for a in plan.angles}
    out: dict[str, Any] = {key: [] for key in STATUS_KEYS.values()}
    for angle_id in angles:
        status = (by_id.get(angle_id) or {}).get("status") or "NOT_RUN"
        out[STATUS_KEYS[status]].append(angle_id)
    conflicts = []
    ids = list(angles)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            fa, fb = by_id.get(a) or {}, by_id.get(b) or {}
            comparable = normalize_text(angles[a].outcome) == normalize_text(angles[b].outcome) \
                and angles[a].outcome_horizon_periods == angles[b].outcome_horizon_periods \
                and angles[a].outcome_unit == angles[b].outcome_unit
            directions = {fa.get("evidence_direction"), fb.get("evidence_direction")}
            if comparable and directions == {"EXPECTED", "OPPOSITE"}:
                conflicts.append({"angles": [a, b], "outcome": angles[a].outcome,
                                  "evidence_direction": {a: fa.get("evidence_direction"),
                                                         b: fb.get("evidence_direction")}})
    requirements = data_plan.get("angle_input_requirements") or {}
    used = {a: {r["data_request_id"] for r in requirements.get(a) or []} for a in angles}
    shared = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            common = sorted(used.get(a, set()) & used.get(b, set()))
            if common:
                shared.append({"angles": [a, b], "shared_bundle_requests": common})
    supported = out["supported"]
    families = {angles[a].method_family for a in supported}
    notes = []
    if len(groups) > 1:
        notes.append(f"The angles ran in {len(groups)} bundle groups with separate sessions and extractions.")
    failed = [g["bundle_group_id"] for g in groups if g.get("status") == "FAILED"]
    if failed:
        notes.append(f"Bundle groups {failed} failed; their angles are NOT_RUN.")
    return {**out,
            "direction_conflicts": conflicts,
            "conditions": [{"angle_id": a, "condition": angles[a].condition,
                            "status": (by_id.get(a) or {}).get("status") or "NOT_RUN",
                            "evidence_direction": (by_id.get(a) or {}).get("evidence_direction")} for a in ids],
            "dependence": shared, "bundle_notes": notes,
            "agreement": {"supported_angles": supported, "distinct_method_families": len(families),
                          "allowed": len(supported) >= 2 and len(families) >= 2},
            "not_a_vote": "Angles are separate questions on one hypothesis; their statuses are not counted as votes."}


class ResearchRunExecutor:
    def __init__(self, client: Any, planner: Any, verified: VerifiedPlanV2, request_id: str, *,
                 execution_timeout: float, timeout: float, max_result_bytes: int,
                 max_session_restarts: int = 1) -> None:
        self.client = client
        self.max_session_restarts = max_session_restarts
        self.planner = planner
        self.verified = verified
        self.request_id = request_id
        self.execution_timeout = execution_timeout
        self.timeout = timeout
        self.max_result_bytes = max_result_bytes
        self.research_run_id: str | None = None
        self.groups: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        self.promotion: dict[str, Any] | None = None
        self.result: dict[str, Any] | None = None
        self.open_group: str | None = None
        self.completions: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.attempted = False
        self.early_finalize_refused = False

    # ------------------------------------------------------------------ sandbox calls

    def _close_group(self, group_id: str, reason: str) -> None:
        reason = re.sub(r"[^A-Z0-9_]", "_", reason.upper())[:60]
        reason = reason if re.fullmatch(r"[A-Z][A-Z0-9_]{1,59}", reason) else "GROUP_FAILED"
        body = _call(self.client, "POST", f"/v1/research-runs/{self.research_run_id}/groups/{group_id}/close",
                     timeout=self.timeout, json={"request_id": self.request_id, "reason": reason})
        self.groups[group_id].update(status="FAILED", reason=reason)
        if body.get("status") == "REJECTED":
            self.groups[group_id]["close_error"] = body.get("code")

    def _open(self, group_id: str) -> dict[str, Any]:
        group = self.groups[group_id]
        body: dict[str, Any] = {"request_id": self.request_id, "bundle_id": group["bundle_id"]}
        carried = current_carried_outputs.get()
        if carried is not None:
            body["carried_outputs"] = carried  # 2d: the tables the approved plan names
        opened = _call(self.client, "POST", "/v1/sessions", timeout=self.timeout + 30 + self.client.open_wait_seconds,
                       json=body)
        if opened.get("status") == "REJECTED" or not opened.get("session_id"):
            return opened
        restore_into(opened, carried if carried is not None else [])  # R-STORE: only the plan's tables
        group.update(session_id=opened["session_id"], status="RUNNING")
        self.sessions[opened["session_id"]] = {"bundle_group_id": group_id, "bundle_id": group["bundle_id"],
                                               "need_id": group["need_id"], "executions": []}
        self.open_group = group_id
        return opened

    def _complete(self, group_id: str, finalize: bool) -> dict[str, Any]:
        group = self.groups[group_id]
        result = _call(self.client, "POST", f"/v1/sessions/{group['session_id']}/complete",
                       timeout=self.timeout * 2, json={"request_id": self.request_id, "finalize": finalize})
        self.completions[group["session_id"]] = result
        if result.get("status") == "COMPLETED":
            group["status"] = "COMPLETED"
            group["completion_id"] = result.get("completion_id")
            if self.open_group == group_id:
                self.open_group = None
            if result.get("released_outputs"):
                result["released_contents"] = released_contents(
                    self.client, group["session_id"], result["released_outputs"], self.timeout, self.request_id,
                    byte_budget=max(0, self.max_result_bytes // 3), final_status=result.get("final_status"))
        return result

    # ------------------------------------------------------------------ tools

    def start(self) -> dict[str, Any]:
        if self.research_run_id is not None:
            return self._state("ALREADY_STARTED")
        self.attempted = True
        governance = governance_v2(self.verified)
        promoted = _call(self.client, "POST", "/v1/research-runs", timeout=self.timeout * 2,
                         json={"request_id": self.request_id, "origin_request_id": self.verified.origin_request_id,
                               "research_governance": governance,
                               "research_data_plan": self.verified.research_data_plan})
        self.promotion = {k: promoted.get(k) for k in ("status", "code", "message", "error", "research_run_id")}
        if promoted.get("status") != "APPROVED" or not promoted.get("research_run_id"):
            error = promoted.get("error") if isinstance(promoted.get("error"), dict) else {}
            return {"status": "REJECTED", "code": error.get("code") or promoted.get("code") or promoted.get("status"),
                    "message": error.get("message") or promoted.get("message"),
                    "issues": (error.get("issues") or [])[:10], "next_action": "REPORT_LIMITATION"}
        self.research_run_id = promoted["research_run_id"]
        for group in promoted.get("groups") or []:
            self.groups[group["bundle_group_id"]] = {"bundle_group_id": group["bundle_group_id"],
                                                     "angle_ids": group["angle_ids"], "need_id": group["need_id"],
                                                     "status": "APPROVED", "bundle_id": None, "session_id": None}
            self.order.append(group["bundle_group_id"])
        for group_id in self.order:
            group = self.groups[group_id]
            bundle = self.planner.prepare(group["need_id"])
            if bundle.get("status") == "READY" and bundle.get("input_bundle_id"):
                group.update(status="READY", bundle_id=bundle["input_bundle_id"],
                             datasets=[{k: d.get(k) for k in ("data_request_id", "logical_name", "rows", "entities",
                                                              "quality_flags")}
                                       for d in bundle.get("datasets") or []],
                             warnings=[w.get("code") for w in bundle.get("relationship_warnings") or []
                                       if isinstance(w, dict)])
                # G19 (2026-10-03): a group whose bundle delivered an empty dataset does not run its angles on
                # nothing; they become NOT_RUN with the reason EMPTY_INPUT (not INSUFFICIENT_EVIDENCE)
                empty = [d.get("logical_name") or d.get("data_request_id") for d in group["datasets"]
                         if "EMPTY_DATASET" in (d.get("quality_flags") or []) or d.get("rows") == 0]
                if empty:
                    group["empty_datasets"] = empty
                    self._close_group(group_id, "EMPTY_INPUT")
            else:
                self._close_group(group_id, str(bundle.get("code") or "BUNDLE_NOT_READY"))
        first = next((g for g in self.order if self.groups[g]["status"] == "READY"), None)
        session = self._open(first) if first else None
        if session is not None and session.get("status") == "REJECTED":
            self._close_group(first, str(session.get("code") or "SESSION_NOT_OPENED"))
            session = None
        state = self._state("STARTED")
        if session is not None:
            state["session"] = {k: session.get(k) for k in ("session_id", "bundle_group_id", "datasets",
                                                              "relationships", "research", "helpers", "limits")}
        state["next_action"] = "RUN_RESEARCH_CODE" if session is not None else "COMPLETE_RESEARCH_RUN"
        return state

    def run(self, group_id: str, code: str) -> dict[str, Any]:
        if self.research_run_id is None:
            return {"status": "REJECTED", "code": "RESEARCH_RUN_NOT_STARTED",
                    "message": "Call start_research_run first.", "next_action": "START_RESEARCH_RUN"}
        group = self.groups.get(group_id)
        if group is None:
            return {"status": "REJECTED", "code": "UNKNOWN_BUNDLE_GROUP",
                    "message": f"Bundle groups of this run: {self.order}.", "next_action": "RUN_RESEARCH_CODE"}
        if group["status"] in ("COMPLETED", "FAILED"):
            return {"status": "REJECTED", "code": "BUNDLE_GROUP_TERMINAL",
                    "message": f"Group {group_id} is {group['status']}; its findings are final.",
                    "next_action": "RUN_RESEARCH_CODE_OR_COMPLETE_RESEARCH_RUN"}
        opened = None
        if self.open_group is not None and self.open_group != group_id:
            previous = self.open_group
            completion = self._complete(previous, finalize=False)
            if completion.get("status") != "COMPLETED":
                return {"status": "REJECTED", "code": "OPEN_GROUP_INCOMPLETE", "open_bundle_group_id": previous,
                        "message": f"Group {previous} is not complete: {completion.get('message') or completion}. "
                                   f"Record its missing angles with run_research_code('{previous}', ...), or call "
                                   "complete_research_run with finalize true to accept it as it stands.",
                        "next_action": "RUN_RESEARCH_CODE"}
        if group.get("session_id") is None:
            opened = self._open(group_id)
            if opened.get("status") == "REJECTED":
                return {"status": "REJECTED", "code": opened.get("code"), "message": opened.get("message"),
                        "next_action": "REPORT_LIMITATION"}
        result = _call(self.client, "POST", f"/v1/sessions/{group['session_id']}/execute",
                       timeout=self.execution_timeout, json={"request_id": self.request_id, "code": code})
        self.sessions[group["session_id"]]["executions"].append(result.get("status"))
        result["bundle_group_id"] = group_id
        if opened is not None:
            result["session_opened"] = {k: opened.get(k) for k in ("session_id", "datasets", "research")}
        if result.get("status") == "REJECTED" and result.get("code") in SESSION_GONE:
            result["session_recovery"] = self._session_ended(group_id, str(result.get("close_reason") or "UNKNOWN"))
            result["next_action"] = result["session_recovery"]["next_action"]
        return result

    def _session_ended(self, group_id: str, reason: str) -> dict[str, Any]:
        """S16: the group's session ended. A crash reopens a new session at the next run_research_code (within
        max_session_restarts); anything else closes the group, whose unrecorded angles become NOT_RUN."""
        group = self.groups[group_id]
        dead = group.get("session_id")
        if dead in self.sessions:
            self.sessions[dead]["ended"] = reason
        if self.open_group == group_id:
            self.open_group = None
        restarts = int(group.get("restarts") or 0)
        angles = list(group["angle_ids"])
        if reason in RESTARTABLE_REASONS and restarts < self.max_session_restarts:
            group.update(session_id=None, status="READY", restarts=restarts + 1)
            left = self.max_session_restarts - restarts - 1
            return {"action": "REOPEN_ON_NEXT_RUN", "reason": reason, "restarts_left": left,
                    "angles_to_record": angles, "next_action": "RUN_RESEARCH_CODE",
                    "message": f"The session of group {group_id} ended ({reason}); its variables and the angles it "
                               f"recorded are gone. The next run_research_code for {group_id} opens a new session on "
                               f"the same bundle: read the data again and record every angle of the group "
                               f"({', '.join(angles)}). {INTERNALS_WARNING}"}
        code = f"SESSION_ENDED_{reason}"
        self._close_group(group_id, code)
        others = [g for g in self.order if self.groups[g]["status"] in ("READY", "APPROVED")]
        why = ("the session was restarted already" if reason in RESTARTABLE_REASONS
               else "a session limit ended it, and a new session would lift that limit"
               if reason not in ("UNKNOWN",) else "its session cannot be recovered")
        return {"action": "GROUP_CLOSED", "reason": reason, "restarts_left": 0, "angles_to_record": [],
                "next_action": "RUN_RESEARCH_CODE" if others else "COMPLETE_RESEARCH_RUN",
                "message": f"The session of group {group_id} ended ({reason}) and the group is closed ({why}): its "
                           f"unrecorded angles become NOT_RUN with reason {code}. "
                           + (f"Run the remaining groups {others}, then call complete_research_run."
                              if others else "Call complete_research_run.")}

    def complete(self, finalize: bool, calls_left: int | None = None) -> dict[str, Any]:
        if self.research_run_id is None:
            return {"status": "REJECTED", "code": "RESEARCH_RUN_NOT_STARTED",
                    "message": "Call start_research_run first.", "next_action": "START_RESEARCH_RUN"}
        last: dict[str, Any] | None = None
        if finalize and not self.early_finalize_refused and (calls_left is None or calls_left >= 2):
            # M36 (suite20, 2026-09-29): 6 of 42 angles became NOT_RUN because the model finalized before recording
            # them, although every execution had succeeded. The first finalize while an approved angle is unrecorded
            # is answered with what is missing (once, and only while tool calls remain to record it); a second
            # finalize is accepted and a genuinely failing angle still becomes NOT_RUN.
            refusal, last = self._early_finalize()
            if refusal is not None:
                self.early_finalize_refused = True
                return refusal
        if self.open_group is not None:
            last = self._complete(self.open_group, finalize)
            if last.get("status") != "COMPLETED" and finalize:
                # S16: a finalize must not depend on the step that failed (coverage, a dead session): the group is
                # closed, its unrecorded angles become NOT_RUN, and the run reaches a terminal state
                closed = self.open_group
                self._close_group(closed, self._incomplete_code(last))
                self.open_group = None
            elif last.get("status") != "COMPLETED":
                return {"status": "INCOMPLETE", "bundle_group_id": self.open_group,
                        "message": last.get("message"), "missing": (last.get("final_status") or {}).get(
                            "research_group", {}).get("missing"),
                        "findings_so_far": [{k: f.get(k) for k in ("angle_id", "status", "status_reason")}
                                            for f in last.get("research_findings_v2") or []],
                        "next_action": "RUN_RESEARCH_CODE_OR_FINALIZE"}
        pending = [g for g in self.order if self.groups[g]["status"] in ("READY", "APPROVED")]
        if pending and not finalize:
            return {"status": "INCOMPLETE", "groups_not_run": pending,
                    "message": f"Groups {pending} have not run; run their angles with run_research_code, or finalize "
                               "to record them as NOT_RUN.", "next_action": "RUN_RESEARCH_CODE_OR_FINALIZE"}
        for group_id in pending:
            self._close_group(group_id, "NOT_RUN_BY_MODEL")
        view = _call(self.client, "GET", f"/v1/research-runs/{self.research_run_id}", timeout=self.timeout,
                     params={"request_id": self.request_id})
        findings = sorted(view.get("findings") or [], key=lambda f: f.get("angle_id") or "")
        planned = [a.angle_id for a in self.verified.plan.angles]
        by_id = {f["angle_id"]: f for f in findings}
        missing = [a for a in planned if a not in by_id]
        counts = {"planned": len(planned), "validated": sum(1 for f in findings if f.get("status") in (
            "SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE")),
            "missing": len(missing), "invalid": sum(1 for f in findings if f.get("status") == "INVALID"),
            "not_run": sum(1 for f in findings if f.get("status") == "NOT_RUN")}
        relied = [f.get("validation_level") for f in findings
                  if f.get("status") in ("SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE")]
        groups = [{k: g.get(k) for k in ("bundle_group_id", "angle_ids", "status", "reason", "session_id",
                                        "completion_id")} for g in (self.groups[i] for i in self.order)]
        status = "COMPLETED" if not missing and all(g["status"] in ("COMPLETED", "FAILED") for g in groups) \
            else "INCOMPLETE"
        self.result = {
            "status": status, "research_findings_version": FINDINGS_V2, "research_run_id": self.research_run_id,
            "plan_id": self.verified.plan_id, "groups": groups, "research_findings": findings,
            "angle_completion": counts, "missing_angle_ids": missing,
            "calculation_validation": weakest(relied) or "NOT_PERFORMED",
            "research_synthesis_map": synthesis_map(self.verified.plan, self.verified.research_data_plan, findings,
                                                    groups),
            "released_contents": (last or {}).get("released_contents") or [],
            # A: every group's released outputs (the previews above are the last group's only)
            "released_outputs": [{**o, "session_id": session_id} for session_id, c in self.completions.items()
                                 if c.get("status") == "COMPLETED" for o in c.get("released_outputs") or []
                                 if isinstance(o, dict)],
            "next_action": "ANSWER_FROM_RESEARCH_FINDINGS" if status == "COMPLETED" else "REPORT_LIMITATION"}
        return self.result

    @staticmethod
    def _incomplete_code(completion: dict[str, Any]) -> str:
        """Why a finalized group could not complete, as a close reason."""
        if completion.get("status") == "REJECTED":
            return str(completion.get("close_reason") or completion.get("code") or "GROUP_INCOMPLETE")
        final = completion.get("final_status") or {}
        if final.get("data_coverage") not in (None, "PASS"):
            return "COVERAGE_FAILED"
        if final.get("sandbox_execution") not in (None, "SUCCESS"):
            return f"EXECUTION_{final.get('sandbox_execution')}"
        return "GROUP_INCOMPLETE"

    def _early_finalize(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """(INCOMPLETE naming the unrecorded angles of the open group and the groups never run, or None when nothing
        is missing; the completion of the open group, completed without finalize, which records nothing as NOT_RUN)."""
        missing: list[str] = []
        group_id = self.open_group
        completion: dict[str, Any] | None = None
        if group_id is not None:
            completion = self._complete(group_id, finalize=False)
            if completion.get("status") != "COMPLETED":
                research = (completion.get("final_status") or {}).get("research_group") or {}
                missing = [str(a) for a in research.get("missing") or []] or list(self.groups[group_id]["angle_ids"])
        pending = [g for g in self.order if self.groups[g]["status"] in ("READY", "APPROVED")]
        if not missing and not pending:
            return None, completion
        not_run = sorted({a for g in pending for a in self.groups[g]["angle_ids"]})
        return {"status": "INCOMPLETE", "code": "ANGLES_NOT_RECORDED", "bundle_group_id": group_id if missing else None,
                "missing_angle_ids": missing, "groups_not_run": pending, "angles_of_groups_not_run": not_run,
                "message": "Finalize was not applied: approved angles are not recorded yet. Record each missing angle "
                           "with run_research_code (its helper and the example call of the session's research view)"
                           + (f" in group {group_id}" if missing else "")
                           + (f", and run groups {pending}" if pending else "")
                           + ", then call complete_research_run with finalize false. Call finalize true again only "
                             "for an angle that cannot be recorded; it then becomes NOT_RUN.",
                "next_action": "RECORD_MISSING_ANGLES"}, completion

    def _state(self, status: str) -> dict[str, Any]:
        return {"status": status, "research_run_id": self.research_run_id,
                "groups": [{k: self.groups[g].get(k) for k in ("bundle_group_id", "angle_ids", "status", "reason",
                                                               "datasets", "warnings", "session_id", "empty_datasets")}
                           for g in self.order]}

    def open_sessions(self) -> list[str]:
        return [s for s, info in self.sessions.items()
                if self.groups[info["bundle_group_id"]]["status"] not in ("COMPLETED",)]


START_DESCRIPTION = (
    "Start the approved multi-angle Research Plan: the backend promotes the plan's checked data into one governed "
    "bundle per bundle group, extracts and verifies it, and opens the first group's analysis session. Returns the "
    "groups (angles, datasets, status) and the open session with each angle's helper, approved values and data "
    "contract. A group whose data cannot be prepared is FAILED and its angles NOT_RUN.")
RUN_DESCRIPTION = (
    "Run Python in one bundle group's session (the helpers of run_python plus saniti.research_conditional, "
    "research_persistence, research_group_comparison, research_quantiles, research_temporal_dependency and "
    "research_custom). Record every angle of the group exactly once with its helper, starting from the angle's example "
    "call in the session's research view: request is the data request id string, each role an expression over that "
    "request's columns, and the outcome {'forward_return': '<price column>'}, with 'request': '<request id>' added "
    "when the price column is in another request of the angle's contract (the backend computes it over the approved "
    "horizon; never a price level or a trailing return column). The thresholds, lags, buckets, groups and horizon "
    "come from the approved plan. Moving to another group completes the open one first. Read every dataset of the "
    "group through the saniti helpers.")
COMPLETE_DESCRIPTION = (
    "Complete the research run: the backend validates the open group (coverage, one recorded input per approved "
    "angle) and recomputes every angle's statistics independently, then returns one backend finding per angle "
    "(SUPPORTED, PARTIALLY_SUPPORTED, INSUFFICIENT_EVIDENCE, INVALID or NOT_RUN, with its validation level), the "
    "angle completion counts and the research synthesis map. With finalize false it reports what is still missing; "
    "record those angles and call it again. finalize true accepts the result as it stands (unrecorded angles become "
    "NOT_RUN); while an approved angle is unrecorded the first finalize true is answered with the missing angles "
    "instead. Answer only from these findings.")


def executor_specs(*, timeout_seconds: float, execution_timeout_seconds: float, max_result_bytes: int) -> list[ToolSpec]:
    def executor() -> ResearchRunExecutor | None:
        context = current_research_context.get()
        return context.executor if context is not None else None

    def refused() -> dict[str, Any]:
        return {"status": "REJECTED", "code": "NO_APPROVED_MULTI_ANGLE_PLAN",
                "message": "These tools run only an approved multi-angle Research Plan in the message that approved "
                           "it.", "next_action": "RETURN_RESEARCH_PLAN_CONFIRMATION"}

    def start(arguments: BaseModel) -> dict[str, Any]:
        run = executor()
        return run.start() if run is not None else refused()

    def run_code(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, RunResearchCodeArgs)
        run = executor()
        return run.run(arguments.bundle_group_id, arguments.code) if run is not None else refused()

    def complete(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, CompleteResearchRunArgs)
        run = executor()
        if run is None:
            return refused()
        context = current_research_context.get()
        calls_left = context.calls_left() if context is not None and callable(context.calls_left) else None
        return run.complete(arguments.finalize, calls_left)

    return [
        ToolSpec(name="start_research_run", effect="COMPUTES", description=START_DESCRIPTION, arguments_model=StartResearchRunArgs,
                 handler=start, timeout_seconds=timeout_seconds * 20, max_result_bytes=max_result_bytes),
        ToolSpec(name="run_research_code", effect="COMPUTES", description=RUN_DESCRIPTION, arguments_model=RunResearchCodeArgs,
                 handler=run_code, timeout_seconds=execution_timeout_seconds + timeout_seconds * 4,
                 max_result_bytes=max_result_bytes),
        ToolSpec(name="complete_research_run", effect="COMPUTES", description=COMPLETE_DESCRIPTION,
                 arguments_model=CompleteResearchRunArgs, handler=complete, timeout_seconds=timeout_seconds * 8,
                 max_result_bytes=max_result_bytes),
    ]


__all__ = ["CompleteResearchRunArgs", "ResearchContext", "ResearchRunExecutor", "RunResearchCodeArgs",
           "remember_feasibility",
           "StartResearchRunArgs", "current_research_context", "executor_specs", "synthesis_map", "weakest",
           "SESSION_PATTERN"]
