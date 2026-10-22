-- EXEC-F05-F06 Fase 1: buy_freq and sell_freq on IDX_Broker_Summary from IDX_Broker_Summary_Freq.
-- Both tables share the five-column natural key (verified 1:1 over 130 months, 2026-10-21), so the copy
-- cannot fan out. Rows without a Freq row (non-4-letter symbols) keep NULL; missing is never zero.
-- The columns are added without a default (metadata only); the backfill runs per month through
-- sync_broker_summary_freq, and the CHECK is validated after the backfill.
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."IDX_Broker_Summary"') IS NULL
       OR to_regclass('public."IDX_Broker_Summary_Freq"') IS NULL THEN
        RAISE EXCEPTION 'IDX_Broker_Summary and IDX_Broker_Summary_Freq are required';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'IDX_Broker_Summary'
                 AND column_name IN ('buy_freq', 'sell_freq')) THEN
        RAISE EXCEPTION 'buy_freq/sell_freq already exist on IDX_Broker_Summary';
    END IF;
END
$preflight$;

ALTER TABLE public."IDX_Broker_Summary"
    ADD COLUMN buy_freq bigint,
    ADD COLUMN sell_freq bigint;

ALTER TABLE public."IDX_Broker_Summary"
    ADD CONSTRAINT "IDX_Broker_Summary_freq_nonnegative_check"
    CHECK ((buy_freq IS NULL OR buy_freq >= 0) AND (sell_freq IS NULL OR sell_freq >= 0)) NOT VALID;

COMMENT ON COLUMN public."IDX_Broker_Summary".buy_freq IS
    'Number of buy transactions for the key combination, copied from IDX_Broker_Summary_Freq on the same Date, Symbol, Broker, Investor Type and Market Board; NULL when Freq has no row (non-4-letter symbols, or not yet synced).';
COMMENT ON COLUMN public."IDX_Broker_Summary".sell_freq IS
    'Number of sell transactions for the key combination, copied from IDX_Broker_Summary_Freq on the same key; NULL when Freq has no row.';

CREATE FUNCTION public.sync_broker_summary_freq(p_from date, p_to date)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
-- Copies buy_freq/sell_freq from IDX_Broker_Summary_Freq for p_from <= Date < p_to. Idempotent: rows already equal
-- are not written; a key without a Freq row is set back to NULL. Never touches value or lot columns.
DECLARE
    v_set bigint;
    v_cleared bigint;
BEGIN
    IF p_from IS NULL OR p_to IS NULL OR p_to <= p_from THEN
        RAISE EXCEPTION 'sync_broker_summary_freq needs p_from < p_to';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('sync_broker_summary_freq', 0));

    UPDATE public."IDX_Broker_Summary" AS b
    SET buy_freq = f.buy_freq, sell_freq = f.sell_freq
    FROM public."IDX_Broker_Summary_Freq" AS f
    WHERE b."Date" >= p_from AND b."Date" < p_to
      AND f.trade_date >= p_from AND f.trade_date < p_to
      AND f.trade_date = b."Date" AND f.symbol = b."Symbol" AND f.broker = b."Broker"
      AND f.investor_type::text = b."Investor Type" AND f.market_board::text = b."Market Board"
      AND (b.buy_freq IS DISTINCT FROM f.buy_freq OR b.sell_freq IS DISTINCT FROM f.sell_freq);
    GET DIAGNOSTICS v_set = ROW_COUNT;

    UPDATE public."IDX_Broker_Summary" AS b
    SET buy_freq = NULL, sell_freq = NULL
    WHERE b."Date" >= p_from AND b."Date" < p_to
      AND (b.buy_freq IS NOT NULL OR b.sell_freq IS NOT NULL)
      AND NOT EXISTS (
          SELECT 1 FROM public."IDX_Broker_Summary_Freq" AS f
          WHERE f.trade_date = b."Date" AND f.symbol = b."Symbol" AND f.broker = b."Broker"
            AND f.investor_type::text = b."Investor Type" AND f.market_board::text = b."Market Board");
    GET DIAGNOSTICS v_cleared = ROW_COUNT;

    RETURN v_set + v_cleared;
END
$function$;

COMMENT ON FUNCTION public.sync_broker_summary_freq(date, date) IS
    'EXEC-F05-F06: copy buy_freq/sell_freq from IDX_Broker_Summary_Freq into IDX_Broker_Summary for p_from <= Date < p_to on the five-column key; idempotent; call after a Broker Summary or Freq load.';

COMMIT;
