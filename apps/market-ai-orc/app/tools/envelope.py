"""The standard envelope of every tool result the model reads (round 2026-10-03, ENV; ROUND_PLAN_2026-10-03.md A2).

Tools answer in their own shapes: an error from the registry ({"ok": false, "error": {...}}), a rejection inside a
successful call ({"status": "REJECTED", "error": {...}, "next_action": ...}), or a plain result. The model had to
learn each shape, and an error without a next step led to retries of the same call. The envelope gives every result
the same frame:

    {"status": "OK | PARTIAL | REJECTED | ERROR", "tool": ..., "data": <the tool's own result, unchanged>,
     "warnings": [...], "errors": [{"code", "message", "retryable", "next_action"}], "meta": {...}}

It is applied only where a result is serialized for the model (orchestrator._handle_call); ToolOutcome.output, which
the orchestrator's gates read, does not change. Every error carries a next action: the tool's own when it gave one,
else ERROR_ACTIONS by code (a test fails when a code the orchestrator can raise has no entry), else one derived from
the code's kind.
"""
from __future__ import annotations

from typing import Any

from .registry import ToolOutcome

# next_action vocabulary (the model reads these words; a tool's own next_action is passed through unchanged)
FIX_ARGUMENTS = "FIX_ARGUMENTS"
WAIT_AND_RETRY = "WAIT_AND_RETRY"
ANSWER_LIMITATION = "ANSWER_LIMITATION"
FINAL_ANSWER = "RETURN_FINAL_RESPONSE"

# code -> (next_action, retryable) for every error the orchestrator itself raises
ERROR_ACTIONS: dict[str, tuple[str, bool]] = {
    "INVALID_ARGUMENTS": (FIX_ARGUMENTS, True),
    "UNKNOWN_TOOL": ("USE_LISTED_TOOLS", True),
    "TOOLS_NOT_AVAILABLE": (FINAL_ANSWER, False),
    "TOOL_NOT_AVAILABLE_IN_THIS_TURN": ("USE_LISTED_TOOLS", True),
    "TOOL_TIMEOUT": ("NARROW_REQUEST_OR_ANSWER_LIMITATION", False),
    "TOOL_FAILED": (ANSWER_LIMITATION, False),
    "TOOL_ERROR": (ANSWER_LIMITATION, False),
    "TOOL_RESULT_TOO_LARGE": ("NARROW_REQUEST", True),
    "TOOL_BUDGET_EXHAUSTED": (FINAL_ANSWER, False),
    "REPAIR_BUDGET_EXHAUSTED": (FINAL_ANSWER, False),
    "REPEATED_TOOL_CALL": ("USE_EARLIER_RESULT", False),
    "MODEL_OUTPUT_TRUNCATED": ("RESEND_CALL_SHORTER", True),
    "CURSOR_INVALID": ("RESTART_PAGING", True),
    "CATALOG_CHANGED_RESTART_DISCOVERY": ("CALL:discover_catalog", True),
    "CATALOG_DETAILS_REQUIRED": ("CALL:get_catalog_details", True),
    "ANALYSIS_SESSION_ALREADY_OPEN": ("USE_OPEN_SESSION", True),
    "INSIGHT_SOURCE_NOT_OPENED": ("CALL:run_python with load_output", True),
    "MULTI_ANGLE_PLAN_REQUIRED": ("PRESENT_MULTI_ANGLE_PLAN", True),
    "PATH_MISMATCH": ("FOLLOW_FIXED_PATH", True),
    # D2 (round 2026-10-03): results of earlier answers
    "OUTPUT_NOT_AVAILABLE": (ANSWER_LIMITATION, False),
    "OUTPUT_NOT_FOUND": (FIX_ARGUMENTS, True),
    "REF_NOT_FOUND": (FIX_ARGUMENTS, True),
    "EXECUTION_NOT_FOUND": (FIX_ARGUMENTS, True),
    # D4: export_result
    "EXPORT_NOT_AVAILABLE": (ANSWER_LIMITATION, False),
    "EXPORT_NOT_SAVED": (ANSWER_LIMITATION, False),
    "EXPORT_NOT_TABULAR": (FIX_ARGUMENTS, True),
    "EXPORT_TOO_LARGE": ("EXPORT_FEWER_COLUMNS_OR_ROWS_OR_PARQUET", True),
    # D5: query_metric
    "METRIC_NOT_IN_CATALOG": ("CALL:submit_data_need_spec", False),
    "METRIC_DIMENSION_NOT_ALLOWED": (FIX_ARGUMENTS, True),
    # D6: get_evidence and the evidence gate
    "EVIDENCE_NOT_FOUND": (FIX_ARGUMENTS, True),
}
REJECTED_STATUSES = frozenset({
    "REJECTED", "FAILED", "FAIL", "INVALID", "INVALID_SPEC", "NOT_FEASIBLE", "REVISION_REQUIRED", "NOT_FOUND",
    "CATALOG_UNAVAILABLE", "REQUEST_BUDGET_EXCEEDED", "FAILED_RETRYABLE", "SESSION_ENDED", "CANCELLED"})
PARTIAL_STATUSES = frozenset({"INCOMPLETE", "PARTIAL"})
RETRYABLE_HINTS = ("TIMEOUT", "CAPACITY", "QUEUE", "RETRY", "BUSY", "UNAVAILABLE")
EXTRA_WARNINGS = {"ignored_arguments": "IGNORED_ARGUMENTS", "unwrapped_arguments": "UNWRAPPED_ARGUMENTS",
                  "omitted_fields_set_to_null": "OMITTED_FIELDS_SET_TO_NULL"}


def _action(code: str | None, given: Any = None) -> tuple[str, bool]:
    """(next_action, retryable): the tool's own next_action first, then ERROR_ACTIONS, then the code's kind."""
    known = ERROR_ACTIONS.get(code or "")
    retryable = known[1] if known else any(hint in (code or "") for hint in RETRYABLE_HINTS)
    if isinstance(given, str) and given:
        return given, retryable
    if known:
        return known
    return (WAIT_AND_RETRY if retryable else "READ_MESSAGE_THEN_FIX_OR_ANSWER_LIMITATION"), retryable


def _error(code: Any, message: Any, next_action: Any = None, details: Any = None) -> dict[str, Any]:
    action, retryable = _action(str(code) if code else None, next_action)
    entry = {"code": str(code or "UNSPECIFIED"), "message": str(message or "")[:1000], "retryable": retryable,
             "next_action": action}
    if details:
        entry["details"] = details
    return entry


def _truncated(node: Any) -> bool:
    if isinstance(node, dict):
        return bool(node.get("rows_truncated") or node.get("truncated") is True) \
            or any(_truncated(v) for v in node.values())
    if isinstance(node, list):
        return any(_truncated(v) for v in node)
    return False


def envelope(outcome: ToolOutcome, *, duration_ms: int | None = None, result_bytes: int | None = None
             ) -> dict[str, Any]:
    """The model's view of one tool outcome."""
    output = outcome.output if isinstance(outcome.output, dict) else {}
    meta: dict[str, Any] = {"call_id": outcome.call_id}
    if duration_ms is not None:
        meta["duration_ms"] = duration_ms
    if result_bytes is not None:
        meta["result_bytes"] = result_bytes
    warnings = [{"code": code, "fields": output[key]} for key, code in EXTRA_WARNINGS.items() if output.get(key)]
    if not outcome.ok:
        error = output.get("error") if isinstance(output.get("error"), dict) else {}
        details = {k: v for k, v in error.items() if k not in ("code", "message", "next_action")} or None
        return {"status": "ERROR", "tool": outcome.name, "data": None, "warnings": warnings,
                "errors": [_error(error.get("code") or outcome.error_code, error.get("message"),
                                  error.get("next_action"), details)],
                "meta": meta | {"truncated": False}}
    result = output.get("result") if "result" in output else output
    errors: list[dict[str, Any]] = []
    status = "OK"
    if isinstance(result, dict):
        result_status = str(result.get("status") or result.get("execution_status") or "")
        error = result.get("error") if isinstance(result.get("error"), dict) else None
        if result_status.startswith("REJECTED") or result_status in REJECTED_STATUSES:
            status = "REJECTED"
            errors.append(_error((error or {}).get("code") or result_status, (error or {}).get("message")
                                 or result.get("message"), result.get("next_action")))
        elif error is not None:
            status = "REJECTED"
            errors.append(_error(error.get("code"), error.get("message"), result.get("next_action")))
        elif result_status in PARTIAL_STATUSES:
            status = "PARTIAL"
    truncated = _truncated(result)
    if truncated and status == "OK":
        status = "PARTIAL"
    return {"status": status, "tool": outcome.name, "data": result, "warnings": warnings, "errors": errors,
            "meta": meta | {"truncated": truncated}}
