"""The Data Request Spec: the only query input the Governor accepts.

It names catalog identifiers and typed values; it has no field for SQL text, expressions,
join keys, or delivery format. market-ai-orc exposes an identical model to the AI
(apps/market-ai-orc/app/tools/request_data.py); a contract test keeps them equal.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TABLE_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,62}$"
COLUMN_PATTERN = r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$"

FilterOperator = Literal["EQ", "NEQ", "GT", "GTE", "LT", "LTE", "IN", "BETWEEN", "IS_NULL", "IS_NOT_NULL"]
AggregateFunction = Literal["SUM", "AVG", "MEDIAN", "MIN", "MAX", "COUNT", "COUNT_DISTINCT"]


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
