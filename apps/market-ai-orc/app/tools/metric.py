"""query_metric (round 2026-10-03 D5; ROUND_PLAN_2026-10-03_FASE_D.md): a short question about an official metric in
one SQL Governor summary per period, instead of a data need, a bundle and a Python session.

The metrics come from AI_metric_catalog (read at startup; the model sees them in the METRICS note of each run, not in
the tool description, so the tool's definition does not change when a metric is added). The orchestrator only maps
the call to a summary spec; the Governor derives from its own catalog whether the metric may run over time and across
the dimensions dropped, and refuses otherwise. The values come back as a database aggregate: citable with
{{metric.mN...}} and checked by number provenance like a database fact.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .analysis import current_data_date, current_run_context
from .data_planner import sha256_json
from .registry import ToolError, ToolSpec
from .request_data import GovernorClient

METRIC_SQL = '''
SELECT m.metric_id, m.metric_version, m.label, m.description, m.source_table, m.measure_column, m.time_function,
       m.entity_column, m.default_dimensions, m.allowed_dimensions, m.default_scope, m.formula, m.interpretation,
       m.misuse_warning, m.review_status, c.unit
FROM public."AI_metric_catalog" AS m
LEFT JOIN public."AI_column_catalog" AS c ON c.table_name = m.source_table AND c.column_name = m.measure_column
WHERE m.is_active
ORDER BY m.metric_id
'''
MAX_PERIODS = 4
MAX_ENTITIES = 20
METRICS_HEADER = ("METRICS (application context from the backend, not from the user): official metrics query_metric "
                  "answers in one database summary per period. Use it for these metrics over a period; anything "
                  "else goes through submit_data_need_spec.")
DESCRIPTION = (
    "An official metric (listed in the METRICS note) for entities over periods, computed by the database in one "
    "summary per period: periods are trading days of the table's own calendar up to as_of (the conversation's data "
    "date by default) or a date range. Returns rows per dimension with days_present, first_date and last_date, and "
    "a metric ref to cite. Not for statistics, rankings across many entities or formulas: use submit_data_need_spec."
)


def read_metrics(reader: Any) -> list[dict[str, Any]]:
    """The active metrics with their measure column's unit (one short read-only transaction of the catalog login)."""
    with reader.read_only() as run:
        return [dict(row) for row in run(METRIC_SQL, ())]


def menu(metrics: list[dict[str, Any]]) -> str:
    lines = [METRICS_HEADER]
    for m in metrics:
        lines.append(f"- {m['metric_id']}: {m['label']}. {m['description']} Dimensions: "
                     f"{', '.join(m['allowed_dimensions'])} (default {', '.join(m['default_dimensions']) or 'none'}); "
                     f"entities are {m['entity_column']} values; unit {m.get('unit') or 'as the column'}; "
                     f"status {m['review_status']}. Caution: {m['misuse_warning']}")
    return "\n".join(lines)


class Filter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1, max_length=63)
    values: list[str] = Field(min_length=1, max_length=20)


class Period(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trading_days: int | None = Field(ge=1, le=260, description="The last N trading days up to as_of.")
    start_date: str | None = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="A date range start.")
    end_date: str | None = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="A date range end.")

    @model_validator(mode="after")
    def _one_form(self) -> "Period":
        ranged = self.start_date is not None and self.end_date is not None
        if (self.trading_days is not None) == ranged or (
                not ranged and (self.start_date is not None or self.end_date is not None)):
            raise ValueError("give trading_days, or start_date and end_date")
        return self


class QueryMetricArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$", description="A metric id from the METRICS note.")
    entities: list[str] | None = Field(max_length=MAX_ENTITIES, description="Entity values (e.g. tickers).")
    filters: list[Filter] | None = Field(max_length=5, description="Equality filters on dimensions of the metric.")
    dimensions: list[str] | None = Field(max_length=4, description="Split by these dimensions; null: the default.")
    periods: list[Period] = Field(min_length=1, max_length=MAX_PERIODS)
    as_of: str | None = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description=(
        "Last date of trading-day periods; null: the conversation's data date, else today."))


def predicate(column: str, values: list[str]) -> dict[str, Any]:
    if len(values) == 1:
        return {"type": "PREDICATE", "column": column, "operator": "EQ", "values": list(values)}
    return {"type": "PREDICATE", "column": column, "operator": "IN", "values": sorted(set(values))}


def scope_of(default: dict[str, Any], parts: list[dict[str, Any]]) -> dict[str, Any]:
    children = ([] if default.get("type") == "ALL" else [default]) + parts
    if not children:
        return {"type": "ALL"}
    return children[0] if len(children) == 1 else {"type": "AND", "children": children}


def as_of_date(given: str | None) -> str:
    if given:
        return given
    data_date = current_data_date.get()
    if data_date is not None and data_date.as_of and not data_date.newest:
        return data_date.as_of
    context = current_run_context.get()
    moment = context.reference_time if context is not None else datetime.now(ZoneInfo("UTC"))
    zone = ZoneInfo(context.timezone) if context is not None else ZoneInfo("Asia/Jakarta")
    return moment.astimezone(zone).date().isoformat()


def metric_specs(governor: GovernorClient, metrics: list[dict[str, Any]], *, timeout_seconds: float,
                 max_result_bytes: int) -> list[ToolSpec]:
    by_id = {m["metric_id"]: m for m in metrics}

    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, QueryMetricArgs)
        metric = by_id.get(arguments.metric)
        if metric is None:
            return {"status": "REJECTED", "code": "METRIC_NOT_IN_CATALOG", "next_action": "CALL:submit_data_need_spec",
                    "message": f"{arguments.metric} is not an official metric; answer through a data need.",
                    "metrics": sorted(by_id)}
        allowed = list(metric["allowed_dimensions"])
        dimensions = arguments.dimensions if arguments.dimensions is not None else list(metric["default_dimensions"])
        unknown = [d for d in dimensions + [f.column for f in arguments.filters or []] if d not in allowed]
        if unknown:
            return {"status": "REJECTED", "code": "METRIC_DIMENSION_NOT_ALLOWED", "next_action": "FIX_ARGUMENTS",
                    "message": f"{', '.join(unknown)} is not a dimension of {arguments.metric}.",
                    "allowed_dimensions": allowed}
        parts = [predicate(metric["entity_column"], arguments.entities)] if arguments.entities else []
        parts += [predicate(f.column, f.values) for f in arguments.filters or []]
        scope = scope_of(metric["default_scope"] or {"type": "ALL"}, parts)
        as_of = as_of_date(arguments.as_of)
        periods = []
        for period in arguments.periods:
            window = {"trading_days": period.trading_days, "as_of": as_of} if period.trading_days is not None \
                else {"from": period.start_date, "to": period.end_date}
            spec = {"summary_version": "summary_spec/v1", "source_table": metric["source_table"], "scope": scope,
                    "restrictions": [], "group_by": dimensions,
                    "measures": [{"column": metric["measure_column"], "function": metric["time_function"],
                                  "as": metric["metric_id"]}], "period": window}
            answer = governor.summary(spec, {"purpose": "METRIC", "recipe_sha256": sha256_json(spec),
                                             "metric_id": metric["metric_id"]}, timeout=timeout_seconds)
            if answer.get("status") != "OK":
                code = answer.get("code") or answer.get("status")
                return {"status": "REJECTED", "code": code, "message": str(answer.get("message") or "")[:600],
                        "next_action": "FIX_ARGUMENTS" if answer.get("status") == "REJECTED_POLICY"
                        else "NARROW_ENTITIES_OR_PERIOD", "governor_status": answer.get("status"),
                        "query_id": answer.get("query_id")}
            periods.append({"period": answer.get("period"), "rows": answer.get("rows") or [],
                            "row_count": answer.get("row_count"), "query_id": answer.get("query_id"),
                            "query_hash": answer.get("query_hash")})
        return {"status": "OK", "metric": {k: metric.get(k) for k in ("metric_id", "metric_version", "label",
                                                                      "time_function", "unit", "review_status",
                                                                      "misuse_warning")},
                "source_table": metric["source_table"], "as_of": as_of, "dimensions": dimensions,
                "entities": arguments.entities, "periods": periods,
                "note": "days_present below the period's calendar_dates means the entity has no row on some "
                        "trading days; say so when you cite the value."}

    if not metrics:
        raise ToolError("No active metric in AI_metric_catalog.")
    return [ToolSpec(name="query_metric", description=DESCRIPTION, arguments_model=QueryMetricArgs, handler=handler,
                     timeout_seconds=timeout_seconds * MAX_PERIODS + 10, max_result_bytes=max_result_bytes)]
