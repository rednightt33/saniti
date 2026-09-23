"""Gate 8: compile a validated request into parameterized SQL.

Identifiers come only from catalog-validated names and are composed with psycopg.sql.Identifier;
every filter value is a bound parameter. There is no code path that places model text into SQL.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from psycopg import sql

from .policy import SelectItem, ValidatedQuery

OPERATORS = {"EQ": "=", "NEQ": "<>", "GT": ">", "GTE": ">=", "LT": "<", "LTE": "<="}
AGGREGATES = {"SUM": "sum", "AVG": "avg", "MIN": "min", "MAX": "max", "COUNT": "count"}


@dataclass(frozen=True)
class CompiledQuery:
    statement: sql.Composed
    params: tuple[Any, ...]
    text: str  # rendered SQL with placeholders; used for hashing and logs, never executed as text

    @property
    def query_hash(self) -> str:
        payload = json.dumps({"sql": self.text, "params": [str(value) for value in self.params]},
                             sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _column(alias: str, column: str) -> sql.Composable:
    return sql.Identifier(alias, column)


def _expression(item: SelectItem) -> sql.Composable:
    ref = _column(item.alias, item.column)
    if item.function is None:
        return ref
    if item.function == "COUNT_DISTINCT":
        return sql.SQL("count(DISTINCT {})").format(ref)
    if item.function == "MEDIAN":
        return sql.SQL("percentile_cont(0.5) WITHIN GROUP (ORDER BY {})").format(ref)
    return sql.SQL("{}({})").format(sql.SQL(AGGREGATES[item.function]), ref)


def compile_query(query: ValidatedQuery, row_cap: int) -> CompiledQuery:
    params: list[Any] = []
    select = sql.SQL(", ").join(
        sql.SQL("{} AS {}").format(_expression(item), sql.Identifier(item.name)) for item in query.select
    )
    base = query.tables[0]
    source = sql.SQL("{} AS {}").format(sql.Identifier("public", base.name), sql.Identifier(base.alias))
    for join in query.joins:
        condition = sql.SQL(" AND ").join(
            sql.SQL("{} = {}").format(_column(la, lc), _column(ra, rc)) for la, lc, ra, rc in join.pairs
        )
        source = sql.SQL("{} JOIN {} AS {} ON {}").format(
            source, sql.Identifier("public", join.table.name), sql.Identifier(join.table.alias), condition
        )

    conditions: list[sql.Composable] = []
    for plan in query.filters:
        ref = _column(plan.alias, plan.column)
        if plan.operator == "IS_NULL":
            conditions.append(sql.SQL("{} IS NULL").format(ref))
        elif plan.operator == "IS_NOT_NULL":
            conditions.append(sql.SQL("{} IS NOT NULL").format(ref))
        elif plan.operator == "IN":
            conditions.append(sql.SQL("{} = ANY({})").format(ref, sql.Placeholder()))
            params.append(list(plan.values))
        elif plan.operator == "BETWEEN":
            conditions.append(sql.SQL("{} BETWEEN {} AND {}").format(ref, sql.Placeholder(), sql.Placeholder()))
            params.extend(plan.values)
        else:
            conditions.append(sql.SQL("{} {} {}").format(ref, sql.SQL(OPERATORS[plan.operator]), sql.Placeholder()))
            params.append(plan.values[0])

    parts: list[sql.Composable] = [sql.SQL("SELECT "), select, sql.SQL(" FROM "), source]
    if conditions:
        parts += [sql.SQL(" WHERE "), sql.SQL(" AND ").join(conditions)]
    if query.group_by:
        parts += [sql.SQL(" GROUP BY "), sql.SQL(", ").join(_column(a, c) for a, c in query.group_by)]
    if query.order_by:
        parts += [sql.SQL(" ORDER BY "), sql.SQL(", ").join(
            sql.SQL("{} {}").format(sql.Identifier(item.name), sql.SQL("ASC" if direction == "ASC" else "DESC"))
            for item, direction in query.order_by
        )]
    parts += [sql.SQL(" LIMIT "), sql.Placeholder()]
    params.append(row_cap)
    statement = sql.Composed(parts)
    return CompiledQuery(statement, tuple(params), statement.as_string(None))
