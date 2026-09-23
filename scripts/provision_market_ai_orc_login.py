#!/usr/bin/env python3
"""Provision/rotate the catalog-only market-ai-orc login without logging secrets.

Requires migration 20260923_001_create_market_ai_catalog_reader.sql. The login is a member
of market_ai_catalog_reader only, so it can SELECT exactly the five AI_* catalog tables.
"""

from __future__ import annotations

import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


LOGIN = "market_ai_orc"
GROUP = "market_ai_catalog_reader"
CATALOG_TABLES = (
    "AI_table_catalog", "AI_column_catalog", "AI_catalog_relationships",
    "AI_calculation_catalog", "AI_data_coverage",
)


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    password = os.environ.get("MARKET_AI_ORC_DB_PASSWORD", "")
    if not database_url or len(password) < 32:
        raise RuntimeError("DATABASE_URL and a strong MARKET_AI_ORC_DB_PASSWORD are required")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (GROUP,)).fetchone():
            raise RuntimeError(f"{GROUP} is missing; apply migration 20260923_001 first")
        exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (LOGIN,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        connection.execute(
            sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
                    "CONNECTION LIMIT 5 PASSWORD {}").format(sql.Identifier(LOGIN), sql.Literal(password))
        )
        connection.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(GROUP), sql.Identifier(LOGIN)))
        for setting, value in (
            ("default_transaction_read_only", "on"),
            ("statement_timeout", "5s"),
            ("lock_timeout", "2s"),
            ("idle_in_transaction_session_timeout", "15s"),
        ):
            connection.execute(
                sql.SQL("ALTER ROLE {} SET {} = {}").format(
                    sql.Identifier(LOGIN), sql.Identifier(setting), sql.Literal(value)
                )
            )
        connection.commit()

        memberships = {
            row["group_name"]
            for row in connection.execute(
                """SELECT g.rolname AS group_name FROM pg_auth_members m
                   JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles u ON u.oid = m.member
                   WHERE u.rolname = %s""",
                (LOGIN,),
            )
        }
        readable = {
            row["relname"]
            for row in connection.execute(
                """SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
                     AND has_table_privilege(%s, c.oid, 'SELECT')""",
                (LOGIN,),
            )
        }
    if memberships != {GROUP}:
        raise RuntimeError(f"{LOGIN} has unexpected role memberships: {sorted(memberships)}")
    if readable != set(CATALOG_TABLES):
        raise RuntimeError(
            f"{LOGIN} readable tables differ from the catalog set: "
            f"extra={sorted(readable - set(CATALOG_TABLES))} missing={sorted(set(CATALOG_TABLES) - readable)}"
        )
    print(f"{LOGIN} provisioned: read-only SELECT on {len(CATALOG_TABLES)} AI catalog tables; "
          "no other public table is readable")


if __name__ == "__main__":
    main()
