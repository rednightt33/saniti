#!/usr/bin/env python3
"""Synchronize the database table catalog and generate DATABASE_SCHEMA.md."""

from __future__ import annotations

import argparse
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg import sql


STATUS_TABLE = "Database_Table_Status"
TABLE_STATUS_RULES = {
    "Database_Table_Status": ("System", "Automatic / daily documentation refresh"),
    "IDX_Broker_Profile": ("Reference", "Periodic / approximately annual"),
    "IDX_Broker_Summary": ("Transactional", "Continuous / each loaded trading day"),
    "IDX_Stock_Universe": ("Reference", "Periodic / when the listed universe changes"),
    "Universe_Equity_Description": ("Reference", "Periodic / when equity descriptions change"),
    "stockbit_broker_summary_load_log": ("System", "Continuous / alongside broker-summary loads"),
}
TRACKED_REFERENCE_TABLES = (
    "IDX_Broker_Profile",
    "IDX_Stock_Universe",
    "Universe_Equity_Description",
)
TABLE_DESCRIPTIONS = {
    "Database_Table_Status": "Tracks the data freshness, change time, and update pattern of each table.",
    "IDX_Broker_Profile": "Reference list of IDX broker codes, names, and domestic/foreign classification.",
    "IDX_Broker_Summary": "Daily broker buy/sell activity by symbol, broker, investor type, and market board.",
    "IDX_Stock_Universe": "Reference universe of Indonesian listed securities and TradingView fundamentals.",
    "Universe_Equity_Description": "Reference descriptions and sector classifications for the Indonesian equity universe.",
    "stockbit_broker_summary_load_log": "Audit log used to resume and verify Stockbit broker-summary loads by date.",
}
COLUMN_DESCRIPTIONS = {
    "Database_Table_Status": {
        "Table Name": "Exact PostgreSQL table name in the public schema.",
        "Table Category": "Operational role: Reference, Transactional, or System.",
        "Update Pattern": "Expected frequency or event that updates the table.",
        "Latest Data Date": "Latest business or trading date represented by the table, when applicable.",
        "Last Changed At": "UTC timestamp of the latest tracked data load or table change.",
        "Last Checked At": "UTC timestamp when the catalog last inspected the table.",
        "Tracking Status": "Explains whether freshness is derived, tracked, or only a baseline.",
        "Last Operation": "Last tracked operation, such as LOAD, INSERT, UPDATE, DELETE, or TRUNCATE.",
    },
    "IDX_Broker_Profile": {
        "broker_code": "Two-character IDX broker code.",
        "broker_name": "Registered broker or securities-company name.",
        "broker_type": "Broker classification: Domestic or Foreign.",
    },
    "IDX_Broker_Summary": {
        "Date": "Exchange trading date.",
        "Symbol": "IDX security ticker.",
        "Broker": "Two-character broker code.",
        "Investor Type": "Investor classification: Domestic or Foreign.",
        "Market Board": "IDX market board: Regular, Nego, or Tunai.",
        "Buy Value": "Gross purchase value for the key combination.",
        "Sell Value": "Gross sale value for the key combination.",
        "Net Value": "Buy Value minus Sell Value.",
        "Buy Lots": "Number of lots purchased.",
        "Sell Lots": "Number of lots sold.",
        "Net Lots": "Buy Lots minus Sell Lots.",
        "Avg Buy": "Average purchase price when supplied by Stockbit.",
        "Avg Sell": "Average sale price when supplied by Stockbit.",
    },
    "IDX_Stock_Universe": {
        "Region": "Geographic market region.",
        "Country": "Country represented by the listing.",
        "Company Name": "Issuer or company name.",
        "Ticker": "IDX ticker and primary identifier for this table.",
        "Exchange": "Exchange on which the security is listed.",
        "TradingView Symbol": "Symbol used by TradingView.",
        "TradingView URL": "TradingView instrument page URL.",
        "Security Type": "Broad security classification.",
        "Type Specs": "More specific security-type detail.",
        "Is Common Stock": "Source flag indicating whether the security is common stock.",
        "Sector": "Source sector classification.",
        "Sector Translated": "Translated sector classification.",
        "Industry": "Source industry classification.",
        "Industry Translated": "Translated industry classification.",
        "TradingView Country": "Country value used by TradingView.",
        "Currency": "Trading currency.",
        "Fundamental Currency": "Currency used for fundamental figures.",
        "Average Volume 10D": "Average trading volume over the latest 10-day source window.",
        "Market Cap": "Market capitalization when available.",
        "Number of Shareholders": "Reported shareholder count when available.",
        "Number of Employees": "Reported employee count when available.",
        "ISIN": "International Securities Identification Number.",
    },
    "Universe_Equity_Description": {
        "Region": "Geographic market region.",
        "Market": "Market-development classification.",
        "Country": "Country represented by the listing.",
        "Exchange": "Exchange on which the security is listed.",
        "Ticker": "Four-character IDX ticker and primary identifier for this table.",
        "Company_Name": "Issuer or security name.",
        "TV_Sector": "TradingView sector classification.",
        "TV_Industry": "TradingView industry classification.",
        "ISIN": "Unique International Securities Identification Number.",
        "Sector": "IDX or curated sector classification.",
        "Industry": "IDX or curated industry classification.",
    },
    "stockbit_broker_summary_load_log": {
        "target_table": "Schema-qualified table populated by the load.",
        "trade_date": "Trading date covered by this load record.",
        "status": "Per-date state: COMPLETED or NEEDS_REVIEW.",
        "filter_count": "Number of broker/investor/board combinations processed.",
        "request_count": "Number of Stockbit API requests made.",
        "row_count": "Number of summary rows stored for the trading date.",
        "response_bytes": "Total Stockbit response payload size in bytes.",
        "fetch_elapsed_ms": "Cumulative API request duration in milliseconds.",
        "completed_at": "UTC timestamp when the date completed successfully; null while NEEDS_REVIEW.",
        "attempt_count": "Cumulative number of date-level attempts across supervisor restarts.",
        "last_error": "Most recent error for a date; cleared after a successful load.",
        "last_attempt_at": "UTC timestamp of the latest attempt.",
        "status_changed_at": "UTC timestamp when this date's status was last changed.",
    },
}
LOGICAL_RELATIONSHIPS = [
    (
        'IDX_Broker_Summary."Broker"',
        'IDX_Broker_Profile.broker_code',
        "Logical",
        "Broker activity uses the broker-code reference. No database foreign key is enforced.",
    ),
    (
        'IDX_Broker_Summary."Symbol"',
        'IDX_Stock_Universe."Ticker"',
        "Logical",
        "Broker activity symbols map to the stock universe when a matching ticker exists. No database foreign key is enforced.",
    ),
    (
        'Universe_Equity_Description."Ticker"',
        'IDX_Stock_Universe."Ticker"',
        "Logical one-to-one by ticker",
        "Both reference tables describe the same listed security when a matching ticker exists. No database foreign key is enforced.",
    ),
]


def markdown(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def code(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return f"`{str(value).replace('`', '``')}`"


def table_names(connection: psycopg.Connection[Any], schema: str) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (schema,),
        ).fetchall()
    ]


def ensure_status_table(connection: psycopg.Connection[Any], schema: str) -> None:
    create_statement = sql.SQL(
        """
        CREATE TABLE IF NOT EXISTS {}.{} (
            "Table Name" text PRIMARY KEY,
            "Table Category" text NOT NULL,
            "Update Pattern" text NOT NULL,
            "Latest Data Date" date,
            "Last Changed At" timestamptz,
            "Last Checked At" timestamptz NOT NULL,
            "Tracking Status" text NOT NULL,
            "Last Operation" text
        )
        """
    ).format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    connection.execute(create_statement)

    existing_columns = {
        row[0]
        for row in connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema, STATUS_TABLE),
        ).fetchall()
    }
    target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    if "Last Updated" in existing_columns and "Last Checked At" not in existing_columns:
        connection.execute(
            sql.SQL('ALTER TABLE {} RENAME COLUMN "Last Updated" TO "Last Checked At"').format(target)
        )

    additions = (
        ('"Table Category"', "text NOT NULL DEFAULT 'Unclassified'"),
        ('"Update Pattern"', "text NOT NULL DEFAULT 'Unknown'"),
        ('"Latest Data Date"', "date"),
        ('"Last Changed At"', "timestamptz"),
        ('"Last Checked At"', "timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ('"Tracking Status"', "text NOT NULL DEFAULT 'Baseline'"),
        ('"Last Operation"', "text"),
    )
    for column_name, definition in additions:
        connection.execute(
            sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} {}").format(
                target, sql.SQL(column_name), sql.SQL(definition)
            )
        )


def existing_status(connection: psycopg.Connection[Any], schema: str) -> dict[str, dict[str, Any]]:
    target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    rows = connection.execute(
        sql.SQL(
            'SELECT "Table Name", "Last Changed At", "Tracking Status", "Last Operation" FROM {}'
        ).format(target)
    ).fetchall()
    return {
        name: {"last_changed_at": changed_at, "tracking_status": tracking, "last_operation": operation}
        for name, changed_at, tracking, operation in rows
    }


def derive_status_rows(
    connection: psycopg.Connection[Any], schema: str, names: list[str], refreshed_at: datetime
) -> list[tuple[Any, ...]]:
    previous = existing_status(connection, schema)
    rows: list[tuple[Any, ...]] = []
    for name in names:
        category, pattern = TABLE_STATUS_RULES.get(name, ("Unclassified", "Unknown"))
        latest_data_date = None
        last_changed_at = previous.get(name, {}).get("last_changed_at")
        tracking_status = previous.get(name, {}).get("tracking_status") or "Baseline"
        last_operation = previous.get(name, {}).get("last_operation")

        if name == "IDX_Broker_Summary":
            latest_data_date = connection.execute(
                sql.SQL('SELECT max("Date") FROM {}.{}').format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            ).fetchone()[0]
            if "stockbit_broker_summary_load_log" in names:
                last_changed_at = connection.execute(
                    sql.SQL("SELECT max(completed_at) FROM {}.{} WHERE status = 'COMPLETED'").format(
                        sql.Identifier(schema), sql.Identifier("stockbit_broker_summary_load_log")
                    )
                ).fetchone()[0]
            tracking_status = "Derived from table data and load log"
            last_operation = "LOAD"
        elif name == "stockbit_broker_summary_load_log":
            latest_data_date, last_changed_at = connection.execute(
                sql.SQL(
                    "SELECT max(trade_date) FILTER (WHERE status = 'COMPLETED'), "
                    "max(status_changed_at) FROM {}.{}"
                ).format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            ).fetchone()
            tracking_status = "Derived from load log"
            last_operation = "LOAD"
        elif name == STATUS_TABLE:
            last_changed_at = refreshed_at
            tracking_status = "System-managed"
            last_operation = "CATALOG_REFRESH"
        elif name in TRACKED_REFERENCE_TABLES and last_changed_at is None:
            last_changed_at = refreshed_at
            tracking_status = "Baseline; exact changes tracked from this time forward"
            last_operation = "BASELINE"
        elif last_changed_at is None:
            last_changed_at = refreshed_at
            tracking_status = "Baseline only"
            last_operation = "BASELINE"

        rows.append(
            (
                name,
                category,
                pattern,
                latest_data_date,
                last_changed_at,
                refreshed_at,
                tracking_status,
                last_operation,
            )
        )
    return rows


def refresh_status(
    connection: psycopg.Connection[Any], schema: str, names: list[str], refreshed_at: datetime
) -> None:
    target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    status_rows = derive_status_rows(connection, schema, names, refreshed_at)
    upsert = sql.SQL(
        """
        INSERT INTO {} (
            "Table Name", "Table Category", "Update Pattern", "Latest Data Date",
            "Last Changed At", "Last Checked At", "Tracking Status", "Last Operation"
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT ("Table Name") DO UPDATE
        SET "Table Category" = EXCLUDED."Table Category",
            "Update Pattern" = EXCLUDED."Update Pattern",
            "Latest Data Date" = EXCLUDED."Latest Data Date",
            "Last Changed At" = EXCLUDED."Last Changed At",
            "Last Checked At" = EXCLUDED."Last Checked At",
            "Tracking Status" = EXCLUDED."Tracking Status",
            "Last Operation" = EXCLUDED."Last Operation"
        """
    ).format(target)
    with connection.cursor() as cursor:
        cursor.executemany(upsert, status_rows)
    connection.execute(
        sql.SQL('DELETE FROM {} WHERE NOT ("Table Name" = ANY(%s))').format(target),
        (names,),
    )


def trigger_exists(
    connection: psycopg.Connection[Any], schema: str, table_name: str, trigger_name: str
) -> bool:
    return connection.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_trigger AS trigger
            JOIN pg_catalog.pg_class AS class ON class.oid = trigger.tgrelid
            JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = class.relnamespace
            WHERE namespace.nspname = %s
              AND class.relname = %s
              AND trigger.tgname = %s
              AND NOT trigger.tgisinternal
        )
        """,
        (schema, table_name, trigger_name),
    ).fetchone()[0]


def function_exists(connection: psycopg.Connection[Any], schema: str, function_name: str) -> bool:
    return connection.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_proc AS function
            JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = function.pronamespace
            WHERE namespace.nspname = %s AND function.proname = %s
        )
        """,
        (schema, function_name),
    ).fetchone()[0]


def ensure_reference_tracking(connection: psycopg.Connection[Any], schema: str, names: list[str]) -> None:
    status_target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    function_statement = sql.SQL(
        """
        CREATE OR REPLACE FUNCTION {}.track_database_table_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
            UPDATE {}
            SET "Last Changed At" = clock_timestamp(),
                "Tracking Status" = 'Tracked automatically',
                "Last Operation" = TG_OP
            WHERE "Table Name" = TG_TABLE_NAME;
            RETURN NULL;
        END;
        $function$
        """
    ).format(sql.Identifier(schema), status_target)
    if not function_exists(connection, schema, "track_database_table_change"):
        connection.execute(function_statement)

    for table_name in TRACKED_REFERENCE_TABLES:
        if table_name not in names:
            continue
        trigger_name = "database_table_status_change_tracker"
        if trigger_exists(connection, schema, table_name, trigger_name):
            continue
        connection.execute(
            sql.SQL(
                "CREATE TRIGGER {} AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {}.{} "
                "FOR EACH STATEMENT EXECUTE FUNCTION {}.track_database_table_change()"
            ).format(
                sql.Identifier(trigger_name),
                sql.Identifier(schema),
                sql.Identifier(table_name),
                sql.Identifier(schema),
            )
        )


def ensure_broker_load_tracking(connection: psycopg.Connection[Any], schema: str, names: list[str]) -> None:
    log_table = "stockbit_broker_summary_load_log"
    if log_table not in names or "IDX_Broker_Summary" not in names:
        return

    status_target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    log_target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(log_table))
    function_statement = sql.SQL(
        """
        CREATE OR REPLACE FUNCTION {}.track_broker_summary_load()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
            UPDATE {} AS table_status
            SET "Latest Data Date" = newest.latest_data_date,
                "Last Changed At" = newest.last_changed_at,
                "Last Operation" = 'LOAD'
            FROM (
                SELECT max(trade_date) AS latest_data_date,
                       max(completed_at) AS last_changed_at
                FROM {}
                WHERE status = 'COMPLETED'
            ) AS newest
            WHERE table_status."Table Name" IN (
                'IDX_Broker_Summary', 'stockbit_broker_summary_load_log'
            );
            RETURN NULL;
        END;
        $function$
        """
    ).format(sql.Identifier(schema), status_target, log_target)
    if not function_exists(connection, schema, "track_broker_summary_load"):
        connection.execute(function_statement)

    trigger_name = "database_table_status_load_tracker"
    if trigger_exists(connection, schema, log_table, trigger_name):
        return
    connection.execute(
        sql.SQL(
            "CREATE TRIGGER {} AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {} "
            "FOR EACH STATEMENT EXECUTE FUNCTION {}.track_broker_summary_load()"
        ).format(sql.Identifier(trigger_name), log_target, sql.Identifier(schema))
    )


def fetch_status_rows(connection: psycopg.Connection[Any], schema: str) -> list[dict[str, Any]]:
    target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    rows = connection.execute(
        sql.SQL(
            """
            SELECT "Table Name", "Table Category", "Update Pattern", "Latest Data Date",
                   "Last Changed At", "Last Checked At", "Tracking Status", "Last Operation"
            FROM {}
            ORDER BY "Table Name"
            """
        ).format(target)
    ).fetchall()
    keys = (
        "table_name", "category", "pattern", "latest_data_date",
        "last_changed_at", "last_checked_at", "tracking_status", "last_operation",
    )
    return [dict(zip(keys, row)) for row in rows]


def fetch_columns(connection: psycopg.Connection[Any], schema: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = connection.execute(
        """
        SELECT
            columns.table_name,
            columns.column_name,
            columns.data_type,
            columns.udt_name,
            columns.is_nullable,
            columns.column_default,
            columns.ordinal_position,
            pg_catalog.col_description(class.oid, attributes.attnum) AS description
        FROM information_schema.columns AS columns
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.nspname = columns.table_schema
        JOIN pg_catalog.pg_class AS class
          ON class.relnamespace = namespace.oid
         AND class.relname = columns.table_name
        JOIN pg_catalog.pg_attribute AS attributes
          ON attributes.attrelid = class.oid
         AND attributes.attname = columns.column_name
        WHERE columns.table_schema = %s
        ORDER BY columns.table_name, columns.ordinal_position
        """,
        (schema,),
    ).fetchall()
    for table_name, column_name, data_type, udt_name, nullable, default, position, description in rows:
        result[table_name].append(
            {
                "name": column_name,
                "type": data_type if data_type != "USER-DEFINED" else udt_name,
                "nullable": nullable,
                "default": default,
                "position": position,
                "description": description,
            }
        )
    return result


def fetch_constraints(connection: psycopg.Connection[Any], schema: str) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    type_names = {"p": "Primary key", "f": "Foreign key", "u": "Unique", "c": "Check"}
    rows = connection.execute(
        """
        SELECT
            class.relname,
            constraint_definition.conname,
            constraint_definition.contype,
            pg_catalog.pg_get_constraintdef(constraint_definition.oid, true)
        FROM pg_catalog.pg_constraint AS constraint_definition
        JOIN pg_catalog.pg_class AS class
          ON class.oid = constraint_definition.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = class.relnamespace
        WHERE namespace.nspname = %s
          AND constraint_definition.contype IN ('p', 'f', 'u', 'c')
        ORDER BY class.relname, constraint_definition.contype, constraint_definition.conname
        """,
        (schema,),
    ).fetchall()
    for table_name, name, constraint_type, definition in rows:
        result[table_name].append(
            {"name": name, "type": type_names[constraint_type], "definition": definition}
        )
    return result


def fetch_indexes(connection: psycopg.Connection[Any], schema: str) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    rows = connection.execute(
        """
        SELECT tablename, indexname, indexdef
        FROM pg_catalog.pg_indexes
        WHERE schemaname = %s
        ORDER BY tablename, indexname
        """,
        (schema,),
    ).fetchall()
    for table_name, name, definition in rows:
        result[table_name].append({"name": name, "definition": definition})
    return result


def fetch_table_comments(connection: psycopg.Connection[Any], schema: str) -> dict[str, str | None]:
    return {
        table_name: description
        for table_name, description in connection.execute(
            """
            SELECT class.relname, pg_catalog.obj_description(class.oid, 'pg_class')
            FROM pg_catalog.pg_class AS class
            JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = class.relnamespace
            WHERE namespace.nspname = %s AND class.relkind = 'r'
            ORDER BY class.relname
            """,
            (schema,),
        ).fetchall()
    }


def generate_document(
    schema: str,
    refreshed_at: datetime,
    names: list[str],
    columns: dict[str, list[dict[str, Any]]],
    constraints: dict[str, list[dict[str, str]]],
    indexes: dict[str, list[dict[str, str]]],
    comments: dict[str, str | None],
    statuses: list[dict[str, Any]],
) -> str:
    lines = [
        "# Database schema",
        "",
        f"Generated from PostgreSQL schema `{schema}` at `{refreshed_at.isoformat()}`.",
        "",
        "`Latest Data Date` is the newest business date represented in a table. `Last Changed At` is the latest tracked database change or completed load. `Last Checked At` is only the time this catalog inspected the table.",
        "",
        "## Tables",
        "",
        "| Table Name | Category | Update Pattern | Latest Data Date | Last Changed At | Tracking | Definition |",
        "|---|---|---|---|---|---|---|",
    ]
    status_by_name = {item["table_name"]: item for item in statuses}
    for name in names:
        status = status_by_name[name]
        description = comments.get(name) or TABLE_DESCRIPTIONS.get(name) or "No description has been recorded."
        lines.append(
            "| "
            + " | ".join(
                [
                    code(name),
                    markdown(status["category"]),
                    markdown(status["pattern"]),
                    code(status["latest_data_date"]),
                    code(status["last_changed_at"]),
                    markdown(status["tracking_status"]),
                    markdown(description),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Logical relationships",
            "",
            "These relationships are documented for analysis but are not enforced as PostgreSQL foreign keys.",
            "",
            "| From | To | Relationship | Notes |",
            "|---|---|---|---|",
        ]
    )
    for source, destination, relationship_type, notes in LOGICAL_RELATIONSHIPS:
        lines.append(
            f"| {code(source)} | {code(destination)} | {markdown(relationship_type)} | {markdown(notes)} |"
        )

    for name in names:
        description = comments.get(name) or TABLE_DESCRIPTIONS.get(name) or "No description has been recorded."
        lines.extend(["", f"## {name}", "", description, "", "### Columns", ""])
        lines.extend(
            [
                "| Column | Type | Nullable | Default | Definition |",
                "|---|---|---|---|---|",
            ]
        )
        for column in columns.get(name, []):
            description = (
                column["description"]
                or COLUMN_DESCRIPTIONS.get(name, {}).get(column["name"])
                or "No column description has been recorded."
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        code(column["name"]),
                        code(column["type"]),
                        "Yes" if column["nullable"] == "YES" else "No",
                        code(column["default"]),
                        markdown(description),
                    ]
                )
                + " |"
            )

        lines.extend(["", "### Constraints", ""])
        if constraints.get(name):
            lines.extend(["| Name | Type | Definition |", "|---|---|---|"])
            for item in constraints[name]:
                lines.append(
                    f"| {code(item['name'])} | {markdown(item['type'])} | {code(item['definition'])} |"
                )
        else:
            lines.append("No primary-key, foreign-key, unique, or check constraints were found.")

        lines.extend(["", "### Indexes", ""])
        if indexes.get(name):
            lines.extend(["| Name | Definition |", "|---|---|"])
            for item in indexes[name]:
                lines.append(f"| {code(item['name'])} | {code(item['definition'])} |")
        else:
            lines.append("No indexes were found.")

    return "\n".join(lines) + "\n"


def write_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        Path(temporary_name).replace(path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="public")
    parser.add_argument("--output", type=Path, default=Path("DATABASE_SCHEMA.md"))
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    refreshed_at = datetime.now(timezone.utc).replace(microsecond=0)
    with psycopg.connect(database_url) as connection:
        ensure_status_table(connection, args.schema)
        names = table_names(connection, args.schema)
        refresh_status(connection, args.schema, names, refreshed_at)
        ensure_reference_tracking(connection, args.schema, names)
        ensure_broker_load_tracking(connection, args.schema, names)
        statuses = fetch_status_rows(connection, args.schema)
        columns = fetch_columns(connection, args.schema)
        constraints = fetch_constraints(connection, args.schema)
        indexes = fetch_indexes(connection, args.schema)
        comments = fetch_table_comments(connection, args.schema)
        document = generate_document(
            args.schema, refreshed_at, names, columns, constraints, indexes, comments, statuses
        )

    write_atomically(args.output, document)
    print(
        f"Synchronized {len(names)} tables into {args.schema}.{STATUS_TABLE} "
        f"and wrote {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
