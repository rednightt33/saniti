"""M80 (a), user decision 2026-10-04: the backend's research findings released as one standard output table, so a
finding can be exported, charted and cited (out.oN) like any other result. Derived from the findings the backend
already computed; nothing is recomputed and the model writes none of it.

One row per tested comparison: a multi-angle finding (research findings v2) gives one row per angle; a hypothesis
finding (v1) gives one row per sub-angle (angle_a: difference of means, angle_b: difference of rates)."""
from __future__ import annotations

from typing import Any

NAME = "research_findings_table"
COLUMNS = ("angle", "comparison", "status", "status_reason", "estimate", "ci_low", "ci_high", "p_value", "p_adjusted",
           "effective_sample", "sample_flag", "unit")
UNITS = {"p_value": "P_VALUE", "p_adjusted": "P_VALUE"}  # estimate and CI carry their unit per row (column unit)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _pair(value: Any) -> tuple[float | None, float | None]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return _number(value[0]), _number(value[1])
    return None, None


def rows(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        sample = finding.get("sample") if isinstance(finding.get("sample"), dict) else {}
        if finding.get("hypothesis_id"):  # v1
            units = finding.get("units") if isinstance(finding.get("units"), dict) else {}
            for part, comparison in (("angle_a", "MEAN_DIFFERENCE"), ("angle_b", "RATE_DIFFERENCE")):
                stats = finding.get(part) if isinstance(finding.get(part), dict) else None
                if stats is None:
                    continue
                out.append({"angle": f"{finding['hypothesis_id']}:{part}", "comparison": comparison,
                            "status": finding.get("verdict"), "status_reason": finding.get("verdict_reason"),
                            "estimate": _number(stats.get("difference")), "ci_low": _number(stats.get("ci_low")),
                            "ci_high": _number(stats.get("ci_high")), "p_value": _number(stats.get("p_value")),
                            "p_adjusted": _number(stats.get("p_adjusted")),
                            "effective_sample": _number(sample.get("effective")),
                            "sample_flag": finding.get("sample_flag") or sample.get("flag"),
                            "unit": units.get(f"{part}.difference")})
            continue
        estimates = finding.get("estimates") if isinstance(finding.get("estimates"), dict) else {}
        primary = estimates.get("primary") if isinstance(estimates.get("primary"), dict) else {}
        units = estimates.get("units") if isinstance(estimates.get("units"), dict) else {}
        low, high = _pair(primary.get("ci"))
        out.append({"angle": finding.get("angle_id"), "comparison": estimates.get("kind"),
                    "status": finding.get("status"), "status_reason": finding.get("status_reason"),
                    "estimate": _number(primary.get("estimate")), "ci_low": low, "ci_high": high,
                    "p_value": _number(primary.get("p_value")), "p_adjusted": _number(primary.get("p_adjusted")),
                    "effective_sample": _number(primary.get("effective") if primary.get("effective") is not None
                                                else sample.get("effective")),
                    "sample_flag": sample.get("flag"), "unit": units.get("estimate")})
    return [{column: row.get(column) for column in COLUMNS} for row in out if row.get("angle")]


DEFINITION = {"filters": [], "notes": "Temuan riset yang dihitung backend (bukan kode AI): satu baris per sudut atau "
                                      "perbandingan; estimate, ci_low dan ci_high dalam satuan kolom unit; p_value "
                                      "dan p_adjusted berupa nilai p."}
