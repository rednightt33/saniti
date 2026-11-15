-- EXEC-INDEX-GROUP-HISTORY stage 2, migration B (user 2026-11-15: "Harga bisa disimpan di price stock Indonesia IDX saja.
-- Karena di sana juga sudah ada IHSG", "2024 saja, go mulai tahap 1-2"; PLAN.md INDEX-GROUP-HISTORY).
--
-- What: the 43 priced entities of Feature_Index_Entity (32 Stockbit indexes, 11 IDX sector indexes) become
-- IDX_Stock_Universe rows of "Security Type" index, like IHSG, with their TradingView symbol (checked 2026-11-15: every
-- one answers with daily history; the five with another TradingView name are listed below).
-- Derived, not listed: the rows are the Feature_Index_Entity entities with has_price that are not in the universe yet;
-- every other column is IHSG's (Region, Country, Exchange, the "Not applicable"/"Undefined" values).
--
-- APPLY ONLY AFTER (runbook, EXEC.md EXEC-INDEX-GROUP-HISTORY):
-- - migration A (20261115_001) is applied (checked below);
-- - the stage 1 intraday code (apps/idx-price-cron/intraday_update.py intraday_indexes) is deployed on idx-intraday-cron:
--   the old code would load intraday bars of all 43 at its next run (checked by the runbook, not by SQL);
-- - right before the stage 3 price backfill.
-- Effects once applied, by design: the daily and recovery price crons fetch the 43 (their last 5 sessions per run, no
-- volume for an index: validate_idx_optional_volume); the Feature 01/04 stock queues skip them (is_universe_index); the
-- Screener keeps only stocks; terminal-publisher lists them (data kind index) with whatever prices exist; the history
-- capture (reference_history_capture) records 43 new versions. ai-data-coverage would expect their broker features from
-- 2016 until its stage 7 change: a known, temporary misstatement of coverage.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_Index_Entity"') IS NULL THEN
        RAISE EXCEPTION 'migration 20261115_001 (Feature_Index_Entity) is not applied: apply it first';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Index_Entity" WHERE has_price AND ticker <> 'IHSG') <> 43 THEN
        RAISE EXCEPTION 'expected 43 priced entities besides IHSG in Feature_Index_Entity';
    END IF;
    IF EXISTS (SELECT 1 FROM public."IDX_Stock_Universe" u JOIN public."Feature_Index_Entity" e ON e.ticker = u."Ticker"
                WHERE e.ticker <> 'IHSG') THEN
        RAISE EXCEPTION 'a Feature_Index_Entity ticker is already an IDX_Stock_Universe row: reconcile before applying';
    END IF;
    IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'IDX_Stock_Universe') <> 17
       OR NOT public.is_universe_index('IHSG') THEN
        RAISE EXCEPTION 'IDX_Stock_Universe differs from the 17 columns with IHSG read on dev 2026-11-15: reconcile first';
    END IF;
END $preflight$;

-- TradingView's name where it is not the ticker (search and daily history checked 2026-11-15)
WITH tv(ticker, symbol) AS (VALUES ('BISNIS27', 'BISNIS_27'), ('SRIKEHATI', 'SRI_KEHATI'), ('IDXSMCLIQ', 'IDXSMC_LIQ'),
                                   ('IDXSMCCOM', 'IDXSMC_COM'), ('IGRADE', 'I_GRADE')),
     new AS (SELECT e.ticker, e.name, 'IDX:' || coalesce(tv.symbol, e.ticker) AS tv_symbol
               FROM public."Feature_Index_Entity" e LEFT JOIN tv ON tv.ticker = e.ticker
              WHERE e.has_price AND NOT EXISTS (SELECT 1 FROM public."IDX_Stock_Universe" u WHERE u."Ticker" = e.ticker))
INSERT INTO public."IDX_Stock_Universe" ("Region", "Country", "Company Name", "Ticker", "Exchange", "TradingView Symbol",
       "TradingView URL", "Security Type", "Type Specs", "Is Common Stock", "TradingView Country", "Currency",
       "Fundamental Currency", "ISIN", "Sector", "Industry", price_feed_daily)
SELECT i."Region", i."Country", n.name, n.ticker, i."Exchange", n.tv_symbol,
       'https://www.tradingview.com/symbols/' || replace(n.tv_symbol, ':', '-') || '/', 'index', i."Type Specs",
       i."Is Common Stock", i."TradingView Country", i."Currency", i."Fundamental Currency", i."ISIN", i."Sector",
       i."Industry", i.price_feed_daily
  FROM new n CROSS JOIN (SELECT * FROM public."IDX_Stock_Universe" WHERE "Ticker" = 'IHSG') i;

DO $check$ DECLARE n int; BEGIN
    SELECT count(*) INTO n FROM public."IDX_Stock_Universe" WHERE "Security Type" = 'index';
    IF n <> 44 THEN RAISE EXCEPTION 'expected 44 universe indexes (IHSG and 43), found %', n; END IF;
    SELECT count(*) INTO n FROM public."Feature_Index_Entity" e WHERE e.has_price AND NOT public.is_universe_index(e.ticker);
    IF n > 0 THEN RAISE EXCEPTION '% priced entities are not universe indexes', n; END IF;
    SELECT count(*) INTO n FROM public."IDX_Stock_Universe" WHERE "Security Type" = 'index' AND "TradingView Symbol" !~ '^IDX:[A-Z0-9_]+$';
    IF n > 0 THEN RAISE EXCEPTION '% universe indexes have a malformed TradingView symbol', n; END IF;
END $check$;

COMMIT;

-- Rollback (only with the user's go; first the INDEX feature rows and prices of these tickers, if any were written):
-- BEGIN;
-- DELETE FROM public."IDX_Stock_Universe" u USING public."Feature_Index_Entity" e
--  WHERE e.ticker = u."Ticker" AND e.has_price AND e.ticker <> 'IHSG';
-- COMMIT;
