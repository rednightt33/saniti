"""DataNeed flow tools (behind AI_ENABLE_DATANEED): submit_data_need_spec.

A DataNeedSpec says only which data the answer needs: logical data requests (catalog table, columns, a database scope
expression tree, time ranges, frequencies, buffers, ordering) and the catalog relationships between them. It carries
no formula, calculation, indicator, method, ranking or output grain: all analytical logic is written later in a
sandbox session. The sandbox's DataNeedValidator is authoritative (apps/market-python-sandbox/app/data_need.py) and
answers APPROVED, REVISION_REQUIRED or CATALOG_UNAVAILABLE with structured issues
{data_request_id, code, field_path, rejected_value} and never suggests a replacement.

Model-facing schema: strict tools inline every nested model and cannot express recursion, so the scope tree is
unrolled to the validator's maximum depth of 4 (ScopeNode -> ScopeNode2 -> ScopeNode3 -> ScopePredicate). The same
four levels are the validator's limit, so nothing expressible is lost. Only types and enums are enforced here; every
value rule (identifier formats, catalog binding, limits) is left to the validator so the model receives the
validator's structured issues rather than a generic argument error. Argument errors that do occur (a wrong JSON type)
are rendered in the same issue shape (argument_issues).
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..research_plan import guard_research_submission
from .analysis import SandboxClient, current_run_context
from .registry import ToolError, ToolSpec

SPEC_VERSION = "data_need_spec/v1"
Operator = Literal["EQ", "NEQ", "GT", "GTE", "LT", "LTE", "IN", "NOT_IN", "BETWEEN", "IS_NULL", "IS_NOT_NULL"]
Value = str | int | float | bool | list[str | int | float] | None
VALUE_DESCRIPTION = ("Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for "
                     "IS_NULL/IS_NOT_NULL. The exact catalog data value.")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- scope expression tree (unrolled, depth <= 4)

class ScopePredicate(Strict):
    """Depth 4: only a predicate fits here."""

    type: Literal["PREDICATE"]
    column: str
    operator: Operator
    value: Value = Field(description=VALUE_DESCRIPTION)


class ScopeNode3(Strict):
    type: Literal["PREDICATE", "AND", "OR", "NOT"]
    column: str | None
    operator: Operator | None
    value: Value
    children: list[ScopePredicate] | None
    child: ScopePredicate | None


class ScopeNode2(Strict):
    type: Literal["PREDICATE", "AND", "OR", "NOT"]
    column: str | None
    operator: Operator | None
    value: Value
    children: list[ScopeNode3] | None
    child: ScopeNode3 | None


class ScopeNode(Strict):
    type: Literal["ALL", "PREDICATE", "AND", "OR", "NOT"] = Field(
        description="ALL (every row; only as the whole scope), PREDICATE (column operator value), AND / OR "
                    "(children: at least two nodes), NOT (child: one node). At most 4 levels and 40 nodes.")
    column: str | None = Field(description="PREDICATE: a filterable catalog column of this request's table; else null.")
    operator: Operator | None = Field(description="PREDICATE only; else null.")
    value: Value = Field(description=VALUE_DESCRIPTION)
    children: list[ScopeNode2] | None = Field(description="AND / OR only; else null.")
    child: ScopeNode2 | None = Field(description="NOT only; else null.")


# ---------------------------------------------------------------- data requests and relationships

class TimeRange(Strict):
    range_id: str = Field(description="Unique within the request, e.g. current_ytd, previous_comparable.")
    start: str = Field(description="YYYY-MM-DD, first date of the range.")
    end: str = Field(description="YYYY-MM-DD, last date of the range; not after the reference date.")


class Buffer(Strict):
    value: int
    unit: Literal["TRADING_OBSERVATIONS", "CALENDAR_DAYS"]


class Ordering(Strict):
    column: str
    direction: Literal["ASC", "DESC"]


class Measure(Strict):
    # "as" is a Python keyword: the field is as_, sent and shown as "as"
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    column: str | None = Field(description="The measured catalog column; null for COUNT (rows at the table's grain).")
    function: Literal["SUM", "MIN", "MAX", "COUNT", "COUNT_DISTINCT"] = Field(
        description="SUM only for a column whose catalog cross_entity_aggregation is SUM; MIN/MAX for numeric "
                    "measures; COUNT counts rows; COUNT_DISTINCT for an identifier or dimension column. No AVG: send "
                    "SUM and COUNT and divide in the session.")
    as_: str = Field(alias="as", description="Output column name (lower-case letters, digits, _), not a catalog "
                                             "column name.")


class Aggregate(Strict):
    group_by: list[str] = Field(description="Columns the warehouse groups by; must include the time column of a dated "
                                            "table; drop the entity or other key columns to summarise across them "
                                            "(e.g. [date, broker] sums over tickers).")
    measures: list[Measure] = Field(description="One to twenty summaries per group.")


class DataRequest(Strict):
    data_request_id: str = Field(description="<request_group_id>_<suffix>, suffix 1-12 letters/digits, e.g. "
                                             "data_request_1_A. Stable across revisions.")
    logical_name: str = Field(description="Lower-case name the session loads the data by, e.g. prices.")
    source_table: str = Field(description="Catalog table.")
    entity_column: str | None = Field(description="The table's catalog entity_column; null when it has none.")
    time_column: str | None = Field(description="The table's catalog time_column; null for static tables.")
    columns: list[str] = Field(description="Catalog columns needed (entity and time columns are always added).")
    scope: ScopeNode = Field(description="Which rows, as an expression tree on filterable columns of this table.")
    time_ranges: list[TimeRange] = Field(description="One or more named ranges ([] for static tables).")
    source_frequency: str = Field(description="A supported_frequencies value of the table (1D, ...; STATIC).")
    analysis_frequency: str = Field(description="Frequency of the analysis (same as source, or coarser with resample).")
    resample: Literal["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"] | None = Field(
        description="Required when analysis_frequency is coarser than source_frequency; else null.")
    history_buffer: Buffer | None = Field(description="Observations before each range needed as warm-up; null if none.")
    future_buffer: Buffer | None = Field(description="Observations after each range (e.g. forward outcomes); null "
                                                     "if none.")
    ordering: list[Ordering] = Field(description="Row order of the delivered dataset ([] for none).")
    sampling_allowed: bool = Field(description="Always false: data is never sampled.")


class AnalysisDataRequest(DataRequest):
    """A request of submit_data_need_spec / check_data_feasibility: it may ask for a summary (G18). Research angle
    requests (check_research_feasibility) keep DataRequest: a summary is refused in mode RESEARCH."""

    columns: list[str] = Field(description="Catalog columns needed (entity and time columns are always added). With "
                                           "aggregate: exactly the group_by and measured columns.")
    aggregate: Aggregate | None = Field(
        description="ANALYSIS only: let the warehouse summarise across entities before delivery "
                                  "(one row per group instead of every raw row); null for raw rows. Refused "
                                  "(AGGREGATION_NOT_ADDITIVE) for a measure the catalog does not allow to be summed.")

    @model_validator(mode="before")
    @classmethod
    def _aggregate_absent_is_null(cls, data: Any) -> Any:
        """The strict schema lists aggregate as required (nullable); a request written before it, or by a provider
        that leaves null fields out, means raw rows."""
        if isinstance(data, dict) and "aggregate" not in data:
            return {**data, "aggregate": None}
        return data


class Relationship(Strict):
    relationship_id: int = Field(description="Catalog relationship_id between the two requests' tables.")
    left_request_id: str
    left_column: str
    right_request_id: str
    right_column: str
    join_type: Literal["INNER", "LEFT"] = Field(
        description="INNER restricts the left request to rows with a match in the right request's scope; LEFT "
                    "leaves it unrestricted. Each request is delivered as its own dataset; the analysis joins them.")
    join_semantics: Literal["CURRENT_STATE", "EXACT_DATE", "AS_OF", "EFFECTIVE_DATED"] = Field(
        description="One of the relationship's supported_join_semantics in the catalog.")
    left_time_column: str | None = Field(description="EXACT_DATE / AS_OF: the catalog left time column; else null.")
    right_time_column: str | None = Field(description="EXACT_DATE / AS_OF: the catalog right time column; else null.")
    as_of_direction: Literal["BACKWARD"] | None = Field(description="AS_OF only; else null.")
    effective_from_column: str | None = Field(description="EFFECTIVE_DATED only: catalog column; else null.")
    effective_to_column: str | None = Field(description="EFFECTIVE_DATED only: catalog column; else null.")


KEY_COLUMNS_DESCRIPTION = ("Every entity key column of the catalog relationship on this side, in the order of its "
                           "left_columns / right_columns without the time column (a composite key such as ticker, "
                           "broker, investor_type and market_board names all of them).")


class RelationshipV2(Strict):
    """data_need_spec/v2 (AI_ENABLE_COMPOSITE_KEYS, IP1 Stage B): a relationship names every entity key pair."""

    relationship_id: int = Field(description="Catalog relationship_id between the two requests' tables.")
    left_request_id: str
    left_columns: list[str] = Field(description=KEY_COLUMNS_DESCRIPTION)
    right_request_id: str
    right_columns: list[str] = Field(description="The matching right-side key columns, pair by pair with "
                                                 "left_columns.")
    join_type: Literal["INNER", "LEFT"] = Field(
        description="INNER restricts the left request to rows with a match in the right request's scope; LEFT "
                    "leaves it unrestricted. Each request is delivered as its own dataset; the analysis joins them.")
    join_semantics: Literal["CURRENT_STATE", "EXACT_DATE", "AS_OF", "EFFECTIVE_DATED"] = Field(
        description="One of the relationship's supported_join_semantics in the catalog.")
    left_time_column: str | None = Field(description="EXACT_DATE / AS_OF: the catalog left time column; else null.")
    right_time_column: str | None = Field(description="EXACT_DATE / AS_OF: the catalog right time column; else null.")
    as_of_direction: Literal["BACKWARD"] | None = Field(description="AS_OF only; else null.")
    effective_from_column: str | None = Field(description="EFFECTIVE_DATED only: catalog column; else null.")
    effective_to_column: str | None = Field(description="EFFECTIVE_DATED only: catalog column; else null.")


class Subject(Strict):
    data_domain: str
    entity_type: str
    asset_type: str | None


class Holdout(Strict):
    data_request_id: str
    range_id: str = Field(description="One of that request's declared ranges, kept out of fitting.")


class MinimumSample(Strict):
    value: int
    unit: Literal["EVENTS", "OBSERVATIONS", "ENTITIES"]


class ResearchGovernance(Strict):
    hypothesis_id: str = Field(description="Lower-case id; revisions of a request group keep it.")
    hypothesis: str
    objective: str
    condition: str | None = Field(description="The condition or event, in plain words; a declaration only. With an "
                                              "approved Research Plan: its experiment's text.")
    outcome: str | None = Field(description="The outcome measured after the condition, in plain words.")
    baseline: str | None = Field(description="What the outcome is compared with, in plain words.")
    candidate_count: int = Field(description="Conditions, lags or parameter combinations the experiment evaluates.")
    pairwise_comparisons: int
    holdout: Holdout | None
    minimum_sample: MinimumSample | None
    multiple_testing_policy: Literal["NONE", "BONFERRONI", "HOLM", "BENJAMINI_HOCHBERG"] = Field(
        description="NONE only for a single comparison.")
    followup_of: str | None = Field(description="request_group_id of an approved experiment on the same hypothesis "
                                                "this one follows up; else null.")


class SuccessRuleArg(Strict):
    """M28: the approved success threshold (outcome <operator> value, in the outcome's unit)."""

    operator: Literal[">=", ">", "<=", "<"] = Field(description="How the outcome is compared with value.")
    value: float = Field(description="The threshold in the outcome's unit.")


class ResearchGovernanceFindings(ResearchGovernance):
    """research_governance with the research findings v1 values, copied from the approved experiment."""

    expected_direction: Literal["HIGHER", "LOWER", "DIFFERENT"] = Field(
        description="The approved experiment's expected_direction.")
    outcome_horizon_periods: int = Field(description="The approved experiment's outcome_horizon_periods.")
    outcome_unit: Literal["PERCENT", "DECIMAL", "OTHER"] = Field(description="The approved experiment's outcome_unit.")
    success_definition: str = Field(description="The approved experiment's success_definition.")
    min_effect: float | None = Field(description="The approved experiment's min_effect (null when it has none).")
    success_rule: SuccessRuleArg | None = Field(
        description="The approved experiment's success_rule, or null; the engine applies it.")

    @model_validator(mode="before")
    @classmethod
    def _success_rule_absent_is_null(cls, data: Any) -> Any:
        if isinstance(data, dict) and "success_rule" not in data:
            return {**data, "success_rule": None}
        return data


class DataNeedSpecBody(Strict):
    """The DataNeedSpec fields shared by submit_data_need_spec and check_data_feasibility."""

    spec_version: Literal["data_need_spec/v1"]
    request_group_id: str = Field(description="Lower-case id of this data need, e.g. data_request_1; revisions keep "
                                              "it.")
    revision: int = Field(description="1 for the first submission, then the next number for each revision.")
    mode: Literal["ANALYSIS", "RESEARCH"]
    question: str = Field(description="The user's question, restated.")
    subject: Subject
    data_requests: list[AnalysisDataRequest] = Field(description="1-8 logical data requests.")
    relationships: list[Relationship] = Field(description="Catalog relationships between requests ([] for none).")


class SubmitDataNeedSpecArgs(DataNeedSpecBody):
    research_governance: ResearchGovernance | None = Field(description="Required for RESEARCH; null for ANALYSIS.")


class CheckDataFeasibilityArgs(DataNeedSpecBody):
    """A Research Plan's data, checked before the plan is presented (no research_governance: it is declared when the
    approved plan runs)."""


class DataNeedSpecBodyV2(DataNeedSpecBody):
    spec_version: Literal["data_need_spec/v2"]  # type: ignore[assignment]
    relationships: list[RelationshipV2] = Field(  # type: ignore[assignment]
        description="Catalog relationships between requests ([] for none), each with every key pair.")


class SubmitDataNeedSpecArgsV2(DataNeedSpecBodyV2):
    research_governance: ResearchGovernance | None = Field(description="Required for RESEARCH; null for ANALYSIS.")


class CheckDataFeasibilityArgsV2(DataNeedSpecBodyV2):
    """check_data_feasibility with data_need_spec/v2."""


TIME_BASIS_DESCRIPTION = (
    "HISTORICAL_DESCRIPTIVE (normal): history may be described with current reference data such as today's sector, "
    "disclosed. POINT_IN_TIME only when the user asks for what was known at the time (no look-ahead, backtest, "
    "classification as of each date): only values in effect and already recorded on each date, through the "
    "EFFECTIVE_DATED relationships of the history tables; refused with POINT_IN_TIME_UNAVAILABLE where that history "
    "does not exist, never replaced by current data.")


class DataNeedSpecBodyPIT(DataNeedSpecBodyV2):
    """data_need_spec/v2 with time_basis (AI_ENABLE_POINT_IN_TIME, IP1 Stage D)."""

    time_basis: Literal["HISTORICAL_DESCRIPTIVE", "POINT_IN_TIME"] = Field(description=TIME_BASIS_DESCRIPTION)


class SubmitDataNeedSpecArgsPIT(DataNeedSpecBodyPIT):
    research_governance: ResearchGovernance | None = Field(description="Required for RESEARCH; null for ANALYSIS.")


class CheckDataFeasibilityArgsPIT(DataNeedSpecBodyPIT):
    """check_data_feasibility with data_need_spec/v2 and time_basis."""


class SubmitDataNeedSpecArgsFindings(DataNeedSpecBody):
    research_governance: ResearchGovernanceFindings | None = Field(description="Required for RESEARCH; null for "
                                                                               "ANALYSIS.")


class SubmitDataNeedSpecArgsV2Findings(DataNeedSpecBodyV2):
    research_governance: ResearchGovernanceFindings | None = Field(description="Required for RESEARCH; null for "
                                                                               "ANALYSIS.")


class SubmitDataNeedSpecArgsPITFindings(DataNeedSpecBodyPIT):
    research_governance: ResearchGovernanceFindings | None = Field(description="Required for RESEARCH; null for "
                                                                               "ANALYSIS.")


# ---------------------------------------------------------------- argument errors in the validator's issue shape

def _walk(data: Any, loc: tuple[Any, ...], missing: bool) -> tuple[str, Any, Any]:
    """Field path (validator format) of a pydantic error location, the value found there, and the data request's id.
    Union member tags in a location (e.g. 'str', 'list[...]') are not data keys and end the walk; for a missing field
    the last location part is the absent key."""
    parts, path, node = (loc[:-1] if missing and loc else loc), "", data
    walked = True
    for part in parts:
        if isinstance(node, dict) and isinstance(part, str) and part in node:
            path, node = (f"{path}.{part}" if path else part), node[part]
        elif isinstance(node, list) and isinstance(part, int) and 0 <= part < len(node):
            path, node = f"{path}[{part}]", node[part]
        else:
            walked = False
            break
    if missing and loc and walked:
        path, node = (f"{path}.{loc[-1]}" if path else str(loc[-1])), None
    request = None
    if len(loc) >= 2 and loc[0] == "data_requests" and isinstance(loc[1], int) and isinstance(data, dict):
        requests = data.get("data_requests")
        if isinstance(requests, list) and 0 <= loc[1] < len(requests) and isinstance(requests[loc[1]], dict):
            request = requests[loc[1]].get("data_request_id")
    return path, node, request


def argument_issues(exc: Exception, raw: Any) -> dict[str, Any]:
    """INVALID_ARGUMENTS for submit_data_need_spec, as {status, issues[]} like the validator's REVISION_REQUIRED."""
    issues: list[dict[str, Any]] = []
    if isinstance(exc, ValidationError):
        for error in exc.errors(include_url=False)[:20]:
            kind = str(error.get("type") or "")
            path, value, request = _walk(raw, tuple(error.get("loc") or ()), kind == "missing")
            code = "MISSING_REQUIRED_FIELD" if kind == "missing" else "UNKNOWN_FIELD" if kind == "extra_forbidden" \
                else "INVALID_FIELD_VALUE" if kind in ("literal_error", "enum") else "INVALID_FIELD_TYPE"
            rendered = value if isinstance(value, (str, int, float, bool)) or value is None else json.dumps(
                value, default=str, separators=(",", ":"))
            if isinstance(rendered, str) and len(rendered) > 200:
                rendered = rendered[:197] + "..."
            entry = {"data_request_id": request if isinstance(request, str) else None, "code": code,
                     "field_path": path, "rejected_value": rendered}
            if entry not in issues:
                issues.append(entry)
    else:
        issues.append({"data_request_id": None, "code": "INVALID_FIELD_TYPE", "field_path": "",
                       "rejected_value": "arguments must be one JSON object"})
    return {"status": "REVISION_REQUIRED", "issues": issues, "next_action": "REVISE_DATA_NEED_SPEC"}


# ---------------------------------------------------------------- client and tool

DECLARATION_FIELDS = ("condition", "outcome", "baseline")


def submit_data_need(client: SandboxClient,
                     arguments: "SubmitDataNeedSpecArgs | SubmitDataNeedSpecArgsV2 | SubmitDataNeedSpecArgsPIT"
                     ) -> dict[str, Any]:
    context = current_run_context.get()
    if context is None:
        raise ToolError("No user request is available to anchor the data need's reference date.")
    payload = arguments.model_dump(mode="json")
    governance = payload.pop("research_governance")
    if arguments.mode == "RESEARCH":
        # The research execution guard: arguments are validated, nothing has reached the sandbox yet. Without a
        # verified approved Research Plan (when confirmation is on), or with a declaration that differs from its
        # approved experiment, the call ends here.
        refused = guard_research_submission(governance)
        if refused is not None:
            return refused
    if governance is not None:
        # The declaration fields are sent only when set, so a sandbox without them still accepts the request.
        for key in DECLARATION_FIELDS:
            if governance.get(key) is None:
                governance.pop(key, None)
    body: dict[str, Any] = {"request_id": client._request_id(), "reference_time": context.reference_time.isoformat(),
                            "timezone": context.timezone, "spec": payload}
    if governance is not None:
        body["research_governance"] = governance
    response = client._call("POST", "/v1/data-needs", json=body)
    result = client._json(response)
    if response.status_code == 200 and "status" in result:
        return result
    return client._rejected(response, result)


SUBMIT_DESCRIPTION = (
    "Declare which data the answer needs (DataNeedSpec), before any extraction. It lists logical data requests and "
    "catalog relationships only: never a formula, indicator, method, ranking or output; all calculations are "
    "written later in the analysis session. Each data request names one catalog table, the columns needed, a scope "
    "(expression tree on filterable columns of that table: ALL, PREDICATE, AND/OR with children, NOT with child), "
    "one or more named time ranges (e.g. the current YTD and the same period last year), the source frequency and "
    "the analysis frequency (resample when coarser), history_buffer for warm-up observations before each range and "
    "future_buffer for observations after it, and ordering. Copy table names, entity/time columns, frequencies and "
    "subject from discover_catalog and get_catalog_details, and relationship ids and join semantics from the "
    "catalog relationships. A restriction by another table (for example prices of banks only) is a second data "
    "request on the reference table with its own scope, joined by an INNER relationship; never a manual ticker "
    "list. The validator answers APPROVED (need_id; next: prepare the data bundle), REVISION_REQUIRED (issues with "
    "data_request_id, code, field_path and rejected_value; fix each and resubmit with revision + 1, same "
    "request_group_id and data_request_ids), or CATALOG_UNAVAILABLE (stop and report temporarily). It never suggests "
    "a replacement: read the catalog again instead of guessing. mode RESEARCH also needs research_governance "
    "(hypothesis, objective, the condition, outcome and baseline as plain-language declarations, candidate_count, "
    "pairwise_comparisons, multiple_testing_policy, optional holdout range and minimum sample); the Research "
    "Governor answers APPROVED, REPLAN_REQUIRED or REJECTED with a reason code. When research needs an approved "
    "Research Plan, a RESEARCH submission without one, or one that differs from its approved experiment, is refused "
    "with RESEARCH_PLAN_* codes before anything is extracted. The same revision sent again returns the same answer."
)


def data_need_specs(client: SandboxClient, *, timeout_seconds: float, max_result_bytes: int,
                    composite_keys: bool = False, point_in_time: bool = False,
                    research_findings: bool = False) -> list[ToolSpec]:
    if research_findings:
        model = (SubmitDataNeedSpecArgsPITFindings if point_in_time else SubmitDataNeedSpecArgsV2Findings) \
            if composite_keys else SubmitDataNeedSpecArgsFindings
    else:
        model = (SubmitDataNeedSpecArgsPIT if point_in_time else SubmitDataNeedSpecArgsV2) if composite_keys \
            else SubmitDataNeedSpecArgs

    def submit(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, (SubmitDataNeedSpecArgs, SubmitDataNeedSpecArgsV2, SubmitDataNeedSpecArgsPIT,
                                      SubmitDataNeedSpecArgsFindings, SubmitDataNeedSpecArgsV2Findings,
                                      SubmitDataNeedSpecArgsPITFindings))
        return submit_data_need(client, arguments)

    return [ToolSpec(name="submit_data_need_spec", description=SUBMIT_DESCRIPTION,
                     arguments_model=model, handler=submit, timeout_seconds=timeout_seconds,
                     max_result_bytes=max_result_bytes, argument_errors=argument_issues,
                     envelope_key="data_need_spec")]
