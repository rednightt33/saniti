"""Consumer of ai_audit.ingest_outbox (market-ai-orc's RUN_FINISHED rows).

market-ai-orc may only INSERT into the outbox (it cannot read or change it). This consumer takes due rows with FOR
UPDATE SKIP LOCKED (several replicas never process one row twice at the same time), turns each into the run, its
ordered observable events, the TOOL_TRACE and FINAL_RESPONSE artifacts (written by this service and READY at once)
and the run's expectations, then finalizes the run. Processing is idempotent (request_id, event idempotency keys,
content addresses), so a crash between two steps is repaired by the retry. A failure is FAILED_RETRYABLE with
exponential backoff; after AUDIT_OUTBOX_MAX_ATTEMPTS the row is INCOMPLETE and its run records the failure."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from .models import FORBIDDEN_KEYS, RunRegistration, forbidden_key
from .service import AuditError, AuditService, canonical, log_event

SCHEMA = "saniti.audit.run_finished/v1"
EVENT_PAYLOAD_LIMIT = 12000


def _bounded(value: Any, limit: int = EVENT_PAYLOAD_LIMIT) -> Any:
    text = json.dumps(value, default=str, separators=(",", ":"))
    if len(text) <= limit:
        return value
    return {"truncated": True, "chars": len(text), "preview": text[: limit - 200]}


def _strip_reasoning(value: Any) -> Any:
    """Defence in depth: market-ai-orc never sends reasoning, and anything under a reasoning key is dropped."""
    if isinstance(value, dict):
        return {k: _strip_reasoning(v) for k, v in value.items() if str(k).lower() not in FORBIDDEN_KEYS}
    if isinstance(value, list):
        return [_strip_reasoning(v) for v in value]
    return value


class OutboxConsumer:
    def __init__(self, service: AuditService) -> None:
        self.service = service
        self.settings = service.settings
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ loop

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="audit-outbox", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.drain()
                self.service.reevaluate_incomplete()
            except Exception as exc:  # noqa: BLE001 - the loop must survive a database outage
                log_event("audit_outbox_loop_error", error=type(exc).__name__, message=str(exc)[:300])
            self._stop.wait(self.settings.outbox_poll_seconds)

    def drain(self) -> dict[str, int]:
        counts = {"complete": 0, "retry": 0, "incomplete": 0}
        while True:
            outcome = self.process_one()
            if outcome is None:
                return counts
            counts[outcome] += 1

    # ------------------------------------------------------------------ one row

    def process_one(self) -> str | None:
        with self.service.tx() as c:
            row = c.execute(
                """SELECT outbox_id, source, idempotency_key, request_id, kind, payload, attempts
                   FROM ai_audit.ingest_outbox
                   WHERE status IN ('PENDING', 'FAILED_RETRYABLE') AND next_attempt_at <= CURRENT_TIMESTAMP
                   ORDER BY next_attempt_at, outbox_id LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
            if row is None:
                return None
            attempts = int(row["attempts"]) + 1
            try:
                self.ingest(row)
            except Exception as exc:  # noqa: BLE001 - every failure is recorded on the row
                final = attempts >= self.settings.outbox_max_attempts or isinstance(exc, (ValidationError,
                                                                                         AuditError))
                delay = min(3600, 10 * 2 ** min(attempts, 12))
                c.execute("""UPDATE ai_audit.ingest_outbox SET status = %s, attempts = %s, last_error = %s,
                                    next_attempt_at = %s WHERE outbox_id = %s""",
                          ("INCOMPLETE" if final else "FAILED_RETRYABLE", attempts,
                           f"{type(exc).__name__}: {getattr(exc, 'message', str(exc))}"[:1000],
                           datetime.now(timezone.utc) + timedelta(seconds=delay), row["outbox_id"]))
                log_event("audit_outbox_failed", outbox_id=row["outbox_id"], request_id=row["request_id"],
                          attempts=attempts, final=final, error=type(exc).__name__)
                return "incomplete" if final else "retry"
            c.execute("""UPDATE ai_audit.ingest_outbox SET status = 'COMPLETE', attempts = %s, last_error = NULL,
                                processed_at = CURRENT_TIMESTAMP WHERE outbox_id = %s""", (attempts, row["outbox_id"]))
            log_event("audit_outbox_ingested", outbox_id=row["outbox_id"], request_id=row["request_id"],
                      attempts=attempts)
            return "complete"

    def ingest(self, row: dict[str, Any]) -> str:
        """RUN_FINISHED -> run, events, TOOL_TRACE, FINAL_RESPONSE, expectations, finalization. Returns run_id."""
        payload = _strip_reasoning(row["payload"])
        if payload.get("schema") != SCHEMA:
            raise AuditError("OUTBOX_SCHEMA", f"Unknown outbox payload schema {payload.get('schema')!r}.", 422)
        if payload.get("request_id") != row["request_id"]:
            raise AuditError("OUTBOX_REQUEST_MISMATCH", "payload.request_id differs from the row.", 422)
        service = self.service
        registration = RunRegistration(request_id=row["request_id"], conversation_id=payload.get("conversation_id"),
                                       turn_index=payload.get("turn_index"),
                                       parent_request_id=payload.get("parent_request_id"))
        summary = {k: v for k, v in (payload.get("summary") or {}).items() if not isinstance(v, (dict, list))}
        run = service.register_run(row["source"], registration, model=payload.get("model"),
                                   provider=payload.get("provider"), deployment=payload.get("deployment") or None,
                                   summary=summary)
        run_id = run["run_id"]
        trace = {"schema": "saniti.audit.tool_trace/v1", "request_id": row["request_id"],
                 "events": payload.get("events") or []}
        trace_id = service.store_own(canonical(trace), "application/json")
        final_id = None
        if payload.get("final_response") is not None:
            final_id = service.store_own(canonical({"schema": "saniti.audit.final_response/v1",
                                                    "request_id": row["request_id"],
                                                    "response": payload["final_response"]}), "application/json")
        from .models import EventIn, LinkIn

        events = [EventIn(idempotency_key=f"orc:{index}", event_type=str(event.get("type") or "orc.event"),
                          occurred_at=event.get("occurred_at") or payload.get("finished_at"),
                          payload=_bounded({k: v for k, v in event.items() if k not in ("type", "occurred_at")}))
                  for index, event in enumerate(payload.get("events") or [])]
        events.append(EventIn(idempotency_key="orc:run.finished", event_type="run.finished",
                              occurred_at=payload.get("finished_at"), artifact_id=final_id or trace_id,
                              payload=_bounded({"summary": summary, "expected": payload.get("expected") or {}})))
        for start in range(0, len(events), self.settings.max_events_per_call):
            service.append_events(row["source"], run_id, events[start:start + self.settings.max_events_per_call])
        links = [LinkIn(artifact_id=trace_id, role="TOOL_TRACE")]
        if final_id:
            links.append(LinkIn(artifact_id=final_id, role="FINAL_RESPONSE"))
        service.link(row["source"], run_id, links)
        expected = {k: [str(v) for v in values] for k, values in (payload.get("expected") or {}).items()
                    if k in ("execution_ids", "completion_ids") and isinstance(values, list)}
        expected["roles"] = ["TOOL_TRACE"] + (["FINAL_RESPONSE"] if final_id else [])
        service.finalize(run_id, expected, finished=True)
        if forbidden_key(payload):  # unreachable after _strip_reasoning; kept as an explicit assertion
            raise AuditError("REASONING_NOT_ALLOWED", "reasoning survived sanitization", 422)
        return run_id
