-- EXEC-INDEX-GROUP-HISTORY stage 2, migration A (user 2026-11-15: "Dari 2022 saja ya / 1A / 2A / 3A / 4A / 5 yes",
-- "D1 A / D2 OK / D3 OK / D4 OK", "2024 saja, go mulai tahap 1-2"; PLAN.md INDEX-GROUP-HISTORY).
--
-- What: the registry of the entities the *_INDEX Feature tables may hold, and the guard and calendar that read it.
-- 1. Feature_Index_Entity: one row per INDEX ticker with how its members are found, derived at run time, never listed:
--    IHSG       MARKET   every source symbol of IDX_Broker_Summary (unchanged; its history and refresh stay as they are);
--    32 INDEX   INDEX    the Stockbit list (Stock_List_Member_History, point in time);
--    11 SECTOR  SECTOR   IDX_Stock_Universe."Sector" of the stocks (IDX_Stock_Universe_History, point in time);
--    33 GROUP   GROUP    the Stockbit KONGLO list; no price, so never Feature 01 or 04.
--    rows_from 2024-01-02 for the 76 new entities (user "2024 saja"); IHSG NULL (its history from 2016/2018 stays).
-- 2. validate_index_feature_identity (the guard on the six *_INDEX tables) reads the registry instead of "a universe
--    index": a GROUP may enter Feature 02, 03, 05 and 06 only; Feature 01 and 04 need a priced entity that is a universe
--    index; a priced entity must be a universe index everywhere; no row of an entity before its rows_from; a
--    fixed-income ticker stays refused. Every refusal names the ticker, what is missing and how to fix it.
-- 3. remark_intraday_sessions: its session calendar is the daily candles of the indexes that have intraday bars (today
--    IHSG), not of every universe index, so the 43 daily-only indexes of migration B cannot add or move a session
--    (index_bars, and intraday_bars_per_year from it, already count only series that have bars). The same rule as
--    apps/idx-price-cron/intraday_update.py intraday_indexes (stage 1).
-- 4. Table_Catalog and Column_Catalog rows of the new table; SELECT for pgweb_reader when it exists.
-- No market data row is written or changed; the 43 universe rows are migration B (20261115_002), applied after the
-- stage 1 deploy. Rehearsed on a local PostgreSQL 16 copy of the dev definitions (verification/index_group_history/).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_Index_Entity"') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature_Index_Entity exists: reconcile before applying';
    END IF;
    IF (SELECT md5(prosrc) FROM pg_proc WHERE oid = 'public.validate_index_feature_identity()'::regprocedure)
       <> 'e8d0fb84209cba39e8145e6ef4d50d1b' THEN
        RAISE EXCEPTION 'validate_index_feature_identity differs from the version read on dev 2026-11-15: reconcile first';
    END IF;
    IF (SELECT md5(prosrc) FROM pg_proc WHERE oid = 'public.remark_intraday_sessions(text,date,date)'::regprocedure)
       <> '06a4761921750a9b5f9be38bd5dc7526' THEN
        RAISE EXCEPTION 'remark_intraday_sessions differs from the version read on dev 2026-11-15: reconcile first';
    END IF;
    IF NOT public.is_universe_index('IHSG') THEN
        RAISE EXCEPTION 'IHSG is not a universe index';
    END IF;
END $preflight$;

CREATE TABLE public."Feature_Index_Entity" (
    ticker text NOT NULL,
    entity_kind text NOT NULL,
    name text,
    member_source text NOT NULL,
    list_key text,
    sector text,
    has_price boolean NOT NULL,
    rows_from date,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT "Feature_Index_Entity_pkey" PRIMARY KEY (ticker),
    CONSTRAINT "Feature_Index_Entity_ticker_check" CHECK (ticker ~ '^[A-Z0-9]{1,12}$'),
    CONSTRAINT "Feature_Index_Entity_kind_check" CHECK (entity_kind IN ('MARKET', 'INDEX', 'SECTOR', 'GROUP')),
    CONSTRAINT "Feature_Index_Entity_source_check" CHECK (
        (member_source = 'ALL_SOURCE_SYMBOLS' AND entity_kind = 'MARKET' AND sector IS NULL)
        OR (member_source = 'STOCK_LIST' AND sector IS NULL
            AND ((entity_kind = 'INDEX' AND list_key LIKE 'INDEX:%') OR (entity_kind = 'GROUP' AND list_key LIKE 'KONGLO:%')))
        OR (member_source = 'UNIVERSE_SECTOR' AND entity_kind = 'SECTOR' AND sector IS NOT NULL AND list_key IS NULL)),
    CONSTRAINT "Feature_Index_Entity_price_check" CHECK (has_price = (entity_kind <> 'GROUP')),
    CONSTRAINT "Feature_Index_Entity_rows_from_check" CHECK ((rows_from IS NULL) = (entity_kind = 'MARKET')),
    CONSTRAINT "Feature_Index_Entity_list_fkey" FOREIGN KEY (list_key) REFERENCES public."Stock_List" (list_key)
);
COMMENT ON TABLE public."Feature_Index_Entity" IS
 'EXEC-INDEX-GROUP-HISTORY: the entities of the *_INDEX Feature tables and how their members are found (Stockbit list, '
 'universe sector, or every source symbol for IHSG); read by validate_index_feature_identity and the INDEX calculation.';

-- the Stockbit lists are named by kind and code here and stored by their key (list_key); a code that matches no list leaves
-- list_key NULL and the source check refuses the row
INSERT INTO public."Feature_Index_Entity" (ticker, entity_kind, name, member_source, list_key, sector, has_price, rows_from)
SELECT v.ticker, v.entity_kind, coalesce(v.name, l.name), v.member_source, l.list_key, v.sector, v.has_price, v.rows_from
  FROM (VALUES
    ('IHSG', 'MARKET', 'IDX Composite Index', 'ALL_SOURCE_SYMBOLS', 'INDEX', 'IHSG', NULL, true, NULL),
    ('LQ45', 'INDEX', 'IDX LQ45 Index', 'STOCK_LIST', 'INDEX', 'LQ45', NULL, true, DATE '2024-01-02'),
    ('JII', 'INDEX', 'Jakarta Islamic Index', 'STOCK_LIST', 'INDEX', 'JII', NULL, true, DATE '2024-01-02'),
    ('MBX', 'INDEX', 'Main Board Index', 'STOCK_LIST', 'INDEX', 'MBX', NULL, true, DATE '2024-01-02'),
    ('DBX', 'INDEX', 'Development Board Index', 'STOCK_LIST', 'INDEX', 'DBX', NULL, true, DATE '2024-01-02'),
    ('BISNIS27', 'INDEX', 'Bisnis-27 Index', 'STOCK_LIST', 'INDEX', 'BISNIS-27', NULL, true, DATE '2024-01-02'),
    ('KOMPAS100', 'INDEX', 'IDX Kompas 100 Index', 'STOCK_LIST', 'INDEX', 'KOMPAS100', NULL, true, DATE '2024-01-02'),
    ('SRIKEHATI', 'INDEX', 'SRI-KEHATI Index', 'STOCK_LIST', 'INDEX', 'SRI-KEHATI', NULL, true, DATE '2024-01-02'),
    ('ISSI', 'INDEX', 'Indonesia Sharia Stock Index', 'STOCK_LIST', 'INDEX', 'ISSI', NULL, true, DATE '2024-01-02'),
    ('IDX30', 'INDEX', 'IDX30', 'STOCK_LIST', 'INDEX', 'IDX30', NULL, true, DATE '2024-01-02'),
    ('INFOBANK15', 'INDEX', 'Infobank15 Index', 'STOCK_LIST', 'INDEX', 'INFOBANK15', NULL, true, DATE '2024-01-02'),
    ('INVESTOR33', 'INDEX', 'Investor33 Index', 'STOCK_LIST', 'INDEX', 'Investor33', NULL, true, DATE '2024-01-02'),
    ('MNC36', 'INDEX', 'MNC36 Index', 'STOCK_LIST', 'INDEX', 'MNC36', NULL, true, DATE '2024-01-02'),
    ('SMINFRA18', 'INDEX', 'SMinfra18 Index', 'STOCK_LIST', 'INDEX', 'SMinfra18', NULL, true, DATE '2024-01-02'),
    ('IDXHIDIV20', 'INDEX', 'IDX High Dividend 20', 'STOCK_LIST', 'INDEX', 'IDXHIDIV20', NULL, true, DATE '2024-01-02'),
    ('IDXBUMN20', 'INDEX', 'IDX BUMN20', 'STOCK_LIST', 'INDEX', 'IDXBUMN20', NULL, true, DATE '2024-01-02'),
    ('JII70', 'INDEX', 'Jakarta Islamic Index 70', 'STOCK_LIST', 'INDEX', 'JII70', NULL, true, DATE '2024-01-02'),
    ('IDXG30', 'INDEX', 'IDX Growth30', 'STOCK_LIST', 'INDEX', 'IDXG30', NULL, true, DATE '2024-01-02'),
    ('IDXV30', 'INDEX', 'IDX Value30', 'STOCK_LIST', 'INDEX', 'IDXV30', NULL, true, DATE '2024-01-02'),
    ('IDXQ30', 'INDEX', 'IDX Quality30', 'STOCK_LIST', 'INDEX', 'IDXQ30', NULL, true, DATE '2024-01-02'),
    ('IDXESGL', 'INDEX', 'IDX ESG Leaders', 'STOCK_LIST', 'INDEX', 'IDXESGL', NULL, true, DATE '2024-01-02'),
    ('IDX80', 'INDEX', 'IDX80', 'STOCK_LIST', 'INDEX', 'IDX80', NULL, true, DATE '2024-01-02'),
    ('IDXMESBUMN', 'INDEX', 'IDX-MES BUMN 17', 'STOCK_LIST', 'INDEX', 'IDXMESBUMN', NULL, true, DATE '2024-01-02'),
    ('ESGSKEHATI', 'INDEX', 'ESG Sector Leaders IDX KEHATI', 'STOCK_LIST', 'INDEX', 'ESGSKEHATI', NULL, true, DATE '2024-01-02'),
    ('ESGQKEHATI', 'INDEX', 'ESG Quality 45 IDX KEHATI', 'STOCK_LIST', 'INDEX', 'ESGQKEHATI', NULL, true, DATE '2024-01-02'),
    ('IDXSMCLIQ', 'INDEX', 'IDX SMC Liquid', 'STOCK_LIST', 'INDEX', 'IDXSMC-LIQ', NULL, true, DATE '2024-01-02'),
    ('IDXSMCCOM', 'INDEX', 'IDX SMC Composite', 'STOCK_LIST', 'INDEX', 'IDXSMC-COM', NULL, true, DATE '2024-01-02'),
    ('IGRADE', 'INDEX', 'PEFINDO i-Grade', 'STOCK_LIST', 'INDEX', 'I-GRADE', NULL, true, DATE '2024-01-02'),
    ('IDXSHAGROW', 'INDEX', 'IDX Sharia Growth', 'STOCK_LIST', 'INDEX', 'IDXSHAGROW', NULL, true, DATE '2024-01-02'),
    ('IDXLQ45LCL', 'INDEX', 'IDX LQ45 Low Carbon Leaders', 'STOCK_LIST', 'INDEX', 'IDXLQ45LCL', NULL, true, DATE '2024-01-02'),
    ('PRIMBANK10', 'INDEX', 'PRIMBANK10', 'STOCK_LIST', 'INDEX', 'PRIMBANK10', NULL, true, DATE '2024-01-02'),
    ('ECONOMIC30', 'INDEX', 'ECONOMIC30', 'STOCK_LIST', 'INDEX', 'ECONOMIC30', NULL, true, DATE '2024-01-02'),
    ('IDXVESTA28', 'INDEX', 'IDXVESTA28', 'STOCK_LIST', 'INDEX', 'IDXVESTA28', NULL, true, DATE '2024-01-02'),
    ('IDXBASIC', 'SECTOR', 'IDX Sector Basic Materials', 'UNIVERSE_SECTOR', NULL, NULL, 'Basic Materials', true, DATE '2024-01-02'),
    ('IDXCYCLIC', 'SECTOR', 'IDX Sector Consumer Cyclicals', 'UNIVERSE_SECTOR', NULL, NULL, 'Consumer Cyclicals', true, DATE '2024-01-02'),
    ('IDXNONCYC', 'SECTOR', 'IDX Sector Consumer Non-Cyclicals', 'UNIVERSE_SECTOR', NULL, NULL, 'Consumer Non-Cyclicals', true, DATE '2024-01-02'),
    ('IDXENERGY', 'SECTOR', 'IDX Sector Energy', 'UNIVERSE_SECTOR', NULL, NULL, 'Energy', true, DATE '2024-01-02'),
    ('IDXFINANCE', 'SECTOR', 'IDX Sector Financials', 'UNIVERSE_SECTOR', NULL, NULL, 'Financials', true, DATE '2024-01-02'),
    ('IDXHEALTH', 'SECTOR', 'IDX Sector Healthcare', 'UNIVERSE_SECTOR', NULL, NULL, 'Healthcare', true, DATE '2024-01-02'),
    ('IDXINDUST', 'SECTOR', 'IDX Sector Industrials', 'UNIVERSE_SECTOR', NULL, NULL, 'Industrials', true, DATE '2024-01-02'),
    ('IDXINFRA', 'SECTOR', 'IDX Sector Infrastructures', 'UNIVERSE_SECTOR', NULL, NULL, 'Infrastructures', true, DATE '2024-01-02'),
    ('IDXPROPERT', 'SECTOR', 'IDX Sector Properties & Real Estate', 'UNIVERSE_SECTOR', NULL, NULL, 'Properties & Real Estate', true, DATE '2024-01-02'),
    ('IDXTECHNO', 'SECTOR', 'IDX Sector Technology', 'UNIVERSE_SECTOR', NULL, NULL, 'Technology', true, DATE '2024-01-02'),
    ('IDXTRANS', 'SECTOR', 'IDX Sector Transportation & Logistic', 'UNIVERSE_SECTOR', NULL, NULL, 'Transportation & Logistic', true, DATE '2024-01-02'),
    ('GSALIM', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'SALIM', NULL, false, DATE '2024-01-02'),
    ('GDANANTARA', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'DANANTARA', NULL, false, DATE '2024-01-02'),
    ('GDJARUM', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'DJARUM', NULL, false, DATE '2024-01-02'),
    ('GSINARMAS', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'SINARMAS', NULL, false, DATE '2024-01-02'),
    ('GPRAJOGO', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'PRAJOGO-PANGESTU', NULL, false, DATE '2024-01-02'),
    ('GTHOHIR', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'THOHIR', NULL, false, DATE '2024-01-02'),
    ('GSANDIAGA', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'SANDIAGA', NULL, false, DATE '2024-01-02'),
    ('GSARATOGA', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'SARATOGA', NULL, false, DATE '2024-01-02'),
    ('GHAJIISAM', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'HAJI-ISAM', NULL, false, DATE '2024-01-02'),
    ('GLOWTUCK', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'LOW-TUCK-KWONG', NULL, false, DATE '2024-01-02'),
    ('GASTRA', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'ASTRA', NULL, false, DATE '2024-01-02'),
    ('GAGOES', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'AGOES-PROJOSASMITO', NULL, false, DATE '2024-01-02'),
    ('GTPRACHMAT', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'TP-RACHMAT', NULL, false, DATE '2024-01-02'),
    ('GPROVIDENT', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'PROVIDENT', NULL, false, DATE '2024-01-02'),
    ('GBAKRIE', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'BAKRIE', NULL, false, DATE '2024-01-02'),
    ('GAGUAN', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'AGUAN', NULL, false, DATE '2024-01-02'),
    ('GHAPSORO', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'HAPSORO', NULL, false, DATE '2024-01-02'),
    ('GEMTEK', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'EMTEK', NULL, false, DATE '2024-01-02'),
    ('GLIPPO', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'LIPPO', NULL, false, DATE '2024-01-02'),
    ('GDANATAMA', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'DANATAMA', NULL, false, DATE '2024-01-02'),
    ('GCTCORP', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'CT-CORP', NULL, false, DATE '2024-01-02'),
    ('GHARITA', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'HARITA', NULL, false, DATE '2024-01-02'),
    ('GTANCORP', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'TANCORP', NULL, false, DATE '2024-01-02'),
    ('GLOKHENGHONG', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'LO-KHENG-HONG', NULL, false, DATE '2024-01-02'),
    ('GCIPUTRA', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'CIPUTRA', NULL, false, DATE '2024-01-02'),
    ('GPANIN', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'PANIN', NULL, false, DATE '2024-01-02'),
    ('GRAJAWALI', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'RAJAWALI', NULL, false, DATE '2024-01-02'),
    ('GMNC', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'MNC', NULL, false, DATE '2024-01-02'),
    ('GHASHIM', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'HASHIM', NULL, false, DATE '2024-01-02'),
    ('GPUNJABI', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'PUNJABI', NULL, false, DATE '2024-01-02'),
    ('GTSOEHARTO', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'TOMMY-SOEHARTO', NULL, false, DATE '2024-01-02'),
    ('GPAM', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'PAM-GROUP', NULL, false, DATE '2024-01-02'),
    ('GTWINATA', 'GROUP', NULL, 'STOCK_LIST', 'KONGLO', 'TOMY-WINATA', NULL, false, DATE '2024-01-02')
) AS v(ticker, entity_kind, name, member_source, list_kind, list_code, sector, has_price, rows_from)
  LEFT JOIN public."Stock_List" l ON l.list_kind = v.list_kind AND l.code = v.list_code;

-- a GROUP row takes its Stock_List name
ALTER TABLE public."Feature_Index_Entity" ALTER COLUMN name SET NOT NULL;

CREATE OR REPLACE FUNCTION public.validate_index_feature_identity()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE e public."Feature_Index_Entity"%ROWTYPE; d date;
BEGIN
 SELECT * INTO e FROM public."Feature_Index_Entity" WHERE ticker = NEW.ticker;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'INDEX feature target % is not in Feature_Index_Entity: register the entity (its kind and member source) before writing its % rows', NEW.ticker, TG_TABLE_NAME;
 END IF;
 IF EXISTS (SELECT 1 FROM public."Universe_Fixed_income" b WHERE b.ticker = NEW.ticker) THEN
  RAISE EXCEPTION 'INDEX feature target requires unambiguous universe index identity: % is also a fixed-income ticker', NEW.ticker;
 END IF;
 IF TG_TABLE_NAME IN ('Feature_01_Stock_Daily_INDEX', 'Feature_04_Technical_Indicator_INDEX') AND NOT e.has_price THEN
  RAISE EXCEPTION '% is a % without a price: it has no % rows (Feature 01 and 04 are computed from a price; a group has Feature 02, 03, 05 and 06 only)', NEW.ticker, e.entity_kind, TG_TABLE_NAME;
 END IF;
 IF e.has_price AND NOT public.is_universe_index(NEW.ticker) THEN
  RAISE EXCEPTION 'INDEX feature target requires unambiguous universe index identity: % is a priced % but not an IDX_Stock_Universe index (add its universe row first, migration 20261115_002)', NEW.ticker, e.entity_kind;
 END IF;
 d := coalesce((to_jsonb(NEW) ->> 'date'), (to_jsonb(NEW) ->> 'trade_date'))::date;
 IF e.rows_from IS NOT NULL AND d < e.rows_from THEN
  RAISE EXCEPTION '% row of % dated % is before its first row date % (Feature_Index_Entity.rows_from): write only from that date; earlier sessions are staging only', TG_TABLE_NAME, NEW.ticker, d, e.rows_from;
 END IF;
 RETURN NEW;
END $function$;

CREATE OR REPLACE FUNCTION public.remark_intraday_sessions(p_timeframe text, p_from date, p_to date)
 RETURNS integer
 LANGUAGE plpgsql
AS $function$
-- Every IDX session from p_from to p_to (the dates of the daily candles of the indexes with intraday bars), oldest first; see the header
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
        -- EXEC-INDEX-GROUP-HISTORY (20261115_001): the calendar is the daily candles of the indexes that have intraday
        -- bars (today IHSG), not of every universe index: a daily-only index must not add or move a session
        cal AS (SELECT DISTINCT p.date AS session_date FROM public."Price_Stock_Indonesia_IDX" p JOIN idx ON idx.ticker = p.ticker
                 WHERE p.timeframe = 'Daily' AND p.is_final AND p.date BETWEEN p_from AND p_to
                   AND EXISTS (SELECT 1 FROM public.price_stock_idx_intraday b WHERE b.ticker = idx.ticker)),
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
$function$;

INSERT INTO public."Table_Catalog"(table_schema, table_name, category, definition, grain, primary_key_columns,
 source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
 readiness_mode, readiness_date_column, observation_date_column, availability_rule, point_in_time_status,
 historical_metadata_method)
VALUES
 ('public', 'Feature_Index_Entity', 'Reference',
  'The entities whose rows the *_INDEX Feature tables may hold, one row per INDEX ticker, and how their members are found: IHSG (MARKET) every source symbol of IDX_Broker_Summary; an INDEX the stocks of its Stockbit list (Stock_List_Member_History, point in time); a SECTOR the stocks of that IDX_Stock_Universe Sector (IDX_Stock_Universe_History, point in time); a GROUP (KONGLO) the stocks of its Stockbit list, without a price. has_price says whether Feature 01 and 04 exist; rows_from is the first date of its feature rows (earlier sessions are staging only).',
  'One INDEX ticker', ARRAY['ticker'], 'Seeded by migration 20261115_001 (EXEC-INDEX-GROUP-HISTORY) from Stock_List, IDX_Stock_Universe sectors and TradingView',
  ARRAY['Stock_List', 'IDX_Stock_Universe'], ARRAY['database/migrations/20261115_001_feature_index_entity.sql'],
  'Changed only by a migration: a new INDEX entity is a new row (its ticker, kind, member source, has_price, rows_from).',
  ARRAY['validate_index_feature_identity()'], 'PARTIAL', 'REFERENCE_STATE', NULL, NULL,
  'Current registry; the members on a date come from the point-in-time history of its source, not from this table.', 'NOT_APPLICABLE',
  'CURRENT_STATE: one row per entity as registered now.')
ON CONFLICT (table_schema, table_name) DO NOTHING;
UPDATE public."Table_Catalog" SET source_tables = array_append(source_tables, 'Feature_Index_Entity'), updated_at = now()
 WHERE table_schema = 'public' AND table_name LIKE '%\_INDEX' AND table_name LIKE 'Feature\_0%'
   AND NOT 'Feature_Index_Entity' = ANY (source_tables);

WITH d(column_name, pk, definition, unit, null_rule) AS (VALUES
 ('ticker', true, 'The INDEX ticker in every *_INDEX table: letters and digits, at most 12 (the terminal-api ticker rule); IHSG, an index code without its dash (BISNIS27), an IDX sector index (IDXENERGY) or G plus the group name (GSALIM).', 'code', 'Never NULL.'),
 ('entity_kind', false, 'MARKET (IHSG), INDEX (a Stockbit index list), SECTOR (an IDX sector index) or GROUP (a Stockbit KONGLO group).', 'category', 'Never NULL.'),
 ('name', false, 'Display name: the index name of the user''s list or TradingView, or the Stockbit group name.', 'text', 'Never NULL.'),
 ('member_source', false, 'How the members are found on a date: ALL_SOURCE_SYMBOLS (every IDX_Broker_Summary symbol, IHSG), STOCK_LIST (Stock_List_Member_History of list_key, point in time) or UNIVERSE_SECTOR (IDX_Stock_Universe stocks of that Sector, point in time).', 'category', 'Never NULL.'),
 ('list_key', false, 'Stock_List.list_key (INDEX:<id> or KONGLO:<id>) whose members define an INDEX or GROUP entity.', 'code', 'NULL for a SECTOR; IHSG names its Stockbit list for reference only (its members are every source symbol, not that list).'),
 ('sector', false, 'IDX_Stock_Universe."Sector" value whose stocks define a SECTOR entity.', 'category', 'NULL unless entity_kind is SECTOR.'),
 ('has_price', false, 'True when the entity has a daily price (a universe index, Price_Stock_Indonesia_IDX) and so Feature 01 and 04 rows; false for a GROUP.', 'boolean', 'Never NULL.'),
 ('rows_from', false, 'First date of the entity''s rows in the *_INDEX tables; sessions before it are computed only as warm-up (window and recursive starts) and never written.', 'date', 'NULL only for IHSG (its full history).'),
 ('created_at', false, 'When the row was created.', 'timestamp', 'Never NULL.'),
 ('updated_at', false, 'When the row last changed.', 'timestamp', 'Never NULL.'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 d.pk, d.definition, NULL, d.unit, d.null_rule, ARRAY['database/migrations/20261115_001_feature_index_entity.sql'], 'PARTIAL'
FROM information_schema.columns c JOIN d ON d.column_name = c.column_name
WHERE c.table_schema = 'public' AND c.table_name = 'Feature_Index_Entity'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

DO $grant$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        GRANT SELECT ON public."Feature_Index_Entity" TO pgweb_reader;
    END IF;
END $grant$;

DO $check$ DECLARE n int; BEGIN
    SELECT count(*) INTO n FROM public."Feature_Index_Entity";
    IF n <> 77 OR (SELECT count(*) FROM public."Feature_Index_Entity" WHERE entity_kind = 'INDEX') <> 32
       OR (SELECT count(*) FROM public."Feature_Index_Entity" WHERE entity_kind = 'SECTOR') <> 11
       OR (SELECT count(*) FROM public."Feature_Index_Entity" WHERE entity_kind = 'GROUP') <> 33 THEN
        RAISE EXCEPTION 'expected 77 entities (IHSG, 32 INDEX, 11 SECTOR, 33 GROUP), found %', n;
    END IF;
    -- every Stockbit list is an entity exactly once, and every sector is a universe sector of stocks
    SELECT count(*) INTO n FROM public."Stock_List" l
     WHERE NOT EXISTS (SELECT 1 FROM public."Feature_Index_Entity" e WHERE e.list_key = l.list_key);
    IF n > 0 THEN RAISE EXCEPTION '% Stock_List rows have no entity', n; END IF;
    SELECT count(*) INTO n FROM public."Feature_Index_Entity" e WHERE e.entity_kind = 'SECTOR'
       AND NOT EXISTS (SELECT 1 FROM public."IDX_Stock_Universe" u WHERE u."Sector" = e.sector AND u."Security Type" = 'stock');
    IF n > 0 THEN RAISE EXCEPTION '% sector entities name no stock sector of IDX_Stock_Universe', n; END IF;
    -- a new ticker is never a stock or fund code (an INDEX row of a stock would merge two meanings)
    SELECT count(*) INTO n FROM public."Feature_Index_Entity" e JOIN public."IDX_Stock_Universe" u ON u."Ticker" = e.ticker
     WHERE u."Security Type" <> 'index';
    IF n > 0 THEN RAISE EXCEPTION '% entity tickers are stock or fund codes of IDX_Stock_Universe', n; END IF;
    SELECT count(*) INTO n FROM information_schema.columns c WHERE c.table_schema = 'public' AND c.table_name = 'Feature_Index_Entity'
       AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_schema = 'public' AND k.table_name = c.table_name
                       AND k.column_name = c.column_name);
    IF n > 0 THEN RAISE EXCEPTION '% columns of Feature_Index_Entity lack a Column_Catalog row', n; END IF;
END $check$;

COMMIT;

-- Rollback (only with the user's go; nothing else depends on the table until the INDEX job runs):
-- BEGIN;
-- DELETE FROM public."Column_Catalog" WHERE table_schema = 'public' AND table_name = 'Feature_Index_Entity';
-- UPDATE public."Table_Catalog" SET source_tables = array_remove(source_tables, 'Feature_Index_Entity') WHERE table_name LIKE '%\_INDEX';
-- DELETE FROM public."Table_Catalog" WHERE table_schema = 'public' AND table_name = 'Feature_Index_Entity';
-- the two function bodies of 20261025 (validate_index_feature_identity) and of the intraday migrations
-- (remark_intraday_sessions), as read on dev 2026-11-15: verification/index_group_history/functions_before_20261115_001.sql;
-- DROP TABLE public."Feature_Index_Entity";
-- COMMIT;
