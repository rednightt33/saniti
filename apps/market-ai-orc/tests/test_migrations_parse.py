"""Every migration under database/migrations/ must parse in PostgreSQL before it is sent to Railway (R27: a generated
migration with an unescaped apostrophe passed its drift test and failed on dev).

PostgreSQL parses a whole multi-statement query before it runs any statement, so the file is sent after a statement
that raises at once: a syntax error anywhere in the file is reported, otherwise the first statement's exception is,
and nothing in the file runs. A DO block's PL/pgSQL body is only parsed when it runs, so each one is also compiled as a
temporary function (check_function_bodies) in a transaction that is rolled back; nothing in it runs either. Not
covered: CREATE FUNCTION bodies and errors that need the live schema (missing tables or columns); the DRYRUN of the
temporary migration job covers those.

Set ORC_TEST_POSTGRES_URL to a disposable server, as for test_catalog_postgres.py.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ADMIN_URL = os.environ.get("ORC_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
MIGRATIONS = sorted((Path(__file__).resolve().parents[3] / "database/migrations").glob("*.sql"))
PARSE_ONLY = "DO $parse_only$ BEGIN RAISE EXCEPTION 'parse-only'; END $parse_only$;\n"
DO_BLOCK = re.compile(r"\bDO\s+(\$\w*\$)(.*?)\1", re.S)


def parse_error(sql: str) -> str | None:
    """None when the text parses; else PostgreSQL's syntax error. Nothing in the text is run."""
    import psycopg

    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        try:
            conn.execute(PARSE_ONLY + sql)
        except psycopg.errors.RaiseException as exc:
            assert "parse-only" in str(exc), exc
            return None
        except psycopg.errors.SyntaxError as exc:
            return str(exc).splitlines()[0]
    raise AssertionError("the parse-only statement did not stop the query")


def do_block_errors(sql: str) -> list[str]:
    """The PL/pgSQL errors of each DO block's body, compiled as a temporary function and rolled back."""
    import psycopg

    errors = []
    with psycopg.connect(ADMIN_URL) as conn:
        for number, (tag, body) in enumerate(DO_BLOCK.findall(sql)):
            try:
                with conn.transaction():
                    conn.execute("SET LOCAL check_function_bodies = on")
                    conn.execute(f"CREATE FUNCTION pg_temp.do_block_{number}() RETURNS void LANGUAGE plpgsql "
                                 f"AS {tag}{body}{tag}")
                    raise _Rollback
            except _Rollback:
                pass
            except psycopg.errors.SyntaxError as exc:
                errors.append(f"DO block {number + 1}: {str(exc).splitlines()[0]}")
        conn.rollback()
    return errors


class _Rollback(Exception):
    pass


def test_the_migrations_are_found() -> None:
    assert len(MIGRATIONS) > 50


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda p: p.name)
def test_the_migration_parses(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    assert parse_error(sql) is None
    assert do_block_errors(sql) == []


def test_an_unescaped_apostrophe_is_caught() -> None:
    assert parse_error("BEGIN;\nSELECT '{\"x\":\"the plan's rule\"}'::jsonb;\nCOMMIT;\n")
    assert parse_error("BEGIN;\nSELECT '{\"x\":\"the plan''s rule\"}'::jsonb;\nCOMMIT;\n") is None


def test_an_unescaped_apostrophe_in_a_do_block_is_caught() -> None:
    broken = "DO $check$\nBEGIN\n    RAISE EXCEPTION 'Expected ('a', 'v5')';\nEND\n$check$;\n"
    assert parse_error(broken) is None  # the outer parse does not see inside the body
    assert do_block_errors(broken)
    assert do_block_errors(broken.replace("('a', 'v5')", "(''a'', ''v5'')")) == []
