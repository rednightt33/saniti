#!/usr/bin/env python3
"""Provision/rotate the market-sql-governor login without logging secrets.

Requires migration 20260923_005_create_market_ai_sql_reader.sql. The login joins
market_ai_sql_reader only: SELECT on the five AI catalogs and the seven approved market-data
tables, nothing else. Its credential belongs to market-sql-governor alone.
"""

from __future__ import annotations

import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

LOGIN = "market_sql_governor"
GROUP = "market_ai_sql_reader"
APPROVED = {
    "AI_table_catalog", "AI_column_catalog", "AI_catalog_relationships", "AI_calculation_catalog",
    "AI_data_coverage", "Feature_01_Stock_Daily", "Feature_02_Broker_Rolling",
    "Feature_03_Stock_Broker_Daily", "IDX_Broker_Profile", "IDX_Broker_Summary",
    "IDX_Stock_Universe", "Price_Stock_Indonesia_IDX",
}


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    password = os.environ.get("MARKET_SQL_GOVERNOR_DB_PASSWORD", "")
    if not database_url or len(password) < 32:
        raise RuntimeError("DATABASE_URL and a strong MARKET_SQL_GOVERNOR_DB_PASSWORD are required")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (GROUP,)).fetchone():
            raise RuntimeError(f"{GROUP} is missing; apply migration 20260923_005 first")
        exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (LOGIN,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        connection.execute(
            sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS "
                    "CONNECTION LIMIT 5 PASSWORD {}").format(sql.Identifier(LOGIN), sql.Literal(password))
        )
        connection.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(GROUP), sql.Identifier(LOGIN)))
        for setting, value in (
            ("default_transaction_read_only", "on"),
            ("statement_timeout", "60s"),
            ("lock_timeout", "2s"),
            ("idle_in_transaction_session_timeout", "30s"),
        ):
            connection.execute(sql.SQL("ALTER ROLE {} SET {} = {}").format(
                sql.Identifier(LOGIN), sql.Identifier(setting), sql.Literal(value)))
        connection.commit()

        memberships = {row["group_name"] for row in connection.execute(
            """SELECT g.rolname AS group_name FROM pg_auth_members m
               JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles u ON u.oid = m.member
               WHERE u.rolname = %s""", (LOGIN,))}
        readable = {row["relname"] for row in connection.execute(
            """SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
                 AND has_table_privilege(%s, c.oid, 'SELECT')""", (LOGIN,))}
        writable = {row["relname"] for row in connection.execute(
            """SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
                 AND has_table_privilege(%s, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE')""", (LOGIN,))}
    if memberships != {GROUP}:
        raise RuntimeError(f"{LOGIN} has unexpected role memberships: {sorted(memberships)}")
    if readable != APPROVED:
        raise RuntimeError(f"{LOGIN} readable tables differ: extra={sorted(readable - APPROVED)} "
                           f"missing={sorted(APPROVED - readable)}")
    if writable:
        raise RuntimeError(f"{LOGIN} can write to: {sorted(writable)}")
    print(f"{LOGIN} provisioned: read-only SELECT on {len(APPROVED)} approved tables "
          "(5 AI catalogs + 7 market-data tables); no write privilege")


if __name__ == "__main__":
    main()
