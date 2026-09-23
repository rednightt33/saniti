"""request_data and lookup_fact: the model-facing tools for actual database observations.

Two separate paths through market-sql-governor, which validates every request against the AI
catalogs, compiles and cost-checks the SQL, and executes it read-only:
- request_data: analysis input. An approved request is always an immutable dataset (dataset_id,
  manifest, checksum); its rows never reach the model.
- lookup_fact: a narrow path for specific source facts (at most 20 values, each with a fact_id).
This module only forwards the specs and returns the Governor's decisions. It holds no database
credential and no SQL logic. The models below must stay identical to
apps/market-sql-governor/app/spec.py (tests/test_request_data.py enforces this).
"""
from __future__ import annotations

import contextvars
import uuid
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .registry import ToolError, ToolSpec

TABLE_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,62}$"
COLUMN_PATTERN = r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$"

FilterOperator = Literal["EQ", "NEQ", "GT", "GTE", "LT", "LTE", "IN", "BETWEEN", "IS_NULL", "IS_NOT_NULL"]
AggregateFunction = Literal["SUM", "AVG", "MEDIAN", "MIN", "MAX", "COUNT", "COUNT_DISTINCT"]

DATASET_DECISIONS = {"DATASET_READY", "NEEDS_NARROWING", "REJECTED", "SANDBOX_REQUIRED"}
LOOKUP_DECISIONS = {"FACTS_READY", "NEEDS_NARROWING", "REJECTED"}

# Set by the orchestrator for each run so Governor logs can be joined to the agent run.
current_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_request_id", default=None)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ColumnRef(Strict):
    table: str = Field(pattern=TABLE_PATTERN, description="Exact table_name from the catalog.")
    column: str = Field(pattern=COLUMN_PATTERN, description="Exact column_name from the catalog.")


class JoinSpec(Strict):
    table: str = Field(pattern=TABLE_PATTERN, description="Table to join; join keys come from the catalog.")
    relationship_id: int | None = Field(
        ge=1, description="Catalog relationship_id to use, or null when exactly one approved relationship applies."
    )


class FilterSpec(Strict):
    table: str = Field(pattern=TABLE_PATTERN)
    column: str = Field(pattern=COLUMN_PATTERN)
    operator: FilterOperator
    value: str | int | float | bool | list[str | int | float] | None = Field(
        description=(
            "Scalar for EQ/NEQ/GT/GTE/LT/LTE; list for IN; [low, high] for BETWEEN; null for "
            "IS_NULL/IS_NOT_NULL. Dates as YYYY-MM-DD strings. Values are bound as parameters."
        )
    )


class AggregationSpec(Strict):
    table: str = Field(pattern=TABLE_PATTERN)
    column: str = Field(pattern=COLUMN_PATTERN)
    function: AggregateFunction


class OrderSpec(Strict):
    table: str = Field(pattern=TABLE_PATTERN)
    column: str = Field(pattern=COLUMN_PATTERN)
    function: AggregateFunction | None = Field(
        description="null to order by the column itself, or the aggregation function listed in aggregations."
    )
    direction: Literal["ASC", "DESC"]


class DataRequestSpec(Strict):
    purpose: str = Field(min_length=1, max_length=500, description="Why the data is needed.")
    from_table: str = Field(pattern=TABLE_PATTERN, description="Primary table from the catalog.")
    columns: list[ColumnRef] = Field(max_length=50, description="Columns to return (group-by columns when aggregating).")
    joins: list[JoinSpec] = Field(max_length=5)
    filters: list[FilterSpec] = Field(max_length=30)
    group_by: list[ColumnRef] = Field(max_length=20)
    aggregations: list[AggregationSpec] = Field(max_length=20)
    order_by: list[OrderSpec] = Field(max_length=10)
    requested_limit: int | None = Field(ge=1, le=5_000_000, description="Optional row limit; null for none.")


# ---------------------------------------------------------------- lookup_fact
# A narrow path for specific source facts. Limits are part of the contract (and repeated in the
# Governor after execution): at most 5 entities, 10 dates, 4 columns, and 20 returned values.
LOOKUP_MAX_ENTITIES = 5
LOOKUP_MAX_DATES = 10
LOOKUP_MAX_COLUMNS = 4
LOOKUP_MAX_VALUES = 20
ENTITY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,19}$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
LookupFunction = Literal["SUM", "AVG", "MIN", "MAX", "COUNT"]


class LookupDateRange(Strict):
    start: str = Field(pattern=DATE_PATTERN, description="First date, YYYY-MM-DD (inclusive).")
    end: str = Field(pattern=DATE_PATTERN, description="Last date, YYYY-MM-DD (inclusive).")


class LookupAggregation(Strict):
    column: str = Field(pattern=COLUMN_PATTERN)
    function: LookupFunction


class LookupFactSpec(Strict):
    purpose: str = Field(min_length=1, max_length=300, description="Which fact is needed and why.")
    mode: Literal["VALUE", "AGGREGATE"] = Field(
        description="VALUE: source values at explicit entity/date keys. AGGREGATE: SUM/AVG/MIN/MAX/COUNT computed "
                    "by the database over the explicit scope.")
    table: str = Field(pattern=TABLE_PATTERN, description="Exact table_name from the catalog.")
    entities: list[str] = Field(min_length=1, max_length=LOOKUP_MAX_ENTITIES,
                                description="Tickers (or the table's entity codes), 1 to 5.")
    dates: list[str] | None = Field(max_length=LOOKUP_MAX_DATES,
                                    description="Explicit dates YYYY-MM-DD (at most 10), or null.")
    date_range: LookupDateRange | None = Field(
        description="Inclusive date range, or null. VALUE mode: at most 10 trading dates may fall inside it.")
    columns: list[str] | None = Field(max_length=LOOKUP_MAX_COLUMNS,
                                      description="VALUE mode: 1 to 4 value columns; null in AGGREGATE mode.")
    aggregations: list[LookupAggregation] | None = Field(
        max_length=LOOKUP_MAX_COLUMNS, description="AGGREGATE mode: 1 to 4 aggregations; null in VALUE mode.")
    per_entity: bool | None = Field(
        description="AGGREGATE mode: true for one value per entity, false for one value across all entities.")


DESCRIPTION = (
    "Request analysis input from the database with a structured data request (never SQL). Use exact "
    "table and column names from the catalog tools. Joins name only the table (and optionally a "
    "catalog relationship_id); join keys come from the catalog. Filters use EQ, NEQ, GT, GTE, LT, "
    "LTE, IN, BETWEEN, IS_NULL, IS_NOT_NULL with typed values. Aggregations must be allowed by the "
    "column catalog; when aggregating, every returned column must be in group_by. The SQL Governor "
    "validates, cost-checks, and executes the request. An approved request is always DATASET_READY: "
    "an immutable dataset reference (dataset_id, row count, columns, date range, entities, "
    "completeness) for run_python_analysis, never the rows themselves. Other decisions are "
    "NEEDS_NARROWING or REJECTED, with next_action and reason_code. A dataset is not an answer: "
    "numbers in an answer come from lookup_fact or from a validated Python analysis."
)

LOOKUP_DESCRIPTION = (
    "Look up specific source facts without Python: mode VALUE returns source values at explicit keys "
    "(1-5 entities such as tickers, explicit dates or a date range of at most 10 trading dates, 1-4 "
    "columns, at most 20 values in total); mode AGGREGATE returns SUM, AVG, MIN, MAX, or COUNT computed "
    "by the database over the explicit scope (per_entity true for one value per entity), at most 20 "
    "values. Filters are only the entities and dates; there is no ranking, ordering by value, or "
    "statistic. Every value comes back with a fact_id, table, column, entity, and date or scope. "
    "A refusal with next_action USE_ANALYSIS_PATH means the question needs request_data plus a "
    "Python analysis (statistics such as correlation, z-score, RSI, returns, rankings, or more values)."
)


class GovernorClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float,
                 transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def query(self, spec: DataRequestSpec) -> dict[str, Any]:
        request_id = current_request_id.get() or f"orc-{uuid.uuid4().hex[:16]}"
        try:
            response = self._client.post("/v1/query", json={"request_id": request_id, "spec": spec.model_dump()})
        except httpx.TimeoutException as exc:
            raise ToolError("The SQL Governor did not answer in time. Try a narrower request.") from exc
        except httpx.HTTPError as exc:
            raise ToolError("The SQL Governor is unreachable.") from exc
        if response.status_code != 200:
            raise ToolError(f"The SQL Governor is unavailable (HTTP {response.status_code}).")
        try:
            result = response.json()
        except ValueError as exc:
            raise ToolError("The SQL Governor returned an invalid response.") from exc
        if not isinstance(result, dict) or "decision" not in result or "next_action" not in result:
            raise ToolError("The SQL Governor returned an invalid response.")
        if result.get("rows") is not None or result["decision"] not in DATASET_DECISIONS:
            # Data rows must never reach the model through request_data (an outdated Governor would send them).
            raise ToolError("The SQL Governor returned rows instead of a dataset reference; request refused.")
        return result

    def lookup(self, spec: "LookupFactSpec") -> dict[str, Any]:
        request_id = current_request_id.get() or f"orc-{uuid.uuid4().hex[:16]}"
        try:
            response = self._client.post("/v1/lookup", json={"request_id": request_id, "spec": spec.model_dump()})
        except httpx.TimeoutException as exc:
            raise ToolError("The SQL Governor did not answer in time.") from exc
        except httpx.HTTPError as exc:
            raise ToolError("The SQL Governor is unreachable.") from exc
        if response.status_code != 200:
            raise ToolError(f"The SQL Governor is unavailable (HTTP {response.status_code}).")
        try:
            result = response.json()
        except ValueError as exc:
            raise ToolError("The SQL Governor returned an invalid response.") from exc
        if not isinstance(result, dict) or result.get("decision") not in LOOKUP_DECISIONS \
                or len(result.get("facts") or []) > LOOKUP_MAX_VALUES:
            raise ToolError("The SQL Governor returned an invalid response.")
        return result

    def manifest(self, dataset_id: str) -> dict[str, Any]:
        """The Governor's bounded safe manifest subset, or an explicit DATASET_EXPIRED / NOT_FOUND status."""
        try:
            response = self._client.get(f"/v1/datasets/{dataset_id}/manifest")
        except httpx.TimeoutException as exc:
            raise ToolError("The SQL Governor did not answer in time.") from exc
        except httpx.HTTPError as exc:
            raise ToolError("The SQL Governor is unreachable.") from exc
        try:
            result = response.json()
        except ValueError as exc:
            raise ToolError("The SQL Governor returned an invalid response.") from exc
        if response.status_code in (200, 404, 410, 422) and isinstance(result, dict) and "status" in result:
            return result
        raise ToolError(f"The SQL Governor is unavailable (HTTP {response.status_code}).")

    def close(self) -> None:
        self._client.close()


def request_data_spec(client: GovernorClient, *, timeout_seconds: float, max_result_bytes: int) -> ToolSpec:
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, DataRequestSpec)
        return client.query(arguments)  # the Governor's decision and next_action are returned unchanged

    return ToolSpec(
        name="request_data",
        description=DESCRIPTION,
        arguments_model=DataRequestSpec,
        handler=handler,
        timeout_seconds=timeout_seconds,
        max_result_bytes=max_result_bytes,
    )


def lookup_fact_spec(client: GovernorClient, *, timeout_seconds: float, max_result_bytes: int) -> ToolSpec:
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, LookupFactSpec)
        return client.lookup(arguments)

    return ToolSpec(
        name="lookup_fact",
        description=LOOKUP_DESCRIPTION,
        arguments_model=LookupFactSpec,
        handler=handler,
        timeout_seconds=timeout_seconds,
        max_result_bytes=max_result_bytes,
    )
