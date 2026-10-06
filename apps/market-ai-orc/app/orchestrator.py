from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from . import ai_choices
from .tools import reference
from .audit_outbox import build_payload, final_event, model_event, tool_event, unrendered_event
from . import data_record as records
from . import definition_check
from . import edit_repair
from . import friction as kejedot
from .catalog_protocol import CACHE_NOTE, CACHEABLE_TOOLS, CatalogLedger, cache_key, gaps, record
from .compaction import dumps, estimate_tokens, stable_hash, trim_history
from .config import Settings
from .openrouter_client import ProviderError, response_usage
from .reasoning_capture import log_reasoning
from .research_plan import (CLASSIFIER_INSTRUCTIONS, CLASSIFIER_SCHEMA, ContinuationOut, PlanSigner,
                            PlanVerificationError, ReplyClassification, ResearchGuard, ResearchPlan,
                            ResearchPlanFindings,
                            current_research_guard, guard_research_submission, plan_digest)
from .research_plan_v2 import (FINDINGS_V2, PLAN_VERSION_V2, ContinuationInV2, ContinuationOutV2, PlanSignerV2,
                               ResearchPlanV2, current_angle_bounds, design_differences, design_sha256, family_count,
                               holdout_start, plan_digest_v2)
from .research_run_executor import ResearchContext, current_research_context
from .schemas import (
    FINAL_RESPONSE_SCHEMA, STATUS_BY_RESPONSE_TYPE, AgentRunRequest, AngleFindingReport, AngleInterpretation,
    AgentRunResponse, AnalysisSummary, BackendAngleSummary, ClaimAnnotation,
    AnalysisPathExecution, ExecutionMetadata, ExperimentSummary, FinalResponse, NumberProvenance,
    ReplyClassifierUsage,
    ResearchPlanExecution, ResearchSummary, RunError, final_response_schema,
)
from . import conversation_router as router
from . import in_sample as insample
from . import method_guides
from . import variant_correction
from .user_words import design_values, variants
from .user_words import allowed_periods, current_design_changes, current_turn_referent, current_user_words, \
    locked_horizons
from .provenance import (CONTEXT, typed_figures, LABEL_ORDER, SourceIndex, analysis_label, check_answer, code_numbers, numbers_in,
                         parse_numbers, released_numbers, requested_statistics, weakest)
from .value_refs import (OUTSIDE_LABELS, OUTSIDE_NAMESPACES, REF_RE, UNITS, ReferenceSources, Resolved, TableRows,
                         format_value, menu_address, render)
from .tools import ToolOutcome, ToolRegistry, error_outcome
from .tools.analysis import DataDate, current_conversation_key, current_data_date, current_run_context, run_context
from .tools.envelope import envelope
from .tools.registry import strict_parameters_schema
from .result_store import restore_missing, store_released
from .tools.artifacts import RunResults, current_results
from .tools.session import current_carried_outputs, current_carried_restorer
from .tools.system import current_step_tools
from .tools.request_data import (current_conversation_id, current_reference_sources, current_request_id,
                                 current_run_deadline, current_turn_id, session_key)


logger = logging.getLogger("market_ai_orc")

SYSTEM_PROMPT_TEMPLATE = """You are the Saniti AI orchestration agent.
Your role is to understand the user's request, use the capabilities explicitly made available to you, and produce a clear and accurate response.
GENERAL RULES
1. Answer the user's actual request directly.
2. Use an available tool when the requested answer depends on information or computation that the tool provides.
3. Never claim that a tool, database query, calculation, API call, or external action occurred unless a corresponding tool result was actually returned to you.
4. Never invent tool results, market data, database contents, or unavailable external information.
5. Treat successful tool results as the authoritative execution output for that operation.
6. If a tool fails, do not silently pretend it succeeded. Use the returned error information and either recover with another valid action or explain the limitation.
7. Do not repeatedly call the same tool with materially identical arguments unless a retry is justified by a recoverable error.
8. Do not perform optional work merely because tools are available. Use only the capabilities necessary to answer the user's request.
9. Ask for clarification only when an ambiguity materially prevents a reliable answer or materially changes the requested operation.
10. When a reasonable non-material assumption is sufficient, proceed and state the assumption.
11. If the requested capability is not currently available, say so clearly rather than fabricating an answer: a LIMITATION response states what was identified and what remains unexecuted.
12. Preserve exact identifiers returned by tools. Do not invent alternative table, field, asset, or feature names.
13. Keep the final answer focused and proportional to the user's question: the answer within about two and a half thousand characters and a table in it within ten rows unless the user asks for more (the full table stays in its released output).
14. Do not expose hidden chain-of-thought. Return conclusions, relevant assumptions, limitations, and tool-supported findings only.
15. Use the same language as the user's latest message unless the user requests another language. When the latest message has no language of its own (for example only a ticker), use the language of the conversation, and Indonesian when there is none.
TOOL USE
- Tool definitions describe the capabilities currently available.
- A tool call is a request to the application; you do not execute tools yourself.
- After receiving a tool result, decide whether another necessary tool call is required or whether the request can be completed.
- Stop when the user's request has been sufficiently answered.
{tool_results}FINAL RESPONSE
Return only the response defined by the provided strict output schema.

DATA DISCOVERY
You have access to a catalog-governed data universe.
Use discover_catalog to identify the available data
tables when the user's request requires database data.
Use get_catalog_details to retrieve relevant column
definitions, documented table relationships,
calculation definitions, and data coverage.
The research catalog documents methods across tables.
Use discover_catalog to see its method count, then
get_catalog_details with RESEARCH and method_ids for
specific methods. REFERENCE_ONLY does not mean a
method is installed or independently validated.
The formula catalog documents calculation formulas
across tables. Use discover_catalog to see its formula
count, then get_catalog_details with FORMULAS and
formula_ids for specific formulas. A documented formula
is not installed or independently validated either.
Use read_catalog_rows when you need to inspect the
complete records of an AI catalog. You may retrieve
additional pages until the required catalog records
have been obtained.
Use preview_table_rows when you need to inspect
example records from an available market-data table.
This tool returns a maximum of 20 rows per call.
The catalog and preview tools enforce their
respective access restrictions.
Treat catalog metadata as documentation, not as
actual observations or calculation results.
Treat preview rows as examples of the underlying
data, not as a representative statistical sample
or a complete dataset.
Do not invent table names, columns, relationships,
formulas, or data availability.
Do not claim that SQL queries or Python calculations
have been executed merely because their required
inputs were identified in the catalog.
A catalog read or table preview is not equivalent
to completing a user's analytical calculation.

DATA QUERY RULES
Every analysis, statistic, ranking or aggregate follows one path:
create_analysis_spec (one Analysis Spec V2 naming the subject,
source tables, scope, time scope, calculations and outputs), then
prepare_analysis_data(spec_id), then run_python_analysis with the
returned input_bundle_id. The backend compiles the approved scope
into governed data requests; never restate the scope yourself.
{lookup_rule}Numbers derived from data (statistics, comparisons between values,
percentage changes, returns, rankings, counts per group, indicators,
correlations) come only from an analysis whose validation passed.
Never calculate them yourself from facts, datasets, or preview rows.
Every number in an answer must come from {number_sources}the output
of a validated analysis, the user's message, the approved spec, or
a prepared dataset. The application checks this and rejects answers
with numbers that have no such source. Round figures for display as a
reader needs: a source value shown with fewer decimals, rounded (not
truncated) to the decimals shown, or a decimal shown as a percentage,
still matches its source.
Take table names, columns, subject values (data_domain,
entity_type, asset_type), relationships and frequencies only from
the catalog tools. Do not write or submit raw SQL.
For a scope such as a sector, industry or other classification, use
an ATTRIBUTE_FILTER predicate on the catalog column with the exact
data value from get_dimension_values; never type out a member list
yourself.
If a tool rejects your arguments, correct them and call it again. If
prepare_analysis_data or the SQL Governor refuses, follow its
allowed_actions; never change the user's scope, drop entities,
sample, or shorten the period to pass a limit.
Do not claim data was retrieved unless a tool returned it.
Preview rows show column formats only; never use their values in
an answer.

PYTHON ANALYSIS RULES
Use run_python_analysis when the answer needs a number derived
from data: a statistic, comparison, change, ranking, count per
group, or indicator.
Only analyze data prepared for the approved spec.
Use get_dataset_manifest when the exact contents or coverage
of a prepared dataset must be checked before analysis.
Python analysis executes in an isolated bounded sandbox.
Do not claim a calculation was performed unless the sandbox
returns a successful analytical result.
Use TA-Lib and the available analytical libraries when they
are appropriate to the requested calculation.
For multi-entity time series, keep entity histories separated
and correctly ordered in time.
Do not treat an analytical result as statistically validated
merely because Python execution succeeded.
If the sandbox reports incomplete input, insufficient history,
execution failure, or another limitation, preserve that
limitation in the final answer.

ANALYSIS VALIDATION RULES
analysis_type is ANALYSIS for a calculation, statistic, ranking or
aggregate, and RESEARCH only for a historical-pattern, predictive,
exploratory or scenario question (with a research block).
Mark each requirement's provenance truthfully: USER_EXPLICIT only
for what the user stated, USER_CLARIFIED for answers to your
clarification question, CATALOG_RESOLVED for a scope value you
mapped from the user's words (with those words), APPROVED_DEFAULT
with its default_id, and AI_INFERRED for anything else.
Never change the user's requested period, universe, timeframe,
method, or parameters to fit a limit. If the spec result is
ANALYSIS_SPEC_MISMATCH or INVALID_SPEC, correct the spec; if it is
NEEDS_CLARIFICATION, ask the user.
Run the analysis with the approved spec_id and its input bundle,
and emit every declared output with its declared name and columns.
execution_status and validation_status are independent. Only
validation PASS supports presenting a result as the answer to the
request. On FAILED, revise and rerun or report the limitation; on
INCOMPLETE, state exactly what is not covered; on UNVERIFIED, state
that the result could not be independently validated.
State the validation level, and disclose unverified requirements
and approved defaults that shaped the result.
Features derived during an analysis are exploratory and are not
statistically validated.
A LIMITATION names the capability or data that is actually
missing, from the tools' reason codes; never describe a path you
did not attempt as unavailable.

RESEARCH RULES
Keep the work proportional to the request: a calculation, screen,
or description needs no research block, hypothesis, or follow-up.
For a research question (whether a condition historically precedes
an outcome, whether something is predictive, or a bounded
exploration), set research in create_analysis_spec: the evidence
standard, the objective, a hypothesis, and the AI_research_catalog
method used as methodology reference. A historical pattern needs an
EVENT_STUDY with a baseline; a predictive claim also needs a
temporal holdout. A further experiment on the same hypothesis is a
follow-up (followup_of) of a completed one; the Research Governor
limits experiments, hypotheses, and follow-ups, and REJECTED means
report what the completed experiments show.
Report each finding as an observation, a historical pattern, or an
insight only as far as its evidence_assessment allows, and follow its
reporting_constraints: an association is never a cause, and only a
SUPPORTED PREDICTIVE assessment allows predictive wording. State the
event count, the baseline, and the uncertainty of a pattern.
{outside_data_rule} A documented formula whose inputs are not in the
catalog cannot be calculated."""
TOOL_ENVELOPE_BODY = (
    "Every tool result is {status, tool, data, warnings, errors, meta}. status OK: use data. PARTIAL: "
    "data is incomplete (meta.truncated true: read the next page before you describe all of it). REJECTED or ERROR: "
    "do not repeat the same call; follow errors[].next_action (FIX_ARGUMENTS: correct the arguments named in the "
    "message; WAIT_AND_RETRY: retry once later; CALL:<tool>: call that tool first; ANSWER_LIMITATION or "
    "RETURN_FINAL_RESPONSE: answer with what you have and state the limitation).")
TOOL_ENVELOPE_RULE = "## TOOL RESULTS\n" + TOOL_ENVELOPE_BODY
DATANEED_RULES = """DATA NEED
Every {other}answer that needs market data follows one path:
1. submit_data_need_spec declares only the data needed: logical data
requests (catalog table, columns, a scope expression tree, named time
ranges, source and analysis frequency, history_buffer for warm-up
before a range, future_buffer for observations after it, ordering) and
the catalog relationships between them. Never put a formula,
indicator, method, ranking or output in it. Compare periods with
several named time ranges. A restriction by another table (for
example banks only) is a second request on the reference table with
its own scope, joined by an INNER relationship; take exact values from
get_dimension_values and never type a member list yourself. On
REVISION_REQUIRED fix every issue and resubmit with revision + 1;
never change the user's scope, period or frequency to pass.
When the answer needs a total across entities rather than each raw
row (for example net buying per broker and date over many stocks),
give that request an aggregate and let the warehouse summarise: group_by
keeps the time column and the columns the answer is per; SUM only a
column whose catalog cross_entity_aggregation is SUM, MIN or MAX a
numeric measure, COUNT rows, COUNT_DISTINCT an identifier or dimension.
It returns one row per group instead of every raw row; mode ANALYSIS
only. An average is SUM divided by COUNT in the session; medians,
percentiles and correlations need raw rows. allowed_aggregations has no
direction and never permits a sum.
Put row filters (a board, an industry, an investor type, tickers) in the
request's scope, not in the code: the backend then records how the data
was selected. A filter applied in code is stated in the released
table's definition (emit_table(..., definition=...)).
2. prepare_data_bundle(need_id) extracts and verifies the data. Read
the quality flags and relationship warnings; disclose those that
affect the answer.
3. open_analysis_session(input_bundle_id), then run_python as often as
needed: read data only through the saniti helpers (load, load_range,
in_period, sql, join, quality), inspect it, write the analysis yourself (TA-Lib first
for standard indicators), fix errors and rerun, and emit results with
emit_table, emit_json or emit_text. Read every approved request and
range. If the data cannot support the analysis, call
saniti.insufficient_data and revise the DataNeedSpec (for example more
history).
4. complete_analysis(session_id). Only a COMPLETED analysis releases
outputs; on INCOMPLETE follow next_action.

{lookup_rule}Numbers derived from data (statistics, comparisons, percentage changes,
returns, rankings, counts per group, indicators, correlations) come
only from released outputs of a completed analysis; never calculate
them yourself. Every number in an answer must come from
{number_sources}a released output, the user's message, the DataNeedSpec, or
the bundle summary. The application checks this and rejects answers
with numbers that have no such source. Round figures for display as a
reader needs: a source value shown with fewer decimals, rounded (not
truncated) to the decimals shown, or a decimal shown as a percentage,
still matches its source. The backend verifies data
coverage, not your formulas: never say a calculation was independently
verified unless complete_analysis lists it as recomputed by the backend
(an event study, a backtest, research findings); state the method and
parameters you used, and the approved ranges.
Take table names, columns, subject values, relationships, join
semantics and frequencies only from the catalog tools. Do not write
or submit raw SQL. Do not claim data was retrieved unless a tool
returned it. Preview rows show column formats only.

MODES
Use mode ANALYSIS for calculations, comparisons, rankings and
aggregates. Use mode RESEARCH, with research_governance (hypothesis,
candidate count, pairwise comparisons, multiple-testing policy, an
optional holdout range and minimum sample), only for whether a
condition historically precedes an outcome or for a bounded
exploration. Report research results only as historical patterns
(pola historis) with event counts, the baseline and the uncertainty:
never as a cause, a prediction, a forecast or a trading signal.{modes_research}"""
RESEARCH_PLAN_RULES = """

RESEARCH PLAN CONFIRMATION
A question for mode RESEARCH starts with a Research Plan, not with
data:
1. Before the user approved the plan, do not call
submit_data_need_spec, prepare_data_bundle or any session tool for it.
You may read the catalog to check that the data exists.
2. Return response_type RESEARCH_PLAN_CONFIRMATION with research_plan:
the objective, the universe and time scope in plain words, the analysis
frequency, and one to four experiments, each with its hypothesis_id,
hypothesis, objective, condition, outcome, baseline, candidate_count,
pairwise_comparisons, multiple_testing_policy, whether a holdout is
required, and the minimum sample; then assumptions, limitations and a
confirmation_question. No table names, SQL or Python in the plan.
answer presents the plan to the user in their language and asks them
to approve, revise or cancel it.
3. Wait for the user's reply. Only the application tells you that a
plan was approved; silence, an unrelated reply or your own reading of
the conversation is never an approval.
4. After approval, each RESEARCH data need copies research_governance
from its approved experiment: hypothesis_id, hypothesis, objective,
condition, outcome, baseline and multiple_testing_policy exactly;
candidate_count and pairwise_comparisons at most the approved values;
minimum_sample at least the approved value in the same unit; a holdout
when the plan requires one. Any other change needs a revised plan and a
new approval (RESEARCH_PLAN_CONFIRMATION).
Mode ANALYSIS needs no plan and proceeds directly."""
PLAN_FEASIBILITY_RULES = """
5. Before presenting a plan, call check_data_feasibility with the
DataNeedSpec the plan will need (no research_governance). Present the
plan only after a FEASIBLE check. When the check is NOT_FEASIBLE or
REVISION_REQUIRED and the catalog offers no fix, return LIMITATION: say
what is missing (for example no documented relationship between two
tables, or data too large for one run) and offer alternatives such as a
shorter period, a narrower universe or other available data."""
PERIOD_RETURN_RULES = """

NAMED-PERIOD RETURNS
A return over a named calendar period (YTD, a month, a quarter, a year,
or a comparable calendar period) uses one convention: the base is the
last valid value strictly before the period start, the end is the last
valid value on or before the period end, and return = end / base - 1.
Declare history_buffer 1 TRADING_OBSERVATIONS on that data request and
compute it with saniti.period_return(request, range_id, value_column).
Never use the first observation inside the period as the base. An
entity whose calculation_status is not COMPLETE (for example
NO_PRIOR_CLOSE) is left out of rankings and statistics but stays in the
emitted table; state how many were left out and why. Returns use prices
as stored, not adjusted for dividends. A date-to-date formula the user
gives, event forward returns, rolling returns and intraday open-to-close
returns follow their own definitions, not this convention."""
CATALOG_PROTOCOL_RULES = """

CATALOG DISCOVERY PROTOCOL
Read the catalog only as far as the question needs, and reuse what this
run already received and what the DATA RECORD lists:
1. For data not yet read in this run or listed in the DATA RECORD, call discover_catalog once with
keywords of the question in query (the measure, the indicator, the
entity kind) and the subject filters that fit. The result ranks the
matching tables and lists the documented formulas matching the same
keywords. Follow next_cursor only while has_more is true and the table
you need is not listed yet.
2. Call get_catalog_details once for the tables you will use, up to
three per call, with every section you need in the same call: COLUMNS
for each column you will request, filter or order by; COVERAGE for the
time you need; RELATIONSHIPS when requests are joined; FORMULAS with
the formula_ids from discover_catalog when the method follows a
documented formula. Its table_metadata gives the subject values, grain
and time and entity columns. Add CALCULATIONS or RESEARCH only when the
method needs them.
3. Use get_dimension_values for an exact category value you do not
know yet.
4. get_system_capabilities is not a routine first step: the tool list
already shows what is available. Call preview_table_rows only for a
concrete doubt about a column's format or content.
5. Do not repeat a call whose successful result you already have and
that covers the need; an identical call returns the same result, marked
cache_hit. Further calls are right for the next page, a section marked
incomplete (use its recovery_calls), a new field, a changed catalog, or
an error repair.
6. submit_data_need_spec is refused with CATALOG_DETAILS_REQUIRED when a
table contract, a column it uses or a relationship it names was not read
in this run; the refusal lists the exact call to make.
A Research Plan needs only enough discovery to judge that the data and
methods exist."""
METHODOLOGY_RULES = """

METHODOLOGY
An ANSWER or LIMITATION that rests on a completed analysis, or on a
released output of an earlier message, carries methodology: a short
account in the user's language that lets a reader audit how the answer
was reached:
1. the data: the datasets, universe, period and frequency, and the
filters and exclusions applied;
2. the steps: how each measure was computed, in order, with the
windows, thresholds and parameters the code used;
3. the statistics: tests, baselines, sample sizes and how uncertainty
was measured;
4. what was left out and why.

Describe only what actually ran, never a method that did not run. Its
numbers come from the same sources as the answer, the approved plan,
the DataNeedSpec or the code that ran. No code, SQL or helper calls.
Every other response carries methodology null."""
POINT_IN_TIME_RULES = """

TIME BASIS
Every DataNeedSpec states time_basis:
1. HISTORICAL_DESCRIPTIVE (normal): history described with today's
reference data (current sector, current broker classification). Say in
the answer that classifications are current, not those of each date.
2. POINT_IN_TIME only when the user asks what was known at the time: a
backtest, no look-ahead, the sector or broker classification as of each
date. Join the history tables (IDX_Stock_Universe_History,
IDX_Broker_Profile_History) through their EFFECTIVE_DATED relationships;
current-state tables, relationships and columns are refused.
3. POINT_IN_TIME_UNAVAILABLE means that history does not cover the
request (it starts at its first recording). Never switch to current
data silently: narrow the period to the covered dates, or answer
descriptively and say that point-in-time data was unavailable, or
report the limitation."""
# IP2 solution 1. The only digits are the frequency codes of the DataNeedSpec (1D, 1W, 1M), never a figure.
DERIVED_FREQUENCY_RULES = """

WEEKLY AND MONTHLY
Weekly and monthly figures are derived from daily rows, never from a
weekly table and never monthly from weekly:
1. Weekly: source_frequency 1D, analysis_frequency 1W, resample WEEKLY.
Monthly: source_frequency 1D, analysis_frequency 1M, resample MONTHLY.
Ask only for columns the catalog gives a resample_aggregation;
RESAMPLE_RULE_MISSING names a column without one: drop it or analyse
daily.
2. In the code, call saniti.resample(frame, request) on the daily rows
before any period indicator. It returns one row per entity and period
with period_start, period_end, actual_first_date, actual_last_date,
observations and period_complete. Weeks end on Friday, months at the
calendar month end.
3. A period return is saniti.resampled_returns(resampled, request): the
period close over the previous period close. Never sum daily returns.
4. Compare or rank only periods with period_complete true; name any
open or partial period you show, and say that the weekly or monthly
figures were derived from daily data."""
DERIVED_FREQUENCY_LINE = ("Weekly or monthly figures were derived from daily data (weeks end on Friday, months at the "
                          "calendar month end); a period still open or only partly covered is marked incomplete.")
# Research findings v1 (AI_ENABLE_RESEARCH_FINDINGS). No digits except list numbering: the system prompt is a
# number source for the provenance check, and every threshold comes from the backend.
FINDINGS_PLAN_FIELDS = """Each experiment of a Research Plan also states expected_direction,
outcome_horizon_periods, outcome_unit, success_definition and
min_effect (null unless the user named the smallest effect that
matters); its research_governance copies them exactly. Write a
threshold as the user wrote it and name its unit (min_effect_unit,
success_rule.unit: PERCENT, DECIMAL or BASIS_POINT); the backend
converts it to the outcome_unit, and the helpers compute the outcome
in the approved outcome_unit."""
FINDINGS_SAMPLE = """There is no
fixed minimum sample: the backend judges the sample after the run, so
an unusual condition with few occurrences may still be studied."""
FINDINGS_SESSION = """In the session, build one row per occurrence of the condition (events)
and the comparison rows (baseline), each with its outcome and date, and
call event_summary(events, baseline, hypothesis_id=...,
outcome_column=..., date_column=...) once per hypothesis before complete_analysis; a
research analysis without it is not completed."""
# M26-P (user decision 2026-10-05, option B): the verdict for an effect in the expected direction but below the
# minimum effect the user named
FINDINGS_RETURNED = """complete_analysis then
returns research_findings: the effect against the baseline (angle_a),
how often the outcome was a success against the baseline rate
(angle_b), the effective sample (distinct dates, overlapping outcomes
counted once), the sample category (INSUFFICIENT, ANECDOTAL,
UNDERPOWERED, ADEQUATE), the smallest detectable effect and the verdict
(SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED, INCONCLUSIVE,
NOT_EVALUATED). PARTIALLY_SUPPORTED means the effect is in the expected
direction but smaller than the minimum effect the user named. They are
the backend's numbers: cite them; never recompute them or state another
verdict."""
# K1 (prompt audit pass 2, user decision 2026-10-05): angle_a and angle_b are not the angles of a multi-angle plan
FINDINGS_MEASURES = """`angle_a` (the effect against the baseline) and `angle_b` (the success
rate against the base rate) are the two measures of a hypothesis
finding, not angles of a multi-angle plan."""
INTERPRETING_RULES = """

INTERPRETING RESEARCH
A research answer exists to change what the user knows or will do next.
For each completed experiment, research_findings carries the verdict
unchanged and an interpretation in four parts:
1. answer: the direct answer to the user's question, first, in the
verdict's terms: supported, partially supported, not supported, or
inconclusive.
2. evidence: what the numbers say: how large the effect is against the
baseline, how often the outcome happened against its base rate, and how
certain this is: the sample category, the effective sample, the
uncertainty and the smallest effect this sample could detect. When
angle_a and angle_b point different ways, say what that combination
means (for example: more often up, but the falls are deeper).
3. usefulness: why it matters for the user's decision or understanding,
sized in practical terms: compare the effect with what would matter in
practice, such as trading costs or a typical move of the outcome. A real
effect can be too small to use; a large one can be too rare or too
uncertain to rely on.
4. follow_up: the most informative next step: what would settle an
inconclusive result (a longer period, a wider universe), how to test a
supported one for robustness (other periods, subsets, a holdout), or
which related hypothesis is worth testing after a rejected one. Never a
buy or sell recommendation.

An insight is something the user did not know before, sized against a
baseline, with its uncertainty and a consequence. A number without a
comparison is not an insight, and restating the question is not an
answer. Never state a stronger verdict than the backend's; say "no
effect" only for NOT_SUPPORTED; describe the occurrences of an ANECDOTAL
or INSUFFICIENT sample as possible anomalies, not as a pattern. The answer
field tells the user the findings in their language, with the sample
category and what it means."""
# The only plan form of the plain DataNeed flow: its findings rules in one block
RESEARCH_FINDINGS_RULES = ("\n\nRESEARCH FINDINGS\n" + FINDINGS_PLAN_FIELDS + " " + FINDINGS_SAMPLE + "\n"
                           + FINDINGS_SESSION + " " + FINDINGS_RETURNED + INTERPRETING_RULES)
# G3 with the hypothesis plan beside the multi-angle plan (prompt audit pass 2, F2.4 and K1): the findings section holds
# only what complete_analysis returns; the plan and session sentences are steps of HYPOTHESIS PLAN
HYPOTHESIS_FINDINGS_RULES = "\n\nHYPOTHESIS FINDINGS\n" + FINDINGS_RETURNED + "\n" + FINDINGS_MEASURES
# G3: beside the multi-angle findings, a hypothesis plan's answer carries the experiment form
HYPOTHESIS_FINDINGS_CONTRACT = ("For an ANSWER that rests on a completed hypothesis plan, research_findings has one "
                                "entry per experiment instead (hypothesis_id, the backend verdict unchanged, "
                                "interpretation with answer, evidence, usefulness and follow_up). ")
RESEARCH_FINDINGS_CONTRACT = ("research_findings: for an ANSWER that rests on completed research experiments, one "
                              "entry per experiment (hypothesis_id, the backend verdict unchanged, interpretation "
                              "with answer, evidence, usefulness and follow_up); otherwise null. ")
FINDINGS_INSTRUCTION = (
    "research_findings does not match the completed research experiments: {problems}. Copy each experiment's "
    "verdict unchanged from complete_analysis, write all four interpretation parts, state the sample category and "
    "the effective sample or the smallest detectable effect in evidence, and use no verdict wording stronger than "
    "the backend's.")
PLAN_FINDINGS_INSTRUCTION = (
    "Every experiment of the Research Plan needs expected_direction, outcome_horizon_periods, outcome_unit, "
    "success_definition and min_effect (null unless the user named one). Return the plan again with them.")
PLAN_FINDINGS_NOTICE = "The Research Plan below is incomplete and cannot be approved as it stands. "
FINDINGS_NOTICE = ("The interpretation of the research result below did not match the backend's verdict; read the "
                   "figures as unconfirmed. ")
SUPPORTED_WORDING = (r"\b(?:terbukti|didukung|mendukung hipotesis|terkonfirmasi|dikonfirmasi|confirmed|proven|"
                     r"supports? the hypothesis|is supported)\b")
# M26 option B (user decision 2026-10-05): an effect in the expected direction but below the minimum effect the user
# named is PARTIALLY_SUPPORTED; its answer may say "supported in part", never plainly "supported"
BELOW_USER_MINIMUM = "BELOW_USER_MINIMUM_EFFECT"
PARTIAL_WORDING = (r"\b(?:didukung sebagian|sebagian didukung|mendukung sebagian|sebagian mendukung|"
                   r"partially supported|partly supported|supported in part|partially supports?)\b")
REASON_LABELS = {BELOW_USER_MINIMUM: "searah, tetapi lebih kecil dari batas minimal yang Anda sebut"}
NO_EFFECT_WORDING = (r"\b(?:tidak ada (?:efek|pengaruh|perbedaan)|tidak berpengaruh|no (?:effect|difference)|"
                     r"has no effect)\b")
# Multi-Angle Research (AI_ENABLE_MULTI_ANGLE_RESEARCH; MULTI_ANGLE_RESEARCH.md). They replace the Research Plan,
# plan feasibility and research findings rules when the feature is active. No digits: the system prompt is a number
# source for the provenance check (the plan's version constant appears only in the schema skeleton).
MULTI_ANGLE_PLAN_RULES = """

MULTI-ANGLE PLAN
A research question (whether a condition historically precedes an
outcome, or a bounded exploration) starts with a multi-angle Research
Plan, not with data:
1. Before the user approved the plan, use no data: do not call
prepare_data_bundle or any session or research run tool for it. You may
read the catalog to check that the data exists.
2. The plan examines one root hypothesis from at least {min_angles} and at
most {max_angles} angles.{families_rule} An angle is one analytical question
answered by one method of the research library: read it with
get_research_library (the methods, their parameters and data
requirements) and choose from it only. Angles may share a method or a
family when their questions differ; each has its own angle_id,
angle_question and why_distinct. Two angles with the same method,
condition, outcome, comparator, horizon and parameters are one question
and are refused. Choose the angles that would change what the user
concludes, not the most methods: use as few as answer the question well.
Keep every text field of the plan to one short sentence.
3. Before presenting the plan, call check_research_feasibility with one
entry per angle: its design (method, parameters, horizon, unit,
comparisons, multiple-testing policy, holdout, and for a return outcome
the request and price column) and its DataNeedSpec requests and
relationships in the angle's own ids. The backend checks each design
against the method's rules, merges shared data and splits the angles
into bundle groups only when they do not fit one. Present the plan only
after FEASIBLE, with exactly the angles and designs checked. On
REVISION_REQUIRED fix the named angles; on NOT_FEASIBLE drop or narrow
the uncovered angles, or return LIMITATION naming what is missing and
the alternatives.
4. Return response_type RESEARCH_PLAN_CONFIRMATION with research_plan;
answer presents the root hypothesis and each angle (its question, method
in plain words, condition, outcome and comparator) in the user's language
and asks to approve, revise or cancel it. No table names, SQL or Python
in the plan.
5. Wait for the user's reply. Only the application tells you that a plan
was approved; silence, an unrelated reply or your own reading of the
conversation is never an approval.
6. After approval call start_research_run, then run_research_code for
each bundle group in turn: record every angle of the group exactly once
with its research helper, starting from the example call that
start_research_run lists for the angle (request is the data request id
string; the outcome is a forward return the backend computes from a
price column, adding the request id when the price is in another
request of the angle, never a price level or a trailing return
column). Prefer this declarative form, which the backend can
reproduce; research_custom only when no helper fits, and it verifies
execution only. A released table of an earlier result the research
builds on is named in the plan's carried_inputs by its ref (out.oN) and
loaded with load_output; a research session loads only the tables its
plan names. Use the approved parameters, horizon and unit. Then
call complete_research_run with finalize false; it lists any angle not
yet recorded: record it and call it again. Finalize only an angle that
truly cannot be recorded: it becomes NOT_RUN and the other angles still
report.
Never import or modify the sandbox's internal modules (saniti_session,
research_*): an angle is recorded once, and a session whose own state
was changed ends. When run_research_code returns session_recovery,
follow it: record every angle it lists again in the new session, or go
on to complete_research_run when the group is closed."""
MULTI_ANGLE_FINDINGS_RULES = """

MULTI-ANGLE FINDINGS
complete_research_run returns one backend finding per approved angle:
its status (SUPPORTED, PARTIALLY_SUPPORTED, INSUFFICIENT_EVIDENCE,
INVALID or NOT_RUN), evidence_direction (EXPECTED, OPPOSITE or NONE: a
result against the hypothesis is INSUFFICIENT_EVIDENCE with direction
OPPOSITE), the validation level, the effective sample, the estimates
with their adjusted uncertainty, and the research synthesis map. They
are the backend's figures: cite them; never recompute them or state
another status.
For an ANSWER, research_findings has one entry per approved angle:
angle_id, the status unchanged, and an interpretation in four parts:
1. answer: the direct answer to the angle's question in its status's
terms;
2. evidence: the effect against the comparator, its adjusted
uncertainty and the effective sample;
3. usefulness: why it matters in practical terms (for example against
trading costs or a typical move);
4. follow_up: the most informative next step, never a buy or sell
recommendation.
The answer synthesises the angles from the synthesis map, never by
counting statuses as votes: which angles support the root hypothesis,
which do not, where the evidence points the other way, and under which
conditions the results differ. Say the angles agree only when the map
allows an agreement (supported angles of different method families);
angles sharing data are not independent confirmations. Report an
INVALID or NOT_RUN angle as such and never fill it in. Never write that
there is no effect or no difference: an INSUFFICIENT_EVIDENCE angle means
the data could not distinguish an effect. Use supported wording only for
a SUPPORTED or PARTIALLY_SUPPORTED angle. Cite only figures that
complete_research_run returned, the confidence level included."""
# G3 (AI_ENABLE_HYPOTHESIS_PLAN, user decision 2026-10-02): the hypothesis plan (research plan v1 with findings v1)
# beside the multi-angle plan, as a separate path the model chooses per question. It replaces the last sentence of the
# multi-angle rules, which refuses every RESEARCH data need.
MULTI_ANGLE_ONLY_SENTENCE = ("A data need in mode RESEARCH is refused: research runs only through an approved "
                             "multi-angle plan.")
HYPOTHESIS_PLAN_RULES = ("""

HYPOTHESIS PLAN
The hypothesis plan tests hypotheses you formulate yourself from the
question and the data, not limited to the research library: one to four
experiments, each one hypothesis (a condition, an outcome and a baseline
you define).
1. Before the user approved it, do not call submit_data_need_spec,
prepare_data_bundle or any session tool for it. You may read the
catalog. Call check_data_feasibility with the DataNeedSpec the plan
will need (no research_governance) and present the plan only after a
FEASIBLE check; when the check cannot pass, return LIMITATION naming
what is missing and the alternatives.
2. Return RESEARCH_PLAN_CONFIRMATION with research_plan in its
experiment form: the objective, the universe and time scope in plain
words, the analysis frequency, and the experiments, each with its
hypothesis_id, hypothesis, objective, condition, outcome, baseline,
candidate_count, pairwise_comparisons, multiple_testing_policy, whether
a holdout is required and the minimum sample; then assumptions,
limitations and a confirmation_question. answer presents the plan and
asks to approve, revise or cancel it; steps 4 and 5 of the multi-angle
plan (no table names, SQL or Python; only the application approves)
apply.
""" + FINDINGS_PLAN_FIELDS + """
3. After approval, each RESEARCH data need copies research_governance
from its approved experiment: hypothesis_id, hypothesis, objective,
condition, outcome, baseline and multiple_testing_policy exactly;
candidate_count and pairwise_comparisons at most the approved values;
minimum_sample at least the approved value in the same unit; a holdout
when the plan requires one. Any other change needs a revised plan and a
new approval.
4. """ + FINDINGS_SESSION + """
The events and the baseline rows may come from your own code, from
an event study (its events and baseline frames) or from a released
table of an earlier result named in carried_inputs (load_output). The
backend recomputes the statistics from the rows you pass to event_summary
(STATISTICS_VERIFIED); it does not check how you built those rows, so
the answer says the condition was built by the analysis code.
""" + FINDINGS_SAMPLE)
DUAL_RESEARCH_SENTENCE = ("A data need in mode RESEARCH is accepted only for an approved hypothesis plan (below); a "
                          "multi-angle plan runs only through start_research_run.")
ANALYSIS_NEEDS_NO_PLAN = "Mode ANALYSIS needs no plan and proceeds directly."
# M62 (golden test 2026-10-02, question 4): with both plans on, the multi-angle opening still claimed every research
# question, and the model followed it for one explicit hypothesis. One decision rule names both forms: K4 (prompt audit
# pass 2, user decision 2026-10-05) merges the two choice sentences into RESEARCH PLANS, before both plans.
MULTI_ANGLE_OPENING = ("A research question (whether a condition historically precedes an outcome, or a bounded "
                       "exploration) starts with a multi-angle Research Plan, not with data:")
RESEARCH_PLANS_RULES = """

RESEARCH PLANS
A research question starts with a Research Plan, not with data. Choose its form by the question:
- one or a few explicit condition -> outcome hypotheses (the user's own idea, "does X precede Y", "test my idea") take the hypothesis plan, even when a library method could also test them, with no angles the user did not ask for;
- one root hypothesis to examine from several sides with the research library, or a bounded exploration, takes the multi-angle plan.

Never mix the two in one plan."""
# The kinds of value reference, one list item each (prompt audit pass 2, F4: the hypothesis plan's finding is its own
# item, and the last item ends with a full stop)
ANGLE_FINDING_REFERENCE = ("{{finding.<angle_id>.<path>}} a backend finding of complete_research_run, for example "
                           "estimates.primary.estimate, estimates.primary.ci.0, estimates.primary.p_adjusted, "
                           "sample.effective")
HYPOTHESIS_FINDING_REFERENCE = ("{{finding.<hypothesis_id>.<path>}} a hypothesis plan's finding of complete_analysis, "
                                "for example angle_a.difference, angle_a.ci_low, sample.effective")
OUTPUT_REFERENCE = ("{{out.<ref>.<path>}} a released output, by the \"ref\" its tool result shows (out.o1, out.o2, ...): "
                    "rows[<column>=<value>].<column>, content.<field>, or rows.<index>.<column> for a table without an "
                    "identifying column")
FACT_REFERENCE = "{{fact.<n>}} a lookup_fact value"
METRIC_REFERENCE = "{{metric.<key>.<path>}} a query_metric value, by the \"ref\" its tool result shows"


def answer_table_rows(text: str) -> int:
    """EXEC-P2 P2e: the data rows of the longest Markdown table in an answer (header and separator lines not counted)."""
    longest = current = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            current += 0 if re.fullmatch(r"\|[\s:|-]+\|?", stripped) else 1
        else:
            current = 0
        longest = max(longest, current - 1)  # the first row of a table is its header
    return max(longest, 0)


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _without_sentence(text: str, sentence: str, replacement: str) -> str:
    """text with one sentence replaced, matched across the prompt's line breaks."""
    pattern = r"\s+".join(re.escape(word) for word in sentence.split())
    new, count = re.subn(pattern, lambda _: replacement, text)
    if count != 1:
        raise ValueError(f"expected the sentence once in the rules, found it {count} times")
    return new


def _drop_sentence(text: str, sentence: str) -> str:
    """text without one sentence and the line break after it, matched across the prompt's line breaks."""
    pattern = r"\s+".join(re.escape(word) for word in sentence.split()) + r"\s*"
    new, count = re.subn(pattern, "", text)
    if count != 1:
        raise ValueError(f"expected the sentence once in the rules, found it {count} times")
    return new
# AI_ENABLE_VALUE_REFERENCES (P11, user decision 2026-09-30): data figures are written as references the backend fills
# in, and each angle's status, evidence and statistics are rendered from the backend's finding (#15)
VALUE_REFERENCE_RULES = """

VALUE REFERENCES
Never type a figure that comes from data. Write a value reference and
the backend fills in the value, formatted:
{reference_items}

Every referable object in a tool result carries its "ref".
After | add a format: dec:N (N decimals), int, pct:N (a fraction shown
as a percent), pctv:N (already a percent), pp:N (percentage points), rp
(rupiah), x:N (times), p (a p-value, shown as "p = ..." or "p < ..."). A
format shows its own unit: type no unit or "p =" next to the reference.
A value whose unit the backend knows (a finding's estimates, an event
study's columns, a column released with units= in emit_table) is shown
by that unit whichever of pct, pctv and pp you write; declare units= for
every share, percent or p-value column you release. A derived figure
uses diff(a, b), abs(a), ratio(a, b) or chg(a, b) of references, for
example `{{diff(finding.a.estimates.primary.ci.1, finding.a.estimates.primary.ci.0)|pp:2}}`.
Compute anything else in the analysis and release it. A figure the user
wrote, a date and a year may be typed as they are. A text value (a ticker,
a broker, a label) may be referenced without a format and is shown as
written; rows[<index>] works like rows.<index>; inside a Markdown table
write the reference unchanged. A row of a table whose rows are identified
by a column (a broker, a ticker, a code, a date) is referenced by that
column, rows[<column>=<value>], never by position; each row shows _row,
its position in the complete table. A reference that does not resolve is
refused with the references that exist."""
VALUE_REFERENCE_CONTRACT = ("Figures from data are value references {{...}} (see VALUE REFERENCES), never typed "
                            "numbers. ")
ANGLE_NARRATIVE_CONTRACT = ("research_findings: for an ANSWER that rests on a completed multi-angle research run, "
                            "your reading of each approved angle (angle_id, interpretation with answer, usefulness and "
                            "follow_up); the backend adds every approved angle's status, evidence and statistics; "
                            "otherwise null. ")
# 10.1 (plan 2026-10-05 item 10): the addresses a result lists, copied by the model instead of composed from memory
ADDRESS_MENU_MAX = 200  # 1b: lines per tool result (measured 2026-10-06: about 890 tokens per table output on average)
WEB_LOOKUP_TOOLS = frozenset({"find_web_fact", "research_web"})  # P34: checked against the database first
# EXEC-P2 P2a (2026-10-06): no push to check_references before writing; the REFERENCE gate lists every wrong address
# with its nearest replacement at once (10.3), and the tool stays available
ADDRESS_MENU_NOTE = ("Each line is \"name: value as shown [unit] → {{address}}\": write the figure by copying its "
                     "{{address}} as it is and adding a format; never compose an address from memory. A table row not "
                     "listed uses the pattern line with that row's value.")
REFERENCE_INSTRUCTION = (
    "Your response has value references that do not resolve: {problems}. Use only the refs and fields the tool "
    "results of this run show (each referable object carries its \"ref\"), with a known format, or remove the figure.")
REFERENCE_HINT = (" Write each data figure as a value reference {{...}} (see VALUE REFERENCES): the backend fills it "
                  "in and rounds it, so it never needs to be typed.")
# M43 (user decision 2026-09-30): a reference to a field the result does not have stays in the answer as [field]
MISSING_FIELD_LINE = "Angka berikut tidak dapat diisi karena field-nya tidak ada di hasil run ini: {fields}."
# P14 (user decision 2026-10-01): a reference that still does not resolve after its repairs is marked, never the cause
# of a discarded answer (the marker holds no figure, so provenance is unaffected)
UNRESOLVED_LINE = "Sebagian angka tidak dapat diisi dari hasil run ini dan ditandai [nilai tidak tersedia]."
MAX_REFERENCE_REPAIRS = 2  # P16: one repair per distinct set of failing references, at most this many per run
NOT_INTERPRETED = "Tidak diinterpretasikan oleh model."
BACKEND_ONLY_USEFULNESS = "Ringkasan dari backend; interpretasi model untuk sudut ini tidak tersedia."
ANGLE_STATUSES = ("SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE", "INVALID", "NOT_RUN")
SAMPLE_UNITS = {"DATES": "tanggal", "ENTITIES": "entitas", "EVENTS": "kejadian", "ROWS": "baris"}
MULTI_ANGLE_FINDINGS_RULES_REFS = MULTI_ANGLE_FINDINGS_RULES.replace(
    "For an ANSWER, research_findings has one entry per approved angle:\nangle_id, the status unchanged, and an interpretation in four parts:\n1. answer: the direct answer to the angle's question in its status's\nterms;\n2. evidence: the effect against the comparator, its adjusted\nuncertainty and the effective sample;\n3. usefulness: why it matters in practical terms (for example against\ntrading costs or a typical move);\n4. follow_up: the most informative next step, never a buy or sell\nrecommendation.",
    "For an ANSWER, research_findings has your reading of each approved\nangle: angle_id and an interpretation in three parts (the backend adds\neach angle's status, evidence and statistics itself):\n1. answer: the direct answer to the angle's question in its status's\nterms;\n2. usefulness: why it matters in practical terms (for example against\ntrading costs or a typical move);\n3. follow_up: the most informative next step, never a buy or sell\nrecommendation.").replace(
    "Cite only figures that\ncomplete_research_run returned", "Cite figures of\ncomplete_research_run only as value references")
ANGLE_FINDINGS_CONTRACT = ("research_findings: for an ANSWER that rests on a completed multi-angle research run, one "
                           "entry per approved angle (angle_id, the backend status unchanged, interpretation with "
                           "answer, evidence, usefulness and follow_up); otherwise null. ")
MULTI_ANGLE_FIELD_RULES = (
    "angle_id and root_hypothesis_id are lower-case identifiers (a letter, then letters, digits or underscores); every "
    "angle_id, angle_question and analytical design is unique in the plan; at least {min_angles} and at most "
    "{max_angles} angles, each with exactly the design check_research_feasibility checked; "
    "method_family is the family of method_id; every parameters field is present and null when the method does not "
    "use it; multiple_testing_policy is NONE only when candidate_count and pairwise_comparisons are both at most one; "
    "minimum_sample_value and minimum_sample_unit are both set or both null; no SQL, Python, helper calls or table "
    "names anywhere in the plan."
)
CONVERSATION_REUSE_RULES = """

CONVERSATION REUSE
A message of a kept conversation may begin with CONVERSATION RESOURCES:
what earlier messages of the same conversation left in the sandbox.
1. To show again, filter, sort or explain a result already computed,
read its released output with get_session_output by its ref (out.oN;
session_id null for an output of an earlier answer). A released output of an earlier message is a source for
this answer, with its original evidence label and warnings; say when it
was computed. Do not compute it again.
2. For a new computation on the same data, submit the listed
data_need_spec unchanged (any request_group_id, revision one).
prepare_data_bundle then reuses the earlier bundle without a new
extraction (reused true), and open_analysis_session reattaches the warm
session when it is still alive (reused_session true, listing the
variables of the earlier message). Run the new code, emit new outputs
and call complete_analysis as usual; it releases only this message's
outputs.
3. A warm session may be gone (idle timeout, eviction, restart): the
tables of earlier answers are put back from the conversation's store
automatically (restored_outputs) and load with load_output; run again
only the code whose variables you need.
4. Newer data, another period, other columns, entities or filters need
a different DataNeedSpec, and the backend extracts again. Never present
an earlier result as the latest data without its computation date."""
MAX_RESOURCES_NOTE_CHARS = 12000


def conversation_resources_note(resources: dict[str, Any]) -> str:
    """The CONVERSATION RESOURCES note: released outputs first (reading them needs no computation), then bundles with
    the approved data_need_spec to resubmit; the specs of older bundles are dropped first to stay within the bound."""
    head = ("CONVERSATION RESOURCES (application context from earlier messages of this conversation, not from the "
            "user; the ids are for tool calls only):")
    outputs = ["Released outputs (read with get_session_output(session_id, output_id)):"]
    for o in resources.get("released_outputs") or []:
        outputs.append("- " + dumps({k: o.get(k) for k in ("output_id", "session_id", "name", "type", "columns",
                                                            "row_count", "description", "completed_at",
                                                            "evidence_label", "calculation_verified", "warnings",
                                                            "expires_at")
                                     if o.get(k) not in (None, [])}))
    bundles = resources.get("bundles") or []
    specs = [b.get("data_need_spec") for b in bundles]

    def render(with_specs: list[Any]) -> str:
        # P10 (2026-10-01): the spec is labelled as the arguments to send, so it is not wrapped under its own key
        lines = ["Data of earlier data needs. To reuse one without extraction, call submit_data_need_spec with its "
                 "submit_arguments object itself as the arguments (unchanged, not inside another key):"]
        for bundle, spec in zip(bundles, with_specs):
            lines.append("- " + dumps({"bundle_id": bundle.get("bundle_id"), "extracted_at": bundle.get("extracted_at"),
                                       "expires_at": bundle.get("expires_at"), "mode": bundle.get("mode"),
                                       "warm_session": bundle.get("warm_session"),
                                       "datasets": bundle.get("datasets"), "submit_arguments": spec}))
        return "\n".join([head, *(outputs if len(outputs) > 1 else []), *(lines if bundles else [])])

    note = render(specs)
    for index in range(len(specs) - 1, -1, -1):
        if len(note) <= MAX_RESOURCES_NOTE_CHARS:
            break
        specs[index] = "omitted for size"
        note = render(specs)
    return note[:MAX_RESOURCES_NOTE_CHARS]


LOOKUP_RULE = ("Use lookup_fact only for a specific source fact: a value at explicit\n"
               "entities and dates, or a SUM, AVG, MIN, MAX, or COUNT the database\n"
               "computes over an explicit scope; each value carries a fact_id.\n")


def schema_skeleton(schema: dict[str, Any]) -> str:
    """A compact JSON-like form of a strict JSON schema: field names in order, value types, enum values, constants."""
    if "anyOf" in schema:
        options = [schema_skeleton(option) for option in schema["anyOf"] if option.get("type") != "null"]
        return " | ".join(options) + (" | null" if any(o.get("type") == "null" for o in schema["anyOf"]) else "")
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    kind = schema.get("type")
    if kind == "object":
        return "{" + ", ".join(f'"{name}": {schema_skeleton(field_schema)}'
                               for name, field_schema in (schema.get("properties") or {}).items()) + "}"
    if kind == "array":
        return "[" + schema_skeleton(schema.get("items") or {}) + ", ...]"
    return str(kind or "value")


def final_contract_block(contract: str, plan_confirmation: bool, research_findings: bool = False,
                         multi_angle: bool = False, dual: bool = False) -> str:
    """The final-response contract for the system prompt (AI_FINAL_CONTRACT_IN_PROMPT). Tool turns carry no output
    schema, so without it a finished run often answered in prose first and was re-asked for JSON (the 2026-09-26
    stress test: 15% of model time and 20% of cost). With Research Plan confirmation it adds the plan's exact field
    form, generated from the ResearchPlan model, so a plan validates the first time. It contains no digits: numbers
    in the system prompt count as sources for the provenance check."""
    block = FINAL_CONTRACT_PREFIX + contract
    if plan_confirmation and multi_angle and dual:
        # G3: the two plan forms, each with its own field rules, are a section of their own after the plans (K3)
        block += "\n\nresearch_plan has exactly one of the two forms under RESEARCH PLAN FORMS."
    elif plan_confirmation and multi_angle:
        block += ("\nresearch_plan has exactly this form: " + schema_skeleton(strict_parameters_schema(ResearchPlanV2))
                  + "\n" + MULTI_ANGLE_FIELD_RULES)
    elif plan_confirmation:
        block += ("\nresearch_plan has exactly this form: "
                  + schema_skeleton(strict_parameters_schema(ResearchPlanFindings if research_findings
                                                             else ResearchPlan)) + "\n" + PLAN_FIELD_RULES)
    return block


def plan_forms_block() -> str:
    """RESEARCH PLAN FORMS (prompt audit pass 2, K3, user decision 2026-10-05): the exact field form of both plans,
    generated from their models, right after the plan rules that use them instead of inside FINAL RESPONSE."""
    return ("RESEARCH PLAN FORMS\nThe multi-angle plan:\n\n" + schema_skeleton(strict_parameters_schema(ResearchPlanV2))
            + "\n\n" + MULTI_ANGLE_FIELD_RULES + "\n\nThe hypothesis plan:\n\n"
            + schema_skeleton(strict_parameters_schema(ResearchPlanFindings)) + "\n\n" + PLAN_FIELD_RULES)


NUMBER_WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def data_sources_block(tools: frozenset[str]) -> str:
    """DATA SOURCES (prompt audit pass 2, F2.1): where data comes from other than a data need, database first and the
    web last: the metric catalog, the reference tables, then data the catalog does not contain and the web fact. A
    sentence that names a tool is written only when that tool is offered."""
    items = [METRIC_PATH_RULE] if "query_metric" in tools else []
    web_rule = OUTSIDE_DATA_RESEARCH_RULE if "research_web" in tools else \
        OUTSIDE_DATA_WEB_RULE if "find_web_fact" in tools else None
    if web_rule is not None:
        items += ([OUTSIDE_DATA_REFERENCE_RULE] if "lookup_reference" in tools else []) + [web_rule]
    else:
        items.append(OUTSIDE_DATA_RULE)
    return "DATA SOURCES\n" + "\n".join("- " + " ".join(item.split()) for item in items)


def build_system_prompt(lookup_fact: bool, dataneed: bool = False, plan_confirmation: bool = False,
                        period_return: bool = False, final_contract: bool = False,
                        catalog_protocol: bool = False, conversation_reuse: bool = False,
                        methodology: bool = False, plan_feasibility: bool = False,
                        point_in_time: bool = False, derived_frequency: bool = False,
                        research_findings: bool = False, multi_angle: bool = False,
                        angle_limits: tuple[int, int, int] = (2, 6, 0), value_references: bool = False,
                        hypothesis_plans: bool = False, tools: frozenset[str] = frozenset(),
                        tool_envelope: bool = False) -> str:
    """The system prompt for the registered tools. It is fixed for a deployment (AI_ENABLE_LOOKUP_FACT,
    AI_ENABLE_DATANEED, AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION, AI_ENABLE_STANDARD_PERIOD_RETURN,
    AI_FINAL_CONTRACT_IN_PROMPT, AI_ENABLE_TOOL_ENVELOPE), so every call of every run shares one byte-identical
    cacheable prefix. With the DataNeed flow its rules replace those of the Analysis Spec path; the Research Plan and
    named-period-return rules exist only in the DataNeed flow. tools: the names of the offered tools; a sentence that
    names a tool is written only when that tool is offered (P31, prompt audit 2026-10-05 A1, A2, A5). The result is
    formatted as Markdown (prompt audit C and pass 2): block titles as headings, one line per paragraph or item, and a
    paragraph longer than MAX_PARAGRAPH_CHARS one line per rule."""
    template = SYSTEM_PROMPT_TEMPLATE
    # Multi-Angle Research replaces the Research Plan, plan feasibility and findings rules (it needs all three flows)
    multi_angle = multi_angle and dataneed and plan_confirmation and plan_feasibility
    # G3: the hypothesis plan beside the multi-angle plan (needs research findings v1 for its verdicts)
    dual = hypothesis_plans and multi_angle and research_findings
    references = [ANGLE_FINDING_REFERENCE, *([HYPOTHESIS_FINDING_REFERENCE] if dual else []), OUTPUT_REFERENCE,
                  *([FACT_REFERENCE] if lookup_fact else []), *([METRIC_REFERENCE] if "query_metric" in tools else [])]
    value_rules = VALUE_REFERENCE_RULES.replace("{reference_items}", "- " + ";\n- ".join(references) + ".") \
        if value_references else ""
    if multi_angle:
        common, _ = SYSTEM_PROMPT_TEMPLATE.split("DATA QUERY RULES\n", 1)
        plan_rules = MULTI_ANGLE_PLAN_RULES
        mode_sentence = MULTI_ANGLE_ONLY_SENTENCE
        findings = MULTI_ANGLE_FINDINGS_RULES_REFS if value_references else MULTI_ANGLE_FINDINGS_RULES
        research = ""
        if dual:
            # K4: one choice rule (RESEARCH PLANS) before both plans; K3: their field forms right after them
            plan_rules = RESEARCH_PLANS_RULES + _drop_sentence(plan_rules, MULTI_ANGLE_OPENING) + HYPOTHESIS_PLAN_RULES \
                + ("\n\n" + plan_forms_block() if final_contract else "")
            mode_sentence = DUAL_RESEARCH_SENTENCE
            # B4, B5 (prompt audit 2026-10-05): the hypothesis findings cite the backend like the angle findings, and
            # the angles' interpretation parts are those of INTERPRETING RESEARCH
            research = _without_sentence(HYPOTHESIS_FINDINGS_RULES, B4_SENTENCE, B4_REFERENCE) + INTERPRETING_RULES
            if value_references:
                findings = _without_sentence(findings, B5_ANGLE_PARTS, B5_REFERENCE)
        # prompt audit C and pass 2: general -> data -> answer -> research
        sections = [common, CATALOG_PROTOCOL_RULES if catalog_protocol else "", data_sources_block(tools),
                    DATANEED_RULES.replace("{modes_research}", "\n" + mode_sentence + " " + ANALYSIS_NEEDS_NO_PLAN),
                    POINT_IN_TIME_RULES if point_in_time else "", PERIOD_RETURN_RULES if period_return else "",
                    DERIVED_FREQUENCY_RULES if derived_frequency else "",
                    CONVERSATION_REUSE_RULES if conversation_reuse else "", value_rules,
                    METHODOLOGY_RULES if methodology else "", plan_rules, findings, research]
        template = "\n\n".join(section.strip("\n") for section in sections if section.strip())
    elif dataneed:
        common, _ = SYSTEM_PROMPT_TEMPLATE.split("DATA QUERY RULES\n", 1)
        template = common + data_sources_block(tools) + "\n\n" + DATANEED_RULES.replace("{modes_research}", "") \
            + (RESEARCH_PLAN_RULES if plan_confirmation else "") \
            + (PLAN_FEASIBILITY_RULES if plan_confirmation and plan_feasibility else "") \
            + (PERIOD_RETURN_RULES if period_return else "") + (CATALOG_PROTOCOL_RULES if catalog_protocol else "") \
            + (CONVERSATION_REUSE_RULES if conversation_reuse else "") + (METHODOLOGY_RULES if methodology else "") \
            + (POINT_IN_TIME_RULES if point_in_time else "") + (DERIVED_FREQUENCY_RULES if derived_frequency else "") \
            + (RESEARCH_FINDINGS_RULES if research_findings else "") + value_rules
    if final_contract:
        # plan_confirmation and methodology reach here only together with dataneed (see AgentOrchestrator.__init__)
        contract = response_contract(plan_confirmation, methodology, research_findings, multi_angle,
                                     value_references, dual)
        template = template.replace(STRICT_SCHEMA_LINE, final_contract_block(contract, plan_confirmation,
                                                                             research_findings, multi_angle, dual))
    # Multi-Angle Research: the negotiated angle limits (AI_RESEARCH_MIN_ANGLES / MAX_ANGLES / MIN_FAMILIES), in words
    low, high, families = angle_limits
    families_rule = (f" The angles use at least {NUMBER_WORDS[families]} of the five method families."
                     if families else "")
    sources = ("a lookup_fact result, " if lookup_fact else "") \
        + ("a query_metric result, " if "query_metric" in tools else "") \
        + ("a lookup_reference row, " if "lookup_reference" in tools else "") \
        + ("a web fact (stated as a web fact), " if "find_web_fact" in tools or "research_web" in tools else "")
    outside = OUTSIDE_DATA_RULE  # the Analysis Spec path keeps it under RESEARCH RULES
    if "research_web" in tools or "find_web_fact" in tools:
        outside = (OUTSIDE_DATA_RESEARCH_RULE if "research_web" in tools else OUTSIDE_DATA_WEB_RULE) \
            + (OUTSIDE_DATA_REFERENCE_RULE if "lookup_reference" in tools else "")
    text = (template.replace("{tool_results}", "TOOL RESULTS\n" + TOOL_ENVELOPE_BODY + "\n" if tool_envelope else "")
            .replace("{lookup_rule}", LOOKUP_RULE if lookup_fact else "")
            .replace("{number_sources}", sources)
            .replace("{other}", "other " if "query_metric" in tools else "")
            .replace("{outside_data_rule}", outside)
            .replace("{min_angles}", NUMBER_WORDS[low]).replace("{max_angles}", NUMBER_WORDS[high])
            .replace("{families_rule}", families_rule))
    return markdown_prompt(text)


# Prompt audit 2026-10-05 (PROMPT_AUDIT_2026-10-05.md, approved by the user): sentences derived from the offered tools
OUTSIDE_DATA_RULE = ("Data the catalog does not contain (for example macro data, yields,\nfundamentals, or news) is "
                     "unavailable: say so and never substitute\nanother dataset.")
OUTSIDE_DATA_WEB_RULE = (
    "Data the catalog does not contain (for example macro data, yields,\nfundamentals, or news) is not in the "
    "database: say so and never substitute\nanother dataset. One public fact about a company (its status, "
    "ownership,\ngroup or index membership) can be looked up with find_web_fact and is\nshown as a web fact; a web "
    "fact describes and never becomes a series, a\ndataset or an input of a calculation.")
# Item 12 (plan 2026-10-05, user decision): with research_web, information outside the database is looked up for
# context or when the database lacks it; the sentences "one public fact about a company ... never becomes a series"
# and "macro data ... is not in the database" are removed together with the new tool
OUTSIDE_DATA_RESEARCH_RULE = (
    "Information the catalog does not contain (for example macro data, events,\nnews, ownership or group membership) "
    "is looked up with research_web, for\ncontext or when the database lacks it, and is shown as a web fact; for\n"
    "market data the database wins. Cite web values by their references; an\nevent date may set an analysis "
    "period, but a web number is never an input\nof a calculation.")
OUTSIDE_DATA_REFERENCE_RULE = ("\nAn attribute the reference tables hold (a sector, an industry, a company\n"
                               "profile) is read with lookup_reference, never from the web.")
METRIC_PATH_RULE = ("An official metric of the metric catalog over periods is answered by\nquery_metric in one "
                    "call, without a data need or a session.\n")
B4_SENTENCE = "They are the backend's numbers: cite them; never recompute them or state another verdict."
B4_REFERENCE = "They are the backend's numbers and are cited like the angle findings above."
B5_ANGLE_PARTS = ("1. answer: the direct answer to the angle's question in its status's terms; 2. usefulness: why it "
                  "matters in practical terms (for example against trading costs or a typical move); 3. follow_up: "
                  "the most informative next step, never a buy or sell recommendation.")
B5_REFERENCE = ("answer (in the angle status's terms), usefulness and follow_up, each as\ndefined under "
                "INTERPRETING RESEARCH below.")
HEADING = re.compile(r"[A-Z][A-Z0-9 :/()-]{2,68}")
ITEM = re.compile(r"(\d+\. |- )")
# Prompt audit pass 2 (F1, user decision 2026-10-05): a paragraph or item longer than this is written one rule per line
MAX_PARAGRAPH_CHARS = 600


def _split_top_level(text: str, marks: str) -> list[str]:
    """text cut after each mark that is followed by a space and stands outside brackets, so a parenthesis, a value
    reference or a list in brackets is never cut. The pieces keep their own punctuation."""
    pieces, depth, start = [], 0, 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char in marks and depth == 0 and text[index + 1:index + 2] == " ":
            pieces.append(text[start:index + 1].strip())
            start = index + 1
    pieces.append(text[start:].strip())
    return [piece for piece in pieces if piece]


def _rule_lines(line: str) -> list[str]:
    """One long paragraph or item as one line per rule: its sentences, and a sentence still too long split at its
    semicolons. An item keeps its marker on the first rule and indents the others under it. No list marker is added:
    a "- " per rule cost about two percent more tokens than the whole pass-2 budget allows. Words are not changed."""
    if len(line) <= MAX_PARAGRAPH_CHARS or line.startswith(("{", "[", "## ", " ")):
        return [line]
    marker = ITEM.match(line)
    prefix, body = (marker.group(1), line[marker.end():]) if marker else ("", line)
    rules = [part for sentence in _split_top_level(body, ".?!")
             for part in (_split_top_level(sentence, ";") if len(sentence) > MAX_PARAGRAPH_CHARS else [sentence])]
    if len(rules) == 1:
        return [line]
    return [prefix + rules[0], *(" " * len(prefix) + rule for rule in rules[1:])]


def markdown_prompt(text: str) -> str:
    """Prompt audit C (2026-10-05): the prompt as Markdown for the model. A block title (a line in capitals) becomes a
    "## " heading; lines wrapped inside a sentence are joined, so each paragraph and each numbered or bulleted item is
    one line, and (pass 2, F1) a paragraph or item longer than MAX_PARAGRAPH_CHARS is then written one line per rule.
    Words are not changed, and formatting a formatted prompt again changes nothing (its rule lines join back into the
    same paragraph and split the same way)."""
    out: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            out.append("")
        elif HEADING.fullmatch(stripped):
            if out and out[-1] != "":
                out.append("")
            out.append("## " + stripped.rstrip(":"))
        elif ITEM.match(stripped) or not out or out[-1] == "" or out[-1].startswith("## "):
            out.append(stripped)
        else:
            out[-1] = out[-1] + " " + stripped
    return "\n".join(rule for line in out for rule in _rule_lines(line))


SYSTEM_PROMPT = build_system_prompt(True)
RUN_CONTEXT_NOTE = ("Run context from the application, not from the user: the reference date is {date} ({tz}). A "
                    "relative or open-ended period ('last 3 months', 'since <date>') ends on this date; the data may "
                    "end earlier.")

VALIDATION_GATE_INSTRUCTION = (
    "Your answer relies on Python analyses that did not pass validation: {findings}. A result that failed "
    "validation must not be presented as a valid answer. Fix the analysis and run it again, request the missing "
    "data, or return response_type \"LIMITATION\" that states what was and was not validated."
)
GATE_NOTICE = ("Validation did not pass for the analysis behind this response; any figures below are not a "
               "validated answer to the request. ")
ROUTING_INSTRUCTION = (
    "The request asks for {families}, which only a Python analysis whose validation passed can answer; source "
    "facts alone are not enough and numbers must not be calculated by you. Use create_analysis_spec, "
    "prepare_analysis_data, and run_python_analysis, or return response_type \"LIMITATION\" stating what was not "
    "calculated."
)
ROUTING_NOTICE = ("This request needs a validated analysis ({families}), and none supports this response; any "
                  "figures below are not a validated answer. ")
PROVENANCE_INSTRUCTION = (
    "These numbers in your answer have no governed source in this run: {numbers}. Every number must come from a "
    "lookup_fact result, the output of an analysis whose validation passed, the user's message, the approved spec, "
    "or a prepared dataset; outputs of failed or incomplete analyses and preview rows are not sources. Remove or "
    "correct those numbers, obtain them with the right tool, or return response_type \"LIMITATION\"."
)
PROVENANCE_NOTICE = ("Some figures below could not be traced to a governed source in this run and are not "
                     "validated: {numbers}. ")
# Predictive or causal wording about market outcomes (English and Indonesian). A match governed by a negation in its
# clause, before or after it ("not a prediction", "bukan penyebab", "menyebabkan … tidak terbukti"), is not a claim.
PREDICTIVE_PATTERN = (
    r"\b(?:will|is likely to|are likely to|is expected to|are expected to|akan|diperkirakan akan|cenderung akan)\s+"
    r"(?:\w+\s+){0,2}?(?:rise|increase|climb|rally|rebound|outperform|fall|decline|drop|underperform|naik|turun|"
    r"menguat|melemah|rebound|berbalik|mengungguli)\b|\bpredict(?:s|ed|ive|ion|ions)?\b|\bforecast(?:s|ed)?\b|"
    r"\bmemprediksi\b|\bprediksi\b|\bmeramalkan\b|\bbuy signal\b|\bsell signal\b|\bsinyal (?:beli|jual)\b"
)
CAUSAL_PATTERN = (r"\bcaus(?:e|es|ed|al|ally|ation)\b|\bdrives? (?:the )?(?:price|return)s?\b|\bmenyebabkan\b|"
                  r"\bmengakibatkan\b|\bpenyebab\b")
NEGATION_PATTERN = (r"\b(?:not|no|never|cannot|can't|isn't|aren't|doesn't|don't|without|rather than|bukan|tidak|"
                    r"tanpa|belum|jangan)\b")
# DataNeed flow: the backend verifies data coverage, never the formulas, so an answer may not say the calculation
# was verified or validated (English and Indonesian).
VERIFIED_CALCULATION_PATTERN = (
    r"\b(?:calculations?|computations?|formulas?|results?|perhitungan|kalkulasi|hasil|rumus)\s+(?:\w+\s+){0,3}?"
    r"(?:(?:has|have|was|were|is|are|been|telah|sudah|sudah\s+di|telah\s+di)\s+)*(?:independently\s+)?"
    r"(?:verified|validated|diverifikasi|divalidasi|terverifikasi|tervalidasi)\b|"
    r"\b(?:verified|validated|terverifikasi|tervalidasi)\s+(?:calculations?|results?|perhitungan|hasil)\b"
)
# P17 (user decision 2026-10-01): "BBCA terbukti naik" claims proof; a historical pattern proves nothing
PROOF_PATTERN = r"\b(?:terbukti|membuktikan|dibuktikan|proven|proves?)\b"
CLAIM_NOTES = {
    "CAUSAL": "Klaim sebab-akibat: analisis historis tidak dapat membuktikan sebab.",
    "PREDICTIVE": "Klaim prediksi: pola historis bukan ramalan.",
    "PROOF": "Klaim pembuktian: hasil historis menunjukkan pola, bukan bukti.",
    "VERIFIED_CALCULATION": "Klaim verifikasi: backend memeriksa cakupan data, bukan rumus perhitungan.",
}
CLAIM_ANNOTATION_LINE = ("Kalimat bercetak miring ditandai: klaim sebab-akibat, prediksi, pembuktian atau verifikasi "
                         "perhitungan tidak didukung oleh analisis historis ini.")
SENTENCE_BOUNDARY = re.compile(r"[.!?:;\n|]")  # a label ("Ringkasnya:") or a clause ends the span too
RESEARCH_CLAIMS = {"HISTORICAL_PATTERN", "PREDICTIVE", "EXPLORATORY", "SCENARIO"}


def annotate_claims(text: str, spans: list[tuple[str, int, int]]) -> tuple[str, list[dict[str, Any]]]:
    """P17 (user decision 2026-10-01): each flagged claim's sentence in italics (the phrase alone when the sentence
    already holds Markdown emphasis) and one annotation per italic span: kind, quote, start/end of the quote in the
    returned text, note. Nothing is removed and the answer is never rejected for it."""
    marks: dict[tuple[int, int], set[str]] = {}
    for kind, start, end in spans:
        left = max((m.end() for m in SENTENCE_BOUNDARY.finditer(text, 0, start)), default=0)
        right_match = SENTENCE_BOUNDARY.search(text, end)
        right = right_match.start() if right_match else len(text)
        while left < start and text[left] in " \t-#>":
            left += 1
        while right > end and text[right - 1] in " \t":
            right -= 1
        if "*" in text[left:right] or "_" in text[left:right]:
            left, right = start, end
        marks.setdefault((left, right), set()).add(kind)
    pieces, annotations, cursor, shift = [], [], 0, 0
    for (left, right), kinds in sorted(marks.items()):
        if left < cursor:
            continue  # overlaps a span already marked
        pieces.append(text[cursor:left])
        quote = text[left:right]
        pieces.append(f"*{quote}*")
        start = left + shift + 1
        for kind in sorted(kinds):
            annotations.append({"kind": kind, "quote": quote, "start": start, "end": start + len(quote),
                                "note": CLAIM_NOTES[kind]})
        shift += 2
        cursor = right
    pieces.append(text[cursor:])
    return "".join(pieces), annotations
DEFINITION_CLAIM_INSTRUCTION = (
    "The answer says its result follows the definition of an earlier result, but the backend sees otherwise: "
    "{problems}. Either use the earlier result's definition (open it with load_output and keep its filters, period "
    "and thresholds), or keep your result and state plainly how its definition differs instead of calling it "
    "consistent.")
DEFINITION_CLAIM_NOTICE = ("Catatan sistem: klaim bahwa hasil ini mengikuti definisi hasil sebelumnya tidak didukung; "
                           "{problems}.")
DATANEED_GATE_INSTRUCTION = (
    "Your answer relies on data analysis that did not complete: {findings}. Only outputs released by "
    "complete_analysis may support an answer. Follow its next_action (process what was not read, revise the "
    "DataNeedSpec, or complete the analysis), or return response_type \"LIMITATION\" that states what was not "
    "completed."
)
DATANEED_ROUTING_INSTRUCTION = (
    "The request asks for {families}, which only an analysis completed with complete_analysis can answer; numbers "
    "must not be calculated by you. Use submit_data_need_spec, prepare_data_bundle, open_analysis_session, "
    "run_python and complete_analysis, or return response_type \"LIMITATION\" stating what was not calculated."
)
DATANEED_PROVENANCE_INSTRUCTION = (
    "These numbers in your answer have no governed source in this run: {numbers}. Every number must come from a "
    "released output of a completed analysis{lookup}, the user's message, the DataNeedSpec, or the bundle summary; "
    "run_python stdout, unreleased outputs and preview rows are not sources. Remove or correct those numbers, obtain "
    "them from a released output, or return response_type \"LIMITATION\"."
)
# P25 (golden test rerun 2026-10-02, turn 4): a complete answer was forced to LIMITATION over "persentil ke-90", the
# threshold its own code chose; the refusal did not say where the number came from. Code literals stay sources of the
# methodology only (a result typed into code must not pass), but the refusal names them and the two right places
CODE_LITERAL_HINT = (" Of these, {numbers} appear only as literals in the code that ran (a parameter such as a "
                     "threshold, a percentile or a window): state a parameter in methodology, or release it with the "
                     "result (for example emit_json of the parameters) and reference it; a number typed into code is "
                     "not a result.")
DATANEED_GATE_NOTICE = ("The data analysis behind this response did not complete; any figures below are not a "
                        "verified answer to the request. ")
DATANEED_ROUTING_NOTICE = ("This request needs a completed analysis ({families}), and none supports this response; "
                           "any figures below are not a verified answer. ")
METHODOLOGY_INSTRUCTION = (
    "Your response rests on a completed analysis but methodology is empty. Add methodology: the data, the steps, the "
    "methods and their parameters in plain words, describing only what actually ran.")
METHODOLOGY_PROVENANCE_INSTRUCTION = (
    "These numbers in methodology have no source in this run: {numbers}. Its numbers must come from the same sources "
    "as the answer, the approved plan, the DataNeedSpec or the code that ran. Remove or correct them.")
METHODOLOGY_MISSING_LINE = "No methodology note was provided for this response."
METHODOLOGY_WITHHELD_LINE = "The methodology note was withheld because it cited figures without a source: {numbers}."
# EXEC-E (user decision 2026-10-06: get_evidence and its gate removed): a figure the model typed from its own code is
# written by its address instead (asked once; an edit is enough)
TYPED_FIGURES_INSTRUCTION = (
    "Your answer types these figures from this run's results without a value reference: {numbers}. Write each as its "
    "{{{{address}}}} from the addresses list of the result that released it, or remove the figure; an edit is enough.")
TYPED_FIGURES_LINE = ("Angka berikut diketik dari hasil analisis tanpa alamat, jadi tidak dibaca ulang dari tabel hasil: "
                      "{numbers}.")
# G23 C (K2, PLAN_FINAL_2026-10-04.md): every one-time gate request says it is asked once and the way out
# EXEC-R R2 (2026-10-06): with an edit offered, {"keep": true} keeps the stored draft (h_add turn 2 resent 8,660 tokens
# unchanged in 109 s to take this way out)
GATE_ONCE_NOTE = (" This check asks only once. If you cannot make the change with the tools you have in this step, keep "
                  'the answer: reply {"keep": true} when an edit is offered below, otherwise send it again unchanged; '
                  "it is then delivered with the backend's note.")
# G23 B: figures the backend computed or recomputed itself (lookup facts, Governor aggregates, recomputed analyses)
BACKEND_RECOMPUTED_KINDS = frozenset({"FACT", "DATABASE_AGGREGATE", "CALCULATION_VERIFIED"})
EVIDENCE_BACKEND_LINE = ("Angka jawaban ini dihitung atau dihitung ulang oleh backend (fakta, agregat Governor, metrik "
                         "resmi atau analisis yang dihitung ulang), sehingga tidak dicek ulang terpisah.")
# G23 D (K3): the step limit or time ran out; the last draft still reaches the user
EXHAUSTED_LINE = "Pemeriksaan tidak selesai ({reason}). Kode permintaan: {request_id}."
EXHAUSTED_NO_DRAFT = "Tidak bisa dihitung: {reason} sebelum ada jawaban. Kode permintaan: {request_id}."
EXHAUSTED_REASONS = {"MAX_ITERATIONS": "batas langkah tercapai", "ANALYSIS_TIMEOUT": "batas waktu tercapai"}
# O4: every figure from the model's code is a value reference; the backend read each from its released table
EVIDENCE_REFERENCED_LINE = ("Angka hasil analisis di jawaban ini dibaca backend langsung dari tabel hasil yang dirujuk "
                            "(bukti DIRUJUK), tanpa hitung ulang terpisah dari kode AI.")
DATANEED_PROVENANCE_NOTICE = ("Some figures below could not be traced to a released analysis output or another "
                              "governed source in this run: {numbers}. ")
WARNING_LINES = {
    "HISTORICAL_REFERENCE_USES_CURRENT_STATE": "Classifications come from the current state of the reference "
                                               "table, not from the classification valid at each historical date.",
    "HISTORY_BUFFER_SHORTFALL": "Some entities have fewer observations before a range than the requested warm-up "
                                "history.",
    "FUTURE_BUFFER_SHORTFALL": "Some entities have fewer observations after a range than requested (the data may "
                               "end at the reference date).",
    "FREQUENCY_GAPS": "Some entities miss dates of the dataset's own calendar inside a range.",
    "EMPTY_RANGE": "A requested range has no data.",
    "PARTIAL_RANGE_COVERAGE": "A requested range is only partly covered by the data.",
    "EMPTY_ENTITY": "An entity named in the request has no data.",
    "NULL_VALUES": "Some delivered values are missing (null).",
    "DUPLICATE_KEYS": "Some rows repeat their key columns.",
    "CURRENT_STATE_COLUMN": "Some columns hold today's value on every historical row (for example the current sector "
                            "or broker classification), not the value of each date.",
}
PIT_FALLBACK_LINE = ("Point-in-time data was requested but is not available ({detail}); these results use current "
                     "reference data (historical descriptive), not what was known at each date.")

RESPONSE_FORMAT_NAME = "saniti_agent_response"
# M48 (2026-10-01): the refused draft goes back whole, so a repair sees what it repairs (it was 4000 characters from the
# first version on, with no recorded reason, and the mode 4 answers reached 19,000); the draft is bounded by
# AI_MAX_OUTPUT_TOKENS and the context by the per-turn CONTEXT_LIMIT check
REJECTED_OUTPUT_ECHO_CHARS = 200_000
JSON_ERROR_CONTEXT = 80  # EXEC-R R4a: characters shown on each side of where the final JSON breaks
RESPONSE_CONTRACT = (
    "Return one JSON object with exactly these fields: "
    "response_type: \"ANSWER\" when the request can be answered, \"CLARIFICATION\" only when an "
    "ambiguity in the user's request materially prevents a reliable answer, or \"LIMITATION\" when "
    "a required capability is unavailable; "
    "answer: the answer for the user (for LIMITATION, what can reliably be said; empty string for "
    "CLARIFICATION); "
    "clarification_question: one focused question for CLARIFICATION, otherwise null; "
    "assumptions: list of strings; limitations: list of strings. "
    "The output format is already defined by the application; never ask the user about it."
)
# With Research Plan confirmation the contract gains one response type and one field.
PLAN_RESPONSE_CONTRACT = RESPONSE_CONTRACT.replace(
    "or \"LIMITATION\" when a required capability is unavailable; ",
    "\"RESEARCH_PLAN_CONFIRMATION\" when a research question needs the user's approval of a Research Plan before "
    "any data is used, or \"LIMITATION\" when a required capability is unavailable; ").replace(
    "assumptions: list of strings; limitations: list of strings. ",
    "assumptions: list of strings; limitations: list of strings; research_plan: the Research Plan object for "
    "RESEARCH_PLAN_CONFIRMATION (answer then presents it and asks to approve, revise or cancel), otherwise null. ")
METHODOLOGY_CONTRACT = ("methodology: for an ANSWER or LIMITATION that rests on an analysis, how it was reached in "
                        "plain words (data, steps, methods, parameters); otherwise null. ")


def response_contract(plan_confirmation: bool, methodology: bool = False, research_findings: bool = False,
                      multi_angle: bool = False, value_references: bool = False, dual: bool = False) -> str:
    """The final-response contract text: RESPONSE_CONTRACT, with the Research Plan, methodology and research findings
    fields when on (Multi-Angle Research: the per-angle findings)."""
    contract = PLAN_RESPONSE_CONTRACT if plan_confirmation else RESPONSE_CONTRACT
    if methodology:
        contract = contract.replace("The output format is already defined", METHODOLOGY_CONTRACT
                                    + "The output format is already defined")
    if multi_angle and plan_confirmation:
        contract = contract.replace("The output format is already defined",
                                    (ANGLE_NARRATIVE_CONTRACT if value_references else ANGLE_FINDINGS_CONTRACT)
                                    + (HYPOTHESIS_FINDINGS_CONTRACT if dual else "")
                                    + "The output format is already defined")
    elif research_findings and plan_confirmation:
        contract = contract.replace("The output format is already defined", RESEARCH_FINDINGS_CONTRACT
                                    + "The output format is already defined")
    if value_references:
        contract = contract.replace("The output format is already defined", VALUE_REFERENCE_CONTRACT
                                    + "The output format is already defined")
    return contract


STRICT_SCHEMA_LINE = "Return only the response defined by the provided strict output schema."
FINAL_CONTRACT_PREFIX = (
    "When no further tool call is needed, your reply is the final response itself: one JSON object and nothing "
    "else, with no text before or after it and no code fence. The application parses it as JSON, so a prose draft "
    "is rejected and costs another turn. "
)
PLAN_FIELD_RULES = (
    "experiment_id and hypothesis_id are lower-case identifiers (a letter, then letters, digits or underscores), "
    "each unique in the plan; one to four experiments; multiple_testing_policy is NONE only when candidate_count and "
    "pairwise_comparisons are both at most one; minimum_sample_value and minimum_sample_unit are both set or both "
    "null; no SQL, Python, helper calls or table names anywhere in the plan."
)
FINALIZE_PREFIX = (
    "Provide your final response to my latest message now, based only on the conversation and "
    "tool results above. Do not call tools. "
)
FINALIZE_INSTRUCTION = FINALIZE_PREFIX + RESPONSE_CONTRACT
# M78 (ma-qa-20261004a q2): a turn with neither text nor a tool call is an interrupted generation (the provider stopped
# after the reasoning), not a draft answer; it is retried with the same tools instead of asking for the final response
EMPTY_TURN_NOTE = ("Application note, not from the user: your previous turn ended without output (the generation "
                   "stopped). Continue the task from where it was: call the next tool, or give the final response.")
MAX_EMPTY_TURN_RETRIES = 2
CONTEXT_BUDGET_PREFIX = (
    "Tool access has ended because this run reached its context budget; no further tools can be "
    "called. Answer my latest message using only the information already retrieved in the tool "
    "results above, and do not state anything about records that were not retrieved. Return "
    "response_type \"LIMITATION\", or \"ANSWER\" only if the retrieved information fully answers "
    "the request. In both cases, limitations must state that tool access ended because the context "
    "budget was reached, what was read (for example which catalogs and pages, using "
    "rows_before_this_page, returned_rows and total_rows), and what remains unread (for example "
    "catalogs whose last page had has_more=true). "
)
CONTEXT_BUDGET_INSTRUCTION = CONTEXT_BUDGET_PREFIX + RESPONSE_CONTRACT

# Research Plan turns. The notes are application context placed before the user's reply; the guard in
# submit_data_need_spec, not these notes, is what prevents unapproved research.
BASE_TYPES = frozenset({"ANSWER", "CLARIFICATION", "LIMITATION"})
SESSION_ID_RE = re.compile(r"^sess_[0-9a-f]{24}$")
ALL_TYPES = BASE_TYPES | {"RESEARCH_PLAN_CONFIRMATION"}
PLAN_TYPES = frozenset({"RESEARCH_PLAN_CONFIRMATION", "CLARIFICATION", "LIMITATION"})
RESEARCH_RUN_TOOLS = frozenset({"start_research_run", "run_research_code", "complete_research_run"})
# G23 A: the tools an analysis repair calls (the gates that ask for one declare them)
LEGACY_ANALYSIS_TOOLS = frozenset({"create_analysis_spec", "prepare_analysis_data", "run_python_analysis"})
DATANEED_ANALYSIS_TOOLS = frozenset({"submit_data_need_spec", "prepare_data_bundle", "open_analysis_session",
                                     "run_python", "complete_analysis"})
# get_research_library (C07) is registered only while multi-angle research serves the research library
DISCOVERY_TOOLS = frozenset({"get_system_capabilities", "discover_catalog", "get_catalog_details",
                             "read_catalog_rows", "get_dimension_values", "get_research_library",
                             "get_method_guide"})
# 4b (G2_G3_REACTIVATION_PLAN.md): the menu offered at the start of every run when the method guides are served
METHOD_MENU_HEADER = ("ANALYSIS METHODS (application context from the backend, not from the user): the analysis paths "
                      "and helpers this deployment offers, when to use each, when not to, and how the backend checks "
                      "its result. Choose the method that fits the question; open its manual with "
                      "get_method_guide(name) before using it the first time in this conversation.")
PLAN_NOTE_PREFIX = "Application note, not from the user: "
APPROVED_NOTE = (PLAN_NOTE_PREFIX + "the user approved Research Plan {plan_id}; the approval was verified. Carry out "
                 "its experiments now. Each RESEARCH data need copies research_governance from its experiment as the "
                 "{rules} rules say; a change beyond them needs a revised plan and a new approval. "
                 "The approved plan: {plan}")
APPROVED_NOTE_V2 = (
    PLAN_NOTE_PREFIX + "the user approved multi-angle Research Plan {plan_id}; the approval was verified. Carry it out "
    "now: start_research_run, then run_research_code for each bundle group (bundle groups and their angles: "
    "{groups}), then complete_research_run. Record every approved angle once with its research helper and the approved "
    "parameters; a change needs a revised plan and a new approval. The approved plan: {plan}")
FEASIBLE_DRAFT_NOTE = (" Before approval this plan's data passed check_data_feasibility (draft {draft_id}): start from "
                       "this DataNeedSpec for each experiment (revision one of a new request_group_id per experiment, "
                       "with research_governance); keep its tables, columns, scopes, ranges and relationships, so no "
                       "catalog reading is needed unless the validator asks for a change: {spec}")
PLAN_FEASIBILITY_INSTRUCTION = (
    "A Research Plan is presented only after its data passed check_data_feasibility in this run (FEASIBLE). Call "
    "check_data_feasibility with the DataNeedSpec the plan needs; when the check cannot pass, return response_type "
    "\"LIMITATION\" saying what is missing and which alternatives exist.")
PLAN_NOT_FEASIBLE_NOTICE = ("A Research Plan was not issued: its data could not be confirmed as available and within "
                            "the limits of one run. ")
PLAN_NOT_EXECUTED_INSTRUCTION = (
    "The user approved the Research Plan, but no RESEARCH data need was submitted in this run. Carry out the approved "
    "experiments now (submit_data_need_spec with mode RESEARCH, then prepare the bundle, run and complete the "
    "analysis), or, only if the data truly cannot be obtained, return response_type \"LIMITATION\" naming the exact "
    "tool result that blocks it.")
PLAN_NOT_EXECUTED_LINE = ("The approved Research Plan was not executed in this message, so it remains pending; "
                          "approving it again runs it.")
REVISE_NOTE = (PLAN_NOTE_PREFIX + "the user asked to revise Research Plan {plan_id}: {instruction}\nReturn the revised "
               "plan as RESEARCH_PLAN_CONFIRMATION (it needs a new approval), or CLARIFICATION if the change is "
               "unclear. A new success threshold the user states (for example \"ubah jadi 5%\") goes into the "
               "experiment's success_rule exactly as the user wrote it; when the user's wish has no number, propose one "
               "and ask. No data may be used in this turn; you may read the catalog. The previous plan{unverified}: "
               "{plan}")
REPLAN_NOTES = {
    "RESEARCH_PLAN_TOKEN_EXPIRED": (
        PLAN_NOTE_PREFIX + "the user's reply to Research Plan {plan_id} arrived after the plan expired, so it cannot "
        "be used. Present the plan again as RESEARCH_PLAN_CONFIRMATION for a new approval, unchanged unless the "
        "dates or data require a change, and say in the answer that the plan was made earlier and expired before "
        "the approval, so it needs the user's approval again. No data may be used in this turn. The expired plan: "
        "{plan}"),
    "RESEARCH_PLAN_TOKEN_INVALID": (
        PLAN_NOTE_PREFIX + "the Research Plan approval sent with this message could not be verified, so no plan is "
        "approved. Present a Research Plan again as RESEARCH_PLAN_CONFIRMATION, from the conversation, for a new "
        "approval. No data may be used in this turn."),
}
ANALYSIS_PATH_NOTE = (PLAN_NOTE_PREFIX + "the caller fixed this request to the ANALYSIS path. Answer it as an analysis: "
                      "every data need uses mode ANALYSIS (a RESEARCH data need is refused) and no Research Plan is "
                      "proposed. The results are descriptive statistics of the historical data: no hypothesis test, "
                      "no significance test and no correction for the many filters or groups compared, so report "
                      "them as what happened in this data, never as a verdict, a reliable pattern, a cause, a "
                      "prediction or a trading signal, and say so in the answer. When the user leaves a parameter "
                      "open (a window, a threshold, a benchmark), choose a reasonable value, state it in "
                      "assumptions, and answer.")
RESEARCH_PATH_NOTE = (PLAN_NOTE_PREFIX + "the caller fixed this request to the RESEARCH path. Treat the question as "
                      "research: propose a Research Plan (RESEARCH_PLAN_CONFIRMATION) under the RESEARCH PLAN "
                      "CONFIRMATION rules, or ask a CLARIFICATION when it cannot be planned; every data need uses "
                      "mode RESEARCH (an ANALYSIS data need is refused).")
# Mode 4 (app/mode4.py): the seconds left of the whole mode 4 request, so its sub-runs together stay within
# AI_MAX_ANALYSIS_SECONDS (None: a run has AI_MAX_ANALYSIS_SECONDS of its own)
current_time_budget: contextvars.ContextVar[float | None] = contextvars.ContextVar("current_time_budget", default=None)
# EXEC-P2 P2e (2026-10-06): answer-length targets, measured and logged (ai_answer_long), never a refusal. The longest
# drafts of golden test 06b were 10-17 thousand characters; writing and checking the answer took 41% of model time
ANSWER_TARGET_CHARS = 2500
MODE4_PART_TARGET_CHARS = 1500  # each part of a mode 4 reply (app/mode4.py sets it for its steps)
ANSWER_TABLE_ROWS = 10
current_answer_target: contextvars.ContextVar[int] = contextvars.ContextVar("current_answer_target",
                                                                            default=ANSWER_TARGET_CHARS)
ANGLE_COUNT_NOTE = (PLAN_NOTE_PREFIX + "for this request the Research Plan has {count} (check_research_feasibility and "
                    "the plan check use this count; it replaces the angle count stated in the instructions).")
ANALYSIS_PATH_LINE = ("Analysis path (fixed by the caller): descriptive historical statistics without a significance "
                      "test or a correction for multiple comparisons; not a verdict, a cause, a prediction or a "
                      "trading signal.")
CANCEL_NOTE = (PLAN_NOTE_PREFIX + "the user cancelled the Research Plan. Nothing was run. Acknowledge it briefly in "
               "the user's language with response_type ANSWER and do not start any analysis.")
UNRELATED_NOTE = (PLAN_NOTE_PREFIX + "Research Plan {plan_id} is waiting for the user's decision, and this message "
                  "neither approves, revises nor cancels it. Return response_type CLARIFICATION that asks whether to "
                  "approve, revise or cancel the plan. Do not run anything.")
TRUNCATED_FINAL_INSTRUCTION = (
    "The response was cut off at the output limit ({limit} tokens, reasoning included), so it is not complete JSON. "
    "Return the whole response again, shorter, and keep the reasoning before it brief.")
TRUNCATED_PLAN_HINT = (" For a Research Plan use the fewest angles that answer the question and one short sentence "
                       "per text field; the answer presents the plan briefly.")
RESEARCH_RUN_INCOMPLETE_INSTRUCTION = (
    "The research run was started but complete_research_run was not called, so no angle has a backend finding and "
    "nothing can be reported. Call complete_research_run with finalize false now: it lists every angle not yet "
    "recorded. Record those angles with run_research_code and call it again; use finalize true only for an angle that "
    "cannot be recorded (it becomes NOT_RUN; the recorded angles still get their findings); a group whose session "
    "ended and cannot be recovered is closed by finalize true. Never import or modify the sandbox's internal modules. "
    "Then answer from its result.")
MULTI_ANGLE_FEASIBILITY_INSTRUCTION = (
    "A multi-angle Research Plan is presented only for angles that passed check_research_feasibility in this run "
    "(FEASIBLE): {problems}. Call check_research_feasibility with one data requirement per angle of the plan you will "
    "present, then present exactly those angles; when the check cannot pass, return response_type \"LIMITATION\" "
    "saying what is missing and which alternatives exist.")
PLAN_VERSION_INSTRUCTION = {
    True: "This deployment runs research as a multi-angle Research Plan: return research_plan in its multi-angle form "
          "(plan_version, root hypothesis and angles) after check_research_feasibility, not the single-experiment form.",
    False: "This deployment does not run multi-angle Research Plans: return research_plan in its experiment form."}
# M69 tahap 1: with hypothesis plans (G3), a user's success threshold is tested by a hypothesis plan
PLAN_VERSION_SUCCESS_RULE_LINE = (" Only when the user stated a success threshold may a hypothesis plan (experiment "
                                  "form) whose experiment carries it as success_rule test it instead.")
TABULAR_OUTPUTS = ("TABLE", "PARQUET", "CSV")
CONTENTS_NOT_SHOWN_NOTE = (
    "The released outputs marked content_shown false are listed without their content (this result previews only "
    "the first tables, JSON and text, never a chart). Each has its ref and is in the data record: read a table or JSON "
    "with get_session_output by its output_id before you describe it; a chart's picture is not readable, so describe "
    "it only from the table it was drawn from.")
CARRIED_INPUTS_INSTRUCTION = (
    "carried_inputs names tables that are not released outputs of this conversation: {unknown}. Name a table by its "
    "ref in the data record ({known}), or set carried_inputs to null.")
PLAN_VERSION_NOTICE = "The Research Plan below is not in the form this deployment runs and cannot be approved. "
RESEARCH_RUN_NOT_EXECUTED_INSTRUCTION = (
    "The user approved the multi-angle Research Plan, but no research run was started in this message. Call "
    "start_research_run, run_research_code for each bundle group and complete_research_run now, or, only if the data "
    "truly cannot be obtained, return response_type \"LIMITATION\" naming the exact tool result that blocks it.")
ANGLE_FINDINGS_INSTRUCTION = (
    "research_findings does not match the multi-angle research run: {problems}. Give one entry per approved angle with "
    "the status copied unchanged from complete_research_run, all four interpretation parts and the effective sample "
    "in evidence; use no status wording stronger than the backend's, and say the angles agree only when the synthesis "
    "map allows an agreement.")
ANGLE_NARRATIVE_INSTRUCTION = (
    "Your reading of the multi-angle research run does not match its findings: {problems}. Use no status wording "
    "stronger than each angle's backend status (the backend writes the statuses and the evidence itself), say the "
    "angles agree only when the synthesis map allows an agreement, and write figures as value references.")
ANGLE_FINDINGS_NOTICE = ("The interpretation of the multi-angle research result below did not match the backend's "
                         "findings; read the figures as unconfirmed. ")
# P09 (suite20 r08, 2026-09-29): "tidak mengizinkan pernyataan bahwa sudut-sudut saling mendukung" was read as an
# agreement claim because the negation stood 47 characters before the phrase and only 40 were checked. A negation
# governs the phrase when it stands in the same clause: after the last sentence or clause boundary (., !, ?, ;, :, a
# line break or a contrast word) and within CLAUSE_WINDOW characters.
CLAUSE_BOUNDARY = re.compile(r"[.!?;:\n]|\b(?:but|however|although|whereas|tetapi|namun|tapi|sedangkan|meskipun|"
                             r"walaupun)\b", re.IGNORECASE)
CLAUSE_WINDOW = 200


# P17 (e02, 2026-09-30): "klaim bahwa … menyebabkan … tidak terbukti" denies the claim with a negation after the
# phrase. After the phrase the clause also ends at a comma, so "X menyebabkan Y, bukan Z" stays a claim.
AFTER_BOUNDARY = re.compile(r"[,.!?;:\n]|\b(?:but|however|although|whereas|tetapi|namun|tapi|sedangkan|meskipun|"
                            r"walaupun)\b", re.IGNORECASE)


def negated_in_clause(text: str, start: int, end: int | None = None) -> bool:
    """Whether a negation (NEGATION_PATTERN) governs the phrase at text[start:end]: before it in the same clause, or,
    when end is given, after it in the same clause (P17)."""
    before = text[max(0, start - CLAUSE_WINDOW):start]
    boundaries = [m.end() for m in CLAUSE_BOUNDARY.finditer(before)]
    clause = before[boundaries[-1]:] if boundaries else before
    if re.search(NEGATION_PATTERN, clause, re.IGNORECASE) is not None:
        return True
    if end is None:
        return False
    after = text[end:end + CLAUSE_WINDOW]
    stop = AFTER_BOUNDARY.search(after)
    return re.search(NEGATION_PATTERN, after[:stop.start()] if stop else after, re.IGNORECASE) is not None


# P10: a zero count governing a verdict phrase ("0 keluarga metode didukung", "nol sudut didukung", "none of the
# angles is supported"); the digit must stand alone (not 0,5 or 0%)
ZERO_QUANTIFIER = re.compile(r"(?<![\d.,])0(?![\d.,%])\s+\w|\b(?:nol|zero|none)\b", re.IGNORECASE)


def negated_or_zero(text: str, start: int, end: int | None = None) -> bool:
    """Whether a negation (before or, with end, after the phrase) or a zero count before it governs the phrase."""
    if negated_in_clause(text, start, end):
        return True
    before = text[max(0, start - CLAUSE_WINDOW):start]
    boundaries = [m.end() for m in CLAUSE_BOUNDARY.finditer(before)]
    clause = before[boundaries[-1]:] if boundaries else before
    return ZERO_QUANTIFIER.search(clause) is not None


BACKEND_FINDING_FOLLOW_UP = ("The model's interpretation of this run did not pass the backend check; rely on the status "
                             "above and read the answer text as unconfirmed.")


def backend_findings(run: dict[str, Any]) -> list[AngleFindingReport] | None:
    """One backend-authored entry per angle of a completed run (status, reason, validation level, effective sample),
    for a LIMITATION forced by the findings gate; None when the run has no findings."""
    entries = []
    for finding in (run.get("research_findings") or [])[:6]:
        status = finding.get("status")
        if not finding.get("angle_id") or status not in ("SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE",
                                                         "INVALID", "NOT_RUN"):
            continue
        sample = (finding.get("sample") or {}).get("effective")
        entries.append(AngleFindingReport(angle_id=str(finding["angle_id"])[:40], status=status,
                                          interpretation=AngleInterpretation(
            answer=f"Backend status {status}: {finding.get('status_reason') or 'no reason given'}.",
            evidence=f"Validation level {finding.get('validation_level') or 'none'}; effective sample "
                     f"{sample if sample is not None else 'not available'}; evidence direction "
                     f"{finding.get('evidence_direction') or 'NONE'}.",
            usefulness="Backend-authored summary of this angle; the interpretation was not confirmed.",
            follow_up=BACKEND_FINDING_FOLLOW_UP)))
    return entries or None


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def backend_summary(finding: dict[str, Any]) -> BackendAngleSummary:
    """The backend's finding of one angle in the response's shape (#15)."""
    sample = finding.get("sample") or {}
    estimates = finding.get("estimates") or {}
    primary = estimates.get("primary") or {}
    ci = primary.get("ci_adjusted") or primary.get("ci")
    return BackendAngleSummary(
        status=finding["status"], status_reason=finding.get("status_reason"),
        validation_level=finding.get("validation_level"), evidence_direction=finding.get("evidence_direction"),
        effective_sample=_float(sample.get("effective")), sample_unit=sample.get("unit"),
        estimate_kind=estimates.get("kind"), estimate=_float(primary.get("estimate")),
        ci=[_float(v) for v in ci][:2] if isinstance(ci, (list, tuple)) else None,
        p_value=_float(primary.get("p_value")), p_adjusted=_float(primary.get("p_adjusted")),
        confidence_level=_float(finding.get("confidence_level")),
        estimate_unit=unit if (unit := (estimates.get("units") or {}).get("estimate")) in ("FRACTION", "PERCENT")
        else None)


def evidence_sentence(summary: BackendAngleSummary) -> str:
    """The evidence part of one angle, written by the backend (Indonesian, figures formatted by value_refs)."""
    reason = REASON_LABELS.get(summary.status_reason or "", summary.status_reason)
    parts = [f"Status backend {summary.status}" + (f" ({reason})" if reason else "")]
    if summary.validation_level:
        parts.append(f"level validasi {summary.validation_level}")
    if summary.effective_sample is not None:
        unit = SAMPLE_UNITS.get(str(summary.sample_unit or "").upper(), str(summary.sample_unit or "").lower())
        parts.append(f"sampel efektif {format_value(summary.effective_sample)}" + (f" {unit}" if unit else ""))
    # P23: a difference of known unit is shown in percentage points (a fraction scaled by 100); P24: p-values with p
    fmt, unit = ("pp", summary.estimate_unit) if summary.estimate_unit else (None, None)
    if summary.estimate is not None:
        text = f"estimasi utama{f' ({summary.estimate_kind})' if summary.estimate_kind else ''} " \
               f"{format_value(summary.estimate, fmt, unit=unit)}"
        if summary.ci and len(summary.ci) == 2 and None not in summary.ci:
            level = f" {format_value(summary.confidence_level * 100)}%" if summary.confidence_level else ""
            text += (f" (CI{level} {format_value(summary.ci[0], fmt, unit=unit)} s/d "
                     f"{format_value(summary.ci[1], fmt, unit=unit)})")
        parts.append(text)
    if summary.p_value is not None:
        parts.append(format_value(summary.p_value, "p")
                     + (f" (terkoreksi: {format_value(summary.p_adjusted, 'p')})" if summary.p_adjusted is not None
                        else ""))
    if summary.evidence_direction:
        parts.append(f"arah bukti {summary.evidence_direction}")
    return "; ".join(parts) + "."


# a claim that the angles agree or confirm one another (English and Indonesian)
AGREEMENT_WORDING = (r"\b(?:(?:all|every|the) (?:\w+ )?angles? (?:\w+ )?(?:agree|confirm|support|point the same way|are "
                     r"consistent)|consistent across (?:all |the )?angles|angles? (?:agree|confirm each other)|"
                     r"(?:semua|seluruh) (?:sudut|angle)\w* (?:\w+ )?(?:mendukung|sepakat|konsisten|searah|"
                     r"mengonfirmasi|mengkonfirmasi)|konsisten di (?:semua|seluruh) (?:sudut|angle)|saling "
                     r"(?:menguatkan|mengonfirmasi|mengkonfirmasi|mendukung))\b")
VERIFIED_LEVELS = ("STATISTICS_VERIFIED", "FORMULA_AND_STATISTICS_VERIFIED")
PLAN_PROVENANCE_INSTRUCTION = (
    "These numbers in your Research Plan answer have no source: {numbers}. A plan uses no data: its numbers come "
    "from the research_plan itself, the user's message or released outputs of this run. Put them in the plan, remove "
    "them, or return response_type \"LIMITATION\"."
)
PLAN_PROVENANCE_NOTICE = "Some figures below could not be traced to the Research Plan or another source: {numbers}. "
PLAN_SUCCESS_RULE_INSTRUCTION = (
    "The success_rule value {values} is not a number the user stated. A success threshold is the user's: take it from "
    "their words, or set success_rule to null and ask them in the plan's confirmation question.")
# 10.6 (plan 2026-10-05, user decision): the user built on an earlier result ("pakai angka hasil analisa kamu barusan")
CITED_THRESHOLD_HINT = (" The user refers to an earlier result: to use one of its values, write that value in the "
                        "plan's answer as a value reference to the result (read it with get_session_output first) "
                        "and the same number in the plan.")
# M26 option B (user decision 2026-10-05): min_effect decides between SUPPORTED and PARTIALLY_SUPPORTED, so it is the
# user's number or null, like the success threshold
PLAN_MIN_EFFECT_INSTRUCTION = (
    "The min_effect value {values} is not a number the user stated. The smallest effect that matters is the user's: "
    "take it from their words, or set min_effect and min_effect_unit to null.")
# EXEC-R R1 (2026-10-06): a plan gate names the fields to change, so an edit's "set" can fix them without a rewrite
PLAN_FIELD_PATHS = " Fields: {paths}."
def _without(numbers: list[float], removed: list[float]) -> list[float]:
    """numbers without the ones equal to a removed value (also as a fraction or a percent of it)."""
    return [n for n in numbers if not any(abs(n - r) < 1e-9 or abs(n * 100 - r) < 1e-9 or abs(n / 100 - r) < 1e-9
                                          for r in removed)]


def previous_weekday(day: Any) -> str:
    """The weekday before day (ISO): the newest trading date a daily load can have delivered by then (holidays are
    not known here, so the day after one reads as one day older)."""
    from datetime import timedelta

    previous = day - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    return previous.isoformat()


# R-STORE (C2e, user decision 4): the backend's own lines about an answer's data date
DATA_DATE_CHANGED_LINE = ("Data jawaban ini sampai {new}; jawaban sebelumnya di percakapan ini memakai data sampai "
                          "{old}, jadi angkanya bisa berbeda.")
DATA_DATE_PINNED_LINE = ("Angka ini memakai data sampai {date}, sama dengan jawaban sebelumnya di percakapan ini. "
                         "Minta \"pakai data terbaru\" untuk menghitung ulang dengan data terbaru.")
# M69 tahap 1 (golden g6_revise 2026-10-02: the user's "within 10 days" became 5 days in the follow-up suggestion)
PLAN_HORIZON_INSTRUCTION = (
    "The user stated the outcome horizon ({stated}); {plan_items} use {used} periods instead. The horizon is the "
    "user's: use {allowed} periods in every experiment and angle. A different horizon is the user's decision: you may "
    "mention it as an option in the answer and use it only after the user asks for it.")
# Variants (user decision 2026-10-06, "2+5 Varian + koreksi", AI_ENABLE_ASK_BACK): every value the user named is tested
PLAN_VARIANT_COVERAGE_INSTRUCTION = (
    "The user asked for each of these values: {asked}. The plan has no experiment or angle for {missing}. Add one per "
    "missing value (the same test with that value: a variant) and keep the others, or say in the plan's answer why it "
    "cannot run.")
VARIANT_COVERAGE_LINE = "Varian yang diminta user tetapi tidak ada di rencana ini: {missing}."
VARIANT_NOTE = (
    "Application note (router), not from the user: the user asks for variants of a design value ({variants}). Answer "
    "every variant with the same method: in an analysis, release one table with a variant column (one row per variant "
    "and measure, so each figure has its address rows[variant=...]); in a plan, one experiment or angle per variant or "
    "combination. Show every variant, also those that do not pass.")
PLAN_TEXT_PROVENANCE_INSTRUCTION = (
    "These numbers in the Research Plan's own text have no source: {numbers}. A count, size or level written in the "
    "plan (how many stocks, rows or days, a threshold) must come from the user's message or this run's feasibility "
    "result; otherwise describe it without a number (for example \"every bank in the current universe\").")


def _plan_texts(value: Any, depth: int = 0) -> list[str]:
    """M29: the plan's scope text (the universe and time scope fields, wherever they appear), whose numbers are
    counts and sizes of the data and so must come from the user or the feasibility result. Method parameters in
    hypotheses (a window length, a threshold) are design values and are not checked here."""
    if depth > 8:
        return []
    if isinstance(value, dict):
        return [t for k, v in value.items() for t in ([v] if k in PLAN_SCOPE_FIELDS and isinstance(v, str)
                                                      else _plan_texts(v, depth + 1))]
    if isinstance(value, list):
        return [t for v in value for t in _plan_texts(v, depth + 1)]
    return []


PLAN_SCOPE_FIELDS = {"universe", "time_scope"}


class ResponsesTransport(Protocol):
    def create(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class GateRejection(ValueError):
    """The final answer relied on an analysis that did not pass validation (one chance to repair)."""


class RunFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def log_event(event: str, **fields: Any) -> None:
    logger.info(dumps({"event": event, **fields}))


def cited_match(value: float, cited: list[float], *, magnitude: bool) -> bool:
    """10.6 (re-test 2026-10-06): a plan value equals a cited result value as the plan writes it: rounded to the plan
    value's own decimals, in the same or the percent scale, and for a minimum effect by its size (a cited difference
    of −0,705 pp is a minimum effect of 0,705)."""
    text = f"{value:.10f}".rstrip("0")
    places = max(len(text.split(".", 1)[1]) if "." in text else 0, 1)
    for number in cited:
        for scaled in (number, number * 100, number / 100):
            candidate = abs(scaled) if magnitude else scaled
            if abs(round(candidate, places) - value) < 1e-9:
                return True
    return False


def static_prefix_hash(payload: dict[str, Any]) -> str:
    """Fingerprint of everything a model call sends except the conversation (input) and the session id (EXEC-S):
    instructions, tools, output format, and settings, serialized in the order sent. Equal fingerprints across a run's
    calls mean the reusable prefix did not change; tools withdrawn or a final JSON format change it legitimately."""
    static = {key: value for key, value in payload.items() if key not in ("input", "session_id")}
    return hashlib.sha256(json.dumps(static, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()[:16]


@dataclass
class RunState:
    request_id: str
    started: float
    input_items: list[dict[str, Any]]
    iterations: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    # Provider-side prompt caching and cost, summed over the run's model calls (see response_usage).
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_metrics_calls: int = 0
    cost: float = 0.0
    cost_calls: int = 0
    model_latency_ms: int = 0
    static_prefixes: list[str] = field(default_factory=list)
    # The instructions every model call of this run sends (system prompt, plus the catalog summary when enabled),
    # fixed at the start so the cacheable prefix cannot change inside a run.
    instructions: str = ""
    # {iteration, provider_response_id} of every model call, for the provider lookup (AI_LOG_PROVIDER)
    model_calls: list[dict[str, Any]] = field(default_factory=list)
    # catalog metadata received in this run, reusable catalog results and discovery counters (AI_ENABLE_CATALOG_PROTOCOL)
    catalog: CatalogLedger = field(default_factory=CatalogLedger)
    provider_response_id: str | None = None
    final_rejections: int = 0
    tools_offered: bool = False
    tools_locked: bool = False
    tools_withdrawn_reason: str | None = None
    structured_only: bool = False
    final_reask_sent: bool = False
    history_turns_dropped: int = 0
    # tool+arguments hash -> (consecutive executions with an unchanged result, last result hash)
    call_history: dict[str, tuple[int, str | None]] = field(default_factory=dict)
    tools_requested: list[str] = field(default_factory=list)
    # analysis_id -> latest known summary, in submission order; spec_id -> review summary
    analyses: dict[str, dict[str, Any]] = field(default_factory=dict)
    specs: dict[str, dict[str, Any]] = field(default_factory=dict)
    gate_rejections: int = 0
    validation_gate: str = "NOT_APPLICABLE"
    # Number provenance: sources collected from tool results only (never from the model).
    user_text: str = ""
    context_numbers: list[float] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)            # {kind, aggregation, value}
    analysis_values: dict[str, dict[str, Any]] = field(default_factory=dict)  # analysis_id -> {label, values}
    gate_kinds_rejected: set[str] = field(default_factory=set)
    number_provenance: dict[str, Any] | None = None
    # AI_ENABLE_METHODOLOGY: numbers in the code of successful run_python calls (parameters that actually ran; a
    # source for methodology only, never for the answer) and the methodology's own provenance result
    code_numbers: list[float] = field(default_factory=list)
    # S4 (K6): the AI's own choices typed in code, and what the user and the data supplied (their origins)
    ai_choices: list[dict[str, Any]] = field(default_factory=list)
    choice_numbers: list[float] = field(default_factory=list)
    seen_strings: set[str] = field(default_factory=set)
    seen_sets: set[frozenset[str]] = field(default_factory=set)
    web_facts: list[dict[str, Any]] = field(default_factory=list)  # S4b: find_web_fact results
    web_research: list[dict[str, Any]] = field(default_factory=list)  # item 12: research_web lookups, in brief
    # P34: web calls refused because a reference column holds the attribute ((subject, attribute) -> the database
    # reads made before the refusal), and the lookup_reference reads of this run
    reference_hints: dict[tuple[str, str], int] = field(default_factory=dict)
    reference_reads: int = 0
    # P34 (user rule: every calculation is sourced from the database; web facts only describe): the values web facts
    # returned, kept apart from the data's (an answer may cite them; code typing a web number is refused once)
    web_numbers: list[float] = field(default_factory=list)
    web_strings: set[str] = field(default_factory=set)
    web_sets: set[frozenset[str]] = field(default_factory=set)
    web_number_refused: bool = False
    user_history: str = ""
    # Research Plan feasibility and execution: the last FEASIBLE draft of this run, the checks made, whether a RESEARCH
    # data need was submitted (an attempt consumes an approval), the verified approval, and a plan left unexecuted
    feasible_draft: str | None = None
    feasibility_checks: list[dict[str, Any]] = field(default_factory=list)
    # IP1 Stage D: POINT_IN_TIME_UNAVAILABLE refusals of this run (never a silent fallback to current data)
    pit_refusals: list[str] = field(default_factory=list)
    # IP2 audit (AI_AUDIT_STORE_ENABLED): observable model and tool events, the sandbox executions of the run
    audit_trace: list[dict[str, Any]] = field(default_factory=list)
    # research findings v1: the backend's finding per hypothesis_id, from complete_analysis
    research_findings: dict[str, dict[str, Any]] = field(default_factory=dict)
    audit_started_at: datetime | None = None
    execution_ids: list[str] = field(default_factory=list)
    # R-STORE: the released outputs and executions of this run, kept at its end (output entries with session_id)
    store_outputs: list[dict[str, Any]] = field(default_factory=list)
    store_executions: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)  # D4: this run's export files (API artifacts)
    referenced: list[str] = field(default_factory=list)  # D6: value references of the final answer (DIRUJUK)
    typed_answer: str | None = None  # O4: the final answer with its value references removed (the typed figures)
    empty_turn_retries: int = 0  # M78: turns with neither text nor a tool call, retried with the same tools
    reference_date: Any = None  # the run's reference date in the analysis timezone
    data_date: Any = None  # R-STORE: the run's DataDate (the conversation's data date and whether NEWEST was asked)
    research_attempted: bool = False
    # AI_ENABLE_ANALYSIS_PATH: the data-need mode the caller fixed for this request, and the refusals it caused
    forced_path: str | None = None
    path_refusals: int = 0
    verified_plan: Any = None
    plan_unexecuted: bool = False
    methodology_provenance: dict[str, Any] | None = None
    # Repair ledger: "tool:reason_code" -> rejections seen this run (bounded retries, see _repair_budget), counted once
    # per model turn (EXEC-R R5b: repair_turns holds the turn a key was last counted in)
    repairs: dict[str, int] = field(default_factory=dict)
    repair_turns: dict[str, int] = field(default_factory=dict)
    # the kejedot index (app/friction.py), counted as the run goes; gate_repairs is filled from gate_rejections
    friction: dict[str, int] = field(default_factory=kejedot.empty)
    evidence_label: str | None = None
    # analysis_id -> the validator's evidence assessment (compact); warning codes the sandbox attached
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    warning_codes: set[str] = field(default_factory=set)
    experiments: list[dict[str, Any]] = field(default_factory=list)
    # DataNeed flow: need_id -> {mode, governance}; session_id -> {bundle_id, executions}; session_id -> completion
    needs: dict[str, dict[str, Any]] = field(default_factory=dict)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    completions: dict[str, dict[str, Any]] = field(default_factory=dict)
    final_status: dict[str, Any] | None = None
    # M25: every completion of the run, in order (final_status keeps the latest for the existing readers)
    final_statuses: list[dict[str, Any]] = field(default_factory=list)
    # H1 (M63): whether this run opened a result of an earlier turn (load_output in successful code, or
    # get_session_output of another request's released output); an INSIGHT turn must, before it completes
    opened_earlier: bool = False
    # Research Plan confirmation: what this request may do (turn), which final response types and tools it allows
    # (None: every registered tool), the guard for submit_data_need_spec, and the continuation to return.
    plan_turn: str | None = None
    allowed_types: frozenset[str] = BASE_TYPES
    tool_filter: frozenset[str] | None = None
    guard: ResearchGuard = field(default_factory=lambda: ResearchGuard(required=False))
    plan_meta: dict[str, Any] = field(default_factory=dict)
    classifier: dict[str, Any] | None = None
    # P3b (AI_ENABLE_ASK_BACK): the plan-reply reader's referent and design value changes (one reading for every path)
    reply_reading: dict[str, Any] | None = None
    guard_rejections: int = 0
    continuation: ContinuationOut | None = None
    # conversation reuse: what the resources note offered, and released outputs of earlier messages read in this run
    # (output_id -> the completion that released it)
    reuse: dict[str, Any] = field(default_factory=dict)
    inherited: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Multi-Angle Research: the run's research context (the last FEASIBLE research data plan of a plan turn, and the
    # executor of an approved plan) and the refused RESEARCH data needs
    research: ResearchContext | None = None
    research_refusals: int = 0
    # P11 value references: what this run may reference (from tool results only), the values resolved in the final
    # response (provenance sources under their labels), and the response as the model wrote it (for the audit)
    ref_sources: ReferenceSources = field(default_factory=ReferenceSources)
    ref_values: list[Resolved] = field(default_factory=list)
    ref_facts: int = 0
    ref_metrics: int = 0  # D5: metric.mN references of query_metric results
    ref_references: int = 0  # 10.5d: reference.rN references of lookup_reference results
    ref_tables: dict[str, TableRows] = field(default_factory=dict)  # M44: output_id -> rows by position
    ref_aliases: dict[str, str] = field(default_factory=dict)  # P18: output_id -> short alias (o1, o2, ...)
    # G2: released tables of an event study the sandbox recomputed and matched (CALCULATION_VERIFIED, not only
    # DATA_COVERAGE_VERIFIED)
    verified_outputs: set[str] = field(default_factory=set)
    # 2d: the output ids of the carried tables the approved plan names (None when no plan is executed)
    carried_outputs: list[str] | None = None
    # IN_SAMPLE: finding id -> the overlaps of its test data with an earlier analysis of the conversation
    in_sample: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    ref_next: int = 1  # P18: the next alias number; seeded from the data record, so numbering is conversation-wide
    # M47: the conversation's data record, seeded from earlier steps and turns and extended by this run
    data_record: dict[str, Any] = field(default_factory=records.empty)
    references_used: int = 0
    # M43 (2026-09-30): the final answer kept references to missing fields as [field] (validation_gate ANNOTATED)
    reference_annotated: bool = False
    # P17 (2026-10-01): the claims marked in the final answer (italics); returned as the response's annotations
    claim_annotations: list[dict[str, Any]] = field(default_factory=list)
    # H1: a consistency claim the definitions did not support stayed, with a limitation stating the difference
    definition_annotated: bool = False
    raw_final: dict[str, Any] | None = None
    # the model's latest final output as it arrived (for the final.rejected / final.forced audit events)
    current_raw: str = ""
    # S4c: reasoning items were sent back in this run; replay_off once a provider refused them
    reasoning_replayed: bool = False
    replay_off: bool = False
    # G23 D (K3): the last final draft that parsed, and the limit that ended the run (MAX_ITERATIONS, ANALYSIS_TIMEOUT)
    last_draft: FinalResponse | None = None
    exhausted: str | None = None
    # M45 (AI_ENABLE_EDIT_REPAIR): the refused draft an edit object of the next reply applies to; set only when the
    # refusal offered the edit
    repair_base: dict[str, Any] | None = None
    # EXEC-R R4b: a failed edit gets one more edit against the same draft (edit_retry_base), once per draft
    edit_retry_base: dict[str, Any] | None = None
    edit_retry_used: bool = False


class FinalJsonError(ValueError):
    """EXEC-R R4a: the final response is not JSON even for the lenient decoder; the message names where."""


class TurnRuleError(ValueError):
    """The final response type is not allowed in this turn (for example a plan while it is cancelled)."""


class AgentOrchestrator:
    """Stateless bounded agent loop: model -> optional registered tools -> strict final answer."""

    def __init__(
        self,
        settings: Settings,
        client: ResponsesTransport,
        registry: ToolRegistry,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        auditor: Any | None = None,
        catalog_summary: Any | None = None,
        provider_logger: Any | None = None,
        provider_policy: Any | None = None,
        session_closer: Callable[[str, list[str]], dict[str, str]] | None = None,
        session_releaser: Callable[[str], list[dict[str, Any]]] | None = None,
        result_store: Any = None,
        output_fetcher: Callable[[str, str, str], bytes] | None = None,
        carried_uploader: Callable[[str, str, dict[str, Any], bytes], dict[str, Any]] | None = None,
        conversation_resources: Callable[[str], dict[str, Any] | None] | None = None,
        draft_reader: Callable[[str], dict[str, Any] | None] | None = None,
        derived_frequency: bool = False,
        audit_outbox: Any | None = None,
        row_reader: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.settings = settings
        # M44: reads rows of a released output the run has not read, when an answer references them
        # (session_id, output_id, request_id, offset, limit) -> the sandbox's output body
        self.row_reader = row_reader
        # IP2: weekly/monthly derived from daily rows (AI_ENABLE_DERIVED_FREQUENCY and the sandbox capability, checked
        # at startup) and the audit outbox writer (AI_AUDIT_STORE_ENABLED)
        self.derived_frequency = derived_frequency and settings.ai_enable_dataneed
        self.audit_outbox = audit_outbox
        # Research Plan feasibility (AI_ENABLE_PLAN_FEASIBILITY): reads a feasibility draft back from the sandbox; set
        # only when the sandbox reports the capability
        self.draft_reader = draft_reader
        # conversation reuse (S1/S2): reads what earlier messages of a SERVER conversation left in the sandbox; set
        # only when the sandbox reports the capability
        self.conversation_resources = conversation_resources
        # closes the analysis sessions a run leaves open (S05): (request_id, session_ids) -> {session_id: reason}
        self.session_closer = session_closer
        self.session_releaser = session_releaser
        # R-STORE (round 2026-10-03 C2): the conversation's durable results, with the sandbox calls that copy a released
        # output out (session_id, output_id, request_id) and put a stored table back (session_id, request_id, meta,
        # data); all three or none
        self.result_store = result_store if output_fetcher is not None and carried_uploader is not None else None
        self.output_fetcher = output_fetcher
        self.carried_uploader = carried_uploader
        self.client = client
        self.registry = registry
        self.auditor = auditor
        # CatalogSummary (AI_CATALOG_SUMMARY_IN_PROMPT) and ProviderLogger (AI_LOG_PROVIDER), when enabled
        self.catalog_summary = catalog_summary
        self.provider_logger = provider_logger
        # CachePricePolicy (AI_PROVIDER_MAX_CACHE_PRICE_RATIO): providers skipped for a poor cache-read discount
        self.provider_policy = provider_policy
        self.wall_clock = wall_clock
        self.clock = clock
        self.dataneed = settings.ai_enable_dataneed
        # Research Plan confirmation guards the DataNeed flow only; the Analysis Spec path (the DataNeed rollback)
        # has no plan step, so the flag has no effect there.
        self.plan_confirmation = settings.ai_require_research_plan_confirmation and self.dataneed
        if settings.ai_require_research_plan_confirmation and not self.dataneed:
            log_event("research_plan_confirmation_inactive", reason="AI_ENABLE_DATANEED is off")
        self.signer = PlanSigner(settings.ai_research_plan_signing_key or "", settings.ai_research_plan_ttl_seconds,
                                 wall_clock) if self.plan_confirmation else None
        period_return = settings.ai_enable_standard_period_return and self.dataneed
        # The protocol guards submit_data_need_spec, so it exists only in the DataNeed flow.
        self.catalog_protocol = settings.ai_enable_catalog_protocol and self.dataneed
        if settings.ai_enable_catalog_protocol and not self.dataneed:
            log_event("catalog_protocol_inactive", reason="AI_ENABLE_DATANEED is off")
        self.conversation_reuse = settings.ai_enable_conversation_reuse and self.dataneed \
            and conversation_resources is not None
        if settings.ai_enable_conversation_reuse and not self.conversation_reuse:
            log_event("conversation_reuse_inactive", reason="AI_ENABLE_DATANEED is off or the sandbox does not "
                                                            "report conversation_reuse")
        names = set(registry.names())
        self.plan_feasibility = self.plan_confirmation and draft_reader is not None \
            and bool({"check_data_feasibility", "check_research_feasibility"} & names)
        if settings.ai_enable_plan_feasibility and not self.plan_feasibility:
            log_event("plan_feasibility_inactive", reason="Research Plan confirmation, the DataNeed flow or the "
                                                          "sandbox capability is missing")
        # Multi-Angle Research: active when the registry negotiated it with the sandbox at startup (it registers
        # check_research_feasibility in place of check_data_feasibility and the research run tools)
        multi_angle = getattr(registry, "multi_angle", None)
        self.multi_angle = settings.ai_enable_multi_angle_research and self.plan_feasibility \
            and isinstance(multi_angle, dict) and callable(multi_angle.get("factory")) \
            and {"check_research_feasibility", *RESEARCH_RUN_TOOLS} <= names
        if settings.ai_enable_multi_angle_research and not self.multi_angle:
            log_event("multi_angle_research_inactive", reason="Research Plan feasibility, DataNeedSpec v2 or the "
                                                              "sandbox capability is missing")
        self.research_limits = multi_angle if self.multi_angle else {}
        self.signer_v2 = PlanSignerV2(settings.ai_research_plan_signing_key or "", settings.ai_research_plan_ttl_seconds,
                                      wall_clock) if self.multi_angle else None
        plan_check = "check_research_feasibility" if self.multi_angle else "check_data_feasibility"
        self.plan_tools = DISCOVERY_TOOLS | ({plan_check} if self.plan_feasibility else set())
        # the methodology note is checked against released outputs, which exist only in the DataNeed flow
        self.methodology = settings.ai_enable_methodology and self.dataneed
        if settings.ai_enable_methodology and not self.dataneed:
            log_event("methodology_inactive", reason="AI_ENABLE_DATANEED is off")
        # IP1 Stage D: active when the registered submit_data_need_spec carries time_basis (AI_ENABLE_POINT_IN_TIME
        # and the sandbox capability, checked at startup)
        submit = registry.get("submit_data_need_spec") if self.dataneed else None
        self.point_in_time = submit is not None and "time_basis" in submit.arguments_model.model_fields
        # research findings v1: active when the registered submit_data_need_spec declares the findings values
        # (AI_ENABLE_RESEARCH_FINDINGS and the sandbox capability, checked at startup) and plans are confirmed
        findings_v1 = submit is not None and self.plan_confirmation \
            and submit.arguments_model.__name__.endswith("Findings")
        # G3 (user decision 2026-10-02): the hypothesis plan (v1 with findings v1) beside the multi-angle plan; it
        # needs the findings capability and check_data_feasibility registered next to check_research_feasibility
        self.hypothesis_plans = settings.ai_enable_hypothesis_plan and self.multi_angle and findings_v1 \
            and "check_data_feasibility" in names
        if settings.ai_enable_hypothesis_plan and not self.hypothesis_plans:
            log_event("hypothesis_plan_inactive", reason="needs Multi-Angle Research, research findings v1 and "
                                                         "check_data_feasibility")
        if self.hypothesis_plans:
            self.plan_tools = self.plan_tools | {"check_data_feasibility"}
        self.research_findings = findings_v1 and (not self.multi_angle or self.hypothesis_plans)
        # caller-chosen path: a request may fix ANALYSIS or RESEARCH (both need the DataNeed flow and plan confirmation)
        self.analysis_path = settings.ai_enable_analysis_path and submit is not None and self.plan_confirmation
        if settings.ai_enable_analysis_path and not self.analysis_path:
            log_event("analysis_path_inactive", reason="needs AI_ENABLE_DATANEED and "
                                                       "AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION")
        # P11 (2026-09-30): data figures as value references the backend fills in (DataNeed flow only)
        self.value_references = settings.ai_enable_value_references and self.dataneed
        # 10.1-10.4 (plan 2026-10-05 item 10): the address menu on tool results and the reference fallback
        self.address_menu = bool(getattr(settings, "ai_enable_address_menu", False)) and self.value_references
        # EXEC-3: the routers may ask back, return the understood intent and every design value (variants); the
        # plan-reply reader returns the same reading (P3b); a failed router call is retried once
        self.ask_back = bool(getattr(settings, "ai_enable_ask_back", False))
        self.system_prompt = build_system_prompt(settings.ai_enable_lookup_fact, self.dataneed,
                                                 self.plan_confirmation, period_return,
                                                 settings.ai_final_contract_in_prompt, self.catalog_protocol,
                                                 self.conversation_reuse, self.methodology, self.plan_feasibility,
                                                 self.point_in_time, self.derived_frequency,
                                                 self.research_findings, self.multi_angle,
                                                 (int(self.research_limits.get("min_angles", 2)),
                                                  int(self.research_limits.get("max_angles", 6)),
                                                  int(self.research_limits.get("min_families") or 0)),
                                                 self.value_references, self.hypothesis_plans,
                                                 frozenset(registry.names()),
                                                 bool(getattr(settings, "ai_enable_tool_envelope", False)))
        self.final_schema = final_response_schema(self.plan_confirmation, self.methodology, self.research_findings,
                                                  self.multi_angle, self.value_references, self.hypothesis_plans)
        contract = response_contract(self.plan_confirmation, self.methodology, self.research_findings,
                                     self.multi_angle, self.value_references, self.hypothesis_plans)
        self.response_contract = contract
        self.finalize_instruction = FINALIZE_PREFIX + contract
        self.context_budget_instruction = CONTEXT_BUDGET_PREFIX + contract

    def close(self) -> None:
        if self.provider_logger is not None:
            self.provider_logger.close()

    def _instructions(self) -> str:
        """The system prompt, followed by the catalog summary when one is available. The summary is documentation for
        planning only; its numbers (dates, counts) are not answer sources, so _source_index reads the system prompt
        alone."""
        summary = ""
        if self.catalog_summary is not None:
            try:
                summary = self.catalog_summary.text()
            except Exception:  # noqa: BLE001 - without a summary the model uses the discovery tools
                summary = ""
        return self.system_prompt + ("\n\n" + summary if summary else "")

    def _provider(self) -> dict[str, Any]:
        """OpenRouter provider preferences. provider.sort (AI_PROVIDER_SORT) turns load balancing off and tries the
        endpoints in that order; without it OpenRouter balances load weighted to the lowest price. provider.ignore
        (AI_PROVIDER_MAX_CACHE_PRICE_RATIO) drops the providers whose cache reads are barely discounted.
        provider.preferred_min_throughput (AI_PROVIDER_MIN_THROUGHPUT) moves endpoints slower than that median speed to
        the end of the list; it never excludes one, so a request still runs when none is fast enough."""
        provider: dict[str, Any] = {"require_parameters": True, "allow_fallbacks": True}
        if self.settings.ai_provider_sort:
            provider["sort"] = self.settings.ai_provider_sort
        if self.settings.ai_provider_min_throughput is not None:
            provider["preferred_min_throughput"] = {"p50": self.settings.ai_provider_min_throughput}
        if self.provider_policy is not None:
            ignored = self.provider_policy.ignored()
            if ignored:
                provider["ignore"] = ignored
        return provider

    def run(self, request: AgentRunRequest, conversation_key: str | None = None,
            data_record: dict[str, Any] | None = None) -> AgentRunResponse:
        """One request. conversation_key (history_mode SERVER with conversation reuse only) is derived by the
        application from the conversation and its owner; it scopes what earlier messages left in the sandbox.
        data_record (M47) is the conversation's data record so far (earlier mode 4 steps and stored turns)."""
        moment = self.wall_clock()
        input_items, dropped = self._build_input(request, moment)
        state = RunState(
            request_id=request.request_id,
            started=self.clock(),
            input_items=input_items,
            history_turns_dropped=dropped,
            user_text=self._routing_text(request),
            instructions=self._instructions(),
            user_history="\n".join(turn.content for turn in request.history if turn.role == "user"),
        )
        state.audit_started_at = moment
        self._seed_data_record(state, data_record)
        # AUTO and MODE4 are routed before this (app/modes.py, app/mode4.py); only ANALYSIS and RESEARCH fix a path
        state.forced_path = request.analysis_path if self.analysis_path \
            and request.analysis_path in ("ANALYSIS", "RESEARCH") else None
        state.research = ResearchContext() if self.multi_angle else None
        if state.research is not None:
            state.research.calls_left = lambda: self.settings.ai_max_tool_calls - state.tool_calls
        for text in [turn.content for turn in request.history if turn.role == "user"] + [request.message]:
            state.context_numbers.extend(value for shown in parse_numbers(text) for value, _ in shown.candidates)
        token = current_request_id.set(request.request_id)
        conversation_token = current_conversation_id.set(current_conversation_id.get() or request.conversation_id)
        references_token = current_reference_sources.set(state.ref_sources)
        # item 12: a mode 4 step keeps its run's turn id (the web budget key); a web lookup waits at most until the
        # run's deadline
        turn_token = current_turn_id.set(current_turn_id.get() or request.request_id)
        budget_left = current_time_budget.get()
        deadline_token = current_run_deadline.set(time.monotonic() + (
            self.settings.ai_max_analysis_seconds if budget_left is None
            else min(budget_left, self.settings.ai_max_analysis_seconds)))
        context = current_run_context.set(run_context(
            moment, self.settings.analysis_timezone,
            [(turn.role, turn.content) for turn in request.history], request.message))
        guard = current_research_guard.set(state.guard)
        key = current_conversation_key.set(conversation_key if self.conversation_reuse else None)
        research = current_research_context.set(state.research)
        restorer = current_carried_restorer.set(self._restorer(request))
        # R-STORE (C2e, user decision 4): a conversation keeps its data date unless this run asks for newer data
        state.data_date = DataDate(records.data_as_of(state.data_record)) if self.result_store is not None else None
        state.reference_date = moment.astimezone(ZoneInfo(self.settings.analysis_timezone)).date()
        data_date = current_data_date.set(state.data_date)
        # D2: what get_session_output (and the phase D tools) may open of this conversation's kept results
        fetch = self.output_fetcher
        results = current_results.set(RunResults(
            conversation_id=request.conversation_id if self.result_store is not None else None,
            request_id=request.request_id, store=self.result_store, record=state.data_record,
            fetch=(lambda sid, oid: fetch(sid, oid, request.request_id)) if fetch is not None else None,
            pending=state.store_executions))
        carried, reading = None, None
        try:
            if self.conversation_reuse and conversation_key and request.history:
                self._add_conversation_resources(state, conversation_key)
            self._prepare_plan_turn(request, state)
            if state.reply_reading is not None and current_design_changes.get() is None:
                # P3b: outside a pipeline the plan-reply reader's reading binds this run's plan gates (M90)
                reading = (current_design_changes.set(state.reply_reading["design_value_changes"]),
                           current_turn_referent.set(state.reply_reading["referent"]))
            self._apply_turn_kind(state)
            carried = current_carried_outputs.set(state.carried_outputs)
            current_research_guard.set(state.guard)
            final = self._loop(state)
            final = self._with_ai_choices(state, final)
            final = self._conversation_correction(state, final)
            state.experiments = self._research_summary(state, final.answer)
            if state.forced_path == "ANALYSIS" and final.response_type == "ANSWER" and state.final_status \
                    and ANALYSIS_PATH_LINE not in final.limitations:
                final = final.model_copy(update={"limitations": [*final.limitations, ANALYSIS_PATH_LINE]})
            if final.response_type == "RESEARCH_PLAN_CONFIRMATION" and isinstance(final.research_plan, ResearchPlanV2) \
                    and self.signer_v2 is not None and state.research is not None \
                    and state.research.feasible is not None:
                # rpc2 binds the plan and the research data plan the backend built before the plan was shown
                data_plan = state.research.feasible
                state.continuation = self.signer_v2.issue(final.research_plan, data_plan, request.request_id,
                                                          request.conversation_id)
                state.plan_meta.update(issued_plan_id=state.continuation.plan_id, plan_version=PLAN_VERSION_V2,
                                       research_data_plan_sha256=data_plan.get("research_data_plan_sha256"))
                log_event("research_plan_issued", request_id=request.request_id, plan_version=PLAN_VERSION_V2,
                          plan_id=state.continuation.plan_id, angles=len(final.research_plan.angles),
                          bundle_groups=len(data_plan.get("bundle_groups") or []),
                          strategy=data_plan.get("strategy"), expires_at=state.continuation.expires_at)
            elif final.response_type == "RESEARCH_PLAN_CONFIRMATION" and self.signer is not None \
                    and final.research_plan is not None and not isinstance(final.research_plan, ResearchPlanV2):
                # The plan id, token and expiry come from the backend only; the model never produces them.
                state.continuation = self.signer.issue(final.research_plan, request.request_id,
                                                       request.conversation_id, state.feasible_draft)
                state.plan_meta["issued_plan_id"] = state.continuation.plan_id
                log_event("research_plan_issued", request_id=request.request_id,
                          plan_id=state.continuation.plan_id, experiments=len(final.research_plan.experiments),
                          expires_at=state.continuation.expires_at, draft_id=state.feasible_draft)
            elif state.plan_unexecuted and state.verified_plan is not None:
                # M19: an approval is consumed by an attempt, not by a turn; the same continuation goes back unchanged
                state.continuation = self._same_continuation(state.verified_plan)
            if final.response_type == "RESEARCH_PLAN_CONFIRMATION" and state.continuation is not None:
                # M64: when the suggestion was issued, so a later turn knows which results are newer than it
                records.mark_suggestion(state.data_record, state.continuation.plan_id, request.request_id)
            result = AgentRunResponse(
                request_id=request.request_id,
                status=STATUS_BY_RESPONSE_TYPE[final.response_type],
                response=final,
                execution=self._execution(state),
                evidence_label=state.evidence_label,
                continuation=state.continuation,
                annotations=[ClaimAnnotation(**a) for a in state.claim_annotations] or None,
                artifacts=state.artifacts or None,
                evidence=self._evidence(state),
            )
            if state.exhausted is not None:
                # G23 D: the answer is delivered, and the limit that ended the run stays visible for statistics
                result = result.model_copy(update={"error": RunError(
                    code=state.exhausted, message=f"{state.exhausted}: the last draft was delivered as a limitation")})
        except (RunFailure, ProviderError) as exc:
            result = self._failed(state, exc.code, str(exc))
        except Exception as exc:
            result = self._failed(
                state, "INTERNAL_ERROR", f"Unexpected orchestrator error ({type(exc).__name__})."
            )
        finally:
            if carried is not None:
                current_carried_outputs.reset(carried)
            if reading is not None:
                current_design_changes.reset(reading[0])
                current_turn_referent.reset(reading[1])
            current_request_id.reset(token)
            current_conversation_id.reset(conversation_token)
            current_reference_sources.reset(references_token)
            current_turn_id.reset(turn_token)
            current_run_deadline.reset(deadline_token)
            current_run_context.reset(context)
            current_research_guard.reset(guard)
            current_research_context.reset(research)
            current_carried_restorer.reset(restorer)
            current_data_date.reset(data_date)
            current_results.reset(results)
        self._store_results(state, request.conversation_id)
        result = self._data_date_lines(state, request, result)
        result = result.model_copy(update={"data_record": records.public(state.data_record)})
        # the closes still carry the conversation key, so an attached session that ran nothing is detached, not lost
        self._end_sessions(state)
        current_conversation_key.reset(key)
        if self.auditor is not None:
            try:
                self.auditor.record(request.request_id, request.message, result, state.experiments,
                                    used_sandbox=bool(state.specs or state.analyses or state.needs or state.sessions
                                                      or self._executor(state) is not None))
            except Exception:  # noqa: BLE001 - auditing never changes the response
                logger.warning(dumps({"event": "research_audit_failed", "request_id": request.request_id}))
        if self.audit_outbox is not None:
            if state.raw_final is not None:
                state.audit_trace.append(unrendered_event(state.raw_final, self.wall_clock()))
            if not records.is_empty(state.data_record):  # M47: the data record after this run, for the audit
                state.audit_trace.append({"type": "data.record", "occurred_at": self.wall_clock().isoformat(),
                                          "record": state.data_record})
            result = self._hand_to_audit(request, result, state)
        log_event(
            "ai_run_completed" if result.status != "FAILED" else "ai_run_failed",
            request_id=state.request_id,
            provider="openrouter",
            model=self.settings.ai_model,
            status=result.status,
            error_code=result.error.code if result.error else None,
            iterations=state.iterations,
            tool_calls=state.tool_calls,
            tools_requested=state.tools_requested,
            tools_withdrawn_reason=state.tools_withdrawn_reason,
            history_turns_dropped=state.history_turns_dropped,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            reasoning_tokens=state.reasoning_tokens,
            total_tokens=state.total_tokens,
            duration_ms=result.execution.duration_ms,
            repair_ledger=state.repairs or None,
            friction=self._friction(state),
        )
        log_event("ai_model_usage_summary", **self._usage_summary(state))
        if state.reuse or state.inherited:
            log_event("conversation_reuse_summary", request_id=state.request_id, **state.reuse,
                      released_outputs_read=sorted(state.inherited))
        if self.catalog_protocol:
            ledger = state.catalog
            log_event("ai_catalog_usage", request_id=state.request_id, calls=ledger.calls,
                      cache_hits=ledger.cache_hits, catalog_queries=sum(ledger.calls.values()) - ledger.cache_hits,
                      refusals=ledger.refusals, tables_read=sorted(t for t, v in ledger.tables.items() if v.contract))
        if self.provider_logger is not None:
            try:
                self.provider_logger.submit(state.request_id, state.model_calls)
            except Exception:  # noqa: BLE001 - logging never changes the response
                logger.warning(dumps({"event": "ai_model_call_provider_failed", "request_id": state.request_id}))
        return result

    def _conversation_correction(self, state: RunState, final: FinalResponse) -> FinalResponse:
        """Variants and turns (2026-10-06, AI_ENABLE_ASK_BACK): when this run recorded a test, every test of the
        conversation's ledger is corrected together (variant_correction) and the answer lists all of them."""
        if not self.ask_back or not any(entry.get("request_id") == state.request_id
                                        and entry.get("kind") in ("HYPOTHESIS", "ANGLE")
                                        for entry in state.data_record.get("findings") or []):
            return final
        correction = variant_correction.correct(state.data_record)
        if correction is None:
            return final
        log_event("conversation_correction", request_id=state.request_id, policy=correction["policy"],
                  family_size=correction["family_size"],
                  below_alpha=sum(1 for t in correction["tests"] if t["below_alpha"]))
        line = variant_correction.line(correction)
        return final.model_copy(update={"limitations": [*[x for x in final.limitations
                                                          if not x.startswith("Koreksi uji berganda")], line]})

    def _seed_data_record(self, state: RunState, data_record: dict[str, Any] | None) -> None:
        """M47: start from the conversation's data record; its tables and columns count as read in this run, and the
        model gets it as one bounded note (whatever the history holds)."""
        state.data_record = records.copy_of(data_record)
        # P18: the aliases of earlier steps and turns keep their numbers; new outputs continue after them
        state.ref_aliases, state.ref_next = records.aliases(state.data_record)
        self._seed_findings(state)
        self._offer_methods(state)
        self._offer_metrics(state)
        if not records.has_data(state.data_record):
            return
        records.seed_ledger(state.data_record, state.catalog)
        note = records.note(state.data_record)
        state.input_items.insert(len(state.input_items) - 1, {"role": "user", "content": note})
        log_event("data_record_offered", request_id=state.request_id, tables=len(state.data_record["tables"]),
                  needs=len(state.data_record["needs"]), outputs=len(state.data_record["outputs"]),
                  note_chars=len(note))

    def _seed_findings(self, state: RunState) -> None:
        """E1: the research findings of earlier turns and steps are sources again (finding.<id> and their figures), so
        a follow-up explains them without running the research again. An event study is cited from its tables."""
        for entry in state.data_record.get("findings") or []:
            finding = entry.get("finding") or {}
            if entry.get("kind") not in ("ANGLE", "HYPOTHESIS") or not finding:
                continue
            values = self._finding_numbers(finding) if entry["kind"] == "ANGLE" else numbers_in(finding)
            if entry["kind"] == "HYPOTHESIS":
                values += [abs(v) for v in values if v < 0]
            state.analysis_values[f"recorded_finding:{entry['id']}"] = {"label": "DATA_COVERAGE_VERIFIED",
                                                                        "values": values}
            if self.value_references:
                state.ref_sources.add("finding", str(entry["id"]), finding, "DATA_COVERAGE_VERIFIED")

    def _offer_metrics(self, state: RunState) -> None:
        """D5: the official metrics query_metric answers (from AI_metric_catalog at startup), as an application note,
        so the tool's own definition stays the same when a metric is added."""
        menu = getattr(self.registry, "metric_menu", None)
        if menu and "query_metric" in self.registry.names():
            state.input_items.insert(len(state.input_items) - 1, {"role": "user", "content": menu})

    def _offer_methods(self, state: RunState) -> None:
        """4b: the menu of analysis methods, then the manuals opened earlier in the conversation (current version), as
        application notes; carried from step to step of mode 4 and from turn to turn by the data record."""
        guides = getattr(self.registry, "method_guides", None)
        if not guides:
            return
        menu = METHOD_MENU_HEADER + "\n" + "\n".join(
            "- " + dumps({k: entry[k] for k in ("name", "g", "title", "use_when", "avoid_when", "verification")})
            for entry in guides["menu"])
        state.input_items.insert(len(state.input_items) - 1, {"role": "user", "content": menu})
        current = {name: {"sha256": method_guides.guide_sha256(method_guides.by_name()[name]),
                          "version": method_guides.GUIDES_VERSION, "guide": method_guides.by_name()[name]}
                   for name in guides["names"]}
        note, refreshed = records.manuals_note(state.data_record, current)
        if note:
            state.input_items.insert(len(state.input_items) - 1, {"role": "user", "content": note})
        log_event("method_guides_offered", request_id=state.request_id, menu=len(guides["menu"]),
                  manuals=len(state.data_record.get("manuals") or []), refreshed=refreshed,
                  manual_chars=len(note or ""))

    def _add_conversation_resources(self, state: RunState, conversation_key: str) -> None:
        """Conversation reuse: a bounded application note listing what earlier messages of the conversation left in
        the sandbox (released outputs, bundles with the data_need_spec to resubmit, warm sessions). Its numbers are
        not answer sources; the sandbox checks every later use."""
        try:
            resources = self.conversation_resources(conversation_key) if self.conversation_resources else None
        except Exception:  # noqa: BLE001 - without the note the run works as a fresh one
            resources = None
        if not resources or not (resources.get("released_outputs") or resources.get("bundles")):
            log_event("conversation_resources", request_id=state.request_id, outputs=0, bundles=0)
            return
        note = conversation_resources_note(resources)
        state.input_items.insert(len(state.input_items) - 1, {"role": "user", "content": note})
        state.reuse = {"offered_outputs": len(resources.get("released_outputs") or []),
                       "offered_bundles": len(resources.get("bundles") or []),
                       "warm_sessions": resources.get("warm_sessions") or 0}
        log_event("conversation_resources", request_id=state.request_id, outputs=state.reuse["offered_outputs"],
                  bundles=state.reuse["offered_bundles"], warm_sessions=state.reuse["warm_sessions"],
                  note_chars=len(note))

    def _path_mismatch(self, state: RunState, call_id: str, name: str, raw_arguments: Any) -> ToolOutcome | None:
        """AI_ENABLE_ANALYSIS_PATH: a data need in the other mode than the caller fixed is refused before it reaches
        the sandbox (bounded like other repairs)."""
        arguments = self._tool_arguments(name, raw_arguments)
        mode = arguments.get("mode") if isinstance(arguments, dict) else None
        if mode is None or mode == state.forced_path:
            return None
        state.path_refusals += 1
        log_event("analysis_path_mismatch", request_id=state.request_id, requested=state.forced_path, mode=mode)
        return error_outcome(
            call_id, name, "PATH_MISMATCH",
            f"The caller fixed this request to the {state.forced_path} path; submit the data need with mode "
            f"{state.forced_path}." + (" Answer it as a descriptive analysis; no Research Plan is used."
                                       if state.forced_path == "ANALYSIS" else ""))

    def _insight_source_unopened(self, state: RunState, call_id: str, name: str) -> ToolOutcome | None:
        """H1 (M63, golden test 2026-10-02): an explanation of an earlier result starts from that result. An INSIGHT
        turn that never opened a released table of an earlier turn (load_output in its code, or get_session_output)
        is refused before it completes, with the tables it can open; a turn without earlier results is not."""
        if state.plan_meta.get("turn_kind") != "INSIGHT" or state.opened_earlier:
            return None
        earlier = [o for o in (state.data_record or {}).get("outputs") or []
                   if o.get("request_id") != state.request_id and o.get("type") in (None, "TABLE", "JSON")]
        if not earlier:
            return None
        listed = [f"{o.get('ref')} {o.get('output_id')} \"{o.get('name')}\"" for o in earlier[-8:]]
        log_event("insight_source_not_opened", request_id=state.request_id, earlier=len(earlier))
        return error_outcome(
            call_id, name, "INSIGHT_SOURCE_NOT_OPENED",
            "This turn explains an earlier result, so it starts from that result's own table: load it in the session "
            "with load_output('<output_id>') (or read it with get_session_output) and use its definition from the "
            "data record; do not rebuild it with a guessed definition. When you need other data, state how its "
            f"definition differs. Earlier results: {'; '.join(listed)}.")

    def _one_open_session(self, state: RunState, call_id: str, name: str) -> ToolOutcome | None:
        """One open analysis session per run (S08): the sandbox has few session slots for every run together, and a run
        that opened a second session before completing its first held two of them. Before another open, an earlier
        session of this run that has not completed is closed when no execution in it succeeded or its complete_analysis
        answered INCOMPLETE (it released nothing); one with successful executions and no complete_analysis refuses the
        new open until complete_analysis has been called on it."""
        pending = [session_id for session_id, session in state.sessions.items()
                   if SESSION_ID_RE.fullmatch(session_id) and not session.get("superseded")
                   and (state.completions.get(session_id) or {}).get("status") != "COMPLETED"]
        # a session whose complete_analysis already answered INCOMPLETE released nothing and may be replaced
        working = [session_id for session_id in pending if session_id not in state.completions
                   and "OK" in state.sessions[session_id].get("executions", [])]
        if working:
            outcome = error_outcome(
                call_id, name, "ANALYSIS_SESSION_ALREADY_OPEN",
                f"Analysis session {working[0]} of this request is still open and has results. Call complete_analysis "
                "on it before opening another session, or keep working in it: one session may run any number of "
                "run_python calls on its bundle.")
            outcome.output["error"]["open_session_id"] = working[0]
            return outcome
        if pending:
            closed: dict[str, str] = {}
            if self.session_closer is not None:
                try:
                    closed = self.session_closer(state.request_id, pending)
                except Exception:  # noqa: BLE001 - best effort; the sandbox's idle timeout remains
                    closed = {session_id: "CLOSE_FAILED" for session_id in pending}
            for session_id in pending:
                state.sessions[session_id]["superseded"] = closed.get(session_id, "NOT_CLOSED")
            log_event("analysis_sessions_superseded", request_id=state.request_id, sessions=closed or pending)
        return None

    def _hand_to_audit(self, request: AgentRunRequest, result: AgentRunResponse,
                       state: RunState) -> AgentRunResponse:
        """IP2: one RUN_FINISHED row in ai_audit.ingest_outbox. Optional mode (AI_AUDIT_STORE_REQUIRED false): a
        failure is logged and the response is unchanged. Required mode: the answer is withheld when the run cannot be
        handed over, so no answer leaves without its audit record."""
        try:
            payload = build_payload(
                request=request, result=result, trace=state.audit_trace,
                started_at=state.audit_started_at or self.wall_clock(), finished_at=self.wall_clock(),
                model=self.settings.ai_model, execution_ids=state.execution_ids,
                completion_ids=[cid for c in state.completions.values() for cid in c.get("completion_ids") or []
                                if str(cid).startswith("cmp_")],
                sessions=[s for s in state.sessions if SESSION_ID_RE.fullmatch(s)],
                bundles=[str(s.get("bundle_id")) for s in state.sessions.values() if s.get("bundle_id")])
            self.audit_outbox.write(payload)
            log_event("audit_outbox_written", request_id=state.request_id, events=len(payload["events"]),
                      executions=len(payload["expected"]["execution_ids"]))
            return result
        except Exception as exc:  # noqa: BLE001 - observable, never silent
            log_event("audit_outbox_failed", request_id=state.request_id, error=type(exc).__name__,
                      required=self.settings.ai_audit_store_required)
            if not self.settings.ai_audit_store_required:
                return result
            return self._failed(state, "AUDIT_UNAVAILABLE", "The run could not be recorded for audit, which this "
                                                            "deployment requires, so its answer is withheld.")

    @staticmethod
    def _track_artifacts(state: RunState, name: str, outcome: ToolOutcome) -> None:
        """D4: the downloads the API response lists (artifacts); the model saw only the id, name and size."""
        result = outcome.output.get("result") if outcome.ok else None
        if name == "export_result" and isinstance(result, dict) and result.get("status") == "EXPORTED":
            state.artifacts.append({k: result.get(k) for k in ("export_id", "file_name", "format", "size_bytes",
                                                               "sha256")} | {"download_path": result.get("download")})

    def _track_results(self, state: RunState, name: str, outcome: ToolOutcome, arguments: Any) -> None:
        """R-STORE: what this run releases and the code it runs, kept with the conversation at the run's end."""
        result = outcome.output.get("result") if outcome.ok else None
        if not isinstance(result, dict):
            return
        if name in ("run_python", "run_research_code") and result.get("execution_id"):
            code = arguments.get("code") if isinstance(arguments, dict) else None
            if isinstance(code, str):
                state.store_executions.append({"execution_id": str(result["execution_id"]),
                                               "session_id": result.get("session_id"), "code": code,
                                               "status": result.get("status"), "modules": result.get("modules"),
                                               "access": result.get("access")})
        elif (name == "complete_analysis" and result.get("status") == "COMPLETED") or name == "complete_research_run":
            verified = {str(i) for i in (result.get("final_status") or {}).get("verified_output_ids") or []}
            for entry in result.get("released_outputs") or []:
                owner = entry.get("session_id") or result.get("session_id") if isinstance(entry, dict) else None
                if owner and entry.get("output_id"):
                    state.store_outputs.append({
                        **entry, "session_id": owner,
                        "label": "CALCULATION_VERIFIED" if str(entry["output_id"]) in verified | state.verified_outputs
                        else "DATA_COVERAGE_VERIFIED"})

    def _data_date_lines(self, state: RunState, request: AgentRunRequest, result: AgentRunResponse) -> AgentRunResponse:
        """R-STORE (C2e, user decision 4): the answer states its data date when it differs from the earlier answers'
        (the user asked for newer data), or offers a recomputation when it kept an older one; the backend writes the
        line from the outputs' own dates, so it never depends on the model. The answer's line goes to the data record."""
        if state.data_date is None:
            return result
        produced = sorted({str(o["lineage"]["data_as_of"]) for o in state.store_outputs
                           if isinstance(o.get("lineage"), dict) and o["lineage"].get("data_as_of")})
        earlier, line = state.data_date.as_of, None
        if produced and earlier and produced[-1] != earlier:
            line = DATA_DATE_CHANGED_LINE.format(new=produced[-1], old=earlier)
        elif produced and earlier and not state.data_date.newest \
                and state.reference_date is not None and earlier < previous_weekday(state.reference_date):
            line = DATA_DATE_PINNED_LINE.format(date=earlier)
        response = result.response
        if records.has_data(state.data_record) and response is not None:
            records.add_answer(state.data_record, state.request_id, question=request.message,
                               response_type=response.response_type, answer=response.answer,
                               data_as_of=produced[-1] if produced else None)
            result = result.model_copy(update={"data_record": records.public(state.data_record)})
        if line and response is not None and response.response_type in ("ANSWER", "LIMITATION") \
                and line not in response.limitations:
            result = result.model_copy(update={"response": response.model_copy(update={
                "limitations": [*response.limitations, line]})})
        return result

    def _restorer(self, request: AgentRunRequest) -> Callable[..., list[dict[str, Any]]] | None:
        """R-STORE: put the conversation's stored tables back into each session this run opens."""
        if self.result_store is None or not request.conversation_id:
            return None
        store, upload, conversation_id = self.result_store, self.carried_uploader, request.conversation_id

        def restore(session_id: str, view: dict[str, Any], allowed: list[str] | None) -> list[dict[str, Any]]:
            return restore_missing(store, lambda sid, meta, data: upload(sid, request.request_id, meta, data),
                                   conversation_id, request.request_id, session_id, view, allowed)
        return restore

    def _store_results(self, state: RunState, conversation_id: str | None) -> None:
        """R-STORE: keep this run's released outputs and executions for the life of the conversation; the data record
        says which were stored. Never fails the answer."""
        if self.result_store is None or not conversation_id or not (state.store_outputs or state.store_executions):
            return
        fetch = self.output_fetcher
        stored = store_released(self.result_store, lambda sid, oid: fetch(sid, oid, state.request_id),
                                conversation_id, state.request_id, state.store_outputs)
        records.mark_stored(state.data_record, stored)
        for execution in state.store_executions:
            try:
                self.result_store.save_execution(conversation_id, state.request_id, execution)
            except Exception as exc:  # noqa: BLE001 - storing never fails the answer
                log_event("result_store_failed", request_id=state.request_id,
                          execution_id=execution.get("execution_id"), error=type(exc).__name__)

    def _end_sessions(self, state: RunState) -> None:
        """S28 (golden g7 2026-10-02): the answer of this request ended, so every sandbox session it holds is released
        (completed: WARM_IDLE, reusable or evictable; any other: closed), including a completed session that ran
        code again, which the per-session closes below skip. Without the sandbox's release (an older sandbox, or a
        failed call) the per-session closes run."""
        if self.session_releaser is not None and (state.sessions or state.needs or state.research is not None):
            try:
                released = self.session_releaser(state.request_id)
                log_event("request_sessions_released", request_id=state.request_id,
                          sessions={r.get("session_id"): r.get("status") for r in released})
                return
            except Exception as exc:  # noqa: BLE001 - release is best effort; the closes and the idle timeout remain
                log_event("request_release_failed", request_id=state.request_id, error=type(exc).__name__)
        self._close_sessions(state)
        self._close_research_sessions(state)

    def _close_sessions(self, state: RunState) -> None:
        """Close every analysis session this run opened that did not complete (S05). The sandbox closes a session
        itself only when complete_analysis passes; a failed, incomplete or abandoned session would otherwise hold
        one of its few slots until the idle timeout, and later runs would meet SESSION_CAPACITY_EXCEEDED."""
        if self.session_closer is None:
            return
        open_ids = [session_id for session_id, session in state.sessions.items() if SESSION_ID_RE.fullmatch(session_id)
                    and session.get("superseded") in (None, "CLOSE_FAILED", "NOT_CLOSED")
                    and (state.completions.get(session_id) or {}).get("status") != "COMPLETED"]
        if not open_ids:
            return
        try:
            closed = self.session_closer(state.request_id, open_ids)
        except Exception:  # noqa: BLE001 - closing is best effort; the sandbox's idle timeout remains
            closed = {session_id: "CLOSE_FAILED" for session_id in open_ids}
        log_event("analysis_sessions_closed", request_id=state.request_id, sessions=closed)

    def _close_research_sessions(self, state: RunState) -> None:
        """Multi-Angle Research: close the group sessions of this run that did not complete (the executor keeps them
        out of state.sessions)."""
        executor = state.research.executor if state.research is not None else None
        if executor is None or self.session_closer is None:
            return
        open_ids = executor.open_sessions()
        if not open_ids:
            return
        try:
            closed = self.session_closer(state.request_id, open_ids)
        except Exception:  # noqa: BLE001 - closing is best effort; the sandbox's idle timeout remains
            closed = {session_id: "CLOSE_FAILED" for session_id in open_ids}
        log_event("research_sessions_closed", request_id=state.request_id, sessions=closed)

    @staticmethod
    def _same_continuation(verified: Any) -> ContinuationOut | ContinuationOutV2:
        """The continuation of a verified plan, unchanged (same token and expiry), so asking again never extends it."""
        common = dict(plan_id=verified.plan_id, origin_request_id=verified.origin_request_id,
                      conversation_id=verified.conversation_id, token=verified.token,
                      expires_at=verified.expires_at.isoformat())
        if isinstance(verified.plan, ResearchPlanV2):
            return ContinuationOutV2(**common, research_data_plan=verified.research_data_plan)
        return ContinuationOut(**common)

    # ------------------------------------------------------------------------------------------ Research Plan turns

    def _prepare_plan_turn(self, request: AgentRunRequest, state: RunState) -> None:
        """Decide what this request may do with research: propose a plan (no continuation), execute a verified
        approved plan, revise, re-plan after a failed verification, cancel, or ask again (unrelated reply). Sets the
        allowed final response types, the tool filter, the guard and an application note."""
        if state.forced_path == "ANALYSIS":
            # no plan step: a pending plan (SERVER mode) is left untouched and its reply is not read
            if request.continuation is not None:
                log_event("analysis_path_continuation_ignored", request_id=request.request_id,
                          plan_id=request.continuation.plan_id)
            names = frozenset(self.registry.names()) - {"check_data_feasibility", "check_research_feasibility"} \
                - RESEARCH_RUN_TOOLS
            state.allowed_types, state.tool_filter = BASE_TYPES, names
            state.guard = ResearchGuard(required=True)
            state.input_items.insert(len(state.input_items) - 1, {"role": "user", "content": ANALYSIS_PATH_NOTE})
            return
        if state.forced_path == "RESEARCH" and request.continuation is None:
            self._set_turn(state, "PROPOSE", PLAN_TYPES, self.plan_tools, ResearchGuard(required=True),
                           note=RESEARCH_PATH_NOTE + self._angle_count_note(), verification="NOT_PRESENTED")
            return
        if not self.plan_confirmation:
            if request.continuation is not None:
                log_event("research_plan_continuation_ignored", request_id=request.request_id,
                          reason="AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION is off")
            return
        continuation = request.continuation
        if continuation is None:
            self._set_turn(state, "PROPOSE", ALL_TYPES, None, ResearchGuard(required=True), verification="NOT_PRESENTED")
            return
        assert self.signer is not None
        verified, verification = None, "VERIFIED"
        is_v2 = isinstance(continuation, ContinuationInV2)
        try:
            if not self._plan_form_runs(is_v2):
                # a v1 plan while only Multi-Angle Research runs, or a v2 plan while it does not: never executed
                raise PlanVerificationError("RESEARCH_PLAN_TOKEN_INVALID", "PLAN_VERSION")
            verified = (self.signer_v2 if is_v2 else self.signer).verify(continuation, request.conversation_id)
        except PlanVerificationError as exc:
            verification = exc.code
            log_event("research_plan_verification_failed", request_id=request.request_id, code=exc.code,
                      reason=exc.reason, plan_id=continuation.plan_id)
        action, instruction, source = continuation.action, continuation.revision_instruction, "EXPLICIT"
        if action is None:
            action, instruction = self._classify_reply(state, request.message, continuation.plan)
            source = "CLASSIFIER"
        if action == "REVISE" and not (instruction or "").strip():
            instruction = request.message[:2000]
        state.plan_meta.update(action=action, action_source=source, verification=verification,
                               approved_plan_id=verified.plan_id if verified and action == "APPROVE" else None)
        plan_json = dumps(continuation.plan.model_dump(mode="json"))
        # P12 (suite20c r04/r06, 2026-09-30): the plan's numbers are read from its JSON values, not by the prose
        # parser over the compact dump (which drops "-40" after a comma and every number of "[25,35,45]")
        numbers = released_numbers(continuation.plan.model_dump(mode="json"))
        guard = ResearchGuard(required=True, verification=verification)
        if action in ("CANCEL", "UNRELATED"):
            state.user_text = request.message  # the reply itself, not the research question it answers
        if action == "UNRELATED" and verification == "RESEARCH_PLAN_TOKEN_EXPIRED":
            # R-STORE C2e: a new question after a plan expired is answered as one; the expired plan is not presented
            self._set_turn(state, "PROPOSE", ALL_TYPES, None, ResearchGuard(required=True),
                           verification="NOT_PRESENTED")
            log_event("research_plan_turn", request_id=request.request_id, turn=state.plan_turn, action=action,
                      action_source=source, verification=verification, plan_id=continuation.plan_id)
            return
        if action == "CANCEL":
            self._set_turn(state, "CANCEL", frozenset({"ANSWER", "LIMITATION"}), frozenset(), guard,
                           note=CANCEL_NOTE)
        elif action == "APPROVE" and verified is not None and is_v2:
            state.verified_plan = verified
            state.carried_outputs = self._carried_ids(state, verified.plan)
            self._approve_v2(state, request, verified, verification, plan_json)
            state.context_numbers.extend(numbers)
        elif action == "APPROVE" and verified is not None:
            # The approved plan becomes the guard's reference for this request only.
            state.verified_plan = verified
            state.carried_outputs = self._carried_ids(state, verified.plan)
            self._set_turn(state, "EXECUTE_APPROVED", ALL_TYPES, None,
                           ResearchGuard(required=True, plan=verified.plan, plan_id=verified.plan_id,
                                         verification=verification),
                           note=APPROVED_NOTE.format(
                               plan_id=verified.plan_id, plan=plan_json,
                               rules="HYPOTHESIS PLAN" if self.hypothesis_plans else "RESEARCH PLAN CONFIRMATION")
                           + self._draft_note(state, verified.draft_id))
            state.user_text = verified.plan.original_question + "\n" + state.user_text
            state.context_numbers.extend(numbers)
        elif action == "UNRELATED" and verified is not None:
            self._set_turn(state, "UNRELATED", frozenset({"CLARIFICATION"}), frozenset(), guard,
                           note=UNRELATED_NOTE.format(plan_id=verified.plan_id))
            # The same continuation goes back unchanged (same token and expiry), so asking again never extends it.
            state.continuation = self._same_continuation(verified)
        elif action == "REVISE":
            self._set_turn(state, "REVISE", PLAN_TYPES, self.plan_tools, guard, note=REVISE_NOTE.format(
                plan_id=continuation.plan_id, instruction=instruction,
                unverified="" if verified is not None else " (sent back by the caller; it could not be verified)",
                plan=plan_json) + self._angle_count_note())
            if verified is not None:
                state.context_numbers.extend(numbers)
        else:  # an approval or unrelated reply whose continuation did not verify: nothing is approved
            note = REPLAN_NOTES[verification].format(plan_id=continuation.plan_id, plan=plan_json)
            self._set_turn(state, "REPLAN", PLAN_TYPES, self.plan_tools, guard, note=note)
            if verification == "RESEARCH_PLAN_TOKEN_EXPIRED":
                state.context_numbers.extend(numbers)
        log_event("research_plan_turn", request_id=request.request_id, turn=state.plan_turn, action=action,
                  action_source=source, verification=verification, plan_id=continuation.plan_id)

    def _approve_v2(self, state: RunState, request: AgentRunRequest, verified: Any, verification: str,
                    plan_json: str) -> None:
        """A verified approval of a multi-angle plan: this run gets the plan's executor and only the discovery, research
        run and session reading tools. A RESEARCH data need stays refused; the executor builds research_governance/v2
        from the verified plan and data plan, so the model never writes it."""
        assert state.research is not None
        state.research.executor = self.research_limits["factory"](verified, request.request_id)
        data_plan = verified.research_data_plan
        groups = {g.get("bundle_group_id"): g.get("angle_ids") for g in data_plan.get("bundle_groups") or []}
        tools = (DISCOVERY_TOOLS | RESEARCH_RUN_TOOLS | {"inspect_session", "get_session_output", "get_lineage"}) \
            & frozenset(self.registry.names())
        self._set_turn(state, "EXECUTE_APPROVED", ALL_TYPES, frozenset(tools),
                       ResearchGuard(required=True, verification=verification),
                       note=APPROVED_NOTE_V2.format(plan_id=verified.plan_id, groups=dumps(groups), plan=plan_json))
        state.plan_meta.update(plan_version=PLAN_VERSION_V2,
                               research_data_plan_sha256=verified.data_plan_sha256)
        state.user_text = verified.plan.original_question + "\n" + state.user_text

    @staticmethod
    def _set_turn(state: RunState, turn: str, allowed: frozenset[str], tools: frozenset[str] | None,
                  guard: ResearchGuard, note: str | None = None, verification: str | None = None) -> None:
        state.plan_turn, state.allowed_types, state.tool_filter, state.guard = turn, allowed, tools, guard
        if verification is not None:
            state.plan_meta.setdefault("verification", verification)
        if note:
            # before the user's reply, after the run context and the history
            state.input_items.insert(len(state.input_items) - 1, {"role": "user", "content": note})

    @staticmethod
    def _angle_count_note() -> str:
        """Mode 4: the angle count this request's plan must have, as an application note (empty otherwise)."""
        bounds = current_angle_bounds.get()
        if bounds is None:
            return ""
        low, high = bounds
        count = (f"exactly {NUMBER_WORDS[low]} angle" + ("s" if low > 1 else "")) if low == high \
            else f"from {NUMBER_WORDS[low]} to {NUMBER_WORDS[high]} angles"
        return " " + ANGLE_COUNT_NOTE.format(count=count)

    def _apply_turn_kind(self, state: RunState) -> None:
        """The conversation router's class for this sub-run (mode 4): its note, and for CLARIFY and CONVERSATIONAL only
        the read-only tools and the answer types, so a question about a result never extracts data or runs code."""
        intent = router.current_intent.get()
        named = variants(current_design_changes.get()) if self.ask_back else {}
        for note in (router.intent_note(intent),
                     router.NOTES["QUICK_SUMMARY"] if (intent or {}).get("choice") == "QUICK_SUMMARY" else None,
                     VARIANT_NOTE.format(variants="; ".join(f"{name}: {', '.join(values)}"
                                                            for name, values in named.items())) if named else None):
            if note:  # EXEC-3: the router's reading of the request, and a quick summary the user chose
                state.input_items.insert(len(state.input_items) - 1, {"role": "user", "content": note})
        kind = router.current_turn_kind.get()
        if kind is None:
            return
        state.plan_meta["turn_kind"] = kind
        if kind in ("CLARIFY", "CONVERSATIONAL", "FACT"):
            available = state.tool_filter if state.tool_filter is not None else frozenset(self.registry.names())
            # FACT (first-message router) also reads public web facts; no step of these kinds pulls warehouse data
            effects = router.READ_EFFECTS | ({"FETCHES_WEB"} if kind == "FACT" else frozenset())
            state.tool_filter = frozenset(available) & self.registry.names_with_effect(frozenset(effects))
            state.allowed_types = BASE_TYPES
        note = router.NOTES.get(kind)
        if note:
            state.input_items.insert(len(state.input_items) - 1, {"role": "user", "content": note})
        log_event("conversation_turn_routed", request_id=state.request_id, turn_kind=kind,
                  tools=sorted(state.tool_filter) if state.tool_filter is not None else "ALL")

    def classify_turn(self, request_id: str, message: str, context: dict[str, Any]
                      ) -> tuple[str | None, str | None, dict[str, Any]]:
        """The conversation router's model call (one small tool-free call, reasoning low): the turn kind and a
        revision instruction, with its usage record. A failure returns None (the backend's rules pick the class)."""
        parsed, record = self._router_call(
            request_id, "turn-router", router.router_instructions(self.ask_back),
            dumps({"conversation": context, "user_message": message[:4000]}), "conversation_turn",
            router.router_schema(self.ask_back), router.TurnClassification, "conversation_router_failed",
            attempts=2 if self.ask_back else 1)
        if parsed is not None:
            record["referent"] = parsed.referent  # M64: what the message is about
            # M82: the design values the message states, as structured changes for the plan gates
            record["design_value_changes"] = [c.model_dump(exclude_none=True) for c in parsed.design_value_changes]
            if self.ask_back:  # EXEC-3
                record.update(understood_intent=parsed.understood_intent, question=parsed.question,
                              options=[o.model_dump() for o in parsed.options])
        log_event("conversation_turn_classified", request_id=request_id, turn_kind=parsed.turn_kind if parsed else None,
                  status=record["status"], referent=record.get("referent"),
                  design_value_changes=record.get("design_value_changes"),
                  latency_ms=record["latency_ms"], input_tokens=record["input_tokens"],
                  output_tokens=record["output_tokens"], **({"attempts": record["attempts"]} if self.ask_back else {}))
        return (parsed.turn_kind if parsed else None), (parsed.revision_instruction if parsed else None), record

    def classify_first(self, request_id: str, message: str) -> tuple[str | None, str | None, dict[str, Any]]:
        """The first-message router (ROUTER_BENCHMARK_2026-10-04.md; one small tool-free call, reasoning low): the
        route and its reason, with its usage record. A failure returns None (the backend's fallback applies)."""
        parsed, record = self._router_call(
            request_id, "first-router", router.first_instructions(self.ask_back), message[:4000],
            "first_message_route", router.first_schema(self.ask_back), router.FirstRoute,
            "first_message_router_failed", attempts=2 if self.ask_back else 1)
        if parsed is not None and self.ask_back:  # EXEC-3: the reading every later step uses
            record.update(understood_intent=parsed.understood_intent, assumptions=parsed.assumptions,
                          question=parsed.question, options=[o.model_dump() for o in parsed.options],
                          design_value_changes=[c.model_dump(exclude_none=True) for c in parsed.design_value_changes],
                          referent="NONE")
        log_event("first_message_routed", request_id=request_id, route=parsed.route if parsed else None,
                  reason=(parsed.reason[:300] if parsed else None), status=record["status"],
                  latency_ms=record["latency_ms"], input_tokens=record["input_tokens"],
                  output_tokens=record["output_tokens"],
                  **({"attempts": record["attempts"], "understood_intent": record.get("understood_intent"),
                      "design_value_changes": record.get("design_value_changes")} if self.ask_back else {}))
        return (parsed.route if parsed else None), (parsed.reason if parsed else None), record

    def _database_holds(self, state: RunState, call_id: str, name: str, arguments: Any) -> ToolOutcome | None:
        """P34 (plan 2026-10-05 Fase D option A): before a web lookup, one small model call compares the asked
        attribute with the reference columns of the catalog (derived from the Governor at run time). When a column
        holds it, the call is refused with next_action CALL:lookup_reference naming that table and column, until
        this run has read the reference tables; after a read the web call runs (the database may lack the row).
        Any failure lets the web call run (fail-open, logged)."""
        catalog = getattr(self.registry, "reference_catalog", None)
        offered = state.tool_filter if state.tool_filter is not None else frozenset(self.registry.names())
        if catalog is None or "lookup_reference" not in offered or not isinstance(arguments, dict):
            return None
        if name == "research_web":  # item 12: the need is the attribute, the subjects its subject
            subject = ", ".join(str(x) for x in arguments.get("subjects") or [])[:200]
            attribute = str(arguments.get("need") or "")
        else:
            subject, attribute = str(arguments.get("subject") or ""), str(arguments.get("attribute") or "")
        key = (subject.strip().casefold(), attribute.strip().casefold())
        if key in state.reference_hints and state.reference_reads > state.reference_hints[key]:
            log_event("web_fact_after_database_read", request_id=state.request_id, subject=subject[:100],
                      attribute=attribute[:100])
            return None
        try:
            tables = catalog.tables()
        except Exception as exc:  # noqa: BLE001 - the web call runs
            log_event("web_fact_catalog_check_failed", request_id=state.request_id, stage="columns",
                      error=type(exc).__name__)
            return None
        if not tables:
            return None
        parsed, record = self._router_call(
            state.request_id, "web-fact-check", reference.MATCH_INSTRUCTIONS,
            dumps(reference.matcher_content(subject, attribute, tables)), "reference_match", reference.MATCH_SCHEMA,
            reference.ReferenceMatch, "web_fact_catalog_check_failed", usage_state=state)
        held = catalog.column(parsed.table, parsed.column) if parsed is not None and parsed.held else None
        log_event("web_fact_catalog_checked", request_id=state.request_id, subject=subject[:100],
                  attribute=attribute[:100], status=record["status"], held=held is not None,
                  table=held["table"] if held else None, column=held["columns"][0]["column"] if held else None,
                  input_tokens=record["input_tokens"], output_tokens=record["output_tokens"],
                  latency_ms=record["latency_ms"])
        if held is None:
            return None
        state.reference_hints[key] = state.reference_reads
        column = held["columns"][0]
        outcome = error_outcome(
            call_id, name, "DATABASE_HOLDS_THIS_ATTRIBUTE",
            f"The database holds this: {held['table']}.{column['column']} ({column.get('description') or ''}). "
            "Read it with lookup_reference (where on the entity column for one subject, or match for a name) and "
            f"answer from it. {name} runs after that read only if the table does not answer.")
        outcome.output["error"].update(
            next_action="CALL:lookup_reference",
            suggested_call={"tool": "lookup_reference", "table": held["table"],
                            "columns": [column["column"]], "entity_column": held.get("entity_column")})
        return outcome

    def _router_call(self, request_id: str, session: str, instructions: str, content: str, schema_name: str,
                     schema: dict[str, Any], model: Any, failure_event: str,
                     usage_state: RunState | None = None, attempts: int = 1) -> tuple[Any, dict[str, Any]]:
        """One router model call: AI_MODEL, reasoning low, strict JSON schema, no tools. Returns the parsed object
        (None on any failure, including an empty reply) and the usage record. usage_state: the run whose usage
        counts this call (a check inside a run). attempts: EXEC-3 retries a failed call once before the backend's
        fallback (the record sums every attempt)."""
        state = usage_state or RunState(request_id=request_id, started=self.clock(), input_items=[])
        payload: dict[str, Any] = {
            "model": self.settings.ai_model, "session_id": session_key(f"{request_id}:{session}"),
            "instructions": instructions,
            "input": [{"role": "user", "content": content}],
            "reasoning": self.settings.reasoning("low"),
            "max_output_tokens": min(2000, self.settings.ai_max_output_tokens),
            "store": False, "provider": self._provider(),
            "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
        }
        started = time.monotonic()
        record: dict[str, Any] = {"status": "FAILED", "input_tokens": 0, "output_tokens": 0, "cost": None,
                                  "latency_ms": 0, "attempts": 0}
        parsed = None
        while parsed is None and record["attempts"] < max(1, attempts):
            record["attempts"] += 1
            try:
                response = self.client.create(payload)
                usage = self._add_usage(state, response)
                record.update(input_tokens=record["input_tokens"] + usage["input_tokens"],
                              output_tokens=record["output_tokens"] + usage["output_tokens"],
                              cost=usage["cost"] if record["cost"] is None or usage["cost"] is None
                              else record["cost"] + usage["cost"])
                parsed = model.model_validate_json(self._output_text(response).strip() or "{}")
                record["status"] = "COMPLETED"
            except Exception as exc:  # noqa: BLE001 - the backend's fallback applies
                log_event(failure_event, request_id=request_id, error=type(exc).__name__,
                          **({"attempt": record["attempts"]} if attempts > 1 else {}))
        record["latency_ms"] = int((time.monotonic() - started) * 1000)
        if attempts <= 1:
            record.pop("attempts")
        return parsed, record

    def classify_reply(self, request_id: str, message: str, plan: Any) -> tuple[str, str | None, dict[str, Any]]:
        """Mode 4: the reply classifier outside a run (APPROVE, REVISE, CANCEL or UNRELATED; any failure is
        UNRELATED), with its usage record (status, tokens, cost, latency)."""
        state = RunState(request_id=request_id, started=self.clock(), input_items=[])
        action, instruction = self._classify_reply(state, message, plan)
        record = dict(state.classifier or {})
        if state.reply_reading is not None:
            record["reading"] = state.reply_reading  # P3b: mode 4 hands it to the step that runs (popped there)
        return action, instruction, record

    def _classify_reply(self, state: RunState, message: str, plan: Any) -> tuple[str, str | None]:
        """A free-text reply to a plan, read by one small tool-free model call constrained to APPROVE, REVISE, CANCEL
        or UNRELATED. Any failure is UNRELATED, which never approves anything."""
        payload: dict[str, Any] = {
            "model": self.settings.ai_model, "session_id": session_key(f"{state.request_id}:plan-reply"),
            "instructions": CLASSIFIER_INSTRUCTIONS + (router.REPLY_READING_RULE if self.ask_back else ""),
            "input": [{"role": "user", "content": dumps({"research_plan": plan_digest_v2(plan)
                                                         if isinstance(plan, ResearchPlanV2) else plan_digest(plan),
                                                         "user_reply": message[:4000]})}],
            "reasoning": self.settings.reasoning("low"), "max_output_tokens": min(2000, self.settings.ai_max_output_tokens),
            "store": False, "provider": self._provider(),
            "text": {"format": {"type": "json_schema", "name": "research_plan_reply", "strict": True,
                                "schema": router.reply_schema(CLASSIFIER_SCHEMA) if self.ask_back
                                else CLASSIFIER_SCHEMA}},
        }
        started = time.monotonic()
        record: dict[str, Any] = {"status": "FAILED", "input_tokens": 0, "output_tokens": 0, "cost": None,
                                  "latency_ms": 0}
        action, instruction = "UNRELATED", None
        try:
            response = self.client.create(payload)
            usage = self._add_usage(state, response)
            state.model_calls.append({"iteration": 0, "call": "plan_reply_classifier",
                                      "provider_response_id": response.get("id")})
            record.update(input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"], cost=usage["cost"])
            raw = json.loads(self._output_text(response).strip() or "{}")
            parsed = ReplyClassification.model_validate(
                {k: raw.get(k) for k in ("action", "revision_instruction")} if self.ask_back and isinstance(raw, dict)
                else raw)
            action, instruction = parsed.action, parsed.revision_instruction
            record["status"] = "COMPLETED"
            if self.ask_back and isinstance(raw, dict):
                try:  # P3b: a reading that does not validate is dropped; the action stands
                    reading = router.ReplyReading.model_validate(raw)
                    state.reply_reading = {"referent": reading.referent, "design_value_changes": [
                        c.model_dump(exclude_none=True) for c in reading.design_value_changes]}
                except Exception:  # noqa: BLE001
                    log_event("research_plan_reading_dropped", request_id=state.request_id)
        except Exception as exc:  # noqa: BLE001 - a failed classification approves nothing
            log_event("research_plan_classifier_failed", request_id=state.request_id, error=type(exc).__name__)
        record["latency_ms"] = int((time.monotonic() - started) * 1000)
        state.model_latency_ms += record["latency_ms"]
        state.classifier = record
        log_event("research_plan_reply_classified", request_id=state.request_id, action=action,
                  status=record["status"], latency_ms=record["latency_ms"], input_tokens=record["input_tokens"],
                  output_tokens=record["output_tokens"],
                  **({"reading": state.reply_reading} if self.ask_back else {}))
        return action, instruction

    def _loop(self, state: RunState) -> FinalResponse:
        while state.iterations < self.settings.ai_max_tool_iterations:
            budget = current_time_budget.get()
            limit = self.settings.ai_max_analysis_seconds if budget is None \
                else min(budget, self.settings.ai_max_analysis_seconds)
            if self.clock() - state.started >= limit:
                return self._exhausted(state, "ANALYSIS_TIMEOUT")

            tools = [] if state.tools_locked or state.structured_only else self._turn_tools(state)
            context_tokens = self._estimate_context(state, tools)
            if tools and context_tokens + self.settings.ai_max_output_tokens >= self._soft_context_limit():
                # Degrade instead of failing: stop tool use and finalize from what was retrieved.
                self._withdraw_tools(state, "CONTEXT_BUDGET")
                state.input_items.append({"role": "user", "content": self.context_budget_instruction})
                tools = []
                context_tokens = self._estimate_context(state, tools)
            # On the final re-ask the tools are still sent, so the request prefix and the provider stay the same,
            # but they are not offered: a call in that turn is refused, as in the strict final turn.
            state.tools_offered = bool(tools) and not state.final_reask_sent
            payload = self._payload(state, tools)
            if context_tokens + self.settings.ai_max_output_tokens > self.settings.ai_max_context_tokens:
                # Last-resort safety net: even the tool-free finalization turn does not fit.
                raise RunFailure("CONTEXT_LIMIT", "Request would exceed AI_MAX_CONTEXT_TOKENS")

            call_started = time.monotonic()
            try:
                response = self.client.create(payload)
            except ProviderError as exc:
                if not (state.reasoning_replayed and exc.code == "PROVIDER_REJECTED"):
                    raise
                # S4c: a provider that refuses replayed reasoning items: drop them and stop replaying in this run
                state.input_items = [i for i in state.input_items if i.get("type") != "reasoning"]
                state.reasoning_replayed, state.replay_off = False, True
                log_event("ai_reasoning_replay_refused", request_id=state.request_id, iteration=state.iterations + 1,
                          status_code=exc.status_code)
                payload = self._payload(state, tools)
                response = self.client.create(payload)
            latency_ms = int((time.monotonic() - call_started) * 1000)
            state.iterations += 1
            usage = self._add_usage(state, response)
            state.model_latency_ms += latency_ms
            prefix = static_prefix_hash(payload)
            state.static_prefixes.append(prefix)
            state.model_calls.append({"iteration": state.iterations, "provider_response_id": response.get("id"),
                                      "latency_ms": latency_ms})
            if self.audit_outbox is not None:
                state.audit_trace.append(model_event(state.model_calls[-1], self.wall_clock()))
            calls = [
                item for item in response.get("output", [])
                if isinstance(item, dict) and item.get("type") == "function_call"
            ]
            log_event(
                "ai_model_call",
                request_id=state.request_id,
                session_id=payload["session_id"],
                iteration=state.iterations,
                model=response.get("model") or self.settings.ai_model,
                provider=response.get("provider"),
                provider_response_id=response.get("id"),
                static_prefix_sha256=prefix,
                tools_offered=[tool["name"] for tool in tools],
                tools_requested=[str(call.get("name")) for call in calls],
                latency_ms=latency_ms,
                **usage,
            )
            if self.settings.ai_capture_reasoning:
                log_reasoning(log_event, response, request_id=state.request_id, iteration=state.iterations,
                              tools_requested=[str(call.get("name")) for call in calls],
                              reasoning_tokens=usage["reasoning_tokens"])
            if usage["input_tokens"] > self.settings.ai_max_context_tokens:
                raise RunFailure("CONTEXT_LIMIT", "Provider-reported input exceeded AI_MAX_CONTEXT_TOKENS")

            if calls:
                if self.settings.ai_replay_reasoning and not state.replay_off:
                    # S4c (K7): the reasoning that led to these calls goes back with them, as received
                    replay = [item for item in response.get("output", [])
                              if isinstance(item, dict) and item.get("type") == "reasoning"]
                    if replay:
                        state.input_items.extend(replay)
                        state.reasoning_replayed = True
                if state.final_reask_sent:
                    state.structured_only = True  # it was asked for the final response, not for a tool
                # OpenRouter closes a tool call cut off at max_output_tokens and still reports it completed; its
                # arguments are then a truncated object. Reaching the cap exactly is the only signal, so such calls
                # are not run.
                truncated = usage["output_tokens"] >= self.settings.ai_max_output_tokens
                if truncated:
                    log_event("ai_output_truncated", request_id=state.request_id, iteration=state.iterations,
                              output_tokens=usage["output_tokens"], reasoning_tokens=usage["reasoning_tokens"],
                              tools=[str(call.get("name")) for call in calls])
                step_tools = current_step_tools.set(self._desk(state))
                try:
                    for call in calls:
                        self._handle_call(state, call, truncated=truncated)
                finally:
                    current_step_tools.reset(step_tools)
                continue

            raw = self._output_text(response)
            unapplied = None
            if state.repair_base is not None:
                raw, unapplied = self._apply_edit(state, raw)
            state.current_raw = raw
            if unapplied is not None and state.edit_retry_base is not None:
                # EXEC-R R4b: one more edit against the same draft, with the exact cause (was a full rewrite)
                self._echo_draft(state, raw)
                state.input_items.append({"role": "user", "content": str(unapplied) + self._offer_edit(state, raw)})
                continue
            try:
                if unapplied is not None:
                    raise unapplied
                dropped: dict[str, Any] = {}
                parsed = self._parse_final_output(raw, dropped)
                state.last_draft = parsed
                if dropped:
                    self._note_extra_keys(state, dropped)
                final = self._check_budget_limitations(state, self._turn_type(state, parsed))
                final, forced = self._resolve_references(state, final)
                if forced:
                    return self._finalize_findings(state, final)
                return self._finalize_findings(state, self._validation_gate(state, final))
            except TurnRuleError as exc:
                self._reject_final(state, raw, str(exc))
            except GateRejection as exc:
                # The model may still repair the analysis, so tools stay available for this turn.
                self._echo_draft(state, raw)
                state.structured_only = False
                state.final_reask_sent = False
                state.input_items.append({"role": "user", "content": str(exc) + self._offer_edit(state, raw)})
            except ValueError as exc:
                issue = str(exc)
                if tools and not raw.strip() and unapplied is None \
                        and state.empty_turn_retries < MAX_EMPTY_TURN_RETRIES:
                    state.empty_turn_retries += 1
                    state.input_items.append({"role": "user", "content": EMPTY_TURN_NOTE})
                    log_event("ai_empty_turn_retried", request_id=state.request_id, iteration=state.iterations,
                              retry=state.empty_turn_retries, provider=response.get("provider"),
                              output_tokens=usage["output_tokens"], reasoning_tokens=usage["reasoning_tokens"])
                    continue
                if usage["output_tokens"] >= self.settings.ai_max_output_tokens:
                    # found live (golden run 2026-09-29): a long plan was cut off mid-JSON and the model only saw
                    # "EOF while parsing"
                    issue = TRUNCATED_FINAL_INSTRUCTION.format(limit=self.settings.ai_max_output_tokens) + (
                        TRUNCATED_PLAN_HINT if self.multi_angle else "")
                    log_event("ai_final_truncated", request_id=state.request_id, iteration=state.iterations,
                              output_tokens=usage["output_tokens"], reasoning_tokens=usage["reasoning_tokens"])
                if tools:
                    self._request_structured_final(state, raw, issue)
                else:
                    self._reject_final(state, raw, issue)
        return self._exhausted(state, "MAX_ITERATIONS")

    @staticmethod
    def _with_ai_choices(state: RunState, final: FinalResponse) -> FinalResponse:
        """S4 (K6): the AI's own choices, written by the system as the first assumption (never by the model)."""
        if final.response_type == "CLARIFICATION":
            return final
        lines = [line for line in (ai_choices.describe(state.ai_choices),
                                   ai_choices.describe_web_used(state.ai_choices),
                                   ai_choices.describe_web(state.web_facts),
                                   ai_choices.describe_web_research(state.web_research))
                 if line is not None and line not in final.assumptions]
        if not lines:
            return final
        log_event("ai_choices", request_id=state.request_id, choices=state.ai_choices[:ai_choices.MAX_CHOICES],
                  web_facts=[{k: f.get(k) for k in ("subject", "attribute", "status", "value")}
                             for f in state.web_facts[:10]], web_research=state.web_research[:10])
        return final.model_copy(update={"assumptions": [*lines, *final.assumptions]})

    def _exhausted(self, state: RunState, code: str) -> FinalResponse:
        """G23 D (K3, PLAN_FINAL_2026-10-04.md): the step limit or the time ran out. The last draft that parsed goes
        through every gate once more with the tools withdrawn, so each gate applies its own outcome (unsourced figures
        are still marked or refused, never passed silently), and reaches the user as a LIMITATION with the request id.
        Without a usable draft the user gets a plain "cannot be computed" message. The run keeps its error code."""
        state.exhausted = code
        reason = EXHAUSTED_REASONS[code]
        line = EXHAUSTED_LINE.format(reason=reason, request_id=state.request_id)
        draft = state.last_draft
        final = None
        if draft is not None and draft.response_type in ("ANSWER", "LIMITATION"):
            state.tools_locked = True  # every gate applies its own outcome; none can ask for a repair now
            try:
                final, forced = self._resolve_references(state, draft)
                final = self._finalize_findings(state, final if forced else self._validation_gate(state, final))
            except (TurnRuleError, GateRejection, ValueError):
                final = None
        log_event("ai_run_exhausted", request_id=state.request_id, code=code, iterations=state.iterations,
                  draft=draft.response_type if draft is not None else None, delivered=final is not None)
        if final is not None and final.response_type in ("ANSWER", "LIMITATION"):
            return final.model_copy(update={"response_type": "LIMITATION",
                                            "limitations": [*final.limitations, line]})
        return FinalResponse(response_type="LIMITATION",
                             answer=EXHAUSTED_NO_DRAFT.format(reason=reason, request_id=state.request_id),
                             assumptions=[], limitations=[line])

    def _turn_tools(self, state: RunState) -> list[dict[str, Any]]:
        desk = self._desk(state)
        return [d for d in self.registry.definitions() if d["name"] in desk]

    @staticmethod
    def _turn_type(state: RunState, final: FinalResponse) -> FinalResponse:
        if final.response_type not in state.allowed_types:
            allowed = ", ".join(sorted(state.allowed_types))
            reason = {"CANCEL": "the user cancelled the Research Plan", "UNRELATED": "a Research Plan awaits the "
                      "user's decision", "REVISE": "the user asked to revise the Research Plan", "REPLAN": "no "
                      "Research Plan is approved"}.get(state.plan_turn or "", "the caller fixed the ANALYSIS path"
                                                       if state.forced_path == "ANALYSIS"
                                                       else "this response type is not enabled")
            raise TurnRuleError(f"response_type {final.response_type} is not allowed here ({reason}); use one of: "
                                f"{allowed}.")
        return final

    def _payload(self, state: RunState, tools: list[dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.ai_model,
            # EXEC-S: one session per conversation (per run without one). OpenRouter uses it as the sticky-routing
            # key, so every call of the conversation goes to the same provider endpoint and reuses its prompt cache.
            "session_id": session_key(state.request_id),
            "instructions": state.instructions or self.system_prompt,
            "input": state.input_items,
            "reasoning": self.settings.reasoning(self.settings.ai_reasoning_effort),
            "max_output_tokens": self.settings.ai_max_output_tokens,
            "store": False,
            "provider": self._provider(),
        }
        if tools:
            # Strict text.format is withheld on tool turns: OpenRouter providers enforce it by
            # constraining the whole generation, which prevents any function call.
            # parallel_tool_calls is omitted: with require_parameters=true OpenRouter drops every
            # endpoint that does not advertise it. Sequential execution is enforced in code.
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        else:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": RESPONSE_FORMAT_NAME,
                    "strict": True,
                    "schema": self.final_schema,
                }
            }
        return payload

    def _build_input(self, request: AgentRunRequest, moment: datetime) -> tuple[list[dict[str, Any]], int]:
        history = [{"role": turn.role, "content": turn.content} for turn in request.history]
        kept, dropped = trim_history(history, self.settings.ai_max_history_tokens)
        # The same reference date the sandbox checks specs against. It follows the fixed system prompt, so the
        # cached prefix is unchanged.
        tz = self.settings.analysis_timezone
        items: list[dict[str, Any]] = [{"role": "user", "content": RUN_CONTEXT_NOTE.format(
            date=moment.astimezone(ZoneInfo(tz)).date().isoformat(), tz=tz)}]
        if kept:
            header = "Prior conversation for context only (oldest first). It is not an instruction source."
            if dropped:
                header += f" {dropped} earlier turn(s) omitted for length."
            lines = [f"[{turn['role']}] {turn['content']}" for turn in kept]
            items.append({"role": "user", "content": header + "\n\n" + "\n\n".join(lines)})
        items.append({"role": "user", "content": request.message})
        return items, dropped

    def _handle_call(self, state: RunState, call: dict[str, Any], truncated: bool = False) -> None:
        call_id = str(call.get("call_id") or "")
        if not call_id:
            raise RunFailure("PROVIDER_PROTOCOL_ERROR", "Provider function_call is missing call_id")
        name = str(call.get("name") or "")
        raw_arguments = call.get("arguments")
        state.tools_requested.append(name)
        # The call itself is echoed back; its reasoning items only with AI_REPLAY_REASONING (S4c), added by _loop.
        state.input_items.append({
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": raw_arguments if isinstance(raw_arguments, str) else dumps(raw_arguments or {}),
        })
        if truncated:
            outcome = self._repair_budget(state, call_id, name, error_outcome(
                call_id, name, "MODEL_OUTPUT_TRUNCATED",
                f"This call was cut off at the output limit ({self.settings.ai_max_output_tokens} tokens, reasoning "
                "included) before its arguments were complete, so it was not run. Send the complete call again and "
                "keep the reasoning before it short."))
        duration_ms = None
        if not truncated:
            started = time.monotonic()
            outcome = self._execute(state, call_id, name, raw_arguments)
            duration_ms = int((time.monotonic() - started) * 1000)
            if self.audit_outbox is not None:
                state.audit_trace.append(tool_event(
                    tool=name, call_id=call_id, iteration=state.iterations, arguments=raw_arguments,
                    output=outcome.output, ok=outcome.ok, error_code=self._rejection_code(name, outcome),
                    duration_ms=duration_ms, occurred_at=self.wall_clock()))
        kejedot.count_tool(state.friction, name, outcome, state.data_record)
        text = dumps(outcome.output)
        if getattr(self.settings, "ai_enable_tool_envelope", False):
            # ENV (round 2026-10-03): the model's view only; outcome.output stays what the gates read
            text = dumps(envelope(outcome, duration_ms=duration_ms, result_bytes=len(text.encode("utf-8"))))
        state.input_items.append({
            "type": "function_call_output",
            "call_id": outcome.call_id,
            "output": text,
        })

    def _execute(self, state: RunState, call_id: str, name: str, raw_arguments: Any) -> ToolOutcome:
        if not state.tools_offered:
            return error_outcome(call_id, name, "TOOLS_NOT_AVAILABLE",
                                 "No tools are available in this step. Return the final response.")
        if state.tool_filter is not None and name not in state.tool_filter:
            # a registered tool that this turn does not offer (for example a data tool while a plan is revised)
            return error_outcome(call_id, name, "TOOL_NOT_AVAILABLE_IN_THIS_TURN",
                                 f"{name} is not available while the Research Plan awaits the user's decision; only "
                                 f"{', '.join(sorted(state.tool_filter)) or 'no tools'} can be used now.")
        if state.forced_path and name == "submit_data_need_spec":
            refused = self._path_mismatch(state, call_id, name, raw_arguments)
            if refused is not None:
                return self._repair_budget(state, call_id, name, refused)
        if self.multi_angle and not self.hypothesis_plans and name == "submit_data_need_spec":
            arguments = self._tool_arguments(name, raw_arguments)
            if isinstance(arguments, dict) and arguments.get("mode") == "RESEARCH":
                state.research_refusals += 1
                log_event("multi_angle_research_data_need_refused", request_id=state.request_id)
                return self._repair_budget(state, call_id, name, error_outcome(
                    call_id, name, "MULTI_ANGLE_PLAN_REQUIRED",
                    "Research runs only through an approved multi-angle Research Plan: check its angles with "
                    "check_research_feasibility and return RESEARCH_PLAN_CONFIRMATION; after approval use "
                    "start_research_run. A calculation, screen or description uses mode ANALYSIS."))
        if state.tool_calls >= self.settings.ai_max_tool_calls:
            self._withdraw_tools(state, "TOOL_CALL_BUDGET")
            return error_outcome(
                call_id, name, "TOOL_BUDGET_EXHAUSTED",
                "The tool-call budget is exhausted. Answer with the results already returned "
                "or state the limitation.",
            )
        state.tool_calls += 1

        key = stable_hash({"tool": name, "arguments": self._normalized_arguments(raw_arguments)})
        count, last_result = state.call_history.get(key, (0, None))
        if count >= self.settings.ai_max_identical_tool_calls:
            return error_outcome(
                call_id, name, "REPEATED_TOOL_CALL",
                f"This identical call already ran {count} time(s) with the same result. "
                "Use the earlier result instead of repeating it.",
            )

        arguments = self._normalized_arguments(raw_arguments)
        stored_hash = None
        if self.catalog_protocol and name in CACHEABLE_TOOLS:
            state.catalog.calls[name] = state.catalog.calls.get(name, 0) + 1
            cached = state.catalog.cache.get(cache_key(name, arguments))
            if cached is not None:
                # no database query; the repeated-call count sees the original result, so repeats stay bounded
                state.catalog.cache_hits += 1
                stored_hash = stable_hash(cached)
                outcome = ToolOutcome(call_id=call_id, name=name, ok=True,
                                      output={**cached, "cache_hit": True, "cache_note": CACHE_NOTE})
                state.call_history[key] = (count + 1 if last_result in (None, stored_hash) else 1, stored_hash)
                return outcome
        if self.catalog_protocol and name == "submit_data_need_spec" and not self._plan_guard_refuses(arguments):
            missing = gaps(state.catalog, arguments)
            if missing is not None:
                state.catalog.refusals += 1
                outcome = error_outcome(
                    call_id, name, "CATALOG_DETAILS_REQUIRED",
                    "This data need uses catalog metadata that this run has not read, so it was not submitted. "
                    "Make the calls listed in suggested_calls, check the data need against their results, then "
                    "submit it again.")
                outcome.output["error"].update(missing=missing["tables"],
                                               missing_relationship_ids=missing["relationship_ids"],
                                               suggested_calls=missing["calls"])
                log_event("catalog_details_required", request_id=state.request_id,
                          tables=[m["table"] for m in missing["tables"]],
                          relationships=missing["relationship_ids"])
                return self._repair_budget(state, call_id, name, outcome)

        if name == "open_analysis_session":
            refused = self._one_open_session(state, call_id, name)
            if refused is not None:
                return self._repair_budget(state, call_id, name, refused)
        if name == "complete_analysis":
            refused = self._insight_source_unopened(state, call_id, name)
            if refused is not None:
                return self._repair_budget(state, call_id, name, refused)
        if name in ("run_python", "run_research_code") and state.web_numbers and not state.web_number_refused \
                and isinstance(arguments, dict) and isinstance(arguments.get("code"), str):
            found = ai_choices.web_numbers_in_code(ai_choices.typed_values(arguments["code"]), self._user_words(state)
                                                   + "\n" + state.user_history, state.web_numbers,
                                                   state.context_numbers)
            if found:
                state.web_number_refused = True  # once per run: a coincidence runs on the next call, as a choice
                log_event("web_number_in_code_refused", request_id=state.request_id, numbers=found[:10])
                return self._repair_budget(state, call_id, name, error_outcome(
                    call_id, name, "WEB_NUMBER_IN_CALCULATION",
                    f"This code uses {', '.join(f'{n:g}' for n in found[:10])}, which only a web fact supplied. A "
                    "calculation's inputs come from the database; a web fact only describes. Take the value from "
                    "the data (or from the user's words), or leave the web fact out of the code and state it in the "
                    "answer as a web fact. If the number is a parameter of your own that only happens to be equal, "
                    "send the code again unchanged."))
        if name in WEB_LOOKUP_TOOLS:
            refused = self._database_holds(state, call_id, name, arguments)
            if refused is not None:
                return self._repair_budget(state, call_id, name, refused)
        outcome = self._repair_budget(state, call_id, name, self.registry.execute(call_id, name, raw_arguments))
        if name == "lookup_reference" and outcome.ok:
            state.reference_reads += 1
        normalized = self._normalized_arguments(raw_arguments)
        if outcome.ok and isinstance(normalized, dict):
            result = outcome.output.get("result") if isinstance(outcome.output.get("result"), dict) else {}
            if (name == "run_python" and "load_output(" in str(normalized.get("code") or "")
                    and result.get("status") == "OK") \
                    or (name == "get_session_output" and result.get("origin")):
                state.opened_earlier = True
        if name == "submit_data_need_spec" and isinstance(normalized, dict) and normalized.get("mode") == "RESEARCH":
            state.research_attempted = True  # an attempt, whatever its outcome (M19)
        if name == "check_data_feasibility":
            self._track_feasibility(state, outcome)
        if name == "check_research_feasibility":
            self._track_research_feasibility(state, outcome, normalized)
        if name == "get_method_guide" and outcome.ok:
            opened = outcome.output.get("result")
            if isinstance(opened, dict) and isinstance(opened.get("guide"), dict):
                # 4b: an opened manual stays in the conversation (data record), so it is not opened twice
                records.add_manual(state.data_record, state.request_id, name=str(opened["name"]),
                                   version=opened.get("version"), sha256=str(opened.get("sha256")),
                                   guide=opened["guide"])
                log_event("method_guide_opened", request_id=state.request_id, name=opened["name"])
        if name == "get_research_library" and outcome.ok:
            # P12 (e04 "95%"): the library's own figures (interval level, minimum samples) may be named in a plan
            state.context_numbers.extend(released_numbers(outcome.output.get("result")))
        if name in RESEARCH_RUN_TOOLS:
            self._track_research_run(state, name, self._normalized_arguments(raw_arguments), outcome)
        if name in CACHEABLE_TOOLS and outcome.ok:
            # M47: the ledger records what the catalog showed in every run (the data record carries it on); the
            # cache and the guard stay with the catalog protocol
            result = outcome.output.get("result")
            if isinstance(result, dict):
                record(state.catalog, name, result)
                records.add_catalog(state.data_record, {t: state.catalog.tables[t] for t in state.catalog.tables},
                                    state.request_id)
                records.add_catalog_facts(state.data_record, name, arguments, result, state.request_id,
                                          self.wall_clock().isoformat(timespec="seconds"))
            if self.catalog_protocol:
                state.catalog.cache[cache_key(name, arguments)] = outcome.output
        self._track_choices(state, name, self._normalized_arguments(raw_arguments), outcome)
        self._track_plan_guard(state, name, outcome)
        self._track_analysis(state, name, outcome, self._normalized_arguments(raw_arguments))
        self._track_sources(state, name, self._normalized_arguments(raw_arguments), outcome)
        self._track_dataneed(state, name, self._tool_arguments(name, raw_arguments), outcome)
        if self.value_references:
            self._track_references(state, name, outcome, self._normalized_arguments(raw_arguments))
        self._track_artifacts(state, name, outcome)
        if self.result_store is not None:
            self._track_results(state, name, outcome, self._normalized_arguments(raw_arguments))
        result_hash = stable_hash(outcome.output)
        count = count + 1 if last_result in (None, result_hash) else 1
        state.call_history[key] = (count, result_hash)
        return outcome

    @staticmethod
    def _track_feasibility(state: RunState, outcome: ToolOutcome) -> None:
        result = outcome.output.get("result") if outcome.ok else None
        if not isinstance(result, dict):
            state.feasibility_checks.append({"status": outcome.error_code or "ERROR"})
            return
        AgentOrchestrator._track_pit_refusals(state, result)
        entry = {"status": result.get("status"), "draft_id": result.get("draft_id"),
                 "issues": [i.get("code") for i in result.get("issues") or [] if isinstance(i, dict)][:10],
                 "requests": [{k: r.get(k) for k in ("data_request_id", "governor_status", "code", "message")}
                              for r in result.get("requests") or [] if isinstance(r, dict)
                              and r.get("governor_status") not in ("WITHIN_LIMITS", "NEEDS_PARTITIONING")]}
        state.feasibility_checks.append(entry)
        # M29: the checked counts (rows, parts, entities) may be named in the plan's text
        state.context_numbers.extend(numbers_in(result.get("requests"), ints_only=True))
        # the plan binds the last FEASIBLE draft; a later failing check does not unbind it (the model may present
        # the plan it checked), but a later FEASIBLE one replaces it
        if result.get("status") == "FEASIBLE" and result.get("draft_id"):
            state.feasible_draft = result["draft_id"]
        log_event("research_plan_feasibility", request_id=state.request_id, status=entry["status"],
                  draft_id=entry["draft_id"], issues=entry["issues"], refused=entry["requests"])

    @staticmethod
    def _track_research_feasibility(state: RunState, outcome: ToolOutcome, arguments: Any = None) -> None:
        """check_research_feasibility: the tool's callback keeps the last FEASIBLE research data plan in the run's
        research context; the checks are recorded here for the plan gate and the logs."""
        result = outcome.output.get("result") if outcome.ok else None
        if not isinstance(result, dict):
            state.feasibility_checks.append({"status": outcome.error_code or "ERROR"})
            return
        entry = {"status": result.get("status"), "strategy": result.get("strategy"),
                 "issues": [str(i.get("code")) for i in result.get("issues") or [] if isinstance(i, dict)][:10],
                 "uncovered_angle_ids": [str(a) for a in result.get("uncovered_angle_ids") or []][:6], "requests": []}
        state.feasibility_checks.append(entry)
        # the checked estimates (rows, parts) may be named in the plan's answer
        state.context_numbers.extend(numbers_in(result.get("bundle_groups"), ints_only=True))
        # P12 (r11 "buffer 25"): the backend's adjustments and the designs and data requests it checked FEASIBLE
        # (future buffers, horizons) belong to the plan the answer presents
        state.context_numbers.extend(numbers_in(result.get("adjustments")))
        if result.get("status") == "FEASIBLE" and isinstance(arguments, dict):
            state.context_numbers.extend(numbers_in(arguments))
        if result.get("status") == "FEASIBLE" and state.research is not None and state.research.feasible:
            records.add_research(state.data_record, state.request_id, state.research.feasible)  # M47
        log_event("research_plan_feasibility", request_id=state.request_id, plan_version=PLAN_VERSION_V2,
                  status=entry["status"], strategy=entry["strategy"], issues=entry["issues"],
                  uncovered=entry["uncovered_angle_ids"],
                  data_plan_sha256=result.get("research_data_plan_sha256"))

    @staticmethod
    def _executor(state: RunState) -> Any:
        return state.research.executor if state.research is not None else None

    def _research_result(self, state: RunState) -> dict[str, Any] | None:
        """The grouped result of this run's complete_research_run, or None."""
        executor = self._executor(state)
        return executor.result if executor is not None else None

    @staticmethod
    def _finding_numbers(finding: dict[str, Any]) -> list[float]:
        """The figures of one backend finding an answer may cite (never hashes, ids or versions); a difference stated as
        a size with a direction word is the same governed figure."""
        values = numbers_in({k: finding.get(k) for k in ("sample", "estimates", "comparator", "multiple_testing",
                                                          "secondary_checks", "holdout", "method_payload",
                                                          "confidence_level")})
        return values + [abs(v) for v in values if v < 0]

    def _track_research_run(self, state: RunState, name: str, arguments: Any, outcome: ToolOutcome) -> None:
        """start_research_run, run_research_code and complete_research_run: the attempt (M19), executions, and the
        backend's findings as number sources."""
        executor = self._executor(state)
        if executor is None:
            return
        state.research_attempted = state.research_attempted or executor.attempted
        result = outcome.output.get("result") if outcome.ok else None
        if not isinstance(result, dict):
            return
        if name == "start_research_run":
            # found live (golden run 2026-09-29): the rows and entities of the prepared bundle were refused as numbers
            # without a source
            state.context_numbers.extend(numbers_in(result.get("groups"), ints_only=True))
            state.context_numbers.extend(numbers_in((result.get("session") or {}).get("datasets"), ints_only=True))
        if name == "run_research_code" and isinstance(result.get("session_opened"), dict):
            state.context_numbers.extend(numbers_in(result["session_opened"].get("datasets"), ints_only=True))
        if name == "run_research_code" and result.get("execution_id"):
            state.execution_ids.append(str(result["execution_id"]))
            code = arguments.get("code") if isinstance(arguments, dict) else None
            if result.get("status") == "OK" and isinstance(code, str):
                state.code_numbers.extend(code_numbers(code))
        elif name == "complete_research_run" and result.get("research_findings_version") == FINDINGS_V2:
            run_id = result.get("research_run_id")
            values = [v for f in result.get("research_findings") or [] if isinstance(f, dict)
                      for v in self._finding_numbers(f)]
            state.analysis_values[f"research_run:{run_id}"] = {"label": "DATA_COVERAGE_VERIFIED", "values": values}
            state.analysis_values[f"research_released:{run_id}"] = {
                "label": "DATA_COVERAGE_VERIFIED", "values": released_numbers(result.get("released_contents"))}
            state.context_numbers.extend(numbers_in(result.get("angle_completion"), ints_only=True))
            seen = insample.analysis_ranges(state.data_record, state.request_id)
            data_plan = getattr(executor.verified, "research_data_plan", None) or {}
            loaded: dict[str, list[dict[str, Any]]] = {}  # angle -> earlier results its group's session loaded
            for group in executor.groups.values():
                completion = executor.completions.get(str(group.get("session_id"))) or {}
                used = (completion.get("final_status") or {}).get("carried_inputs") or []
                for angle_id in group.get("angle_ids") or []:
                    loaded[str(angle_id)] = insample.carried(used, state.data_record)
            for finding in result.get("research_findings") or []:
                if isinstance(finding, dict) and finding.get("angle_id"):
                    overlap = insample.overlaps(seen, insample.research_ranges_v2(data_plan, str(finding["angle_id"])))
                    overlap += loaded.get(str(finding["angle_id"])) or []
                    if overlap:
                        state.in_sample[str(finding["angle_id"])] = overlap
                    # E1: kept for later turns of the conversation (cited as finding.<angle_id>)
                    records.add_finding(state.data_record, state.request_id, kind="ANGLE",
                                        finding_id=str(finding["angle_id"]),
                                        finding={**finding, **({"in_sample": overlap} if overlap else {})},
                                        recorded_at=self.wall_clock().isoformat(timespec="seconds"))
            state.final_status = {k: result.get(k) for k in (
                "status", "research_findings_version", "research_run_id", "plan_id", "calculation_validation",
                "angle_completion", "missing_angle_ids")}
            state.final_statuses.append(state.final_status)
            log_event("research_run_completed", request_id=state.request_id, research_run_id=run_id,
                      status=result.get("status"), calculation_validation=result.get("calculation_validation"),
                      angle_completion=result.get("angle_completion"),
                      statuses={f.get("angle_id"): f.get("status") for f in result.get("research_findings") or []})

    def _draft_note(self, state: RunState, draft_id: str | None) -> str:
        """The approved turn starts from the plan's feasibility draft: its spec goes into the approval note."""
        if not self.plan_feasibility or not draft_id or self.draft_reader is None:
            return ""
        try:
            draft = self.draft_reader(draft_id)
        except Exception:  # noqa: BLE001 - without the draft the model reads the catalog as before
            draft = None
        spec = (draft or {}).get("spec")
        if not isinstance(spec, dict):
            log_event("research_plan_draft_unavailable", request_id=state.request_id, draft_id=draft_id)
            return ""
        state.plan_meta["draft_id"] = draft_id
        return FEASIBLE_DRAFT_NOTE.format(draft_id=draft_id, spec=dumps({**spec, "revision": 1}))

    @staticmethod
    def _plan_guard_refuses(arguments: Any) -> bool:
        """True when the Research Plan guard inside submit_data_need_spec will refuse this RESEARCH submission; that
        refusal then comes first, so the model is not sent to read the catalog for a spec that needs a plan."""
        if not isinstance(arguments, dict) or arguments.get("mode") != "RESEARCH":
            return False
        governance = arguments.get("research_governance")
        return guard_research_submission(governance if isinstance(governance, dict) else None) is not None

    @staticmethod
    def _track_plan_guard(state: RunState, name: str, outcome: ToolOutcome) -> None:
        result = outcome.output.get("result") if outcome.ok else None
        if name == "submit_data_need_spec" and isinstance(result, dict) and result.get("status") == "REJECTED":
            code = str((result.get("error") or {}).get("code") or "")
            if code.startswith("RESEARCH_PLAN_"):
                state.guard_rejections += 1
                log_event("research_plan_guard_rejected", request_id=state.request_id, code=code,
                          plan_id=state.guard.plan_id, fields=[i.get("field_path") for i in
                                                            (result.get("error") or {}).get("issues") or []][:20])

    @staticmethod
    def _rejection_code(name: str, outcome: ToolOutcome) -> str | None:
        """The machine-readable reason a tool call did not succeed, or None for a success or a result to report."""
        if not outcome.ok:
            return outcome.error_code
        result = outcome.output.get("result")
        if not isinstance(result, dict):
            return None
        status = result.get("status") or result.get("decision")
        if name == "create_analysis_spec" and status in ("INVALID_SPEC", "ANALYSIS_SPEC_MISMATCH"):
            codes = result.get("problem_codes") or [m.get("code") for m in result.get("mismatches") or []]
            return f"{status}:{','.join(sorted(c for c in codes if c)) or 'UNSPECIFIED'}"
        if name == "prepare_analysis_data" and status not in (None, "READY"):
            return f"{status}:{(result.get('rejection') or {}).get('reason_code')}"
        if name == "run_python_analysis" and result.get("execution_status") == "FAILED":
            return f"FAILED:{(result.get('error') or {}).get('code')}"
        if name == "run_python_analysis" and result.get("status") == "REJECTED":
            return f"REJECTED:{(result.get('error') or {}).get('code')}"
        if name == "open_analysis_session" and status == "REJECTED":
            # bounded like other repairs: a capacity refusal was retried until the run's budget ran out (S05)
            return f"REJECTED:{result.get('code') or 'UNSPECIFIED'}"
        code = str((result.get("error") or {}).get("code") or "") if isinstance(result.get("error"), dict) else ""
        if name == "submit_data_need_spec" and result.get("status") == "REJECTED" and code.startswith("RESEARCH_PLAN_"):
            return f"REJECTED:{code}"  # the research guard's refusals are bounded like other repairs
        return None

    def _repair_budget(self, state: RunState, call_id: str, name: str, outcome: ToolOutcome) -> ToolOutcome:
        """Bounded repair: the same rejection may be repaired a limited number of times per run, then the model
        must report it. Counters live in the run state and are logged with the run (auditable). EXEC-R R5b: one model
        turn counts once per cause (06b: four parallel query_metric calls refused for one reason spent the budget at
        once)."""
        code = self._rejection_code(name, outcome)
        if code is None:
            return outcome
        key = f"{name}:{code}"
        if state.repair_turns.get(key) != state.iterations:  # EXEC-R R5b: parallel calls of one turn count once
            state.repair_turns[key] = state.iterations
            state.repairs[key] = state.repairs.get(key, 0) + 1
        if state.repairs[key] <= self.settings.ai_max_repair_attempts:
            return outcome
        return error_outcome(call_id, name, "REPAIR_BUDGET_EXHAUSTED",
                             f"{name} was rejected {state.repairs[key]} times for the same reason ({code}). Do not "
                             "retry it: return response_type \"LIMITATION\" naming this reason code and what it "
                             "means for the request.")

    def _estimate_context(self, state: RunState, tools: list[dict[str, Any]]) -> int:
        return estimate_tokens({
            "instructions": state.instructions or self.system_prompt, "input": state.input_items,
            "tools": tools, "schema": self.final_schema,
        })

    def _soft_context_limit(self) -> float:
        return self.settings.ai_max_context_tokens * self.settings.ai_context_soft_limit_ratio

    @staticmethod
    def _withdraw_tools(state: RunState, reason: str) -> None:
        """The single tools-withdrawn mechanism (tool-call budget or context budget); first reason wins."""
        if not state.tools_locked:
            state.tools_locked = True
            state.tools_withdrawn_reason = reason

    @staticmethod
    def _check_budget_limitations(state: RunState, final: FinalResponse) -> FinalResponse:
        if state.tools_withdrawn_reason == "CONTEXT_BUDGET" and (
            final.response_type == "CLARIFICATION"
            or (final.response_type == "ANSWER" and not final.limitations)
        ):
            raise ValueError(
                "Tool access ended at the context budget, so the response must be LIMITATION, or "
                "ANSWER with limitations stating what was read and what remains unread."
            )
        return final

    @staticmethod
    def _track_analysis(state: RunState, name: str, outcome: ToolOutcome, arguments: Any = None) -> None:
        """Record every spec review and analysis status the model has seen (from tool results only; the
        research block is taken from the approved spec's own arguments)."""
        if not outcome.ok:
            return
        result = outcome.output.get("result")
        if not isinstance(result, dict):
            return
        if name == "create_analysis_spec" and result.get("spec_id"):
            research = (arguments or {}).get("research") if isinstance(arguments, dict) else None
            state.specs[result["spec_id"]] = {
                "status": result.get("status"),
                "unverified": [str(u.get("requirement")) for u in result.get("unverified_requirements") or []][:12],
                "research": {"evidence_standard": research.get("evidence_standard"),
                             "hypothesis_id": (research.get("hypothesis") or {}).get("id"),
                             "followup_of": research.get("followup_of")} if isinstance(research, dict) else None,
                "governor": (result.get("governor") or {}).get("decision")}
        elif name in ("run_python_analysis", "get_analysis_result") and result.get("analysis_id") \
                and result.get("execution_status"):
            previous = state.analyses.get(result["analysis_id"], {})
            state.analyses[result["analysis_id"]] = {
                "analysis_id": result["analysis_id"], "spec_id": result.get("spec_id") or previous.get("spec_id"),
                "execution_status": result["execution_status"], "validation_status": result.get("validation_status"),
                "validation_level": result.get("validation_level"),
                "reason_codes": list(result.get("reason_codes") or [])[:10],
                "error_code": (result.get("error") or {}).get("code")}
            assessment = result.get("evidence_assessment")
            if isinstance(assessment, dict):
                state.evidence[result["analysis_id"]] = {
                    k: assessment.get(k) for k in ("claim_type", "decision", "evidence_level")} | {
                    "reporting_constraints": [str(c) for c in assessment.get("reporting_constraints") or []][:10]}
            state.warning_codes |= {str(w.get("code")) for w in result.get("warnings") or [] if isinstance(w, dict)}

    def _gate_findings(self, state: RunState) -> tuple[list[str], list[str]]:
        """(blocking findings, mandatory limitation lines) from the latest analysis of each spec."""
        latest: dict[str, dict[str, Any]] = {}
        for summary in state.analyses.values():
            latest[summary.get("spec_id") or summary["analysis_id"]] = summary
        blocking, lines = [], []
        for summary in latest.values():
            ident = summary["analysis_id"]
            reasons = ", ".join(summary["reason_codes"]) or "no reason recorded"
            execution, validation = summary["execution_status"], summary.get("validation_status")
            level = summary.get("validation_level") or "EXECUTION_ONLY"
            if execution in ("QUEUED", "RUNNING"):
                blocking.append(f"analysis {ident} had not finished")
                lines.append(f"Analysis {ident} had not finished, so no calculated result from it is available.")
            elif execution != "COMPLETED":
                blocking.append(f"analysis {ident} did not complete ({summary.get('error_code') or execution})")
                lines.append(f"Analysis {ident} did not complete ({summary.get('error_code') or execution}); no "
                             f"validated calculation result is available from it.")
            elif validation in ("FAILED", "INCOMPLETE"):
                blocking.append(f"analysis {ident} validation {validation} ({reasons})")
                lines.append(f"Analysis {ident}: execution COMPLETED but validation {validation} ({reasons}); its "
                             f"result is not a validated answer to the requested scope.")
            elif validation == "UNVERIFIED":
                lines.append(f"Analysis {ident}: validation UNVERIFIED (level {level}); its scope and values could "
                             f"not be checked independently.")
            elif level != "CALCULATION_VERIFIED":
                lines.append(f"Analysis {ident}: validation {validation} at level {level}; the calculation itself "
                             f"was not independently recalculated.")
            spec = state.specs.get(summary.get("spec_id") or "")
            if spec and spec["unverified"]:
                lines.append(f"Requirements not stated by the user in the spec of analysis {ident}: "
                             f"{', '.join(spec['unverified'])}.")
            evidence = state.evidence.get(ident)
            if evidence and evidence.get("claim_type") in RESEARCH_CLAIMS:
                lines.append(f"Analysis {ident} ({evidence['claim_type']}): evidence {evidence.get('decision')}, "
                             f"level {evidence.get('evidence_level')}.")
                lines.extend(c for c in evidence["reporting_constraints"] if c not in lines)
        if "CORPORATE_ACTIONS_NOT_ADJUSTED" in state.warning_codes and latest:
            lines.append("Prices are split-adjusted as fetched and not dividend-adjusted; returns that span a "
                         "corporate action can be distorted.")
        return blocking, lines

    @staticmethod
    def _routing_text(request: AgentRunRequest) -> str:
        """The user's question for the routing guard: the latest message, plus the previous user turn when the
        latest message answers a clarification question."""
        text = request.message
        history = list(request.history)
        if len(history) >= 2 and history[-1].role == "assistant" and history[-1].content.rstrip().endswith("?") \
                and history[-2].role == "user":
            text = history[-2].content + "\n" + text
        return text

    def _track_choices(self, state: RunState, name: str, arguments: Any, outcome: ToolOutcome) -> None:
        """S4 (K6): the filter, group and threshold values the model typed into code that ran, traced to their origin
        (the user's words, the values tool results returned, else the AI's own choice); then this result's values
        join what the data returned. Read before this result is added, so a list the code printed is not its own
        source."""
        if not outcome.ok or not isinstance(outcome.output.get("result"), dict):
            return
        result = outcome.output["result"]
        code = arguments.get("code") if isinstance(arguments, dict) else None
        if name in ("run_python", "run_research_code"):
            if result.get("status") != "OK" or not isinstance(code, str):
                return
            typed = ai_choices.typed_values(code)
            state.choice_numbers.extend(float(t.value) for t in typed if t.kind == "NUMBER")
            words = self._user_words(state) + "\n" + state.user_history
            for choice in ai_choices.classify(typed, words, state.seen_strings, state.seen_sets,
                                              state.context_numbers, state.web_strings, state.web_sets):
                if choice not in state.ai_choices and len(state.ai_choices) < ai_choices.MAX_CHOICES:
                    state.ai_choices.append(choice)
            return  # a run's printed text and its own outputs are not values the data supplied
        if name == "find_web_fact" and result.get("status"):
            state.web_facts.append(result)
            values = [v.get("value") for v in result.get("versions") or []] + [result.get("value")]
            # free text ("56.7% of the shares") is read like an answer's text, with its unit variants
            state.web_numbers.extend(value for text in values if text is not None
                                     for shown in parse_numbers(str(text)) for value, _ in shown.candidates)
            ai_choices.string_leaves(values, state.web_strings)
            ai_choices.string_sets(values, state.web_sets)
            return  # a web fact describes; its values are not values the data returned (P34)
        citable = [e for e in result.get("citable") or [] if isinstance(e, dict) and e.get("label") in OUTSIDE_LABELS]
        if citable:
            self._track_outside(state, arguments, result, citable)
            return  # item 12: values from outside the database describe; they are not values the data returned
        ai_choices.string_leaves(result, state.seen_strings)
        ai_choices.string_sets(result, state.seen_sets)

    @staticmethod
    def _track_sources(state: RunState, name: str, arguments: Any, outcome: ToolOutcome) -> None:
        """Collect the numbers an answer may cite, from tool results the application received."""
        if not outcome.ok:
            return
        result = outcome.output.get("result")
        if not isinstance(result, dict):
            return
        if name == "lookup_fact" and result.get("decision") == "FACTS_READY":
            for fact in result.get("facts") or []:
                kind = "DATABASE_AGGREGATE" if fact.get("kind") == "AGGREGATE" else "FACT"
                state.facts.append({"kind": kind, "aggregation": fact.get("aggregation"),
                                    "values": numbers_in(fact.get("value"))})
        elif name == "lookup_reference" and result.get("status") == "ROWS_READY":
            # P34: values of a governed reference table, read by the Governor
            state.facts.append({"kind": "FACT", "aggregation": None, "values": numbers_in(result.get("rows"))})
        elif name == "query_metric" and result.get("status") == "OK":
            # D5: computed by the database from governed rows in one summary, like a lookup aggregate
            for period in result.get("periods") or []:
                state.facts.append({"kind": "DATABASE_AGGREGATE",
                                    "aggregation": (result.get("metric") or {}).get("time_function"),
                                    "values": numbers_in(period.get("rows"))})
        elif name == "request_data" and result.get("decision") == "DATASET_READY":
            state.context_numbers.extend(numbers_in(result.get("dataset"), ints_only=True))
        elif name == "prepare_analysis_data" and result.get("status") == "READY":
            state.context_numbers.extend(numbers_in(result.get("inputs"), ints_only=True))
        elif name == "get_dataset_manifest" and result.get("status") == "AVAILABLE":
            state.context_numbers.extend(numbers_in(result, ints_only=True))
        elif name == "create_analysis_spec" and result.get("spec_id"):
            state.context_numbers.extend(numbers_in(arguments))
            for key in ("resolved_period", "required_input", "output_contract"):
                state.context_numbers.extend(numbers_in(result.get(key)))
        elif name in ("run_python_analysis", "get_analysis_result") and result.get("analysis_id") \
                and result.get("execution_status"):
            label = analysis_label(result.get("execution_status"), result.get("validation_status"),
                                   result.get("validation_level"))
            # the validator's own evidence statistics (event counts, baseline, intervals) are sources too
            statistics = (result.get("evidence_assessment") or {}).get("statistics")
            state.analysis_values[result["analysis_id"]] = {
                "label": label, "values": numbers_in(result.get("outputs")) + numbers_in(statistics) if label else []}
            evidence = [{k: v for k, v in item.items() if k not in ("examples", "missing_examples",
                                                                     "unexpected_examples", "diagnosis")}
                        for item in result.get("validation_evidence") or [] if isinstance(item, dict)]
            for part in (result.get("expected_scope"), result.get("actual_scope"), evidence):
                state.context_numbers.extend(numbers_in(part, ints_only=True))

    @staticmethod
    def _track_pit_refusals(state: RunState, result: dict[str, Any]) -> None:
        for issue in result.get("issues") or []:
            if isinstance(issue, dict) and issue.get("code") == "POINT_IN_TIME_UNAVAILABLE":
                detail = str(issue.get("rejected_value") or issue.get("field_path") or "")[:200]
                if detail not in state.pit_refusals:
                    state.pit_refusals.append(detail)

    @staticmethod
    def _track_dataneed(state: RunState, name: str, arguments: Any, outcome: ToolOutcome) -> None:
        """DataNeed flow: needs, sessions, completions, and the numbers an answer may cite (released outputs)."""
        if not outcome.ok:
            return
        result = outcome.output.get("result")
        if not isinstance(result, dict):
            return
        if name == "submit_data_need_spec":
            AgentOrchestrator._track_pit_refusals(state, result)
        if name == "submit_data_need_spec" and result.get("need_id"):
            records.add_need(state.data_record, state.request_id, result,
                             (arguments or {}).get("mode") if isinstance(arguments, dict) else None)
            state.needs[result["need_id"]] = {
                "mode": (arguments or {}).get("mode") if isinstance(arguments, dict) else None,
                "governance": result.get("research_governance"),
                "hypothesis_id": ((arguments or {}).get("research_governance") or {}).get("hypothesis_id")
                if isinstance(arguments, dict) else None}
            state.context_numbers.extend(numbers_in(arguments))
        elif name == "prepare_data_bundle" and result.get("status") == "READY":
            if result.get("reused"):
                state.reuse["bundles_reused"] = state.reuse.get("bundles_reused", 0) + 1
            state.context_numbers.extend(numbers_in(result.get("datasets"), ints_only=True))
            state.warning_codes |= {str(w.get("code")) for w in result.get("relationship_warnings") or []
                                    if isinstance(w, dict)}
        elif name == "open_analysis_session" and result.get("session_id"):
            state.sessions[result["session_id"]] = {"need_id": result.get("need_id"),
                                                    "bundle_id": result.get("bundle_id"), "executions": []}
            if result.get("reused_session"):
                state.reuse["sessions_reused"] = state.reuse.get("sessions_reused", 0) + 1
        elif name == "run_python" and result.get("execution_id"):
            state.execution_ids.append(str(result["execution_id"]))
            session = state.sessions.setdefault(result.get("session_id") or "", {"executions": []})
            session["executions"].append(result.get("status"))
            code = (arguments or {}).get("code") if isinstance(arguments, dict) else None
            if result.get("status") == "OK" and isinstance(code, str):
                state.code_numbers.extend(code_numbers(code))
        elif name == "get_session_output" and result.get("released"):
            if result.get("read_mode") == "READ_RELEASED" and isinstance(result.get("origin"), dict):
                # released by an earlier completion (an earlier message, or an earlier epoch of this session)
                state.inherited[str(result.get("output_id"))] = {"name": result.get("name"), **result["origin"]}
                if result["origin"].get("calculation_verified"):
                    state.verified_outputs.add(str(result.get("output_id")))
            record = state.analysis_values.setdefault(f"released:{result.get('output_id')}", {
                "label": "CALCULATION_VERIFIED" if str(result.get("output_id")) in state.verified_outputs
                else "DATA_COVERAGE_VERIFIED", "values": []})
            record["values"].extend(released_numbers(result.get("rows")) + released_numbers(result.get("content")))
        elif name == "complete_analysis" and result.get("final_status"):
            session_id = result.get("session_id") or ((arguments or {}).get("session_id") if isinstance(
                arguments, dict) else "")
            # a session can complete more than once in a run (conversation reuse: code run after a passed completion
            # starts a new epoch), so the released values of every completion stay sources
            earlier = (state.completions.get(session_id) or {}).get("completion_ids") or []
            state.completions[session_id] = {"status": result.get("status"), "final": result["final_status"],
                                             "coverage": (result.get("coverage") or {}).get("coverage_status"),
                                             "need_id": result.get("need_id"), "completion_id":
                                             result.get("completion_id"), "next_action": result.get("next_action"),
                                             "completion_ids": [*earlier, result.get("completion_id") or session_id]}
            state.final_status = {"completion_id": result.get("completion_id"), "session_id": session_id,
                                  "need_id": result.get("need_id"), "status": result.get("status"),
                                  **result["final_status"]}
            state.final_statuses.append(state.final_status)
            if result.get("status") == "COMPLETED":
                verified = {str(i) for i in result["final_status"].get("verified_output_ids") or []}
                state.verified_outputs |= verified
                contents = [c for c in result.get("released_contents") or [] if isinstance(c, dict)]
                state.analysis_values[f"completion:{result.get('completion_id') or session_id}"] = {
                    "label": "DATA_COVERAGE_VERIFIED",
                    "values": released_numbers([c for c in contents if str(c.get("output_id")) not in verified])}
                if verified:
                    # G2: the event-study tables the sandbox recomputed from their declaration
                    state.analysis_values[f"verified:{result.get('completion_id') or session_id}"] = {
                        "label": "CALCULATION_VERIFIED",
                        "values": released_numbers([c for c in contents if str(c.get("output_id")) in verified])}
                findings = result["final_status"].get("research_findings") or []
                if findings:  # only a sandbox with research findings v1 sends them
                    values = numbers_in(findings)
                    # a difference is often stated as a size with a direction word ("lower by 0.6"): its magnitude
                    # is the same governed figure
                    values += [abs(v) for v in values if v < 0]
                    state.analysis_values[f"findings:{result.get('completion_id') or session_id}"] = {
                        "label": "DATA_COVERAGE_VERIFIED", "values": values}
                    overlap = insample.overlaps(insample.analysis_ranges(state.data_record, state.request_id),
                                                insample.research_ranges_v1(state.data_record, state.request_id))
                    overlap += insample.carried(result["final_status"].get("carried_inputs") or [],
                                                state.data_record)
                    for finding in findings:
                        state.research_findings[str(finding.get("hypothesis_id"))] = finding
                        if overlap:
                            state.in_sample[str(finding.get("hypothesis_id"))] = overlap
                        # E1: kept for later turns of the conversation (cited as finding.<hypothesis_id>)
                        records.add_finding(state.data_record, state.request_id, kind="HYPOTHESIS",
                                            finding_id=str(finding.get("hypothesis_id")),
                                            finding={**finding, **({"in_sample": overlap} if overlap else {})},
                                            recorded_at=_utc_now())
                for study in result["final_status"].get("event_studies") or []:
                    if isinstance(study, dict) and study.get("status") == "PASS" and study.get("name"):
                        # G2: the recomputed study, its figures cited from its tables (out.oN)
                        records.add_finding(state.data_record, state.request_id, kind="EVENT_STUDY",
                                            finding_id=str(study["name"]), recorded_at=_utc_now(), finding={
                                                "status": "PASS", "validation_level": "FORMULA_AND_STATISTICS_VERIFIED",
                                                "summary_output_id": study.get("summary_output_id"),
                                                "events_output_id": study.get("events_output_id")})
                state.context_numbers.extend(numbers_in(result.get("coverage"), ints_only=True))

    def _dataneed_findings(self, state: RunState) -> tuple[list[str], list[str]]:
        """(blocking findings, mandatory limitation lines) of the DataNeed flow."""
        blocking, lines = [], []
        for session_id, session in state.sessions.items():
            completion = state.completions.get(session_id)
            if session.get("superseded"):
                continue  # replaced by another session of this run (S08); it released nothing
            if completion is None:
                if session.get("executions"):
                    blocking.append(f"analysis session {session_id} was not completed with complete_analysis")
                    lines.append(f"Analysis session {session_id} was not completed, so none of its outputs were "
                                 "released.")
            elif completion["status"] != "COMPLETED":
                final = completion["final"]
                blocking.append(f"analysis session {session_id} is INCOMPLETE (data_coverage "
                                f"{final.get('data_coverage')}, sandbox_execution {final.get('sandbox_execution')})")
                lines.append(f"Analysis session {session_id}: data coverage {final.get('data_coverage')}, sandbox "
                             f"execution {final.get('sandbox_execution')}; its outputs were not released.")
        completed = [c for c in state.completions.values() if c["status"] == "COMPLETED"]
        if completed:
            studies = [s for c in completed for s in c["final"].get("event_studies") or [] if isinstance(s, dict)]
            passed = sorted({str(s.get("name")) for s in studies if s.get("status") == "PASS"})
            if passed:
                # G2: only the event-study tables were recomputed; every other calculation was not
                lines.append(f"Data coverage was verified against the approved DataNeedSpec. The event studies "
                             f"{', '.join(passed)} were recomputed independently by the backend from their "
                             "declaration and matched (CALCULATION_VERIFIED); the other calculations were not "
                             "independently recalculated.")
            else:
                lines.append("Data coverage was verified against the approved DataNeedSpec; the calculations "
                             "themselves were not independently recalculated by the backend (calculation_validation "
                             "NOT_PERFORMED).")
            invalid = sorted({f"{s.get('name')} ({s.get('reason')})" for s in studies if s.get("status") == "INVALID"})
            if invalid:
                lines.append(f"Event studies the backend could not recompute: {', '.join(invalid)}; their tables are "
                             "not independently verified.")
            codes = sorted({code for c in completed for code in c["final"].get("warnings") or []})
            lines.extend(WARNING_LINES[code] for code in codes if code in WARNING_LINES)
            if any(c["final"].get("derived_frequency") for c in completed):
                lines.append(DERIVED_FREQUENCY_LINE)
            if state.pit_refusals and any(c["final"].get("time_basis") != "POINT_IN_TIME" for c in completed):
                # IP1 Stage D: a point-in-time request was refused and the answer rests on descriptive data
                lines.append(PIT_FALLBACK_LINE.format(detail="; ".join(state.pit_refusals[:3])))
            if any((state.needs.get(c.get("need_id") or "") or {}).get("mode") == "RESEARCH" for c in completed):
                lines.append("Research results describe a historical pattern only; they are not evidence of a cause "
                             "or a prediction.")
        if state.inherited:
            for output_id, origin in state.inherited.items():
                lines.append(f"Figures from {origin.get('name') or output_id} were computed in an earlier message "
                             f"(completion {origin.get('completion_id')}, {origin.get('completed_at')}) and were not "
                             "recomputed in this message.")
            if not completed:
                lines.append("Data coverage was verified when those results were computed; the calculations were "
                             "not independently recalculated by the backend (calculation_validation NOT_PERFORMED).")
            codes = sorted({code for origin in state.inherited.values() for code in origin.get("warnings") or []})
            lines.extend(line for line in (WARNING_LINES[code] for code in codes if code in WARNING_LINES)
                         if line not in lines)
        if state.in_sample:
            lines.append(insample.LINE.format(ids=", ".join(sorted(state.in_sample)),
                                              detail=insample.details(state.in_sample)))
        executor = self._executor(state)
        if executor is not None and executor.research_run_id is not None:
            run = executor.result
            if run is None:
                blocking.append("the multi-angle research run was not completed with complete_research_run")
                lines.append("The multi-angle research run was not completed, so none of its findings were released.")
            else:
                if run.get("status") != "COMPLETED":
                    blocking.append(f"the multi-angle research run is {run.get('status')} (angles without a finding: "
                                    f"{', '.join(run.get('missing_angle_ids') or []) or 'none'})")
                lines.extend(self._research_run_lines(run))
        return blocking, lines

    @staticmethod
    def _research_run_lines(run: dict[str, Any]) -> list[str]:
        counts = run.get("angle_completion") or {}
        findings = run.get("research_findings") or []
        lines = [f"Multi-angle research: {counts.get('planned')} angles planned, {counts.get('validated')} with a "
                 f"validated finding, {counts.get('invalid')} invalid, {counts.get('not_run')} not run; calculation "
                 f"validation {run.get('calculation_validation')} (the weakest level of the findings relied on)."]
        for status, label in (("INVALID", "invalid"), ("NOT_RUN", "not run")):
            angles = [f"{f.get('angle_id')} ({f.get('status_reason')})" for f in findings if f.get("status") == status]
            if angles:
                lines.append(f"Angles {label}: {', '.join(angles)}.")
        if run.get("calculation_validation") not in VERIFIED_LEVELS:
            lines.append("The backend did not recompute the research statistics of the findings relied on "
                         "(EXECUTION_ONLY or NOT_PERFORMED).")
        lines.append("Research results describe a historical pattern only; they are not evidence of a cause or a "
                     "prediction.")
        return lines

    def _row_fetcher(self, state: RunState, session_id: str | None, output_id: str) -> Any:
        # D2: an output of an earlier answer is read from the conversation's store when the sandbox lost it, so a
        # reference to it renders without its session
        if self.row_reader is None or not (session_id or self.result_store is not None):
            return None

        def fetch(offset: int, limit: int) -> tuple[list[Any], int | None]:
            body = self.row_reader(session_id, output_id, state.request_id, offset, limit)
            if not body.get("released") or not isinstance(body.get("rows"), list):
                return [], body.get("row_count")
            units = (body.get("meta") or {}).get("units") if isinstance(body.get("meta"), dict) else None
            if units and ("out", output_id) not in state.ref_sources.units:
                # P23: a table listed without its content learns its declared units with its first page
                state.ref_sources.units[("out", output_id)] = {str(k): v for k, v in units.items() if v in UNITS}
            return body["rows"], body.get("row_count")
        return fetch

    @staticmethod
    def _track_outside(state: RunState, arguments: Any, result: dict[str, Any], citable: list[dict[str, Any]]) -> None:
        """Item 12: the items of a citable envelope from outside the database. Their numbers (a figure's value and the
        number written in its source; for a text, its numbers except years) may be shown as context and are refused
        as inputs of a calculation (WEB_NUMBER_IN_CALCULATION); their texts and lists are recorded like a web fact's,
        so a code filter that uses them is named as web-sourced."""
        values: list[Any] = []
        for entry in citable:
            value = entry.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                state.web_numbers.append(float(value))
            texts = [entry.get("value_as_written")] if entry.get("value_as_written") else []
            if isinstance(value, str):
                texts.append(value)
            for text in texts:
                # as written ("US$264,70 miliar": 264.7e9) and without its scale and currency words (264.7)
                for variant in (str(text), re.sub(r"[^\W\d_]+|[$€£¥]", " ", str(text))):
                    state.web_numbers.extend(v for shown in parse_numbers(variant) for v, _ in shown.candidates
                                             if not (float(v).is_integer() and 1900 <= v <= 2100))
            values.append(entry.get("members") if isinstance(entry.get("members"), list) else value)
        ai_choices.string_leaves(values, state.web_strings)
        ai_choices.string_sets(values, state.web_sets)
        state.web_research.append({
            "need": str((arguments or {}).get("need") or "")[:200] if isinstance(arguments, dict) else "",
            "status": result.get("status"), "items": len(citable),
            "domains": sorted({str((e.get("source") or {}).get("domain")) for e in citable
                               if (e.get("source") or {}).get("domain")})})

    def _track_references(self, state: RunState, name: str, outcome: ToolOutcome,
                          arguments: dict[str, Any] | None = None) -> None:
        """P11: register what the final response may reference, and show each referable object its "ref".
        M44 (2026-10-01): a table's rows are kept by their position in the complete table; a page read later adds
        rows and never replaces the ones read before, and each row carries `_row`, its position in the table."""
        if not outcome.ok:
            return
        result = outcome.output.get("result")
        if not isinstance(result, dict):
            return
        sources = state.ref_sources
        session_id = result.get("session_id") or (arguments or {}).get("session_id")
        refs: list[str] = []  # 10.1: the objects registered by this result, for its address menu

        def output(entry: Any, offset: int = 0) -> None:
            if not (isinstance(entry, dict) and entry.get("output_id")):
                return
            output_id = str(entry["output_id"])
            owner = entry.get("session_id") or session_id
            meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
            if not isinstance(entry.get("units"), dict) and isinstance(meta.get("units"), dict):
                entry["units"] = meta["units"]  # P23: get_session_output carries the declared units in its meta
            registered = entry
            listed_only = "rows" not in entry and "content" not in entry  # A: released, its content not shown
            if isinstance(entry.get("rows"), list) or (listed_only and entry.get("type") in TABULAR_OUTPUTS):
                table = state.ref_tables.get(output_id)
                if table is None:
                    table = TableRows(entry.get("row_count"), fetch=self._row_fetcher(state, owner, output_id))
                    state.ref_tables[output_id] = table
                if isinstance(entry.get("rows"), list):
                    table.add(offset, entry["rows"], entry.get("row_count"))
                registered = {**{k: v for k, v in entry.items() if k != "rows"}, "rows": table}
            if listed_only:
                entry["content_shown"] = False
            sources.add("out", output_id, registered, "CALCULATION_VERIFIED" if output_id in state.verified_outputs
                        else "DATA_COVERAGE_VERIFIED")
            # P18 (2026-10-01): the model writes a short alias, not out_ + 24 hex characters after the out. namespace
            alias = state.ref_aliases.get(output_id)
            if alias is None:
                alias = state.ref_aliases[output_id] = f"o{state.ref_next}"
                state.ref_next += 1
            sources.alias("out", alias, output_id)
            entry["ref"] = f"out.{alias}"
            refs.append(f"out.{alias}")
            rows = entry.get("rows") if isinstance(entry.get("rows"), list) else []
            columns = entry.get("columns") if isinstance(entry.get("columns"), list) else \
                [str(k) for k in (rows[0] if rows and isinstance(rows[0], dict) else {}) if k != "_row"]
            columns = [str(c.get("name")) if isinstance(c, dict) else str(c) for c in columns]
            definition = entry.get("definition") if isinstance(entry.get("definition"), dict) \
                else meta.get("definition") if isinstance(meta.get("definition"), dict) else None
            records.add_output(state.data_record, state.request_id, alias=alias, output_id=output_id,
                               session_id=owner, name=entry.get("name"), columns=columns,
                               row_count=entry.get("row_count"),
                               label="CALCULATION_VERIFIED" if output_id in state.verified_outputs
                               else "DATA_COVERAGE_VERIFIED", kind=entry.get("type"), definition=definition,
                               lineage=entry.get("lineage") if isinstance(entry.get("lineage"), dict) else None)

        def released(result: dict[str, Any]) -> None:
            """A (user decision 2026-10-02): every released output gets its ref and its place in the data record, not
            only the ones whose content the result previews (the first tables, JSON and text); charts and the rest
            are listed with content_shown false and a note, and a table's rows are read on demand."""
            lineage = {str(e.get("output_id")): e for e in result.get("released_outputs") or [] if isinstance(e, dict)}
            for entry in result.get("released_contents") or []:
                if isinstance(entry, dict) and "lineage" not in entry and isinstance(
                        lineage.get(str(entry.get("output_id")), {}).get("lineage"), dict):
                    entry["lineage"] = lineage[str(entry["output_id"])]["lineage"]  # R-STORE: its data date
                output(entry)
            shown = {str(c.get("output_id")) for c in result.get("released_contents") or [] if isinstance(c, dict)}
            hidden = [e for e in result.get("released_outputs") or []
                      if isinstance(e, dict) and e.get("output_id") and str(e["output_id"]) not in shown]
            for entry in hidden:
                output(entry)
            if hidden:
                result["contents_not_shown_note"] = CONTENTS_NOT_SHOWN_NOTE

        if name == "complete_research_run":
            for finding in result.get("research_findings") or []:
                if isinstance(finding, dict) and finding.get("angle_id"):
                    sources.add("finding", str(finding["angle_id"]), finding, "DATA_COVERAGE_VERIFIED")
                    finding["ref"] = f"finding.{finding['angle_id']}"
                    refs.append(finding["ref"])
            released(result)
        elif name == "complete_analysis" and result.get("status") == "COMPLETED":
            state.verified_outputs |= {str(i) for i in (result.get("final_status") or {}).get("verified_output_ids")
                                       or []}
            released(result)
            for finding in (result.get("final_status") or {}).get("research_findings") or []:
                if isinstance(finding, dict) and finding.get("hypothesis_id"):
                    sources.add("finding", str(finding["hypothesis_id"]), finding, "DATA_COVERAGE_VERIFIED")
                    finding["ref"] = f"finding.{finding['hypothesis_id']}"
                    refs.insert(0, finding["ref"])
                    self._summary_fallback(sources, str(finding["hypothesis_id"]))
        elif name == "get_session_output" and result.get("released"):
            output(result, int(result.get("offset") or 0))
        elif name == "lookup_fact" and result.get("decision") == "FACTS_READY":
            for fact in result.get("facts") or []:
                if isinstance(fact, dict):
                    state.ref_facts += 1
                    kind = "DATABASE_AGGREGATE" if fact.get("kind") == "AGGREGATE" else "FACT"
                    sources.add("fact", str(state.ref_facts), fact.get("value"), kind)
                    fact["ref"] = f"fact.{state.ref_facts}"
                    refs.append(fact["ref"])
        elif name == "query_metric" and result.get("status") == "OK":
            state.ref_metrics += 1
            key = f"m{state.ref_metrics}"
            sources.add("metric", key, {"periods": result.get("periods") or []}, "DATABASE_AGGREGATE")
            result["ref"] = f"metric.{key}.periods[<i>].rows[<dimension>=<value>].<column>"
            refs.append(f"metric.{key}")
        elif name == "lookup_reference" and result.get("status") == "ROWS_READY":
            # 10.5d (plan 2026-10-05 item 10): the number of rows a reference read matched is a sourced count
            state.ref_references += 1
            key = f"r{state.ref_references}"
            sources.add("reference", key, {"matched": result.get("matched"), "rows": result.get("rows") or []},
                        "FACT")
            result["ref"] = f"reference.{key}"
            refs.append(f"reference.{key}.matched")
        elif name in ("run_python_analysis", "get_analysis_result") and result.get("analysis_id"):
            label = analysis_label(result.get("execution_status"), result.get("validation_status"),
                                   result.get("validation_level"))
            if label:
                sources.add("analysis", str(result["analysis_id"]), result.get("outputs"), label)
                result["ref"] = f"analysis.{result['analysis_id']}.<output path>"
                refs.append(f"analysis.{result['analysis_id']}")
        for entry in result.get("citable") or []:
            # item 12: any result with a citable envelope; an item's label names its namespace (a web fact: web)
            namespace = OUTSIDE_NAMESPACES.get(entry.get("label")) if isinstance(entry, dict) else None
            if namespace is None or not entry.get("id"):
                continue
            source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
            # a percent figure declares its unit, so a percent format shows 2,92 as 2,92% (not 292%)
            units = {"value": "PERCENT"} if entry.get("unit_code") == "PERCENT" else None
            sources.add(namespace, str(entry["id"]), entry, entry["label"], units=units, origin=source.get("domain"))
            entry["ref"] = f"{namespace}.{entry['id']}"  # its own ref is its address: no menu line
        if getattr(self, "address_menu", False) and refs:
            menu = [line for ref in dict.fromkeys(refs) for line in sources.menu(ref)]
            if len(menu) > ADDRESS_MENU_MAX:  # never cut silently: the pattern lines cover the rows not listed
                menu = menu[:ADDRESS_MENU_MAX - 1] + [
                    f"… {len(menu) - ADDRESS_MENU_MAX + 1} more addresses not listed; write them with the pattern lines"]
            if menu:
                result["addresses"] = menu
                result["addresses_note"] = ADDRESS_MENU_NOTE

    @staticmethod
    def _cited_result_values(state: RunState) -> list[float]:
        """10.6: the values of this conversation's results that the plan's text cites as value references, only when
        the conversation router read the newest message as building on the latest result."""
        if current_turn_referent.get() != "NEWEST_RESULT":
            return []
        return [r.value for r in state.ref_values if r.label in LABEL_ORDER]

    @staticmethod
    def _log_cited_thresholds(state: RunState, final: FinalResponse, stated: list[float], cited: list[float]) -> None:
        """10.6: record a success threshold or minimum effect taken from a cited result rather than the user's words."""
        if not cited:
            return
        items = getattr(final.research_plan, "experiments", None) or getattr(final.research_plan, "angles", None) or []
        values = [getattr(getattr(i, "success_rule", None), "value", None) for i in items] \
            + [getattr(i, "min_effect", None) for i in items]

        def matches(value: float, pool: list[float]) -> bool:
            return any(abs(n - value) < 1e-9 or abs(n * 100 - value) < 1e-9 or abs(n / 100 - value) < 1e-9
                       for n in pool)

        taken = [v for v in values if v is not None and not matches(v, stated) and cited_match(v, cited, magnitude=True)]
        if taken:
            log_event("plan_threshold_from_result", request_id=state.request_id, values=taken[:10])

    @staticmethod
    def _reference_suggestions(state: RunState, failing: list[str]) -> str:
        """10.3 (plan 2026-10-05 item 10): for each failing reference, the addresses of this run that end with the same
        field name (finding.x.groups.CONDITION.median -> out.o2.content.groups.CONDITION.median), as a suggestion."""
        sources = state.ref_sources
        shown = {(namespace, key): alias for namespace, aliases in sources.aliases.items()
                 for alias, key in aliases.items()}
        menu = [address for namespace, keys in sources.objects.items()
                for key in keys for line in sources.menu(f"{namespace}.{shown.get((namespace, key), key)}")
                if (address := menu_address(line)) is not None]
        lines = []
        for expression in failing[:8]:
            parts = expression.split("|", 1)[0].strip().split(".")
            name = parts[-1]

            def shared(address: str) -> int:  # how many trailing segments the address shares with the reference
                tail = address.split(".")
                return next((n for n in range(min(len(tail), len(parts)), 0, -1) if tail[-n:] == parts[-n:]), 0)

            found = sorted((a for a in menu if a.endswith("." + name) and a != ".".join(parts)),
                           key=lambda a: -shared(a))[:3]
            if found and name:
                lines.append(f"{expression} -> {' or '.join(found)}")
        return (" Addresses of this run with the same field: " + "; ".join(lines) + ".") if lines else ""

    @staticmethod
    def _summary_fallback(sources: ReferenceSources, hypothesis_id: str) -> None:
        """10.4 (plan 2026-10-05 item 10): a field the backend's hypothesis finding lacks (the median of each group)
        is read from the research_summary_<id> output of this run, when exactly one such output is registered."""
        summaries = [key for key, (value, _) in sources.objects.get("out", {}).items()
                     if isinstance(value, dict) and value.get("name") == f"research_summary_{hypothesis_id}"]
        if len(summaries) == 1:
            sources.fallback("finding", hypothesis_id, "out", summaries[0], ("content",))

    @staticmethod
    def _code_literal_hint(state: RunState, text: str | None, unsupported: list[str]) -> str:
        """P25: the refused numbers that are literals of the run's successful code, named in the refusal."""
        if not state.code_numbers or not unsupported:
            return ""
        index = SourceIndex()
        index.add(CONTEXT, state.code_numbers)
        in_code = set(unsupported) - set(check_answer(text or "", index).unsupported)
        literals = [n for n in unsupported if n in in_code]
        return CODE_LITERAL_HINT.format(numbers=", ".join(literals[:20])) if literals else ""

    def _source_index(self, state: RunState) -> SourceIndex:
        index = SourceIndex()
        for resolved in state.ref_values:  # P11: a value the backend filled in counts under its source's label
            index.add(resolved.label if resolved.label in LABEL_ORDER else CONTEXT, [resolved.value])
        static = self.system_prompt + "\n" + "\n".join(str(d.get("description", "")) for d in self.registry.definitions())
        index.add(CONTEXT, state.context_numbers + state.choice_numbers + state.web_numbers
                  + [value for shown in parse_numbers(static) for value, _ in shown.candidates])
        for fact in state.facts:
            index.add(fact["kind"], fact["values"])
        for record in state.analysis_values.values():
            if record["label"]:
                index.add(record["label"], record["values"])
        return index

    def _resolve_references(self, state: RunState, final: FinalResponse) -> tuple[FinalResponse, bool]:
        """P11: fill every value reference of an ANSWER or LIMITATION from this run's sources. The resolved values
        become provenance sources, so the gates run unchanged on the rendered text. A reference that does not resolve
        is refused for repair once per distinct set of failing references (at most MAX_REFERENCE_REPAIRS per run,
        P16). After that, a reference to a field the object does not have (or to an object) stays in the answer as
        [field] with a limitation line and the response keeps its type (M43, user decision 2026-09-30); any other
        unresolved reference is shown as [nilai tidak tersedia] with a limitation line, and the response also keeps
        its type (P14, user decision 2026-10-01)."""
        state.reference_annotated = False  # it describes this final only, not an earlier refused draft
        # 10.6: a plan's answer may cite an earlier result's value as its threshold; it is rendered (and its values
        # become sources) before the plan gate reads them (golden test ma-qa-20261006b threshold_from_result turn 2:
        # the cited value never reached the gate, and the plan was forced to a LIMITATION)
        if not self.value_references or final.response_type not in ("ANSWER", "LIMITATION",
                                                                     "RESEARCH_PLAN_CONFIRMATION"):
            return final, False
        # D6: the references the answer cites, listed as evidence (DIRUJUK) next to the checked claims
        state.referenced = list(dict.fromkeys(m.group("expr").strip() for m in REF_RE.finditer(final.answer or "")))
        state.typed_answer = REF_RE.sub(" ", final.answer or "")
        problems: list[str] = []
        failed: list[str] = []
        missing: list[tuple[str, str, str]] = []
        values: list[Resolved] = []
        count = 0

        def fill(text: str | None) -> str | None:
            nonlocal count
            if text is None:
                return None
            rendering = render(text, state.ref_sources)
            problems.extend(rendering.problems)
            failed.extend(rendering.failed)
            missing.extend(rendering.missing)
            values.extend(rendering.values)
            count += rendering.count
            if rendering.dropped_units:
                log_event("ai_reference_unit_repeated", request_id=state.request_id, units=rendering.dropped_units)
            if rendering.corrected_units:
                # P23: a figure shown by its data's unit rather than by the format the model wrote
                log_event("ai_reference_unit_corrected", request_id=state.request_id,
                          references=rendering.corrected_units[:20])
            if rendering.unknown_units:
                log_event("ai_reference_unit_unknown", request_id=state.request_id,
                          references=rendering.unknown_units[:20])
            return rendering.text

        update: dict[str, Any] = {"answer": fill(final.answer), "limitations": [fill(x) for x in final.limitations],
                                  "assumptions": [fill(x) for x in final.assumptions],
                                  "methodology": fill(final.methodology)}
        if final.research_findings:
            entries = []
            for entry in final.research_findings:
                parts = entry.interpretation
                filled = parts.model_copy(update={k: fill(getattr(parts, k)) for k in
                                                  ("answer", "evidence", "usefulness", "follow_up")})
                entries.append(entry.model_copy(update={"interpretation": filled}))
            update["research_findings"] = entries
        if state.ref_sources.redirected:
            log_event("ai_reference_redirected", request_id=state.request_id,
                      references=dict(list(state.ref_sources.redirected.items())[:20]))
            state.ref_sources.redirected.clear()
        if not count:
            return final, False
        state.references_used += count
        state.raw_final = final.model_dump(mode="json")
        rendered = final.model_copy(update=update)
        state.ref_values.extend(values)
        if not problems and not missing:
            return rendered, False
        detail = "; ".join(dict.fromkeys(problems + [message for _, _, message in missing]))[:1500]
        failing = sorted(set(failed) | {expression for expression, _, _ in missing})
        if getattr(self, "address_menu", False):
            detail += self._reference_suggestions(state, failing)
        kind = "REFERENCE:" + stable_hash(failing)[:12]
        spent = sum(1 for k in state.gate_kinds_rejected if k.startswith("REFERENCE"))
        self._gate_once(state, kind, REFERENCE_INSTRUCTION.format(problems=detail),
                        allowed=spent < MAX_REFERENCE_REPAIRS, outcome="ANNOTATED")
        lines = []
        if missing:
            lines.append(MISSING_FIELD_LINE.format(fields=", ".join(dict.fromkeys(name for _, name, _ in missing))))
        if problems:
            # P14 (user decision 2026-10-01): marked [nilai tidak tersedia], the answer keeps its type
            lines.append(UNRESOLVED_LINE)
        state.reference_annotated = True  # validation_gate ANNOTATED, set when this final passes the other gates
        return rendered.model_copy(update={"limitations": [*rendered.limitations, *lines]}), False

    def _finalize_findings(self, state: RunState, final: FinalResponse) -> FinalResponse:
        """Multi-Angle Research after a completed run: every LIMITATION carries the backend's per-angle findings (M39),
        and with value references every response carries all approved angles rendered from the backend (#15)."""
        self._log_answer_length(state, final)
        run = self._research_result(state)
        if run is None or not run.get("research_findings") or final.response_type not in ("ANSWER", "LIMITATION"):
            return final
        if self.value_references:
            return final.model_copy(update={"research_findings": self._rendered_findings(state, run, final)})
        if final.response_type == "LIMITATION" and final.research_findings is None:
            return final.model_copy(update={"research_findings": backend_findings(run)})
        return final

    @staticmethod
    def _log_answer_length(state: RunState, final: FinalResponse) -> None:
        """EXEC-P2 P2e: an answer longer than its target, or with a table longer than ANSWER_TABLE_ROWS rows, is logged
        (ai_answer_long); it is delivered as it is."""
        target, rows = current_answer_target.get(), answer_table_rows(final.answer or "")
        if len(final.answer or "") > target or rows > ANSWER_TABLE_ROWS:
            log_event("ai_answer_long", request_id=state.request_id, iteration=state.iterations,
                      response_type=final.response_type, chars=len(final.answer or ""), target_chars=target,
                      table_rows=rows, target_rows=ANSWER_TABLE_ROWS)

    def _rendered_findings(self, state: RunState, run: dict[str, Any],
                           final: FinalResponse) -> list[AngleFindingReport] | None:
        executor = self._executor(state)
        backend = {str(f.get("angle_id")): f for f in run.get("research_findings") or []
                   if isinstance(f, dict) and f.get("angle_id") and f.get("status") in ANGLE_STATUSES}
        order = [a.angle_id for a in executor.verified.plan.angles] if executor is not None else sorted(backend)
        given = {f.angle_id: f for f in final.research_findings or [] if isinstance(f, AngleFindingReport)} \
            if final.response_type == "ANSWER" else {}
        entries = []
        for angle_id in [*order, *sorted(set(backend) - set(order))][:6]:
            finding = backend.get(angle_id)
            if finding is None:
                continue
            summary = backend_summary(finding)
            parts = given[angle_id].interpretation if angle_id in given else None
            entries.append(AngleFindingReport(
                angle_id=angle_id[:40], status=summary.status, backend=summary,
                interpretation=AngleInterpretation(
                    answer=parts.answer if parts else NOT_INTERPRETED,
                    evidence=evidence_sentence(summary),
                    usefulness=parts.usefulness if parts else BACKEND_ONLY_USEFULNESS,
                    follow_up=parts.follow_up if parts else BACKEND_FINDING_FOLLOW_UP)))
        return entries or None

    def _gate_once(self, state: RunState, kind: str, message: str, allowed: bool = True,
                   outcome: str = "FORCED_LIMITATION", needs: frozenset[str] | None = None) -> None:
        """Reject a final answer once per kind of problem while the model can still repair it with tools. allowed:
        False when the kind's repair budget is spent (P16); outcome: what happens when no repair is possible; needs:
        the tools the repair calls (any one is enough). G23 A: a repair whose tools are not on this step's desk is
        never asked for; the gate's own outcome applies at once."""
        desk = self._desk(state)
        no_tools_this_turn = not desk
        missing_tool = bool(needs) and not (needs & desk)
        repairable = allowed and kind not in state.gate_kinds_rejected and not state.tools_locked \
            and not no_tools_this_turn and not missing_tool
        log_event("ai_final_gate", request_id=state.request_id, iteration=state.iterations, kind=kind,
                  outcome="REJECTED_FOR_REPAIR" if repairable else outcome,
                  reason=None if repairable else ("already_rejected" if kind in state.gate_kinds_rejected
                                                  else "repair_budget" if not allowed
                                                  else "tools_withdrawn" if state.tools_locked
                                                  else "no_tools" if no_tools_this_turn
                                                  else "tool_not_in_step"),
                  detail=message[:300])
        if self.audit_outbox is not None and (repairable or outcome == "FORCED_LIMITATION"):
            state.audit_trace.append(final_event("final.rejected" if repairable else "final.forced",
                                                 iteration=state.iterations, stage=kind, detail=message,
                                                 draft=state.current_raw, occurred_at=self.wall_clock()))
        if repairable:
            state.gate_kinds_rejected.add(kind)
            state.gate_rejections += 1
            raise GateRejection(message + GATE_ONCE_NOTE)

    def _desk(self, state: RunState) -> frozenset[str]:
        """G23 A: the tools this step can call — one source for the tools sent to the model, the gates and
        get_system_capabilities. Empty once the tools are withdrawn."""
        if state.tools_locked:
            return frozenset()
        return state.tool_filter if state.tool_filter is not None else frozenset(self.registry.names())

    def _consulted_labels(self, state: RunState) -> list[str]:
        labels = [record["label"] for record in state.analysis_values.values() if record["label"]]
        return labels + sorted({fact["kind"] for fact in state.facts})

    def _validation_gate(self, state: RunState, final: FinalResponse) -> FinalResponse:
        """Backend enforcement of the answer contract, in order:
        1. an ANSWER may not rest on an analysis that failed validation or did not complete;
        2. a request for a derived number (statistic, change, ranking) needs a usable analysis;
        3. every number in the answer must trace to a governed source of this run.
        Each check rejects once (tools stay available for a repair), then forces LIMITATION."""
        if final.response_type == "CLARIFICATION":
            state.evidence_label = None
            return final
        if final.response_type == "RESEARCH_PLAN_CONFIRMATION":
            return self._plan_gate(state, final)
        if state.plan_turn == "EXECUTE_APPROVED" and not state.research_attempted:
            # M19: an approved plan is executed, or the model names what blocks it after one reminder; either way an
            # approval without any attempt is not consumed
            self._gate_once(state, "PLAN_NOT_EXECUTED", RESEARCH_RUN_NOT_EXECUTED_INSTRUCTION
                            if self._executor(state) is not None else PLAN_NOT_EXECUTED_INSTRUCTION,
                            needs=RESEARCH_RUN_TOOLS if self._executor(state) is not None
                            else DATANEED_ANALYSIS_TOOLS | LEGACY_ANALYSIS_TOOLS)
            state.plan_unexecuted = True
            if PLAN_NOT_EXECUTED_LINE not in final.limitations:
                final = final.model_copy(update={"limitations": [*final.limitations, PLAN_NOT_EXECUTED_LINE]})
        executor = self._executor(state)
        if executor is not None and executor.research_run_id is not None and executor.result is None:
            # found live (golden run 2026-09-29): the model stopped after recording some angles and never completed
            # the run, so no finding existed even for the recorded angles
            self._gate_once(state, "RESEARCH_RUN_INCOMPLETE", RESEARCH_RUN_INCOMPLETE_INSTRUCTION,
                            needs=frozenset({"complete_research_run"}))
        if self.dataneed:
            return self._dataneed_gate(state, final)
        blocking, lines = self._gate_findings(state)
        if blocking and final.response_type == "ANSWER":
            self._gate_once(state, "ANALYSIS", VALIDATION_GATE_INSTRUCTION.format(findings="; ".join(blocking)),
                            needs=LEGACY_ANALYSIS_TOOLS)
            return self._forced(state, final, GATE_NOTICE, lines)

        families, plain_average = requested_statistics(state.user_text)
        usable = any(record["label"] for record in state.analysis_values.values())
        average_fact = any(f["kind"] == "DATABASE_AGGREGATE" and f["aggregation"] == "AVG" for f in state.facts)
        missing = sorted(families) if not usable else []
        if not missing and plain_average and not usable and not average_fact:
            missing = ["AVERAGE"]
        if missing and final.response_type == "ANSWER":
            names = ", ".join(missing)
            self._gate_once(state, "ROUTING", ROUTING_INSTRUCTION.format(families=names), needs=LEGACY_ANALYSIS_TOOLS)
            return self._forced(state, final, ROUTING_NOTICE.format(families=names),
                                [f"The request needs a validated analysis ({names}); no such analysis supports this "
                                 f"response."] + lines)

        provenance = check_answer(final.answer, self._source_index(state))
        state.number_provenance = {"checked": provenance.checked, "unsupported": provenance.unsupported[:50]}
        if provenance.unsupported:
            numbers = ", ".join(provenance.unsupported[:20])
            self._gate_once(state, "PROVENANCE", PROVENANCE_INSTRUCTION.format(numbers=numbers)
                            + self._code_literal_hint(state, final.answer, provenance.unsupported))
            return self._forced(state, final, PROVENANCE_NOTICE.format(numbers=numbers),
                                [f"Figures without a governed source in this run: {numbers}."] + lines)

        final = self._annotate_claims(state, final)  # P17: marked, never rejected
        annotated = state.reference_annotated or bool(state.claim_annotations) or state.definition_annotated

        missing_lines = [line for line in lines if line not in final.limitations]
        if state.analyses:
            state.validation_gate = "ANNOTATED" if missing_lines or annotated else "PASSED"
        elif annotated:
            state.validation_gate = "ANNOTATED"
        if final.response_type == "LIMITATION" and blocking:
            state.evidence_label = "NOT_VALIDATED"
        else:
            state.evidence_label = weakest(provenance.data_kinds) or weakest(self._consulted_labels(state))
        if not missing_lines:
            return final
        return final.model_copy(update={"limitations": [*final.limitations, *missing_lines]})

    def _dataneed_gate(self, state: RunState, final: FinalResponse) -> FinalResponse:
        """The answer contract of the DataNeed flow: completed analysis, routing and released-output provenance (each
        rejects once while tools are available, then forces LIMITATION); causal, predictive, proof and "verified
        calculation" claims are marked in italics with annotations, never rejected (P17, user decision 2026-10-01)."""
        blocking, lines = self._dataneed_findings(state)
        if blocking and final.response_type == "ANSWER":
            self._gate_once(state, "ANALYSIS", DATANEED_GATE_INSTRUCTION.format(findings="; ".join(blocking)),
                            needs=DATANEED_ANALYSIS_TOOLS)
            return self._forced(state, final, DATANEED_GATE_NOTICE, lines)
        families, plain_average = requested_statistics(state.user_text)
        # a released output of an earlier message read in this run is a completed analysis's result (reuse)
        run = self._research_result(state)
        usable = any(c["status"] == "COMPLETED" for c in state.completions.values()) or bool(state.inherited) \
            or (run is not None and run.get("status") == "COMPLETED") \
            or any(k.startswith("recorded_finding:") for k in state.analysis_values)  # E1: an earlier turn's finding
        average_fact = any(f["kind"] == "DATABASE_AGGREGATE" and f["aggregation"] == "AVG" for f in state.facts)
        missing = sorted(families) if not usable else []
        if not missing and plain_average and not usable and not average_fact:
            missing = ["AVERAGE"]
        if missing and final.response_type == "ANSWER":
            names = ", ".join(missing)
            self._gate_once(state, "ROUTING", DATANEED_ROUTING_INSTRUCTION.format(families=names),
                            needs=DATANEED_ANALYSIS_TOOLS)
            return self._forced(state, final, DATANEED_ROUTING_NOTICE.format(families=names),
                                [f"The request needs a completed analysis ({names}); none supports this "
                                 f"response."] + lines)
        provenance = check_answer(final.answer, self._source_index(state))
        state.number_provenance = {"checked": provenance.checked, "unsupported": provenance.unsupported[:50]}
        if provenance.unsupported:
            numbers = ", ".join(provenance.unsupported[:20])
            self._gate_once(state, "PROVENANCE", DATANEED_PROVENANCE_INSTRUCTION.format(
                numbers=numbers, lookup=", a lookup_fact result" if self.settings.ai_enable_lookup_fact else "")
                + self._code_literal_hint(state, final.answer, provenance.unsupported)
                + (REFERENCE_HINT if self.value_references else ""))
            return self._forced(state, final, DATANEED_PROVENANCE_NOTICE.format(numbers=numbers),
                                [f"Figures without a governed source in this run: {numbers}."] + lines)
        # Multi-Angle Research: the backend recomputed the statistics, so saying so at the returned level is allowed;
        # G2: so is an answer whose every number comes from event-study tables the backend recomputed
        # P17 (user decision 2026-10-01): unsupported claims are marked in italics with annotations, never rejected
        recomputed = bool(provenance.data_kinds) and weakest(provenance.data_kinds) == "CALCULATION_VERIFIED"
        final = self._annotate_claims(state, final, dataneed=True, verified_ok=recomputed or (
            run is not None and run.get("calculation_validation") in VERIFIED_LEVELS))
        final, problems = self._findings_problems(state, final)
        if problems:
            text = "; ".join(problems[:6])
            v2 = run is not None and final.response_type == "ANSWER"
            # found live (golden run 2, 2026-09-29): a multi-angle answer has four to six interpretations, and fixing
            # one problem often surfaced another, so it gets a second repair before the answer is forced to LIMITATION
            kind = "FINDINGS_2" if v2 and "FINDINGS" in state.gate_kinds_rejected else "FINDINGS"
            instruction = (ANGLE_NARRATIVE_INSTRUCTION if self.value_references else ANGLE_FINDINGS_INSTRUCTION) \
                if v2 else FINDINGS_INSTRUCTION
            self._gate_once(state, kind, instruction.format(
                problems=text))
            forced = self._forced(state, final, ANGLE_FINDINGS_NOTICE if v2 else FINDINGS_NOTICE,
                                  [f"Research findings problem: {text}."] + lines)
            if v2:
                # P09 (suite20 r08, 2026-09-29): four valid backend findings disappeared with the model's reading; the
                # LIMITATION keeps each angle's backend status, reason and effective sample, labelled as such
                forced = forced.model_copy(update={"research_findings": backend_findings(run)})
            return forced
        final = self._definition_claims(state, final)
        final = self._evidence_gate(state, final, provenance.data_kinds)
        missing_lines = [line for line in lines if line not in final.limitations]
        annotated = state.reference_annotated or bool(state.claim_annotations) or state.definition_annotated
        if state.sessions or state.completions or state.inherited or run is not None:
            state.validation_gate = "ANNOTATED" if missing_lines or annotated else "PASSED"
        elif annotated:
            state.validation_gate = "ANNOTATED"
        if final.response_type == "LIMITATION" and blocking:
            state.evidence_label = "NOT_VALIDATED"
        else:
            state.evidence_label = weakest(provenance.data_kinds)
        final = self._methodology_gate(state, final)
        if not missing_lines:
            return final
        return final.model_copy(update={"limitations": [*final.limitations, *missing_lines]})

    def _evidence_gate(self, state: RunState, final: FinalResponse, data_kinds: list[str]) -> FinalResponse:
        """EXEC-E (user decision 2026-10-06, replaces the D6 get_evidence gate): a figure the model typed from its own
        code is written by its address instead, asked once; a typed figure equal to exactly one released value counts
        as that value's reference (EXEC-R R3). Figures written as value references are read by the backend from their
        released tables (DIRUJUK); the backend's own figures are labelled."""
        if final.response_type != "ANSWER" or not self.value_references:
            return final
        extra: list[str] = []
        own_figures = [kind for kind in data_kinds if kind not in BACKEND_RECOMPUTED_KINDS]
        typed_text = state.typed_answer if state.typed_answer is not None else (final.answer or "")
        typed = [shown for shown, kind in typed_figures(typed_text, self._source_index(state))
                 if kind not in BACKEND_RECOMPUTED_KINDS]
        typed = self._auto_references(state, list(dict.fromkeys(typed)))
        if typed:
            numbers = ", ".join(typed[:12])
            self._gate_once(state, "TYPED_FIGURES", TYPED_FIGURES_INSTRUCTION.format(numbers=numbers))
            extra.append(TYPED_FIGURES_LINE.format(numbers=numbers))
        elif own_figures and state.referenced:
            extra.append(EVIDENCE_REFERENCED_LINE)
        elif data_kinds and not own_figures:
            extra.append(EVIDENCE_BACKEND_LINE)
        extra = [line for line in extra if line not in final.limitations]
        if extra:
            state.reference_annotated = True
            return final.model_copy(update={"limitations": [*final.limitations, *extra]})
        return final

    def _auto_references(self, state: RunState, typed: list[str]) -> list[str]:
        """EXEC-R R3: a typed figure equal, as written (rounded to its own decimals), to exactly one value this run can
        reference is that value's reference: it joins the answer's DIRUJUK list (`ai_reference_auto`). Two or more
        equal values, or none, leave it typed."""
        if not typed:
            return typed
        sources = state.ref_sources
        shown = {(namespace, key): alias for namespace, aliases in sources.aliases.items()
                 for alias, key in aliases.items()}
        leaves = [leaf for namespace, keys in sources.objects.items() for key in keys
                  for leaf in sources.leaves(f"{namespace}.{shown.get((namespace, key), key)}")]
        left: list[str] = []
        for text in typed:
            matches: set[str] = set()
            for number in parse_numbers(text):
                for value, _ in number.candidates:
                    matches |= {address for address, leaf in leaves if cited_match(value, [leaf], magnitude=False)}
            if len(matches) == 1:
                address = matches.pop()
                if address not in state.referenced:
                    state.referenced.append(address)
                log_event("ai_reference_auto", request_id=state.request_id, figure=text, address=address)
            else:
                left.append(text)
        return left

    def _evidence(self, state: RunState) -> list[dict[str, Any]] | None:
        """D6: the API's evidence[]: the answer's value references (DIRUJUK: where each cited figure comes from, read
        from its released table without a recomputation). The recomputed claims of get_evidence ended with EXEC-E."""
        items: list[dict[str, Any]] = []
        outputs = {o.get("ref"): o for o in (state.data_record or {}).get("outputs") or [] if isinstance(o, dict)}
        for expr in state.referenced[:20]:
            head = ".".join(expr.split(".")[:2])
            output = outputs.get(head)
            items.append({"kind": "REFERENCED", "status": "DIRUJUK", "claim": expr,
                          "source": {k: output.get(k) for k in ("ref", "output_id", "name", "label", "data_as_of")}
                          if output else {"ref": head}})
        return items or None

    def _definition_claims(self, state: RunState, final: FinalResponse) -> FinalResponse:
        """H1 (M63): "consistent with the previous answer" only when the definitions match. Rejected once for repair;
        if it stays, the answer keeps its figures and a limitation states the difference (never a silent claim)."""
        if final.response_type != "ANSWER":
            return final
        produced = [{"name": o.get("name"), "definition": o.get("definition")}
                    for o in (state.data_record or {}).get("outputs") or [] if o.get("request_id") == state.request_id]
        opened = [i for c in state.completions.values() for i in (c.get("final") or {}).get("carried_inputs") or []
                  if isinstance(i, dict)]
        found = definition_check.problems(final.answer, produced, opened)
        if not found:
            return final
        text = "; ".join(found[:4])
        self._gate_once(state, "DEFINITION", DEFINITION_CLAIM_INSTRUCTION.format(problems=text))
        line = DEFINITION_CLAIM_NOTICE.format(problems=text)
        state.definition_annotated = True
        return final.model_copy(update={"limitations": [*final.limitations, line]})

    def _findings_problems(self, state: RunState, final: FinalResponse) -> tuple[FinalResponse, list[str]]:
        """Research findings v1: an ANSWER resting on completed research experiments carries one research_findings
        entry per experiment with the backend verdict unchanged, a complete interpretation that names the sample
        (effective sample or smallest detectable effect), governed numbers only, and no verdict wording stronger than
        the backend's. Anything else carries research_findings null."""
        run = self._research_result(state)
        if run is not None and final.response_type == "ANSWER":
            return self._angle_findings_problems(state, final, run)
        if not self.research_findings or final.response_type != "ANSWER" or not state.research_findings:
            if final.research_findings is not None:
                final = final.model_copy(update={"research_findings": None})
            return final, []
        backend = state.research_findings
        given = {f.hypothesis_id: f for f in final.research_findings or []}
        problems = [f"no entry for {h}" for h in backend if h not in given]
        problems += [f"{h} is not a completed experiment" for h in given if h not in backend]
        index = self._source_index(state)
        verdicts = {finding.get("verdict") for finding in backend.values()}
        for hypothesis, item in given.items():
            finding = backend.get(hypothesis)
            if finding is None:
                continue
            if item.verdict != finding.get("verdict"):
                problems.append(f"{hypothesis}: verdict {item.verdict} differs from the backend's "
                                f"{finding.get('verdict')}")
            parts = item.interpretation
            text = " ".join([parts.answer, parts.evidence, parts.usefulness, parts.follow_up])
            problems += [f"{hypothesis}: {p}" for p in self._verdict_wording(text, {finding.get("verdict")})]
            sample = finding.get("sample") or {}
            anchors = [sample.get("effective"), sample.get("minimum_detectable_effect")]
            shown = [value for numbers in parse_numbers(parts.evidence) for value, _ in numbers.candidates]
            if not any(a is not None and any(abs(v - a) <= max(0.051 * abs(a), 0.006) for v in shown)
                       for a in anchors):
                problems.append(f"{hypothesis}: evidence names neither the effective sample nor the smallest "
                                f"detectable effect")
            unsupported = check_answer(text, index).unsupported
            if unsupported:
                problems.append(f"{hypothesis}: figures without a governed source: {', '.join(unsupported[:10])}")
        problems += [f"answer: {p}" for p in self._verdict_wording(final.answer, verdicts)]
        return final, problems

    def _angle_findings_problems(self, state: RunState, final: FinalResponse,
                                 run: dict[str, Any]) -> tuple[FinalResponse, list[str]]:
        """Multi-Angle Research: one entry per approved angle with the backend status unchanged, a complete
        interpretation naming the effective sample, governed numbers only, no status wording stronger than the
        backend's, and an agreement between angles only when the synthesis map allows one."""
        backend = {f.get("angle_id"): f for f in run.get("research_findings") or []}
        given_list = list(final.research_findings or [])
        problems = []
        # #15 (2026-09-30): with value references the backend renders every angle's status, evidence and sample, so
        # only the model's own reading is checked (verdict wording, agreement, figures)
        rendered = self.value_references
        if any(not isinstance(f, AngleFindingReport) for f in given_list):
            problems.append("each entry needs angle_id and interpretation" if rendered
                            else "each entry needs angle_id, status and interpretation")
        given = {f.angle_id: f for f in given_list if isinstance(f, AngleFindingReport)}
        if not rendered:
            problems += [f"no entry for {a}" for a in backend if a not in given]
        problems += [f"{a} is not an approved angle of this run" for a in given if a not in backend]
        index = self._source_index(state)
        for angle_id, item in given.items():
            finding = backend.get(angle_id)
            if finding is None:
                continue
            status = finding.get("status")
            if not rendered and item.status != status:
                problems.append(f"{angle_id}: status {item.status} differs from the backend's {status}")
            parts = item.interpretation
            text = " ".join(t for t in [parts.answer, None if rendered else parts.evidence, parts.usefulness,
                                        parts.follow_up] if t)
            allowed = self._supported_claims(finding)
            problems += [f"{angle_id}: {p}" for p in self._verdict_wording(text, allowed)]
            effective = (finding.get("sample") or {}).get("effective")
            if not rendered and status not in ("INVALID", "NOT_RUN") and isinstance(effective, (int, float)):
                shown = [value for numbers in parse_numbers(parts.evidence or "") for value, _ in numbers.candidates]
                if not any(abs(v - effective) <= max(0.051 * abs(effective), 0.006) for v in shown):
                    problems.append(f"{angle_id}: evidence does not name the effective sample")
            unsupported = check_answer(text, index).unsupported
            if unsupported:
                problems.append(f"{angle_id}: figures without a governed source: {', '.join(unsupported[:10])}")
        claims = set().union(*(self._supported_claims(f) for f in backend.values()))
        problems += [f"answer: {p}" for p in self._verdict_wording(final.answer, claims)]
        agreement = ((run.get("research_synthesis_map") or {}).get("agreement") or {}).get("allowed") is True
        if not agreement:
            for match in re.finditer(AGREEMENT_WORDING, final.answer or "", re.IGNORECASE):
                if not negated_in_clause(final.answer or "", match.start(), match.end()):
                    problems.append(f"answer: \"{match.group(0)}\" claims the angles agree, but the synthesis map "
                                    "allows no agreement (it needs supported angles of different method families)")
                    break
        return final, problems

    @staticmethod
    def _supported_claims(finding: dict[str, Any]) -> set[str]:
        """The supported wording an angle's status allows: SUPPORTED, and PARTIALLY_SUPPORTED for a reason other than
        the user's minimum effect, allow "supported"; below the user's minimum effect only "supported in part"."""
        status = finding.get("status")
        if status == "PARTIALLY_SUPPORTED" and finding.get("status_reason") == BELOW_USER_MINIMUM:
            return {"PARTIALLY_SUPPORTED"}
        return {"SUPPORTED"} if status in ("SUPPORTED", "PARTIALLY_SUPPORTED") else set()

    @staticmethod
    def _verdict_wording(text: str, verdicts: set[Any]) -> list[str]:
        problems = []
        text = text or ""
        # M26 option B: a qualified claim ("didukung sebagian") is allowed for a partly supported verdict; a plain
        # "didukung" only for a supported one
        partial = [m.span() for m in re.finditer(PARTIAL_WORDING, text, re.IGNORECASE)]
        for pattern, allowed, label in ((SUPPORTED_WORDING, "SUPPORTED", "supported"),
                                        (NO_EFFECT_WORDING, "NOT_SUPPORTED", "no effect")):
            if allowed in verdicts:
                continue
            for match in re.finditer(pattern, text, re.IGNORECASE):
                qualified = pattern is SUPPORTED_WORDING and any(start <= match.start() < end for start, end in partial)
                if qualified and "PARTIALLY_SUPPORTED" in verdicts:
                    continue
                # P10 (suite20b r08, 2026-09-29): "0 keluarga metode didukung" was read as a supported verdict; a
                # negation or a zero count anywhere in the phrase's clause (P09's clause rule) makes it no claim
                if not negated_or_zero(text, match.start(), match.end()):
                    hint = (" (the backend's verdict is partly supported: the effect is below the minimum effect the "
                            "user named; write it as supported in part, for example \"didukung sebagian\")"
                            if label == "supported" and "PARTIALLY_SUPPORTED" in verdicts else "")
                    problems.append(f"\"{match.group(0)}\" states a {label} verdict the backend did not give{hint}")
                    break
        return problems

    def _methodology_gate(self, state: RunState, final: FinalResponse) -> FinalResponse:
        """AI_ENABLE_METHODOLOGY: an answer resting on a completed analysis (or on released outputs of an earlier
        message) needs a methodology note, and its numbers must trace to the answer's sources, the approved plan, the
        DataNeedSpec or the code of a successful run_python call. Each problem rejects once; then the answer stands
        without the note and a limitation says why (the note never forces a LIMITATION on a sound answer)."""
        if not self.methodology:
            return final.model_copy(update={"methodology": None}) if final.methodology is not None else final
        analysed = any(c["status"] == "COMPLETED" for c in state.completions.values()) or bool(state.inherited)
        text = (final.methodology or "").strip()
        if not text:
            if not analysed:
                return final.model_copy(update={"methodology": None})
            self._gate_once(state, "METHODOLOGY", METHODOLOGY_INSTRUCTION)
            return final.model_copy(update={"methodology": None,
                                            "limitations": [*final.limitations, METHODOLOGY_MISSING_LINE]})
        index = self._source_index(state)
        index.add(CONTEXT, state.code_numbers)
        provenance = check_answer(text, index)
        state.methodology_provenance = {"checked": provenance.checked, "unsupported": provenance.unsupported[:50]}
        if provenance.unsupported:
            numbers = ", ".join(provenance.unsupported[:20])
            self._gate_once(state, "METHODOLOGY_PROVENANCE", METHODOLOGY_PROVENANCE_INSTRUCTION.format(numbers=numbers))
            return final.model_copy(update={"methodology": None, "limitations": [
                *final.limitations, METHODOLOGY_WITHHELD_LINE.format(numbers=numbers)]})
        return final.model_copy(update={"methodology": text})

    def _plan_gate(self, state: RunState, final: FinalResponse) -> FinalResponse:
        """A Research Plan uses no data: its answer may cite only the plan's own numbers, the user's messages and
        released outputs of this run. Hypotheses are phrased as questions to test, so the claim check does not apply;
        the plan carries no evidence label."""
        assert final.research_plan is not None
        is_v2 = isinstance(final.research_plan, ResearchPlanV2)
        if not self._plan_form_runs(is_v2, presenting=True, plan=final.research_plan):
            self._gate_once(state, "PLAN_VERSION", PLAN_VERSION_INSTRUCTION[self.multi_angle] + (
                PLAN_VERSION_SUCCESS_RULE_LINE if self.multi_angle and self.hypothesis_plans else ""))
            return self._forced(state, final, PLAN_VERSION_NOTICE, ["The Research Plan is not in the form this "
                                                                    "deployment runs."])
        if is_v2:
            plan = self._checked_angle_ids(state, final.research_plan)
            if plan is not final.research_plan:
                final = final.model_copy(update={"research_plan": plan})
            problems = self._plan_v2_problems(state, final.research_plan)
            if problems:
                # M38 (suite20, 2026-09-29): a plan with several angles often needed a second repair, like FINDINGS_2
                kind = "PLAN_FEASIBILITY_2" if "PLAN_FEASIBILITY" in state.gate_kinds_rejected else "PLAN_FEASIBILITY"
                self._gate_once(state, kind, MULTI_ANGLE_FEASIBILITY_INSTRUCTION.format(
                    problems="; ".join(problems[:6])))
                return self._plan_not_feasible(state, final)
        elif self.research_findings and not isinstance(final.research_plan, ResearchPlanFindings):
            self._gate_once(state, "PLAN_FINDINGS", PLAN_FINDINGS_INSTRUCTION)
            return self._forced(state, final, PLAN_FINDINGS_NOTICE,
                                ["The Research Plan lacks expected_direction, outcome_horizon_periods, outcome_unit, "
                                 "success_definition or min_effect in its experiments."])
        unknown = [i.output_ref for i in final.research_plan.carried_inputs or []
                   if self._carried_id(state, i.output_ref) is None]
        if unknown:
            known = [o.get("ref") for o in state.data_record.get("outputs") or [] if o.get("ref")]
            self._gate_once(state, "PLAN_CARRIED_INPUTS", CARRIED_INPUTS_INSTRUCTION.format(
                unknown=", ".join(unknown), known=", ".join(known[-20:]) or "none"))
            return self._forced(state, final, PLAN_VERSION_NOTICE, [f"The Research Plan names tables that are not "
                                                                    f"released in this conversation: "
                                                                    f"{', '.join(unknown)}."])
        if self.plan_feasibility and not is_v2 and state.feasible_draft is None:
            self._gate_once(state, "PLAN_FEASIBILITY", PLAN_FEASIBILITY_INSTRUCTION,
                            needs=frozenset({"check_data_feasibility"}))
            return self._plan_not_feasible(state, final)
        # M28 / H2: a success threshold is the user's number (their question or this message), never the model's
        words = self._user_words(state)
        # a pipeline's own user words are the whole source; a plan's original_question is the model's restatement
        sources = [words] if current_user_words.get() is not None else [
            words, getattr(final.research_plan, "original_question", "")]
        stated = released_numbers(sources)
        # 10.6 (plan 2026-10-05, user decision): when the router read the newest message as building on the latest
        # result ("pakai angka hasil analisa kamu barusan"), a threshold may be a value of this conversation's results
        # that the plan's own text cites as a value reference (the user sees where it comes from before approving)
        cited = self._cited_result_values(state)
        before = list(stated)
        stated = stated + cited
        # variants (2026-10-06): a threshold the user took out (REMOVE) is no longer theirs
        changes = current_design_changes.get() if self.ask_back else None
        stated_success = _without(stated, design_values(changes, "SUCCESS_THRESHOLD", "REMOVE"))
        invented_at = [(index, e.success_rule.value)
                       for index, e in enumerate(getattr(final.research_plan, "experiments", None) or [])
                       if getattr(e, "success_rule", None) is not None
                       and not any(abs(n - e.success_rule.value) < 1e-9 or abs(n * 100 - e.success_rule.value) < 1e-9
                                   or abs(n / 100 - e.success_rule.value) < 1e-9 for n in stated_success)
                       and not cited_match(e.success_rule.value, cited, magnitude=False)]
        invented = [value for _, value in invented_at]
        if invented:
            values = ", ".join(f"{v:g}" for v in invented)
            paths = ", ".join(f"research_plan.experiments[{index}].success_rule" for index, _ in invented_at)
            self._gate_once(state, "PLAN_SUCCESS_RULE", PLAN_SUCCESS_RULE_INSTRUCTION.format(values=values)
                            + PLAN_FIELD_PATHS.format(paths=paths)
                            + (CITED_THRESHOLD_HINT if current_turn_referent.get() == "NEWEST_RESULT" else ""))
            return self._forced(state, final, PLAN_PROVENANCE_NOTICE.format(numbers=values),
                                [f"Success thresholds the user did not state: {values}."])
        # M26 option B: a minimum effect decides the verdict, so it is the user's number too (experiments and angles)
        plan_items = "experiments" if getattr(final.research_plan, "experiments", None) else "angles"
        items_with_effect = [(index, i) for index, i in enumerate(getattr(final.research_plan, plan_items, None) or [])
                             if getattr(i, "min_effect", None) is not None]
        stated_effect = _without(stated, design_values(changes, "MIN_EFFECT", "REMOVE"))
        invented_at = [(index, i.min_effect) for index, i in items_with_effect
                       if not any(abs(n - i.min_effect) < 1e-9 or abs(n * 100 - i.min_effect) < 1e-9
                                  or abs(n / 100 - i.min_effect) < 1e-9 for n in stated_effect)
                       and not cited_match(i.min_effect, cited, magnitude=True)]
        invented = [value for _, value in invented_at]
        if invented:
            values = ", ".join(f"{v:g}" for v in invented)
            paths = ", ".join(f"research_plan.{plan_items}[{index}].min_effect" for index, _ in invented_at)
            self._gate_once(state, "PLAN_MIN_EFFECT", PLAN_MIN_EFFECT_INSTRUCTION.format(values=values)
                            + PLAN_FIELD_PATHS.format(paths=paths)
                            + (CITED_THRESHOLD_HINT if current_turn_referent.get() == "NEWEST_RESULT" else ""))
            return self._forced(state, final, PLAN_PROVENANCE_NOTICE.format(numbers=values),
                                [f"Minimum effects the user did not state: {values}."])
        self._log_cited_thresholds(state, final, before, cited)
        # M69 tahap 1: an outcome horizon the user stated binds every experiment and angle
        # the newest statement wins: a revision replaces the horizon of the first question (oldest text first)
        horizons, disagreement = locked_horizons(list(reversed(sources)), current_design_changes.get())
        if disagreement:
            log_event("plan_horizon_readings_disagree", request_id=state.request_id, detail=disagreement)
        allowed = allowed_periods(horizons, getattr(final.research_plan, "analysis_frequency", None))
        horizon_key = "angles" if getattr(final.research_plan, "angles", None) else "experiments"
        items = [(getattr(i, "angle_id", None) or getattr(i, "experiment_id", "?"), i.outcome_horizon_periods,
                  f"research_plan.{horizon_key}[{index}].outcome_horizon_periods")
                 for index, i in enumerate(getattr(final.research_plan, horizon_key, None) or [])
                 if getattr(i, "outcome_horizon_periods", None) is not None]
        drifted = [(name, used, path) for name, used, path in items if allowed and used not in allowed]
        if drifted:
            stated_text = ", ".join(f"{n} {u.lower()}{'s' if n > 1 else ''}" for n, u in sorted(horizons))
            self._gate_once(state, "PLAN_HORIZON", PLAN_HORIZON_INSTRUCTION.format(
                stated=stated_text, plan_items=", ".join(n for n, _, _ in drifted),
                used=", ".join(sorted({str(u) for _, u, _ in drifted})),
                allowed=" or ".join(str(a) for a in sorted(allowed)))
                + PLAN_FIELD_PATHS.format(paths=", ".join(path for _, _, path in drifted)))
            return self._forced(state, final, PLAN_VERSION_NOTICE, [
                f"The Research Plan changes the outcome horizon the user stated ({stated_text})."])
        if changes is not None and not disagreement:
            final = self._variant_coverage(state, final, horizons, allowed, {used for _, used, _ in items}, changes)
        # M29 (d02 2026-09-29: "about 6 banks" planned, 48 run): a number written in the plan's own text (universe,
        # scope, hypotheses, assumptions) needs a source too; the plan's structured fields are design values
        plan_json = final.research_plan.model_dump(mode="json")
        own = self._source_index(state)
        own.add(CONTEXT, numbers_in(plan_json))
        written = check_answer("\n".join(_plan_texts(plan_json)), own)
        if written.unsupported:
            numbers = ", ".join(written.unsupported[:20])
            self._gate_once(state, "PLAN_TEXT_PROVENANCE", PLAN_TEXT_PROVENANCE_INSTRUCTION.format(numbers=numbers))
            return self._forced(state, final, PLAN_PROVENANCE_NOTICE.format(numbers=numbers),
                                [f"Figures without a source in the Research Plan's text: {numbers}."])
        index = self._source_index(state)
        index.add(CONTEXT, released_numbers(final.research_plan.model_dump(mode="json")))  # P12
        provenance = check_answer(final.answer, index)
        state.number_provenance = {"checked": provenance.checked, "unsupported": provenance.unsupported[:50]}
        if provenance.unsupported:
            numbers = ", ".join(provenance.unsupported[:20])
            self._gate_once(state, "PLAN_PROVENANCE", PLAN_PROVENANCE_INSTRUCTION.format(numbers=numbers))
            return self._forced(state, final, PLAN_PROVENANCE_NOTICE.format(numbers=numbers),
                                [f"Figures without a source in this Research Plan: {numbers}."])
        state.evidence_label = None
        return final

    def _variant_coverage(self, state: RunState, final: FinalResponse, horizons: set[tuple[int, str]],
                          allowed: set[int], used: set[int], changes: list[dict]) -> FinalResponse:
        """Variants (2026-10-06): every outcome horizon and every threshold the user named more than once is in the plan
        (or was already tested in this conversation). Rejected once with the missing values; then the plan goes out
        with a limitation that names them (a plan without one variant is still the user's to approve)."""
        tested = {int(v) for entry in state.data_record.get("findings") or []
                  for key in ("horizon_periods", "outcome_horizon_periods")
                  for v in [((entry.get("finding") or {}).get("parameters") or {}).get(key)]
                  if isinstance(v, (int, float))}
        asked, missing = [], []
        if len(horizons) > 1 and allowed:
            asked.append("outcome horizons " + ", ".join(str(a) for a in sorted(allowed)) + " periods")
            missing += [f"outcome horizon {a} periods" for a in sorted(allowed - used - tested)]
        plan = final.research_plan.model_dump(mode="json")
        items = [i for i in (plan.get("experiments") or []) + (plan.get("angles") or []) if isinstance(i, dict)]
        # where each kind of value sits in a plan: the event's definition, the success rule, the minimum effect
        where = {"CONDITION_THRESHOLD": [n for i in items for n in numbers_in(i.get("parameters"))] + [
                     value for i in items for key in ("condition", "hypothesis", "angle_question")
                     for shown in parse_numbers(str(i.get(key) or "")) for value, _ in shown.candidates],
                 "SUCCESS_THRESHOLD": [float((i.get("success_rule") or {}).get("value")) for i in items
                                       if isinstance((i.get("success_rule") or {}).get("value"), (int, float))],
                 "MIN_EFFECT": [float(i["min_effect"]) for i in items if isinstance(i.get("min_effect"), (int, float))]}
        for name, found in where.items():
            values = design_values(changes, name, "ADD", "REPLACE")
            if len(values) < 2:
                continue
            asked.append(name.lower().replace("_", " ") + " " + ", ".join(f"{v:g}" for v in values))
            missing += [f"{name.lower().replace('_', ' ')} {v:g}" for v in values if _without([v], found)]
        if not missing:
            return final
        self._gate_once(state, "PLAN_VARIANT_COVERAGE", PLAN_VARIANT_COVERAGE_INSTRUCTION.format(
            asked="; ".join(asked), missing=", ".join(missing)), outcome="ANNOTATED")
        line = VARIANT_COVERAGE_LINE.format(missing=", ".join(missing))
        return final if line in final.limitations else final.model_copy(
            update={"limitations": [*final.limitations, line]})

    @staticmethod
    def _carried_id(state: RunState, ref: str) -> str | None:
        """The output id of a released table of this conversation by its ref (out.oN), from the data record."""
        return next((str(o["output_id"]) for o in state.data_record.get("outputs") or []
                     if o.get("ref") == ref and o.get("output_id")), None)

    def _carried_ids(self, state: RunState, plan: Any) -> list[str]:
        """2d: the tables an approved plan names, as the output ids its research sessions may load (none when it
        names none; a ref that no longer resolves is left out and logged)."""
        ids = []
        for item in getattr(plan, "carried_inputs", None) or []:
            output_id = self._carried_id(state, item.output_ref)
            if output_id is None:
                log_event("carried_input_unresolved", request_id=state.request_id, ref=item.output_ref)
                continue
            ids.append(output_id)
        return ids

    def _plan_form_runs(self, is_v2: bool, presenting: bool = False, plan: Any = None) -> bool:
        """Whether this deployment runs a plan of this form: the multi-angle form with Multi-Angle Research, the
        experiment form without it, and both with hypothesis plans (G3). Mode 4 sets angle bounds for the plans it
        proposes, so a plan it presents is multi-angle, except (M69 tahap 1, golden g6_revise 2026-10-02) a hypothesis
        plan whose experiments carry a success_rule: the multi-angle methods have no success rule, so a user's
        threshold ("up at least 3% within 10 days") is tested only by the hypothesis plan (event_summary). Whether
        the threshold is the user's number is the PLAN_SUCCESS_RULE gate's check."""
        if presenting and is_v2 is False and self.multi_angle and current_angle_bounds.get() is not None:
            return self.hypothesis_plans and any(getattr(e, "success_rule", None) is not None
                                                 for e in getattr(plan, "experiments", None) or [])
        return is_v2 == self.multi_angle or (self.hypothesis_plans and not is_v2)

    @staticmethod
    def _user_words(state: RunState) -> str:
        """The user's own words in this run (a pipeline's sub-run adds application context to its message)."""
        words = current_user_words.get()
        return state.user_text if words is None else words

    def _checked_angle_ids(self, state: RunState, plan: ResearchPlanV2) -> ResearchPlanV2:
        """M49 (2026-10-01, m01 m4b): an angle's id is the key the feasibility check gave its data and design; a plan
        angle the model renamed (its title and wording may change) but whose design is exactly one unmatched checked
        angle's design takes that checked id back, so a rename is not a new angle. Anything else stays as written and
        the checks below name what was not checked."""
        feasible = state.research.feasible if state.research is not None else None
        if feasible is None:
            return plan
        checked = set(feasible.get("angle_to_bundle_group") or {})
        designs = feasible.get("angle_design_sha256s") or {}
        planned = {a.angle_id for a in plan.angles}
        open_checked = {i: designs.get(i) for i in checked - planned if designs.get(i)}
        renamed: dict[str, str] = {}
        for angle in plan.angles:
            if angle.angle_id in checked:
                continue
            same = [i for i, design in open_checked.items() if design == design_sha256(angle.model_dump(mode="json"))]
            if len(same) == 1 and same[0] not in renamed.values():
                renamed[angle.angle_id] = same[0]
        if not renamed:
            return plan
        log_event("research_plan_angle_ids_restored", request_id=state.request_id, renamed=renamed)
        return plan.model_copy(update={"angles": [a.model_copy(update={"angle_id": renamed.get(a.angle_id,
                                                                                                a.angle_id)})
                                                  for a in plan.angles]})

    def _plan_v2_problems(self, state: RunState, plan: ResearchPlanV2) -> list[str]:
        """A multi-angle plan is issued only for exactly the angles of this run's last FEASIBLE research data plan,
        within the deployment's angle limits, with a separate later range for every angle that requires a holdout."""
        feasible = state.research.feasible if state.research is not None else None
        if feasible is None:
            return ["no check_research_feasibility result of this run was FEASIBLE"]
        problems = []
        planned = sorted(a.angle_id for a in plan.angles)
        checked = sorted(feasible.get("angle_to_bundle_group") or {})
        if planned != checked:
            # M49: name exactly what is new and what was dropped, so only those are checked again
            new, dropped = sorted(set(planned) - set(checked)), sorted(set(checked) - set(planned))
            problems.append(f"the plan's angles {planned} differ from the angles checked {checked}"
                            + (f"; not checked: {new}" if new else "") + (f"; checked but missing: {dropped}"
                                                                          if dropped else ""))
        low, high = current_angle_bounds.get() or (self.research_limits.get("min_angles", 2),
                                                    self.research_limits.get("max_angles", 6))
        if not low <= len(planned) <= high:
            problems.append(f"the plan has {len(planned)} angles; this deployment runs {low} to {high}")
        families = min(int(self.research_limits.get("min_families") or 0), high)  # a one-angle plan has one family
        if families and family_count([a.method_id for a in plan.angles]) < families:
            problems.append(f"the angles use {family_count([a.method_id for a in plan.angles])} method families; "
                            f"this deployment needs at least {families}")
        contracts = feasible.get("angle_data_contracts") or {}
        checked_designs = feasible.get("angle_design_sha256s") or {}
        designs = state.research.designs if state.research is not None else {}
        for angle in plan.angles:
            if angle.holdout_required and angle.angle_id in contracts \
                    and holdout_start(contracts[angle.angle_id]) is None:
                problems.append(f"{angle.angle_id} requires a holdout, but its checked data has a single range; add "
                                "a separate later range for it")
            dumped = angle.model_dump(mode="json")
            if angle.angle_id in checked_designs and design_sha256(dumped) != checked_designs[angle.angle_id]:
                # M38: the plan carries exactly the design check_research_feasibility checked
                fields = design_differences(dumped, designs.get(angle.angle_id) or {})
                problems.append(f"{angle.angle_id}: {', '.join(fields) or 'the design'} differ from the design "
                                "check_research_feasibility checked; present the checked design, or check the new one")
        return problems

    @staticmethod
    def _plan_not_feasible(state: RunState, final: FinalResponse) -> FinalResponse:
        """A plan presented without a FEASIBLE check after the reminder becomes a LIMITATION: no plan id, no token."""
        state.validation_gate = "FORCED_LIMITATION"
        state.evidence_label = None
        reasons = []
        for check in state.feasibility_checks[-3:]:
            refused = "; ".join(f"{r.get('data_request_id')}: {r.get('governor_status')} {r.get('code') or ''}".strip()
                                for r in check.get("requests") or [])
            reasons.append(f"Feasibility check {check.get('status')}"
                           + (f" (issues: {', '.join(str(i) for i in check['issues'])})" if check.get("issues") else "")
                           + (f" (angles not served: {', '.join(check['uncovered_angle_ids'])})"
                              if check.get("uncovered_angle_ids") else "")
                           + (f" ({refused})" if refused else "") + ".")
        if not reasons:
            reasons.append("The plan's data was not checked with check_data_feasibility.")
        return FinalResponse(response_type="LIMITATION", answer=PLAN_NOT_FEASIBLE_NOTICE + " ".join(reasons),
                             clarification_question=None, assumptions=final.assumptions,
                             limitations=reasons + [x for x in final.limitations if x not in reasons])

    @staticmethod
    def _claim_spans(state: RunState, answer: str, dataneed: bool = False,
                     verified_ok: bool = False) -> list[tuple[str, int, int]]:
        """The asserted claims of an answer (kind, start, end): causal and proof wording are never supported by these
        analyses; predictive wording needs a PREDICTIVE analysis whose evidence was SUPPORTED (never in the DataNeed
        flow); in the DataNeed flow a claim that the calculation was verified is not supported either. A phrase that a
        negation governs, before or after it in its clause, is not a claim (P17)."""
        text = answer or ""
        spans = []

        def asserted(kind: str, pattern: str, negation_inside: bool = False) -> None:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                inside = negation_inside and re.search(NEGATION_PATTERN, match.group(0), re.IGNORECASE)
                if not inside and not negated_in_clause(text, match.start(), match.end()):
                    spans.append((kind, match.start(), match.end()))

        asserted("CAUSAL", CAUSAL_PATTERN)
        asserted("PROOF", PROOF_PATTERN)
        supported = not dataneed and any(e.get("claim_type") == "PREDICTIVE" and e.get("decision") == "SUPPORTED"
                                         for e in state.evidence.values())
        if not supported:
            asserted("PREDICTIVE", PREDICTIVE_PATTERN)
        if dataneed and not verified_ok:
            asserted("VERIFIED_CALCULATION", VERIFIED_CALCULATION_PATTERN, negation_inside=True)
        return spans

    def _annotate_claims(self, state: RunState, final: FinalResponse, dataneed: bool = False,
                         verified_ok: bool = False) -> FinalResponse:
        """P17 (user decision 2026-10-01): an unsupported claim is marked, never a reason to reject or discard the
        answer: its sentence in italics, response annotations for a hover, one limitation line, ANNOTATED."""
        state.claim_annotations = []
        if final.response_type not in ("ANSWER", "LIMITATION"):
            return final
        spans = self._claim_spans(state, final.answer, dataneed=dataneed, verified_ok=verified_ok)
        if not spans:
            return final
        text, annotations = annotate_claims(final.answer, spans)
        state.claim_annotations = annotations
        log_event("ai_claims_annotated", request_id=state.request_id, iteration=state.iterations,
                  kinds=sorted({a["kind"] for a in annotations}), count=len(annotations))
        limitations = final.limitations if CLAIM_ANNOTATION_LINE in final.limitations \
            else [*final.limitations, CLAIM_ANNOTATION_LINE]
        return final.model_copy(update={"answer": text, "limitations": limitations})

        causal = asserted(CAUSAL_PATTERN)
        if causal:
            return f"causal wording ({causal!r}) for a historical association"
        predictive = asserted(PREDICTIVE_PATTERN)
        supported = not dataneed and any(e.get("claim_type") == "PREDICTIVE" and e.get("decision") == "SUPPORTED"
                                         for e in state.evidence.values())
        if predictive and not supported:
            return f"predictive wording ({predictive!r}) without a supported predictive analysis"
        verified = asserted(VERIFIED_CALCULATION_PATTERN, negation_inside=True) if dataneed and not verified_ok \
            else None
        if verified:
            return (f"verification wording ({verified!r}): the backend verifies data coverage, not the calculation "
                    f"(calculation_validation NOT_PERFORMED)")
        return None

    def _angle_research(self, state: RunState, answer: str) -> list[dict[str, Any]]:
        """Multi-Angle Research: one experiment entry per approved angle (payload_version research_findings/v2)."""
        executor = self._executor(state)
        if executor is None:
            return []
        run = executor.result or {}
        findings = {f.get("angle_id"): f for f in run.get("research_findings") or []}
        mapping = executor.verified.research_data_plan.get("angle_to_bundle_group") or {}
        experiments = []
        for angle in executor.verified.plan.angles:
            finding = findings.get(angle.angle_id) or {}
            status = finding.get("status")
            retained = "NOT_RUN"
            if status and status != "NOT_RUN":
                index = SourceIndex()
                index.add("DATA_COVERAGE_VERIFIED", self._finding_numbers(finding))
                cited = check_answer(answer or "", index)
                retained = "RETAINED" if cited.checked > len(cited.unsupported) else "DISCARDED"
            group = executor.groups.get(mapping.get(angle.angle_id) or "") or {}
            experiments.append({
                "spec_id": group.get("need_id") or executor.research_run_id or executor.verified.plan_id,
                "evidence_standard": "HISTORICAL_PATTERN", "hypothesis_id": executor.verified.plan.root_hypothesis_id,
                "followup_of": None, "governor_decision": (executor.promotion or {}).get("status"),
                "analysis_id": finding.get("session_id") or group.get("session_id"),
                "execution_status": group.get("status"), "validation_status": status,
                "validation_level": finding.get("validation_level"), "evidence_decision": status,
                "evidence_level": (finding.get("sample") or {}).get("flag"), "retained": retained,
                "payload_version": FINDINGS_V2, "angle_id": angle.angle_id, "method_id": angle.method_id,
                "method_family": angle.method_family, "status": status or "NOT_RUN",
                "status_reason": finding.get("status_reason") or ("NOT_RECORDED" if not finding else None),
                "bundle_group_id": mapping.get(angle.angle_id), "research_run_id": executor.research_run_id})
        return experiments

    def _dataneed_research(self, state: RunState, answer: str) -> list[dict[str, Any]]:
        """RESEARCH data needs of this run as experiments (spec_id carries the need_id, analysis_id the session)."""
        experiments = []
        for need_id, need in state.needs.items():
            if need.get("mode") != "RESEARCH":
                continue
            session_id = next((sid for sid, s in state.sessions.items() if s.get("need_id") == need_id), None)
            completion = state.completions.get(session_id or "")
            retained = "NOT_RUN"
            if completion:
                index = SourceIndex()
                for completion_id in completion.get("completion_ids") or []:
                    record = state.analysis_values.get(f"completion:{completion_id}") or {}
                    if record.get("label"):
                        index.add(record["label"], record["values"])
                cited = check_answer(answer or "", index)
                retained = "RETAINED" if cited.checked > len(cited.unsupported) else "DISCARDED"
            governance = need.get("governance") or {}
            finding = state.research_findings.get(str(need.get("hypothesis_id"))) or {}
            experiments.append({
                "spec_id": need_id, "evidence_standard": "HISTORICAL_PATTERN", "hypothesis_id": need.get("hypothesis_id"),
                "followup_of": (governance.get("constraints") or {}).get("followup_of"),
                "governor_decision": governance.get("decision"), "analysis_id": session_id,
                "execution_status": (completion or {}).get("final", {}).get("sandbox_execution"),
                "validation_status": (completion or {}).get("coverage"),
                "validation_level": (completion or {}).get("final", {}).get("evidence_label"),
                "evidence_decision": finding.get("verdict"), "evidence_level": finding.get("sample_flag"),
                "retained": retained})
        return experiments

    def _research_summary(self, state: RunState, answer: str) -> list[dict[str, Any]]:
        """Experiments of this run and whether the final answer relies on them (from the numbers it cites)."""
        if self.dataneed:
            return self._angle_research(state, answer) + self._dataneed_research(state, answer)
        latest: dict[str, dict[str, Any]] = {}
        for summary in state.analyses.values():
            if summary.get("spec_id"):
                latest[summary["spec_id"]] = summary
        followed = {spec["research"]["followup_of"] for spec in state.specs.values()
                    if spec.get("research") and spec["research"].get("followup_of")}
        experiments = []
        for spec_id, spec in state.specs.items():
            analysis = latest.get(spec_id)
            retained = "NOT_RUN"
            if analysis:
                record = state.analysis_values.get(analysis["analysis_id"]) or {}
                index = SourceIndex()
                if record.get("label"):
                    index.add(record["label"], record["values"])
                cited = check_answer(answer or "", index)
                retained = "RETAINED" if cited.checked > len(cited.unsupported) else "DISCARDED"
                if spec_id in followed:
                    retained = "FOLLOWED_UP" if retained == "DISCARDED" else retained
            evidence = state.evidence.get(analysis["analysis_id"]) if analysis else None
            experiments.append({
                "spec_id": spec_id, "evidence_standard": (spec.get("research") or {}).get("evidence_standard")
                or "CALCULATION", "hypothesis_id": (spec.get("research") or {}).get("hypothesis_id"),
                "followup_of": (spec.get("research") or {}).get("followup_of"), "governor_decision":
                spec.get("governor"), "analysis_id": analysis["analysis_id"] if analysis else None,
                "execution_status": analysis["execution_status"] if analysis else None,
                "validation_status": analysis.get("validation_status") if analysis else None,
                "validation_level": analysis.get("validation_level") if analysis else None,
                "evidence_decision": (evidence or {}).get("decision"),
                "evidence_level": (evidence or {}).get("evidence_level"), "retained": retained})
        return experiments

    @staticmethod
    def _forced(state: RunState, final: FinalResponse, notice: str, lines: list[str]) -> FinalResponse:
        state.validation_gate = "FORCED_LIMITATION"
        state.evidence_label = "NOT_VALIDATED"
        # M39 (suite20b r11, 2026-09-29): a LIMITATION forced by any gate after a completed multi-angle run keeps the
        # backend's per-angle findings (the provenance gate dropped three validated findings)
        executor = state.research.executor if state.research is not None else None
        run = executor.result if executor is not None else None
        return FinalResponse(response_type="LIMITATION", answer=notice + final.answer, clarification_question=None,
                             assumptions=final.assumptions,
                             limitations=lines + [x for x in final.limitations if x not in lines],
                             research_findings=backend_findings(run) if run else None)

    def _tool_arguments(self, name: str, raw: Any) -> Any:
        """The arguments as the tool validates them (M55's envelope taken out by the registry's own rule): a wrapped
        data need keeps its mode for the path and research guards and the data record."""
        arguments = self._normalized_arguments(raw)
        reader = getattr(self.registry, "arguments_of", None)
        return reader(name, arguments) if reader is not None else arguments

    @staticmethod
    def _normalized_arguments(raw: Any) -> Any:
        if isinstance(raw, str):
            try:
                return json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                return raw
        return raw or {}

    def _request_structured_final(self, state: RunState, raw: str, issue: str = "") -> None:
        """A tool turn ended with a draft answer; ask for the final response as JSON.

        The first re-ask keeps the tool-turn request unchanged (same tools, no text.format), so it stays on the
        provider that served the run and reuses its prompt cache; the contract comes from FINALIZE_INSTRUCTION
        and the answer is still parsed and validated strictly. Only when that answer is still not a valid final
        response does the next turn drop the tools and enforce the strict JSON schema. With
        provider.require_parameters, that strict turn can only run on endpoints that support structured outputs,
        which may not be the endpoint that served the tool turns (verified 2026-09-24).
        """
        if self.audit_outbox is not None:
            state.audit_trace.append(final_event("final.rejected", iteration=state.iterations, stage="FORMAT",
                                                 detail=issue or "not a final response", draft=raw,
                                                 occurred_at=self.wall_clock()))
        self._echo_draft(state, raw)
        if state.final_reask_sent:
            state.structured_only = True
        state.final_reask_sent = True
        # M46 (2026-10-01): every re-ask names what was wrong (it used to only for a cut-off response, so a schema
        # refusal was rewritten blind)
        state.input_items.append({"role": "user", "content": (issue + " " if issue else "")
                                  + self.finalize_instruction + self._offer_edit(state, raw)})
        log_event("ai_final_reask", request_id=state.request_id, iteration=state.iterations,
                  next_turn="STRICT_SCHEMA" if state.structured_only else "SAME_PREFIX",
                  looked_like_json=raw.strip().startswith(("{", "```")), output_chars=len(raw), issue=issue[:300])

    @staticmethod
    def _echo_draft(state: RunState, raw: str) -> None:
        """The refused draft, as the model wrote it, before the refusal (M48: whole up to REJECTED_OUTPUT_ECHO_CHARS;
        a longer one says it was cut)."""
        if not raw.strip():
            return
        text = raw[:REJECTED_OUTPUT_ECHO_CHARS]
        if len(raw) > REJECTED_OUTPUT_ECHO_CHARS:
            log_event("ai_final_echo_truncated", request_id=state.request_id, iteration=state.iterations,
                      chars=len(raw), echoed=REJECTED_OUTPUT_ECHO_CHARS)
            text += f"\n[draft cut at {REJECTED_OUTPUT_ECHO_CHARS} of {len(raw)} characters]"
        state.input_items.append({"role": "assistant", "content": text})

    def _reject_final(self, state: RunState, raw: str, issue: str) -> None:
        state.final_rejections += 1
        limit = self.settings.ai_final_response_max_retries
        log_event("ai_final_rejected", request_id=state.request_id, iteration=state.iterations,
                  rejections=state.final_rejections, issue=issue[:300])
        if self.audit_outbox is not None:
            state.audit_trace.append(final_event("final.rejected", iteration=state.iterations, stage="FORMAT",
                                                 detail=issue, draft=raw, occurred_at=self.wall_clock()))
        if state.final_rejections > limit:
            raise RunFailure(
                "INVALID_FINAL_RESPONSE",
                f"Final response remained invalid after {limit} retries: {issue}"[:1000],
            )
        self._echo_draft(state, raw)
        # M45: with an edit offered the next turn stays free-form (the strict schema admits only the full response)
        offer = self._offer_edit(state, raw)
        state.input_items.append({
            "role": "user",
            "content": (
                f"Your previous response was rejected ({state.final_rejections}/{limit} retries): "
                f"{issue} Correct exactly this issue. Do not call tools. " + self.response_contract + offer
            ),
        })
        if not offer:
            state.structured_only = True

    def _offer_edit(self, state: RunState, raw: str) -> str:
        """M45 (AI_ENABLE_EDIT_REPAIR): the edit instruction when the refused draft is a JSON object and the next turn
        is free-form (an edit object cannot pass the strict schema); otherwise nothing: the full rewrite as before."""
        state.repair_base = None
        retry_base, state.edit_retry_base = state.edit_retry_base, None
        if not self.settings.ai_enable_edit_repair or state.tools_locked or state.structured_only \
                or not self._turn_tools(state):
            return ""
        state.repair_base = retry_base if retry_base is not None else edit_repair.draft_object(raw)
        return " " + edit_repair.EDIT_REPAIR_INSTRUCTION if state.repair_base is not None else ""

    def _apply_edit(self, state: RunState, raw: str) -> tuple[str, ValueError | None]:
        """M45: a reply that is an edit object becomes the edited draft, which then passes every check as a full
        response would; a reply that is not an edit is taken as it is. EXEC-R R4b: the first edit that does not apply
        exactly is refused with its cause and the same draft is offered for one more edit; a second failure returns the
        refusal that asks for the full response. {"keep": true} (R2) returns the draft unchanged."""
        base, state.repair_base = state.repair_base, None
        reply = edit_repair.draft_object(raw, edits=True)
        if not edit_repair.is_edit(reply):
            state.edit_retry_used = False
            return raw, None
        try:
            merged, counts = edit_repair.apply(base, reply, set(FinalResponse.model_fields))
        except edit_repair.EditNotApplied as exc:
            retry = not state.edit_retry_used
            state.edit_retry_used = True
            log_event("ai_final_edit_failed", request_id=state.request_id, iteration=state.iterations,
                      issue=str(exc)[:300], retry_offered=retry)
            if self.audit_outbox is not None:
                state.audit_trace.append(final_event("final.rejected", iteration=state.iterations, stage="EDIT",
                                                     detail=str(exc), draft=raw, occurred_at=self.wall_clock()))
            if retry:
                state.edit_retry_base = base
                return raw, edit_repair.EditNotApplied(
                    f"The edit could not be applied ({exc}). The draft before your edit is unchanged; correct the "
                    "edit, or send the complete corrected final response.")
            return raw, edit_repair.EditNotApplied(
                f"The edit could not be applied ({exc}). Send the complete corrected final response.")
        state.edit_retry_used = False
        log_event("ai_final_edit_applied", request_id=state.request_id, iteration=state.iterations,
                  edit_chars=len(raw), draft_chars=len(merged), **counts)
        if self.audit_outbox is not None:
            state.audit_trace.append(final_event("final.edit_applied", iteration=state.iterations, stage="EDIT",
                                                 detail=json.dumps(counts), draft=raw,
                                                 occurred_at=self.wall_clock()))
        return merged, None

    def _add_usage(self, state: RunState, response: dict[str, Any]) -> dict[str, Any]:
        usage = response_usage(response)
        state.input_tokens += usage["input_tokens"]
        state.output_tokens += usage["output_tokens"]
        state.reasoning_tokens += usage["reasoning_tokens"]
        state.total_tokens += usage["total_tokens"]
        state.cached_input_tokens += usage["cached_input_tokens"]
        state.cache_write_tokens += usage["cache_write_tokens"]
        state.cache_metrics_calls += int(usage["cache_metrics_reported"])
        if usage["cost"] is not None:
            state.cost += usage["cost"]
            state.cost_calls += 1
        state.provider_response_id = response.get("id") or state.provider_response_id
        return usage

    def _usage_summary(self, state: RunState) -> dict[str, Any]:
        """Run-level model usage: logical prompt tokens versus what the provider served from its cache."""
        return {
            "request_id": state.request_id,
            "session_id": session_key(state.request_id),
            "model": self.settings.ai_model,
            "model_calls": state.iterations,
            "prompt_tokens": state.input_tokens,
            "cached_input_tokens": state.cached_input_tokens,
            "cache_write_tokens": state.cache_write_tokens,
            "fresh_input_tokens": max(state.input_tokens - state.cached_input_tokens, 0),
            "completion_tokens": state.output_tokens,
            "reasoning_tokens": state.reasoning_tokens,
            "total_tokens": state.total_tokens,
            "cache_ratio": round(state.cached_input_tokens / state.input_tokens, 4) if state.input_tokens else None,
            "cache_metrics_reported_calls": state.cache_metrics_calls,
            "cost": round(state.cost, 8) if state.cost_calls else None,
            "cost_reported_calls": state.cost_calls,
            "average_latency_ms": round(state.model_latency_ms / state.iterations) if state.iterations else None,
            "plan_reply_classifier_calls": 1 if state.classifier else 0,
            "distinct_static_prefixes": len(dict.fromkeys(state.static_prefixes)),
        }

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str:
        parts: list[str] = []
        for item in response.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if (
                    isinstance(content, dict)
                    and content.get("type") == "output_text"
                    and isinstance(content.get("text"), str)
                ):
                    parts.append(content["text"])
        return "".join(parts)

    @staticmethod
    def _parse_final_output(raw: str, dropped: dict[str, Any] | None = None) -> FinalResponse:
        candidate = raw.strip()
        if not candidate:
            raise ValueError("The response contained neither a tool call nor a final answer.")
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if len(lines) < 3 or lines[0].strip().lower() not in {"```", "```json"} or lines[-1].strip() != "```":
                raise ValueError("Final response used an invalid Markdown wrapper.")
            candidate = "\n".join(lines[1:-1]).strip()
        # M46 (user decision 2026-10-01): keys the response format does not have (limitations_note, ...) are taken
        # out instead of refusing the whole answer; the caller keeps them for the audit. Nested objects stay strict.
        try:
            data = json.loads(candidate, strict=False)
        except ValueError:
            data = None
        if isinstance(data, dict):
            extra = {key: data.pop(key) for key in list(data) if key not in FinalResponse.model_fields}
            extra.update(AgentOrchestrator._feasibility_fields(data))
            if extra:
                candidate = json.dumps(data, ensure_ascii=False)
                if dropped is not None:
                    dropped.update(extra)
        try:
            try:
                return FinalResponse.model_validate_json(candidate)
            except ValueError as strict_error:
                # M40 (2026-09-30): a raw control character (a line break) inside a JSON string is valid for a
                # lenient decoder. EXEC-R R4a (2026-10-06): when the lenient decoder fails too, its error is the one
                # the model sees, with where and the text around it; the strict parser's "control character" pointed
                # at a line break the backend accepts (q7, P3d)
                try:
                    data = json.loads(candidate, strict=False)
                except json.JSONDecodeError as lenient_error:
                    raise FinalJsonError(AgentOrchestrator._json_error(candidate, lenient_error)) from None
                if not isinstance(data, dict):
                    raise strict_error from None
                return FinalResponse.model_validate(data)
        except FinalJsonError:
            raise
        except Exception as exc:
            details = []
            if hasattr(exc, "errors"):
                relevant = AgentOrchestrator._relevant_branch(candidate)
                for item in exc.errors(include_url=False, include_input=False):
                    location = ".".join(str(part) for part in item.get("loc") or ()) or "root"
                    if not relevant(location):
                        continue
                    location = re.sub(r"(?:function-after\[[^\]]*\]|list\[[A-Za-z]+\])\.?", "", location)
                    details.append(f"{location.rstrip('.') or 'root'}: {item.get('msg', 'invalid value')}")
                    if len(details) == 8:
                        break
            issue = "; ".join(details) if details else type(exc).__name__
            raise ValueError(f"Final response failed schema validation: {issue}") from exc

    @staticmethod
    def _json_error(candidate: str, error: json.JSONDecodeError) -> str:
        """EXEC-R R4a: the lenient decoder's error, its line and column, and the text around it (the error marked)."""
        start, end = max(error.pos - JSON_ERROR_CONTEXT, 0), min(error.pos + JSON_ERROR_CONTEXT, len(candidate))
        around = candidate[start:error.pos] + "<<HERE>>" + candidate[error.pos:end]
        return (f"Final response is not valid JSON: {error.msg} at line {error.lineno} column {error.colno} "
                f"(character {error.pos}). Text around it: {json.dumps(around, ensure_ascii=False)}")

    @staticmethod
    def _feasibility_fields(data: dict[str, Any]) -> dict[str, Any]:
        """P8 (2026-10-01, ma-steps 2-m4b): a plan angle that carries the check_research_feasibility input of its data
        (data_requests, relationships, broad_scope, design) was refused as a whole and rewritten. Those fields belong
        to the check, whose result the backend already holds; they are taken out of each angle (derived from the two
        models, not listed by hand) and kept for the audit. Any other unknown nested field is still refused."""
        from .research_plan_v2 import ResearchAngle
        from .tools.research_planner import AngleRequirement

        owned = set(AngleRequirement.model_fields) - set(ResearchAngle.model_fields)
        plan = data.get("research_plan")
        taken: dict[str, Any] = {}
        if isinstance(plan, dict) and isinstance(plan.get("angles"), list):
            for index, angle in enumerate(plan["angles"]):
                if isinstance(angle, dict):
                    for key in sorted(owned & set(angle)):
                        taken[f"research_plan.angles[{index}].{key}"] = angle.pop(key)
        return taken

    def _note_extra_keys(self, state: RunState, dropped: dict[str, Any]) -> None:
        """M46: the keys taken out of a final response, logged and kept in the audit with their content."""
        keys = sorted(dropped)
        log_event("ai_final_extra_keys", request_id=state.request_id, iteration=state.iterations, keys=keys[:20])
        if self.audit_outbox is not None:
            state.audit_trace.append(final_event("final.extra_keys", iteration=state.iterations, stage="FORMAT",
                                                 detail="keys outside the response format: " + ", ".join(keys),
                                                 draft=json.dumps(dropped, ensure_ascii=False, default=str),
                                                 occurred_at=self.wall_clock()))

    @staticmethod
    def _relevant_branch(candidate: str) -> Callable[[str], bool]:
        """Found live (golden run 2026-09-29): a v2 plan with one bad field was answered with the errors of every
        union member (the v1 plan forms too: "plan_version should be research_plan/v1", "experiments: Field
        required"), which sent the model the wrong way. Only the errors of the form the response uses are kept."""
        try:
            data = json.loads(candidate)
        except ValueError:
            return lambda location: True
        drop: list[str] = []
        plan = data.get("research_plan") if isinstance(data, dict) else None
        if isinstance(plan, dict):
            drop += ["ResearchPlanFindings]", "ResearchPlan]"] if plan.get("plan_version") == PLAN_VERSION_V2 \
                else ["ResearchPlanV2]"]
        findings = data.get("research_findings") if isinstance(data, dict) else None
        if isinstance(findings, list) and findings and isinstance(findings[0], dict):
            drop += ["list[ResearchFinding]"] if "angle_id" in findings[0] else ["list[AngleFindingReport]"]
        return lambda location: not any(marker in location for marker in drop)

    def _execution(self, state: RunState) -> ExecutionMetadata:
        return ExecutionMetadata(
            model=self.settings.ai_model,
            provider_response_id=state.provider_response_id,
            iterations=state.iterations,
            tool_call_count=state.tool_calls,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            reasoning_tokens=state.reasoning_tokens,
            total_tokens=state.total_tokens,
            cached_input_tokens=state.cached_input_tokens,
            cache_write_tokens=state.cache_write_tokens,
            cost=round(state.cost, 8) if state.cost_calls else None,
            duration_ms=int((self.clock() - state.started) * 1000),
            tools_withdrawn_reason=state.tools_withdrawn_reason,
            analyses=[AnalysisSummary(**{k: v for k, v in a.items() if k != "error_code"})
                      for a in state.analyses.values()],
            validation_gate=state.validation_gate,
            number_provenance=NumberProvenance(**state.number_provenance) if state.number_provenance else None,
            methodology_provenance=NumberProvenance(**state.methodology_provenance)
            if state.methodology_provenance else None,
            research=ResearchSummary(experiments=[ExperimentSummary(**e) for e in state.experiments])
            if state.experiments else None,
            analysis_final_status=state.final_status,
            analysis_final_statuses=state.final_statuses or None,
            research_plan=self._plan_execution(state),
            analysis_path=AnalysisPathExecution(requested=state.forced_path, mismatches_refused=state.path_refusals)
            if state.forced_path else None,
            friction=self._friction(state),
        )

    @staticmethod
    def _friction(state: RunState) -> dict[str, int]:
        return {**state.friction, "gate_repairs": state.gate_rejections}

    @staticmethod
    def _plan_execution(state: RunState) -> ResearchPlanExecution | None:
        if state.plan_turn is None:
            return None
        meta = state.plan_meta
        return ResearchPlanExecution(
            turn=state.plan_turn, verification=meta.get("verification") or "NOT_PRESENTED",
            action=meta.get("action"), action_source=meta.get("action_source"),
            approved_plan_id=meta.get("approved_plan_id"), issued_plan_id=meta.get("issued_plan_id"),
            guard_rejections=state.guard_rejections,
            research_submitted=state.research_attempted if state.plan_turn == "EXECUTE_APPROVED" else None,
            draft_id=meta.get("draft_id") or (meta.get("issued_plan_id") and state.feasible_draft) or None,
            classifier=ReplyClassifierUsage(**state.classifier) if state.classifier else None,
            plan_version=meta.get("plan_version"), research_data_plan_sha256=meta.get("research_data_plan_sha256"),
            research_run_id=state.research.executor.research_run_id
            if state.research is not None and state.research.executor is not None else None)

    def _failed(self, state: RunState, code: str, message: str) -> AgentRunResponse:
        return AgentRunResponse(
            request_id=state.request_id,
            status="FAILED",
            response=None,
            execution=self._execution(state),
            error=RunError(code=code, message=message[:1000]),
        )
