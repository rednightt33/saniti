"""IP2 solution 2 (PY_SANDBOX_AUDIT_STORE_ENABLED): archive DataNeed executions to market-audit-store.

Everything here runs in the root harness, after an execution or a completion, never in an analysis process: the
Audit Store key, the upload URLs and the spool directory (root only, 0700) are out of the analysis user's reach.

Per execution: the exact Python source (PYTHON_SOURCE, byte for byte), a runtime/library manifest (RUNTIME_MANIFEST)
and the execution trace (EXECUTION_TRACE: data access, resample traces, status, bounded error), the execution record
(runtime image with installed distributions, declared imports from the AST, loaded distributions observed in
sys.modules, prebound packages, standard-library and unresolved modules, seed, timezone, input checksums in order,
contract hash) and a link to each raw input Parquet by content (the Governor uploads those bytes). Per completion:
released outputs (OUTPUT), the execution manifest, the validation result, the approved DataNeed contract and the input
bundle manifest; the released output checksums become expectations of the run.

Durable outbox: a separate SQLite file (audit_outbox.sqlite3) plus spooled copies of the bytes, so an Audit Store
outage never loses evidence and never fails an analysis. A background thread drains due items idempotently
(content addresses, execution id, link and event keys); statuses PENDING, FAILED_RETRYABLE (backoff), COMPLETE, and
INCOMPLETE after PY_SANDBOX_AUDIT_MAX_ATTEMPTS or when the spool budget did not fit a file, recorded on the run.
Hidden model reasoning never reaches the sandbox, so none is stored here."""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import shutil
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit_client import AuditClient, AuditRejected, AuditUnavailable

logger = logging.getLogger("market_python_sandbox")

# bound into every session namespace before the code runs (runtime/session_worker.py): listed as prebound, whether
# or not the code used them
PREBOUND_PACKAGES = ("pandas", "numpy", "duckdb", "saniti")
RUNTIME_MODULES = {"saniti", "saniti_session", "session_worker", "confine", "seccomp", "profiler", "expression",
                   "reference", "validator", "__main__"}
MEDIA = {"PARQUET": "application/vnd.apache.parquet", "CSV": "text/csv", "PNG": "image/png",
         "JSON": "application/json", "TEXT": "text/plain", "BIN": "application/octet-stream"}
TRACE_LIMIT = 200_000
SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    request_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    files TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS items_due ON items (status, next_attempt_at);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str, separators=(",", ":")))


# ---------------------------------------------------------------------------------------- library evidence

def runtime_inventory(requirement_files: list[Path]) -> dict[str, Any]:
    """The installed runtime (importlib.metadata; pip is removed from the image): Python, OS, architecture, every
    installed distribution and version, and the sha256 of the locked requirement files."""
    seen: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        name = (dist.metadata.get("Name") or "").strip()
        if name and name.lower() not in {n.lower() for n in seen}:
            seen[name] = dist.version
    hasher = hashlib.sha256()
    present = [p for p in sorted(requirement_files) if p.is_file()]
    for path in present:
        hasher.update(path.name.encode() + b"\0" + path.read_bytes())
    return {"python_version": platform.python_version(), "python_implementation": platform.python_implementation(),
            "os": platform.platform()[:200], "arch": platform.machine() or "unknown",
            "requirements_sha256": hasher.hexdigest() if present else None,
            "distributions": [{"name": n, "version": v} for n, v in sorted(seen.items(), key=lambda i: i[0].lower())]}


def declared_imports(code: str) -> list[str]:
    """Module names the source imports, from its AST (the code is parsed, never run, here)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
    return sorted(names)


_DISTRIBUTIONS: dict[str, list[str]] | None = None


def classify_modules(modules: list[str]) -> dict[str, list[Any]]:
    """Top-level modules first imported by an execution, as observed in sys.modules: mapped to installed
    distributions (packages_distributions), the standard library, or unresolved. Runtime helper modules are left
    out; prebound packages are recorded separately and were imported before the code ran."""
    global _DISTRIBUTIONS
    if _DISTRIBUTIONS is None:
        _DISTRIBUTIONS = importlib.metadata.packages_distributions()
    tops = sorted({m.split(".")[0] for m in modules if m and not m.startswith("_")} - RUNTIME_MODULES)
    loaded: dict[str, str] = {}
    stdlib, unresolved = [], []
    for top in tops:
        if top in sys.stdlib_module_names:
            stdlib.append(top)
        elif top in _DISTRIBUTIONS:
            for name in _DISTRIBUTIONS[top]:
                try:
                    loaded[name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    unresolved.append(top)
        else:
            unresolved.append(top)
    return {"loaded_distributions": [{"name": n, "version": v} for n, v in sorted(loaded.items())],
            "stdlib_modules": stdlib, "unresolved_modules": sorted(set(unresolved))}


# ---------------------------------------------------------------------------------------- outbox

class AuditOutbox:
    def __init__(self, settings: Any, client: AuditClient | None = None) -> None:
        self.settings = settings
        data = Path(settings.data_dir)
        self.spool = data / "audit-spool"
        self.spool.mkdir(parents=True, exist_ok=True)
        os.chmod(self.spool, 0o700)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(data / "audit_outbox.sqlite3"), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        os.chmod(data / "audit_outbox.sqlite3", 0o600)
        self.client = client or AuditClient(settings.audit_store_url or "", settings.audit_store_key or "",
                                            settings.audit_timeout_seconds)
        app_root = Path(__file__).resolve().parents[1]
        self.runtime = runtime_inventory([app_root / "requirements.txt", app_root / "requirements-analysis.txt"])
        self.deployment = {"git_commit": os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
                           "deployment_id": os.environ.get("RAILWAY_DEPLOYMENT_ID")}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ producers (harness, after the fact)

    def _spool_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.spool.rglob("*") if p.is_file())

    def enqueue(self, kind: str, key: str, request_id: str, payload: dict[str, Any],
                files: list[dict[str, Any]]) -> None:
        """Never raises: an audit problem is logged, the analysis goes on."""
        try:
            with self._lock:
                if self._db.execute("SELECT 1 FROM items WHERE idempotency_key = ?", (key,)).fetchone():
                    return
                folder = self.spool / hashlib.sha256(key.encode()).hexdigest()[:32]
                folder.mkdir(mode=0o700, exist_ok=True)
                budget = self.settings.audit_spool_max_bytes - self._spool_bytes()
                stored, omitted = [], []
                for index, item in enumerate(files):
                    data: bytes = item.pop("data")
                    if len(data) > budget:
                        omitted.append({**item, "size_bytes": len(data), "reason": "SPOOL_FULL"})
                        continue
                    path = folder / f"{index:03d}"
                    path.write_bytes(data)
                    budget -= len(data)
                    stored.append({**item, "path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                                   "size_bytes": len(data)})
                payload = {**payload, "omitted": omitted}
                self._db.execute("""INSERT INTO items (idempotency_key, kind, request_id, payload, files, created_at)
                                    VALUES (?, ?, ?, ?, ?, ?)""",
                                 (key, kind, request_id, json.dumps(payload, default=str), json.dumps(stored),
                                  utc_now()))
            _log("sandbox_audit_enqueued", kind=kind, request_id=request_id, key=key, files=len(stored),
                 omitted=len(omitted))
        except Exception as exc:  # noqa: BLE001 - audit never fails an analysis while it is optional
            _log("sandbox_audit_enqueue_failed", kind=kind, request_id=request_id, error=type(exc).__name__)

    def record_execution(self, *, request_id: str, session: dict[str, Any], execution_id: str, seq: int,
                         code: str, answer: dict[str, Any], status: str, started_at: str, finished_at: str,
                         runtime_ms: int, cpu_seconds: float, inputs: list[dict[str, Any]],
                         contract_sha256: str | None) -> None:
        libraries = classify_modules(answer.get("modules") or [])
        access = answer.get("access") or []
        resample = [a for a in access if a.get("call") == "resample"]
        source = code.encode("utf-8")
        record = {
            "execution_id": execution_id, "request_id": request_id, "session_id": session["session_id"],
            "bundle_id": session.get("bundle_id"), "seq": seq, "status": status,
            "source_sha256": hashlib.sha256(source).hexdigest(), "runtime": self.runtime,
            **{k: v for k, v in self.deployment.items() if v}, "random_seed": self.settings.random_seed,
            "timezone": "UTC", "declared_imports": declared_imports(code), **libraries,
            "prebound_packages": list(PREBOUND_PACKAGES),
            "input_checksums": [{k: i.get(k) for k in ("position", "data_request_id", "dataset_id", "sha256",
                                                        "size_bytes", "ordering")} for i in inputs],
            "contract_sha256": contract_sha256,
            "resample": [{k: r.get(k) for k in ("data_request_id", "source_frequency", "target_frequency",
                                                "semantics_version", "rules_sha256", "input_rows", "rows",
                                                "periods", "incomplete_periods")} for r in resample][:100],
            "resource_usage": {"runtime_ms": runtime_ms, "cpu_seconds": cpu_seconds},
            "started_at": started_at, "finished_at": finished_at}
        manifest = {"schema": "saniti.audit.runtime_manifest/v1", "execution_id": execution_id,
                    "runtime": self.runtime, "declared_imports": record["declared_imports"], **libraries,
                    "prebound_packages": list(PREBOUND_PACKAGES), "random_seed": record["random_seed"],
                    "timezone": "UTC (process); trading dates are Asia/Jakarta calendar dates",
                    **self.deployment,
                    "evidence_note": "loaded_distributions were observed in sys.modules after this execution and "
                                     "not before it; prebound packages are available to every execution; "
                                     "declared_imports come from the source's AST."}
        trace = {"schema": "saniti.audit.execution_trace/v1", "execution_id": execution_id, "status": status,
                 "access": access, "resample": resample, "warnings": answer.get("warnings") or [],
                 "error": answer.get("error") or answer.get("insufficient"),
                 "outputs": [o.get("name") for o in answer.get("outputs") or []]}
        trace_bytes = json.dumps(trace, default=str, sort_keys=True).encode()[:TRACE_LIMIT]
        files = [{"role": "PYTHON_SOURCE", "media_type": "text/x-python", "execution_id": execution_id,
                  "data": source},
                 {"role": "RUNTIME_MANIFEST", "media_type": "application/json", "execution_id": execution_id,
                  "data": json.dumps(manifest, default=str, sort_keys=True).encode()},
                 {"role": "EXECUTION_TRACE", "media_type": "application/json", "execution_id": execution_id,
                  "data": trace_bytes}]
        if status != "OK" and trace["error"]:
            files.append({"role": "ERROR_DETAIL", "media_type": "application/json", "execution_id": execution_id,
                          "data": json.dumps(trace["error"], default=str, sort_keys=True).encode()[:20_000]})
        self.enqueue("EXECUTION", f"execution:{execution_id}", request_id, {"execution": record, "inputs": inputs},
                     files)

    def record_completion(self, *, request_id: str, result: dict[str, Any], execution_manifest: dict[str, Any],
                          need: dict[str, Any] | None, bundle: dict[str, Any],
                          released: list[dict[str, Any]]) -> None:
        completion_id = result["completion_id"]
        files = [{"role": "EXECUTION_MANIFEST", "media_type": "application/json", "label": completion_id,
                  "data": json.dumps(execution_manifest, default=str, sort_keys=True).encode()},
                 {"role": "VALIDATION_RESULT", "media_type": "application/json", "label": completion_id,
                  "data": json.dumps({k: result.get(k) for k in ("status", "final_status", "coverage",
                                                                 "released_outputs", "execution_manifest_sha256")},
                                     default=str, sort_keys=True).encode()},
                 {"role": "INPUT_BUNDLE_MANIFEST", "media_type": "application/json",
                  "label": bundle.get("input_bundle_id"),
                  "data": json.dumps(bundle, default=str, sort_keys=True).encode()}]
        if need is not None:
            files.append({"role": "APPROVED_DATANEED_CONTRACT", "media_type": "application/json",
                          "label": need.get("need_id"), "data": json.dumps(need, default=str,
                                                                           sort_keys=True).encode()})
        outputs = []
        for output in released:
            data = Path(output["path"]).read_bytes()
            files.append({"role": "OUTPUT", "media_type": MEDIA.get(output["format"], "application/octet-stream"),
                          "execution_id": output.get("execution_id"), "label": output["name"][:200], "data": data})
            outputs.append(hashlib.sha256(data).hexdigest())
        self.enqueue("COMPLETION", f"completion:{completion_id}", request_id,
                     {"completion_id": completion_id, "status": result.get("status"), "output_sha256": outputs},
                     files)

    # ------------------------------------------------------------------ drain

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="sandbox-audit", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.drain()
            self._stop.wait(self.settings.audit_poll_seconds)

    def drain(self) -> dict[str, int]:
        counts = {"complete": 0, "retry": 0, "incomplete": 0}
        while True:
            with self._lock:
                row = self._db.execute("""SELECT * FROM items WHERE status IN ('PENDING', 'FAILED_RETRYABLE')
                                          AND next_attempt_at <= ? ORDER BY item_id LIMIT 1""",
                                       (time.time(),)).fetchone()
            if row is None:
                return counts
            counts[self._process(dict(row))] += 1

    def status(self) -> dict[str, int]:
        with self._lock:
            return {r["status"]: r["n"] for r in self._db.execute(
                "SELECT status, count(*) AS n FROM items GROUP BY status").fetchall()}

    def _process(self, item: dict[str, Any]) -> str:
        payload, files = json.loads(item["payload"]), json.loads(item["files"])
        attempts = int(item["attempts"]) + 1
        try:
            run_id = self.client.register_run(item["request_id"])
            links = []
            for entry in files:
                artifact = self.client.store_artifact(Path(entry["path"]).read_bytes(), entry["media_type"])
                links.append({k: v for k, v in (("artifact_id", artifact), ("role", entry["role"]),
                                                ("execution_id", entry.get("execution_id")),
                                                ("label", entry.get("label"))) if v})
            if item["kind"] == "EXECUTION":
                record = payload["execution"]
                for entry in payload.get("inputs") or []:
                    if entry.get("sha256") and entry.get("size_bytes") is not None:
                        artifact = self.client.reference_artifact(entry["sha256"], entry["size_bytes"],
                                                                  "application/vnd.apache.parquet")
                        links.append({k: v for k, v in (("artifact_id", artifact), ("role", "RAW_INPUT_PARQUET"),
                                                        ("label", entry.get("dataset_id"))) if v})
                self.client.register_execution(record)
                event = {"idempotency_key": item["idempotency_key"], "event_type": "execution.recorded",
                         "occurred_at": record.get("finished_at") or utc_now(), "execution_id": record["execution_id"],
                         "payload": {"status": record["status"], "seq": record["seq"],
                                     "source_sha256": record["source_sha256"], "resample": record["resample"][:20],
                                     "omitted": payload.get("omitted") or []}}
            else:
                self.client.expect(run_id, {"output_sha256": payload["output_sha256"]})
                event = {"idempotency_key": item["idempotency_key"], "event_type": "completion.archived",
                         "occurred_at": utc_now(),
                         "payload": {"completion_id": payload["completion_id"], "status": payload["status"],
                                     "outputs": len(payload["output_sha256"]),
                                     "omitted": payload.get("omitted") or []}}
            if links:
                self.client.link(run_id, links)
            self.client.append_events(run_id, [event])
            final = "INCOMPLETE" if payload.get("omitted") else "COMPLETE"
            self._finish(item, final, attempts, None)
            return "incomplete" if final == "INCOMPLETE" else "complete"
        except (AuditUnavailable, OSError, TimeoutError) as exc:
            if attempts >= self.settings.audit_max_attempts:
                self._finish(item, "INCOMPLETE", attempts, f"{type(exc).__name__}: {exc}")
                return "incomplete"
            with self._lock:
                self._db.execute("""UPDATE items SET status = 'FAILED_RETRYABLE', attempts = ?, last_error = ?,
                                    next_attempt_at = ? WHERE item_id = ?""",
                                 (attempts, f"{type(exc).__name__}: {exc}"[:500],
                                  time.time() + min(3600, 15 * 2 ** attempts), item["item_id"]))
            _log("sandbox_audit_retry", key=item["idempotency_key"], attempts=attempts, status="FAILED_RETRYABLE",
                 error=type(exc).__name__)
            return "retry"
        except (AuditRejected, ValueError, KeyError) as exc:
            self._finish(item, "INCOMPLETE", attempts, f"{type(exc).__name__}: {exc}")
            return "incomplete"

    def _finish(self, item: dict[str, Any], status: str, attempts: int, error: str | None) -> None:
        with self._lock:
            self._db.execute("""UPDATE items SET status = ?, attempts = ?, last_error = ?, completed_at = ?
                                WHERE item_id = ?""", (status, attempts, (error or "")[:500] or None, utc_now(),
                                                       item["item_id"]))
        for entry in json.loads(item["files"]):
            shutil.rmtree(Path(entry["path"]).parent, ignore_errors=True)
            break
        _log("sandbox_audit_" + ("archived" if status == "COMPLETE" else "incomplete"),
             key=item["idempotency_key"], status=status, attempts=attempts, error=error)
