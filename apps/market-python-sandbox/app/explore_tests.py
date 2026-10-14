"""EXEC-FASTLANE B3 (PY_SANDBOX_EXPLORE_TESTS_ENABLED; user 2026-10-14: insight tests need no Research Governor "but
should be reliable and trustworthy enough sehingga hasilnya tidak misleading"): the exploratory tests of one analysis,
corrected together.

saniti.explore_test (a research library method run by the research engines on the model's frame) and, in a session
with explore_test, saniti.event_study record one explore_test_call_<name> each. At complete_analysis this module reads
the records of the successful executions and adjusts their p-values together with Benjamini-Hochberg at ALPHA (the
engines' adjust_p_values), so an answer that tried many tests reports how many hold after the correction. Nothing is
recomputed here: the statistics are the session's, labelled exploratory; the correction and the counts are the
backend's.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import research_validation as RV

PREFIX = "explore_test_call_"
EXPLORE_TESTS_VERSION = 1
POLICY = "BENJAMINI_HOCHBERG"
FIELDS = ("name", "source", "method_id", "question", "output", "candidate", "estimate_kind", "estimate", "ci_low",
          "ci_high", "p_value", "effective", "sample_flag", "stability", "outcome_unit", "horizon")


def summarize(*, outputs: list[dict[str, Any]], executions: list[dict[str, Any]], outputs_root: Path
              ) -> dict[str, Any] | None:
    """{version, policy, alpha, count, held, tests: [... p_adjusted, holds]} for the tests of the successful
    executions, or None when the analysis recorded none."""
    ok = {e["execution_id"] for e in executions if e.get("status") == "OK"}
    calls = [o for o in outputs if str(o.get("name") or "").startswith(PREFIX)
             and (o.get("execution_id") in ok or o.get("execution_id") is None)]
    if not calls:
        return None
    latest: dict[str, dict[str, Any]] = {}
    for call in calls:
        latest[str(call["name"])[len(PREFIX):]] = call
    tests = []
    for name, record in latest.items():
        try:
            row = json.loads((outputs_root / record["relative_path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        tests.append({**{k: row.get(k) for k in FIELDS}, "name": name, "record_output_id": record.get("output_id")})
    if not tests:
        return None
    engines = RV.engines()
    p_values = [_number(t.get("p_value")) for t in tests]
    m = len([p for p in p_values if p is not None]) or 1
    adjusted = engines.adjust_p_values(p_values, POLICY, m)
    for test, p in zip(tests, adjusted):
        test["p_adjusted"] = p
        test["holds"] = p is not None and p < engines.ALPHA and test.get("sample_flag") not in ("INSUFFICIENT",
                                                                                              "ANECDOTAL")
    return {"version": EXPLORE_TESTS_VERSION, "policy": POLICY, "alpha": engines.ALPHA, "count": len(tests),
            "held": sum(1 for t in tests if t["holds"]),
            "unstable": sum(1 for t in tests if t.get("stability") == "UNSTABLE"),
            "small_samples": sum(1 for t in tests if t.get("sample_flag") in ("INSUFFICIENT", "ANECDOTAL",
                                                                             "UNDERPOWERED")),
            "record_output_ids": [t["record_output_id"] for t in tests], "tests": tests}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None
