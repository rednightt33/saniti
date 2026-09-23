from __future__ import annotations

import importlib.util
import os
import uuid
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest

from fixture import (
    MARKET_TABLES, POLICY_CASES_SQL, READER_MIGRATION, REPO_ROOT, TRIGGER_FUNCTION_STUB, catalog_ddl,
    catalog_rows_sql, market_insert, relationships_sql, table_ddl,
)

ADMIN_URL = os.environ.get("GOVERNOR_TEST_POSTGRES_URL") or os.environ.get("ORC_TEST_POSTGRES_URL", "")
API_KEY = "test-governor-api-key-" + "k" * 24
LOGIN_PASSWORD = "test-login-password-" + "p" * 24
ROLES = ("market_sql_governor", "market_ai_sql_reader")


def base_env(**overrides: str) -> dict[str, str]:
    return {"SQL_GOVERNOR_API_KEY": API_KEY,
            "GOVERNOR_DATABASE_URL": "postgresql://market_sql_governor@127.0.0.1:1/unused", **overrides}


def _url(database: str, user: str | None = None) -> str:
    parts = urlsplit(ADMIN_URL)
    netloc = parts.netloc if user is None else f"{user}:{LOGIN_PASSWORD}@{parts.netloc.split('@')[-1]}"
    return urlunsplit((parts.scheme, netloc, f"/{database}", "", ""))


@pytest.fixture(scope="session")
def governed_db() -> Iterator[dict[str, str]]:
    if not ADMIN_URL:
        pytest.skip("GOVERNOR_TEST_POSTGRES_URL / ORC_TEST_POSTGRES_URL not set")
    psycopg = pytest.importorskip("psycopg")
    name = f"governor_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        preexisting = {row[0] for row in admin.execute(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (list(ROLES),))}
        admin.execute(f'CREATE DATABASE "{name}"')
    admin_url = _url(name)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(TRIGGER_FUNCTION_STUB)
        connection.execute(catalog_ddl())
        connection.execute(catalog_rows_sql())
        connection.execute(relationships_sql())
        for table in MARKET_TABLES:
            connection.execute(table_ddl(table))
            connection.execute(market_insert(table))
        connection.execute(POLICY_CASES_SQL)
        connection.execute(READER_MIGRATION.read_text())
        connection.execute("ANALYZE")
    spec = importlib.util.spec_from_file_location(
        "provision_governor", REPO_ROOT / "scripts/provision_market_sql_governor_login.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    previous = {key: os.environ.get(key) for key in ("DATABASE_URL", "MARKET_SQL_GOVERNOR_DB_PASSWORD")}
    os.environ.update(DATABASE_URL=admin_url, MARKET_SQL_GOVERNOR_DB_PASSWORD=LOGIN_PASSWORD)
    try:
        module.main()
    finally:
        for key, value in previous.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
    try:
        yield {"admin": admin_url, "login": _url(name, "market_sql_governor")}
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            for role in ("market_sql_governor", "market_ai_sql_reader"):
                if role not in preexisting:
                    admin.execute(f"DROP ROLE IF EXISTS {role}")
