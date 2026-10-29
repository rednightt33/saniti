-- EXEC-LOADER-M217 (user 2026-10-29: "exec217, database tidak menolak muatan yang tidak lengkap, tapi setiap muatan yang
-- tidak lengkap harus di-remark"; "M217 tidak perlu AI menyebut remark"; go EXEC-GO-1029): every write to
-- IDX_Broker_Summary, by any loader, leaves one quality row per trade date: COMPLETE, INCOMPLETE with a plain remark,
-- or UNCHECKED (too few earlier dates to compare). Nothing is refused and no data row is changed.
--
-- Evidence read 2026-10-29 (pgweb, read-only): the stockbit-updater importer loads four-letter symbols only
-- (apps/stockbit-updater/broker_import.py:259-283); a sample date per year 2016-2026 has frequency on 100% of the stock
-- rows and on none of the other symbols (warrants, rights: the source has none); daily 23,002-27,805 rows, 89 brokers
-- since 2024, 860-876 stocks; other symbols 17-428 per sampled date before 2026-09-01 and none since (ERRORS M218).
-- So the checks are on the stock group (the importer's scope) plus one check that the other symbols vanished.
--
-- Baselines are derived, not typed: the median and the median absolute deviation (MAD) of the 20 earlier dates whose
-- same check passed. A value is short when it is below median - max(5 x MAD, 5% of the median) for counts, or below
-- median - max(5 x MAD, 0.001) for the frequency share; fewer than 5 earlier dates leaves the date UNCHECKED.
-- Disk cost (Part A item 25): one row per trade date, about 2,600 rows; a derived view would rescan ~25,000 rows per
-- date on every read, so the small table is stored.
BEGIN;

CREATE TABLE public.broker_summary_date_quality (
    trade_date date PRIMARY KEY,
    stock_rows integer NOT NULL,
    stock_brokers integer NOT NULL,
    stock_symbols integer NOT NULL,
    stock_freq_share numeric NOT NULL CHECK (stock_freq_share BETWEEN 0 AND 1),
    other_symbols integer NOT NULL,
    other_rows integer NOT NULL,
    stock_complete boolean NOT NULL,
    other_complete boolean NOT NULL,
    status text NOT NULL CHECK (status IN ('COMPLETE', 'INCOMPLETE', 'UNCHECKED')),
    findings jsonb NOT NULL DEFAULT '[]'::jsonb,
    baseline jsonb,
    remark text,
    checked_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    checked_by text
);
COMMENT ON TABLE public.broker_summary_date_quality IS
 'EXEC-LOADER-M217: completeness of each IDX_Broker_Summary trade date after every write (trigger), compared with the 20 earlier dates whose check passed; remark in plain Indonesian. Loads are never refused.';

CREATE FUNCTION public.remark_broker_summary_date(p_date date) RETURNS text
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
        IF s.stock_rows < b.rows_med - greatest(5 * b.rows_mad, 0.05 * b.rows_med) THEN
            found := found || jsonb_build_object('check', 'stock_rows', 'value', s.stock_rows, 'usual', round(b.rows_med));
            parts := parts || format('baris saham %s (biasanya ±%s)', s.stock_rows, round(b.rows_med));
            stock_ok := false;
        END IF;
        IF s.stock_brokers < b.brokers_med - greatest(5 * b.brokers_mad, 0.05 * b.brokers_med) THEN
            found := found || jsonb_build_object('check', 'stock_brokers', 'value', s.stock_brokers, 'usual', round(b.brokers_med));
            parts := parts || format('broker %s (biasanya %s)', s.stock_brokers, round(b.brokers_med));
            stock_ok := false;
        END IF;
        IF s.stock_symbols < b.symbols_med - greatest(5 * b.symbols_mad, 0.05 * b.symbols_med) THEN
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
COMMENT ON FUNCTION public.remark_broker_summary_date(date) IS
 'EXEC-LOADER-M217: recomputes broker_summary_date_quality for one trade date (called by the IDX_Broker_Summary triggers and by the backfill); returns the status, NULL when the date has no rows.';

CREATE FUNCTION public.broker_summary_remark_new() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE d date;
BEGIN
    FOR d IN SELECT DISTINCT "Date" FROM changed_rows ORDER BY 1 LOOP
        PERFORM public.remark_broker_summary_date(d);
    END LOOP;
    RETURN NULL;
END
$fn$;

CREATE TRIGGER idx_broker_summary_remark_insert AFTER INSERT ON public."IDX_Broker_Summary"
    REFERENCING NEW TABLE AS changed_rows FOR EACH STATEMENT EXECUTE FUNCTION public.broker_summary_remark_new();
CREATE TRIGGER idx_broker_summary_remark_update AFTER UPDATE ON public."IDX_Broker_Summary"
    REFERENCING NEW TABLE AS changed_rows FOR EACH STATEMENT EXECUTE FUNCTION public.broker_summary_remark_new();
CREATE TRIGGER idx_broker_summary_remark_delete AFTER DELETE ON public."IDX_Broker_Summary"
    REFERENCING OLD TABLE AS changed_rows FOR EACH STATEMENT EXECUTE FUNCTION public.broker_summary_remark_new();

DO $grant$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        GRANT SELECT ON public.broker_summary_date_quality TO pgweb_reader;
    END IF;
END $grant$;

INSERT INTO public."Table_Catalog"(table_schema, table_name, category, definition, grain, primary_key_columns,
 source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
 readiness_mode, readiness_date_column, observation_date_column, availability_rule)
VALUES ('public', 'broker_summary_date_quality', 'System',
 'Completeness of each IDX_Broker_Summary trade date after every write: stock rows, brokers, stocks and frequency share against the 20 earlier dates whose check passed, and whether the non-stock symbols vanished; status COMPLETE, INCOMPLETE or UNCHECKED with a plain Indonesian remark. Loads are never refused.',
 'One IDX_Broker_Summary trade date', ARRAY['trade_date'], 'Derived from IDX_Broker_Summary (EXEC-LOADER-M217)',
 ARRAY['IDX_Broker_Summary'], ARRAY['database/migrations/20261029_001_broker_summary_date_quality.sql'],
 'Recomputed by the IDX_Broker_Summary statement triggers for every inserted, updated or deleted date; filled for history by the backfill job of 2026-10-29.',
 ARRAY['remark_broker_summary_date(date)', 'broker_summary_remark_new()'],
 'VERIFIED', 'NOT_APPLICABLE', NULL, 'trade_date', 'Operational quality log, not market data; not exposed to the AI.')
ON CONFLICT (table_schema, table_name) DO NOTHING;

WITH d(column_name, definition, unit, null_rule) AS (VALUES
 ('trade_date', 'IDX_Broker_Summary trade date the row describes.', NULL, 'Never NULL.'),
 ('stock_rows', 'Rows of four-letter symbols (stocks) on the date.', 'rows', 'Never NULL.'),
 ('stock_brokers', 'Distinct brokers in the stock rows.', 'brokers', 'Never NULL.'),
 ('stock_symbols', 'Distinct four-letter symbols.', 'symbols', 'Never NULL.'),
 ('stock_freq_share', 'Share of stock rows with buy_freq and sell_freq filled, 0 to 1.', 'FRACTION', 'Never NULL.'),
 ('other_symbols', 'Distinct symbols that are not four letters (warrants, rights); the source gives them no frequency.', 'symbols', 'Never NULL.'),
 ('other_rows', 'Rows of the other symbols.', 'rows', 'Never NULL.'),
 ('stock_complete', 'No stock check failed (an UNCHECKED date counts); such dates form the baseline of later stock checks.', NULL, 'Never NULL.'),
 ('other_complete', 'The non-stock check passed; such dates form the baseline of that check.', NULL, 'Never NULL.'),
 ('status', 'COMPLETE, INCOMPLETE (a check failed) or UNCHECKED (fewer than 5 earlier complete dates).', NULL, 'Never NULL.'),
 ('findings', 'JSON array of the failed checks: check, value, usual (the baseline median).', NULL, 'Never NULL; empty array when none.'),
 ('baseline', 'JSON: the baseline medians and the number of earlier dates used.', NULL, 'NULL never written by the function.'),
 ('remark', 'Plain Indonesian remark: what is missing and how to fix it; for UNCHECKED, why it is not compared.', NULL, 'NULL for COMPLETE.'),
 ('checked_at', 'Time of the last recomputation.', NULL, 'Never NULL.'),
 ('checked_by', 'application_name of the session that wrote IDX_Broker_Summary (the loader).', NULL, 'NULL when the session set none.'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 c.column_name = 'trade_date', d.definition, 'remark_broker_summary_date(date)', d.unit, d.null_rule,
 ARRAY['database/migrations/20261029_001_broker_summary_date_quality.sql'], 'VERIFIED'
FROM information_schema.columns c JOIN d USING (column_name)
WHERE c.table_schema = 'public' AND c.table_name = 'broker_summary_date_quality'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

DO $check$ DECLARE missing int; BEGIN
    SELECT count(*) INTO missing FROM information_schema.columns c
     WHERE c.table_schema = 'public' AND c.table_name = 'broker_summary_date_quality'
       AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_schema = 'public'
                       AND k.table_name = c.table_name AND k.column_name = c.column_name);
    IF missing > 0 THEN RAISE EXCEPTION '% columns lack a Column_Catalog row', missing; END IF;
    SELECT count(*) INTO missing FROM pg_trigger WHERE tgrelid = 'public."IDX_Broker_Summary"'::regclass
       AND tgname LIKE 'idx_broker_summary_remark_%';
    IF missing <> 3 THEN RAISE EXCEPTION 'expected 3 remark triggers, found %', missing; END IF;
END $check$;

COMMIT;
