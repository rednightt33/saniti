"""request_data: the only model-facing tool for actual database observations.

The model sends a structured Data Request Spec; market-sql-governor validates it against the
AI catalogs, compiles and cost-checks the SQL, executes it read-only, and decides whether the
result is returned inline or as an immutable dataset snapshot. This module only forwards the
spec and returns the Governor's decision unchanged. It holds no database credential and no
SQL logic. The models below must stay identical to apps/market-sql-governor/app/spec.py
(tests/test_request_data.py enforces this).
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


DESCRIPTION = (
    "Request actual database observations with a structured data request (never SQL). Use exact "
    "table and column names from the catalog tools. Joins name only the table (and optionally a "
    "catalog relationship_id); join keys come from the catalog. Filters use EQ, NEQ, GT, GTE, LT, "
    "LTE, IN, BETWEEN, IS_NULL, IS_NOT_NULL with typed values. Aggregations must be allowed by the "
    "column catalog; when aggregating, every returned column must be in group_by. The SQL Governor "
    "validates, cost-checks, and executes the request and returns a decision: INLINE_RESULT (rows "
    "included), DATASET_READY (a dataset_id reference only), NEEDS_NARROWING, or REJECTED, with "
    "next_action and reason_code."
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
        return result

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
