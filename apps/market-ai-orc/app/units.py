"""Units of research thresholds (P26, round 2026-10-03; ROUND_PLAN_2026-10-03.md B2).

A threshold in a Research Plan (min_effect, success_rule.value) is compared with an outcome computed in the
experiment's outcome_unit. Golden test g6 (2026-10-02) wrote the user's "one point" as 0.01 with outcome_unit DECIMAL
and the "+3%" success rule as 3.0 in the same plan, while the data was in percent: the minimum detectable effect 2.82
(percent) was compared with 0.01 and the recommended sample came out 14,868,205 instead of about 1,487. A threshold
therefore carries its own unit; the backend converts it to the outcome's unit, and a threshold whose unit is not
stated and whose size is implausible for that outcome unit is refused instead of guessed.
"""
from __future__ import annotations

from typing import Literal

ThresholdUnit = Literal["PERCENT", "DECIMAL", "BASIS_POINT"]
THRESHOLD_UNITS: tuple[str, ...] = ("PERCENT", "DECIMAL", "BASIS_POINT")
# how many of each unit make one whole (a return of 1.0 as a fraction)
PER_WHOLE = {"DECIMAL": 1.0, "PERCENT": 100.0, "BASIS_POINT": 10_000.0}
# |value| outside these bounds, with no unit stated, is not taken as written: in DECIMAL a threshold of one or more
# is a return of 100 % or more; in PERCENT a threshold below a tenth is a return below 0.1 % (usually a fraction
# written in the wrong unit). The plan must then name the unit; an explicit unit is always honoured.
AMBIGUOUS = {"DECIMAL": lambda v: abs(v) >= 1.0, "PERCENT": lambda v: 0 < abs(v) < 0.1}


class UnitError(ValueError):
    """A threshold that cannot be expressed in the outcome's unit, with the numbers in the message."""


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """value in from_unit expressed in to_unit (0.03 DECIMAL = 3 PERCENT = 300 BASIS_POINT)."""
    if from_unit not in PER_WHOLE or to_unit not in PER_WHOLE:
        raise UnitError(f"{value:g} {from_unit} cannot be expressed in {to_unit}: only PERCENT, DECIMAL and "
                        "BASIS_POINT convert into each other.")
    return float(value) * PER_WHOLE[to_unit] / PER_WHOLE[from_unit]


def in_outcome_unit(value: float | None, unit: str | None, outcome_unit: str, field: str) -> float | None:
    """The threshold in the outcome's unit. unit None means the outcome's own unit (plans written before P26)."""
    if value is None:
        return None
    if unit is None:
        if outcome_unit in AMBIGUOUS and AMBIGUOUS[outcome_unit](float(value)):
            other = "PERCENT" if outcome_unit == "DECIMAL" else "DECIMAL"
            raise UnitError(
                f"{field} {value:g} has no unit and the outcome unit is {outcome_unit}, which would make it "
                f"{convert(value, outcome_unit, 'PERCENT'):g} percent. State its unit: {field} unit {other} if the "
                f"user meant {value:g} {other.lower()}, or {outcome_unit} if {value:g} {outcome_unit.lower()} is meant.")
        return float(value)
    if outcome_unit not in PER_WHOLE:
        raise UnitError(f"{field} {value:g} is in {unit}, but the outcome unit is {outcome_unit}, which is not a "
                        "return: a percent, decimal or basis-point threshold cannot be compared with it. Use outcome "
                        "unit PERCENT or DECIMAL for a return, or leave the threshold's unit null.")
    return convert(value, unit, outcome_unit)
