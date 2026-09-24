"""Gates 1-7: validate a Data Request Spec against the five AI catalogs.

The catalogs are the only policy source. Validation is a pure function of the spec, the
loaded catalog rows, and backend settings, so every gate is testable without a database.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .config import Settings
from .decisions import narrowing, rejected
from .spec import AggregationSpec, ColumnRef, DataRequestSpec, FilterSpec

Runner = Callable[[str, tuple[Any, ...]], list[dict[str, Any]]]

TABLES_SQL = '''
SELECT table_name, is_active, ai_access_level, time_column, entity_column, primary_key_columns,
       coverage_enabled
FROM public."AI_table_catalog" WHERE table_name = ANY(%s)
'''
COLUMNS_SQL = '''
SELECT table_name, column_name, data_type, semantic_type, ai_allowed, is_sensitive, filter_allowed,
       group_by_allowed, allowed_aggregations, unit
FROM public."AI_column_catalog" WHERE table_name = ANY(%s)
'''
RELATIONSHIPS_SQL = '''
SELECT relationship_id, left_table, left_columns, right_table, right_columns, relationship_type,
       temporal_rule, safe_output_grain, requires_preaggregation, is_allowed, version
FROM public."AI_catalog_relationships"
WHERE left_table = ANY(%s) OR right_table = ANY(%s)
ORDER BY relationship_id
'''
COVERAGE_SQL = '''
SELECT dataset_name, coverage_mode, actual_min_date, actual_max_date, expected_min_date,
       expected_max_date, verification_status, pipeline_status
FROM public."AI_data_coverage"
WHERE coverage_scope = 'DATASET' AND dataset_name = ANY(%s)
'''

NUMERIC_TYPES = ("smallint", "integer", "bigint", "numeric", "real", "double precision")
SQL_FUNCTIONS = {
    "SUM": "sum", "AVG": "avg", "MIN": "min", "MAX": "max", "COUNT": "count",
    "COUNT_DISTINCT": "count_distinct", "MEDIAN": "median",
}


@dataclass
class Policy:
    tables: dict[str, dict[str, Any]]
    columns: dict[tuple[str, str], dict[str, Any]]
    relationships: list[dict[str, Any]]
    coverage: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, run: Runner, spec: DataRequestSpec) -> "Policy":
        names = sorted({spec.from_table, *(join.table for join in spec.joins)})
        return cls(
            tables={row["table_name"]: row for row in run(TABLES_SQL, (names,))},
            columns={(row["table_name"], row["column_name"]): row for row in run(COLUMNS_SQL, (names,))},
            relationships=run(RELATIONSHIPS_SQL, (names, names)),
            coverage={row["dataset_name"]: row for row in run(COVERAGE_SQL, (names,))},
        )


@dataclass
class TableUse:
    name: str
    alias: str
    time_column: str | None
    entity_column: str | None


@dataclass
class JoinPlan:
    table: TableUse
    relationship: dict[str, Any]
    pairs: list[tuple[str, str, str, str]]  # (left_alias, left_column, right_alias, right_column)


@dataclass
class SelectItem:
    name: str
    table: str
    alias: str
    column: str
    function: str | None
    data_type: str
    unit: str | None = None  # AI_column_catalog.unit; a COUNT has no unit


@dataclass
class FilterPlan:
    alias: str
    column: str
    operator: str
    values: list[Any]


@dataclass
class ValidatedQuery:
    tables: list[TableUse]
    joins: list[JoinPlan]
    select: list[SelectItem]
    filters: list[FilterPlan]
    group_by: list[tuple[str, str]]
    order_by: list[tuple[SelectItem, str]]
    limit: int | None
    requested_range: dict[str, str | None] | None = None
    requested_entities: list[str] | None = None
    time_output: str | None = None
    entity_output: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def source_tables(self) -> list[str]:
        return [table.name for table in self.tables]


def _coerce(value: Any, data_type: str, label: str) -> Any:
    kind = data_type.lower()
    invalid = rejected("INVALID_FILTER_VALUE", f"{label}: value {value!r} does not match column type {data_type}.")
    if isinstance(value, bool) and kind != "boolean":
        raise invalid
    try:
        if kind == "date":
            if not isinstance(value, str):
                raise invalid
            return date.fromisoformat(value)
        if kind.startswith("timestamp"):
            if not isinstance(value, str):
                raise invalid
            return datetime.fromisoformat(value)
        if kind in ("smallint", "integer", "bigint"):
            if isinstance(value, float) and not value.is_integer():
                raise invalid
            if isinstance(value, str):
                raise invalid
            return int(value)
        if kind in ("numeric", "real", "double precision"):
            if isinstance(value, str):
                raise invalid
            return Decimal(str(value))
        if kind == "boolean":
            if not isinstance(value, bool):
                raise invalid
            return value
        if not isinstance(value, str) or len(value) > 200:
            raise invalid
        return value
    except (ValueError, InvalidOperation) as exc:
        raise invalid from exc


class Validator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate(self, spec: DataRequestSpec, policy: Policy) -> ValidatedQuery:
        tables, joins = self._tables_and_joins(spec, policy)
        alias_of = {table.name: table.alias for table in tables}
        column = self._column_gate(policy, alias_of)

        if len(spec.columns) + len(spec.aggregations) > self.settings.max_columns:
            raise narrowing("TOO_MANY_COLUMNS", f"At most {self.settings.max_columns} output columns are allowed.",
                            limit=self.settings.max_columns)
        if not spec.columns and not spec.aggregations:
            raise rejected("NO_COLUMNS", "Request at least one column or aggregation.")

        # Gate 5 - GROUP BY
        group_keys: list[tuple[str, str]] = []
        for ref in spec.group_by:
            meta = column(ref, "group by")
            if not meta["group_by_allowed"]:
                raise rejected("GROUP_BY_NOT_ALLOWED", f"{ref.table}.{ref.column} cannot be used in GROUP BY.")
            group_keys.append((ref.table, ref.column))
        if len(set(group_keys)) != len(group_keys):
            raise rejected("DUPLICATE_GROUP_BY", "group_by contains duplicates.")

        # Gate 2 - selected columns, Gate 6 - aggregations
        select: list[SelectItem] = []
        seen: set[tuple[str, str, str | None]] = set()
        for ref in spec.columns:
            meta = column(ref, "select")
            key = (ref.table, ref.column, None)
            if key in seen:
                raise rejected("DUPLICATE_COLUMN", f"{ref.table}.{ref.column} is requested twice.")
            seen.add(key)
            if (spec.aggregations or spec.group_by) and (ref.table, ref.column) not in group_keys:
                raise rejected("COLUMN_NOT_GROUPED",
                               f"{ref.table}.{ref.column} must be listed in group_by when aggregating or grouping.")
            select.append(SelectItem(ref.column, ref.table, alias_of[ref.table], ref.column, None, meta["data_type"],
                                     meta.get("unit")))
        for agg in spec.aggregations:
            meta = column(agg, "aggregate")
            allowed = list(meta["allowed_aggregations"] or [])
            if agg.function not in allowed:
                raise rejected("AGGREGATION_NOT_ALLOWED",
                               f"{agg.function} is not allowed on {agg.table}.{agg.column}.", allowed=allowed)
            key = (agg.table, agg.column, agg.function)
            if key in seen:
                raise rejected("DUPLICATE_AGGREGATION", f"{agg.function}({agg.table}.{agg.column}) is requested twice.")
            seen.add(key)
            result_type = "bigint" if agg.function in ("COUNT", "COUNT_DISTINCT") else (
                "numeric" if agg.function in ("SUM", "AVG", "MEDIAN") else meta["data_type"])
            select.append(SelectItem(f"{SQL_FUNCTIONS[agg.function]}_{agg.column}", agg.table,
                                     alias_of[agg.table], agg.column, agg.function, result_type,
                                     None if agg.function in ("COUNT", "COUNT_DISTINCT") else meta.get("unit")))
        self._unique_output_names(select)

        # Gate 3 - filters
        if len(spec.filters) > self.settings.max_filters:
            raise narrowing("TOO_MANY_FILTERS", f"At most {self.settings.max_filters} filters are allowed.",
                            limit=self.settings.max_filters)
        filters = [self._filter(item, column(item, "filter"), alias_of) for item in spec.filters]

        order_by = self._order_by(spec, select)
        limit = spec.requested_limit
        query = ValidatedQuery(tables, joins, select, filters,
                               [(alias_of[t], c) for t, c in group_keys], order_by, limit)
        self._coverage_gate(spec, policy, query)
        return query

    # Gate 1 - tables, Gate 4 - joins
    def _tables_and_joins(self, spec: DataRequestSpec, policy: Policy) -> tuple[list[TableUse], list[JoinPlan]]:
        if len(spec.joins) > self.settings.max_joins:
            raise narrowing("TOO_MANY_JOINS", f"At most {self.settings.max_joins} joins are allowed.",
                            limit=self.settings.max_joins)
        names = [spec.from_table, *(join.table for join in spec.joins)]
        if len(set(names)) != len(names):
            raise rejected("DUPLICATE_TABLE", "Each table may appear once (no self-joins).")
        if len(names) > self.settings.max_tables:
            raise narrowing("TOO_MANY_TABLES", f"At most {self.settings.max_tables} tables are allowed.",
                            limit=self.settings.max_tables)
        tables: list[TableUse] = []
        for index, name in enumerate(names):
            meta = policy.tables.get(name)
            if meta is None:
                raise rejected("TABLE_NOT_APPROVED", f"{name} is not an approved AI catalog table.")
            if not meta["is_active"]:
                raise rejected("TABLE_INACTIVE", f"{name} is inactive in AI_table_catalog.")
            if meta["ai_access_level"] != "BOUNDED_READ":
                raise rejected("TABLE_DENIED", f"{name} has ai_access_level {meta['ai_access_level']}.")
            tables.append(TableUse(name, f"t{index}", meta["time_column"], meta["entity_column"]))

        joins: list[JoinPlan] = []
        joined = [tables[0]]
        for spec_join, table in zip(spec.joins, tables[1:]):
            present = {item.name: item for item in joined}
            candidates = [
                rel for rel in policy.relationships
                if (rel["left_table"] in present and rel["right_table"] == table.name)
                or (rel["right_table"] in present and rel["left_table"] == table.name)
            ]
            if spec_join.relationship_id is not None:
                candidates = [rel for rel in candidates if rel["relationship_id"] == spec_join.relationship_id]
                if not candidates:
                    raise rejected("UNKNOWN_RELATIONSHIP",
                                   f"relationship_id {spec_join.relationship_id} does not connect {table.name} "
                                   "to a table already in the request.")
            allowed = [rel for rel in candidates if rel["is_allowed"]]
            if not allowed:
                code = "RELATIONSHIP_NOT_ALLOWED" if candidates else "RELATIONSHIP_NOT_APPROVED"
                raise rejected(code, f"No approved catalog relationship joins {table.name} to "
                                     f"{', '.join(present)}.")
            if len(allowed) > 1:
                raise rejected("AMBIGUOUS_RELATIONSHIP", f"Several relationships join {table.name}; set relationship_id.",
                               relationship_ids=[rel["relationship_id"] for rel in allowed])
            rel = allowed[0]
            if rel["requires_preaggregation"]:
                raise rejected(
                    "PREAGGREGATION_REQUIRED",
                    f"Relationship {rel['relationship_id']} requires pre-aggregation; a direct row-level join "
                    "would duplicate rows. Request each table separately at the safe output grain.",
                    relationship=_relationship_info(rel),
                )
            if rel["right_table"] == table.name:
                other = present[rel["left_table"]]
                pairs = [(other.alias, lc, table.alias, rc) for lc, rc in zip(rel["left_columns"], rel["right_columns"])]
            else:
                other = present[rel["right_table"]]
                pairs = [(other.alias, rc, table.alias, lc) for lc, rc in zip(rel["left_columns"], rel["right_columns"])]
            joins.append(JoinPlan(table, rel, pairs))
            joined.append(table)
        return tables, joins

    def _column_gate(self, policy: Policy, alias_of: dict[str, str]):
        def column(ref: ColumnRef | FilterSpec | AggregationSpec, usage: str) -> dict[str, Any]:
            if ref.table not in alias_of:
                raise rejected("TABLE_NOT_IN_REQUEST", f"{ref.table} is not from_table or a joined table.")
            meta = policy.columns.get((ref.table, ref.column))
            if meta is None:
                raise rejected("UNKNOWN_COLUMN", f"{ref.table}.{ref.column} is not in AI_column_catalog.")
            if not meta["ai_allowed"] or meta["is_sensitive"]:
                raise rejected("COLUMN_NOT_ALLOWED",
                               f"{ref.table}.{ref.column} is not available to the AI ({usage}).")
            return meta
        return column

    def _filter(self, item: FilterSpec, meta: dict[str, Any], alias_of: dict[str, str]) -> FilterPlan:
        label = f"{item.table}.{item.column} {item.operator}"
        if not meta["filter_allowed"]:
            raise rejected("FILTER_NOT_ALLOWED", f"{item.table}.{item.column} cannot be filtered.")
        value = item.value
        if item.operator in ("IS_NULL", "IS_NOT_NULL"):
            if value is not None:
                raise rejected("INVALID_FILTER_VALUE", f"{label} takes value null.")
            values: list[Any] = []
        elif item.operator == "IN":
            if not isinstance(value, list) or not value:
                raise rejected("INVALID_FILTER_VALUE", f"{label} needs a non-empty list.")
            if len(value) > self.settings.max_in_values:
                raise narrowing("TOO_MANY_IN_VALUES", f"{label} allows at most {self.settings.max_in_values} values.",
                                limit=self.settings.max_in_values)
            values = list(dict.fromkeys(_coerce(entry, meta["data_type"], label) for entry in value))
        elif item.operator == "BETWEEN":
            if not isinstance(value, list) or len(value) != 2:
                raise rejected("INVALID_FILTER_VALUE", f"{label} needs [low, high].")
            values = [_coerce(entry, meta["data_type"], label) for entry in value]
            if values[0] > values[1]:
                raise rejected("INVALID_FILTER_VALUE", f"{label} low bound is above high bound.")
        else:
            if value is None or isinstance(value, list):
                raise rejected("INVALID_FILTER_VALUE", f"{label} needs one scalar value.")
            values = [_coerce(value, meta["data_type"], label)]
        return FilterPlan(alias_of[item.table], item.column, item.operator, values)

    @staticmethod
    def _unique_output_names(select: list[SelectItem]) -> None:
        counts: dict[str, int] = {}
        for item in select:
            counts[item.name] = counts.get(item.name, 0) + 1
        for item in select:
            if counts[item.name] > 1:
                item.name = f"{item.table}.{item.name}"

    @staticmethod
    def _order_by(spec: DataRequestSpec, select: list[SelectItem]) -> list[tuple[SelectItem, str]]:
        result = []
        for order in spec.order_by:
            match = next((item for item in select if (item.table, item.column, item.function)
                          == (order.table, order.column, order.function)), None)
            if match is None:
                raise rejected("ORDER_BY_NOT_IN_OUTPUT",
                               f"order_by {order.table}.{order.column} ({order.function}) must be a returned column "
                               "or a requested aggregation.")
            result.append((match, order.direction))
        return result

    # Gate 7 - coverage and date-range bounds
    def _coverage_gate(self, spec: DataRequestSpec, policy: Policy, query: ValidatedQuery) -> None:
        by_alias = {table.alias: table for table in query.tables}
        time_filters: list[FilterPlan] = []
        entity_values: list[str] = []
        entity_filtered = False
        for plan in query.filters:
            table = by_alias[plan.alias]
            if table.time_column and plan.column == table.time_column:
                time_filters.append(plan)
            if table.entity_column and plan.column == table.entity_column and plan.operator in ("EQ", "IN"):
                entity_filtered = True
                entity_values.extend(str(value) for value in plan.values)
        timed = [table for table in query.tables if table.time_column]
        for item in query.select:
            table = next(t for t in query.tables if t.alias == item.alias)
            if item.function is None and table.time_column == item.column and query.time_output is None:
                query.time_output = item.name
            if item.function is None and table.entity_column == item.column and query.entity_output is None:
                query.entity_output = item.name
        if entity_values:
            query.requested_entities = sorted(set(entity_values))
        if not timed:
            return

        low, high = None, None
        for plan in time_filters:
            if plan.operator in ("EQ", "IN", "BETWEEN"):
                low = max(filter(None, [low, min(plan.values)]), default=None)
                high = min(filter(None, [high, max(plan.values)]), default=None)
            elif plan.operator in ("GT", "GTE"):
                low = max(filter(None, [low, plan.values[0]]), default=None)
            elif plan.operator in ("LT", "LTE"):
                high = min(filter(None, [high, plan.values[0]]), default=None)

        primary = timed[0]
        coverage = policy.coverage.get(primary.name) or {}
        verified = coverage.get("coverage_mode") == "ACTUAL_SOURCE" and coverage.get("verification_status") == "VERIFIED"
        cov_low = coverage.get("actual_min_date") if verified else coverage.get("expected_min_date")
        cov_high = coverage.get("actual_max_date") if verified else coverage.get("expected_max_date")
        available = {"from": _iso(cov_low), "to": _iso(cov_high), "verified": verified,
                     "coverage_mode": coverage.get("coverage_mode"),
                     "verification_status": coverage.get("verification_status")}

        if verified and cov_low and cov_high and (
            (low and _as_date(low) > cov_high) or (high and _as_date(high) < cov_low)
        ):
            raise narrowing("OUTSIDE_VERIFIED_COVERAGE",
                            f"The requested period is outside the verified coverage of {primary.name}.",
                            available_range=available)
        if coverage and not verified:
            query.warnings.append(
                f"{primary.name} coverage is {coverage.get('coverage_mode')}/{coverage.get('verification_status')}: "
                "the recorded range is expected, not confirmed physical availability.")
        elif not coverage:
            query.warnings.append(f"{primary.name} has no DATASET coverage record.")

        start = _as_date(low) if low else cov_low
        end = _as_date(high) if high else (cov_high or date.today())
        limit = self.settings.max_date_range_days if entity_filtered else self.settings.max_unfiltered_date_range_days
        query.requested_range = {"from": _iso(low), "to": _iso(high)}
        if start is None:
            raise narrowing("TIME_FILTER_REQUIRED",
                            f"Add a {primary.time_column} filter on {primary.name}; no coverage range is recorded.",
                            max_days=limit, entity_filtered=entity_filtered, available_range=available)
        span = (end - start).days + 1
        if span > limit:
            raise narrowing(
                "DATE_RANGE_TOO_LARGE",
                f"The effective {primary.time_column} range is {span} days; the limit is {limit} days "
                f"{'with' if entity_filtered else 'without'} a filter on {primary.entity_column}.",
                max_days=limit, entity_filtered=entity_filtered, effective_range={"from": _iso(start), "to": _iso(end)},
                available_range=available,
            )
        if verified and cov_low and cov_high and (start < cov_low or end > cov_high):
            query.warnings.append(
                f"Part of the requested period lies outside the verified coverage of {primary.name} "
                f"({_iso(cov_low)} to {_iso(cov_high)}).")


def _as_date(value: Any) -> date:
    return value.date() if isinstance(value, datetime) else value


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _relationship_info(rel: dict[str, Any]) -> dict[str, Any]:
    return {key: rel[key] for key in ("relationship_id", "left_table", "left_columns", "right_table",
                                     "right_columns", "relationship_type", "temporal_rule",
                                     "safe_output_grain", "requires_preaggregation")}
