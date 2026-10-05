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

import ast
import contextlib
import hashlib
import json
import logging
import os
import re
import secrets
import select
import shutil
import signal
import stat
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import carried as carried_tables
from .executor import _rss_mb, child_environment, disk_usage
from .records import utc_now

MAX_MODULES = 50
# G14: bytes one value takes in a pandas frame, by column type family (first match; dates load as Python objects).
# The same table goes to the session (session.json "frames"), so the estimate shown before code runs and the check
# that refuses a frame use one rule.
FRAME_TYPE_BYTES = [("bool", 1), ("int", 8), ("double", 8), ("float", 8), ("real", 8), ("numeric", 8),
                    ("decimal", 8), ("date", 64), ("time", 64)]
FRAME_DEFAULT_BYTES = 72  # text and anything else: a Python object


def frame_type_bytes(type_name: Any) -> int:
    name = str(type_name or "").lower()
    return next((size for key, size in FRAME_TYPE_BYTES if key in name), FRAME_DEFAULT_BYTES)


def frame_estimate(rows: int, column_types: list[Any], budget_mb: int) -> dict[str, Any]:
    """G14: a dataset's estimated pandas size and whether it may be materialized whole (DIRECT) or must be filtered
    or aggregated in DuckDB first (AGGREGATE_FIRST)."""
    per_row = sum(frame_type_bytes(t) for t in column_types) or FRAME_DEFAULT_BYTES
    megabytes = round(rows * per_row / (1 << 20), 1)
    return {"frame_mb": megabytes, "frame_budget_mb": budget_mb,
            "materialize": "DIRECT" if megabytes <= budget_mb else "AGGREGATE_FIRST"}


def imported_modules(code: str) -> list[str]:
    """The top-level modules a code text imports (import x.y / from x.y import z -> x), read from its syntax tree
    without running it; relative imports and code that does not parse give none. Pre-loaded modules such as pandas
    and numpy are listed when the code imports them, whatever the session already loaded."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return []
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return sorted(names)[:MAX_MODULES]

logger = logging.getLogger("market_python_sandbox")
SESSION_ID_PREFIX = "sess_"
OUTPUT_EXTENSIONS = {"PARQUET": "parquet", "CSV": "csv", "PNG": "png", "JSON": "json", "TEXT": "txt", "BIN": "bin"}
VALUE_UNITS = ("FRACTION", "PERCENT", "P_VALUE")


def _output_definition(definition: Any) -> dict[str, Any] | None:
    """H1: the definition the runtime validated (a dict; {} states no filter beyond the data request). Anything else
    or anything oversized is dropped, so the completion asks for it again."""
    if not isinstance(definition, dict):
        return None
    try:
        size = len(json.dumps(definition, ensure_ascii=False))
    except (TypeError, ValueError):
        return None
    return definition if size <= DEFINITION_MAX_CHARS else None


def _output_units(units: Any, columns: list[str] | None) -> dict[str, str]:
    """P23 (2026-10-02): the units an output declared ({column or field: FRACTION | PERCENT | P_VALUE}), re-checked
    here because the manifest is written inside the session: unknown units and, for a table, unknown columns are
    dropped."""
    if not isinstance(units, dict):
        return {}
    return {str(k)[:120]: v for k, v in list(units.items())[:200]
            if v in VALUE_UNITS and (columns is None or str(k) in columns)}
READ_LIMIT = 16 << 20
GRACE_SECONDS = 5.0
# S16 (suite20b r09, 2026-09-29): the worker's pipe closes while Python is still finalizing, so poll() right after
# the EOF read a crash as WORKER_UNRESPONSIVE; the exit is awaited this long before it is labelled
EXIT_WAIT_SECONDS = 2.0
EXIT_STATE_CORRUPTED = 3  # runtime/session_worker.py: the code broke the worker's own bookkeeping
WORKER_LOG_TAIL = 600
# close reasons of a worker that ended abnormally: the tail of its worker.log (a Python traceback) is logged before
# the workspace is removed; it never goes to the model
OUTPUT_ID_RE = re.compile(r"^out_[0-9a-f]{24}$")
RESTORE_VERSION = 1  # R-STORE: POST /v1/sessions/{id}/carried and GET .../outputs/{id}/file
SESSION_RELEASE_VERSION = 1  # S28: POST /v1/requests/{request_id}/release and the open queue
ABNORMAL_REASONS = frozenset({"WORKER_CRASHED", "WORKER_UNRESPONSIVE", "SESSION_STATE_CORRUPTED", "PROTOCOL_ERROR",
                              "FORBIDDEN_OPERATION", "CPU_BUDGET_EXCEEDED", "MEMORY_LIMIT_EXCEEDED",
                              "DISK_LIMIT_EXCEEDED", "EXECUTION_TIMEOUT_UNINTERRUPTIBLE", "WORKER_START_FAILED"})
# The value types of every frame the helpers return (DuckDB .df(date_as_object=True)). Most failed executions in the
# 2026-09-26 stress test were pandas date idioms applied to these date objects (TypeError, KeyError, AttributeError).
DATA_TYPES = ("Frames from load, range, sql and join: the time column holds datetime.date "
              "objects (object dtype), numeric columns are float64, text columns are pandas strings. Compare dates "
              "with datetime.date(2026, 1, 2) (import datetime) or select a period with range(); before .dt, "
              ".resample(), .loc['2026-01-02'] or a comparison with a date string, convert first: "
              "frame[col] = pd.to_datetime(frame[col]).")
STATE_CORRUPTED_HINT = ("The code changed the session's own state (the saniti_session/research_* modules, stdin or the "
                        "protocol pipe). Do not import or modify the sandbox's internal modules.")
# S13: the per-angle records the research_* helpers write; one of each per angle and epoch
RESEARCH_RECORDS = ("research_call_", "research_input_")
# H1: the largest output definition kept (runtime/saniti_session.py DEFINITION_MAX_CHARS)
DEFINITION_MAX_CHARS = 4000
RESEARCH_HELPERS = ["research_conditional", "research_persistence", "research_group_comparison", "research_quantiles",
                    "research_temporal_dependency", "research_custom"]


# Found live (golden run 2026-09-29): with only a prose hint the model passed a contract entry as request= (a dict),
# tried to import runtime internals, and read a trailing return column as the outcome. Each angle now carries one
# concrete call in the declarative form, and the view states the expression grammar and the outcome rule.
RESEARCH_EXAMPLES = {
    "conditional_distribution": ("research_conditional", "condition='close / lag(close, 1) - 1 <= -0.05', "
                                                         "outcome={'forward_return': 'close'}"),
    "threshold_sensitivity": ("research_conditional", "signal='(close / lag(close, 1) - 1) * 100', "
                                                      "outcome={'forward_return': 'close'}"),
    "streak_persistence": ("research_persistence", "state='close < lag(close, 1)'"),
    "regime_comparison": ("research_group_comparison", "group={'column': '<label column>'}, "
                                                       "outcome={'forward_return': 'close'}"),
    "cohort_comparison": ("research_group_comparison", "group={'column': '<label column>'}, "
                                                       "outcome={'forward_return': 'close'}"),
    "quantile_ranking": ("research_quantiles", "signal='close / lag(close, 20) - 1', "
                                               "outcome={'forward_return': 'close'}"),
    "lead_lag": ("research_temporal_dependency", "leader='close / lag(close, 1) - 1', "
                                                 "follower={'forward_return': 'close'}"),
    "correlation_dependency": ("research_temporal_dependency", "leader='close / lag(close, 1) - 1', "
                                                               "follower={'forward_return': 'close'}"),
}
RESEARCH_RULES = (
    "Record every angle exactly once, then call complete_research_run. Preferred (FORMULA_AND_STATISTICS_VERIFIED): "
    "request='<data_request_id string from the angle's contract>' with each role as an expression string over that "
    "request's columns. Expressions: + - * / **, comparisons, & | ~, abs log exp sqrt sign min max where, "
    "lag(x, k), rolling_sum(x, n), rolling_mean(x, n); past values only. The outcome (or follower) is "
    "{'forward_return': '<price column>'}: the backend computes the forward return over the approved horizon and "
    "unit, so never use a trailing return column or a price level as the outcome (a price level is refused as "
    "OUTCOME_NOT_APPROVED). When the price column is in another request of the angle's contract, add "
    "'request': '<that data_request_id>'. A label role is {'column': '<name>'}. "
    "Otherwise frame=<DataFrame with date, entity and one column per role> (STATISTICS_VERIFIED). research_custom "
    "only when no helper fits (EXECUTION_ONLY). Thresholds, lags, buckets, groups and horizons come from the approved "
    "plan, never from the code. The helpers are in saniti; do not import runtime modules.")


PRICE_COLUMNS = ("close", "adj_close", "close_price", "price", "last_price")


def _research_example(angle_id: str, helper: str, roles: str, datasets: list[dict[str, Any]]) -> str:
    """One runnable example call for an angle, built on its own contract (S15/G12, suite20 2026-09-29): the price
    column comes from the contract; when it is in another request than the first, the forward return names that
    request; when the contract has no price column, the example says a forward return cannot be declared."""
    if not roles:
        return f"saniti.research_custom({angle_id!r}, result, note)"
    request = datasets[0].get("data_request_id") if datasets else "<data_request_id>"
    located = next(((d.get("data_request_id"), c) for name in PRICE_COLUMNS for d in datasets
                    for c in d.get("columns") or [] if c == name), None)
    if located is None:
        located = next(((d.get("data_request_id"), c) for d in datasets for c in d.get("columns") or []
                        if "close" in c.lower() or "price" in c.lower()), None)
    example = roles
    if "forward_return" in roles:
        if located is None:
            return (f"saniti.{helper}({angle_id!r}, request={request!r}, {roles}) -- note: this angle's contract has "
                    "no price column, so a forward return cannot be declared; record it with research_custom and say why.")
        other, column = located
        if other == request:
            example = example.replace("close", column)  # expressions and the forward return on this request's price
        else:
            example = example.replace("{'forward_return': 'close'}",
                                      f"{{'forward_return': {column!r}, 'request': {other!r}}}")
    return f"saniti.{helper}({angle_id!r}, request={request!r}, {example})"


def research_view(research: dict[str, Any]) -> dict[str, Any]:
    """What the model sees of a multi-angle research session: the group's angles with their method, the approved
    values, the contract's requests, columns and ranges, one example call per angle, and how to record them."""
    angles = []
    for angle_id, angle in sorted((research.get("angles") or {}).items()):
        contract = angle.get("contract") or {}
        datasets = contract.get("datasets") or []
        helper, roles = RESEARCH_EXAMPLES.get(angle.get("method_id"), ("research_custom", ""))
        angles.append({"angle_id": angle_id, "method_id": angle.get("method_id"), "helper": helper,
                       "question": angle.get("angle_question"), "expected_direction": angle.get("expected_direction"),
                       "outcome_horizon_periods": angle.get("outcome_horizon_periods"),
                       "outcome_unit": angle.get("outcome_unit"), "parameters": angle.get("parameters"),
                       "contract": [{"data_request_id": d.get("data_request_id"), "logical_name": d.get("logical_name"),
                                     "columns": d.get("columns"),
                                     "ranges": [w.get("range_id") for w in d.get("ranges") or []]}
                                    for d in datasets],
                       "example": _research_example(angle_id, helper, roles, datasets)})
    return {"research_run_id": research.get("research_run_id"), "bundle_group_id": research.get("bundle_group_id"),
            "angles": angles, "record_each_angle": RESEARCH_RULES}


HELPERS = ["requests()", "manifest()", "quality(request)", "load(request, columns=None)",
           "load_range(request, range_id, columns=None, include_buffers=False) (also saniti.range; plain range is "
           "Python's built-in)", "in_period(frame, request, range_id=None, date_column=None) (mask of the rows inside "
           "the approved ranges, without buffer rows: count and summarise only these)", "sql(query, params=None)",
           "relation(request)", "load_output(output_id, columns=None) (a released table of this conversation; see "
           "carried())", "carried()", "join(relationship_id, left=None, right=None, how=None)",
           "resample(frame, request, frequency=None)",
           "period_return(request, range_id, value_column='close', entity_column=None, date_column=None)",
           "event_study(request, event, outcome, horizon, *, range_id=None, overlap_policy='NON_OVERLAPPING', "
           "baseline='ALL_ELIGIBLE', min_events=None, holdout_start=None, outcome_unit=None, name=None) "
           "(recomputed by the backend at complete_analysis; outcome_unit is the approved experiment's in a research "
           "session, else PERCENT)",
           "backtest(request, frame, signal, *, exit_signal=None, stop=None, target=None, max_hold=None, fee=None, "
           "unit=None, prices=None, range_id=None, name=None) (trades of a stated rule on the bundle prices; re-run "
           "by the backend at complete_analysis)",
           "insufficient_data(request, range_id=None, value=None, unit='TRADING_OBSERVATIONS', "
           "requirement_type='ADDITIONAL_HISTORY', reason='')", "intermediate_path(name)",
           "emit_table(name, frame, description='', units=None, definition=None) (definition required to release: "
           "{'filters': [{'column', 'operator', 'value'}], 'period', 'entities', 'thresholds', 'notes'}; {} when the "
           "code added no filter to the data request)",
           "emit_chart(figure=None, name='chart', title='', description='')",
           "emit_json(name, value, description='', units=None, definition=None) (definition as for emit_table)",
           "emit_text(name, text, description='')",
           "emit_file(name, data, format='PARQUET'|'CSV'|'PNG'|..., description='')", "add_warning(code, message)"]


MAX_RESAMPLE_LOGS = 20
RESAMPLE_LOG_FIELDS = ("data_request_id", "source_frequency", "target_frequency", "input_rows", "rows", "periods",
                       "rules_sha256", "semantics_version", "incomplete_periods")


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
        try:
            code = self.process.wait(EXIT_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            return "WORKER_UNRESPONSIVE"
        if code == EXIT_STATE_CORRUPTED:
            return "SESSION_STATE_CORRUPTED"
        if code == -signal.SIGXCPU or (code == -signal.SIGKILL and self.last_cpu >= self.cpu_budget - 2):
            return "CPU_BUDGET_EXCEEDED"
        if code == -signal.SIGSYS:
            return "FORBIDDEN_OPERATION"
        return "WORKER_CRASHED"

    def log_tail(self) -> str | None:
        """The last bytes of the worker's own stdout/stderr (worker.log), for the server log only."""
        try:
            with open(self.directory / "worker.log", "rb") as handle:
                handle.seek(0, os.SEEK_END)
                handle.seek(max(0, handle.tell() - WORKER_LOG_TAIL))
                text = handle.read().decode("utf-8", "replace").strip()
        except OSError:
            return None
        return text or None

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
        try:
            return json.loads(line.decode("utf-8"))
        except ValueError:
            # something other than the worker wrote to the protocol pipe: the session cannot be trusted
            self.kill("PROTOCOL_ERROR")
            raise EOFError from None

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
        # carried outputs (2026-10-02): per session the outputs it may load (None: every table of the conversation),
        # and the profiles of the tables and bundle datasets already summarised
        self.carried_allowed: dict[str, set[str] | None] = {}
        self.profiles: dict[str, dict[str, Any]] = {}
        # S14: session workspaces are this manager's; the analysis janitor must leave them alone
        getattr(analysis, "foreign_prefixes", set()).add(SESSION_ID_PREFIX)
        self._lock = threading.Lock()
        # S28: openers waiting for a slot, first come first served; woken when a slot may have been freed
        self._freed = threading.Condition()
        self._waiting: deque[object] = deque()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        # IP2: set by DataNeedService when PY_SANDBOX_AUDIT_STORE_ENABLED (app/audit.py AuditOutbox)
        self.audit: Any = None
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

    def open(self, request_id: str, bundle_id: str, cpu_seconds: int | None = None, *,
             conversation_key: str | None = None, need_id: str | None = None, bound: bool = False,
             research: dict[str, Any] | None = None, carried_outputs: list[str] | None = None,
             findings: dict[str, Any] | None = None) -> dict[str, Any]:
        """A new session on a READY bundle of this request, or (bound) on an earlier bundle of the same conversation
        that the service bound to this request's approved need. With no free slot, the least recently used WARM_IDLE
        session is evicted; an ACTIVE or BUSY session never is."""
        s = self.settings
        record = self.store.get_bundle(bundle_id)
        if record is None or (record["request_id"] != request_id and not bound) or record["status"] != "READY":
            raise SessionError("BUNDLE_NOT_READY", "No READY bundle with this id exists for this request.", 404,
                               "PREPARE_DATA_BUNDLE")
        manifest = record["manifest"]
        if datetime.fromisoformat(manifest["expires_at"]) <= datetime.now(timezone.utc):
            raise SessionError("BUNDLE_EXPIRED", "The bundle has expired; prepare it again.", 410,
                               "PREPARE_DATA_BUNDLE")
        self._settle_request(request_id)
        with self._slot(request_id) as (uid, cpus):
            session_id = f"{SESSION_ID_PREFIX}{secrets.token_hex(12)}"
            directory = Path(s.jobs_dir) / session_id
            budget = max(10, min(int(cpu_seconds or s.session_cpu_seconds), s.session_cpu_seconds))
            try:
                worker = self._launch(session_id, uid, cpus, directory, manifest, budget, research, findings)
            except SessionError:
                shutil.rmtree(directory, ignore_errors=True)
                raise
            self.workers[session_id] = worker
        now = datetime.now(timezone.utc).replace(microsecond=0)
        expires = min(now + timedelta(seconds=s.session_max_seconds), datetime.fromisoformat(manifest["expires_at"]))
        need_id = need_id or manifest["need_id"]
        self.store.insert_session({"session_id": session_id, "request_id": request_id, "bundle_id": bundle_id,
                                   "status": "ACTIVE", "slot": uid, "created_at": now.isoformat(),
                                   "last_active_at": now.isoformat(), "expires_at": expires.isoformat(),
                                   "executions": 0, "failed_executions": 0,
                                   "usage": {"cpu_seconds": 0.0, "cpu_budget": budget},
                                   "origin_request_id": request_id, "conversation_key": conversation_key,
                                   "need_id": need_id, "epoch": 1, "epoch_start_seq": 0})
        self.store.insert_epoch({"session_id": session_id, "epoch": 1, "request_id": request_id, "need_id": need_id,
                                 "start_seq": 0, "attached_at": now.isoformat()})
        self._log("session_opened", request_id=request_id, session_id=session_id, bundle_id=bundle_id, uid=uid,
                  cpu_budget=budget, bound_bundle=bound, conversation=bool(conversation_key))
        self.carried_allowed[session_id] = self._allowed(need_id, carried_outputs)
        view = self._view(session_id, bundle_id, need_id, manifest, budget, expires.isoformat())
        if research:
            view["research"] = research_view(research)
        self._offer_carried(session_id, view)
        return view

    def _allowed(self, need_id: str | None, carried_outputs: list[str] | None) -> set[str] | None:
        """A RESEARCH need's session loads only the carried tables its approved plan names (none when it names none);
        an analysis session may load every released table of its conversation."""
        need = self.store.get_need(need_id) if need_id else None
        if (need or {}).get("mode") == "RESEARCH":
            return {str(o) for o in carried_outputs or []}
        return None

    def stage_carried(self, session_id: str) -> list[dict[str, Any]]:
        """Link the session's carried tables into input/carried with their manifest (before every execution, so a
        table released by another session of the conversation since is there too)."""
        record = self.store.get_session(session_id)
        worker = self.workers.get(session_id)
        if record is None or worker is None or not self.settings.conversation_reuse:
            return []
        outputs = carried_tables.candidates(self.store, record.get("conversation_key"), session_id)
        if not outputs and not (worker.directory / "input" / carried_tables.CARRIED_DIR).exists():
            return []
        return carried_tables.stage(worker.directory, outputs, outputs_root=self.outputs_root,
                                    origin_of=self._release_origin,
                                    allowed=self.carried_allowed.get(session_id), profiles=self.profiles,
                                    now=utc_now())

    def _offer_carried(self, session_id: str, view: dict[str, Any]) -> None:
        try:
            entries = self.stage_carried(session_id)
        except Exception as exc:  # noqa: BLE001 - a carried table never blocks a session
            self._log("carried_outputs_failed", session_id=session_id, error=type(exc).__name__)
            entries = []
        # R-STORE: every carried output_id (the listing below shows at most 20), so the orchestrator uploads only
        # the stored tables this sandbox no longer holds
        view["carried_output_ids"] = [e["output_id"] for e in entries]
        if entries:
            view["carried_outputs"] = carried_tables.listing(entries)
            view["carried_note"] = ("Tables released earlier in this conversation; load one with "
                                    "load_output(output_id) and read its profile with carried(). Each keeps its "
                                    "label: a figure derived from it is never stronger than that label.")

    def _free_slots(self) -> list[tuple[int, list[int]]]:
        used = {w.uid for w in self.workers.values() if w.alive}
        return [slot for slot in self.slots if slot[0] not in used]

    # ------------------------------------------------------------------ S28: slots, release and the open queue

    def _settle_request(self, request_id: str) -> None:
        """S28 (golden g7 2026-10-02: three sessions opened in one answer): one active session per request. Opening
        another session moves this request's ACTIVE sessions that already completed to WARM_IDLE, so they can be
        reused or evicted; a session without a completion keeps its work until a slot is needed."""
        if not self.settings.conversation_reuse:
            return
        for record in self.store.sessions_for(request_id):
            worker = self.workers.get(record["session_id"])
            if record["status"] == "ACTIVE" and worker is not None and worker.alive \
                    and self.store.passed_completions(record["session_id"]):
                self.store.update_session(record["session_id"], status="WARM_IDLE", last_active_at=utc_now())
                self._log("session_settled", request_id=request_id, session_id=record["session_id"])

    def _take_slot(self, request_id: str) -> tuple[int, list[int]] | None:
        """A free slot, after evicting the least recently used WARM_IDLE session, then this request's own ACTIVE
        sessions that never completed (the caller opened another one instead); ACTIVE sessions of other requests and
        BUSY sessions are never taken. Called with self._lock held."""
        free = self._free_slots()
        if not free:
            for warm in self.store.warm_sessions():
                if warm["session_id"] in self.workers:
                    self._close_locked(warm["session_id"], "EVICTED")
                    break
            free = self._free_slots()
        if not free:
            for record in self.store.sessions_for(request_id):
                if record["status"] == "ACTIVE" and record["session_id"] in self.workers:
                    self._close_locked(record["session_id"], "REPLACED_IN_REQUEST")
                    break
            free = self._free_slots()
        return free[0] if free else None

    @contextlib.contextmanager
    def _slot(self, request_id: str):
        """Hold self._lock with a free slot. With no slot, wait up to PY_SANDBOX_OPEN_WAIT_SECONDS in arrival order
        (S28: a refusal at once failed the answer while another conversation finished seconds later)."""
        s = self.settings
        ticket, started = object(), time.monotonic()
        with self._freed:
            self._waiting.append(ticket)
        try:
            while True:
                with self._freed:
                    first = self._waiting[0] is ticket
                if first:
                    with self._lock:
                        slot = self._take_slot(request_id)
                        if slot is not None:
                            with self._freed:
                                self._waiting.remove(ticket)
                                self._freed.notify_all()
                            ticket = None
                            waited = time.monotonic() - started
                            if waited >= 1:
                                self._log("session_open_waited", request_id=request_id, seconds=round(waited, 1))
                            yield slot
                            return
                left = s.open_wait_seconds - (time.monotonic() - started)
                if left <= 0:
                    raise SessionError(
                        "SESSION_CAPACITY_EXCEEDED",
                        f"Every analysis session slot is in use (waited {int(time.monotonic() - started)} s).", 429,
                        "RETRY_LATER", retry_after_seconds=s.retry_after_seconds,
                        waited_seconds=int(time.monotonic() - started))
                with self._freed:
                    self._freed.wait(min(1.0, left))
        finally:
            if ticket is not None:
                with self._freed:
                    if ticket in self._waiting:
                        self._waiting.remove(ticket)
                    self._freed.notify_all()

    def _slot_freed(self) -> None:
        with self._freed:
            self._freed.notify_all()

    def release(self, request_id: str) -> list[dict[str, Any]]:
        """S28: the end of a request's answer. Each of its open sessions that completed goes to WARM_IDLE (reusable
        by the conversation, or evicted when a slot is needed); any other (never completed, or BUSY with an
        execution the caller stopped waiting for) is closed with RELEASED."""
        done = []
        for record in self.store.sessions_for(request_id):
            if record["status"] not in ("ACTIVE", "BUSY", "WARM_IDLE"):
                continue
            worker = self.workers.get(record["session_id"])
            keep = self.settings.conversation_reuse and bool(record.get("conversation_key")) \
                and record["status"] != "BUSY" and worker is not None and worker.alive \
                and bool(self.store.passed_completions(record["session_id"]))
            if keep:
                if record["status"] != "WARM_IDLE":
                    self.store.update_session(record["session_id"], status="WARM_IDLE", last_active_at=utc_now())
                done.append({"session_id": record["session_id"], "status": "WARM_IDLE"})
            else:
                done.append({k: v for k, v in self.close(record["session_id"], "RELEASED").items()
                             if k in ("session_id", "status")})
        self._slot_freed()
        self._log("request_released", request_id=request_id, sessions=len(done),
                  warm=sum(1 for d in done if d["status"] == "WARM_IDLE"))
        return done

    def _view(self, session_id: str, bundle_id: str, need_id: str, manifest: dict[str, Any], budget: Any,
              expires_at: str) -> dict[str, Any]:
        from .bundles import row_counts

        s = self.settings
        return {"session_id": session_id, "status": "ACTIVE", "bundle_id": bundle_id, "need_id": need_id,
                "datasets": [{"data_request_id": d["data_request_id"], "logical_name": d["logical_name"],
                              "columns": [c["name"] for c in d.get("columns") or []],
                              "time_column": d.get("time_column"), **row_counts(d),
                              **frame_estimate(int(d["rows"] or 0), [c.get("type") for c in d.get("columns") or []],
                                               s.frame_budget_mb),
                              "ranges": [w["range_id"] for w in d.get("ranges") or []],
                              "quality_flags": (d.get("quality") or {}).get("quality_flags") or [],
                              "profile": self._dataset_profile(manifest, d)}
                             for d in manifest["datasets"]],
                "relationships": [{k: r.get(k) for k in ("relationship_id", "left_request_id", "right_request_id",
                                                         "join_type", "join_semantics")}
                                  for r in manifest.get("relationships") or []],
                "helpers": HELPERS, "data_types": DATA_TYPES,
                "preloaded": ["saniti", "pd", "np", "every saniti helper by name"],
                "limits": {"execution_seconds": s.session_execution_seconds, "cpu_seconds": budget,
                           "memory_mb": s.max_memory_mb, "max_executions": s.session_max_executions,
                           "max_failed_executions": s.session_max_failed, "idle_seconds": s.session_idle_seconds,
                           "max_outputs": s.session_max_outputs, "expires_at": expires_at},
                "next_action": "RUN_PYTHON"}

    def _dataset_profile(self, manifest: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any] | None:
        """P1: the shape of a bundle dataset (computed once per bundle and request; a failure leaves it out)."""
        key = f"{manifest['input_bundle_id']}:{dataset['data_request_id']}"
        if key not in self.profiles:
            try:
                paths = [str(self.bundles.path_of(manifest["input_bundle_id"], part["file"]))
                         for part in dataset.get("partitions") or []]
                self.profiles[key] = carried_tables.profile(
                    paths, time_column=dataset.get("time_column"), entity_column=dataset.get("entity_column"),
                    columns=[c["name"] for c in dataset.get("columns") or []])
            except Exception as exc:  # noqa: BLE001 - a profile never blocks a session
                self._log("dataset_profile_failed", bundle_id=manifest.get("input_bundle_id"), error=type(exc).__name__)
                return None
        return self.profiles[key]

    def attach(self, session_id: str, request_id: str, need_id: str,
               carried_outputs: list[str] | None = None) -> dict[str, Any]:
        """A later request of the same conversation takes over a WARM_IDLE session (conversation reuse, S2): a new
        epoch starts for this request and its approved need. The namespace, the cumulative execution, failure and CPU
        counters and the expiry stay; earlier completions and released outputs are never changed."""
        record = self.store.get_session(session_id)
        worker = self.workers.get(session_id)
        if record is None or record["status"] != "WARM_IDLE" or worker is None or not worker.alive:
            raise SessionError("SESSION_NOT_REUSABLE", "The earlier session is no longer alive; open a new session on "
                                                       "the bundle.", 409, "OPEN_ANALYSIS_SESSION")
        epoch = self._new_epoch(record, request_id, need_id)
        bundle = self.store.get_bundle(record["bundle_id"])["manifest"]
        usage = record.get("usage") or {}
        view = self._view(session_id, record["bundle_id"], need_id, bundle, usage.get("cpu_budget"),
                          record["expires_at"])
        variables: list[Any] = []
        if worker.lock.acquire(blocking=False):
            try:
                variables = (worker.request({"op": "inspect", "names": None, "max_rows": 0}, 30).get("variables")
                             or [])[:60]
            except (EOFError, ValueError):
                variables = []
            finally:
                worker.lock.release()
        passed = [c for c in self.store.passed_completions(session_id)
                  if (c.get("final_status") or {}).get("status") == "COMPLETED"]
        view.update({"reused_session": True, "epoch": epoch, "origin_request_id": record.get("origin_request_id"),
                     "parent_completion_id": passed[-1]["completion_id"] if passed else None,
                     "variables": variables,
                     "session_budget": {"executions_used": record["executions"],
                                        "failed_used": record["failed_executions"],
                                        "cpu_seconds_used": usage.get("cpu_seconds")},
                     "note": "The variables of the earlier message are still defined. Data read before counts for "
                             "coverage only with a successful execution and an output in this message."})
        self.carried_allowed[session_id] = self._allowed(need_id, carried_outputs)
        self._offer_carried(session_id, view)
        self._log("session_attached", request_id=request_id, session_id=session_id, epoch=epoch, need_id=need_id,
                  origin_request_id=record.get("origin_request_id"))
        return view

    def _new_epoch(self, record: dict[str, Any], request_id: str, need_id: str | None) -> int:
        epoch = int(record.get("epoch") or 1) + 1
        now = utc_now()
        self.store.update_session(record["session_id"], request_id=request_id, status="ACTIVE", epoch=epoch,
                                  epoch_start_seq=record["executions"], need_id=need_id or record.get("need_id"),
                                  last_active_at=now)
        self.store.insert_epoch({"session_id": record["session_id"], "epoch": epoch, "request_id": request_id,
                                 "need_id": need_id or record.get("need_id"), "start_seq": record["executions"],
                                 "attached_at": now})
        return epoch

    def _launch(self, session_id: str, uid: int, cpus: list[int], directory: Path, manifest: dict[str, Any],
                budget: int, research: dict[str, Any] | None = None, findings: dict[str, Any] | None = None
                ) -> Worker:
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
                "resample_rules": dataset.get("resample_rules") or {},
                **({"resample_semantics_version": dataset["resample_semantics_version"]}
                   if dataset.get("resample_semantics_version") is not None else {}),
                "aggregation_rules": dataset.get("aggregation_rules") or {}, "quality": quality}
        session = {
            "session_id": session_id, "limits": s.child_limits(budget), "cpus": cpus, "require_seccomp": True,
            "seed": s.random_seed, "reference_date": manifest["reference_date"],
            **({"observe_modules": True} if self.audit is not None else {}),
            **({"extra_helpers": [*(["event_summary"] if s.research_findings_enabled else []),
                                  *(RESEARCH_HELPERS if research else [])]}
               if s.research_findings_enabled or research else {}),
            **({"research_v2": research} if research else {}),
            # M28: the approved hypothesis plan's findings values (success_rule, min_effect, ...), read by event_summary
            **({"research_v1": {"findings": findings}} if findings else {}),
            "bundle": {k: manifest.get(k) for k in ("input_bundle_id", "need_id", "request_group_id", "revision",
                                                     "mode", "reference_date", "relationships",
                                                     "relationship_warnings")},
            "requests": requests,
            "outputs": {"max_outputs": s.session_max_outputs, "max_table_rows": s.max_table_output_rows,
                        "max_json_bytes": 1 << 20, "max_text_chars": 200_000},
            "frames": {"budget_mb": s.frame_budget_mb, "budget_bytes": s.frame_budget_mb << 20,
                       "type_bytes": FRAME_TYPE_BYTES,
                       "default_bytes": FRAME_DEFAULT_BYTES},
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

    def _session(self, session_id: str, request_id: str, reopen: bool = False) -> tuple[dict[str, Any], Worker]:
        record = self.store.get_session(session_id)
        if record is None or record["request_id"] != request_id:
            raise SessionError("SESSION_NOT_FOUND", "No session with this id exists for this request.", 404,
                               "OPEN_ANALYSIS_SESSION")
        if record["status"] == "WARM_IDLE" and reopen and session_id in self.workers:
            # an execution after complete_analysis passed: a new epoch, not released until it completes again
            self._new_epoch(record, request_id, record.get("need_id"))
            record = self.store.get_session(session_id)
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
        if not isinstance(code, str) or not code.strip() or len(code) > s.max_code_chars:
            raise SessionError("INVALID_CODE", f"Code must be 1 to {s.max_code_chars} characters.", 422,
                               "REVISE_PYTHON_CODE")
        record, worker = self._session(session_id, request_id, reopen=True)
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
        started_at = utc_now()
        modules = imported_modules(code)
        try:
            self.stage_carried(session_id)
        except Exception as exc:  # noqa: BLE001 - a carried table never blocks an execution
            self._log("carried_outputs_failed", session_id=session_id, error=type(exc).__name__)
        self.store.insert_execution({"execution_id": execution_id, "session_id": session_id, "seq": seq,
                                     "kind": "EXECUTE", "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
                                     "status": "RUNNING", "started_at": started_at,
                                     "epoch": int(record.get("epoch") or 1), "request_id": request_id,
                                     "modules": modules})
        try:
            answer = worker.request({"op": "execute", "execution_id": execution_id, "code": code},
                                    s.session_execution_seconds)
        except (EOFError, ValueError):
            answer = None
        finally:
            worker.lock.release()
        runtime_ms = round((time.monotonic() - started) * 1000)
        corrupted = answer is not None and answer.get("status") == "SESSION_STATE_CORRUPTED"
        if answer is None or corrupted:
            reason = "SESSION_STATE_CORRUPTED" if corrupted else worker.classify_exit()
            worker.kill(reason)
            detail = (answer or {}).get("error") or {}
            error = {"code": reason, **({"error_type": detail.get("error_type"), "message": detail.get("message"),
                                         "cause": detail.get("cause")} if corrupted else {})}
            tail = worker.log_tail()
            self.store.update_execution(execution_id, status="SESSION_ENDED", finished_at=utc_now(),
                                        runtime_ms=runtime_ms, error=error)
            if self.audit is not None:
                # S16: the code that ended a session is archived too (it was the one execution missing from the audit)
                self._archive_execution(record, request_id, execution_id, seq, code,
                                        {"error": {**error, "worker_log_tail": tail}}, "SESSION_ENDED", started_at,
                                        runtime_ms, 0.0)
            self.close(session_id, reason)
            self._log("session_execution", session_id=session_id, execution_id=execution_id, status="SESSION_ENDED",
                      reason=reason, cause=error.get("cause"))
            message = (f"The session worker ended during the execution ({reason}); its variables are gone."
                       + (f" {STATE_CORRUPTED_HINT}" if corrupted else ""))
            raise SessionError("SESSION_ENDED", message, 409, "OPEN_ANALYSIS_SESSION",
                               execution_id=execution_id, close_reason=reason)
        cpu = round(max(0.0, _cpu_seconds(worker.process.pid) - cpu_before), 3)
        status = answer.get("status") or "SCRIPT_ERROR"
        outputs, rejected = self._collect(session_id, execution_id, worker, answer.get("outputs") or [],
                                          recorded=self._recorded_angles(session_id, record))
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
            if view.get("error_type") == "MaterializationLimitExceeded":
                # G14: the data stay in this session; reduce them in DuckDB here instead of fetching them again
                view.update(next_action="AGGREGATE_IN_SQL",
                            forbidden_actions=["SUBMIT_DATA_NEED_SPEC", "PREPARE_DATA_BUNDLE", "OPEN_ANALYSIS_SESSION"])
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
                  runtime_ms=runtime_ms, cpu_seconds=cpu, outputs=len(outputs), modules=modules,
                  access=[{k: a.get(k) for k in ("call", "data_request_id", "range_id", "rows")}
                          for a in (answer.get("access") or [])[:20]],
                  error_type=(answer.get("error") or {}).get("error_type"),
                  error_message=str((answer.get("error") or {}).get("message") or "")[:200] or None)
        for entry in (answer.get("access") or [])[:MAX_RESAMPLE_LOGS]:
            if entry.get("call") == "resample":  # IP2: an observable, bounded resample trace (never the data)
                self._log("saniti_resample", request_id=request_id, session_id=session_id, execution_id=execution_id,
                          **{k: entry.get(k) for k in RESAMPLE_LOG_FIELDS})
        if self.audit is not None:
            self._archive_execution(record, request_id, execution_id, seq, code, answer, status, started_at,
                                    runtime_ms, cpu)
        return view

    def _archive_execution(self, record: dict[str, Any], request_id: str, execution_id: str, seq: int, code: str,
                           answer: dict[str, Any], status: str, started_at: str, runtime_ms: int,
                           cpu: float) -> None:
        """IP2: hand the execution to the audit outbox (harness side, after the fact). Never fails the execution."""
        try:
            from .data_need import data_contract_sha256

            bundle = self.store.get_bundle(record["bundle_id"])["manifest"]
            inputs, position = [], 0
            for dataset in bundle["datasets"]:
                ordering = [o["column"] for o in self._order(dataset)]
                for part in dataset["partitions"]:
                    path = self.bundles.path_of(bundle["input_bundle_id"], part["file"])
                    inputs.append({"position": position, "data_request_id": dataset["data_request_id"],
                                   "dataset_id": part.get("dataset_id"), "sha256": part["checksum_sha256"],
                                   "size_bytes": path.stat().st_size if path.exists() else None,
                                   "ordering": ordering})
                    position += 1
            need = self.store.get_need(record.get("need_id") or bundle["need_id"])
            contract = data_contract_sha256(need["approved"]) if need and need.get("approved") else None
            self.audit.record_execution(
                request_id=request_id, session={"session_id": record["session_id"], "bundle_id": record["bundle_id"]},
                execution_id=execution_id, seq=seq, code=code, answer=answer, status=status, started_at=started_at,
                finished_at=utc_now(), runtime_ms=runtime_ms, cpu_seconds=cpu, inputs=inputs,
                contract_sha256=contract)
        except Exception as exc:  # noqa: BLE001 - audit is optional
            self._log("sandbox_audit_enqueue_failed", request_id=request_id, execution_id=execution_id,
                      error=type(exc).__name__)

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

    def inspect_dataset(self, session_id: str, request_id: str, dataset: str) -> dict[str, Any]:
        """D1 (round 2026-10-03): the profiler's full statistics of one dataset of the session's bundle (every column,
        gaps, empty entities, duplicate keys); no row values. Read from the bundle manifest, so it works after the
        session closed and after the bundle's files expired."""
        record = self.store.get_session(session_id)
        if record is None or record["request_id"] != request_id:
            raise SessionError("SESSION_NOT_FOUND", "No session with this id exists for this request.", 404,
                               "OPEN_ANALYSIS_SESSION")
        manifest = (self.store.get_bundle(record["bundle_id"]) or {}).get("manifest") or {}
        datasets = manifest.get("datasets") or []
        found = next((d for d in datasets if dataset in (d.get("logical_name"), d.get("data_request_id"))), None)
        if found is None:
            raise SessionError("DATASET_NOT_FOUND", f"The session's bundle has no dataset '{dataset}'.", 404,
                               "FIX_ARGUMENTS", datasets=[d.get("logical_name") for d in datasets])
        from .bundles import RANGE_COUNT_KEYS, ROW_COUNTS_NOTE, column_stats

        quality = found.get("quality") or {}
        ranges = [{k: r.get(k) for k in (*RANGE_COUNT_KEYS, "frequency_gaps")}
                  for r in quality.get("requested_ranges") or []]
        return {"session_id": session_id, "dataset": found.get("logical_name"),
                "data_request_id": found.get("data_request_id"), "source_table": found.get("source_table"),
                "rows": quality.get("rows"), "rows_extracted": quality.get("rows"),
                "rows_in_ranges": quality.get("rows_in_ranges"), "row_counts": ROW_COUNTS_NOTE,
                "entities": quality.get("entities"),
                **column_stats(quality, None), "ranges": ranges,
                "duplicate_keys": {k: v for k, v in (quality.get("duplicate_keys") or {}).items() if k != "examples"},
                "empty_entities": quality.get("empty_entities") or [],
                "quality_flags": quality.get("quality_flags") or []}

    def close(self, session_id: str, reason: str = "CLOSED_BY_CALLER") -> dict[str, Any]:
        return self._close_locked(session_id, reason)

    def _close_locked(self, session_id: str, reason: str) -> dict[str, Any]:
        worker = self.workers.pop(session_id, None)
        self.carried_allowed.pop(session_id, None)
        if worker is not None:
            if reason in ABNORMAL_REASONS:
                self._log("session_worker_ended", session_id=session_id, reason=reason,
                          exit_code=worker.process.poll(), worker_log_tail=worker.log_tail())
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
        self._slot_freed()
        return {"session_id": session_id, "status": "CLOSED", "close_reason": reason}

    # ------------------------------------------------------------------ outputs

    def _recorded_angles(self, session_id: str, record: dict[str, Any]) -> dict[str, str]:
        """S13: the research records (research_call_/research_input_<angle>) already stored by a successful execution
        of this epoch, by name. Read from the store, not from the worker's memory, which can be reset."""
        start = int(record.get("epoch_start_seq") or 0)
        ok = {e["execution_id"]: e["seq"] for e in self.store.executions_for(session_id)
              if e["status"] == "OK" and int(e["seq"]) > start}
        return {str(o["name"]): o["output_id"] for o in self.store.outputs_for(session_id)
                if o["execution_id"] in ok and str(o.get("name") or "").startswith(RESEARCH_RECORDS)}

    def _collect(self, session_id: str, execution_id: str, worker: Worker, entries: list[dict[str, Any]],
                 recorded: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Copy each emitted output into the root-only output store (checksum), with its verified metadata. A research
        record of an angle already recorded in this epoch is refused here (S13), so it never reaches the validator as
        a duplicate that would make the angle INVALID."""
        s = self.settings
        drop = self.executor.drop_privileges
        accepted, rejected = [], []
        recorded = dict(recorded or {})
        now = datetime.now(timezone.utc).replace(microsecond=0)
        folder = self.outputs_root / session_id
        folder.mkdir(mode=0o700, exist_ok=True)
        for entry in entries[: s.session_max_outputs]:
            output_name = str(entry.get("name") or "")
            if output_name.startswith(RESEARCH_RECORDS) and output_name in recorded:
                rejected.append({"name": output_name, "reason": "ANGLE_ALREADY_RECORDED",
                                 "message": f"{output_name} is already stored ({recorded[output_name]}); an angle is "
                                            "recorded once and its finding is final. This copy was not kept."})
                continue
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
                      "meta": {**{k: entry.get(k) for k in ("description", "title", "characters") if entry.get(k)},
                               **({"units": units} if (units := _output_units(entry.get("units"), columns)) else {}),
                               **({"definition": defined} if (defined := _output_definition(entry.get("definition")))
                                  is not None else {})},
                      "released": 0, "created_at": now.isoformat(),
                      "expires_at": (now + timedelta(hours=s.result_retention_hours)).isoformat()}
            self.store.insert_output(record)
            if record["name"].startswith(RESEARCH_RECORDS):
                recorded[record["name"]] = output_id
            accepted.append({"output_id": output_id, "name": record["name"], "type": kind, "format": fmt,
                             "columns": columns, "row_count": rows, "byte_count": size,
                             "description": record["meta"].get("description"),
                             **({"definition": record["meta"]["definition"]}
                                if "definition" in record["meta"] else {}),
                             **({"units": record["meta"]["units"]} if record["meta"].get("units") else {})})
        return accepted, rejected

    def read_output(self, session_id: str, request_id: str, output_id: str, offset: int, limit: int,
                    conversation_key: str | None = None) -> dict[str, Any]:
        """An output of this request's session; with conversation reuse also a RELEASED output of an earlier
        request of the same conversation (READ_RELEASED), with the evidence of the completion that released it."""
        output, path, origin = self._readable_output(session_id, request_id, output_id, conversation_key)
        base = {k: output[k] for k in ("output_id", "name", "type", "format", "row_count", "columns", "byte_count",
                                       "checksum_sha256")} | {"released": bool(output["released"]),
                                                              "meta": output.get("meta") or {}}
        if origin is not None:
            base["read_mode"] = "READ_RELEASED"
            base["origin"] = origin
        # P5 (2026-10-02): every table the model reads carries how the backend checked it
        label = carried_tables.label_of(origin or self._release_origin(session_id, output_id)) \
            if output["released"] else "NOT_RELEASED"
        base.update(label=label, label_meaning=carried_tables.LABEL_MEANING.get(label, ""))
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

    def _readable_output(self, session_id: str, request_id: str, output_id: str, conversation_key: str | None
                         ) -> tuple[dict[str, Any], Path, dict[str, Any] | None]:
        """(output row, file path, release origin or None) when the caller may read the output: this request's
        session and epoch, or, with conversation reuse, a RELEASED output of an earlier request of the same
        conversation."""
        record = self.store.get_session(session_id)
        output = self.store.get_output(output_id)
        if record is None or output is None or output["session_id"] != session_id:
            raise SessionError("OUTPUT_NOT_FOUND", "No output with this id exists in this session.", 404)
        origin: dict[str, Any] | None = None
        if record["request_id"] != request_id or self._epoch_of(output) != int(record.get("epoch") or 1):
            # another request's output, or an earlier epoch's: only a released one, only within the conversation
            same_request = record["request_id"] == request_id
            if not (same_request or (self.settings.conversation_reuse and conversation_key
                                     and record.get("conversation_key") == conversation_key)) \
                    or not output["released"]:
                raise SessionError("OUTPUT_NOT_FOUND", "No output with this id exists in this session.", 404)
            origin = self._release_origin(session_id, output_id)
        path = self.outputs_root / output["relative_path"]
        if not path.is_file():
            raise SessionError("OUTPUT_EXPIRED", "The output has expired.", 410)
        return output, path, origin

    def output_file(self, session_id: str, request_id: str, output_id: str, conversation_key: str | None = None
                    ) -> tuple[Path, dict[str, Any]]:
        """R-STORE (round 2026-10-03 C2c): the stored file of a RELEASED output, for the orchestrator to keep it
        beyond this sandbox's retention; the same access rule as read_output."""
        output, path, _ = self._readable_output(session_id, request_id, output_id, conversation_key)
        if not output["released"]:
            raise SessionError("OUTPUT_NOT_RELEASED", "Only a released output can be copied.", 409)
        return path, output

    def restore_output(self, session_id: str, request_id: str, conversation_key: str | None, meta: dict[str, Any],
                       data: bytes) -> dict[str, Any]:
        """R-STORE (round 2026-10-03 C2d): a released table of this conversation that this sandbox no longer holds,
        uploaded back by the orchestrator from its durable store. It is kept as a released output of this session
        under its original output_id (marked restored, with its original label, definition, units and data date), so
        carried() and load_output offer it as before; the checksum and the Parquet file are verified first."""
        record = self.store.get_session(session_id)
        if record is None or record["request_id"] != request_id or record["status"] not in ("ACTIVE", "BUSY"):
            raise SessionError("SESSION_NOT_FOUND", "No open session with this id exists for this request.", 404)
        if not (self.settings.conversation_reuse and conversation_key
                and record.get("conversation_key") == conversation_key):
            raise SessionError("RESTORE_NOT_ALLOWED", "Only a session of the same conversation takes a stored table.",
                               409)
        output_id = str(meta.get("output_id") or "")
        if not OUTPUT_ID_RE.fullmatch(output_id) or str(meta.get("format")) != "PARQUET" \
                or not isinstance(meta.get("name"), str) or not 1 <= len(meta["name"]) <= 80:
            raise SessionError("RESTORE_INVALID", "A stored table needs output_id, name and format PARQUET.", 422)
        if hashlib.sha256(data).hexdigest() != meta.get("checksum_sha256"):
            raise SessionError("RESTORE_CHECKSUM_MISMATCH", "The uploaded file does not match its checksum.", 422)
        existing = self.store.get_output(output_id)
        if existing is not None and (self.outputs_root / existing["relative_path"]).is_file():
            return {"output_id": output_id, "status": "ALREADY_PRESENT"}
        relative = f"restored/{session_id}/{output_id}.parquet"
        path = self.outputs_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.chmod(path, 0o400)
        try:
            import pyarrow.parquet as pq

            parquet = pq.ParquetFile(path)
            columns, rows = parquet.schema_arrow.names, parquet.metadata.num_rows
        except Exception:  # noqa: BLE001 - an unreadable file is refused
            path.unlink(missing_ok=True)
            raise SessionError("RESTORE_INVALID", "The uploaded file is not a readable Parquet table.", 422) from None
        if existing is not None:
            self.store.delete_output(output_id)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        origin = meta.get("origin") if isinstance(meta.get("origin"), dict) else {}
        self.store.insert_output({
            "output_id": output_id, "session_id": session_id,
            "execution_id": str(meta.get("execution_id") or "exe_restored"), "name": meta["name"], "type": "TABLE",
            "format": "PARQUET", "relative_path": relative, "byte_count": len(data), "row_count": rows,
            "columns": columns, "checksum_sha256": meta["checksum_sha256"],
            "meta": {"restored": True, "origin": {**origin, "restored": True},
                     **({"definition": d} if (d := _output_definition(meta.get("definition"))) is not None else {}),
                     **({"units": u} if (u := _output_units(meta.get("units"), columns)) else {}),
                     **({"data_as_of": str(meta["data_as_of"])[:10]} if meta.get("data_as_of") else {})},
            "released": 1, "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=self.settings.result_retention_hours)).isoformat()})
        self._log("carried_restored", request_id=request_id, session_id=session_id, output_id=output_id,
                  rows=rows, bytes=len(data))
        return {"output_id": output_id, "status": "RESTORED", "rows": rows}

    def write_backend_table(self, session_id: str, execution_id: str, name: str, rows: list[dict[str, Any]],
                            columns: tuple[str, ...], *, definition: dict[str, Any] | None = None,
                            units: dict[str, str] | None = None) -> dict[str, Any]:
        """M80 (a): a table the backend made (not the session's code), stored like any output of the session
        (Parquet, checksum, retention) and released with the completion; returns the output record."""
        import hashlib
        import io

        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.Table.from_pylist(rows, schema=None) if rows else pa.table({c: pa.array([], pa.null())
                                                                               for c in columns})
        table = table.select(list(columns))
        buffer = io.BytesIO()
        pq.write_table(table, buffer)
        data = buffer.getvalue()
        output_id = f"out_{secrets.token_hex(12)}"
        relative = f"{session_id}/{output_id}.parquet"
        path = self.outputs_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.chmod(path, 0o400)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        record = {"output_id": output_id, "session_id": session_id, "execution_id": execution_id, "name": name,
                  "type": "TABLE", "format": "PARQUET", "relative_path": relative, "byte_count": len(data),
                  "row_count": table.num_rows, "columns": list(columns),
                  "checksum_sha256": hashlib.sha256(data).hexdigest(),
                  "meta": {"backend": True,
                           **({"definition": d} if (d := _output_definition(definition)) is not None else {}),
                           **({"units": u} if (u := _output_units(units, list(columns))) else {})},
                  "released": 0, "created_at": now.isoformat(),
                  "expires_at": (now + timedelta(hours=self.settings.result_retention_hours)).isoformat()}
        self.store.insert_output(record)
        return record

    def _epoch_of(self, output: dict[str, Any]) -> int:
        execution = self.store.get_execution(output["execution_id"]) or {}
        return int(execution.get("epoch") or 1)

    def _release_origin(self, session_id: str, output_id: str) -> dict[str, Any] | None:
        """The completion that released an output: its id, request, evidence label, warnings and time (the as-of of
        the result). Its label is never raised. A restored table keeps the origin it was stored with."""
        output = self.store.get_output(output_id) or {}
        meta = output.get("meta") if isinstance(output.get("meta"), dict) else {}
        if meta.get("restored"):
            return meta.get("origin") or {"restored": True}
        for completion in reversed(self.store.passed_completions(session_id)):
            final = completion.get("final_status") or {}
            if any(o.get("output_id") == output_id for o in final.get("released_outputs") or []):
                status = final.get("final_status") or {}
                return {"completion_id": completion["completion_id"], "request_id": completion["request_id"],
                        "need_id": completion["need_id"], "completed_at": completion["created_at"],
                        "evidence_label": status.get("evidence_label"), "warnings": status.get("warnings") or [],
                        "calculation_validation": status.get("calculation_validation"),
                        # G2: a table of an event study the backend recomputed and matched
                        "calculation_verified": output_id in (status.get("verified_output_ids") or [])}
        return None

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
