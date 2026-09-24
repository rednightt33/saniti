"""Run audit: after every run, record what the AI finally reported and the evidence it relied on.

1. The final report (answer and its hash, evidence label, gate outcome, the experiments and whether the answer
   cites them) goes to market-python-sandbox, which holds the run's operational state (specs, governor
   decisions, analyses, budgets) for its record retention.
2. One summary row per run is copied to PostgreSQL table "AI_research_run_audit" (INSERT only; a retried
   request_id keeps its first row), when RESEARCH_AUDIT_DATABASE_URL is configured.

Auditing never changes the response and never fails the run: every problem is logged and skipped. Hidden model
reasoning and secrets are never recorded; datasets are recorded by id and checksum, not content.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger("market_ai_orc")

# A conflict target would need SELECT on the table; without one the INSERT-only writer role is enough.
INSERT_SQL = '''
INSERT INTO public."AI_research_run_audit" (
    request_id, status, response_type, evidence_label, validation_gate, error_code, question_sha256, question,
    answer_sha256, answer, limitations, number_provenance, experiments, datasets, budget, model, tool_call_count,
    total_tokens, duration_ms, sandbox_summary_status)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, %s,
        %s)
ON CONFLICT DO NOTHING
'''
MAX_QUESTION = 16000
MAX_ANSWER = 20000


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def build_report(question: str, result: Any, experiments: list[dict[str, Any]]) -> dict[str, Any]:
    response = result.response
    execution = result.execution
    answer = response.answer if response is not None else None
    return {
        "status": result.status, "response_type": response.response_type if response is not None else None,
        "evidence_label": result.evidence_label, "validation_gate": execution.validation_gate,
        "question_sha256": sha256(question), "question": question[:MAX_QUESTION],
        "answer_sha256": sha256(answer) if answer is not None else None,
        "answer": answer[:MAX_ANSWER] if answer is not None else None,
        "limitations": list(response.limitations)[:60] if response is not None else [],
        "number_provenance": execution.number_provenance.model_dump() if execution.number_provenance else None,
        "experiments": experiments[:60], "model": execution.model, "tool_call_count": execution.tool_call_count,
        "total_tokens": execution.total_tokens, "duration_ms": execution.duration_ms,
        "error_code": result.error.code if result.error else None,
    }


class RunAuditor:
    def __init__(self, sandbox: Any | None, database_url: str | None, *, connect_timeout_seconds: int = 5) -> None:
        self.sandbox = sandbox
        self.database_url = database_url
        self.connect_timeout_seconds = connect_timeout_seconds

    def record(self, request_id: str, question: str, result: Any, experiments: list[dict[str, Any]],
               used_sandbox: bool) -> dict[str, Any]:
        report = build_report(question, result, experiments)
        outcome: dict[str, Any] = {"sandbox_report": "NOT_USED", "database": "DISABLED"}
        summary: dict[str, Any] | None = None
        if self.sandbox is not None and used_sandbox:
            try:
                stored = self.sandbox.put_report(request_id, report)
                outcome["sandbox_report"] = "STORED" if stored.get("stored") else "ALREADY_STORED"
                summary = self.sandbox.run_summary(request_id)
            except Exception as exc:  # noqa: BLE001 - auditing never fails the run
                outcome["sandbox_report"] = f"ERROR:{type(exc).__name__}"
        if self.database_url:
            outcome["database"] = self._insert(request_id, report, summary, used_sandbox)
        logger.info(json.dumps({"event": "research_audit", "request_id": request_id, **outcome}))
        return outcome

    def _insert(self, request_id: str, report: dict[str, Any], summary: dict[str, Any] | None,
                used_sandbox: bool) -> str:
        import psycopg

        datasets: dict[str, Any] = {}
        for analysis in (summary or {}).get("analyses") or []:
            datasets.update(analysis.get("datasets") or {})
        experiments = report["experiments"]
        if summary:
            by_analysis = {a["analysis_id"]: a for a in summary.get("analyses") or []}
            experiments = [{**e, **{k: by_analysis.get(e.get("analysis_id") or "", {}).get(k)
                                    for k in ("code_sha256", "dataset_ids", "leakage_check", "cpu_seconds")}}
                           for e in experiments]
        status = (summary or {}).get("status") or ("UNAVAILABLE" if used_sandbox else "NOT_USED")
        values = (request_id, report["status"], report["response_type"], report["evidence_label"],
                  report["validation_gate"], report["error_code"], report["question_sha256"], report["question"],
                  report["answer_sha256"], report["answer"], json.dumps(report["limitations"]),
                  json.dumps(report["number_provenance"]) if report["number_provenance"] is not None else None,
                  json.dumps(experiments, default=str), json.dumps(
                      [{"dataset_id": k, **v} for k, v in sorted(datasets.items())], default=str),
                  json.dumps((summary or {}).get("budget") or {}, default=str), report["model"],
                  report["tool_call_count"], report["total_tokens"], report["duration_ms"], status)
        try:
            with psycopg.connect(self.database_url, connect_timeout=self.connect_timeout_seconds,
                                 autocommit=True) as connection:
                # The orchestrator login defaults to read-only transactions; this session only inserts.
                connection.execute("SET default_transaction_read_only = off")
                connection.execute("SET statement_timeout = '5s'")
                cursor = connection.execute(INSERT_SQL, values)
                return "INSERTED" if cursor.rowcount == 1 else "ALREADY_RECORDED"
        except Exception as exc:  # noqa: BLE001 - auditing never fails the run
            return f"ERROR:{type(exc).__name__}"
