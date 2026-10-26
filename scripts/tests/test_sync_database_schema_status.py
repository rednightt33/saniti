"""Database_Table_Status takes category, update rule and latest date from Table_Catalog (the owner), not from a list in
the script; a table missing from that list is no longer 'Unclassified / Unknown'. Needs a scratch PostgreSQL."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sync_database_schema import derive_status_rows  # noqa: E402

URL = os.environ.get("SCHEMA_TEST_POSTGRES_URL") or os.environ.get("ORC_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="SCHEMA_TEST_POSTGRES_URL is not set")


@pytest.fixture()
def db():
    with psycopg.connect(URL) as connection:
        connection.execute("CREATE SCHEMA status_test")
        connection.execute("""CREATE TABLE status_test."Database_Table_Status" ("Table Name" text PRIMARY KEY,
            "Last Changed At" timestamptz, "Tracking Status" text, "Last Operation" text)""")
        connection.execute("""CREATE TABLE public."Table_Catalog" (table_schema text, table_name text, category text,
            update_rule text, observation_date_column text)""") if not connection.execute(
            "SELECT to_regclass('public.\"Table_Catalog\"')").fetchone()[0] else None
        connection.execute("CREATE TABLE status_test.indexed_feature (ticker text, trade_date date)")
        connection.execute("CREATE INDEX ON status_test.indexed_feature (trade_date)")
        connection.execute("CREATE TABLE status_test.unindexed_feature (ticker text, trade_date date)")
        for t in ("indexed_feature", "unindexed_feature"):
            connection.execute(f"INSERT INTO status_test.{t} VALUES ('A', '2026-10-01'), ('B', '2026-10-23')")
            connection.execute("""INSERT INTO public."Table_Catalog" VALUES ('status_test', %s, 'Feature',
                'refresh after the source load', 'trade_date')""", (t,))
        connection.execute("CREATE TABLE status_test.uncatalogued (x int)")
        yield connection
        connection.rollback()


def test_category_rule_and_latest_date_come_from_table_catalog(db) -> None:
    names = ["indexed_feature", "unindexed_feature", "uncatalogued"]
    rows = {r[0]: r for r in derive_status_rows(db, "status_test", names, datetime.now(timezone.utc))}
    assert rows["indexed_feature"][1:4] == ("Feature", "refresh after the source load", rows["indexed_feature"][3])
    assert str(rows["indexed_feature"][3]) == "2026-10-23"
    # no index that starts with the date column: left unknown instead of scanning the table
    assert rows["unindexed_feature"][1] == "Feature" and rows["unindexed_feature"][3] is None
    assert rows["uncatalogued"][1:3] == ("Unclassified", "Unknown")
