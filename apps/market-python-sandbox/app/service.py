"""Analysis lifecycle with the Execution Validation Gate.

    create_spec: proposed Analysis Spec -> independent intent check -> immutable contract (spec_id)
    submit:      spec_id + logical inputs + code -> QUEUED
    run:         governed inputs (checksum-verified) -> logical binding -> workspace -> preflight validator
                 -> analysis process -> output collection -> postflight validator -> COMPLETED
                 with a separate validation_status, then the temporary workspace is deleted

execution_status says whether the code ran; validation_status says whether what it produced
matches the approved contract. Jobs wait in a bounded in-process queue and run one per worker slot.
Each slot has its own non-root user id and CPU set; the validator runs as another dedicated user.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import re
import secrets
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .datasets import DatasetFailure, DatasetProvider
from .executor import Executor, Outcome, disk_usage, read_child_json
from .intent import messages_sha256, review
from .isolation import IsolationReport, run_selftest
from .logical import PARTITION_INCOMPLETE, BindingError, GrantedFile, bind
from .models import TERMINAL, AnalysisRequest, AnalysisResult, next_action
from .outputs import OutputRejected, OutputStore
from .policy import check_source
from .records import Records, utc_now
from .research_policy import research_context as build_research_context
from .research_policy import review as research_review
from .spec import (SPEC_VERSION, SpecInvalid, SpecRequest, convention_notes, derived_feature_definitions, normalize,
                   output_contract, reference_date, required_input, resolve_period, sha256_json)
from .spec_v2 import (SPEC_VERSION_V2, AnalysisSpecV2, catalog_tables, normalize_v2, review_scope, scope_document,
                      scope_sha256)

logger = logging.getLogger("market_python_sandbox")
RUNTIME_VERSION = "market-python-sandbox/v2"
PRICE_TABLES = {"Price_Stock_Indonesia_IDX", "Feature_01_Stock_Daily"}
PRICE_CHANGE_METHODS = {"RETURN", "FORWARD_RETURN", "EVENT_STUDY", "CORRELATION", "ROLLING_CORRELATION", "CUSTOM"}
CORPORATE_ACTIONS_MESSAGE = (
    "Prices are split-adjusted as fetched (TradingView adjustment=splits) and are not dividend-adjusted; history stored "
    "before a later split is not re-adjusted. Returns that span a corporate action can be distorted.")
# Failures worth resubmitting unchanged; any other identical resubmission returns the recorded result.
TRANSIENT_ERRORS = {"SANDBOX_RESTARTED", "DATASET_UNAVAILABLE", "DATASET_STORAGE_UNAVAILABLE", "INTERNAL_ERROR",
                    "SANDBOX_ISOLATION_UNAVAILABLE", "VALIDATOR_ERROR"}
OUTCOME_ERRORS = {
    "TIMEOUT": ("RUNTIME_LIMIT_EXCEEDED", "The analysis exceeded the sandbox runtime limit and was stopped."),
    "CPU": ("RUNTIME_LIMIT_EXCEEDED", "The analysis exceeded its CPU-time budget and was stopped."),
    "MEMORY": ("MEMORY_LIMIT_EXCEEDED", "The analysis exceeded the sandbox memory limit and was stopped."),
    "DISK": ("OUTPUT_LIMIT_EXCEEDED", "The analysis wrote more data than the sandbox disk quota and was stopped."),
    "FORBIDDEN": ("FORBIDDEN_OPERATION", "The analysis attempted an operation the sandbox forbids and was stopped."),
    "CRASH": ("PYTHON_EXCEPTION", "The analysis process crashed."),
}
CHILD_ERRORS = {"PYTHON_EXCEPTION", "SYNTAX_ERROR", "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED", "OUTPUT_INVALID",
                "FORBIDDEN_OPERATION", "INSUFFICIENT_HISTORY", "DUPLICATE_OBSERVATIONS",
                "MATERIALIZATION_LIMIT_EXCEEDED"}
# Preflight problems that more (or differently requested) data would fix, versus unusable inputs.
DATA_SHORTFALL_CODES = {"INSUFFICIENT_WARMUP_HISTORY", "PERIOD_NOT_COVERED", "ANALYSIS_SCOPE_MISMATCH",
                        "UNIVERSE_MISMATCH"}
APPROVED = {"APPROVED", "APPROVED_WITH_UNVERIFIED"}
EVIDENCE_ITEMS = 40
RETAIN_MARKER = ".retain_until"


class ServiceUnavailable(Exception):
    def __init__(self, code: str, message: str, http_status: int, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.http_status, self.retry_after = code, message, http_status, retry_after


def _write_readonly(path: Path, payload: Any) -> None:
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload, default=str), encoding="utf-8")
    os.chmod(path, 0o444)


def prepare_workspace(settings: Settings, job_dir: Path, uid: int | None, validator_uid: int | None, *,
                      manifest: dict[str, Any], analysis_spec: dict[str, Any], code: str) -> None:
    """Create a job workspace. Root owns everything the analysis must not change (manifest, spec,
    code, inputs); the slot user owns only intermediate/ and output/; the validator user owns only
    validation/result/. Neither child user can list the jobs root or read another job."""
    jobs_root = Path(settings.jobs_dir)
    jobs_root.mkdir(parents=True, exist_ok=True)
    os.chmod(jobs_root, 0o711)
    job_dir.mkdir(mode=0o755)
    (job_dir / "input").mkdir(mode=0o755)
    for private in ("intermediate", "output"):
        path = job_dir / private
        path.mkdir(mode=0o700)
    owned = [job_dir / "intermediate", job_dir / "output"]
    for sub in ("home", "tmp", ".duckdb_tmp"):
        path = job_dir / "intermediate" / sub
        path.mkdir(mode=0o700)
        owned.append(path)
    mpl_cache = Path(settings.mpl_cache_dir)
    if mpl_cache.is_dir():  # prebuilt matplotlib font cache, so no analysis rebuilds it
        target = job_dir / "intermediate" / "home" / ".matplotlib"
        shutil.copytree(mpl_cache, target)
        owned += [target, *target.rglob("*")]
    validation = job_dir / "validation"
    validation.mkdir(mode=0o755)
    (validation / "outputs").mkdir(mode=0o755)
    validator_owned = []
    for sub in ("result", "home"):
        path = validation / sub
        path.mkdir(mode=0o700)
        validator_owned.append(path)
    (validation / "home" / "tmp").mkdir(mode=0o700)
    validator_owned.append(validation / "home" / "tmp")
    if uid is not None:
        for path in owned:
            os.chown(path, uid, uid, follow_symlinks=False)
    if validator_uid is not None:
        for path in validator_owned:
            os.chown(path, validator_uid, validator_uid, follow_symlinks=False)
    _write_readonly(job_dir / "manifest.json", manifest)
    _write_readonly(job_dir / "analysis_spec.json", analysis_spec)
    _write_readonly(job_dir / "analysis.py", code)


def idempotency_key(request: AnalysisRequest, code_sha256: str) -> str:
    material = json.dumps([request.request_id, request.spec_id,
                           sorted([b.name, sorted(b.dataset_ids), b.duplicate_policy] for b in request.inputs),
                           code_sha256, sorted(request.expected_outputs)], separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


def _view_sql(logical: dict[str, Any], job_dir: Path, overlapping: bool) -> str:
    """How the analysis sees a logical input: the union of its files, and one row per key only when the
    preflight found overlapping rows (deduplicating needs every row at once, so it is not done needlessly)."""
    files = sorted(logical["files"], key=lambda f: f.get("created_at") or "")
    paths = [str(job_dir / f["local_path"]) for f in files]
    listed = ", ".join("'" + p.replace("'", "''") + "'" for p in paths)
    if len(paths) == 1 or not overlapping:
        return f"SELECT * FROM read_parquet([{listed}])"
    ranks = " ".join(f"WHEN '{p}' THEN {i}" for i, p in enumerate(paths))
    keys = ", ".join('"' + k.replace('"', '""') + '"' for k in logical["key_columns"])
    return (f"SELECT * EXCLUDE (filename, _saniti_rank) FROM (SELECT *, row_number() OVER (PARTITION BY {keys} "
            f"ORDER BY CASE filename {ranks} END DESC) AS _saniti_rank FROM read_parquet([{listed}], filename=true)) "
            f"WHERE _saniti_rank = 1")


class AnalysisService:
    def __init__(self, settings: Settings, *, records: Records | None = None, datasets: DatasetProvider | None = None,
                 executor: Executor | None = None) -> None:
        self.settings = settings
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        os.chmod(settings.data_dir, 0o700)
        self.records = records or Records(Path(settings.data_dir) / "analyses.sqlite3")
        self.datasets = datasets or DatasetProvider(settings)
        self.datasets.on_cached = self._cached
        self.executor = executor or Executor(settings)
        self.outputs = OutputStore(settings, self.records)
        self.queue: queue.Queue[str] = queue.Queue(maxsize=settings.max_queued)
        self.events: dict[str, threading.Event] = {}
        self.running: dict[str, int] = {}  # analysis_id -> child pid (for cancel)
        self.active: set[str] = set()      # workspaces the janitor must not touch
        self.sources: dict[str, str] = {}  # queued source code, held in memory until the job starts
        self.cancelled: set[str] = set()
        self._lock = threading.Lock()
        self._submit_lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.isolation = IsolationReport(failure="self-test has not run")
        available = sorted(os.sched_getaffinity(0))
        self.slots = [
            (settings.slot_uid_base + i,
             [available[(i * settings.cpus_per_job + j) % len(available)] for j in range(settings.cpus_per_job)])
            for i in range(settings.concurrency)]

    # ------------------------------------------------------------ lifecycle

    def start(self, run_workers: bool = True) -> None:
        interrupted = self.records.interrupt_unfinished(utc_now())
        workspaces = self.cleanup_workspaces()  # crash/redeploy leftovers; retained failures keep their TTL
        uid, cpus = self.slots[0]
        self.isolation = run_selftest(self.settings, self.executor, uid, cpus)
        self._log("sandbox_started", interrupted_analyses=interrupted, orphan_workspaces_removed=workspaces,
                  isolation_enforced=self.isolation.ok, isolation_failure=self.isolation.failure,
                  versions=self.isolation.versions)
        if not run_workers:
            return
        for index in range(self.settings.concurrency):
            thread = threading.Thread(target=self._worker, args=(index,), name=f"sandbox-slot-{index}", daemon=True)
            thread.start()
            self._threads.append(thread)
        if self.settings.cleanup_interval_seconds > 0:
            thread = threading.Thread(target=self._janitor, name="sandbox-janitor", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self, timeout: float = 10.0) -> None:
        """Shut down: running analyses are killed and recorded as SANDBOX_RESTARTED."""
        self._stop.set()
        with self._lock:
            pids = list(self.running.values())
        for pid in pids:
            try:
                os.killpg(pid, 9)
            except ProcessLookupError:
                pass
        for _ in range(self.settings.concurrency):
            try:
                self.queue.put_nowait("")
            except queue.Full:
                pass
        deadline = time.monotonic() + timeout
        for thread in self._threads:
            thread.join(max(0.0, deadline - time.monotonic()))

    # ------------------------------------------------------------ specs

    def create_spec(self, request: SpecRequest) -> dict[str, Any]:
        """Check a proposed Analysis Spec against the user's own messages; store it only if approved."""
        try:
            ZoneInfo(request.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return {"status": "INVALID_SPEC", "problems": [f"unknown timezone {request.timezone!r}"],
                    "next_action": "REVISE_SPEC"}
        ref = reference_date(request.reference_time, request.timezone)
        v2 = isinstance(request.spec, AnalysisSpecV2)
        catalog = None
        try:
            if v2:
                # Every table, column, relationship, frequency and subject is checked against the Governor's catalog
                # contract; the approved contract keeps the per-table catalog hashes.
                try:
                    catalog = self.datasets.catalog_contract(catalog_tables(request.spec),
                                                             request_id=request.request_id)
                except DatasetFailure as failure:
                    self._log("sandbox_spec_review", request_id=request.request_id, status="CATALOG_UNAVAILABLE")
                    return {"status": "CATALOG_UNAVAILABLE", "problems": [failure.message], "next_action": "RETRY_LATER"}
                spec = normalize_v2(request.spec, ref, catalog)
                data_plan = spec.pop("data_plan")
            else:
                spec = normalize(request.spec, ref)
        except SpecInvalid as exc:
            self._log("sandbox_spec_review", request_id=request.request_id, status="INVALID_SPEC",
                      problems=len(exc.problems), spec_version="2.0" if v2 else "1")
            return {"status": "INVALID_SPEC", "problems": exc.problems[:30], "next_action": "REVISE_SPEC",
                    "problem_codes": sorted({m.group(1) for p in exc.problems
                                             for m in [re.search(r"\(([A-Z][A-Z0-9_]+)\)$", p)] if m})}
        messages = [m.model_dump() for m in request.user_messages]
        # The same spec for the same request and user messages is the same experiment: a retry returns the
        # stored spec_id and reserves nothing again.
        key = sha256_json({"request_id": request.request_id, "spec": spec, "messages": messages_sha256(messages),
                           "reference_date": ref.isoformat(), "timezone": request.timezone})
        existing = self.records.find_spec_by_key(request.request_id, key)
        if existing and existing.get("review"):
            self._log("sandbox_spec_review", request_id=request.request_id, status=existing["status"],
                      spec_id=existing["spec_id"], replayed=True)
            return {**existing["review"], "replayed": True}
        result, found = review(spec, messages, ref)
        if v2:
            _review_v2_scope(spec, found, result)
        resolved = resolve_period(spec["analysis_period"], ref)
        needs = required_input(spec, resolved, ref)
        features = derived_feature_definitions(spec)
        status = result.status
        body: dict[str, Any] = {
            "status": status, "reference": {"date": ref.isoformat(), "timezone": request.timezone,
                                            "reference_time": request.reference_time.isoformat()},
            "resolved_period": resolved, "required_input": needs,
            "checks": result.checks, "mismatches": result.mismatches,
            "unverified_requirements": result.unverified, "clarification_needed": result.clarifications,
            "expected_requirements": found.record(), "output_contract": output_contract(spec),
            "derived_features": features, "convention_notes": convention_notes(spec),
            "next_action": {"APPROVED": "PREPARE_DATA_THEN_RUN_ANALYSIS" if v2 else "REQUEST_DATA_THEN_RUN_ANALYSIS",
                            "APPROVED_WITH_UNVERIFIED": "PREPARE_DATA_THEN_RUN_ANALYSIS" if v2
                            else "REQUEST_DATA_THEN_RUN_ANALYSIS",
                            "ANALYSIS_SPEC_MISMATCH": "REVISE_SPEC_TO_MATCH_REQUEST",
                            "NEEDS_CLARIFICATION": "ASK_USER_CLARIFICATION"}[status],
        }
        v2_contract: dict[str, Any] = {}
        if v2:
            profile = "X_RESEARCH" if spec["analysis_type"] == "RESEARCH" else "Y_ANALYSIS"
            plan = data_plan
            for name, entry in plan.items():
                window = needs[name]["recommended_request_date_range"]
                entry["date_range"] = {"column": entry["time_column"], "from": window["from"], "to": window["to"]} \
                    if window and entry["time_column"] else None
            digest_scope = scope_sha256(spec, resolved)
            source_contracts = {name: source_contract(meta) for name, meta in catalog["tables"].items()}
            v2_contract = {"analysis_type": spec["analysis_type"], "validation_profile": profile,
                           "scope_sha256": digest_scope, "scope": scope_document(spec, resolved), "data_plan": plan,
                           "catalog": {"catalog_sha256": catalog.get("catalog_sha256"),
                                       "catalog_version": catalog.get("catalog_version"),
                                       "tables": {n: m.get("catalog_table_sha256") for n, m in catalog["tables"].items()},
                                       "source_contracts": source_contracts}}
            body.update(analysis_type=spec["analysis_type"], validation_profile=profile, scope_sha256=digest_scope,
                        data_plan=[{"input": e["input"], "source_table": e["source_table"], "role": e["role"],
                                    "joins": e["joins"], "filters": len(e["filters"]), "date_range": e["date_range"]}
                                   for e in plan.values()])
        governor = None
        if status in APPROVED:
            if self.records.count_specs(request.request_id) >= self.settings.max_specs_per_request:
                return {"status": "REQUEST_BUDGET_EXCEEDED", "next_action": "REPORT_LIMITATION",
                        "problems": ["This request has reached its limit of analysis specs."]}
            if (spec.get("analysis_type") == "RESEARCH") if v2 else spec.get("research"):
                with self._submit_lock:  # one reservation at a time per service
                    governor, context = self._govern(request.request_id, spec, resolved)
                body["governor"] = governor
                if governor["decision"] != "APPROVED":
                    body.update(status=governor["decision"],
                                next_action="REVISE_SPEC" if governor["decision"] == "REPLAN_REQUIRED"
                                else "REPORT_LIMITATION")
                    self._log("sandbox_research_decision", request_id=request.request_id,
                              decision=governor["decision"], reason_code=governor["reason_code"],
                              budget=governor["budget_before"])
                    return body
            else:
                context = {"evidence_standard": "CALCULATION"}
            contract = {"spec_version": SPEC_VERSION_V2 if v2 else SPEC_VERSION, **v2_contract,
                        "request_id": request.request_id, "reference": body["reference"],
                        "spec": spec, "resolved_period": resolved, "required_input": needs,
                        "review": {"status": status, "checks": result.checks,
                                   "unverified_requirements": result.unverified},
                        "expected_requirements": body["expected_requirements"], "derived_features": features,
                        "user_messages_sha256": messages_sha256(messages), "governor": governor,
                        "research_context": context}
            spec_id = f"spec_{secrets.token_hex(12)}"
            digest = sha256_json(contract)
            body.update(spec_id=spec_id, spec_sha256=digest)
            self.records.insert_spec(spec_id, request.request_id, utc_now(), digest, status, contract,
                                     idempotency_key=key, review=body)
            if governor:
                self._log("sandbox_research_decision", request_id=request.request_id, spec_id=spec_id,
                          decision="APPROVED", evidence_standard=context["evidence_standard"],
                          hypothesis_id=context.get("hypothesis_id"), budget=governor["budget_after_reservation"])
        self._log("sandbox_spec_review", request_id=request.request_id, status=status, spec_id=body.get("spec_id"),
                  mismatches=len(result.mismatches), unverified=len(result.unverified),
                  clarifications=len(result.clarifications))
        return body

    def _govern(self, request_id: str, spec: dict[str, Any], resolved: dict[str, Any]
                ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Research Governor pre-run decision for one experiment (called under the submit lock)."""
        policy = self.settings.research_policy()
        experiments = self.records.research_experiments(request_id)
        parent = None
        followup = spec["research"].get("followup_of")
        if followup:
            row = self.records.get_spec(followup)
            parent_research = (row or {}).get("research") or {}
            parent = {"exists": bool(row and row["request_id"] == request_id and parent_research),
                      "hypothesis_id": (parent_research.get("hypothesis") or {}).get("id"),
                      "completed": bool(row) and self.records.spec_completed(followup)}
        decision = research_review(spec, resolved, experiments, parent, policy)
        context = build_research_context(spec, decision, experiments, policy) \
            if decision["decision"] == "APPROVED" else None
        return decision, context

    # ------------------------------------------------------------ research runs (audit)

    def run_summary(self, request_id: str) -> dict[str, Any] | None:
        """Everything this service knows about one orchestrator run: experiments, governor decisions, analyses
        with their code, data and validation fingerprints, evidence decisions, budgets, and the final report."""
        specs = self.records.specs_for(request_id)
        analyses = self.records.analyses_for(request_id)
        report = self.records.get_run_report(request_id)
        if not specs and not analyses and report is None:
            return None
        s = self.settings
        policy = s.research_policy()
        from .research_policy import ledger

        experiments = self.records.research_experiments(request_id)
        counters = ledger(experiments)
        usage = self.records.request_usage(request_id)
        rows = []
        for a in analyses:
            assessment = a.get("evidence_assessment") or fallback_assessment(a) or {}
            rows.append({
                "analysis_id": a["analysis_id"], "spec_id": a.get("spec_id"), "spec_sha256": a.get("spec_sha256"),
                "execution_status": a["status"], "validation_status": a.get("validation_status"),
                "validation_level": a.get("validation_level"), "reason_codes": a.get("reason_codes") or [],
                "code_sha256": a["code_sha256"], "dataset_ids": a["dataset_ids"],
                "datasets": {ds: {k: m.get(k) for k in ("checksum_sha256", "row_count", "source_tables",
                                                        "completeness_status", "actual_date_range")}
                             for ds, m in (a.get("inputs") or {}).items()},
                "evidence": {k: assessment.get(k) for k in ("claim_type", "decision", "evidence_level", "checks",
                                                            "reporting_constraints")},
                "leakage_check": (a.get("leakage_check") or {}).get("result"),
                "cpu_seconds": a.get("cpu_seconds"), "created_at": a["created_at"], "completed_at": a.get("completed_at"),
            })
        active = any(a["status"] in ("QUEUED", "RUNNING") for a in analyses)
        return {
            "request_id": request_id,
            "status": "ACTIVE" if active else "REPORTED" if report else "AWAITING_REPORT",
            "experiments": [{"spec_id": x["spec_id"], "spec_sha256": x["spec_sha256"], "created_at": x["created_at"],
                             "status": x["status"], "question": x["contract"]["spec"]["question"],
                             "research": x.get("research"),
                             "governor": {k: (x["contract"].get("governor") or {}).get(k) for k in
                                          ("decision", "reason_code", "budget_after_reservation")}
                             if x["contract"].get("governor") else None}
                            for x in specs],
            "analyses": rows,
            "budget": {"analyses": {"used": usage["analyses"], "max": s.max_analyses_per_request},
                       "specs": {"used": len(specs), "max": s.max_specs_per_request},
                       "cpu_seconds": {"used": round(usage["cpu_seconds"], 3), "max": s.max_cpu_seconds_per_request},
                       "research": {"experiments": {"used": counters["experiments"], "max": policy.max_experiments},
                                    "hypotheses": {"used": len(counters["hypotheses"]),
                                                   "max": policy.max_hypotheses},
                                    "followups": counters["followups"],
                                    "max_followups_per_hypothesis": policy.max_followups_per_hypothesis}},
            "report": report,
        }

    def put_report(self, request_id: str, report: dict[str, Any]) -> dict[str, Any]:
        stored = self.records.put_run_report(request_id, utc_now(), report)
        self._log("sandbox_run_report", request_id=request_id, stored=stored, status=report.get("status"),
                  evidence_label=report.get("evidence_label"))
        return {"request_id": request_id, "stored": stored,
                "detail": None if stored else "A report for this request already exists; the first one is kept."}

    def get_spec(self, spec_id: str) -> dict[str, Any] | None:
        row = self.records.get_spec(spec_id)
        if row is None:
            return None
        return {"spec_id": spec_id, "spec_sha256": row["spec_sha256"], "status": row["status"],
                "created_at": row["created_at"], **row["contract"]}

    # ------------------------------------------------------------ API operations

    def submit(self, request: AnalysisRequest) -> dict[str, Any]:
        s = self.settings
        if not self.isolation.ok:
            raise ServiceUnavailable("SANDBOX_ISOLATION_UNAVAILABLE",
                                     "The Python sandbox cannot verify its isolation and is refusing analyses.", 503)
        if len(request.inputs) > s.max_logical_datasets:
            raise ServiceUnavailable("INVALID_REQUEST", f"At most {s.max_logical_datasets} logical inputs.", 422)
        if len(request.dataset_ids) > s.max_input_files:
            raise ServiceUnavailable("INVALID_REQUEST", f"At most {s.max_input_files} input files per analysis.", 422)
        if len(request.python_code) > s.max_code_chars:
            raise ServiceUnavailable("INVALID_REQUEST", f"python_code exceeds {s.max_code_chars} characters.", 422)
        spec = self.records.get_spec(request.spec_id)
        if spec is None or spec["request_id"] != request.request_id or spec["status"] not in APPROVED:
            raise ServiceUnavailable("SPEC_NOT_FOUND", "No approved analysis spec with this spec_id exists for this "
                                                       "request. Create one with create_analysis_spec.", 422)
        code_sha256 = hashlib.sha256(request.python_code.encode()).hexdigest()
        key = idempotency_key(request, code_sha256)
        with self._submit_lock:
            existing = self.records.find_by_key(key)
            if existing and not (existing["status"] == "FAILED" and existing["error_code"] in TRANSIENT_ERRORS):
                return self.wait(existing["analysis_id"], s.submit_wait_seconds)
            usage = self.records.request_usage(request.request_id)
            if usage["analyses"] >= s.max_analyses_per_request:
                raise ServiceUnavailable("REQUEST_BUDGET_EXCEEDED", "This request has used all of its Python analyses.",
                                         429)
            if usage["cpu_seconds"] >= s.max_cpu_seconds_per_request - 5:
                raise ServiceUnavailable("REQUEST_BUDGET_EXCEEDED", "This request has used its Python compute budget.",
                                         429)
            analysis_id = f"ana_{secrets.token_hex(12)}"
            now = utc_now()
            record = {
                "analysis_id": analysis_id, "idempotency_key": key, "request_id": request.request_id,
                "status": "QUEUED", "validation_status": "PENDING", "validation_level": "EXECUTION_ONLY",
                "purpose": spec["contract"]["spec"]["question"], "dataset_ids": request.dataset_ids,
                "logical_inputs": [b.model_dump() for b in request.inputs], "spec_id": request.spec_id,
                "spec_sha256": spec["spec_sha256"], "expected_outputs": request.expected_outputs,
                "code_sha256": code_sha256, "code": request.python_code if s.retain_code else None, "created_at": now,
                "lineage": self._lineage(code_sha256, spec),
                "research_context": spec["contract"].get("research_context") or {"evidence_standard": "CALCULATION"},
                "derived_features": spec["contract"]["derived_features"],
            }
            violation = check_source(request.python_code)
            if violation is not None:
                self.records.insert({**record, "status": "FAILED", "validation_status": "UNVERIFIED",
                                     "reason_codes": [violation.code], "completed_at": now,
                                     "error_code": violation.code, "error_message": violation.message,
                                     "error_frames": [{"line": violation.line}] if violation.line else []})
                self._log_result(analysis_id)
                return self.render(self.records.get(analysis_id))
            with self._lock:
                self.events[analysis_id] = threading.Event()
                self.sources[analysis_id] = request.python_code
            self.records.insert(record)
        try:
            self.queue.put_nowait(analysis_id)
        except queue.Full:
            self.records.update(analysis_id, status="FAILED", validation_status="UNVERIFIED", completed_at=utc_now(),
                                error_code="QUEUE_FULL", error_message="The sandbox queue is full.")
            with self._lock:
                self.sources.pop(analysis_id, None)
            self._finish_event(analysis_id)
            raise ServiceUnavailable("QUEUE_FULL", "The sandbox is busy; retry later.", 429, s.retry_after_seconds)
        return self.wait(analysis_id, s.submit_wait_seconds)

    def wait(self, analysis_id: str, seconds: float) -> dict[str, Any]:
        record = self.records.get(analysis_id)
        if record is None:
            raise KeyError(analysis_id)
        if record["status"] not in TERMINAL and seconds > 0:
            with self._lock:
                event = self.events.get(analysis_id)
            if event is not None:
                event.wait(seconds)
            record = self.records.get(analysis_id)
        return self.render(record)

    def cancel(self, analysis_id: str) -> dict[str, Any]:
        record = self.records.get(analysis_id)
        if record is None:
            raise KeyError(analysis_id)
        if self.records.transition(analysis_id, {"QUEUED"}, status="CANCELLED", validation_status="UNVERIFIED",
                                   completed_at=utc_now(), error_code="CANCELLED",
                                   error_message="Cancelled before it started."):
            with self._lock:
                self.sources.pop(analysis_id, None)
            self._finish_event(analysis_id)
        elif record["status"] == "RUNNING":
            with self._lock:
                self.cancelled.add(analysis_id)
                pid = self.running.get(analysis_id)
            if pid:
                try:
                    os.killpg(pid, 9)
                except ProcessLookupError:
                    pass
        return self.wait(analysis_id, 5)

    # ------------------------------------------------------------ worker

    def _worker(self, index: int) -> None:
        uid, cpus = self.slots[index]
        while not self._stop.is_set():
            analysis_id = self.queue.get()
            if not analysis_id:
                continue
            try:
                self._run(analysis_id, uid, cpus)
            except Exception as exc:  # noqa: BLE001 - never let a worker die
                self.records.update(analysis_id, status="FAILED", validation_status="UNVERIFIED",
                                    completed_at=utc_now(), error_code="INTERNAL_ERROR",
                                    error_message=f"Internal sandbox error ({type(exc).__name__}).")
                logger.exception("sandbox_internal_error")
            finally:
                self._finish_event(analysis_id)
                self._log_result(analysis_id)

    def _run(self, analysis_id: str, uid: int, cpus: list[int]) -> None:
        s = self.settings
        with self._lock:
            source = self.sources.pop(analysis_id, None)
            self.active.add(analysis_id)
        job_dir = Path(s.jobs_dir) / analysis_id
        failed = True
        try:
            if source is None or not self.records.transition(analysis_id, {"QUEUED"}, status="RUNNING",
                                                             started_at=utc_now()):
                failed = False
                return  # cancelled while queued
            failed = self._execute_job(analysis_id, job_dir, uid, cpus, source)
        finally:
            self._release_workspace(analysis_id, job_dir, failed)

    def _execute_job(self, analysis_id: str, job_dir: Path, uid: int, cpus: list[int], source: str) -> bool:
        """Run one job end to end. Returns True when the job failed (its workspace may be retained)."""
        s = self.settings
        record = self.records.get(analysis_id)
        contract = self.records.get_spec(record["spec_id"])["contract"]
        drop = self.executor.drop_privileges
        started = time.monotonic()
        try:
            granted, paths = self._prepare_inputs(record)
        except DatasetFailure as failure:
            self._finish(analysis_id, "FAILED", error=(failure.code, failure.message))
            return True
        download_ms = round((time.monotonic() - started) * 1000)
        try:
            logical = bind(contract["spec"], record["logical_inputs"], granted, s.max_input_files,
                           {"spec_id": record["spec_id"], "spec_sha256": record["spec_sha256"], **contract})
        except BindingError as exc:
            status = "INCOMPLETE" if exc.code in PARTITION_INCOMPLETE else "FAILED"
            self._finish(analysis_id, "FAILED", error=("INPUT_VALIDATION_FAILED", exc.message),
                         validation=(status, [exc.code]), evidence=[{"check": "input.binding",
                                                                     "result": "INCOMPLETE" if status == "INCOMPLETE"
                                                                     else "FAIL", "code": exc.code, **exc.details}])
            return True
        manifest = {"job_id": analysis_id, "analysis_id": analysis_id, "spec_id": record["spec_id"],
                    "logical_datasets": logical,
                    "scope_evidence": [info["scope_evidence"] for info in logical.values() if info["scope_evidence"]],
                    "validation_profile": contract.get("validation_profile") or (
                        "X_RESEARCH" if contract["spec"].get("research") else "Y_ANALYSIS")}
        self.records.update(analysis_id, database_features={
            name: info["database_features"] for name, info in logical.items() if info["database_features"]})
        analysis_spec = {"spec_id": record["spec_id"], "spec_sha256": record["spec_sha256"], **contract}
        prepare_workspace(s, job_dir, uid if drop else None, s.validator_uid if drop else None,
                          manifest=manifest, analysis_spec=analysis_spec, code=source)
        for name, file in granted.items():
            DatasetProvider.link(paths[name], job_dir / "input" / file.local_name)
        inputs = {g.dataset_id: {k: g.manifest.get(k) for k in (
            "checksum_sha256", "row_count", "byte_count", "source_tables", "query_id", "completeness_status",
            "missing_entities_count", "actual_date_range", "numeric_float64_columns", "expires_at")}
            for g in granted.values()}
        input_rows = sum(i["row_count"] or 0 for i in inputs.values())
        input_bytes = sum(i["byte_count"] or 0 for i in inputs.values())
        self.records.update(analysis_id, inputs=inputs, input_rows=input_rows, input_bytes=input_bytes)
        warnings = [{"code": "NUMERIC_AS_FLOAT64", "message": (
            f"{ds}: numeric columns {meta['numeric_float64_columns'][:10]} are float64 (not decimal-exact). Suitable "
            f"for indicators, returns, and statistics; not for exact accounting reconciliation.")}
            for ds, meta in inputs.items() if meta.get("numeric_float64_columns")]
        price_sources = {t for meta in inputs.values() for t in (meta.get("source_tables") or [])} & PRICE_TABLES
        if price_sources and {c["method"] for c in contract["spec"]["calculations"]} & PRICE_CHANGE_METHODS:
            warnings.append({"code": "CORPORATE_ACTIONS_NOT_ADJUSTED", "message": CORPORATE_ACTIONS_MESSAGE})

        # preflight: does the bound data cover the contract?
        pre, pre_outcome = self._validate(job_dir, "preflight", cpus, {})
        usage: dict[str, Any] = {"download_ms": download_ms, "input_rows": input_rows, "input_bytes": input_bytes,
                                 "input_files": len(granted), "validator_cpu_seconds": pre_outcome.cpu_seconds}
        if pre is None or pre.get("validator_error"):
            self._finish(analysis_id, "FAILED", error=("VALIDATOR_ERROR", "The independent validator could not check "
                                                       "the inputs." + _validator_detail(pre, pre_outcome)),
                         usage=usage, warnings=warnings)
            return True
        expected_scope = self._expected_scope(contract, pre)
        if pre["blocking"]:
            codes = sorted({b["code"] for b in pre["blocking"]})
            status = "INCOMPLETE" if set(codes) <= DATA_SHORTFALL_CODES else "FAILED"
            message = " ".join(b["message"] for b in pre["blocking"])[:800]
            self._finish(analysis_id, "FAILED", error=("INPUT_VALIDATION_FAILED", message),
                         validation=(status, codes), evidence=pre["evidence"] + [
                             {"check": "preflight", "result": "FAIL", **b} for b in pre["blocking"]],
                         expected_scope=expected_scope, usage=usage, warnings=warnings)
            return True

        # the analysis itself
        request_usage = self.records.request_usage(record["request_id"])
        cpu_budget = max(5, min(s.cpu_seconds, int(s.max_cpu_seconds_per_request - request_usage["cpu_seconds"])))
        self._write_runtime(job_dir, logical, pre, cpus, record["expected_outputs"], cpu_budget)
        outcome = self._execute(analysis_id, job_dir, uid, cpu_budget)
        usage.update(cpu_seconds=outcome.cpu_seconds, max_rss_mb=outcome.max_rss_mb,
                     peak_intermediate_bytes=outcome.notes.get("peak_disk_bytes", {}).get("intermediate"),
                     peak_output_dir_bytes=outcome.notes.get("peak_disk_bytes", {}).get("output"))
        diagnostics = {"stdout_tail": outcome.stdout_tail, "stderr_tail": outcome.stderr_tail}
        with self._lock:
            was_cancelled = analysis_id in self.cancelled
            self.cancelled.discard(analysis_id)
        common = {"outcome": outcome, "usage": usage, "diagnostics": diagnostics, "warnings": warnings,
                  "expected_scope": expected_scope}
        if self._stop.is_set() and not was_cancelled:
            self._finish(analysis_id, "FAILED", error=("SANDBOX_RESTARTED", "The sandbox shut down while this "
                                                       "analysis was running. Submit it again."), **common)
            return True
        if was_cancelled:
            self._finish(analysis_id, "CANCELLED", error=("CANCELLED", "Cancelled while running."), **common)
            return False
        if outcome.kind != "OK":
            code, message, frames = self._outcome_error(outcome)
            self._finish(analysis_id, "FAILED", error=(code, message), frames=frames, **common)
            return True
        try:
            collected = self.outputs.collect(analysis_id, job_dir / "output", uid if drop else None,
                                             record["expected_outputs"])
        except OutputRejected as rejected:
            self._discard_outputs(analysis_id)
            self._finish(analysis_id, "FAILED", error=(rejected.code, rejected.message), **common)
            return True
        usage.update(output_rows=collected.output_rows, output_bytes=collected.stored_bytes)

        # postflight: what did the outputs actually cover, and do supported calculations recompute?
        declared = self._stage_declared_outputs(job_dir, contract["spec"], collected.outputs)
        post, post_outcome = self._validate(job_dir, "postflight", cpus, {
            "outputs": declared, "research_context": record.get("research_context") or {}})
        usage["validator_cpu_seconds"] = round(usage["validator_cpu_seconds"] + post_outcome.cpu_seconds, 3)
        usage["validator_max_rss_mb"] = max(pre_outcome.max_rss_mb, post_outcome.max_rss_mb)
        if post is None or post.get("validator_error"):
            validation = ("UNVERIFIED", ["VALIDATOR_ERROR"])
            evidence = [{"check": "postflight", "result": "ERROR",
                         "detail": "The independent validator did not complete." + _validator_detail(post, post_outcome)}]
            level, actual_scope = "EXECUTION_ONLY", {}
        else:
            reasons = post["reasons"]
            codes = sorted(c for c, sev in reasons.items() if sev in ("FAILED", "INCOMPLETE")) or \
                sorted(c for c, sev in reasons.items())
            validation = (post["validation_status"], codes)
            evidence = post["evidence"]
            level = post["validation_level"]
            actual_scope = self._actual_scope(pre, post)
            assessment = post.get("evidence_assessment")
            leak = self._leakage_check(analysis_id, record, contract, logical, granted, paths, pre, cpus, uid, source,
                                       job_dir, declared, usage) if status_allows_leak_check(post) else None
            if leak is not None:
                self.records.update(analysis_id, leakage_check=leak)
                evidence = evidence + leak["evidence"]
                if leak["result"] == "FAIL":
                    validation = ("FAILED", sorted(set(validation[1]) | {"TEMPORAL_LEAKAGE_DETECTED"}))
                    level = "EXECUTION_ONLY"
                    assessment = {**(assessment or {}), "decision": "INVALID", "evidence_level": "NONE",
                                  "reporting_constraints": ["The analysis uses information from after each date "
                                                            "(temporal leakage); none of its values may be reported."]}
            self.records.update(analysis_id, evidence_assessment=assessment)
            expected_scope = self._expected_scope(contract, post, pre)
        features = self._feature_results(contract, evidence, level)
        definitions = self.outputs.store_json(analysis_id, "derived_feature_definitions",
                                              {"analysis_id": analysis_id, "spec_id": record["spec_id"],
                                               "features": features})
        index = read_child_json(job_dir / "output" / "index.json", uid if drop else None, 1 << 20) \
            if (job_dir / "output" / "index.json").exists() else {}
        self.records.update(analysis_id, feature_artifact={k: definitions[k] for k in (
            "artifact_id", "format", "byte_count", "checksum_sha256", "expires_at")})
        self._finish(analysis_id, "COMPLETED", outcome=outcome, usage=usage, diagnostics=diagnostics,
                     warnings=warnings + collected.warnings, outputs=collected.outputs,
                     validation=validation, level=level, evidence=evidence, expected_scope=expected_scope,
                     actual_scope=actual_scope, features=features,
                     self_reported={"access_log": (index.get("access_log") or [])[:50] if isinstance(index, dict)
                                    else [], "note": "Reported by the analysis code itself; never used as evidence."})
        return False

    # ------------------------------------------------------------ steps

    def _prepare_inputs(self, record: dict[str, Any]) -> tuple[dict[str, GrantedFile], dict[str, Path]]:
        s = self.settings
        grants = [self.datasets.grant(ds, request_id=record["request_id"], analysis_id=record["analysis_id"])
                  for ds in record["dataset_ids"]]
        rows, size = sum(g.row_count for g in grants), sum(g.byte_count for g in grants)
        if rows > s.max_input_rows or size > s.max_input_bytes:
            raise DatasetFailure("INPUT_LIMIT_EXCEEDED",
                                 f"The input datasets hold {rows} rows / {size} bytes, above the sandbox input limit. "
                                 f"Request narrower data.")
        used = self.records.request_usage(record["request_id"])["input_bytes"]
        if used + size > s.max_input_bytes_per_request:
            raise DatasetFailure("REQUEST_BUDGET_EXCEEDED", "This request has used its Python input-data budget.")
        granted, paths = {}, {}
        for index, grant in enumerate(grants, start=1):
            name = f"input_{index:03d}.parquet"
            granted[grant.dataset_id] = GrantedFile(grant.dataset_id, grant.manifest, name)
            paths[grant.dataset_id] = self.datasets.fetch(grant)
        return granted, paths

    def _write_runtime(self, job_dir: Path, logical: dict[str, Any], pre: dict[str, Any], cpus: list[int],
                       expected_outputs: list[str], cpu_budget: int) -> None:
        s = self.settings
        period = pre["period"]
        overlapping = {item["check"].split(".", 1)[1] for item in pre["evidence"] if item["check"].startswith("input.")
                       and (item.get("identical_duplicates_removed") or item.get("conflicting_duplicates"))}
        runtime = {
            "limits": s.child_limits(cpu_budget), "cpus": cpus, "threads": s.threads_per_job, "require_seccomp": True,
            "seed": s.random_seed, "expected_outputs": expected_outputs,
            "inputs": {name: {"files": [str(job_dir / f["local_path"]) for f in info["files"]],
                              "columns": [c["name"] for c in info["columns"]], "entity_column": info["entity_column"],
                              "date_column": info["date_column"], "source_table": info["source_table"],
                              "grain": info["grain"], "view_sql": _view_sql(info, job_dir, name in overlapping)}
                       for name, info in logical.items()},
            "analysis_period": {"start": period["start"], "end": period["end"],
                                "reference_date": period["reference_date"], "mode": period["mode"]},
            "duckdb": {"memory_limit_mb": s.duckdb_memory_mb, "threads": s.threads_per_job,
                       "temp_directory": str(job_dir / "intermediate" / ".duckdb_tmp"),
                       "max_temp_directory_mb": max(16, s.max_intermediate_bytes // (1 << 20) - 16),
                       "allowed_directories": [str(job_dir / "input") + "/", str(job_dir / "intermediate") + "/"]},
        }
        _write_readonly(job_dir / "runtime.json", runtime)

    def _validate(self, job_dir: Path, mode: str, cpus: list[int], extra: dict[str, Any]
                  ) -> tuple[dict[str, Any] | None, Outcome]:
        s = self.settings
        request = job_dir / "validation" / "request.json"
        if request.exists():
            request.unlink()
        _write_readonly(request, {"mode": mode, "limits": s.validator_limits(), "cpus": cpus, "require_seccomp": True,
                                  "outputs": {}, **extra})
        drop = self.executor.drop_privileges
        home = job_dir / "validation" / "home"
        outcome = self.executor.run(
            job_dir, s.validator_uid, script="validator.py", args=(mode,), cwd=home, home=home, tmp=home / "tmp",
            quotas={home: 64 << 20, job_dir / "validation" / "result": 16 << 20},
            deadline_seconds=s.validator_runtime_seconds, memory_mb=s.validator_memory_mb,
            cpu_seconds=s.validator_limits()["cpu_seconds"], error_dir=job_dir / "validation" / "result",
            log_name=f"validator-{mode}")
        if outcome.kind != "OK":
            return None, outcome
        try:
            return read_child_json(job_dir / "validation" / "result" / f"{mode}.json",
                                   s.validator_uid if drop else None, 8 << 20), outcome
        except (OSError, ValueError):
            return None, outcome

    def _stage_declared_outputs(self, job_dir: Path, spec: dict[str, Any], outputs: list[dict[str, Any]]
                                ) -> dict[str, str]:
        """Copy the stored outputs the spec declares into the validator's read-only view."""
        declared: dict[str, str] = {}
        by_name = {o["name"]: o for o in outputs if o["type"] == "TABLE" or
                   (o["type"] == "ARTIFACT" and o.get("format") == "PARQUET")}
        for index, output in enumerate(spec["outputs"], start=1):
            stored = by_name.get(output["name"])
            if stored is None:
                continue
            entry = self.records.get_file(stored.get("result_id") or stored.get("artifact_id"))
            if entry is None:
                continue
            target = job_dir / "validation" / "outputs" / f"out_{index:03d}.parquet"
            shutil.copyfile(self.outputs.path_for(entry), target)
            os.chmod(target, 0o444)
            declared[output["name"]] = f"validation/outputs/out_{index:03d}.parquet"
        return declared

    # ------------------------------------------------------------ temporal leakage (prefix re-run)

    @staticmethod
    def _leakage_targets(spec: dict[str, Any]) -> dict[str, list[str]]:
        """ENTITY_DATE outputs with CUSTOM calculations that claim to be trailing but cannot be recalculated:
        {output name: [value columns to compare]}."""
        from .spec import _looks_ahead

        calcs = {c["id"]: c for c in spec["calculations"]}
        targets: dict[str, list[str]] = {}
        for output in spec["outputs"]:
            if output["grain"] != "ENTITY_DATE":
                continue
            columns = [calcs[c]["output_column"] for c in output["calculations"]
                       if calcs[c]["method"] == "CUSTOM" and not calcs[c].get("expression")
                       and not _looks_ahead(calcs[c], calcs)]
            if columns:
                targets[output["name"]] = columns
        return targets

    def _leakage_check(self, analysis_id: str, record: dict[str, Any], contract: dict[str, Any],
                       logical: dict[str, Any], granted: dict[str, GrantedFile], paths: dict[str, Path],
                       pre: dict[str, Any], cpus: list[int], uid: int, source: str, job_dir: Path,
                       declared: dict[str, str], usage: dict[str, Any]) -> dict[str, Any] | None:
        """Re-run the same code on inputs truncated at a cutoff date; values at or before the cutoff must not
        change. A trailing calculation is invariant to data after t; look-ahead (shift(-k), centred windows,
        full-sample normalisation) is not."""
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq

        s = self.settings
        spec = contract["spec"]
        targets = {name: cols for name, cols in self._leakage_targets(spec).items() if name in declared}
        if not s.leakage_check or not targets or contract["resolved_period"]["mode"] not in ("EXPLICIT_DATES",
                                                                                               "TRAILING"):
            return None

        def skipped(reason: str) -> dict[str, Any]:
            return {"result": "NOT_VERIFIABLE", "reason": reason, "evidence": [
                {"check": "temporal.leakage", "result": "WARN", "code": "LEAKAGE_CHECK_INCONCLUSIVE", "detail": reason}]}

        period = pre["period"]
        primary = logical[period["primary_input"]]
        date_column = primary["date_column"]
        by_local = {f["local_path"].split("/", 1)[1]: (name, info) for name, info in logical.items()
                    for f in info["files"]}
        dates: set = set()
        for dataset_id, file in granted.items():
            name, info = by_local[file.local_name]
            if name == period["primary_input"] and date_column:
                column = pq.read_table(paths[dataset_id], columns=[date_column]).column(0).to_pandas()
                dates.update(pd.to_datetime(column, errors="coerce").dropna().dt.normalize())
        in_period = sorted(d for d in dates if pd.Timestamp(period["start"]) <= d <= pd.Timestamp(period["end"]))
        if len(in_period) < 10:
            return skipped("Fewer than 10 trading dates in the period; the prefix re-run is not informative.")
        cutoff = in_period[int(len(in_period) * 0.6) - 1]
        remaining = int(s.max_cpu_seconds_per_request - self.records.request_usage(record["request_id"])["cpu_seconds"]
                        - usage.get("cpu_seconds", 0) - usage.get("validator_cpu_seconds", 0))
        budget = min(s.cpu_seconds, remaining)
        if budget < max(10, int(usage.get("cpu_seconds", 0)) + 5):
            return skipped("Not enough of the request's compute budget remains for the prefix re-run.")
        prefix_dir = Path(s.jobs_dir) / f"{analysis_id}-prefix"
        drop = self.executor.drop_privileges
        try:
            manifest = {"job_id": f"{analysis_id}-prefix", "analysis_id": analysis_id, "spec_id": record["spec_id"],
                        "logical_datasets": logical}
            prepare_workspace(s, prefix_dir, uid if drop else None, s.validator_uid if drop else None,
                              manifest=manifest, analysis_spec={"spec_id": record["spec_id"],
                                                                "spec_sha256": record["spec_sha256"], **contract},
                              code=source)
            for dataset_id, file in granted.items():
                _, info = by_local[file.local_name]
                table = pq.read_table(paths[dataset_id])
                column = info["date_column"]
                if column:
                    keep = (pd.to_datetime(table.column(column).to_pandas(), errors="coerce").dt.normalize()
                            <= cutoff).fillna(False).to_numpy()
                    table = table.filter(pa.array(keep))
                target = prefix_dir / "input" / file.local_name
                pq.write_table(table, target, compression="zstd")
                os.chmod(target, 0o444)
            self._write_runtime(prefix_dir, logical, pre, cpus, record["expected_outputs"], budget)
            outcome = self._execute(analysis_id, prefix_dir, uid, budget)
            usage["leakage_check_cpu_seconds"] = round(outcome.cpu_seconds, 3)
            if outcome.kind != "OK":
                return skipped(f"The code did not complete on the truncated input ({outcome.kind}).")
            names = {name: job_dir / "validation" / "outputs" / f"prefix_{i:03d}.parquet"
                     for i, name in enumerate(sorted(targets), start=1)}
            copied = self.outputs.copy_tables(prefix_dir / "output", uid if drop else None, names)
            if set(copied) != set(targets):
                return skipped("The re-run on the truncated input did not emit every checked output.")
            result, _ = self._validate(job_dir, "leakcheck", cpus, {
                "outputs": declared, "prefix_outputs": {k: str(v.relative_to(job_dir)) for k, v in copied.items()},
                "targets": targets, "cutoff": str(cutoff.date())})
            if result is None or result.get("validator_error"):
                return skipped("The validator could not compare the prefix re-run.")
            return {"result": result["result"], "cutoff": str(cutoff.date()), "outputs": result["outputs"],
                    "evidence": result["evidence"]}
        finally:
            shutil.rmtree(prefix_dir, ignore_errors=True)

    def _execute(self, analysis_id: str, job_dir: Path, uid: int, cpu_budget: int) -> Outcome:
        def started(pid: int) -> None:
            with self._lock:
                self.running[analysis_id] = pid  # lets cancel() and stop() kill the process group
                kill = analysis_id in self.cancelled or self._stop.is_set()
            if kill:  # cancelled between RUNNING and process start
                os.killpg(pid, 9)

        try:
            return self.executor.run(job_dir, uid, cpu_seconds=cpu_budget, on_start=started)
        finally:
            with self._lock:
                self.running.pop(analysis_id, None)

    def _outcome_error(self, outcome: Outcome) -> tuple[str, str, list[dict[str, Any]]]:
        if outcome.kind == "ERROR":
            error = outcome.error if isinstance(outcome.error, dict) else {}
            code = error.get("code") if isinstance(error.get("code"), str) else "PYTHON_EXCEPTION"
            code = code if code in CHILD_ERRORS else "PYTHON_EXCEPTION"
            message = str(error.get("message") or "The analysis raised an error.")[:800]
            frames = error.get("analysis_frames") if isinstance(error.get("analysis_frames"), list) else []
            return code, message, [f for f in frames[:6] if isinstance(f, dict)]
        code, message = OUTCOME_ERRORS.get(outcome.kind, ("PYTHON_EXCEPTION", "The analysis process failed."))
        if outcome.kind == "CRASH":
            message = f"{message} (exit status {outcome.returncode})."
        if outcome.kind == "DISK" and outcome.notes.get("disk_quota_exceeded"):
            message = f"{message} ({outcome.notes['disk_quota_exceeded']} quota)"
        return code, message, []

    def _finish(self, analysis_id: str, status: str, *, error: tuple[str, str] | None = None,
                frames: list | None = None, outcome: Outcome | None = None, usage: dict[str, Any] | None = None,
                diagnostics: dict[str, str] | None = None, warnings: list | None = None, outputs: list | None = None,
                validation: tuple[str, list[str]] | None = None, level: str = "EXECUTION_ONLY",
                evidence: list | None = None, expected_scope: dict | None = None, actual_scope: dict | None = None,
                features: list | None = None, self_reported: dict | None = None) -> None:
        s = self.settings
        record = self.records.get(analysis_id)
        validation_status, reasons = validation or ("UNVERIFIED", [error[0]] if error else [])
        fields: dict[str, Any] = {
            "status": status, "completed_at": utc_now(), "validation_status": validation_status,
            "validation_level": level if status == "COMPLETED" else "EXECUTION_ONLY", "reason_codes": reasons,
            "validation_evidence": (evidence or [])[:200], "expected_scope": expected_scope or {},
            "actual_scope": actual_scope or {}, "warnings": warnings or [], "resource_usage": usage or {},
            "cpu_seconds": round((usage or {}).get("cpu_seconds", 0) + (usage or {}).get("validator_cpu_seconds", 0)
                                 + (usage or {}).get("leakage_check_cpu_seconds", 0), 3),
        }
        if outcome is not None:
            fields["runtime_ms"] = outcome.runtime_ms
        if diagnostics is not None:
            fields["diagnostics"] = diagnostics
        if error:
            fields.update(error_code=error[0], error_message=error[1], error_frames=frames or [])
        if outputs is not None:
            fields.update(outputs=outputs, outputs_expire_at=(datetime.now(timezone.utc) + timedelta(
                hours=s.result_retention_hours)).replace(microsecond=0).isoformat())
        if features is not None:
            fields["derived_features"] = features
            self.records.add_derived_features(record["request_id"], analysis_id, record["spec_id"], utc_now(),
                                              features)
        if self_reported is not None:
            fields["self_reported"] = self_reported
        inputs = record.get("inputs") or {}
        expiries = sorted(m.get("expires_at") for m in inputs.values() if m.get("expires_at"))
        fields["reproducible_until"] = expiries[0] if expiries else None
        fields["execution_report"] = {
            "analysis_id": analysis_id, "spec_id": record["spec_id"], "spec_sha256": record["spec_sha256"],
            "execution_status": status, "validation_status": validation_status, "validation_level":
                fields["validation_level"], "reason_codes": reasons, "code_sha256": record["code_sha256"],
            "inputs": {ds: {"checksum_sha256": m.get("checksum_sha256"), "row_count": m.get("row_count"),
                            "source_tables": m.get("source_tables"), "query_id": m.get("query_id"),
                            "expires_at": m.get("expires_at")} for ds, m in inputs.items()},
            "logical_inputs": record.get("logical_inputs"), "resource_usage": usage or {},
            "runtime_version": RUNTIME_VERSION, "library_versions": self.isolation.versions,
            "finished_at": fields["completed_at"],
        }
        self.records.update(analysis_id, **fields)
        job_report = Path(self.settings.jobs_dir) / analysis_id / "execution_report.json"
        if job_report.parent.exists():
            try:
                _write_readonly(job_report, fields["execution_report"])
            except OSError:
                pass

    def _release_workspace(self, analysis_id: str, job_dir: Path, failed: bool) -> None:
        """Completed jobs lose their workspace at once (results and audit are already persisted). A failed
        job keeps a small diagnostic workspace for a bounded time; its inputs are always deleted."""
        s = self.settings
        try:
            if job_dir.exists():
                if failed and s.failed_workspace_ttl_hours > 0:
                    shutil.rmtree(job_dir / "input", ignore_errors=True)
                    shutil.rmtree(job_dir / "validation" / "outputs", ignore_errors=True)
                    if disk_usage(job_dir) <= s.failed_workspace_max_bytes:
                        until = (datetime.now(timezone.utc) + timedelta(hours=s.failed_workspace_ttl_hours)).replace(
                            microsecond=0).isoformat()
                        (job_dir / RETAIN_MARKER).write_text(until, encoding="utf-8")
                        os.chmod(job_dir / RETAIN_MARKER, 0o400)
                        return
                shutil.rmtree(job_dir, ignore_errors=True)
        finally:
            with self._lock:
                self.active.discard(analysis_id)

    def _discard_outputs(self, analysis_id: str) -> None:
        directory = self.outputs.root / analysis_id
        shutil.rmtree(directory, ignore_errors=True)
        for entry in self.records.files_for(analysis_id):
            self.records.delete_file(entry["file_id"])

    def _finish_event(self, analysis_id: str) -> None:
        with self._lock:
            event = self.events.pop(analysis_id, None)
        if event is not None:
            event.set()

    def _cached(self, file_name: str, dataset_id: str, checksum: str, byte_count: int, expires_at: str | None) -> None:
        self.records.cache_add(file_name, dataset_id, checksum, byte_count, expires_at, utc_now())

    # ------------------------------------------------------------ scope summaries

    @staticmethod
    def _expected_scope(contract: dict[str, Any], validation: dict[str, Any],
                        pre: dict[str, Any] | None = None) -> dict[str, Any]:
        spec = contract["spec"]
        period = validation.get("period") or {}
        warmup = (pre or validation).get("warmup") or {}
        return {"reference_date": contract["reference"]["date"], "timezone": contract["reference"]["timezone"],
                "period_mode": spec["analysis_period"]["mode"], "analysis_start": period.get("start"),
                "analysis_end": period.get("end"), "trading_dates": period.get("trading_dates"),
                "universe": spec["universe"]["type"], "tickers": spec["universe"]["tickers"],
                "expected_entities": validation.get("expected_entities"),
                "warmup_observations": {name: {"minimum": info["minimum"], "recommended": info["recommended"]}
                                        for name, info in warmup.items()},
                "frequency": spec["frequency"]["value"]}

    @staticmethod
    def _actual_scope(pre: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
        inputs = [{k: v for k, v in item.items() if k != "result"} for item in pre["evidence"]
                  if item["check"].startswith("input.")]
        return {"inputs": inputs, "outputs": post.get("outputs", [])}

    @staticmethod
    def _feature_results(contract: dict[str, Any], evidence: list[dict[str, Any]], level: str) -> list[dict[str, Any]]:
        outcome: dict[str, str] = {}
        for item in evidence:
            parts = item.get("check", "").split(".")
            if parts[0] == "calculation" and len(parts) >= 2:
                previous = outcome.get(parts[1])
                if item["result"] == "FAIL" or previous is None or previous == "SKIPPED":
                    outcome[parts[1]] = item["result"]
        features = []
        for definition in contract["derived_features"]:
            result = outcome.get(definition["calculation_id"])
            check = {"PASS": "RECALCULATED_MATCH", "FAIL": "RECALCULATED_MISMATCH"}.get(result or "", "NOT_CHECKED")
            status = definition.get("formula_status")
            if definition.get("method") == "CUSTOM" and check == "RECALCULATED_MATCH":
                status = "VALIDATED_CUSTOM_FORMULA_RESULT"  # an AI-generated formula whose values were recalculated
            features.append({**definition, "independent_check_result": check, "validation_level": level,
                             "statistical_validation": "NOT_PERFORMED", "formula_status": status})
        return features

    # ------------------------------------------------------------ janitor

    def cleanup_workspaces(self, now: datetime | None = None) -> int:
        """Remove every workspace that no running job owns, except failed-job diagnostics within their TTL."""
        root = Path(self.settings.jobs_dir)
        if not root.exists():
            return 0
        now = now or datetime.now(timezone.utc)
        with self._lock:
            active = set(self.active)
        removed = 0
        for entry in root.iterdir():
            if entry.name in active:
                continue
            marker = entry / RETAIN_MARKER
            if marker.exists():
                try:
                    until = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
                    if until > now:
                        continue
                except (OSError, ValueError):
                    pass
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        return removed

    def cleanup(self, now: datetime | None = None) -> dict[str, int]:
        now = now or datetime.now(timezone.utc)
        stamp = now.replace(microsecond=0).isoformat()
        removed = self.outputs.purge_expired(stamp)
        expired = self.records.expire_outputs(stamp)
        purged = self.records.purge_records(
            (now - timedelta(days=self.settings.record_retention_days)).replace(microsecond=0).isoformat())
        workspaces = self.cleanup_workspaces(now)
        cache = self.datasets.evict_expired(self.records, now)
        summary = {"files_removed": removed, "analyses_expired": len(expired), "records_purged": purged,
                   "workspaces_removed": workspaces, "cache_files_removed": cache}
        self._log("sandbox_cleanup", **summary)
        return summary

    def _janitor(self) -> None:
        while not self._stop.wait(self.settings.cleanup_interval_seconds):
            try:
                self.cleanup()
            except Exception:  # noqa: BLE001
                logger.exception("sandbox_cleanup_error")

    # ------------------------------------------------------------ rendering and logs

    def _lineage(self, code_sha256: str, spec: dict[str, Any]) -> dict[str, Any]:
        s = self.settings
        return {"runtime_version": RUNTIME_VERSION, "code_sha256": code_sha256, "seed": s.random_seed,
                "spec_id": spec["spec_id"], "spec_sha256": spec["spec_sha256"],
                "python_version": self.isolation.versions.get("python"),
                "library_versions": {k: v for k, v in self.isolation.versions.items() if k != "python"},
                "deployment_id": os.environ.get("RAILWAY_DEPLOYMENT_ID"),
                "limits": {"max_runtime_seconds": s.max_runtime_seconds, "max_memory_mb": s.max_memory_mb,
                           "cpus": s.cpus_per_job, "max_table_output_rows": s.max_table_output_rows,
                           "max_table_preview_rows": s.max_table_preview_rows}}

    def render(self, record: dict[str, Any]) -> dict[str, Any]:
        status = record["status"]
        validation_status = record.get("validation_status") or "UNVERIFIED"
        reasons = record.get("reason_codes") or []
        error = None
        if record.get("error_code") and status in {"FAILED", "CANCELLED"}:
            error = {"code": record["error_code"], "message": record.get("error_message") or "",
                     "analysis_frames": record.get("error_frames") or []}
        inputs = record.get("inputs") or {}
        lineage = {**(record.get("lineage") or {}),
                   "datasets": {ds: {k: v for k, v in meta.items() if k in {"checksum_sha256", "row_count",
                                                                              "completeness_status", "source_tables",
                                                                              "numeric_float64_columns"}}
                                for ds, meta in inputs.items()},
                   "reproducible_until": record.get("reproducible_until")}
        diagnostics = record.get("diagnostics")
        if diagnostics is not None and status == "COMPLETED":
            diagnostics = {k: v for k, v in diagnostics.items() if v} or None
        evidence = record.get("validation_evidence") or []
        important = [e for e in evidence if e.get("result") not in ("PASS", "SKIPPED")]
        summary = [e for e in evidence if e.get("result") in ("PASS", "SKIPPED")
                   and e.get("check", "").startswith(("calculation.", "output.", "universe.", "period.", "scope."))]
        logical = {b["name"]: b["dataset_ids"] for b in (record.get("logical_inputs") or [])}
        warnings = list(record.get("warnings") or [])
        result = AnalysisResult(
            analysis_id=record["analysis_id"], spec_id=record.get("spec_id"), spec_sha256=record.get("spec_sha256"),
            execution_status=status, validation_status=validation_status,
            validation_level=record.get("validation_level") or "EXECUTION_ONLY", reason_codes=reasons,
            next_action=next_action(status, validation_status, record.get("error_code"), reasons),
            request_id=record["request_id"], question=record["purpose"], inputs=logical,
            dataset_ids=record["dataset_ids"], expected_outputs=record["expected_outputs"],
            created_at=record["created_at"], started_at=record.get("started_at"),
            completed_at=record.get("completed_at"), runtime_ms=record.get("runtime_ms"),
            retry_after_seconds=self.settings.retry_after_seconds if status in {"QUEUED", "RUNNING"} else None,
            expected_scope=record.get("expected_scope") or {}, actual_scope=record.get("actual_scope") or {},
            outputs=(record.get("outputs") or []) if status == "COMPLETED" else [],
            warnings=warnings, validation_evidence=(important + summary)[:EVIDENCE_ITEMS], error=error,
            diagnostics=diagnostics, derived_features=record.get("derived_features") or [],
            derived_feature_definitions=record.get("feature_artifact") if status == "COMPLETED" else None,
            database_features=[{"input": b, "columns": cols, "origin": "DATABASE_FEATURE"}
                               for b, cols in ((record.get("database_features") or {}).items())],
            self_reported=record.get("self_reported") or {}, lineage=lineage,
            resource_usage=record.get("resource_usage") or {}, outputs_expire_at=record.get("outputs_expire_at"))
        data = result.model_dump()
        data["evidence_assessment"] = record.get("evidence_assessment") or fallback_assessment(record)
        if record.get("leakage_check"):
            data["leakage_check"] = record["leakage_check"]
        if status == "EXPIRED":
            data["warnings"] = [*data["warnings"], {"code": "OUTPUTS_EXPIRED", "message": (
                "The stored outputs of this analysis have expired; its metadata remains. Run it again if needed.")}]
        until = record.get("reproducible_until")
        if until and until <= utc_now():
            data["warnings"] = [*data["warnings"], {"code": "INPUT_SNAPSHOT_EXPIRED", "message": (
                "The governed input snapshot has expired. Its checksum is recorded, but this analysis can no longer be "
                "re-run on the same data.")}]
        return data

    def _log_result(self, analysis_id: str) -> None:
        record = self.records.get(analysis_id)
        if record is None:
            return
        outputs = record.get("outputs") or []
        usage = record.get("resource_usage") or {}
        self._log("sandbox_analysis", request_id=record["request_id"], analysis_id=analysis_id,
                  spec_id=record.get("spec_id"), dataset_ids=record["dataset_ids"],
                  dataset_checksums={k: v.get("checksum_sha256") for k, v in (record.get("inputs") or {}).items()},
                  code_sha256=record["code_sha256"], execution_status=record["status"],
                  validation_status=record.get("validation_status"), validation_level=record.get("validation_level"),
                  reason_codes=record.get("reason_codes"), runtime_ms=record.get("runtime_ms"),
                  input_rows=record.get("input_rows"), input_bytes=record.get("input_bytes"),
                  output_types=sorted({o["type"] for o in outputs}), output_rows=usage.get("output_rows"),
                  output_bytes=usage.get("output_bytes"), error_code=record.get("error_code"),
                  cpu_seconds=usage.get("cpu_seconds"), validator_cpu_seconds=usage.get("validator_cpu_seconds"),
                  max_rss_mb=usage.get("max_rss_mb"), peak_intermediate_bytes=usage.get("peak_intermediate_bytes"))

    @staticmethod
    def _log(event: str, **fields: Any) -> None:
        logger.info(json.dumps({"event": event, **fields}, separators=(",", ":"), default=str))


def status_allows_leak_check(post: dict[str, Any]) -> bool:
    return post.get("validation_status") in ("PASS", "UNVERIFIED", "INCOMPLETE")


def fallback_assessment(record: dict[str, Any]) -> dict[str, Any] | None:
    """Evidence decision for an analysis the postflight validator did not assess (it failed or never ran)."""
    status = record.get("status")
    if status in ("QUEUED", "RUNNING"):
        return None
    claim = (record.get("research_context") or {}).get("evidence_standard") or "CALCULATION"
    failed = record.get("validation_status") == "FAILED"
    return {"claim_type": claim, "decision": "INVALID" if failed else "INSUFFICIENT_EVIDENCE",
            "evidence_level": "NONE", "checks": {},
            "reporting_constraints": ["No result of this analysis may be reported as a finding."],
            "source": "HARNESS"}


def _validator_detail(result: dict[str, Any] | None, outcome: Outcome) -> str:
    if result and result.get("validator_error"):
        return f" ({result['validator_error'][:200]})"
    if outcome.kind != "OK":
        return f" (validator process ended with {outcome.kind}: {outcome.stderr_tail[-200:]})"
    return ""


def source_contract(meta: dict[str, Any]) -> dict[str, Any]:
    """Source semantics of one catalog table (the same shape the Governor puts in validator manifests)."""
    frequencies = meta.get("supported_frequencies")
    return {"table": meta["table_name"], "grain": list(meta.get("primary_key_columns") or []),
            "grain_description": meta.get("grain"), "entity_column": meta.get("entity_column"),
            "time_column": meta.get("time_column"), "supported_frequencies": frequencies,
            "frequency": (frequencies[0] if frequencies and len(frequencies) == 1 else None),
            "time_semantics": meta.get("time_semantics"), "data_domain": meta.get("data_domain"),
            "entity_type": meta.get("entity_type"), "asset_type": meta.get("asset_type"),
            "subject_metadata_status": meta.get("subject_metadata_status"),
            "catalog_table_sha256": meta.get("catalog_table_sha256")}


def _review_v2_scope(spec: dict[str, Any], found: Any, result: Any) -> None:
    """V2 scope review: attribute predicates are checked against the user's own words (their provenance); the
    V1 universe check applies to entity lists and all-eligible scopes only."""
    for output in spec["outputs"]:
        ranking = output.get("ranking")
        if not ranking:
            continue
        stated = ranking["provenance"] in ("USER_EXPLICIT", "USER_CLARIFIED") and \
            re.search(rf"(?<!\d){ranking['limit']}(?!\d)", found.user_text)
        result.add(f"output.{output['name']}.ranking", "MATCH" if stated else "UNVERIFIED",
                   ranking["limit"] if stated else None, f"{ranking['direction']} top {ranking['limit']}",
                   "The request states how many to rank." if stated else
                   "The number of ranked rows is not stated in the request (chosen by the AI).")
    if spec["scope"]["selection_type"] != "ATTRIBUTE_FILTER":
        return
    for bucket in (result.checks, result.mismatches, result.unverified):
        bucket[:] = [item for item in bucket if item["requirement"] != "universe"]
    for requirement, outcome, expected, proposed, detail, code in review_scope(spec, found.user_text):
        result.add(requirement, outcome, expected, proposed, detail, code)
