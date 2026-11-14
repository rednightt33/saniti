-- EXEC-RADAR R1/R2 (user go 2026-11-14: "Ok go"): the Radar's daily measures, gates, rules and results.
--
-- What it holds
--   "Feature_07_Radar_Measure": one row per universe ticker and Regular session, the measures the screener library's
--     filters read (SCREENER_LIBRARY.md sections 2, 9, 11, 12, 13; PLAN.md RADAR): G3 buying, S1/S6 foreign 5-session
--     flow and its own-history rank, S2/S6-delta changes against 5 sessions before, S3 broker concentration, S7 FL34,
--     S8 one-day spike, plus the cross-section of the date (G2, gates, S2 and S3 ranks).
--   "Feature_07_Radar_Gate": the date's universe size and Broad/Liquid cut-offs.
--   "Feature_07_Radar_Filter", "Feature_07_Radar_Rule": the filters and every condition with its Loose/Standard/Strict
--     threshold and its English label. The only place a threshold lives: the result function reads it and the publisher
--     sends the labels to the page.
--   "Feature_07_Radar_Result": per date, filter, level and gate, the stocks that pass (hit), miss one condition (near) or
--     passed on the previous result date and no longer pass (left), with the met conditions, the run of days, the sort
--     value and the outlier flag.
--
-- Conventions (verified 2026-11-14 against 20261022_003 and the user's decisions in EXEC.md EXEC-RADAR)
--   * Sessions are the ticker's sessions as in Feature 06: the dates it traded on any board; a session without a Regular
--     trade counts zero on the Regular board. Windows (5, 20) and own-history baselines (252) count these sessions, so
--     a suspension is skipped ("A1 ok"). Rows are written only for sessions with a Regular trade.
--   * Own-history ranks: 100 x (previous values strictly below today's) / 252, NULL unless 252 complete previous values
--     ("D1 ok": one convention for every filter; Feature 06 stores a midrank). Without a full year a rank is NULL and a
--     condition reading it is not met; the other conditions are still judged ("B1 ok").
--   * Cross-stock ranks (S2, S3): 100 x (other stocks strictly below) / (n - 1) over the stocks that pass the gate
--     (SCREENER_LIBRARY.md 9.1; persentil sesudah gerbang, decision 9).
--   * Universe G2: tickers of IDX_Stock_Universe with a Regular session on the date and at least 5 Regular sessions in
--     the last 16 result dates. Feature 06 rows of other codes (warrants, rights: 383-462 a day before 2026-11-05,
--     0 since) are not read, so the population is the same on every date.
--   * S6-delta thresholds are provisional (option C, user 2026-11-14): set from 20 dates in R4 and approved before use.
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_07_Radar_Measure"') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature_07_Radar_Measure already exists';
    END IF;
    IF to_regclass('public."Feature_06_Foreign_Domestic"') IS NULL OR to_regclass('public."Feature_03_Stock_Broker_Daily"') IS NULL
       OR to_regclass('public."Feature_05_Foreign_Domestic_Broker_Detail"') IS NULL OR to_regclass('public."IDX_Stock_Universe"') IS NULL
       OR to_regclass('public.idx_event_annotation') IS NULL THEN
        RAISE EXCEPTION 'Feature 03, 05, 06, IDX_Stock_Universe and idx_event_annotation are required first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_market_reader') OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        RAISE EXCEPTION 'roles terminal_market_reader and pgweb_reader are required';
    END IF;
END
$preflight$;

-- ---------------------------------------------------------------------------------------------------------------
-- helpers
CREATE FUNCTION public.feature_07_below_percentile(p_current double precision, p_history double precision[], p_size integer)
RETURNS double precision
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
AS $function$
DECLARE
    v double precision;
    below_count integer := 0;
BEGIN
    IF cardinality(p_history) <> p_size THEN RETURN NULL; END IF;
    FOREACH v IN ARRAY p_history LOOP
        IF v IS NULL THEN RETURN NULL; END IF;
        IF v < p_current THEN below_count := below_count + 1; END IF;
    END LOOP;
    RETURN 100.0 * below_count / p_size;
END
$function$;
COMMENT ON FUNCTION public.feature_07_below_percentile(double precision, double precision[], integer) IS
    'EXEC-RADAR D1: 100*count(previous < current)/p_size; NULL unless exactly p_size complete previous values (SCREENER_LIBRARY.md 9.1 type A).';

CREATE FUNCTION public.feature_07_robust_z(p_current double precision, p_history double precision[], p_min integer)
RETURNS double precision
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE
AS $function$
DECLARE
    v_med double precision;
    v_mad double precision;
    v_n integer;
BEGIN
    IF p_current IS NULL OR p_history IS NULL THEN RETURN NULL; END IF;
    SELECT count(x), percentile_cont(0.5) WITHIN GROUP (ORDER BY x) INTO v_n, v_med FROM unnest(p_history) AS x WHERE x IS NOT NULL;
    IF v_n < p_min THEN RETURN NULL; END IF;
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(x - v_med)) INTO v_mad FROM unnest(p_history) AS x WHERE x IS NOT NULL;
    IF v_mad IS NULL OR v_mad = 0 THEN RETURN NULL; END IF;
    RETURN (p_current - v_med) / (1.4826 * v_mad);
END
$function$;
COMMENT ON FUNCTION public.feature_07_robust_z(double precision, double precision[], integer) IS
    'EXEC-RADAR S8 (SCREENER_LIBRARY.md 13.2): (current - median) / (1.4826 * MAD) of the non-NULL previous values; NULL with fewer than p_min values or MAD 0.';

-- ---------------------------------------------------------------------------------------------------------------
-- tables
CREATE TABLE public."Feature_07_Radar_Measure" (
    trade_date date NOT NULL,
    ticker text NOT NULL,
    s5_from date,                                   -- first date of the ticker's 5-session window
    foreign_net_1d numeric NOT NULL,                -- Regular foreign buy - sell, the day (N)
    total_buy_1d numeric NOT NULL,                  -- Regular foreign + domestic buy, the day (TBV)
    -- G3, S1, S6
    total_buy_5d numeric,                           -- G3 measure: Regular buying over 5 sessions
    foreign_net_5d numeric,
    foreign_ratio_5d double precision,              -- 100 x foreign_net_5d / total_buy_5d
    buy_days_5d smallint,                           -- sessions with foreign net > 0 among the 5
    foreign_net_5d_pct252 double precision,         -- S1 own-history rank (strict)
    foreign_net_5d_z252 double precision,           -- S1 z-score (sample sd, as Feature 06)
    foreign_ratio_5d_pct252 double precision,       -- S6 V2
    -- S2, S6-delta
    foreign_ratio_5d_prev double precision,         -- the ratio 5 sessions before (the previous 5-session block)
    foreign_ratio_5d_change double precision,       -- S2 / V1-delta, points
    foreign_ratio_5d_pct252_prev double precision,
    foreign_ratio_5d_pct252_change double precision, -- V2-delta, points
    foreign_net_5d_max_day numeric,                 -- largest one-day foreign net in the 5 sessions (outlier flag)
    foreign_net_5d_max_date date,
    -- S7 (FL34 over 5 sessions, Feature 03 classes)
    inst_net_5d numeric,
    retail_net_5d numeric,
    fl34_5d double precision,                       -- 100 x (inst - retail) / total buy, 5 sessions
    fl34_5d_prev double precision,
    inst_share_5d double precision,                 -- 100 x inst net / total buy, 5 sessions
    inst_buy_days_5d smallint,
    -- S8
    adv20_prev numeric,                             -- mean TBV of the 20 sessions before the day
    foreign_ratio_1d double precision,              -- U1 = 100 x N / TBV
    net_vs_adv20 double precision,                  -- U3 = 100 x N / ADV20
    rz_foreign_ratio_1d double precision,           -- robust z of U1 over 252 previous sessions (>= 200 values)
    rz_net_vs_adv20 double precision,               -- robust z of U3
    net_1d_pct252 double precision,                 -- rank of N over 252 previous sessions (strict)
    -- cross-section of the date (refresh_feature_07_day)
    g2_eligible boolean,
    gate_broad boolean,
    gate_liquid boolean,
    s2_rank_broad double precision,
    s2_rank_liquid double precision,
    s3_net_buyers smallint,
    s3_cr3 double precision,
    s3_cr3_excess double precision,                 -- CR3 - 3/k
    s3_intensity double precision,                  -- net of the net buyers / gross buy of all brokers
    s3_group_broad smallint,
    s3_group_rank_broad double precision,
    s3_intensity_rank_broad double precision,
    s3_group_liquid smallint,
    s3_group_rank_liquid double precision,
    s3_intensity_rank_liquid double precision,
    calculated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    CONSTRAINT feature_07_radar_measure_pkey PRIMARY KEY (ticker, trade_date)
);
CREATE INDEX feature_07_radar_measure_date_idx ON public."Feature_07_Radar_Measure" (trade_date);
COMMENT ON TABLE public."Feature_07_Radar_Measure" IS
    'EXEC-RADAR: per universe ticker and Regular session, the measures of the Radar filters S1, S2, S3, S6, S6-delta, S7, S8 (SCREENER_LIBRARY.md) and the date''s cross-section. Refreshed by refresh_feature_07 (per ticker) and refresh_feature_07_day (per date).';

CREATE TABLE public."Feature_07_Radar_Gate" (
    trade_date date PRIMARY KEY,
    universe_n integer NOT NULL,
    broad_cut numeric,
    liquid_cut numeric,
    broad_n integer NOT NULL,
    liquid_n integer NOT NULL,
    calculated_at timestamptz NOT NULL DEFAULT statement_timestamp()
);
COMMENT ON TABLE public."Feature_07_Radar_Gate" IS
    'EXEC-RADAR: per result date, the G2 universe size and the Broad (P50) and Liquid (P80) cut-offs of 5-session Regular buying.';

CREATE TABLE public."Feature_07_Radar_Filter" (
    rule_version text NOT NULL,
    filter_id text NOT NULL,
    position smallint NOT NULL,
    column_id text NOT NULL,                        -- the board column (S6D_* share S6D)
    column_label text NOT NULL,
    variant_label text,                             -- S6-delta: Ratio, Rank, Both
    is_default_variant boolean NOT NULL DEFAULT true,
    name text NOT NULL,
    question text NOT NULL,
    warning text NOT NULL,
    sort_label text NOT NULL,
    own_levels boolean NOT NULL DEFAULT false,      -- S8: Strong/Watch instead of Loose/Standard/Strict
    PRIMARY KEY (rule_version, filter_id)
);
CREATE TABLE public."Feature_07_Radar_Rule" (
    rule_version text NOT NULL,
    filter_id text NOT NULL,
    cond_key text NOT NULL CHECK (cond_key = ANY (ARRAY['A', 'B', 'C', 'D'])),
    level text NOT NULL CHECK (level = ANY (ARRAY['loose', 'standard', 'strict'])),
    label text NOT NULL,
    threshold double precision,
    threshold2 double precision,
    status text NOT NULL DEFAULT 'decided' CHECK (status = ANY (ARRAY['decided', 'provisional'])),
    PRIMARY KEY (rule_version, filter_id, cond_key, level),
    FOREIGN KEY (rule_version, filter_id) REFERENCES public."Feature_07_Radar_Filter" (rule_version, filter_id)
);
COMMENT ON TABLE public."Feature_07_Radar_Rule" IS
    'EXEC-RADAR: every condition of every Radar filter with its threshold per level and its English label; the only place a threshold lives.';

CREATE TABLE public."Feature_07_Radar_Result" (
    trade_date date NOT NULL,
    filter_id text NOT NULL,
    level text NOT NULL,
    gate text NOT NULL CHECK (gate = ANY (ARRAY['broad', 'liquid'])),
    ticker text NOT NULL,
    status text NOT NULL CHECK (status = ANY (ARRAY['hit', 'near', 'left'])),  -- near: one condition short, not a hit the date before
    met smallint,                                   -- bit 1 = A, 2 = B, 4 = C, 8 = D; NULL when not evaluated (left)
    cond_n smallint NOT NULL,
    run_day integer,                                -- hits: consecutive result dates in this filter, level and gate
    left_reason text,                               -- left: the first condition no longer met, 'gate' or 'no_data'
    strong boolean,                                 -- S8 hits: Strong (all three) or Watch
    sort_value double precision,
    flag text,                                      -- outlier note (D6)
    rule_version text NOT NULL,
    calculated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    PRIMARY KEY (trade_date, filter_id, level, gate, ticker)
);
COMMENT ON TABLE public."Feature_07_Radar_Result" IS
    'EXEC-RADAR: per result date, filter, level and gate, the stocks that pass (hit), miss exactly one condition (near) or no longer pass (left). Refreshed by refresh_feature_07_day.';

-- ---------------------------------------------------------------------------------------------------------------
-- rules (radar-v1): RADAR_PAGE_SPEC.md section 5, PLAN.md RADAR, EXEC.md EXEC-RADAR D2-D6
CREATE FUNCTION public.feature_07_rule_version() RETURNS text LANGUAGE sql IMMUTABLE AS $$ SELECT 'radar-v1'::text $$;

INSERT INTO public."Feature_07_Radar_Filter"
    (rule_version, filter_id, position, column_id, column_label, variant_label, is_default_variant, name, question, warning, sort_label, own_levels) VALUES
('radar-v1', 'S1', 1, 'S1', 'S1', NULL, true, 'Heavy foreign accumulation',
 'Foreign net buying over 5 sessions that is unusually large for this stock.',
 'Unusual for this stock, not large in rupiah. A small stock can be unusual with little money; the 5% floor keeps those out.', 'z-score', false),
('radar-v1', 'S2', 2, 'S2', 'S2', NULL, true, 'Strengthening foreign flow',
 'Foreign buying that rose the most against the 5 sessions before, compared across stocks.',
 'A large rise often means a recovery from heavy selling, not heavy buying.', 'change', false),
('radar-v1', 'S3', 3, 'S3', 'S3', NULL, true, 'Concentrated net buying',
 'Net buying held by a few brokers, compared with stocks that have a similar number of net buyers.',
 'Shows who is buying, not where the price goes. All investors are counted, so foreigners can be selling.', 'average rank', false),
('radar-v1', 'S6', 4, 'S6', 'S6', NULL, true, 'Foreign accumulation (5D)',
 'Foreign net buying that is a large share of all buying and high for this stock''s own year.',
 'High for this stock, measured as a share of buying. Says nothing about rupiah size against other stocks.', 'foreign ratio', false),
('radar-v1', 'S6D_RATIO', 5, 'S6D', 'S6Δ', 'Ratio', true, 'Foreign accumulation, strengthening',
 'Stocks in S6 whose foreign ratio rose against 5 sessions ago.',
 'Built on S6. A rise can start from net selling; read it together with S6''s level. Thresholds are provisional.', 'ratio change', false),
('radar-v1', 'S6D_RANK', 6, 'S6D', 'S6Δ', 'Rank', false, 'Foreign accumulation, strengthening',
 'Stocks in S6 whose rank in the stock''s own year rose against 5 sessions ago.',
 'Built on S6. A rise can start from net selling; read it together with S6''s level. Thresholds are provisional.', 'rank change', false),
('radar-v1', 'S6D_BOTH', 7, 'S6D', 'S6Δ', 'Both', false, 'Foreign accumulation, strengthening',
 'Stocks in S6 whose foreign ratio and its rank in the stock''s own year both rose against 5 sessions ago.',
 'Built on S6. A rise can start from net selling; read it together with S6''s level. Thresholds are provisional.', 'ratio change', false),
('radar-v1', 'S7', 8, 'S7', 'S7', NULL, true, 'Institutions in, retail out',
 'Brokers serving institutions turned net buyers while retail brokers sold, against 5 sessions ago.',
 'Broker labels describe each broker''s usual clients, not the investor of each trade. One broker can make up the whole institutional side.', 'FL34 now', false),
('radar-v1', 'S8', 9, 'S8', 'S8', NULL, true, 'One-day foreign buying spike',
 'One session of foreign net buying far above the stock''s usual day.',
 'One day of buying, often a single block. Strong = all three checks; Watch = large and unusual, but not in the top 5% of its own history.', 'robust z', true);

INSERT INTO public."Feature_07_Radar_Rule" (rule_version, filter_id, cond_key, level, label, threshold, threshold2, status)
SELECT 'radar-v1', r.filter_id, r.cond_key, l.level,
       replace(replace(r.label, '{t}', CASE l.level WHEN 'loose' THEN r.t1 WHEN 'standard' THEN r.t2 ELSE r.t3 END),
               '{u}', coalesce(CASE l.level WHEN 'loose' THEN r.u1 WHEN 'standard' THEN r.u2 ELSE r.u3 END, '')),
       CASE l.level WHEN 'loose' THEN r.t1 WHEN 'standard' THEN r.t2 ELSE r.t3 END::double precision,
       CASE l.level WHEN 'loose' THEN r.u1 WHEN 'standard' THEN r.u2 ELSE r.u3 END::double precision,
       r.status
FROM (VALUES
    ('S1', 'A', 'Foreign net 5D above 0', '0', '0', '0', NULL, NULL, NULL, 'decided'),
    ('S1', 'B', 'Foreign net ≥ 5% of buying', '5', '5', '5', NULL, NULL, NULL, 'decided'),
    ('S1', 'C', 'Above P{t} of its own year', '90', '95', '95', NULL, NULL, '2', 'decided'),
    ('S1', 'D', 'Net buying on 3 or more of 5 days', '3', '3', '3', NULL, NULL, NULL, 'decided'),
    ('S2', 'A', 'Foreign net 5D above 0', '0', '0', '0', NULL, NULL, NULL, 'decided'),
    ('S2', 'B', 'Foreign ratio up vs prior 5 sessions', '0', '0', '0', NULL, NULL, NULL, 'decided'),
    ('S2', 'C', 'Change in the top {u}% of stocks', '75', '90', '95', '25', '10', '5', 'decided'),
    ('S3', 'A', 'At least 10 net buyers', '10', '10', '10', NULL, NULL, NULL, 'decided'),
    ('S3', 'B', 'Concentration ≥ P{t} in its group', '70', '80', '90', NULL, NULL, NULL, 'decided'),
    ('S3', 'C', 'Intensity ≥ P{t}', '60', '75', '90', NULL, NULL, NULL, 'decided'),
    ('S6', 'A', 'Foreign net 5D above 0', '0', '0', '0', NULL, NULL, NULL, 'decided'),
    ('S6', 'B', 'Foreign ratio ≥ {t}%', '3', '5', '10', NULL, NULL, NULL, 'decided'),
    ('S6', 'C', 'Ratio ≥ P{t} of its own year', '90', '95', '98', NULL, NULL, NULL, 'decided'),
    ('S6D_RATIO', 'A', 'Foreign net 5D above 0', '0', '0', '0', NULL, NULL, NULL, 'decided'),
    ('S6D_RATIO', 'B', 'Foreign ratio ≥ {t}%', '3', '5', '10', NULL, NULL, NULL, 'decided'),
    ('S6D_RATIO', 'C', 'Ratio ≥ P{t} of its own year', '90', '95', '98', NULL, NULL, NULL, 'decided'),
    ('S6D_RATIO', 'D', 'Ratio up ≥ {t} pt vs 5 sessions ago', '12', '20', '35', NULL, NULL, NULL, 'provisional'),
    ('S6D_RANK', 'A', 'Foreign net 5D above 0', '0', '0', '0', NULL, NULL, NULL, 'decided'),
    ('S6D_RANK', 'B', 'Foreign ratio ≥ {t}%', '3', '5', '10', NULL, NULL, NULL, 'decided'),
    ('S6D_RANK', 'C', 'Ratio ≥ P{t} of its own year', '90', '95', '98', NULL, NULL, NULL, 'decided'),
    ('S6D_RANK', 'D', 'Rank up ≥ {t} pt vs 5 sessions ago', '40', '65', '90', NULL, NULL, NULL, 'provisional'),
    ('S6D_BOTH', 'A', 'Foreign net 5D above 0', '0', '0', '0', NULL, NULL, NULL, 'decided'),
    ('S6D_BOTH', 'B', 'Foreign ratio ≥ {t}%', '3', '5', '10', NULL, NULL, NULL, 'decided'),
    ('S6D_BOTH', 'C', 'Ratio ≥ P{t} of its own year', '90', '95', '98', NULL, NULL, NULL, 'decided'),
    ('S6D_BOTH', 'D', 'Ratio up ≥ {t} pt and rank up ≥ {u} pt', '12', '20', '35', '40', '65', '90', 'provisional'),
    ('S7', 'A', 'FL34 up ≥ {t} pt vs 5 sessions ago', '10', '20', '40', NULL, NULL, NULL, 'decided'),
    ('S7', 'B', 'FL34 now at 0 or above', '0', '0', '0', NULL, NULL, NULL, 'decided'),
    ('S7', 'C', 'Institutional net above 0', '0', '0', '0', NULL, NULL, NULL, 'decided'),
    ('S7', 'D', 'Institutional side ≥ {t}% of buying', '2', '5', '10', NULL, NULL, NULL, 'decided'),   -- library 12.3 6a
    ('S8', 'A', 'Robust z ≥ 3 on the foreign ratio or on net vs ADV20', '3', '3', '3', NULL, NULL, NULL, 'decided'),
    ('S8', 'B', 'Net ≥ 10% of the 20-day average value', '10', '10', '10', NULL, NULL, NULL, 'decided'),
    ('S8', 'C', 'Net ≥ P95 of its own days', '95', '95', '95', NULL, NULL, NULL, 'decided')
) AS r(filter_id, cond_key, label, t1, t2, t3, u1, u2, u3, status)
CROSS JOIN (VALUES ('loose'), ('standard'), ('strict')) AS l(level)
WHERE r.filter_id <> 'S8' OR l.level = 'standard';   -- S8 has its own levels (Strong/Watch), stored once
-- S1 Strict adds z >= 2 to condition C (threshold2); Loose and Standard have no z test
UPDATE public."Feature_07_Radar_Rule" SET threshold2 = NULL, label = replace(label, '{u}', '')
 WHERE rule_version = 'radar-v1' AND filter_id = 'S1' AND cond_key = 'C' AND level <> 'strict';
UPDATE public."Feature_07_Radar_Rule" SET label = 'Above P95 of its own year and z ≥ 2'
 WHERE rule_version = 'radar-v1' AND filter_id = 'S1' AND cond_key = 'C' AND level = 'strict';
-- S2 C compares the rank with the threshold (P75 / P90 / P95); the label names the top share
UPDATE public."Feature_07_Radar_Rule" SET threshold2 = NULL WHERE rule_version = 'radar-v1' AND filter_id = 'S2' AND cond_key = 'C';

-- ---------------------------------------------------------------------------------------------------------------
-- per ticker: the measures of every Regular session from p_from on (NULL: the whole history)
CREATE FUNCTION public.refresh_feature_07(p_ticker text, p_from date DEFAULT NULL)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
DECLARE
    v_range_start date;
    v_rows bigint;
BEGIN
    IF p_ticker IS NULL THEN
        RAISE EXCEPTION 'refresh_feature_07 needs a ticker';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('refresh_feature_07:' || p_ticker, 0));
    -- 400 sessions before p_from: the deepest need is 272 (252 baseline of U3, whose oldest value needs the 20 sessions of
    -- its ADV20); the ratio's rank needs 252 + 5 + 4 plus every session without a ratio it skips, so the margin keeps a
    -- daily refresh equal to a full one while fewer than 128 such sessions fall in the year (tested in R4)
    IF p_from IS NOT NULL THEN
        SELECT CASE WHEN count(*) = 400 THEN min(d) END INTO v_range_start
        FROM (SELECT DISTINCT trade_date AS d FROM public."Feature_06_Foreign_Domestic"
              WHERE ticker = p_ticker AND trade_date < p_from ORDER BY d DESC LIMIT 400) AS prior;
    END IF;

    DELETE FROM public."Feature_07_Radar_Measure" WHERE ticker = p_ticker AND (p_from IS NULL OR trade_date >= p_from);

    WITH sess AS (
        SELECT trade_date, row_number() OVER (ORDER BY trade_date) AS s
        FROM (SELECT DISTINCT trade_date FROM public."Feature_06_Foreign_Domestic"
              WHERE ticker = p_ticker AND (v_range_start IS NULL OR trade_date >= v_range_start)) AS d
    ), reg AS (
        SELECT trade_date, foreign_buy_1d AS fb, foreign_sell_1d AS fs, domestic_buy_1d AS db
        FROM public."Feature_06_Foreign_Domestic"
        WHERE ticker = p_ticker AND market_board = 'Regular' AND (v_range_start IS NULL OR trade_date >= v_range_start)
    ), f3 AS (
        SELECT date AS trade_date, total_buy_value AS tb3, institutional_net_value AS inst, retail_net_value AS ret
        FROM public."Feature_03_Stock_Broker_Daily"
        WHERE ticker = p_ticker AND market_board = 'Regular' AND (v_range_start IS NULL OR date >= v_range_start)
    ), daily AS (
        SELECT ss.trade_date, ss.s, r.trade_date IS NOT NULL AS active,
               (r.trade_date IS NOT NULL AND c.trade_date IS NULL) AS no_f3,
               coalesce(r.fb, 0) - coalesce(r.fs, 0) AS f, coalesce(r.fb, 0) + coalesce(r.db, 0) AS t,
               coalesce(c.tb3, 0) AS tb3, coalesce(c.inst, 0) AS inst, coalesce(c.ret, 0) AS ret
        FROM sess AS ss
        LEFT JOIN reg AS r ON r.trade_date = ss.trade_date
        LEFT JOIN f3 AS c ON c.trade_date = ss.trade_date
    ), w1 AS (
        SELECT d.*,
               CASE WHEN d.s >= 5 THEN first_value(d.trade_date) OVER w5 END AS s5_from,
               CASE WHEN d.s >= 5 THEN sum(d.f) OVER w5 END AS f5,
               CASE WHEN d.s >= 5 THEN sum(d.t) OVER w5 END AS t5,
               CASE WHEN d.s >= 5 THEN count(*) FILTER (WHERE d.f > 0) OVER w5 END AS buy5,
               CASE WHEN d.s >= 5 THEN max(d.f) OVER w5 END AS fmax5,
               CASE WHEN d.s >= 5 THEN array_agg(d.f) OVER w5 END AS fw5,
               CASE WHEN d.s >= 5 THEN array_agg(d.trade_date) OVER w5 END AS dw5,
               -- QA 2026-11-14: the broker-class measures only from a window whose every Regular session has its
               -- Feature 03 row (a missing row would make a partial window look whole)
               CASE WHEN d.s >= 5 AND NOT bool_or(d.no_f3) OVER w5 THEN sum(d.inst) OVER w5 END AS inst5,
               CASE WHEN d.s >= 5 AND NOT bool_or(d.no_f3) OVER w5 THEN sum(d.ret) OVER w5 END AS ret5,
               CASE WHEN d.s >= 5 AND NOT bool_or(d.no_f3) OVER w5 THEN sum(d.tb3) OVER w5 END AS tb35,
               CASE WHEN d.s >= 5 AND NOT bool_or(d.no_f3) OVER w5 THEN count(*) FILTER (WHERE d.inst > 0) OVER w5 END AS ibuy5,
               CASE WHEN d.s >= 21 THEN avg(d.t) OVER p20 END AS adv20
        FROM daily AS d
        WINDOW w5 AS (ORDER BY d.s ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
               p20 AS (ORDER BY d.s ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING)
    ), w2 AS (
        SELECT w.*,
               CASE WHEN w.t5 > 0 THEN (100 * w.f5 / w.t5)::double precision END AS r5,
               CASE WHEN w.t > 0 THEN (100 * w.f / w.t)::double precision END AS u1,
               CASE WHEN w.adv20 > 0 THEN (100 * w.f / w.adv20)::double precision END AS u3,
               CASE WHEN w.tb35 > 0 THEN (100 * (w.inst5 - w.ret5) / w.tb35)::double precision END AS fl34,
               CASE WHEN w.tb35 > 0 THEN (100 * w.inst5 / w.tb35)::double precision END AS ishare
        FROM w1 AS w
    ), w3 AS (
        SELECT w.*,
               lag(w.r5, 5) OVER o AS r5_prev,
               lag(w.fl34, 5) OVER o AS fl34_prev,
               count(w.f5) OVER b AS n5, avg(w.f5::double precision) OVER b AS m5, stddev_samp(w.f5::double precision) OVER b AS sd5,
               array_agg(w.f5::double precision) OVER b AS h5,
               array_agg(w.u1) OVER b AS hu1, array_agg(w.u3) OVER b AS hu3,
               count(w.f) OVER b AS nn, array_agg(w.f::double precision) OVER b AS hn
        FROM w2 AS w
        WINDOW o AS (ORDER BY w.s), b AS (ORDER BY w.s ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING)
    ), rv AS (
        -- the ratio's own history: the 252 most recent previous sessions that have a ratio. A session whose 5-session
        -- window has no Regular buying at all (only Nego or Tunai trades) has no ratio and is skipped, as a suspension is
        -- ("A1 ok"); counted as missing it would void the rank for a whole year (ARKO, BNBR on 2026-11-03).
        SELECT v.s, CASE WHEN count(*) OVER b2 = 252 THEN public.feature_07_below_percentile(v.r5, array_agg(v.r5) OVER b2, 252) END AS pr5
        FROM w2 AS v WHERE v.r5 IS NOT NULL
        WINDOW b2 AS (ORDER BY v.s ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING)
    ), w5 AS (
        SELECT w.*, rv.pr5, lag(rv.pr5, 5) OVER (ORDER BY w.s) AS pr5_prev
        FROM w3 AS w LEFT JOIN rv ON rv.s = w.s
    )
    INSERT INTO public."Feature_07_Radar_Measure" (trade_date, ticker, s5_from, foreign_net_1d, total_buy_1d,
        total_buy_5d, foreign_net_5d, foreign_ratio_5d, buy_days_5d, foreign_net_5d_pct252, foreign_net_5d_z252,
        foreign_ratio_5d_pct252, foreign_ratio_5d_prev, foreign_ratio_5d_change, foreign_ratio_5d_pct252_prev,
        foreign_ratio_5d_pct252_change, foreign_net_5d_max_day, foreign_net_5d_max_date,
        inst_net_5d, retail_net_5d, fl34_5d, fl34_5d_prev, inst_share_5d, inst_buy_days_5d,
        adv20_prev, foreign_ratio_1d, net_vs_adv20, rz_foreign_ratio_1d, rz_net_vs_adv20, net_1d_pct252)
    SELECT x.trade_date, p_ticker, x.s5_from, x.f, x.t,
           x.t5, x.f5, x.r5, x.buy5,
           CASE WHEN x.n5 = 252 THEN public.feature_07_below_percentile(x.f5::double precision, x.h5, 252) END,
           CASE WHEN x.n5 = 252 AND x.sd5 > 0 THEN (x.f5::double precision - x.m5) / x.sd5 END,
           x.pr5, x.r5_prev, x.r5 - x.r5_prev, x.pr5_prev, x.pr5 - x.pr5_prev,
           x.fmax5,
           (SELECT x.dw5[i] FROM generate_subscripts(x.fw5, 1) AS i WHERE x.fw5[i] = x.fmax5 ORDER BY i DESC LIMIT 1),
           x.inst5, x.ret5, x.fl34, x.fl34_prev, x.ishare, x.ibuy5,
           x.adv20, x.u1, x.u3,
           public.feature_07_robust_z(x.u1, x.hu1, 200),
           public.feature_07_robust_z(x.u3, x.hu3, 200),
           CASE WHEN x.nn = 252 THEN public.feature_07_below_percentile(x.f::double precision, x.hn, 252) END
    FROM w5 AS x
    WHERE x.active AND (p_from IS NULL OR x.trade_date >= p_from);
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END
$function$;
COMMENT ON FUNCTION public.refresh_feature_07(text, date) IS
    'EXEC-RADAR: recalculate the per-ticker Radar measures from p_from on (reads 400 prior sessions of Feature 06 and Feature 03); p_from NULL recalculates the whole history. Call after refresh_feature_06, then refresh_feature_07_day for the dates.';

-- ---------------------------------------------------------------------------------------------------------------
-- per date: universe, gates, cross-stock ranks, S3 from broker rows, then the rule results
CREATE FUNCTION public.refresh_feature_07_day(p_date date)
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
    WITH nb AS (
        SELECT f.ticker, f.broker, sum(f.buy_value - f.sell_value) AS net, sum(f.buy_value) AS buy
        FROM f07_day AS d JOIN public."Feature_05_Foreign_Domestic_Broker_Detail" AS f
          ON f.ticker = d.ticker AND f.market_board = 'Regular' AND f.trade_date BETWEEN d.s5_from AND p_date
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
    'EXEC-RADAR: for one result date, the G2 universe, the Broad/Liquid gates, the cross-stock ranks (S2, S3 with broker rows of Feature 05), then the rule results of every filter, level and gate. Run the dates in order: a run of days reads the previous result date.';

GRANT SELECT ON public."Feature_07_Radar_Measure", public."Feature_07_Radar_Gate", public."Feature_07_Radar_Filter",
    public."Feature_07_Radar_Rule", public."Feature_07_Radar_Result" TO terminal_market_reader, pgweb_reader;

COMMIT;
