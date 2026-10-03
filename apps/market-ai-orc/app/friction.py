"""The kejedot index (round 2026-10-03, ROUND_PLAN_2026-10-03.md §0): how often a run hit a wall on its way to the
answer, counted by code from what the run already records, so golden tests compare runs without reading logs by hand.

- rejected_tool_calls: tool results the model saw as ERROR or REJECTED (the envelope's own status rule);
- gate_repairs: final answers the gates sent back for repair (state.gate_rejections);
- repeated_data_orders: approved data needs that ask for the same tables and row filters as a need the conversation
  already had (the g7 pattern: ordering the data again instead of reusing it);
- capacity_refusals: SESSION_CAPACITY_EXCEEDED results (S28).
"""
from __future__ import annotations

from typing import Any

from .tools.envelope import envelope
from .tools.registry import ToolOutcome

KEYS = ("rejected_tool_calls", "gate_repairs", "repeated_data_orders", "capacity_refusals")


def empty() -> dict[str, int]:
    return dict.fromkeys(KEYS, 0)


def _need_key(requests: list[Any]) -> frozenset[tuple[str, str]]:
    return frozenset((str(r.get("source_table")), str(r.get("scope_sha256"))) for r in requests
                     if isinstance(r, dict) and r.get("source_table"))


def count_tool(counts: dict[str, int], name: str, outcome: ToolOutcome, record: dict[str, Any]) -> None:
    """Count one tool outcome; record is the conversation's data record (needs of earlier turns and this run)."""
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
