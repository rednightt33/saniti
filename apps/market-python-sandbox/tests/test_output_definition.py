"""H1 (M63, golden test 2026-10-02): every released table or JSON states how it was made, in the DataNeed scope
grammar, so a later turn reads its definition instead of guessing it."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from app import data_need  # noqa: E402
from app.dataneed_service import undefined_outputs  # noqa: E402

import saniti_session as S  # noqa: E402


def test_the_definition_operators_are_the_data_need_operators() -> None:
    assert S.DEFINITION_OPERATORS == data_need.OPERATORS


def test_a_definition_is_validated_and_kept() -> None:
    defined = {"filters": [{"column": "market_board", "operator": "EQ", "value": "Regular"}],
               "period": {"start": "2022-01-03", "end": "2026-08-31"}, "thresholds": {"crash": -1.0}, "notes": "x"}
    assert S._definition(defined) == defined
    assert S._definition({}) == {} and S._definition(None) is None
    for bad in ("Regular only", {"filters": [{"column": "x", "operator": "=="}]}, {"period": {"from": "2022-01-01"}}):
        with pytest.raises(S.InvalidOutput):
            S._definition(bad)
    with pytest.raises(S.OutputLimitExceeded):
        S._definition({"notes": "x" * (S.DEFINITION_MAX_CHARS + 1)})


@pytest.fixture
def warnings():
    S._WARNINGS.clear()
    yield S._WARNINGS
    S._WARNINGS.clear()


def test_a_thresholds_list_or_value_becomes_a_dict_with_a_warning(warnings) -> None:
    """EXEC-BE1-1 (user 2026-10-15): a label the sandbox can read another way no longer fails the execution."""
    named = S._definition({"thresholds": [{"name": "crash_day", "value": -1}, {"label": "window", "value": 20}, 0.05]})
    assert named["thresholds"] == {"crash_day": -1, "window": 20, "threshold_3": 0.05}
    assert S._definition({"thresholds": "return_1d_pct <= -1"})["thresholds"] == {"threshold_1": "return_1d_pct <= -1"}
    assert S._definition({"thresholds": [{"name": "a", "value": 1}, {"name": "a", "value": 2}]})["thresholds"] == {"a": 1, "a_2": 2}
    assert [w["code"] for w in warnings] == ["THRESHOLDS_CONVERTED"] * 3


def test_an_unknown_definition_key_is_kept_in_the_notes_with_a_warning(warnings) -> None:
    kept = S._definition({"filter": [{"column": "board", "operator": "EQ", "value": "RG"}], "notes": "net per day"})
    assert kept["notes"].startswith("net per day; filter: ") and '"board"' in kept["notes"] and "filter" not in kept
    assert S._definition({"method": "median"})["notes"] == 'method: "median"'
    assert [w["code"] for w in warnings] == ["DEFINITION_KEYS_MOVED"] * 2


def test_an_unknown_unit_is_dropped_with_a_warning_and_a_known_one_is_read_in_any_case(warnings) -> None:
    assert S._units({"r": "percent", "p": " P_VALUE ", "x": "DECIMAL", "y": None}, ["r", "p", "x", "y"]) \
        == {"r": "PERCENT", "p": "P_VALUE"}
    assert [w["code"] for w in warnings] == ["UNIT_DROPPED", "UNIT_DROPPED"]
    assert "'x'" in warnings[0]["message"] and "plain number" in warnings[0]["message"]
    with pytest.raises(S.InvalidOutput):  # a unit for a column the output does not have is still refused
        S._units({"missing": "PERCENT"}, ["r"])
    with pytest.raises(S.InvalidOutput):
        S._units(["PERCENT"], ["r"])


def test_completion_names_the_released_results_without_a_definition() -> None:
    outputs = [
        {"name": "a", "type": "TABLE", "meta": {}},
        {"name": "a", "type": "TABLE", "meta": {"definition": {}}},  # emitted again with a definition: fixed
        {"name": "b", "type": "JSON", "meta": {"units": {}}},
        {"name": "chart", "type": "CHART", "meta": {}},
        {"name": "research_input_a1", "type": "TABLE", "meta": {}},  # a backend record
        {"name": "c", "type": "TABLE", "meta": None},
    ]
    assert undefined_outputs(outputs) == ["b", "c"]
