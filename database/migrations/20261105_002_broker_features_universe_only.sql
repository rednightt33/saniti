-- EXEC-UNIVERSE-BROKER S2 (user go 2026-11-05: "S2 P2 P3 bisa dijalankan"; decision the same day: "fitur-fitur ini
-- dihitung hanya untuk saham-saham yang ada di IDX Universe", old rows kept, codes outside the universe not computed
-- any more).
-- refresh_feature_05 writes only the tickers of IDX_Stock_Universe, read at run time (no list in code): a ticker added
-- to the universe is computed from its next refresh on, a ticker outside it is not. Its delete touches only universe
-- tickers, so rows already stored for codes outside the universe (3,058 codes not four letters up to 2026-08-31, 225
-- four-letter codes; F06 count 2026-11-05) stay as they are. Feature 02, 03 and 06 are refreshed per ticker or date
-- from Feature 05 and follow it without a change. The IHSG _INDEX tables keep reading every symbol of
-- IDX_Broker_Summary (scripts/backfill_index_features.py).
-- Rollback: re-create refresh_feature_05 from 20261022_005_rename_feature_05_06_and_date_index.sql.
BEGIN;
SET LOCAL lock_timeout = '10s';

CREATE OR REPLACE FUNCTION public.refresh_feature_05(p_from date, p_to date, p_tickers text[] DEFAULT NULL)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
-- Replaces Feature 05 rows for p_from <= trade_date < p_to (and the given tickers, all when NULL) from
-- IDX_Broker_Summary in one transaction, for the tickers of IDX_Stock_Universe only (EXEC-UNIVERSE-BROKER S2).
-- Rows of tickers outside the universe are neither written nor deleted. Daily rows only: a refresh never reads
-- outside the given dates.
DECLARE
    v_rows bigint;
BEGIN
    IF p_from IS NULL OR p_to IS NULL OR p_to <= p_from THEN
        RAISE EXCEPTION 'refresh_feature_05 needs p_from < p_to';
    END IF;
    IF p_tickers IS NOT NULL AND cardinality(p_tickers) = 0 THEN
        RETURN 0;
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('refresh_feature_05', 0));

    DELETE FROM public."Feature_05_Foreign_Domestic_Broker_Detail" AS t
    WHERE t.trade_date >= p_from AND t.trade_date < p_to
      AND (p_tickers IS NULL OR t.ticker = ANY (p_tickers))
      AND t.ticker IN (SELECT u."Ticker" FROM public."IDX_Stock_Universe" AS u);

    INSERT INTO public."Feature_05_Foreign_Domestic_Broker_Detail" (
        trade_date, ticker, broker, market_board, investor_type,
        buy_value, sell_value, net_value, buy_lots, sell_lots, net_lots,
        buy_freq, sell_freq, source_balance_gap)
    SELECT b."Date", b."Symbol", b."Broker", b."Market Board", b."Investor Type",
           b."Buy Value", b."Sell Value", b."Buy Value" - b."Sell Value",
           b."Buy Lots", b."Sell Lots", b."Buy Lots" - b."Sell Lots",
           b.buy_freq, b.sell_freq,
           sum(b."Buy Value") OVER w <> sum(b."Sell Value") OVER w
    FROM public."IDX_Broker_Summary" AS b
    WHERE b."Date" >= p_from AND b."Date" < p_to
      AND (p_tickers IS NULL OR b."Symbol" = ANY (p_tickers))
      AND b."Symbol" IN (SELECT u."Ticker" FROM public."IDX_Stock_Universe" AS u)
    WINDOW w AS (PARTITION BY b."Date", b."Symbol", b."Market Board")
    ORDER BY b."Symbol", b."Date", b."Broker", b."Investor Type", b."Market Board";  -- ticker-ordered heap for Feature 06 reads
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END
$function$;

COMMENT ON FUNCTION public.refresh_feature_05(date, date, text[]) IS
 'EXEC-UNIVERSE-BROKER S2 (2026-11-05): replaces Feature 05 rows of a date range from IDX_Broker_Summary for the tickers of IDX_Stock_Universe only; rows of other codes are kept as stored and not computed any more.';

UPDATE public."Table_Catalog"
SET update_rule = concat_ws(' ', update_rule, 'From 2026-11-05 (EXEC-UNIVERSE-BROKER S2) only tickers of IDX_Stock_Universe are computed; rows already stored for codes outside the universe (codes not four letters up to 2026-08-31, four-letter codes outside the universe) are kept and no longer refreshed.')
WHERE table_schema = 'public'
  AND table_name IN ('Feature_05_Foreign_Domestic_Broker_Detail', 'Feature_02_Broker_Rolling',
                     'Feature_03_Stock_Broker_Daily', 'Feature_06_Foreign_Domestic')
  AND coalesce(update_rule, '') NOT LIKE '%EXEC-UNIVERSE-BROKER S2%';

COMMIT;
