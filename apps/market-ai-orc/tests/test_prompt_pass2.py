"""Prompt audit pass 2 (PROMPT_AUDIT_2026-10-05.md "Putaran 2", user decision 2026-10-05): the dev system prompt is
re-formatted without changing what it says. Its sentences before (tests/fixtures/prompt_dev_before_pass2.md, the dev
prompt of main d9c4ebc) and after are compared ignoring order and line layout: the only differences are the approved
ones (K1-K4, M26-P, F4). The guards of the plan: no new digit, tokens at most two percent more (measured with
characters here, the tokenizer is not a dependency), no prose line longer than MAX_PARAGRAPH_CHARS, the 22 sections in
the planned order. Later approved changes are added to REMOVED and ADDED (EXEC-P2 P2e, 2026-10-06)."""
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
    # EXEC-W A3 (M121 h, user decision 2026-10-08): a failed check asks the user for an alternative
    "on NOT_FEASIBLE drop or narrow the uncovered angles, or return LIMITATION naming what is missing and the "
    "alternatives.",
    "when the check cannot pass, return LIMITATION naming what is missing and the alternatives.",
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
    # EXEC-P2 P2e (user approval 2026-10-06): answer-length targets
    "Keep the final answer focused and proportional to the user's question.",    # EXEC-V stage 2 (user approval 2026-10-07): the same data is recognised whatever its labels
    "For a new computation on the same data, submit the listed data_need_spec unchanged (any request_group_id, "
    "revision one).",
    "prepare_data_bundle then reuses the earlier bundle without a new extraction (reused true), and "
    "open_analysis_session reattaches the warm session when it is still alive (reused_session true, listing the "
    "variables of the earlier message).",
}
ADDED = {
    # EXEC-W A3 (M121 h, user decision 2026-10-08)
    "on NOT_FEASIBLE drop or narrow the uncovered angles, or name what is missing and ask the user (CLARIFICATION) "
    "for an alternative.",
    "when the check cannot pass, name what is missing and ask the user (CLARIFICATION) for an alternative, or return "
    "LIMITATION.",
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
    # EXEC-P2 P2e: in words, so the prompt gains no digit (it is a number source)
    "Keep the final answer focused and proportional to the user's question: the answer within about two and a half "
    "thousand characters and a table in it within ten rows unless the user asks for more (the full table stays in its "
    "released output).",
    # EXEC-V stage 2 (M110), revised 2026-10-08 (option D, version (i)): the same Governor SQL is the same data
    "For a new computation on the same data, submit the listed data_need_spec (any request_group_id, revision one).",
    "Data whose SQL an earlier answer ran is reused if its range ends before today, whatever its labels "
    "(prepare_data_bundle's data_reuse says which).",
    "With the same spec, open_analysis_session reattaches the warm session (reused_session true, listing the earlier "
    "variables);",
    "otherwise it opens a new session.",
}
# M125 C (user decisions 2026-10-08: "Naikan batas", "Lanjut tulis prompt. Pakai best practice prompt. Pastikan tidak
# ada prompt yg contradict di system prompt."): the reader section, and the sentences that asked for codes or names
# in the reader's text. A sentence an earlier change added and this one replaces leaves ADDED instead of joining REMOVED.
C_REMOVED = {
    "An ANSWER or LIMITATION that rests on a completed analysis, or on a released output of an earlier message, carries methodology: a short account in the user's language that lets a reader audit how the answer was reached: the data: the datasets, universe, period and frequency, and the filters and exclusions applied;",
    "Do not invent alternative table, field, asset, or feature names.",
    "For an ANSWER, research_findings has your reading of each approved angle: angle_id and an interpretation in three parts (the backend adds each angle's status, evidence and statistics itself): answer (in the angle status's terms), usefulness and follow_up, each as defined under INTERPRETING RESEARCH below.",
    "For each completed experiment, research_findings carries the verdict unchanged and an interpretation in four parts: answer: the direct answer to the user's question, first, in the verdict's terms: supported, partially supported, not supported, or inconclusive.",
    "Preserve exact identifiers returned by tools.",
    "Report an INVALID or NOT_RUN angle as such and never fill it in.",
    "The answer field tells the user the findings in their language, with the sample category and what it means.",
    "disclose those that affect the answer.",
    "evidence: what the numbers say: how large the effect is against the baseline, how often the outcome happened against its base rate, and how certain this is: the sample category, the effective sample, the uncertainty and the smallest effect this sample could detect."
}
C_ADDED = {
    "An ANSWER or LIMITATION that rests on a completed analysis, or on a released output of an earlier message, carries methodology: a short account in the user's language that lets a reader audit how the answer was reached: the data: which data, in plain words rather than table or column names, the universe, period and frequency, and the filters and exclusions applied;",
    "Explain a statistical idea in plain words where it first appears (a confidence interval is the range the true value plausibly lies in; a p-value is how easily such a difference arises by chance) and keep its figure next to the explanation.",
    "For an ANSWER, research_findings has your reading of each approved angle: angle_id and an interpretation in three parts (the backend adds each angle's status, evidence and statistics itself): answer (in words that match the angle's status), usefulness and follow_up, each as defined under INTERPRETING RESEARCH below.",
    "For each completed experiment, research_findings carries the verdict unchanged and an interpretation in four parts: answer: the direct answer to the user's question, first, in words that match the verdict: supported, partially supported, not supported, or inconclusive.",
    "For example, an answer in Indonesian for an inconclusive test: \"**Belum bisa disimpulkan.** Lonjakan volume BBRI hanya terjadi {{finding.vol_spike.sample.effective|int}} kali dalam periode ini, terlalu sedikit untuk tahu apakah harganya cenderung naik sesudahnya.",
    "In tool calls and value references, use the exact identifiers that tools return and never invent a table, field, asset or feature name;",
    "Lima hari setelah lonjakan, return rata-rata berbeda {{finding.vol_spike.angle_a.difference|pp}} dari hari biasa, selisih yang masih bisa muncul karena kebetulan.",
    "Name data, measures and results by what they mean to the reader: daily share prices, net foreign buying, the broker ranking from the previous question.",
    "Periode yang lebih panjang atau beberapa saham bank sekaligus akan memberi jawaban yang lebih pasti\".",
    "Plain words change how a figure is explained, never where it comes from: every figure stays a value reference or another permitted source.",
    "Say plainly when an angle is invalid or did not run, and never fill it in.",
    "Table, column, output, angle, experiment and method names, references such as out.oN, internal ids and backend codes (statuses, verdicts, sample categories, quality flags, validation levels) belong in tool calls, value references and the structured fields that ask for them (verdict, status, ids);",
    "The answer field tells the user the findings in their language and in plain words, with how far the sample can be trusted.",
    "The reader is an individual investor, not a data analyst.",
    "Then give the two or three figures that carry it, each with what it is compared with, then what it means for the reader, then the caveats that change how far it can be trusted.",
    "Write every text the user reads (answer, clarification_question, assumptions, limitations, methodology, a plan's text and research_findings) so that such a reader understands it on the first reading: Lead with the conclusion in one or two sentences.",
    "Write the way people talk: short sentences, everyday words, active verbs.",
    "disclose in plain words those that affect the answer.",
    "evidence: what the numbers say: how large the effect is against the baseline, how often the outcome happened against its base rate, and how certain this is: how far the sample can be trusted (its category, in words), the effective sample, the uncertainty and the smallest effect this sample could detect.",
    "in text the reader reads, describe them in plain words (see WRITING FOR THE READER).",
    "in text the reader reads, say what they mean instead."
}
REMOVED, ADDED = (REMOVED | (C_REMOVED - ADDED)) - C_ADDED, (ADDED - C_REMOVED) | (C_ADDED - REMOVED)
# the reader section added about six percent (the budget was two percent over the pass-2 fixture)
SIZE_BUDGET = 1.09

SECTIONS = ["GENERAL RULES", "TOOL USE", "TOOL RESULTS", "FINAL RESPONSE", "WRITING FOR THE READER", "DATA DISCOVERY", "DATA SOURCES",
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
    assert len(text) <= len(BEFORE) * SIZE_BUDGET
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


def test_no_sentence_asks_for_codes_or_names_in_the_readers_text() -> None:
    """M125 C (user decision 2026-10-08: "Pastikan tidak ada prompt yg contradict di system prompt"): WRITING FOR THE
    READER keeps codes, categories and identifiers out of the text the user reads. A sentence that tells the response to
    say, state, report, disclose or name one of them must ask for plain words too, in every prompt the service builds."""
    from app.orchestrator import SYSTEM_PROMPT
    asks = re.compile(r"\b(say|says|state|states|report|reports|tell|tells|disclose|name|names)\b", re.I)
    coded = re.compile(r"\b(categor(y|ies)|(reason|backend|status) codes?|identifiers?|flags?|terms)\b", re.I)
    plain = re.compile(r"\b(plain words|in words|what they mean|say what)\b", re.I)
    tool_side = re.compile(r"\btool calls\b", re.I)  # a sentence about what goes into tool calls, not the reader's text
    for prompt in (dev_prompt(), SYSTEM_PROMPT):
        conflicting = [s for s in inventory(prompt)
                       if asks.search(s) and coded.search(s) and not plain.search(s) and not tool_side.search(s)]
        assert conflicting == [], conflicting
