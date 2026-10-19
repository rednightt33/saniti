"""EXEC-FASTLANE-LEN and the manual path of EXEC-SHARE-UI (user 2026-10-19: "Selain yang tidak saya sebutkan harus
dirubah dengan goal based instead of hardcode"; "Teks final 'CITING AND CHECKS' ... OK"; "ya for now both"; "Ok,
execute"): with AI_FASTLANE_GOAL_ANSWERS the fast prefix asks for a complete answer and lists every check in one place,
a reproduction is only for an attached number, the answer's separate fields can be edited, and a raw quote in the final
JSON is repaired before the reply is asked again; a manual run can wait without AI_MODEL and send its routers to
Claude. The standard lane and the switches off are unchanged."""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest

from app import edit_repair, lanes
from app.manual_agent import MANUAL_MODEL, ManualAgent
from app.model_choices import current_model_choice, resolve
from app.orchestrator import (CITING_CHECKS_RULES, EXPLORE_GOAL_CAVEAT, GOAL_ANSWER_RULES, REPRODUCE_NOTE,
                              REPRODUCE_SCOPE_NOTE, AgentOrchestrator, RunState, attachments_note, explore_note)
from app.schemas import AgentRunRequest
from app.tools import build_default_registry
from app.tools.request_data import current_request_id, current_run_deadline
from app.value_refs import ReferenceSources
from conftest import ANSWER, ScriptedClient, final_response, make_settings
from test_fastlane import FAST_ON, Counting, Recording, run
from test_dataneed_orchestrator import answer, completed, flow

GOAL_ON = {**FAST_ON, "AI_FASTLANE_GOAL_ANSWERS": "true"}
TEXT = {"kind": "TEXT", "request_id": "edge_1", "section": "ANSWER", "quote": "Q1 (turun terbesar)", "figures": []}


def dev_fast(goal: bool) -> str:
    """The fast prefix of the dev profile (scripts/snapshot_system_prompt.py), which renders every section."""
    from app.orchestrator import build_system_prompt
    from test_prompt_pass2 import DEV, DEV_TOOLS
    return build_system_prompt(**DEV, tools=DEV_TOOLS, tool_envelope=True, memo_note=True, merged_steps=True,
                               table_directives=True, research_sections=False, goal_answers=goal)


def prompts(**settings):
    agent = AgentOrchestrator(make_settings(**settings), Recording([]), Counting([completed()]).registry())
    return agent.system_prompt, agent.fast_system_prompt


# ---------------------------------------------------------------- the fast prefix

def test_the_fast_prefix_asks_for_a_complete_answer_and_lists_the_checks_only_with_the_switch() -> None:
    standard_off, fast_off = prompts(**FAST_ON)
    standard_on, fast_on = prompts(**GOAL_ON)
    assert standard_on == standard_off  # the standard lane never changes
    assert "two and a half thousand characters" in fast_off and "CITING AND CHECKS" not in fast_off
    assert "two and a half thousand characters" not in fast_on
    plain, goal = dev_fast(False), dev_fast(True)
    for old, new in GOAL_ANSWER_RULES:  # every pair applies to the dev profile
        assert " ".join(old.split()) in " ".join(plain.split())
        assert old in new or " ".join(old.split()) not in " ".join(goal.split())
        assert " ".join(new.split()) in " ".join(goal.split())
    # kept: the table limit of rule 13 and rule 14
    assert "within ten rows unless the user asks for more" in fast_on and "14. Do not expose hidden" in fast_on
    assert "## CITING AND CHECKS" in fast_on and fast_on.count("\n9. The final reply is one JSON object.") == 1
    assert "load_output" in fast_on and "‘kata’" in fast_on and '\\"kata\\"' in fast_on
    # the examples hold placeholders, never a real figure
    assert "<angka yang diketik sendiri>" in CITING_CHECKS_RULES and "triliun" not in CITING_CHECKS_RULES


def test_the_explore_note_explains_the_tested_effects_only_with_the_switch() -> None:
    plain, goal = explore_note(lanes.INSIGHT), explore_note(lanes.INSIGHT, goal=True)
    assert "do not write your own caveat paragraph about testing" in plain and EXPLORE_GOAL_CAVEAT not in plain
    assert EXPLORE_GOAL_CAVEAT in goal and "caveat paragraph" not in goal
    assert explore_note(lanes.ANSWER, goal=True) == explore_note(lanes.ANSWER)


# ---------------------------------------------------------------- reproduction

def test_the_reproduction_rule_says_first_that_only_an_attached_number_is_reproduced() -> None:
    request = AgentRunRequest.model_validate({"request_id": "r", "message": "x", "attachments": [TEXT]})
    assert REPRODUCE_SCOPE_NOTE not in attachments_note(request.attachments)
    note = attachments_note(request.attachments, goal=True)
    single = REPRODUCE_NOTE.replace("{{", "{").replace("}}", "}")
    assert note.endswith(REPRODUCE_SCOPE_NOTE + " " + single) and "label or text" in note
    assert '"reproductions": [{"original": "<the attached' in note and "{{" not in note


@pytest.mark.parametrize("settings,lane,text", [(GOAL_ON, lanes.FAST, True), (FAST_ON, lanes.FAST, False),
                                                (GOAL_ON, lanes.STANDARD, False)])
def test_a_reproduction_of_a_text_label_is_refused_with_why(settings, lane, text) -> None:
    """edge_c1ad148e…-m4h: a reproduction declared for the label "Q1 (turun terbesar)" was refused as 'does not
    resolve to one number'."""
    sources = ReferenceSources()
    sources.add("out", "o7", {"rows": [{"kelompok": "Q1 (turun terbesar)"}]}, "DATA_COVERAGE_VERIFIED")
    sources.add("out", "o9", {"rows": [{"hasil": 1.0}]}, "DATA_COVERAGE_VERIFIED")
    agent = AgentOrchestrator(make_settings(**settings), Recording([]), Counting([]).registry())
    state = SimpleNamespace(request_id="now", lane=lane, ref_sources=sources, reproductions=[],
                            declared_reproductions=[{"original": "out.o7.rows.0.kelompok",
                                                     "result": "out.o9.rows.0.hasil"}],
                            attached_figures={"out.o7.rows.0.kelompok": "Q1 (turun terbesar)"},
                            data_record={"outputs": [{"ref": "out.o9", "request_id": "now"}]})
    problems = agent._check_reproductions(state)
    assert len(problems) == 1
    assert ("is text (\"Q1 (turun terbesar)\"), not a number" in problems[0]) is text
    assert ("does not resolve to one number" in problems[0]) is not text


# ---------------------------------------------------------------- edit of the separate fields (all lanes)

def test_an_edit_may_remove_the_reproductions_and_set_the_other_separate_fields() -> None:
    agent = AgentOrchestrator(make_settings(), Recording([]), Counting([]).registry())
    state = RunState(request_id="e1", started=0.0, input_items=[])
    state.repair_base = {**ANSWER, "reproductions": [{"original": "out.o7.rows.0.kelompok", "result": "x"}]}
    merged, problem = agent._apply_edit(state, json.dumps({"fields": {"reproductions": [],
                                                                      "offered_action": None}}))
    assert problem is None and json.loads(merged)["reproductions"] == []
    state.repair_base = dict(ANSWER)
    _, problem = agent._apply_edit(state, json.dumps({"fields": {"not_a_field": 1}}))
    assert problem is not None and "not_a_field" in str(problem)


# ---------------------------------------------------------------- raw quotes in the final JSON

RAW_QUOTED = ('{"response_type": "ANSWER", "answer": "Rata-rata "harian" naik, kata analis "cukup kuat", lalu turun.", '
              '"clarification_question": null, "assumptions": ["Periode "YTD" 2026"], "limitations": []}')


def test_a_raw_quote_inside_a_string_is_escaped_and_the_rest_is_left_alone() -> None:
    repaired = edit_repair.repair_quotes(RAW_QUOTED)
    data = json.loads(repaired)
    assert data["answer"] == 'Rata-rata "harian" naik, kata analis "cukup kuat", lalu turun.'
    assert data["assumptions"] == ['Periode "YTD" 2026'] and data["clarification_question"] is None
    assert edit_repair.repair_quotes(json.dumps(ANSWER)) is None  # valid JSON is not touched
    assert edit_repair.repair_quotes('{"answer": "cut off') is None  # what cannot be repaired is asked again
    assert edit_repair.repair_quotes("plain text") is None
    assert json.loads(edit_repair.repair_quotes("```json\n" + RAW_QUOTED + "\n```"))["limitations"] == []


@pytest.mark.parametrize("settings,lane,repaired", [(GOAL_ON, lanes.FAST, True), (FAST_ON, lanes.FAST, False),
                                                    (GOAL_ON, lanes.STANDARD, False)])
def test_the_fast_lane_repairs_raw_quotes_before_asking_again(settings, lane, repaired) -> None:
    body = json.dumps(answer("Return YTD BBCA naik."))
    broken = body.replace("naik.", 'naik, disebut "kuat".')
    script = [*flow(), final_response(broken), final_response(body)]
    result, scripted, _ = run(script, lane=lane, path="ANALYSIS" if lane == lanes.STANDARD else "RESEARCH",
                              settings=settings)
    assert result.status == "COMPLETED"
    asked_again = any("not valid JSON" in json.dumps(p["input"][-1:]) for p in scripted.payloads)
    assert asked_again is not repaired
    if repaired:
        assert '"kuat"' in result.response.answer


# ---------------------------------------------------------------- the manual path without AI_MODEL

MANUAL_ON = {"AI_ENABLE_MANUAL_AGENT": "true", "AI_MANUAL_AGENT_WAIT_SECONDS": "30"}


def test_without_the_fallback_a_step_waits_past_the_wait_and_ends_at_the_runs_time_limit() -> None:
    settings = make_settings(**MANUAL_ON, AI_MANUAL_AGENT_FALLBACK="false")
    real = ScriptedClient([])
    now = [0.0]
    agent = ManualAgent(real, settings, clock=lambda: now[0], poll_seconds=0.001)
    seen: list[str] = []

    def claude() -> None:
        now[0] = 10_000.0  # far past AI_MANUAL_AGENT_WAIT_SECONDS: no fallback
        for _ in range(500):
            if agent.pending():
                time.sleep(0.05)
                step = agent.pending()[0]["step_id"]
                seen.append(agent.answer(step, final_response(ANSWER)))
                return
            time.sleep(0.005)
    threading.Thread(target=claude, daemon=True).start()
    token = current_request_id.set("nf1")
    try:
        reply = agent.create({"model": MANUAL_MODEL, "input": []})
        deadline = current_run_deadline.set(time.monotonic() + 0.05)  # the run's own limit ends a wait
        try:
            expired = agent.create({"model": MANUAL_MODEL, "input": []})
        finally:
            current_run_deadline.reset(deadline)
    finally:
        current_request_id.reset(token)
    assert seen == ["ANSWERED"] and reply["output"] == final_response(ANSWER)["output"]
    assert expired["output"] == [] and real.payloads == []  # OpenRouter is never called


def test_with_the_routers_switch_a_manual_runs_routers_go_to_claude() -> None:
    for routers, expected in (("true", MANUAL_MODEL), ("false", None)):
        settings = make_settings(**MANUAL_ON, AI_MANUAL_AGENT_ROUTERS=routers)
        client = ScriptedClient([final_response({"follow_ups": [], "insight_ideas": [], "data_test": None})] * 2)
        agent = AgentOrchestrator(settings, client, build_default_registry())
        token = current_model_choice.set(resolve(MANUAL_MODEL, None, settings))
        try:
            agent.suggest_follow_ups("r1", "{}")
        finally:
            current_model_choice.reset(token)
        agent.suggest_follow_ups("r2", "{}")  # a run that did not choose Claude keeps AI_MODEL
        assert [p["model"] for p in client.payloads] == [expected or settings.ai_model, settings.ai_model]
