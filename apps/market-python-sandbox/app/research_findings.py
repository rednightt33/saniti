"""Research findings v1 (PY_SANDBOX_RESEARCH_FINDINGS_ENABLED): the backend's own sample category and verdict.

A RESEARCH data need is complete only when its session released research_events_<hypothesis_id> (the per-date
aggregates saniti.event_summary() writes). The harness reads that released copy (root-only, checksummed at
collection) and recomputes both angles, the effective sample, the minimum detectable effect, the sample category
and the verdict with runtime/research_stats.py and the approved experiment's declared values: expected direction,
outcome horizon, outcome unit, smallest effect of interest and multiple-testing policy. Nothing the model computed
or passed to event_summary is trusted for these values.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

VERSION = 1
EVENTS_OUTPUT = "research_events_{hypothesis_id}"


def _stats():
    name = "saniti_runtime_research_stats"
    if name not in sys.modules:
        location = Path(__file__).resolve().parents[1] / "runtime" / "research_stats.py"
        spec = importlib.util.spec_from_file_location(name, location)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def parameters(constraints: dict[str, Any]) -> dict[str, Any]:
    """The approved experiment's values for research_stats.summarize (declared in research_governance)."""
    findings = constraints.get("findings") or {}
    return {"horizon_periods": int(findings.get("outcome_horizon_periods") or 1),
            "expected_direction": findings.get("expected_direction") or "DIFFERENT",
            "outcome_unit": findings.get("outcome_unit") or "OTHER",
            "min_effect": findings.get("min_effect"),
            "comparisons": max(int(constraints.get("candidate_count") or 1),
                               int(constraints.get("pairwise_comparisons") or 0), 1),
            "multiple_testing_policy": constraints.get("multiple_testing_policy") or "NONE"}


def evaluate(constraints: dict[str, Any], outputs: list[dict[str, Any]], outputs_root: Path) -> dict[str, Any]:
    """{"status": "OK", "finding": {...}} or {"status": "MISSING" | "INVALID", "message": ...}.
    outputs: this epoch's outputs of successful executions, in order (the last matching one counts)."""
    stats = _stats()
    hypothesis = constraints.get("hypothesis_id")
    wanted = EVENTS_OUTPUT.format(hypothesis_id=hypothesis)
    matches = [o for o in outputs if o.get("name") == wanted and str(o.get("format") or "").upper() == "PARQUET"]
    if not matches:
        return {"status": "MISSING", "message": (
            f"Call event_summary(events, baseline, hypothesis_id={hypothesis!r}, outcome_column=..., date_column=...) "
            f"in a successful execution: a research answer needs its released {wanted}.")}
    try:
        import pandas as pd
        import pyarrow.parquet as pq

        table = pq.read_table(outputs_root / matches[-1]["relative_path"]).to_pandas()
        table = table[list(stats.AGGREGATE_COLUMNS)] if set(stats.AGGREGATE_COLUMNS) <= set(table.columns) else table
        table["date"] = table["date"].astype(str)
        for column in ("n", "k", "m"):
            table[column] = pd.to_numeric(table[column], errors="raise").astype("int64")
        for column in ("total", "total_sq"):
            table[column] = pd.to_numeric(table[column], errors="raise").astype("float64")
        if not set(table["group"].unique()) <= set(stats.GROUPS) or (table[["n", "k", "m"]] < 0).any().any() \
                or (table["k"] > table["m"]).any():
            raise ValueError("unexpected groups or counts")
        params = parameters(constraints)
        summary = stats.summarize(table, **params)
    except Exception as exc:  # noqa: BLE001 - a malformed table is reported, never trusted
        return {"status": "INVALID", "message": f"{wanted} could not be evaluated ({type(exc).__name__}: "
                                                f"{str(exc)[:200]}); rebuild it with event_summary()."}
    finding = {"hypothesis_id": hypothesis, "version": VERSION, "output_id": matches[-1].get("output_id"),
               "verdict": summary["verdict"], "verdict_reason": summary["verdict_reason"],
               "sample_flag": summary["sample"]["flag"], "angles_disagree": summary["angles_disagree"],
               "sample": summary["sample"], "angle_a": summary["angle_a"], "angle_b": summary["angle_b"],
               "groups": {g: {k: v for k, v in d.items() if k != "sd_of_date_means"}
                          for g, d in summary["groups"].items()},
               "parameters": summary["parameters"],
               "success_definition": (constraints.get("findings") or {}).get("success_definition"),
               # P23: each figure's unit from the approved outcome unit, so the answer cannot show it 100 times off
               "units": stats.summary_units(params["outcome_unit"])}
    return {"status": "OK", "finding": finding}
