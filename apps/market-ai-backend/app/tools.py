from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from time import monotonic
from typing import Any, Callable

from psycopg import sql

from .compaction import compact_result, dumps, query_hash
from .config import Settings
from .db import Database


class ToolError(ValueError):
    pass


OPERATORS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
AGGREGATIONS = {
    "SUM": "SUM", "AVG": "AVG", "MIN": "MIN", "MAX": "MAX", "COUNT": "COUNT",
    "COUNT_DISTINCT": "COUNT_DISTINCT", "MEDIAN": "MEDIAN",
}


def _object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or list(properties),
        "additionalProperties": False,
    }


QUERY_PROPERTIES = {
    "table": {"type": "string"},
    "columns": {"type": "array", "items": {"type": "string"}},
    "tickers": {"type": ["array", "null"], "items": {"type": "string"}},
    "start_date": {"type": ["string", "null"]},
    "end_date": {"type": ["string", "null"]},
    "filters": {
        "type": ["array", "null"],
        "items": _object_schema({
            "column": {"type": "string"},
            "operator": {"type": "string", "enum": list(OPERATORS) + ["in", "between"]},
            "value": {
                "type": ["string", "number", "boolean", "null", "array"],
                "items": {"type": ["string", "number", "boolean", "null"]},
            },
        }),
    },
    "order_by": {
        "type": ["array", "null"],
        "items": _object_schema({
            "column": {"type": "string"},
            "direction": {"type": "string", "enum": ["asc", "desc"]},
        }),
    },
    "limit": {"type": ["integer", "null"]},
}


@dataclass
class Execution:
    payload: dict[str, Any]
    query_hash: str | None = None
    estimated_rows: int | None = None
    processed_rows: int | None = None
    duration_ms: int = 0


class ToolRegistry:
    """Catalog-driven structured tools. No handler accepts SQL text."""

    CORE_FAMILIES = {"META", "DISCOVERY", "QUALITY"}
    ALWAYS_EXPOSED = {"record_evidence", "complete_analysis"}
    STAGE_FAMILIES = {
        "DISCOVERY": CORE_FAMILIES,
        "SCREENING": CORE_FAMILIES | {"QUERY", "SCREENING"},
        "HISTORICAL_VALIDATION": CORE_FAMILIES | {"QUERY", "SCREENING", "HISTORICAL_VALIDATION"},
        "ADVANCED": CORE_FAMILIES | {"QUERY", "SCREENING", "HISTORICAL_VALIDATION", "ADVANCED"},
    }

    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.handlers: dict[str, Callable[[dict[str, Any], str], Execution]] = {
            "list_tools": self.list_tools,
            "validate_query_request": self.validate_query_request,
            "estimate_query_size": self.estimate_query_size,
            "find_features": self.find_features,
            "get_feature_definition": self.get_feature_definition,
            "list_feature_tables": self.list_feature_tables,
            "check_data_freshness": self.check_data_freshness,
            "check_data_quality": self.check_data_quality,
            "query_features": self.query_features,
            "get_timeseries": self.get_timeseries,
            "compare_periods": self.compare_periods,
            "screen_features": self.screen_features,
            "rank_features": self.rank_features,
            "aggregate_features": self.aggregate_features,
            "compare_groups": self.compare_groups,
            "record_evidence": self.record_evidence,
            "complete_analysis": self.complete_analysis,
            "get_analysis_history": self.get_analysis_history,
        }

    def definitions(self, families: set[str]) -> list[dict[str, Any]]:
        with self.db.query_transaction() as connection:
            rows = connection.execute(
                '''SELECT tool_name, purpose, tool_family FROM public."Tool_Catalog"
                   WHERE is_active AND (tool_family = ANY(%s) OR tool_name = ANY(%s))
                   ORDER BY tool_name''',
                (sorted(families), sorted(self.ALWAYS_EXPOSED)),
            ).fetchall()
        definitions = []
        for row in rows:
            name = row["tool_name"]
            if name not in self.handlers:
                continue
            definitions.append({
                "type": "function",
                "name": name,
                "description": row["purpose"],
                "parameters": self.schema_for(name),
                "strict": True,
            })
        return definitions

    @staticmethod
    def schema_for(name: str) -> dict[str, Any]:
        query_schema = _object_schema(QUERY_PROPERTIES)
        schemas: dict[str, dict[str, Any]] = {
            "list_tools": _object_schema({
                "requested_families": {"type": ["array", "null"], "items": {"type": "string", "enum": ["QUERY", "SCREENING", "HISTORICAL_VALIDATION", "ADVANCED"]}},
                "justification": {"type": ["string", "null"]},
            }),
            "validate_query_request": query_schema,
            "estimate_query_size": query_schema,
            "find_features": _object_schema({
                "search_text": {"type": "string"},
                "tables": {"type": ["array", "null"], "items": {"type": "string"}},
                "limit": {"type": ["integer", "null"]},
            }),
            "get_feature_definition": _object_schema({
                "features": {"type": "array", "items": _object_schema({"table": {"type": "string"}, "column": {"type": "string"}})},
            }),
            "list_feature_tables": _object_schema({"include_columns": {"type": "boolean"}}),
            "check_data_freshness": _object_schema({"tables": {"type": "array", "items": {"type": "string"}}}),
            "check_data_quality": _object_schema({
                "table": {"type": "string"}, "tickers": {"type": ["array", "null"], "items": {"type": "string"}},
                "start_date": {"type": ["string", "null"]}, "end_date": {"type": ["string", "null"]},
            }),
            "query_features": query_schema,
            "get_timeseries": _object_schema({
                "table": {"type": "string"}, "ticker": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "start_date": {"type": "string"}, "end_date": {"type": "string"}, "limit": {"type": ["integer", "null"]},
            }),
            "compare_periods": _object_schema({
                "table": {"type": "string"}, "ticker": {"type": "string"}, "column": {"type": "string"},
                "periods": {"type": "array", "items": _object_schema({"label": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}})},
                "aggregation": {"type": "string", "enum": ["AVG", "SUM", "MIN", "MAX", "MEDIAN"]},
            }),
            "screen_features": query_schema,
            "rank_features": _object_schema({
                "table": {"type": "string"}, "column": {"type": "string"}, "direction": {"type": "string", "enum": ["asc", "desc"]},
                "tickers": {"type": ["array", "null"], "items": {"type": "string"}}, "date": {"type": "string"}, "limit": {"type": ["integer", "null"]},
            }),
            "aggregate_features": _object_schema({
                "table": {"type": "string"}, "group_by": {"type": "array", "items": {"type": "string"}},
                "metrics": {"type": "array", "items": _object_schema({"column": {"type": "string"}, "aggregation": {"type": "string", "enum": list(AGGREGATIONS)}})},
                "tickers": {"type": ["array", "null"], "items": {"type": "string"}}, "start_date": {"type": "string"}, "end_date": {"type": "string"}, "limit": {"type": ["integer", "null"]},
            }),
            "compare_groups": _object_schema({
                "table": {"type": "string"}, "group_column": {"type": "string"}, "metric_column": {"type": "string"},
                "aggregation": {"type": "string", "enum": ["AVG", "SUM", "MIN", "MAX", "MEDIAN"]},
                "start_date": {"type": "string"}, "end_date": {"type": "string"}, "limit": {"type": ["integer", "null"]},
            }),
            "record_evidence": _object_schema({
                "evidence_type": {"type": "string", "enum": ["OBSERVATION", "QUALITY", "ANOMALY", "STATISTIC", "HISTORICAL_TEST", "WARNING"]},
                "claim": {"type": "string"}, "compact_payload_json": {"type": "string"}, "query_hash": {"type": ["string", "null"]},
                "source_tables": {"type": "array", "items": {"type": "string"}}, "analysis_ready_date": {"type": ["string", "null"]},
            }),
            "complete_analysis": _object_schema({
                "evidence_sufficient": {"type": "boolean"},
                "necessary_followups_completed": {"type": "boolean"},
                "completion_reason": {"type": "string"},
                "remaining_uncertainties": {"type": "array", "items": {"type": "string"}},
                "optional_next_analysis": {"type": "array", "items": {"type": "string"}},
            }),
            "get_analysis_history": _object_schema({"search_text": {"type": "string"}, "limit": {"type": ["integer", "null"]}}),
        }
        return schemas[name]

    def execute(self, name: str, arguments: dict[str, Any], request_id: str) -> Execution:
        handler = self.handlers.get(name)
        if handler is None:
            raise ToolError(f"Tool {name} is not implemented or active")
        started = monotonic()
        result = handler(arguments, request_id)
        result.duration_ms = round((monotonic() - started) * 1000)
        return result

    def _catalog(self, table: str) -> dict[str, dict[str, Any]]:
        with self.db.query_transaction() as connection:
            table_row = connection.execute(
                '''SELECT table_name FROM public."Table_Catalog"
                   WHERE table_schema='public' AND table_name=%s AND category='Feature'
                     AND documentation_status='VERIFIED' ''',
                (table,),
            ).fetchone()
            if not table_row:
                raise ToolError(f"Unknown or unverified Feature table: {table}")
            rows = connection.execute(
                '''SELECT feature_column, semantic_role, allowed_aggregations,
                          is_filterable, is_groupable, definition, unit,
                          ranking_interpretation, point_in_time_safe,
                          historical_metadata_warning
                   FROM public."Feature_Catalog"
                   WHERE feature_table=%s AND is_active''',
                (table,),
            ).fetchall()
        return {row["feature_column"]: dict(row) for row in rows}

    def _validate_query(self, arguments: dict[str, Any]) -> dict[str, Any]:
        table = str(arguments.get("table") or "")
        catalog = self._catalog(table)
        columns = list(arguments.get("columns") or [])
        if not columns or len(columns) > self.settings.query_max_columns:
            raise ToolError(f"columns must contain 1..{self.settings.query_max_columns} items")
        unknown = sorted(set(columns) - set(catalog))
        if unknown:
            raise ToolError(f"Columns are not active in Feature_Catalog: {unknown}")
        tickers = arguments.get("tickers") or []
        if len(tickers) > self.settings.query_max_tickers:
            raise ToolError(f"Ticker count exceeds {self.settings.query_max_tickers}")
        if any(not isinstance(item, str) or not item.strip() for item in tickers):
            raise ToolError("tickers must be non-empty strings")
        start = self._date(arguments.get("start_date"), "start_date")
        end = self._date(arguments.get("end_date"), "end_date")
        if (start is None) != (end is None):
            raise ToolError("start_date and end_date must be provided together")
        if start and end:
            if start > end:
                raise ToolError("start_date must be on or before end_date")
            max_days = self.settings.query_max_date_range_days if tickers else self.settings.query_max_unfiltered_date_range_days
            if (end - start).days + 1 > max_days:
                raise ToolError(f"Date range exceeds {max_days} days for this request")
        elif not tickers:
            raise ToolError("A ticker filter or bounded date range is required")
        limit = arguments.get("limit") or self.settings.query_default_rows
        if not isinstance(limit, int) or not 1 <= limit <= self.settings.query_max_rows:
            raise ToolError(f"limit must be 1..{self.settings.query_max_rows}")
        filters = arguments.get("filters") or []
        for item in filters:
            column = item.get("column")
            operator = item.get("operator")
            if column not in catalog or not catalog[column]["is_filterable"]:
                raise ToolError(f"Column is not filterable: {column}")
            if operator not in set(OPERATORS) | {"in", "between"}:
                raise ToolError(f"Unsupported operator: {operator}")
            value = item.get("value")
            if operator in {"in", "between"} and (not isinstance(value, list) or not value):
                raise ToolError(f"{operator} requires a non-empty array value")
            if operator == "between" and len(value) != 2:
                raise ToolError("between requires exactly two values")
        order = arguments.get("order_by") or []
        for item in order:
            if item.get("column") not in catalog or item.get("direction") not in {"asc", "desc"}:
                raise ToolError("Invalid order_by")
        return {**arguments, "table": table, "columns": columns, "tickers": tickers, "start": start, "end": end, "limit": limit, "catalog": catalog}

    @staticmethod
    def _date(value: Any, name: str) -> date | None:
        if value in (None, ""):
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError as exc:
            raise ToolError(f"{name} must use YYYY-MM-DD") from exc

    def _select(self, arguments: dict[str, Any], *, execute: bool) -> Execution:
        valid = self._validate_query(arguments)
        conditions: list[Any] = []
        params: list[Any] = []
        if valid["tickers"]:
            conditions.append(sql.SQL("ticker = ANY(%s)"))
            params.append(valid["tickers"])
        if valid["start"]:
            conditions.extend([sql.SQL("date >= %s"), sql.SQL("date <= %s")])
            params.extend([valid["start"], valid["end"]])
        for item in arguments.get("filters") or []:
            identifier = sql.Identifier(item["column"])
            operator = item["operator"]
            value = item["value"]
            if operator == "in":
                conditions.append(sql.SQL("{} = ANY(%s)").format(identifier))
                params.append(value)
            elif operator == "between":
                conditions.append(sql.SQL("{} BETWEEN %s AND %s").format(identifier))
                params.extend(value)
            else:
                conditions.append(sql.SQL("{} {} %s").format(identifier, sql.SQL(OPERATORS[operator])))
                params.append(value)
        statement = sql.SQL("SELECT {} FROM public.{}{}").format(
            sql.SQL(", ").join(map(sql.Identifier, valid["columns"])),
            sql.Identifier(valid["table"]),
            sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions) if conditions else sql.SQL(""),
        )
        order = arguments.get("order_by") or []
        if order:
            statement += sql.SQL(" ORDER BY ") + sql.SQL(", ").join(
                sql.SQL("{} {}").format(sql.Identifier(item["column"]), sql.SQL(item["direction"].upper())) for item in order
            )
        statement += sql.SQL(" LIMIT %s")
        params.append(valid["limit"])
        with self.db.query_transaction() as connection:
            rendered = statement.as_string(connection)
            plan = connection.execute(sql.SQL("EXPLAIN (FORMAT JSON) ") + statement, params).fetchone()["QUERY PLAN"]
            estimated = self._estimated_rows(plan[0]["Plan"])
            if estimated > self.settings.query_max_estimated_rows:
                raise ToolError(f"Estimated rows {estimated} exceed {self.settings.query_max_estimated_rows}; aggregate or narrow the query")
            rows = connection.execute(statement, params).fetchall() if execute else []
        digest = query_hash(rendered, params)
        if not execute:
            return Execution({"valid": True, "estimated_rows": estimated, "decision": "EXECUTE", "query_hash": digest}, digest, estimated)
        payload = {
            "table": valid["table"], "columns": valid["columns"], "rows": [dict(row) for row in rows],
            "total_rows": len(rows), "query_hash": digest,
            "point_in_time_warnings": sorted({meta["historical_metadata_warning"] for name, meta in valid["catalog"].items() if name in valid["columns"] and meta["historical_metadata_warning"]}),
        }
        if len(dumps(payload).encode("utf-8")) > self.settings.query_max_output_bytes:
            payload, _, _ = compact_result(
                payload,
                max_rows=valid["limit"],
                max_bytes=self.settings.query_max_output_bytes,
                max_tokens=max(1, self.settings.query_max_output_bytes // 3),
            )
            payload["backend_output_compacted"] = True
        return Execution(payload, digest, estimated, len(rows))

    def list_tools(self, arguments: dict[str, Any], _: str) -> Execution:
        requested = set(arguments.get("requested_families") or [])
        allowed = {"QUERY", "SCREENING"}  # Release 1B; worker families remain unavailable.
        approved = sorted(requested & allowed)
        with self.db.query_transaction() as connection:
            rows = connection.execute(
                '''SELECT tool_name, tool_family, purpose, requires_analytics_worker, is_active
                   FROM public."Tool_Catalog" ORDER BY tool_family, tool_name'''
            ).fetchall()
        return Execution({"tools": [dict(row) for row in rows], "approved_expansion": approved, "unavailable_requested": sorted(requested - allowed)})

    def validate_query_request(self, arguments: dict[str, Any], _: str) -> Execution:
        self._validate_query(arguments)
        return Execution({"valid": True, "effective_limits": self._limit_summary()})

    def estimate_query_size(self, arguments: dict[str, Any], _: str) -> Execution:
        return self._select(arguments, execute=False)

    def query_features(self, arguments: dict[str, Any], _: str) -> Execution:
        return self._select(arguments, execute=True)

    def screen_features(self, arguments: dict[str, Any], request_id: str) -> Execution:
        return self.query_features(arguments, request_id)

    def get_timeseries(self, arguments: dict[str, Any], request_id: str) -> Execution:
        query = {
            "table": arguments["table"], "columns": ["date", "ticker", *arguments["columns"]],
            "tickers": [arguments["ticker"]], "start_date": arguments["start_date"], "end_date": arguments["end_date"],
            "filters": None, "order_by": [{"column": "date", "direction": "asc"}], "limit": arguments.get("limit"),
        }
        query["columns"] = list(dict.fromkeys(query["columns"]))
        return self.query_features(query, request_id)

    def find_features(self, arguments: dict[str, Any], _: str) -> Execution:
        words = list(dict.fromkeys(arguments["search_text"].strip().split()))[:8]
        if not words:
            raise ToolError("search_text must contain at least one keyword")
        patterns = [f"%{word}%" for word in words]
        limit = min(arguments.get("limit") or 30, 100)
        tables = arguments.get("tables") or []
        with self.db.query_transaction() as connection:
            rows = connection.execute(
                '''SELECT feature_table, feature_column, feature_category, definition, unit,
                          semantic_role, semantic_review_status
                   FROM public."Feature_Catalog" AS f
                   WHERE is_active AND EXISTS (
                         SELECT 1 FROM unnest(%s::text[]) AS p(pattern)
                         WHERE f.feature_column ILIKE p.pattern
                            OR f.definition ILIKE p.pattern
                            OR f.feature_category ILIKE p.pattern
                            OR f.analytical_interpretation ILIKE p.pattern
                       )
                     AND (cardinality(%s::text[]) = 0 OR f.feature_table = ANY(%s::text[]))
                   ORDER BY feature_table, feature_column LIMIT %s''',
                (patterns, tables, tables, limit),
            ).fetchall()
        return Execution({
            "rows": [dict(row) for row in rows], "total_rows": len(rows),
            "search_mode": "whitespace_keywords_or", "keywords": words,
        })

    def get_feature_definition(self, arguments: dict[str, Any], _: str) -> Execution:
        features = arguments["features"]
        if not 1 <= len(features) <= self.settings.query_max_columns:
            raise ToolError("Feature definition request is outside the metadata limit")
        pairs = [(item["table"], item["column"]) for item in features]
        with self.db.query_transaction() as connection:
            rows = connection.execute(
                '''SELECT feature_table, feature_column, grain, feature_category, definition,
                          calculation, source_tables, source_columns, lookback_window,
                          minimum_history, unit, null_rule, allowed_aggregations,
                          semantic_role, ranking_interpretation, is_filterable, is_groupable,
                          availability_rule, point_in_time_safe, historical_metadata_warning,
                          analytical_interpretation, recommended_use, misuse_warning,
                          semantic_review_status, validation_evidence, version
                   FROM public."Feature_Catalog" f
                   WHERE is_active AND (feature_table, feature_column) IN
                     (SELECT * FROM unnest(%s::text[], %s::text[]))
                   ORDER BY feature_table, feature_column''',
                ([p[0] for p in pairs], [p[1] for p in pairs]),
            ).fetchall()
        return Execution({"rows": [dict(row) for row in rows], "total_rows": len(rows)})

    def list_feature_tables(self, arguments: dict[str, Any], _: str) -> Execution:
        with self.db.query_transaction() as connection:
            rows = connection.execute(
                '''SELECT t.table_name, t.definition, t.grain, t.primary_key_columns,
                          t.readiness_mode, t.readiness_date_column,
                          count(f.feature_column)::integer AS active_columns
                   FROM public."Table_Catalog" t JOIN public."Feature_Catalog" f
                     ON f.feature_table=t.table_name AND f.is_active
                   WHERE t.category='Feature' AND t.documentation_status='VERIFIED'
                   GROUP BY t.table_name, t.definition, t.grain, t.primary_key_columns,
                            t.readiness_mode, t.readiness_date_column ORDER BY t.table_name'''
            ).fetchall()
        return Execution({"rows": [dict(row) for row in rows], "include_columns": arguments["include_columns"]})

    def check_data_freshness(self, arguments: dict[str, Any], _: str) -> Execution:
        tables = arguments["tables"]
        if not tables or len(tables) > 10:
            raise ToolError("tables must contain 1..10 Feature tables")
        for table in tables:
            self._catalog(table)
        with self.db.query_transaction() as connection:
            rows = connection.execute("SELECT * FROM public.check_analysis_data_readiness(%s)", (tables,)).fetchall()
        safe_dates = [row["safe_analysis_date"] for row in rows if row["safe_analysis_date"]]
        return Execution({"rows": [dict(row) for row in rows], "analysis_ready_date": min(safe_dates).isoformat() if safe_dates else None})

    def check_data_quality(self, arguments: dict[str, Any], _: str) -> Execution:
        table = arguments["table"]
        catalog = self._catalog(table)
        tickers = arguments.get("tickers") or []
        if len(tickers) > self.settings.query_max_tickers:
            raise ToolError("Too many tickers")
        start = self._date(arguments.get("start_date"), "start_date")
        end = self._date(arguments.get("end_date"), "end_date")
        if not start or not end:
            raise ToolError("check_data_quality requires an explicit bounded date range")
        if start > end or (end - start).days + 1 > self.settings.query_max_date_range_days:
            raise ToolError("check_data_quality date range is invalid or exceeds the configured limit")
        conditions, params = [], []
        if tickers:
            conditions.append(sql.SQL("ticker = ANY(%s)")); params.append(tickers)
        conditions.extend([sql.SQL("date >= %s"), sql.SQL("date <= %s")]); params.extend([start, end])
        where = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("")
        measures = [name for name, meta in catalog.items() if meta["semantic_role"] == "MEASURE"][: self.settings.query_max_columns]
        null_parts = [sql.SQL("count(*) FILTER (WHERE {} IS NULL)").format(sql.Identifier(name)) for name in measures]
        statement = sql.SQL("SELECT count(*) AS row_count, ARRAY[{}] AS null_counts FROM public.{}{}").format(
            sql.SQL(",").join(null_parts), sql.Identifier(table), where
        )
        anomaly_rows: list[dict[str, Any]] = []
        with self.db.query_transaction() as connection:
            plan = connection.execute(sql.SQL("EXPLAIN (FORMAT JSON) ") + statement, params).fetchone()["QUERY PLAN"]
            estimated = self._estimated_rows(plan[0]["Plan"])
            if estimated > self.settings.query_max_estimated_rows:
                raise ToolError(f"Estimated quality scan {estimated} exceeds {self.settings.query_max_estimated_rows}; narrow the scope")
            summary = connection.execute(statement, params).fetchone()
            if table == "Feature_01_Stock_Daily" and "return_1d_pct" in catalog:
                anomaly_statement = sql.SQL('''SELECT date,ticker,return_1d_pct,volume_zscore_20d
                    FROM public.{}{}{} ORDER BY abs(return_1d_pct) DESC NULLS LAST LIMIT 20''').format(
                    sql.Identifier(table), where,
                    sql.SQL(" AND return_1d_pct IS NOT NULL") if conditions else sql.SQL(" WHERE return_1d_pct IS NOT NULL"),
                )
                anomaly_rows = [dict(row) for row in connection.execute(anomaly_statement, params).fetchall()]
        invalid = False  # Physical constraints are the authoritative impossible-data gate.
        warnings = []
        if summary["row_count"] == 0:
            warnings.append("No observations matched the requested scope")
        payload = {
            "classification": "FAIL" if invalid else ("WARNING" if warnings else "PASS"),
            "row_count": summary["row_count"],
            "null_counts": dict(zip(measures, summary["null_counts"])),
            "warnings": warnings,
            "anomaly_flags": anomaly_rows,
            "policy": "Source-valid extremes remain PASS with anomaly flags; impossible values FAIL; incomplete/suspicious scope warns.",
        }
        return Execution(payload, estimated_rows=estimated, processed_rows=summary["row_count"])

    def rank_features(self, arguments: dict[str, Any], request_id: str) -> Execution:
        return self.query_features({
            "table": arguments["table"], "columns": ["date", "ticker", arguments["column"]],
            "tickers": arguments.get("tickers"), "start_date": arguments["date"], "end_date": arguments["date"],
            "filters": None, "order_by": [{"column": arguments["column"], "direction": arguments["direction"]}],
            "limit": arguments.get("limit") or 20,
        }, request_id)

    def _aggregate(self, table: str, group_by: list[str], metrics: list[dict[str, str]], start_date: str, end_date: str, tickers: list[str] | None, limit: int | None) -> Execution:
        catalog = self._catalog(table)
        if not group_by or len(group_by) > self.settings.query_max_columns:
            raise ToolError("group_by is required and too large")
        if any(name not in catalog or not catalog[name]["is_groupable"] for name in group_by):
            raise ToolError("Every group_by column must be catalog-approved as groupable")
        if not metrics or len(metrics) + len(group_by) > self.settings.query_max_columns:
            raise ToolError("metrics is required and total output columns exceed the limit")
        selects = [sql.Identifier(name) for name in group_by]
        aliases = list(group_by)
        for item in metrics:
            column, aggregation = item["column"], item["aggregation"]
            meta = catalog.get(column)
            if not meta or aggregation not in meta["allowed_aggregations"] or aggregation not in AGGREGATIONS:
                raise ToolError(f"{aggregation} is not allowed for {column}")
            ident = sql.Identifier(column)
            if aggregation == "COUNT_DISTINCT": expression = sql.SQL("count(DISTINCT {})").format(ident)
            elif aggregation == "MEDIAN": expression = sql.SQL("percentile_cont(0.5) WITHIN GROUP (ORDER BY {})").format(ident)
            else: expression = sql.SQL("{}({})").format(sql.SQL(AGGREGATIONS[aggregation]), ident)
            alias = f"{aggregation.lower()}_{column}"
            selects.append(sql.SQL("{} AS {}").format(expression, sql.Identifier(alias))); aliases.append(alias)
        start, end = self._date(start_date, "start_date"), self._date(end_date, "end_date")
        if not start or not end or start > end or (end - start).days + 1 > self.settings.query_max_date_range_days:
            raise ToolError("Invalid or excessive aggregate date range")
        ticker_values = tickers or []
        if len(ticker_values) > self.settings.query_max_tickers:
            raise ToolError("Too many tickers")
        conditions: list[Any] = [sql.SQL("date BETWEEN %s AND %s")]
        params: list[Any] = [start, end]
        if ticker_values:
            conditions.append(sql.SQL("ticker = ANY(%s)")); params.append(ticker_values)
        row_limit = min(limit or self.settings.query_max_groups, self.settings.query_max_groups)
        statement = sql.SQL("SELECT {} FROM public.{} WHERE {} GROUP BY {} ORDER BY {} LIMIT %s").format(
            sql.SQL(",").join(selects), sql.Identifier(table), sql.SQL(" AND ").join(conditions),
            sql.SQL(",").join(map(sql.Identifier, group_by)), sql.SQL(",").join(map(sql.Identifier, group_by)),
        )
        params.append(row_limit)
        with self.db.query_transaction() as connection:
            rendered = statement.as_string(connection)
            plan = connection.execute(sql.SQL("EXPLAIN (FORMAT JSON) ") + statement, params).fetchone()["QUERY PLAN"]
            estimated = self._estimated_rows(plan[0]["Plan"])
            if estimated > self.settings.query_max_estimated_rows:
                raise ToolError("Estimated aggregate output exceeds safety limit")
            rows = connection.execute(statement, params).fetchall()
        digest = query_hash(rendered, params)
        payload = {"table": table, "columns": aliases, "rows": [dict(row) for row in rows], "total_rows": len(rows), "query_hash": digest}
        if len(dumps(payload).encode("utf-8")) > self.settings.query_max_output_bytes:
            payload, _, _ = compact_result(payload, max_rows=row_limit, max_bytes=self.settings.query_max_output_bytes, max_tokens=max(1, self.settings.query_max_output_bytes // 3))
            payload["backend_output_compacted"] = True
        return Execution(payload, digest, estimated, len(rows))

    def aggregate_features(self, arguments: dict[str, Any], _: str) -> Execution:
        return self._aggregate(arguments["table"], arguments["group_by"], arguments["metrics"], arguments["start_date"], arguments["end_date"], arguments.get("tickers"), arguments.get("limit"))

    def compare_groups(self, arguments: dict[str, Any], _: str) -> Execution:
        return self._aggregate(arguments["table"], [arguments["group_column"]], [{"column": arguments["metric_column"], "aggregation": arguments["aggregation"]}], arguments["start_date"], arguments["end_date"], None, arguments.get("limit"))

    def compare_periods(self, arguments: dict[str, Any], _: str) -> Execution:
        periods = arguments["periods"]
        if not 1 <= len(periods) <= self.settings.query_max_periods:
            raise ToolError(f"periods must contain 1..{self.settings.query_max_periods} items")
        rows = []
        hashes = []
        for period in periods:
            result = self._aggregate(arguments["table"], ["ticker"], [{"column": arguments["column"], "aggregation": arguments["aggregation"]}], period["start_date"], period["end_date"], [arguments["ticker"]], 1)
            rows.append({"label": period["label"], **(result.payload["rows"][0] if result.payload["rows"] else {})})
            hashes.append(result.query_hash)
        return Execution({"rows": rows, "total_rows": len(rows), "query_hash": hashes})

    def record_evidence(self, arguments: dict[str, Any], request_id: str) -> Execution:
        required = {"evidence_type", "claim", "compact_payload_json", "source_tables"}
        missing = sorted(required - arguments.keys())
        if missing:
            raise ToolError(f"record_evidence missing required fields: {missing}")
        if arguments["evidence_type"] not in {
            "OBSERVATION", "QUALITY", "ANOMALY", "STATISTIC", "HISTORICAL_TEST", "WARNING",
        }:
            raise ToolError("record_evidence evidence_type is invalid")
        if not isinstance(arguments["claim"], str) or not arguments["claim"].strip():
            raise ToolError("record_evidence claim must be non-empty text")
        if not isinstance(arguments["source_tables"], list) or not arguments["source_tables"]:
            raise ToolError("record_evidence source_tables must be a non-empty list")
        try:
            compact_payload = json.loads(arguments["compact_payload_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise ToolError("compact_payload_json must be valid JSON") from exc
        if not isinstance(compact_payload, dict):
            raise ToolError("compact_payload_json must encode an object")
        with self.db.connection() as connection, connection.transaction():
            count = connection.execute('SELECT count(*) FROM public."Analysis_Evidence" WHERE request_id=%s', (request_id,)).fetchone()["count"]
            if count >= 25:
                raise ToolError("Evidence limit of 25 reached")
            row = connection.execute(
                '''INSERT INTO public."Analysis_Evidence" (request_id,evidence_type,claim,compact_payload,query_hash,source_tables,analysis_ready_date)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING evidence_id''',
                (request_id, arguments["evidence_type"], arguments["claim"][:2000], json.dumps(compact_payload), arguments.get("query_hash"), arguments["source_tables"], arguments.get("analysis_ready_date")),
            ).fetchone()
        return Execution({
            "evidence_id": str(row["evidence_id"]),
            "recorded": True,
            "note": "Evidence was stored; this does not finalize the analysis.",
        })

    def complete_analysis(self, arguments: dict[str, Any], _: str) -> Execution:
        required = {
            "evidence_sufficient", "necessary_followups_completed", "completion_reason",
            "remaining_uncertainties", "optional_next_analysis",
        }
        missing = sorted(required - arguments.keys())
        if missing:
            raise ToolError(f"complete_analysis missing required fields: {missing}")
        if arguments["evidence_sufficient"] is not True:
            raise ToolError("complete_analysis requires evidence_sufficient=true")
        if arguments["necessary_followups_completed"] is not True:
            raise ToolError("Complete necessary follow-up analysis before finalization")
        if not isinstance(arguments["completion_reason"], str) or not arguments["completion_reason"].strip():
            raise ToolError("complete_analysis completion_reason must be non-empty text")
        for field in ("remaining_uncertainties", "optional_next_analysis"):
            if not isinstance(arguments[field], list) or any(not isinstance(item, str) for item in arguments[field]):
                raise ToolError(f"complete_analysis {field} must be an array of text")
        return Execution({
            "completion_accepted": True,
            "next_action": "Return the strict final response using only evidence IDs recorded in this request.",
        })

    def get_analysis_history(self, arguments: dict[str, Any], _: str) -> Execution:
        limit = min(arguments.get("limit") or 5, 20)
        term = f"%{arguments['search_text'].strip()}%"
        with self.db.query_transaction() as connection:
            rows = connection.execute(
                '''SELECT request_id,question,answer,recommended_next_analysis,completed_at
                   FROM public."Analysis_Request" WHERE status='SUCCESS' AND question ILIKE %s
                   ORDER BY completed_at DESC LIMIT %s''', (term, limit)
            ).fetchall()
        return Execution({"rows": [dict(row) for row in rows], "total_rows": len(rows)})

    def _limit_summary(self) -> dict[str, int]:
        return {
            "max_rows": self.settings.query_max_rows,
            "max_tickers": self.settings.query_max_tickers,
            "max_columns": self.settings.query_max_columns,
            "max_date_range_days": self.settings.query_max_date_range_days,
            "max_estimated_rows": self.settings.query_max_estimated_rows,
            "timeout_seconds": self.settings.query_timeout_seconds,
        }

    @staticmethod
    def _estimated_rows(plan: dict[str, Any]) -> int:
        """Use the largest planner node, not only LIMIT's capped output node."""
        return max(
            [int(plan.get("Plan Rows", 0))]
            + [ToolRegistry._estimated_rows(child) for child in plan.get("Plans", [])]
        )
