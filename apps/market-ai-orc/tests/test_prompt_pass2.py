"""Prompt audit pass 2 (PROMPT_AUDIT_2026-10-05.md "Putaran 2", user decision 2026-10-05): the dev system prompt is
re-formatted without changing what it says. Its sentences before (tests/fixtures/prompt_dev_before_pass2.md, the dev
prompt of main d9c4ebc) and after are compared ignoring order and line layout: the only differences are the approved
ones (K1-K4, M26-P, F4). The guards of the plan: no new digit, tokens at most two percent more (measured with
characters here, the tokenizer is not a dependency), no prose line longer than MAX_PARAGRAPH_CHARS, the 22 sections in
the planned order."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from app.orchestrator import (MAX_PARAGRAPH_CHARS, TOOL_ENVELOPE_RULE, _split_top_level, build_system_prompt,
                              markdown_prompt)

BEFORE = (Path(__file__).parent / "fixtures" / "prompt_dev_before_pass2.md").read_text(encoding="utf-8")
DEV = dict(lookup_fact=False, dataneed=True, plan_confirmation=True, period_return=True, final_contract=True,
           conversation_reuse=True, methodology=True, plan_feasibility=True, point_in_time=True,
           derived_frequency=True, research_findings=True, multi_angle=True, angle_limits=(2, 5, 0),
           value_references=True, hypothesis_plans=True)
# item 12 (plan 2026-10-05): dev offers research_web instead of find_web_fact (AI_ENABLE_WEB_RESEARCH)
DEV_TOOLS = frozenset({"query_metric", "lookup_reference", "research_web"})

# The approved differences, as sentences (a sentence ends at . ? ! or ; outside brackets)
REMOVED = {
    # K3: the plan forms are a section of their own
    "research_plan has exactly one of two forms.",
    # F4: the hypothesis plan's finding is its own list item, and the last item ends with a full stop
    "Write a value reference and the backend fills in the value, formatted: {{finding.<angle_id>.<path>}} a backend "
    "finding of complete_research_run (a hypothesis plan's finding of complete_analysis is "
    "{{finding.<hypothesis_id>.<path>}}, for example angle_a.difference, angle_a.ci_low, sample.effective), for example "
    "estimates.primary.estimate, estimates.primary.ci.0, estimates.primary.p_adjusted, sample.effective;",
    "{{metric.<key>.<path>}} a query_metric value, by the \"ref\" its tool result shows;",
    # K4: one choice rule before both plans
    "Choose its form by the question: one or a few explicit condition -> outcome hypotheses (the user's own idea, "
    "\"does X precede Y\", \"test my idea\") take the hypothesis plan (below), with no angles the user did not ask for;",
    "The multi-angle plan: Before the user approved the plan, use no data: do not call prepare_data_bundle or any "
    "session or research run tool for it.",
    "The second kind of Research Plan tests hypotheses you formulate yourself from the question and the data, not "
    "limited to the research library: one to four experiments, each one hypothesis (a condition, an outcome and a "
    "baseline you define).",
    "Choose it for one or a few explicit condition -> outcome hypotheses, even when a library method could also test "
    "them;",
    "choose the multi-angle plan to examine one root hypothesis from several sides with library methods.",
    # M26-P: the verdict list
    "complete_analysis then returns research_findings: the effect against the baseline (angle_a), how often the "
    "outcome was a success against the baseline rate (angle_b), the effective sample (distinct dates, overlapping "
    "outcomes counted once), the sample category (INSUFFICIENT, ANECDOTAL, UNDERPOWERED, ADEQUATE), the smallest "
    "detectable effect and the verdict (SUPPORTED, NOT_SUPPORTED, INCONCLUSIVE, NOT_EVALUATED).",
    "For each completed experiment, research_findings carries the verdict unchanged and an interpretation in four "
    "parts: answer: the direct answer to the user's question, first, in the verdict's terms: supported, not "
    "supported, or inconclusive.",
    # K1
    "When the two angles point different ways, say what that combination means (for example: more often up, but the "
    "falls are deeper).",
    # item 12 (user decision 2026-10-05): removed together with the new web tool
    "Data the catalog does not contain (for example macro data, yields, fundamentals, or news) is not in the "
    "database: say so and never substitute another dataset.",
    "One public fact about a company (its status, ownership, group or index membership) can be looked up with "
    "find_web_fact and is shown as a web fact;",
    "a web fact describes and never becomes a series, a dataset or an input of a calculation.",
}
ADDED = {
    # K2
    "When the latest message has no language of its own (for example only a ticker), use the language of the "
    "conversation, and Indonesian when there is none.",
    # K3
    "research_plan has exactly one of the two forms under RESEARCH PLAN FORMS.",
    # F4
    "Write a value reference and the backend fills in the value, formatted: {{finding.<angle_id>.<path>}} a backend "
    "finding of complete_research_run, for example estimates.primary.estimate, estimates.primary.ci.0, "
    "estimates.primary.p_adjusted, sample.effective;",
    "{{finding.<hypothesis_id>.<path>}} a hypothesis plan's finding of complete_analysis, for example "
    "angle_a.difference, angle_a.ci_low, sample.effective;",
    "{{metric.<key>.<path>}} a query_metric value, by the \"ref\" its tool result shows.",
    # K4
    "Choose its form by the question: one or a few explicit condition -> outcome hypotheses (the user's own idea, "
    "\"does X precede Y\", \"test my idea\") take the hypothesis plan, even when a library method could also test them, "
    "with no angles the user did not ask for;",
    "Before the user approved the plan, use no data: do not call prepare_data_bundle or any session or research run "
    "tool for it.",
    "The hypothesis plan tests hypotheses you formulate yourself from the question and the data, not limited to the "
    "research library: one to four experiments, each one hypothesis (a condition, an outcome and a baseline you "
    "define).",
    # M26-P
    "complete_analysis then returns research_findings: the effect against the baseline (angle_a), how often the "
    "outcome was a success against the baseline rate (angle_b), the effective sample (distinct dates, overlapping "
    "outcomes counted once), the sample category (INSUFFICIENT, ANECDOTAL, UNDERPOWERED, ADEQUATE), the smallest "
    "detectable effect and the verdict (SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED, INCONCLUSIVE, NOT_EVALUATED).",
    "PARTIALLY_SUPPORTED means the effect is in the expected direction but smaller than the minimum effect the user "
    "named.",
    "For each completed experiment, research_findings carries the verdict unchanged and an interpretation in four "
    "parts: answer: the direct answer to the user's question, first, in the verdict's terms: supported, partially "
    "supported, not supported, or inconclusive.",
    # K1
    "`angle_a` (the effect against the baseline) and `angle_b` (the success rate against the base rate) are the two "
    "measures of a hypothesis finding, not angles of a multi-angle plan.",
    "When angle_a and angle_b point different ways, say what that combination means (for example: more often up, but "
    "the falls are deeper).",
    # item 12: research_web
    "Information the catalog does not contain (for example macro data, events, news, ownership or group membership) "
    "is looked up with research_web, for context or when the database lacks it, and is shown as a web fact;",
    "for market data the database wins.",
    "Cite web values by their references;",
    "an event date may set an analysis period, but a web number is never an input of a calculation.",
}
SECTIONS = ["GENERAL RULES", "TOOL USE", "TOOL RESULTS", "FINAL RESPONSE", "DATA DISCOVERY", "DATA SOURCES",
            "DATA NEED", "MODES", "TIME BASIS", "NAMED-PERIOD RETURNS", "WEEKLY AND MONTHLY", "CONVERSATION REUSE",
            "VALUE REFERENCES", "METHODOLOGY", "RESEARCH PLANS", "MULTI-ANGLE PLAN", "HYPOTHESIS PLAN",
            "RESEARCH PLAN FORMS", "MULTI-ANGLE FINDINGS", "HYPOTHESIS FINDINGS", "INTERPRETING RESEARCH"]


def dev_prompt() -> str:
    return build_system_prompt(**DEV, tools=DEV_TOOLS, tool_envelope=True)


def inventory(text: str) -> Counter[str]:
    """The prompt's sentences without headings, list markers or line layout."""
    lines = [re.sub(r"^(\d+\. |- )", "", line.strip()) for line in text.splitlines()
             if line.strip() and not line.strip().startswith("## ")]
    return Counter(" ".join(piece.split()) for piece in _split_top_level(" ".join(lines), ".?!;"))


def test_the_before_fixture_is_the_dev_prompt_of_the_previous_layout() -> None:
    assert BEFORE.endswith(TOOL_ENVELOPE_RULE) and BEFORE.count("## ") == 18


def test_only_the_approved_sentences_change() -> None:
    before, after = inventory(BEFORE), inventory(dev_prompt())
    assert set(before - after) == REMOVED and all(n == 1 for n in (before - after).values())
    assert set(after - before) == ADDED and all(n == 1 for n in (after - before).values())


def test_the_sections_follow_the_planned_order_under_uniform_headings() -> None:
    text = dev_prompt()
    assert [line[3:] for line in text.splitlines() if line.startswith("## ")] == SECTIONS
    assert text.startswith("You are the Saniti AI orchestration agent.")


def test_no_new_digit_no_long_prose_line_and_at_most_two_percent_more() -> None:
    text, digits = dev_prompt(), re.compile(r"\d")
    assert sorted(digits.findall(text)) == sorted(digits.findall(BEFORE))  # the prompt is a number source
    assert all(len(line) <= MAX_PARAGRAPH_CHARS for line in text.splitlines() if not line.startswith("{"))
    assert len(text) <= len(BEFORE) * 1.02
    assert markdown_prompt(text) == text  # formatting is stable


def test_the_moved_blocks_sit_where_they_are_used() -> None:
    text = dev_prompt()

    def section(name: str) -> str:
        return text.split("## " + name + "\n", 1)[1].split("\n## ", 1)[0]

    # F2.1: database first, the web last; F2.2: the research data-need rule under MODES
    sources = section("DATA SOURCES")
    assert sources.index("query_metric") < sources.index("lookup_reference") < sources.index("research_web")
    assert "research_web" not in section("MODES") and "approved hypothesis plan" in section("MODES")
    # F2.3: the sandbox rules are a part of running the multi-angle plan
    assert "session_recovery" in section("MULTI-ANGLE PLAN") and "session_recovery" not in section("MULTI-ANGLE FINDINGS")
    # F2.4: what the plan states and how the session builds rows are steps of the hypothesis plan
    plan = section("HYPOTHESIS PLAN")
    assert "min_effect" in plan and "event_summary(events, baseline" in plan and "fixed minimum sample" in plan
    assert "event_summary(events" not in section("HYPOTHESIS FINDINGS")
    # K3: the schemas follow the plans, FINAL RESPONSE only points to them
    assert "{\"carried_inputs\"" in section("RESEARCH PLAN FORMS") and "{\"carried_inputs\"" not in section("FINAL RESPONSE")
    # F2.5: the tool-result envelope right after TOOL USE, only when the envelope is on
    assert "## TOOL RESULTS" not in build_system_prompt(**DEV, tools=DEV_TOOLS)
