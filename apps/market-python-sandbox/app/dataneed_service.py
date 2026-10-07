"""The DataNeed flow of the sandbox service: validation of DataNeedSpecs (with the Research Governor for RESEARCH),
governed bundles, persistent analysis sessions, and completion with the Coverage Validator.

This module owns only the new flow. It reuses the analysis service's dataset provider (Governor grants and the
verified dataset cache), executor, isolation self-test and settings, so the security boundaries are the same ones.
"""
from __future__ import annotations

import json
import logging
import secrets
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .bundles import BundleBuilder, BundleError, row_counts
from .bundles import model_view as bundle_view
from .coverage import execution_manifest, processing_coverage
from .data_need import (COMPLETENESS_RULE, DEFAULT_TIME_BASIS, NULL_POLICY, PERIOD_POLICY, Limits, contract_tables,
                        aliased_manifest, contract_alias, data_contract_sha256, sha256_json, summary_options,
                        validate)
from .datasets import DatasetFailure
from .dataneed_store import DRAFT_RETENTION_DAYS, DataNeedStore
from .records import utc_now
from .research_governance import GOVERNANCE_V2, check_request, check_request_v2, review_v2
from . import findings_table
from .research_findings import evaluate as evaluate_findings
from .research_methods import sha256_json as research_sha256
from .sessions import SessionError, SessionManager
from .research_governance import review as governance_review
from . import backtest_validation, event_study_validation, research_validation

# outputs only the saniti helpers write (runtime/saniti_session.py RESEARCH_RESERVED): records the backend recomputes
# from, released for the audit but never offered as results
BACKEND_RECORDS = ("research_input_", "research_call_", event_study_validation.PREFIX, backtest_validation.PREFIX)

logger = logging.getLogger("market_python_sandbox")

NEXT_ACTION = {"APPROVED": "PREPARE_DATA_BUNDLE", "REVISION_REQUIRED": "REVISE_DATA_NEED_SPEC",
               "CATALOG_UNAVAILABLE": "STOP_TEMPORARILY"}


class DataNeedError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 422, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details

    def body(self) -> dict[str, Any]:
        details = dict(self.details)
        action = details.pop("next_action", None)
        body: dict[str, Any] = {"status": "REJECTED", "error": {"code": self.code, "message": self.message, **details}}
        if action:
            body["next_action"] = action
        return body


def _summary_hint(request: dict[str, Any], contract: dict[str, Any] | None, mode: str | None) -> dict[str, Any]:
    """G18: a raw ANALYSIS request whose requested columns could be summarised in the warehouse names that option
    ({"summary_available": ...}), derived from the catalog, so the model knows before it pulls every raw row."""
    if mode != "ANALYSIS" or not contract:
        return {}
    meta = (contract.get("tables") or {}).get(request["source_table"]) or {}
    known = (contract.get("columns") or {}).get(request["source_table"]) or {}
    options = summary_options(meta, known, list(request.get("columns") or []))
    if options is None or not options["sum_across_entities"]:
        return {}
    return {"summary_available": {
        **options, "note": "These columns add up across entities: a total per group can be asked with this request's "
                           "aggregate (one row per group instead of every raw row). Raw rows stay right when the "
                           "analysis needs each row (a median, a percentile, a per-entity series)."}}


def reference_date(reference_time: datetime, tz: str) -> date:
    try:
        zone = ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    moment = reference_time if reference_time.tzinfo else reference_time.replace(tzinfo=ZoneInfo("UTC"))
    return moment.astimezone(zone).date()


def undefined_outputs(outputs: list[dict[str, Any]]) -> list[str]:
    """H1: the names of tables and JSON results whose latest version has no definition (backend records and charts or
    text are exempt; the latest output of a name counts, so emitting it again with a definition fixes it)."""
    latest: dict[str, dict[str, Any]] = {}
    for output in outputs:
        latest[str(output.get("name") or "")] = output
    missing = []
    for name, output in latest.items():
        if output.get("type") not in ("TABLE", "JSON") or name.startswith(BACKEND_RECORDS):
            continue
        meta = output.get("meta") if isinstance(output.get("meta"), dict) else {}
        if not isinstance(meta.get("definition"), dict):
            missing.append(name)
    return missing


def data_as_of(manifest: dict[str, Any]) -> dict[str, Any]:
    """{data_as_of, reference_date} of a bundle (R-STORE, round 2026-10-03 C2c): the largest actual end date of its
    requested ranges (the last date of the data an output was computed from) and the reference date it was bound
    to; a static bundle has no data_as_of."""
    ends = [str(r["actual_end"])[:10] for d in manifest.get("datasets") or []
            for r in (d.get("quality") or {}).get("requested_ranges") or [] if r.get("actual_end")]
    return {"data_as_of": max(ends) if ends else None, "reference_date": manifest.get("reference_date")}


class DataNeedService:
    def __init__(self, analysis: Any, store: DataNeedStore, limits: Limits = Limits()) -> None:
        self.analysis = analysis
        self.settings = analysis.settings
        self.store = store
        # IP2: the derived-frequency semantics follow the service flag (a caller-supplied Limits keeps its own value)
        self.limits = (replace(limits, derived_frequency=True)
                       if getattr(self.settings, "derived_frequency_enabled", False) else limits)
        self.policy = self.settings.governance_policy()
        self.bundles = BundleBuilder(analysis, store)
        self.sessions = SessionManager(analysis, store, self.bundles)
        # IP2 solution 2: archive to market-audit-store from the harness (off by default)
        self.audit = None
        if getattr(self.settings, "audit_store_enabled", False):
            from .audit import AuditOutbox

            self.audit = AuditOutbox(self.settings)
            self.sessions.audit = self.audit

    @staticmethod
    def _log(event: str, **fields: Any) -> None:
        logger.info(json.dumps({"event": event, **fields}, default=str, separators=(",", ":")))

    # ------------------------------------------------------------------------------------------ data need specs

    def submit(self, request_id: str, reference_time: datetime, tz: str, spec: Any,
               governance: Any | None, conversation_key: str | None = None, as_of: date | None = None
               ) -> dict[str, Any]:
        """Validate one DataNeedSpec revision; RESEARCH specs also go to the Research Governor. conversation_key
        (conversation reuse only) records which conversation the need belongs to, with its data contract hash."""
        key = conversation_key if self.settings.conversation_reuse else None
        ref = reference_date(reference_time, tz)
        submitted = {"spec": spec, "research_governance": governance}
        submitted_sha = sha256_json(submitted)
        group = spec.get("request_group_id") if isinstance(spec, dict) else None
        revision = spec.get("revision") if isinstance(spec, dict) else None
        # A revision number is consumed only by a submission the validator judged: a catalog outage or a sequencing
        # conflict leaves it free, so the same revision can be sent again.
        earlier = [n for n in (self.store.needs_for_group(request_id, group) if isinstance(group, str) else [])
                   if n["status"] != "CATALOG_UNAVAILABLE"
                   and not any(i["code"] == "REVISION_CONFLICT" for i in n["result"]["issues"])]
        same = [n for n in earlier if n["revision"] == revision]
        if same:
            if same[-1]["spec_sha256"] == submitted_sha:
                return {**same[-1]["result"], "replayed": True}
            return self._record(request_id, spec, governance, submitted, submitted_sha, key, {
                "status": "REVISION_REQUIRED", "warnings": [], "issues": [{
                    "data_request_id": None, "code": "REVISION_CONFLICT", "field_path": "revision",
                    "rejected_value": revision}]}, None, None)
        expected = max((n["revision"] for n in earlier if isinstance(n["revision"], int)), default=0) + 1
        if isinstance(revision, int) and not isinstance(revision, bool) and revision != expected:
            return self._record(request_id, spec, governance, submitted, submitted_sha, key, {
                "status": "REVISION_REQUIRED", "warnings": [], "issues": [{
                    "data_request_id": None, "code": "REVISION_CONFLICT", "field_path": "revision",
                    "rejected_value": revision}]}, None, None, expected_revision=expected)

        contract: dict[str, Any] | None = {"tables": {}, "columns": {}, "relationships": []}
        tables = contract_tables(spec) if isinstance(spec, dict) else []
        if tables:
            try:
                contract = self.analysis.datasets.catalog_contract(tables, request_id=request_id)
            except DatasetFailure:
                contract = None
        outcome = validate(spec, contract, ref, self.limits, latest_bound=as_of)
        body = outcome.body()
        mode = spec.get("mode") if isinstance(spec, dict) else None
        research = None
        if outcome.status != "CATALOG_UNAVAILABLE":
            extra: list[dict[str, Any]] = []
            if mode == "RESEARCH":
                if governance is None:
                    extra.append({"data_request_id": None, "code": "MISSING_REQUIRED_FIELD",
                                  "field_path": "research_governance", "rejected_value": None})
                else:
                    extra.extend(check_request(governance, self.policy.findings_fields_required))
            elif mode == "ANALYSIS" and governance is not None:
                extra.append({"data_request_id": None, "code": "MODE_MISMATCH", "field_path": "research_governance",
                              "rejected_value": "research_governance is only for mode RESEARCH"})
            if extra:
                body = {**body, "status": "REVISION_REQUIRED", "issues": body["issues"] + extra}
        approved = outcome.approved if body["status"] == "APPROVED" else None
        if approved is not None and mode == "RESEARCH":
            history = [{"request_group_id": n["request_group_id"], "revision": n["revision"],
                        "governance": n["governance"]}
                       for n in self.store.needs_for_request(request_id)
                       if n["mode"] == "RESEARCH" and n["extraction_allowed"]]
            research = governance_review(governance, spec, history, len(earlier), self.policy)
        return self._record(request_id, spec, governance, submitted, submitted_sha, key, body, approved, research,
                            contract=contract)

    def _record(self, request_id: str, spec: Any, governance: Any, submitted: dict[str, Any], submitted_sha: str,
                conversation_key: str | None, body: dict[str, Any], approved: dict[str, Any] | None,
                research: dict[str, Any] | None, *, contract: dict[str, Any] | None = None,
                **extra: Any) -> dict[str, Any]:
        mode = spec.get("mode") if isinstance(spec, dict) else None
        status = body["status"]
        allowed = status == "APPROVED" and (mode != "RESEARCH" or (research or {}).get("decision") == "APPROVED")
        need_id = f"need_{secrets.token_hex(12)}"
        if status != "APPROVED":
            next_action = NEXT_ACTION[status]
        elif research is not None and research["decision"] != "APPROVED":
            next_action = "REVISE_DATA_NEED_SPEC" if research["decision"] == "REPLAN_REQUIRED" else "REPORT_LIMITATION"
        else:
            next_action = NEXT_ACTION["APPROVED"]
        result = {
            "status": status, "need_id": need_id if allowed else None,
            "request_group_id": spec.get("request_group_id") if isinstance(spec, dict) else None,
            "revision": spec.get("revision") if isinstance(spec, dict) else None,
            "issues": body.get("issues") or [], "warnings": body.get("warnings") or [],
            "research_governance": research if mode == "RESEARCH" else {"decision": "NOT_APPLICABLE"},
            "extraction_allowed": allowed, "next_action": next_action, **extra}
        if allowed and approved is not None:
            result["approved"] = {
                "spec_sha256": approved["spec_sha256"], "reference_date": approved["reference_date"],
                "time_basis": approved.get("time_basis") or DEFAULT_TIME_BASIS,
                "catalog_sha256": approved["catalog_sha256"],
                "requests": [{"data_request_id": r["data_request_id"], "logical_name": r["logical_name"],
                              "source_table": r["source_table"], "extract_columns": r["extract_columns"],
                              "ranges": r["windows"], "scope_sha256": r["scope_sha256"],
                              # H1 (M63): the row filter itself, readable, so a later turn reads the definition of
                              # the data instead of guessing it (DERIVED: the backend applied it at extraction)
                              "scope": r.get("scope"),
                              "restricted_by": [x["relationship_id"] for x in r["restrictions"]],
                              "restrictions": [{"relationship_id": x["relationship_id"],
                                                "right_table": x.get("right_table"),
                                                "right_scope": x.get("right_scope")} for x in r["restrictions"]],
                              # G18: a summary names what the warehouse computes and the grain it delivers; a raw
                              # analysis request whose columns could be summarised says so (derived from the catalog)
                              **({"aggregate": r["aggregate"], "key_columns": r["key_columns"]}
                                 if r.get("aggregate") else _summary_hint(r, contract, mode))}
                             for r in approved["requests"].values()]}
        self.store.insert_need({
            "need_id": need_id, "request_id": request_id,
            "request_group_id": result["request_group_id"] if isinstance(result["request_group_id"], str) else None,
            "revision": result["revision"] if isinstance(result["revision"], int) else None, "mode": mode,
            "status": status, "spec_sha256": submitted_sha, "submitted": submitted, "result": result,
            "approved": {**approved, "research_governance": research} if allowed and approved else None,
            "governance": governance, "research": research, "extraction_allowed": int(allowed),
            "created_at": utc_now(), "conversation_key": conversation_key,
            "contract_sha256": data_contract_sha256(approved) if allowed and approved else None})
        self._log("data_need_reviewed", request_id=request_id, need_id=need_id if allowed else None,
                  request_group_id=result["request_group_id"], revision=result["revision"], status=status,
                  mode=mode, research=(research or {}).get("decision"), issues=[i["code"] for i in result["issues"]],
                  warnings=[w["code"] for w in result["warnings"]])
        return result

    def check(self, request_id: str, reference_time: datetime, tz: str, spec: Any, as_of: date | None = None
              ) -> dict[str, Any]:
        """Research Plan feasibility: validate a DataNeedSpec with all four layers before any plan is approved, without
        a revision, a Research Governor review or anything extractable. An approved spec is kept as a draft (draft_id)
        whose approved contract the backend planner sends to the Governor as estimate-only extractions; mode RESEARCH
        needs no research_governance here (the governance is declared, and reviewed, when the approved plan runs)."""
        ref = reference_date(reference_time, tz)
        contract: dict[str, Any] | None = {"tables": {}, "columns": {}, "relationships": []}
        tables = contract_tables(spec) if isinstance(spec, dict) else []
        if tables:
            try:
                contract = self.analysis.datasets.catalog_contract(tables, request_id=request_id)
            except DatasetFailure:
                contract = None
        outcome = validate(spec, contract, ref, self.limits, latest_bound=as_of)
        body = outcome.body()
        result: dict[str, Any] = {"status": body["status"], "draft_id": None, "issues": body["issues"],
                                  "warnings": body["warnings"], "next_action": NEXT_ACTION[body["status"]]}
        if body["status"] == "APPROVED" and outcome.approved is not None:
            draft_id = f"draft_{secrets.token_hex(12)}"
            result.update(draft_id=draft_id, next_action="ESTIMATE_EXTRACTION")
            now = datetime.now(timezone.utc)
            self.store.insert_draft({
                "draft_id": draft_id, "request_id": request_id, "submitted": {"spec": spec},
                "approved": outcome.approved, "result": result, "contract_sha256": data_contract_sha256(outcome.approved),
                "created_at": now.isoformat()}, purge_before=(now - timedelta(days=DRAFT_RETENTION_DAYS)).isoformat())
        self._log("data_need_draft_checked", request_id=request_id, draft_id=result["draft_id"], status=body["status"],
                  issues=[i["code"] for i in body["issues"]], warnings=[w["code"] for w in body["warnings"]])
        return result

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        """A feasibility draft: its spec and approved contract, in the planner's need shape (need_id = draft_id)."""
        record = self.store.get_draft(draft_id)
        if record is None:
            return None
        return {"need_id": draft_id, "draft_id": draft_id, "request_id": record["request_id"],
                "spec": record["submitted"]["spec"], "created_at": record["created_at"],
                "contract_sha256": record["contract_sha256"], "warnings": record["result"].get("warnings") or [],
                **record["approved"]}

    def get_need(self, need_id: str) -> dict[str, Any] | None:
        """The approved contract (backend use: the planner and the bundle builder)."""
        record = self.store.get_need(need_id)
        if record is None or not record["extraction_allowed"]:
            return None
        return {"need_id": need_id, "request_id": record["request_id"],
                "warnings": record["result"].get("warnings") or [], **record["approved"]}

    # ------------------------------------------------------------------------------------------ multi-angle research

    def _multi_angle(self) -> None:
        if not self.settings.multi_angle_research_enabled:
            raise DataNeedError("MULTI_ANGLE_RESEARCH_DISABLED", "Multi-angle research is not enabled.", http_status=404)

    def promote_research(self, request_id: str, origin_request_id: str, governance: Any,
                         data_plan: Any, conversation_key: str | None = None) -> dict[str, Any]:
        """Promote the signed feasibility drafts of an approved research_plan/v2 into one approved RESEARCH need per
        bundle group, after the Research Governor v2 approved the declaration. Every draft must be the one the plan
        was checked against (its spec hash and data contract hash) and belong to the request that proposed the plan;
        nothing is re-planned here and the model never rebuilds a spec."""
        self._multi_angle()
        policy = self.settings.multi_angle_policy()
        issues = check_request_v2(governance, policy)
        plan_sha = research_sha256({k: v for k, v in data_plan.items() if k != "research_data_plan_sha256"}) \
            if isinstance(data_plan, dict) else None
        for run in self.store.research_runs_for(request_id):
            if plan_sha and run["data_plan_sha256"] == plan_sha and isinstance(governance, dict) \
                    and run["plan_id"] == governance.get("plan_id"):
                return {**self.research_run(request_id, run["research_run_id"]), "replayed": True}
        groups: list[dict[str, Any]] = []
        drafts: dict[str, dict[str, Any]] = {}
        if not issues:
            issues += self._check_data_plan(origin_request_id, governance, data_plan, plan_sha, drafts)
            groups = data_plan.get("bundle_groups") or [] if not issues else []
        if issues:
            self._log("research_run_rejected", request_id=request_id, issues=[i["code"] for i in issues][:20])
            return {"status": "REJECTED", "error": {"code": "RESEARCH_RUN_INVALID", "message": "The approved plan's "
                    "research governance or data plan does not verify.", "issues": issues[:20]},
                    "next_action": "REPORT_LIMITATION"}
        history = [{"governance": r["governance"]} for r in self.store.research_runs_for(request_id)]
        decision = review_v2(governance, history, policy)
        if decision["decision"] != "APPROVED":
            self._log("research_run_rejected", request_id=request_id, decision=decision["decision"],
                      reason=decision["reason_code"])
            return {"status": decision["decision"], "error": {"code": decision["reason_code"],
                                                              "message": decision["message"]},
                    "budget": decision["budget"], "next_action": "REPORT_LIMITATION"}
        run_id = f"rrun_{secrets.token_hex(12)}"
        now = utc_now()
        contracts = data_plan.get("angle_data_contracts") or {}
        base_policy = self.policy
        group_rows, needs = [], []
        for group in groups:
            draft = drafts[group["draft_id"]]
            angle_ids = list(group["angle_ids"])
            angles = {}
            for angle_id in angle_ids:
                angle = dict(decision["constraints"]["angles"][angle_id])
                contract = contracts[angle_id]
                angle.update(angle_id=angle_id, contract=contract,
                             holdout_start=research_validation.holdout_start(contract)
                             if angle.get("holdout_required") else None)
                angles[angle_id] = angle
            research = {"decision": "APPROVED", "reason_code": None, "message": None, "budget": decision["budget"],
                        "constraints": {"governance_version": GOVERNANCE_V2, "research_run_id": run_id,
                                        "bundle_group_id": group["bundle_group_id"],
                                        "plan_id": governance["plan_id"],
                                        "root_hypothesis_id": governance["root_hypothesis_id"],
                                        "compute_seconds": base_policy.compute_seconds_per_experiment
                                        * max(1, len(angle_ids)), "angles": angles}}
            spec = draft["submitted"]["spec"]
            approved = draft["approved"]
            need_id = f"need_{secrets.token_hex(12)}"
            submitted = {"spec": spec, "research_governance": governance, "promoted_from_draft": group["draft_id"]}
            result = {"status": "APPROVED", "need_id": need_id, "request_group_id": spec.get("request_group_id"),
                      "revision": spec.get("revision"), "issues": [],
                      "warnings": draft["result"].get("warnings") or [], "research_governance": research,
                      "extraction_allowed": True, "next_action": "PREPARE_DATA_BUNDLE",
                      "promoted_from_draft": group["draft_id"]}
            needs.append({"need_id": need_id, "request_id": request_id,
                          "request_group_id": spec.get("request_group_id"), "revision": spec.get("revision"),
                          "mode": "RESEARCH", "status": "APPROVED", "spec_sha256": research_sha256(submitted),
                          "submitted": submitted, "result": result,
                          "approved": {**approved, "research_governance": research}, "governance": governance,
                          "research": research, "extraction_allowed": 1, "created_at": now,
                          # M47: research data belongs to the conversation too (offered and reusable later)
                          "conversation_key": conversation_key,
                          "contract_sha256": draft.get("contract_sha256")})
            group_rows.append({"research_run_id": run_id, "bundle_group_id": group["bundle_group_id"],
                               "need_id": need_id, "draft_id": group["draft_id"], "spec_sha256": group["spec_sha256"],
                               "angle_ids": angle_ids, "status": "APPROVED", "reason": None, "session_id": None,
                               "completion_id": None, "updated_at": now})
        for need in needs:
            self.store.insert_need(need)
        self.store.insert_research_run({"research_run_id": run_id, "request_id": request_id,
                                        "origin_request_id": origin_request_id, "plan_id": governance["plan_id"],
                                        "plan_sha256": governance["hashes"]["plan_sha256"],
                                        "data_plan_sha256": plan_sha, "governance": governance,
                                        "data_plan": data_plan, "decision": decision, "status": "APPROVED",
                                        "created_at": now}, group_rows)
        self._log("research_run_approved", request_id=request_id, research_run_id=run_id,
                  plan_id=governance["plan_id"], groups=len(group_rows), angles=len(governance["angles"]))
        return self.research_run(request_id, run_id)

    def _check_data_plan(self, origin_request_id: str, governance: dict[str, Any], data_plan: Any,
                         plan_sha: str | None, drafts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []

        def add(code: str, path: str, value: Any) -> None:
            issues.append({"data_request_id": None, "code": code, "field_path": f"research_data_plan{path}",
                           "rejected_value": value if not isinstance(value, (dict, list)) else str(value)[:200]})

        if not isinstance(data_plan, dict) or data_plan.get("data_plan_version") != "research_data_plan/v1" \
                or data_plan.get("strategy") not in ("SINGLE_BUNDLE", "MULTI_BUNDLE"):
            add("DATA_PLAN_INVALID", "", None)
            return issues
        if data_plan.get("research_data_plan_sha256") != plan_sha:
            add("DATA_PLAN_HASH_MISMATCH", ".research_data_plan_sha256", data_plan.get("research_data_plan_sha256"))
        hashes = governance["hashes"]
        groups = data_plan.get("bundle_groups") or []
        contracts = data_plan.get("angle_data_contracts") or {}
        if hashes.get("research_data_plan_sha256") != plan_sha:
            add("GOVERNANCE_DATA_PLAN_MISMATCH", ".research_data_plan_sha256", hashes.get("research_data_plan_sha256"))
        if hashes.get("draft_ids") != [g.get("draft_id") for g in groups]:
            add("GOVERNANCE_DRAFTS_MISMATCH", ".bundle_groups", hashes.get("draft_ids"))
        if hashes.get("spec_sha256s") != [g.get("spec_sha256") for g in groups]:
            add("GOVERNANCE_SPECS_MISMATCH", ".bundle_groups", hashes.get("spec_sha256s"))
        if data_plan.get("angle_to_bundle_group") != governance.get("angle_to_bundle_group"):
            add("ANGLE_GROUP_MISMATCH", ".angle_to_bundle_group", data_plan.get("angle_to_bundle_group"))
        computed = {}
        for angle_id, contract in contracts.items():
            body = {k: v for k, v in contract.items() if k != "angle_data_contract_sha256"} \
                if isinstance(contract, dict) else None
            computed[angle_id] = research_sha256(body) if body is not None else None
            if not isinstance(contract, dict) or contract.get("angle_data_contract_sha256") != computed[angle_id]:
                add("ANGLE_CONTRACT_HASH_MISMATCH", f".angle_data_contracts.{angle_id}", angle_id)
        if hashes.get("angle_data_contract_sha256s") != computed:
            add("GOVERNANCE_CONTRACTS_MISMATCH", ".angle_data_contracts", sorted(computed))
        for angle in governance["angles"]:
            if computed.get(angle["angle_id"]) != angle.get("angle_data_contract_sha256"):
                add("ANGLE_CONTRACT_HASH_MISMATCH", f".angles.{angle['angle_id']}", angle["angle_id"])
        covered = [a for g in groups for a in g.get("angle_ids") or []]
        if sorted(covered) != sorted(a["angle_id"] for a in governance["angles"]) or len(covered) != len(set(covered)):
            add("ANGLE_COVERAGE_MISMATCH", ".bundle_groups", covered)
        for index, group in enumerate(groups):
            draft = self.store.get_draft(str(group.get("draft_id")))
            path = f".bundle_groups[{index}]"
            if draft is None:
                add("DRAFT_NOT_FOUND", f"{path}.draft_id", group.get("draft_id"))
                continue
            if draft["request_id"] != origin_request_id:
                add("DRAFT_OTHER_REQUEST", f"{path}.draft_id", group.get("draft_id"))
            if research_sha256(draft["submitted"]["spec"]) != group.get("spec_sha256"):
                add("DRAFT_SPEC_MISMATCH", f"{path}.spec_sha256", group.get("spec_sha256"))
            if group.get("data_contract_sha256") != draft.get("contract_sha256"):
                add("DRAFT_CONTRACT_MISMATCH", f"{path}.data_contract_sha256", group.get("data_contract_sha256"))
            if (draft["submitted"]["spec"] or {}).get("mode") != "RESEARCH":
                add("DRAFT_MODE_MISMATCH", f"{path}.draft_id", group.get("draft_id"))
            for angle_id in group.get("angle_ids") or []:
                contract = contracts.get(angle_id) or {}
                if contract.get("bundle_group_id") != group.get("bundle_group_id") \
                        or contract.get("data_contract_sha256") != draft.get("contract_sha256"):
                    add("ANGLE_CONTRACT_GROUP_MISMATCH", f".angle_data_contracts.{angle_id}", angle_id)
                elif contract and any(d.get("data_request_id") not in {r["data_request_id"] for r in
                                                                       draft["approved"]["requests"].values()}
                                      for d in contract.get("datasets") or []):
                    add("ANGLE_CONTRACT_REQUEST_UNKNOWN", f".angle_data_contracts.{angle_id}", angle_id)
            drafts[group["draft_id"]] = draft
        for angle in governance["angles"]:
            if angle.get("holdout_required") and research_validation.holdout_start(contracts.get(angle["angle_id"])
                                                                                   or {}) is None:
                add("HOLDOUT_RANGE_MISSING", f".angle_data_contracts.{angle['angle_id']}", angle["angle_id"])
        return issues

    def research_run(self, request_id: str, research_run_id: str) -> dict[str, Any]:
        """The grouped state of one research run: groups (need, session, completion, terminal state) and the
        backend findings recorded so far."""
        run = self.store.get_research_run(research_run_id)
        if run is None or run["request_id"] != request_id:
            raise DataNeedError("RESEARCH_RUN_NOT_FOUND", "No research run with this id exists for this request.",
                                http_status=404)
        groups = self.store.research_groups(research_run_id)
        findings = self.store.research_findings(research_run_id)
        return {"status": run["status"], "research_run_id": research_run_id, "plan_id": run["plan_id"],
                "data_plan_sha256": run["data_plan_sha256"],
                "groups": [{k: g[k] for k in ("bundle_group_id", "need_id", "draft_id", "angle_ids", "status", "reason",
                                              "session_id", "completion_id")} for g in groups],
                "findings": [f["finding"] for f in findings],
                "angles": [a["angle_id"] for a in run["governance"]["angles"]]}

    def close_research_group(self, request_id: str, research_run_id: str, bundle_group_id: str,
                             reason: str) -> dict[str, Any]:
        """A bundle group that cannot run (its bundle, session or execution limits failed) becomes FAILED and each of
        its angles without a finding gets a backend-authored NOT_RUN finding, so no angle disappears."""
        self._multi_angle()
        view = self.research_run(request_id, research_run_id)
        group = next((g for g in view["groups"] if g["bundle_group_id"] == bundle_group_id), None)
        if group is None:
            raise DataNeedError("RESEARCH_GROUP_NOT_FOUND", "No such bundle group in this research run.",
                                http_status=404)
        if group["status"] in ("COMPLETED", "FAILED"):
            return {**view, "replayed": True}
        run = self.store.get_research_run(research_run_id)
        angles = {a["angle_id"]: a for a in run["governance"]["angles"]}
        recorded = {f["angle_id"] for f in view["findings"]}
        context = {"plan_id": run["plan_id"], "research_run_id": research_run_id, "bundle_group_id": bundle_group_id,
                   "session_id": group.get("session_id"),
                   "hashes": {"plan_sha256": run["plan_sha256"], "research_data_plan_sha256": run["data_plan_sha256"]}}
        code = str(reason or "GROUP_FAILED")[:60]
        for angle_id in group["angle_ids"]:
            if angle_id in recorded:
                continue
            finding = research_validation.envelope(context, angle_id, angles[angle_id], status="NOT_RUN",
                                                   reason=code, level=None)
            self.store.upsert_research_finding({"research_run_id": research_run_id, "angle_id": angle_id,
                                                "bundle_group_id": bundle_group_id,
                                                "session_id": group.get("session_id"), "completion_id": None,
                                                "status": "NOT_RUN", "validation_level": None, "finding": finding,
                                                "created_at": utc_now()})
        self.store.update_research_group(research_run_id, bundle_group_id, status="FAILED", reason=code,
                                         updated_at=utc_now())
        self._log("research_group_failed", request_id=request_id, research_run_id=research_run_id,
                  bundle_group_id=bundle_group_id, reason=code)
        return self.research_run(request_id, research_run_id)

    # ------------------------------------------------------------------------------------------ governed bundles

    BUNDLE_ACTIONS = {"BUNDLE_TOO_LARGE": "REVISE_DATA_NEED_SPEC", "NEED_NOT_FOUND": "SUBMIT_DATA_NEED_SPEC",
                      "REQUEST_BUDGET_EXCEEDED": "REPORT_LIMITATION", "DATA_QUALITY_PROFILING_FAILED": "RETRY_LATER",
                      "DATASET_EXPIRED": "PREPARE_DATA_BUNDLE", "DATASET_NOT_FOUND": "PREPARE_DATA_BUNDLE"}

    def build_bundle(self, request_id: str, need_id: str, plan: Any) -> dict[str, Any]:
        """Verify, store, profile and cover the planner's extracted parts as one immutable bundle."""
        need = self.get_need(need_id)
        if need is None or need["request_id"] != request_id:
            raise DataNeedError("NEED_NOT_FOUND", "No approved data need with this need_id exists for this request.",
                                http_status=404, next_action="SUBMIT_DATA_NEED_SPEC")
        try:
            manifest = self.bundles.build(request_id, need, plan)
        except BundleError as exc:
            self._log("bundle_rejected", request_id=request_id, need_id=need_id, code=exc.code)
            raise DataNeedError(exc.code, exc.message, http_status=exc.http_status,
                                next_action=self.BUNDLE_ACTIONS.get(exc.code, "REPORT_LIMITATION"),
                                **exc.details) from exc
        key = (self.store.get_need(need_id) or {}).get("conversation_key")
        if key and self.settings.conversation_reuse:
            self.store.set_bundle_conversation(manifest["input_bundle_id"], key)
        view = bundle_view(manifest)
        coverage = manifest.get("coverage") or {}
        codes = sorted({i["code"] for r in coverage.get("requests") or [] for i in r.get("issues") or []})
        if manifest["status"] == "READY":
            view["next_action"] = "OPEN_ANALYSIS_SESSION"
        else:
            view["next_action"] = "REVISE_DATA_NEED_SPEC" if "CATALOG_CHANGED_SINCE_APPROVAL" in codes \
                else "REPORT_LIMITATION"
        self._log("bundle_built", request_id=request_id, need_id=need_id, bundle_id=manifest["input_bundle_id"],
                  status=manifest["status"], coverage=coverage.get("coverage_status"), issues=codes,
                  rows=manifest.get("row_count"), bytes=manifest.get("byte_count"),
                  quality_flags={d["data_request_id"]: (d.get("quality") or {}).get("quality_flags")
                                 for d in manifest["datasets"]}, replayed=manifest.get("replayed", False))
        return view

    # ------------------------------------------------------------------------------------------ analysis sessions

    def start(self, run_janitor: bool = True) -> None:
        self.sessions.start(run_janitor=run_janitor)
        if self.audit is not None and run_janitor:
            self.audit.start()

    def stop(self) -> None:
        self.sessions.stop()
        if self.audit is not None:
            self.audit.stop()

    def open_session(self, request_id: str, bundle_id: str, conversation_key: str | None = None,
                     carried_outputs: list[str] | None = None) -> dict[str, Any]:
        """A persistent session on a READY bundle; a RESEARCH need gets its approved compute budget.

        Conversation reuse (S2): a bundle of an earlier request is usable only through a binding to this request's
        own approved need (reuse_bundle); a WARM_IDLE session on that bundle in the same conversation is then
        attached with a new epoch instead of starting a new worker."""
        key = conversation_key if self.settings.conversation_reuse else None
        record = self.store.get_bundle(bundle_id)
        binding = self._binding_to_serve(request_id, record, key) if key and record is not None else None
        need_id = binding["need_id"] if binding else (record or {}).get("need_id")
        cpu, research_v2, mode, findings = None, None, None, None
        if need_id:
            need = self.store.get_need(need_id)
            mode = (need or {}).get("mode")
            research = (need or {}).get("research") or {}
            cpu = (research.get("constraints") or {}).get("compute_seconds")
            research_v2 = self._session_research(research)
            constraints = research.get("constraints") or {}
            if research_v2 is None and constraints.get("governance_version") != GOVERNANCE_V2:
                findings = constraints.get("findings") or None  # M28: research findings v1
        # A warm worker's namespace holds what its earlier epochs computed. 2c binds a need to a bundle of any mode, so
        # the mode decides the attach: a RESEARCH need always starts a fresh worker (it reads only its bundle and the
        # tables its approved plan names, with its own compute budget), and an ANALYSIS need never takes over a
        # research worker.
        # EXEC-V stage 2: a warm worker's namespace knows the labels it was opened with, so a need that reads the
        # bundle under other labels gets a new worker on the same files
        if key and record is not None and mode != "RESEARCH" and not (binding or {}).get("aliases") \
                and (binding is not None or record["request_id"] == request_id):
            for warm in self.store.warm_sessions(key):
                if warm.get("need_id") and (self.store.get_need(warm["need_id"]) or {}).get("mode") == "RESEARCH":
                    continue
                if warm["bundle_id"] == bundle_id and warm["session_id"] in self.sessions.workers:
                    try:
                        return self.sessions.attach(warm["session_id"], request_id, need_id, carried_outputs)
                    except SessionError:
                        continue
        return self.sessions.open(request_id, bundle_id, cpu_seconds=cpu, conversation_key=key, need_id=need_id,
                                  bound=binding is not None, research=research_v2, carried_outputs=carried_outputs,
                                  findings=findings)

    def _binding_to_serve(self, request_id: str, record: dict[str, Any], key: str) -> dict[str, Any] | None:
        """The binding whose need an open of this bundle serves, or None for the bundle's own need.

        Several needs of one request may share one bundle (EXEC-V stage 2: the same data asked again under other
        labels). They are served in the order they were prepared: the first that has no COMPLETED result yet; when
        all have one, the newest (the behaviour before several needs could share a bundle)."""
        bindings = [b for b in self.store.bindings_to(request_id, record["bundle_id"]) if b["conversation_key"] == key]
        if not bindings:
            return None
        waiting: list[dict[str, Any] | None] = [None] if record["request_id"] == request_id else []
        waiting += bindings
        done = {c["need_id"] for c in self.store.completions_for(request_id)
                if (c.get("final_status") or {}).get("status") == "COMPLETED"}
        for candidate in waiting:
            if (candidate["need_id"] if candidate else record["need_id"]) not in done:
                return candidate
        return bindings[-1]

    def _session_research(self, research: dict[str, Any]) -> dict[str, Any] | None:
        """The research_v2 section of session.json for a need promoted by a multi-angle research run (flag on only)."""
        constraints = research.get("constraints") or {}
        if not self.settings.multi_angle_research_enabled or constraints.get("governance_version") != GOVERNANCE_V2:
            return None
        return {"version": 2, "research_run_id": constraints.get("research_run_id"),
                "bundle_group_id": constraints.get("bundle_group_id"), "plan_id": constraints.get("plan_id"),
                "angles": constraints.get("angles") or {}}

    def reuse_bundle(self, request_id: str, need_id: str, conversation_key: str | None) -> dict[str, Any]:
        """Conversation reuse (S1, 2c): bind this request's approved need to an earlier READY bundle of the same
        conversation whose need has the same data contract (data_contract_sha256) or one that covers it
        (contract_alias: any mode, same or wider columns, any request labels), so no extraction runs.
        The earlier bundle's manifest and checksum are unchanged; the binding records the lineage. NO_MATCH (with a
        reason) sends the caller to the normal planner."""
        if not self.settings.conversation_reuse or not conversation_key:
            raise DataNeedError("REUSE_UNAVAILABLE", "Conversation reuse is not enabled.", http_status=404)
        record = self.store.get_need(need_id)
        if record is None or record["request_id"] != request_id or not record["extraction_allowed"]:
            raise DataNeedError("NEED_NOT_FOUND", "No approved data need with this need_id exists for this request.",
                                http_status=404, next_action="SUBMIT_DATA_NEED_SPEC")
        if record.get("conversation_key") != conversation_key or not record.get("contract_sha256"):
            return {"status": "NO_MATCH", "reason": "NEED_NOT_IN_CONVERSATION"}
        existing = self.store.get_binding(need_id)
        if existing is not None:
            bundle = self.store.get_bundle(existing["bundle_id"])
            return self._reused_view({**bundle, "alias": existing.get("aliases")}, need_id, 1, replayed=True)
        now = datetime.now(ZoneInfo("UTC"))
        candidates, expired, own = [], 0, None
        later = record["approved"]
        for bundle in self.store.conversation_bundles(conversation_key):
            alias: dict[str, Any] = {}
            if bundle["contract_sha256"] != record["contract_sha256"]:
                # 2c: an earlier bundle that holds all of this need's data (any mode, same or wider columns); EXEC-V
                # stage 2: under any request labels (the alias renames them for this need)
                earlier = self.store.get_need(bundle["need_id"]) if bundle.get("need_id") else None
                if earlier is None:
                    continue
                alias, difference = contract_alias(earlier.get("approved") or {}, later)
                if difference is not None:
                    continue
            manifest = bundle["manifest"]
            if datetime.fromisoformat(manifest["expires_at"]) <= now or not self._files_present(manifest):
                expired += 1
                continue
            if bundle["need_id"] == need_id:
                own = own or bundle
                continue
            candidates.append({**bundle, "alias": alias})
        if own is not None:
            # G14: the same need prepared again in its request (e.g. after a refused frame) gets its own READY bundle
            # back instead of a second extraction
            self._log("bundle_reused", request_id=request_id, need_id=need_id, bundle_id=own["bundle_id"],
                      source_request_id=own["request_id"], candidates=1)
            return self._reused_view(own, need_id, 1, replayed=True)
        if not candidates:
            return {"status": "NO_MATCH", "reason": "EXPIRED" if expired else "NO_COVERING_CONTRACT"}
        chosen = candidates[0]  # the newest snapshot that holds this need's data
        self.store.insert_binding({"need_id": need_id, "request_id": request_id, "bundle_id": chosen["bundle_id"],
                                   "source_need_id": chosen["need_id"], "source_request_id": chosen["request_id"],
                                   "conversation_key": conversation_key, "created_at": utc_now(),
                                   "aliases": chosen["alias"] or None})
        self._log("bundle_reused", request_id=request_id, need_id=need_id, bundle_id=chosen["bundle_id"],
                  source_request_id=chosen["request_id"], candidates=len(candidates),
                  renamed=len((chosen["alias"] or {}).get("requests") or {}))
        return self._reused_view(chosen, need_id, len(candidates))

    def _files_present(self, manifest: dict[str, Any]) -> bool:
        try:
            return all(self.bundles.path_of(manifest["input_bundle_id"], part["file"]).is_file()
                       for d in manifest["datasets"] for part in d["partitions"])
        except Exception:  # noqa: BLE001 - an unreadable bundle is not reused
            return False

    @staticmethod
    def _reused_view(bundle: dict[str, Any], need_id: str, candidates: int, replayed: bool = False
                     ) -> dict[str, Any]:
        manifest = bundle["manifest"]
        renamed = aliased_manifest(manifest, bundle.get("alias"))
        view = bundle_view(renamed)
        if renamed.get("aliases"):
            view["aliases"] = renamed["aliases"]
        view.update({"need_id": need_id, "reused": True, "replayed": replayed, "next_action": "OPEN_ANALYSIS_SESSION",
                     "reused_from": {"bundle_id": manifest["input_bundle_id"], "need_id": manifest["need_id"],
                                     "request_id": bundle["request_id"], "extracted_at": bundle["created_at"],
                                     "expires_at": manifest["expires_at"], "equal_candidates": candidates},
                     "note": "No new extraction: this data need was already prepared in this request; its bundle is "
                             "returned." if manifest["need_id"] == need_id else
                             "No new extraction: the data of an earlier message that holds all of this approved "
                             "data contract (any mode; it may carry more columns) is reused. Disclose its extraction "
                             "time as the as-of of the data."
                             + (" The same data was asked under other request labels: the datasets carry this need's "
                                "data_request_id, logical_name and range ids (aliases lists the earlier ones)."
                                if renamed.get("aliases") else "")})
        return view

    def close_session(self, session_id: str, request_id: str, conversation_key: str | None = None
                      ) -> dict[str, Any]:
        """The caller's close. With conversation reuse, a session that an earlier message completed and this request
        attached without running anything goes back to WARM_IDLE (its namespace is unchanged); any other session
        is closed."""
        record = self.store.get_session(session_id)
        if record is None or record["request_id"] != request_id:
            raise SessionError("SESSION_NOT_FOUND", "No session with this id exists for this request.", 404)
        key = conversation_key if self.settings.conversation_reuse else None
        if key and record.get("conversation_key") == key and record["status"] == "ACTIVE" \
                and int(record.get("epoch") or 1) > 1 and record["executions"] == record.get("epoch_start_seq") \
                and session_id in self.sessions.workers and self.sessions.workers[session_id].alive:
            self.store.update_session(session_id, status="WARM_IDLE", last_active_at=utc_now())
            self.sessions._slot_freed()  # S28: a waiting open may evict it
            self._log("session_detached", request_id=request_id, session_id=session_id, epoch=record.get("epoch"))
            return {"session_id": session_id, "status": "WARM_IDLE", "close_reason": "DETACHED_UNCHANGED"}
        return self.sessions.close(session_id, "CLOSED_BY_CALLER")

    def resources(self, conversation_key: str, max_outputs: int = 12, max_bundles: int = 3) -> dict[str, Any]:
        """What earlier messages of one conversation left that a later message may reuse: WARM_IDLE sessions, READY
        unexpired bundles with the approved DataNeedSpec to resubmit, and released unexpired outputs with the
        completion that released them. Ids and summaries only, no data."""
        if not self.settings.conversation_reuse:
            raise DataNeedError("REUSE_UNAVAILABLE", "Conversation reuse is not enabled.", http_status=404)
        now = datetime.now(ZoneInfo("UTC"))
        warm = {w["bundle_id"]: w for w in self.store.warm_sessions(conversation_key)
                if w["session_id"] in self.sessions.workers}
        bundles = []
        for bundle in self.store.conversation_bundles(conversation_key):
            manifest = bundle["manifest"]
            if datetime.fromisoformat(manifest["expires_at"]) <= now or len(bundles) >= max_bundles:
                continue
            need = self.store.get_need(bundle["need_id"]) or {}
            spec = dict(((need.get("approved") or {}).get("spec")) or {})
            session = warm.get(bundle["bundle_id"])
            bundles.append({
                "bundle_id": bundle["bundle_id"], "extracted_at": bundle["created_at"],
                "expires_at": manifest["expires_at"], "mode": bundle["mode"],
                "reference_date": manifest.get("reference_date"),
                "datasets": [{"data_request_id": d["data_request_id"], "logical_name": d["logical_name"],
                              "source_table": d["source_table"], **row_counts(d),
                              "columns": [c["name"] for c in d.get("columns") or []]}
                             for d in manifest["datasets"]],
                "data_need_spec": spec or None,
                "warm_session": {"session_id": session["session_id"], "epoch": session.get("epoch"),
                                 "last_active_at": session["last_active_at"], "expires_at": session["expires_at"]}
                if session else None})
        outputs = []
        for output in self.store.released_outputs(conversation_key, max_outputs * 3):
            if len(outputs) >= max_outputs or output["expires_at"] <= now.isoformat():
                continue
            if str(output.get("name") or "").startswith(BACKEND_RECORDS):
                continue  # a declaration the backend reads, not a result to answer from
            origin = self.sessions._release_origin(output["session_id"], output["output_id"]) or {}
            outputs.append({"output_id": output["output_id"], "session_id": output["session_id"],
                            "name": output["name"], "type": output["type"], "format": output["format"],
                            "columns": output.get("columns"), "row_count": output.get("row_count"),
                            "description": (output.get("meta") or {}).get("description"),
                            # H1: its definition and the execution that produced it
                            "definition": (output.get("meta") or {}).get("definition"),
                            "execution_id": output.get("execution_id"),
                            "completion_id": origin.get("completion_id"), "request_id": origin.get("request_id"),
                            "completed_at": origin.get("completed_at"), "expires_at": output["expires_at"],
                            "evidence_label": origin.get("evidence_label"), "warnings": origin.get("warnings"),
                            **({"calculation_verified": True} if origin.get("calculation_verified") else {})})
        return {"conversation_reuse": True, "bundles": bundles, "released_outputs": outputs,
                "warm_sessions": len(warm)}

    # ------------------------------------------------------------------------------------------ completion

    CLAIMS_ALLOWED = ["the DataNeedSpec was validated", "the SQL extraction succeeded",
                      "the requested ranges were delivered as approved", "a Data Quality Manifest is available",
                      "data coverage passed", "the sandbox execution succeeded", "the methods and parameters used"]
    CLAIMS_FORBIDDEN = ["the calculation was independently verified",
                        "a backend validator recalculated the formula"]
    RESEARCH_CLAIMS_FORBIDDEN = ["a causal effect", "a prediction or forecast of future prices or returns"]

    def complete(self, session_id: str, request_id: str, finalize: bool = False) -> dict[str, Any]:
        """ExecutionManifest + Coverage Validator (delivery and processing) + final status; outputs are released and
        the session closed only when coverage passes and the execution succeeded. For a multi-angle research group,
        every approved angle also needs one backend finding (finalize: an angle without a record becomes NOT_RUN and
        an INVALID finding is accepted as the group's terminal state)."""
        record = self.store.get_session(session_id)
        if record is None or record["request_id"] != request_id:
            raise SessionError("SESSION_NOT_FOUND", "No session with this id exists for this request.", 404,
                               "OPEN_ANALYSIS_SESSION")
        epoch = int(record.get("epoch") or 1)
        # completion is per epoch: a PASS of an earlier message never completes a later one (S2)
        earlier = self.store.completion_for_epoch(session_id, epoch)
        # only a COMPLETED result is final; an INCOMPLETE one with coverage PASS (for example no output yet) is
        # evaluated again, so the analysis can finish after the fix (S06)
        if earlier is not None and (earlier["final_status"] or {}).get("status") == "COMPLETED":
            return {**earlier["final_status"], "replayed": True}
        stored = self.store.get_bundle(record["bundle_id"])["manifest"]
        need_id = record.get("need_id") or stored["need_id"]
        # EXEC-V stage 2: coverage, lineage and validation read the bundle under this need's labels
        bundle = self.sessions.manifest_for(record["bundle_id"], need_id)
        need = self.get_need(need_id)
        start = int(record.get("epoch_start_seq") or 0)
        executions = [e for e in self.store.executions_for(session_id) if e["seq"] > start]
        outputs = [o for o in self.store.outputs_for(session_id)
                   if any(e["execution_id"] == o["execution_id"] and e["status"] == "OK" for e in executions)]
        manifest = execution_manifest(record, bundle, executions, outputs)
        if self.settings.conversation_reuse:
            manifest.update(epoch=epoch, need_id=need_id)
        processing = processing_coverage(need, manifest)
        # data read in full by any earlier epoch of this session that completed with PASS (same bundle, same
        # namespace) stays in the namespace: it counts as INHERITED, labelled with the completions, never as read again
        # in this epoch. Every earlier passed epoch counts, not only the last one: an epoch that only reused variables
        # read nothing itself (S07)
        ancestors = [c for c in self.store.passed_completions(session_id)
                     if int(c.get("epoch") or 1) < epoch
                     and (c.get("final_status") or {}).get("status") == "COMPLETED"] if epoch > 1 else []
        parent = ancestors[-1] if ancestors else None
        inherited: dict[str, dict[str, Any]] = {}
        for ancestor in ancestors:
            for item in processing_coverage(need, ancestor["execution_manifest"]):
                if item["status"] == "PROCESSED":
                    inherited[item["data_request_id"]] = item
        delivery = bundle.get("coverage") or {}
        by_request = {r["data_request_id"]: r for r in delivery.get("requests") or []}
        requests = []
        for item in processing:
            before = inherited.get(item["data_request_id"])
            if item["status"] != "PROCESSED" and before is not None and before["status"] == "PROCESSED":
                item = {**item, "status": "INHERITED",
                        "ranges": [{**r, "status": "PROCESSED" if r["status"] == "PROCESSED" else "INHERITED"}
                                   for r in item["ranges"]]}
            done = ("PROCESSED", "INHERITED")
            delivered = by_request.get(item["data_request_id"]) or {}
            delivered_ranges = {r["range_id"]: r["status"] for r in delivered.get("ranges") or []}
            ranges = [{"range_id": r["range_id"], "delivery": delivered_ranges.get(r["range_id"], "FAIL"),
                       "processing": r["status"],
                       "status": "PASS" if delivered_ranges.get(r["range_id"]) == "PASS"
                       and r["status"] in done else "FAIL"} for r in item["ranges"]]
            status = "PASS" if delivered.get("status") == "PASS" and item["status"] in done else "FAIL"
            requests.append({"data_request_id": item["data_request_id"], "logical_name": item["logical_name"],
                             "status": status, "delivery": delivered.get("status", "FAIL"),
                             "processing": item["status"], "ranges": ranges,
                             "partitions_expected": delivered.get("partitions_expected"),
                             "partitions_delivered": delivered.get("partitions_delivered"),
                             "sampling": bool(delivered.get("sampling")), "truncation": bool(delivered.get("truncation"))})
        coverage_status = "PASS" if delivery.get("coverage_status") == "PASS" and all(
            r["status"] == "PASS" for r in requests) else "FAIL"
        ok_runs = [e for e in executions if e["status"] == "OK"]
        insufficient = [e for e in executions if e["status"] == "INSUFFICIENT_INPUT_DATA"]
        if ok_runs and outputs and not (insufficient and insufficient[-1]["seq"] > ok_runs[-1]["seq"]):
            execution = "SUCCESS"
        elif insufficient:
            execution = "INSUFFICIENT_INPUT_DATA"
        else:
            execution = "FAILED" if executions else "NO_EXECUTION"
        quality_flags = sorted({f for d in bundle["datasets"] for f in (d.get("quality") or {}).get("quality_flags")
                                or []})
        ranges_ok = all(r.get("status") == "OK" for d in bundle["datasets"]
                        for r in (d.get("quality") or {}).get("requested_ranges") or [])
        research = need.get("research_governance") or {}
        mode = need.get("mode")
        passed = coverage_status == "PASS" and execution == "SUCCESS"
        # multi-angle research: one backend finding per approved angle of this bundle group
        constraints = research.get("constraints") or {}
        grouped = None
        if mode == "RESEARCH" and constraints.get("governance_version") == GOVERNANCE_V2:
            if not self.settings.multi_angle_research_enabled:
                passed = False
            elif passed:
                ok_ids = {e["execution_id"] for e in executions if e["status"] == "OK"}
                grouped = research_validation.validate_group(
                    context={"plan_id": constraints.get("plan_id"),
                             "research_run_id": constraints.get("research_run_id"),
                             "bundle_group_id": constraints.get("bundle_group_id"), "session_id": session_id,
                             "hashes": self._research_hashes(constraints, bundle)},
                    angles=constraints.get("angles") or {}, bundle=bundle, path_of=self.bundles.path_of,
                    outputs=[o for o in outputs if o["execution_id"] in ok_ids], executions=executions,
                    outputs_root=self.sessions.outputs_root, finalize=finalize)
                passed = not grouped["missing"] and not grouped["unapproved"] \
                    and (finalize or not grouped["invalid"])
        # research findings v1: the backend's own sample category and verdict from the released event aggregates
        findings = None
        if self.settings.research_findings_enabled and mode == "RESEARCH" and passed and grouped is None \
                and constraints.get("governance_version") != GOVERNANCE_V2:
            findings = evaluate_findings(research.get("constraints") or {}, outputs, self.sessions.outputs_root)
            passed = findings["status"] == "OK"
        # G2 event study: every saniti.event_study of this epoch is rebuilt from its declaration and recomputed here,
        # outside the model's process; a released table that differs fails the completion (CALCULATION_MISMATCH)
        studies = None
        if passed:
            try:
                studies = event_study_validation.validate(bundle=bundle, path_of=self.bundles.path_of,
                                                          outputs=outputs, outputs_root=self.sessions.outputs_root)
            except Exception as exc:  # noqa: BLE001 - a validator defect never fails a completion that did not use it
                self._log("event_study_validation_failed", request_id=request_id, session_id=session_id,
                          error=type(exc).__name__)
                studies = {"status": "INVALID", "verified_output_ids": [],
                           "record_output_ids": [o["output_id"] for o in outputs if str(o.get("name") or "")
                                                 .startswith(event_study_validation.PREFIX)],
                           "studies": [{"name": None, "status": "INVALID",
                                        "reason": f"VALIDATOR_ERROR: {type(exc).__name__}"}]}
                if not studies["record_output_ids"]:
                    studies = None
            if studies is not None and studies["status"] == "FAIL":
                passed = False
        # P32 layer 3: every saniti.backtest is re-run on the bundle prices from its recorded signal dates
        backtests = None
        if passed:
            try:
                backtests = backtest_validation.validate(bundle=bundle, path_of=self.bundles.path_of,
                                                         outputs=outputs, outputs_root=self.sessions.outputs_root)
            except Exception as exc:  # noqa: BLE001 - a validator defect never fails a completion that did not use it
                self._log("backtest_validation_failed", request_id=request_id, session_id=session_id,
                          error=type(exc).__name__)
                ids = [o["output_id"] for o in outputs
                       if str(o.get("name") or "").startswith(backtest_validation.PREFIX)]
                backtests = {"status": "INVALID", "verified_output_ids": [], "record_output_ids": ids,
                             "backtests": [{"name": None, "status": "INVALID",
                                            "reason": f"VALIDATOR_ERROR: {type(exc).__name__}"}]} if ids else None
            if backtests is not None and backtests["status"] == "FAIL":
                passed = False
        records = {o["output_id"] for o in outputs
                   if str(o.get("name") or "").startswith((event_study_validation.PREFIX, backtest_validation.PREFIX))}
        # H1 (M63): every released table or JSON states how it was made, so a later turn reads it instead of guessing
        undefined = undefined_outputs(outputs) if passed else []
        if undefined:
            passed = False
        final = {
            "data_need_validation": "PASS",
            "research_governance": research.get("decision", "APPROVED") if mode == "RESEARCH" else "NOT_APPLICABLE",
            "sql_governance": "PASS", "data_quality_profiling": "COMPLETE", "data_coverage": coverage_status,
            "sandbox_execution": execution, "calculation_validation": "NOT_PERFORMED",
            "data_complete": delivery.get("coverage_status") == "PASS" and ranges_ok
            and "EMPTY_ENTITY" not in quality_flags,
            "execution_complete": passed,
            "evidence_label": "DATA_COVERAGE_VERIFIED" if passed else "NOT_VALIDATED",
            "warnings": sorted({w["code"] for w in bundle.get("relationship_warnings") or []} | set(quality_flags)),
            "claims_allowed": self.CLAIMS_ALLOWED if passed else [],
            "claims_forbidden": self.CLAIMS_FORBIDDEN + (self.RESEARCH_CLAIMS_FORBIDDEN if mode == "RESEARCH" else []),
            "research_constraints": research.get("constraints") if mode == "RESEARCH" else None,
            # IP1 Stage D: what the data may claim about time (HISTORICAL_DESCRIPTIVE or POINT_IN_TIME)
            "time_basis": bundle.get("time_basis") or DEFAULT_TIME_BASIS}
        derived = [d for d in bundle["datasets"] if d.get("resample_semantics_version") is not None]
        if derived:
            # IP2 solution 1: how weekly/monthly figures were derived, and from which data and code
            calls = [a for e in executions for a in e.get("access") or [] if a.get("call") == "resample"]
            final["derived_frequency"] = {
                "requests": [{"data_request_id": d["data_request_id"], "source_frequency": d.get("source_frequency"),
                              "analysis_frequency": d.get("analysis_frequency"), "resample": d.get("resample"),
                              "resample_semantics_version": d["resample_semantics_version"],
                              "period_policy": PERIOD_POLICY.get(d.get("analysis_frequency") or ""),
                              "resample_calls": sum(1 for a in calls if a.get("data_request_id")
                                                    == d["data_request_id"]),
                              "incomplete_periods": max([int(a.get("incomplete_periods") or 0) for a in calls
                                                         if a.get("data_request_id") == d["data_request_id"]]
                                                        or [0])} for d in derived],
                "completeness_rule": COMPLETENESS_RULE, "null_policy": NULL_POLICY,
                "contract_sha256": data_contract_sha256(need),
                "input_checksum": bundle.get("checksum_sha256") or self.store.get_bundle(record["bundle_id"]).get(
                    "checksum_sha256"),
                "execution_ids": [e["execution_id"] for e in executions if e["status"] == "OK"]}
        if findings is not None and findings["status"] == "OK":
            final["research_findings"] = [findings["finding"]]
        used = {}
        for run in executions:
            if run["status"] != "OK":
                continue
            for entry in run.get("access") or []:
                if entry.get("call") == "load_output" and entry.get("output_id"):
                    used[entry["output_id"]] = {k: entry.get(k) for k in ("output_id", "name", "kind", "label",
                                                                          "definition")}
        if used:
            # tables of earlier results this analysis built on: their labels bound what its figures can claim
            final["carried_inputs"] = list(used.values())
        if studies is not None and studies["status"] != "NOT_PERFORMED":
            final["event_studies"] = [{k: study.get(k) for k in (
                "name", "status", "reason", "summary_output_id", "events_output_id", "baseline_output_id",
                "flow_output_id", "checked", "mismatched", "examples")} for study in studies["studies"]]
            verified = [st["name"] for st in studies["studies"] if st["status"] == "PASS"]
            if passed and grouped is None:
                final["calculation_validation"] = event_study_validation.level(
                    studies, [o["output_id"] for o in outputs if o["output_id"] not in records])
            if passed and verified:
                final["verified_output_ids"] = studies["verified_output_ids"]
                scoped = f"a calculation other than the event studies {verified}"
                final["claims_forbidden"] = [
                    {"the calculation was independently verified": f"{scoped} was independently verified",
                     "a backend validator recalculated the formula": f"a backend validator recalculated {scoped}"}
                    .get(c, c) for c in final["claims_forbidden"]]
                final["claims_allowed"] = [*final["claims_allowed"],
                                           f"the event studies {verified} were recomputed independently by the "
                                           "backend from their declaration (FORMULA_AND_STATISTICS_VERIFIED)"]
        if backtests is not None and backtests["status"] != "NOT_PERFORMED":
            final["backtests"] = [{k: b.get(k) for k in ("name", "status", "reason", "trades_output_id",
                                                         "summary_output_id", "checked", "mismatched", "examples")}
                                  for b in backtests["backtests"]]
            verified_bt = [b["name"] for b in backtests["backtests"] if b["status"] == "PASS"]
            if passed and verified_bt:
                final["verified_output_ids"] = [*(final.get("verified_output_ids") or []),
                                                *backtests["verified_output_ids"]]
                final["claims_allowed"] = [*final["claims_allowed"],
                                           f"the backtests {verified_bt} were re-run by the backend on the governed "
                                           "prices from their signal dates (the signals are the analysis code's)"]
                if final["calculation_validation"] == "NOT_PERFORMED":
                    final["calculation_validation"] = "PARTIAL"
        if grouped is not None:
            final["calculation_validation"] = grouped["calculation_validation"] if passed else "NOT_PERFORMED"
            final["research_group"] = {"research_run_id": constraints.get("research_run_id"),
                                       "bundle_group_id": constraints.get("bundle_group_id"),
                                       "angles": sorted(constraints.get("angles") or {}),
                                       "missing": grouped["missing"], "invalid": grouped["invalid"],
                                       "unapproved_outputs": grouped["unapproved"], "finalized": bool(finalize)}
            if passed:
                final["research_findings_v2"] = [grouped["findings"][a] for a in sorted(grouped["findings"])]
                if grouped["calculation_validation"] != "NOT_PERFORMED":
                    final["claims_forbidden"] = [c for c in final["claims_forbidden"]
                                                 if c not in self.CLAIMS_FORBIDDEN]
                    final["claims_allowed"] = [*final["claims_allowed"],
                                               f"the research statistics were recomputed by the backend "
                                               f"({grouped['calculation_validation']})"]
        if self.settings.modules_audit_enabled:
            final["modules_used"] = sorted({m for e in executions if e["status"] == "OK"
                                            for m in e.get("modules") or []})
        if parent is not None:
            final["inherited_coverage"] = {
                "parent_completion_id": parent["completion_id"], "parent_request_id": parent["request_id"],
                "ancestor_completion_ids": [c["completion_id"] for c in ancestors],
                "data_request_ids": sorted(r["data_request_id"] for r in requests if r["processing"] == "INHERITED")}
        coverage = {"coverage_status": coverage_status, "requests": requests,
                    "delivery_issues": [i for r in delivery.get("requests") or [] for i in r.get("issues") or []][:10]}
        released = []
        if passed:
            # M80 (a): the backend's research findings also as a standard table (export, chart, value references)
            found = ([grouped["findings"][a] for a in sorted(grouped["findings"])] if grouped is not None else []) \
                + ([findings["finding"]] if findings is not None and findings["status"] == "OK" else [])
            ok_runs = [e for e in executions if e["status"] == "OK"]
            table_rows = findings_table.rows(found)
            if table_rows and ok_runs:
                outputs = [*outputs, self.sessions.write_backend_table(
                    session_id, ok_runs[-1]["execution_id"], findings_table.NAME, table_rows, findings_table.COLUMNS,
                    definition=findings_table.DEFINITION, units=findings_table.UNITS)]
            self.store.release_outputs([o["output_id"] for o in outputs])
            # an event study's declaration record is released for the audit but not listed for the answer
            code_of = {e["execution_id"]: e.get("code_sha256") for e in executions}
            released = [{**{k: o[k] for k in ("output_id", "name", "type", "format", "row_count", "columns")},
                         **({"definition": (o.get("meta") or {})["definition"]}
                            if isinstance(o.get("meta"), dict) and "definition" in o["meta"] else {}),
                         # H1: the execution, code and data that produced it
                         "lineage": {"execution_id": o.get("execution_id"),
                                     "code_sha256": code_of.get(o.get("execution_id")), "need_id": need_id,
                                     "bundle_id": record["bundle_id"],
                                     # R-STORE: the data's last date, so a later recomputation can use the same one
                                     **data_as_of(bundle)}}
                        for o in outputs if o["output_id"] not in records]
        completion_id = f"cmp_{secrets.token_hex(12)}"
        result = {"completion_id": completion_id, "session_id": session_id, "bundle_id": record["bundle_id"],
                  "need_id": need_id, "status": "COMPLETED" if passed else "INCOMPLETE",
                  "final_status": final, "coverage": coverage, "released_outputs": released,
                  "execution_manifest_sha256": sha256_json(manifest)}
        if passed:
            result["next_action"] = "ANSWER_FROM_RELEASED_OUTPUTS"
        elif undefined:
            result["next_action"] = "RUN_PYTHON"
            result["missing_definitions"] = undefined
            result["message"] = (
                f"Every released table or JSON states how it was made. Missing a definition: {undefined}. Emit each "
                "again under the same name with definition=..., for example emit_table(name, frame, description, "
                "definition={'filters': [{'column': 'market_board', 'operator': 'EQ', 'value': 'Regular'}], "
                "'period': {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}, 'thresholds': {...}, 'notes': '...'}) "
                "(definition={} when the code applied no filter beyond the data request), then complete again.")
        elif studies is not None and studies["status"] == "FAIL":
            result["next_action"] = "RUN_PYTHON"
            failed = [st for st in studies["studies"] if st["status"] == "FAIL"]
            result["message"] = (
                "Event study tables differ from the backend's recomputation: "
                + "; ".join(f"{st['name']} ({st['reason']}"
                            + (f", e.g. {st['examples'][0]}" if st.get("examples") else "") + ")" for st in failed)
                + ". Run saniti.event_study again under that name and do not overwrite or re-emit its tables, then "
                  "complete again.")
        elif grouped is not None and not passed:
            result["next_action"] = "RUN_PYTHON"
            parts = []
            if grouped["missing"]:
                parts.append(f"angles without a record: {grouped['missing']} (call their saniti.research_* helper in "
                             "a successful execution)")
            if grouped["invalid"]:
                parts.append(f"angles INVALID: {grouped['invalid']} (see the findings' status_reason; fix the input "
                             "or complete with finalize to accept them)")
            if grouped["unapproved"]:
                parts.append(f"outputs of unapproved angles: {grouped['unapproved']}")
                result["next_action"] = "REPORT_LIMITATION"
            result["message"] = "Research group incomplete: " + "; ".join(parts)
            result["research_findings_v2"] = [grouped["findings"][a] for a in sorted(grouped["findings"])]
        elif findings is not None and findings["status"] != "OK":
            result["next_action"] = "RUN_PYTHON"
            result["message"] = findings["message"]
            result["research_findings_status"] = findings["status"]
        elif execution == "INSUFFICIENT_INPUT_DATA":
            result["next_action"] = "REVISE_DATA_NEED_SPEC"
        elif coverage_status == "FAIL" and delivery.get("coverage_status") == "PASS":
            missing = [f"{r['logical_name']}:{g['range_id']}" if g else r["logical_name"] for r in requests
                       for g in (r["ranges"] or [None]) if (g or r)["status"] == "FAIL"
                       and (g is None or g["processing"] == "NOT_PROCESSED")]
            result["next_action"] = "RUN_PYTHON"
            result["message"] = ("Read every approved request and range through the saniti helpers in a successful "
                                 "execution before completing. Not processed: " + ", ".join(missing[:20]))
        else:
            result["next_action"] = "RUN_PYTHON" if execution != "SUCCESS" else "REPORT_LIMITATION"
        worker = self.sessions.workers.get(session_id)
        # kept warm for a later message of the conversation; an interrupted execution leaves the namespace uncertain,
        # so such a session is closed instead
        warm = passed and self.settings.conversation_reuse and bool(record.get("conversation_key")) \
            and worker is not None and worker.alive and not any(e["status"] == "TIMEOUT" for e in executions)
        if self.settings.conversation_reuse:
            result["epoch"] = epoch
            if passed:
                result["session_status"] = "WARM_IDLE" if warm else "CLOSED"
        self.store.insert_completion({"completion_id": completion_id, "session_id": session_id,
                                      "request_id": request_id, "bundle_id": record["bundle_id"],
                                      "need_id": need_id, "coverage_status": coverage_status,
                                      "execution_manifest": manifest, "coverage": coverage,
                                      "final_status": result, "created_at": utc_now(), "epoch": epoch,
                                      "parent_completion_id": parent["completion_id"] if parent else None})
        if self.audit is not None:
            try:
                released_files = [{"name": o["name"], "format": o["format"], "execution_id": o["execution_id"],
                                   "path": str(self.sessions.outputs_root / o["relative_path"])}
                                  for o in outputs if passed]
                self.audit.record_completion(request_id=request_id, result=result, execution_manifest=manifest,
                                             need=need, bundle=bundle, released=released_files)
            except Exception as exc:  # noqa: BLE001 - audit never fails a completion while optional
                self._log("sandbox_audit_enqueue_failed", request_id=request_id, completion_id=completion_id,
                          error=type(exc).__name__)
        if grouped is not None and passed:
            for angle_id, finding in grouped["findings"].items():
                self.store.upsert_research_finding({
                    "research_run_id": constraints.get("research_run_id"), "angle_id": angle_id,
                    "bundle_group_id": constraints.get("bundle_group_id"), "session_id": session_id,
                    "completion_id": completion_id, "status": finding["status"],
                    "validation_level": finding.get("validation_level"), "finding": finding, "created_at": utc_now()})
            self.store.update_research_group(constraints.get("research_run_id"), constraints.get("bundle_group_id"),
                                             status="COMPLETED", session_id=session_id, completion_id=completion_id,
                                             updated_at=utc_now())
        if warm:
            self.store.update_session(session_id, status="WARM_IDLE", last_active_at=utc_now())
            self.sessions._slot_freed()  # S28: a waiting open may evict it
        elif passed:
            self.sessions.close(session_id, "COMPLETED")
        self._log("analysis_completed", request_id=request_id, session_id=session_id, completion_id=completion_id,
                  coverage=coverage_status, execution=execution, released=len(released),
                  evidence_label=final["evidence_label"])
        return result

    def _research_hashes(self, constraints: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
        run = self.store.get_research_run(str(constraints.get("research_run_id"))) or {}
        return {"plan_sha256": run.get("plan_sha256"), "research_data_plan_sha256": run.get("data_plan_sha256"),
                "bundle_checksum_sha256": bundle.get("checksum_sha256"), "bundle_id": bundle.get("input_bundle_id")}

    def get_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        record = self.store.get_bundle(bundle_id)
        return None if record is None else {**record["manifest"], "status": record["status"]}

    def bundle_lineage(self, bundle_id: str, request_id: str, conversation_key: str | None) -> dict[str, Any]:
        """D3 (round 2026-10-03): how a bundle was made, for its own request or a later request of the same
        conversation; another conversation's bundle is not found."""
        from .bundles import lineage_view

        record = self.store.get_bundle(bundle_id)
        allowed = record is not None and (record.get("request_id") == request_id or (
            conversation_key is not None and record.get("conversation_key") == conversation_key))
        if not allowed:
            raise DataNeedError("BUNDLE_NOT_FOUND", "No bundle with this id belongs to this request or conversation.",
                                404)
        return {**lineage_view(record["manifest"]), "status": record["status"]}
