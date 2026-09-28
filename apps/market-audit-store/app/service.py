"""Audit Store operations on schema ai_audit. Every producer operation is idempotent on its source identity:
request_id (run), (run, source, idempotency_key) (event), sha256 (artifact), (run, artifact, role, execution, label)
(link), execution_id (execution), runtime fingerprint (runtime image). Retries never duplicate rows.

Run state: OPEN until market-ai-orc's RUN_FINISHED (or a producer's final expectations) asks for finalization;
FINALIZING while evaluated; COMPLETE only when every expected artifact is READY (verified by this service), else
INCOMPLETE with the missing items, re-evaluated whenever a late artifact, link or execution arrives. Completion is
never reported while a required artifact is missing."""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .config import Settings
from .models import (ArtifactPrepare, EventIn, ExecutionRecord, LinkIn, RunRegistration, forbidden_key)
from .storage import ObjectStore, object_key, staging_key

logger = logging.getLogger("market_audit_store")

EXPECTATION_KEYS = ("roles", "execution_ids", "completion_ids", "input_sha256", "output_sha256", "dataset_ids")
PREBOUND_NOTE = ("prebound_packages are bound into every session namespace before the code runs; they are listed "
                 "whether or not the code used them. loaded_distributions are the distributions whose modules were "
                 "observed in sys.modules after the execution and not before it; declared_imports come from the "
                 "source's AST.")
DETERMINISM_NOTE = ("The Python computation can be replayed deterministically when every raw input, the exact source, "
                    "the runtime image (same Python and package versions), the random seed, the timezone, the input "
                    "ordering and the resample semantics version are present. The model's own output (which code it "
                    "wrote, what it answered) comes from a provider and may not be reproducible.")


class AuditError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def log_event(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str, separators=(",", ":")))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode()


def runtime_fingerprint(runtime: dict[str, Any]) -> str:
    body = {**runtime, "distributions": sorted(({"name": d["name"].lower(), "version": d["version"]}
                                                for d in runtime.get("distributions") or []),
                                               key=lambda d: (d["name"], d["version"]))}
    return "rt_" + hashlib.sha256(canonical(body)).hexdigest()


class AuditService:
    def __init__(self, settings: Settings, store: ObjectStore) -> None:
        self.settings = settings
        self.store = store

    # ------------------------------------------------------------------ plumbing

    @contextmanager
    def tx(self) -> Iterator[psycopg.Connection]:
        s = self.settings
        with psycopg.connect(s.database_url, connect_timeout=s.connect_timeout_seconds, row_factory=dict_row,
                             options=f"-c statement_timeout={s.statement_timeout_seconds * 1000} "
                                     f"-c lock_timeout=5000 -c TimeZone=UTC") as connection:
            with connection.transaction():
                yield connection

    def ping(self) -> None:
        with self.tx() as c:
            c.execute("SELECT 1 FROM ai_audit.run LIMIT 1")
        self.store.ping()

    def _expiry(self, retention_class: str) -> datetime:
        days = (self.settings.retention_pinned_days if retention_class == "PINNED"
                else self.settings.retention_standard_days)
        return utc_now() + timedelta(days=days)

    @staticmethod
    def _run(c: psycopg.Connection, run_id: str, lock: bool = False) -> dict[str, Any]:
        row = c.execute("SELECT * FROM ai_audit.run WHERE run_id = %s" + (" FOR UPDATE" if lock else ""),
                        (run_id,)).fetchone()
        if row is None:
            raise AuditError("RUN_NOT_FOUND", "No run with this run_id.", 404)
        return row

    # ------------------------------------------------------------------ runs

    def register_run(self, source: str, reg: RunRegistration, *, model: str | None = None,
                     provider: str | None = None, deployment: dict[str, Any] | None = None,
                     summary: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.tx() as c:
            return self._ensure_run(c, source, reg, model=model, provider=provider, deployment=deployment,
                                    summary=summary)

    def _ensure_run(self, c: psycopg.Connection, source: str, reg: RunRegistration, *, model: str | None = None,
                    provider: str | None = None, deployment: dict[str, Any] | None = None,
                    summary: dict[str, Any] | None = None) -> dict[str, Any]:
        parent = None
        if reg.parent_request_id:
            found = c.execute("SELECT run_id FROM ai_audit.run WHERE request_id = %s",
                              (reg.parent_request_id,)).fetchone()
            parent = found["run_id"] if found else None
        row = c.execute(
            """INSERT INTO ai_audit.run (run_id, request_id, conversation_id, turn_index, parent_run_id, expires_at,
                                         model, provider, deployment, summary)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (request_id) DO UPDATE SET
                   conversation_id = COALESCE(ai_audit.run.conversation_id, EXCLUDED.conversation_id),
                   turn_index = COALESCE(ai_audit.run.turn_index, EXCLUDED.turn_index),
                   parent_run_id = COALESCE(ai_audit.run.parent_run_id, EXCLUDED.parent_run_id),
                   model = COALESCE(EXCLUDED.model, ai_audit.run.model),
                   provider = COALESCE(EXCLUDED.provider, ai_audit.run.provider),
                   deployment = ai_audit.run.deployment || EXCLUDED.deployment,
                   summary = ai_audit.run.summary || EXCLUDED.summary,
                   updated_at = CURRENT_TIMESTAMP
               RETURNING run_id, request_id, status""",
            (f"run_{secrets.token_hex(16)}", reg.request_id, reg.conversation_id, reg.turn_index, parent,
             self._expiry("STANDARD"), model, provider,
             Jsonb({source: deployment} if deployment else {}), Jsonb(summary or {}))).fetchone()
        return row

    def run_by_request(self, request_id: str) -> dict[str, Any]:
        with self.tx() as c:
            row = c.execute("SELECT run_id FROM ai_audit.run WHERE request_id = %s", (request_id,)).fetchone()
        if row is None:
            raise AuditError("RUN_NOT_FOUND", "No run with this request_id.", 404)
        return self.run_view(row["run_id"])

    def run_view(self, run_id: str) -> dict[str, Any]:
        with self.tx() as c:
            run = self._run(c, run_id)
            counts = c.execute(
                """SELECT (SELECT count(*) FROM ai_audit.event WHERE run_id = %(r)s) AS events,
                          (SELECT count(*) FROM ai_audit.run_artifact WHERE run_id = %(r)s) AS artifacts,
                          (SELECT count(*) FROM ai_audit.execution WHERE run_id = %(r)s) AS executions,
                          (SELECT count(*) FROM ai_audit.retention_hold
                           WHERE run_id = %(r)s AND released_at IS NULL) AS active_holds""",
                {"r": run_id}).fetchone()
            parent = None
            if run["parent_run_id"]:
                parent = run["parent_run_id"]
        return {"run_id": run["run_id"], "request_id": run["request_id"], "conversation_id": run["conversation_id"],
                "turn_index": run["turn_index"], "parent_run_id": parent, "status": run["status"],
                "retention_class": run["retention_class"], "expires_at": run["expires_at"], "model": run["model"],
                "provider": run["provider"], "deployment": run["deployment"], "summary": run["summary"],
                "expected": run["expected"], "missing": run["missing"], "created_at": run["created_at"],
                "updated_at": run["updated_at"], "finalized_at": run["finalized_at"], "counts": counts}

    def conversation_runs(self, conversation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.tx() as c:
            return c.execute(
                """SELECT run_id, request_id, turn_index, parent_run_id, status, model, created_at, finalized_at,
                          summary->>'response_type' AS response_type, summary->>'status' AS run_status
                   FROM ai_audit.run WHERE conversation_id = %s ORDER BY created_at, turn_index NULLS LAST LIMIT %s""",
                (conversation_id, limit)).fetchall()

    # ------------------------------------------------------------------ events

    def append_events(self, source: str, run_id: str, events: list[EventIn]) -> list[dict[str, Any]]:
        if len(events) > self.settings.max_events_per_call:
            raise AuditError("TOO_MANY_EVENTS", f"At most {self.settings.max_events_per_call} events per call.", 413)
        with self.tx() as c:
            run = self._run(c, run_id, lock=True)
            acks = self._append(c, run, source, [e.model_dump() for e in events])
        self.reevaluate(run_id)
        return acks

    @staticmethod
    def _append(c: psycopg.Connection, run: dict[str, Any], source: str,
                events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Append in the given order under the run's row lock; a known (source, idempotency_key) keeps its seq."""
        run_id, seq, acks = run["run_id"], int(run["next_event_seq"]), []
        for event in events:
            known = c.execute("SELECT seq FROM ai_audit.event WHERE run_id = %s AND source = %s AND "
                              "idempotency_key = %s", (run_id, source, event["idempotency_key"])).fetchone()
            if known:
                acks.append({"idempotency_key": event["idempotency_key"], "seq": known["seq"], "duplicate": True})
                continue
            try:
                c.execute("""INSERT INTO ai_audit.event (run_id, seq, source, idempotency_key, event_type, occurred_at,
                                                        execution_id, artifact_id, payload)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                          (run_id, seq, source, event["idempotency_key"], event["event_type"], event["occurred_at"],
                           event.get("execution_id"), event.get("artifact_id"), Jsonb(event.get("payload") or {})))
            except psycopg.errors.ForeignKeyViolation as exc:
                raise AuditError("ARTIFACT_NOT_FOUND", "An event references an unknown artifact_id.", 409) from exc
            acks.append({"idempotency_key": event["idempotency_key"], "seq": seq, "duplicate": False})
            seq += 1
        c.execute("UPDATE ai_audit.run SET next_event_seq = %s, updated_at = CURRENT_TIMESTAMP WHERE run_id = %s",
                  (seq, run_id))
        return acks

    def events(self, run_id: str, after_seq: int = 0, limit: int = 200) -> dict[str, Any]:
        with self.tx() as c:
            self._run(c, run_id)
            rows = c.execute("""SELECT seq, source, event_type, occurred_at, recorded_at, execution_id, artifact_id,
                                       payload
                                FROM ai_audit.event WHERE run_id = %s AND seq > %s ORDER BY seq LIMIT %s""",
                             (run_id, after_seq, limit)).fetchall()
        return {"run_id": run_id, "events": rows, "next_after_seq": rows[-1]["seq"] if len(rows) == limit else None}

    # ------------------------------------------------------------------ artifacts

    def prepare_artifact(self, source: str, prep: ArtifactPrepare) -> dict[str, Any]:
        if prep.size_bytes > self.settings.max_artifact_bytes:
            raise AuditError("ARTIFACT_TOO_LARGE", f"size_bytes exceeds {self.settings.max_artifact_bytes}.", 413)
        with self.tx() as c:
            row = c.execute("SELECT * FROM ai_audit.artifact WHERE sha256 = %s FOR UPDATE", (prep.sha256,)).fetchone()
            if row is None:
                artifact_id = f"art_{secrets.token_hex(16)}"
                c.execute("""INSERT INTO ai_audit.artifact (artifact_id, sha256, size_bytes, media_type, object_key,
                                                            first_source)
                             VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (sha256) DO NOTHING""",
                          (artifact_id, prep.sha256, prep.size_bytes, prep.media_type, object_key(prep.sha256),
                           source))
                row = c.execute("SELECT * FROM ai_audit.artifact WHERE sha256 = %s FOR UPDATE",
                                (prep.sha256,)).fetchone()
            if int(row["size_bytes"]) != prep.size_bytes:
                raise AuditError("ARTIFACT_SIZE_CONFLICT", "This sha256 is registered with a different size_bytes; "
                                 "the content or its claimed size is wrong.", 409)
            if row["state"] == "READY":
                return {"artifact_id": row["artifact_id"], "state": "READY", "deduplicated": True, "upload": None}
            if row["state"] in ("REJECTED", "DELETED"):
                c.execute("UPDATE ai_audit.artifact SET state = 'PENDING', deleted_at = NULL WHERE artifact_id = %s",
                          (row["artifact_id"],))
            if not prep.upload:
                return {"artifact_id": row["artifact_id"], "state": "PENDING", "deduplicated": False, "upload": None}
            staged = staging_key(row["artifact_id"])
            expires = utc_now() + timedelta(seconds=self.settings.upload_url_ttl_seconds)
            c.execute("UPDATE ai_audit.artifact SET staging_key = %s, upload_expires_at = %s WHERE artifact_id = %s",
                      (staged, expires, row["artifact_id"]))
        url, headers = self.store.presigned_put(staged, row["media_type"], self.settings.upload_url_ttl_seconds)
        return {"artifact_id": row["artifact_id"], "state": "PENDING", "deduplicated": False,
                "upload": {"method": "PUT", "url": url, "headers": headers, "expires_at": expires}}

    def verify_artifact(self, artifact_id: str) -> dict[str, Any]:
        """Hash the staged upload here (never trusting the producer), then promote it to its content address."""
        with self.tx() as c:
            row = c.execute("SELECT * FROM ai_audit.artifact WHERE artifact_id = %s", (artifact_id,)).fetchone()
        if row is None:
            raise AuditError("ARTIFACT_NOT_FOUND", "No artifact with this artifact_id.", 404)
        if row["state"] == "READY":
            return {"artifact_id": artifact_id, "state": "READY", "rejected_reason": None}
        if row["state"] != "PENDING" or not row["staging_key"]:
            raise AuditError("UPLOAD_NOT_PREPARED", "Prepare the artifact with upload true before verifying.", 409)
        staged = row["staging_key"]
        digest = self.store.digest(staged)
        with self.tx() as c:
            current = c.execute("SELECT * FROM ai_audit.artifact WHERE artifact_id = %s FOR UPDATE",
                                (artifact_id,)).fetchone()
            if current["state"] == "READY":
                return {"artifact_id": artifact_id, "state": "READY", "rejected_reason": None}
            if current["staging_key"] != staged:
                raise AuditError("UPLOAD_SUPERSEDED", "A newer upload was prepared; verify again.", 409)
            if digest is None:
                c.execute("UPDATE ai_audit.artifact SET verify_attempts = verify_attempts + 1 WHERE artifact_id = %s",
                          (artifact_id,))
                raise AuditError("UPLOAD_MISSING", "Nothing was uploaded to the prepared URL yet.", 409)
            sha, size = digest
            reason = None if (sha, size) == (row["sha256"], int(row["size_bytes"])) else (
                "SIZE_MISMATCH" if size != int(row["size_bytes"]) else "CHECKSUM_MISMATCH")
            if reason is None:
                self.store.promote(staged, row["object_key"])
                c.execute("""UPDATE ai_audit.artifact SET state = 'READY', verified_at = CURRENT_TIMESTAMP,
                                    staging_key = NULL, upload_expires_at = NULL, rejected_reason = NULL,
                                    verify_attempts = verify_attempts + 1
                             WHERE artifact_id = %s""", (artifact_id,))
            else:
                c.execute("""UPDATE ai_audit.artifact SET state = 'REJECTED', rejected_reason = %s, staging_key = NULL,
                                    upload_expires_at = NULL, verify_attempts = verify_attempts + 1
                             WHERE artifact_id = %s""", (reason, artifact_id))
        self.store.delete(staged)
        log_event("audit_artifact_verified", artifact_id=artifact_id, state="READY" if reason is None else "REJECTED",
                  reason=reason, size_bytes=size)
        if reason is None:
            self._reevaluate_artifact_runs(artifact_id)
        return {"artifact_id": artifact_id, "state": "READY" if reason is None else "REJECTED",
                "rejected_reason": reason}

    def store_own(self, payload: bytes, media_type: str) -> str:
        """An artifact this service writes itself (for example market-ai-orc's final response): hashed here, written
        to its content address and READY at once. Returns the artifact_id."""
        sha, size = hashlib.sha256(payload).hexdigest(), len(payload)
        with self.tx() as c:
            c.execute("""INSERT INTO ai_audit.artifact (artifact_id, sha256, size_bytes, media_type, object_key,
                                                        first_source)
                         VALUES (%s, %s, %s, %s, %s, 'market-audit-store') ON CONFLICT (sha256) DO NOTHING""",
                      (f"art_{secrets.token_hex(16)}", sha, size, media_type, object_key(sha)))
            row = c.execute("SELECT * FROM ai_audit.artifact WHERE sha256 = %s FOR UPDATE", (sha,)).fetchone()
            if row["state"] == "READY":
                return row["artifact_id"]
            self.store.put(row["object_key"], payload, media_type)
            c.execute("""UPDATE ai_audit.artifact SET state = 'READY', verified_at = CURRENT_TIMESTAMP,
                                deleted_at = NULL, staging_key = NULL, upload_expires_at = NULL
                         WHERE artifact_id = %s""", (row["artifact_id"],))
            return row["artifact_id"]

    def link(self, source: str, run_id: str, links: list[LinkIn]) -> dict[str, Any]:
        linked = 0
        with self.tx() as c:
            self._run(c, run_id)
            for link in links:
                try:
                    inserted = c.execute(
                        """INSERT INTO ai_audit.run_artifact (run_id, artifact_id, role, source, execution_id, label)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON CONFLICT (run_id, artifact_id, role, COALESCE(execution_id, ''), COALESCE(label, ''))
                           DO NOTHING RETURNING run_artifact_id""",
                        (run_id, link.artifact_id, link.role, source, link.execution_id, link.label)).fetchone()
                except psycopg.errors.ForeignKeyViolation as exc:
                    raise AuditError("ARTIFACT_NOT_FOUND", f"Unknown artifact_id {link.artifact_id}.", 409) from exc
                linked += int(inserted is not None)
        self.reevaluate(run_id)
        return {"run_id": run_id, "linked": linked, "duplicates": len(links) - linked}

    def run_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self.tx() as c:
            self._run(c, run_id)
            return c.execute(
                """SELECT l.artifact_id, l.role, l.source, l.execution_id, l.label, l.linked_at, a.sha256,
                          a.size_bytes, a.media_type, a.state, a.verified_at
                   FROM ai_audit.run_artifact l JOIN ai_audit.artifact a USING (artifact_id)
                   WHERE l.run_id = %s ORDER BY l.run_artifact_id""", (run_id,)).fetchall()

    # ------------------------------------------------------------------ executions

    def register_execution(self, source: str, record: ExecutionRecord) -> dict[str, Any]:
        with self.tx() as c:
            run = self._ensure_run(c, source, RunRegistration(request_id=record.request_id))
            runtime_id = None
            if record.runtime is not None:
                runtime = record.runtime.model_dump()
                runtime_id = runtime_fingerprint(runtime)
                c.execute("""INSERT INTO ai_audit.runtime_image (runtime_image_id, python_version,
                                    python_implementation, os, arch, requirements_sha256, distributions,
                                    distribution_count)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (runtime_image_id) DO NOTHING""",
                          (runtime_id, runtime["python_version"], runtime["python_implementation"], runtime["os"],
                           runtime["arch"], runtime["requirements_sha256"],
                           Jsonb(sorted(runtime["distributions"], key=lambda d: d["name"].lower())),
                           len(runtime["distributions"])))
            inserted = c.execute(
                """INSERT INTO ai_audit.execution (execution_id, run_id, session_id, bundle_id, seq, status,
                          source_sha256, runtime_image_id, git_commit, deployment_id, random_seed, timezone,
                          declared_imports, loaded_distributions, prebound_packages, stdlib_modules,
                          unresolved_modules, input_checksums, contract_sha256, resample, resource_usage, started_at,
                          finished_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (execution_id) DO NOTHING RETURNING execution_id""",
                (record.execution_id, run["run_id"], record.session_id, record.bundle_id, record.seq, record.status,
                 record.source_sha256, runtime_id, record.git_commit, record.deployment_id, record.random_seed,
                 record.timezone, Jsonb(sorted(set(record.declared_imports))),
                 Jsonb([d.model_dump() for d in record.loaded_distributions]),
                 Jsonb(sorted(set(record.prebound_packages))), Jsonb(sorted(set(record.stdlib_modules))),
                 Jsonb(sorted(set(record.unresolved_modules))),
                 Jsonb([i.model_dump() for i in sorted(record.input_checksums, key=lambda i: i.position)]),
                 record.contract_sha256, Jsonb(record.resample), Jsonb(record.resource_usage), record.started_at,
                 record.finished_at)).fetchone()
            existing = c.execute("SELECT run_id, runtime_image_id FROM ai_audit.execution WHERE execution_id = %s",
                                 (record.execution_id,)).fetchone()
        if existing["run_id"] != run["run_id"]:
            raise AuditError("EXECUTION_CONFLICT", "This execution_id belongs to another run.", 409)
        self.reevaluate(run["run_id"])
        return {"execution_id": record.execution_id, "run_id": run["run_id"],
                "runtime_image_id": existing["runtime_image_id"], "duplicate": inserted is None}

    def execution_runtime(self, execution_id: str) -> dict[str, Any]:
        with self.tx() as c:
            row = c.execute(
                """SELECT e.*, r.request_id, i.python_version, i.python_implementation, i.os, i.arch,
                          i.requirements_sha256, i.distributions, i.distribution_count
                   FROM ai_audit.execution e JOIN ai_audit.run r USING (run_id)
                   LEFT JOIN ai_audit.runtime_image i USING (runtime_image_id)
                   WHERE e.execution_id = %s""", (execution_id,)).fetchone()
        if row is None:
            raise AuditError("EXECUTION_NOT_FOUND", "No execution with this execution_id.", 404)
        return {
            "execution_id": row["execution_id"], "run_id": row["run_id"], "request_id": row["request_id"],
            "session_id": row["session_id"], "bundle_id": row["bundle_id"], "seq": row["seq"],
            "status": row["status"], "source_sha256": row["source_sha256"], "git_commit": row["git_commit"],
            "deployment_id": row["deployment_id"], "random_seed": row["random_seed"], "timezone": row["timezone"],
            "runtime": None if row["runtime_image_id"] is None else {
                "runtime_image_id": row["runtime_image_id"], "python_version": row["python_version"],
                "python_implementation": row["python_implementation"], "os": row["os"], "arch": row["arch"],
                "requirements_sha256": row["requirements_sha256"], "distribution_count": row["distribution_count"],
                "distributions": row["distributions"]},
            "libraries": {"declared_imports": row["declared_imports"],
                          "loaded_distributions": row["loaded_distributions"],
                          "prebound_packages": row["prebound_packages"], "stdlib_modules": row["stdlib_modules"],
                          "unresolved_modules": row["unresolved_modules"], "evidence_note": PREBOUND_NOTE},
            "input_checksums": row["input_checksums"], "contract_sha256": row["contract_sha256"],
            "resample": row["resample"], "resource_usage": row["resource_usage"],
            "started_at": row["started_at"], "finished_at": row["finished_at"]}

    # ------------------------------------------------------------------ finalization

    def finalize(self, run_id: str, expected: dict[str, list[str]] | None, *, finished: bool) -> dict[str, Any]:
        """Merge expectations; finished (market-ai-orc's RUN_FINISHED) moves the run to FINALIZING and evaluates.
        A producer's expectations alone re-evaluate only a run that is already being finalized."""
        unknown = sorted(set(expected or {}) - set(EXPECTATION_KEYS))
        if unknown:
            raise AuditError("UNKNOWN_EXPECTATION", f"Unknown expectation keys {unknown}.", 422)
        with self.tx() as c:
            run = self._run(c, run_id, lock=True)
            merged = {k: list(v) for k, v in (run["expected"] or {}).items()}
            for key, values in (expected or {}).items():
                merged[key] = sorted(set(merged.get(key, [])) | set(values))
            if finished:
                merged["run_finished"] = ["true"]
            status = "FINALIZING" if finished or run["status"] != "OPEN" else "OPEN"
            c.execute("""UPDATE ai_audit.run SET expected = %s, status = %s, finalized_at = CASE WHEN %s = 'FINALIZING'
                         THEN NULL ELSE finalized_at END, updated_at = CURRENT_TIMESTAMP WHERE run_id = %s""",
                      (Jsonb(merged), status, status, run_id))
        return self.reevaluate(run_id, force=True) or self.run_view(run_id)

    def reevaluate(self, run_id: str, force: bool = False) -> dict[str, Any] | None:
        with self.tx() as c:
            run = self._run(c, run_id, lock=True)
            if run["status"] == "OPEN" or not (force or run["status"] in ("FINALIZING", "INCOMPLETE", "COMPLETE")):
                return None
            missing = self._missing(c, run_id, run["expected"] or {})
            status = "INCOMPLETE" if missing else "COMPLETE"
            if status != run["status"] or (missing or None) != run["missing"] or run["finalized_at"] is None:
                c.execute("""UPDATE ai_audit.run SET status = %s, missing = %s, finalized_at = CURRENT_TIMESTAMP,
                                    updated_at = CURRENT_TIMESTAMP WHERE run_id = %s""",
                          (status, Jsonb(missing) if missing else None, run_id))
                if status != run["status"]:
                    log_event("audit_run_status", run_id=run_id, request_id=run["request_id"], status=status,
                              missing={k: len(v) for k, v in missing.items()})
        return self.run_view(run_id)

    def _reevaluate_artifact_runs(self, artifact_id: str) -> None:
        with self.tx() as c:
            runs = [r["run_id"] for r in c.execute(
                """SELECT DISTINCT l.run_id FROM ai_audit.run_artifact l JOIN ai_audit.run r USING (run_id)
                   WHERE l.artifact_id = %s AND r.status IN ('FINALIZING', 'INCOMPLETE')""",
                (artifact_id,)).fetchall()]
        for run_id in runs:
            self.reevaluate(run_id)

    def reevaluate_incomplete(self) -> int:
        """Periodic sweep: INCOMPLETE runs updated within AUDIT_REEVALUATE_HOURS (late uploads)."""
        with self.tx() as c:
            runs = [r["run_id"] for r in c.execute(
                """SELECT run_id FROM ai_audit.run WHERE status IN ('INCOMPLETE', 'FINALIZING')
                   AND updated_at > CURRENT_TIMESTAMP - make_interval(hours => %s) ORDER BY updated_at LIMIT 200""",
                (self.settings.reevaluate_hours,)).fetchall()]
        for run_id in runs:
            self.reevaluate(run_id)
        return len(runs)

    @staticmethod
    def _missing(c: psycopg.Connection, run_id: str, expected: dict[str, list[str]]) -> dict[str, list[str]]:
        if not expected.get("run_finished"):
            return {"run_finished": ["market-ai-orc has not reported the run as finished"]}
        links = c.execute(
            """SELECT l.role, l.execution_id, l.label, a.sha256, a.state
               FROM ai_audit.run_artifact l JOIN ai_audit.artifact a USING (artifact_id) WHERE l.run_id = %s""",
            (run_id,)).fetchall()
        ready = [link for link in links if link["state"] == "READY"]

        def has(role: str, *, execution_id: str | None = None, label: str | None = None,
                sha: str | None = None) -> bool:
            return any(link["role"] == role and (execution_id is None or link["execution_id"] == execution_id)
                       and (label is None or link["label"] == label) and (sha is None or link["sha256"] == sha)
                       for link in ready)

        executions = {row["execution_id"]: row for row in c.execute(
            "SELECT execution_id, input_checksums FROM ai_audit.execution WHERE run_id = %s", (run_id,)).fetchall()}
        missing: dict[str, list[str]] = {}

        def add(key: str, value: str) -> None:
            missing.setdefault(key, []).append(value)

        for role in expected.get("roles", []):
            if not has(role):
                add("roles", role)
        inputs = set(expected.get("input_sha256", []))
        for execution_id in expected.get("execution_ids", []):
            record = executions.get(execution_id)
            if record is None:
                add("executions", execution_id)
                continue
            if not has("PYTHON_SOURCE", execution_id=execution_id):
                add("python_source", execution_id)
            if not has("RUNTIME_MANIFEST", execution_id=execution_id):
                add("runtime_manifest", execution_id)
            inputs |= {i["sha256"] for i in record["input_checksums"] or []}
        for sha in sorted(inputs):
            if not has("RAW_INPUT_PARQUET", sha=sha):
                add("raw_inputs", sha)
        for completion_id in expected.get("completion_ids", []):
            if not has("EXECUTION_MANIFEST", label=completion_id):
                add("execution_manifests", completion_id)
        for sha in expected.get("output_sha256", []):
            if not has("OUTPUT", sha=sha):
                add("outputs", sha)
        for dataset_id in expected.get("dataset_ids", []):
            if not has("RAW_INPUT_PARQUET", label=dataset_id):
                add("datasets", dataset_id)
        return missing

    # ------------------------------------------------------------------ replay

    def replay_manifest(self, run_id: str) -> dict[str, Any]:
        with self.tx() as c:
            run = self._run(c, run_id)
            executions = c.execute(
                """SELECT e.execution_id, e.session_id, e.bundle_id, e.seq, e.status, e.source_sha256, e.random_seed,
                          e.timezone, e.input_checksums, e.contract_sha256, e.resample, e.runtime_image_id,
                          e.git_commit, i.python_version, i.distributions
                   FROM ai_audit.execution e LEFT JOIN ai_audit.runtime_image i USING (runtime_image_id)
                   WHERE e.run_id = %s ORDER BY e.session_id, e.seq""", (run_id,)).fetchall()
            links = c.execute(
                """SELECT l.role, l.execution_id, l.label, a.artifact_id, a.sha256, a.size_bytes, a.state
                   FROM ai_audit.run_artifact l JOIN ai_audit.artifact a USING (artifact_id)
                   WHERE l.run_id = %s ORDER BY l.run_artifact_id""", (run_id,)).fetchall()

        def of(role: str, execution_id: str | None = None) -> list[dict[str, Any]]:
            return [{"artifact_id": link["artifact_id"], "sha256": link["sha256"], "size_bytes": link["size_bytes"],
                     "label": link["label"], "state": link["state"]} for link in links
                    if link["role"] == role and (execution_id is None or link["execution_id"] == execution_id)]

        return {
            "run_id": run_id, "request_id": run["request_id"], "status": run["status"],
            "raw_inputs": of("RAW_INPUT_PARQUET"), "approved_contracts": of("APPROVED_DATANEED_CONTRACT"),
            "executions": [{
                "execution_id": e["execution_id"], "session_id": e["session_id"], "bundle_id": e["bundle_id"],
                "seq": e["seq"], "status": e["status"], "python_source_sha256": e["source_sha256"],
                "random_seed": e["random_seed"], "timezone": e["timezone"],
                "input_ordering": e["input_checksums"], "contract_sha256": e["contract_sha256"],
                "resample_semantics_versions": sorted({r.get("semantics_version") for r in e["resample"] or []
                                                       if r.get("semantics_version") is not None}),
                "runtime_fingerprint": e["runtime_image_id"], "git_commit": e["git_commit"],
                "python_version": e["python_version"], "package_manifest": e["distributions"],
                "outputs": of("OUTPUT", e["execution_id"]),
                "python_source": of("PYTHON_SOURCE", e["execution_id"])} for e in executions],
            "outputs": of("OUTPUT"), "execution_manifests": of("EXECUTION_MANIFEST"),
            "determinism_note": DETERMINISM_NOTE}

    # ------------------------------------------------------------------ access, holds, retention

    def grant_access(self, accessor: str, artifact_id: str, purpose: str, run_id: str | None) -> dict[str, Any]:
        ttl = self.settings.access_url_ttl_seconds
        with self.tx() as c:
            row = c.execute("SELECT state, object_key FROM ai_audit.artifact WHERE artifact_id = %s",
                            (artifact_id,)).fetchone()
            if row is None:
                raise AuditError("ARTIFACT_NOT_FOUND", "No artifact with this artifact_id.", 404)
            if row["state"] != "READY":
                raise AuditError("ARTIFACT_NOT_READY", f"The artifact is {row['state']}.", 409)
            expires = utc_now() + timedelta(seconds=ttl)
            c.execute("""INSERT INTO ai_audit.artifact_access (artifact_id, run_id, accessor, purpose, url_expires_at)
                         VALUES (%s, %s, %s, %s, %s)""", (artifact_id, run_id, accessor, purpose, expires))
        log_event("audit_artifact_access", artifact_id=artifact_id, accessor=accessor, run_id=run_id)
        return {"artifact_id": artifact_id, "url": self.store.presigned_get(row["object_key"], ttl),
                "expires_at": expires}

    def add_hold(self, actor: str, run_id: str | None, artifact_id: str | None, reason: str) -> dict[str, Any]:
        if (run_id is None) == (artifact_id is None):
            raise AuditError("HOLD_TARGET", "Give exactly one of run_id and artifact_id.", 422)
        hold_id = f"hold_{secrets.token_hex(16)}"
        try:
            with self.tx() as c:
                return c.execute("""INSERT INTO ai_audit.retention_hold (hold_id, run_id, artifact_id, reason, created_by)
                                    VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                                 (hold_id, run_id, artifact_id, reason, actor)).fetchone()
        except psycopg.errors.ForeignKeyViolation as exc:
            raise AuditError("HOLD_TARGET_NOT_FOUND", "The run or artifact does not exist.", 404) from exc

    def release_hold(self, actor: str, hold_id: str) -> dict[str, Any]:
        with self.tx() as c:
            row = c.execute("""UPDATE ai_audit.retention_hold SET released_at = CURRENT_TIMESTAMP, released_by = %s
                               WHERE hold_id = %s AND released_at IS NULL RETURNING *""", (actor, hold_id)).fetchone()
        if row is None:
            raise AuditError("HOLD_NOT_ACTIVE", "No active hold with this hold_id.", 404)
        return row

    def retention_report(self, sample: int = 100) -> dict[str, Any]:
        """Dry run only: which READY artifacts retention could delete, and why the others are kept. An object is
        eligible only when every run referencing it has expired, no active hold covers it or any of those runs, and
        (for an unreferenced object) it is older than the standard retention. Nothing is deleted."""
        with self.tx() as c:
            rows = c.execute(
                """WITH refs AS (
                       SELECT a.artifact_id, a.size_bytes, a.created_at,
                              count(l.run_id) AS runs,
                              count(l.run_id) FILTER (WHERE r.expires_at > CURRENT_TIMESTAMP) AS live_runs,
                              bool_or(EXISTS (SELECT 1 FROM ai_audit.retention_hold h
                                              WHERE h.run_id = l.run_id AND h.released_at IS NULL)) AS run_held,
                              EXISTS (SELECT 1 FROM ai_audit.retention_hold h
                                      WHERE h.artifact_id = a.artifact_id AND h.released_at IS NULL) AS artifact_held
                       FROM ai_audit.artifact a
                       LEFT JOIN ai_audit.run_artifact l USING (artifact_id)
                       LEFT JOIN ai_audit.run r ON r.run_id = l.run_id
                       WHERE a.state = 'READY'
                       GROUP BY a.artifact_id, a.size_bytes, a.created_at)
                   SELECT artifact_id, size_bytes, runs, live_runs, COALESCE(run_held, false) AS run_held,
                          artifact_held,
                          CASE WHEN artifact_held OR COALESCE(run_held, false) THEN 'HELD'
                               WHEN live_runs > 0 THEN 'REFERENCED_BY_UNEXPIRED_RUN'
                               WHEN runs = 0 AND created_at > CURRENT_TIMESTAMP - make_interval(days => %s)
                                   THEN 'UNREFERENCED_WITHIN_GRACE'
                               ELSE 'ELIGIBLE' END AS decision
                   FROM refs ORDER BY artifact_id""", (self.settings.retention_standard_days,)).fetchall()
            runs = c.execute(
                """SELECT count(*) FILTER (WHERE expires_at <= CURRENT_TIMESTAMP) AS expired,
                          count(*) FILTER (WHERE expires_at <= CURRENT_TIMESTAMP AND EXISTS (
                              SELECT 1 FROM ai_audit.retention_hold h
                              WHERE h.run_id = run.run_id AND h.released_at IS NULL)) AS expired_but_held,
                          count(*) AS total
                   FROM ai_audit.run""").fetchone()
        summary: dict[str, dict[str, int]] = {}
        for row in rows:
            entry = summary.setdefault(row["decision"], {"artifacts": 0, "bytes": 0})
            entry["artifacts"] += 1
            entry["bytes"] += int(row["size_bytes"])
        return {"dry_run": True, "generated_at": utc_now(), "policy": {
                    "standard_days": self.settings.retention_standard_days,
                    "pinned_days": self.settings.retention_pinned_days,
                    "rule": "delete an object only when every referencing run has expired and no active hold covers "
                            "it or those runs; destructive cleanup is not enabled in this release"},
                "runs": runs, "artifacts": summary,
                "eligible_sample": [r["artifact_id"] for r in rows if r["decision"] == "ELIGIBLE"][:sample]}


def reject_reasoning(value: Any) -> None:
    found = forbidden_key(value)
    if found:
        raise AuditError("REASONING_NOT_ALLOWED", f"Payload may not carry model reasoning ({found}).", 422)
