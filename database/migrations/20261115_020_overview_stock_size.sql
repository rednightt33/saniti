-- EXEC-OVERVIEW O1 (user go 2026-11-15: "1 ok, 2 ok, 3 ok, go"; decision 2: "nanti akan ditambahkan data saham beredar,
-- make sure saja ini bisa di re-direct nanti dari sisi source data"): the Market Overview's tile size comes from one
-- function, public.overview_stock_size(date). Today it is the 20-session average traded value (close x volume of the
-- final daily prices, every board, as the price table holds them; within 0.3% of the broker summary's value on
-- 2026-11-09: BBCA Rp 1,496.7 bn vs 1,493.3 bn). When shares outstanding are loaded, a new migration replaces this
-- function with close x shares and size_basis 'market_cap'; the publisher writes the basis into the files and the page
-- names it, so neither changes.
--
-- The 20 sessions are the market's (the dates of the MARKET entity of Feature_Index_Entity, IHSG today), not the
-- stock's own: a day without a trade counts zero, so a stock suspended for weeks is small, not sized by old trades.
--
-- Also: SELECT for the publisher's role (terminal_market_reader) on the Feature tables the Overview reads (01, 04, 06 and
-- 06 _INDEX, Feature_Index_Entity); it read none of them before (has_table_privilege on dev, 2026-11-15).
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '2min';

DO $preflight$
BEGIN
    IF to_regprocedure('public.overview_stock_size(date)') IS NOT NULL THEN
        RAISE EXCEPTION 'overview_stock_size(date) already exists';
    END IF;
    IF to_regclass('public."Price_Stock_Indonesia_IDX"') IS NULL OR to_regclass('public."Feature_Index_Entity"') IS NULL
       OR to_regclass('public."Feature_01_Stock_Daily"') IS NULL OR to_regclass('public."Feature_04_Technical_Indicator"') IS NULL
       OR to_regclass('public."Feature_06_Foreign_Domestic"') IS NULL OR to_regclass('public."Feature_06_Foreign_Domestic_INDEX"') IS NULL THEN
        RAISE EXCEPTION 'the price table, Feature_Index_Entity and Features 01, 04, 06 and 06 _INDEX are required first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_market_reader') THEN
        RAISE EXCEPTION 'role terminal_market_reader is required';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Index_Entity" WHERE entity_kind = 'MARKET') <> 1 THEN
        RAISE EXCEPTION 'Feature_Index_Entity must name exactly one MARKET entity (the market calendar)';
    END IF;
END
$preflight$;

CREATE FUNCTION public.overview_stock_size(p_date date)
RETURNS TABLE (ticker text, size_value double precision, size_basis text)
LANGUAGE sql STABLE
AS $function$
    WITH market AS (
        SELECT e.ticker FROM public."Feature_Index_Entity" AS e WHERE e.entity_kind = 'MARKET'
    ), days AS (   -- the market's 20 newest final sessions up to p_date (index (ticker, date DESC) of final daily rows)
        SELECT p.date FROM public."Price_Stock_Indonesia_IDX" AS p
        WHERE p.ticker = (SELECT m.ticker FROM market AS m) AND p.timeframe = 'Daily' AND p.is_final AND p.date <= p_date
        ORDER BY p.date DESC LIMIT 20
    )
    SELECT p.ticker::text, (sum(p.close * p.volume) / 20)::double precision, 'adv20_value'::text
    FROM public."Price_Stock_Indonesia_IDX" AS p
    WHERE p.date IN (SELECT d.date FROM days AS d) AND p.timeframe = 'Daily' AND p.is_final AND p.volume IS NOT NULL
    GROUP BY p.ticker
    HAVING (SELECT count(*) FROM days) = 20 AND sum(p.close * p.volume) > 0
$function$;
COMMENT ON FUNCTION public.overview_stock_size(date) IS
    'EXEC-OVERVIEW: the Market Overview tile size of every ticker on p_date and its basis. adv20_value: sum(close x volume) of the final daily rows over the market''s 20 newest sessions up to p_date, divided by 20 (a day without a trade counts zero). Replace with market_cap (close x shares outstanding) when that source exists; the files carry the basis.';

GRANT EXECUTE ON FUNCTION public.overview_stock_size(date) TO terminal_market_reader;
GRANT SELECT ON public."Feature_01_Stock_Daily", public."Feature_04_Technical_Indicator", public."Feature_06_Foreign_Domestic",
                public."Feature_06_Foreign_Domestic_INDEX", public."Feature_Index_Entity" TO terminal_market_reader;

UPDATE public."Table_Catalog"
SET related_functions = array_append(related_functions, 'overview_stock_size(date)'),
    source_code_paths = array_append(source_code_paths, 'database/migrations/20261115_020_overview_stock_size.sql'),
    updated_at = now()
WHERE table_schema = 'public' AND table_name = 'Price_Stock_Indonesia_IDX'
  AND NOT ('overview_stock_size(date)' = ANY (related_functions));

DO $verify$
DECLARE
    v_basis text;
BEGIN
    SELECT s.size_basis INTO v_basis FROM public.overview_stock_size(current_date) AS s LIMIT 1;
    IF v_basis IS DISTINCT FROM 'adv20_value' AND v_basis IS NOT NULL THEN
        RAISE EXCEPTION 'overview_stock_size returned basis %', v_basis;
    END IF;
    IF NOT has_function_privilege('terminal_market_reader', 'public.overview_stock_size(date)', 'EXECUTE')
       OR NOT has_table_privilege('terminal_market_reader', 'public."Feature_06_Foreign_Domestic_INDEX"', 'SELECT')
       OR NOT has_table_privilege('terminal_market_reader', 'public."Feature_04_Technical_Indicator"', 'SELECT') THEN
        RAISE EXCEPTION 'terminal_market_reader lacks a grant of this migration';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE table_name = 'Price_Stock_Indonesia_IDX'
                   AND 'overview_stock_size(date)' = ANY (related_functions)) THEN
        RAISE EXCEPTION 'Table_Catalog does not name overview_stock_size';
    END IF;
END
$verify$;

COMMIT;
