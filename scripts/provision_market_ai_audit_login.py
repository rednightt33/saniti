#!/usr/bin/env python3
"""Provision/rotate the market-audit-store login without logging secrets.

Requires migration 20260928_001_create_ai_audit_store.sql. The login market_ai_audit joins market_ai_audit_store
(SELECT, INSERT, UPDATE on the ai_audit tables; INSERT and SELECT only on the append-only event and artifact_access;
no DELETE or TRUNCATE) and nothing else, so AUDIT_DATABASE_URL cannot read market data, the catalogs, conversations or
the public run audit.
Environment: DATABASE_URL (an administrative connection) and MARKET_AI_AUDIT_DB_PASSWORD (32+ characters).
"""

from __future__ import annotations

import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

LOGIN = "market_ai_audit"
GROUP = "market_ai_audit_store"


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    password = os.environ.get("MARKET_AI_AUDIT_DB_PASSWORD", "")
    if not database_url or len(password) < 32:
        raise RuntimeError("DATABASE_URL and a strong MARKET_AI_AUDIT_DB_PASSWORD are required")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (GROUP,)).fetchone():
            raise RuntimeError(f"{GROUP} is missing; apply migration 20260928_001 first")
        exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (LOGIN,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        connection.execute(
            sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
                    "CONNECTION LIMIT 10 PASSWORD {}").format(sql.Identifier(LOGIN), sql.Literal(password)))
        connection.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(GROUP), sql.Identifier(LOGIN)))
        for setting, value in (("statement_timeout", "30s"), ("lock_timeout", "5s"),
                               ("idle_in_transaction_session_timeout", "60s"), ("TimeZone", "UTC")):
            connection.execute(sql.SQL("ALTER ROLE {} SET {} = {}").format(
                sql.Identifier(LOGIN), sql.Identifier(setting), sql.Literal(value)))
        connection.commit()
        memberships = {row["group_name"] for row in connection.execute(
            """SELECT g.rolname AS group_name FROM pg_auth_members m
               JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles u ON u.oid = m.member WHERE u.rolname = %s""",
            (LOGIN,))}
        outside = [row["relname"] for row in connection.execute(
            """SELECT n.nspname || '.' || c.relname AS relname FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname NOT IN ('ai_audit', 'pg_catalog', 'information_schema')
                 AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                 AND has_table_privilege(%s, c.oid, 'SELECT,INSERT,UPDATE,DELETE')""", (LOGIN,))]
        deletable = [row["relname"] for row in connection.execute(
            """SELECT c.relname FROM pg_class c WHERE c.relnamespace = 'ai_audit'::regnamespace AND c.relkind = 'r'
               AND has_table_privilege(%s, c.oid, 'DELETE,TRUNCATE')""", (LOGIN,))]
    if memberships != {GROUP}:
        raise RuntimeError(f"{LOGIN} has unexpected role memberships: {sorted(memberships)}")
    if outside:
        raise RuntimeError(f"{LOGIN} reaches tables outside ai_audit: {sorted(outside)[:10]}")
    if deletable:
        raise RuntimeError(f"{LOGIN} may delete from ai_audit: {sorted(deletable)}")
    print(f"{LOGIN} provisioned: ai_audit only (no DELETE or TRUNCATE); no other table is reachable")


if __name__ == "__main__":
    main()
