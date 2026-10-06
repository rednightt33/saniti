"""EXEC-C (user decisions 2026-10-06: "Seharusnya AI membawa semuanya tanpa terkecuali", Q1 "pakai MEMO", Q2
"BACKEND + AI"; AI_ENABLE_RUN_MEMORY): every run leaves a memory and every later run of the conversation reads it."""
from __future__ import annotations

import json
from typing import Any

from app import data_record as records
from app import run_memory as memory
from app import tool_desks as desks
from app.conversations import CUT_POINTER_TOOL, assistant_text, fit_text, history_text
from app.orchestrator import AgentOrchestrator, RunState
from app.schemas import AgentRunRequest
from app.tools.registry import ToolOutcome
from conftest import ScriptedClient, final_response, make_settings, tool_call_response
from test_dataneed_orchestrator import Tools, answer, completed, flow

CONVERSATION = "conv_" + "a" * 32


class FakeMemory:
    """MemoryStore in memory: the rows in the order the runs ended."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def save(self, conversation_id: str, turn_request_id: str, run_id: str, **row: Any) -> bool:
        if any(r["run_id"] == run_id for r in self.rows):
            return False
        self.rows.append({"conversation_id": conversation_id, "turn_request_id": turn_request_id, "run_id": run_id,
                          **json.loads(json.dumps(row, default=str))})
        return True

    def load(self, conversation_id: str) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["conversation_id"] == conversation_id]

    def runs(self, conversation_id: str) -> list[dict[str, Any]]:
        return [{k: r.get(k) for k in ("run_id", "status")} for r in self.load(conversation_id)]

    def read(self, conversation_id: str, run_id: str) -> dict[str, Any] | None:
        return next((r for r in self.load(conversation_id) if r["run_id"] == run_id), None)


def agent(script: list, store: FakeMemory, tools: Tools | None = None, **env: str) -> AgentOrchestrator:
    return AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true", **env), ScriptedClient(script),
                             (tools or Tools([completed()])).registry(), run_memory=store)


def request(request_id: str, message: str = "Berapa return YTD BBCA dan BBRI?") -> AgentRunRequest:
    return AgentRunRequest(request_id=request_id, message=message, conversation_id=CONVERSATION)


# ---------------------------------------------------------------------------------------------- memo and note


def facts(run_id: str, **extra: Any) -> dict[str, Any]:
    return {"run_id": run_id, "step": "AUTO", "status": "COMPLETED", "response_type": "ANSWER",
            "at": "2026-10-06 10:00 UTC", "message": "Berapa return YTD?", **extra}


def test_a_memo_names_what_the_run_did_and_where_the_full_texts_are() -> None:
    block = memory.memo_block(facts(
        "t1", tools={"submit_data_need_spec": 2, "run_python": 1}, tools_refused={"submit_data_need_spec": 1},
        released=['out.o1 "ytd" (2 rows)'], decisions=[{"name": "OUTCOME_HORIZON", "value": "10 DAY",
                                                         "origin": "user's words (ADD)"}],
        refusals=[{"stage": "GATE", "name": "REFERENCE", "code": None, "outcome": "REJECTED_FOR_REPAIR",
                   "message": "x" * 500}],
        web=[{"id": "w_1", "subject": "BI rate", "value_as_written": "6,00%", "domain": "bi.go.id",
              "url": "https://bi.go.id"}],
        citable=["fact.1", "web.w_1", "out.o1"], code=[{"execution_id": "exe_1", "status": "OK"}],
        answer="Return YTD BBCA lebih tinggi.", note="BBCA lebih tinggi; BBRI turun.", reasoning_chars=1200))
    assert block.startswith("## t1 (AUTO; COMPLETED, ANSWER; 2026-10-06 10:00 UTC)")
    assert "OUTCOME_HORIZON = 10 DAY (user's words (ADD))" in block
    assert "refused ×1 (full messages and drafts: refusals)" in block and "x" * 500 not in block
    assert "web.w_1 BI rate: 6,00% (bi.go.id, https://bi.go.id)" in block
    assert "citable in later runs under the same address: fact.1, web.w_1, out.o1" in block
    assert "note from this run's model: BBCA lebih tinggi; BBRI turun." in block
    assert "reasoning: 1200 characters (reasoning)" in block


def test_the_memory_note_only_grows_at_its_end() -> None:
    """Append-only (EXEC-S cache): the note of run N+1 starts with the note of run N."""
    memos = [{"run_id": f"t{i}", "memo": memory.memo_block(facts(f"t{i}"))} for i in range(4)]
    notes = [memory.memory_note(memos[:k]) for k in range(1, 5)]
    for shorter, longer in zip(notes, notes[1:]):
        assert longer.startswith(shorter)
    assert notes[0].startswith(memory.MEMORY_HEADER)


def test_memos_beyond_the_budget_are_named_with_a_pointer(monkeypatch) -> None:
    monkeypatch.setattr(memory, "MAX_MEMO_NOTE_CHARS", 200)
    memos = [{"run_id": f"t{i}", "memo": memory.memo_block(facts(f"t{i}"))} for i in range(6)]
    note = memory.memory_note(memos)
    assert "read them with read_conversation_memory" in note and "t0" in note
    assert memos[-1]["memo"] in note


# ---------------------------------------------------------------------------------------------- a run and the next


def test_a_run_leaves_its_memory_and_the_next_run_reads_it_after_the_history() -> None:
    store = FakeMemory()
    script = [*flow(), final_response({**answer("BBCA naik lebih tinggi dari BBRI."),
                                       "memo_note": "Saya membandingkan return YTD; BBCA lebih tinggi."})]
    first = agent(script, store, AI_ENABLE_VALUE_REFERENCES="true").run(request("t1"))
    assert first.status == "COMPLETED" and first.data_record
    row = store.rows[0]
    assert row["run_id"] == "t1" and row["status"] == "COMPLETED"
    assert row["note"] == "Saya membandingkan return YTD; BBCA lebih tinggi."
    assert "note from this run's model: Saya membandingkan" in row["memo"]
    assert row["content"]["answer"]["answer"] == "BBCA naik lebih tinggi dari BBRI."
    assert "memo_note" not in first.model_dump(mode="json")["response"]  # never shown to the user
    assert "hidden" in row["reasoning"]  # the provider's reasoning of the tool calls, kept with the run

    second_agent = agent([final_response(answer("Sudah dijawab sebelumnya."))], store,
                         AI_ENABLE_VALUE_REFERENCES="true")
    second = second_agent.run(request("t2", "lanjut"), data_record=first.data_record)
    assert second.status == "COMPLETED" and [r["run_id"] for r in store.rows] == ["t1", "t2"]
    texts = [i["content"] for i in second_agent.client.payloads[0]["input"] if i.get("role") == "user"]
    memo_at = next(i for i, t in enumerate(texts) if t.startswith(memory.MEMORY_HEADER))
    record_at = next(i for i, t in enumerate(texts) if t.startswith("DATA RECORD"))
    assert memo_at < record_at and "## t1 " in texts[memo_at]
    assert texts[-1] == "lanjut"


def test_the_final_schema_and_contract_ask_for_the_note_only_with_the_memory() -> None:
    with_memory = agent([], FakeMemory())
    assert "memo_note" in with_memory.final_schema["required"]
    assert "memo_note:" in with_memory.response_contract
    without = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), ScriptedClient([]), Tools([]).registry())
    assert "memo_note" not in without.final_schema["properties"] and "memo_note" not in without.response_contract


def test_every_refusal_is_kept_whole_with_its_arguments() -> None:
    orchestrator = agent([], FakeMemory())
    state = RunState(request_id="t", started=0.0, input_items=[])
    refused = ToolOutcome(call_id="c", name="query_metric", ok=True, output={"ok": True, "result": {
        "status": "REJECTED", "error": {"code": "PERIOD_INVALID", "message": "needs start and end " * 40}}})
    orchestrator._remember_tool_refusal(state, "query_metric", '{"metric": "x"}', refused)
    orchestrator._remember_tool_refusal(state, "query_metric", "{}", ToolOutcome(
        call_id="c", name="query_metric", ok=True, output={"ok": True, "result": {"status": "OK"}}))
    assert len(state.refusals) == 1
    entry = state.refusals[0]
    assert entry["code"] == "PERIOD_INVALID" and entry["message"].count("needs start and end") == 40
    assert entry["arguments"] == '{"metric": "x"}'


def test_sources_of_earlier_runs_are_cited_by_the_same_address() -> None:
    """Item 11: fact, metric, reference, web and an earlier table are registered at the start of the run; this run's
    numbering continues after theirs."""
    rows = [{"run_id": "t1", "memo": "m", "sources": {
        "fact": {"3": {"value": 41.5, "label": "FACT"}},
        "metric": {"m2": {"value": {"periods": [{"rows": [{"ticker": "BBCA", "value": 1.25}]}]},
                          "label": "DATABASE_AGGREGATE"}},
        "web": {"r9_1": {"value": {"id": "r9_1", "value": 6.0, "label": "WEB_FACT"}, "label": "WEB_FACT",
                         "units": {"value": "PERCENT"}, "origin": "bi.go.id"}},
        "out": {"out_" + "b" * 24: {"output_id": "out_" + "b" * 24, "content": {"median": 0.02},
                                    "label": "DATA_COVERAGE_VERIFIED"}}}}]
    calls: list[tuple] = []

    def reader(session_id, output_id, request_id, offset, limit):
        calls.append((session_id, output_id))
        return {"released": True, "rows": [{"ticker": "BBCA", "ytd": 0.12}], "row_count": 1}

    orchestrator = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true", AI_ENABLE_VALUE_REFERENCES="true"),
                                     ScriptedClient([]), Tools([]).registry(), run_memory=FakeMemory(),
                                     row_reader=reader)
    state = RunState(request_id="t2", started=0.0, input_items=[{"role": "user", "content": "x"}])
    table = "out_" + "c" * 24
    records.add_output(state.data_record, "t1", alias="o1", output_id=table, session_id="sess_" + "d" * 24,
                       name="ytd", columns=["ticker", "ytd"], row_count=1, label="DATA_COVERAGE_VERIFIED")
    state.ref_aliases, state.ref_next = records.aliases(state.data_record)
    orchestrator._seed_sources(state, rows)
    sources = state.ref_sources
    assert sources.lookup("fact.3").value == 41.5 and state.ref_facts == 3 and state.ref_metrics == 2
    assert sources.lookup("metric.m2.periods[0].rows[0].value").value == 1.25
    assert sources.lookup("web.r9_1.value").label == "WEB_FACT" and 6.0 in state.web_numbers
    assert sources.lookup(f"out.out_{'b' * 24}.content.median").value == 0.02
    assert sources.lookup("out.o1.rows[0].ytd").value == 0.12 and calls  # read when rendered, not before
    state.referenced = ["out.o1.rows[0].ytd"]
    assert orchestrator._cites_carried(state)
    # what this run received is not kept again as its own
    assert memory.serialize_sources(sources, state.carried_sources, {}) == {}


def test_a_failed_run_still_leaves_its_memory() -> None:
    store = FakeMemory()
    failing = agent([RuntimeError("provider down")], store)
    result = failing.run(request("t9"))
    assert result.status == "FAILED" and store.rows[0]["run_id"] == "t9"
    assert store.rows[0]["error_code"] == result.error.code
    assert store.rows[0]["content"]["error"]["code"] == result.error.code


# ---------------------------------------------------------------------------------------------- the read tool


def test_the_read_tool_lists_runs_reads_sections_in_pages_and_the_record() -> None:
    store = FakeMemory()
    store.save(CONVERSATION, "t1", "t1", status="COMPLETED", response_type="ANSWER", error_code=None, memo="## t1",
               content={"answer": {"answer": "a" * 50_000}, "refusals": [{"message": "m"}]}, sources={}, note="n",
               reasoning="r" * 10)
    args = memory.ReadMemoryArgs
    listed = memory.read_memory(store, CONVERSATION, args(run_id=None, section=None, item=None, offset=None))
    assert [r["run_id"] for r in listed["runs"]] == ["t1"]
    page = memory.read_memory(store, CONVERSATION, args(run_id="t1", section="answer", item=None, offset=None))
    assert len(page["text"]) == memory.PAGE_CHARS and page["next_offset"] == memory.PAGE_CHARS
    last = memory.read_memory(store, CONVERSATION, args(run_id="t1", section="answer", item=None, offset=40_000))
    assert last["next_offset"] is None
    assert memory.read_memory(store, CONVERSATION, args(run_id="t9", section=None, item=None,
                                                        offset=None))["code"] == "RUN_NOT_FOUND"
    record = records.empty()
    record["columns"] = {"Feature_01": {"close": {"unit": "IDR", "description": "Harga penutupan."}}}
    catalog = memory.read_memory(store, CONVERSATION, args(run_id=None, section="catalog", item="Feature_01",
                                                           offset=None), record=record)
    assert "Harga penutupan." in catalog["text"]
    assert memory.read_memory(None, CONVERSATION, args(run_id=None, section=None, item=None,
                                                       offset=None))["code"] == "MEMORY_NOT_AVAILABLE"


def test_the_read_tool_is_on_every_desk() -> None:
    registered = frozenset({"read_conversation_memory", "get_session_output", "submit_data_need_spec"})
    for process in desks.DESKS:
        assert "read_conversation_memory" in desks.tools(process, registered, lambda name: "READS"), process


# ---------------------------------------------------------------------------------------------- record and history


def test_the_full_note_is_never_cut_and_carries_the_column_details() -> None:
    record = records.empty()
    for i in range(records.MAX_OUTPUTS):
        records.add_output(record, "t1", alias=f"o{i + 1}", output_id=f"out_{i:024x}", session_id=None,
                           name=f"tabel {i} " + "x" * 60, columns=[f"kolom_{c}" for c in range(12)], row_count=1)
    result = {"sections": {"COLUMNS": {"by_table": {"Feature_01": [
        {"column_name": "close", "description": "Harga penutupan harian.", "unit": "IDR", "data_type": "numeric",
         "resample_aggregation": "LAST"}]}}}}
    records.add_catalog_facts(record, "get_catalog_details", {}, result, "t1", "2026-10-06T10:00:00")
    assert len(records.note(record)) <= records.MAX_NOTE_CHARS  # the earlier note cut itself
    full = records.full_note(record)
    assert all(f"out.o{i + 1} " in full for i in range(records.MAX_OUTPUTS))
    assert "close [IDR] (numeric): Harga penutupan harian.; resample_aggregation=LAST" in full


def test_column_details_beyond_the_budget_are_named_with_a_pointer(monkeypatch) -> None:
    monkeypatch.setattr(records, "COLUMNS_NOTE_CHARS", 120)
    record = records.empty()
    record["columns"] = {f"T{i}": {"c": {"description": "d" * 60}} for i in range(3)}
    full = records.full_note(record)
    assert "details not shown here" in full and "read_conversation_memory" in full


def test_an_answer_keeps_its_tail_and_points_to_the_rest() -> None:
    body, tail = "b" * 30_000, "Asumsi:\n- a\n\nBatasan:\n- l\n\nMetodologi:\nm"
    pointer = CUT_POINTER_TOOL.replace("{request_id}", "t1")
    text = fit_text(body, tail, 16_000, pointer)
    assert len(text) <= 16_000 and text.endswith(tail)
    assert 'read_conversation_memory(run_id="t1", section="answer")' in text
    omitted = int(text.split("[… ")[1].split(" characters")[0])
    assert omitted == 30_000 - text.index(" [… ")


def test_a_failed_turn_is_history_with_how_it_ended() -> None:
    text = history_text({"request_id": "t3", "status": "COMPLETED", "run_status": "FAILED",
                         "error_code": "ANALYSIS_TIMEOUT", "response": {"response": None}}, True)
    assert text.startswith("[No answer: this message ended FAILED (ANALYSIS_TIMEOUT).")
    assert "read_conversation_memory" in text


def test_a_short_answer_is_unchanged() -> None:
    from types import SimpleNamespace

    response = SimpleNamespace(response_type="ANSWER", answer="Jawaban.", clarification_question=None,
                               assumptions=["a"], limitations=[], methodology=None)
    assert assistant_text(SimpleNamespace(response=response, request_id="t")) == "Jawaban.\n\nAsumsi:\n- a"


def test_the_router_reading_is_kept_for_later_turns() -> None:
    record = records.empty()
    records.add_reading(record, "t1", {"route": "ANALYSIS", "understood_intent": "return YTD BBCA",
                                       "design_value_changes": [{"name": "OUTCOME_HORIZON", "action": "ADD"}],
                                       "cost": 0.001})
    assert record["readings"][0] == {"request_id": "t1", "route": "ANALYSIS",
                                     "understood_intent": "return YTD BBCA",
                                     "design_value_changes": [{"name": "OUTCOME_HORIZON", "action": "ADD"}]}
    assert "How the router read earlier messages" in records.full_note(record)
    assert not records.is_empty(record)
    assert records.normalize(record)["readings"] == record["readings"]


def test_the_tool_call_of_a_run_is_told_its_reasoning_is_kept_only_in_memory() -> None:
    """The reasoning goes to the memory, never back to the model (no replay without AI_REPLAY_REASONING)."""
    store = FakeMemory()
    orchestrator = agent([tool_call_response("get_session_output", "{}"), final_response(answer("ok"))], store)
    orchestrator.run(request("t5", "lihat"))
    assert not any(i.get("type") == "reasoning" for p in orchestrator.client.payloads for i in p["input"])
    assert "hidden" in store.rows[0]["reasoning"]
