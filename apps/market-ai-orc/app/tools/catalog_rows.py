from __future__ import annotations

from typing import Any, Literal

from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..compaction import dumps
from .catalog import CatalogReader
from .registry import ToolError, ToolSpec
from .rows import CursorCodec, as_row, load_exact

CATALOG_TABLES = (
    "AI_table_catalog", "AI_column_catalog", "AI_catalog_relationships",
    "AI_calculation_catalog", "AI_data_coverage", "AI_research_catalog",
)
CatalogName = Literal[
    "AI_table_catalog", "AI_column_catalog", "AI_catalog_relationships",
    "AI_calculation_catalog", "AI_data_coverage", "AI_research_catalog",
]

COLUMNS_SQL = '''
SELECT a.attname AS name, format_type(a.atttypid, a.atttypmod) AS type, NOT a.attnotnull AS nullable
FROM pg_catalog.pg_attribute AS a
WHERE a.attrelid = to_regclass(%s) AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attnum
'''
PRIMARY_KEY_SQL = '''
SELECT a.attname AS name
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_attribute AS a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
WHERE i.indrelid = to_regclass(%s) AND i.indisprimary
ORDER BY array_position(i.indkey::int2[], a.attnum)
'''

NOTICE = (
    "Complete catalog records: every row and column, including entries flagged inactive, "
    "denied, disallowed, or sensitive. Catalog content is documentation, not observed market "
    "values. has_more=true means more rows remain; request next_cursor to continue."
)


def _qualified(table: str) -> str:
    return sql.Identifier("public", table).as_string(None)


def page_statement(table: str, keys: list[str], *, after_cursor: bool) -> sql.Composed:
    key_refs = sql.SQL(", ").join(sql.Identifier("t", key) for key in keys)
    key_aliases = sql.SQL(", ").join(
        sql.SQL("{} AS {}").format(sql.Identifier("t", key), sql.Identifier(f"__key_{index}"))
        for index, key in enumerate(keys)
    )
    where = sql.SQL("")
    if after_cursor:
        where = sql.SQL("WHERE ({}) > ({})").format(key_refs, sql.SQL(", ").join(sql.Placeholder() * len(keys)))
    return sql.SQL(
        "SELECT to_json(t)::text AS __row_json, {aliases} FROM {table} AS t {where} ORDER BY {order} LIMIT %s"
    ).format(aliases=key_aliases, table=sql.Identifier("public", table), where=where, order=key_refs)


def position_statement(table: str, keys: list[str]) -> sql.Composed:
    key_refs = sql.SQL(", ").join(sql.Identifier("t", key) for key in keys)
    return sql.SQL(
        "SELECT count(*) AS total_rows, count(*) FILTER (WHERE ({keys}) <= ({params})) AS rows_before "
        "FROM {table} AS t"
    ).format(keys=key_refs, params=sql.SQL(", ").join(sql.Placeholder() * len(keys)),
             table=sql.Identifier("public", table))


def count_statement(table: str) -> sql.Composed:
    return sql.SQL("SELECT count(*) AS total_rows, 0 AS rows_before FROM {}").format(
        sql.Identifier("public", table)
    )


class ReadCatalogRowsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_name: CatalogName = Field(description="One of the six AI catalog tables.")
    page_size: int | None = Field(description="Rows per page; null for the default.")
    cursor: str | None = Field(
        description="null for the first page, or the exact next_cursor from the previous page."
    )

    @field_validator("cursor")
    @classmethod
    def _cursor_length(cls, value: str | None) -> str | None:
        if value is not None and not 1 <= len(value) <= 2048:
            raise ValueError("cursor must be the exact next_cursor value")
        return value


class CatalogRowsTool:
    def __init__(
        self,
        reader: CatalogReader,
        codec: CursorCodec,
        *,
        default_page_size: int,
        max_page_size: int,
        page_max_bytes: int,
    ) -> None:
        self.reader = reader
        self.codec = codec
        self.default_page_size = default_page_size
        self.max_page_size = max_page_size
        self.page_max_bytes = page_max_bytes

    def read(self, arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, ReadCatalogRowsArguments)
        table = arguments.catalog_name
        page_size = self.default_page_size if arguments.page_size is None else arguments.page_size
        if not 1 <= page_size <= self.max_page_size:
            raise ToolError(f"page_size must be between 1 and {self.max_page_size}.")

        with self.reader.read_only() as run:
            columns = run(COLUMNS_SQL, (_qualified(table),))
            keys = [row["name"] for row in run(PRIMARY_KEY_SQL, (_qualified(table),))]
            if not columns or not keys:
                raise ToolError(f"{table} has no readable columns or primary key; stable paging is impossible.")
            after = None
            if arguments.cursor is not None:
                after = self.codec.decode(arguments.cursor, table, len(keys))
            params: tuple[Any, ...] = (*(after or ()), page_size + 1)
            fetched = run(page_statement(table, keys, after_cursor=after is not None), params)
            position = run(
                position_statement(table, keys) if after is not None else count_statement(table),
                tuple(after or ()),
            )[0]

        names = [column["name"] for column in columns]
        rows: list[list[Any]] = []
        last_key: list[Any] | None = None
        used = 0
        limited_by: str | None = None
        for record in fetched[:page_size]:
            row = as_row(load_exact(record["__row_json"]), names)
            cost = len(dumps(row).encode("utf-8")) + 1
            if used + cost > self.page_max_bytes:
                if not rows:
                    raise ToolError(
                        f"A single {table} row exceeds the {self.page_max_bytes}-byte page limit and "
                        "cannot be returned."
                    )
                limited_by = "BYTE_BUDGET"
                break
            rows.append(row)
            used += cost
            last_key = [record[f"__key_{index}"] for index in range(len(keys))]
        else:
            if len(fetched) > page_size:
                limited_by = "PAGE_SIZE"

        has_more = limited_by is not None
        return {
            "catalog_name": table,
            "columns": [
                {"name": column["name"], "type": column["type"], "nullable": column["nullable"]}
                for column in columns
            ],
            "order_by": keys,
            "rows": rows,
            "returned_rows": len(rows),
            "page_size": page_size,
            "page_limited_by": limited_by,
            "total_rows": int(position["total_rows"]),
            "rows_before_this_page": int(position["rows_before"]),
            "has_more": has_more,
            "next_cursor": self.codec.encode(table, last_key) if has_more and last_key else None,
            "notice": NOTICE,
        }


def catalog_rows_spec(
    reader: CatalogReader,
    codec: CursorCodec,
    *,
    default_page_size: int,
    max_page_size: int,
    page_max_bytes: int,
    timeout_seconds: float,
) -> ToolSpec:
    tool = CatalogRowsTool(
        reader, codec, default_page_size=default_page_size, max_page_size=max_page_size,
        page_max_bytes=page_max_bytes,
    )
    return ToolSpec(
        name="read_catalog_rows",
        description=(
            "Read the complete records of one AI catalog table (every column and row, in primary-key "
            f"order), one page at a time. Default page_size {default_page_size}, maximum "
            f"{max_page_size}; a page can end earlier to stay within the output limit. Continue with "
            "next_cursor while has_more is true. Returns catalog documentation, not market data."
        ),
        arguments_model=ReadCatalogRowsArguments,
        handler=tool.read,
        timeout_seconds=timeout_seconds,
        max_result_bytes=page_max_bytes + 8192,
    )
