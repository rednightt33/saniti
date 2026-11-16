BEGIN;
SELECT public.remark_intraday_sessions('1h', '2026-09-15', '2026-11-13') AS written;
SELECT md5(string_agg(concat_ws('|', session_date, stocks, stock_bars, median_bars_per_stock, index_bars, status, findings::text), ',' ORDER BY session_date)) AS digest, count(*) AS sessions FROM public.price_stock_idx_intraday_quality WHERE timeframe='1h';
-- a daily-only index with a candle on Sunday 2026-10-04 (no IDX session)
INSERT INTO public."IDX_Stock_Universe" SELECT (jsonb_populate_record(NULL::public."IDX_Stock_Universe", to_jsonb(u) || '{"Ticker":"LQ45","TradingView Symbol":"IDX:LQ45","Company Name":"IDX LQ45 Index"}')).* FROM public."IDX_Stock_Universe" u WHERE "Ticker"='IHSG';
INSERT INTO public."Price_Stock_Indonesia_IDX" SELECT (jsonb_populate_record(NULL::public."Price_Stock_Indonesia_IDX", to_jsonb(p) || '{"ticker":"LQ45","date":"2026-10-04"}')).* FROM public."Price_Stock_Indonesia_IDX" p WHERE ticker='IHSG' AND date='2026-10-02';
DELETE FROM public.price_stock_idx_intraday_quality;
SELECT public.remark_intraday_sessions('1h', '2026-09-15', '2026-11-13') AS written_with_lq45;
SELECT count(*) AS sessions_with_lq45, count(*) FILTER (WHERE session_date='2026-10-04') AS sunday_session FROM public.price_stock_idx_intraday_quality WHERE timeframe='1h';
ROLLBACK;
