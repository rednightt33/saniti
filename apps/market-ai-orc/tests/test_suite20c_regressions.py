"""Regressions found in the refused drafts of suite20c (ma-suite20-20260930c, 2026-09-30; ERRORS_AND_SOLUTIONS P12, P13,
M40) and the model switcher (user decision 2026-09-30)."""
from __future__ import annotations

import copy
import json

import pytest

from app.compaction import dumps
from app.config import ConfigError
from app.orchestrator import AgentOrchestrator
from app.provenance import CONTEXT, SourceIndex, check_answer, code_numbers, parse_numbers, released_numbers
from app.schemas import AgentRunRequest, FinalResponse
from app.value_refs import ReferenceSources, render
from conftest import final_response, make_settings
from test_multi_angle import (DESIGN_KEYS, QUESTION, agent, angle, angles, call, feasibility_args, plan_response,
                              request, requirement)
from test_orchestrator import orchestrator
from test_prompt_caching import run_logged, three_turns

# ---------------------------------------------------------------------------------------------------------- P12


@pytest.mark.parametrize("values,text", [
    ([-30, -40, -50], "Ambang yang diuji: -30, -40 dan -50."),                                      # r04
    ([25, 35, 45, 55], "Persentil 25, 35, 45 dan 55."),                                               # r03
    ([50000000000, 100000000000, 250000000000], "Net beli asing ≥ 50 miliar, 100 miliar dan 250 miliar."),  # r06
])
def test_plan_numbers_are_read_from_the_json_values_not_the_compact_dump(values, text) -> None:
    plan = {"angles": [{"parameters": {"thresholds": values}}]}
    old, new = SourceIndex(), SourceIndex()
    old.add(CONTEXT, [v for shown in parse_numbers(dumps(plan)) for v, _ in shown.candidates])
    new.add(CONTEXT, released_numbers(plan))
    assert check_answer(text, old).unsupported  # the defect: the prose parser loses them
    assert check_answer(text, new).unsupported == []


def test_code_numbers_keep_signs_and_compact_lists() -> None:
    assert sorted(code_numbers("t = [25,35,45]\nx = -40\ny = f(1.5e3, -0.25)")) == [-40, -0.25, 25, 35, 45, 1500]
    assert sorted(code_numbers("t = [25,35 broken((  -40")) == [-40, 25, 35]  # code that does not parse


def threshold_plan(answer: str) -> dict:
    thr = angle("a_fall", "threshold_sensitivity", "CONDITIONAL_OUTCOME",
                {"thresholds": [-30, -40, -50], "threshold_operator": "<=", "baseline_mode": "COMPLEMENT"},
                "Does the effect depend on how deep the fall is?", candidate_count=3,
                multiple_testing_policy="HOLM", condition="The daily return.")
    return {**plan_response(angles=[thr] + angles()[1:]), "answer": answer}, thr


def test_a_plan_answer_may_name_its_own_threshold_list() -> None:
    body, thr = threshold_plan("Sudut pertama menguji ambang -30, -40 dan -50 terhadap hari lainnya. Setujui?")
    design = {**{k: copy.deepcopy(thr[k]) for k in DESIGN_KEYS},
              "outcome_price": {"data_request_id": "a_fall_A", "column": "close"}}
    args = feasibility_args()
    args["angles"][0] = requirement("a_fall", request("a_fall_A", columns=("ticker", "date", "close")),
                                    design_=design)
    runner, _, _ = agent([call("check_research_feasibility", args, "c1"), final_response(body)])
    result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    assert result.response.response_type == "RESEARCH_PLAN_CONFIRMATION", result.response.limitations
    assert result.execution.validation_gate != "FORCED_LIMITATION"


# ---------------------------------------------------------------------------------------------------------- P13


def sources() -> ReferenceSources:
    src = ReferenceSources()
    src.add("out", "o1", {"rows": [{"Broker": "ZP", "Buy Value": 695e9, "ticker": "DEFI", "v": 165.78}],
                          "content": {"min_ticker": "AMAG"}}, "DATA_COVERAGE_VERIFIED")
    src.add("finding", "a", {"warnings": ["only 12 events in 2023"], "est": 0.9955}, "CALCULATION_VERIFIED")
    return src


def test_an_escaped_separator_in_a_markdown_table_resolves() -> None:  # a03
    out = render("| {{out.o1.rows.0.Broker}} | {{out.o1.rows.0.Buy Value\\|rp:0}} |", sources())
    assert out.text == "| ZP | Rp 695 miliar |" and not out.problems


def test_a_python_style_index_resolves() -> None:  # a02
    out = render("{{out.o1.rows[0].ticker}} {{out.o1.rows[0].v|pctv:2}}", sources())
    assert out.text == "DEFI 165,78%" and not out.problems


def test_a_text_value_is_shown_as_written_and_its_numbers_become_sources() -> None:  # r03, r07, r08
    out = render("{{out.o1.content.min_ticker}}; {{finding.a.warnings.0}}", sources())
    assert out.text == "AMAG; only 12 events in 2023" and not out.problems
    assert [(v.value, v.label) for v in out.values] == [(12.0, "CALCULATION_VERIFIED")]


def test_a_text_value_with_a_number_format_is_shown_as_written() -> None:
    # P14 (user decision 2026-10-01): every value has a display; a number format does not apply to a text
    out = render("{{out.o1.rows.0.Broker|pct}}", sources())
    assert out.problems == [] and "{{" not in out.text


def test_a_number_is_still_formatted_by_code() -> None:
    assert render("{{finding.a.est|dec:2}}", sources()).text == "1,00"


# ---------------------------------------------------------------------------------------------------------- M40


BASE = {"response_type": "ANSWER", "answer": "Jawaban.", "assumptions": [], "limitations": []}


def test_an_omitted_clarification_question_reads_as_null() -> None:
    final = AgentOrchestrator._parse_final_output(json.dumps(BASE))
    assert final.clarification_question is None
    with pytest.raises(ValueError, match="CLARIFICATION requires"):
        FinalResponse.model_validate({**BASE, "response_type": "CLARIFICATION"})
    with pytest.raises(ValueError, match="requires clarification_question to be null"):
        FinalResponse.model_validate({**BASE, "clarification_question": "Yang mana?"})


def test_a_raw_line_break_in_a_string_and_a_single_limitation_string_are_read() -> None:
    raw = json.dumps({**BASE, "limitations": "Satu batasan."}).replace("Jawaban.", "Baris satu\nBaris dua")
    assert "\n" in raw
    final = AgentOrchestrator._parse_final_output(raw)
    assert final.answer == "Baris satu\nBaris dua" and final.limitations == ["Satu batasan."]
    assert AgentOrchestrator._parse_final_output(json.dumps({**BASE, "limitations": None})).limitations == []  # r01
    with pytest.raises(ValueError, match="LIMITATION requires at least one limitation"):
        AgentOrchestrator._parse_final_output(json.dumps({**BASE, "response_type": "LIMITATION", "limitations": None}))


def test_broken_json_and_a_string_interpretation_are_still_refused() -> None:
    with pytest.raises(ValueError, match="schema validation"):
        AgentOrchestrator._parse_final_output('{"response_type": "ANSWER", "answer": "x"')
    with pytest.raises(ValueError, match="schema validation"):
        AgentOrchestrator._parse_final_output(json.dumps({**BASE, "answer": 5}))


# -------------------------------------------------------------------------------------------------- switcher


def test_switch_1_is_the_default_and_keeps_the_payload() -> None:
    settings = make_settings()
    assert settings.ai_model_switch == 1 and settings.ai_model == "deepseek/deepseek-v4.1-flash"
    assert settings.reasoning("high") == {"effort": "high"}


def test_switch_2_runs_mimo_with_reasoning_enabled() -> None:
    settings = make_settings(AI_MODEL_SWITCH="2")
    assert settings.ai_model == "xiaomi/mimo-v2.6-pro" and settings.ai_model_1 == "deepseek/deepseek-v4.1-flash"
    assert settings.reasoning("high") == {"enabled": True} and settings.reasoning("low") == {"enabled": False}
    agent_, client = orchestrator(three_turns(), AI_MODEL_SWITCH="2")
    run_logged(agent_)
    assert {p["model"] for p in client.payloads} == {"xiaomi/mimo-v2.6-pro"}
    assert all(p["reasoning"] == {"enabled": True} for p in client.payloads)


def test_switch_2_sends_the_effort_level_when_its_form_is_effort() -> None:
    settings = make_settings(AI_MODEL_SWITCH="2", AI_MODEL_2="xiaomi/mimo-v2.6-flash", AI_MODEL_2_REASONING_FORM="effort")
    assert settings.reasoning("high") == {"effort": "high"} and settings.reasoning("low") == {"effort": "low"}
    # the form belongs to model 2: switch 1 is unaffected either way
    assert make_settings(AI_MODEL_2_REASONING_FORM="enabled").reasoning("high") == {"effort": "high"}
    with pytest.raises(ConfigError, match="AI_MODEL_2_REASONING_FORM"):
        make_settings(AI_MODEL_2_REASONING_FORM="budget")


@pytest.mark.parametrize("bad", ["0", "3", "x"])
def test_an_unknown_switch_stops_startup(bad) -> None:
    with pytest.raises(ConfigError):
        make_settings(AI_MODEL_SWITCH=bad)
