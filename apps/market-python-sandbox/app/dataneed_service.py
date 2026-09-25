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

from .data_need import Limits, contract_tables, sha256_json, validate
from .datasets import DatasetFailure
from .dataneed_store import DataNeedStore
from .records import utc_now
from .research_governance import check_request
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
        return {"status": "REJECTED", "error": {"code": self.code, "message": self.message, **self.details}}


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
        return {"need_id": need_id, "request_id": record["request_id"], **record["approved"]}
