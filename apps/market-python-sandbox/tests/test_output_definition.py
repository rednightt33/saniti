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
    for bad in ("Regular only", {"filter": []}, {"filters": [{"column": "x", "operator": "=="}]},
                {"period": {"from": "2022-01-01"}}, {"thresholds": [1]}):
        with pytest.raises(S.InvalidOutput):
            S._definition(bad)
    with pytest.raises(S.OutputLimitExceeded):
        S._definition({"notes": "x" * (S.DEFINITION_MAX_CHARS + 1)})


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
