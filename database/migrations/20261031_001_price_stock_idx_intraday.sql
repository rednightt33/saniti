-- EXEC-INTRADAY-IDX (user 2026-10-31: "kecuali timeframe 5 menit, semua timeframe kita tarik saja dari 2020. Sekarang
-- proses penarikan data dulu saja. Feature bisa nanti. IHSG juga."; then "1A 2OK 3semua 4 no, ini ingestion saja ke table
-- baru seharusnya tidak berpengaruh"): intraday bars of the IDX stocks and IHSG at 5m, 15m, 1h and 4h from TradingView,
-- in a table of their own. The daily Price_Stock_Indonesia_IDX, Feature 01 and Feature 04 are not touched; no trigger
-- reaches a Feature table, and nothing is published to the rack yet.
--
-- Evidence read 2026-10-31 (read-only, verification/intraday_design/):
-- - TradingView without an account gives about 5,000 bars a series, also after request_more_data: 5m back to
--   2026-07-13 (67 bars a session), 15m to 2025-11-03 (23), 1h to 2023-01-02 (6-7), 4h to 2016-01-04 for BBCA (2, at
--   09:00 and 13:00). Answer 1A: what is available, then collected forward every day; 4h is cut at 2020-01-01.
-- - Every timeframe sums to the same session totals; close, high and low equal the daily candle, the session volume is
--   94.9-99.9 % of the daily volume and the open differs at times (pre-opening auction). The daily table is therefore
--   never derived from these bars, and the identity is stated in the catalog (Part A 15a).
-- - Bars carry the post-trading minutes 16:00-16:10 (5m) and the lunch break (session 2 from 13:30, Friday 14:00).
--
-- Grain: one bar per (ticker, timeframe, bar_time); bar_time is the bar's open time as TradingView gives it,
-- session_date its Asia/Jakarta trading date. Prices split-adjusted as TradingView gives them at load time for stocks,
-- unadjusted for the index (adjustment column; Part A 14). Only bars of sessions whose close plus finality delay has
-- passed (Equity_Market_Schedule) are written.
--
-- Disk cost (Part A 25): not derived, so not a view. Estimate from TradingView's depth, 845 symbols: backfill about
-- 4.2 M (5m) + 4.4 M (15m) + 5.1 M (1h) + 2.4 M (4h) = 16 M rows; growth about 14 M (5m) + 4.8 M (15m) + 1.3 M (1h)
-- + 0.4 M (4h) = 20.5 M rows a year. About 120 bytes a row plus the primary key: about 2.5-3 GB for the backfill and
-- 3-4 GB a year (measured after the backfill, DATABASE_CHANGELOG). The Postgres volume holds 47.1 of 75 GB
-- (2026-10-31). Partitioned by timeframe so each timeframe keeps its own index; no other index until a measured query
-- pattern needs one (Part A 24).
BEGIN;

CREATE TABLE public.price_stock_idx_intraday (
    ticker varchar NOT NULL,
    timeframe text NOT NULL CHECK (timeframe = ANY (ARRAY['5m', '15m', '1h', '4h'])),
    bar_time timestamptz NOT NULL,
    session_date date NOT NULL,
    open numeric(24, 8) NOT NULL,
    high numeric(24, 8) NOT NULL,
    low numeric(24, 8) NOT NULL,
    close numeric(24, 8) NOT NULL,
    volume numeric(30, 8),
    adjustment text NOT NULL CHECK (adjustment = ANY (ARRAY['splits', 'none'])),
    tradingview_symbol varchar NOT NULL,
    source varchar NOT NULL DEFAULT 'TradingView',
    query_date date NOT NULL,
    ingestion_time timestamptz NOT NULL DEFAULT statement_timestamp(),
    CONSTRAINT price_stock_idx_intraday_pkey PRIMARY KEY (ticker, timeframe, bar_time),
    CONSTRAINT price_stock_idx_intraday_ohlc CHECK (low <= open AND open <= high AND low <= close AND close <= high
                                                    AND low >= 0 AND (volume IS NULL OR volume >= 0)),
    CONSTRAINT price_stock_idx_intraday_ticker_upper CHECK (ticker = upper(btrim(ticker)))
) PARTITION BY LIST (timeframe);

CREATE TABLE public.price_stock_idx_intraday_5m PARTITION OF public.price_stock_idx_intraday FOR VALUES IN ('5m');
CREATE TABLE public.price_stock_idx_intraday_15m PARTITION OF public.price_stock_idx_intraday FOR VALUES IN ('15m');
CREATE TABLE public.price_stock_idx_intraday_1h PARTITION OF public.price_stock_idx_intraday FOR VALUES IN ('1h');
CREATE TABLE public.price_stock_idx_intraday_4h PARTITION OF public.price_stock_idx_intraday FOR VALUES IN ('4h');

COMMENT ON TABLE public.price_stock_idx_intraday IS
 'EXEC-INTRADAY-IDX: intraday OHLCV bars of the IDX_Stock_Universe stocks and IHSG at 5m, 15m, 1h and 4h from TradingView; one row per ticker, timeframe and bar open time. Stocks split-adjusted as TradingView gives them at load time, the index unadjusted. Never derived into or from the daily Price_Stock_Indonesia_IDX: the session volume is 95-100 % of the daily volume and the first open can differ (pre-opening auction).';

-- One quality row per timeframe and session after every write (Part A 28): completeness against the 20 earlier
-- sessions of the same timeframe whose check passed (median and MAD, the rule of broker_summary_date_quality). The
-- loader calls remark_intraday_sessions for the range it wrote; one grouped scan per call.
CREATE TABLE public.price_stock_idx_intraday_quality (
    timeframe text NOT NULL CHECK (timeframe = ANY (ARRAY['5m', '15m', '1h', '4h'])),
    session_date date NOT NULL,
    stocks integer NOT NULL,
    stock_bars integer NOT NULL,
    median_bars_per_stock numeric NOT NULL,
    index_bars integer NOT NULL,
    status text NOT NULL CHECK (status = ANY (ARRAY['COMPLETE', 'INCOMPLETE', 'UNCHECKED'])),
    findings jsonb NOT NULL DEFAULT '[]'::jsonb,
    baseline jsonb,
    remark text,
    checked_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    checked_by text,
    PRIMARY KEY (timeframe, session_date)
);
COMMENT ON TABLE public.price_stock_idx_intraday_quality IS
 'EXEC-INTRADAY-IDX: completeness of each timeframe and session of price_stock_idx_intraday after every write: stocks with bars and bars per stock against the 20 earlier sessions whose check passed, and whether IHSG has bars; status COMPLETE, INCOMPLETE or UNCHECKED with a plain Indonesian remark. Loads are never refused.';

CREATE FUNCTION public.remark_intraday_sessions(p_timeframe text, p_from date, p_to date) RETURNS integer
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
                 WHERE q.timeframe = p_timeframe AND q.session_date < r.session_date AND q.status = 'COMPLETE'
                 ORDER BY q.session_date DESC LIMIT 20) base;
        v_findings := '[]'::jsonb;
        IF n_base >= 5 THEN
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(stocks - b_stocks)),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(median_bars_per_stock - b_median))
              INTO m_stocks, m_median
              FROM (SELECT q.stocks, q.median_bars_per_stock FROM public.price_stock_idx_intraday_quality q
                     WHERE q.timeframe = p_timeframe AND q.session_date < r.session_date AND q.status = 'COMPLETE'
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
            WHEN 'UNCHECKED' THEN format('Belum dibandingkan: baru %s sesi %s sebelumnya yang lengkap (perlu 5).', n_base, p_timeframe)
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

DO $grant$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        GRANT SELECT ON public.price_stock_idx_intraday, public.price_stock_idx_intraday_5m,
              public.price_stock_idx_intraday_15m, public.price_stock_idx_intraday_1h,
              public.price_stock_idx_intraday_4h, public.price_stock_idx_intraday_quality TO pgweb_reader;
    END IF;
END $grant$;

INSERT INTO public."Table_Catalog"(table_schema, table_name, category, definition, grain, primary_key_columns,
 source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
 readiness_mode, readiness_date_column, observation_date_column, availability_rule)
VALUES
('public', 'price_stock_idx_intraday', 'Transactional',
 'Intraday OHLCV bars of the IDX stocks and IHSG at 5m, 15m, 1h and 4h (TradingView). Stocks split-adjusted as TradingView gives them at load time, IHSG unadjusted (column adjustment). The session volume is 95-100 % of the daily Price_Stock_Indonesia_IDX volume and the first open can differ (pre-opening auction): never derive the daily candle from these bars or the reverse. Depth from the source: 5m from 2026-07-13, 15m from 2025-11-03, 1h from 2023-01-02, 4h from 2020-01-01, then collected every day. Partitioned by timeframe.',
 'One bar per ticker, timeframe and bar open time', ARRAY['ticker', 'timeframe', 'bar_time'],
 'TradingView websocket, unauthenticated (apps/idx-price-cron/intraday_update.py)', ARRAY['IDX_Stock_Universe'],
 ARRAY['database/migrations/20261031_001_price_stock_idx_intraday.sql', 'apps/idx-price-cron/intraday_update.py'],
 'Daily after the IDX close plus finality delay (cron idx-intraday-cron), upsert on the key; history once by --mode backfill. A changed bar is updated in place; ingestion_time moves only for a changed or new bar.',
 ARRAY['remark_intraday_sessions(text,date,date)'], 'VERIFIED', 'DATA_DATE', 'session_date', 'session_date',
 'Available after the session close plus Equity_Market_Schedule.finality_delay_minutes; not exposed to the AI yet.'),
('public', 'price_stock_idx_intraday_quality', 'System',
 'Completeness of each timeframe and session of price_stock_idx_intraday after every write: stocks with bars and median bars per stock against the 20 earlier sessions whose check passed (median minus max(5 MAD, 5 %)), and IHSG bars present; status COMPLETE, INCOMPLETE or UNCHECKED with a plain Indonesian remark. Loads are never refused.',
 'One timeframe and session', ARRAY['timeframe', 'session_date'], 'Derived from price_stock_idx_intraday (EXEC-INTRADAY-IDX)',
 ARRAY['price_stock_idx_intraday'], ARRAY['database/migrations/20261031_001_price_stock_idx_intraday.sql'],
 'Recomputed by remark_intraday_sessions(timeframe, from, to) for the sessions every load wrote; the sessions are the dates of the universe index daily candles, so a session without bars is flagged too.',
 ARRAY['remark_intraday_sessions(text,date,date)'], 'VERIFIED', 'NOT_APPLICABLE', NULL, 'session_date',
 'Operational quality log, not market data; not exposed to the AI.')
ON CONFLICT (table_schema, table_name) DO NOTHING;

WITH d(table_name, column_name, definition, unit, null_rule) AS (VALUES
 ('price_stock_idx_intraday', 'ticker', 'IDX_Stock_Universe ticker (upper case), the same code as Price_Stock_Indonesia_IDX; IHSG for the index.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday', 'timeframe', 'Bar length: 5m, 15m, 1h or 4h.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday', 'bar_time', 'Open time of the bar as TradingView gives it (timestamptz; the exchange time zone is Asia/Jakarta). 4h bars open at 09:00 and 13:00; 5m bars include the post-trading minutes 16:00-16:10.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday', 'session_date', 'IDX trading date of the bar in Asia/Jakarta.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday', 'open', 'First price of the bar.', 'IDR', 'Never NULL.'),
 ('price_stock_idx_intraday', 'high', 'Highest price of the bar.', 'IDR', 'Never NULL.'),
 ('price_stock_idx_intraday', 'low', 'Lowest price of the bar.', 'IDR', 'Never NULL.'),
 ('price_stock_idx_intraday', 'close', 'Last price of the bar; the last bar of a session closes at the daily close.', 'IDR', 'Never NULL.'),
 ('price_stock_idx_intraday', 'volume', 'Shares traded in the bar (split-adjusted with the price for stocks). A session sums to 95-100 % of the daily volume.', 'shares', 'NULL when the source gives no volume (index).'),
 ('price_stock_idx_intraday', 'adjustment', 'Price adjustment TradingView applied: splits for stocks, none for the index.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday', 'tradingview_symbol', 'TradingView symbol used (IDX_Stock_Universe mapping, e.g. IDX:COMPOSITE for IHSG).', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday', 'source', 'Source system: TradingView.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday', 'query_date', 'Asia/Jakarta date of the request that wrote the bar.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday', 'ingestion_time', 'Database statement time of the write that created or last changed the bar.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday_quality', 'timeframe', 'Bar length of the checked session.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday_quality', 'session_date', 'Checked IDX trading date.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday_quality', 'stocks', 'Stocks (not the index) with at least one bar in the session.', 'stocks', 'Never NULL.'),
 ('price_stock_idx_intraday_quality', 'stock_bars', 'Bars of those stocks in the session.', 'bars', 'Never NULL.'),
 ('price_stock_idx_intraday_quality', 'median_bars_per_stock', 'Median bars per stock with bars (illiquid stocks have fewer).', 'bars', 'Never NULL.'),
 ('price_stock_idx_intraday_quality', 'index_bars', 'Bars of the universe index (IHSG) in the session.', 'bars', 'Never NULL.'),
 ('price_stock_idx_intraday_quality', 'status', 'COMPLETE, INCOMPLETE (a check failed) or UNCHECKED (fewer than 5 earlier complete sessions of the timeframe).', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday_quality', 'findings', 'JSON array of the failed checks: check, value, usual (the baseline median).', NULL, 'Never NULL; empty array when none.'),
 ('price_stock_idx_intraday_quality', 'baseline', 'JSON: number of earlier sessions used and their medians.', NULL, 'NULL never written by the function.'),
 ('price_stock_idx_intraday_quality', 'remark', 'Plain Indonesian remark: what is missing and how to fix it; for UNCHECKED, why it is not compared.', NULL, 'NULL for COMPLETE.'),
 ('price_stock_idx_intraday_quality', 'checked_at', 'Time of the last recomputation.', NULL, 'Never NULL.'),
 ('price_stock_idx_intraday_quality', 'checked_by', 'application_name of the session that wrote the bars (the loader).', NULL, 'NULL when the session set none.'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 (c.table_name, c.column_name) IN (('price_stock_idx_intraday', 'ticker'), ('price_stock_idx_intraday', 'timeframe'),
  ('price_stock_idx_intraday', 'bar_time'), ('price_stock_idx_intraday_quality', 'timeframe'),
  ('price_stock_idx_intraday_quality', 'session_date')),
 d.definition,
 CASE WHEN c.table_name = 'price_stock_idx_intraday' THEN 'TradingView bar (apps/idx-price-cron/intraday_update.py)'
      ELSE 'remark_intraday_sessions(text,date,date)' END,
 d.unit, d.null_rule,
 ARRAY['database/migrations/20261031_001_price_stock_idx_intraday.sql'], 'VERIFIED'
FROM information_schema.columns c JOIN d USING (table_name, column_name)
WHERE c.table_schema = 'public' AND c.table_name IN ('price_stock_idx_intraday', 'price_stock_idx_intraday_quality')
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

DO $check$ DECLARE missing int; BEGIN
    SELECT count(*) INTO missing FROM information_schema.columns c
     WHERE c.table_schema = 'public' AND c.table_name IN ('price_stock_idx_intraday', 'price_stock_idx_intraday_quality')
       AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_schema = 'public'
                       AND k.table_name = c.table_name AND k.column_name = c.column_name);
    IF missing > 0 THEN RAISE EXCEPTION '% columns lack a Column_Catalog row', missing; END IF;
    SELECT count(*) INTO missing FROM pg_inherits WHERE inhparent = 'public.price_stock_idx_intraday'::regclass;
    IF missing <> 4 THEN RAISE EXCEPTION 'expected 4 partitions, found %', missing; END IF;
END $check$;

COMMIT;
