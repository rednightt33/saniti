-- EXEC-LOADER-M217 correction (go EXEC-GO-1029, 2026-10-29): the history backfill (job of 2026-10-29, 2,601 dates)
-- flagged 22 dates for a low stock row count and 5 for a low stock count. Checked against an independent source
-- (pgweb, read-only): 2024-06-13, 2025-07-04 and 2025-10-16 have the same symbol coverage as their neighbours and the
-- same ratio of broker-summary lots to exchange volume (1.33 vs 1.29/1.39; 1.25 vs 1.13/1.14; 1.04 vs 1.04/1.10), so
-- those loads were complete: the row count measures how many broker x stock pairs traded (activity), not whether the
-- load is whole. The row check is dropped (stock_rows stays recorded); the stock and broker checks keep 5 x MAD with a
-- floor of 10% of the median (the 2016 stock flags were 6-8% below, quiet days). Still caught: a missing broker or
-- stock group, missing frequency, vanished non-stock symbols. Not caught: rows cut inside symbols that still appear
-- (a page limit); a volume reconciliation with the price table would cover it (FUTURE_PLAN). Forward-only: 001 is
-- applied and frozen; the backfill job is run again after this file.
BEGIN;

CREATE OR REPLACE FUNCTION public.remark_broker_summary_date(p_date date) RETURNS text
LANGUAGE plpgsql AS $fn$
DECLARE
    s record;
    b record;
    found jsonb := '[]'::jsonb;
    parts text[] := ARRAY[]::text[];
    stock_ok boolean := true;
    other_ok boolean := true;
    v_status text;
    v_remark text;
BEGIN
    SELECT count(*) FILTER (WHERE "Symbol" ~ '^[A-Z]{4}$') AS stock_rows,
           count(DISTINCT "Broker") FILTER (WHERE "Symbol" ~ '^[A-Z]{4}$') AS stock_brokers,
           count(DISTINCT "Symbol") FILTER (WHERE "Symbol" ~ '^[A-Z]{4}$') AS stock_symbols,
           coalesce(avg((buy_freq IS NOT NULL AND sell_freq IS NOT NULL)::int)
                    FILTER (WHERE "Symbol" ~ '^[A-Z]{4}$'), 0) AS stock_freq_share,
           count(DISTINCT "Symbol") FILTER (WHERE "Symbol" !~ '^[A-Z]{4}$') AS other_symbols,
           count(*) FILTER (WHERE "Symbol" !~ '^[A-Z]{4}$') AS other_rows,
           count(*) AS all_rows
      INTO s FROM public."IDX_Broker_Summary" WHERE "Date" = p_date;
    IF s.all_rows = 0 THEN
        DELETE FROM public.broker_summary_date_quality WHERE trade_date = p_date;
        RETURN NULL;
    END IF;

    WITH st AS (SELECT * FROM public.broker_summary_date_quality
                 WHERE trade_date < p_date AND stock_complete ORDER BY trade_date DESC LIMIT 20),
         ot AS (SELECT * FROM public.broker_summary_date_quality
                 WHERE trade_date < p_date AND other_complete ORDER BY trade_date DESC LIMIT 20),
         med AS (SELECT (SELECT count(*) FROM st) AS n_stock, (SELECT count(*) FROM ot) AS n_other,
                        (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY stock_rows) FROM st) AS rows_med,
                        (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY stock_brokers) FROM st) AS brokers_med,
                        (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY stock_symbols) FROM st) AS symbols_med,
                        (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY stock_freq_share) FROM st) AS freq_med,
                        (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY other_symbols) FROM ot) AS other_med)
    SELECT med.*,
           (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(stock_rows - med.rows_med)) FROM st) AS rows_mad,
           (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(stock_brokers - med.brokers_med)) FROM st) AS brokers_mad,
           (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(stock_symbols - med.symbols_med)) FROM st) AS symbols_mad,
           (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(stock_freq_share - med.freq_med)) FROM st) AS freq_mad
      INTO b FROM med;

    IF b.n_stock >= 5 THEN
        IF s.stock_brokers < b.brokers_med - greatest(5 * b.brokers_mad, 0.10 * b.brokers_med) THEN
            found := found || jsonb_build_object('check', 'stock_brokers', 'value', s.stock_brokers, 'usual', round(b.brokers_med));
            parts := parts || format('broker %s (biasanya %s)', s.stock_brokers, round(b.brokers_med));
            stock_ok := false;
        END IF;
        IF s.stock_symbols < b.symbols_med - greatest(5 * b.symbols_mad, 0.10 * b.symbols_med) THEN
            found := found || jsonb_build_object('check', 'stock_symbols', 'value', s.stock_symbols, 'usual', round(b.symbols_med));
            parts := parts || format('saham %s (biasanya ±%s)', s.stock_symbols, round(b.symbols_med));
            stock_ok := false;
        END IF;
        IF s.stock_freq_share < b.freq_med - greatest(5 * b.freq_mad, 0.001) THEN
            found := found || jsonb_build_object('check', 'stock_freq_share', 'value', round(s.stock_freq_share, 4),
                                                 'usual', round(b.freq_med::numeric, 4));
            parts := parts || format('frekuensi terisi pada %s%% baris saham (biasanya %s%%)',
                                     round(100 * s.stock_freq_share, 1), round(100 * b.freq_med::numeric, 1));
            stock_ok := false;
        END IF;
    END IF;
    IF b.n_other >= 5 AND b.other_med > 0 AND s.other_symbols = 0 THEN
        found := found || jsonb_build_object('check', 'other_symbols', 'value', 0, 'usual', round(b.other_med));
        parts := parts || format('tidak ada simbol non-saham (waran/right; biasanya ±%s); importer stockbit-updater hanya '
                                 'memuat saham (ERRORS M218, keputusan user terbuka)', round(b.other_med));
        other_ok := false;
    END IF;

    v_status := CASE WHEN jsonb_array_length(found) > 0 THEN 'INCOMPLETE'
                     WHEN b.n_stock < 5 THEN 'UNCHECKED' ELSE 'COMPLETE' END;
    v_remark := CASE v_status
        WHEN 'INCOMPLETE' THEN 'Muatan tidak lengkap: ' || array_to_string(parts, '; ')
             || CASE WHEN NOT stock_ok THEN '. Muat ulang tanggal ini lewat stockbit-updater (UPDATE_TABLE.md bagian 0).'
                     ELSE '.' END
        WHEN 'UNCHECKED' THEN format('Belum bisa dibandingkan: baru %s tanggal lengkap sebelumnya (perlu 5).', b.n_stock)
        END;

    INSERT INTO public.broker_summary_date_quality AS q (trade_date, stock_rows, stock_brokers, stock_symbols,
        stock_freq_share, other_symbols, other_rows, stock_complete, other_complete, status, findings, baseline,
        remark, checked_at, checked_by)
    VALUES (p_date, s.stock_rows, s.stock_brokers, s.stock_symbols, round(s.stock_freq_share, 6), s.other_symbols,
            s.other_rows, stock_ok, other_ok, v_status, found,
            jsonb_build_object('stock_dates', b.n_stock, 'other_dates', b.n_other, 'rows', b.rows_med,
                               'brokers', b.brokers_med, 'symbols', b.symbols_med, 'freq_share', b.freq_med,
                               'other_symbols', b.other_med),
            v_remark, statement_timestamp(), nullif(current_setting('application_name', true), ''))
    ON CONFLICT (trade_date) DO UPDATE SET stock_rows = EXCLUDED.stock_rows, stock_brokers = EXCLUDED.stock_brokers,
        stock_symbols = EXCLUDED.stock_symbols, stock_freq_share = EXCLUDED.stock_freq_share,
        other_symbols = EXCLUDED.other_symbols, other_rows = EXCLUDED.other_rows,
        stock_complete = EXCLUDED.stock_complete, other_complete = EXCLUDED.other_complete, status = EXCLUDED.status,
        findings = EXCLUDED.findings, baseline = EXCLUDED.baseline, remark = EXCLUDED.remark,
        checked_at = EXCLUDED.checked_at, checked_by = EXCLUDED.checked_by;
    RETURN v_status;
END
$fn$;

COMMIT;
