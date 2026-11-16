-- EXEC-RADAR (user go 2026-11-14: "3 A go"): refresh_feature_07_day reads each gated stock's Feature 05 rows through
-- the primary key. Migration 20261114_001 joined on a per-stock date range; on dev the planner answered it with a hash
-- join over a sequential scan of all of Feature 05 (45 M rows): the backfill DRYRUN measured about 86 s a date
-- (EXPLAIN on dev, 2026-11-14). The LATERAL lookup below read the same rows in 0.6 s (EXPLAIN ANALYZE, read-only, on
-- dev). Same results; nothing else changes. Migration 001 is applied and stays as it is (AGENTS.md, History rules).
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regprocedure('public.refresh_feature_07_day(date)') IS NULL THEN
        RAISE EXCEPTION 'refresh_feature_07_day(date) is missing: apply 20261114_001 first';
    END IF;
END
$preflight$;

CREATE OR REPLACE FUNCTION public.refresh_feature_07_day(p_date date)
RETURNS integer
LANGUAGE plpgsql
AS $function$
DECLARE
    v_prev date;
    v_last16 date[];
    v_version text := public.feature_07_rule_version();
    v_s3_floor double precision;
    v_rows integer;
    g text;
BEGIN
    IF p_date IS NULL THEN
        RAISE EXCEPTION 'refresh_feature_07_day needs a date';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('refresh_feature_07_day', 0));
    SELECT threshold INTO v_s3_floor FROM public."Feature_07_Radar_Rule"
    WHERE rule_version = v_version AND filter_id = 'S3' AND cond_key = 'A' AND level = 'standard';

    -- The date's rows were written moments ago, so the planner may hold no statistics for them (none at all inside the
    -- first fill's transaction: on an estimate of one row the G2 step rescanned the table for every stock, over ten
    -- minutes for one date in the 2026-11-14 rehearsal). Every step therefore reads the table only by index (the date,
    -- or the 16 dates) into temporary tables that are analyzed before any join, and writes back once by primary key.
    WITH RECURSIVE d AS (   -- the last 16 market dates up to p_date, one index probe each
        SELECT max(trade_date) AS d, 1 AS n FROM public."Feature_07_Radar_Measure" WHERE trade_date <= p_date
        UNION ALL
        SELECT (SELECT max(trade_date) FROM public."Feature_07_Radar_Measure" WHERE trade_date < d.d), d.n + 1
        FROM d WHERE d.n < 16 AND d.d IS NOT NULL
    )
    SELECT array_agg(d.d) INTO v_last16 FROM d WHERE d.d IS NOT NULL;

    IF to_regclass('pg_temp.f07_day') IS NOT NULL THEN DROP TABLE pg_temp.f07_day; END IF;
    IF to_regclass('pg_temp.f07_act') IS NOT NULL THEN DROP TABLE pg_temp.f07_act; END IF;
    CREATE TEMP TABLE f07_act ON COMMIT DROP AS
    SELECT ticker, count(*) AS n FROM public."Feature_07_Radar_Measure" WHERE trade_date = ANY (v_last16) GROUP BY ticker;
    ANALYZE f07_act;
    CREATE TEMP TABLE f07_day ON COMMIT DROP AS
    SELECT m.ticker, m.s5_from, m.total_buy_5d, m.foreign_net_5d, m.foreign_ratio_5d_change,
           false AS g2, false AS gb, false AS gl,
           NULL::double precision AS s2b, NULL::double precision AS s2l,
           NULL::smallint AS k, NULL::double precision AS cr3, NULL::double precision AS cr3x, NULL::double precision AS intensity,
           NULL::smallint AS g3b, NULL::double precision AS gr3b, NULL::double precision AS ir3b,
           NULL::smallint AS g3l, NULL::double precision AS gr3l, NULL::double precision AS ir3l
    FROM public."Feature_07_Radar_Measure" AS m WHERE m.trade_date = p_date;
    IF NOT EXISTS (SELECT 1 FROM f07_day) THEN    -- QA 2026-11-14: never replace a date's results with nothing
        RAISE EXCEPTION 'refresh_feature_07_day(%): no measure row for this date; run refresh_feature_07 for its tickers first', p_date;
    END IF;
    ANALYZE f07_day;

    -- G2: universe stocks with at least 5 Regular sessions in the last 16 market dates and a full 5-session window
    UPDATE f07_day AS d SET g2 = true
    FROM f07_act AS a
    WHERE a.ticker = d.ticker AND a.n >= 5 AND d.total_buy_5d IS NOT NULL
      AND EXISTS (SELECT 1 FROM public."IDX_Stock_Universe" AS u WHERE u."Ticker" = d.ticker);

    -- G3: Broad keeps the top 50%, Liquid the top 20% of 5-session Regular buying (linear percentile, as numpy)
    DELETE FROM public."Feature_07_Radar_Gate" WHERE trade_date = p_date;
    INSERT INTO public."Feature_07_Radar_Gate" (trade_date, universe_n, broad_cut, liquid_cut, broad_n, liquid_n)
    SELECT p_date, count(*),
           percentile_cont(0.5) WITHIN GROUP (ORDER BY total_buy_5d), percentile_cont(0.8) WITHIN GROUP (ORDER BY total_buy_5d), 0, 0
    FROM f07_day WHERE g2;
    UPDATE f07_day AS d SET gb = d.total_buy_5d >= g.broad_cut, gl = d.total_buy_5d >= g.liquid_cut
    FROM public."Feature_07_Radar_Gate" AS g WHERE g.trade_date = p_date AND d.g2;
    UPDATE public."Feature_07_Radar_Gate"
    SET broad_n = (SELECT count(*) FROM f07_day WHERE gb), liquid_n = (SELECT count(*) FROM f07_day WHERE gl)
    WHERE trade_date = p_date;
    ANALYZE f07_day;

    -- S3 from the broker rows of each Broad stock's own 5 sessions (Regular, investor types summed)
    -- each stock's own rows through the primary key (ticker, trade_date): a join on a per-stock date range let the
    -- planner hash-join a sequential scan of all of Feature 05 (45 M rows, about 86 s a date on dev, 2026-11-14);
    -- OFFSET 0 keeps the subquery a per-stock index lookup (0.6 s for 430 stocks)
    WITH nb AS (
        SELECT f.ticker, f.broker, sum(f.buy_value - f.sell_value) AS net, sum(f.buy_value) AS buy
        FROM f07_day AS d CROSS JOIN LATERAL (
            SELECT x.ticker, x.broker, x.buy_value, x.sell_value
            FROM public."Feature_05_Foreign_Domestic_Broker_Detail" AS x
            WHERE x.ticker = d.ticker AND x.market_board = 'Regular' AND x.trade_date BETWEEN d.s5_from AND p_date
            OFFSET 0) AS f
        WHERE d.gb
        GROUP BY f.ticker, f.broker
    ), r AS (
        SELECT nb.*, row_number() OVER (PARTITION BY nb.ticker ORDER BY nb.net DESC, nb.broker) AS rn FROM nb
    ), agg AS (
        SELECT ticker, count(*) FILTER (WHERE net > 0) AS k, sum(net) FILTER (WHERE net > 0) AS pos,
               sum(net) FILTER (WHERE net > 0 AND rn <= 3) AS top3, sum(buy) AS tbuy
        FROM r GROUP BY ticker
    )
    UPDATE f07_day AS d
    SET k = a.k,
        cr3 = CASE WHEN a.pos > 0 THEN (a.top3 / a.pos)::double precision END,
        cr3x = CASE WHEN a.pos > 0 THEN (a.top3 / a.pos)::double precision - 3.0 / a.k END,
        intensity = CASE WHEN a.tbuy > 0 THEN (coalesce(a.pos, 0) / a.tbuy)::double precision END
    FROM agg AS a WHERE d.ticker = a.ticker;
    ANALYZE f07_day;

    -- cross-stock ranks per gate: S2 among net foreign buyers, S3 among stocks with at least 10 net buyers (G4) in five
    -- groups of k: quintile edges of k (linear), a stock goes to the first group whose edge is at or above its k, so a
    -- value of k is never split (the library's groups of 3 Nov: k 10-21, 22-26, 27-31, 32-38, 39-63)
    FOREACH g IN ARRAY ARRAY['broad', 'liquid'] LOOP
        WITH pop AS (
            SELECT ticker, foreign_ratio_5d_change AS v FROM f07_day
            WHERE foreign_net_5d > 0 AND foreign_ratio_5d_change IS NOT NULL AND CASE g WHEN 'broad' THEN gb ELSE gl END
        ), rk AS (
            SELECT ticker, CASE WHEN count(*) OVER () > 1 THEN 100.0 * (rank() OVER (ORDER BY v) - 1) / (count(*) OVER () - 1) END AS r FROM pop
        )
        UPDATE f07_day AS d
        SET s2b = CASE WHEN g = 'broad' THEN rk.r ELSE d.s2b END,
            s2l = CASE WHEN g = 'liquid' THEN rk.r ELSE d.s2l END
        FROM rk WHERE d.ticker = rk.ticker;

        WITH pop AS (   -- G4: the floor of net buyers is S3 condition A of the rule table
            SELECT ticker, k, cr3x AS e, intensity AS i FROM f07_day
            WHERE k >= v_s3_floor AND cr3x IS NOT NULL AND intensity IS NOT NULL AND CASE g WHEN 'broad' THEN gb ELSE gl END
        ), edges AS (
            SELECT percentile_cont(ARRAY[0.2, 0.4, 0.6, 0.8]) WITHIN GROUP (ORDER BY k) AS e FROM pop
        ), grp AS (
            SELECT pop.*, (SELECT count(*) FROM unnest(edges.e) AS x WHERE x < pop.k)::smallint AS gi FROM pop, edges
        ), rk AS (
            SELECT ticker, gi,
                   CASE WHEN count(*) OVER (PARTITION BY gi) > 1 THEN 100.0 * (rank() OVER (PARTITION BY gi ORDER BY e) - 1) / (count(*) OVER (PARTITION BY gi) - 1) END AS gr,
                   CASE WHEN count(*) OVER () > 1 THEN 100.0 * (rank() OVER (ORDER BY i) - 1) / (count(*) OVER () - 1) END AS ir
            FROM grp
        )
        UPDATE f07_day AS d
        SET g3b = CASE WHEN g = 'broad' THEN rk.gi ELSE d.g3b END,
            gr3b = CASE WHEN g = 'broad' THEN rk.gr ELSE d.gr3b END,
            ir3b = CASE WHEN g = 'broad' THEN rk.ir ELSE d.ir3b END,
            g3l = CASE WHEN g = 'liquid' THEN rk.gi ELSE d.g3l END,
            gr3l = CASE WHEN g = 'liquid' THEN rk.gr ELSE d.gr3l END,
            ir3l = CASE WHEN g = 'liquid' THEN rk.ir ELSE d.ir3l END
        FROM rk WHERE d.ticker = rk.ticker;
    END LOOP;

    -- one write per stock of the date, by primary key
    UPDATE public."Feature_07_Radar_Measure" AS m
    SET g2_eligible = d.g2, gate_broad = d.gb, gate_liquid = d.gl, s2_rank_broad = d.s2b, s2_rank_liquid = d.s2l,
        s3_net_buyers = d.k, s3_cr3 = d.cr3, s3_cr3_excess = d.cr3x, s3_intensity = d.intensity,
        s3_group_broad = d.g3b, s3_group_rank_broad = d.gr3b, s3_intensity_rank_broad = d.ir3b,
        s3_group_liquid = d.g3l, s3_group_rank_liquid = d.gr3l, s3_intensity_rank_liquid = d.ir3l
    FROM f07_day AS d
    WHERE m.ticker = d.ticker AND m.trade_date = p_date;

    -- rule results. The day's rows were written moments ago, so the planner has no statistics for them: each working set
    -- goes to a temporary table with ANALYZE before it is joined (planned on a one-row estimate, the same joins as CTEs
    -- ran over 2 minutes for one date in the 2026-11-14 rehearsal; with ANALYZE well under a second).
    SELECT max(trade_date) INTO v_prev FROM public."Feature_07_Radar_Gate" WHERE trade_date < p_date;
    IF to_regclass('pg_temp.f07_mg') IS NOT NULL THEN DROP TABLE pg_temp.f07_mg; END IF;
    IF to_regclass('pg_temp.f07_today') IS NOT NULL THEN DROP TABLE pg_temp.f07_today; END IF;
    IF to_regclass('pg_temp.f07_prev') IS NOT NULL THEN DROP TABLE pg_temp.f07_prev; END IF;

    CREATE TEMP TABLE f07_mg ON COMMIT DROP AS
    SELECT m.*, gt.gate,
           -- D6 (user 2026-11-14 "D6 ok"): a corporate action within the stock's own 5 sessions
           (SELECT 'Corporate action: ' || replace(lower(e.event_type), '_', ' ') || ' on ' || to_char(e.annotation_date, 'FMDD Mon')
            FROM public.idx_event_annotation AS e
            WHERE e.ticker = m.ticker AND e.event_family = 'CORPORATE_ACTION' AND e.annotation_date BETWEEN m.s5_from AND p_date
            ORDER BY e.annotation_date DESC, e.event_type LIMIT 1) AS ca_note
    FROM public."Feature_07_Radar_Measure" AS m
    CROSS JOIN (VALUES ('broad'), ('liquid')) AS gt(gate)
    WHERE m.trade_date = p_date AND m.g2_eligible AND CASE gt.gate WHEN 'broad' THEN m.gate_broad ELSE m.gate_liquid END;
    ANALYZE f07_mg;

    CREATE TEMP TABLE f07_today ON COMMIT DROP AS
    WITH ev AS (
        SELECT mg.ticker, mg.gate, r.filter_id, r.level, r.cond_key,
               -- a hit needs every condition; S8 (own levels) needs A and B, and C only makes it Strong
               (NOT f.own_levels OR r.cond_key IN ('A', 'B')) AS required,
               coalesce(CASE r.filter_id || ':' || r.cond_key
                   WHEN 'S1:A' THEN mg.foreign_net_5d > r.threshold
                   WHEN 'S1:B' THEN mg.foreign_ratio_5d >= r.threshold
                   WHEN 'S1:C' THEN mg.foreign_net_5d_pct252 >= r.threshold AND (r.threshold2 IS NULL OR mg.foreign_net_5d_z252 >= r.threshold2)
                   WHEN 'S1:D' THEN mg.buy_days_5d >= r.threshold
                   WHEN 'S2:A' THEN mg.foreign_net_5d > r.threshold
                   WHEN 'S2:B' THEN mg.foreign_ratio_5d_change > r.threshold
                   WHEN 'S2:C' THEN CASE mg.gate WHEN 'broad' THEN mg.s2_rank_broad ELSE mg.s2_rank_liquid END >= r.threshold
                   WHEN 'S3:A' THEN mg.s3_net_buyers >= r.threshold
                   WHEN 'S3:B' THEN CASE mg.gate WHEN 'broad' THEN mg.s3_group_rank_broad ELSE mg.s3_group_rank_liquid END >= r.threshold
                   WHEN 'S3:C' THEN CASE mg.gate WHEN 'broad' THEN mg.s3_intensity_rank_broad ELSE mg.s3_intensity_rank_liquid END >= r.threshold
                   WHEN 'S7:A' THEN mg.fl34_5d - mg.fl34_5d_prev >= r.threshold
                   WHEN 'S7:B' THEN mg.fl34_5d >= r.threshold
                   WHEN 'S7:C' THEN mg.inst_net_5d > r.threshold
                   WHEN 'S7:D' THEN mg.inst_share_5d >= r.threshold
                   WHEN 'S8:A' THEN greatest(mg.rz_foreign_ratio_1d, mg.rz_net_vs_adv20) >= r.threshold
                   WHEN 'S8:B' THEN mg.net_vs_adv20 >= r.threshold
                   WHEN 'S8:C' THEN mg.net_1d_pct252 >= r.threshold
                   ELSE CASE r.cond_key   -- S6 and its three S6-delta variants share A-C
                       WHEN 'A' THEN mg.foreign_net_5d > r.threshold
                       WHEN 'B' THEN mg.foreign_ratio_5d >= r.threshold
                       WHEN 'C' THEN mg.foreign_ratio_5d_pct252 >= r.threshold
                       WHEN 'D' THEN CASE r.filter_id
                           WHEN 'S6D_RATIO' THEN mg.foreign_ratio_5d_change >= r.threshold
                           WHEN 'S6D_RANK' THEN mg.foreign_ratio_5d_pct252_change >= r.threshold
                           WHEN 'S6D_BOTH' THEN mg.foreign_ratio_5d_change >= r.threshold AND mg.foreign_ratio_5d_pct252_change >= r.threshold2
                       END
                   END
               END, false) AS met
        FROM f07_mg AS mg
        JOIN public."Feature_07_Radar_Rule" AS r ON r.rule_version = v_version
        JOIN public."Feature_07_Radar_Filter" AS f ON f.rule_version = r.rule_version AND f.filter_id = r.filter_id
    )
    SELECT ticker, gate, filter_id, level,
           sum(CASE WHEN met THEN (CASE cond_key WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 4 ELSE 8 END) ELSE 0 END)::smallint AS met,
           count(*)::smallint AS cond_n,
           count(*) FILTER (WHERE required AND NOT met)::smallint AS missing,
           count(*) FILTER (WHERE NOT met)::smallint AS missing_all,
           bool_or(met) FILTER (WHERE cond_key = 'C') AS c_met
    FROM ev GROUP BY ticker, gate, filter_id, level;
    ANALYZE f07_today;

    CREATE TEMP TABLE f07_prev ON COMMIT DROP AS
    SELECT ticker, gate, filter_id, level, run_day FROM public."Feature_07_Radar_Result"
    WHERE trade_date = v_prev AND status = 'hit';
    ANALYZE f07_prev;

    DELETE FROM public."Feature_07_Radar_Result" WHERE trade_date = p_date;
    INSERT INTO public."Feature_07_Radar_Result" (trade_date, filter_id, level, gate, ticker, status, met, cond_n, run_day,
        left_reason, strong, sort_value, flag, rule_version)
    SELECT p_date, t.filter_id, t.level, t.gate, t.ticker, CASE WHEN t.missing = 0 THEN 'hit' ELSE 'near' END, t.met, t.cond_n,
           CASE WHEN t.missing = 0 THEN coalesce(p.run_day, 0) + 1 END, NULL,
           CASE WHEN t.missing = 0 AND t.filter_id = 'S8' THEN coalesce(t.c_met, false) END,
           CASE t.filter_id
               WHEN 'S1' THEN mg.foreign_net_5d_z252
               WHEN 'S2' THEN mg.foreign_ratio_5d_change
               WHEN 'S3' THEN (CASE t.gate WHEN 'broad' THEN mg.s3_group_rank_broad + mg.s3_intensity_rank_broad
                                           ELSE mg.s3_group_rank_liquid + mg.s3_intensity_rank_liquid END) / 2
               WHEN 'S6' THEN mg.foreign_ratio_5d
               WHEN 'S6D_RATIO' THEN mg.foreign_ratio_5d_change
               WHEN 'S6D_RANK' THEN mg.foreign_ratio_5d_pct252_change
               WHEN 'S6D_BOTH' THEN mg.foreign_ratio_5d_change
               WHEN 'S7' THEN mg.fl34_5d
               WHEN 'S8' THEN greatest(mg.rz_foreign_ratio_1d, mg.rz_net_vs_adv20)
           END,
           nullif(concat_ws('; ',
               -- D6: one day >= 80% of a positive 5-session foreign net, on the filters that read that 5-session flow
               CASE WHEN t.filter_id IN ('S1', 'S2', 'S6', 'S6D_RATIO', 'S6D_RANK', 'S6D_BOTH') AND mg.foreign_net_5d > 0
                         AND mg.foreign_net_5d_max_day >= 0.8 * mg.foreign_net_5d
                    THEN 'One-day block: Rp ' || to_char(round(mg.foreign_net_5d_max_day / 1e9, 1), 'FM999,999,990.0')
                         || 'B of the foreign net came on ' || to_char(mg.foreign_net_5d_max_date, 'FMDD Mon') END,
               mg.ca_note), ''),
           v_version
    FROM f07_today AS t
    JOIN f07_mg AS mg ON mg.ticker = t.ticker AND mg.gate = t.gate
    LEFT JOIN f07_prev AS p ON p.ticker = t.ticker AND p.gate = t.gate AND p.filter_id = t.filter_id AND p.level = t.level
    -- near (RADAR_PAGE_SPEC.md 4: "meet all conditions but one"): one condition short of all of them, not a hit
    WHERE t.missing = 0 OR (t.missing_all = 1 AND p.ticker IS NULL)
    UNION ALL
    -- left: a hit on the previous result date that is not a hit today, with the first condition it no longer meets; a
    -- stock that left and misses one condition is stored once, as left (its met bits still show it is one away)
    SELECT p_date, p.filter_id, p.level, p.gate, p.ticker, 'left', t.met, coalesce(t.cond_n, 0), NULL,
           CASE WHEN t.ticker IS NOT NULL THEN
                    (SELECT u.k FROM unnest(ARRAY['A', 'B', 'C', 'D'], ARRAY[1, 2, 4, 8]) AS u(k, b)
                     WHERE t.met & u.b = 0 ORDER BY u.k LIMIT 1)
                WHEN EXISTS (SELECT 1 FROM public."Feature_07_Radar_Measure" AS m WHERE m.trade_date = p_date AND m.ticker = p.ticker)
                    THEN 'gate'
                ELSE 'no_data' END,
           NULL, NULL, NULL, v_version
    FROM f07_prev AS p
    LEFT JOIN f07_today AS t ON t.ticker = p.ticker AND t.gate = p.gate AND t.filter_id = p.filter_id AND t.level = p.level
    WHERE t.ticker IS NULL OR t.missing > 0;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END
$function$;

COMMENT ON FUNCTION public.refresh_feature_07_day(date) IS
    'EXEC-RADAR: for one result date, the G2 universe, the Broad/Liquid gates, the cross-stock ranks (S2, S3 with broker rows of Feature 05 read per stock through its primary key), then the rule results of every filter, level and gate. Run the dates in order: a run of days reads the previous result date.';

COMMIT;
