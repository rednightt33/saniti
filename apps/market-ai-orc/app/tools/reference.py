"""lookup_reference and the database check before the web (P34, plan 2026-10-05 Fase D option A).

Root cause (P34): a short fact question is routed FACT, and the FACT step offered no reader of the database's
reference tables (classifications, profiles), so the model looked up on the web what the database holds (BBCA's
sector). Two parts, both derived from the catalog at run time (no table, column or attribute is named here):

- lookup_reference (effect READS, so every step that reads is offered it): the columns of the static reference tables
  (no time column) with their catalog descriptions, or rows of one of them through the SQL Governor
  (/v1/catalog/reference-rows: catalog, compile and EXPLAIN gates; at most 100 rows).
- the check before a web lookup (orchestrator): one small model call compares the asked attribute with those
  columns; when one holds it, the web call is refused once with next_action CALL:lookup_reference naming the table
  and column. Any failure lets the web call run (logged).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from .registry import ToolError, ToolSpec
from .request_data import GovernorClient

COLUMNS_TTL_SECONDS = 600.0  # the catalog changes by migration; a deployment re-reads it within ten minutes
NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$"

DESCRIPTION = (
    "Read the database's reference tables (static classifications and profiles: a stock's sector, industry, board, "
    "company name or description; a broker's name or type). Without table: the tables and their columns with "
    "descriptions. With table: up to 100 rows, filtered by where (exact stored values; one value or several) and "
    "optionally by match (a case-insensitive part of one column's text, e.g. a group or company name). Use it "
    "before a web lookup for any attribute these tables hold; the web is only for what they do not hold. Rows are "
    "current values, not as of past dates; dated data (prices, volumes, flows) needs a data need.")

MATCH_INSTRUCTIONS = (
    "You decide whether a database column already holds an attribute that is about to be looked up on the web. You "
    "get the subject, the attribute and the reference tables with their columns and descriptions. held is true only "
    "when one column directly states that attribute for that kind of subject (for example a sector column for "
    "'which sector', a company-description column for 'what business'). An attribute the columns do not state "
    "(ownership, shareholders, state ownership, group membership, news, events, figures) is not held, even when a "
    "column is related. When held, give that table and column exactly as listed; otherwise give empty strings.")
MATCH_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["held", "table", "column"],
    "properties": {"held": {"type": "boolean"}, "table": {"type": "string"}, "column": {"type": "string"}}}


class ReferenceMatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    held: bool
    table: str = ""
    column: str = ""


class Where(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(pattern=NAME_PATTERN, description="A column of the table, exactly as listed.")
    values: list[str] = Field(min_length=1, max_length=50,
                              description="Exact stored values; one value, or several for any of them.")


class Match(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(pattern=NAME_PATTERN, description="The text column to search.")
    text: str = Field(min_length=2, max_length=60, description="A case-insensitive part of its text.")


class LookupReferenceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str | None = Field(pattern=NAME_PATTERN, description="A reference table, or null to list them.")
    columns: list[str] = Field(max_length=8, description="Columns to return (the entity column is always added); "
                                                         "empty when listing.")
    where: list[Where] = Field(max_length=4, description="Exact-value conditions, all of them must hold.")
    match: Match | None = Field(description="A text search on one column, or null.")


class ReferenceCatalog:
    """The reference columns from the Governor, cached for COLUMNS_TTL_SECONDS (metadata only)."""

    def __init__(self, client: GovernorClient, clock: Callable[[], float] = time.monotonic) -> None:
        self.client = client
        self.clock = clock
        self._lock = threading.Lock()
        self._tables: list[dict[str, Any]] | None = None
        self._read_at = 0.0

    def tables(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._tables is not None and self.clock() - self._read_at < COLUMNS_TTL_SECONDS:
                return self._tables
        result = self.client.reference_columns()
        if result.get("status") != "OK" or not isinstance(result.get("tables"), list):
            raise ToolError("The SQL Governor did not list the reference columns.")
        with self._lock:
            self._tables, self._read_at = result["tables"], self.clock()
            return self._tables

    def column(self, table: str, column: str) -> dict[str, Any] | None:
        """The listed table with only that column, or None when the pair is not a reference column."""
        for entry in self.tables():
            if entry.get("table") == table:
                for item in entry.get("columns") or []:
                    if item.get("column") == column:
                        return {**entry, "columns": [item]}
        return None


def matcher_content(subject: str, attribute: str, tables: list[dict[str, Any]]) -> dict[str, Any]:
    """What the matcher reads: the question and the reference columns (names and descriptions only)."""
    return {"subject": subject, "attribute": attribute,
            "reference_tables": [{"table": t.get("table"), "description": t.get("description"),
                                  "columns": [{"column": c.get("column"), "description": c.get("description")}
                                              for c in t.get("columns") or []]} for t in tables]}


def lookup_reference_spec(client: GovernorClient, catalog: ReferenceCatalog, *, timeout_seconds: float) -> ToolSpec:
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, LookupReferenceArgs)
        if arguments.table is None:
            return {"status": "OK", "tables": catalog.tables(),
                    "note": "Call again with table, columns and where (or match) to read rows."}
        where = [{"column": w.column, "operator": "EQ" if len(w.values) == 1 else "IN",
                  "value": w.values[0] if len(w.values) == 1 else w.values} for w in arguments.where]
        columns = arguments.columns or [c["column"] for c in next(
            (t.get("columns") or [] for t in catalog.tables() if t.get("table") == arguments.table), [])][:8]
        if not columns:
            return {"status": "REJECTED", "reason_code": "TABLE_NOT_REFERENCE",
                    "message": f"{arguments.table} is not a reference table; call with table null to list them."}
        return client.reference_rows(arguments.table, columns, where,
                                     arguments.match.model_dump() if arguments.match else None)

    return ToolSpec(name="lookup_reference", effect="READS", description=DESCRIPTION,
                    arguments_model=LookupReferenceArgs, handler=handler, timeout_seconds=timeout_seconds,
                    max_result_bytes=32000)
