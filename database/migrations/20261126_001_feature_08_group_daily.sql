-- EXEC-SECTOR-ANALYSIS S1 (user decisions UD66 A-J and UD67 "1A 2A 3 go", 2026-11-26; build contract
-- verification/sector_analysis/CONTRACT.md section 2): the daily aggregates of the Sector Analysis page.
--
-- What it holds
--   "Feature_08_Group_Daily": one row per market date and group. Groups: MARKET (one row, group_name = the MARKET
--     ticker of Feature_Index_Entity, today IHSG: every common stock, the "Undefined" sector included), SECTOR (the 11
--     SECTOR entities of Feature_Index_Entity, group_name and sector = the IDX_Stock_Universe."Sector" value) and INDUSTRY
--     (every IDX_Stock_Universe."Industry" of the common stocks except 'Undefined', sector = its sector). Per group:
--     members with a final daily close, the EMA50/EMA200 breadth of Feature 04, advancers/unchanged/decliners, the sum
--     of the weights, the weighted daily return and a chain-linked index level.
--   public.feature_08_weight(date) -> (ticker, weight, weight_basis): the ONE weight basis of the page (decision D1,
--     "d1 but design plugablebuntuk ganti pakai marketcap"). Today public.overview_stock_size(date), basis adv20_value
--     (the Overview's 20-session average traded value). Market cap later = a new version of this function (new basis
--     name), then a recompute (the backfill job); the files carry the basis and the page reads its label.
--     Interpretation of the contract (it names (ticker, weight)): the function also returns the basis name, as
--     overview_stock_size does, so the basis travels with the weights and is never written twice.
--   public.refresh_feature_08_day(date): computes one market date (idempotent upsert; the rows of groups no longer in the
--     current classification are deleted for that date). Called by feature-04-worker after a daily run is finalized
--     (apps/feature-04-worker/worker.py refresh_feature_08) and by the backfill job
--     (verification/sector_analysis/db/backfill/), always in date order: the level is chain-linked.
--
-- Conventions (CONTRACT.md section 2; SECTOR_FORMULAS.md explains them in plain Indonesian)
--   * Membership is the current classification (IDX_Stock_Universe as of the refresh), as the Overview and Feature 01:
--     history built from today's membership has survivorship and reclassification bias (point_in_time_status PARTIAL).
--   * Breadth (n_ema50, above_ema50, n_ema200, above_ema200) is counted over the group's Feature 04 rows of the date
--     (timeframe Daily, asset_type equity), close > ema with Feature 04's own close, NULL ema not counted: on the
--     MARKET row exactly the Overview's BREADTH_SQL (apps/terminal-publisher/overview.py), the same counts and NULL
--     handling (measured equal on dev for 2026-11-25: 837/133/829/132).
--   * A/U/D compares each member's final close with its own previous final close (the latest one before the date); a
--     member without a previous close (a new listing) is in none of the three.
--   * ret_1d_w = 100 x sum(w_i(t-1) x (close_i(t) / prev_close_i - 1)) / sum(w_i(t-1)) over the members with both closes
--     and a weight on the previous market date t-1: a date's return never uses that date's own weights.
--   * index_level: the group's first row = 100; then level(t) = level(last non-NULL) x (1 + ret_1d_w / 100); NULL on a
--     date whose ret_1d_w is NULL (no member with both closes and a weight), the level carries over it. A date is refused
--     when the MARKET row of the previous market date is missing while older rows exist (a gap would skip a return).
--
-- Size (ERRORS Part A item 25): about 70 groups x 1,407 market dates (2021-01-25 to 2026-11-26) = 98,500 rows of about
-- 150 bytes, about 15 MB plus a 5 MB primary key. A view cannot replace it: the same counts read from Feature 04
-- (2.5 GB, one date's rows spread over the table) took 11 s for 60 dates and timed out for 300 (overview.py header).
-- Indexes: the primary key (date, group_kind, group_name) only. Every reader filters by date: the publisher reads its 300
-- series dates (a range) and the refresh one date plus each group's previous row (a backward scan of the key from the
-- date, about 70 entries). Measured read-only on dev (EXPLAIN ANALYZE, verification/sector_analysis/db/EXPLAIN.md): the
-- refresh's SELECT part 37-66 ms warm, 0.3-1.3 s with the pages read from disk (2021-03-15 1.26 s, 29,096 pages), so
-- the backfill of 1,407 dates takes about 10-30 minutes. No other index.
--
-- Catalog: Table_Catalog (category Feature, VERIFIED), Column_Catalog and Feature_Catalog v1 for every column
-- (CALCULATION_VERIFIED on the rehearsal's synthetic proofs and the dev measurement; the backfill job's independent
-- recount and verification/sector_analysis/db/validate_feature_08.py check the applied rows). No
-- Feature_Relationship_Catalog row: a group-grain row has no safe join to a stock-grain Feature. Not exposed to the AI
-- (no AI_* rows, no grant to market_ai_sql_reader).
-- Grants: SELECT to terminal_market_reader (the publisher) and pgweb_reader; EXECUTE of feature_08_weight to both;
-- EXECUTE of refresh_feature_08_day revoked from PUBLIC and granted to the role that applies this migration, which must
-- own Feature_04_Technical_Indicator: feature-04-worker connects with ${{Postgres.DATABASE_URL}}, that owner role
-- (apps/feature-04-worker/README.md).
-- Expand-only: a new table and two new functions; nothing the live site's code reads changes.
-- Rehearsed on a local PostgreSQL 16 (verification/sector_analysis/db/REHEARSAL.md).
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_08_Group_Daily"') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature_08_Group_Daily already exists: reconcile before applying';
    END IF;
    IF to_regprocedure('public.overview_stock_size(date)') IS NULL THEN
        RAISE EXCEPTION 'public.overview_stock_size(date) is required first (migration 20261115_020)';
    END IF;
    IF to_regclass('public."Price_Stock_Indonesia_IDX"') IS NULL OR to_regclass('public."Feature_04_Technical_Indicator"') IS NULL
       OR to_regclass('public."IDX_Stock_Universe"') IS NULL OR to_regclass('public."Feature_Index_Entity"') IS NULL THEN
        RAISE EXCEPTION 'the price table, Feature 04, IDX_Stock_Universe and Feature_Index_Entity are required first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_market_reader')
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        RAISE EXCEPTION 'roles terminal_market_reader and pgweb_reader are required';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Index_Entity" WHERE entity_kind = 'MARKET') <> 1 THEN
        RAISE EXCEPTION 'Feature_Index_Entity must name exactly one MARKET entity (the market and its calendar)';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Index_Entity" WHERE entity_kind = 'SECTOR') <> 11 THEN
        RAISE EXCEPTION 'Feature_Index_Entity must name the 11 IDX sectors (entity_kind SECTOR)';
    END IF;
    IF (SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'Feature_04_Technical_Indicator')
       IS DISTINCT FROM current_user THEN
        RAISE EXCEPTION 'apply this migration as the owner of Feature_04_Technical_Indicator (the role feature-04-worker connects as): it receives EXECUTE of refresh_feature_08_day';
    END IF;
END
$preflight$;

CREATE TABLE public."Feature_08_Group_Daily" (
    date date NOT NULL,
    group_kind text NOT NULL,
    group_name text NOT NULL,
    sector text,
    members integer NOT NULL,
    n_ema50 integer NOT NULL,
    above_ema50 integer NOT NULL,
    n_ema200 integer NOT NULL,
    above_ema200 integer NOT NULL,
    adv_1d integer NOT NULL,
    unch_1d integer NOT NULL,
    dec_1d integer NOT NULL,
    weight_basis text,
    weight_sum double precision,
    ret_1d_w double precision,
    index_level double precision,
    calculation_version text NOT NULL,
    calculated_at timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT "Feature_08_Group_Daily_pkey" PRIMARY KEY (date, group_kind, group_name),
    CONSTRAINT "Feature_08_Group_Daily_kind_check" CHECK (group_kind = ANY (ARRAY['MARKET', 'SECTOR', 'INDUSTRY'])),
    CONSTRAINT "Feature_08_Group_Daily_name_check" CHECK (btrim(group_name) <> ''),
    CONSTRAINT "Feature_08_Group_Daily_sector_check" CHECK (
        (group_kind = 'MARKET' AND sector IS NULL) OR (group_kind = 'SECTOR' AND sector = group_name)
        OR (group_kind = 'INDUSTRY' AND sector IS NOT NULL)),
    CONSTRAINT "Feature_08_Group_Daily_counts_check" CHECK (
        members >= 0 AND n_ema50 >= 0 AND n_ema200 >= 0 AND above_ema50 BETWEEN 0 AND n_ema50
        AND above_ema200 BETWEEN 0 AND n_ema200 AND adv_1d >= 0 AND unch_1d >= 0 AND dec_1d >= 0
        AND adv_1d + unch_1d + dec_1d <= members),
    CONSTRAINT "Feature_08_Group_Daily_weight_check" CHECK (weight_sum IS NULL OR (weight_sum >= 0 AND weight_basis IS NOT NULL)),
    CONSTRAINT "Feature_08_Group_Daily_values_check" CHECK (
        (ret_1d_w IS NULL OR ret_1d_w >= -100) AND (index_level IS NULL OR index_level >= 0)),
    CONSTRAINT "Feature_08_Group_Daily_version_check" CHECK (btrim(calculation_version) <> '')
);
COMMENT ON TABLE public."Feature_08_Group_Daily" IS
 'EXEC-SECTOR-ANALYSIS: per market date and group (MARKET, the 11 IDX sectors, the IDX-IC industries), the members with '
 'a final close, the EMA50/EMA200 breadth of Feature 04, advancers/unchanged/decliners, the weight sum, the weighted '
 'daily return and a chain-linked index level (first date 100). Weights from feature_08_weight (adv20_value today); '
 'membership is the current classification. Written by refresh_feature_08_day(date).';

CREATE FUNCTION public.feature_08_weight(p_date date)
RETURNS TABLE (ticker text, weight double precision, weight_basis text)
LANGUAGE sql STABLE
AS $function$
    -- the one weight basis of Feature 08 and the Sector Analysis page (decision D1): today the Overview's tile size,
    -- the 20-session average traded value (adv20_value); a market-cap basis replaces this body and its basis name
    SELECT s.ticker, s.size_value, s.size_basis FROM public.overview_stock_size(p_date) AS s
$function$;
COMMENT ON FUNCTION public.feature_08_weight(date) IS
    'EXEC-SECTOR-ANALYSIS D1: the weight of every ticker on p_date and its basis name, the one source of every weight of the Sector Analysis page (industry index, treemap area, top-N by size, dot size). Today overview_stock_size(p_date): adv20_value, the 20-session average traded value. A market-cap basis is a new version of this function, then a recompute of Feature_08_Group_Daily.';

CREATE FUNCTION public.refresh_feature_08_day(p_date date)
RETURNS integer
LANGUAGE plpgsql
AS $function$
DECLARE
    v_market text;
    v_prev date;
    v_basis text;
    v_bases integer;
    v_rows integer;
BEGIN
    IF p_date IS NULL THEN
        RAISE EXCEPTION 'refresh_feature_08_day: a market date is required';
    END IF;
    -- one refresh at a time (the worker and the backfill job): the level of a date reads the previous date's row
    PERFORM pg_advisory_xact_lock(hashtext('feature_08_group_daily_refresh'));
    SELECT e.ticker INTO v_market FROM public."Feature_Index_Entity" AS e WHERE e.entity_kind = 'MARKET';
    IF v_market IS NULL THEN
        RAISE EXCEPTION 'refresh_feature_08_day(%): Feature_Index_Entity has no MARKET entity (the market and its calendar)', p_date;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public."Price_Stock_Indonesia_IDX" AS p WHERE p.ticker = v_market AND p.timeframe = 'Daily'
                   AND p.is_final AND p.date = p_date) THEN
        RAISE EXCEPTION 'refresh_feature_08_day(%): not a market date: % has no final daily close on it; pass a date of the market calendar', p_date, v_market;
    END IF;
    SELECT max(p.date) INTO v_prev FROM public."Price_Stock_Indonesia_IDX" AS p
    WHERE p.ticker = v_market AND p.timeframe = 'Daily' AND p.is_final AND p.date < p_date;
    IF EXISTS (SELECT 1 FROM public."Feature_08_Group_Daily" AS h WHERE h.group_kind = 'MARKET' AND h.date < p_date)
       AND NOT EXISTS (SELECT 1 FROM public."Feature_08_Group_Daily" AS h WHERE h.group_kind = 'MARKET' AND h.date = v_prev) THEN
        RAISE EXCEPTION 'refresh_feature_08_day(%): the previous market date % has no row while older dates have: refresh the dates in order from the first missing one (the index level is chain-linked)', p_date, v_prev;
    END IF;
    SELECT count(DISTINCT w.weight_basis), max(w.weight_basis) INTO v_bases, v_basis FROM public.feature_08_weight(p_date) AS w;
    IF v_bases > 1 THEN
        RAISE EXCEPTION 'refresh_feature_08_day(%): feature_08_weight returned % weight bases; one basis per date is required', p_date, v_bases;
    END IF;

    -- the rows of a group no longer in the current classification are not kept for this date
    DELETE FROM public."Feature_08_Group_Daily" AS h
    WHERE h.date = p_date
      AND NOT ((h.group_kind = 'MARKET' AND h.group_name = v_market)
               OR (h.group_kind = 'SECTOR' AND h.group_name IN (SELECT e.sector FROM public."Feature_Index_Entity" AS e
                                                                WHERE e.entity_kind = 'SECTOR'))
               OR (h.group_kind = 'INDUSTRY' AND h.group_name IN (SELECT s."Industry" FROM public."IDX_Stock_Universe" AS s
                                                                  WHERE s."Security Type" = 'stock' AND s."Industry" <> 'Undefined')));

    -- per stock first (MATERIALIZED: one lookup per stock, then hash joins; inlined, the planner repeated the price and
    -- Feature 04 lookups per group membership and took 2.3 s for an old date instead of 66 ms, measured on dev)
    WITH u AS MATERIALIZED (
        SELECT s."Ticker"::text AS ticker, s."Sector"::text AS sector, s."Industry"::text AS industry
        FROM public."IDX_Stock_Universe" AS s WHERE s."Security Type" = 'stock'
    ), sec AS MATERIALIZED (
        SELECT e.sector FROM public."Feature_Index_Entity" AS e WHERE e.entity_kind = 'SECTOR'
    ), ind AS MATERIALIZED (   -- an industry's sector: the sector of most of its stocks (each has one sector on dev)
        SELECT u.industry, mode() WITHIN GROUP (ORDER BY u.sector) AS sector FROM u
        WHERE u.industry IS NOT NULL AND u.industry <> 'Undefined' GROUP BY u.industry
    ), grp AS (
        SELECT 'MARKET'::text AS group_kind, v_market AS group_name, NULL::text AS sector
        UNION ALL SELECT 'SECTOR', sec.sector, sec.sector FROM sec
        UNION ALL SELECT 'INDUSTRY', ind.industry, ind.sector FROM ind
    ), gm AS (
        SELECT 'MARKET'::text AS group_kind, v_market AS group_name, u.ticker FROM u
        UNION ALL SELECT 'SECTOR', u.sector, u.ticker FROM u JOIN sec ON sec.sector = u.sector
        UNION ALL SELECT 'INDUSTRY', u.industry, u.ticker FROM u JOIN ind ON ind.industry = u.industry
    ), st AS MATERIALIZED (     -- the members: a final daily close on the date, and the stock's own previous final close
        SELECT p.ticker::text AS ticker, p.close::double precision AS close, pc.close AS prev_close
        FROM public."Price_Stock_Indonesia_IDX" AS p
        LEFT JOIN LATERAL (SELECT q.close::double precision AS close FROM public."Price_Stock_Indonesia_IDX" AS q
                           WHERE q.ticker = p.ticker AND q.timeframe = 'Daily' AND q.is_final AND q.date < p_date
                           ORDER BY q.date DESC LIMIT 1) AS pc ON true
        WHERE p.date = p_date AND p.timeframe = 'Daily' AND p.is_final AND p.ticker IN (SELECT u.ticker FROM u)
    ), f4 AS MATERIALIZED (     -- the Overview's BREADTH_SQL rows (Feature 04's own close against its EMAs)
        SELECT t.ticker::text AS ticker, t.close, t.ema_50, t.ema_200 FROM public."Feature_04_Technical_Indicator" AS t
        WHERE t.trade_date = p_date AND t.timeframe = 'Daily' AND t.asset_type = 'equity' AND t.ticker IN (SELECT u.ticker FROM u)
    ), w0 AS MATERIALIZED (
        SELECT w.ticker, w.weight FROM public.feature_08_weight(p_date) AS w
    ), w1 AS MATERIALIZED (     -- the weights of the previous market date (no date: no row)
        SELECT w.ticker, w.weight FROM public.feature_08_weight(v_prev) AS w WHERE v_prev IS NOT NULL
    ), sx AS MATERIALIZED (
        SELECT u.ticker, st.close, st.prev_close, f4.close AS f4_close, f4.ema_50, f4.ema_200, w0.weight AS w0, w1.weight AS w1
        FROM u
        LEFT JOIN st ON st.ticker = u.ticker
        LEFT JOIN f4 ON f4.ticker = u.ticker
        LEFT JOIN w0 ON w0.ticker = st.ticker
        LEFT JOIN w1 ON w1.ticker = st.ticker
    ), agg AS (
        SELECT g.group_kind, g.group_name, g.sector,
               count(x.close)::integer AS members,
               count(x.ema_50)::integer AS n_ema50,
               (count(*) FILTER (WHERE x.f4_close > x.ema_50))::integer AS above_ema50,
               count(x.ema_200)::integer AS n_ema200,
               (count(*) FILTER (WHERE x.f4_close > x.ema_200))::integer AS above_ema200,
               (count(*) FILTER (WHERE x.close > x.prev_close))::integer AS adv_1d,
               (count(*) FILTER (WHERE x.close = x.prev_close))::integer AS unch_1d,
               (count(*) FILTER (WHERE x.close < x.prev_close))::integer AS dec_1d,
               -- sums in ticker order: the same inputs give the same bits whatever the join order (a re-run of a date
               -- leaves its row equal, so the publisher's content fingerprint does not move)
               sum(x.w0 ORDER BY x.ticker) AS weight_sum,
               100 * sum(x.w1 * (x.close / x.prev_close - 1) ORDER BY x.ticker) FILTER (WHERE x.prev_close > 0 AND x.w1 > 0)
                   / nullif(sum(x.w1 ORDER BY x.ticker) FILTER (WHERE x.prev_close > 0 AND x.w1 > 0), 0) AS ret_1d_w
        FROM grp AS g
        LEFT JOIN gm ON gm.group_kind = g.group_kind AND gm.group_name = g.group_name
        LEFT JOIN sx AS x ON x.ticker = gm.ticker
        GROUP BY g.group_kind, g.group_name, g.sector
    ), lv AS (
        SELECT a.*,
               EXISTS (SELECT 1 FROM public."Feature_08_Group_Daily" AS h
                       WHERE h.group_kind = a.group_kind AND h.group_name = a.group_name AND h.date < p_date) AS has_prev,
               (SELECT h.index_level FROM public."Feature_08_Group_Daily" AS h
                WHERE h.group_kind = a.group_kind AND h.group_name = a.group_name AND h.date < p_date
                  AND h.index_level IS NOT NULL
                ORDER BY h.date DESC LIMIT 1) AS prev_level
        FROM agg AS a
    )
    INSERT INTO public."Feature_08_Group_Daily" AS f (date, group_kind, group_name, sector, members, n_ema50, above_ema50,
        n_ema200, above_ema200, adv_1d, unch_1d, dec_1d, weight_basis, weight_sum, ret_1d_w, index_level,
        calculation_version, calculated_at)
    SELECT p_date, lv.group_kind, lv.group_name, lv.sector, lv.members, lv.n_ema50, lv.above_ema50, lv.n_ema200,
           lv.above_ema200, lv.adv_1d, lv.unch_1d, lv.dec_1d,
           CASE WHEN lv.weight_sum IS NULL THEN NULL ELSE v_basis END, lv.weight_sum, lv.ret_1d_w,
           CASE WHEN NOT lv.has_prev THEN 100
                WHEN lv.ret_1d_w IS NULL THEN NULL
                ELSE coalesce(lv.prev_level, 100) * (1 + lv.ret_1d_w / 100) END,
           'v1', clock_timestamp()
    FROM lv
    ON CONFLICT (date, group_kind, group_name) DO UPDATE SET
        sector = EXCLUDED.sector, members = EXCLUDED.members, n_ema50 = EXCLUDED.n_ema50,
        above_ema50 = EXCLUDED.above_ema50, n_ema200 = EXCLUDED.n_ema200, above_ema200 = EXCLUDED.above_ema200,
        adv_1d = EXCLUDED.adv_1d, unch_1d = EXCLUDED.unch_1d, dec_1d = EXCLUDED.dec_1d,
        weight_basis = EXCLUDED.weight_basis, weight_sum = EXCLUDED.weight_sum, ret_1d_w = EXCLUDED.ret_1d_w,
        index_level = EXCLUDED.index_level, calculation_version = EXCLUDED.calculation_version,
        calculated_at = EXCLUDED.calculated_at;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END
$function$;
COMMENT ON FUNCTION public.refresh_feature_08_day(date) IS
    'EXEC-SECTOR-ANALYSIS: computes Feature_08_Group_Daily for one market date (every group of the current classification; idempotent upsert) and returns the rows written. Run the dates in order: the index level is chain-linked to the previous row of each group, and a date whose previous market date has no MARKET row is refused while older rows exist.';

REVOKE ALL ON FUNCTION public.refresh_feature_08_day(date) FROM PUBLIC;
DO $grant$ BEGIN
    EXECUTE format('GRANT EXECUTE ON FUNCTION public.refresh_feature_08_day(date) TO %I', current_user);
END $grant$;
GRANT SELECT ON public."Feature_08_Group_Daily" TO terminal_market_reader, pgweb_reader;
GRANT EXECUTE ON FUNCTION public.feature_08_weight(date) TO terminal_market_reader, pgweb_reader;

-- ---------------------------------------------------------------------------------------------------------------
-- catalog
INSERT INTO public."Table_Catalog" (table_schema, table_name, category, definition, grain, primary_key_columns,
    source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column, availability_rule, point_in_time_status,
    historical_metadata_method)
VALUES ('public', 'Feature_08_Group_Daily', 'Feature',
    'Sector Analysis group aggregates per market date: for the market (IHSG, every common stock), the 11 IDX sectors and the IDX-IC industries, the members with a final daily close, the stocks above their EMA50 and EMA200 (Feature 04), advancers, unchanged and decliners, the sum of the members'' weights (20-day average traded value today), the weighted daily return and a chain-linked index level (first date 100). Sector breadth, industry index, EMA50 EMA200 breadth history.',
    'One row per market date and group (group_kind MARKET, SECTOR or INDUSTRY, group_name)',
    ARRAY['date', 'group_kind', 'group_name'],
    'Derived from the final daily prices, Feature 04 and the current stock universe classification',
    ARRAY['Price_Stock_Indonesia_IDX', 'Feature_04_Technical_Indicator', 'IDX_Stock_Universe', 'Feature_Index_Entity'],
    ARRAY['database/migrations/20261126_001_feature_08_group_daily.sql', 'apps/feature-04-worker/worker.py',
          'verification/sector_analysis/db/backfill/backfill_job.py', 'apps/terminal-publisher/sector.py'],
    'refresh_feature_08_day(date) after feature-04-worker finalizes an equity run (the correction window of market dates up to the newest, in date order); the backfill job fills every market date from 2021-01-25 in order. A new weight basis needs a recompute of every date.',
    ARRAY['refresh_feature_08_day(date)', 'feature_08_weight(date)'], 'VERIFIED', 'DATA_DATE', 'date', 'date',
    'Available after Feature 04 of the date is complete (the worker refreshes the date when its daily run is finalized); prices are final daily closes.',
    'PARTIAL',
    'CURRENT_STATE membership: every date groups the stocks by today''s IDX_Stock_Universe Sector and Industry, so history has survivorship and reclassification bias.');

WITH d(column_name, pk, definition, unit, null_rule) AS (VALUES
 ('date', true, 'Market date: a date with a final daily close of the MARKET entity (IHSG).', 'date', 'Never NULL.'),
 ('group_kind', true, 'MARKET (every common stock), SECTOR (an IDX sector) or INDUSTRY (an IDX-IC industry).', 'category', 'Never NULL.'),
 ('group_name', true, 'The group: the market ticker (IHSG) for MARKET, the IDX_Stock_Universe Sector value for SECTOR, the Industry value for INDUSTRY.', 'category', 'Never NULL.'),
 ('sector', false, 'The sector of the group: the sector itself for SECTOR, the industry''s sector for INDUSTRY.', 'category', 'NULL for MARKET.'),
 ('members', false, 'Common stocks of the group (current classification) with a final daily close on the date.', 'stocks', 'Never NULL; 0 when no member traded.'),
 ('n_ema50', false, 'Members with a Feature 04 Daily row whose ema_50 is not NULL on the date (the breadth denominator).', 'stocks', 'Never NULL.'),
 ('above_ema50', false, 'Of n_ema50, the stocks whose Feature 04 close is above ema_50.', 'stocks', 'Never NULL.'),
 ('n_ema200', false, 'Members with a Feature 04 Daily row whose ema_200 is not NULL on the date.', 'stocks', 'Never NULL.'),
 ('above_ema200', false, 'Of n_ema200, the stocks whose Feature 04 close is above ema_200.', 'stocks', 'Never NULL.'),
 ('adv_1d', false, 'Members whose close is above their own previous final close.', 'stocks', 'Never NULL.'),
 ('unch_1d', false, 'Members whose close equals their own previous final close.', 'stocks', 'Never NULL.'),
 ('dec_1d', false, 'Members whose close is below their own previous final close.', 'stocks', 'Never NULL.'),
 ('weight_basis', false, 'The weight basis of feature_08_weight on the date: adv20_value (20-session average traded value) today.', 'category', 'NULL when no member has a weight (weight_sum NULL).'),
 ('weight_sum', false, 'Sum of the members'' weights on the date (feature_08_weight; IDR per day for adv20_value).', 'IDR', 'NULL when no member has a weight.'),
 ('ret_1d_w', false, 'Weighted daily return in percent: sum of previous-date weight x (close / previous close - 1) over the members with both closes and a weight, divided by the sum of those weights, x 100.', 'percent', 'NULL when no member has both closes and a previous-date weight.'),
 ('index_level', false, 'Chain-linked group index: 100 on the group''s first date, then the last level x (1 + ret_1d_w / 100).', 'index points', 'NULL on a date whose ret_1d_w is NULL (the level carries over it); 100 on the first date.'),
 ('calculation_version', false, 'Version of the refresh formula (v1).', 'text', 'Never NULL.'),
 ('calculated_at', false, 'When refresh_feature_08_day wrote the row.', 'timestamp', 'Never NULL.'))
INSERT INTO public."Column_Catalog" (table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
    default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
       d.pk, d.definition, 'Feature_Catalog active semantic version', d.unit, d.null_rule,
       ARRAY['database/migrations/20261126_001_feature_08_group_daily.sql', 'verification/sector_analysis/db/REHEARSAL.md'],
       'VERIFIED'
FROM information_schema.columns AS c JOIN d ON d.column_name = c.column_name
WHERE c.table_schema = 'public' AND c.table_name = 'Feature_08_Group_Daily';

WITH d(column_name, category, role, aggs, ranking, filterable, groupable, calculation, source_columns, lookback, unit,
       null_rule, interpretation, use, misuse) AS (VALUES
 ('date', 'Identity', 'IDENTITY', ARRAY['COUNT', 'COUNT_DISTINCT'], 'NOT_APPLICABLE', true, true,
  'Price_Stock_Indonesia_IDX.date of a final Daily row of the MARKET entity (Feature_Index_Entity)', 'date', '1 session', 'date', 'Never NULL.',
  'The market date the group figures describe.', 'Filter or join by date; every group has a row on every market date it is refreshed for.',
  'Not a stock''s own trading date: a group row exists even when no member traded (members 0).'),
 ('group_kind', 'Identity', 'IDENTITY', ARRAY['COUNT', 'COUNT_DISTINCT'], 'NOT_APPLICABLE', true, true,
  'MARKET, SECTOR or INDUSTRY', 'Feature_Index_Entity.entity_kind, IDX_Stock_Universe.Sector, Industry', '1 session', 'category', 'Never NULL.',
  'Which kind of group the row aggregates.', 'Always filter one group_kind: the market, sector and industry rows overlap (a stock is in all three).',
  'Never sum across group kinds: every stock is counted once per kind.'),
 ('group_name', 'Identity', 'IDENTITY', ARRAY['COUNT', 'COUNT_DISTINCT'], 'NOT_APPLICABLE', true, true,
  'MARKET: the MARKET ticker; SECTOR: IDX_Stock_Universe.Sector; INDUSTRY: IDX_Stock_Universe.Industry', 'Ticker, Sector, Industry', '1 session', 'category', 'Never NULL.',
  'The group the row describes, by today''s classification.', 'Join to the page''s sector list by name; the sector index ticker is in Feature_Index_Entity (entity_kind SECTOR).',
  'Membership is current-state: a stock reclassified later is counted in its new group on every past date.'),
 ('sector', 'Identity', 'DIMENSION', ARRAY['COUNT', 'COUNT_DISTINCT'], 'NOT_APPLICABLE', true, true,
  'SECTOR: group_name; INDUSTRY: the most common Sector of its stocks', 'IDX_Stock_Universe.Sector', '1 session', 'category', 'NULL for MARKET.',
  'The sector an industry belongs to.', 'Group the industry rows by sector.', 'NULL on the MARKET row; not a member filter.'),
 ('members', 'Metadata', 'MEASURE', ARRAY['AVG', 'MIN', 'MAX'], 'CONTEXTUAL', true, false,
  'count of the group''s common stocks with a final Daily close on the date', 'Price_Stock_Indonesia_IDX.close', '1 session', 'stocks', 'Never NULL.',
  'How many stocks the group''s figures rest on that day.', 'Read beside every share and return: a figure of an industry with 1 or 2 members is one stock''s.',
  'Not the number of listed stocks: a suspended stock without a close is not a member that day.'),
 ('n_ema50', 'Price Positioning', 'MEASURE', ARRAY['AVG', 'MIN', 'MAX'], 'CONTEXTUAL', true, false,
  'count(Feature_04.ema_50) over the group''s stocks, Daily, equity, on the date', 'Feature_04_Technical_Indicator.ema_50', '50 sessions (EMA warm-up)', 'stocks', 'Never NULL.',
  'The denominator of the EMA50 breadth.', 'Divide above_ema50 by it for the percent above EMA50 (the Overview''s market breadth).',
  'Smaller than members when a stock has no EMA50 yet (new listing) or Feature 04 is not complete for the date.'),
 ('above_ema50', 'Price Positioning', 'MEASURE', ARRAY['AVG', 'MIN', 'MAX'], 'HIGHER', true, false,
  'count(*) FILTER (WHERE close > ema_50) of Feature 04 over the group''s stocks on the date', 'Feature_04_Technical_Indicator.close, ema_50', '50 sessions (EMA warm-up)', 'stocks', 'Never NULL.',
  'How many of the group''s stocks close above their 50-session EMA: a breadth measure of the group''s trend.', 'Use 100 x above_ema50 / n_ema50 and compare it over time or across groups.',
  'A count, not a share: groups differ in size; equal close and EMA counts as not above.'),
 ('n_ema200', 'Price Positioning', 'MEASURE', ARRAY['AVG', 'MIN', 'MAX'], 'CONTEXTUAL', true, false,
  'count(Feature_04.ema_200) over the group''s stocks, Daily, equity, on the date', 'Feature_04_Technical_Indicator.ema_200', '200 sessions (EMA warm-up)', 'stocks', 'Never NULL.',
  'The denominator of the EMA200 breadth.', 'Divide above_ema200 by it for the percent above EMA200.', 'Stocks with fewer than 200 sessions have no EMA200 and are not counted.'),
 ('above_ema200', 'Price Positioning', 'MEASURE', ARRAY['AVG', 'MIN', 'MAX'], 'HIGHER', true, false,
  'count(*) FILTER (WHERE close > ema_200) of Feature 04 over the group''s stocks on the date', 'Feature_04_Technical_Indicator.close, ema_200', '200 sessions (EMA warm-up)', 'stocks', 'Never NULL.',
  'How many of the group''s stocks close above their 200-session EMA: the long-trend breadth.', 'Use 100 x above_ema200 / n_ema200.', 'A count, not a share.'),
 ('adv_1d', 'Return', 'MEASURE', ARRAY['AVG', 'MIN', 'MAX'], 'HIGHER', true, false,
  'count of members with close > their own previous final close', 'Price_Stock_Indonesia_IDX.close', '2 own sessions', 'stocks', 'Never NULL.',
  'Advancers of the day.', 'Compare with dec_1d (advance/decline) and members.', 'A new listing has no previous close and is in none of adv, unch, dec.'),
 ('unch_1d', 'Return', 'MEASURE', ARRAY['AVG', 'MIN', 'MAX'], 'CONTEXTUAL', true, false,
  'count of members with close = their own previous final close', 'Price_Stock_Indonesia_IDX.close', '2 own sessions', 'stocks', 'Never NULL.',
  'Unchanged stocks of the day.', 'Read with adv_1d and dec_1d.', 'Many illiquid stocks close unchanged; not a sign of balance.'),
 ('dec_1d', 'Return', 'MEASURE', ARRAY['AVG', 'MIN', 'MAX'], 'LOWER', true, false,
  'count of members with close < their own previous final close', 'Price_Stock_Indonesia_IDX.close', '2 own sessions', 'stocks', 'Never NULL.',
  'Decliners of the day.', 'Compare with adv_1d.', 'A count over the stock''s own previous close: after a suspension it spans several market days.'),
 ('weight_basis', 'Metadata', 'DIMENSION', ARRAY['COUNT', 'COUNT_DISTINCT'], 'NOT_APPLICABLE', true, true,
  'feature_08_weight(date).weight_basis (adv20_value today)', 'overview_stock_size(date).size_basis', '20 sessions', 'category', 'NULL when no member has a weight.',
  'Names what the weights are, so a page labels them.', 'Check it before comparing weight_sum or ret_1d_w across dates: a new basis changes both.',
  'Not market capitalisation today: adv20_value is a liquidity measure.'),
 ('weight_sum', 'Volume', 'MEASURE', ARRAY['AVG', 'MIN', 'MAX'], 'CONTEXTUAL', true, false,
  'sum(feature_08_weight(date).weight) over the members', 'Price_Stock_Indonesia_IDX.close x volume (20 sessions)', '20 market sessions', 'IDR', 'NULL when no member has a weight.',
  'The group''s total weight on the date: for adv20_value its average daily traded value over 20 sessions.', 'Use for the group''s share of the market (weight_sum / the MARKET row''s).',
  'Not a market capitalisation and not the day''s traded value; never sum over dates.'),
 ('ret_1d_w', 'Return', 'MEASURE', ARRAY['AVG', 'MEDIAN', 'MIN', 'MAX', 'PERCENTILE'], 'HIGHER', true, false,
  '100 x sum(w(t-1) x (close(t) / previous close - 1)) / sum(w(t-1)) over members with both closes and a weight on the previous market date', 'Price_Stock_Indonesia_IDX.close; feature_08_weight(previous market date)', '1 session (weights: 20 sessions)', 'percent', 'NULL when no member has both closes and a previous-date weight.',
  'The group''s weighted price move of the day, weights fixed at the previous date so the day''s own trading does not weigh its return.', 'Chain over dates with index_level; compare groups on the same date.',
  'Weighted by traded value, not free-float capitalisation: it differs from the IDX sector index of the same name (2026-11-25: Financials -0.16% here, IDXFINANCE -0.31%). Do not add returns across dates; compound them.'),
 ('index_level', 'Price', 'MEASURE', ARRAY['MIN', 'MAX'], 'CONTEXTUAL', true, false,
  '100 on the group''s first row; then the last non-NULL level x (1 + ret_1d_w / 100)', 'ret_1d_w', 'every session since the group''s first row', 'index points', 'NULL on a date without ret_1d_w (the level carries); 100 on the first date.',
  'A price index of the group built by EDGE from its members (the industries have no exchange index).', 'Use ratios of two dates for a period return (level(e) / level(b) - 1).',
  'Starts at 100 on the group''s first date (2021-01-25 for the backfill), not comparable as a level across groups; current membership (survivorship bias).'),
 ('calculation_version', 'Metadata', 'DIMENSION', ARRAY['COUNT', 'COUNT_DISTINCT'], 'NOT_APPLICABLE', true, true,
  'refresh_feature_08_day formula version', 'refresh_feature_08_day', '1 session', 'text', 'Never NULL.',
  'Which formula wrote the row.', 'Check that every row of a period has the same version.', 'Not a data date.'),
 ('calculated_at', 'Data Quality', 'IDENTITY', ARRAY['MIN', 'MAX', 'COUNT'], 'NOT_APPLICABLE', true, false,
  'clock_timestamp() of the refresh', 'refresh_feature_08_day', '1 session', 'timestamp', 'Never NULL.',
  'When the row was computed.', 'Operational freshness only.', 'Not when the market data became available; a re-run refreshes it.'))
INSERT INTO public."Feature_Catalog" (feature_table, feature_column, grain, feature_category, definition, calculation,
    source_tables, source_columns, lookback_window, minimum_history, unit, null_rule, refresh_trigger, dependency_rule,
    version, is_active, semantic_role, allowed_aggregations, ranking_interpretation, is_filterable, is_groupable,
    availability_rule, point_in_time_safe, historical_metadata_warning, analytical_interpretation, recommended_use,
    misuse_warning, semantic_review_status, validation_evidence)
SELECT 'Feature_08_Group_Daily', d.column_name, 'Market date x group (MARKET, SECTOR, INDUSTRY)', d.category,
       c.definition, d.calculation,
       'Price_Stock_Indonesia_IDX, Feature_04_Technical_Indicator, IDX_Stock_Universe, Feature_Index_Entity',
       d.source_columns, d.lookback, d.lookback, d.unit, d.null_rule,
       'refresh_feature_08_day(date) after feature-04-worker finalizes an equity run; backfill job for history',
       'Requires the final daily prices and Feature 04 of the date; the previous market date''s row of each group (chain)',
       'v1', true, d.role, d.aggs, d.ranking, d.filterable, d.groupable,
       'Use after Feature 04 of the date is complete (the worker refreshes it when the daily run is finalized).', false,
       'Membership is IDX_Stock_Universe as of the refresh (current Sector and Industry), not as of the date.',
       d.interpretation, d.use, d.misuse, 'CALCULATION_VERIFIED',
       ARRAY['database/migrations/20261126_001_feature_08_group_daily.sql', 'verification/sector_analysis/db/REHEARSAL.md',
             'verification/sector_analysis/db/EXPLAIN.md', 'verification/sector_analysis/db/validate_feature_08.py',
             'SECTOR_FORMULAS.md', 'DATABASE_CHANGELOG.md']
FROM d JOIN public."Column_Catalog" AS c
  ON c.table_schema = 'public' AND c.table_name = 'Feature_08_Group_Daily' AND c.column_name = d.column_name;

DO $check$
DECLARE
    n integer;
BEGIN
    SELECT count(*) INTO n FROM information_schema.columns AS c
    WHERE c.table_schema = 'public' AND c.table_name = 'Feature_08_Group_Daily'
      AND (NOT EXISTS (SELECT 1 FROM public."Column_Catalog" AS k WHERE k.table_schema = 'public'
                       AND k.table_name = c.table_name AND k.column_name = c.column_name)
           OR NOT EXISTS (SELECT 1 FROM public."Feature_Catalog" AS f WHERE f.feature_table = c.table_name
                          AND f.feature_column = c.column_name AND f.is_active));
    IF n > 0 THEN
        RAISE EXCEPTION '% columns of Feature_08_Group_Daily lack a Column_Catalog or active Feature_Catalog row', n;
    END IF;
    IF (SELECT count(*) FROM public."Feature_Catalog" WHERE feature_table = 'Feature_08_Group_Daily' AND is_active) <> 18 THEN
        RAISE EXCEPTION 'expected 18 active Feature_Catalog rows of Feature_08_Group_Daily';
    END IF;
    IF NOT has_table_privilege('terminal_market_reader', 'public."Feature_08_Group_Daily"', 'SELECT')
       OR NOT has_table_privilege('pgweb_reader', 'public."Feature_08_Group_Daily"', 'SELECT')
       OR NOT has_function_privilege('terminal_market_reader', 'public.feature_08_weight(date)', 'EXECUTE')
       OR has_function_privilege('terminal_market_reader', 'public.refresh_feature_08_day(date)', 'EXECUTE')
       OR NOT has_function_privilege(current_user, 'public.refresh_feature_08_day(date)', 'EXECUTE') THEN
        RAISE EXCEPTION 'a grant of this migration is missing (or the reader may run the refresh)';
    END IF;
    IF (SELECT count(DISTINCT w.weight_basis) FROM public.feature_08_weight(current_date) AS w) > 1 THEN
        RAISE EXCEPTION 'feature_08_weight returns more than one basis';
    END IF;
END
$check$;

COMMIT;

-- Rollback (only with the user's go; nothing reads the table before the publisher's family `sector` is deployed):
-- BEGIN;
-- DELETE FROM public."Feature_Catalog" WHERE feature_table = 'Feature_08_Group_Daily';
-- DELETE FROM public."Column_Catalog" WHERE table_schema = 'public' AND table_name = 'Feature_08_Group_Daily';
-- DELETE FROM public."Table_Catalog" WHERE table_schema = 'public' AND table_name = 'Feature_08_Group_Daily';
-- DROP FUNCTION public.refresh_feature_08_day(date);
-- DROP FUNCTION public.feature_08_weight(date);
-- DROP TABLE public."Feature_08_Group_Daily";
-- COMMIT;
