"""Analysis lifecycle: submit -> QUEUED -> RUNNING -> COMPLETED | FAILED (| CANCELLED), then EXPIRED.

Jobs wait in a bounded in-process queue and run one per worker slot. Each slot has its own
non-root user id and CPU set, so concurrent analyses cannot see or signal each other.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import secrets
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .datasets import DatasetFailure, DatasetProvider
from .executor import Executor, Outcome
from .isolation import IsolationReport, run_selftest
from .models import TERMINAL, AnalysisRequest, AnalysisResult, next_action
from .outputs import OutputRejected, OutputStore
from .policy import check_source
from .records import Records, utc_now

logger = logging.getLogger("market_python_sandbox")
RUNTIME_VERSION = "market-python-sandbox/v1"
# Failures worth resubmitting unchanged; any other identical resubmission returns the recorded result.
TRANSIENT_ERRORS = {"SANDBOX_RESTARTED", "DATASET_UNAVAILABLE", "DATASET_STORAGE_UNAVAILABLE", "INTERNAL_ERROR",
                    "SANDBOX_ISOLATION_UNAVAILABLE"}
OUTCOME_ERRORS = {
    "TIMEOUT": ("RUNTIME_LIMIT_EXCEEDED", "The analysis exceeded the sandbox runtime limit and was stopped."),
    "CPU": ("RUNTIME_LIMIT_EXCEEDED", "The analysis exceeded the sandbox CPU-time limit and was stopped."),
    "MEMORY": ("MEMORY_LIMIT_EXCEEDED", "The analysis exceeded the sandbox memory limit and was stopped."),
    "DISK": ("OUTPUT_LIMIT_EXCEEDED", "The analysis wrote more data than the sandbox disk quota and was stopped."),
    "FORBIDDEN": ("FORBIDDEN_OPERATION", "The analysis attempted an operation the sandbox forbids and was stopped."),
    "CRASH": ("PYTHON_EXCEPTION", "The analysis process crashed."),
}


class ServiceUnavailable(Exception):
    def __init__(self, code: str, message: str, http_status: int, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.http_status, self.retry_after = code, message, http_status, retry_after


def prepare_job_dir(settings: Settings, job_dir: Path, uid: int | None, job: dict[str, Any]) -> None:
    """Create a job directory: root-owned job file and inputs, slot-user-owned work and output."""
    jobs_root = Path(settings.jobs_dir)
    jobs_root.mkdir(parents=True, exist_ok=True)
    os.chmod(jobs_root, 0o711)  # traversable, not listable
    job_dir.mkdir(mode=0o755)
    (job_dir / "input").mkdir(mode=0o755)
    for private in ("work", "output"):
        path = job_dir / private
        path.mkdir(mode=0o700)
        if uid is not None:
            os.chown(path, uid, uid)
    owned = [job_dir / "work" / "tmp"]
    owned[0].mkdir(mode=0o700)
    mpl_cache = Path(settings.mpl_cache_dir)
    if mpl_cache.is_dir():  # prebuilt matplotlib font cache, so no analysis rebuilds it
        target = job_dir / "work" / ".matplotlib"
        shutil.copytree(mpl_cache, target)
        owned += [target, *target.rglob("*")]
    if uid is not None:
        for path in owned:
            os.chown(path, uid, uid, follow_symlinks=False)
    job_file = job_dir / "job.json"
    job_file.write_text(json.dumps(job), encoding="utf-8")
    os.chmod(job_file, 0o444)


def idempotency_key(request: AnalysisRequest, code_sha256: str) -> str:
    material = json.dumps([request.request_id, request.purpose, sorted(request.dataset_ids), code_sha256,
                           sorted(request.expected_outputs)], separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


class AnalysisService:
    def __init__(self, settings: Settings, *, records: Records | None = None, datasets: DatasetProvider | None = None,
                 executor: Executor | None = None) -> None:
        self.settings = settings
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        os.chmod(settings.data_dir, 0o700)
        self.records = records or Records(Path(settings.data_dir) / "analyses.sqlite3")
        self.datasets = datasets or DatasetProvider(settings)
        self.executor = executor or Executor(settings)
        self.outputs = OutputStore(settings, self.records)
        self.queue: queue.Queue[str] = queue.Queue(maxsize=settings.max_queued)
        self.events: dict[str, threading.Event] = {}
        self.running: dict[str, int] = {}  # analysis_id -> child pid (for cancel)
        self.sources: dict[str, str] = {}  # queued source code, held in memory until the job starts
        self.cancelled: set[str] = set()
        self._lock = threading.Lock()
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
        shutil.rmtree(self.settings.jobs_dir, ignore_errors=True)
        interrupted = self.records.interrupt_unfinished(utc_now())
        uid, cpus = self.slots[0]
        self.isolation = run_selftest(self.settings, self.executor, uid, cpus)
        self._log("sandbox_started", interrupted_analyses=interrupted, isolation_enforced=self.isolation.ok,
                  isolation_failure=self.isolation.failure, versions=self.isolation.versions)
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

    # ------------------------------------------------------------ API operations

    def submit(self, request: AnalysisRequest) -> dict[str, Any]:
        s = self.settings
        if not self.isolation.ok:
            raise ServiceUnavailable("SANDBOX_ISOLATION_UNAVAILABLE",
                                     "The Python sandbox cannot verify its isolation and is refusing analyses.", 503)
        if len(request.dataset_ids) > s.max_datasets:
            raise ServiceUnavailable("INVALID_REQUEST", f"At most {s.max_datasets} datasets per analysis.", 422)
        if len(request.python_code) > s.max_code_chars:
            raise ServiceUnavailable("INVALID_REQUEST", f"python_code exceeds {s.max_code_chars} characters.", 422)
        code_sha256 = hashlib.sha256(request.python_code.encode()).hexdigest()
        key = idempotency_key(request, code_sha256)
        existing = self.records.find_by_key(key)
        if existing and not (existing["status"] == "FAILED" and existing["error_code"] in TRANSIENT_ERRORS):
            return self.wait(existing["analysis_id"], s.submit_wait_seconds)
        analysis_id = f"ana_{secrets.token_hex(12)}"
        now = utc_now()
        record = {
            "analysis_id": analysis_id, "idempotency_key": key, "request_id": request.request_id, "status": "QUEUED",
            "purpose": request.purpose, "dataset_ids": request.dataset_ids,
            "expected_outputs": request.expected_outputs, "code_sha256": code_sha256,
            "code": request.python_code if s.retain_code else None, "created_at": now,
            "lineage": self._lineage(code_sha256), "research_context": None,
        }
        violation = check_source(request.python_code)
        if violation is not None:
            self.records.insert({**record, "status": "FAILED", "completed_at": now, "error_code": violation.code,
                                 "error_message": violation.message,
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
            self.records.update(analysis_id, status="FAILED", completed_at=utc_now(), error_code="QUEUE_FULL",
                                error_message="The sandbox queue is full.")
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
        if self.records.transition(analysis_id, {"QUEUED"}, status="CANCELLED", completed_at=utc_now(),
                                   error_code="CANCELLED", error_message="Cancelled before it started."):
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
                self.records.update(analysis_id, status="FAILED", completed_at=utc_now(), error_code="INTERNAL_ERROR",
                                    error_message=f"Internal sandbox error ({type(exc).__name__}).")
                logger.exception("sandbox_internal_error")
            finally:
                self._finish_event(analysis_id)
                self._log_result(analysis_id)

    def _run(self, analysis_id: str, uid: int, cpus: list[int]) -> None:
        s = self.settings
        with self._lock:
            source = self.sources.pop(analysis_id, None)
        if source is None or not self.records.transition(analysis_id, {"QUEUED"}, status="RUNNING",
                                                         started_at=utc_now()):
            return  # cancelled while queued
        record = self.records.get(analysis_id)
        job_dir = Path(s.jobs_dir) / analysis_id
        drop = self.executor.drop_privileges
        try:
            download_started = time.monotonic()
            inputs, warnings, paths = self._prepare_inputs(record)
            download_ms = round((time.monotonic() - download_started) * 1000)
            prepare_job_dir(s, job_dir, uid if drop else None, {
                "code": source,
                "datasets": {ds: str(job_dir / "input" / f"{ds}.parquet") for ds in paths},
                "seed": s.random_seed, "limits": s.child_limits(), "expected_outputs": record["expected_outputs"],
                "cpus": cpus, "threads": s.threads_per_job, "require_seccomp": True})
            for dataset_id, source in paths.items():
                DatasetProvider.link(source, job_dir / "input" / f"{dataset_id}.parquet")
            self.records.update(analysis_id, inputs=inputs, input_rows=sum(i["row_count"] for i in inputs.values()),
                                input_bytes=sum(i["byte_count"] for i in inputs.values()))
            outcome = self._execute(analysis_id, job_dir, uid)
            usage = {"cpu_seconds": outcome.cpu_seconds, "max_rss_mb": outcome.max_rss_mb, "download_ms": download_ms,
                     "input_rows": sum(i["row_count"] for i in inputs.values()),
                     "input_bytes": sum(i["byte_count"] for i in inputs.values())}
            diagnostics = {"stdout_tail": outcome.stdout_tail, "stderr_tail": outcome.stderr_tail}
            with self._lock:
                was_cancelled = analysis_id in self.cancelled
                self.cancelled.discard(analysis_id)
            if self._stop.is_set() and not was_cancelled:
                self._fail(analysis_id, "SANDBOX_RESTARTED", "The sandbox shut down while this analysis was running. "
                           "Submit it again.", outcome, usage, diagnostics)
                return
            if was_cancelled:
                self._fail(analysis_id, "CANCELLED", "Cancelled while running.", outcome, usage, diagnostics,
                           status="CANCELLED")
                return
            if outcome.kind != "OK":
                code, message, frames = self._outcome_error(outcome)
                self._fail(analysis_id, code, message, outcome, usage, diagnostics, frames=frames,
                           warnings=warnings)
                return
            try:
                collected = self.outputs.collect(analysis_id, job_dir / "output", uid if drop else None,
                                                 record["expected_outputs"])
            except OutputRejected as rejected:
                self._discard_outputs(analysis_id)
                self._fail(analysis_id, rejected.code, rejected.message, outcome, usage, diagnostics,
                           warnings=warnings)
                return
            usage.update(output_rows=collected.output_rows, output_bytes=collected.stored_bytes)
            expires = (datetime.now(timezone.utc) + timedelta(hours=s.result_retention_hours)).replace(
                microsecond=0).isoformat()
            self.records.update(analysis_id, status="COMPLETED", completed_at=utc_now(), runtime_ms=outcome.runtime_ms,
                                outputs=collected.outputs, warnings=warnings + collected.warnings,
                                resource_usage=usage, diagnostics=diagnostics, outputs_expire_at=expires)
        except DatasetFailure as failure:
            self.records.update(analysis_id, status="FAILED", completed_at=utc_now(), error_code=failure.code,
                                error_message=failure.message)
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    def _execute(self, analysis_id: str, job_dir: Path, uid: int) -> Outcome:
        def started(pid: int) -> None:
            with self._lock:
                self.running[analysis_id] = pid  # lets cancel() and stop() kill the process group
                kill = analysis_id in self.cancelled or self._stop.is_set()
            if kill:  # cancelled between RUNNING and process start
                os.killpg(pid, 9)

        try:
            return self.executor.run(job_dir, uid, on_start=started)
        finally:
            with self._lock:
                self.running.pop(analysis_id, None)

    def _prepare_inputs(self, record: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, Path]]:
        s = self.settings
        grants = [self.datasets.grant(ds, request_id=record["request_id"], analysis_id=record["analysis_id"])
                  for ds in record["dataset_ids"]]
        rows, size = sum(g.row_count for g in grants), sum(g.byte_count for g in grants)
        if rows > s.max_input_rows or size > s.max_input_bytes:
            raise DatasetFailure("INPUT_LIMIT_EXCEEDED",
                                 f"The input datasets hold {rows} rows / {size} bytes, above the sandbox input limit. "
                                 f"Request narrower data.")
        inputs: dict[str, Any] = {}
        warnings: list[dict[str, str]] = []
        paths: dict[str, Path] = {}
        for grant in grants:
            manifest = grant.manifest
            inputs[grant.dataset_id] = {
                "checksum_sha256": grant.checksum, "row_count": grant.row_count, "byte_count": grant.byte_count,
                "source_tables": manifest.get("source_tables"), "query_id": manifest.get("query_id"),
                "completeness_status": manifest.get("completeness_status"),
                "missing_entities_count": manifest.get("missing_entities_count"),
                "actual_date_range": manifest.get("actual_date_range"),
                "numeric_float64_columns": manifest.get("numeric_float64_columns") or [],
                "expires_at": manifest.get("expires_at"),
            }
            if manifest.get("numeric_float64_columns"):
                warnings.append({"code": "NUMERIC_AS_FLOAT64", "message": (
                    f"{grant.dataset_id}: numeric columns {manifest['numeric_float64_columns'][:10]} are float64 "
                    f"(not decimal-exact). Suitable for indicators, returns, and statistics; not for exact "
                    f"accounting reconciliation.")})
            if manifest.get("completeness_status") not in (None, "COMPLETE"):
                warnings.append({"code": "INCOMPLETE_INPUT", "message": (
                    f"{grant.dataset_id}: completeness_status {manifest.get('completeness_status')}, "
                    f"{manifest.get('missing_entities_count') or 0} requested entities missing.")})
            paths[grant.dataset_id] = self.datasets.fetch(grant)
        return inputs, warnings, paths

    def _outcome_error(self, outcome: Outcome) -> tuple[str, str, list[dict[str, Any]]]:
        if outcome.kind == "ERROR":
            error = outcome.error if isinstance(outcome.error, dict) else {}
            code = error.get("code") if isinstance(error.get("code"), str) else "PYTHON_EXCEPTION"
            allowed = {"PYTHON_EXCEPTION", "SYNTAX_ERROR", "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED",
                       "OUTPUT_INVALID", "FORBIDDEN_OPERATION", "INSUFFICIENT_HISTORY", "DUPLICATE_OBSERVATIONS"}
            code = code if code in allowed else "PYTHON_EXCEPTION"
            message = str(error.get("message") or "The analysis raised an error.")[:800]
            frames = error.get("analysis_frames") if isinstance(error.get("analysis_frames"), list) else []
            return code, message, [f for f in frames[:6] if isinstance(f, dict)]
        code, message = OUTCOME_ERRORS.get(outcome.kind, ("PYTHON_EXCEPTION", "The analysis process failed."))
        if outcome.kind == "CRASH":
            message = f"{message} (exit status {outcome.returncode})."
        return code, message, []

    def _fail(self, analysis_id: str, code: str, message: str, outcome: Outcome, usage: dict[str, Any],
              diagnostics: dict[str, str], *, frames: list | None = None, warnings: list | None = None,
              status: str = "FAILED") -> None:
        self.records.update(analysis_id, status=status, completed_at=utc_now(), runtime_ms=outcome.runtime_ms,
                            error_code=code, error_message=message, error_frames=frames or [],
                            resource_usage=usage, diagnostics=diagnostics, warnings=warnings or [])

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

    # ------------------------------------------------------------ janitor

    def cleanup(self, now: datetime | None = None) -> dict[str, int]:
        now = now or datetime.now(timezone.utc)
        stamp = now.replace(microsecond=0).isoformat()
        removed = self.outputs.purge_expired(stamp)
        expired = self.records.expire_outputs(stamp)
        purged = self.records.purge_records(
            (now - timedelta(days=self.settings.record_retention_days)).replace(microsecond=0).isoformat())
        summary = {"files_removed": removed, "analyses_expired": len(expired), "records_purged": purged}
        self._log("sandbox_cleanup", **summary)
        return summary

    def _janitor(self) -> None:
        while not self._stop.wait(self.settings.cleanup_interval_seconds):
            try:
                self.cleanup()
            except Exception:  # noqa: BLE001
                logger.exception("sandbox_cleanup_error")

    # ------------------------------------------------------------ rendering and logs

    def _lineage(self, code_sha256: str) -> dict[str, Any]:
        s = self.settings
        return {"runtime_version": RUNTIME_VERSION, "code_sha256": code_sha256, "seed": s.random_seed,
                "python_version": self.isolation.versions.get("python"),
                "library_versions": {k: v for k, v in self.isolation.versions.items() if k != "python"},
                "deployment_id": os.environ.get("RAILWAY_DEPLOYMENT_ID"),
                "limits": {"max_runtime_seconds": s.max_runtime_seconds, "max_memory_mb": s.max_memory_mb,
                           "cpus": s.cpus_per_job, "max_table_output_rows": s.max_table_output_rows,
                           "max_table_preview_rows": s.max_table_preview_rows}}

    def render(self, record: dict[str, Any]) -> dict[str, Any]:
        status = record["status"]
        error = None
        if record.get("error_code") and status in {"FAILED", "CANCELLED"}:
            error = {"code": record["error_code"], "message": record.get("error_message") or "",
                     "analysis_frames": record.get("error_frames") or []}
        inputs = record.get("inputs") or {}
        lineage = {**(record.get("lineage") or {}),
                   "datasets": {ds: {k: v for k, v in meta.items() if k in {"checksum_sha256", "row_count",
                                                                              "completeness_status", "source_tables",
                                                                              "numeric_float64_columns"}}
                                for ds, meta in inputs.items()}}
        diagnostics = record.get("diagnostics")
        if diagnostics is not None and status == "COMPLETED":
            diagnostics = {k: v for k, v in diagnostics.items() if v} or None
        result = AnalysisResult(
            analysis_id=record["analysis_id"], status=status, next_action=next_action(status, record.get("error_code")),
            request_id=record["request_id"], purpose=record["purpose"], dataset_ids=record["dataset_ids"],
            expected_outputs=record["expected_outputs"], created_at=record["created_at"],
            started_at=record.get("started_at"), completed_at=record.get("completed_at"),
            runtime_ms=record.get("runtime_ms"),
            retry_after_seconds=self.settings.retry_after_seconds if status in {"QUEUED", "RUNNING"} else None,
            outputs=(record.get("outputs") or []) if status == "COMPLETED" else [],
            warnings=record.get("warnings") or [], error=error, diagnostics=diagnostics, lineage=lineage,
            resource_usage=record.get("resource_usage") or {},
            outputs_expire_at=record.get("outputs_expire_at"))
        data = result.model_dump()
        if status == "EXPIRED":
            data["warnings"] = [*data["warnings"], {"code": "OUTPUTS_EXPIRED", "message": (
                "The stored outputs of this analysis have expired; its metadata remains. Run it again if needed.")}]
        return data

    def _log_result(self, analysis_id: str) -> None:
        record = self.records.get(analysis_id)
        if record is None:
            return
        outputs = record.get("outputs") or []
        usage = record.get("resource_usage") or {}
        self._log("sandbox_analysis", request_id=record["request_id"], analysis_id=analysis_id,
                  dataset_ids=record["dataset_ids"],
                  dataset_checksums={k: v.get("checksum_sha256") for k, v in (record.get("inputs") or {}).items()},
                  code_sha256=record["code_sha256"], status=record["status"], runtime_ms=record.get("runtime_ms"),
                  input_rows=record.get("input_rows"), input_bytes=record.get("input_bytes"),
                  output_types=sorted({o["type"] for o in outputs}), output_rows=usage.get("output_rows"),
                  output_bytes=usage.get("output_bytes"), error_code=record.get("error_code"),
                  cpu_seconds=usage.get("cpu_seconds"), max_rss_mb=usage.get("max_rss_mb"))

    @staticmethod
    def _log(event: str, **fields: Any) -> None:
        logger.info(json.dumps({"event": event, **fields}, separators=(",", ":"), default=str))
