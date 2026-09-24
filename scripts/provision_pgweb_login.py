#!/usr/bin/env python3
"""Provision/rotate the pgweb login without logging secrets.

Requires migration 20260924_001_create_pgweb_reader.sql. The login joins
pgweb_reader (SELECT on every table/view in schema public, present and future; no
write, DDL, role, or function grant anywhere). Session defaults additionally force
read-only transactions and bounded statement/idle time as a second layer of defense
independent of the GRANT-level restriction.
"""

from __future__ import annotations

import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


LOGIN = "pgweb"
GROUP = "pgweb_reader"


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    password = os.environ.get("PGWEB_DB_PASSWORD", "")
    if not database_url or len(password) < 20:
        raise RuntimeError("DATABASE_URL and a strong PGWEB_DB_PASSWORD (>=20 chars) are required")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (GROUP,)).fetchone():
            raise RuntimeError(f"{GROUP} is missing; apply migration 20260924_001 first")
        exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (LOGIN,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        connection.execute(
            sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
                    "CONNECTION LIMIT 5 PASSWORD {}").format(sql.Identifier(LOGIN), sql.Literal(password))
        )
        connection.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(GROUP), sql.Identifier(LOGIN)))
        for setting, value in (
            ("default_transaction_read_only", "on"),
            ("statement_timeout", "30s"),
            ("lock_timeout", "5s"),
            ("idle_in_transaction_session_timeout", "5min"),
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
        writable = {
            row["relname"]
            for row in connection.execute(
                """SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
                     AND has_table_privilege(%s, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE')""",
                (LOGIN,),
            )
        }
        readable_count = connection.execute(
            """SELECT count(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
                 AND has_table_privilege(%s, c.oid, 'SELECT')""",
            (LOGIN,),
        ).fetchone()["n"]
    if memberships != {GROUP}:
        raise RuntimeError(f"{LOGIN} has unexpected role memberships: {sorted(memberships)}")
    if writable:
        raise RuntimeError(f"{LOGIN} unexpectedly can modify: {sorted(writable)}")
    print(f"{LOGIN} provisioned: read-only SELECT on {readable_count} public table(s)/view(s); "
          f"no write access anywhere; session forced to read-only transactions")


if __name__ == "__main__":
    main()
