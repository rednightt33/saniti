#!/usr/bin/env python3
"""Provision/rotate the market-ai-orc conversation-store login without logging secrets.

Requires migration 20260927_002_create_ai_conversation_store.sql. The login market_ai_conversation joins
market_ai_conversation_store (SELECT, INSERT, UPDATE, DELETE on AI_conversation and AI_conversation_turn only) and
nothing else, so CONVERSATION_DATABASE_URL cannot read the catalogs, market data or the run audit.
Environment: DATABASE_URL (an administrative connection) and MARKET_AI_CONVERSATION_DB_PASSWORD (32+ characters).
"""

from __future__ import annotations

import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


LOGIN = "market_ai_conversation"
GROUP = "market_ai_conversation_store"
# 20260927_002: the conversation and its turns; 20261003_006 (R-STORE): its outputs, executions and exports
TABLES = {"AI_conversation", "AI_conversation_turn", "AI_conversation_output", "AI_conversation_execution",
          "AI_conversation_export"}


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    password = os.environ.get("MARKET_AI_CONVERSATION_DB_PASSWORD", "")
    if not database_url or len(password) < 32:
        raise RuntimeError("DATABASE_URL and a strong MARKET_AI_CONVERSATION_DB_PASSWORD are required")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (GROUP,)).fetchone():
            raise RuntimeError(f"{GROUP} is missing; apply migration 20260927_002 first")
        exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (LOGIN,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        connection.execute(
            sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
                    "CONNECTION LIMIT 10 PASSWORD {}").format(sql.Identifier(LOGIN), sql.Literal(password))
        )
        connection.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(GROUP), sql.Identifier(LOGIN)))
        for setting, value in (
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
        reachable = {
            row["relname"]
            for row in connection.execute(
                """SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
                     AND has_table_privilege(%s, c.oid, 'SELECT,INSERT,UPDATE,DELETE')""",
                (LOGIN,),
            )
        }
        writable = {
            row["relname"]
            for row in connection.execute(
                """SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = ANY(%s)
                     AND has_table_privilege(%s, c.oid, 'SELECT')
                     AND has_table_privilege(%s, c.oid, 'INSERT')
                     AND has_table_privilege(%s, c.oid, 'UPDATE')
                     AND has_table_privilege(%s, c.oid, 'DELETE')""",
                (sorted(TABLES), LOGIN, LOGIN, LOGIN, LOGIN),
            )
        }
    if memberships != {GROUP}:
        raise RuntimeError(f"{LOGIN} has unexpected role memberships: {sorted(memberships)}")
    if reachable != TABLES or writable != TABLES:
        raise RuntimeError(f"{LOGIN} table access differs from the conversation tables: reachable={sorted(reachable)} "
                           f"full={sorted(writable)}")
    print(f"{LOGIN} provisioned: SELECT, INSERT, UPDATE, DELETE on {len(TABLES)} conversation tables only")


if __name__ == "__main__":
    main()
