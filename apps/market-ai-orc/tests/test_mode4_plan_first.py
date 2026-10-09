"""EXEC-P1 (user approval 2026-10-06; its first round replaced by option B, EXEC-Y Fase 2 2026-10-09): mode 4's first round stops after the analysis and its Research Plan, which waits
for the user's approval; an approval runs it and a next plan follows only when the user asks for one. EXEC-C items 7
and 8 (with the run memory): the steps hand each other whole texts and the combined answer keeps every part."""
from __future__ import annotations

from app import mode4
from app.conversation_plans import advance
from app.research_plan import ContinuationIn
from app.schemas import FinalResponse
from test_mode4 import (PLAN1, PLAN3, fake_continuation, first_round_script, m4, plan_final, response, run_result,
                        stub)


NEWS = {"status": "ANSWERED", "seconds": 42.0, "usage": {"cost_usd": 0.031},
        "answer_cited": "**Riwayat**\nBI menaikkan suku bunga pada 2025-11-20 [1][2].\nAngka 7% tanpa sumber.\n"
                        "Belum ada keputusan baru.\n\n## Implikasi & yang perlu dipantau\n- Dampak [1]\n\n"
                        "## Pertanyaan lanjutan\n1. Apa berikutnya?",
        "citations": [{"n": 1, "publisher": "Kontan", "url": "https://kontan.co.id/a", "date": "2025-11-20"},
                      {"n": 2, "publisher": "Bisnis", "url": "https://bisnis.com/b", "date": "2025-11-21"}],
        "plan": {"implications": {"timeline": [
                     {"event": "Rapat BI berikutnya", "when_text": "18 November 2026", "status": "dijadwalkan",
                      "sources": [2]},
                     {"event": "Tanpa sumber", "when_text": "2027", "status": "diusulkan", "sources": []}]},
                 "follow_ups": [{"question": "Kapan rapat BI berikutnya?", "why": "x"}]}}


class FakeNews:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def ask(self, request_id, question, as_of):
        self.calls.append((request_id, question, as_of))
        if self.error:
            raise self.error
        return self.result


def test_option_b_the_first_round_is_the_answer_with_the_news_and_no_plan() -> None:
    """EXEC-Y Fase 2 (user 2026-10-09 "explore pakai B"): no research plan is built in the first round; /v1/ask runs next
    to the analysis and the backend writes its sections (every sentence linked, an unsourced figure dropped, upcoming
    events with their source); its cost counts in the turn and its questions are kept for the follow-ups."""
    wrapper, inner = stub(first_round_script(), auto_research=False)
    wrapper.news_client = FakeNews(NEWS)
    result = wrapper.run(m4(request_id="q", conversation_id="conv_1", message="Kenapa broker ZP aktif?"))
    assert [r.request_id for r in inner.requests] == ["q-m4a"]  # no plan step
    assert wrapper.news_client.calls[0][0] == "q-m4w" and wrapper.news_client.calls[0][1] == "Kenapa broker ZP aktif?"
    assert [s["step"] for s in result.mode4["steps"]] == ["analysis", "news"]
    assert result.status == "COMPLETED" and result.continuation is None
    answer = result.response.answer
    assert answer.index("**Jawaban**") < answer.index("**Riwayat dan konteks berita**")
    assert "BI menaikkan suku bunga pada 2025-11-20 ([Kontan](https://kontan.co.id/a), [Bisnis](https://bisnis.com/b))" \
        in answer
    assert "7%" not in answer and "Belum ada keputusan baru." in answer and "Implikasi" not in answer
    assert "- 18 November 2026: Rapat BI berikutnya (dijadwalkan) ([Bisnis](https://bisnis.com/b))" in answer
    assert "Tanpa sumber" not in answer
    assert mode4.PLAN_TITLE not in answer and "**Hasil riset**" not in answer and "Riset tidak dijalankan" not in answer
    news = result.mode4["news"]
    assert news["lines_dropped"] == 1 and news["follow_ups"] == ["Kapan rapat BI berikutnya?"]
    analysis_cost = result.mode4["steps"][0]["cost"] or 0
    assert abs(result.execution.cost - (analysis_cost + 0.031)) < 1e-9  # the news research counts in the turn


def test_option_b_without_the_news_still_answers() -> None:
    wrapper, inner = stub(first_round_script(), auto_research=False)
    wrapper.news_client = FakeNews(error=RuntimeError("down"))
    result = wrapper.run(m4(request_id="q", conversation_id="conv_1", message="Kenapa broker ZP aktif?"))
    assert result.status == "COMPLETED" and "Analisis: broker ZP." in result.response.answer
    assert "Riwayat dan konteks berita" not in result.response.answer
    assert result.mode4["steps"][-1]["status"] == "FAILED" and result.mode4["news"]["error"] == "RuntimeError"


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
    wrapper, inner = stub(script, auto_research=True)  # step B runs only with AI_MODE4_AUTO_RESEARCH (option B)
    wrapper.memory = True
    wrapper.run(m4(request_id="q", conversation_id="conv_1", message="Kenapa broker ZP aktif?"))
    context = inner.requests[1].message
    assert body.strip()[-200:] in context  # the whole body, not its first 5,000 characters
    assert "Batasan:\n- Board digabung." in context and "Metodologi:\nNet value per broker" in context


def test_without_the_run_memory_the_plan_step_keeps_the_earlier_cut() -> None:
    body = "x" * 7000
    script = first_round_script(m4a=run_result("q-m4a", response("ANSWER", body)))
    wrapper, inner = stub(script, auto_research=True)
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
    wrapper, _ = stub(first_round_script(m4a=run_result("q-m4a", analysis)), auto_research=True)
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
