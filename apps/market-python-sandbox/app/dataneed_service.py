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

from .bundles import BundleBuilder, BundleError
from .bundles import model_view as bundle_view
from .coverage import execution_manifest, processing_coverage
from .data_need import (COMPLETENESS_RULE, DEFAULT_TIME_BASIS, NULL_POLICY, PERIOD_POLICY, Limits, contract_tables,
                        data_contract_sha256, sha256_json, validate)
from .datasets import DatasetFailure
from .dataneed_store import DRAFT_RETENTION_DAYS, DataNeedStore
from .records import utc_now
from .research_governance import check_request
from .research_findings import evaluate as evaluate_findings
from .sessions import SessionError, SessionManager
from .research_governance import review as governance_review

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


def reference_date(reference_time: datetime, tz: str) -> date:
    try:
        zone = ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    moment = reference_time if reference_time.tzinfo else reference_time.replace(tzinfo=ZoneInfo("UTC"))
    return moment.astimezone(zone).date()


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
               governance: Any | None, conversation_key: str | None = None) -> dict[str, Any]:
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
        outcome = validate(spec, contract, ref, self.limits)
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
        return self._record(request_id, spec, governance, submitted, submitted_sha, key, body, approved, research)

    def _record(self, request_id: str, spec: Any, governance: Any, submitted: dict[str, Any], submitted_sha: str,
                conversation_key: str | None, body: dict[str, Any], approved: dict[str, Any] | None,
                research: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
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
                              "restricted_by": [x["relationship_id"] for x in r["restrictions"]]}
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

    def check(self, request_id: str, reference_time: datetime, tz: str, spec: Any) -> dict[str, Any]:
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
        outcome = validate(spec, contract, ref, self.limits)
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

    def open_session(self, request_id: str, bundle_id: str, conversation_key: str | None = None) -> dict[str, Any]:
        """A persistent session on a READY bundle; a RESEARCH need gets its approved compute budget.

        Conversation reuse (S2): a bundle of an earlier request is usable only through a binding to this request's
        own approved need (reuse_bundle); a WARM_IDLE session on that bundle in the same conversation is then
        attached with a new epoch instead of starting a new worker."""
        key = conversation_key if self.settings.conversation_reuse else None
        record = self.store.get_bundle(bundle_id)
        binding = self.store.binding_for(request_id, bundle_id) if key and record is not None else None
        if binding is not None and binding["conversation_key"] != key:
            binding = None
        need_id = binding["need_id"] if binding else (record or {}).get("need_id")
        cpu = None
        if need_id:
            need = self.store.get_need(need_id)
            research = (need or {}).get("research") or {}
            cpu = (research.get("constraints") or {}).get("compute_seconds")
        if key and record is not None and (binding is not None or record["request_id"] == request_id):
            for warm in self.store.warm_sessions(key):
                if warm["bundle_id"] == bundle_id and warm["session_id"] in self.sessions.workers:
                    try:
                        return self.sessions.attach(warm["session_id"], request_id, need_id)
                    except SessionError:
                        continue
        return self.sessions.open(request_id, bundle_id, cpu_seconds=cpu, conversation_key=key, need_id=need_id,
                                  bound=binding is not None)

    def reuse_bundle(self, request_id: str, need_id: str, conversation_key: str | None) -> dict[str, Any]:
        """Conversation reuse (S1): bind this request's approved need to an earlier READY bundle of the same
        conversation whose need has exactly the same data contract (data_contract_sha256), so no extraction runs.
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
            return self._reused_view(bundle, need_id, 1, replayed=True)
        now = datetime.now(ZoneInfo("UTC"))
        candidates, expired = [], 0
        for bundle in self.store.conversation_bundles(conversation_key):
            if bundle["contract_sha256"] != record["contract_sha256"] or bundle["request_id"] == request_id:
                continue
            manifest = bundle["manifest"]
            if datetime.fromisoformat(manifest["expires_at"]) <= now or not self._files_present(manifest):
                expired += 1
                continue
            candidates.append(bundle)
        if not candidates:
            return {"status": "NO_MATCH", "reason": "EXPIRED" if expired else "NO_EQUAL_CONTRACT"}
        chosen = candidates[0]  # the newest snapshot; the others hold the same contract
        self.store.insert_binding({"need_id": need_id, "request_id": request_id, "bundle_id": chosen["bundle_id"],
                                   "source_need_id": chosen["need_id"], "source_request_id": chosen["request_id"],
                                   "conversation_key": conversation_key, "created_at": utc_now()})
        self._log("bundle_reused", request_id=request_id, need_id=need_id, bundle_id=chosen["bundle_id"],
                  source_request_id=chosen["request_id"], candidates=len(candidates))
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
        view = bundle_view(manifest)
        view.update({"need_id": need_id, "reused": True, "replayed": replayed, "next_action": "OPEN_ANALYSIS_SESSION",
                     "reused_from": {"bundle_id": manifest["input_bundle_id"], "need_id": manifest["need_id"],
                                     "request_id": bundle["request_id"], "extracted_at": bundle["created_at"],
                                     "expires_at": manifest["expires_at"], "equal_candidates": candidates},
                     "note": "No new extraction: the data of an earlier message with the same approved data contract "
                             "is reused. Disclose its extraction time as the as-of of the data."})
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
                              "source_table": d["source_table"], "rows": d["rows"],
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
            origin = self.sessions._release_origin(output["session_id"], output["output_id"]) or {}
            outputs.append({"output_id": output["output_id"], "session_id": output["session_id"],
                            "name": output["name"], "type": output["type"], "format": output["format"],
                            "columns": output.get("columns"), "row_count": output.get("row_count"),
                            "description": (output.get("meta") or {}).get("description"),
                            "completion_id": origin.get("completion_id"), "request_id": origin.get("request_id"),
                            "completed_at": origin.get("completed_at"), "expires_at": output["expires_at"],
                            "evidence_label": origin.get("evidence_label"), "warnings": origin.get("warnings")})
        return {"conversation_reuse": True, "bundles": bundles, "released_outputs": outputs,
                "warm_sessions": len(warm)}

    # ------------------------------------------------------------------------------------------ completion

    CLAIMS_ALLOWED = ["the DataNeedSpec was validated", "the SQL extraction succeeded",
                      "the requested ranges were delivered as approved", "a Data Quality Manifest is available",
                      "data coverage passed", "the sandbox execution succeeded", "the methods and parameters used"]
    CLAIMS_FORBIDDEN = ["the calculation was independently verified",
                        "a backend validator recalculated the formula"]
    RESEARCH_CLAIMS_FORBIDDEN = ["a causal effect", "a prediction or forecast of future prices or returns"]

    def complete(self, session_id: str, request_id: str) -> dict[str, Any]:
        """ExecutionManifest + Coverage Validator (delivery and processing) + final status; outputs are released and
        the session closed only when coverage passes and the execution succeeded."""
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
        bundle = self.store.get_bundle(record["bundle_id"])["manifest"]
        need_id = record.get("need_id") or bundle["need_id"]
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
        # research findings v1: the backend's own sample category and verdict from the released event aggregates
        findings = None
        if self.settings.research_findings_enabled and mode == "RESEARCH" and passed:
            findings = evaluate_findings(research.get("constraints") or {}, outputs, self.sessions.outputs_root)
            passed = findings["status"] == "OK"
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
            self.store.release_outputs([o["output_id"] for o in outputs])
            released = [{k: o[k] for k in ("output_id", "name", "type", "format", "row_count", "columns")}
                        for o in outputs]
        completion_id = f"cmp_{secrets.token_hex(12)}"
        result = {"completion_id": completion_id, "session_id": session_id, "bundle_id": record["bundle_id"],
                  "need_id": need_id, "status": "COMPLETED" if passed else "INCOMPLETE",
                  "final_status": final, "coverage": coverage, "released_outputs": released,
                  "execution_manifest_sha256": sha256_json(manifest)}
        if passed:
            result["next_action"] = "ANSWER_FROM_RELEASED_OUTPUTS"
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
        if warm:
            self.store.update_session(session_id, status="WARM_IDLE", last_active_at=utc_now())
        elif passed:
            self.sessions.close(session_id, "COMPLETED")
        self._log("analysis_completed", request_id=request_id, session_id=session_id, completion_id=completion_id,
                  coverage=coverage_status, execution=execution, released=len(released),
                  evidence_label=final["evidence_label"])
        return result

    def get_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        record = self.store.get_bundle(bundle_id)
        return None if record is None else {**record["manifest"], "status": record["status"]}
