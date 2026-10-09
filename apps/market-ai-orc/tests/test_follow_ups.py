"""EXEC-Y Fase 2 (app/follow_ups.py): follow-up questions, insight ideas and a data test after an answer of a data route;
never after a plan, a question, a fact, a pause or a stopped answer; ideas only from the data the conversation read."""
from __future__ import annotations

import json
from datetime import date

from app import follow_ups
from app.schemas import ModeExecution
from test_mode4 import response, run_result

RECORD = {"tables": {"Feature_03_Stock_Broker_Daily": {"read": ["date"]}, "IDX_Stock_Universe": {"read": []}},
          "columns": {"Feature_03_Stock_Broker_Daily": {"date": {}, "foreign_net_value": {}}},
          "coverage": {"Feature_03_Stock_Broker_Daily": {"actual_min_date": "2018-01-02",
                                                         "actual_max_date": "2026-08-31"}}}


def result(final="ANSWER", route=None, name="MODE4", block=None, label="DATA_COVERAGE_VERIFIED", **execution):
    r = run_result("q", response(final, "Asing net jual BBRI Rp 20 triliun."))
    r = r.model_copy(update={"mode4": block, "data_record": RECORD, "evidence_label": label,
                             "execution": r.execution.model_copy(update={
                                 "mode": ModeExecution(mode=4 if name == "MODE4" else 2, name=name, source="ROUTER",
                                                       route=route), **execution})})
    return r


def test_only_answers_of_data_routes_get_suggestions_and_only_explore_gets_a_data_test() -> None:
    assert follow_ups.wanted(result(route="ANALYSIS", name="ANALYSIS")) == (True, False)
    assert follow_ups.wanted(result(route="EXPLORE", block={"round": "FIRST"})) == (True, True)
    assert follow_ups.wanted(result(route="EXPLORE", block={"round": "FIRST"}, label=None)) == (True, False)
    assert follow_ups.wanted(result(block={"round": "ROUTED", "turn_kind": "INSIGHT"})) == (True, False)
    assert follow_ups.wanted(result(route="FACT", block={"round": "FACT"})) == (False, False)
    assert follow_ups.wanted(result(block={"round": "ROUTED", "turn_kind": "CLARIFY"})) == (False, False)
    assert follow_ups.wanted(result("CLARIFICATION", route="EXPLORE", block={"round": "FIRST"}))[0] is False
    waiting = result(route="EXPLORE", block={"round": "FIRST"}).model_copy(update={"status": "AWAITING_CONFIRMATION"})
    assert follow_ups.wanted(waiting) == (False, False)
    assert follow_ups.wanted(result(route="ANALYSIS", name="ANALYSIS", stopped=True)) == (False, False)
    assert follow_ups.wanted(result(route="ANALYSIS", name="ANALYSIS", pause={"cause": "X"})) == (False, False)


def test_ideas_come_only_from_the_data_read_and_never_name_a_table() -> None:
    parsed = follow_ups.Suggestions.model_validate({
        "follow_ups": [{"question": "Kapan rapat BI berikutnya?"}, {"question": "Kapan rapat BI berikutnya?"},
                       {"question": "Berapa isi Feature_03_Stock_Broker_Daily?"}],
        "insight_ideas": [{"question": "Bulan apa jual asing BBRI terbesar?", "tables": ["Feature_03_Stock_Broker_Daily"]},
                          {"question": "Bagaimana harga emas?", "tables": ["Commodity_Gold"]},
                          {"question": "Tanpa tabel?", "tables": []}],
        "data_test": {"hypothesis": "Saham bank turun setelah BI-Rate naik."}})
    assert follow_ups.items(parsed, RECORD, ask_test=True) == [
        {"kind": "FOLLOW_UP", "label": "Kapan rapat BI berikutnya?"},
        {"kind": "INSIGHT_IDEA", "label": "Bulan apa jual asing BBRI terbesar?"},
        {"kind": "DATA_TEST", "label": "Uji dengan data: Saham bank turun setelah BI-Rate naik"}]
    assert all(i["kind"] != "DATA_TEST" for i in follow_ups.items(parsed, RECORD, ask_test=False))


def test_the_call_reads_the_answer_the_data_and_the_news_questions() -> None:
    sent = json.loads(follow_ups.content("Q?", "A.", RECORD, ["Kapan?"], True, "2026-10-09"))
    assert sent["DATA"][0] == {"table": "Feature_03_Stock_Broker_Daily", "columns": ["date", "foreign_net_value"],
                               "from": "2018-01-02", "to": "2026-08-31"}
    assert sent["CANDIDATES"] == ["Kapan?"] and sent["ASK_TEST"] is True and sent["TODAY"] == "2026-10-09"


class Orc:
    def __init__(self, parsed=None, cost=0.002, error=None):
        self.parsed, self.cost, self.error, self.contents = parsed, cost, error, []

    def _today(self):
        return date(2026, 10, 9)

    def suggest_follow_ups(self, request_id, content):
        if self.error:
            raise self.error
        self.contents.append(json.loads(content))
        return self.parsed, {"status": "COMPLETED" if self.parsed else "FAILED", "cost": self.cost}


def test_attach_adds_the_suggestions_and_their_cost_and_never_breaks_the_answer() -> None:
    parsed = follow_ups.Suggestions.model_validate({"follow_ups": [{"question": "Lalu?"}], "insight_ideas": [],
                                                    "data_test": None})
    base = result(route="ANALYSIS", name="ANALYSIS")
    done = follow_ups.attach(Orc(parsed), "Q?", base)
    assert done.follow_ups == [{"kind": "FOLLOW_UP", "label": "Lalu?"}]
    assert abs(done.execution.cost - (base.execution.cost + 0.002)) < 1e-9
    assert "follow_ups" in done.model_dump() and "follow_ups" not in base.model_dump()
    assert follow_ups.attach(Orc(error=RuntimeError("x")), "Q?", base) == base
    assert follow_ups.attach(Orc(None), "Q?", base).follow_ups is None
    fact = result(route="FACT", block={"round": "FACT"})
    orc = Orc(parsed)
    assert follow_ups.attach(orc, "Q?", fact) == fact and orc.contents == []  # no call at all
