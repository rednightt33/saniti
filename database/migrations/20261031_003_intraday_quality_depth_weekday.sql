-- EXEC-INTRADAY-IDX (user 2026-10-31: "Lanjut 1-4"): the quality rule after the full backfill and the two read-only
-- reviews of 2026-10-31. Three causes made thousands of 1h/15m/5m sessions INCOMPLETE without any data missing:
-- 1. Depth: TradingView gives about 5,000-6,200 bars a series, so an illiquid stock reaches back years while a liquid
--    one starts 2023-01-02 (1h), 2025-11-03 (15m) or 2026-07-13 (5m). Sessions before that date hold only part of
--    the stocks by construction. The depth start of a timeframe is derived: the first session from which every later
--    session has bars for at least 80 % of the stocks the daily table shows as traded (the latest first session of the
--    cut stocks was tried in the rehearsal and gave 2025-12-08 for 4h through one late-starting series). Earlier
--    sessions get status BEFORE_DEPTH with a remark, not INCOMPLETE.
-- 2. Friday: the session is shorter (break to 14:00), so a Friday has fewer bars per stock (5m median 44-46 against
--    55). Bars per stock and index bars are compared with earlier sessions of the same day class (Friday or not).
-- 3. The expected number of stocks is the daily table's count of stocks with a final candle and volume > 0 on the
--    date, not a median of earlier sessions; a stock may lack bars on some days, so the check allows
--    max(5, 2 %). Measured on 4h: 802 of 1.12 M traded stock-sessions have no bars, clustered on 2026-03-02 (84),
--    2026-02-04/05, 2025-11-04 and 2025-12-02/03, which stay INCOMPLETE (source gaps).
-- The index check flags IHSG bars below 80 % of the same-class baseline: 2025-09-26 (one of two 4h bars) is flagged,
-- the 5m count moving between 65 and 66 is not.
BEGIN;

ALTER TABLE public.price_stock_idx_intraday_quality
    DROP CONSTRAINT price_stock_idx_intraday_quality_status_check,
    ADD CONSTRAINT price_stock_idx_intraday_quality_status_check
        CHECK (status = ANY (ARRAY['COMPLETE', 'INCOMPLETE', 'UNCHECKED', 'BEFORE_DEPTH'])),
    ADD COLUMN expected_stocks integer;

CREATE OR REPLACE FUNCTION public.remark_intraday_sessions(p_timeframe text, p_from date, p_to date) RETURNS integer
LANGUAGE plpgsql AS $fn$
-- Every IDX session from p_from to p_to (the dates of the universe index daily candles), oldest first; see the header
-- of migration 20261031_003. Returns the sessions written.
DECLARE
    r record; n_written integer := 0; v_depth date;
    b_median numeric; m_median numeric; b_index numeric; n_base integer;
    v_findings jsonb; v_status text; v_remark text; v_short integer;
BEGIN
    IF p_timeframe <> ALL (ARRAY['5m', '15m', '1h', '4h']) OR p_from IS NULL OR p_to IS NULL OR p_from > p_to THEN
        RAISE EXCEPTION 'remark_intraday_sessions: timeframe 5m, 15m, 1h or 4h and from <= to are required';
    END IF;
    -- depth start: the first session from which every later session has bars for at least 80 % of the stocks the daily
    -- table shows as traded (source-gap days are about 89-90 %; sessions cut by the source depth far below)
    WITH idx AS (SELECT u."Ticker" AS ticker FROM public."IDX_Stock_Universe" u WHERE public.is_universe_index(u."Ticker")),
    have AS (SELECT b.session_date, count(DISTINCT b.ticker) AS n FROM public.price_stock_idx_intraday b
              WHERE b.timeframe = p_timeframe AND b.session_date <= p_to AND b.ticker NOT IN (SELECT ticker FROM idx)
              GROUP BY b.session_date),
    cov AS (SELECT p.date AS session_date, coalesce(max(h.n), 0)::numeric / count(*) AS c
              FROM public."Price_Stock_Indonesia_IDX" p LEFT JOIN have h ON h.session_date = p.date
             WHERE p.timeframe = 'Daily' AND p.is_final AND p.volume > 0 AND p.ticker NOT IN (SELECT ticker FROM idx)
               AND p.date BETWEEN (SELECT min(session_date) FROM have) AND p_to
             GROUP BY p.date)
    SELECT min(c1.session_date) INTO v_depth FROM cov c1
     WHERE NOT EXISTS (SELECT 1 FROM cov c2 WHERE c2.session_date >= c1.session_date AND c2.c < 0.8);
    FOR r IN
        WITH idx AS (SELECT u."Ticker" AS ticker FROM public."IDX_Stock_Universe" u WHERE public.is_universe_index(u."Ticker")),
        cal AS (SELECT DISTINCT p.date AS session_date FROM public."Price_Stock_Indonesia_IDX" p JOIN idx ON idx.ticker = p.ticker
                 WHERE p.timeframe = 'Daily' AND p.is_final AND p.date BETWEEN p_from AND p_to),
        traded AS (SELECT p.date AS session_date, count(*) AS n FROM public."Price_Stock_Indonesia_IDX" p
                    WHERE p.timeframe = 'Daily' AND p.is_final AND p.date BETWEEN p_from AND p_to AND p.volume > 0
                      AND p.ticker NOT IN (SELECT ticker FROM idx) GROUP BY p.date),
        per AS (SELECT b.session_date, b.ticker, count(*) AS n, (b.ticker IN (SELECT ticker FROM idx)) AS is_index
                  FROM public.price_stock_idx_intraday b
                 WHERE b.timeframe = p_timeframe AND b.session_date BETWEEN p_from AND p_to
                 GROUP BY b.session_date, b.ticker),
        agg AS (SELECT session_date,
                       count(*) FILTER (WHERE NOT is_index) AS stocks,
                       coalesce(sum(n) FILTER (WHERE NOT is_index), 0) AS stock_bars,
                       coalesce(percentile_cont(0.5) WITHIN GROUP (ORDER BY n) FILTER (WHERE NOT is_index), 0)::numeric AS median_bars,
                       coalesce(sum(n) FILTER (WHERE is_index), 0) AS index_bars
                  FROM per GROUP BY session_date)
        SELECT d.session_date, coalesce(a.stocks, 0)::int AS stocks, coalesce(a.stock_bars, 0)::int AS stock_bars,
               coalesce(a.median_bars, 0)::numeric AS median_bars, coalesce(a.index_bars, 0)::int AS index_bars,
               t.n::int AS expected, extract(isodow FROM d.session_date) = 5 AS friday
          FROM (SELECT session_date FROM cal UNION SELECT session_date FROM agg) d
          LEFT JOIN agg a USING (session_date) LEFT JOIN traded t USING (session_date)
         ORDER BY d.session_date
    LOOP
        v_findings := '[]'::jsonb;
        IF v_depth IS NOT NULL AND r.session_date < v_depth THEN
            v_status := 'BEFORE_DEPTH';
            v_remark := format('Sebelum batas kedalaman sumber %s (%s): TradingView memberi sekitar 5.000-6.200 bar per saham, jadi pada sesi ini hanya saham yang jarang bertransaksi yang masih punya bar (%s dari %s saham bertransaksi). Bukan data yang hilang dan tidak bisa ditarik ulang.',
                               p_timeframe, v_depth, r.stocks, coalesce(r.expected::text, '-'));
        ELSE
            SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY median_bars_per_stock),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY index_bars)
              INTO n_base, b_median, b_index
              FROM (SELECT q.median_bars_per_stock, q.index_bars FROM public.price_stock_idx_intraday_quality q
                     WHERE q.timeframe = p_timeframe AND q.session_date < r.session_date
                       AND q.status IN ('COMPLETE', 'UNCHECKED')
                       AND (extract(isodow FROM q.session_date) = 5) = r.friday
                     ORDER BY q.session_date DESC LIMIT 20) base;
            IF r.expected IS NOT NULL THEN
                v_short := r.expected - r.stocks;
                IF v_short > greatest(5, 0.02 * r.expected) THEN
                    v_findings := v_findings || jsonb_build_object('check', 'stocks', 'value', r.stocks, 'usual', r.expected);
                END IF;
            END IF;
            IF n_base >= 5 THEN
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(median_bars_per_stock - b_median)) INTO m_median
                  FROM (SELECT q.median_bars_per_stock FROM public.price_stock_idx_intraday_quality q
                         WHERE q.timeframe = p_timeframe AND q.session_date < r.session_date
                           AND q.status IN ('COMPLETE', 'UNCHECKED')
                           AND (extract(isodow FROM q.session_date) = 5) = r.friday
                         ORDER BY q.session_date DESC LIMIT 20) base;
                IF r.median_bars < b_median - greatest(5 * m_median, 0.2 * b_median) THEN
                    v_findings := v_findings || jsonb_build_object('check', 'bars_per_stock', 'value', r.median_bars, 'usual', b_median);
                END IF;
                IF r.index_bars < 0.8 * b_index THEN
                    v_findings := v_findings || jsonb_build_object('check', 'index_bars', 'value', r.index_bars, 'usual', b_index);
                END IF;
            ELSIF r.index_bars = 0 THEN
                v_findings := v_findings || jsonb_build_object('check', 'index_bars', 'value', 0, 'usual', NULL);
            END IF;
            v_status := CASE WHEN jsonb_array_length(v_findings) > 0 THEN 'INCOMPLETE'
                             WHEN n_base < 5 OR r.expected IS NULL THEN 'UNCHECKED' ELSE 'COMPLETE' END;
            v_remark := CASE v_status
                WHEN 'COMPLETE' THEN NULL
                WHEN 'UNCHECKED' THEN format('Belum dibandingkan: %s.', CASE WHEN r.expected IS NULL
                    THEN 'tabel harga harian belum punya saham bertransaksi pada tanggal ini'
                    ELSE format('baru %s sesi %s sebelumnya (kelompok hari yang sama) yang tidak bermasalah, perlu 5', n_base, p_timeframe) END)
                ELSE format('Sesi %s %s kurang lengkap: %s dari %s saham bertransaksi punya bar, median %s bar per saham (biasanya %s), IHSG %s bar (biasanya %s). Bila sumbernya sudah punya, tarik ulang dengan intraday_update.py --mode backfill --timeframes %s; bila tidak, ini celah di TradingView.',
                            p_timeframe, r.session_date, r.stocks, coalesce(r.expected::text, '-'), round(r.median_bars, 1),
                            coalesce(round(b_median, 1)::text, '-'), r.index_bars, coalesce(round(b_index)::text, '-'), p_timeframe) END;
        END IF;
        INSERT INTO public.price_stock_idx_intraday_quality AS q (timeframe, session_date, stocks, stock_bars,
            median_bars_per_stock, index_bars, status, findings, baseline, remark, checked_at, checked_by, expected_stocks)
        VALUES (p_timeframe, r.session_date, r.stocks, r.stock_bars, r.median_bars, r.index_bars, v_status, v_findings,
                jsonb_build_object('sessions', n_base, 'median_bars_per_stock', b_median, 'index_bars', b_index,
                                   'depth_start', v_depth, 'friday', r.friday),
                v_remark, statement_timestamp(), nullif(current_setting('application_name', true), ''), r.expected)
        ON CONFLICT (timeframe, session_date) DO UPDATE SET stocks = EXCLUDED.stocks, stock_bars = EXCLUDED.stock_bars,
            median_bars_per_stock = EXCLUDED.median_bars_per_stock, index_bars = EXCLUDED.index_bars,
            status = EXCLUDED.status, findings = EXCLUDED.findings, baseline = EXCLUDED.baseline,
            remark = EXCLUDED.remark, checked_at = EXCLUDED.checked_at, checked_by = EXCLUDED.checked_by,
            expected_stocks = EXCLUDED.expected_stocks;
        n_written := n_written + 1;
        n_base := 0; b_median := NULL; b_index := NULL;
    END LOOP;
    RETURN n_written;
END
$fn$;

-- recompute every loaded timeframe, oldest first, from a clean table (the baseline reads earlier rows)
DO $recompute$ DECLARE r record; BEGIN
    CREATE TEMP TABLE intraday_ranges ON COMMIT DROP AS
        SELECT timeframe, min(session_date) AS lo, max(session_date) AS hi FROM public.price_stock_idx_intraday_quality GROUP BY timeframe;
    DELETE FROM public.price_stock_idx_intraday_quality;
    FOR r IN SELECT * FROM intraday_ranges LOOP
        PERFORM public.remark_intraday_sessions(r.timeframe, r.lo, r.hi);
    END LOOP;
END $recompute$;

UPDATE public."Table_Catalog"
SET definition = 'Completeness of each timeframe and session of price_stock_idx_intraday after every write. Stocks with bars against the daily table''s stocks with a final candle and volume > 0 that date (short by more than max(5, 2 %) fails); median bars per stock and IHSG bars against the 20 earlier sessions of the same day class (Friday or not) whose check did not fail. Sessions before the timeframe''s depth start (derived: the latest first session among stocks whose intraday history is cut by the source) are BEFORE_DEPTH. Status COMPLETE, INCOMPLETE, UNCHECKED or BEFORE_DEPTH with a plain Indonesian remark. Loads are never refused.',
    source_code_paths = ARRAY['database/migrations/20261031_001_price_stock_idx_intraday.sql',
                              'database/migrations/20261031_002_intraday_quality_baseline.sql',
                              'database/migrations/20261031_003_intraday_quality_depth_weekday.sql']
WHERE table_schema = 'public' AND table_name = 'price_stock_idx_intraday_quality';

UPDATE public."Column_Catalog" SET definition = 'COMPLETE, INCOMPLETE (a check failed), UNCHECKED (no daily candles on the date, or fewer than 5 earlier sessions of the same day class) or BEFORE_DEPTH (before the source depth of the timeframe: only part of the stocks can have bars).'
WHERE table_schema = 'public' AND table_name = 'price_stock_idx_intraday_quality' AND column_name = 'status';

INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default, false,
 'Stocks with a final daily candle and volume > 0 in Price_Stock_Indonesia_IDX on the session date: the stocks expected to have bars.',
 'remark_intraday_sessions(text,date,date)', 'stocks', 'NULL when the daily table has no traded stock on the date.',
 ARRAY['database/migrations/20261031_003_intraday_quality_depth_weekday.sql'], 'VERIFIED'
FROM information_schema.columns c
WHERE c.table_schema = 'public' AND c.table_name = 'price_stock_idx_intraday_quality' AND c.column_name = 'expected_stocks'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

UPDATE public."Table_Catalog"
SET definition = replace(definition, 'The session volume is 95-100 % of the daily Price_Stock_Indonesia_IDX volume and the first open can differ (pre-opening auction)',
                         'Since 2024-12-09 the bars leave out the pre-opening auction, so the first open, the high or low and the session volume can differ from the daily candle (volume median 99.8 %, as low as 68 % on extreme days; before that date equal in 96 % of sessions); the last close equals the daily close apart from closing-auction ticks'),
    source_code_paths = ARRAY['database/migrations/20261031_001_price_stock_idx_intraday.sql',
                              'database/migrations/20261031_003_intraday_quality_depth_weekday.sql']
WHERE table_schema = 'public' AND table_name = 'price_stock_idx_intraday';

UPDATE public."Column_Catalog"
SET definition = 'Shares traded in the bar (split-adjusted with the price for stocks). Since 2024-12-09 a session leaves out the pre-opening auction: median 99.8 % of the daily volume, as low as 68 % on extreme days; before that date it equals the daily volume in 96 % of sessions.'
WHERE table_schema = 'public' AND table_name = 'price_stock_idx_intraday' AND column_name = 'volume';

DO $check$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE table_name = 'price_stock_idx_intraday'
                   AND definition LIKE '%pre-opening auction, so the first open%') THEN
        RAISE EXCEPTION 'Table_Catalog definition of price_stock_idx_intraday not updated';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public."Column_Catalog" WHERE table_name = 'price_stock_idx_intraday_quality'
                   AND column_name = 'expected_stocks') THEN
        RAISE EXCEPTION 'expected_stocks lacks a Column_Catalog row';
    END IF;
END $check$;

COMMIT;
