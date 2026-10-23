"""EXEC-M209 step 3 (user 2026-10-23): the system's assumption that a stored Feature column with a window counts the
stock's own trading days; added after the run's loop, so no answer gate reads it."""
from __future__ import annotations

import inspect
from contextlib import contextmanager

from app import user_texts as texts
from app.orchestrator import AgentOrchestrator, RunState
from app.schemas import FinalResponse
from app.tools import _windowed_columns, build_default_registry
from app.tools.catalog import is_windowed
from conftest import ScriptedClient, make_settings


def test_a_window_of_several_observations_counts_and_one_day_does_not() -> None:
    # live lookback_window values (job 2105d567)
    assert is_windowed("20 sessions") and is_windowed("5 ticker transaction dates")
    assert is_windowed("20 trading observations including current observation")
    assert is_windowed("14 valid OHLCV bars; lookback=13")
    assert not is_windowed("1 source date") and not is_windowed("1 session")
    assert not is_windowed("Current trading observation") and not is_windowed(None)


class Reader:
    def __init__(self, rows=None, fail=False) -> None:
        self.rows, self.fail = rows or [], fail

    @contextmanager
    def read_only(self):
        if self.fail:
            raise RuntimeError("database down")

        def run(_sql, _params):
            return self.rows
        yield run


def test_the_catalog_check_reads_the_lookback_and_never_raises() -> None:
    rows = [{"target_table": "F6", "column_name": "foreign_net_20d", "lookback_window": "20 sessions"},
            {"target_table": "F6", "column_name": "foreign_net_1d", "lookback_window": "1 session"}]
    check = _windowed_columns(Reader(rows))
    assert check([("F6", "foreign_net_20d"), ("F6", "ticker")])
    assert not check([("F6", "foreign_net_1d")])
    assert not check([])
    assert not _windowed_columns(Reader(fail=True))([("F6", "foreign_net_20d")])


def orchestrator(windowed: bool) -> AgentOrchestrator:
    registry = build_default_registry()
    registry.windowed_columns = lambda pairs: windowed and ("F6", "foreign_net_20d") in pairs
    return AgentOrchestrator(make_settings(), ScriptedClient([]), registry)


def state_with_need(request_id: str = "r1") -> RunState:
    state = RunState(request_id="r1", started=0.0, input_items=[])
    state.data_record["needs"] = [{"need_id": "need_1", "request_id": request_id, "requests": [
        {"source_table": "F6", "columns": ["ticker", "trade_date", "foreign_net_20d"]}]}]
    return state


def answer(kind: str = "ANSWER") -> FinalResponse:
    question = "Papan mana yang dimaksud?" if kind == "CLARIFICATION" else None
    return FinalResponse(response_type=kind, answer="BBRI paling besar.", clarification_question=question,
                         assumptions=["papan Regular"], limitations=[])


def test_the_line_is_added_by_the_system_when_the_need_asked_for_a_windowed_column() -> None:
    out = orchestrator(True)._with_window_basis(state_with_need(), answer())
    assert out.assumptions == ["papan Regular", texts.WINDOW_BASIS_LINE]
    assert out.answer == "BBRI paling besar." and out.response_type == "ANSWER"
    again = orchestrator(True)._with_window_basis(state_with_need(), out)
    assert again.assumptions.count(texts.WINDOW_BASIS_LINE) == 1


def test_no_line_for_daily_columns_another_runs_need_or_a_clarification() -> None:
    assert orchestrator(False)._with_window_basis(state_with_need(), answer()).assumptions == ["papan Regular"]
    assert orchestrator(True)._with_window_basis(state_with_need("r0"), answer()).assumptions == ["papan Regular"]
    assert orchestrator(True)._with_window_basis(state_with_need(), answer("CLARIFICATION")).assumptions \
        == ["papan Regular"]


def test_the_line_is_added_after_the_loop_that_holds_every_answer_gate() -> None:
    source = inspect.getsource(AgentOrchestrator)
    assert source.index("final = self._loop(state)") < source.index("final = self._with_window_basis(state, final)")
