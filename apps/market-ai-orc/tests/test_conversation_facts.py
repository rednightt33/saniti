"""O5 item 1 (EXEC-IMPL-1016 Fase 2; user 2026-10-15: "kadang ada LIFO, yang berlaku adalah message yang dikirimkan
user belakangan. How we handle this?"): the facts a conversation settled (entities, event dates and their meaning,
periods, definitions) are kept in the data record with where they came from. The user's newest statement applies,
then the user's earlier ones, then the database, the web and the AI's own reading; a replaced fact is kept, so the user
can go back to it. Which facts speak of the same thing is the model's judgement; the order is code."""
from __future__ import annotations

from app import conversation_router as router
from app import data_record as records
from app.mode4 import with_user_facts
from app.orchestrator import AgentOrchestrator, RunState
from app.value_refs import ReferenceSources


def change(name: str, text: str, action: str = "REPLACE") -> dict:
    return {"name": name, "value": None, "unit": "NONE", "text": text, "basis": "STATED", "action": action}


def test_the_users_newest_statement_applies_and_the_replaced_one_is_kept() -> None:
    record = records.empty()
    records.add_fact(record, "r1", kind="EVENT_DATE", value="25 November 2025", origin="WEB", subject="MSCI Nov 2025",
                     meaning="EFFECTIVE", sources=["web.w1"])
    records.add_user_facts(record, "r2", {"design_value_changes": [change("EVENT_DATE", "tanggal efektif 25 Nov")]})
    records.add_user_facts(record, "r3", {"design_value_changes": [change("EVENT_DATE", "pakai 24 Nov saja")]})
    applies = records.effective_facts(record)
    assert [(f["origin"], f["value"]) for f in applies] == [("USER", "pakai 24 Nov saja"),
                                                            ("WEB", "25 November 2025")]
    replaced = [f for f in record["facts"] if f.get("superseded_by")]
    assert [f["value"] for f in replaced] == ["tanggal efektif 25 Nov"]  # kept, not deleted
    # "kembali ke yang tadi": the router reads it as a REPLACE with the earlier words
    records.add_user_facts(record, "r4", {"design_value_changes": [change("EVENT_DATE", "tanggal efektif 25 Nov")]})
    assert records.effective_facts(record)[0]["value"] == "tanggal efektif 25 Nov"


def test_add_keeps_and_remove_withdraws_and_an_unrelated_message_changes_nothing() -> None:
    record = records.empty()
    records.add_user_facts(record, "r1", {"design_value_changes": [change("SCOPE", "BBRI dan BMRI")]})
    records.add_user_facts(record, "r2", {"design_value_changes": [change("SCOPE", "tambah BBCA", "ADD")]})
    assert [f["value"] for f in records.effective_facts(record)] == ["tambah BBCA", "BBRI dan BMRI"]
    records.add_user_facts(record, "r3", {"design_value_changes": [change("SCOPE", "tambah BBCA", "REMOVE")]})
    assert [f["value"] for f in records.effective_facts(record)] == ["BBRI dan BMRI"]
    # design values that are not facts (a horizon) and a message without changes leave the facts alone
    before = list(record["facts"])
    records.add_user_facts(record, "r4", {"design_value_changes": [{"name": "OUTCOME_HORIZON", "value": 5,
                                                                    "unit": "DAY", "action": "REPLACE"}]})
    records.add_user_facts(record, "r5", None)
    assert record["facts"] == before


def test_the_order_of_origins_is_code_and_the_note_states_it() -> None:
    record = records.empty()
    for origin in ("AI", "WEB", "DATABASE"):
        records.add_fact(record, "r1", kind="DEFINITION", value=f"{origin} reading", origin=origin)
    records.add_fact(record, "r2", kind="ENTITY_SET", value="BBRI, BMRI", origin="DATABASE", sources=["out.o1"])
    assert [f["origin"] for f in records.effective_facts(record)] == ["DATABASE", "DATABASE", "WEB", "AI"]
    assert [f["kind"] for f in records.effective_facts(record)][0] == "ENTITY_SET"  # kinds in FACT_KINDS order
    for text in (records.note(record), records.full_note(record)):
        assert records.FACTS_HEADER in text and "DEFINITION [WEB, r1]: WEB reading" in text
    kept = records.normalize(records.public(record))
    assert kept["facts"] == record["facts"] and not records.is_empty(kept)
    assert records.normalize({**record, "facts": [{"fact_id": "f9", "kind": "OTHER", "origin": "USER"}]})["facts"] == []


def test_the_list_keeps_active_facts_when_it_is_full() -> None:
    record = records.empty()
    for i in range(records.MAX_CONVERSATION_FACTS + 5):
        records.add_fact(record, f"r{i}", kind="PERIOD", value=f"periode {i}", origin="USER")
    assert len(record["facts"]) == records.MAX_CONVERSATION_FACTS
    assert records.effective_facts(record)[0]["value"] == f"periode {records.MAX_CONVERSATION_FACTS + 4}"


def test_the_stated_facts_enter_the_record_before_the_answering_step() -> None:
    usage = {"design_value_changes": [change("DEFINITION", "pembelian tertinggi maksudnya net")]}
    updated = with_user_facts(None, "r1", usage)
    assert records.effective_facts(updated)[0]["value"] == "pembelian tertinggi maksudnya net"
    assert with_user_facts({"version": 1}, "r2", {"design_value_changes": []}) == {"version": 1}
    # the router sees the facts that apply, so a change can name what it replaces
    assert router.context(updated, [], None)["facts"] == ["DEFINITION: pembelian tertinggi maksudnya net"]


def test_a_facts_origin_is_read_from_its_sources_not_from_the_model() -> None:
    state = RunState(request_id="r", started=0.0, input_items=[])
    state.ref_sources = ReferenceSources()
    state.ref_sources.add("out", "out_dates", {"rows": [{"date": "2025-11-24"}]}, "DATA_COVERAGE_VERIFIED")
    state.ref_sources.alias("out", "o1", "out_dates")
    state.ref_sources.add("web", "w1", {"value": "24 Nov 2025"}, "WEB_FACT")
    assert AgentOrchestrator._fact_origin(state, ["{{out.o1.rows.0.date}}"]) == ("DATABASE", ["out.o1.rows.0.date"])
    assert AgentOrchestrator._fact_origin(state, ["web.w1.value"])[0] == "WEB"
    assert AgentOrchestrator._fact_origin(state, ["out.o9.rows.0.date", "MSCI says so"]) == ("AI", [])
    assert AgentOrchestrator._fact_origin(state, []) == ("AI", [])


def test_the_answers_facts_field_is_in_the_schema_and_taken_out_before_parsing() -> None:
    import json

    from app.schemas import FACTS_PROPERTY, final_response_schema

    schema = final_response_schema(True, True, True, True, True, True, conversation_facts=True)
    assert schema["properties"]["facts"] == FACTS_PROPERTY and "facts" in schema["required"]
    assert "facts" not in final_response_schema(True, True, True, True, True, True)["properties"]
    assert FACTS_PROPERTY["items"]["properties"]["kind"]["enum"] == list(records.FACT_KINDS)
    dropped: dict = {}
    raw = json.dumps({"response_type": "ANSWER", "answer": "a", "clarification_question": None, "assumptions": [],
                      "limitations": [], "facts": [{"kind": "EVENT_DATE", "subject": "MSCI Nov 2025",
                                                    "value": "24 November 2025", "meaning": "IMPLEMENTATION_CLOSE",
                                                    "sources": ["web.w1"]}]})
    parsed = AgentOrchestrator._parse_final_output(raw, dropped)
    assert parsed.answer == "a" and dropped["facts"][0]["meaning"] == "IMPLEMENTATION_CLOSE"
