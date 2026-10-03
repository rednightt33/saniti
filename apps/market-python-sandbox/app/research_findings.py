"""Research findings v1 (PY_SANDBOX_RESEARCH_FINDINGS_ENABLED): the backend's own sample category and verdict.

A RESEARCH data need is complete only when its session released research_events_<hypothesis_id> (the per-date
aggregates saniti.event_summary() writes). The harness reads that released copy (root-only, checksummed at
collection) and recomputes both angles, the effective sample, the minimum detectable effect, the sample category
and the verdict with runtime/research_stats.py and the approved experiment's declared values: expected direction,
outcome horizon, outcome unit, smallest effect of interest and multiple-testing policy. Nothing the model computed
or passed to event_summary is trusted for these values.
"""
from __future__ import annotations

import json

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


# P26 (golden g6 2026-10-02): the plan's outcome unit was DECIMAL and the outcomes were percent, so a decimal smallest
# effect was compared with a percent minimum detectable effect. An outcome is a return in the approved unit; a return
# whose root mean square is above one whole (100 %) per outcome is not a fraction (the bound of
# research_inputs.outcome_problem). A percent series with very small moves is not detected by this bound.
DECIMAL_RMS_LIMIT = 1.0


def unit_problem(table, outcome_unit: str, outputs: list[dict[str, Any]], outputs_root: Path,
                 hypothesis: str) -> str | None:
    """A reason when the released outcomes are not in the approved outcome unit, else None."""
    import math

    summaries = [o for o in outputs if o.get("name") == f"research_summary_{hypothesis}"]
    if summaries:
        try:
            built = json.loads((outputs_root / summaries[-1]["relative_path"]).read_text(encoding="utf-8")
                               ).get("parameters", {}).get("outcome_unit")
        except (OSError, ValueError, AttributeError):
            built = None
        if built and built != outcome_unit:
            return (f"The approved outcome unit is {outcome_unit}, but research_events_{hypothesis} was built with "
                    f"outcome_unit {built}. Call event_summary (and event_study) again without outcome_unit: they use "
                    "the approved unit.")
    rows = float(table["n"].sum())
    if outcome_unit == "DECIMAL" and rows > 0:
        rms = math.sqrt(max(float(table["total_sq"].sum()), 0.0) / rows)
        if rms > DECIMAL_RMS_LIMIT:
            return (f"The approved outcome unit is DECIMAL (a fraction: 0.03 is three percent), but the released "
                    f"outcomes have a root mean square of {rms:.4g}, a move of more than 100 % per outcome: they look "
                    "like percent. Compute the outcome as a fraction (event_study uses the approved unit when "
                    "outcome_unit is unset), or revise the Research Plan to outcome_unit PERCENT.")
    return None


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
        problem = unit_problem(table, params["outcome_unit"], outputs, outputs_root, hypothesis)
        if problem:
            return {"status": "INVALID", "message": problem}
        summary = stats.summarize(table, **params)
    except Exception as exc:  # noqa: BLE001 - a malformed table is reported, never trusted
        return {"status": "INVALID", "message": f"{wanted} could not be evaluated ({type(exc).__name__}: "
                                                f"{str(exc)[:200]}); rebuild it with event_summary()."}
    # M28 (golden g6 2026-10-02: the first event_summary used outcome > 0 for an approved ">= 3%"): the rule the
    # engine applied, recorded in research_summary_<id>, must be the approved one
    approved_rule = (constraints.get("findings") or {}).get("success_rule")
    if isinstance(approved_rule, dict):
        summaries = [o for o in outputs if o.get("name") == f"research_summary_{hypothesis}"]
        applied = None
        if summaries:
            try:
                applied = json.loads((outputs_root / summaries[-1]["relative_path"]).read_text(encoding="utf-8")
                                     ).get("success_rule")
            except (OSError, ValueError, KeyError, AttributeError):
                applied = None
        if not isinstance(applied, dict) or applied.get("operator") != approved_rule.get("operator") \
                or float(applied.get("value", float("nan"))) != float(approved_rule.get("value")):
            return {"status": "INVALID", "message": (
                f"The approved success rule is outcome {approved_rule.get('operator')} {approved_rule.get('value')}, "
                f"but {wanted} was built with {applied!r}. Call event_summary again without success_above or "
                "success_column (it reads the approved rule), then complete again.")}
    finding = {"hypothesis_id": hypothesis, "version": VERSION, "output_id": matches[-1].get("output_id"),
               "verdict": summary["verdict"], "verdict_reason": summary["verdict_reason"],
               "sample_flag": summary["sample"]["flag"], "angles_disagree": summary["angles_disagree"],
               "sample": summary["sample"], "angle_a": summary["angle_a"], "angle_b": summary["angle_b"],
               "groups": {g: {k: v for k, v in d.items() if k != "sd_of_date_means"}
                          for g, d in summary["groups"].items()},
               "parameters": summary["parameters"],
               "success_definition": (constraints.get("findings") or {}).get("success_definition"),
               # M28: the rule the engine applied (the approved one, checked above), shown instead of the text
               **({"success_rule": approved_rule} if isinstance(approved_rule, dict) else {}),
               # P23: each figure's unit from the approved outcome unit, so the answer cannot show it 100 times off
               "units": stats.summary_units(params["outcome_unit"])}
    return {"status": "OK", "finding": finding}
