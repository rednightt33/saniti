"""M80 (a): the backend's research findings flattened into one table (findings v2 per angle, hypothesis v1 per sub-angle);
nothing is recomputed, a missing statistic stays empty, and a non-finite number is never written."""
from __future__ import annotations

from app import findings_table


V2 = {"angle_id": "sustained_breadth", "status": "INSUFFICIENT_EVIDENCE", "status_reason": "UNDERPOWERED",
      "sample": {"flag": "UNDERPOWERED", "effective": 418},
      "estimates": {"kind": "MEAN_DIFFERENCE", "units": {"estimate": "PERCENT", "p_value": "P_VALUE"},
                    "primary": {"estimate": -0.135, "ci": [-0.65, 0.38], "p_value": 0.61, "p_adjusted": 0.61,
                                "effective": 418}}}
V1 = {"hypothesis_id": "foreign_buy", "verdict": "NOT_SUPPORTED", "verdict_reason": "EFFECT_BELOW_MINIMUM",
      "sample_flag": "ADEQUATE", "sample": {"effective": 1026},
      "angle_a": {"difference": -0.05, "ci_low": -0.2, "ci_high": 0.1, "p_value": 0.4},
      "angle_b": {"difference": 0.01, "ci_low": float("nan"), "ci_high": None, "p_value": 0.7},
      "units": {"angle_a.difference": "PERCENT", "angle_b.difference": "FRACTION"}}


def test_a_multi_angle_finding_is_one_row_with_its_unit() -> None:
    [row] = findings_table.rows([V2])
    assert row == {"angle": "sustained_breadth", "comparison": "MEAN_DIFFERENCE", "status": "INSUFFICIENT_EVIDENCE",
                   "status_reason": "UNDERPOWERED", "estimate": -0.135, "ci_low": -0.65, "ci_high": 0.38,
                   "p_value": 0.61, "p_adjusted": 0.61, "effective_sample": 418.0, "sample_flag": "UNDERPOWERED",
                   "unit": "PERCENT"}


def test_a_hypothesis_finding_is_one_row_per_sub_angle_and_nan_stays_empty() -> None:
    a, b = findings_table.rows([V1])
    assert (a["angle"], a["comparison"], a["status"], a["unit"]) == ("foreign_buy:angle_a", "MEAN_DIFFERENCE",
                                                                    "NOT_SUPPORTED", "PERCENT")
    assert b["unit"] == "FRACTION" and b["ci_low"] is None and b["ci_high"] is None and b["p_adjusted"] is None


def test_nothing_usable_gives_no_rows() -> None:
    assert findings_table.rows([{"status": "NOT_RUN"}, "x", None]) == []
