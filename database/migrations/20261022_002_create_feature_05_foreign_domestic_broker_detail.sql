-- EXEC-F05-F06 Fase 2: canonical broker-level daily dataset for Feature 06.
-- Grain: trade_date x ticker x broker x market_board x investor_type, one row per IDX_Broker_Summary row (only
-- combinations that traded). No window. source_balance_gap is internal information (not exposed to the AI): the
-- ticker's buy and sell totals over all brokers differ on that date and board (ERRORS M157).
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public.feature_05_foreign_domestic_broker_detail') IS NOT NULL THEN
        RAISE EXCEPTION 'feature_05_foreign_domestic_broker_detail already exists';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'IDX_Broker_Summary'
                     AND column_name = 'buy_freq') THEN
        RAISE EXCEPTION 'Fase 1 (IDX_Broker_Summary.buy_freq) is required first';
    END IF;
END
$preflight$;

CREATE TABLE public.feature_05_foreign_domestic_broker_detail (
    trade_date date NOT NULL,
    ticker text NOT NULL,
    broker text NOT NULL,
    market_board text NOT NULL CHECK (market_board = ANY (ARRAY['Regular', 'Nego', 'Tunai'])),
    investor_type text NOT NULL CHECK (investor_type = ANY (ARRAY['Foreign', 'Domestic'])),
    buy_value numeric NOT NULL CHECK (buy_value >= 0),
    sell_value numeric NOT NULL CHECK (sell_value >= 0),
    net_value numeric NOT NULL,
    buy_lots numeric NOT NULL CHECK (buy_lots >= 0),
    sell_lots numeric NOT NULL CHECK (sell_lots >= 0),
    net_lots numeric NOT NULL,
    buy_freq bigint CHECK (buy_freq IS NULL OR buy_freq >= 0),
    sell_freq bigint CHECK (sell_freq IS NULL OR sell_freq >= 0),
    source_balance_gap boolean NOT NULL,
    calculated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    CONSTRAINT feature_05_foreign_domestic_broker_detail_pkey
        PRIMARY KEY (ticker, trade_date, broker, investor_type, market_board),
    CONSTRAINT feature_05_net_value_check CHECK (net_value = buy_value - sell_value),
    CONSTRAINT feature_05_net_lots_check CHECK (net_lots = buy_lots - sell_lots)
);

COMMENT ON TABLE public.feature_05_foreign_domestic_broker_detail IS
    'EXEC-F05-F06 Feature 05: one row per IDX_Broker_Summary row (date, ticker, broker, investor type, board) with buy/sell value, lots and frequency; the only source of Feature 06. Refreshed by refresh_feature_05 for a date range and ticker list.';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.trade_date IS 'IDX_Broker_Summary "Date": exchange trading date.';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.ticker IS 'IDX_Broker_Summary "Symbol", including warrants and rights.';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.broker IS 'IDX_Broker_Summary "Broker": two-character broker code.';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.market_board IS 'IDX_Broker_Summary "Market Board": Regular, Nego or Tunai; boards never mix.';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.investor_type IS 'IDX_Broker_Summary "Investor Type": source investor identity Foreign or Domestic, not broker domicile.';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.buy_value IS 'Gross buy value in IDR (IDX_Broker_Summary "Buy Value").';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.sell_value IS 'Gross sell value in IDR (IDX_Broker_Summary "Sell Value").';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.net_value IS 'buy_value - sell_value in IDR; positive is net buying.';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.buy_lots IS 'Buy lots (1 lot = 100 shares; odd lots appear as fractions).';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.sell_lots IS 'Sell lots (1 lot = 100 shares; odd lots appear as fractions).';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.net_lots IS 'buy_lots - sell_lots.';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.buy_freq IS 'Number of buy transactions (IDX_Broker_Summary.buy_freq); NULL when the source has no frequency (non-4-letter symbols).';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.sell_freq IS 'Number of sell transactions (IDX_Broker_Summary.sell_freq); NULL when the source has no frequency.';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.source_balance_gap IS 'Internal: true when, for this date, ticker and board, total Buy Value over all brokers differs from total Sell Value in IDX_Broker_Summary (brokers missing from the source, ERRORS M157). Not exposed to the AI.';
COMMENT ON COLUMN public.feature_05_foreign_domestic_broker_detail.calculated_at IS 'Statement timestamp when the row was written; not source time.';

CREATE FUNCTION public.refresh_feature_05(p_from date, p_to date, p_tickers text[] DEFAULT NULL)
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

    DELETE FROM public.feature_05_foreign_domestic_broker_detail AS t
    WHERE t.trade_date >= p_from AND t.trade_date < p_to
      AND (p_tickers IS NULL OR t.ticker = ANY (p_tickers));

    INSERT INTO public.feature_05_foreign_domestic_broker_detail (
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
$function$;

COMMENT ON FUNCTION public.refresh_feature_05(date, date, text[]) IS
    'EXEC-F05-F06: replace Feature 05 rows for p_from <= trade_date < p_to and the given tickers (all when NULL) from IDX_Broker_Summary; call after sync_broker_summary_freq for the same dates.';

COMMIT;
