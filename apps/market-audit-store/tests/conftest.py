"""Integration fixtures: a scratch database with migration 20260928_001 applied, the service connecting as a login
that only belongs to market_ai_audit_store (so every test also proves the grants are enough), market-ai-orc's
outbox writer as a second login, and local object storage. Set AUDIT_TEST_POSTGRES_URL (an administrative URL)."""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "database" / "migrations" / "20260928_001_create_ai_audit_store.sql"
ADMIN_URL = os.environ.get("AUDIT_TEST_POSTGRES_URL") or os.environ.get("ORC_TEST_POSTGRES_URL")
GOVERNOR_KEY, SANDBOX_KEY, READER_KEY = "g" * 40, "s" * 40, "r" * 40


def _with(url: str, *, user: str | None = None, database: str | None = None) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc.split("@", 1)[-1]
    auth = user if user is not None else parts.netloc.split("@", 1)[0] if "@" in parts.netloc else ""
    return urlunsplit((parts.scheme, f"{auth}@{netloc}" if auth else netloc,
                       f"/{database}" if database else parts.path, parts.query, parts.fragment))


@pytest.fixture(scope="session")
def database() -> dict[str, str]:
    if not ADMIN_URL:
        pytest.skip("AUDIT_TEST_POSTGRES_URL is not set")
    name = f"audit_test_{secrets.token_hex(4)}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
        for role, group in (("audit_test_store", "market_ai_audit_store"),
                            ("audit_test_orc", "market_ai_audit_outbox_writer")):
            admin.execute(f"DO $$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
                          f"CREATE ROLE {role} LOGIN; END IF; END$$")
    admin_db = _with(ADMIN_URL, database=name)
    with psycopg.connect(admin_db, autocommit=True) as connection:
        connection.execute(MIGRATION.read_text())
        connection.execute("GRANT market_ai_audit_store TO audit_test_store")
        connection.execute("GRANT market_ai_audit_outbox_writer TO audit_test_orc")
    yield {"admin": admin_db, "store": _with(admin_db, user="audit_test_store"),
           "orc": _with(admin_db, user="audit_test_orc")}
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture()
def clean(database: dict[str, str]) -> dict[str, str]:
    with psycopg.connect(database["admin"], autocommit=True) as c:
        c.execute("ALTER TABLE ai_audit.event DISABLE TRIGGER event_append_only")
        c.execute("ALTER TABLE ai_audit.artifact_access DISABLE TRIGGER artifact_access_append_only")
        c.execute("TRUNCATE ai_audit.event, ai_audit.artifact_access, ai_audit.run_artifact, ai_audit.execution, "
                  "ai_audit.retention_hold, ai_audit.ingest_outbox, ai_audit.artifact, ai_audit.run, "
                  "ai_audit.runtime_image")
        c.execute("ALTER TABLE ai_audit.event ENABLE TRIGGER event_append_only")
        c.execute("ALTER TABLE ai_audit.artifact_access ENABLE TRIGGER artifact_access_append_only")
    return database


@pytest.fixture()
def settings(clean: dict[str, str], tmp_path: Path):
    from app.config import Settings

    return Settings.from_env({
        "AUDIT_DATABASE_URL": clean["store"], "AUDIT_STORE_GOVERNOR_KEY": GOVERNOR_KEY,
        "AUDIT_STORE_SANDBOX_KEY": SANDBOX_KEY, "AUDIT_STORE_READER_KEY": READER_KEY,
        "AUDIT_LOCAL_OBJECT_DIR": str(tmp_path / "objects"), "AUDIT_LOCAL_SIGNING_KEY": "k" * 40,
        "AUDIT_PUBLIC_BASE_URL": "http://testserver", "AUDIT_OUTBOX_MAX_ATTEMPTS": "3"})


@pytest.fixture()
def client(settings) -> TestClient:
    from app.main import create_app

    with TestClient(create_app(settings, start_consumer=False)) as test_client:
        yield test_client


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


GOV, SBX, READ = bearer(GOVERNOR_KEY), bearer(SANDBOX_KEY), bearer(READER_KEY)
