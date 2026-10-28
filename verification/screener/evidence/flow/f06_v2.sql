CREATE FUNCTION public.refresh_feature_06(p_ticker text, p_from date DEFAULT NULL)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
DECLARE
    v_range_start date;
    v_rows bigint;
BEGIN
    IF p_ticker IS NULL THEN
        RAISE EXCEPTION 'refresh_feature_06 needs a ticker';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('refresh_feature_06:' || p_ticker, 0));

    -- 312 sessions before p_from (252 baseline + 60-session window); NULL means from the ticker's first session.
    IF p_from IS NOT NULL THEN
        SELECT CASE WHEN count(*) = 312 THEN min(d) END INTO v_range_start
        FROM (SELECT DISTINCT trade_date AS d
              FROM F05
              WHERE ticker = p_ticker AND trade_date < p_from
              ORDER BY d DESC LIMIT 312) AS prior;
    END IF;

    DELETE FROM F06 AS t
    WHERE t.ticker = p_ticker AND (p_from IS NULL OR t.trade_date >= p_from);

    WITH base AS (
        SELECT f.trade_date, f.market_board,
               sum(f.buy_value) FILTER (WHERE f.investor_type = 'Foreign') AS fb,
               sum(f.sell_value) FILTER (WHERE f.investor_type = 'Foreign') AS fs,
               sum(f.buy_value) FILTER (WHERE f.investor_type = 'Domestic') AS db,
               sum(f.sell_value) FILTER (WHERE f.investor_type = 'Domestic') AS ds,
               sum(f.buy_lots) FILTER (WHERE f.investor_type = 'Foreign') AS fbl,
               sum(f.sell_lots) FILTER (WHERE f.investor_type = 'Foreign') AS fsl,
               sum(f.buy_lots) FILTER (WHERE f.investor_type = 'Domestic') AS dbl,
               sum(f.sell_lots) FILTER (WHERE f.investor_type = 'Domestic') AS dsl,
               sum(f.buy_freq) FILTER (WHERE f.investor_type = 'Foreign') AS bf,
               sum(f.sell_freq) FILTER (WHERE f.investor_type = 'Foreign') AS sf,
               sum(f.buy_freq) FILTER (WHERE f.investor_type = 'Domestic') AS dbf,
               sum(f.sell_freq) FILTER (WHERE f.investor_type = 'Domestic') AS dsf,
               count(f.buy_freq) AS freq_rows,
               bool_or(f.source_balance_gap) AS gap
        FROM F05 AS f
        WHERE f.ticker = p_ticker AND (v_range_start IS NULL OR f.trade_date >= v_range_start)
        GROUP BY f.trade_date, f.market_board
    ), sessions AS (
        SELECT trade_date, row_number() OVER (ORDER BY trade_date) AS s
        FROM (SELECT DISTINCT trade_date FROM base) AS d
    ), boards AS (
        SELECT DISTINCT market_board FROM base
    ), has_freq AS (
        SELECT coalesce(sum(freq_rows), 0) > 0 AS yes FROM base
    ), anchor AS (
        SELECT DISTINCT ON (t.market_board) t.market_board,
               t.foreign_cumulative_net AS foreign_anchor, t.domestic_cumulative_net AS domestic_anchor
        FROM F06 AS t
        WHERE v_range_start IS NOT NULL AND t.ticker = p_ticker AND t.trade_date < v_range_start
        ORDER BY t.market_board, t.trade_date DESC
    ), dense AS (
        -- Every board in every session; a board that did not trade in a session counts zero, and an investor type
        -- that did not trade on an active board counts zero. Frequency is zero-filled only for tickers that carry
        -- frequency; it stays NULL for symbols without frequency (warrants, rights).
        SELECT ss.trade_date, ss.s, bo.market_board, b.trade_date IS NOT NULL AS active,
               coalesce(b.gap, false) AS gap,
               coalesce(b.fb, 0) AS fb, coalesce(b.fs, 0) AS fs,
               coalesce(b.db, 0) AS db, coalesce(b.ds, 0) AS ds,
               coalesce(b.fbl, 0) AS fbl, coalesce(b.fsl, 0) AS fsl,
               coalesce(b.dbl, 0) AS dbl, coalesce(b.dsl, 0) AS dsl,
               CASE WHEN b.trade_date IS NULL THEN CASE WHEN hf.yes THEN 0 END WHEN b.freq_rows > 0 THEN coalesce(b.bf, 0) ELSE b.bf END AS bf,
               CASE WHEN b.trade_date IS NULL THEN CASE WHEN hf.yes THEN 0 END WHEN b.freq_rows > 0 THEN coalesce(b.sf, 0) ELSE b.sf END AS sf,
               CASE WHEN b.trade_date IS NULL THEN CASE WHEN hf.yes THEN 0 END WHEN b.freq_rows > 0 THEN coalesce(b.dbf, 0) ELSE b.dbf END AS dbf,
               CASE WHEN b.trade_date IS NULL THEN CASE WHEN hf.yes THEN 0 END WHEN b.freq_rows > 0 THEN coalesce(b.dsf, 0) ELSE b.dsf END AS dsf,
               coalesce(an.foreign_anchor, 0) AS foreign_anchor,
               coalesce(an.domestic_anchor, 0) AS domestic_anchor
        FROM sessions AS ss CROSS JOIN boards AS bo CROSS JOIN has_freq AS hf
        LEFT JOIN base AS b ON b.trade_date = ss.trade_date AND b.market_board = bo.market_board
        LEFT JOIN anchor AS an ON an.market_board = bo.market_board
    ), daily AS (
        SELECT d.*, d.fb - d.fs AS f, d.db - d.ds AS dn, d.fb + d.db AS t,
               CASE WHEN d.fb + d.db > 0 THEN (d.fb - d.fs) / (d.fb + d.db) END AS r
        FROM dense AS d
    ), w1 AS (
        SELECT d.*,
               d.foreign_anchor + sum(d.f) OVER (PARTITION BY d.market_board ORDER BY d.s ROWS UNBOUNDED PRECEDING) AS f_cum,
               d.domestic_anchor + sum(d.dn) OVER (PARTITION BY d.market_board ORDER BY d.s ROWS UNBOUNDED PRECEDING) AS d_cum,
               CASE WHEN d.s >= 5 THEN sum(d.f) OVER w5 END AS f5,
               CASE WHEN d.s >= 10 THEN sum(d.f) OVER w10 END AS f10,
               CASE WHEN d.s >= 20 THEN sum(d.f) OVER w20 END AS f20,
               CASE WHEN d.s >= 40 THEN sum(d.f) OVER w40 END AS f40,
               CASE WHEN d.s >= 60 THEN sum(d.f) OVER w60 END AS f60,
               CASE WHEN d.s >= 5 THEN sum(d.dn) OVER w5 END AS d5,
               CASE WHEN d.s >= 10 THEN sum(d.dn) OVER w10 END AS d10,
               CASE WHEN d.s >= 20 THEN sum(d.dn) OVER w20 END AS d20,
               CASE WHEN d.s >= 60 THEN sum(d.dn) OVER w60 END AS d60,
               CASE WHEN d.s >= 5 THEN sum(d.t) OVER w5 END AS t5,
               CASE WHEN d.s >= 20 THEN sum(d.t) OVER w20 END AS t20,
               CASE WHEN d.s >= 5 THEN count(*) FILTER (WHERE d.f > 0) OVER w5 END AS buy5,
               CASE WHEN d.s >= 10 THEN count(*) FILTER (WHERE d.f > 0) OVER w10 END AS buy10,
               CASE WHEN d.s >= 20 THEN count(*) FILTER (WHERE d.f > 0) OVER w20 END AS buy20,
               CASE WHEN d.s >= 40 THEN count(*) FILTER (WHERE d.f > 0) OVER w40 END AS buy40,
               CASE WHEN d.s >= 5 THEN count(*) FILTER (WHERE d.f < 0) OVER w5 END AS sell5,
               CASE WHEN d.s >= 10 THEN count(*) FILTER (WHERE d.f < 0) OVER w10 END AS sell10,
               CASE WHEN d.s >= 20 THEN count(*) FILTER (WHERE d.f < 0) OVER w20 END AS sell20,
               CASE WHEN d.s >= 40 THEN count(*) FILTER (WHERE d.f < 0) OVER w40 END AS sell40,
               CASE WHEN d.s >= 40 THEN sum(d.f) OVER (PARTITION BY d.market_board ORDER BY d.s
                    ROWS BETWEEN 39 PRECEDING AND 20 PRECEDING) END AS f_prev20,
               CASE WHEN d.s >= 80 THEN sum(d.f) OVER (PARTITION BY d.market_board ORDER BY d.s
                    ROWS BETWEEN 79 PRECEDING AND 40 PRECEDING) END AS f_prev40,
               CASE WHEN d.s >= 20 THEN sum(d.r) OVER w20 END AS r20,
               CASE WHEN d.s >= 20 THEN sum(abs(d.r)) OVER w20 END AS ar20,
               CASE WHEN d.s >= 50 THEN sum(d.r) OVER w50 END AS r50,
               CASE WHEN d.s >= 50 THEN sum(abs(d.r)) OVER w50 END AS ar50,
               CASE WHEN d.s >= 20 THEN sum(d.bf) OVER w20 END AS bf20,
               CASE WHEN d.s >= 20 THEN sum(d.sf) OVER w20 END AS sf20,
               CASE WHEN d.s >= 20 THEN sum(d.dbf) OVER w20 END AS dbf20,
               CASE WHEN d.s >= 20 THEN sum(d.dsf) OVER w20 END AS dsf20,
               CASE WHEN d.s >= 25 THEN sum(d.bf) OVER w5 END AS c_bf, CASE WHEN d.s >= 25 THEN sum(d.sf) OVER w5 END AS c_sf,
               CASE WHEN d.s >= 25 THEN sum(d.dbf) OVER w5 END AS c_dbf, CASE WHEN d.s >= 25 THEN sum(d.dsf) OVER w5 END AS c_dsf,
               CASE WHEN d.s >= 25 THEN sum(d.fb) OVER w5 END AS c_fb, CASE WHEN d.s >= 25 THEN sum(d.fs) OVER w5 END AS c_fs,
               CASE WHEN d.s >= 25 THEN sum(d.db) OVER w5 END AS c_db, CASE WHEN d.s >= 25 THEN sum(d.ds) OVER w5 END AS c_ds,
               CASE WHEN d.s >= 25 THEN sum(d.bf) OVER p20 END AS p_bf, CASE WHEN d.s >= 25 THEN sum(d.sf) OVER p20 END AS p_sf,
               CASE WHEN d.s >= 25 THEN sum(d.dbf) OVER p20 END AS p_dbf, CASE WHEN d.s >= 25 THEN sum(d.dsf) OVER p20 END AS p_dsf,
               CASE WHEN d.s >= 25 THEN sum(d.fb) OVER p20 END AS p_fb, CASE WHEN d.s >= 25 THEN sum(d.fs) OVER p20 END AS p_fs,
               CASE WHEN d.s >= 25 THEN sum(d.db) OVER p20 END AS p_db, CASE WHEN d.s >= 25 THEN sum(d.ds) OVER p20 END AS p_ds
        FROM daily AS d
        WINDOW w5 AS (PARTITION BY d.market_board ORDER BY d.s ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
               w10 AS (PARTITION BY d.market_board ORDER BY d.s ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),
               w20 AS (PARTITION BY d.market_board ORDER BY d.s ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
               w40 AS (PARTITION BY d.market_board ORDER BY d.s ROWS BETWEEN 39 PRECEDING AND CURRENT ROW),
               w50 AS (PARTITION BY d.market_board ORDER BY d.s ROWS BETWEEN 49 PRECEDING AND CURRENT ROW),
               w60 AS (PARTITION BY d.market_board ORDER BY d.s ROWS BETWEEN 59 PRECEDING AND CURRENT ROW),
               p20 AS (PARTITION BY d.market_board ORDER BY d.s ROWS BETWEEN 24 PRECEDING AND 5 PRECEDING)
    ), w2 AS (
        SELECT w.*,
               CASE WHEN w.s >= 20 AND w.ar20 > 0 THEN 100 * w.r20 / w.ar20 END AS strength20,
               CASE WHEN w.s >= 50 AND w.ar50 > 0 THEN 100 * w.r50 / w.ar50 END AS strength50
        FROM w1 AS w
    ), w3 AS (
        -- baselines: the preceding 252 / 60 values of the same rolling net, today excluded
        SELECT w.*,
               lag(w.strength20, 5) OVER (PARTITION BY w.market_board ORDER BY w.s) AS strength20_lag5,
               count(w.f5) OVER b252 AS n5, avg(w.f5::double precision) OVER b252 AS m5, stddev_samp(w.f5::double precision) OVER b252 AS sd5,
               array_agg(w.f5) FILTER (WHERE w.f5 IS NOT NULL) OVER b252 AS h5,
               count(w.f10) OVER b252 AS n10, avg(w.f10::double precision) OVER b252 AS m10, stddev_samp(w.f10::double precision) OVER b252 AS sd10,
               array_agg(w.f10) FILTER (WHERE w.f10 IS NOT NULL) OVER b252 AS h10,
               count(w.f20) OVER b252 AS n20, avg(w.f20::double precision) OVER b252 AS m20, stddev_samp(w.f20::double precision) OVER b252 AS sd20,
               array_agg(w.f20) FILTER (WHERE w.f20 IS NOT NULL) OVER b252 AS h20,
               count(w.f40) OVER b252 AS n40, avg(w.f40::double precision) OVER b252 AS m40, stddev_samp(w.f40::double precision) OVER b252 AS sd40,
               array_agg(w.f40) FILTER (WHERE w.f40 IS NOT NULL) OVER b252 AS h40,
               count(w.f60) OVER b252 AS n60, avg(w.f60::double precision) OVER b252 AS m60, stddev_samp(w.f60::double precision) OVER b252 AS sd60,
               array_agg(w.f60) FILTER (WHERE w.f60 IS NOT NULL) OVER b252 AS h60,
               count(w.f5) OVER b60 AS q5, avg(w.f5::double precision) OVER b60 AS qm5, stddev_samp(w.f5::double precision) OVER b60 AS qsd5,
               array_agg(w.f5) FILTER (WHERE w.f5 IS NOT NULL) OVER b60 AS qh5,
               count(w.f10) OVER b60 AS q10, avg(w.f10::double precision) OVER b60 AS qm10, stddev_samp(w.f10::double precision) OVER b60 AS qsd10,
               array_agg(w.f10) FILTER (WHERE w.f10 IS NOT NULL) OVER b60 AS qh10,
               count(w.f20) OVER b60 AS q20, avg(w.f20::double precision) OVER b60 AS qm20, stddev_samp(w.f20::double precision) OVER b60 AS qsd20,
               array_agg(w.f20) FILTER (WHERE w.f20 IS NOT NULL) OVER b60 AS qh20
        FROM w2 AS w
        WINDOW b252 AS (PARTITION BY w.market_board ORDER BY w.s ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING),
               b60 AS (PARTITION BY w.market_board ORDER BY w.s ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING)
    )
    INSERT INTO F06
    SELECT x.trade_date, p_ticker, x.market_board,
           x.fb, x.fs, x.f, x.db, x.ds, x.dn, x.f_cum, x.d_cum,
           x.f5, x.f10, x.f20, x.f40, x.f60, x.d5, x.d10, x.d20, x.d60,
           CASE WHEN x.t > 0 THEN (100 * x.f / x.t)::double precision END,
           CASE WHEN x.t5 > 0 THEN (100 * x.f5 / x.t5)::double precision END,
           CASE WHEN x.t20 > 0 THEN (100 * x.f20 / x.t20)::double precision END,
           CASE WHEN x.t > 0 THEN (100 * x.fb / x.t)::double precision END,
           CASE WHEN x.t > 0 THEN (100 * x.fs / x.t)::double precision END,
           x.buy5, x.buy10, x.buy20, x.buy40, x.sell5, x.sell10, x.sell20, x.sell40,
           CASE WHEN x.n5 = 252 AND x.sd5 > 0 THEN (x.f5::double precision - x.m5) / x.sd5 END,
           CASE WHEN x.n10 = 252 AND x.sd10 > 0 THEN (x.f10::double precision - x.m10) / x.sd10 END,
           CASE WHEN x.n20 = 252 AND x.sd20 > 0 THEN (x.f20::double precision - x.m20) / x.sd20 END,
           CASE WHEN x.n40 = 252 AND x.sd40 > 0 THEN (x.f40::double precision - x.m40) / x.sd40 END,
           CASE WHEN x.n60 = 252 AND x.sd60 > 0 THEN (x.f60::double precision - x.m60) / x.sd60 END,
           CASE WHEN x.n5 = 252 THEN public.feature_06_midrank_percentile(x.f5, x.h5, 252) END,
           CASE WHEN x.n10 = 252 THEN public.feature_06_midrank_percentile(x.f10, x.h10, 252) END,
           CASE WHEN x.n20 = 252 THEN public.feature_06_midrank_percentile(x.f20, x.h20, 252) END,
           CASE WHEN x.n40 = 252 THEN public.feature_06_midrank_percentile(x.f40, x.h40, 252) END,
           CASE WHEN x.n60 = 252 THEN public.feature_06_midrank_percentile(x.f60, x.h60, 252) END,
           CASE WHEN x.q5 = 60 AND x.qsd5 > 0 THEN (x.f5::double precision - x.qm5) / x.qsd5 END,
           CASE WHEN x.q10 = 60 AND x.qsd10 > 0 THEN (x.f10::double precision - x.qm10) / x.qsd10 END,
           CASE WHEN x.q20 = 60 AND x.qsd20 > 0 THEN (x.f20::double precision - x.qm20) / x.qsd20 END,
           CASE WHEN x.q5 = 60 THEN public.feature_06_midrank_percentile(x.f5, x.qh5, 60) END,
           CASE WHEN x.q10 = 60 THEN public.feature_06_midrank_percentile(x.f10, x.qh10, 60) END,
           CASE WHEN x.q20 = 60 THEN public.feature_06_midrank_percentile(x.f20, x.qh20, 60) END,
           x.f20 - x.f_prev20,
           x.f40 - x.f_prev40,
           x.strength20, x.strength50, x.strength20 - x.strength20_lag5,
           x.bf, x.sf, x.dbf, x.dsf,
           CASE WHEN x.bf + x.sf > 0 THEN 100.0 * (x.bf - x.sf) / (x.bf + x.sf) END,
           CASE WHEN x.bf20 + x.sf20 > 0 THEN (100 * (x.bf20 - x.sf20) / (x.bf20 + x.sf20))::double precision END,
           CASE WHEN x.bf + x.dbf > 0 THEN 100.0 * x.bf / (x.bf + x.dbf) END,
           CASE WHEN x.sf + x.dsf > 0 THEN 100.0 * x.sf / (x.sf + x.dsf) END,
           CASE WHEN x.bf > 0 THEN (x.fb / x.bf)::double precision END,
           CASE WHEN x.sf > 0 THEN (x.fs / x.sf)::double precision END,
           CASE WHEN x.bf > 0 AND x.sf > 0 AND x.fs > 0 THEN ((x.fb / x.bf) / (x.fs / x.sf))::double precision END,
           CASE WHEN x.bf > 0 THEN (x.fbl / x.bf)::double precision END,
           CASE WHEN x.sf > 0 THEN (x.fsl / x.sf)::double precision END,
           CASE WHEN x.dbf + x.dsf > 0 THEN 100.0 * (x.dbf - x.dsf) / (x.dbf + x.dsf) END,
           CASE WHEN x.dbf20 + x.dsf20 > 0 THEN (100 * (x.dbf20 - x.dsf20) / (x.dbf20 + x.dsf20))::double precision END,
           CASE WHEN x.bf + x.dbf > 0 THEN 100.0 * x.dbf / (x.bf + x.dbf) END,
           CASE WHEN x.sf + x.dsf > 0 THEN 100.0 * x.dsf / (x.sf + x.dsf) END,
           CASE WHEN x.dbf > 0 THEN (x.db / x.dbf)::double precision END,
           CASE WHEN x.dsf > 0 THEN (x.ds / x.dsf)::double precision END,
           CASE WHEN x.dbf > 0 AND x.dsf > 0 AND x.ds > 0 THEN ((x.db / x.dbf) / (x.ds / x.dsf))::double precision END,
           CASE WHEN x.dbf > 0 THEN (x.dbl / x.dbf)::double precision END,
           CASE WHEN x.dsf > 0 THEN (x.dsl / x.dsf)::double precision END,
           CASE WHEN x.c_bf + x.c_dbf > 0 AND x.p_bf + x.p_dbf > 0
                THEN (100 * x.c_dbf / (x.c_bf + x.c_dbf) - 100 * x.p_dbf / (x.p_bf + x.p_dbf))::double precision END,
           CASE WHEN x.c_bf + x.c_dbf > 0 AND x.p_bf + x.p_dbf > 0
                THEN (100 * x.c_bf / (x.c_bf + x.c_dbf) - 100 * x.p_bf / (x.p_bf + x.p_dbf))::double precision END,
           CASE WHEN x.c_dbf > 0 AND x.p_dbf > 0 AND x.p_db > 0
                THEN (100 * ((x.c_db / x.c_dbf) / (x.p_db / x.p_dbf) - 1))::double precision END,
           CASE WHEN x.c_bf > 0 AND x.p_bf > 0 AND x.p_fb > 0
                THEN (100 * ((x.c_fb / x.c_bf) / (x.p_fb / x.p_bf) - 1))::double precision END,
           CASE WHEN x.c_sf + x.c_dsf > 0 AND x.p_sf + x.p_dsf > 0
                THEN (100 * x.c_dsf / (x.c_sf + x.c_dsf) - 100 * x.p_dsf / (x.p_sf + x.p_dsf))::double precision END,
           CASE WHEN x.c_sf + x.c_dsf > 0 AND x.p_sf + x.p_dsf > 0
                THEN (100 * x.c_sf / (x.c_sf + x.c_dsf) - 100 * x.p_sf / (x.p_sf + x.p_dsf))::double precision END,
           CASE WHEN x.c_dsf > 0 AND x.p_dsf > 0 AND x.p_ds > 0
                THEN (100 * ((x.c_ds / x.c_dsf) / (x.p_ds / x.p_dsf) - 1))::double precision END,
           CASE WHEN x.c_sf > 0 AND x.p_sf > 0 AND x.p_fs > 0
                THEN (100 * ((x.c_fs / x.c_sf) / (x.p_fs / x.p_sf) - 1))::double precision END,
           CASE WHEN x.bf IS NULL OR x.sf IS NULL OR x.f = 0 OR x.bf = x.sf THEN NULL
                ELSE sign(x.f) <> sign(x.bf - x.sf) END,
           x.gap, statement_timestamp()
    FROM w3 AS x
    WHERE x.active AND (p_from IS NULL OR x.trade_date >= p_from);
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END
$function$;
