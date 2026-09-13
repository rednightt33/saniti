#!/usr/bin/env python3
"""Provision/rotate the fixed least-privilege backend login without logging secrets."""

from __future__ import annotations

import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    password = os.environ.get("MARKET_AI_DB_PASSWORD", "")
    if not database_url or len(password) < 32:
        raise RuntimeError("DATABASE_URL and a strong MARKET_AI_DB_PASSWORD are required")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname='market_ai_app'").fetchone()
        command = sql.SQL("ALTER ROLE market_ai_app LOGIN PASSWORD {}") if exists else sql.SQL("CREATE ROLE market_ai_app LOGIN PASSWORD {}")
        connection.execute(command.format(sql.Literal(password)))
        connection.execute("GRANT market_ai_reader, market_ai_logger TO market_ai_app")
        connection.execute("ALTER ROLE market_ai_app SET statement_timeout = '15s'")
        connection.execute("ALTER ROLE market_ai_app SET idle_in_transaction_session_timeout = '30s'")
        connection.execute("ALTER ROLE market_ai_app SET lock_timeout = '5s'")
        connection.commit()
        checks = connection.execute(
            '''SELECT
               pg_has_role('market_ai_app','market_ai_reader','MEMBER') AS reader,
               pg_has_role('market_ai_app','market_ai_logger','MEMBER') AS logger,
               has_table_privilege('market_ai_app','public."Feature_01_Stock_Daily"','SELECT') AS feature_read,
               has_table_privilege('market_ai_app','public."Price_Stock_Indonesia_IDX"','SELECT') AS raw_price_read,
               has_table_privilege('market_ai_app','public."IDX_Broker_Summary"','SELECT') AS raw_broker_read'''
        ).fetchone()
        if not checks["reader"] or not checks["logger"] or not checks["feature_read"]:
            raise RuntimeError("market_ai_app grants are incomplete")
        if checks["raw_price_read"] or checks["raw_broker_read"]:
            raise RuntimeError("market_ai_app unexpectedly has raw-table access")
    print("market_ai_app provisioned: Feature/catalog read + analysis-log write; raw access denied")


if __name__ == "__main__":
    main()
