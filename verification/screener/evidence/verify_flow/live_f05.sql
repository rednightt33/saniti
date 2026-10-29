CREATE OR REPLACE FUNCTION public.refresh_feature_05(p_from date, p_to date, p_tickers text[] DEFAULT NULL::text[])
 RETURNS bigint
 LANGUAGE plpgsql
AS $function$
-- Replaces Feature 05 rows for p_from <= trade_date < p_to (and the given tickers, all when NULL) from
-- IDX_Broker_Summary in one transaction. Daily rows only: a refresh never reads outside the given dates.
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
      AND (p_tickers IS NULL OR t.ticker = ANY (p_tickers));

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
    WINDOW w AS (PARTITION BY b."Date", b."Symbol", b."Market Board")
    ORDER BY b."Symbol", b."Date", b."Broker", b."Investor Type", b."Market Board";  -- ticker-ordered heap for Feature 06 reads
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END
$function$
