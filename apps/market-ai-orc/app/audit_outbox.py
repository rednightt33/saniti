"""IP2 solution 2: hand every finished run to market-audit-store through ai_audit.ingest_outbox.

market-ai-orc has no persistent volume and no audit-bucket credential. At the end of a run it INSERTs one RUN_FINISHED
row (idempotent on request_id; ON CONFLICT DO NOTHING needs no SELECT) with the run's identity, the observable model
and tool events (tool names, sanitized and bounded arguments and results with their hashes, statuses, durations), the
final response, provider/model metadata, a token/duration summary and what the sandbox must have archived
(execution and completion ids). market-audit-store consumes the row. Hidden model reasoning is never sent: nothing
here reads a reasoning item, and any key naming reasoning is dropped. Secrets (keys, tokens, presigned URLs) are
redacted before hashing."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import psycopg

SCHEMA = "saniti.audit.run_finished/v1"
SOURCE = "market-ai-orc"
FORBIDDEN = {"reasoning", "reasoning_content", "reasoning_details", "thinking", "chain_of_thought", "encrypted_content"}
SECRET_KEY = re.compile(r"(token|secret|password|api[_-]?key|authorization|credential|signature)", re.I)
URL = re.compile(r"https?://\S+")
MAX_STRING = 2000
MAX_ITEMS = 50
MAX_EVENT_CHARS = 8000
MAX_EVENTS = 400
MAX_FINAL_CHARS = 1_000_000
INSERT_SQL = """
INSERT INTO ai_audit.ingest_outbox (source, idempotency_key, request_id, kind, payload)
VALUES (%s, %s, %s, 'RUN_FINISHED', %s::jsonb)
ON CONFLICT DO NOTHING
"""


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def sanitize(value: Any, depth: int = 0) -> Any:
    """Bounded, secret-free and reasoning-free copy of a JSON value."""
    if depth > 8:
        return "[depth limit]"
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:MAX_ITEMS]:
            name = str(key)
            if name.lower() in FORBIDDEN:
                continue
            out[name] = "[redacted]" if SECRET_KEY.search(name) else sanitize(item, depth + 1)
        return out
    if isinstance(value, list):
        items = [sanitize(item, depth + 1) for item in value[:MAX_ITEMS]]
        return items + ([f"[{len(value) - MAX_ITEMS} more]"] if len(value) > MAX_ITEMS else [])
    if isinstance(value, str):
        text = URL.sub("[url]", value)
        return text if len(text) <= MAX_STRING else text[:MAX_STRING] + f"...[{len(text) - MAX_STRING} more chars]"
    return value


def bounded(value: Any, limit: int = MAX_EVENT_CHARS) -> Any:
    clean = sanitize(value)
    text = json.dumps(clean, default=str, separators=(",", ":"))
    return clean if len(text) <= limit else {"truncated": True, "chars": len(text), "preview": text[:limit]}


def tool_event(*, tool: str, call_id: str, iteration: int, arguments: Any, output: dict[str, Any], ok: bool,
               error_code: str | None, duration_ms: int, occurred_at: datetime) -> dict[str, Any]:
    clean_args, clean_out = sanitize(arguments), sanitize(output)
    return {"type": "tool.call", "occurred_at": occurred_at.isoformat(), "tool": tool, "call_id": call_id,
            "iteration": iteration, "ok": ok, "error_code": error_code, "duration_ms": duration_ms,
            "arguments": bounded(clean_args), "arguments_sha256": _sha(clean_args),
            "result": bounded(clean_out), "result_sha256": _sha(clean_out)}


def model_event(record: dict[str, Any], occurred_at: datetime) -> dict[str, Any]:
    """An observable model call: iteration, latency and provider response id; never its content or reasoning."""
    return {"type": "model.call", "occurred_at": occurred_at.isoformat(),
            **{k: record.get(k) for k in ("iteration", "call", "provider_response_id", "latency_ms", "status")
               if record.get(k) is not None}}


MAX_DRAFT_CHARS = 20_000


def final_event(kind: str, *, iteration: int, stage: str, detail: str, draft: str | None,
                occurred_at: datetime) -> dict[str, Any]:
    """final.rejected / final.forced (2026-09-30): a gate or the format check refused the model's final response. The
    draft is the model's visible output as it arrived (never reasoning), URLs redacted, bounded; it lets an auditor
    read what a gate refused (the conversation store keeps only the final answer)."""
    text = URL.sub("[url]", draft or "")
    return {"type": kind, "occurred_at": occurred_at.isoformat(), "iteration": iteration, "stage": stage,
            "detail": str(detail)[:2000], "draft": text[:MAX_DRAFT_CHARS], "draft_chars": len(text),
            "draft_sha256": hashlib.sha256(text.encode()).hexdigest()}


def unrendered_event(response: dict[str, Any], occurred_at: datetime) -> dict[str, Any]:
    """final.unrendered: the final response as the model wrote it, with its value references, before the backend
    filled them in (the rendered one is final_response)."""
    text = URL.sub("[url]", json.dumps(response, default=str, ensure_ascii=False))
    return {"type": "final.unrendered", "occurred_at": occurred_at.isoformat(), "response": text[:MAX_DRAFT_CHARS],
            "response_chars": len(text)}


def build_payload(*, request: Any, result: Any, trace: list[dict[str, Any]], started_at: datetime,
                  finished_at: datetime, model: str, execution_ids: list[str], completion_ids: list[str],
                  sessions: list[str], bundles: list[str]) -> dict[str, Any]:
    execution = result.execution
    response = result.response.model_dump(mode="json") if result.response is not None else None
    if response is not None and len(json.dumps(response, default=str)) > MAX_FINAL_CHARS:
        response = {"truncated": True, "sha256": _sha(response)}
    continuation = getattr(request, "continuation", None)
    return {
        "schema": SCHEMA, "request_id": request.request_id, "conversation_id": request.conversation_id,
        "turn_index": None, "parent_request_id": getattr(continuation, "origin_request_id", None),
        "started_at": started_at.isoformat(), "finished_at": finished_at.isoformat(),
        "model": model, "provider": execution.provider,
        "deployment": {"git_commit": os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
                       "deployment_id": os.environ.get("RAILWAY_DEPLOYMENT_ID")},
        "summary": {"status": result.status, "response_type": response.get("response_type") if response else None,
                    "evidence_label": result.evidence_label, "error_code": result.error.code if result.error else None,
                    "iterations": execution.iterations, "tool_call_count": execution.tool_call_count,
                    "input_tokens": execution.input_tokens, "output_tokens": execution.output_tokens,
                    "reasoning_token_count": execution.reasoning_tokens, "total_tokens": execution.total_tokens,
                    "cached_input_tokens": execution.cached_input_tokens, "cost": execution.cost,
                    "duration_ms": execution.duration_ms, "validation_gate": execution.validation_gate},
        "events": trace[:MAX_EVENTS],
        "final_response": response,
        "analysis_final_status": sanitize(execution.analysis_final_status),
        "analysis_final_statuses": sanitize(execution.analysis_final_statuses),
        "expected": {"execution_ids": sorted(set(execution_ids)), "completion_ids": sorted(set(completion_ids))},
        "resources": {"session_ids": sorted(set(sessions)), "bundle_ids": sorted(set(bundles))},
    }


class AuditOutbox:
    """INSERT-only writer of ai_audit.ingest_outbox (AUDIT_OUTBOX_DATABASE_URL, a login in
    market_ai_audit_outbox_writer)."""

    def __init__(self, database_url: str, *, connect_timeout_seconds: int = 5) -> None:
        self.database_url = database_url
        self.connect_timeout_seconds = connect_timeout_seconds

    def write(self, payload: dict[str, Any]) -> None:
        with psycopg.connect(self.database_url, connect_timeout=self.connect_timeout_seconds,
                             autocommit=True) as connection:
            # the orchestrator login defaults to read-only transactions; this session only inserts
            connection.execute("SET default_transaction_read_only = off")
            connection.execute("SET statement_timeout = '5s'")
            connection.execute(INSERT_SQL, (SOURCE, f"{payload['request_id']}:RUN_FINISHED", payload["request_id"],
                                            json.dumps(payload, default=str)))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
