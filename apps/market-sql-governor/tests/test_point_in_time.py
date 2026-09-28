"""IP1 Stages D and E on a real PostgreSQL server: the reference-history core of migration 20260927_006 (capture
triggers, bitemporal versions, generated point-in-time validity) under a controlled clock, the catalog contract's
point-in-time metadata, and the EFFECTIVE_DATED restriction choosing the same version as saniti.join."""
from __future__ import annotations

from datetime import date

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("pyarrow.parquet")

from fixture import MIGRATIONS  # noqa: E402
from test_extract import ALL, admin, extraction, extractor, pred, restriction, rows_of, submit  # noqa: E402

MIGRATION = MIGRATIONS / "20260927_006_reference_history_point_in_time.sql"
TICKER = "T001"


def core_sql() -> str:
    """The migration's history core, with now() read from a test clock (production uses the transaction time)."""
    text = MIGRATION.read_text()
    core = text[text.index("-- BEGIN reference history core"):text.index("-- END reference history core")]
    return core.replace("now()", "public.test_clock()")


def clock(db: dict, moment: str) -> None:
    admin(db, "UPDATE public.test_clock_value SET t = %s", (moment,))


@pytest.fixture(scope="module")
def history(governed_db):
    db = governed_db
    admin(db, '''CREATE TABLE public.test_clock_value (t timestamptz NOT NULL);
                 INSERT INTO public.test_clock_value VALUES ('2025-03-03 10:00+07');
                 CREATE FUNCTION public.test_clock() RETURNS timestamptz LANGUAGE sql STABLE
                     AS 'SELECT t FROM public.test_clock_value';''')
    admin(db, f'''UPDATE public."IDX_Stock_Universe" SET "Sector" = 'Mining' WHERE "Ticker" = '{TICKER}' ''')
    with psycopg.connect(db["admin"], autocommit=True) as connection:
        connection.execute(core_sql())  # no parameters: the function bodies contain RAISE ... % placeholders
    admin(db, "SELECT public.capture_stock_universe_history('INITIAL')")
    # the sector move is recorded on 2025-03-10 in the evening: Mining until 03-10, the new sector from 03-11
    clock(db, "2025-03-10 20:00+07")
    admin(db, f'''UPDATE public."IDX_Stock_Universe" SET "Sector" = 'Finance' WHERE "Ticker" = '{TICKER}' ''')
    # catalog: the history table, value_time_basis, availability readable by the Governor, one EFFECTIVE_DATED link
    admin(db, '''
ALTER TABLE public."AI_column_catalog" ADD COLUMN value_time_basis text NOT NULL DEFAULT 'HISTORICAL';
UPDATE public."AI_column_catalog" SET value_time_basis = 'CURRENT_STATE' WHERE table_name = 'IDX_Stock_Universe';
ALTER TABLE public."Table_Catalog" ADD COLUMN observation_date_column text, ADD COLUMN data_available_at_column text,
    ADD COLUMN availability_rule text, ADD COLUMN point_in_time_status text, ADD COLUMN historical_metadata_method text;
INSERT INTO public."Table_Catalog" VALUES
    ('public', 'Price_Stock_Indonesia_IDX', 'date', 'ingestion_time', 'close t, used t+1', 'PARTIAL', 'x'),
    ('public', 'IDX_Stock_Universe_History', 'valid_from', 'available_at', 'pit', 'PARTIAL', 'PROSPECTIVE_CAPTURE');
GRANT SELECT ON public."IDX_Stock_Universe_History" TO market_ai_sql_reader;
INSERT INTO public."AI_table_catalog" (table_name, description, category, grain, primary_key_columns, time_column,
    entity_column, is_active, ai_access_level, coverage_enabled, documentation_status, data_domain, entity_type,
    asset_type, supported_frequencies, time_semantics)
VALUES ('IDX_Stock_Universe_History', 'Synthetic history.', 'REFERENCE', 'version', ARRAY['history_id'], NULL,
        'Ticker', true, 'BOUNDED_READ', false, 'PARTIAL', 'MARKET', 'STOCK', 'IDX_EQUITY', ARRAY['STATIC'], 'history');
INSERT INTO public."AI_column_catalog" (table_name, column_name, ordinal_position, description, data_type,
    semantic_type, nullable, is_primary_key, allowed_aggregations, filter_allowed, group_by_allowed,
    documentation_status)
SELECT 'IDX_Stock_Universe_History', column_name, ordinal_position, 'x', data_type,
       CASE WHEN data_type = 'date' THEN 'TIME' WHEN column_name IN ('history_id', 'Ticker') THEN 'IDENTIFIER'
            ELSE 'DIMENSION' END, is_nullable = 'YES', column_name = 'history_id', ARRAY['COUNT'], true, true, 'PARTIAL'
FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'IDX_Stock_Universe_History'
  AND column_name IN ('history_id', 'Ticker', 'Sector', 'pit_valid_from', 'pit_valid_to');''')
    admin(db, '''GRANT SELECT (table_schema, table_name, observation_date_column, data_available_at_column,
                  availability_rule, point_in_time_status, historical_metadata_method)
                  ON public."Table_Catalog" TO market_ai_sql_reader''')
    relationship = admin(db, '''
INSERT INTO public."AI_catalog_relationships" (left_table, left_columns, right_table, right_columns,
    relationship_type, temporal_rule, safe_output_grain, requires_preaggregation, description, version, is_allowed,
    supported_join_semantics, effective_from_column, effective_to_column)
VALUES ('Price_Stock_Indonesia_IDX', ARRAY['ticker'], 'IDX_Stock_Universe_History', ARRAY['Ticker'], 'MANY_TO_ONE',
        'Point in time', 'date x ticker', false, 'Synthetic.', 'v1', true, ARRAY['EFFECTIVE_DATED'],
        'pit_valid_from', 'pit_valid_to') RETURNING relationship_id''')[0][0]
    admin(db, "ANALYZE")
    yield {"relationship": relationship}
    admin(db, '''
DELETE FROM public."AI_catalog_relationships" WHERE right_table = 'IDX_Stock_Universe_History';
DELETE FROM public."AI_column_catalog" WHERE table_name = 'IDX_Stock_Universe_History';
DELETE FROM public."AI_table_catalog" WHERE table_name = 'IDX_Stock_Universe_History';
REVOKE SELECT (table_schema, table_name, observation_date_column, data_available_at_column, availability_rule,
               point_in_time_status, historical_metadata_method) ON public."Table_Catalog" FROM market_ai_sql_reader;
DELETE FROM public."Table_Catalog" WHERE observation_date_column IS NOT NULL;
ALTER TABLE public."Table_Catalog" DROP COLUMN observation_date_column, DROP COLUMN data_available_at_column,
    DROP COLUMN availability_rule, DROP COLUMN point_in_time_status, DROP COLUMN historical_metadata_method;
ALTER TABLE public."AI_column_catalog" DROP COLUMN value_time_basis;
DROP TRIGGER reference_history_capture ON public."IDX_Stock_Universe";
DROP TRIGGER reference_history_capture ON public."IDX_Broker_Profile";
DROP FUNCTION public.capture_reference_history(), public.capture_stock_universe_history(text),
    public.capture_broker_profile_history(text),
    public.correct_stock_universe_history(text, date, date, jsonb, text, timestamptz, text, text),
    public.correct_broker_profile_history(text, date, date, jsonb, text, timestamptz, text, text),
    public.stock_universe_history_as_known(timestamptz, date), public.broker_profile_history_as_known(timestamptz, date);
DROP TABLE public."IDX_Stock_Universe_History", public."IDX_Broker_Profile_History",
    public."Reference_History_Capture_Log";
DROP FUNCTION public.test_clock(); DROP TABLE public.test_clock_value;''')
    admin(db, f'''UPDATE public."IDX_Stock_Universe" SET "Sector" = 'restored' WHERE "Ticker" = '{TICKER}' ''')


def test_the_capture_keeps_the_superseded_version_and_dates_it_by_recording(governed_db, history) -> None:
    rows = admin(governed_db, f'''SELECT "Sector", valid_from, valid_to, valid_basis, recorded_to IS NULL,
                                         pit_valid_from, pit_valid_to
                                  FROM public."IDX_Stock_Universe_History" WHERE "Ticker" = '{TICKER}'
                                  ORDER BY history_id''')
    mining, closed, finance = rows
    assert mining[:5] == ("Mining", date(2025, 3, 3), None, "FIRST_CAPTURE", False)  # superseded, kept
    assert closed[:5] == ("Mining", date(2025, 3, 3), date(2025, 3, 10), "FIRST_CAPTURE", True)
    assert finance[:5] == ("Finance", date(2025, 3, 10), None, "CHANGE_CAPTURED", True)
    # point in time: first capture used from the next date; the move recorded 03-10 is used from 03-11
    assert (mining[5], mining[6]) == (date(2025, 3, 4), date(2025, 3, 11))
    assert closed[5] >= closed[6]  # the closed copy was recorded 03-10: it applies to no date
    assert (finance[5], finance[6]) == (date(2025, 3, 11), None)


def test_the_contract_carries_point_in_time_metadata(governed_db, tmp_path, history) -> None:
    contract = extractor(governed_db, tmp_path).governor.catalog_contract(
        "t", ["Price_Stock_Indonesia_IDX", "IDX_Stock_Universe_History", "IDX_Stock_Universe"])
    assert contract["point_in_time_metadata"] is True
    rel = next(r for r in contract["relationships"] if r["relationship_id"] == history["relationship"])
    assert rel["history_available_from"] == "2025-03-04"  # the first capture's next date
    assert contract["tables"]["Price_Stock_Indonesia_IDX"]["availability"]["point_in_time_status"] == "PARTIAL"
    assert contract["tables"]["IDX_Stock_Universe"]["availability"] is None  # not documented in this fixture
    assert contract["columns"]["IDX_Stock_Universe"]["Sector"]["value_time_basis"] == "CURRENT_STATE"
    assert contract["columns"]["Price_Stock_Indonesia_IDX"]["close"]["value_time_basis"] == "HISTORICAL"


def test_without_the_availability_grant_the_contract_fails_closed(governed_db, tmp_path, history) -> None:
    admin(governed_db, 'REVOKE SELECT (point_in_time_status) ON public."Table_Catalog" FROM market_ai_sql_reader')
    try:
        contract = extractor(governed_db, tmp_path).governor.catalog_contract("t", ["Price_Stock_Indonesia_IDX"])
        assert "point_in_time_metadata" not in contract
        assert "availability" not in contract["tables"]["Price_Stock_Indonesia_IDX"]
    finally:
        admin(governed_db, 'GRANT SELECT (point_in_time_status) ON public."Table_Catalog" TO market_ai_sql_reader')


def test_the_sector_filter_applies_after_the_version_is_chosen(governed_db, tmp_path, history) -> None:
    ext = extractor(governed_db, tmp_path)
    rule = restriction(history["relationship"], "EFFECTIVE_DATED", "IDX_Stock_Universe_History",
                       pred("Sector", "EQ", "Mining"), left_time="date",
                       effective=("pit_valid_from", "pit_valid_to"))
    rows = rows_of(ext, submit(ext, extraction(restrictions=[rule], window=("2025-03-01", "2025-03-20"))))
    days = sorted(r["date"] for r in rows if r["ticker"] == TICKER)
    assert {r["ticker"] for r in rows} == {TICKER}
    # nothing before the first capture was known; Mining until the move was recorded; never after it
    assert days[0] == date(2025, 3, 4) and days[-1] == date(2025, 3, 10)
    finance = restriction(history["relationship"], "EFFECTIVE_DATED", "IDX_Stock_Universe_History",
                          pred("Sector", "EQ", "Finance"), left_time="date",
                          effective=("pit_valid_from", "pit_valid_to"))
    moved = [r["date"] for r in rows_of(ext, submit(ext, extraction(restrictions=[finance],
                                                                    window=("2025-03-01", "2025-03-20"))))
             if r["ticker"] == TICKER]
    assert min(moved) == date(2025, 3, 11)
