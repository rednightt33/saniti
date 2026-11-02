"""EXEC-DATA-DATE (user 2026-11-02): a conversation pinned to an older data date never uses that date in silence when a
requested table already has newer data. The model chooses NEWEST or CONVERSATION, or asks the user; the answer's first
line names the date (tests/test_result_store.py)."""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from app.tools import analysis
from app.tools.analysis import DataDate, current_data_date, data_date_choice, take_data_date_policy
from app.tools.preview import newest_date


def spec(table: str = "IDX_Broker_Summary", end: str = "LATEST") -> dict:
    return {"data_requests": [{"data_request_id": "a", "source_table": table,
                               "time_ranges": [{"range_id": "r", "start": "2026-10-01", "end": end}]}]}


@pytest.fixture
def pinned():
    reads: list[str] = []

    def reader(table: str) -> str | None:
        reads.append(table)
        return {"IDX_Broker_Summary": "2026-11-02", "Price_Stock_Indonesia_IDX": "2026-10-27"}.get(table)

    analysis.set_newest_date_reader(reader)
    token = current_data_date.set(DataDate("2026-10-27"))
    try:
        yield reads
    finally:
        current_data_date.reset(token)
        analysis.set_newest_date_reader(None)


def test_newer_data_with_no_choice_is_refused_with_both_dates_and_the_way_to_pass(pinned) -> None:
    refused = data_date_choice(spec(), None)
    assert refused is not None and refused["status"] == "REVISION_REQUIRED"
    [issue] = refused["issues"]
    assert issue["code"] == "DATA_DATE_CHOICE_REQUIRED" and issue["field_path"] == "data_as_of_policy"
    assert issue["conversation_data_date"] == "2026-10-27"
    assert issue["newest_data_date"] == {"IDX_Broker_Summary": "2026-11-02"}
    for part in ("2026-10-27", "2026-11-02", "NEWEST", "CONVERSATION", "CLARIFICATION", "Example"):
        assert part in issue["message"]
    data_date_choice(spec(), None)
    assert pinned == ["IDX_Broker_Summary"]  # read once per run


def test_no_newer_data_keeps_the_pin_without_a_question(pinned) -> None:
    assert data_date_choice(spec("Price_Stock_Indonesia_IDX"), None) is None
    assert current_data_date.get().newer() == {}


def test_newest_passes_and_lifts_the_pin(pinned) -> None:
    payload = {**spec(), "data_as_of_policy": "NEWEST"}
    policy = take_data_date_policy(payload)
    assert policy == "NEWEST" and "data_as_of_policy" not in payload
    assert data_date_choice(payload, policy) is None and current_data_date.get().newest
    assert pinned == []


def test_conversation_passes_and_the_newer_date_is_known_for_the_answer(pinned) -> None:
    payload = {**spec(), "data_as_of_policy": "CONVERSATION"}
    policy = take_data_date_policy(payload)
    assert data_date_choice(payload, policy) is None
    data_date = current_data_date.get()
    assert data_date.kept and not data_date.newest and data_date.newer() == {"IDX_Broker_Summary": "2026-11-02"}


def test_an_explicit_end_date_is_not_pinned_and_not_checked(pinned) -> None:
    assert data_date_choice(spec(end="2026-10-27"), None) is None and pinned == []


def test_no_conversation_date_no_check() -> None:
    analysis.set_newest_date_reader(lambda table: "2026-11-02")
    token = current_data_date.set(DataDate(None))
    try:
        assert data_date_choice(spec(), None) is None
    finally:
        current_data_date.reset(token)
        analysis.set_newest_date_reader(None)


def test_an_unreadable_table_never_blocks_the_run() -> None:
    def broken(table: str) -> str | None:
        raise RuntimeError("database unavailable")

    analysis.set_newest_date_reader(broken)
    token = current_data_date.set(DataDate("2026-10-27"))
    try:
        assert data_date_choice(spec(), None) is None
    finally:
        current_data_date.reset(token)
        analysis.set_newest_date_reader(None)


def test_submit_returns_the_refusal_before_anything_reaches_the_sandbox(pinned) -> None:
    from datetime import datetime, timezone

    from app.tools.analysis import RunContext, current_run_context
    from app.tools.data_need import submit_data_need

    class NoSandbox:
        def _call(self, *args, **kwargs):
            raise AssertionError("the sandbox must not be called")

        def _request_id(self) -> str:
            return "rq"

    class Arguments:  # the fields submit_data_need reads, as the validated arguments would carry them
        mode = "ANALYSIS"

        def model_dump(self, mode: str = "json") -> dict:
            return {**spec(), "mode": "ANALYSIS", "research_governance": None, "data_as_of_policy": None}

    arguments = Arguments()
    token = current_run_context.set(RunContext(datetime(2026, 11, 2, 17, tzinfo=timezone.utc), "Asia/Jakarta",
                                               (("user", "akumulasi 3 hari terakhir"),)))
    try:
        refused = submit_data_need(NoSandbox(), arguments)  # type: ignore[arg-type]
    finally:
        current_run_context.reset(token)
    assert refused["issues"][0]["code"] == "DATA_DATE_CHOICE_REQUIRED"


class Reader:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    @contextmanager
    def read_only(self):
        yield lambda sql, params: [{"payload": json.dumps(self.payload)}]


def test_the_newest_date_is_the_first_row_of_the_ordered_preview() -> None:
    order = '"Date" DESC, "Symbol" DESC, "Broker" DESC, "Investor Type" DESC, "Market Board" DESC'
    reader = Reader({"table_name": "IDX_Broker_Summary", "order_by": order, "row_limit": 20,
                     "rows": [{"Date": "2026-11-02", "Symbol": "ZYRX"}, {"Date": "2026-11-02", "Symbol": "ZONE"}]})
    assert newest_date(reader, "IDX_Broker_Summary") == "2026-11-02"  # type: ignore[arg-type]
    assert newest_date(reader, "IDX_Stock_Universe") is None  # type: ignore[arg-type]  (no date column)
    assert newest_date(reader, "Not_A_Table") is None  # type: ignore[arg-type]
    wrong = Reader({"table_name": "IDX_Broker_Summary", "order_by": "something else", "rows": [{"Date": "2026-11-02"}]})
    assert newest_date(wrong, "IDX_Broker_Summary") is None  # type: ignore[arg-type]


def test_the_note_carries_the_data_date_rule_only_when_the_conversation_has_a_data_date() -> None:
    from app import data_record as records

    record = records.empty()
    assert "Data date of this conversation" not in records.full_note(record)
    records.add_output(record, "earlier", alias="o1", output_id="out_" + "3" * 24, session_id="sess_" + "1" * 24,
                       name="top", columns=["ticker"], row_count=2, lineage={"data_as_of": "2026-10-27"})
    for note in (records.full_note(record), records.note(record)):
        assert "Data date of this conversation: its earlier answers used data up to 2026-10-27" in note
        assert "DATA_DATE_CHOICE_REQUIRED" in note and "Never call 2026-10-27 the last available date" in note
