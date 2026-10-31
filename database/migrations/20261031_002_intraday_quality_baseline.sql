-- EXEC-INTRADAY-IDX: the baseline of remark_intraday_sessions counts every earlier session whose check did not fail
-- (COMPLETE or UNCHECKED), the rule of broker_summary_date_quality ("an UNCHECKED date counts"). With COMPLETE only,
-- the first five sessions stay UNCHECKED and no session can ever become COMPLETE: the 4h backfill of 2026-10-31 left
-- 1,643 of 1,645 sessions UNCHECKED. The quality rows of every loaded timeframe are recomputed, oldest first.
BEGIN;

CREATE OR REPLACE FUNCTION public.remark_intraday_sessions(p_timeframe text, p_from date, p_to date) RETURNS integer
LANGUAGE plpgsql AS $fn$
-- Every IDX session from p_from to p_to (the dates on which the universe index has a final daily candle in
-- Price_Stock_Indonesia_IDX, so a session without a single bar is checked too), oldest first: counts from one grouped
-- scan, each compared with the 20 earlier sessions of the timeframe whose check passed. Returns the sessions written.
DECLARE
    r record; n_written integer := 0;
    b_stocks numeric; m_stocks numeric; b_median numeric; m_median numeric; n_base integer;
    v_findings jsonb; v_status text; v_remark text;
BEGIN
    IF p_timeframe <> ALL (ARRAY['5m', '15m', '1h', '4h']) OR p_from IS NULL OR p_to IS NULL OR p_from > p_to THEN
        RAISE EXCEPTION 'remark_intraday_sessions: timeframe 5m, 15m, 1h or 4h and from <= to are required';
    END IF;
    FOR r IN
        WITH idx AS (SELECT u."Ticker" AS ticker FROM public."IDX_Stock_Universe" u WHERE public.is_universe_index(u."Ticker")),
        cal AS (SELECT DISTINCT p.date AS session_date FROM public."Price_Stock_Indonesia_IDX" p JOIN idx ON idx.ticker = p.ticker
                 WHERE p.timeframe = 'Daily' AND p.is_final AND p.date BETWEEN p_from AND p_to),
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
               coalesce(a.median_bars, 0)::numeric AS median_bars, coalesce(a.index_bars, 0)::int AS index_bars
          FROM (SELECT session_date FROM cal UNION SELECT session_date FROM agg) d
          LEFT JOIN agg a USING (session_date)
         ORDER BY d.session_date
    LOOP
        SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY stocks),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY median_bars_per_stock)
          INTO n_base, b_stocks, b_median
          FROM (SELECT q.stocks, q.median_bars_per_stock FROM public.price_stock_idx_intraday_quality q
                 WHERE q.timeframe = p_timeframe AND q.session_date < r.session_date AND q.status <> 'INCOMPLETE'
                 ORDER BY q.session_date DESC LIMIT 20) base;
        v_findings := '[]'::jsonb;
        IF n_base >= 5 THEN
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(stocks - b_stocks)),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(median_bars_per_stock - b_median))
              INTO m_stocks, m_median
              FROM (SELECT q.stocks, q.median_bars_per_stock FROM public.price_stock_idx_intraday_quality q
                     WHERE q.timeframe = p_timeframe AND q.session_date < r.session_date AND q.status <> 'INCOMPLETE'
                     ORDER BY q.session_date DESC LIMIT 20) base;
            IF r.stocks < b_stocks - greatest(5 * m_stocks, 0.05 * b_stocks) THEN
                v_findings := v_findings || jsonb_build_object('check', 'stocks', 'value', r.stocks, 'usual', b_stocks);
            END IF;
            IF r.median_bars < b_median - greatest(5 * m_median, 0.05 * b_median) THEN
                v_findings := v_findings || jsonb_build_object('check', 'bars_per_stock', 'value', r.median_bars, 'usual', b_median);
            END IF;
        END IF;
        IF r.index_bars = 0 THEN
            v_findings := v_findings || jsonb_build_object('check', 'index_bars', 'value', 0, 'usual', NULL);
        END IF;
        v_status := CASE WHEN jsonb_array_length(v_findings) > 0 THEN 'INCOMPLETE'
                         WHEN n_base < 5 THEN 'UNCHECKED' ELSE 'COMPLETE' END;
        v_remark := CASE v_status
            WHEN 'COMPLETE' THEN NULL
            WHEN 'UNCHECKED' THEN format('Belum dibandingkan: baru %s sesi %s sebelumnya yang tidak bermasalah (perlu 5).', n_base, p_timeframe)
            ELSE format('Sesi %s %s kurang lengkap: %s saham dengan bar (biasanya %s), median %s bar per saham (biasanya %s)%s. Tarik ulang dengan intraday_update.py --mode backfill --timeframes %s.',
                        p_timeframe, r.session_date, r.stocks, coalesce(round(b_stocks)::text, '-'), round(r.median_bars, 1),
                        coalesce(round(b_median, 1)::text, '-'),
                        CASE WHEN r.index_bars = 0 THEN ', IHSG tanpa bar' ELSE '' END, p_timeframe) END;
        INSERT INTO public.price_stock_idx_intraday_quality AS q (timeframe, session_date, stocks, stock_bars,
            median_bars_per_stock, index_bars, status, findings, baseline, remark, checked_at, checked_by)
        VALUES (p_timeframe, r.session_date, r.stocks, r.stock_bars, r.median_bars, r.index_bars, v_status, v_findings,
                jsonb_build_object('sessions', n_base, 'stocks', b_stocks, 'median_bars_per_stock', b_median),
                v_remark, statement_timestamp(), nullif(current_setting('application_name', true), ''))
        ON CONFLICT (timeframe, session_date) DO UPDATE SET stocks = EXCLUDED.stocks, stock_bars = EXCLUDED.stock_bars,
            median_bars_per_stock = EXCLUDED.median_bars_per_stock, index_bars = EXCLUDED.index_bars,
            status = EXCLUDED.status, findings = EXCLUDED.findings, baseline = EXCLUDED.baseline,
            remark = EXCLUDED.remark, checked_at = EXCLUDED.checked_at, checked_by = EXCLUDED.checked_by;
        n_written := n_written + 1;
    END LOOP;
    RETURN n_written;
END
$fn$;

DO $recompute$ DECLARE r record; BEGIN
    FOR r IN SELECT timeframe, min(session_date) AS lo, max(session_date) AS hi
               FROM public.price_stock_idx_intraday_quality GROUP BY timeframe LOOP
        PERFORM public.remark_intraday_sessions(r.timeframe, r.lo, r.hi);
    END LOOP;
END $recompute$;

UPDATE public."Table_Catalog"
SET definition = replace(definition, 'against the 20 earlier sessions whose check passed (median minus max(5 MAD, 5 %))',
                         'against the 20 earlier sessions whose check did not fail, COMPLETE or UNCHECKED (median minus max(5 MAD, 5 %))'),
    source_code_paths = ARRAY['database/migrations/20261031_001_price_stock_idx_intraday.sql',
                              'database/migrations/20261031_002_intraday_quality_baseline.sql']
WHERE table_schema = 'public' AND table_name = 'price_stock_idx_intraday_quality';

DO $check$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE table_name = 'price_stock_idx_intraday_quality'
                   AND definition LIKE '%did not fail, COMPLETE or UNCHECKED%') THEN
        RAISE EXCEPTION 'Table_Catalog definition not updated';
    END IF;
END $check$;

COMMIT;
