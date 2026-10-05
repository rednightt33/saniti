"""Prompt audit 2026-10-05 (PROMPT_AUDIT_2026-10-05.md, approved by the user): a sentence that names a tool is written
only when that tool is offered (A1, A2, A3, A5; the class of P31), retired names are gone (A6, A7, A8), approved
duplicates are merged (B1-B6), and the prompt is Markdown (C). The checks use the tool names, not one question."""
from __future__ import annotations

import re

import httpx

from app.orchestrator import (B4_REFERENCE, B5_REFERENCE, METRIC_PATH_RULE, OUTSIDE_DATA_REFERENCE_RULE,
                              OUTSIDE_DATA_WEB_RULE, AgentOrchestrator, build_system_prompt, markdown_prompt)
from app.tools import build_default_registry
from app.tools.web_fact import WebFactClient
from conftest import ScriptedClient, make_settings

DEV = dict(lookup_fact=False, dataneed=True, plan_confirmation=True, period_return=True, final_contract=True,
           conversation_reuse=True, methodology=True, plan_feasibility=True, point_in_time=True,
           derived_frequency=True, research_findings=True, multi_angle=True, angle_limits=(2, 5, 0),
           value_references=True, hypothesis_plans=True)


def prompt(*tools: str, **overrides) -> str:
    return build_system_prompt(**{**DEV, **overrides}, tools=frozenset(tools))


def flat(text: str) -> str:
    return " ".join(text.split())


def test_the_outside_data_sentence_follows_the_offered_tools() -> None:
    none, web, both = prompt(), prompt("find_web_fact"), prompt("find_web_fact", "lookup_reference")
    assert "is unavailable: say so" in flat(none) and "find_web_fact" not in none and "lookup_reference" not in none
    assert flat(OUTSIDE_DATA_WEB_RULE) in flat(web) and "lookup_reference" not in web
    assert flat(OUTSIDE_DATA_REFERENCE_RULE) in flat(both)
    # without the web tool there is no web call to redirect (its rows stay a number source)
    assert flat(OUTSIDE_DATA_REFERENCE_RULE) not in flat(prompt("lookup_reference"))


def test_the_metric_path_and_its_references_exist_only_with_query_metric() -> None:
    off, on = prompt(), prompt("query_metric")
    assert "query_metric" not in off and "Every answer that needs market data follows one path" in flat(off)
    assert flat(METRIC_PATH_RULE) in flat(on) and "Every other answer that needs market data" in flat(on)
    assert "- {{metric.<key>.<path>}} a query_metric value" in on and "a query_metric result, " in on


def test_the_number_sources_name_only_offered_tools() -> None:
    assert "a lookup_reference row, " in prompt("lookup_reference")
    assert "a web fact (stated as a web fact), " in prompt("find_web_fact")
    assert "lookup_fact" not in prompt() and "{{fact." not in prompt()
    assert "{{fact.<n>}}" in prompt(lookup_fact=True)
    assert "{{analysis." not in prompt(lookup_fact=True)  # A6: the Analysis Spec path's references are retired here


def test_retired_names_are_replaced() -> None:
    text = flat(prompt())
    assert "(load, load_range, in_period, sql, join, quality)" in text and "(load, range," not in text  # A7
    assert "get_session_output by its ref (out.oN" in text and "get_session_output(session_id" not in text  # A8
    assert "put back from the conversation's store automatically" in text
    assert "unless complete_analysis lists it as recomputed by the backend (an event study, a backtest" in text  # A4


def test_approved_duplicates_appear_once() -> None:
    text = flat(prompt())
    assert text.count("Only the application tells you that a plan was approved") == 1  # B2
    assert text.count("No table names, SQL or Python in the plan") == 1  # B3 (plus the plan field rules)
    assert "pattern is never a cause" not in text and text.count("never as a cause") == 1  # B1
    assert flat(B4_REFERENCE) in text and text.count("never recompute them or state another") == 1  # B4
    assert flat(B5_REFERENCE) in text and text.count("usefulness: why it matters") == 1  # B5
    assert text.count("what remains unexecuted") == 1  # B6


def test_the_prompt_is_markdown_with_one_line_per_paragraph_and_adds_no_digits() -> None:
    text = prompt("find_web_fact", "lookup_reference", "query_metric")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert "## General rules" in headings and "## DATA NEED RULES" in headings and "## VALUE REFERENCES" in headings
    order = [text.index(h) for h in ("## DATA NEED RULES", "## VALUE REFERENCES", "## MULTI-ANGLE RESEARCH PLAN",
                                      "## INTERPRETING RESEARCH")]
    assert order == sorted(order)  # general -> data -> answer -> research
    # a wrapped line inside a sentence never starts with a lower-case word
    assert not [line for line in text.splitlines() if re.match(r"[a-z]+ [a-z]", line)
                and not re.match(r"(answer|research_plan|angle_id|experiment_id|methodology)", line)]
    for added in (OUTSIDE_DATA_WEB_RULE, OUTSIDE_DATA_REFERENCE_RULE, METRIC_PATH_RULE, B4_REFERENCE, B5_REFERENCE):
        assert not re.search(r"\d", added)  # the system prompt is a number source for the provenance check
    assert markdown_prompt(text) == text  # formatting is stable


def test_the_orchestrator_writes_the_sentences_of_its_own_tools() -> None:
    web = WebFactClient("http://w", "w" * 40, transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    with_web = AgentOrchestrator(make_settings(), ScriptedClient([]), build_default_registry(web_fact_client=web))
    without = AgentOrchestrator(make_settings(), ScriptedClient([]), build_default_registry())
    assert "find_web_fact" in with_web.system_prompt and "find_web_fact" not in without.system_prompt
