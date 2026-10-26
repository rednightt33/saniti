"""EXEC-M224 against a real PostgreSQL server: rows dated after the check date are kept apart from the last date.

Set COVERAGE_TEST_POSTGRES_URL to an admin URL of a disposable server, for example
postgresql://postgres@127.0.0.1:55432/postgres. A temporary database is created and dropped. The coverage tables come
from the applied migrations verbatim.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

import coverage_job

psycopg = pytest.importorskip("psycopg")

ADMIN_URL = os.environ.get("COVERAGE_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="COVERAGE_TEST_POSTGRES_URL not set")
MIGRATIONS = Path(__file__).resolve().parents[2] / "database/migrations"
AS_OF = date(2026, 10, 26)
CHECKED = datetime(2026, 10, 26, 0, 30, tzinfo=timezone.utc)


def _schema() -> str:
    first = (MIGRATIONS / "20260922_001_create_ai_catalogs.sql").read_text()
    table = first[first.index('CREATE TABLE public."AI_data_coverage"'):]
    table = table[:table.index(");") + 2]
    index = first[first.index('CREATE UNIQUE INDEX "AI_data_coverage_identity_idx"'):]
    index = index[:index.index(";") + 1]
    later = (MIGRATIONS / "20261026_003_coverage_scheduled_rows.sql").read_text()
    alter = later[later.index('ALTER TABLE public."AI_data_coverage"'):]
    alter = alter[:alter.index(";") + 1]
    return f"""
    CREATE TABLE public."AI_table_catalog" (table_name text PRIMARY KEY, is_active boolean, coverage_enabled boolean);
    {table}
    {index}
    {alter}
    CREATE TABLE public.idx_event_annotation (ticker text, annotation_date date);
    CREATE TABLE public."Price_Stock_Indonesia_IDX" (ticker text, date date);
    INSERT INTO public."AI_table_catalog" VALUES ('idx_event_annotation', true, true),
        ('Price_Stock_Indonesia_IDX', true, true);
    """


@pytest.fixture()
def connection():
    name = f"coverage_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(ADMIN_URL)
    url = urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    try:
        with psycopg.connect(url) as conn:
            conn.execute(_schema())
            yield conn
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _refresh(conn, dataset: str, mode: str = "full") -> None:
    rows = coverage_job.raw_coverage_rows(conn, dataset, mode, 30, AS_OF)
    coverage_job.upsert_raw_entities(conn, dataset, rows, CHECKED, mode, AS_OF)
    coverage_job.upsert_raw_dataset_summary(conn, dataset, CHECKED, AS_OF)


def _row(conn, dataset: str, entity: str | None = None):
    return conn.execute(
        """SELECT actual_min_date, actual_max_date, scheduled_max_date, scheduled_row_count, source_row_count
           FROM public."AI_data_coverage" WHERE dataset_name = %s AND COALESCE(entity_id, '') = %s""",
        (dataset, entity or "")).fetchone()


def test_an_event_table_keeps_scheduled_rows_apart(connection) -> None:
    connection.execute("""INSERT INTO public.idx_event_annotation VALUES
        ('BBCA', '2026-08-31'), ('BBCA', '2026-10-23'), ('BBCA', '2026-12-18'), ('BBCA', '2026-11-03'),
        ('TLKM', '2026-10-20'), ('NEWX', '2026-11-30')""")
    _refresh(connection, "idx_event_annotation")
    assert _row(connection, "idx_event_annotation", "BBCA") == (
        date(2026, 8, 31), date(2026, 10, 23), date(2026, 12, 18), 2, 4)
    # a ticker with only scheduled rows has no date that has happened
    assert _row(connection, "idx_event_annotation", "NEWX")[1:4] == (None, date(2026, 11, 30), 1)
    assert _row(connection, "idx_event_annotation") == (
        date(2026, 8, 31), date(2026, 10, 23), date(2026, 12, 18), 3, 6)


def test_a_stored_future_last_date_is_replaced_in_a_nightly_run(connection) -> None:
    """Rows written before EXEC-M224 hold the plain maximum; a nightly upsert must not keep it by GREATEST."""
    connection.execute("""INSERT INTO public."AI_data_coverage" (dataset_name, coverage_scope, entity_id,
        coverage_mode, actual_min_date, actual_max_date, pipeline_status, verification_status, quality_status,
        last_checked_at) VALUES ('idx_event_annotation', 'ENTITY', 'BBCA', 'ACTUAL_SOURCE', '2009-01-20',
        '2026-12-18', 'SOURCE_OBSERVED', 'VERIFIED', 'HEALTHY', '2026-10-25T00:30:00Z')""")
    connection.execute("INSERT INTO public.idx_event_annotation VALUES ('BBCA', '2026-10-23'), ('BBCA', '2026-12-18')")
    _refresh(connection, "idx_event_annotation", mode="nightly")
    assert _row(connection, "idx_event_annotation", "BBCA")[:4] == (
        date(2009, 1, 20), date(2026, 10, 23), date(2026, 12, 18), 1)


def test_a_table_without_future_rows_is_unchanged(connection) -> None:
    """A price table: the last date is the plain maximum, with no scheduled rows, in both modes."""
    connection.execute("""INSERT INTO public."Price_Stock_Indonesia_IDX" VALUES
        ('BBCA', '2026-10-21'), ('BBCA', '2026-10-22'), ('BBCA', '2026-10-23')""")
    _refresh(connection, "Price_Stock_Indonesia_IDX")
    assert _row(connection, "Price_Stock_Indonesia_IDX", "BBCA") == (
        date(2026, 10, 21), date(2026, 10, 23), None, 0, 3)
    assert _row(connection, "Price_Stock_Indonesia_IDX")[1:4] == (date(2026, 10, 23), None, 0)
