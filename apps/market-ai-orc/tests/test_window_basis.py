"""EXEC-M209 steps 1 and 3 (user 2026-10-23): the structured window of a stored Feature column (catalog
window_basis/window_length), shown in COLUMNS, and the system's assumption that such a column counts the stock's own
trading days; added after the run's loop, so no answer gate reads it."""
from __future__ import annotations

import inspect
from contextlib import contextmanager

from app import user_texts as texts
from app.orchestrator import AgentOrchestrator, RunState
from app.schemas import FinalResponse
from app.tools import _windowed_columns, build_default_registry
from app.tools.catalog import WINDOW_NOTE, _columns_v2, is_windowed
from conftest import ScriptedClient, make_settings


def test_a_window_of_several_entity_sessions_counts_and_others_do_not() -> None:
    assert is_windowed({"window_basis": "ENTITY_SESSIONS", "window_length": "20"})
    assert is_windowed({"window_basis": "ENTITY_SESSIONS", "window_length": 14})
    assert not is_windowed({"window_basis": "ENTITY_SESSIONS", "window_length": "1"})
    assert not is_windowed({"window_basis": "ENTITY_SESSIONS", "window_length": None})  # cumulative "all sessions"
    # an exchange-day window would be a different statement to the user, so the entity-session line does not apply
    assert not is_windowed({"window_basis": "EXCHANGE_DAYS", "window_length": "20"})
    assert not is_windowed({}) and not is_windowed({"window_basis": "ENTITY_SESSIONS", "window_length": "x"})


def column_row(name: str, length=None, basis=None) -> dict:
    return {"table_name": "F6", "column_name": name, "description": "d", "data_type": "numeric", "unit": "IDR",
            "table_total": 2, "total_matching": 2, "window_length": length, "window_basis": basis}


def test_columns_show_the_window_where_the_model_reads_the_column() -> None:
    section = _columns_v2([column_row("foreign_net_20d", "20", "ENTITY_SESSIONS"), column_row("ticker")],
                          ["F6"], None, 100_000)
    by_name = {entry["column_name"]: entry for entry in section["by_table"]["F6"]}
    assert by_name["foreign_net_20d"]["window"] == {"length": 20, "basis": "ENTITY_SESSIONS"}
    assert "window" not in by_name["ticker"] and section["window_note"] == WINDOW_NOTE
    plain = _columns_v2([column_row("ticker")], ["F6"], None, 100_000)
    assert "window_note" not in plain


def test_the_window_survives_the_smallest_tier() -> None:
    rows = [column_row(f"c{i}", "20", "ENTITY_SESSIONS") | {"description": "x" * 400} for i in range(40)]
    section = _columns_v2(rows, ["F6"], None, 9_000)
    assert section["detail"] in ("COMPACT", "MINIMAL")
    assert all(entry["window"]["basis"] == "ENTITY_SESSIONS" for entry in section["by_table"]["F6"])


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


def test_the_catalog_check_reads_the_structured_window_and_never_raises() -> None:
    rows = [{"target_table": "F6", "column_name": "foreign_net_20d", "window_basis": "ENTITY_SESSIONS",
             "window_length": "20"},
            {"target_table": "F6", "column_name": "foreign_net_1d", "window_basis": "ENTITY_SESSIONS",
             "window_length": "1"}]
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
