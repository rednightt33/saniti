#!/usr/bin/env python3
"""Verify deterministic routing and isolated worker database contracts."""

from __future__ import annotations

import argparse
import os

import psycopg
from psycopg.rows import dict_row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    connect = (
        {
            "host": args.host,
            "port": args.port or 5432,
            "dbname": os.environ["PGDATABASE"],
            "user": os.environ["PGUSER"],
            "password": os.environ["PGPASSWORD"],
            "sslmode": "require",
        }
        if args.host
        else {"conninfo": os.environ["DATABASE_URL"]}
    )
    with psycopg.connect(**connect, row_factory=dict_row) as connection:
        tools = connection.execute(
            '''SELECT tool_name,execution_type,is_active
               FROM public."Tool_Catalog"
               WHERE tool_name IN ('route_analysis','run_query_sandbox',
                                    'run_statistical_validation','run_analytics_job')
               ORDER BY tool_name,version'''
        ).fetchall()
        active = {row["tool_name"] for row in tools if row["is_active"]}
        assert active == {
            "route_analysis", "run_query_sandbox", "run_statistical_validation"
        }, active
        column = connection.execute(
            '''SELECT data_type,is_nullable FROM information_schema.columns
               WHERE table_schema='public' AND table_name='Analytics_Job'
                 AND column_name='execution_class' '''
        ).fetchone()
        assert column == {"data_type": "text", "is_nullable": "NO"}, column
        index = connection.execute(
            '''SELECT indexdef FROM pg_indexes
               WHERE schemaname='public' AND indexname='Analytics_Job_claim_idx' '''
        ).fetchone()
        assert index and "execution_class" in index["indexdef"]
        grants = connection.execute(
            '''SELECT count(*) AS count FROM information_schema.role_table_grants
               WHERE grantee IN ('market_query_sandbox','market_statistical_worker')
                 AND table_schema='public' '''
        ).fetchone()["count"]
        assert grants == 0, grants
        catalog = connection.execute(
            '''SELECT documentation_status FROM public."Column_Catalog"
               WHERE table_name='Analytics_Job' AND column_name='execution_class' '''
        ).fetchone()
        assert catalog == {"documentation_status": "VERIFIED"}, catalog
        raw_tables = [
            "Price_Stock_Indonesia_IDX", "IDX_Broker_Summary", "IDX_Stock_Universe",
            "Universe_Equity_Description", "IDX_Broker_Profile",
        ]
        privileges = connection.execute(
            '''SELECT table_name,privilege_type FROM information_schema.role_table_grants
               WHERE grantee='market_ai_app' AND table_schema='public'
                 AND table_name=ANY(%s) ORDER BY table_name,privilege_type''',
            (raw_tables,),
        ).fetchall()
        assert {row["table_name"] for row in privileges} == set(raw_tables)
        assert {row["privilege_type"] for row in privileges} == {"SELECT"}
    print("PASS: routing, queue isolation, index/catalog, backend SELECT-only raw access, zero worker grants")


if __name__ == "__main__":
    main()
