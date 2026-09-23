from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..compaction import dumps
from .catalog import CatalogReader
from .registry import ToolError, ToolSpec
from .rows import as_row, load_exact

PREVIEW_ROW_LIMIT = 20
PREVIEW_MAX_BYTES = 48000
PREVIEW_SQL = "SELECT public.ai_preview_table_rows(%s)::text AS payload"

PreviewTable = Literal[
    "Feature_01_Stock_Daily", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily",
    "IDX_Broker_Profile", "IDX_Broker_Summary", "IDX_Stock_Universe", "Price_Stock_Indonesia_IDX",
]

# Must equal the ORDER BY clauses in database/migrations/20260923_002_create_market_ai_preview_interface.sql
# (the database function is the enforcement point; tests compare both).
RECENT = "Rows with the most recent {date} first; ties broken by the remaining key columns, all descending."
ORDERING: dict[str, tuple[str, str]] = {
    "Feature_01_Stock_Daily": ("date DESC, ticker DESC", RECENT.format(date="date")),
    "Feature_02_Broker_Rolling": (
        "date DESC, market_board DESC, ticker DESC, broker DESC, investor_type DESC",
        RECENT.format(date="date"),
    ),
    "Feature_03_Stock_Broker_Daily": ("date DESC, market_board DESC, ticker DESC", RECENT.format(date="date")),
    "IDX_Broker_Profile": ("broker_code ASC", "Primary key order (broker_code ascending); reference table without a date column."),
    "IDX_Broker_Summary": (
        '"Date" DESC, "Symbol" DESC, "Broker" DESC, "Investor Type" DESC, "Market Board" DESC',
        RECENT.format(date='"Date"'),
    ),
    "IDX_Stock_Universe": ('"Ticker" ASC', "Primary key order (Ticker ascending); reference table without a date column."),
    "Price_Stock_Indonesia_IDX": ("date DESC, ticker DESC", RECENT.format(date="date")),
}
NOTICE = (
    "Example rows only: at most 20 per table in a fixed deterministic order. They are not a "
    "random or representative sample, not the complete dataset, and not an analytical result."
)


class PreviewArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_name: PreviewTable = Field(description="One of the seven approved market-data tables.")


class PreviewTool:
    def __init__(self, reader: CatalogReader) -> None:
        self.reader = reader

    def preview(self, arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, PreviewArguments)
        table = arguments.table_name
        with self.reader.read_only() as run:
            rows = run(PREVIEW_SQL, (table,))
        payload = load_exact(rows[0]["payload"]) if rows and rows[0].get("payload") else None
        if not isinstance(payload, dict) or payload.get("table_name") != table:
            raise ToolError("The preview interface returned an unexpected response.")
        order_by, description = ORDERING[table]
        records = payload.get("rows") or []
        columns = payload.get("columns") or []
        if payload.get("row_limit") != PREVIEW_ROW_LIMIT or len(records) > PREVIEW_ROW_LIMIT:
            raise ToolError("The preview interface violated the 20-row contract; nothing was returned.")
        if payload.get("order_by") != order_by:
            raise ToolError("The preview interface ordering does not match this service version.")
        names = [column["name"] for column in columns]
        result = {
            "table_name": table,
            "columns": [
                {"name": column["name"], "type": column["type"], "nullable": column["nullable"]}
                for column in columns
            ],
            "rows": [as_row(record, names) for record in records],
            "returned_rows": len(records),
            "row_limit": PREVIEW_ROW_LIMIT,
            "ordering": {"order_by": order_by, "description": description},
            "is_sample": True,
            "notice": NOTICE,
        }
        size = len(dumps(result).encode("utf-8"))
        if size > PREVIEW_MAX_BYTES:
            raise ToolError(
                f"The {len(records)}-row preview of {table} is {size} bytes, above the "
                f"{PREVIEW_MAX_BYTES}-byte output limit. No partial preview was returned."
            )
        return result


def preview_spec(reader: CatalogReader, *, timeout_seconds: float) -> ToolSpec:
    return ToolSpec(
        name="preview_table_rows",
        description=(
            "Return up to 20 example rows (all columns) from one of seven approved market-data "
            "tables, in a fixed deterministic order stated in the result. No filters, offsets, "
            "custom limits, or pagination. Example records only, not a complete or representative "
            "dataset and not an analysis."
        ),
        arguments_model=PreviewArguments,
        handler=PreviewTool(reader).preview,
        timeout_seconds=timeout_seconds,
        max_result_bytes=PREVIEW_MAX_BYTES + 4096,
    )
