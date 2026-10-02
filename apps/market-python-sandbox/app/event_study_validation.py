"""Event study (G2): the independent recalculation at complete_analysis (user decision 2026-10-02).

It runs in the harness, never in the model's process, and trusts nothing the session computed. For every event study
the session recorded (event_study_call_<name>, written only by saniti.event_study), it reads the declaration, rebuilds
the input from the governed bundle files with runtime/research_inputs.py, recomputes the summary with
runtime/event_study.py, and compares it with the summary table the session released under that name. This is the
Analysis Spec validator's EVENT_STUDY check (runtime/validator.py, CALCULATION_MISMATCH) moved onto the DataNeed
bundle: the released figures are labelled CALCULATION_VERIFIED only when they equal the backend's.

    PASS                  every recorded event study matches (its summary and its events table)
    FAIL                  a released table differs (CALCULATION_MISMATCH) or is missing (SUMMARY_MISSING,
                          EVENTS_MISSING): completion fails until saniti.event_study is run again
    INVALID               a record cannot be read or rebuilt (the reason is named): its tables are released without
                          the CALCULATION_VERIFIED label, as any table the model computed
    NOT_PERFORMED         the session recorded no event study

The summary is FORMULA_AND_STATISTICS_VERIFIED: the event and the outcome are rebuilt from the declaration, not read
from the session.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import research_validation as RV

PREFIX = "event_study_call_"
EVENT_STUDY_VERSION = 1  # runtime/event_study.py VERSION (a test keeps them equal); reported in /v1/runtime
MAX_EXAMPLES = 5


def event_study():
    RV.engines()  # runtime/event_study.py reads the engines under their private name
    return RV._module("saniti_runtime_event_study", "event_study.py")


def _names(dataset: dict[str, Any]) -> list[str]:
    """The delivered column names of a bundle dataset (the manifest lists {name, type, ...})."""
    return [c["name"] if isinstance(c, dict) else c for c in dataset.get("columns") or []]


def _last(outputs: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    matches = [o for o in outputs if o.get("name") == name]
    return matches[-1] if matches else None


def validate(*, bundle: dict[str, Any], path_of, outputs: list[dict[str, Any]], outputs_root: Path) -> dict[str, Any]:
    calls = [o for o in outputs if str(o.get("name") or "").startswith(PREFIX)]
    if not calls:
        return {"status": "NOT_PERFORMED", "studies": [], "verified_output_ids": [], "record_output_ids": []}
    ES, I = event_study(), RV.inputs()
    names = list(dict.fromkeys(str(c["name"])[len(PREFIX):] for c in calls))
    studies = []
    for name in names:
        record = _last(calls, PREFIX + name)
        entry: dict[str, Any] = {"name": name, "status": "INVALID", "reason": None, "summary_output_id": None,
                                 "events_output_id": None, "baseline_output_id": None, "checked": 0, "mismatched": 0,
                                 "examples": []}
        studies.append(entry)
        try:
            call = json.loads((outputs_root / record["relative_path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError, TypeError):
            entry["reason"] = "RECORD_UNREADABLE"
            continue
        summary_output = _last(outputs, call.get("summary_output") or name)
        events_output = _last(outputs, call.get("events_output") or f"{name}_events")
        entry["events_output_id"] = (events_output or {}).get("output_id")
        # 2b (2026-10-02): the baseline rows are released and recomputed too (a record without one predates it)
        baseline_output = _last(outputs, call["baseline_output"]) if call.get("baseline_output") else None
        entry["baseline_output_id"] = (baseline_output or {}).get("output_id")
        if call.get("baseline_output") and baseline_output is None:
            entry.update(status="FAIL", reason="BASELINE_MISSING")
            continue
        # S27 (2026-10-02): the flow table is released and recomputed too (a record without one predates it)
        flow_output = _last(outputs, call["flow_output"]) if call.get("flow_output") else None
        entry["flow_output_id"] = (flow_output or {}).get("output_id")
        if call.get("flow_output") and flow_output is None:
            entry.update(status="FAIL", reason="FLOW_MISSING")
            continue
        entry["summary_output_id"] = (summary_output or {}).get("output_id")
        if summary_output is None or events_output is None:
            entry.update(status="FAIL", reason="SUMMARY_MISSING" if summary_output is None else "EVENTS_MISSING")
            continue
        declaration = call.get("declaration") or {}
        delivered = next((d for d in bundle["datasets"] if d["data_request_id"] == declaration.get("request")), None)
        if delivered is None:
            entry["reason"] = "REQUEST_NOT_IN_BUNDLE"
            continue
        try:
            params = ES.parameters(**{k: (call.get("parameters") or {}).get(k) for k in
                                      ("horizon", "overlap_policy", "baseline", "min_events", "holdout_start")})
            keys = [c for c in (delivered.get("entity_column"), delivered.get("time_column")) if c]
            columns = [c for c in _names(delivered) if c not in keys]
            rows = RV._read_request(bundle, delivered["data_request_id"], list(dict.fromkeys(keys + columns)),
                                    path_of)
            related = {}
            spec = (declaration.get("roles") or {}).get("outcome") or {}
            if isinstance(spec, dict) and isinstance(spec.get("request"), str):
                other = next((d for d in bundle["datasets"] if d["data_request_id"] == spec["request"]), None)
                if other is None:
                    raise I.InputError("REQUEST_NOT_IN_BUNDLE", f"{spec['request']} is not in the bundle.")
                other_keys = [c for c in (other.get("entity_column"), other.get("time_column")) if c]
                other_columns = [c for c in _names(other) if c not in other_keys]
                related[other["data_request_id"]] = {
                    "rows": RV._read_request(bundle, other["data_request_id"],
                                             list(dict.fromkeys(other_keys + other_columns)), path_of),
                    "entity_column": other.get("entity_column"), "time_column": other["time_column"],
                    "columns": other_columns}
            ranges = {w["range_id"]: w for w in delivered.get("ranges") or []}
            chosen = declaration.get("range_id")
            if chosen is not None and chosen not in ranges:
                raise I.InputError("RANGE_NOT_IN_BUNDLE", f"{chosen!r} is not a range of the request.")
            rebuilt, _ = ES.build_input(I, declaration, rows, entity_column=delivered.get("entity_column"),
                                        time_column=delivered["time_column"], columns=columns,
                                        ranges=[w for rid, w in ranges.items() if chosen is None or rid == chosen],
                                        horizon=params["horizon"], unit=call.get("outcome_unit") or "PERCENT",
                                        related=related)
            recomputed, recomputed_events = ES.summarize(rebuilt, params)
        except (I.InputError, ES.EventStudyError) as exc:
            entry["reason"] = getattr(exc, "code", "REBUILD_FAILED")
            continue
        except (OSError, ValueError, KeyError, TypeError) as exc:
            entry["reason"] = f"REBUILD_FAILED: {type(exc).__name__}"
            continue
        try:
            import pyarrow.parquet as pq

            released = pq.read_table(outputs_root / summary_output["relative_path"]).to_pylist()
            released_events = pq.read_table(outputs_root / events_output["relative_path"]).to_pylist()
            released_baseline = pq.read_table(outputs_root / baseline_output["relative_path"]).to_pylist() \
                if baseline_output is not None else None
            released_flow = pq.read_table(outputs_root / flow_output["relative_path"]).to_pylist() \
                if flow_output is not None else None
        except (OSError, ValueError, KeyError):
            entry.update(status="FAIL", reason="TABLE_UNREADABLE")
            continue
        mismatches = ES.compare(released, recomputed)
        # P23: the summary's declared units are part of what is checked (the answer formats its figures by them)
        declared = ((summary_output.get("meta") or {}).get("units") or {}) \
            if isinstance(summary_output.get("meta"), dict) else {}
        expected_units = ES.summary_units(call.get("outcome_unit") or "PERCENT")
        if declared != expected_units:
            mismatches.append({"table": "units", "declared": declared, "expected": expected_units})
        mismatches += [{"table": "events", **m} for m in ES.compare_events(released_events, recomputed_events)]
        checked_baseline = 0
        if released_baseline is not None:
            expected_baseline = ES.baseline_rows(rebuilt, params)
            mismatches += [{"table": "baseline", **m}
                           for m in ES.compare_events(released_baseline, expected_baseline)]
            checked_baseline = len(expected_baseline)
        checked_flow = 0
        if released_flow is not None:
            expected_flow = ES.flow(rebuilt, params)
            mismatches += ES.compare_flow(released_flow, expected_flow)
            checked_flow = len(expected_flow) * (len(ES.FLOW_COLUMNS) - 1)
        entry["checked"] = (len(recomputed) * (len(ES.SUMMARY_COLUMNS) - 1) + len(recomputed_events) + checked_baseline
                            + checked_flow)
        entry["mismatched"] = len(mismatches)
        entry["examples"] = mismatches[:MAX_EXAMPLES]
        entry.update(status="FAIL" if mismatches else "PASS", reason="CALCULATION_MISMATCH" if mismatches else None)
    order = ("FAIL", "INVALID", "PASS")
    status = min((s["status"] for s in studies), key=order.index) if studies else "NOT_PERFORMED"
    return {"status": status, "studies": studies,
            "verified_output_ids": [i for s in studies if s["status"] == "PASS"
                                    for i in (s["summary_output_id"], s["events_output_id"],
                                              s.get("baseline_output_id"), s.get("flow_output_id")) if i],
            "record_output_ids": [c["output_id"] for c in calls if c.get("output_id")]}


def level(result: dict[str, Any], released_ids: list[str]) -> str:
    """The completion's calculation_validation: FORMULA_AND_STATISTICS_VERIFIED when every released output is a table
    of a passed event study, PARTIAL when only some are, NOT_PERFORMED when none is."""
    verified = set(result.get("verified_output_ids") or [])
    if not verified:
        return "NOT_PERFORMED"
    return "FORMULA_AND_STATISTICS_VERIFIED" if set(released_ids) <= verified else "PARTIAL"
