"""Persistent analysis sessions over governed bundles (DataNeed flow).

A session is one long-lived worker process (runtime/session_worker.py) started as a dedicated non-root session
user, bound to one request and one READY bundle. The harness

- builds the workspace: the bundle files copied read-only into input/ with their checksums verified, private
  intermediate/ and output/ directories owned by the session user, and a root-owned session.json;
- starts the worker with a constructed environment and a private response pipe; the worker confines itself
  (session CPU budget, memory, file size, process count, CPU set, seccomp) before it reads any command;
- watches it: resident memory and the disk quotas continuously, the wall clock per execution (SIGINT first, so the
  session survives a timeout; SIGKILL if the code does not yield);
- runs one command at a time per session and records every execution (code hash, status, error, what the helpers
  read, outputs, CPU) in dataneed.sqlite3;
- copies every emitted output into a root-only store with its checksum before the model can read it; outputs are
  released only when the analysis completes with coverage PASS (Phase 4);
- closes sessions that are idle, too old, over budget, or whose worker died. Sessions do not survive a restart of
  the service (they are closed as SANDBOX_RESTARTED); bundles and outputs do.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import select
import shutil
import signal
import stat
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .executor import _rss_mb, child_environment, disk_usage
from .records import utc_now

logger = logging.getLogger("market_python_sandbox")
SESSION_ID_PREFIX = "sess_"
OUTPUT_EXTENSIONS = {"PARQUET": "parquet", "CSV": "csv", "PNG": "png", "JSON": "json", "TEXT": "txt", "BIN": "bin"}
READ_LIMIT = 16 << 20
GRACE_SECONDS = 5.0
# The value types of every frame the helpers return (DuckDB .df(date_as_object=True)). Most failed executions in the
# 2026-09-26 stress test were pandas date idioms applied to these date objects (TypeError, KeyError, AttributeError).
DATA_TYPES = ("Frames from load, range, sql and join: the time column holds datetime.date "
              "objects (object dtype), numeric columns are float64, text columns are pandas strings. Compare dates "
              "with datetime.date(2026, 1, 2) (import datetime) or select a period with range(); before .dt, "
              ".resample(), .loc['2026-01-02'] or a comparison with a date string, convert first: "
              "frame[col] = pd.to_datetime(frame[col]).")
HELPERS = ["requests()", "manifest()", "quality(request)", "load(request, columns=None)",
           "range(request, range_id, columns=None, include_buffers=False)", "sql(query, params=None)",
           "relation(request)", "join(relationship_id, left=None, right=None, how=None)",
           "resample(frame, request, frequency=None)",
           "period_return(request, range_id, value_column='close', entity_column=None, date_column=None)",
           "insufficient_data(request, range_id=None, value=None, unit='TRADING_OBSERVATIONS', "
           "requirement_type='ADDITIONAL_HISTORY', reason='')", "intermediate_path(name)",
           "emit_table(name, frame, description='')", "emit_chart(figure=None, name='chart', title='', description='')",
           "emit_json(name, value, description='')", "emit_text(name, text, description='')",
           "emit_file(name, data, format='PARQUET'|'CSV'|'PNG'|..., description='')", "add_warning(code, message)"]


class SessionError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 409, next_action: str | None = None,
                 **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.next_action = next_action
        self.details = details


def _cpu_seconds(pid: int) -> float:
    try:
        with open(f"/proc/{pid}/stat") as handle:
            fields = handle.read().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return 0.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class Worker:
    session_id: str
    uid: int
    cpus: list[int]
    directory: Path
    process: subprocess.Popen
    reader: int
    memory_mb: int
    cpu_budget: int
    quotas: dict[Path, int]
    lock: threading.Lock = field(default_factory=threading.Lock)
    seq: int = 0
    death: str | None = None
    peak_rss_mb: float = 0.0
    last_cpu: float = 0.0
    buffer: bytes = b""

    @property
    def alive(self) -> bool:
        return self.death is None and self.process.poll() is None

    def kill(self, reason: str) -> None:
        if self.death is None:
            self.death = reason
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def classify_exit(self) -> str:
        if self.death:
            return self.death
        code = self.process.poll()
        if code is None:
            return "WORKER_UNRESPONSIVE"
        if code == -signal.SIGXCPU or (code == -signal.SIGKILL and self.last_cpu >= self.cpu_budget - 2):
            return "CPU_BUDGET_EXCEEDED"
        if code == -signal.SIGSYS:
            return "FORBIDDEN_OPERATION"
        return "WORKER_CRASHED"

    def _read_line(self, deadline: float) -> dict[str, Any] | None:
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([self.reader], [], [], min(remaining, 0.5))
            self.last_cpu = max(self.last_cpu, _cpu_seconds(self.process.pid))
            if not ready:
                if self.process.poll() is not None or self.death:
                    raise EOFError
                continue
            chunk = os.read(self.reader, 1 << 16)
            if not chunk:
                raise EOFError
            self.buffer += chunk
            if len(self.buffer) > READ_LIMIT:
                self.kill("PROTOCOL_ERROR")
                raise EOFError
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))

    def request(self, message: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Send one command and wait for its answer; SIGINT at the deadline, SIGKILL after the grace period."""
        self.seq += 1
        seq = self.seq
        try:
            self.process.stdin.write((json.dumps({**message, "seq": seq}) + "\n").encode("utf-8"))
            self.process.stdin.flush()
        except (BrokenPipeError, OSError):
            raise EOFError from None
        deadline = time.monotonic() + timeout
        interrupted = False
        while True:
            answer = self._read_line(deadline)
            if answer is None:
                if interrupted:
                    self.kill("EXECUTION_TIMEOUT_UNINTERRUPTIBLE")
                    raise EOFError
                interrupted = True
                try:
                    os.kill(self.process.pid, signal.SIGINT)
                except ProcessLookupError:
                    raise EOFError from None
                deadline = time.monotonic() + GRACE_SECONDS
                continue
            if answer.get("seq") == seq:
                return answer

    def watch(self, stop: threading.Event) -> None:
        next_disk = time.monotonic()
        while not stop.is_set() and self.process.poll() is None:
            rss = _rss_mb(self.process.pid)
            self.peak_rss_mb = max(self.peak_rss_mb, rss)
            if rss > self.memory_mb:
                self.kill("MEMORY_LIMIT_EXCEEDED")
                return
            if time.monotonic() >= next_disk:
                next_disk = time.monotonic() + 1.0
                for path, quota in self.quotas.items():
                    if disk_usage(path) > quota:
                        self.kill("DISK_LIMIT_EXCEEDED")
                        return
            stop.wait(0.2)


class SessionManager:
    def __init__(self, analysis: Any, store: Any, bundles: Any) -> None:
        self.analysis = analysis
        self.settings = analysis.settings
        self.store = store
        self.bundles = bundles
        self.executor = analysis.executor
        self.workers: dict[str, Worker] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.outputs_root = Path(self.settings.data_dir) / "session_outputs"
        self.outputs_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.outputs_root, 0o700)
        available = sorted(os.sched_getaffinity(0))
        s = self.settings
        self.slots = [(s.session_uid_base + i,
                       [available[(i * s.cpus_per_job + j) % len(available)] for j in range(s.cpus_per_job)])
                      for i in range(s.max_sessions)]

    # ------------------------------------------------------------------ lifecycle

    def start(self, run_janitor: bool = True) -> None:
        closed = self.store.close_orphans(utc_now())
        root = Path(self.settings.jobs_dir)
        removed = 0
        if root.is_dir():
            for path in root.glob(f"{SESSION_ID_PREFIX}*"):
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        self._log("sessions_started", orphan_sessions_closed=closed, orphan_workspaces_removed=removed)
        if run_janitor and self.settings.cleanup_interval_seconds > 0:
            thread = threading.Thread(target=self._janitor, name="session-janitor", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        for session_id in list(self.workers):
            self.close(session_id, "SANDBOX_STOPPED")

    def _janitor(self) -> None:
        while not self._stop.wait(min(30, self.settings.cleanup_interval_seconds)):
            try:
                self.sweep()
            except Exception:  # noqa: BLE001 - the janitor never stops the service
                logger.exception("session janitor failed")

    def sweep(self, now: datetime | None = None) -> dict[str, int]:
        """Close idle, expired and dead sessions; delete expired outputs; evict expired bundles."""
        now = now or datetime.now(timezone.utc)
        closed = 0
        for record in self.store.open_sessions():
            worker = self.workers.get(record["session_id"])
            idle = now - datetime.fromisoformat(record["last_active_at"])
            if worker is None or not worker.alive:
                self.close(record["session_id"], worker.classify_exit() if worker else "SANDBOX_RESTARTED")
                closed += 1
            elif datetime.fromisoformat(record["expires_at"]) <= now:
                self.close(record["session_id"], "SESSION_EXPIRED")
                closed += 1
            elif idle.total_seconds() > self.settings.session_idle_seconds and record["status"] != "BUSY":
                self.close(record["session_id"], "SESSION_IDLE")
                closed += 1
        deleted = 0
        for output in self.store.expired_outputs(now.isoformat()):
            (self.outputs_root / output["relative_path"]).unlink(missing_ok=True)
            self.store.delete_output(output["output_id"])
            deleted += 1
        return {"sessions_closed": closed, "outputs_deleted": deleted, "bundles_evicted": self.bundles.evict(now)}

    # ------------------------------------------------------------------ open

    def open(self, request_id: str, bundle_id: str, cpu_seconds: int | None = None) -> dict[str, Any]:
        s = self.settings
        record = self.store.get_bundle(bundle_id)
        if record is None or record["request_id"] != request_id or record["status"] != "READY":
            raise SessionError("BUNDLE_NOT_READY", "No READY bundle with this id exists for this request.", 404,
                               "PREPARE_DATA_BUNDLE")
        manifest = record["manifest"]
        if datetime.fromisoformat(manifest["expires_at"]) <= datetime.now(timezone.utc):
            raise SessionError("BUNDLE_EXPIRED", "The bundle has expired; prepare it again.", 410,
                               "PREPARE_DATA_BUNDLE")
        with self._lock:
            used = {w.uid for w in self.workers.values() if w.alive}
            free = [slot for slot in self.slots if slot[0] not in used]
            if not free:
                raise SessionError("SESSION_CAPACITY_EXCEEDED", "Every analysis session slot is in use.", 429,
                                   "RETRY_LATER", retry_after_seconds=s.retry_after_seconds)
            uid, cpus = free[0]
            session_id = f"{SESSION_ID_PREFIX}{secrets.token_hex(12)}"
            directory = Path(s.jobs_dir) / session_id
            budget = max(10, min(int(cpu_seconds or s.session_cpu_seconds), s.session_cpu_seconds))
            try:
                worker = self._launch(session_id, uid, cpus, directory, manifest, budget)
            except SessionError:
                shutil.rmtree(directory, ignore_errors=True)
                raise
            self.workers[session_id] = worker
        now = datetime.now(timezone.utc).replace(microsecond=0)
        expires = min(now + timedelta(seconds=s.session_max_seconds), datetime.fromisoformat(manifest["expires_at"]))
        self.store.insert_session({"session_id": session_id, "request_id": request_id, "bundle_id": bundle_id,
                                   "status": "ACTIVE", "slot": uid, "created_at": now.isoformat(),
                                   "last_active_at": now.isoformat(), "expires_at": expires.isoformat(),
                                   "executions": 0, "failed_executions": 0,
                                   "usage": {"cpu_seconds": 0.0, "cpu_budget": budget}})
        self._log("session_opened", request_id=request_id, session_id=session_id, bundle_id=bundle_id, uid=uid,
                  cpu_budget=budget)
        return {"session_id": session_id, "status": "ACTIVE", "bundle_id": bundle_id, "need_id": manifest["need_id"],
                "datasets": [{"data_request_id": d["data_request_id"], "logical_name": d["logical_name"],
                              "columns": [c["name"] for c in d.get("columns") or []],
                              "time_column": d.get("time_column"), "rows": d["rows"],
                              "ranges": [w["range_id"] for w in d.get("ranges") or []],
                              "quality_flags": (d.get("quality") or {}).get("quality_flags") or []}
                             for d in manifest["datasets"]],
                "relationships": [{k: r.get(k) for k in ("relationship_id", "left_request_id", "right_request_id",
                                                         "join_type", "join_semantics")}
                                  for r in manifest.get("relationships") or []],
                "helpers": HELPERS, "data_types": DATA_TYPES,
                "preloaded": ["saniti", "pd", "np", "every saniti helper by name"],
                "limits": {"execution_seconds": s.session_execution_seconds, "cpu_seconds": budget,
                           "memory_mb": s.max_memory_mb, "max_executions": s.session_max_executions,
                           "max_failed_executions": s.session_max_failed, "idle_seconds": s.session_idle_seconds,
                           "max_outputs": s.session_max_outputs, "expires_at": expires.isoformat()},
                "next_action": "RUN_PYTHON"}

    def _launch(self, session_id: str, uid: int, cpus: list[int], directory: Path, manifest: dict[str, Any],
                budget: int) -> Worker:
        s = self.settings
        drop = self.executor.drop_privileges
        root = Path(s.jobs_dir)
        root.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o711)
        directory.mkdir(mode=0o755)
        (directory / "input").mkdir(mode=0o755)
        owned = [directory / "intermediate", directory / "output", directory / "intermediate" / "home",
                 directory / "intermediate" / "tmp", directory / "intermediate" / ".duckdb_tmp"]
        for path in owned:
            path.mkdir(mode=0o700)
        mpl = Path(s.mpl_cache_dir)
        if mpl.is_dir():
            target = directory / "intermediate" / "home" / ".matplotlib"
            shutil.copytree(mpl, target)
            owned += [target, *target.rglob("*")]
        if drop:
            for path in owned:
                os.chown(path, uid, uid, follow_symlinks=False)
        requests: dict[str, Any] = {}
        for dataset in manifest["datasets"]:
            files = []
            for part in dataset["partitions"]:
                source = self.bundles.path_of(manifest["input_bundle_id"], part["file"])
                target = directory / "input" / f"{part['partition_id']}.parquet"
                try:
                    os.link(source, target)
                except OSError:
                    shutil.copyfile(source, target)
                    os.chmod(target, 0o444)
                if _sha256(target) != part["checksum_sha256"]:
                    raise SessionError("BUNDLE_INTEGRITY_ERROR", f"{part['partition_id']}: the bundle file does not "
                                                                 "match its checksum.", 500, "PREPARE_DATA_BUNDLE")
                files.append(str(target))
            quality = dataset.get("quality") or {}
            requests[dataset["data_request_id"]] = {
                "data_request_id": dataset["data_request_id"], "logical_name": dataset["logical_name"],
                "source_table": dataset["source_table"], "columns": [c["name"] for c in dataset.get("columns") or []],
                "key_columns": dataset.get("key_columns") or [], "entity_column": dataset.get("entity_column"),
                "time_column": dataset.get("time_column"), "files": files, "ranges": dataset.get("ranges") or [],
                "order_by": self._order(dataset), "rows": dataset["rows"],
                "source_frequency": dataset.get("source_frequency"),
                "analysis_frequency": dataset.get("analysis_frequency"), "resample": dataset.get("resample"),
                "resample_rules": dataset.get("resample_rules") or {}, "quality": quality}
        session = {
            "session_id": session_id, "limits": s.child_limits(budget), "cpus": cpus, "require_seccomp": True,
            "seed": s.random_seed, "reference_date": manifest["reference_date"],
            "bundle": {k: manifest.get(k) for k in ("input_bundle_id", "need_id", "request_group_id", "revision",
                                                     "mode", "reference_date", "relationships",
                                                     "relationship_warnings")},
            "requests": requests,
            "outputs": {"max_outputs": s.session_max_outputs, "max_table_rows": s.max_table_output_rows,
                        "max_json_bytes": 1 << 20, "max_text_chars": 200_000},
            "duckdb": {"memory_limit_mb": s.duckdb_memory_mb, "threads": s.threads_per_job,
                       "temp_directory": str(directory / "intermediate" / ".duckdb_tmp"),
                       "max_temp_directory_mb": max(16, s.max_intermediate_bytes // (1 << 20) - 16),
                       "allowed_directories": [str(directory / "input") + "/", str(directory / "intermediate") + "/"]}}
        path = directory / "session.json"
        path.write_text(json.dumps(session, default=str), encoding="utf-8")
        os.chmod(path, 0o444)
        reader, writer = os.pipe()
        home = directory / "intermediate" / "home"
        kwargs: dict[str, Any] = {"user": uid, "group": uid, "extra_groups": []} if drop else {}
        log = directory / "worker.log"
        with open(log, "wb") as sink:
            process = subprocess.Popen(
                [s.python_executable, "-s", "-B", str(Path(s.runtime_dir) / "session_worker.py"), str(directory),
                 str(writer)],
                cwd=str(directory / "intermediate"), env=child_environment(s, home, directory / "intermediate" / "tmp"),
                stdin=subprocess.PIPE, stdout=sink, stderr=sink, close_fds=True, pass_fds=(writer,),
                process_group=0, umask=0o077, **kwargs)
        os.close(writer)
        worker = Worker(session_id, uid, cpus, directory, process, reader, s.max_memory_mb, budget,
                        {directory / "intermediate": s.max_intermediate_bytes,
                         directory / "output": s.max_output_dir_bytes})
        stop = threading.Event()
        watcher = threading.Thread(target=worker.watch, args=(stop,), name=f"watch-{session_id}", daemon=True)
        watcher.start()
        try:
            ready = worker._read_line(time.monotonic() + 60)
        except (EOFError, ValueError):
            ready = None
        if not ready or ready.get("status") != "READY":
            worker.kill("WORKER_START_FAILED")
            tail = log.read_bytes()[-600:].decode("utf-8", "replace") if log.exists() else ""
            raise SessionError("SESSION_START_FAILED", f"The session worker did not start. {tail}"[:800], 503,
                               "RETRY_LATER")
        return worker

    @staticmethod
    def _order(dataset: dict[str, Any]) -> list[dict[str, str]]:
        keys = [c for c in [dataset.get("entity_column"), dataset.get("time_column"),
                            *(dataset.get("key_columns") or [])] if c]
        return [{"column": c, "direction": "ASC"} for c in dict.fromkeys(keys)]

    # ------------------------------------------------------------------ commands

    def _session(self, session_id: str, request_id: str) -> tuple[dict[str, Any], Worker]:
        record = self.store.get_session(session_id)
        if record is None or record["request_id"] != request_id:
            raise SessionError("SESSION_NOT_FOUND", "No session with this id exists for this request.", 404,
                               "OPEN_ANALYSIS_SESSION")
        worker = self.workers.get(session_id)
        if record["status"] == "CLOSED" or worker is None:
            raise SessionError("SESSION_CLOSED", f"The session is closed ({record.get('close_reason')}); its "
                                                 "variables are gone. Open a new session on the bundle.", 409,
                               "OPEN_ANALYSIS_SESSION", close_reason=record.get("close_reason"))
        if not worker.alive:
            reason = worker.classify_exit()
            self.close(session_id, reason)
            raise SessionError("SESSION_CLOSED", f"The session worker ended ({reason}).", 409,
                               "OPEN_ANALYSIS_SESSION", close_reason=reason)
        return record, worker

    def execute(self, session_id: str, request_id: str, code: str) -> dict[str, Any]:
        s = self.settings
        record, worker = self._session(session_id, request_id)
        if not isinstance(code, str) or not code.strip() or len(code) > s.max_code_chars:
            raise SessionError("INVALID_CODE", f"Code must be 1 to {s.max_code_chars} characters.", 422,
                               "REVISE_PYTHON_CODE")
        if record["executions"] >= s.session_max_executions:
            raise SessionError("SESSION_EXECUTION_LIMIT", f"The session has used its {s.session_max_executions} "
                                                          "executions.", 429, "COMPLETE_ANALYSIS")
        if record["failed_executions"] >= s.session_max_failed:
            raise SessionError("SESSION_RETRY_LIMIT", f"The session has had {s.session_max_failed} failed "
                                                      "executions.", 429, "REPORT_LIMITATION")
        if not worker.lock.acquire(blocking=False):
            raise SessionError("SESSION_BUSY", "The session is running another command.", 409, "RETRY_LATER",
                               retry_after_seconds=5)
        execution_id = f"exe_{secrets.token_hex(12)}"
        seq = record["executions"] + 1
        started = time.monotonic()
        cpu_before = _cpu_seconds(worker.process.pid)
        self.store.update_session(session_id, status="BUSY", last_active_at=utc_now())
        self.store.insert_execution({"execution_id": execution_id, "session_id": session_id, "seq": seq,
                                     "kind": "EXECUTE", "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
                                     "status": "RUNNING", "started_at": utc_now()})
        try:
            answer = worker.request({"op": "execute", "execution_id": execution_id, "code": code},
                                    s.session_execution_seconds)
        except (EOFError, ValueError):
            answer = None
        finally:
            worker.lock.release()
        runtime_ms = round((time.monotonic() - started) * 1000)
        if answer is None:
            reason = worker.classify_exit()
            worker.kill(reason)
            self.store.update_execution(execution_id, status="SESSION_ENDED", finished_at=utc_now(),
                                        runtime_ms=runtime_ms, error={"code": reason})
            self.close(session_id, reason)
            self._log("session_execution", session_id=session_id, execution_id=execution_id, status="SESSION_ENDED",
                      reason=reason)
            raise SessionError("SESSION_ENDED", f"The session worker ended during the execution ({reason}); its "
                                                "variables are gone.", 409, "OPEN_ANALYSIS_SESSION",
                               execution_id=execution_id, close_reason=reason)
        cpu = round(max(0.0, _cpu_seconds(worker.process.pid) - cpu_before), 3)
        status = answer.get("status") or "SCRIPT_ERROR"
        outputs, rejected = self._collect(session_id, execution_id, worker, answer.get("outputs") or [])
        failed = status != "OK"
        usage = dict(record.get("usage") or {})
        usage["cpu_seconds"] = round(float(usage.get("cpu_seconds") or 0) + cpu, 3)
        usage["peak_rss_mb"] = round(max(float(usage.get("peak_rss_mb") or 0), worker.peak_rss_mb), 1)
        self.store.update_execution(execution_id, status=status, finished_at=utc_now(), runtime_ms=runtime_ms,
                                    cpu_seconds=cpu, error=answer.get("error") or answer.get("insufficient"),
                                    access=answer.get("access") or [], outputs=[o["output_id"] for o in outputs])
        self.store.update_session(session_id, status="ACTIVE", last_active_at=utc_now(), executions=seq,
                                  failed_executions=record["failed_executions"] + int(failed), usage=usage)
        view: dict[str, Any] = {"execution_id": execution_id, "session_id": session_id, "status": status,
                                "stdout": answer.get("stdout") or "", "runtime_ms": runtime_ms, "cpu_seconds": cpu,
                                "outputs": outputs, "variables": answer.get("variables") or [],
                                "warnings": answer.get("warnings") or []}
        if rejected:
            view["rejected_outputs"] = rejected
        if status == "SCRIPT_ERROR":
            view.update({k: v for k, v in (answer.get("error") or {}).items()})
            view["next_action"] = "REVISE_PYTHON_CODE"
        elif status == "INSUFFICIENT_INPUT_DATA":
            view.update(answer.get("insufficient") or {})
            view["next_action"] = "REVISE_DATA_NEED_SPEC"
        elif status == "TIMEOUT":
            view["error_type"] = "TimeoutError"
            view["message"] = (f"The execution exceeded {s.session_execution_seconds} s and was interrupted; the "
                               "session and its earlier variables remain.")
            view["next_action"] = "REVISE_PYTHON_CODE"
        else:
            view["next_action"] = "RUN_PYTHON_OR_COMPLETE_ANALYSIS"
        view["session"] = {"executions_used": seq, "executions_limit": s.session_max_executions,
                           "failed_used": record["failed_executions"] + int(failed),
                           "failed_limit": s.session_max_failed, "cpu_seconds_used": usage["cpu_seconds"],
                           "cpu_seconds_limit": usage.get("cpu_budget")}
        self._log("session_execution", session_id=session_id, execution_id=execution_id, status=status,
                  runtime_ms=runtime_ms, cpu_seconds=cpu, outputs=len(outputs),
                  access=[{k: a.get(k) for k in ("call", "data_request_id", "range_id", "rows")}
                          for a in (answer.get("access") or [])[:20]],
                  error_type=(answer.get("error") or {}).get("error_type"),
                  error_message=str((answer.get("error") or {}).get("message") or "")[:200] or None)
        return view

    def inspect(self, session_id: str, request_id: str, names: list[str] | None, max_rows: int) -> dict[str, Any]:
        _, worker = self._session(session_id, request_id)
        if names is not None and (not isinstance(names, list) or len(names) > 20
                                  or not all(isinstance(n, str) and n.isidentifier() for n in names)):
            raise SessionError("INVALID_REQUEST", "names must be up to 20 Python identifiers.", 422)
        if not worker.lock.acquire(blocking=False):
            raise SessionError("SESSION_BUSY", "The session is running another command.", 409, "RETRY_LATER")
        try:
            answer = worker.request({"op": "inspect", "names": names, "max_rows": max_rows}, 30)
        except (EOFError, ValueError):
            reason = worker.classify_exit()
            self.close(session_id, reason)
            raise SessionError("SESSION_ENDED", f"The session worker ended ({reason}).", 409,
                               "OPEN_ANALYSIS_SESSION") from None
        finally:
            worker.lock.release()
        self.store.update_session(session_id, last_active_at=utc_now())
        text = json.dumps(answer.get("variables") or [], default=str)
        variables = json.loads(text) if len(text) <= 60_000 else json.loads(text[:0] + "[]")
        return {"session_id": session_id, "variables": variables, "truncated": len(text) > 60_000}

    def close(self, session_id: str, reason: str = "CLOSED_BY_CALLER") -> dict[str, Any]:
        worker = self.workers.pop(session_id, None)
        if worker is not None:
            worker.kill(reason if worker.death is None else worker.death)
            try:
                worker.process.wait(10)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.close(worker.reader)
            except OSError:
                pass
            if worker.process.stdin:
                try:
                    worker.process.stdin.close()
                except OSError:
                    pass
            shutil.rmtree(worker.directory, ignore_errors=True)
        record = self.store.get_session(session_id)
        if record is not None and record["status"] != "CLOSED":
            self.store.update_session(session_id, status="CLOSED", closed_at=utc_now(), close_reason=reason)
            self._log("session_closed", session_id=session_id, reason=reason)
        return {"session_id": session_id, "status": "CLOSED", "close_reason": reason}

    # ------------------------------------------------------------------ outputs

    def _collect(self, session_id: str, execution_id: str, worker: Worker, entries: list[dict[str, Any]]
                 ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Copy each emitted output into the root-only output store (checksum), with its verified metadata."""
        s = self.settings
        drop = self.executor.drop_privileges
        accepted, rejected = [], []
        now = datetime.now(timezone.utc).replace(microsecond=0)
        folder = self.outputs_root / session_id
        folder.mkdir(mode=0o700, exist_ok=True)
        for entry in entries[: s.session_max_outputs]:
            name = str(entry.get("file") or "")
            if "/" in name or name.startswith(".") or not name:
                rejected.append({"name": entry.get("name"), "reason": "invalid file name"})
                continue
            try:
                fd = os.open(worker.directory / "output" / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except OSError:
                rejected.append({"name": entry.get("name"), "reason": "file missing"})
                continue
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > s.max_artifact_bytes \
                        or (drop and info.st_uid != worker.uid):
                    rejected.append({"name": entry.get("name"), "reason": "not an acceptable regular file"})
                    continue
                kind = str(entry.get("type") or "ARTIFACT")
                fmt = str(entry.get("format") or "BIN").upper()
                output_id = f"out_{secrets.token_hex(12)}"
                relative = f"{session_id}/{output_id}.{OUTPUT_EXTENSIONS.get(fmt, 'bin')}"
                digest, size = hashlib.sha256(), 0
                with open(self.outputs_root / relative, "wb") as sink:
                    while chunk := os.read(fd, 1 << 20):
                        digest.update(chunk)
                        sink.write(chunk)
                        size += len(chunk)
                os.chmod(self.outputs_root / relative, 0o400)
            finally:
                os.close(fd)
            columns, rows = None, None
            if fmt in ("PARQUET",):
                try:
                    import pyarrow.parquet as pq

                    meta = pq.ParquetFile(self.outputs_root / relative)
                    columns, rows = meta.schema_arrow.names, meta.metadata.num_rows
                except Exception:  # noqa: BLE001 - an unreadable file is not an output
                    (self.outputs_root / relative).unlink(missing_ok=True)
                    rejected.append({"name": entry.get("name"), "reason": "unreadable Parquet"})
                    continue
            elif fmt == "CSV":
                columns, rows = entry.get("columns"), entry.get("row_count")
            record = {"output_id": output_id, "session_id": session_id, "execution_id": execution_id,
                      "name": str(entry.get("name"))[:80], "type": kind, "format": fmt, "relative_path": relative,
                      "byte_count": size, "row_count": rows, "columns": columns, "checksum_sha256": digest.hexdigest(),
                      "meta": {k: entry.get(k) for k in ("description", "title", "characters") if entry.get(k)},
                      "released": 0, "created_at": now.isoformat(),
                      "expires_at": (now + timedelta(hours=s.result_retention_hours)).isoformat()}
            self.store.insert_output(record)
            accepted.append({"output_id": output_id, "name": record["name"], "type": kind, "format": fmt,
                             "columns": columns, "row_count": rows, "byte_count": size,
                             "description": record["meta"].get("description")})
        return accepted, rejected

    def read_output(self, session_id: str, request_id: str, output_id: str, offset: int, limit: int
                    ) -> dict[str, Any]:
        record = self.store.get_session(session_id)
        output = self.store.get_output(output_id)
        if record is None or record["request_id"] != request_id or output is None \
                or output["session_id"] != session_id:
            raise SessionError("OUTPUT_NOT_FOUND", "No output with this id exists in this session.", 404)
        path = self.outputs_root / output["relative_path"]
        if not path.is_file():
            raise SessionError("OUTPUT_EXPIRED", "The output has expired.", 410)
        base = {k: output[k] for k in ("output_id", "name", "type", "format", "row_count", "columns", "byte_count",
                                       "checksum_sha256")} | {"released": bool(output["released"]),
                                                              "meta": output.get("meta") or {}}
        offset, limit = max(0, int(offset)), max(1, min(int(limit), 500))
        if output["format"] == "PARQUET":
            import pyarrow.parquet as pq

            table = pq.read_table(path)
            rows = table.slice(offset, limit).to_pylist()
            return {**base, "offset": offset, "rows": json.loads(json.dumps(rows, default=str)),
                    "next_offset": offset + len(rows) if offset + len(rows) < table.num_rows else None}
        if output["format"] == "CSV":
            import pyarrow.csv as pc

            table = pc.read_csv(path)
            rows = table.slice(offset, limit).to_pylist()
            return {**base, "offset": offset, "rows": json.loads(json.dumps(rows, default=str)),
                    "next_offset": offset + len(rows) if offset + len(rows) < table.num_rows else None}
        if output["format"] in ("JSON", "TEXT"):
            text = path.read_text(encoding="utf-8")
            chunk = text[offset * 100: offset * 100 + limit * 100]
            value: Any = chunk
            if output["format"] == "JSON" and len(text) <= limit * 100 and offset == 0:
                value = json.loads(text)
            return {**base, "offset": offset, "content": value,
                    "next_offset": offset + limit if offset * 100 + limit * 100 < len(text) else None}
        return {**base, "note": "Binary output (chart or file): metadata only."}

    def outputs(self, session_id: str) -> list[dict[str, Any]]:
        return [{k: o[k] for k in ("output_id", "execution_id", "name", "type", "format", "row_count", "columns",
                                   "byte_count", "checksum_sha256", "released")} for o in self.store.outputs_for(session_id)]

    def state(self, session_id: str, request_id: str) -> dict[str, Any]:
        record = self.store.get_session(session_id)
        if record is None or record["request_id"] != request_id:
            raise SessionError("SESSION_NOT_FOUND", "No session with this id exists for this request.", 404)
        executions = [{k: e.get(k) for k in ("execution_id", "seq", "status", "runtime_ms", "cpu_seconds",
                                             "code_sha256")} for e in self.store.executions_for(session_id)]
        return {k: record.get(k) for k in ("session_id", "bundle_id", "status", "created_at", "last_active_at",
                                           "expires_at", "closed_at", "close_reason", "executions",
                                           "failed_executions", "usage")} | {
            "execution_log": executions, "outputs": self.outputs(session_id)}

    @staticmethod
    def _log(event: str, **fields: Any) -> None:
        logger.info(json.dumps({"event": event, **fields}, default=str, separators=(",", ":")))
