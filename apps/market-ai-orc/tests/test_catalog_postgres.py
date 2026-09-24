"""Integration tests against a real PostgreSQL server using the exact catalog migration DDL.

Set ORC_TEST_POSTGRES_URL to an admin URL of a disposable server, for example
postgresql://postgres@127.0.0.1:55432/postgres. A temporary database is created and dropped.
"""
from __future__ import annotations

import importlib.util
import json
import os
import uuid
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest

psycopg = pytest.importorskip("psycopg")

from app.catalog_store import CatalogStore  # noqa: E402
from app.tools import ToolError, build_default_registry  # noqa: E402
from catalog_fixture import (  # noqa: E402
    FIXTURE_SQL, MARKET_DATA_STUBS, READER_MIGRATION, REPO_ROOT, TRIGGER_FUNCTION_STUB, catalog_ddl,
    RESEARCH_FIXTURE_SQL, research_catalog_ddl,
)

ADMIN_URL = os.environ.get("ORC_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")


def _with_database(url: str, database: str, user: str | None = None) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc if user is None else f"{user}:unused-under-test@{parts.netloc.split('@')[-1]}"
    return urlunsplit((parts.scheme, netloc, f"/{database}", parts.query, parts.fragment))


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    name = f"orc_catalog_test_{uuid.uuid4().hex[:8]}"
    roles = ("market_ai_orc", "market_ai_catalog_reader")
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
        preexisting = {row[0] for row in admin.execute(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (list(roles),))}
    url = _with_database(ADMIN_URL, name)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(TRIGGER_FUNCTION_STUB)
        connection.execute(catalog_ddl())
        connection.execute(FIXTURE_SQL)
        connection.execute(research_catalog_ddl())
        connection.execute(RESEARCH_FIXTURE_SQL)
    try:
        yield url
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            for role in roles:
                if role not in preexisting:
                    admin.execute(f"DROP ROLE IF EXISTS {role}")


def registry_for(url: str):
    store = CatalogStore(url, connect_timeout_seconds=5, statement_timeout_ms=5000)
    return build_default_registry(store)


def call(registry, name: str, arguments: dict | None = None) -> dict:
    outcome = registry.execute("c1", name, json.dumps(arguments or {}))
    assert outcome.ok, outcome.output
    return outcome.output["result"]


def details(registry, tables, sections, column_names=None, entity_ids=None) -> dict:
    return call(registry, "get_catalog_details", {
        "table_names": tables, "sections": sections,
        "column_names": column_names, "entity_ids": entity_ids,
    })


def test_discover_exposes_only_active_bounded_read_tables(database: str) -> None:
    result = call(registry_for(database), "discover_catalog")
    names = [table["table_name"] for table in result["tables"]]
    assert names == ["Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily",
                     "IDX_Broker_Profile", "IDX_Broker_Summary"]
    by_name = {table["table_name"]: table for table in result["tables"]}
    summary = by_name["IDX_Broker_Summary"]
    assert summary["primary_key_columns"] == ["Date", "Symbol", "Broker", "Investor Type", "Market Board"]
    assert summary["freshness_sla"] == "1 day"
    assert summary["available_metadata"] == {"columns": 3, "calculations": 0, "relationships": 1}
    assert by_name["Feature_02_Broker_Rolling"]["available_metadata"] == {
        "columns": 2, "calculations": 2, "relationships": 2,
    }
    assert "time_column" not in by_name["IDX_Broker_Profile"]


def test_columns_hide_disallowed_and_sensitive_and_keep_nulls(database: str) -> None:
    result = details(registry_for(database), ["IDX_Broker_Summary"], ["COLUMNS"])
    columns = {entry["column_name"]: entry for entry in result["sections"]["COLUMNS"]["by_table"]["IDX_Broker_Summary"]}
    assert list(columns) == ["Date", "Investor Type", "Undocumented Field"]
    assert columns["Undocumented Field"]["description"] is None
    assert columns["Undocumented Field"]["documentation_status"] == "NEEDS_REVIEW"
    assert "unit" not in columns["Date"]


def test_column_filter_with_spaces_and_unknown_columns(database: str) -> None:
    result = details(registry_for(database), ["IDX_Broker_Summary"], ["COLUMNS"],
                     column_names=["Investor Type", "Internal Note", "Nope"])
    section = result["sections"]["COLUMNS"]
    assert [entry["column_name"] for entry in section["by_table"]["IDX_Broker_Summary"]] == ["Investor Type"]
    assert section["unknown_columns"] == ["Internal Note", "Nope"]


def test_relationships_exclude_disallowed_and_hidden_tables(database: str) -> None:
    result = details(registry_for(database), ["IDX_Broker_Summary", "Feature_02_Broker_Rolling"], ["RELATIONSHIPS"])
    entries = result["sections"]["RELATIONSHIPS"]["entries"]
    assert [(entry["left_table"], entry["right_table"]) for entry in entries] == [
        ("IDX_Broker_Summary", "Feature_02_Broker_Rolling"),
        ("Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily"),
    ]
    assert entries[0]["left_columns"] == ["Date", "Symbol", "Broker", "Investor Type", "Market Board"]
    assert entries[1]["requires_preaggregation"] is True


def test_calculations_only_active_and_filterable(database: str) -> None:
    registry = registry_for(database)
    result = details(registry, ["Feature_02_Broker_Rolling"], ["CALCULATIONS"])
    calcs = result["sections"]["CALCULATIONS"]["by_table"]["Feature_02_Broker_Rolling"]
    assert [(c["calculation_name"], c["version"]) for c in calcs] == [("net_value_1d", "v2"), ("net_value_20d", "v2")]
    rolling = calcs[1]
    assert rolling["required_inputs"] == {"source_tables": ["IDX_Broker_Summary"],
                                          "source_columns": ["Buy Value", "Sell Value"]}
    assert rolling["parameters"] == {"lookback_window": "20 ticker transaction dates", "minimum_history": None}
    assert "defaults" not in rolling
    assert rolling["status"] == "ACTIVE" and "validation_evidence" in rolling
    narrowed = details(registry, ["Feature_02_Broker_Rolling"], ["CALCULATIONS"], column_names=["net_value_20d"])
    assert [c["calculation_name"] for c in narrowed["sections"]["CALCULATIONS"]["by_table"]["Feature_02_Broker_Rolling"]] == ["net_value_20d"]


def test_coverage_dataset_status_entities_and_disabled(database: str) -> None:
    result = details(registry_for(database), ["Feature_02_Broker_Rolling", "IDX_Broker_Profile"],
                     ["COVERAGE"], entity_ids=["BBCA", "ZZZZ"])
    coverage = result["sections"]["COVERAGE"]
    dataset = coverage["datasets"]["Feature_02_Broker_Rolling"]
    assert dataset["coverage_mode"] == "EXPECTED_DERIVED"
    assert dataset["expected_min_date"] == "2018-01-02" and "actual_min_date" not in dataset
    assert dataset["availability_interpretation"].startswith("EXPECTED_NOT_CONFIRMED")
    assert coverage["entity_status_counts"]["Feature_02_Broker_Rolling"] == [{
        "pipeline_status": "MANUAL_REFRESH_REQUIRED", "verification_status": "UNVERIFIED",
        "quality_status": "WARNING", "entity_count": 2,
    }]
    assert [entity["entity_id"] for entity in coverage["entities"]["Feature_02_Broker_Rolling"]] == ["BBCA"]
    assert coverage["unknown_entities"] == ["ZZZZ"]
    assert coverage["coverage_disabled_tables"] == ["IDX_Broker_Profile"]


@pytest.mark.parametrize("hidden", ["Hidden_Inactive_Table", "Denied_Table"])
def test_hidden_tables_cannot_be_requested(database: str, hidden: str) -> None:
    outcome = registry_for(database).execute("c1", "get_catalog_details", json.dumps({
        "table_names": [hidden], "sections": ["COLUMNS"], "column_names": None, "entity_ids": None,
    }))
    assert outcome.error_code == "TOOL_ERROR"


def test_store_is_read_only_and_times_out(database: str) -> None:
    with pytest.raises(ToolError):
        with CatalogStore(database, connect_timeout_seconds=5, statement_timeout_ms=5000).read_only() as run:
            run('DELETE FROM public."AI_table_catalog"', ())
    with pytest.raises(ToolError, match="time limit"):
        with CatalogStore(database, connect_timeout_seconds=5, statement_timeout_ms=100).read_only() as run:
            run("SELECT pg_sleep(1)", ())
    assert len(call(registry_for(database), "discover_catalog")["tables"]) == 4


def _load_provisioning_script():
    spec = importlib.util.spec_from_file_location(
        "provision_market_ai_orc_login", REPO_ROOT / "scripts/provision_market_ai_orc_login.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_least_privilege_role_reads_only_catalogs(database: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with psycopg.connect(database, autocommit=True) as connection:
        connection.execute(MARKET_DATA_STUBS.replace(
            'CREATE TABLE public."Feature_02_Broker_Rolling"', 'CREATE TABLE public."Market_Stub_Feature"'
        ).replace('CREATE TABLE public."IDX_Broker_Summary"', 'CREATE TABLE public."Market_Stub_Raw"'))
        connection.execute(READER_MIGRATION.read_text())
        connection.execute('GRANT SELECT ON public."AI_research_catalog" TO market_ai_catalog_reader')
    monkeypatch.setenv("DATABASE_URL", database)
    monkeypatch.setenv("MARKET_AI_ORC_DB_PASSWORD", "p" * 40)
    _load_provisioning_script().main()

    login_url = _with_database(database, urlsplit(database).path.lstrip("/"), user="market_ai_orc")
    with psycopg.connect(login_url) as connection:
        assert connection.execute("SELECT current_user").fetchone()[0] == "market_ai_orc"
        assert connection.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"
        assert connection.execute('SELECT count(*) FROM public."AI_table_catalog"').fetchone()[0] == 6
        assert connection.execute('SELECT count(*) FROM public."AI_research_catalog"').fetchone()[0] == 1
        for forbidden in ("Market_Stub_Feature", "Market_Stub_Raw", "Table_Catalog"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(f'SELECT 1 FROM public."{forbidden}"')
            connection.rollback()
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            connection.execute('UPDATE public."AI_table_catalog" SET owner = owner')
        connection.rollback()

    result = call(registry_for(login_url), "discover_catalog")
    assert len(result["tables"]) == 4
