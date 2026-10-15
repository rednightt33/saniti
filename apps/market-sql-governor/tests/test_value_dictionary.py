"""EXEC-IMPL-1016 Fase 3 (O1, user decisions 2026-10-15: every text value in a scope comes from the table, or is
refused; "user bilang BRI, tapi kode tickernya BBRI ... How we handle this?"; matching "Alias + persis + potongan",
no pg_trgm): the value dictionary derives stored values, names and aliases from what the database holds.

The fake database below has the live shape (a current and a history reference table per entity, a dated table whose
entity column is registered in the coverage table, a dated code column joined only to profiles) with invented rows.
"""
from __future__ import annotations

import re
from typing import Any

import pytest

from app import value_dictionary as vd
from app.value_dictionary import build, fold, initials, short_name

STATIC = {
    "Universe": {"entity": "Ticker", "label": "Company Name", "rows": [
        {"Ticker": "BBRI", "Company Name": "PT Bank Rakyat Indonesia (Persero) Tbk Class B", "Sector": "Finance"},
        {"Ticker": "BMRI", "Company Name": "PT Bank Mandiri (Persero) Tbk", "Sector": "Finance"},
        {"Ticker": "MAHA", "Company Name": "PT Mandiri Herindo Adiperkasa Tbk", "Sector": "Energy"},
        {"Ticker": "BBCA", "Company Name": "PT Bank Central Asia Tbk", "Sector": "Finance"},
        {"Ticker": "BCAP", "Company Name": "PT Bumi Citra Asia Persada Tbk", "Sector": "Finance"},
        {"Ticker": "NEWX", "Company Name": "PT New Listing Example Tbk", "Sector": "Energy"},
    ]},
    "UniverseHistory": {"entity": "Ticker", "label": "Company Name", "rows": [
        {"Ticker": "BBRI", "Company Name": "PT Bank Rakyat Indonesia (Persero) Tbk"},
        {"Ticker": "OLDX", "Company Name": "PT Old Delisted Company Tbk"},
    ]},
    "Profile": {"entity": "code", "label": "name", "rows": [
        {"code": "YP", "name": "Mirae Asset Sekuritas Indonesia", "kind": "Securities"},
        {"code": "CC", "name": "Mandiri Sekuritas", "kind": "Securities"},
    ]},
}
TABLES = [
    {"table_name": "Universe", "entity_column": "Ticker", "time_column": None},
    {"table_name": "UniverseHistory", "entity_column": "Ticker", "time_column": None},
    {"table_name": "Profile", "entity_column": "code", "time_column": None},
    {"table_name": "Price", "entity_column": "ticker", "time_column": "date"},
    {"table_name": "BrokerDaily", "entity_column": "symbol", "time_column": "date"},
]


def column(table: str, name: str, *, group: bool = True, entity_name: bool = False, kind: str = "text"):
    return {"table_name": table, "column_name": name, "data_type": kind, "group_by_allowed": group,
            "filter_allowed": True, "entity_name": entity_name}


COLUMNS = [
    column("Universe", "Ticker"), column("Universe", "Company Name", entity_name=True), column("Universe", "Sector"),
    column("UniverseHistory", "Ticker"), column("UniverseHistory", "Company Name", entity_name=True),
    column("Profile", "code"), column("Profile", "name", entity_name=True), column("Profile", "kind"),
    column("Price", "ticker"), column("Price", "close", kind="numeric"),
    column("BrokerDaily", "symbol"), column("BrokerDaily", "broker"), column("BrokerDaily", "investor_type"),
]
RELATIONSHIPS = [
    {"left_table": "Universe", "left_columns": ["Ticker"], "right_table": "Price", "right_columns": ["ticker"]},
    {"left_table": "Price", "left_columns": ["ticker"], "right_table": "UniverseHistory", "right_columns": ["Ticker"]},
    {"left_table": "Universe", "left_columns": ["Ticker"], "right_table": "BrokerDaily", "right_columns": ["symbol"]},
    {"left_table": "Profile", "left_columns": ["code"], "right_table": "BrokerDaily", "right_columns": ["broker"]},
    {"left_table": "Price", "left_columns": ["ticker", "date"], "right_table": "BrokerDaily",
     "right_columns": ["symbol", "date"]},
]
# registered entities of the dated tables: OLDX traded before it was delisted; NEWX listed after the last job run
COVERAGE = {"Price": ["BBRI", "BMRI", "MAHA", "BBCA", "BCAP", "OLDX"], "BrokerDaily": ["BBRI", "BMRI"]}
CHECKS = [{"table_name": "BrokerDaily",
           "definition": "CHECK ((investor_type = ANY (ARRAY['Foreign'::text, 'Domestic'::text])))"}]
DISTINCT_RE = re.compile(r'SELECT DISTINCT "(?P<c>[^"]+)" AS value FROM public\."(?P<t>[^"]+)"')
NAMES_RE = re.compile(r'SELECT DISTINCT "(?P<e>[^"]+)" AS code, "(?P<n>[^"]+)" AS name FROM public\."(?P<t>[^"]+)"')


def fake(*, entity_name: bool = True, aliases: list[dict[str, Any]] | None = None, coverage: bool = True):
    calls: list[str] = []

    def run(statement: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        calls.append(statement)
        if "AS entity_name" in statement:
            return [{"entity_name": entity_name, "aliases": aliases is not None, "coverage": coverage}]
        if "AI_table_catalog" in statement:
            return TABLES
        if "AI_column_catalog" in statement:
            assert ("entity_name" in statement) == entity_name
            return [{k: v for k, v in c.items() if entity_name or k != "entity_name"} for c in COLUMNS]
        if "pg_constraint" in statement:
            return CHECKS
        if "AI_catalog_relationships" in statement:
            return RELATIONSHIPS
        if "AI_data_coverage" in statement:
            assert coverage
            return [{"dataset_name": t, "entity_id": e} for t, ids in COVERAGE.items() for e in ids]
        if "AI_entity_alias" in statement:
            return aliases or []
        if match := NAMES_RE.search(statement):
            pairs = {(r[match["e"]], r[match["n"]]) for r in STATIC[match["t"]]["rows"] if r.get(match["n"])}
            return [{"code": c, "name": n} for c, n in sorted(pairs)]
        if match := DISTINCT_RE.search(statement):
            return [{"value": v} for v in sorted({r[match["c"]] for r in STATIC[match["t"]]["rows"]
                                                  if r.get(match["c"]) is not None})]
        raise AssertionError(statement)

    run.calls = calls  # type: ignore[attr-defined]
    return run


def search(dictionary, table: str, col: str, term: str) -> dict[str, Any]:
    outcome = dictionary.search(table, col, [term])
    assert outcome["status"] == "VALUES_FOUND"
    return outcome["results"][0]


@pytest.mark.parametrize(("name", "short", "acronym"), [
    ("PT Bank Rakyat Indonesia (Persero) Tbk Class B", "Bank Rakyat Indonesia", "BRI"),
    ("PT Bank Central Asia Tbk", "Bank Central Asia", "BCA"),
    ("PT Bank Mandiri (Persero) Tbk", "Bank Mandiri", None),  # two words: no initials, never a two-letter alias
    ("Mirae Asset Sekuritas Indonesia", "Mirae Asset Sekuritas Indonesia", "MASI"),
    ("pt. Telkom Indonesia (Persero) tbk.", "Telkom Indonesia", None),
])
def test_names_give_the_short_name_and_initials(name, short, acronym) -> None:
    assert short_name(name) == short and initials(short) == acronym


def test_a_dated_entity_column_takes_registered_entities_and_reference_codes() -> None:
    dictionary = build(fake())
    price = dictionary.domain("Price", "ticker")
    # complete: a delisted code that traded (coverage) and a code listed after the last coverage run (reference)
    assert price.source == "COVERAGE" and price.complete and price.kind == "ENTITY"
    assert {"OLDX", "NEWX", "BBRI"} <= set(price.values)
    assert dictionary.domain("Price", "close") is None  # numbers have no value list


def test_a_code_column_joined_only_to_profiles_is_incomplete() -> None:
    broker = build(fake()).domain("BrokerDaily", "broker")
    # a traded broker code may be missing from a current-state profile: a warning, never a refusal
    assert broker.source == "REFERENCE_TABLE" and not broker.complete and broker.values == ["CC", "YP"]


def test_category_values_come_from_check_lists_and_static_tables() -> None:
    dictionary = build(fake())
    assert dictionary.domain("BrokerDaily", "investor_type").values == ["Domestic", "Foreign"]
    sector = dictionary.domain("Universe", "Sector")
    assert sector.source == "STATIC_TABLE" and sector.kind == "CATEGORY" and sector.values == ["Energy", "Finance"]


def test_an_acronym_resolves_to_the_code_on_every_column_that_joins_the_reference() -> None:
    dictionary = build(fake())
    for table, col in (("Universe", "Ticker"), ("Price", "ticker"), ("BrokerDaily", "symbol")):
        got = search(dictionary, table, col, "BRI")
        assert got["found"] and got["value"] == "BBRI" and got["matched_by"] == "ALIAS"
        assert got["alias"][0]["name"].startswith("PT Bank Rakyat Indonesia")


def test_an_exact_code_is_found_whatever_its_letter_case() -> None:
    got = search(build(fake()), "Price", "ticker", " bbca ")
    assert got["found"] and got["value"] == "BBCA" and got["matched_by"] == "VALUE"


def test_a_name_fragment_gives_candidates_never_a_guess() -> None:
    got = search(build(fake()), "Price", "ticker", "Mandiri")
    assert not got["found"] and got["value"] is None
    assert [c["value"] for c in got["candidates"]] == ["BMRI", "MAHA"]
    assert got["candidates"][0]["name"] == "PT Bank Mandiri (Persero) Tbk"


def test_a_short_name_is_an_alias() -> None:
    got = search(build(fake()), "Price", "ticker", "bank mandiri")
    assert got["found"] and got["value"] == "BMRI"


def test_initials_shared_by_two_entities_are_ambiguous() -> None:
    got = search(build(fake()), "Price", "ticker", "BCA")  # Bank Central Asia and Bumi Citra Asia (Persada: 4)
    assert got["found"] and got["value"] == "BBCA"
    many = search(build(fake()), "Price", "ticker", "Bank")
    assert not many["found"] and {"BBRI", "BMRI", "BBCA"} <= {c["value"] for c in many["candidates"]}


def test_two_codes_behind_one_alias_are_returned_as_candidates() -> None:
    curated = [{"table_name": "Universe", "column_name": "Ticker", "code": "BCAP", "alias": "BCA",
                "alias_type": "MANUAL"}]
    got = search(build(fake(aliases=curated)), "Price", "ticker", "BCA")
    assert not got["found"] and got["ambiguous"] and {a["code"] for a in got["alias"]} == {"BBCA", "BCAP"}


def test_a_former_name_from_the_history_table_is_an_alias() -> None:
    got = search(build(fake()), "Price", "ticker", "Old Delisted Company")
    assert got["found"] and got["value"] == "OLDX"


def test_a_curated_alias_reaches_the_columns_joined_to_its_reference() -> None:
    curated = [{"table_name": "Profile", "column_name": "code", "code": "CC", "alias": "Mansek",
                "alias_type": "MANUAL"}]
    got = search(build(fake(aliases=curated)), "BrokerDaily", "broker", "mansek")
    assert got["found"] and got["value"] == "CC" and got["alias"][0]["alias_type"] == "MANUAL"


def test_the_contract_carries_short_aliases_only() -> None:
    contract = build(fake()).domain("Price", "ticker").contract()
    assert contract["aliases"]["bri"] == ["BBRI"]
    assert "bank rakyat indonesia" not in contract["aliases"]  # whole names stay in the Governor (search-values)
    assert contract["complete"] and contract["kind"] == "ENTITY"


def test_without_the_names_migration_values_still_resolve() -> None:
    dictionary = build(fake(entity_name=False, coverage=False))
    price = dictionary.domain("Price", "ticker")
    assert price.source == "REFERENCE_TABLE" and not price.complete and not price.aliases
    assert search(dictionary, "Price", "ticker", "bbri")["value"] == "BBRI"


def test_an_unknown_column_is_refused() -> None:
    outcome = build(fake()).search("Price", "close", ["1"])
    assert outcome["status"] == "REJECTED" and outcome["reason_code"] == "NO_VALUE_LIST"


def test_a_category_above_the_bound_is_incomplete_and_lists_nothing(monkeypatch) -> None:
    monkeypatch.setattr(vd, "VALUE_DOMAIN_MAX", 1)
    sector = build(fake()).domain("Universe", "Sector")
    assert sector.values == [] and not sector.complete
    assert build(fake()).domain("Universe", "Ticker").complete  # entity codes have their own, higher bound


def test_the_cache_rebuilds_after_its_lifetime() -> None:
    run = fake()
    cache = vd.DictionaryCache(seconds=3600)
    first = cache.get(run)
    assert cache.get(run) is first
    cache.seconds = -1
    assert cache.get(run) is not first


def test_fold_lowers_and_squeezes() -> None:
    assert fold("  Bank   RAKYAT ") == "bank rakyat"
