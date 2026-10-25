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
# The objects market_ai_sql_reader may read, as granted by the migrations: the six AI catalogs (AI_entity_alias:
# 20261015_014), the seven first market-data tables, the two reference histories (20260927_006) and the fixed-income
# view, its universe and Feature 04 (20261020_001, EXEC-ONBOARD-1), the stock views of Feature 05/06 (20261023_004,
# EXEC-M204), the six INDEX Feature tables (20261025_005, EXEC-INDEX-1). Table_Catalog's column grants are not
# table reads.
APPROVED = {
    "AI_table_catalog", "AI_column_catalog", "AI_catalog_relationships", "AI_calculation_catalog",
    "AI_data_coverage", "AI_entity_alias", "Feature_01_Stock_Daily", "Feature_02_Broker_Rolling",
    "Feature_03_Stock_Broker_Daily", "IDX_Broker_Profile", "IDX_Broker_Summary",
    "IDX_Stock_Universe", "Price_Stock_Indonesia_IDX", "IDX_Stock_Universe_History", "IDX_Broker_Profile_History",
    "Price_Fixed_Income_Final", "Universe_Fixed_income", "Feature_04_Technical_Indicator",
    "Feature_05_Foreign_Domestic_Broker_Detail_Stock", "Feature_06_Foreign_Domestic_Stock",
    "Feature_01_Stock_Daily_INDEX", "Feature_02_Broker_Rolling_INDEX", "Feature_03_Stock_Broker_Daily_INDEX",
    "Feature_04_Technical_Indicator_INDEX", "Feature_05_Foreign_Domestic_Broker_Detail_INDEX",
    "Feature_06_Foreign_Domestic_INDEX",
}
CATALOGS = sum(name.startswith("AI_") for name in APPROVED)


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
        # an approved object absent from this database (a test fixture with the first tables only) is not required
        existing = {name for name in APPROVED if connection.execute(
            "SELECT to_regclass(format('public.%%I', %s::text)) IS NOT NULL AS present", (name,)).fetchone()["present"]}
        writable = {row["relname"] for row in connection.execute(
            """SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
                 AND has_table_privilege(%s, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE')""", (LOGIN,))}
    if memberships != {GROUP}:
        raise RuntimeError(f"{LOGIN} has unexpected role memberships: {sorted(memberships)}")
    if readable != existing:
        raise RuntimeError(f"{LOGIN} readable tables differ: extra={sorted(readable - APPROVED)} "
                           f"missing={sorted(existing - readable)}")
    if writable:
        raise RuntimeError(f"{LOGIN} can write to: {sorted(writable)}")
    print(f"{LOGIN} provisioned: read-only SELECT on {len(existing)} of {len(APPROVED)} approved objects "
          f"({CATALOGS} AI catalogs + {len(APPROVED) - CATALOGS} market-data objects); no write privilege")


if __name__ == "__main__":
    main()
