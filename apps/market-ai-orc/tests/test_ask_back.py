"""EXEC-3 (user approvals 2026-10-05 and 2026-10-06, "kalau ambigu maka pilih clarify"; AI_ENABLE_ASK_BACK): the
routers may ask back with one question and quick choices instead of guessing, a failed router call is retried once and
then asked back with a fixed question, a quick choice runs its route without a router call, a reply to a first-message
question is still routed as the first message, and the routers' reading of the request (intent, design values) reaches
the step that does the work. P3b: the plan-reply reader returns the same reading outside mode 4 (M90)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app import conversation_router as router
from app.orchestrator import AgentOrchestrator, RunState
from app.schemas import AgentRunRequest, AgentRunResponse, HistoryMessage
from app.tools import ToolRegistry
from app.user_words import current_design_changes, current_turn_referent
from conftest import ScriptedClient, final_response, make_settings
from test_first_message_router import ROUTER_ON, RoutedInner
from test_mode4 import fake_continuation, response, run_result, stub

ASK_ON = {**ROUTER_ON, "AI_ENABLE_CONVERSATION_ROUTER": "true", "AI_ENABLE_ASK_BACK": "true"}
QUESTION = "BBRI mau dilihat dari sisi apa?"
OPTIONS = [{"label": "Ringkasan harga terbaru", "route": "QUICK_SUMMARY"},
           {"label": "Analisis aliran asing", "route": "ANALYSIS"},
           {"label": "Uji pola tertentu", "route": "RESEARCH"}]


class AskInner(RoutedInner):
    """The first router answers with a usage record like the real one (question, options, reading)."""

    def __init__(self, script: dict[str, Any], route: str | None, usage: dict[str, Any] | None = None) -> None:
        super().__init__(script, route)
        self.settings = make_settings(**ASK_ON)
        self.usage = usage or {}
        self.seen: list[tuple[Any, Any]] = []

    def classify_first(self, request_id: str, message: str):
        self.routed.append(message)
        return self.route, "r", {"status": "COMPLETED" if self.route else "FAILED", "input_tokens": 10,
                                 "output_tokens": 2, "cost": 0.0001, "latency_ms": 5, **self.usage}

    def run(self, request: AgentRunRequest, conversation_key: str | None = None,
            data_record: dict | None = None) -> AgentRunResponse:
        self.seen.append((router.current_intent.get(), current_design_changes.get()))
        return super().run(request, conversation_key, data_record)


def asking(script: dict[str, Any], route: str | None, usage: dict[str, Any] | None = None) -> tuple[Any, AskInner]:
    wrapper, _ = stub(script)
    inner = AskInner(script, route, usage)
    wrapper.inner, wrapper.first_router, wrapper.router, wrapper.ask_back = inner, True, True, True
    return wrapper, inner


def asked_history(message: str = "BBRI") -> list[HistoryMessage]:
    return [HistoryMessage(role="user", content=message),
            HistoryMessage(role="assistant", content=router.question_text(QUESTION, OPTIONS))]


# ---------------------------------------------------------------- the router texts

def test_switched_off_the_router_texts_and_schemas_are_the_earlier_ones() -> None:
    assert router.router_instructions(False) == router.ROUTER_INSTRUCTIONS and "ASK_BACK" not in \
        router.ROUTER_INSTRUCTIONS
    assert router.first_instructions(False) == router.FIRST_INSTRUCTIONS and "ASK_BACK" not in router.FIRST_INSTRUCTIONS
    assert router.ROUTER_SCHEMA["properties"]["design_value_changes"]["items"]["properties"]["name"]["enum"] == \
        ["OUTCOME_HORIZON"]
    assert "ASK_BACK" not in router.FIRST_SCHEMA["properties"]["route"]["enum"]


def test_switched_on_both_routers_can_ask_back_and_read_every_design_value() -> None:
    first, turn = router.first_instructions(True), router.router_instructions(True)
    for criterion in router.ASK_BACK_CRITERIA[:2]:
        assert criterion in first and criterion in turn
    assert "prefer ANALYSIS over CHAT or FACT" not in first  # the "ambiguous + data -> ANALYSIS" rule is withdrawn
    assert "never goes to CHAT or FACT" in first and "never asked back" in first
    for route, (time_cost, example) in router.FIRST_ROUTE_GUIDE.items():
        assert time_cost in first and example in first, route
    assert router.first_schema(True)["properties"]["route"]["enum"][-1] == "ASK_BACK"
    assert router.router_schema(True)["properties"]["turn_kind"]["enum"][-1] == "ASK_BACK"
    names = router.first_schema(True)["properties"]["design_value_changes"]["items"]["properties"]["name"]["enum"]
    assert names == list(router.DESIGN_VALUES) and "REMOVE" in router.CHANGE_ACTIONS


def test_the_route_guide_examples_are_not_benchmark_messages() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    first = json.loads((fixtures / "first_message_router_cases.json").read_text())
    turn = json.loads((fixtures / "turn_router_cases.json").read_text())["cases"]
    variant = json.loads((fixtures / "turn_router_cases.json").read_text())["variant_cases"]
    messages = {i["message"].casefold() for key in ("development", "heldout", "ask_back") for i in first[key]} | \
        {c["message"].casefold() for c in turn + variant}
    assert not any(example.casefold() in messages for _, example in router.FIRST_ROUTE_GUIDE.values())


def test_the_question_numbers_each_choice_and_says_how_to_answer() -> None:
    text = router.question_text(QUESTION, OPTIONS)
    assert text.splitlines() == [QUESTION, "① Ringkasan harga terbaru", "② Analisis aliran asing",
                                 "③ Uji pola tertentu", router.ANSWER_HINT]
    assert router.asked_back(text) and not router.asked_back("Jawaban biasa.")
    assert [o["route"] for o in router.fallback_options(False, pending=False)] == ["CLARIFY", "CONTINUE"]
    assert [o["route"] for o in router.fallback_options(False, pending=True)] == ["CLARIFY", "CONTINUE", "APPROVE"]


def test_unusable_choices_are_dropped() -> None:
    options = [{"label": "a", "route": "ANALYSIS"}, {"label": "b", "route": "ANALYSIS"}, {"label": "", "route": "FACT"},
               {"label": "c", "route": "CONTINUE"}, {"label": "d", "route": "RESEARCH"}]
    assert router.usable_options(options, router.FIRST_OPTION_ROUTES) == [{"label": "a", "route": "ANALYSIS"},
                                                                          {"label": "d", "route": "RESEARCH"}]
    assert router.usable_options([{"label": "x", "route": "APPROVE"}], router.TURN_OPTION_ROUTES, pending=False) == []


# ---------------------------------------------------------------- first message

def test_a_bare_ticker_is_asked_back_and_nothing_runs() -> None:
    wrapper, inner = asking({}, "ASK_BACK", {"question": QUESTION, "options": OPTIONS,
                                             "understood_intent": "Pengguna menyebut BBRI saja."})
    result = wrapper.run(AgentRunRequest(request_id="q", message="BBRI"))
    assert inner.requests == [] and result.status == "NEEDS_CLARIFICATION"
    assert result.response.response_type == "CLARIFICATION" and result.response.clarification_question.startswith(
        QUESTION)
    assert result.options == OPTIONS and result.execution.mode.route == "ASK_BACK"
    assert result.execution.cost == 0.0001 and result.mode4["round"] == "ASK_BACK"
    assert result.model_dump(mode="json")["options"] == OPTIONS


def test_a_failed_router_is_asked_back_with_the_fixed_question() -> None:
    wrapper, inner = asking({}, None)
    result = wrapper.run(AgentRunRequest(request_id="q", message="BBRI"))
    assert inner.requests == [] and result.execution.mode.route == "ROUTER_FAILED"
    assert result.response.answer.startswith(router.FALLBACK_QUESTION)
    assert [o["route"] for o in result.options] == ["QUICK_SUMMARY", "ANALYSIS", "RESEARCH"]


def test_an_ask_back_with_too_few_usable_choices_gets_the_fixed_ones() -> None:
    wrapper, _ = asking({}, "ASK_BACK", {"question": QUESTION, "options": OPTIONS[:1]})
    result = wrapper.run(AgentRunRequest(request_id="q", message="BBRI"))
    assert result.response.answer.startswith(router.FALLBACK_QUESTION) and len(result.options) == 3


def test_a_quick_choice_runs_its_route_without_a_router_call() -> None:
    wrapper, inner = asking({"q": run_result("q", response("ANSWER", "Ringkasan BBRI."))}, "EXPLORE")
    result = wrapper.run(AgentRunRequest(request_id="q", message="Ringkasan harga terbaru", history=asked_history(),
                                         chosen_option="QUICK_SUMMARY", analysis_path="MODE4"))
    assert inner.routed == [] and [(r.request_id, r.analysis_path) for r in inner.requests] == [("q", "ANALYSIS")]
    assert inner.seen[0][0]["choice"] == "QUICK_SUMMARY"
    assert result.execution.mode.source == "CHOICE" and result.execution.mode.route == "QUICK_SUMMARY"


def test_a_free_text_reply_is_routed_again_with_the_exchange_then_runs() -> None:
    wrapper, inner = asking({"q": run_result("q", response("ANSWER", "Aliran asing BBRI."))}, "ANALYSIS",
                            {"understood_intent": "Aliran asing BBRI sebulan terakhir",
                             "assumptions": ["data harian"], "design_value_changes": []})
    wrapper.run(AgentRunRequest(request_id="q", message="aliran asingnya sebulan ini", history=asked_history()))
    assert inner.routed[0].startswith("User: BBRI\nAssistant asked: " + QUESTION)
    assert inner.routed[0].endswith("User: aliran asingnya sebulan ini")
    intent, changes = inner.seen[0]
    assert intent["understood_intent"] == "Aliran asing BBRI sebulan terakhir" and changes == []


def test_after_two_questions_an_unclear_reply_runs_the_fallback_step() -> None:
    history = [*asked_history(), HistoryMessage(role="user", content="hmm"),
               HistoryMessage(role="assistant", content=router.question_text(None, router.fallback_options(True)))]
    wrapper, inner = asking({"q": run_result("q", response("ANSWER", "x"))}, "ASK_BACK",
                            {"question": QUESTION, "options": OPTIONS})
    result = wrapper.run(AgentRunRequest(request_id="q", message="terserah", history=history))
    assert [(r.request_id, r.analysis_path) for r in inner.requests] == [("q", "ANALYSIS")]
    assert result.execution.mode.route == "ROUTER_FAILED"


def test_switched_off_a_reply_after_a_question_is_a_later_message() -> None:
    wrapper, inner = asking({"q": run_result("q", response("ANSWER", "x"))}, "ANALYSIS")
    wrapper.ask_back = False
    wrapper.run(AgentRunRequest(request_id="q", message="aliran asing", history=asked_history(),
                                analysis_path="ANALYSIS", chosen_option="ANALYSIS"))
    assert inner.routed == []  # not the first-message router: the conversation router path, unchanged


# ---------------------------------------------------------------- later messages

def later(message: str, **fields: Any) -> AgentRunRequest:
    history = [HistoryMessage(role="user", content="Return BBRI September?"),
               HistoryMessage(role="assistant", content="Return BBRI September 3%.")]
    return AgentRunRequest(request_id="q", message=message, history=history, analysis_path="MODE4", **fields)


def test_a_later_message_can_be_asked_back_and_approve_is_offered_only_while_a_suggestion_waits() -> None:
    usage = {"status": "COMPLETED", "question": "Maksudnya yang mana?",
             "options": [{"label": "Jelaskan", "route": "CLARIFY"}, {"label": "Setujui", "route": "APPROVE"},
                         {"label": "Uji", "route": "CONTINUE"}]}
    wrapper, inner = asking({}, "ANALYSIS")
    inner.classify_turn = lambda rid, message, context: ("ASK_BACK", None, usage)
    result = wrapper.run(later("yang itu?"))
    assert inner.requests == [] and [o["route"] for o in result.options] == ["CLARIFY", "CONTINUE"]
    assert result.mode4["turn_kind"] == "ASK_BACK" and result.execution.mode is None
    result = wrapper.run(later("yang itu?", continuation=fake_continuation()))
    assert [o["route"] for o in result.options] == ["CLARIFY", "APPROVE", "CONTINUE"]
    assert result.response.limitations and "masih menunggu" in result.response.limitations[0]


def test_a_failed_turn_router_is_asked_back_with_the_fixed_question() -> None:
    wrapper, inner = asking({}, "ANALYSIS")
    inner.classify_turn = lambda rid, message, context: (None, None, {"status": "FAILED"})
    result = wrapper.run(later("lanjut"))
    assert inner.requests == [] and [o["route"] for o in result.options] == ["CLARIFY", "CONTINUE"]


def test_a_later_quick_choice_runs_its_class_and_the_question_reaches_the_router() -> None:
    wrapper, inner = asking({"m4n": run_result("q-m4n", response("ANSWER", "Lanjutan."))}, "ANALYSIS")
    contexts: list[dict] = []

    def classify(rid: str, message: str, context: dict):
        contexts.append(context)
        return "CONTINUE", None, {"status": "COMPLETED", "understood_intent": "Uji lanjutan"}
    inner.classify_turn = classify
    wrapper.run(later("Analisis lanjutan", chosen_option="CONTINUE"))
    assert contexts == [] and [r.request_id for r in inner.requests] == ["q-m4n"]
    request = later("yang kedua")
    request = request.model_copy(update={"history": [*request.history, HistoryMessage(
        role="user", content="itu"), HistoryMessage(role="assistant", content=router.question_text(QUESTION, OPTIONS))]})
    wrapper.run(request)
    assert contexts[0]["question_the_message_answers"].startswith(QUESTION)
    assert inner.seen[-1][0] == {"understood_intent": "Uji lanjutan"}


# ---------------------------------------------------------------- the orchestrator's router calls

ROUTE_JSON = {"route": "ANALYSIS", "reason": "data", "understood_intent": "Harga BBRI minggu ini",
              "assumptions": ["harga penutupan"], "question": None, "options": [],
              "design_value_changes": [{"name": "OUTCOME_HORIZON", "value": 5, "unit": "DAY", "text": None,
                                        "action": "ADD"}]}


def test_a_failed_router_call_is_retried_once_and_the_reading_is_returned() -> None:
    client = ScriptedClient([RuntimeError("boom"), final_response(ROUTE_JSON)])
    orchestrator = AgentOrchestrator(make_settings(**ASK_ON), client, ToolRegistry())
    route, _, record = orchestrator.classify_first("q", "harga BBRI minggu ini")
    assert route == "ANALYSIS" and record["attempts"] == 2 and record["understood_intent"] == "Harga BBRI minggu ini"
    assert record["design_value_changes"] == [{"name": "OUTCOME_HORIZON", "value": 5.0, "unit": "DAY",
                                               "action": "ADD"}]
    assert client.payloads[0]["text"]["format"]["schema"] == router.FIRST_SCHEMA_ASK_BACK
    off = AgentOrchestrator(make_settings(**ROUTER_ON), ScriptedClient([RuntimeError("boom")]), ToolRegistry())
    route, _, record = off.classify_first("q", "x")
    assert route is None and "attempts" not in record


def test_the_reading_and_a_quick_summary_reach_the_working_step_as_notes() -> None:
    orchestrator = AgentOrchestrator(make_settings(**ASK_ON), object(), ToolRegistry())
    state = RunState(request_id="q", started=0.0, input_items=[{"role": "user", "content": "m"}])
    token = router.current_intent.set({"understood_intent": "Ringkasan BBRI", "assumptions": ["data harian"],
                                       "choice": "QUICK_SUMMARY"})
    try:
        orchestrator._apply_turn_kind(state)
    finally:
        router.current_intent.reset(token)
    notes = [item["content"] for item in state.input_items[:-1]]
    assert notes[0].startswith("Application note (router)") and "Ringkasan BBRI." in notes[0] and "data harian" in \
        notes[0]
    assert notes[1] == router.NOTES["QUICK_SUMMARY"] and state.input_items[-1]["content"] == "m"


# ---------------------------------------------------------------- P3b: the plan-reply reader

REPLY_JSON = {"action": "REVISE", "revision_instruction": "tambah horizon 10 hari", "referent": "PENDING_SUGGESTION",
              "design_value_changes": [{"name": "OUTCOME_HORIZON", "value": 10, "unit": "DAY", "text": None,
                                        "action": "ADD"}]}


def test_the_plan_reply_reader_returns_the_reading_on_every_path() -> None:
    from test_mode4 import PLAN1

    orchestrator = AgentOrchestrator(make_settings(**ASK_ON), ScriptedClient([final_response(REPLY_JSON)]),
                                     ToolRegistry())
    action, instruction, record = orchestrator.classify_reply("q", "tambahkan juga 10 hari, tetap 3 hari", PLAN1)
    assert (action, instruction) == ("REVISE", "tambah horizon 10 hari")
    assert record["reading"] == {"referent": "PENDING_SUGGESTION", "design_value_changes": [
        {"name": "OUTCOME_HORIZON", "value": 10.0, "unit": "DAY", "action": "ADD"}]}
    off = AgentOrchestrator(make_settings(**ROUTER_ON), ScriptedClient([final_response(
        {"action": "APPROVE", "revision_instruction": None})]), ToolRegistry())
    _, _, record = off.classify_reply("q", "ok", PLAN1)
    assert "reading" not in record


def test_outside_mode4_the_reading_binds_the_runs_plan_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = AgentOrchestrator(make_settings(**ASK_ON), object(), ToolRegistry())
    seen: list[Any] = []
    reading = {"referent": "PENDING_SUGGESTION",
               "design_value_changes": [{"name": "OUTCOME_HORIZON", "value": 10, "unit": "DAY", "action": "ADD"}]}
    monkeypatch.setattr(orchestrator, "_prepare_plan_turn",
                        lambda request, state: setattr(state, "reply_reading", reading))

    def loop(state: RunState):
        seen.append((current_design_changes.get(), current_turn_referent.get()))
        raise RuntimeError("stop")
    monkeypatch.setattr(orchestrator, "_loop", loop)
    orchestrator.run(AgentRunRequest(request_id="q", message="tambah 10 hari"))
    assert seen == [(reading["design_value_changes"], "PENDING_SUGGESTION")]
    assert current_design_changes.get() is None and current_turn_referent.get() is None


def test_in_mode4_the_reply_readers_reading_reaches_the_step() -> None:
    from test_mode4 import first_round_script

    wrapper, inner = asking(first_round_script(), "ANALYSIS")
    wrapper.router = False
    inner.classify_reply = lambda rid, message, plan: ("APPROVE", None, {
        "status": "COMPLETED", "reading": {"referent": "PENDING_SUGGESTION", "design_value_changes": [
            {"name": "OUTCOME_HORIZON", "value": 10, "unit": "DAY", "action": "ADD"}]}})
    wrapper.run(AgentRunRequest(request_id="q", message="jalankan, tambah 10 hari", analysis_path="MODE4",
                                continuation=fake_continuation()))
    assert inner.seen[0][1] == [{"name": "OUTCOME_HORIZON", "value": 10, "unit": "DAY", "action": "ADD"}]


def test_the_api_accepts_a_choice_and_refuses_an_unknown_one() -> None:
    assert AgentRunRequest(request_id="q", message="1", chosen_option="QUICK_SUMMARY").chosen_option == "QUICK_SUMMARY"
    with pytest.raises(ValueError):
        AgentRunRequest(request_id="q", message="1", chosen_option="RUN_EVERYTHING")


def test_through_the_api_a_bare_ticker_is_asked_back_and_a_choice_answers_it() -> None:
    """End to end with AI_MODE_SWITCH=4 (CLIENT history): the question, then the reply with the picked choice runs one
    analysis step without another router call (main.routed treats a reply to a first-message question as a first
    message, so the switch's mode 4 does not apply)."""
    from app.main import create_app
    from conftest import ANSWER
    from test_mode4 import mode4_agent
    from test_modes import post

    settings = {**ASK_ON, "AI_MODE_SWITCH": "4"}
    asked = {**ROUTE_JSON, "route": "ASK_BACK", "question": QUESTION, "options": OPTIONS, "design_value_changes": []}
    runner, scripted, _ = mode4_agent([final_response(asked), final_response(ANSWER)])
    runner.inner.settings, runner.inner.ask_back = make_settings(**settings), True
    app = create_app(make_settings(**settings), orchestrator=runner.inner)
    body = post(app, {"request_id": "a1", "message": "BBRI"})
    assert body["status"] == "NEEDS_CLARIFICATION" and body["options"] == OPTIONS
    assert body["execution"]["mode"] == {"mode": 4, "name": "MODE4", "source": "ROUTER", "route": "ASK_BACK"}
    history = [{"role": "user", "content": "BBRI"}, {"role": "assistant", "content": body["response"]["answer"]}]
    body = post(app, {"request_id": "a2", "message": "Ringkasan harga terbaru", "history": history,
                      "chosen_option": "QUICK_SUMMARY"})
    assert body["execution"]["mode"] == {"mode": 2, "name": "ANALYSIS", "source": "CHOICE", "route": "QUICK_SUMMARY"}
    assert len(scripted.payloads) == 2  # one router call (the first message), one analysis step
    assert router.NOTES["QUICK_SUMMARY"] in json.dumps(scripted.payloads[1]["input"], ensure_ascii=False)
