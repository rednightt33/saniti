"""POST /v1/summary: a summary over a period, per entity or group, returned as rows (G18 phase 2; round 2026-10-03 D5,
ROUND_PLAN_2026-10-03_FASE_D.md).

G18 phase 1 (/v1/extract with aggregate) sums across entities on the same date and delivers a Parquet dataset. A short
question ("net foreign buy of BBCA over 5 and 20 trading days") and a claim check (get_evidence) need the other
direction: one value per entity (or group) over a period, a few rows, straight back. The spec is catalog identifiers
and canonical values only, never SQL:

- source_table, scope (the canonical scope tree) and restrictions (INNER semi-joins), exactly as /v1/extract;
- group_by: the columns that stay (the entity, a board, a broker, ...); never the time column;
- measures: {column, function, as} with function SUM, MIN, MAX, FIRST, LAST or COUNT (rows, column null);
- period: {from, to}, or {trading_days: N, as_of}: the last N dates of the table's own calendar up to as_of.

The rules are derived from the Governor's own catalog contract (the caller's choice is not trusted):

- over time: SUM needs resample_aggregation SUM, FIRST and LAST need resample_aggregation FIRST or LAST, MIN and MAX a
  numeric MEASURE column; COUNT counts rows;
- across the grain keys a summary drops (entity, board, broker, investor type, ...): SUM needs
  cross_entity_aggregation SUM; FIRST and LAST keep every non-time grain key (one value per date);
- every group also returns days_present (dates with a row), first_date and last_date, and the response the window's
  own trading days, so coverage is visible next to the value.

The compiled SQL is EXPLAINed under the extraction limits (plan cost, scanned rows) and runs under the session's
statement timeout. At most 200 rows: a larger summary is refused, never cut.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import extract as ex
from .catalog_contract import sha256_json
from .compiler import CompiledQuery

SUMMARY_VERSION = "summary_spec/v1"
MAX_ROWS = 200
MAX_TRADING_DAYS = 260
MAX_RANGE_DAYS = 3660
FUNCTIONS = ("SUM", "MIN", "MAX", "FIRST", "LAST", "COUNT")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SummaryMeasure(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    column: str | None = Field(pattern=ex.COLUMN_PATTERN)
    function: Literal["SUM", "MIN", "MAX", "FIRST", "LAST", "COUNT"]
    alias: str = Field(alias="as", pattern=ex.ALIAS_PATTERN)


class Period(Strict):
    """Either a date range (from, to) or the last trading_days dates of the table's calendar up to as_of."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start: str | None = Field(default=None, alias="from", pattern=ex.DATE_PATTERN)
    end: str | None = Field(default=None, alias="to", pattern=ex.DATE_PATTERN)
    trading_days: int | None = Field(default=None, ge=1, le=MAX_TRADING_DAYS)
    as_of: str | None = Field(default=None, pattern=ex.DATE_PATTERN)

    @model_validator(mode="after")
    def _one_form(self) -> "Period":
        ranged = self.start is not None and self.end is not None
        counted = self.trading_days is not None and self.as_of is not None
        if ranged == counted or (not ranged and (self.start or self.end)) or (
                not counted and (self.trading_days or self.as_of)):
            raise ValueError("give either from and to, or trading_days and as_of")
        return self


class SummarySpec(Strict):
    summary_version: Literal["summary_spec/v1"]
    source_table: str = Field(pattern=ex.TABLE_PATTERN)
    scope: ex.ScopeNode
    restrictions: list[ex.Restriction] = Field(max_length=8)
    group_by: list[str] = Field(max_length=6)
    measures: list[SummaryMeasure] = Field(min_length=1, max_length=10)
    period: Period


class SummaryLineage(Strict):
    """Who asked and why, and the hash of the summary exactly as sent (checked like extraction_sha256)."""

    purpose: Literal["METRIC", "EVIDENCE"]
    recipe_sha256: str = Field(pattern=ex.SHA256_PATTERN)
    metric_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")


@dataclass
class BoundSummary:
    spec: SummarySpec
    table: dict[str, Any]
    group_by: list[dict[str, Any]]
    measures: list[dict[str, Any]]
    scope: ex.BoundNode
    restrictions: list[ex.BoundRestriction]
    dropped: list[str] = field(default_factory=list)

    @property
    def time_column(self) -> str:
        return str(self.table["time_column"])

    @property
    def source_tables(self) -> list[str]:
        return list(dict.fromkeys([self.spec.source_table, *(r.right_table for r in self.restrictions)]))


def bind_summary(spec: SummarySpec, contract: dict[str, Any], *, max_in_values: int) -> BoundSummary:
    """Validate a summary against the catalog contract of its tables (pure)."""
    table = spec.source_table
    meta = (contract.get("tables") or {}).get(table)
    if meta is None:
        raise ex.policy("TABLE_NOT_APPROVED", f"{table} is not an active, AI-readable catalog table.")
    time_column = meta.get("time_column")
    if not time_column:
        raise ex.policy("SUMMARY_NEEDS_TIME", f"{table} has no time column; a summary over a period needs one.")
    known = (contract.get("columns") or {}).get(table) or {}
    grain = list(dict.fromkeys(c for c in (meta.get("entity_column"), *(meta.get("primary_key_columns") or []))
                               if c and c != time_column))
    if len(set(spec.group_by)) != len(spec.group_by):
        raise ex.policy("SUMMARY_INVALID", f"{table}: a group_by column is repeated.")
    group_by = []
    for name in spec.group_by:
        info = known.get(name)
        if info is None:
            raise ex.policy("COLUMN_NOT_ALLOWED", f"{table}.{name} is not an AI-allowed catalog column.")
        if name == time_column:
            raise ex.policy("SUMMARY_INVALID", f"{table}: the time column is summarised over the period, not grouped.")
        if not (info.get("group_by_allowed") or name in grain):
            raise ex.policy("AGGREGATE_GROUP_BY_NOT_ALLOWED", f"{table}.{name} cannot be grouped.")
        group_by.append({"name": name, "data_type": info.get("data_type") or "text", "unit": info.get("unit")})
    dropped = [c for c in grain if c not in spec.group_by]
    measures, aliases = [], {c["name"] for c in group_by} | {"days_present", "first_date", "last_date"}
    for measure in spec.measures:
        label = f"{table}.{measure.column or '*'} {measure.function}"
        if measure.alias in aliases or measure.alias in known:
            raise ex.policy("SUMMARY_INVALID", f"{label}: the name {measure.alias!r} is taken.")
        aliases.add(measure.alias)
        if (measure.function == "COUNT") != (measure.column is None):
            raise ex.policy("SUMMARY_INVALID", f"{label}: COUNT counts rows (column null); the others name a column.")
        info = known.get(measure.column) if measure.column else {}
        if info is None:
            raise ex.policy("COLUMN_NOT_ALLOWED", f"{label}: not an AI-allowed catalog column.")
        kind = str(info.get("data_type") or "text").lower()
        semantic = str(info.get("semantic_type") or "").upper()
        over_time = info.get("resample_aggregation")
        if measure.function == "SUM":
            if over_time != "SUM":
                raise ex.policy("AGGREGATION_NOT_ADDITIVE", f"{label}: the catalog has no SUM rule over time "
                                                            f"(resample_aggregation {over_time}).")
            if dropped and info.get("cross_entity_aggregation") != "SUM":
                raise ex.policy("AGGREGATION_NOT_ADDITIVE", f"{label}: the catalog has no SUM rule across "
                                                            f"{', '.join(dropped)}; group by them.", dropped=dropped)
        elif measure.function in ("FIRST", "LAST"):
            if over_time != measure.function:
                raise ex.policy("AGGREGATION_NOT_ALLOWED", f"{label}: the catalog's rule over time is {over_time}.")
            if dropped:
                raise ex.policy("AGGREGATION_NOT_ALLOWED", f"{label}: {measure.function} needs one value per date; "
                                                           f"group by {', '.join(dropped)}.", dropped=dropped)
        elif measure.function in ("MIN", "MAX") and (kind not in ex.NUMERIC or semantic != "MEASURE"):
            raise ex.policy("AGGREGATION_NOT_ALLOWED", f"{label}: MIN and MAX apply to numeric measures.")
        counted = measure.function == "COUNT"
        measures.append({"name": measure.alias, "function": measure.function, "source_column": measure.column,
                         "data_type": "bigint" if counted else info.get("data_type") or "numeric",
                         "unit": None if counted else info.get("unit")})
    scope = ex._bind_scope(spec.scope, known, table, max_in_values)
    restrictions = [ex._bind_restriction(i, item, meta, contract, max_in_values)
                    for i, item in enumerate(spec.restrictions)]
    return BoundSummary(spec, meta, group_by, measures, scope, restrictions, dropped)


def calendar_sql(table: str, time_column: str) -> sql.Composable:
    """The table's own dates at or before a date, newest first, by a loose index scan (one probe per date), bounded
    by a count and an earliest date: SELECT d FROM (...) with params (as_of, earliest, limit)."""
    t, c = sql.Identifier("public", table), sql.Identifier(time_column)
    return sql.SQL(
        "WITH RECURSIVE cal(d) AS ((SELECT {c} FROM {t} WHERE {c} <= %s ORDER BY {c} DESC LIMIT 1) UNION ALL "
        "SELECT (SELECT {c} FROM {t} WHERE {c} < cal.d ORDER BY {c} DESC LIMIT 1) FROM cal WHERE cal.d >= %s) "
        "SELECT d FROM cal WHERE d IS NOT NULL AND d >= %s LIMIT %s").format(c=c, t=t)


def _measure(base: str, measure: dict[str, Any], time_column: str) -> sql.Composable:
    function = measure["function"]
    if function == "COUNT":
        return sql.SQL("count(*)")
    source = ex._column(base, measure["source_column"])
    if function in ("FIRST", "LAST"):
        return sql.SQL("(array_agg({s} ORDER BY {t} {d}) FILTER (WHERE {s} IS NOT NULL))[1]").format(
            s=source, t=ex._column(base, time_column), d=sql.SQL("ASC" if function == "FIRST" else "DESC"))
    return sql.SQL("{}({})").format(sql.SQL(function.lower()), source)


def compile_summary(bound: BoundSummary, start: date, end: date, row_cap: int | None) -> CompiledQuery:
    base = "t0"
    params: list[Any] = [start, end]
    keys = [ex._column(base, g["name"]) for g in bound.group_by]
    time = ex._column(base, bound.time_column)
    select = [sql.SQL("{} AS {}").format(k, sql.Identifier(g["name"])) for k, g in zip(keys, bound.group_by)]
    select += [sql.SQL("{} AS {}").format(_measure(base, m, bound.time_column), sql.Identifier(m["name"]))
               for m in bound.measures]
    select += [sql.SQL("count(DISTINCT {}) AS {}").format(time, sql.Identifier("days_present")),
               sql.SQL("min({}) AS {}").format(time, sql.Identifier("first_date")),
               sql.SQL("max({}) AS {}").format(time, sql.Identifier("last_date"))]
    conditions = [sql.SQL("{} BETWEEN {} AND {}").format(time, sql.Placeholder(), sql.Placeholder())]
    if bound.scope.type != "ALL":
        conditions.append(ex._scope_sql(bound.scope, base, params))
    for restriction in bound.restrictions:
        conditions.append(ex._restriction_sql(restriction, base, bound.time_column, params))
    parts: list[sql.Composable] = [
        sql.SQL("SELECT "), sql.SQL(", ").join(select),
        sql.SQL(" FROM {} AS {} WHERE ").format(sql.Identifier("public", bound.spec.source_table),
                                                sql.Identifier(base)),
        sql.SQL(" AND ").join(conditions)]
    if keys:
        parts += [sql.SQL(" GROUP BY "), sql.SQL(", ").join(keys), sql.SQL(" ORDER BY "),
                  sql.SQL(", ").join(sql.SQL("{} ASC").format(k) for k in keys)]
    else:
        parts.append(sql.SQL(" HAVING count(*) > 0"))
    if row_cap is not None:
        parts += [sql.SQL(" LIMIT "), sql.Placeholder()]
        params.append(row_cap)
    statement = sql.Composed(parts)
    return CompiledQuery(statement, tuple(params), statement.as_string(None))


def recipe_sha256(raw: Any) -> str:
    return sha256_json(raw)
