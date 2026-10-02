"""IN_SAMPLE (speed plan step 9 item 2, user decision 2026-10-02: flag, do not refuse).

A hypothesis suggested by an analysis and then tested on the same data is almost bound to look supported (data
snooping). A research finding of this conversation is marked IN_SAMPLE, and the answer says so with the overlap, when
its test
- reads a table over a period an earlier analysis of the conversation read too (from the two data contracts: tables and
  date ranges in the data record and the research data plan), or
- loads a released table of an earlier result (load_output; the sandbox's completion lists each one it loaded), which
  is by construction data an earlier step already looked at.
It is derived from contracts and the sandbox's access log, never from the model's wording; it applies to every table,
including later cross-asset and macro data.
"""
from __future__ import annotations

from typing import Any


def _overlap(a: tuple[str, str], b: tuple[str, str]) -> bool:
    return bool(a[0] and a[1] and b[0] and b[1]) and max(a[0], b[0]) <= min(a[1], b[1])


def analysis_ranges(record: dict[str, Any], request_id: str) -> list[dict[str, Any]]:
    """Tables and ranges earlier analysis needs of the conversation read (not this request's own)."""
    found = []
    for need in record.get("needs") or []:
        if need.get("mode") == "RESEARCH" or need.get("request_id") == request_id:
            continue
        for request in need.get("requests") or []:
            for window in request.get("ranges") or []:
                found.append({"table": request.get("source_table"), "start": window.get("start"),
                              "end": window.get("end"), "request_id": need.get("request_id")})
    return found


def research_ranges_v1(record: dict[str, Any], request_id: str) -> list[dict[str, Any]]:
    """The RESEARCH needs this request submitted (a hypothesis plan's data)."""
    return [{"table": r.get("source_table"), "start": w.get("start"), "end": w.get("end")}
            for need in record.get("needs") or [] if need.get("mode") == "RESEARCH"
            and need.get("request_id") == request_id
            for r in need.get("requests") or [] for w in r.get("ranges") or []]


def research_ranges_v2(data_plan: dict[str, Any], angle_id: str) -> list[dict[str, Any]]:
    """An angle's data contract in the approved research data plan."""
    contract = (data_plan.get("angle_data_contracts") or {}).get(angle_id) or {}
    return [{"table": d.get("source_table"), "start": w.get("start"), "end": w.get("end")}
            for d in contract.get("datasets") or [] for w in d.get("ranges") or []]


def overlaps(analysis: list[dict[str, Any]], research: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each research range that an earlier analysis range of the same table overlaps."""
    found = []
    for test in research:
        for seen in analysis:
            if test["table"] == seen["table"] and _overlap((test["start"], test["end"]), (seen["start"], seen["end"])):
                found.append({"table": test["table"], "research_range": [test["start"], test["end"]],
                              "analysis_range": [seen["start"], seen["end"]],
                              "analysis_request_id": seen["request_id"]})
    return found


def carried(used: list[dict[str, Any]], record: dict[str, Any]) -> list[dict[str, Any]]:
    """The earlier results a test loaded (the completion's carried_inputs), with their refs from the data record."""
    refs = {str(o.get("output_id")): o for o in record.get("outputs") or []}
    found = []
    for entry in used or []:
        output_id = str(entry.get("output_id") or "")
        if not output_id:
            continue
        known = refs.get(output_id) or {}
        found.append({"table": entry.get("name") or output_id, "carried_output": known.get("ref") or output_id,
                      "kind": entry.get("kind"), "label": entry.get("label"),
                      "analysis_request_id": known.get("request_id")})
    return found


def describe(entry: dict[str, Any]) -> str:
    if entry.get("carried_output"):
        return f"{entry['carried_output']} \"{entry['table']}\", an earlier result loaded as test data"
    return (f"{entry['table']} {entry['research_range'][0]} to {entry['research_range'][1]} against "
            f"{entry['analysis_range'][0]} to {entry['analysis_range'][1]}")


def details(in_sample: dict[str, list[dict[str, Any]]], limit: int = 3) -> str:
    """The distinct overlaps behind the flagged findings, at most limit of them (the rest counted, not cut silently)."""
    seen: list[str] = []
    for entries in in_sample.values():
        for entry in entries:
            text = describe(entry)
            if text not in seen:
                seen.append(text)
    shown = "; ".join(seen[:limit])
    return shown + (f"; {len(seen) - limit} more" if len(seen) > limit else "")


LINE = ("IN_SAMPLE: {ids} were tested on data an earlier step of this conversation already read ({detail}); a "
        "pattern found and tested on the same period tends to look stronger than it is. Read these findings as "
        "exploratory and confirm them on another period or universe.")
