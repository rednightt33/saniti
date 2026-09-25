"""The DataNeed flow of the sandbox service: validation of DataNeedSpecs (with the Research Governor for RESEARCH),
governed bundles, persistent analysis sessions, and completion with the Coverage Validator.

This module owns only the new flow. It reuses the analysis service's dataset provider (Governor grants and the
verified dataset cache), executor, isolation self-test and settings, so the security boundaries are the same ones.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .bundles import BundleBuilder, BundleError
from .bundles import model_view as bundle_view
from .coverage import execution_manifest, processing_coverage
from .data_need import Limits, contract_tables, sha256_json, validate
from .datasets import DatasetFailure
from .dataneed_store import DataNeedStore
from .records import utc_now
from .research_governance import check_request
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
        self.limits = limits
        self.policy = self.settings.governance_policy()
        self.bundles = BundleBuilder(analysis, store)
        self.sessions = SessionManager(analysis, store, self.bundles)

    @staticmethod
    def _log(event: str, **fields: Any) -> None:
        logger.info(json.dumps({"event": event, **fields}, default=str, separators=(",", ":")))

    # ------------------------------------------------------------------------------------------ data need specs

    def submit(self, request_id: str, reference_time: datetime, tz: str, spec: Any,
               governance: Any | None) -> dict[str, Any]:
        """Validate one DataNeedSpec revision; RESEARCH specs also go to the Research Governor."""
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
            return self._record(request_id, spec, governance, submitted, submitted_sha, {
                "status": "REVISION_REQUIRED", "warnings": [], "issues": [{
                    "data_request_id": None, "code": "REVISION_CONFLICT", "field_path": "revision",
                    "rejected_value": revision}]}, None, None)
        expected = max((n["revision"] for n in earlier if isinstance(n["revision"], int)), default=0) + 1
        if isinstance(revision, int) and not isinstance(revision, bool) and revision != expected:
            return self._record(request_id, spec, governance, submitted, submitted_sha, {
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
                    extra.extend(check_request(governance))
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
        return self._record(request_id, spec, governance, submitted, submitted_sha, body, approved, research)

    def _record(self, request_id: str, spec: Any, governance: Any, submitted: dict[str, Any], submitted_sha: str,
                body: dict[str, Any], approved: dict[str, Any] | None, research: dict[str, Any] | None,
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
            "created_at": utc_now()})
        self._log("data_need_reviewed", request_id=request_id, need_id=need_id if allowed else None,
                  request_group_id=result["request_group_id"], revision=result["revision"], status=status,
                  mode=mode, research=(research or {}).get("decision"), issues=[i["code"] for i in result["issues"]],
                  warnings=[w["code"] for w in result["warnings"]])
        return result

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

    def stop(self) -> None:
        self.sessions.stop()

    def open_session(self, request_id: str, bundle_id: str) -> dict[str, Any]:
        """A persistent session on a READY bundle; a RESEARCH need gets its approved compute budget."""
        record = self.store.get_bundle(bundle_id)
        cpu = None
        if record is not None:
            need = self.store.get_need(record["need_id"])
            research = (need or {}).get("research") or {}
            cpu = (research.get("constraints") or {}).get("compute_seconds")
        return self.sessions.open(request_id, bundle_id, cpu_seconds=cpu)

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
        earlier = self.store.completion_for_session(session_id)
        if earlier is not None and earlier["coverage_status"] == "PASS":
            return {**earlier["final_status"], "replayed": True}
        bundle = self.store.get_bundle(record["bundle_id"])["manifest"]
        need = self.get_need(bundle["need_id"])
        executions = self.store.executions_for(session_id)
        outputs = [o for o in self.store.outputs_for(session_id)
                   if any(e["execution_id"] == o["execution_id"] and e["status"] == "OK" for e in executions)]
        manifest = execution_manifest(record, bundle, executions, outputs)
        processing = processing_coverage(need, manifest)
        delivery = bundle.get("coverage") or {}
        by_request = {r["data_request_id"]: r for r in delivery.get("requests") or []}
        requests = []
        for item in processing:
            delivered = by_request.get(item["data_request_id"]) or {}
            delivered_ranges = {r["range_id"]: r["status"] for r in delivered.get("ranges") or []}
            ranges = [{"range_id": r["range_id"], "delivery": delivered_ranges.get(r["range_id"], "FAIL"),
                       "processing": r["status"],
                       "status": "PASS" if delivered_ranges.get(r["range_id"]) == "PASS"
                       and r["status"] == "PROCESSED" else "FAIL"} for r in item["ranges"]]
            status = "PASS" if delivered.get("status") == "PASS" and item["status"] == "PROCESSED" else "FAIL"
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
            "research_constraints": research.get("constraints") if mode == "RESEARCH" else None}
        coverage = {"coverage_status": coverage_status, "requests": requests,
                    "delivery_issues": [i for r in delivery.get("requests") or [] for i in r.get("issues") or []][:10]}
        released = []
        if passed:
            self.store.release_outputs([o["output_id"] for o in outputs])
            released = [{k: o[k] for k in ("output_id", "name", "type", "format", "row_count", "columns")}
                        for o in outputs]
        completion_id = f"cmp_{secrets.token_hex(12)}"
        result = {"completion_id": completion_id, "session_id": session_id, "bundle_id": record["bundle_id"],
                  "need_id": bundle["need_id"], "status": "COMPLETED" if passed else "INCOMPLETE",
                  "final_status": final, "coverage": coverage, "released_outputs": released,
                  "execution_manifest_sha256": sha256_json(manifest)}
        if passed:
            result["next_action"] = "ANSWER_FROM_RELEASED_OUTPUTS"
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
        self.store.insert_completion({"completion_id": completion_id, "session_id": session_id,
                                      "request_id": request_id, "bundle_id": record["bundle_id"],
                                      "need_id": bundle["need_id"], "coverage_status": coverage_status,
                                      "execution_manifest": manifest, "coverage": coverage,
                                      "final_status": result, "created_at": utc_now()})
        if passed:
            self.sessions.close(session_id, "COMPLETED")
        self._log("analysis_completed", request_id=request_id, session_id=session_id, completion_id=completion_id,
                  coverage=coverage_status, execution=execution, released=len(released),
                  evidence_label=final["evidence_label"])
        return result

    def get_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        record = self.store.get_bundle(bundle_id)
        return None if record is None else {**record["manifest"], "status": record["status"]}
