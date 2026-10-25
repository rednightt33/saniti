-- EXEC-INDEX-1 B (user 2026-10-25: "Hapus saja. IDX_Broker_Summary Agustus keatas memang lagi di download ulang
-- termasuk untuk data freq"; target of the new frequency load "Belum tahu"): empty IDX_Broker_Summary_Freq and keep its
-- structure (the parent and its 12 yearly partitions stay, so a loader that writes there does not fail).
-- Read-only check 2026-10-25 (ERRORS M215): last read 2026-10-22 by sync_broker_summary_freq only; no view, FK, AI
-- catalog row or AI grant; its values are already in IDX_Broker_Summary.buy_freq/sell_freq (dates to 2026-08-31).
--
-- sync_broker_summary_freq set buy_freq/sell_freq to NULL for every key without a Freq row. With Freq empty, a later
-- call would have erased the copied frequency (and refresh_feature_05 would carry the NULLs on). It now refuses a
-- range in which a Broker Summary date has no Freq row at all; within a date that has Freq rows, a key without one
-- is still NULL (non-4-letter symbols), as before.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."IDX_Broker_Summary_Freq"') IS NULL THEN
        RAISE EXCEPTION 'IDX_Broker_Summary_Freq is missing';
    END IF;
    IF (SELECT count(*) FROM pg_inherits WHERE inhparent = 'public."IDX_Broker_Summary_Freq"'::regclass) <> 12 THEN
        RAISE EXCEPTION 'IDX_Broker_Summary_Freq does not have the 12 partitions read on 2026-10-25: reconcile first';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_stat_activity WHERE pid <> pg_backend_pid()
               AND query ILIKE '%broker_summary_freq%' AND state <> 'idle') THEN
        RAISE EXCEPTION 'a session is using IDX_Broker_Summary_Freq now: retry later';
    END IF;
END
$preflight$;

CREATE OR REPLACE FUNCTION public.sync_broker_summary_freq(p_from date, p_to date)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
-- Copies buy_freq/sell_freq from IDX_Broker_Summary_Freq for p_from <= Date < p_to. Idempotent: rows already equal
-- are not written; within a date that has Freq rows, a key without one is set back to NULL. A Broker Summary date
-- without any Freq row is refused (Freq not loaded for it), so frequency is never erased by a missing load.
DECLARE
    v_set bigint;
    v_cleared bigint;
    v_missing date[];
BEGIN
    IF p_from IS NULL OR p_to IS NULL OR p_to <= p_from THEN
        RAISE EXCEPTION 'sync_broker_summary_freq needs p_from < p_to';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('sync_broker_summary_freq', 0));

    SELECT array_agg(d ORDER BY d) INTO v_missing
    FROM (SELECT DISTINCT b."Date" AS d FROM public."IDX_Broker_Summary" AS b
          WHERE b."Date" >= p_from AND b."Date" < p_to) AS dates
    WHERE NOT EXISTS (SELECT 1 FROM public."IDX_Broker_Summary_Freq" AS f WHERE f.trade_date = dates.d);
    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'IDX_Broker_Summary_Freq has no rows for % Broker Summary date(s), first %: load Freq for these dates or narrow the range',
            cardinality(v_missing), v_missing[1:5];
    END IF;

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
    'EXEC-F05-F06, guarded by EXEC-INDEX-1: copy buy_freq/sell_freq from IDX_Broker_Summary_Freq into IDX_Broker_Summary for p_from <= Date < p_to on the five-column key; idempotent; refuses a range in which a Broker Summary date has no Freq row; call after a Broker Summary and Freq load.';

TRUNCATE public."IDX_Broker_Summary_Freq";

COMMENT ON TABLE public."IDX_Broker_Summary_Freq" IS
    'Staging for Stockbit buy/sell transaction counts per Date, Symbol, Broker, Investor Type and Market Board, copied into IDX_Broker_Summary.buy_freq/sell_freq by sync_broker_summary_freq. Emptied 2026-10-25 (EXEC-INDEX-1, values already copied up to 2026-08-31); reload it for new dates before syncing.';

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM public."IDX_Broker_Summary_Freq") THEN
        RAISE EXCEPTION 'IDX_Broker_Summary_Freq still holds rows';
    END IF;
    IF (SELECT count(*) FROM pg_inherits WHERE inhparent = 'public."IDX_Broker_Summary_Freq"'::regclass) <> 12 THEN
        RAISE EXCEPTION 'a partition was lost';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public."IDX_Broker_Summary" WHERE "Date" = DATE '2026-08-31' AND buy_freq IS NOT NULL) THEN
        RAISE EXCEPTION 'copied frequency in IDX_Broker_Summary is missing';
    END IF;
END
$verify$;
COMMIT;
