"""Catalog discovery v2 (AI_ENABLE_CATALOG_DISCOVERY_V2, implementation plan 2026-09-27, phases C1-C2) against a real
PostgreSQL server: join-semantics and resample fields, table metadata, column tiers and completeness, formula search,
and filtered, keyset-paginated discovery with bound cursors. Two databases: one with only the base catalog migration
(the join-semantics, resample and subject columns absent) and one with those columns added as migrations
20260925_001 and 20260925_003 add them, plus extra tables and formulas for paging and search.

Set ORC_TEST_POSTGRES_URL to an admin URL of a disposable server (see test_catalog_postgres.py)."""
from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest

psycopg = pytest.importorskip("psycopg")

from app.catalog_store import CatalogStore  # noqa: E402
from app.tools import build_default_registry  # noqa: E402
from app.tools.catalog import COLUMN_FULL_V2, _columns_v2  # noqa: E402
from catalog_fixture import (  # noqa: E402
    FIXTURE_SQL, FORMULA_FIXTURE_SQL, RESEARCH_FIXTURE_SQL, TRIGGER_FUNCTION_STUB, catalog_ddl,
    formula_catalog_ddl, research_catalog_ddl,
)

ADMIN_URL = os.environ.get("ORC_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
SECRET = b"catalog-v2-test-secret-0123456789"

# The columns migrations 20260925_001 (subject) and 20260925_003 (join semantics, resample) add, with the join
# semantics the live migration records for the fixture's two visible relationships.
MIGRATED_SQL = '''
ALTER TABLE public."AI_table_catalog"
    ADD COLUMN data_domain text, ADD COLUMN entity_type text, ADD COLUMN asset_type text,
    ADD COLUMN supported_frequencies text[], ADD COLUMN time_semantics text, ADD COLUMN subject_metadata_status text;
UPDATE public."AI_table_catalog" SET data_domain = 'MARKET', entity_type = 'STOCK', asset_type = 'IDX_EQUITY',
    supported_frequencies = ARRAY['1D'], time_semantics = 'Asia/Jakarta exchange trading date',
    subject_metadata_status = 'INFERRED'
WHERE table_name <> 'IDX_Broker_Profile';
UPDATE public."AI_table_catalog" SET data_domain = 'MARKET', entity_type = 'BROKER', asset_type = NULL,
    supported_frequencies = ARRAY['STATIC'], time_semantics = 'Current-state reference data',
    subject_metadata_status = 'INFERRED'
WHERE table_name = 'IDX_Broker_Profile';
ALTER TABLE public."AI_catalog_relationships"
    ADD COLUMN supported_join_semantics text[] NOT NULL DEFAULT '{}'::text[],
    ADD COLUMN left_time_column text, ADD COLUMN right_time_column text,
    ADD COLUMN effective_from_column text, ADD COLUMN effective_to_column text;
UPDATE public."AI_catalog_relationships"
SET supported_join_semantics = ARRAY['EXACT_DATE'], left_time_column = 'Date', right_time_column = 'date'
WHERE left_table = 'IDX_Broker_Summary' AND right_table = 'Feature_02_Broker_Rolling';
UPDATE public."AI_catalog_relationships"
SET supported_join_semantics = ARRAY['EXACT_DATE'], left_time_column = 'date', right_time_column = 'date'
WHERE left_table = 'Feature_02_Broker_Rolling' AND right_table = 'Feature_03_Stock_Broker_Daily';
ALTER TABLE public."AI_column_catalog" ADD COLUMN resample_aggregation text;
UPDATE public."AI_column_catalog" SET resample_aggregation = 'SUM'
WHERE table_name = 'Feature_02_Broker_Rolling' AND column_name = 'net_value_1d';
'''
EXTRA_TABLES = 55
EXTRA_FORMULAS = 60


def _with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def _create(extra_sql: str = "") -> Iterator[str]:
    name = f"orc_catalog_v2_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = _with_database(ADMIN_URL, name)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(TRIGGER_FUNCTION_STUB)
        connection.execute(catalog_ddl())
        connection.execute(FIXTURE_SQL)
        connection.execute(research_catalog_ddl())
        connection.execute(RESEARCH_FIXTURE_SQL)
        connection.execute(formula_catalog_ddl())
        connection.execute(FORMULA_FIXTURE_SQL)
        if extra_sql:
            connection.execute(extra_sql)
    try:
        yield url
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _extras() -> str:
    tables = ",\n".join(
        f"('Paging_Table_{i:03d}', 'Synthetic paging table {i:03d}. ' || repeat('Long description text. ', 12), "
        f"'FEATURE', 'date x ticker', ARRAY['date','ticker'], 'date', 'ticker', true, 'BOUNDED_READ', "
        f"interval '1 day', false, 'PARTIAL')"
        for i in range(1, EXTRA_TABLES + 1))
    formulas = ",\n".join(
        f"('f_{i:03d}', 'Synthetic metric {i:03d}', 'Synthetic test formula number {i:03d}.', 'close', 'm', "
        f"'window=5', 'out', 'Test only')" for i in range(1, EXTRA_FORMULAS + 1))
    return f'''
INSERT INTO public."AI_table_catalog" (table_name, description, category, grain, primary_key_columns, time_column,
    entity_column, is_active, ai_access_level, freshness_sla, coverage_enabled, documentation_status) VALUES
{tables};
UPDATE public."AI_table_catalog" SET data_domain = 'MACRO', entity_type = 'SERIES', asset_type = NULL,
    supported_frequencies = ARRAY['1M'] WHERE table_name LIKE 'Paging_Table_%';
INSERT INTO public."AI_formula_reference" (calculation_id, calculation_name, description, required_inputs,
    formula_method, parameters, output, implementation) VALUES
{formulas},
('zz_rsi_wilder', 'Relative Strength Index', 'Momentum oscillator with Wilder smoothing of gains and losses.',
 'close', 'Wilder', 'period=14', 'rsi', 'Test only'),
('zz_odd_name', 'Odd_name 100% match', 'Name with LIKE wildcards in it.', 'close', 'm', '', 'odd', 'Test only');
'''


@pytest.fixture(scope="module")
def legacy_db() -> Iterator[str]:
    yield from _create()


@pytest.fixture(scope="module")
def migrated_db() -> Iterator[str]:
    yield from _create(MIGRATED_SQL + _extras())


def registry_for(url: str, v2: bool = True):
    store = CatalogStore(url, connect_timeout_seconds=5, statement_timeout_ms=5000)
    return build_default_registry(store, cursor_secret=SECRET, catalog_discovery_v2=v2)


def call(registry, name: str, arguments: dict | None = None) -> dict:
    outcome = registry.execute("c1", name, json.dumps(arguments or {}))
    assert outcome.ok, outcome.output
    return outcome.output["result"]


def failure(registry, name: str, arguments: dict) -> dict:
    outcome = registry.execute("c1", name, json.dumps(arguments))
    assert not outcome.ok
    return outcome.output["error"]


def details(registry, tables, sections, **extra) -> dict:
    return call(registry, "get_catalog_details", {"table_names": tables, "sections": sections,
                                                  "column_names": None, "entity_ids": None, **extra})


# ------------------------------------------------------------------------------------- flag off stays unchanged

def test_with_the_flag_off_the_tool_schemas_are_the_v1_schemas(legacy_db: str) -> None:
    v1 = {d["name"]: d for d in registry_for(legacy_db, v2=False).definitions()}
    assert v1["discover_catalog"]["parameters"]["properties"] == {}
    assert "formula_query" not in v1["get_catalog_details"]["parameters"]["properties"]
    v2 = {d["name"]: d for d in registry_for(legacy_db).definitions()}
    assert set(v2["discover_catalog"]["parameters"]["properties"]) == {
        "query", "data_domain", "entity_type", "asset_type", "page_size", "cursor"}
    assert "formula_query" in v2["get_catalog_details"]["parameters"]["properties"]


# ------------------------------------------------------------------------------- C1: complete targeted response

def test_relationships_carry_the_recorded_join_semantics(migrated_db: str) -> None:
    result = details(registry_for(migrated_db), ["IDX_Broker_Summary", "Feature_02_Broker_Rolling"], ["RELATIONSHIPS"])
    entries = result["sections"]["RELATIONSHIPS"]["entries"]
    by_pair = {(e["left_table"], e["right_table"]): e for e in entries}
    first = by_pair[("IDX_Broker_Summary", "Feature_02_Broker_Rolling")]
    assert first["supported_join_semantics"] == ["EXACT_DATE"]
    assert (first["left_time_column"], first["right_time_column"]) == ("Date", "date")
    assert first["effective_from_column"] is None and first["effective_to_column"] is None  # explicit, not absent
    assert by_pair[("Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily")]["left_time_column"] == "date"
    assert "join_semantics_note" in result["sections"]["RELATIONSHIPS"]
    # visibility still applies: the disallowed and the denied relationship stay hidden
    assert len(entries) == 2


def test_a_catalog_without_the_join_semantics_columns_says_so_instead_of_inventing_them(legacy_db: str) -> None:
    section = details(registry_for(legacy_db), ["IDX_Broker_Summary"], ["RELATIONSHIPS"])["sections"]["RELATIONSHIPS"]
    assert section["join_semantics_recorded"] is False
    assert all("supported_join_semantics" not in e for e in section["entries"])


def test_columns_carry_resample_rules_permissions_and_completeness(migrated_db: str) -> None:
    result = details(registry_for(migrated_db), ["Feature_02_Broker_Rolling", "IDX_Broker_Summary"], ["COLUMNS"])
    section = result["sections"]["COLUMNS"]
    columns = {c["column_name"]: c for c in section["by_table"]["Feature_02_Broker_Rolling"]}
    assert columns["net_value_1d"]["resample_aggregation"] == "SUM"
    assert columns["net_value_20d"]["resample_aggregation"] is None  # recorded as NULL, shown as null
    assert columns["net_value_20d"]["filter_allowed"] is True and columns["net_value_20d"]["unit"] == "IDR"
    assert "never assume LAST" in section["null_meaning"]
    assert section["completeness"]["Feature_02_Broker_Rolling"] == {
        "columns_returned": 2, "columns_total": 2, "complete": True}
    summary = [c["column_name"] for c in section["by_table"]["IDX_Broker_Summary"]]
    assert summary == ["Date", "Investor Type", "Undocumented Field"]  # hidden and sensitive columns stay out
    assert section["by_table"]["IDX_Broker_Summary"][2]["description"] is None
    assert "incomplete" not in section


def test_a_catalog_without_resample_rules_says_they_are_not_recorded(legacy_db: str) -> None:
    section = details(registry_for(legacy_db), ["Feature_02_Broker_Rolling"], ["COLUMNS"])["sections"]["COLUMNS"]
    assert section["resample_rules_recorded"] is False
    assert all(c["resample_aggregation"] is None for c in section["by_table"]["Feature_02_Broker_Rolling"])


def test_details_start_with_the_table_contract_a_data_need_copies(migrated_db: str) -> None:
    meta = details(registry_for(migrated_db), ["IDX_Broker_Summary", "IDX_Broker_Profile"], ["COVERAGE"])
    table = meta["table_metadata"]["IDX_Broker_Summary"]
    assert table["time_column"] == "Date" and table["entity_column"] == "Symbol"
    assert table["subject"]["data_domain"] == "MARKET" and table["subject"]["supported_frequencies"] == ["1D"]
    profile = meta["table_metadata"]["IDX_Broker_Profile"]
    assert profile["time_column"] is None and profile["subject"]["asset_type"] is None


def rows_for(table: str, count: int, description: str = "d" * 400) -> list[dict]:
    return [{"table_name": table, "column_name": f"col_{i:03d}", "description": description, "data_type": "numeric",
             "semantic_type": "MEASURE", "unit": "IDR", "nullable": True, "is_primary_key": False,
             "source_column_or_expression": "x" * 200, "allowed_aggregations": ["SUM"], "filter_allowed": True,
             "group_by_allowed": False, "example_value": None, "documentation_status": "VERIFIED",
             "resample_aggregation": None, "resample_recorded": True, "table_total": count,
             "total_matching": count} for i in range(count)]


def test_prose_is_shortened_then_dropped_before_any_contract_field_and_cuts_name_the_recovery_call() -> None:
    rows = rows_for("Wide_Table", 40)
    compact = _columns_v2(rows, ["Wide_Table"], None, budget=24000)
    assert compact["detail"] == "COMPACT" and len(compact["by_table"]["Wide_Table"]) == 40
    assert len(compact["by_table"]["Wide_Table"][0]["description"]) <= 160
    assert compact["completeness"]["Wide_Table"]["complete"] is True
    minimal = _columns_v2(rows, ["Wide_Table"], None, budget=7000)
    assert minimal["detail"] == "MINIMAL"
    kept = minimal["by_table"]["Wide_Table"]
    assert all({"column_name", "data_type", "unit", "filter_allowed", "group_by_allowed", "allowed_aggregations",
                "resample_aggregation"} <= set(c) for c in kept)
    assert "description" not in kept[0]
    cut = _columns_v2(rows, ["Wide_Table"], None, budget=2500)
    assert cut["incomplete"] is True and cut["completeness"]["Wide_Table"]["complete"] is False
    recovery = cut["recovery_calls"][0]
    returned = {c["column_name"] for c in cut["by_table"]["Wide_Table"]}
    assert recovery["table_names"] == ["Wide_Table"] and recovery["sections"] == ["COLUMNS"]
    assert set(recovery["column_names"]).isdisjoint(returned) and len(returned) + len(recovery["column_names"]) == 40
    full = _columns_v2(rows_for("Small", 2, "short"), ["Small"], None, budget=24000)
    assert full["detail"] == "FULL" and set(full["by_table"]["Small"][0]) <= set(COLUMN_FULL_V2)


# -------------------------------------------------------------------------------------- C2: formula search

def test_formula_search_finds_a_definition_beyond_the_first_fifty_ids(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    found = details(registry, [], ["FORMULAS"], formula_query="relative STRENGTH")["sections"]["FORMULAS"]
    assert found["mode"] == "SEARCH" and [e["calculation_id"] for e in found["entries"]] == ["zz_rsi_wilder"]
    assert found["entries"][0]["match"] == "NAME" and found["entries"][0]["matched_words"] == ["relative", "strength"]
    by_description = details(registry, [], ["FORMULAS"], formula_query="smoothing gains")["sections"]["FORMULAS"]
    assert by_description["entries"][0]["match"] == "DESCRIPTION"
    exact = details(registry, [], ["FORMULAS"], formula_query="ZZ_RSI_WILDER")["sections"]["FORMULAS"]
    assert exact["entries"][0]["match"] == "EXACT"
    # a descriptive query (the A/B run of 2026-09-27 asked "RSI relative strength index"): any keyword matches, the
    # formula matching most of them in its name comes first
    phrase = details(registry, [], ["FORMULAS"], formula_query="RSI relative strength index")["sections"]["FORMULAS"]
    assert phrase["entries"][0]["calculation_id"] == "zz_rsi_wilder"
    assert phrase["query_words"] == ["rsi", "relative", "strength", "index"]
    full = details(registry, [], ["FORMULAS"], formula_ids=["zz_rsi_wilder"])["sections"]["FORMULAS"]
    assert full["entries"][0]["formula_method"] == "Wilder"


def test_formula_search_is_bounded_and_says_when_nothing_or_too_much_matches(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    many = details(registry, [], ["FORMULAS"], formula_query="synthetic metric")["sections"]["FORMULAS"]
    assert many["returned"] == 20 and many["total_matching"] >= EXTRA_FORMULAS and many["truncated"] is True
    assert [e["calculation_id"] for e in many["entries"]][:2] == ["f_001", "f_002"]
    assert all(e["matched_words"] == ["synthetic", "metric"] for e in many["entries"])  # full matches first
    none = details(registry, [], ["FORMULAS"], formula_query="stochastic kalman")["sections"]["FORMULAS"]
    assert none["entries"] == [] and "not synonyms" in none["note"]


def test_formula_query_text_is_data_and_punctuation_only_separates_keywords(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    hostile = details(registry, [], ["FORMULAS"],
                      formula_query="x'; DROP TABLE \"AI_formula_reference\"; --")["sections"]["FORMULAS"]
    assert hostile["mode"] == "SEARCH" and hostile["query_words"] == ["drop", "formula", "reference"]
    assert call(registry, "discover_catalog", {})["formula_catalog"]["formula_count"] == EXTRA_FORMULAS + 3
    literal = details(registry, [], ["FORMULAS"], formula_query="100%")["sections"]["FORMULAS"]
    assert [e["calculation_id"] for e in literal["entries"]] == ["zz_odd_name"]
    underscore = details(registry, [], ["FORMULAS"], formula_query="odd_")["sections"]["FORMULAS"]
    assert [e["calculation_id"] for e in underscore["entries"]] == ["zz_odd_name"]
    assert details(registry, [], ["FORMULAS"], formula_ids=["f_001"])["sections"]["FORMULAS"]["returned"] == 1


def test_formula_query_conflicts_are_refused_not_resolved_silently(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    both = failure(registry, "get_catalog_details", {"table_names": [], "sections": ["FORMULAS"],
                                                     "column_names": None, "entity_ids": None,
                                                     "formula_ids": ["f_001"], "formula_query": "rsi"})
    assert both["code"] == "INVALID_ARGUMENTS" and "exclusive" in both["message"]
    wrong_section = failure(registry, "get_catalog_details", {"table_names": ["IDX_Broker_Summary"],
                                                              "sections": ["COLUMNS"], "column_names": None,
                                                              "entity_ids": None, "formula_query": "rsi"})
    assert "FORMULAS" in wrong_section["message"]


# -------------------------------------------------------------------------------- C2: filtered, paged discovery

def walk(registry, arguments: dict) -> tuple[list[str], list[dict]]:
    names, pages, cursor = [], [], None
    while True:
        page = call(registry, "discover_catalog", {**arguments, "cursor": cursor})
        pages.append(page)
        names += [t["table_name"] for t in page["tables"]]
        if not page["has_more"]:
            return names, pages
        cursor = page["next_cursor"]


def test_an_empty_call_is_still_valid_and_small_catalogs_fit_one_page(legacy_db: str) -> None:
    page = call(registry_for(legacy_db), "discover_catalog", {})
    assert [t["table_name"] for t in page["tables"]] == ["Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily",
                                                         "IDX_Broker_Profile", "IDX_Broker_Summary"]
    assert page["total_matching"] == 4 and page["has_more"] is False and page["next_cursor"] is None
    assert page["formula_catalog"]["formula_count"] == 1 and len(page["catalog_fingerprint"]) == 16


def test_every_visible_table_is_reached_once_across_pages(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    names, pages = walk(registry, {})
    assert len(names) == len(set(names)) == 4 + EXTRA_TABLES
    assert names == sorted(names) and "Hidden_Inactive_Table" not in names and "Denied_Table" not in names
    assert pages[0]["returned_count"] == 20 and pages[0]["total_matching"] == 4 + EXTRA_TABLES
    # a large page is cut by the byte budget, not by page_size, and continues from the last table actually sent
    big, big_pages = walk(registry, {"page_size": 50})
    assert big == names and big_pages[0]["returned_count"] < 50 and big_pages[0]["has_more"] is True


def test_filters_narrow_discovery_and_are_reported(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    market = call(registry, "discover_catalog", {"data_domain": "market", "page_size": 50})
    assert market["total_matching"] == 4 and market["applied_filters"] == {"data_domain": "MARKET"}
    brokers = call(registry, "discover_catalog", {"query": "broker", "entity_type": "STOCK"})
    assert {t["table_name"] for t in brokers["tables"]} == {
        "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily", "IDX_Broker_Summary"}
    nothing = call(registry, "discover_catalog", {"query": "no such table anywhere"})
    assert nothing["tables"] == [] and nothing["note"].startswith("No table matches these filters.")
    assert {"data_domain": "MACRO", "entity_type": "SERIES", "tables": EXTRA_TABLES} in nothing["available_subjects"]
    bad = failure(registry, "discover_catalog", {"data_domain": "market data"})
    assert bad["code"] == "INVALID_ARGUMENTS"


def test_a_keyword_query_matches_any_keyword_and_ranks_tables_matching_more(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    # the A/B run of 2026-09-27 sent phrases such as "stock daily price volume"; a whole-phrase match found nothing
    page = call(registry, "discover_catalog", {"query": "synthetic paging 003", "page_size": 5})
    assert page["query_words"] == ["synthetic", "paging", "003"] and page["total_matching"] == EXTRA_TABLES
    assert page["tables"][0]["table_name"] == "Paging_Table_003"
    assert page["tables"][0]["matched_words"] == ["synthetic", "paging", "003"]
    assert all(t["matched_words"] == ["synthetic", "paging"] for t in page["tables"][1:])
    names, _ = walk(registry, {"query": "synthetic paging 003", "page_size": 20})
    assert len(names) == len(set(names)) == EXTRA_TABLES and names[0] == "Paging_Table_003"
    assert names[1:] == sorted(names[1:])


def test_a_query_also_lists_the_documented_formulas_matching_its_keywords(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    # the A/B run of 2026-09-27 searched "RSI relative strength index" with discover_catalog and found no table
    page = call(registry, "discover_catalog", {"query": "RSI relative strength index"})
    matches = page["formula_catalog"]["matches"]
    assert matches[0] == {"calculation_id": "zz_rsi_wilder", "calculation_name": "Relative Strength Index",
                          "match": "NAME", "matched_words": ["rsi", "relative", "strength", "index"]}
    assert len(matches) <= 5 and "formula_ids" in page["formula_catalog"]["note"]
    assert "matches" not in call(registry, "discover_catalog", {})["formula_catalog"]


def test_keywords_match_visible_column_names_and_descriptions_only(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    foreign = call(registry, "discover_catalog", {"query": "foreign investors"})
    assert [t["table_name"] for t in foreign["tables"]][0] == "IDX_Broker_Summary"
    assert foreign["tables"][0]["matched_words"] == ["foreign", "investor"]  # plural s removed
    hidden = call(registry, "discover_catalog", {"query": "holder"})  # a sensitive column's name
    assert "IDX_Broker_Summary" not in [t["table_name"] for t in hidden["tables"]]


def test_null_written_as_text_means_no_filter_and_generic_queries_are_refused(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    unfiltered = call(registry, "discover_catalog", {"query": "null", "data_domain": "null", "entity_type": "None",
                                                     "page_size": 5})
    assert unfiltered["applied_filters"] == {} and unfiltered["total_matching"] == 4 + EXTRA_TABLES
    generic = failure(registry, "discover_catalog", {"query": "data table"})
    assert generic["code"] == "INVALID_ARGUMENTS" and "keyword" in generic["message"]


def test_cursors_are_bound_to_their_filters_and_refuse_forgery(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    first = call(registry, "discover_catalog", {"data_domain": "MACRO"})
    assert first["has_more"] is True
    changed = failure(registry, "discover_catalog", {"data_domain": "MARKET", "cursor": first["next_cursor"]})
    assert changed["code"] == "CURSOR_INVALID"
    forged = failure(registry, "discover_catalog", {"cursor": first["next_cursor"][:-3] + "abc"})
    assert forged["code"] == "CURSOR_INVALID"
    other_secret = build_default_registry(CatalogStore(migrated_db, connect_timeout_seconds=5,
                                                       statement_timeout_ms=5000),
                                          cursor_secret=b"another-secret-0123456789abcdef", catalog_discovery_v2=True)
    assert failure(other_secret, "discover_catalog", {"data_domain": "MACRO",
                                                      "cursor": first["next_cursor"]})["code"] == "CURSOR_INVALID"


def test_a_catalog_change_while_paging_asks_to_restart(migrated_db: str) -> None:
    registry = registry_for(migrated_db)
    first = call(registry, "discover_catalog", {"query": "paging"})
    with psycopg.connect(migrated_db, autocommit=True) as connection:
        connection.execute('UPDATE public."AI_table_catalog" SET description = description || \' (edited)\' '
                           "WHERE table_name = 'Paging_Table_055'")
    try:
        restart = failure(registry, "discover_catalog", {"query": "paging", "cursor": first["next_cursor"]})
        assert restart["code"] == "CATALOG_CHANGED_RESTART_DISCOVERY"
        again = call(registry, "discover_catalog", {"query": "paging"})
        assert again["catalog_fingerprint"] != first["catalog_fingerprint"]
    finally:
        with psycopg.connect(migrated_db, autocommit=True) as connection:
            connection.execute('UPDATE public."AI_table_catalog" SET description = replace(description, '
                               "' (edited)', '') WHERE table_name = 'Paging_Table_055'")


# ------------------------------------------------------------------ IP1 Stage D: point-in-time metadata in details

PIT_SQL = '''
ALTER TABLE public."AI_column_catalog" ADD COLUMN value_time_basis text NOT NULL DEFAULT 'HISTORICAL';
UPDATE public."AI_column_catalog" SET value_time_basis = 'CURRENT_STATE'
WHERE table_name = 'IDX_Broker_Summary' AND column_name = 'Investor Type';
CREATE TABLE public."Table_Catalog" (table_schema text NOT NULL DEFAULT 'public', table_name text,
    point_in_time_status text, availability_rule text);
INSERT INTO public."Table_Catalog" (table_name, point_in_time_status, availability_rule) VALUES
    ('IDX_Broker_Profile', 'UNAVAILABLE', 'Current reference snapshot only.'),
    ('IDX_Broker_Summary', 'PARTIAL', 'Close of day, used from the next trading observation.');
'''


@pytest.fixture(scope="module")
def pit_db() -> Iterator[str]:
    yield from _create(MIGRATED_SQL + PIT_SQL)


def test_point_in_time_details_carry_availability_and_current_state_columns(pit_db: str, legacy_db: str) -> None:
    store = CatalogStore(pit_db, connect_timeout_seconds=5, statement_timeout_ms=5000)
    on = build_default_registry(store, cursor_secret=SECRET, catalog_discovery_v2=True, point_in_time=True)
    meta = details(on, ["IDX_Broker_Summary", "IDX_Broker_Profile"], ["COLUMNS"])
    assert meta["table_metadata"]["IDX_Broker_Profile"]["availability"] == {
        "point_in_time_status": "UNAVAILABLE", "availability_rule": "Current reference snapshot only."}
    assert meta["table_metadata"]["IDX_Broker_Summary"]["availability"]["point_in_time_status"] == "PARTIAL"
    summary = details(on, ["IDX_Broker_Summary"], ["COLUMNS"])["sections"]["COLUMNS"]["by_table"]["IDX_Broker_Summary"]
    marked = {c["column_name"] for c in summary if c.get("value_time_basis") == "CURRENT_STATE"}
    assert marked == {"Investor Type"} and len(summary) > 1
    # flag off: the result is unchanged
    off = details(registry_for(pit_db), ["IDX_Broker_Summary"], ["COLUMNS"])
    assert "availability" not in off["table_metadata"]["IDX_Broker_Summary"]
    assert not any("value_time_basis" in c for c in off["sections"]["COLUMNS"]["by_table"]["IDX_Broker_Summary"])
    # a catalog without the metadata (or without the grant) still answers, without it
    legacy = build_default_registry(CatalogStore(legacy_db, connect_timeout_seconds=5, statement_timeout_ms=5000),
                                    cursor_secret=SECRET, catalog_discovery_v2=True, point_in_time=True)
    assert "availability" not in details(legacy, ["IDX_Broker_Profile"], ["COLUMNS"])["table_metadata"][
        "IDX_Broker_Profile"]
