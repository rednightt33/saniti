"""EXEC-R and EXEC-P2 (user approval 2026-10-06, golden test ma-qa-20261006b): the steps after a refusal. R4a: JSON the
lenient decoder cannot read either is refused with its position and the text around it; R5b: the repair budget counts
one model turn once per cause; R5c: a query_metric period may start without an end; P2e: an answer longer than its
target is logged, never refused."""
from __future__ import annotations

import json
import logging

import pytest

from app import mode4
from app.orchestrator import (ANSWER_TABLE_ROWS, ANSWER_TARGET_CHARS, MODE4_PART_TARGET_CHARS, AgentOrchestrator,
                              FinalJsonError, RunState, answer_table_rows, current_answer_target)
from app.schemas import AgentRunRequest, FinalResponse
from app.tools import ToolRegistry, error_outcome
from app.tools.metric import Period
from conftest import ScriptedClient, make_settings
from test_orchestrator import ListHandler


def logged(action):
    logger = logging.getLogger("market_ai_orc")
    handler, previous = ListHandler(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        action()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
    return [json.loads(m) for m in handler.messages]


# ---------------------------------------------------------------- R4a

def test_broken_json_is_refused_with_its_position_and_the_text_around_it() -> None:
    raw = '{"response_type": "ANSWER", "answer": "naik "tajam" kemarin", "limitations": []}'
    with pytest.raises(FinalJsonError) as raised:
        AgentOrchestrator._parse_final_output(raw)
    message = str(raised.value)
    assert message.startswith("Final response is not valid JSON: Expecting ',' delimiter at line 1 column 46")
    assert '\\"naik \\"<<HERE>>tajam' in message  # the marked spot, as JSON text
    assert "control character" not in message  # P3d: the strict parser's message pointed elsewhere


def test_a_raw_line_break_inside_a_string_is_still_accepted() -> None:
    raw = '{"response_type": "ANSWER", "answer": "Baris satu\nBaris dua", "assumptions": [], "limitations": []}'
    assert AgentOrchestrator._parse_final_output(raw).answer == "Baris satu\nBaris dua"


# ---------------------------------------------------------------- R5b

def test_parallel_refusals_of_one_turn_spend_one_repair() -> None:
    """06b lang_ticker_only (M88): four parallel query_metric refusals in one turn closed the tool for the run."""
    orc = AgentOrchestrator(make_settings(AI_MAX_REPAIR_ATTEMPTS="2"), ScriptedClient([]), ToolRegistry())
    state = RunState(request_id="r5b", started=0.0, input_items=[])

    def refuse(call: str) -> str | None:
        outcome = orc._repair_budget(state, call, "query_metric",
                                     error_outcome(call, "query_metric", "INVALID_ARGUMENTS", "period"))
        return outcome.error_code

    state.iterations = 1
    assert [refuse(f"c{i}") for i in range(4)] == ["INVALID_ARGUMENTS"] * 4
    state.iterations = 2
    assert refuse("c5") == "INVALID_ARGUMENTS"
    state.iterations = 3
    assert refuse("c6") == "REPAIR_BUDGET_EXHAUSTED"
    assert state.repairs == {"query_metric:INVALID_ARGUMENTS": 3}


# ---------------------------------------------------------------- R5c

def test_a_metric_period_may_start_without_an_end() -> None:
    assert Period.model_validate({"trading_days": None, "start_date": "2026-01-02", "end_date": None}).end_date is None
    assert Period.model_validate({"trading_days": 20, "start_date": None, "end_date": None}).trading_days == 20
    for invalid in ({"trading_days": None, "start_date": None, "end_date": "2026-01-02"},
                    {"trading_days": 20, "start_date": "2026-01-02", "end_date": None},
                    {"trading_days": None, "start_date": None, "end_date": None}):
        with pytest.raises(ValueError, match="give trading_days, or start_date"):
            Period.model_validate(invalid)


# ---------------------------------------------------------------- P2e

TABLE = "| Broker | Hari |\n|---|---|\n" + "".join(f"| B{i} | {i} |\n" for i in range(12))


def test_table_rows_count_the_longest_table_without_header_and_separator() -> None:
    assert answer_table_rows(TABLE) == 12
    assert answer_table_rows("Teks.\n| a |\n|:-:|\n| 1 |\n\n| b |\n|---|\n| 1 |\n| 2 |") == 2
    assert answer_table_rows("Tanpa tabel.") == 0


def test_a_long_answer_is_logged_and_delivered_unchanged() -> None:
    orc = AgentOrchestrator(make_settings(), ScriptedClient([]), ToolRegistry())
    state = RunState(request_id="p2e", started=0.0, input_items=[])
    long = FinalResponse(response_type="ANSWER", answer="x" * (ANSWER_TARGET_CHARS + 1), clarification_question=None,
                         assumptions=[], limitations=[])
    short = long.model_copy(update={"answer": "Ringkas."})
    events = logged(lambda: (orc._finalize_findings(state, long), orc._finalize_findings(state, short)))
    flagged = [e for e in events if e["event"] == "ai_answer_long"]
    assert len(flagged) == 1 and flagged[0]["chars"] == ANSWER_TARGET_CHARS + 1
    assert flagged[0]["target_chars"] == ANSWER_TARGET_CHARS and flagged[0]["target_rows"] == ANSWER_TABLE_ROWS
    assert orc._finalize_findings(state, long) == long
    table = short.model_copy(update={"answer": TABLE})
    events = logged(lambda: orc._finalize_findings(state, table))
    assert [e["table_rows"] for e in events if e["event"] == "ai_answer_long"] == [12]


def test_a_mode4_step_measures_each_part_against_its_own_target(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    class Inner:
        clock = staticmethod(lambda: 0.0)

        def run(self, request, key, data_record=None):
            seen.append(current_answer_target.get())
            raise RuntimeError("stop")

    pipeline = mode4._Mode4Run.__new__(mode4._Mode4Run)
    pipeline.inner, pipeline.started, pipeline.steps, pipeline.base_id = Inner(), 0.0, [], "m4"
    pipeline.settings = make_settings()
    pipeline.request = AgentRunRequest(request_id="m4", conversation_id="c", message="BBCA")
    pipeline.key, pipeline.record, pipeline.router_usage = None, None, None
    with pytest.raises(RuntimeError):
        pipeline.sub("analysis", "m4a", "BBCA", "ANALYSIS")
    assert seen == [MODE4_PART_TARGET_CHARS] and current_answer_target.get() == ANSWER_TARGET_CHARS
