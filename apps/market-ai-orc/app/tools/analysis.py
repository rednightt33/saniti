"""Governed analysis tools: get_dataset_manifest, create_analysis_spec, run_python_analysis,
get_analysis_result.

market-ai-orc never executes model-generated Python. Every analysis follows the Execution
Validation Gate implemented in market-python-sandbox:

1. create_analysis_spec: the model proposes a structured Analysis Spec. This module adds what the
   model must not control: the user's own messages from this run, the run's reference time, and
   the reference time zone. The sandbox checks the spec against those messages and stores an
   approved spec immutably (spec_id).
2. run_python_analysis: code runs against an approved spec_id and logical inputs bound to
   governed dataset_ids. The sandbox validates inputs before and outputs after execution.
3. Results carry execution_status and validation_status separately; the orchestrator enforces
   what the final answer may claim from them.

This module holds only the sandbox's bearer key; it never sees dataset URLs, bucket or database
credentials, or complete result tables. The request models must stay aligned with
apps/market-python-sandbox/app/models.py and app/spec.py (tests enforce it).
"""
from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .registry import ToolError, ToolSpec
from .request_data import GovernorClient, current_request_id

DATASET_ID_PATTERN = r"^ds_[0-9a-f]{24}$"
ANALYSIS_ID_PATTERN = r"^ana_[0-9a-f]{24}$"
SPEC_ID_PATTERN = r"^spec_[0-9a-f]{24}$"
IDENT_PATTERN = r"^[a-z][a-z0-9_]{0,39}$"
COLUMN_PATTERN = r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$"
TABLE_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,62}$"
OUTPUT_NAME_PATTERN = r"^[A-Za-z0-9_\-. ]{1,80}$"
TICKER_PATTERN = r"^[A-Z0-9]{2,6}$"
OutputType = Literal["TABLE", "METRICS", "CHART", "ARTIFACT"]
Provenance = Literal["USER_EXPLICIT", "USER_CLARIFIED", "APPROVED_DEFAULT", "AI_INFERRED"]
Method = Literal["SMA", "ROLLING_STD", "ROLLING_ZSCORE", "RETURN", "FORWARD_RETURN", "RSI", "ROLLING_CORRELATION",
                 "CORRELATION", "EVENT_STUDY", "PERIOD_RETURN", "PERIOD_STAT", "GROUP_AGGREGATE", "GROUP_CORRELATION",
                 "CUSTOM"]
ScopeProvenance = Literal["USER_EXPLICIT", "USER_CLARIFIED", "CATALOG_RESOLVED", "APPROVED_DEFAULT", "AI_INFERRED"]
SUBJECT_ID_PATTERN = r"^[A-Z][A-Z0-9_]{1,39}$"
ENTITY_VALUE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,19}$"
BUNDLE_ID_PATTERN = r"^bundle_[0-9a-f]{24}$"
Family = Literal["RSI", "SMA", "STD", "ZSCORE", "RETURN", "FORWARD_RETURN", "CORRELATION", "EVENT_STUDY"]
EvidenceStandard = Literal["CALCULATION", "SCREEN", "DESCRIPTIVE", "HISTORICAL_PATTERN", "EXPLORATORY", "PREDICTIVE",
                           "SCENARIO"]
DIAGNOSTIC_CHARS = 1000
MAX_USER_MESSAGES = 12
MAX_MESSAGE_CHARS = 8000
# Next step for a request the sandbox refused before creating an analysis.
REJECTION_ACTIONS = {"QUEUE_FULL": "RETRY_LATER", "INVALID_REQUEST": "REVISE_ANALYSIS",
                     "SANDBOX_ISOLATION_UNAVAILABLE": "REPORT_LIMITATION", "SPEC_NOT_FOUND": "CREATE_ANALYSIS_SPEC",
                     "REQUEST_BUDGET_EXCEEDED": "REPORT_LIMITATION"}


@dataclass(frozen=True)
class RunContext:
    """Set by the orchestrator for each run; the model cannot change any of it."""

    reference_time: datetime
    timezone: str
    messages: tuple[tuple[str, str], ...]  # (role, content), oldest first, ending with the current message


current_run_context: contextvars.ContextVar[RunContext | None] = contextvars.ContextVar("current_run_context",
                                                                                         default=None)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetDatasetManifestArgs(Strict):
    dataset_id: str = Field(pattern=DATASET_ID_PATTERN, description="dataset_id from a DATASET_READY result.")


# ---------------------------------------------------------------- create_analysis_spec

class SpecSubject(Strict):
    data_domain: str = Field(pattern=SUBJECT_ID_PATTERN, description="The tables' data_domain from discover_catalog.")
    entity_type: str = Field(pattern=SUBJECT_ID_PATTERN, description="The tables' entity_type from discover_catalog.")
    asset_type: str | None = Field(pattern=SUBJECT_ID_PATTERN,
                                   description="The tables' asset_type from discover_catalog; null when it has none.")


class SpecInput(Strict):
    name: str = Field(pattern=IDENT_PATTERN, description="Logical input name, e.g. prices.")
    source_table: str = Field(pattern=TABLE_PATTERN, description="Catalog table the data comes from.")
    role: Literal["PRIMARY_DATA", "UNIVERSE", "REFERENCE"] = Field(
        description="PRIMARY_DATA (measured observations), UNIVERSE (defines the entities in scope), or REFERENCE "
                    "(unscoped lookup table).")
    entity_column: str | None = Field(description="null: the catalog entity_column.")
    date_column: str | None = Field(description="null: the catalog time_column.")
    columns: list[str] = Field(min_length=1, max_length=50, description="Columns the analysis needs.")


class SpecRelationship(Strict):
    relationship_id: int = Field(ge=1, description="Catalog relationship_id joining two input tables.")


class SpecScopePredicate(Strict):
    input: str = Field(pattern=IDENT_PATTERN, description="The input whose table holds the column.")
    table: str = Field(pattern=TABLE_PATTERN)
    column: str = Field(pattern=COLUMN_PATTERN, description="A filterable catalog column.")
    operator: Literal["EQ", "NEQ", "IN", "GT", "GTE", "LT", "LTE", "IS_NULL", "IS_NOT_NULL"]
    value: str | int | float | bool | list[str | int | float] | None = Field(
        description="Scalar; a list for IN; null for IS_NULL / IS_NOT_NULL. Use the exact catalog data value.")
    provenance: ScopeProvenance
    user_text: str | None = Field(max_length=200, description="CATALOG_RESOLVED: the user's words this value "
                                                              "resolves, verbatim; else null.")


class SpecScope(Strict):
    selection_type: Literal["ALL_ELIGIBLE", "ENTITY_LIST", "ATTRIBUTE_FILTER"]
    entities: list[str] | None = Field(max_length=200, description="ENTITY_LIST: entity values; else null.")
    predicates: list[SpecScopePredicate] | None = Field(
        max_length=8, description="ATTRIBUTE_FILTER: 1-8 predicates, all must hold; else null.")
    provenance: Provenance
    default_id: str | None


class SpecTimeScope(Strict):
    mode: Literal["EXPLICIT_DATES", "TRAILING", "TRADING_DAYS", "LATEST"]
    start: str | None = Field(description="YYYY-MM-DD for EXPLICIT_DATES, else null.")
    end: str | None = Field(description="YYYY-MM-DD for EXPLICIT_DATES, else null.")
    unit: Literal["DAY", "WEEK", "MONTH", "YEAR"] | None = Field(description="TRAILING calendar unit, else null.")
    count: int | None = Field(ge=1, le=3650, description="Units for TRAILING, dates for TRADING_DAYS, else null.")
    frequency: Literal["1D", "1W", "1M"] = Field(description="Must be a supported_frequencies value of the tables.")
    provenance: Provenance
    default_id: str | None


class SpecParam(Strict):
    name: str = Field(pattern=IDENT_PATTERN)
    value: int | float | str | bool | list[str | int | float] | None = Field(
        description="The parameter value; null applies the method's approved default (recorded as APPROVED_DEFAULT).")
    provenance: Provenance
    default_id: str | None


class SpecPredicate(Strict):
    calculation: str = Field(pattern=IDENT_PATTERN)
    op: Literal[">", ">=", "<", "<=", "==", "!="]
    value: float
    provenance: Provenance
    default_id: str | None


class SpecGroupKey(Strict):
    input: str = Field(pattern=IDENT_PATTERN, description="Input holding the grouping column.")
    column: str = Field(pattern=COLUMN_PATTERN)


class SpecSegmentPredicate(Strict):
    input: str = Field(pattern=IDENT_PATTERN, description="The input whose table holds the column.")
    column: str = Field(pattern=COLUMN_PATTERN, description="A filterable catalog column.")
    operator: Literal["EQ", "NEQ", "IN", "GT", "GTE", "LT", "LTE", "IS_NULL", "IS_NOT_NULL"]
    value: str | int | float | bool | list[str | int | float] | None = Field(
        description="Scalar; a list for IN; null for IS_NULL / IS_NOT_NULL. Use the exact catalog data value.")


class SpecSegment(Strict):
    label: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.&()/-]{0,39}$", description="The group's key value.")
    predicates: list[SpecSegmentPredicate] = Field(min_length=1, max_length=4, description="All must hold.")
    provenance: ScopeProvenance
    user_text: str | None = Field(max_length=200, description="CATALOG_RESOLVED: the user's words this segment "
                                                              "stands for, verbatim; else null.")


class SpecDataPolicies(Strict):
    zero_denominator: Literal["NULL", "ZERO"]
    missing: Literal["PROPAGATE"]


class SpecCalculation(Strict):
    id: str = Field(pattern=IDENT_PATTERN)
    method: Method
    dataset: str = Field(pattern=IDENT_PATTERN, description="Logical input name.")
    columns: list[str] = Field(max_length=4, description="Input columns ([] when input_calculation is set).")
    input_calculation: str | None = Field(description="id of an earlier calculation used as input, or null.")
    params: list[SpecParam] = Field(max_length=20)
    output_column: str = Field(pattern=COLUMN_PATTERN, description="Column holding this value in the outputs.")
    formula: str | None = Field(max_length=1000, description="Required for CUSTOM; null for other methods.")
    time_alignment: str | None = Field(max_length=300, description="Required for CUSTOM; null otherwise.")
    covers: list[Family] | None = Field(description="CUSTOM only: requested method families it implements.")
    signal: list[SpecPredicate] | None = Field(
        max_length=6, description="EVENT_STUDY only: predicates on earlier trailing calculations that define an event "
                                  "(all must hold at t); null otherwise.")
    expression: str | None = Field(
        max_length=500, description="CUSTOM only: recalculable expression over the input columns and earlier "
                                    "calculation ids, e.g. rolling_sum(net_value, 20) / rolling_sum(value, 20); null "
                                    "for free-form code that cannot be recalculated.")
    formula_refs: list[str] | None = Field(max_length=5, description="CUSTOM only: AI_formula_reference ids "
                                                                    "(CALC_###) the formula adapts; null if none.")
    meaning: str | None = Field(max_length=300, description="CUSTOM only: what the value means financially.")
    unit: str | None = Field(max_length=40, description="CUSTOM only: unit of the value (ratio, IDR, percent).")
    data_policies: SpecDataPolicies | None = Field(
        description="CUSTOM only: zero_denominator NULL (default) or ZERO; missing PROPAGATE.")
    group_by: list[SpecGroupKey] | None = Field(
        max_length=3, description="GROUP_AGGREGATE only: 1-3 catalog grouping columns (group_by_allowed); else null.")
    segments: list[SpecSegment] | None = Field(
        max_length=10, description="GROUP_AGGREGATE only, instead of group_by: labelled groups defined by predicates "
                                   "(for groups one column cannot express); else null.")
    provenance: Provenance
    default_id: str | None

    @field_validator("formula_refs")
    @classmethod
    def _formula_refs(cls, values: list[str] | None) -> list[str] | None:
        import re

        if values and any(not re.fullmatch(r"CALC_[0-9]{3}", v) for v in values):
            raise ValueError("formula_refs must be AI_formula_reference ids like CALC_028")
        return values


class SpecRanking(Strict):
    calculation: str = Field(pattern=IDENT_PATTERN)
    direction: Literal["ASC", "DESC"]
    limit: int = Field(ge=1, le=100)
    tie_policy: Literal["INCLUDE_EXACTLY_N_STABLE", "INCLUDE_TIES"]
    provenance: Provenance
    default_id: str | None


class SpecOutput(Strict):
    name: str = Field(pattern=OUTPUT_NAME_PATTERN, description="The name the code passes to emit_table.")
    grain: Literal["ENTITY_DATE", "ENTITY", "ENTITY_PAIR", "GROUP", "GROUP_DATE", "GROUP_PAIR", "SUMMARY",
                   "UNSPECIFIED"]
    coverage: Literal["FULL", "SELECTION"]
    calculations: list[str] = Field(max_length=12)
    selection: list[SpecPredicate] | None = Field(max_length=6, description="Predicates for SELECTION, else null.")
    entity_column: str | None
    date_column: str | None
    pair_columns: list[str] | None = Field(description="Two entity columns for ENTITY_PAIR, else null.")
    key_columns: list[str] | None = Field(max_length=4, description="The output's key columns (entity, grouping "
                                                                    "columns, date); null derives them.")
    ranking: SpecRanking | None = Field(description="Top-N of one calculation over every in-scope candidate "
                                                    "(ENTITY or GROUP grain, coverage SELECTION); else null.")


class SpecExclusion(Strict):
    rule: Literal["MIN_OBSERVATIONS_IN_PERIOD", "MAX_STALENESS_DAYS", "EXCLUDE_TICKERS"]
    value: int | list[str]
    provenance: Provenance
    default_id: str | None


class SpecHypothesis(Strict):
    id: str = Field(pattern=r"^H[0-9]{1,2}$", description="H1, H2, ...")
    statement: str = Field(min_length=1, max_length=500)


class SpecHoldout(Strict):
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="First out-of-sample date (YYYY-MM-DD).")
    end: str | None = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="Last out-of-sample date, or null.")


class SpecResearch(Strict):
    evidence_standard: EvidenceStandard
    objective: str = Field(min_length=1, max_length=500)
    hypothesis: SpecHypothesis | None
    method_ref: str | None = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$",
                                   description="AI_research_catalog method_id used as methodology reference, or null.")
    followup_of: str | None = Field(pattern=SPEC_ID_PATTERN,
                                    description="spec_id of the completed experiment this follows up, or null.")
    candidates: int | None = Field(ge=1, le=1_000_000,
                                   description="Conditions, lags or combinations this experiment evaluates; null = 1.")
    holdout: SpecHoldout | None


class CreateAnalysisSpecArgs(Strict):
    spec_version: Literal["2.0"]
    analysis_type: Literal["ANALYSIS", "RESEARCH"] = Field(
        description="ANALYSIS for a calculation, statistic, ranking or aggregate (research null); RESEARCH for a "
                    "historical-pattern, predictive, exploratory or scenario question (research block required).")
    question: str = Field(min_length=1, max_length=1000, description="The analytical request, restated.")
    subject: SpecSubject
    inputs: list[SpecInput] = Field(min_length=1, max_length=4)
    relationships: list[SpecRelationship] = Field(max_length=5, description="Catalog relationships joining input "
                                                                            "tables (needed when a scope predicate "
                                                                            "is on another input's table).")
    scope: SpecScope
    time_scope: SpecTimeScope | None = Field(
        description="null for static reference data (no period invented); required when any input is dated.")
    calculations: list[SpecCalculation] = Field(min_length=1, max_length=12)
    outputs: list[SpecOutput] = Field(min_length=1, max_length=8)
    exclusion_rules: list[SpecExclusion] = Field(max_length=8)
    research: SpecResearch | None = Field(
        description="null for a plain calculation, screen, or description. For research (a historical pattern, "
                    "predictive, exploratory, or scenario question) the experiment's evidence standard, hypothesis, "
                    "and follow-up link; the Research Governor approves it against the run's budget.")


# ---------------------------------------------------------------- run_python_analysis

class InputBindingArgs(Strict):
    name: str = Field(pattern=IDENT_PATTERN, description="A logical input name from the approved spec.")
    dataset_ids: list[str] = Field(min_length=1, max_length=8,
                                   description="DATASET_READY dataset_ids holding this input (same table and columns).")
    duplicate_policy: Literal["ERROR_ON_CONFLICT", "PREFER_LATEST_SNAPSHOT"]

    @field_validator("dataset_ids")
    @classmethod
    def _dataset_ids(cls, values: list[str]) -> list[str]:
        import re

        if any(not re.fullmatch(DATASET_ID_PATTERN, value) for value in values):
            raise ValueError("each dataset_id must match ^ds_[0-9a-f]{24}$")
        if len(set(values)) != len(values):
            raise ValueError("dataset_ids must be unique")
        return values


class RunPythonAnalysisArgs(Strict):
    spec_id: str = Field(pattern=SPEC_ID_PATTERN, description="spec_id of an approved analysis spec.")
    input_bundle_id: str = Field(pattern=BUNDLE_ID_PATTERN,
                                 description="input_bundle_id from prepare_analysis_data for this spec_id.")
    python_code: str = Field(min_length=1, max_length=20000, description="Python source to run in the sandbox.")
    expected_outputs: list[OutputType] = Field(
        min_length=1, max_length=4, description="Output types the code will emit (unique).")

    @field_validator("expected_outputs")
    @classmethod
    def _unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("expected_outputs must be unique")
        return values


class GetAnalysisResultArgs(Strict):
    analysis_id: str = Field(pattern=ANALYSIS_ID_PATTERN, description="analysis_id from run_python_analysis.")


MANIFEST_DESCRIPTION = (
    "Describe exactly what one governed dataset contains (a dataset_id from prepare_analysis_data or a DATASET_READY "
    "result): columns and types, row count, source tables, requested versus actual date range, entities "
    "present and missing, completeness, checksum, numeric-precision warnings, and expiry. This is the "
    "extracted dataset itself, not the catalog's coverage estimate. status is AVAILABLE, or explicitly "
    "DATASET_EXPIRED or DATASET_NOT_FOUND."
)

SPEC_DESCRIPTION = (
    "Required before any analysis: propose the one machine-readable contract (Analysis Spec V2) of the calculation. "
    "The service checks every table, column, relationship, frequency and subject against the catalog and the spec "
    "against the user's own messages, and returns APPROVED (with spec_id), APPROVED_WITH_UNVERIFIED (spec_id plus "
    "interpretations the user did not state, which must be disclosed), ANALYSIS_SPEC_MISMATCH (fix the spec to match "
    "the request; never change the request to fit limits), NEEDS_CLARIFICATION (ask the user), INVALID_SPEC (fix "
    "each problem; its code is in parentheses), or for RESEARCH specs the Research Governor's REPLAN_REQUIRED or "
    "REJECTED. The same spec again returns the same spec_id. After approval call prepare_analysis_data(spec_id): the "
    "backend compiles and extracts exactly the approved scope; you never restate the scope as a data request. "
    "subject and source tables: copy data_domain, entity_type and asset_type from discover_catalog; every "
    "PRIMARY_DATA and UNIVERSE input table must have that subject. scope: ALL_ELIGIBLE (every entity in the "
    "source), ENTITY_LIST (entities), or ATTRIBUTE_FILTER (predicates on filterable catalog columns, all must hold; "
    "e.g. a classification column EQ a value). A predicate names the input whose table has the column; when it "
    "restricts another input (for example prices restricted by a column of a reference table), list the catalog "
    "relationship_id that joins the two tables. Use the exact data value; provenance CATALOG_RESOLVED with "
    "user_text = the user's own words when you mapped words to a catalog value. time_scope: null for static "
    "reference data (a count per group of a table without a time column); otherwise mode, dates or count/unit, and a "
    "frequency the tables support. "
    "provenance per requirement: USER_EXPLICIT only for what the user stated, USER_CLARIFIED for answers to your "
    "clarification question, APPROVED_DEFAULT with default_id for a documented default, AI_INFERRED otherwise. "
    "Definitions follow TA-Lib first, then AI_formula_reference, then your own formula (CUSTOM). "
    "Defaults: DEFAULT_TRAILING_CALENDAR_WINDOW ('last N months' = TRAILING), DEFAULT_TRADING_DAYS, DEFAULT_LATEST, "
    "DEFAULT_MONTH_WITHOUT_YEAR, DEFAULT_UNIVERSE_ALL_IN_SOURCE ('all stocks'), DEFAULT_FREQUENCY_DAILY, "
    "DEFAULT_ROLLING_WINDOW_UNIT, DEFAULT_STD_DDOF (0, TA-Lib STDDEV), DEFAULT_ZSCORE_DDOF (1), "
    "DEFAULT_ZSCORE_INCLUDES_CURRENT (true for a price, false for a return series), DEFAULT_RETURN_KIND (SIMPLE), "
    "DEFAULT_RETURN_HORIZON (1), DEFAULT_RETURN_AS_PERCENT (false), DEFAULT_RSI_PERIOD (14), DEFAULT_RSI_SMOOTHING "
    "(WILDER, TA-Lib), DEFAULT_FORWARD_RETURN_ENTRY (NEXT_OPEN: close[t+h] / open[t+1] - 1; SIGNAL_CLOSE only when "
    "the user asks), DEFAULT_CORRELATION_METHOD, DEFAULT_CORRELATION_TRANSFORM (SIMPLE_RETURN), "
    "DEFAULT_CORRELATION_MIN_OVERLAP, DEFAULT_EVENT_OVERLAP_POLICY (NON_OVERLAPPING), DEFAULT_EVENT_BASELINE "
    "(ALL_ELIGIBLE), DEFAULT_EVENT_MIN_EVENTS (30), DEFAULT_ZERO_DENOMINATOR (NULL), DEFAULT_PERIOD_RETURN_BASE "
    "(PREVIOUS_OBSERVATION), DEFAULT_GROUP_MISSING_KEY (SEPARATE_GROUP), DEFAULT_GROUP_UNKNOWN_VALUES ([]), "
    "DEFAULT_GROUP_MIN_OBSERVATIONS (1), DEFAULT_RANK_TIE_POLICY (INCLUDE_EXACTLY_N_STABLE), DEFAULT_PERIOD_STD_DDOF "
    "(1, not annualized), DEFAULT_PERIOD_STAT_MIN_OBSERVATIONS (1), DEFAULT_SERIES_ALIGNMENT (COMMON_DATES: no "
    "forward fill, lag 0). Omitted method parameters get their default. "
    "Methods with independent recalculation (params): SMA(window), ROLLING_STD(window, ddof), "
    "ROLLING_ZSCORE(window, ddof, include_current), RETURN(horizon, kind SIMPLE|LOG, as_percent), "
    "PERIOD_RETURN(kind, as_percent, base PREVIOUS_OBSERVATION|FIRST_IN_PERIOD; the change over the whole period, "
    "one column), FORWARD_RETURN(horizon, kind, as_percent, entry NEXT_OPEN|SIGNAL_CLOSE; columns [close, open] for "
    "NEXT_OPEN, [close] for SIGNAL_CLOSE), RSI(period), ROLLING_CORRELATION(window, method, transform; two columns), "
    "CORRELATION(method, transform, min_overlap; ENTITY_PAIR output over an ENTITY_LIST scope), "
    "PERIOD_STAT(function MEAN|MEDIAN|STD|MIN|MAX|SUM|COUNT, ddof for STD, min_observations; one column or "
    "input_calculation; the statistic of each entity's observations inside the period, e.g. volatility = STD of a "
    "1-observation RETURN; never substitute a stored annualized or rolling feature column), "
    "GROUP_AGGREGATE(function COUNT|COUNT_DISTINCT|SUM|AVG|MEDIAN|MIN|MAX, per_date, missing_group_policy "
    "SEPARATE_GROUP|EXCLUDE, unknown_group_values [values treated as unknown], min_observations; one column or "
    "input_calculation = a per-entity calculation such as PERIOD_RETURN or PERIOD_STAT; group_by = catalog grouping "
    "columns of any input, mapped to entities by entity column; or segments = [{label, predicates [{input, column, "
    "operator, value}], provenance, user_text}] when the groups are defined on different columns (an entity belongs "
    "to every segment whose predicates all hold; key column segment); per_date true gives one aligned series per "
    "group), GROUP_CORRELATION(method, min_overlap, alignment; no columns; input_calculation = a per_date "
    "GROUP_AGGREGATE with one key or segments; GROUP_PAIR output with key_columns [<key>_a, <key>_b], one row per "
    "pair of groups; also emit the GROUP_DATE series). Averaging a return across entities over a period: say which "
    "return the user asked for (PERIOD_RETURN = the return over the whole period, or PERIOD_STAT MEAN of a daily "
    "RETURN); when the user did not say, the service returns NEEDS_CLARIFICATION. "
    "EVENT_STUDY(min_events, overlap_policy, baseline; no columns; input_calculation = the FORWARD_RETURN outcome; "
    "signal = predicates on earlier trailing calculations; one SUMMARY output with columns segment, event_count, mean, "
    "median, hit_rate, baseline_count, baseline_mean, baseline_median, delta_mean, censored_count, "
    "overlapping_dropped and rows ALL, plus IN_SAMPLE and OUT_OF_SAMPLE when research.holdout is set). "
    "Any other formula is CUSTOM with formula, time_alignment, covers, and ideally an expression, which is "
    "recalculated independently: input columns and earlier calculation ids with + - * / **, comparisons, & | ~, abs, "
    "log, exp, sqrt, sign, min, max, where(c, a, b), lag(x, k), rolling_sum(x, n), rolling_mean(x, n) (past only). "
    "A CUSTOM without an expression is never independently recalculated (optional warmup_observations param). Add "
    "formula_refs (CALC_### ids it adapts), meaning, and unit to CUSTOM. Chain a method on another calculation with "
    "input_calculation (e.g. ROLLING_STD of a RETURN). "
    "outputs: each TABLE the code emits, by name. grain ENTITY_DATE (one row per entity and date in the period), "
    "ENTITY (one row per entity at its latest observation in the period), ENTITY_PAIR, GROUP (one row per group; "
    "key_columns = the group_by columns or [segment]), GROUP_DATE (per group and date; per_date true), GROUP_PAIR "
    "(GROUP_CORRELATION), SUMMARY (EVENT_STUDY), or "
    "UNSPECIFIED (not checkable). coverage FULL (every entity/date/group in scope) or SELECTION (rows meeting the "
    "selection predicates, e.g. RSI < 30, or the top-N of a ranking {calculation, direction, limit, tie_policy}). "
    "Only declared outputs with a checkable grain can pass validation. "
    "research: null when analysis_type is ANALYSIS. For RESEARCH set evidence_standard (HISTORICAL_PATTERN and "
    "PREDICTIVE need a hypothesis and an EVENT_STUDY; PREDICTIVE also a holdout; EXPLORATORY for bounded exploration; "
    "SCENARIO for hypotheticals), objective, hypothesis {id H1.., statement}, method_ref (AI_research_catalog "
    "method_id), candidates (conditions or lags tested), and followup_of (spec_id of a completed experiment on the "
    "same hypothesis) for a follow-up."
)

PREPARE_DESCRIPTION = (
    "Prepare the governed input data of an approved spec: the backend compiles the spec's approved scope (tables, "
    "relationships, predicates, entities, warm-up date range) into data requests, the SQL Governor validates and "
    "extracts them, and large extractions are split into date partitions without changing the scope. Returns "
    "status READY with input_bundle_id (pass it to run_python_analysis) and, per logical input, row counts and "
    "completeness; or NEEDS_NARROWING / REJECTED with a structured rejection (stage, reason_code, observed, limit, "
    "allowed_actions, forbidden_actions, retryable). Never change the user's scope to pass a limit: revise the spec "
    "only when the rejection says the spec itself is wrong, otherwise report the limitation."
)

RUN_DESCRIPTION = (
    "Run Python analysis in an isolated sandbox against an approved spec_id and the input_bundle_id that "
    "prepare_analysis_data returned for it (the prepared datasets are bound to the spec's logical inputs by the "
    "backend). The code runs without network, subprocess, or file access outside its workspace. The helper module "
    "saniti and its functions, pandas as pd and numpy as np are already imported. Inputs "
    "are DuckDB views named after the logical inputs. load(name, columns=[...]) returns the whole input as a "
    "pandas DataFrame sorted by entity and date (date columns hold datetime.date objects; use pd.to_datetime for "
    "Timestamps), including the warm-up history before the analysis period; "
    "sql('SELECT ... FROM prices WHERE ...', [params]) runs DuckDB SQL (filter and aggregate in SQL; large results "
    "are refused). Compute every indicator per entity on that full date-sorted history, then keep the period rows "
    "with out = df[in_period(df)], which applies the approved period (including LATEST and trading-day periods) "
    "the same way the validator does; never cut the input to the period before computing. INPUTS lists each "
    "input's columns; SPEC is the approved spec; ANALYSIS_START, ANALYSIS_END and REFERENCE_DATE are the resolved "
    "period. Write intermediate Parquet only to intermediate_path(name). Libraries: numpy 2, pandas 3 "
    "(groupby().apply drops the grouping columns; prefer groupby()[col].transform), polars, pyarrow, duckdb, scipy, "
    "statsmodels, matplotlib, TA-Lib (import talib). Helpers: iter_series, prepare_panel, panel_check, add_warning. "
    "Emit every spec output with emit_table(output_name, dataframe, description='') (no other arguments); the "
    "dataframe's columns must include the output's key columns (entity_column, date_column, pair_columns, or the "
    "group key columns) and the output_column of each calculation it lists; a ranked output holds exactly its top-N "
    "rows. Also emit_metrics(dict), emit_chart(figure, name, title, "
    "description), emit_artifact(name, data, format). print() is not a result, and nothing the code reports about "
    "itself counts as evidence. The result has execution_status and validation_status (PASS, INCOMPLETE, FAILED, "
    "UNVERIFIED) with validation_level, reason_codes, expected_scope, actual_scope and validation_evidence (including "
    "scope.lineage: the executed scope equals the approved scope); a "
    "CALCULATION_MISMATCH can carry a diagnosis naming the parameter or procedure the values match. "
    "evidence_assessment says what the validated evidence supports for the spec's evidence standard (decision "
    "SUPPORTED, PARTIALLY_SUPPORTED, INSUFFICIENT_EVIDENCE or INVALID, evidence_level, checks, the validator's own "
    "statistics) and the reporting_constraints your answer must follow. CUSTOM code without an expression is re-run "
    "on data truncated at a cutoff date: values that change reveal look-ahead (TEMPORAL_LEAKAGE_DETECTED)."
)

RESULT_DESCRIPTION = (
    "Get the execution_status, validation_status, validation_level, and structured outputs of a "
    "run_python_analysis job. Waits briefly while it runs."
)


def _compact_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for item in items[:25]:
        entry = {k: v for k, v in item.items() if k not in ("examples", "missing_examples", "unexpected_examples")}
        for key in ("examples", "missing_examples", "unexpected_examples"):
            if item.get(key):
                entry[key] = item[key][:3]
        compact.append(entry)
    return compact


def model_view(result: dict[str, Any]) -> dict[str, Any]:
    """The analysis record as the model sees it: no limits, deployment ids, or usage internals."""
    lineage = dict(result.get("lineage") or {})
    lineage.pop("limits", None)
    lineage.pop("deployment_id", None)
    view = {key: result.get(key) for key in (
        "analysis_id", "spec_id", "execution_status", "validation_status", "validation_level", "reason_codes",
        "next_action", "retry_after_seconds", "question", "inputs", "expected_outputs", "runtime_ms",
        "expected_scope", "actual_scope", "outputs", "warnings", "error", "outputs_expire_at", "evidence_assessment")}
    if (result.get("leakage_check") or {}).get("result"):
        view["leakage_check"] = {k: result["leakage_check"].get(k) for k in ("result", "cutoff", "reason")}
    view["validation_evidence"] = _compact_evidence(result.get("validation_evidence") or [])
    view["derived_features"] = [
        {k: f.get(k) for k in ("name", "method", "parameters", "output_grain", "independent_check_result", "status",
                               "statistical_validation", "formula_status")} for f in (result.get("derived_features") or [])]
    if result.get("database_features"):
        view["database_features"] = result["database_features"]
    view["lineage"] = lineage
    diagnostics = result.get("diagnostics") or {}
    if diagnostics:
        view["diagnostics"] = {k: str(v)[-DIAGNOSTIC_CHARS:] for k, v in diagnostics.items() if v}
    return {k: v for k, v in view.items() if v is not None and v != []}


def spec_view(result: dict[str, Any]) -> dict[str, Any]:
    keys = ("status", "spec_id", "analysis_type", "validation_profile", "scope_sha256", "reference", "resolved_period",
            "required_input", "data_plan", "output_contract", "mismatches", "unverified_requirements",
            "clarification_needed", "problems", "problem_codes", "next_action", "governor", "replayed")
    view = {k: result.get(k) for k in keys if result.get(k) not in (None, [])}
    if result.get("derived_features"):
        view["derived_features"] = [f.get("name") for f in result["derived_features"]]
    if result.get("convention_notes"):
        view["convention_notes"] = result["convention_notes"]
    return view


class SandboxClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float, poll_wait_seconds: int,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.poll_wait_seconds = poll_wait_seconds
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport,
                                    headers={"Authorization": f"Bearer {api_key}"})

    def ready(self) -> bool:
        try:
            response = self._client.get("/ready", timeout=5)
            return response.status_code == 200 and response.json().get("status") == "ready"
        except (httpx.HTTPError, ValueError):
            return False

    def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ToolError("The Python sandbox did not answer in time; use get_analysis_result if an "
                            "analysis_id was returned earlier.") from exc
        except httpx.HTTPError as exc:
            raise ToolError("The Python sandbox is unreachable.") from exc

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ToolError("The Python sandbox returned an invalid response.") from exc
        if not isinstance(body, dict):
            raise ToolError("The Python sandbox returned an invalid response.")
        return body

    @staticmethod
    def _request_id() -> str:
        return current_request_id.get() or f"orc-{uuid.uuid4().hex[:16]}"

    def _rejected(self, response: httpx.Response, body: dict[str, Any]) -> dict[str, Any]:
        error = body.get("error") if isinstance(body.get("error"), dict) else None
        if response.status_code in (422, 429, 503) and error:
            rejected = {"status": "REJECTED", "error": {"code": error.get("code"), "message": error.get("message")},
                        "next_action": REJECTION_ACTIONS.get(error.get("code"), "REPORT_LIMITATION")}
            if error.get("details"):
                rejected["error"]["details"] = error["details"][:15]
            if body.get("retry_after_seconds"):
                rejected["retry_after_seconds"] = body["retry_after_seconds"]
            return rejected
        raise ToolError(f"The Python sandbox is unavailable (HTTP {response.status_code}).")

    def create_spec(self, arguments: CreateAnalysisSpecArgs) -> dict[str, Any]:
        context = current_run_context.get()
        if context is None:
            raise ToolError("No user request is available to check the spec against.")
        messages = [{"role": role, "content": content[-MAX_MESSAGE_CHARS:]}
                    for role, content in context.messages[-MAX_USER_MESSAGES:]]
        response = self._call("POST", "/v1/specs", json={
            "request_id": self._request_id(), "reference_time": context.reference_time.isoformat(),
            "timezone": context.timezone, "user_messages": messages, "spec": arguments.model_dump(mode="json")})
        body = self._json(response)
        if response.status_code == 200 and "status" in body:
            return spec_view(body)
        return self._rejected(response, body)

    def get_spec(self, spec_id: str) -> dict[str, Any] | None:
        """The approved contract of a spec (backend use only: the compiler reads the approved data plan)."""
        response = self._call("GET", f"/v1/specs/{spec_id}")
        if response.status_code == 404:
            return None
        body = self._json(response)
        if response.status_code != 200:
            raise ToolError(f"The Python sandbox is unavailable (HTTP {response.status_code}).")
        return body

    def submit(self, arguments: RunPythonAnalysisArgs, bindings: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {k: v for k, v in arguments.model_dump(mode="json").items() if k != "input_bundle_id"}
        response = self._call("POST", "/v1/analyses", json={"request_id": self._request_id(), **payload,
                                                            "inputs": bindings})
        body = self._json(response)
        if response.status_code == 200 and "analysis_id" in body:
            return model_view(body)
        return self._rejected(response, body)

    def result(self, analysis_id: str) -> dict[str, Any]:
        response = self._call("GET", f"/v1/analyses/{analysis_id}", params={"wait_seconds": self.poll_wait_seconds})
        if response.status_code == 404:
            return {"analysis_id": analysis_id, "execution_status": "NOT_FOUND", "next_action": "STOP_OR_REFORMULATE",
                    "error": {"code": "ANALYSIS_NOT_FOUND", "message": "No analysis exists with this analysis_id."}}
        body = self._json(response)
        if response.status_code == 200 and "analysis_id" in body:
            return model_view(body)
        raise ToolError(f"The Python sandbox is unavailable (HTTP {response.status_code}).")

    def put_report(self, request_id: str, report: dict[str, Any]) -> dict[str, Any]:
        """Audit: the orchestrator's final report of a run (not a model-facing tool)."""
        response = self._client.post(f"/v1/runs/{request_id}/report", json=report, timeout=10)
        response.raise_for_status()
        return response.json()

    def run_summary(self, request_id: str) -> dict[str, Any] | None:
        response = self._client.get(f"/v1/runs/{request_id}", timeout=10)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._client.close()


def run_context(reference_time: datetime | None, tz: str, history: list[tuple[str, str]], message: str) -> RunContext:
    moment = reference_time or datetime.now(timezone.utc)
    return RunContext(reference_time=moment, timezone=tz, messages=tuple(history) + (("user", message),))


def manifest_spec(client: GovernorClient, *, timeout_seconds: float) -> ToolSpec:
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, GetDatasetManifestArgs)
        return client.manifest(arguments.dataset_id)

    return ToolSpec(name="get_dataset_manifest", description=MANIFEST_DESCRIPTION,
                    arguments_model=GetDatasetManifestArgs, handler=handler, timeout_seconds=timeout_seconds)


def analysis_specs(client: SandboxClient, *, timeout_seconds: float, max_result_bytes: int,
                   bundles: Any = None) -> list[ToolSpec]:
    def create(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, CreateAnalysisSpecArgs)
        return client.create_spec(arguments)

    def run(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, RunPythonAnalysisArgs)
        bundle = bundles.resolve(arguments.input_bundle_id, current_request_id.get() or "", arguments.spec_id) \
            if bundles is not None else None
        if bundle is None:
            return {"status": "REJECTED", "next_action": "PREPARE_ANALYSIS_DATA", "error": {
                "code": "INPUT_BUNDLE_MISMATCH",
                "message": "input_bundle_id is not a bundle prepare_analysis_data returned for this spec_id in this "
                           "request. Call prepare_analysis_data(spec_id) and use its input_bundle_id."}}
        bindings = [{"name": name, "dataset_ids": ids, "duplicate_policy": "ERROR_ON_CONFLICT"}
                    for name, ids in sorted(bundle.inputs.items())]
        return client.submit(arguments, bindings)

    def result(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, GetAnalysisResultArgs)
        return client.result(arguments.analysis_id)

    return [
        ToolSpec(name="create_analysis_spec", description=SPEC_DESCRIPTION, arguments_model=CreateAnalysisSpecArgs,
                 handler=create, timeout_seconds=timeout_seconds, max_result_bytes=max_result_bytes),
        ToolSpec(name="run_python_analysis", description=RUN_DESCRIPTION, arguments_model=RunPythonAnalysisArgs,
                 handler=run, timeout_seconds=timeout_seconds, max_result_bytes=max_result_bytes),
        ToolSpec(name="get_analysis_result", description=RESULT_DESCRIPTION, arguments_model=GetAnalysisResultArgs,
                 handler=result, timeout_seconds=timeout_seconds, max_result_bytes=max_result_bytes),
    ]
