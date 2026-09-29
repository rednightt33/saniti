from __future__ import annotations

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

from .audit_outbox import build_payload, model_event, tool_event
from .catalog_protocol import CACHE_NOTE, CACHEABLE_TOOLS, CatalogLedger, cache_key, gaps, record
from .compaction import dumps, estimate_tokens, stable_hash, trim_history
from .config import Settings
from .openrouter_client import ProviderError, response_usage
from .research_plan import (CLASSIFIER_INSTRUCTIONS, CLASSIFIER_SCHEMA, ContinuationOut, PlanSigner,
                            PlanVerificationError, ReplyClassification, ResearchGuard, ResearchPlan,
                            ResearchPlanFindings,
                            current_research_guard, guard_research_submission, plan_digest)
from .research_plan_v2 import (FINDINGS_V2, PLAN_VERSION_V2, ContinuationInV2, ContinuationOutV2, PlanSignerV2,
                               ResearchPlanV2, design_differences, design_sha256, family_count, holdout_start,
                               plan_digest_v2)
from .research_run_executor import ResearchContext, current_research_context
from .schemas import (
    FINAL_RESPONSE_SCHEMA, STATUS_BY_RESPONSE_TYPE, AgentRunRequest, AngleFindingReport, AgentRunResponse, AnalysisSummary,
    AnalysisPathExecution, ExecutionMetadata, ExperimentSummary, FinalResponse, FindingInterpretation, NumberProvenance,
    ReplyClassifierUsage,
    ResearchPlanExecution, ResearchSummary, RunError, final_response_schema,
)
from .provenance import (CONTEXT, SourceIndex, analysis_label, check_answer, numbers_in, parse_numbers,
                         released_numbers, requested_statistics, weakest)
from .tools import ToolOutcome, ToolRegistry, error_outcome
from .tools.analysis import current_conversation_key, current_run_context, run_context
from .tools.registry import strict_parameters_schema
from .tools.request_data import current_request_id


logger = logging.getLogger("market_ai_orc")

SYSTEM_PROMPT_TEMPLATE = """You are the Saniti AI orchestration agent.
Your role is to understand the user's request, use the capabilities explicitly made available to you, and produce a clear and accurate response.
General rules:
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
11. If the requested capability is not currently available, say so clearly rather than fabricating an answer.
12. Preserve exact identifiers returned by tools. Do not invent alternative table, field, asset, or feature names.
13. Keep the final answer focused and proportional to the user's question.
14. Do not expose hidden chain-of-thought. Return conclusions, relevant assumptions, limitations, and tool-supported findings only.
15. Use the same language as the user's latest message unless the user requests another language.
Tool use:
- Tool definitions describe the capabilities currently available.
- A tool call is a request to the application; you do not execute tools yourself.
- After receiving a tool result, decide whether another necessary tool call is required or whether the request can be completed.
- Stop when the user's request has been sufficiently answered.
Final response:
Return only the response defined by the provided strict output schema.

DATA DISCOVERY RULES
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
When the required execution capability is unavailable,
return a LIMITATION response explaining what has
been identified and what remains unexecuted.

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
Data the catalog does not contain (for example macro data, yields,
fundamentals, or news) is unavailable: say so and never substitute
another dataset. A documented formula whose inputs are not in the
catalog cannot be calculated."""
DATANEED_RULES = """DATA NEED RULES
Every answer that needs market data follows one path:
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
2. prepare_data_bundle(need_id) extracts and verifies the data. Read
the quality flags and relationship warnings; disclose those that
affect the answer.
3. open_analysis_session(input_bundle_id), then run_python as often as
needed: read data only through the saniti helpers (load, range, sql,
join, quality), inspect it, write the analysis yourself (TA-Lib first
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
verified; state the method and parameters you used, and the approved
ranges.
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
never as a cause, a prediction, a forecast or a trading signal.
Data the catalog does not contain (for example macro data, yields,
fundamentals, or news) is unavailable: say so and never substitute
another dataset."""
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
run already received:
1. For data not yet read in this run, call discover_catalog once with
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
RESEARCH_FINDINGS_RULES = """

RESEARCH FINDINGS
Each experiment of a Research Plan also states expected_direction,
outcome_horizon_periods, outcome_unit, success_definition and
min_effect (null unless the user named the smallest effect that
matters); its research_governance copies them exactly. There is no
fixed minimum sample: the backend judges the sample after the run, so
an unusual condition with few occurrences may still be studied.
In the session, build one row per occurrence of the condition (events)
and the comparison rows (baseline), each with its outcome and date, and
call event_summary(events, baseline, hypothesis_id=..., outcome_column=
..., date_column=...) once per hypothesis before complete_analysis; a
research analysis without it is not completed. complete_analysis then
returns research_findings: the effect against the baseline (angle_a),
how often the outcome was a success against the baseline rate
(angle_b), the effective sample (distinct dates, overlapping outcomes
counted once), the sample category (INSUFFICIENT, ANECDOTAL,
UNDERPOWERED, ADEQUATE), the smallest detectable effect and the verdict
(SUPPORTED, NOT_SUPPORTED, INCONCLUSIVE, NOT_EVALUATED). They are the
backend's numbers: cite them; never recompute them or state another
verdict.

INTERPRETING RESEARCH
A research answer exists to change what the user knows or will do next.
For each completed experiment, research_findings carries the verdict
unchanged and an interpretation in four parts:
1. answer: the direct answer to the user's question, first, in the
verdict's terms: supported, not supported, or inconclusive.
2. evidence: what the numbers say: how large the effect is against the
baseline, how often the outcome happened against its base rate, and how
certain this is: the sample category, the effective sample, the
uncertainty and the smallest effect this sample could detect. When the
two angles point different ways, say what that combination means (for
example: more often up, but the falls are deeper).
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
or INSUFFICIENT sample as possible anomalies, not as a pattern; a
pattern is never a cause, a prediction or a trading signal. The answer
field tells the user the findings in their language, with the sample
category and what it means."""
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
NO_EFFECT_WORDING = (r"\b(?:tidak ada (?:efek|pengaruh|perbedaan)|tidak berpengaruh|no (?:effect|difference)|"
                     r"has no effect)\b")
# Multi-Angle Research (AI_ENABLE_MULTI_ANGLE_RESEARCH; MULTI_ANGLE_RESEARCH.md). They replace the Research Plan,
# plan feasibility and research findings rules when the feature is active. No digits: the system prompt is a number
# source for the provenance check (the plan's version constant appears only in the schema skeleton).
MULTI_ANGLE_PLAN_RULES = """

MULTI-ANGLE RESEARCH PLAN
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
execution only. Use the approved parameters, horizon and unit. Then
call complete_research_run with finalize false; it lists any angle not
yet recorded: record it and call it again. Finalize only an angle that
truly cannot be recorded: it becomes NOT_RUN and the other angles still
report.
A data need in mode RESEARCH is refused: research runs only through an
approved multi-angle plan. Mode ANALYSIS needs no plan and proceeds
directly."""
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
complete_research_run returned, the confidence level included. A pattern
is never a cause, a prediction or a trading signal."""
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
read its released output with get_session_output(session_id,
output_id). A released output of an earlier message is a source for
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
3. A warm session may be gone (idle timeout, eviction, restart): then
run the code that is needed again on the reused bundle.
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
                                                            "evidence_label", "warnings", "expires_at")
                                     if o.get(k) not in (None, [])}))
    bundles = resources.get("bundles") or []
    specs = [b.get("data_need_spec") for b in bundles]

    def render(with_specs: list[Any]) -> str:
        lines = ["Data of earlier data needs (submit the data_need_spec unchanged to reuse it without extraction):"]
        for bundle, spec in zip(bundles, with_specs):
            lines.append("- " + dumps({"bundle_id": bundle.get("bundle_id"), "extracted_at": bundle.get("extracted_at"),
                                       "expires_at": bundle.get("expires_at"), "mode": bundle.get("mode"),
                                       "warm_session": bundle.get("warm_session"),
                                       "datasets": bundle.get("datasets"), "data_need_spec": spec}))
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
                         multi_angle: bool = False) -> str:
    """The final-response contract for the system prompt (AI_FINAL_CONTRACT_IN_PROMPT). Tool turns carry no output
    schema, so without it a finished run often answered in prose first and was re-asked for JSON (the 2026-09-26
    stress test: 15% of model time and 20% of cost). With Research Plan confirmation it adds the plan's exact field
    form, generated from the ResearchPlan model, so a plan validates the first time. It contains no digits: numbers
    in the system prompt count as sources for the provenance check."""
    block = FINAL_CONTRACT_PREFIX + contract
    if plan_confirmation and multi_angle:
        block += ("\nresearch_plan has exactly this form: " + schema_skeleton(strict_parameters_schema(ResearchPlanV2))
                  + "\n" + MULTI_ANGLE_FIELD_RULES)
    elif plan_confirmation:
        block += ("\nresearch_plan has exactly this form: "
                  + schema_skeleton(strict_parameters_schema(ResearchPlanFindings if research_findings
                                                             else ResearchPlan)) + "\n" + PLAN_FIELD_RULES)
    return block


NUMBER_WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def build_system_prompt(lookup_fact: bool, dataneed: bool = False, plan_confirmation: bool = False,
                        period_return: bool = False, final_contract: bool = False,
                        catalog_protocol: bool = False, conversation_reuse: bool = False,
                        methodology: bool = False, plan_feasibility: bool = False,
                        point_in_time: bool = False, derived_frequency: bool = False,
                        research_findings: bool = False, multi_angle: bool = False,
                        angle_limits: tuple[int, int, int] = (2, 6, 0)) -> str:
    """The system prompt for the registered tools. It is fixed for a deployment (AI_ENABLE_LOOKUP_FACT,
    AI_ENABLE_DATANEED, AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION, AI_ENABLE_STANDARD_PERIOD_RETURN,
    AI_FINAL_CONTRACT_IN_PROMPT), so every call of every run shares one byte-identical cacheable prefix. With the
    DataNeed flow its rules replace those of the Analysis Spec path; the Research Plan and named-period-return rules
    exist only in the DataNeed flow."""
    template = SYSTEM_PROMPT_TEMPLATE
    # Multi-Angle Research replaces the Research Plan, plan feasibility and findings rules (it needs all three flows)
    multi_angle = multi_angle and dataneed and plan_confirmation and plan_feasibility
    if multi_angle:
        common, _ = SYSTEM_PROMPT_TEMPLATE.split("DATA QUERY RULES\n", 1)
        template = common + DATANEED_RULES + MULTI_ANGLE_PLAN_RULES \
            + (PERIOD_RETURN_RULES if period_return else "") + (CATALOG_PROTOCOL_RULES if catalog_protocol else "") \
            + (CONVERSATION_REUSE_RULES if conversation_reuse else "") + (METHODOLOGY_RULES if methodology else "") \
            + (POINT_IN_TIME_RULES if point_in_time else "") + (DERIVED_FREQUENCY_RULES if derived_frequency else "") \
            + MULTI_ANGLE_FINDINGS_RULES
    elif dataneed:
        common, _ = SYSTEM_PROMPT_TEMPLATE.split("DATA QUERY RULES\n", 1)
        template = common + DATANEED_RULES + (RESEARCH_PLAN_RULES if plan_confirmation else "") \
            + (PLAN_FEASIBILITY_RULES if plan_confirmation and plan_feasibility else "") \
            + (PERIOD_RETURN_RULES if period_return else "") + (CATALOG_PROTOCOL_RULES if catalog_protocol else "") \
            + (CONVERSATION_REUSE_RULES if conversation_reuse else "") + (METHODOLOGY_RULES if methodology else "") \
            + (POINT_IN_TIME_RULES if point_in_time else "") + (DERIVED_FREQUENCY_RULES if derived_frequency else "") \
            + (RESEARCH_FINDINGS_RULES if research_findings else "")
    if final_contract:
        # plan_confirmation and methodology reach here only together with dataneed (see AgentOrchestrator.__init__)
        contract = response_contract(plan_confirmation, methodology, research_findings, multi_angle)
        template = template.replace(STRICT_SCHEMA_LINE, final_contract_block(contract, plan_confirmation,
                                                                             research_findings, multi_angle))
    # Multi-Angle Research: the negotiated angle limits (AI_RESEARCH_MIN_ANGLES / MAX_ANGLES / MIN_FAMILIES), in words
    low, high, families = angle_limits
    families_rule = (f" The angles use at least {NUMBER_WORDS[families]} of the five method families."
                     if families else "")
    return (template.replace("{lookup_rule}", LOOKUP_RULE if lookup_fact else "")
            .replace("{number_sources}", "a lookup_fact result, " if lookup_fact else "")
            .replace("{min_angles}", NUMBER_WORDS[low]).replace("{max_angles}", NUMBER_WORDS[high])
            .replace("{families_rule}", families_rule))


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
CLAIM_INSTRUCTION = (
    "Your answer makes a claim the evidence of this run does not support: {problem}. Historical results describe an "
    "association, not a cause, and a result is predictive only when an analysis with evidence_standard PREDICTIVE "
    "has evidence_assessment decision SUPPORTED. Rephrase the claim to what the evidence supports (follow each "
    "analysis's reporting_constraints), or return response_type \"LIMITATION\"."
)
CLAIM_NOTICE = "The evidence of this run does not support a causal or predictive reading of the result below. "
# Predictive or causal wording about market outcomes (English and Indonesian). A match preceded closely by a
# negation ("not a prediction", "bukan penyebab") is not a claim.
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
RESEARCH_CLAIMS = {"HISTORICAL_PATTERN", "PREDICTIVE", "EXPLORATORY", "SCENARIO"}
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
DATANEED_CLAIM_INSTRUCTION = (
    "Your answer makes a claim this architecture never supports: {problem}. Results describe the delivered data and "
    "historical patterns only; they are never evidence of a cause, a prediction, a forecast or a trading signal, "
    "and the backend verified data coverage, not your calculation. Rephrase, or return response_type "
    "\"LIMITATION\"."
)
DATANEED_CLAIM_NOTICE = ("The evidence of this run does not support a causal, predictive or independently verified "
                         "reading of the result below. ")
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
REJECTED_OUTPUT_ECHO_CHARS = 4000
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
                      multi_angle: bool = False) -> str:
    """The final-response contract text: RESPONSE_CONTRACT, with the Research Plan, methodology and research findings
    fields when on (Multi-Angle Research: the per-angle findings)."""
    contract = PLAN_RESPONSE_CONTRACT if plan_confirmation else RESPONSE_CONTRACT
    if methodology:
        contract = contract.replace("The output format is already defined", METHODOLOGY_CONTRACT
                                    + "The output format is already defined")
    if multi_angle and plan_confirmation:
        contract = contract.replace("The output format is already defined", ANGLE_FINDINGS_CONTRACT
                                    + "The output format is already defined")
    elif research_findings and plan_confirmation:
        contract = contract.replace("The output format is already defined", RESEARCH_FINDINGS_CONTRACT
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
# get_research_library (C07) is registered only while multi-angle research serves the research library
DISCOVERY_TOOLS = frozenset({"get_system_capabilities", "discover_catalog", "get_catalog_details",
                             "read_catalog_rows", "get_dimension_values", "get_research_library"})
PLAN_NOTE_PREFIX = "Application note, not from the user: "
APPROVED_NOTE = (PLAN_NOTE_PREFIX + "the user approved Research Plan {plan_id}; the approval was verified. Carry out "
                 "its experiments now. Each RESEARCH data need copies research_governance from its experiment as the "
                 "RESEARCH PLAN CONFIRMATION rules say; a change beyond them needs a revised plan and a new approval. "
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
               "unclear. No data may be used in this turn; you may read the catalog. The previous plan{unverified}: "
               "{plan}")
REPLAN_NOTES = {
    "RESEARCH_PLAN_TOKEN_EXPIRED": (
        PLAN_NOTE_PREFIX + "the user's reply to Research Plan {plan_id} arrived after the plan expired, so it cannot "
        "be used. Present the plan again as RESEARCH_PLAN_CONFIRMATION for a new approval, unchanged unless the "
        "dates or data require a change. No data may be used in this turn. The expired plan: {plan}"),
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
    "cannot be recorded (it becomes NOT_RUN; the recorded angles still get their findings). Then answer from its "
    "result.")
MULTI_ANGLE_FEASIBILITY_INSTRUCTION = (
    "A multi-angle Research Plan is presented only for angles that passed check_research_feasibility in this run "
    "(FEASIBLE): {problems}. Call check_research_feasibility with one data requirement per angle of the plan you will "
    "present, then present exactly those angles; when the check cannot pass, return response_type \"LIMITATION\" "
    "saying what is missing and which alternatives exist.")
PLAN_VERSION_INSTRUCTION = {
    True: "This deployment runs research as a multi-angle Research Plan: return research_plan in its multi-angle form "
          "(plan_version, root hypothesis and angles) after check_research_feasibility, not the single-experiment form.",
    False: "This deployment does not run multi-angle Research Plans: return research_plan in its experiment form."}
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
ANGLE_FINDINGS_NOTICE = ("The interpretation of the multi-angle research result below did not match the backend's "
                         "findings; read the figures as unconfirmed. ")
# P09 (suite20 r08, 2026-09-29): "tidak mengizinkan pernyataan bahwa sudut-sudut saling mendukung" was read as an
# agreement claim because the negation stood 47 characters before the phrase and only 40 were checked. A negation
# governs the phrase when it stands in the same clause: after the last sentence or clause boundary (., !, ?, ;, :, a
# line break or a contrast word) and within CLAUSE_WINDOW characters.
CLAUSE_BOUNDARY = re.compile(r"[.!?;:\n]|\b(?:but|however|although|whereas|tetapi|namun|tapi|sedangkan|meskipun|"
                             r"walaupun)\b", re.IGNORECASE)
CLAUSE_WINDOW = 200


def negated_in_clause(text: str, start: int) -> bool:
    """Whether a negation (NEGATION_PATTERN) precedes position start in the same clause."""
    before = text[max(0, start - CLAUSE_WINDOW):start]
    boundaries = [m.end() for m in CLAUSE_BOUNDARY.finditer(before)]
    clause = before[boundaries[-1]:] if boundaries else before
    return re.search(NEGATION_PATTERN, clause, re.IGNORECASE) is not None


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
                                          interpretation=FindingInterpretation(
            answer=f"Backend status {status}: {finding.get('status_reason') or 'no reason given'}.",
            evidence=f"Validation level {finding.get('validation_level') or 'none'}; effective sample "
                     f"{sample if sample is not None else 'not available'}; evidence direction "
                     f"{finding.get('evidence_direction') or 'NONE'}.",
            usefulness="Backend-authored summary of this angle; the interpretation was not confirmed.",
            follow_up=BACKEND_FINDING_FOLLOW_UP)))
    return entries or None


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


def static_prefix_hash(payload: dict[str, Any]) -> str:
    """Fingerprint of everything a model call sends except the conversation (input): instructions, tools,
    output format, and settings, serialized in the order sent. Equal fingerprints across a run's calls mean
    the reusable prefix did not change; tools withdrawn or a final JSON format change it legitimately."""
    static = {key: value for key, value in payload.items() if key != "input"}
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
    research_attempted: bool = False
    # AI_ENABLE_ANALYSIS_PATH: the data-need mode the caller fixed for this request, and the refusals it caused
    forced_path: str | None = None
    path_refusals: int = 0
    verified_plan: Any = None
    plan_unexecuted: bool = False
    methodology_provenance: dict[str, Any] | None = None
    # Repair ledger: "tool:reason_code" -> rejections seen this run (bounded retries, see _repair_budget)
    repairs: dict[str, int] = field(default_factory=dict)
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
    # Research Plan confirmation: what this request may do (turn), which final response types and tools it allows
    # (None: every registered tool), the guard for submit_data_need_spec, and the continuation to return.
    plan_turn: str | None = None
    allowed_types: frozenset[str] = BASE_TYPES
    tool_filter: frozenset[str] | None = None
    guard: ResearchGuard = field(default_factory=lambda: ResearchGuard(required=False))
    plan_meta: dict[str, Any] = field(default_factory=dict)
    classifier: dict[str, Any] | None = None
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
        session_closer: Callable[[str, list[str]], dict[str, str]] | None = None,
        conversation_resources: Callable[[str], dict[str, Any] | None] | None = None,
        draft_reader: Callable[[str], dict[str, Any] | None] | None = None,
        derived_frequency: bool = False,
        audit_outbox: Any | None = None,
    ) -> None:
        self.settings = settings
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
        self.client = client
        self.registry = registry
        self.auditor = auditor
        # CatalogSummary (AI_CATALOG_SUMMARY_IN_PROMPT) and ProviderLogger (AI_LOG_PROVIDER), when enabled
        self.catalog_summary = catalog_summary
        self.provider_logger = provider_logger
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
        self.research_findings = submit is not None and self.plan_confirmation \
            and submit.arguments_model.__name__.endswith("Findings") and not self.multi_angle
        # caller-chosen path: a request may fix ANALYSIS or RESEARCH (both need the DataNeed flow and plan confirmation)
        self.analysis_path = settings.ai_enable_analysis_path and submit is not None and self.plan_confirmation
        if settings.ai_enable_analysis_path and not self.analysis_path:
            log_event("analysis_path_inactive", reason="needs AI_ENABLE_DATANEED and "
                                                       "AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION")
        self.system_prompt = build_system_prompt(settings.ai_enable_lookup_fact, self.dataneed,
                                                 self.plan_confirmation, period_return,
                                                 settings.ai_final_contract_in_prompt, self.catalog_protocol,
                                                 self.conversation_reuse, self.methodology, self.plan_feasibility,
                                                 self.point_in_time, self.derived_frequency,
                                                 self.research_findings, self.multi_angle,
                                                 (int(self.research_limits.get("min_angles", 2)),
                                                  int(self.research_limits.get("max_angles", 6)),
                                                  int(self.research_limits.get("min_families") or 0)))
        self.final_schema = final_response_schema(self.plan_confirmation, self.methodology, self.research_findings,
                                                  self.multi_angle)
        contract = response_contract(self.plan_confirmation, self.methodology, self.research_findings,
                                     self.multi_angle)
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
        endpoints in that order; without it OpenRouter balances load weighted to the lowest price."""
        provider: dict[str, Any] = {"require_parameters": True, "allow_fallbacks": True}
        if self.settings.ai_provider_sort:
            provider["sort"] = self.settings.ai_provider_sort
        return provider

    def run(self, request: AgentRunRequest, conversation_key: str | None = None) -> AgentRunResponse:
        """One request. conversation_key (history_mode SERVER with conversation reuse only) is derived by the
        application from the conversation and its owner; it scopes what earlier messages left in the sandbox."""
        moment = self.wall_clock()
        input_items, dropped = self._build_input(request, moment)
        state = RunState(
            request_id=request.request_id,
            started=self.clock(),
            input_items=input_items,
            history_turns_dropped=dropped,
            user_text=self._routing_text(request),
            instructions=self._instructions(),
        )
        state.audit_started_at = moment
        state.forced_path = request.analysis_path if self.analysis_path else None
        state.research = ResearchContext() if self.multi_angle else None
        if state.research is not None:
            state.research.calls_left = lambda: self.settings.ai_max_tool_calls - state.tool_calls
        for text in [turn.content for turn in request.history if turn.role == "user"] + [request.message]:
            state.context_numbers.extend(value for shown in parse_numbers(text) for value, _ in shown.candidates)
        token = current_request_id.set(request.request_id)
        context = current_run_context.set(run_context(
            moment, self.settings.analysis_timezone,
            [(turn.role, turn.content) for turn in request.history], request.message))
        guard = current_research_guard.set(state.guard)
        key = current_conversation_key.set(conversation_key if self.conversation_reuse else None)
        research = current_research_context.set(state.research)
        try:
            if self.conversation_reuse and conversation_key and request.history:
                self._add_conversation_resources(state, conversation_key)
            self._prepare_plan_turn(request, state)
            current_research_guard.set(state.guard)
            final = self._loop(state)
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
            result = AgentRunResponse(
                request_id=request.request_id,
                status=STATUS_BY_RESPONSE_TYPE[final.response_type],
                response=final,
                execution=self._execution(state),
                evidence_label=state.evidence_label,
                continuation=state.continuation,
            )
        except (RunFailure, ProviderError) as exc:
            result = self._failed(state, exc.code, str(exc))
        except Exception as exc:
            result = self._failed(
                state, "INTERNAL_ERROR", f"Unexpected orchestrator error ({type(exc).__name__})."
            )
        finally:
            current_request_id.reset(token)
            current_run_context.reset(context)
            current_research_guard.reset(guard)
            current_research_context.reset(research)
        # the closes still carry the conversation key, so an attached session that ran nothing is detached, not lost
        self._close_sessions(state)
        self._close_research_sessions(state)
        current_conversation_key.reset(key)
        if self.auditor is not None:
            try:
                self.auditor.record(request.request_id, request.message, result, state.experiments,
                                    used_sandbox=bool(state.specs or state.analyses or state.needs or state.sessions
                                                      or self._executor(state) is not None))
            except Exception:  # noqa: BLE001 - auditing never changes the response
                logger.warning(dumps({"event": "research_audit_failed", "request_id": request.request_id}))
        if self.audit_outbox is not None:
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
        arguments = self._normalized_arguments(raw_arguments)
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
                           note=RESEARCH_PATH_NOTE, verification="NOT_PRESENTED")
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
            if is_v2 != self.multi_angle:
                # a v1 plan while Multi-Angle Research is active, or a v2 plan while it is not: never executed
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
        numbers = [value for shown in parse_numbers(plan_json) for value, _ in shown.candidates]
        guard = ResearchGuard(required=True, verification=verification)
        if action in ("CANCEL", "UNRELATED"):
            state.user_text = request.message  # the reply itself, not the research question it answers
        if action == "CANCEL":
            self._set_turn(state, "CANCEL", frozenset({"ANSWER", "LIMITATION"}), frozenset(), guard,
                           note=CANCEL_NOTE)
        elif action == "APPROVE" and verified is not None and is_v2:
            state.verified_plan = verified
            self._approve_v2(state, request, verified, verification, plan_json)
            state.context_numbers.extend(numbers)
        elif action == "APPROVE" and verified is not None:
            # The approved plan becomes the guard's reference for this request only.
            state.verified_plan = verified
            self._set_turn(state, "EXECUTE_APPROVED", ALL_TYPES, None,
                           ResearchGuard(required=True, plan=verified.plan, plan_id=verified.plan_id,
                                         verification=verification),
                           note=APPROVED_NOTE.format(plan_id=verified.plan_id, plan=plan_json)
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
                plan=plan_json))
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
        tools = (DISCOVERY_TOOLS | RESEARCH_RUN_TOOLS | {"inspect_session", "get_session_output"}) \
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

    def _classify_reply(self, state: RunState, message: str, plan: Any) -> tuple[str, str | None]:
        """A free-text reply to a plan, read by one small tool-free model call constrained to APPROVE, REVISE, CANCEL
        or UNRELATED. Any failure is UNRELATED, which never approves anything."""
        payload: dict[str, Any] = {
            "model": self.settings.ai_model, "session_id": f"{state.request_id}:plan-reply",
            "instructions": CLASSIFIER_INSTRUCTIONS,
            "input": [{"role": "user", "content": dumps({"research_plan": plan_digest_v2(plan)
                                                         if isinstance(plan, ResearchPlanV2) else plan_digest(plan),
                                                         "user_reply": message[:4000]})}],
            "reasoning": {"effort": "low"}, "max_output_tokens": min(2000, self.settings.ai_max_output_tokens),
            "store": False, "provider": self._provider(),
            "text": {"format": {"type": "json_schema", "name": "research_plan_reply", "strict": True,
                                "schema": CLASSIFIER_SCHEMA}},
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
            parsed = ReplyClassification.model_validate_json(self._output_text(response).strip() or "{}")
            action, instruction = parsed.action, parsed.revision_instruction
            record["status"] = "COMPLETED"
        except Exception as exc:  # noqa: BLE001 - a failed classification approves nothing
            log_event("research_plan_classifier_failed", request_id=state.request_id, error=type(exc).__name__)
        record["latency_ms"] = int((time.monotonic() - started) * 1000)
        state.model_latency_ms += record["latency_ms"]
        state.classifier = record
        log_event("research_plan_reply_classified", request_id=state.request_id, action=action,
                  status=record["status"], latency_ms=record["latency_ms"], input_tokens=record["input_tokens"],
                  output_tokens=record["output_tokens"])
        return action, instruction

    def _loop(self, state: RunState) -> FinalResponse:
        while state.iterations < self.settings.ai_max_tool_iterations:
            if self.clock() - state.started >= self.settings.ai_max_analysis_seconds:
                raise RunFailure("ANALYSIS_TIMEOUT", "AI_MAX_ANALYSIS_SECONDS exhausted before a final answer")

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
            if usage["input_tokens"] > self.settings.ai_max_context_tokens:
                raise RunFailure("CONTEXT_LIMIT", "Provider-reported input exceeded AI_MAX_CONTEXT_TOKENS")

            if calls:
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
                for call in calls:
                    self._handle_call(state, call, truncated=truncated)
                continue

            raw = self._output_text(response)
            try:
                final = self._check_budget_limitations(state, self._turn_type(state, self._parse_final_output(raw)))
                return self._validation_gate(state, final)
            except TurnRuleError as exc:
                self._reject_final(state, raw, str(exc))
            except GateRejection as exc:
                # The model may still repair the analysis, so tools stay available for this turn.
                if raw.strip():
                    state.input_items.append({"role": "assistant", "content": raw[:REJECTED_OUTPUT_ECHO_CHARS]})
                state.input_items.append({"role": "user", "content": str(exc)})
                state.structured_only = False
                state.final_reask_sent = False
            except ValueError as exc:
                issue = str(exc)
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
        raise RunFailure("MAX_ITERATIONS", "AI_MAX_TOOL_ITERATIONS reached before a final answer")

    def _turn_tools(self, state: RunState) -> list[dict[str, Any]]:
        definitions = self.registry.definitions()
        if state.tool_filter is None:
            return definitions
        return [d for d in definitions if d["name"] in state.tool_filter]

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
            # One session per run: OpenRouter uses it as the sticky-routing key, so every call of the run
            # goes to the same provider endpoint and can reuse its implicit prompt cache.
            "session_id": state.request_id,
            "instructions": state.instructions or self.system_prompt,
            "input": state.input_items,
            "reasoning": {"effort": self.settings.ai_reasoning_effort},
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
        # Only the call itself is echoed back; provider reasoning items are never replayed.
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
        else:
            started = time.monotonic()
            outcome = self._execute(state, call_id, name, raw_arguments)
            if self.audit_outbox is not None:
                state.audit_trace.append(tool_event(
                    tool=name, call_id=call_id, iteration=state.iterations, arguments=raw_arguments,
                    output=outcome.output, ok=outcome.ok, error_code=self._rejection_code(name, outcome),
                    duration_ms=int((time.monotonic() - started) * 1000), occurred_at=self.wall_clock()))
        state.input_items.append({
            "type": "function_call_output",
            "call_id": outcome.call_id,
            "output": dumps(outcome.output),
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
        if self.multi_angle and name == "submit_data_need_spec":
            arguments = self._normalized_arguments(raw_arguments)
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
        outcome = self._repair_budget(state, call_id, name, self.registry.execute(call_id, name, raw_arguments))
        normalized = self._normalized_arguments(raw_arguments)
        if name == "submit_data_need_spec" and isinstance(normalized, dict) and normalized.get("mode") == "RESEARCH":
            state.research_attempted = True  # an attempt, whatever its outcome (M19)
        if name == "check_data_feasibility":
            self._track_feasibility(state, outcome)
        if name == "check_research_feasibility":
            self._track_research_feasibility(state, outcome)
        if name in RESEARCH_RUN_TOOLS:
            self._track_research_run(state, name, self._normalized_arguments(raw_arguments), outcome)
        if self.catalog_protocol and name in CACHEABLE_TOOLS and outcome.ok:
            result = outcome.output.get("result")
            if isinstance(result, dict):
                record(state.catalog, name, result)
            state.catalog.cache[cache_key(name, arguments)] = outcome.output
        self._track_plan_guard(state, name, outcome)
        self._track_analysis(state, name, outcome, self._normalized_arguments(raw_arguments))
        self._track_sources(state, name, self._normalized_arguments(raw_arguments), outcome)
        self._track_dataneed(state, name, self._normalized_arguments(raw_arguments), outcome)
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
        # the plan binds the last FEASIBLE draft; a later failing check does not unbind it (the model may present
        # the plan it checked), but a later FEASIBLE one replaces it
        if result.get("status") == "FEASIBLE" and result.get("draft_id"):
            state.feasible_draft = result["draft_id"]
        log_event("research_plan_feasibility", request_id=state.request_id, status=entry["status"],
                  draft_id=entry["draft_id"], issues=entry["issues"], refused=entry["requests"])

    @staticmethod
    def _track_research_feasibility(state: RunState, outcome: ToolOutcome) -> None:
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
                state.code_numbers.extend(value for shown in parse_numbers(code) for value, _ in shown.candidates)
        elif name == "complete_research_run" and result.get("research_findings_version") == FINDINGS_V2:
            run_id = result.get("research_run_id")
            values = [v for f in result.get("research_findings") or [] if isinstance(f, dict)
                      for v in self._finding_numbers(f)]
            state.analysis_values[f"research_run:{run_id}"] = {"label": "DATA_COVERAGE_VERIFIED", "values": values}
            state.analysis_values[f"research_released:{run_id}"] = {
                "label": "DATA_COVERAGE_VERIFIED", "values": released_numbers(result.get("released_contents"))}
            state.context_numbers.extend(numbers_in(result.get("angle_completion"), ints_only=True))
            state.final_status = {k: result.get(k) for k in (
                "status", "research_findings_version", "research_run_id", "plan_id", "calculation_validation",
                "angle_completion", "missing_angle_ids")}
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
        must report it. Counters live in the run state and are logged with the run (auditable)."""
        code = self._rejection_code(name, outcome)
        if code is None:
            return outcome
        key = f"{name}:{code}"
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
                state.code_numbers.extend(value for shown in parse_numbers(code) for value, _ in shown.candidates)
        elif name == "get_session_output" and result.get("released"):
            if result.get("read_mode") == "READ_RELEASED" and isinstance(result.get("origin"), dict):
                # released by an earlier completion (an earlier message, or an earlier epoch of this session)
                state.inherited[str(result.get("output_id"))] = {"name": result.get("name"), **result["origin"]}
            record = state.analysis_values.setdefault(f"released:{result.get('output_id')}",
                                                      {"label": "DATA_COVERAGE_VERIFIED", "values": []})
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
            if result.get("status") == "COMPLETED":
                state.analysis_values[f"completion:{result.get('completion_id') or session_id}"] = {
                    "label": "DATA_COVERAGE_VERIFIED", "values": released_numbers(result.get("released_contents"))}
                findings = result["final_status"].get("research_findings") or []
                if findings:  # only a sandbox with research findings v1 sends them
                    values = numbers_in(findings)
                    # a difference is often stated as a size with a direction word ("lower by 0.6"): its magnitude
                    # is the same governed figure
                    values += [abs(v) for v in values if v < 0]
                    state.analysis_values[f"findings:{result.get('completion_id') or session_id}"] = {
                        "label": "DATA_COVERAGE_VERIFIED", "values": values}
                    for finding in findings:
                        state.research_findings[str(finding.get("hypothesis_id"))] = finding
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
            lines.append("Data coverage was verified against the approved DataNeedSpec; the calculations themselves "
                         "were not independently recalculated by the backend (calculation_validation NOT_PERFORMED).")
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

    def _source_index(self, state: RunState) -> SourceIndex:
        index = SourceIndex()
        static = self.system_prompt + "\n" + "\n".join(str(d.get("description", "")) for d in self.registry.definitions())
        index.add(CONTEXT, state.context_numbers
                  + [value for shown in parse_numbers(static) for value, _ in shown.candidates])
        for fact in state.facts:
            index.add(fact["kind"], fact["values"])
        for record in state.analysis_values.values():
            if record["label"]:
                index.add(record["label"], record["values"])
        return index

    def _gate_once(self, state: RunState, kind: str, message: str) -> None:
        """Reject a final answer once per kind of problem while the model can still repair it with tools."""
        no_tools_this_turn = state.tool_filter is not None and not state.tool_filter
        repairable = kind not in state.gate_kinds_rejected and not state.tools_locked and not no_tools_this_turn
        log_event("ai_final_gate", request_id=state.request_id, iteration=state.iterations, kind=kind,
                  outcome="REJECTED_FOR_REPAIR" if repairable else "FORCED_LIMITATION",
                  reason=None if repairable else ("already_rejected" if kind in state.gate_kinds_rejected
                                                  else "tools_withdrawn" if state.tools_locked else "no_tools"),
                  detail=message[:300])
        if repairable:
            state.gate_kinds_rejected.add(kind)
            state.gate_rejections += 1
            raise GateRejection(message)

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
                            if self._executor(state) is not None else PLAN_NOT_EXECUTED_INSTRUCTION)
            state.plan_unexecuted = True
            if PLAN_NOT_EXECUTED_LINE not in final.limitations:
                final = final.model_copy(update={"limitations": [*final.limitations, PLAN_NOT_EXECUTED_LINE]})
        executor = self._executor(state)
        if executor is not None and executor.research_run_id is not None and executor.result is None:
            # found live (golden run 2026-09-29): the model stopped after recording some angles and never completed
            # the run, so no finding existed even for the recorded angles
            self._gate_once(state, "RESEARCH_RUN_INCOMPLETE", RESEARCH_RUN_INCOMPLETE_INSTRUCTION)
        if self.dataneed:
            return self._dataneed_gate(state, final)
        blocking, lines = self._gate_findings(state)
        if blocking and final.response_type == "ANSWER":
            self._gate_once(state, "ANALYSIS", VALIDATION_GATE_INSTRUCTION.format(findings="; ".join(blocking)))
            return self._forced(state, final, GATE_NOTICE, lines)

        families, plain_average = requested_statistics(state.user_text)
        usable = any(record["label"] for record in state.analysis_values.values())
        average_fact = any(f["kind"] == "DATABASE_AGGREGATE" and f["aggregation"] == "AVG" for f in state.facts)
        missing = sorted(families) if not usable else []
        if not missing and plain_average and not usable and not average_fact:
            missing = ["AVERAGE"]
        if missing and final.response_type == "ANSWER":
            names = ", ".join(missing)
            self._gate_once(state, "ROUTING", ROUTING_INSTRUCTION.format(families=names))
            return self._forced(state, final, ROUTING_NOTICE.format(families=names),
                                [f"The request needs a validated analysis ({names}); no such analysis supports this "
                                 f"response."] + lines)

        provenance = check_answer(final.answer, self._source_index(state))
        state.number_provenance = {"checked": provenance.checked, "unsupported": provenance.unsupported[:50]}
        if provenance.unsupported:
            numbers = ", ".join(provenance.unsupported[:20])
            self._gate_once(state, "PROVENANCE", PROVENANCE_INSTRUCTION.format(numbers=numbers))
            return self._forced(state, final, PROVENANCE_NOTICE.format(numbers=numbers),
                                [f"Figures without a governed source in this run: {numbers}."] + lines)

        problem = self._claim_problem(state, final.answer)
        if problem and final.response_type == "ANSWER":
            self._gate_once(state, "CLAIM", CLAIM_INSTRUCTION.format(problem=problem))
            return self._forced(state, final, CLAIM_NOTICE, [f"Unsupported claim: {problem}."] + lines)

        missing_lines = [line for line in lines if line not in final.limitations]
        if state.analyses:
            state.validation_gate = "ANNOTATED" if missing_lines else "PASSED"
        if final.response_type == "LIMITATION" and blocking:
            state.evidence_label = "NOT_VALIDATED"
        else:
            state.evidence_label = weakest(provenance.data_kinds) or weakest(self._consulted_labels(state))
        if not missing_lines:
            return final
        return final.model_copy(update={"limitations": [*final.limitations, *missing_lines]})

    def _dataneed_gate(self, state: RunState, final: FinalResponse) -> FinalResponse:
        """The answer contract of the DataNeed flow: completed analysis, routing, released-output provenance, and no
        causal or predictive claims. Each check rejects once (tools stay available), then forces LIMITATION."""
        blocking, lines = self._dataneed_findings(state)
        if blocking and final.response_type == "ANSWER":
            self._gate_once(state, "ANALYSIS", DATANEED_GATE_INSTRUCTION.format(findings="; ".join(blocking)))
            return self._forced(state, final, DATANEED_GATE_NOTICE, lines)
        families, plain_average = requested_statistics(state.user_text)
        # a released output of an earlier message read in this run is a completed analysis's result (reuse)
        run = self._research_result(state)
        usable = any(c["status"] == "COMPLETED" for c in state.completions.values()) or bool(state.inherited) \
            or (run is not None and run.get("status") == "COMPLETED")
        average_fact = any(f["kind"] == "DATABASE_AGGREGATE" and f["aggregation"] == "AVG" for f in state.facts)
        missing = sorted(families) if not usable else []
        if not missing and plain_average and not usable and not average_fact:
            missing = ["AVERAGE"]
        if missing and final.response_type == "ANSWER":
            names = ", ".join(missing)
            self._gate_once(state, "ROUTING", DATANEED_ROUTING_INSTRUCTION.format(families=names))
            return self._forced(state, final, DATANEED_ROUTING_NOTICE.format(families=names),
                                [f"The request needs a completed analysis ({names}); none supports this "
                                 f"response."] + lines)
        provenance = check_answer(final.answer, self._source_index(state))
        state.number_provenance = {"checked": provenance.checked, "unsupported": provenance.unsupported[:50]}
        if provenance.unsupported:
            numbers = ", ".join(provenance.unsupported[:20])
            self._gate_once(state, "PROVENANCE", DATANEED_PROVENANCE_INSTRUCTION.format(
                numbers=numbers, lookup=", a lookup_fact result" if self.settings.ai_enable_lookup_fact else ""))
            return self._forced(state, final, DATANEED_PROVENANCE_NOTICE.format(numbers=numbers),
                                [f"Figures without a governed source in this run: {numbers}."] + lines)
        # Multi-Angle Research: the backend recomputed the statistics, so saying so at the returned level is allowed
        problem = self._claim_problem(state, final.answer, dataneed=True, verified_ok=run is not None
                                      and run.get("calculation_validation") in VERIFIED_LEVELS)
        if problem and final.response_type == "ANSWER":
            self._gate_once(state, "CLAIM", DATANEED_CLAIM_INSTRUCTION.format(problem=problem))
            return self._forced(state, final, DATANEED_CLAIM_NOTICE, [f"Unsupported claim: {problem}."] + lines)
        final, problems = self._findings_problems(state, final)
        if problems:
            text = "; ".join(problems[:6])
            v2 = run is not None and final.response_type == "ANSWER"
            # found live (golden run 2, 2026-09-29): a multi-angle answer has four to six interpretations, and fixing
            # one problem often surfaced another, so it gets a second repair before the answer is forced to LIMITATION
            kind = "FINDINGS_2" if v2 and "FINDINGS" in state.gate_kinds_rejected else "FINDINGS"
            self._gate_once(state, kind, (ANGLE_FINDINGS_INSTRUCTION if v2 else FINDINGS_INSTRUCTION).format(
                problems=text))
            forced = self._forced(state, final, ANGLE_FINDINGS_NOTICE if v2 else FINDINGS_NOTICE,
                                  [f"Research findings problem: {text}."] + lines)
            if v2:
                # P09 (suite20 r08, 2026-09-29): four valid backend findings disappeared with the model's reading; the
                # LIMITATION keeps each angle's backend status, reason and effective sample, labelled as such
                forced = forced.model_copy(update={"research_findings": backend_findings(run)})
            return forced
        missing_lines = [line for line in lines if line not in final.limitations]
        if state.sessions or state.completions or state.inherited or run is not None:
            state.validation_gate = "ANNOTATED" if missing_lines else "PASSED"
        if final.response_type == "LIMITATION" and blocking:
            state.evidence_label = "NOT_VALIDATED"
        else:
            state.evidence_label = weakest(provenance.data_kinds)
        final = self._methodology_gate(state, final)
        if not missing_lines:
            return final
        return final.model_copy(update={"limitations": [*final.limitations, *missing_lines]})

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
        if any(not isinstance(f, AngleFindingReport) for f in given_list):
            problems.append("each entry needs angle_id, status and interpretation")
        given = {f.angle_id: f for f in given_list if isinstance(f, AngleFindingReport)}
        problems += [f"no entry for {a}" for a in backend if a not in given]
        problems += [f"{a} is not an approved angle of this run" for a in given if a not in backend]
        index = self._source_index(state)
        for angle_id, item in given.items():
            finding = backend.get(angle_id)
            if finding is None:
                continue
            status = finding.get("status")
            if item.status != status:
                problems.append(f"{angle_id}: status {item.status} differs from the backend's {status}")
            parts = item.interpretation
            text = " ".join([parts.answer, parts.evidence, parts.usefulness, parts.follow_up])
            allowed = {"SUPPORTED"} if status in ("SUPPORTED", "PARTIALLY_SUPPORTED") else set()
            problems += [f"{angle_id}: {p}" for p in self._verdict_wording(text, allowed)]
            effective = (finding.get("sample") or {}).get("effective")
            if status not in ("INVALID", "NOT_RUN") and isinstance(effective, (int, float)):
                shown = [value for numbers in parse_numbers(parts.evidence) for value, _ in numbers.candidates]
                if not any(abs(v - effective) <= max(0.051 * abs(effective), 0.006) for v in shown):
                    problems.append(f"{angle_id}: evidence does not name the effective sample")
            unsupported = check_answer(text, index).unsupported
            if unsupported:
                problems.append(f"{angle_id}: figures without a governed source: {', '.join(unsupported[:10])}")
        supported = any(f.get("status") in ("SUPPORTED", "PARTIALLY_SUPPORTED") for f in backend.values())
        problems += [f"answer: {p}" for p in self._verdict_wording(final.answer, {"SUPPORTED"} if supported
                                                                    else set())]
        agreement = ((run.get("research_synthesis_map") or {}).get("agreement") or {}).get("allowed") is True
        if not agreement:
            for match in re.finditer(AGREEMENT_WORDING, final.answer or "", re.IGNORECASE):
                if not negated_in_clause(final.answer or "", match.start()):
                    problems.append(f"answer: \"{match.group(0)}\" claims the angles agree, but the synthesis map "
                                    "allows no agreement (it needs supported angles of different method families)")
                    break
        return final, problems

    @staticmethod
    def _verdict_wording(text: str, verdicts: set[Any]) -> list[str]:
        problems = []
        for pattern, allowed, label in ((SUPPORTED_WORDING, "SUPPORTED", "supported"),
                                        (NO_EFFECT_WORDING, "NOT_SUPPORTED", "no effect")):
            if allowed in verdicts:
                continue
            for match in re.finditer(pattern, text or "", re.IGNORECASE):
                before = (text or "")[max(0, match.start() - 40):match.start()]
                if not re.search(NEGATION_PATTERN, before, re.IGNORECASE):
                    problems.append(f"\"{match.group(0)}\" states a {label} verdict the backend did not give")
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
        if is_v2 != self.multi_angle:
            self._gate_once(state, "PLAN_VERSION", PLAN_VERSION_INSTRUCTION[self.multi_angle])
            return self._forced(state, final, PLAN_VERSION_NOTICE, ["The Research Plan is not in the form this "
                                                                    "deployment runs."])
        if is_v2:
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
        if self.plan_feasibility and not is_v2 and state.feasible_draft is None:
            self._gate_once(state, "PLAN_FEASIBILITY", PLAN_FEASIBILITY_INSTRUCTION)
            return self._plan_not_feasible(state, final)
        index = self._source_index(state)
        plan_json = dumps(final.research_plan.model_dump(mode="json"))
        index.add(CONTEXT, [value for shown in parse_numbers(plan_json) for value, _ in shown.candidates])
        provenance = check_answer(final.answer, index)
        state.number_provenance = {"checked": provenance.checked, "unsupported": provenance.unsupported[:50]}
        if provenance.unsupported:
            numbers = ", ".join(provenance.unsupported[:20])
            self._gate_once(state, "PLAN_PROVENANCE", PLAN_PROVENANCE_INSTRUCTION.format(numbers=numbers))
            return self._forced(state, final, PLAN_PROVENANCE_NOTICE.format(numbers=numbers),
                                [f"Figures without a source in this Research Plan: {numbers}."])
        state.evidence_label = None
        return final

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
            problems.append(f"the plan's angles {planned} differ from the angles checked {checked}")
        low, high = self.research_limits.get("min_angles", 2), self.research_limits.get("max_angles", 6)
        if not low <= len(planned) <= high:
            problems.append(f"the plan has {len(planned)} angles; this deployment runs {low} to {high}")
        families = int(self.research_limits.get("min_families") or 0)
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
    def _claim_problem(state: RunState, answer: str, dataneed: bool = False, verified_ok: bool = False) -> str | None:
        """Causal wording is never supported by these analyses; predictive wording needs a PREDICTIVE analysis
        whose evidence was SUPPORTED. In the DataNeed flow predictive wording is never supported, and neither is a
        claim that the calculation was verified."""
        text = answer or ""

        def asserted(pattern: str, negation_inside: bool = False) -> str | None:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                before = text[max(0, match.start() - 40):match.end() if negation_inside else match.start()]
                if not re.search(NEGATION_PATTERN, before, re.IGNORECASE):
                    return match.group(0)
            return None

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
        return FinalResponse(response_type="LIMITATION", answer=notice + final.answer, clarification_question=None,
                             assumptions=final.assumptions,
                             limitations=lines + [x for x in final.limitations if x not in lines])

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
        if raw.strip():
            state.input_items.append({"role": "assistant", "content": raw[:REJECTED_OUTPUT_ECHO_CHARS]})
        # a response cut off at the output limit says so; any other re-ask keeps the unchanged instruction
        truncated = issue.startswith(TRUNCATED_FINAL_INSTRUCTION[:40])
        state.input_items.append({"role": "user", "content": (issue + " " if truncated else "")
                                  + self.finalize_instruction})
        if state.final_reask_sent:
            state.structured_only = True
        state.final_reask_sent = True
        log_event("ai_final_reask", request_id=state.request_id, iteration=state.iterations,
                  next_turn="STRICT_SCHEMA" if state.structured_only else "SAME_PREFIX",
                  looked_like_json=raw.strip().startswith(("{", "```")), output_chars=len(raw), issue=issue[:300])

    def _reject_final(self, state: RunState, raw: str, issue: str) -> None:
        state.final_rejections += 1
        limit = self.settings.ai_final_response_max_retries
        log_event("ai_final_rejected", request_id=state.request_id, iteration=state.iterations,
                  rejections=state.final_rejections, issue=issue[:300])
        if state.final_rejections > limit:
            raise RunFailure(
                "INVALID_FINAL_RESPONSE",
                f"Final response remained invalid after {limit} retries: {issue}"[:1000],
            )
        if raw:
            state.input_items.append({"role": "assistant", "content": raw[:REJECTED_OUTPUT_ECHO_CHARS]})
        state.input_items.append({
            "role": "user",
            "content": (
                f"Your previous response was rejected ({state.final_rejections}/{limit} retries): "
                f"{issue} Correct exactly this issue. Do not call tools. " + self.response_contract
            ),
        })
        state.structured_only = True

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
            "session_id": state.request_id,
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
    def _parse_final_output(raw: str) -> FinalResponse:
        candidate = raw.strip()
        if not candidate:
            raise ValueError("The response contained neither a tool call nor a final answer.")
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if len(lines) < 3 or lines[0].strip().lower() not in {"```", "```json"} or lines[-1].strip() != "```":
                raise ValueError("Final response used an invalid Markdown wrapper.")
            candidate = "\n".join(lines[1:-1]).strip()
        try:
            return FinalResponse.model_validate_json(candidate)
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
            research_plan=self._plan_execution(state),
            analysis_path=AnalysisPathExecution(requested=state.forced_path, mismatches_refused=state.path_refusals)
            if state.forced_path else None,
        )

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
