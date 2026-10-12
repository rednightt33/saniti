"""The kejedot index (round 2026-10-03, ROUND_PLAN_2026-10-03.md §0): how often a run hit a wall on its way to the
answer, counted by code from what the run already records, so golden tests compare runs without reading logs by hand.

- rejected_tool_calls: tool results the model saw as ERROR or REJECTED (the envelope's own status rule);
- gate_repairs: final answers the gates sent back for repair (state.gate_rejections);
- repeated_data_orders: approved data needs that ask for the same tables and row filters as a need the conversation
  already had (the g7 pattern: ordering the data again instead of reusing it);
- capacity_refusals: SESSION_CAPACITY_EXCEEDED results (S28);
- failed_executions: code runs that ended SCRIPT_ERROR or TIMEOUT (EXEC-FRICTION: the envelope shows them as data, so
  rejected_tool_calls never counted them).

refusal() is the one rule for what a tool outcome counts as refused or failed: the run memory's refusal ledger, the
hurdles shown to the user (execution.hurdles) and failed_executions read it (EXEC-FRICTION, M142: the ledger used to
skip REVISION_REQUIRED, so a refused data need never reached the memo).
"""
from __future__ import annotations

from typing import Any

from .compaction import dumps
from .tools.envelope import REJECTED_STATUSES, envelope
from .tools.registry import ToolOutcome

KEYS = ("rejected_tool_calls", "gate_repairs", "repeated_data_orders", "capacity_refusals", "failed_executions")
FAILED_EXECUTION_STATUSES = frozenset({"SCRIPT_ERROR", "TIMEOUT"})
# the ledger's statuses before EXEC-FRICTION plus every status the envelope shows as REJECTED
LEDGER_STATUSES = REJECTED_STATUSES | FAILED_EXECUTION_STATUSES | frozenset({"ERROR", "INCOMPLETE"})


def refusal(outcome: ToolOutcome) -> dict[str, Any] | None:
    """{kind: REJECTED | FAILED_EXECUTION, code, message} for a refused or failed tool outcome, else None. A refused
    data need is named by its first issue codes (for example RELATIONSHIP_KEY_MISMATCH), not by REVISION_REQUIRED."""
    output = outcome.output if isinstance(outcome.output, dict) else {}
    if not outcome.ok:
        error = output.get("error") if isinstance(output.get("error"), dict) else {}
        return {"kind": "REJECTED", "code": outcome.error_code or error.get("code"), "message": error.get("message")}
    result = output.get("result")
    if not isinstance(result, dict):
        return None
    status = str(result.get("status") or result.get("decision") or result.get("execution_status") or "")
    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    if not (status.startswith("REJECTED") or status in LEDGER_STATUSES or error):
        return None
    issues = [i for i in result.get("issues") or [] if isinstance(i, dict) and i.get("code")]
    code = error.get("code") or result.get("code") \
        or (", ".join(dict.fromkeys(str(i["code"]) for i in issues[:3])) if issues else None) or status
    message = error.get("message") or result.get("message") or result.get("reason") \
        or dumps({k: result[k] for k in ("issues", "problems", "stderr_tail") if k in result})[:4000]
    return {"kind": "FAILED_EXECUTION" if status in FAILED_EXECUTION_STATUSES else "REJECTED", "code": code,
            "message": message}


def empty() -> dict[str, int]:
    return dict.fromkeys(KEYS, 0)


def _need_key(requests: list[Any]) -> frozenset[tuple[str, str]]:
    return frozenset((str(r.get("source_table")), str(r.get("scope_sha256"))) for r in requests
                     if isinstance(r, dict) and r.get("source_table"))


def count_tool(counts: dict[str, int], name: str, outcome: ToolOutcome, record: dict[str, Any]) -> None:
    """Count one tool outcome; record is the conversation's data record (needs of earlier turns and this run)."""
    found = refusal(outcome)
    if found is not None and found["kind"] == "FAILED_EXECUTION":
        counts["failed_executions"] += 1
    view = envelope(outcome)
    if view["status"] in ("ERROR", "REJECTED"):
        counts["rejected_tool_calls"] += 1
        if any(e.get("code") == "SESSION_CAPACITY_EXCEEDED" for e in view["errors"]):
            counts["capacity_refusals"] += 1
        return
    result = view["data"] if isinstance(view["data"], dict) else {}
    approved = result.get("approved")
    if name != "submit_data_need_spec" or not isinstance(approved, dict):
        return
    key = _need_key(approved.get("requests") or [])
    if key and any(_need_key(n.get("requests") or []) == key for n in record.get("needs") or []
                   if isinstance(n, dict) and n.get("need_id") != result.get("need_id")):
        counts["repeated_data_orders"] += 1
