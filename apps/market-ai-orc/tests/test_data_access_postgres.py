"""Integration tests for read_catalog_rows and preview_table_rows on a real PostgreSQL server.

Catalog tables use the exact DDL of migration 20260922_001; market tables use the exact columns,
keys, and indexes of the live-generated DATABASE_SCHEMA.md with synthetic rows. Both new
migrations and the provisioning script are applied, and every tool call runs as the
least-privilege market_ai_orc login. Set ORC_TEST_POSTGRES_URL to run.
"""
from __future__ import annotations

import base64
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
from app.tools.catalog_rows import CATALOG_TABLES  # noqa: E402
from app.tools.preview import ORDERING  # noqa: E402
from catalog_fixture import (  # noqa: E402
    FIXTURE_SQL, MARKET_ROWS, MARKET_TABLES, PREVIEW_MIGRATION, READER_MIGRATION, REPO_ROOT,
    TRIGGER_FUNCTION_STUB, catalog_ddl, market_insert, market_primary_key, market_table_ddl,
    RESEARCH_FIXTURE_SQL, research_catalog_ddl,
)

ADMIN_URL = os.environ.get("ORC_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
ROLES = ("market_ai_orc", "market_ai_catalog_reader", "market_ai_preview_reader", "market_ai_preview_owner")
PLAN_ROWS = 20000  # extra rows for the large tables so the planner's index choice is meaningful
LARGE = ("Feature_01_Stock_Daily", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily",
         "IDX_Broker_Summary", "Price_Stock_Indonesia_IDX")
EXACT_CLOSE = "12345678901234567.89"


def _url(database: str, user: str | None = None) -> str:
    parts = urlsplit(ADMIN_URL)
    netloc = parts.netloc if user is None else f"{user}:unused-under-test@{parts.netloc.split('@')[-1]}"
    return urlunsplit((parts.scheme, netloc, f"/{database}", "", ""))


@pytest.fixture(scope="module")
def db() -> Iterator[dict[str, str]]:
    name = f"orc_data_access_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        preexisting = {row[0] for row in admin.execute(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (list(ROLES),))}
        admin.execute(f'CREATE DATABASE "{name}"')
    admin_url = _url(name)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(TRIGGER_FUNCTION_STUB)
        connection.execute(catalog_ddl())
        connection.execute(FIXTURE_SQL)
        connection.execute(research_catalog_ddl())
        connection.execute(RESEARCH_FIXTURE_SQL)
        connection.execute('''
            INSERT INTO public."AI_data_coverage" (dataset_name, coverage_scope, entity_id, coverage_mode,
                pipeline_status, verification_status, quality_status, check_error, last_checked_at)
            SELECT 'IDX_Broker_Summary', 'ENTITY', 'E' || lpad(g::text, 4, '0'), 'ACTUAL_SOURCE',
                   'SOURCE_OBSERVED', 'VERIFIED', 'HEALTHY', repeat('long check note ', 12), now()
            FROM generate_series(1, 45) AS g''')
        for table in MARKET_TABLES:
            connection.execute(market_table_ddl(table))
            connection.execute(market_insert(table, MARKET_ROWS[table]))
            if table in LARGE:
                connection.execute(market_insert(table, PLAN_ROWS).replace(
                    f"generate_series(1, {PLAN_ROWS})", f"generate_series(1001, {1000 + PLAN_ROWS})"))
        connection.execute(f'''
            UPDATE public."Price_Stock_Indonesia_IDX" SET close = {EXACT_CLOSE}
            WHERE (ticker, date) = (SELECT ticker, date FROM public."Price_Stock_Indonesia_IDX"
                                    ORDER BY date DESC, ticker DESC LIMIT 1)''')
        connection.execute(READER_MIGRATION.read_text())
        connection.execute('GRANT SELECT ON public."AI_research_catalog" TO market_ai_catalog_reader')
        connection.execute(PREVIEW_MIGRATION.read_text())
        connection.execute("ANALYZE")
    spec = importlib.util.spec_from_file_location("provision", REPO_ROOT / "scripts/provision_market_ai_orc_login.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    previous = {key: os.environ.get(key) for key in ("DATABASE_URL", "MARKET_AI_ORC_DB_PASSWORD")}
    os.environ.update(DATABASE_URL=admin_url, MARKET_AI_ORC_DB_PASSWORD="p" * 40)
    try:
        module.main()
    finally:
        for key, value in previous.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
    try:
        yield {"admin": admin_url, "login": _url(name, "market_ai_orc")}
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            for role in ROLES:
                if role not in preexisting:
                    admin.execute(f"DROP ROLE IF EXISTS {role}")


def registry(url: str, **options):
    store = CatalogStore(url, connect_timeout_seconds=5, statement_timeout_ms=5000)
    return build_default_registry(store, cursor_secret=b"test-secret", **options)


def call(reg, name: str, arguments: dict) -> dict:
    outcome = reg.execute("c1", name, json.dumps(arguments))
    assert outcome.ok, outcome.output
    return outcome.output["result"]


def admin_rows(url: str, query: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(url) as connection:
        return connection.execute(query, params).fetchall()


def columns_of(url: str, table: str) -> list[str]:
    return [row[0] for row in admin_rows(url, '''
        SELECT attname FROM pg_attribute WHERE attrelid = %s::regclass AND attnum > 0
        AND NOT attisdropped ORDER BY attnum''', (f'public."{table}"',))]


def traverse(reg, catalog: str, page_size: int | None) -> list[dict]:
    pages, cursor = [], None
    while True:
        page = call(reg, "read_catalog_rows", {"catalog_name": catalog, "page_size": page_size, "cursor": cursor})
        pages.append(page)
        if not page["has_more"]:
            assert page["next_cursor"] is None
            return pages
        assert page["next_cursor"]
        cursor = page["next_cursor"]
        assert len(pages) < 500


# --- read_catalog_rows ------------------------------------------------------------------------

EXPECTED_KEYS = {
    "AI_table_catalog": ["table_name"],
    "AI_column_catalog": ["table_name", "column_name"],
    "AI_catalog_relationships": ["relationship_id"],
    "AI_calculation_catalog": ["target_table", "calculation_name", "version"],
    "AI_data_coverage": ["coverage_id"],
    "AI_research_catalog": ["method_id"],
}


@pytest.mark.parametrize("catalog", CATALOG_TABLES)
def test_each_catalog_is_read_completely_in_key_order(db: dict, catalog: str) -> None:
    pages = traverse(registry(db["login"]), catalog, page_size=2)
    names = columns_of(db["admin"], catalog)
    keys = EXPECTED_KEYS[catalog]
    assert all(page["order_by"] == keys for page in pages)
    assert all([column["name"] for column in page["columns"]] == names for page in pages)
    rows = [row for page in pages for row in page["rows"]]
    positions = [names.index(key) for key in keys]
    seen = [tuple(row[i] for i in positions) for row in rows]
    expected = admin_rows(db["admin"], 'SELECT {} FROM public."{}" ORDER BY {}'.format(
        ", ".join(f'"{k}"' for k in keys), catalog, ", ".join(f'"{k}"' for k in keys)))
    assert seen == [tuple(row) for row in expected]  # nothing skipped, duplicated, or reordered
    total = admin_rows(db["admin"], f'SELECT count(*) FROM public."{catalog}"')[0][0]
    assert all(page["total_rows"] == total for page in pages)
    before = 0
    for page in pages:
        assert page["rows_before_this_page"] == before
        before += page["returned_rows"]
    assert before == total


def test_full_catalog_includes_rows_hidden_by_discovery_flags(db: dict) -> None:
    reg = registry(db["login"])
    tables = call(reg, "read_catalog_rows", {"catalog_name": "AI_table_catalog", "page_size": None, "cursor": None})
    names = [column["name"] for column in tables["columns"]]
    by_name = {row[names.index("table_name")]: row for row in tables["rows"]}
    assert {"Denied_Table", "Hidden_Inactive_Table"} <= set(by_name)
    assert by_name["Denied_Table"][names.index("ai_access_level")] == "DENIED"
    assert by_name["IDX_Broker_Summary"][names.index("freshness_sla")] == "1 day"
    assert tables["has_more"] is False and tables["page_size"] == 100
    discovered = {t["table_name"] for t in call(reg, "discover_catalog", {})["tables"]}
    assert "Denied_Table" not in discovered
    columns = traverse(reg, "AI_column_catalog", None)
    all_columns = {row[1] for page in columns for row in page["rows"]}
    assert {"Account Holder", "Internal Note"} <= all_columns


def test_byte_budget_ends_pages_early_without_losing_rows(db: dict) -> None:
    reg = registry(db["login"], page_max_bytes=4096)
    pages = traverse(reg, "AI_data_coverage", page_size=200)
    assert pages[0]["page_limited_by"] == "BYTE_BUDGET" and pages[0]["returned_rows"] < 200
    total = admin_rows(db["admin"], 'SELECT count(*) FROM public."AI_data_coverage"')[0][0]
    ids = [row[0] for page in pages for row in page["rows"]]
    assert len(ids) == len(set(ids)) == total


@pytest.mark.parametrize("catalog", CATALOG_TABLES)
def test_default_16000_byte_pages_traverse_completely_with_headroom(db: dict, catalog: str) -> None:
    from app.compaction import dumps

    reg = registry(db["login"])  # defaults: page_size 100 / max 200, page_max_bytes 16000
    pages = traverse(reg, catalog, page_size=200)
    rows = [row for page in pages for row in page["rows"]]
    names = [column["name"] for column in pages[0]["columns"]]
    keys = [tuple(row[names.index(k)] for k in EXPECTED_KEYS[catalog]) for row in rows]
    total = admin_rows(db["admin"], f'SELECT count(*) FROM public."{catalog}"')[0][0]
    assert len(keys) == len(set(keys)) == total == pages[-1]["total_rows"]
    for page in pages:
        row_bytes = sum(len(dumps(row).encode("utf-8")) + 1 for row in page["rows"])
        assert row_bytes <= 16000
        envelope = len(dumps({"ok": True, "tool": "read_catalog_rows", "result": page}).encode("utf-8"))
        assert envelope <= 16000 + 8192 and envelope - row_bytes < 4096  # well inside the headroom
        if page["has_more"]:
            assert page["page_limited_by"] in {"PAGE_SIZE", "BYTE_BUDGET"} and page["next_cursor"]
    if catalog == "AI_data_coverage":
        assert any(page["page_limited_by"] == "BYTE_BUDGET" for page in pages)


@pytest.mark.parametrize(
    "arguments",
    [
        {"catalog_name": "AI_table_catalog", "page_size": 201, "cursor": None},
        {"catalog_name": "AI_table_catalog", "page_size": 0, "cursor": None},
        {"catalog_name": "AI_table_catalog", "page_size": 5, "cursor": "not-a-cursor"},
    ],
)
def test_invalid_pages_and_cursors_are_rejected(db: dict, arguments: dict) -> None:
    outcome = registry(db["login"]).execute("c", "read_catalog_rows", json.dumps(arguments))
    assert outcome.error_code == "TOOL_ERROR"


def test_cursor_is_bound_to_catalog_and_tamper_evident(db: dict) -> None:
    reg = registry(db["login"])
    page = call(reg, "read_catalog_rows", {"catalog_name": "AI_table_catalog", "page_size": 2, "cursor": None})
    cursor = page["next_cursor"]
    payload = json.loads(base64.urlsafe_b64decode(cursor.split(".")[0] + "=="))
    assert set(payload) == {"v", "c", "k"} and payload["c"] == "AI_table_catalog"
    for bad in (
        {"catalog_name": "AI_column_catalog", "page_size": 2, "cursor": cursor},
        {"catalog_name": "AI_table_catalog", "page_size": 2, "cursor": cursor[:-2] + "AA"},
    ):
        assert reg.execute("c", "read_catalog_rows", json.dumps(bad)).error_code == "TOOL_ERROR"
    other = registry(db["login"])
    other_codec_page = other.execute("c", "read_catalog_rows", json.dumps(
        {"catalog_name": "AI_table_catalog", "page_size": 2, "cursor": cursor}))
    assert other_codec_page.ok  # same secret -> cursors survive restarts and replicas


@pytest.mark.parametrize("extra", [{"sql": "SELECT 1"}, {"where": "is_active"}, {"offset": 5}, {"table": "Price_Stock_Indonesia_IDX"}])
def test_catalog_reader_accepts_no_sql_or_other_tables(db: dict, extra: dict) -> None:
    arguments = {"catalog_name": "AI_table_catalog", "page_size": None, "cursor": None, **extra}
    assert registry(db["login"]).execute("c", "read_catalog_rows", json.dumps(arguments)).error_code == "INVALID_ARGUMENTS"
    bad_name = {"catalog_name": "Price_Stock_Indonesia_IDX", "page_size": None, "cursor": None}
    assert registry(db["login"]).execute("c", "read_catalog_rows", json.dumps(bad_name)).error_code == "INVALID_ARGUMENTS"


# --- preview_table_rows ------------------------------------------------------------------------

@pytest.mark.parametrize("table", MARKET_TABLES)
def test_preview_returns_documented_order_and_all_columns(db: dict, table: str) -> None:
    result = call(registry(db["login"]), "preview_table_rows", {"table_name": table})
    total = MARKET_ROWS[table] + (PLAN_ROWS if table in LARGE else 0)
    assert result["returned_rows"] == len(result["rows"]) == min(20, total)
    assert result["row_limit"] == 20 and result["is_sample"] is True
    names = columns_of(db["admin"], table)
    assert [column["name"] for column in result["columns"]] == names
    order_by = ORDERING[table][0]
    assert result["ordering"]["order_by"] == order_by
    key = market_primary_key(table)
    expected = admin_rows(db["admin"], 'SELECT {} FROM public."{}" ORDER BY {} LIMIT 20'.format(
        ", ".join(f'"{k}"' for k in key), table, order_by))
    got = [tuple(row[names.index(k)] for k in key) for row in result["rows"]]
    assert got == [tuple(str(v) for v in row) for row in expected]


def test_preview_returns_fewer_rows_when_table_is_small(db: dict) -> None:
    result = call(registry(db["login"]), "preview_table_rows", {"table_name": "IDX_Broker_Profile"})
    assert result["returned_rows"] == 5 and "Primary key order" in result["ordering"]["description"]


def test_preview_is_deterministic_and_numeric_values_are_exact(db: dict) -> None:
    reg = registry(db["login"])
    first = call(reg, "preview_table_rows", {"table_name": "Price_Stock_Indonesia_IDX"})
    second = call(reg, "preview_table_rows", {"table_name": "Price_Stock_Indonesia_IDX"})
    assert first["rows"] == second["rows"]
    names = [column["name"] for column in first["columns"]]
    assert first["rows"][0][names.index("close")] == EXACT_CLOSE
    assert "most recent" in first["ordering"]["description"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"table_name": "AI_table_catalog"},
        {"table_name": "Universe_Equity_Description"},
        {"table_name": "Analysis_Request"},
        {"table_name": "Feature_01_Stock_Daily; DROP TABLE x"},
        {"table_name": "Feature_01_Stock_Daily", "limit": 100},
        {"table_name": "Feature_01_Stock_Daily", "offset": 20},
        {"table_name": "Feature_01_Stock_Daily", "cursor": "x"},
        {"table_name": "Feature_01_Stock_Daily", "where": "ticker = 'BBCA'"},
        {"table_name": "Feature_01_Stock_Daily", "order_by": "date ASC"},
        {"table_name": "Feature_01_Stock_Daily", "sql": "SELECT * FROM x"},
    ],
)
def test_preview_rejects_other_tables_and_any_extra_argument(db: dict, arguments: dict) -> None:
    outcome = registry(db["login"]).execute("c", "preview_table_rows", json.dumps(arguments))
    assert outcome.error_code == "INVALID_ARGUMENTS"


def test_database_itself_enforces_the_preview_boundary(db: dict) -> None:
    with psycopg.connect(db["login"]) as connection:
        for table in MARKET_TABLES:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(f'SELECT 1 FROM public."{table}" LIMIT 1')
            connection.rollback()
        for name in ("AI_table_catalog", "Universe_Equity_Description", 'Feature_01_Stock_Daily" --'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("SELECT public.ai_preview_table_rows(%s)", (name,))
            connection.rollback()
        size = connection.execute(
            "SELECT json_array_length(public.ai_preview_table_rows('Feature_02_Broker_Rolling') -> 'rows')"
        ).fetchone()[0]
        assert size == 20
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            connection.execute('DELETE FROM public."AI_table_catalog"')


def test_preview_function_runs_as_a_least_privilege_owner(db: dict) -> None:
    [(owner, definer, config, can_login, superuser)] = admin_rows(db["admin"], '''
        SELECT p.proowner::regrole::text, p.prosecdef, p.proconfig, r.rolcanlogin, r.rolsuper
        FROM pg_proc AS p JOIN pg_roles AS r ON r.oid = p.proowner
        WHERE p.oid = 'public.ai_preview_table_rows(text)'::regprocedure''')
    assert owner == "market_ai_preview_owner" and definer and not can_login and not superuser
    assert config == ["search_path=pg_catalog, pg_temp"]
    relations = '''
        SELECT c.relname FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
          AND has_table_privilege('market_ai_preview_owner', c.oid, %s)'''
    assert {row[0] for row in admin_rows(db["admin"], relations, ("SELECT",))} == set(MARKET_TABLES)
    assert admin_rows(db["admin"], relations, ("INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER",)) == []
    members = admin_rows(db["admin"], '''
        SELECT 1 FROM pg_auth_members WHERE roleid = 'market_ai_preview_owner'::regrole
           OR member = 'market_ai_preview_owner'::regrole''')
    assert members == []


def test_preview_queries_use_indexes_not_full_table_sorts(db: dict) -> None:
    for table in LARGE:
        plan = admin_rows(db["admin"], 'EXPLAIN (FORMAT JSON) SELECT * FROM public."{}" ORDER BY {} LIMIT 20'.format(
            table, ORDERING[table][0]))[0][0]
        text = json.dumps(plan)
        assert "Seq Scan" not in text, (table, text)
        assert "Index Scan" in text, (table, text)


def test_missing_interface_is_reported_explicitly(db: dict) -> None:
    store = CatalogStore(db["login"], connect_timeout_seconds=5, statement_timeout_ms=5000)
    with pytest.raises(ToolError, match="not installed"):
        with store.read_only() as run:
            run("SELECT public.no_such_preview_function(%s)", ("x",))


# --- End-to-end through the existing agent loop --------------------------------------------------

def test_agent_loop_uses_all_four_tools_and_returns_structured_answer(db: dict) -> None:
    from app.orchestrator import AgentOrchestrator
    from app.schemas import AgentRunRequest
    from conftest import ScriptedClient, final_response, make_settings, tool_call_response

    answer = {
        "response_type": "ANSWER",
        "answer": "Feature_02_Broker_Rolling documents broker flows; example rows were shown.",
        "clarification_question": None, "assumptions": [],
        "limitations": ["No analytical calculation was executed."],
    }
    client = ScriptedClient([
        tool_call_response("discover_catalog", "{}", call_id="c1"),
        tool_call_response("get_catalog_details", json.dumps({
            "table_names": ["Feature_02_Broker_Rolling"], "sections": ["COLUMNS", "CALCULATIONS"],
            "column_names": None, "entity_ids": None}), call_id="c2"),
        tool_call_response("read_catalog_rows", json.dumps({
            "catalog_name": "AI_calculation_catalog", "page_size": None, "cursor": None}), call_id="c3"),
        tool_call_response("preview_table_rows", json.dumps({"table_name": "Feature_02_Broker_Rolling"}), call_id="c4"),
        final_response(answer),
    ])
    agent = AgentOrchestrator(make_settings(), client, registry(db["login"]))
    result = agent.run(AgentRunRequest(request_id="e2e", message="Show broker accumulation data and examples."))
    assert result.status == "COMPLETED" and result.response.model_dump() == answer
    assert result.execution.tool_call_count == 4 and result.execution.iterations == 5
    outputs = [json.loads(item["output"]) for item in client.payloads[4]["input"]
               if item.get("type") == "function_call_output"]
    assert [output["tool"] for output in outputs] == [
        "discover_catalog", "get_catalog_details", "read_catalog_rows", "preview_table_rows"]
    assert all(output["ok"] for output in outputs)
    assert outputs[2]["result"]["returned_rows"] == 3 and outputs[2]["result"]["has_more"] is False
    assert outputs[3]["result"]["returned_rows"] == 20
