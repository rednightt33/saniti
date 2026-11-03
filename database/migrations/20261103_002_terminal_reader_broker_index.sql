-- EXEC-IHSG-FLOW (user go 2026-11-03), ERRORS M343: terminal-publisher reads an index's broker rows from
-- Feature_05_Foreign_Domestic_Broker_Detail_INDEX. Its login reads through terminal_market_reader, which had no SELECT on
-- that table, so the daily run of 2026-11-03 12:00 UTC failed at plan with InsufficientPrivilege. Read only, one table.
BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_market_reader') THEN
    RAISE EXCEPTION 'role terminal_market_reader is missing';
  END IF;
  IF to_regclass('public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX"') IS NULL THEN
    RAISE EXCEPTION 'table Feature_05_Foreign_Domestic_Broker_Detail_INDEX is missing';
  END IF;
END $$;

GRANT SELECT ON public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX" TO terminal_market_reader;

COMMIT;
