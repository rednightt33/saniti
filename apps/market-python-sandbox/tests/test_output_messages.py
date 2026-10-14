"""EXEC-FASTLANE (user 2026-10-14, "OK" to advice in refusals): an invalid units or definition argument of emit_table
is refused with the right form, so one repair is enough (ma-gates-20261014-s1: t1 thresholds as a list, o1
units={'estimasi': None} for a column holding a ratio in one row and percentage points in another)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import saniti_session as S  # noqa: E402


def test_a_unit_of_none_says_what_to_leave_out_and_how_to_split_a_mixed_column() -> None:
    with pytest.raises(S.InvalidOutput) as refused:
        S._units({"estimasi": None}, ["estimasi"])
    message = str(refused.value)
    assert "units['estimasi'] is None" in message and "Leave out of units a column that is no share" in message
    assert "estimate_ratio and estimate_pp" in message


def test_units_that_are_no_dict_show_an_example() -> None:
    with pytest.raises(S.InvalidOutput, match=r"for example units=\{'return_pct': 'PERCENT'.*got list"):
        S._units(["PERCENT"], None)


def test_thresholds_that_are_no_dict_show_an_example_and_what_came() -> None:
    with pytest.raises(S.InvalidOutput, match=r"definition\['thresholds'\] is a dict .*'window_days': 20.*got list"):
        S._definition({"thresholds": ["p90"]})
    assert S._definition({"thresholds": {"big_buy": "net_buy >= p90"}})["thresholds"] == {"big_buy": "net_buy >= p90"}
