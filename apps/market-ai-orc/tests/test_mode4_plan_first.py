"""EXEC-P1 (user approval 2026-10-06): mode 4's first round stops after the analysis and its Research Plan, which waits
for the user's approval; an approval runs it and a next plan follows only when the user asks for one. EXEC-C items 7
and 8 (with the run memory): the steps hand each other whole texts and the combined answer keeps every part."""
from __future__ import annotations

from app import mode4
from app.conversation_plans import advance
from app.research_plan import ContinuationIn
from app.schemas import FinalResponse
from test_mode4 import (PLAN1, PLAN3, fake_continuation, first_round_script, m4, plan_final, response, run_result,
                        stub)


def test_the_first_round_ends_with_the_plan_waiting_for_approval() -> None:
    wrapper, inner = stub(first_round_script(), auto_research=False)
    result = wrapper.run(m4(request_id="q", conversation_id="conv_1", message="Kenapa broker ZP aktif?"))
    assert [s["step"] for s in result.mode4["steps"]] == ["analysis", "research_plan"]
    assert [r.request_id for r in inner.requests] == ["q-m4a", "q-m4b"]  # no research run, no suggestion
    assert result.status == "AWAITING_CONFIRMATION" and result.continuation.plan_id == "rp_b"
    answer = result.response.answer
    assert answer.index("**Jawaban**") < answer.index(mode4.PLAN_TITLE) and "Rencana tiga sudut." in answer
    assert "**Hasil riset**" not in answer and "Riset tidak dijalankan" not in answer
    assert len(result.response.research_plan.angles) == len(PLAN3.angles)
    # the conversation store keeps B's plan as the pending plan
    state = advance({}, result, "q", 0)
    assert state["research_plan"]["status"] == "PENDING" and state["research_plan"]["plan_id"] == "rp_b"


def test_a_plan_that_could_not_be_made_returns_the_analysis_with_the_reason() -> None:
    script = first_round_script(m4b=run_result("q-m4b", response("LIMITATION", "Data tidak cukup.")))
    wrapper, inner = stub(script, auto_research=False)
    result = wrapper.run(m4(request_id="q", conversation_id="conv_1", message="Kenapa broker ZP aktif?"))
    assert [r.request_id for r in inner.requests] == ["q-m4a", "q-m4b"]
    assert result.status == "COMPLETED" and result.continuation is None
    assert any(n.startswith("Rencana riset tidak dapat dibuat") for n in result.mode4["notes"])


def test_an_approval_runs_the_plan_and_proposes_nothing_unless_asked() -> None:
    script = {"m4c": run_result("q2-m4c", response("ANSWER", "Riset: a_fall mendukung."), turn="EXECUTE_APPROVED",
                                approved="rp_d")}
    wrapper, inner = stub(script, auto_research=False)
    result = wrapper.run(m4(request_id="q2", conversation_id="conv_1", message="setuju",
                            continuation=fake_continuation()))
    assert [r.request_id for r in inner.requests] == ["q2-m4c"]
    assert result.status == "COMPLETED" and result.continuation is None
    assert mode4.NO_SUGGESTION_LINE in result.response.answer
    assert "Riset: a_fall mendukung." in result.response.answer


def test_a_user_who_asks_for_a_next_suggestion_gets_one() -> None:
    script = {"m4c": run_result("q3-m4c", response("ANSWER", "Riset: a_fall mendukung."), turn="EXECUTE_APPROVED",
                                approved="rp_d"),
              "m4d": run_result("q3-m4d", plan_final(PLAN1), turn="PROPOSE", plan_id="rp_next")}
    wrapper, inner = stub(script, auto_research=False)
    result = wrapper.run(m4(request_id="q3", conversation_id="conv_1",
                            message="jalankan, lalu kasih satu usulan lagi", continuation=fake_continuation()))
    assert [r.request_id for r in inner.requests] == ["q3-m4c", "q3-m4d"]
    assert result.status == "AWAITING_CONFIRMATION" and result.continuation.plan_id == "rp_next"


def test_with_the_run_memory_the_plan_step_reads_the_whole_analysis() -> None:
    """EXEC-C item 8: B received the first 5,000 characters of A's answer without its assumptions, limitations and
    methodology; with the run memory it receives all of it (a longer text names where the rest is)."""
    body = "Analisis panjang. " * 400  # about 7,200 characters
    analysis = FinalResponse.model_validate({
        "response_type": "ANSWER", "answer": body, "assumptions": ["Hari bursa saja."],
        "limitations": ["Board digabung."], "methodology": "Net value per broker per hari."})
    script = first_round_script(m4a=run_result("q-m4a", analysis))
    wrapper, inner = stub(script, auto_research=False)
    wrapper.memory = True
    wrapper.run(m4(request_id="q", conversation_id="conv_1", message="Kenapa broker ZP aktif?"))
    context = inner.requests[1].message
    assert body.strip()[-200:] in context  # the whole body, not its first 5,000 characters
    assert "Batasan:\n- Board digabung." in context and "Metodologi:\nNet value per broker" in context


def test_without_the_run_memory_the_plan_step_keeps_the_earlier_cut() -> None:
    body = "x" * 7000
    script = first_round_script(m4a=run_result("q-m4a", response("ANSWER", body)))
    wrapper, inner = stub(script, auto_research=False)
    wrapper.run(m4(request_id="q", conversation_id="conv_1", message="Kenapa broker ZP aktif?"))
    assert "x" * mode4.ANALYSIS_CHARS in inner.requests[1].message
    assert "x" * (mode4.ANALYSIS_CHARS + 1) not in inner.requests[1].message


def test_with_the_run_memory_the_combined_answer_keeps_every_part() -> None:
    """EXEC-C item 7: every assumption and limitation (no 20-item cut) and the methodology of each step, with the plan
    that ran when the round ran it at once (here the suggestion failed, so the research answer is the base)."""
    many = [f"Batasan {i}." for i in range(30)]
    analysis = FinalResponse.model_validate({"response_type": "ANSWER", "answer": "Analisis.", "assumptions": [],
                                             "limitations": many, "methodology": "Langkah analisis."})
    research = FinalResponse.model_validate({"response_type": "ANSWER", "answer": "Riset.", "assumptions": [],
                                             "limitations": [], "methodology": "Langkah riset."})
    script = first_round_script(m4a=run_result("q-m4a", analysis),
                                m4c=run_result("q-m4c", research, turn="EXECUTE_APPROVED", approved="rp_b"),
                                m4d=run_result("q-m4d", response("LIMITATION", "Tidak ada usulan.")))
    wrapper, _ = stub(script, auto_research=True)
    wrapper.memory = True
    result = wrapper.run(m4(request_id="q", conversation_id="conv_1", message="Kenapa broker ZP aktif?"))
    assert all(item in result.response.limitations for item in many)
    assert "Analisis: Langkah analisis." in result.response.methodology
    assert "Riset: Langkah riset." in result.response.methodology
    assert "Rencana yang dijalankan (langkah B)" in result.response.methodology


def test_a_turn_that_ends_with_a_plan_still_hands_its_methodology_to_the_next_turn() -> None:
    """EXEC-C item 7: the plan response has no methodology field; the next turn's history takes the steps' own."""
    from app.conversations import history_text

    analysis = FinalResponse.model_validate({"response_type": "ANSWER", "answer": "Analisis.",
                                             "assumptions": ["Hari bursa saja."], "limitations": ["Board digabung."],
                                             "methodology": "Net value per broker per hari."})
    wrapper, _ = stub(first_round_script(m4a=run_result("q-m4a", analysis)), auto_research=False)
    wrapper.memory = True
    result = wrapper.run(m4(request_id="q", conversation_id="conv_1", message="Kenapa broker ZP aktif?"))
    assert result.response.response_type == "RESEARCH_PLAN_CONFIRMATION" and result.response.methodology is None
    text = history_text({"request_id": "q", "response": result.model_dump(mode="json")}, True)
    assert "Asumsi:\n- Hari bursa saja." in text and "Batasan:\n- Board digabung." in text
    assert "Metodologi:\nAnalisis: Net value per broker per hari." in text


def test_a_reply_to_a_hypothesis_plan_of_step_b_keeps_the_conversations_data_record() -> None:
    """M105: a reply to any mode 4 step's plan now stays in mode 4; a research_plan/v1 (hypothesis) plan still goes to the
    plan-reply reader of the orchestrator, and it gets the conversation's data record (that path used to drop it)."""
    script = {"q2": run_result("q2", response("ANSWER", "Riset jalan."), turn="EXECUTE_APPROVED", approved="rp_v1")}
    wrapper, inner = stub(script, auto_research=False)
    continuation = ContinuationIn.model_construct(kind="RESEARCH_PLAN", plan_id="rp_v1", origin_request_id="q-m4b",
                                                  plan=None, token="t", action=None, revision_instruction=None)
    record = {"needs": [{"need_id": "dn_1"}]}
    result = wrapper.run(m4(request_id="q2", conversation_id="conv_1", message="setuju", continuation=continuation),
                         data_record=record)
    assert [r.request_id for r in inner.requests] == ["q2"] and inner.records == [record]
    assert result.status == "COMPLETED"
