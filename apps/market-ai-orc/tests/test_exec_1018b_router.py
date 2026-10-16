"""EXEC-1018B Fase 4 (M176; user 2026-10-16 "3. OK 4. Otomatis"): the turn router sees what each released result and
supporting table holds, the end of the previous answer and the action it offered (E9a, method i); a read-only step
that finds the request needs a calculation hands the same message to a CONTINUE step in the same turn and says so
(E9b); a short yes to the offered action runs that action (E9c)."""
from __future__ import annotations


from app import conversation_router as router
from app import data_record as records
from app.schemas import HistoryMessage, final_response_schema
from test_conversation_router import HISTORY, routed, single
from test_mode4 import m4, response, run_result

OFFER = {"label": "hitung data harian per broker",
         "message": "Hitung data harian per broker untuk ADRO Agustus 2026 dan ekspor ke Excel."}


def record_with(**extra) -> dict:
    record = records.empty()
    record["outputs"] = [
        {"ref": "out.o1", "output_id": "out_a", "name": "top_brokers", "row_count": 5,
         "columns": ["broker", "net_value"], "definition": {"notes": "net buy per broker, August 2026"}},
        {"ref": "out.o2", "output_id": "out_b", "name": "daily_rows", "row_count": 1169, "columns": ["date"],
         "support": {"checksum_sha256": "c" * 64, "keep_until": "2026-11-15"}}]
    record.update(extra)
    return record


def test_the_router_reads_the_tables_the_offer_and_the_end_of_the_answer() -> None:
    history = [*HISTORY[:1], HistoryMessage(role="assistant", content="x" * 3000 + " Mau saya hitung per hari?")]
    seen = router.context(record_with(offer={"request_id": "r1", **OFFER}), history, None)
    assert seen["results"] == ["out.o1 top_brokers: 5 rows; columns broker, net_value; net buy per broker, August 2026"]
    assert seen["supporting_tables"][0].startswith("out.o2 daily_rows: 1169 rows")
    assert seen["pending_offer"] == {"label": OFFER["label"], "message": OFFER["message"]}
    assert len(seen["previous_answer_end"]) == router.ANSWER_END_CHARS
    assert seen["previous_answer_end"].endswith("Mau saya hitung per hari?")
    # a waiting research plan is the suggestion; the asked-back question is read instead of the answer end
    assert "pending_offer" not in router.context(record_with(offer=OFFER), history, {"plan_id": "rp"})
    assert "previous_answer_end" not in router.context(None, history, None, asked="Yang mana?")


def test_the_router_card_names_the_offer_and_the_existing_tables() -> None:
    text = router.router_instructions(True)
    assert "pending_offer" in text and "gas" in text and "supporting table" in text


def test_a_read_only_note_hands_a_calculation_on_when_the_answer_can() -> None:
    clarify = router.read_note(router.NOTES["CLARIFY"])
    assert router.READ_OFFER_SENTENCE not in clarify and "needs_computation" in clarify
    assert "needs_computation" in router.read_note(router.NOTES["CONVERSATIONAL"])
    schema = final_response_schema(False, next_step=True)
    assert {"needs_computation", "offered_action"} <= set(schema["required"])
    assert "needs_computation" not in final_response_schema(False)["properties"]


def test_a_read_only_turn_that_needs_a_calculation_moves_to_continue_in_the_same_turn() -> None:
    clarify = run_result("q3-m4q", response("ANSWER", "Tabel harian belum ada.")).model_copy(
        update={"needs_computation": "data harian per broker belum dihitung"})
    script = {"m4q": clarify, "m4h": run_result("q3-m4h", response("ANSWER", "File harian siap."))}
    wrapper, inner = routed(script, "CLARIFY")
    result = wrapper.run(m4(request_id="q3", message="Minta data hariannya dalam Excel", history=HISTORY))
    assert [r.request_id for r in inner.requests] == ["q3-m4q", "q3-m4h"]
    assert inner.requests[1].message == "Minta data hariannya dalam Excel"
    assert result.mode4["turn_kind"] == "CONTINUE" and "File harian siap." in result.response.answer
    assert any("butuh hitungan baru" in a for a in result.response.assumptions)


def test_a_read_only_answer_without_the_field_is_kept() -> None:
    wrapper, inner = routed(single("m4q"), "CLARIFY")
    result = wrapper.run(m4(request_id="q3", message="Artinya apa?", history=HISTORY))
    assert [r.request_id for r in inner.requests] == ["q3-m4q"] and result.mode4["turn_kind"] == "CLARIFY"


def test_a_short_yes_runs_the_offered_action_and_a_new_offer_replaces_it() -> None:
    offered = run_result("q4-m4n", response("ANSWER", "File siap.")).model_copy(
        update={"offered_action": {"label": "bandingkan dengan Juli", "message": "Bandingkan dengan Juli 2026."}})
    wrapper, inner = routed({"m4n": offered}, "APPROVE", "PENDING_SUGGESTION")
    result = wrapper.run(m4(request_id="q4", message="gas", history=HISTORY),
                         data_record=record_with(offer={"request_id": "q3", **OFFER}))
    assert [(r.request_id, r.message) for r in inner.requests] == [("q4-m4n", OFFER["message"])]
    assert any(OFFER["label"] in a for a in result.response.assumptions)
    assert result.data_record["offer"]["message"] == "Bandingkan dengan Juli 2026."
    assert result.offered_action == {"label": "bandingkan dengan Juli", "message": "Bandingkan dengan Juli 2026."}


def test_approve_without_an_offer_or_plan_stays_continue_on_the_message() -> None:
    wrapper, inner = routed(single("m4n"), "APPROVE")
    result = wrapper.run(m4(request_id="q3", message="Ok coba event study", history=HISTORY),
                         data_record=record_with())
    assert [(r.request_id, r.message) for r in inner.requests] == [("q3-m4n", "Ok coba event study")]
    assert result.data_record["offer"] is None


