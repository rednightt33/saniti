"""Backtest (P32 layer 3, plan 2026-10-05): the backend's recomputation at complete_analysis.

For every backtest the session recorded (backtest_call_<name>, written only by saniti.backtest), it reads the
declaration (request, ranges, price columns, parameters and the entry/exit signal dates), reads the prices from the
governed bundle files, re-runs runtime/backtest.py and compares the released <name>_trades and <name>_summary tables.

    PASS           the released tables equal the backend's
    FAIL           a table differs (CALCULATION_MISMATCH) or is missing: completion fails until saniti.backtest runs
                   again
    INVALID        a record cannot be read or rebuilt (the reason is named): its tables keep the model's label
    NOT_PERFORMED  the session recorded no backtest

What is verified is the simulation on the governed prices; the signal dates are the model's code (not recomputed).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import research_validation as RV

PREFIX = "backtest_call_"
BACKTEST_VERSION = 1  # runtime/backtest.py VERSION (a test keeps them equal); reported in /v1/runtime
MAX_EXAMPLES = 5


def backtest():
    return RV._module("saniti_runtime_backtest", "backtest.py")


def _last(outputs: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    matches = [o for o in outputs if o.get("name") == name]
    return matches[-1] if matches else None


def validate(*, bundle: dict[str, Any], path_of, outputs: list[dict[str, Any]], outputs_root: Path) -> dict[str, Any]:
    calls = [o for o in outputs if str(o.get("name") or "").startswith(PREFIX)]
    if not calls:
        return {"status": "NOT_PERFORMED", "backtests": [], "verified_output_ids": [], "record_output_ids": []}
    BT = backtest()
    results = []
    for name in dict.fromkeys(str(c["name"])[len(PREFIX):] for c in calls):
        record = _last(calls, PREFIX + name)
        entry: dict[str, Any] = {"name": name, "status": "INVALID", "reason": None, "trades_output_id": None,
                                 "summary_output_id": None, "checked": 0, "mismatched": 0, "examples": []}
        results.append(entry)
        try:
            call = json.loads((outputs_root / record["relative_path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError, TypeError):
            entry["reason"] = "RECORD_UNREADABLE"
            continue
        trades_output = _last(outputs, call.get("trades_output") or f"{name}_trades")
        summary_output = _last(outputs, call.get("summary_output") or f"{name}_summary")
        entry["trades_output_id"] = (trades_output or {}).get("output_id")
        entry["summary_output_id"] = (summary_output or {}).get("output_id")
        if trades_output is None or summary_output is None:
            entry.update(status="FAIL", reason="TRADES_MISSING" if trades_output is None else "SUMMARY_MISSING")
            continue
        delivered = next((d for d in bundle["datasets"] if d["data_request_id"] == call.get("request")), None)
        if delivered is None:
            entry["reason"] = "REQUEST_NOT_IN_BUNDLE"
            continue
        approved = {w["range_id"]: w for w in delivered.get("ranges") or []}
        ranges = call.get("ranges") or []
        if not ranges or any(approved.get(w.get("range_id"), {}).get("start") != w.get("start")
                             or approved.get(w.get("range_id"), {}).get("end") != w.get("end") for w in ranges):
            entry["reason"] = "RANGE_NOT_IN_BUNDLE"
            continue
        try:
            params = BT.parameters(**{k: (call.get("parameters") or {}).get(k)
                                      for k in ("stop", "target", "max_hold", "fee", "unit")})
            columns = call.get("columns") or {}
            entity, time = delivered.get("entity_column"), delivered["time_column"]
            rows = RV._read_request(bundle, delivered["data_request_id"],
                                    list(dict.fromkeys([c for c in (entity, time) if c] + list(columns.values()))),
                                    path_of)
            trades, summary = BT.simulate(rows, entity_column=entity, time_column=time, columns=columns,
                                          ranges=ranges, signals={tuple(p) for p in call.get("signals") or []},
                                          exits={tuple(p) for p in call.get("exits") or []}, params=params)
        except BT.BacktestError as exc:
            entry["reason"] = exc.code
            continue
        except (OSError, ValueError, KeyError, TypeError) as exc:
            entry["reason"] = f"REBUILD_FAILED: {type(exc).__name__}"
            continue
        try:
            import pyarrow.parquet as pq

            released_trades = pq.read_table(outputs_root / trades_output["relative_path"]).to_pylist()
            released_summary = pq.read_table(outputs_root / summary_output["relative_path"]).to_pylist()
        except (OSError, ValueError, KeyError):
            entry.update(status="FAIL", reason="TABLE_UNREADABLE")
            continue
        mismatches = [{"table": "trades", **m} for m in BT.compare(released_trades, trades, "entity",
                                                                   BT.TRADE_COLUMNS)]
        mismatches += [{"table": "summary", **m} for m in BT.compare(released_summary, summary, "entity",
                                                                     BT.SUMMARY_COLUMNS)]
        declared = ((summary_output.get("meta") or {}).get("units") or {}) \
            if isinstance(summary_output.get("meta"), dict) else {}
        if declared != BT.summary_units(params["unit"]):
            mismatches.append({"table": "units", "declared": declared, "expected": BT.summary_units(params["unit"])})
        entry["checked"] = len(trades) * len(BT.TRADE_COLUMNS) + len(summary) * len(BT.SUMMARY_COLUMNS)
        entry["mismatched"] = len(mismatches)
        entry["examples"] = mismatches[:MAX_EXAMPLES]
        entry.update(status="FAIL" if mismatches else "PASS", reason="CALCULATION_MISMATCH" if mismatches else None)
    order = ("FAIL", "INVALID", "PASS")
    status = min((r["status"] for r in results), key=order.index) if results else "NOT_PERFORMED"
    return {"status": status, "backtests": results,
            "verified_output_ids": [i for r in results if r["status"] == "PASS"
                                    for i in (r["trades_output_id"], r["summary_output_id"]) if i],
            "record_output_ids": [c["output_id"] for c in calls if c.get("output_id")]}
