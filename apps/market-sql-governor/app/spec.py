"""The Governor's two query inputs: the Data Request Spec and the Lookup Fact Spec.

Both name catalog identifiers and typed values; neither has a field for SQL text, expressions,
join keys, ranking, or delivery format. market-ai-orc exposes identical models to the AI
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
