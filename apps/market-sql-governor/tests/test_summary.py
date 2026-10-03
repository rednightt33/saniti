"""POST /v1/summary (G18 phase 2, round 2026-10-03 D5): a summary over a period per entity or group, its rules
derived from the Governor's own catalog contract, the window taken from the table's own calendar, and the values equal
to the same summary computed independently."""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app import extract as ex
from app import summary as sm
from app.config import Settings
from app.governor import Database, Governor, Summarizer
from conftest import base_env
from test_extract import ALL, PRICE, admin, contract, pred

FEATURE_03 = "Feature_03_Stock_Broker_Daily"


def unit_contract() -> dict[str, Any]:
    catalog = contract()
    columns = catalog["columns"][PRICE]
    for name, semantic in (("ticker", "IDENTIFIER"), ("date", "TIME"), ("close", "MEASURE"), ("volume", "MEASURE")):
        columns[name]["semantic_type"] = semantic
        columns[name]["group_by_allowed"] = semantic != "MEASURE"
    columns["close"]["resample_aggregation"] = "LAST"
    columns["volume"]["resample_aggregation"] = "SUM"
    columns["volume"]["cross_entity_aggregation"] = None
    return catalog


def spec(group_by=("ticker",), measures=None, period=None, scope: dict = ALL) -> dict[str, Any]:
    return {"summary_version": "summary_spec/v1", "source_table": PRICE, "scope": scope, "restrictions": [],
            "group_by": list(group_by),
            "measures": measures if measures is not None else [
                {"column": "volume", "function": "SUM", "as": "volume_sum"},
                {"column": "close", "function": "LAST", "as": "last_close"},
                {"column": "close", "function": "MAX", "as": "high_close"},
                {"column": None, "function": "COUNT", "as": "rows"}],
            "period": period or {"trading_days": 5, "as_of": "2026-08-31"}}


def bind(raw: dict[str, Any], catalog: dict[str, Any] | None = None) -> sm.BoundSummary:
    return sm.bind_summary(sm.SummarySpec.model_validate(raw), catalog or unit_contract(), max_in_values=500)


def test_a_per_entity_summary_compiles_last_first_and_coverage() -> None:
    bound = bind(spec())
    assert bound.dropped == []
    text = sm.compile_summary(bound, date(2026, 8, 25), date(2026, 8, 31), 201).text
    assert 'sum("t0"."volume") AS "volume_sum"' in text
    assert '(array_agg("t0"."close" ORDER BY "t0"."date" DESC) FILTER (WHERE "t0"."close" IS NOT NULL))[1] AS ' \
           '"last_close"' in text
    assert 'count(DISTINCT "t0"."date") AS "days_present"' in text and 'GROUP BY "t0"."ticker"' in text


@pytest.mark.parametrize("raw, code", [
    # summed over time but not additive over time (a price)
    (spec(measures=[{"column": "close", "function": "SUM", "as": "s"}]), "AGGREGATION_NOT_ADDITIVE"),
    # summed across the tickers it drops without a cross-entity SUM rule (volume: NULL in the catalog)
    (spec(group_by=(), measures=[{"column": "volume", "function": "SUM", "as": "s"}]), "AGGREGATION_NOT_ADDITIVE"),
    # LAST of a column whose rule over time is SUM, and LAST across tickers
    (spec(measures=[{"column": "volume", "function": "LAST", "as": "s"}]), "AGGREGATION_NOT_ALLOWED"),
    (spec(group_by=(), measures=[{"column": "close", "function": "LAST", "as": "s"}]), "AGGREGATION_NOT_ALLOWED"),
    (spec(measures=[{"column": "ticker", "function": "MAX", "as": "s"}]), "AGGREGATION_NOT_ALLOWED"),
    (spec(group_by=("date",)), "SUMMARY_INVALID"),
    (spec(measures=[{"column": None, "function": "COUNT", "as": "days_present"}]), "SUMMARY_INVALID"),
    (spec(measures=[{"column": "volume", "function": "COUNT", "as": "n"}]), "SUMMARY_INVALID"),
])
def test_the_rules_come_from_the_catalog(raw, code) -> None:
    with pytest.raises(ex.ExtractStop) as caught:
        bind(raw)
    assert (caught.value.status, caught.value.code) == ("REJECTED_POLICY", code)


def test_a_cross_entity_rule_allows_a_total_across_tickers() -> None:
    catalog = unit_contract()
    catalog["columns"][PRICE]["volume"]["cross_entity_aggregation"] = "SUM"
    assert bind(spec(group_by=(), measures=[{"column": "volume", "function": "SUM", "as": "s"}]), catalog).dropped \
        == ["ticker"]


@pytest.mark.parametrize("period", [{"from": "2026-08-01"}, {"trading_days": 5},
                                    {"from": "2026-08-01", "to": "2026-08-31", "trading_days": 5, "as_of": "2026-08-31"}])
def test_a_period_is_a_range_or_trading_days(period) -> None:
    with pytest.raises(ValueError):
        sm.SummarySpec.model_validate(spec(period=period))


# ---------------------------------------------------------------- integration (the market_sql_governor login)

@pytest.fixture
def rules(governed_db):
    """The catalog's rules over time and across entities for the test (the live values: 20260928_002, 20260927_005)."""
    for column in ("resample_aggregation", "cross_entity_aggregation"):
        if not admin(governed_db, "SELECT 1 FROM information_schema.columns WHERE table_name = 'AI_column_catalog' "
                                  "AND column_name = %s", (column,)):
            admin(governed_db, f'ALTER TABLE public."AI_column_catalog" ADD COLUMN {column} text')
    for table, column, over_time, across in ((PRICE, "volume", "SUM", None), (PRICE, "close", "LAST", None),
                                             (FEATURE_03, "foreign_net_value", "SUM", "SUM")):
        admin(governed_db, 'UPDATE public."AI_column_catalog" SET resample_aggregation = %s, '
                           "cross_entity_aggregation = %s WHERE table_name = %s AND column_name = %s",
              (over_time, across, table, column))
    yield


def summarizer(db: dict, tmp_path) -> Summarizer:
    settings = Settings.from_env(base_env(GOVERNOR_DATABASE_URL=db["login"], SQL_DATASET_LOCAL_DIR=str(tmp_path)))
    return Summarizer(Governor(settings, Database(settings), None))


def ask(service: Summarizer, raw: dict[str, Any], purpose: str = "METRIC") -> dict[str, Any]:
    return service.handle("test-summary", raw, {"purpose": purpose, "recipe_sha256": sm.recipe_sha256(raw)})


def test_a_per_ticker_window_equals_the_same_summary_computed_independently(governed_db, tmp_path, rules) -> None:
    service = summarizer(governed_db, tmp_path)
    raw = spec(scope=pred("ticker", "IN", "BBCA", "BMRI"))
    answer = ask(service, raw)
    assert answer["status"] == "OK", answer
    days = [r[0] for r in admin(governed_db, f'SELECT DISTINCT date FROM public."{PRICE}" WHERE date <= '
                                             "'2026-08-31' ORDER BY date DESC LIMIT 5")]
    assert answer["period"]["from"] == min(days).isoformat() and answer["period"]["calendar_dates"] == 5
    expected = admin(governed_db, f'''
        SELECT ticker, sum(volume), (array_agg(close ORDER BY date DESC))[1], max(close), count(*)
        FROM public."{PRICE}" WHERE date BETWEEN %s AND %s AND ticker IN ('BBCA', 'BMRI')
        GROUP BY ticker ORDER BY ticker''', (min(days), max(days)))
    got = [(r["ticker"], float(r["volume_sum"]), float(r["last_close"]), float(r["high_close"]), r["rows"])
           for r in answer["rows"]]
    assert got == [(t, float(v), float(c), float(h), n) for t, v, c, h, n in expected]
    assert all(r["days_present"] == 5 for r in answer["rows"])
    assert answer["query_id"].startswith("qry_") and len(answer["query_hash"]) == 64


def test_another_table_and_a_date_range(governed_db, tmp_path, rules) -> None:
    """A case other than the price table: net foreign value per board over a date range (SUM over time and across
    boards when the board is dropped)."""
    service = summarizer(governed_db, tmp_path)
    raw = {**spec(), "source_table": FEATURE_03, "scope": pred("ticker", "EQ", "BBCA"), "group_by": ["ticker"],
           "measures": [{"column": "foreign_net_value", "function": "SUM", "as": "net_foreign"}],
           "period": {"from": "2026-08-01", "to": "2026-08-31"}}
    answer = ask(service, raw, "EVIDENCE")
    assert answer["status"] == "OK", answer
    expected = admin(governed_db, f'SELECT sum(foreign_net_value) FROM public."{FEATURE_03}" WHERE ticker = '
                                  "'BBCA' AND date BETWEEN '2026-08-01' AND '2026-08-31'")[0][0]
    assert float(answer["rows"][0]["net_foreign"]) == float(expected)


def test_refusals_are_explained(governed_db, tmp_path, rules, monkeypatch) -> None:
    service = summarizer(governed_db, tmp_path)
    total = spec(group_by=(), measures=[{"column": "volume", "function": "SUM", "as": "s"}])
    assert ask(service, total)["code"] == "AGGREGATION_NOT_ADDITIVE"
    raw = spec()
    mismatch = service.handle("test-summary", raw, {"purpose": "METRIC", "recipe_sha256": "0" * 64})
    assert mismatch["code"] == "LINEAGE_MISMATCH"
    monkeypatch.setattr(sm, "MAX_ROWS", 3)
    many = ask(service, spec())
    assert (many["status"], many["code"]) == ("REJECTED_ROW_LIMIT", "SUMMARY_TOO_MANY_ROWS")
