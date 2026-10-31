#!/usr/bin/env python3
"""EXEC-INTRADAY-FEATURES S1: write database/migrations/20261031_004_intraday_features.sql.

Nothing about an indicator is typed here. The Feature 04 columns come from `features/feature04/engine.py` (COLUMNS),
the Feature 01 columns from the daily table's own names (1d -> 1bar), and every catalog text from the active
Feature_Catalog rows of the two daily tables (exported read-only with pgweb to a JSON file). Each daily text is
carried over with its period words changed to bars. Only the identity, metadata and intraday-specific rows below are
written here.

  python3 scripts/onboarding/build_intraday_feature_migration.py <fcat_daily.json> > <migration.sql>
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'features/feature04'))
import engine  # noqa: E402  (features/feature04/engine.py; needs TA-Lib)

F01, F04 = 'Feature_01_Stock_Intraday', 'Feature_04_Technical_Indicator_Intraday'
D01, D04 = 'Feature_01_Stock_Daily', 'Feature_04_Technical_Indicator'
TIMEFRAMES = ('5m', '15m', '1h', '4h')
MIGRATION = 'database/migrations/20261031_004_intraday_features.sql'
EVIDENCE = [MIGRATION, 'verification/intraday_features/README.md', 'apps/idx-price-cron/intraday_features.py',
            'apps/idx-price-cron/test_intraday_features.py']
GRAIN = 'ticker x timeframe (5m, 15m, 1h, 4h) x bar_time'
SOURCE_TABLES = 'price_stock_idx_intraday'
SOURCE_COLUMNS = ('price_stock_idx_intraday: ticker, timeframe, bar_time, session_date, open, high, low, close, volume '
                  '(stocks only; IDX_Stock_Universe "Security Type" index excluded)')
REFRESH = 'idx-intraday-cron feature step (intraday_feature_queue) after each daily load; once by the backfill job'
AVAILABILITY = ('Close-of-bar value, loaded once a day after the session close plus Equity_Market_Schedule.'
                'finality_delay_minutes; not available intraday in real time and not exposed to the AI yet.')
WARNING_ADD = (' Intraday bars are split-adjusted as TradingView gives them at load time; a series whose whole stored '
               'scale changed is not written until rescaled (loader verdict SCALE_CHANGED). Session completeness: join '
               'price_stock_idx_intraday_quality on (timeframe, session_date).')
DEP04 = ('State after the last calculated bar of the series (feature04_intraday_state), then the new bars in order; a '
         'change at or before that bar recalculates the whole series. No future bars; ticker and timeframe series are '
         'isolated.')
DEP01 = ('The 120 bars before the first changed bar are read as context, so each written bar equals a full-history '
         'calculation; rows are written from that bar to the end of the series.')

# Feature 04: integers that fit smallint (pattern codes -200..200, 0/1 flags); bar indices stay integer
F04_BAR_INDEX = ('temp_high_bar', 'temp_low_bar')
F04_DROPPED = ('trade_date', 'asset_type', 'calculation_version')   # bar_time/session_date; always equity; in the state


def f04_columns():
    out = []
    for c in engine.COLUMNS:
        if c in F04_DROPPED or c in ('ticker', 'timeframe', 'calculated_at', 'close'):
            continue
        if c.startswith('cdl_') or c in ('inside_bar', 'tracking_high', 'tracking_low', 'break_swing_high'):
            out.append((c, 'smallint'))
        elif c in F04_BAR_INDEX:
            out.append((c, 'integer'))
        else:
            out.append((c, 'double precision'))
    return out


def f01_name(daily):
    return re.sub(r'_(\d+)d(?=_|$)', r'_\1bar', daily)


F01_DAILY = ['close', 'volume', 'close_1d_ago', 'close_5d_ago', 'close_20d_ago', 'close_60d_ago', 'return_1d_pct',
             'return_5d_pct', 'return_20d_pct', 'return_60d_pct', 'abs_return_1d_pct', 'volatility_5d_ann_pct',
             'volatility_20d_ann_pct', 'volatility_60d_ann_pct', 'volatility_5d_change_pct', 'volatility_20d_change_pct',
             'volatility_60d_change_pct', 'volume_avg_20d', 'volume_std_20d', 'volume_ratio_20d', 'volume_zscore_20d',
             'high_20d', 'high_60d', 'drawdown_20d_pct', 'drawdown_60d_pct']
F01_TYPES = {'close': 'numeric NOT NULL', 'volume': 'numeric', 'high_20d': 'numeric', 'high_60d': 'numeric'}


def f01_type(daily):
    return F01_TYPES.get(daily, 'numeric' if daily.endswith('_ago') else 'double precision')


WORDS01 = [  # daily wording -> per-bar wording (Feature 01 texts)
    (r'SQRT\(252\)', 'SQRT(bars_per_year)'), (r'daily decimal returns', 'bar decimal returns'),
    (r'daily returns', 'bar returns'), (r'valid trading observations', 'bars'), (r'valid trading observation', 'bar'),
    (r'trading observations', 'bars'), (r'trading observation', 'bar'), (r'on the trading date', 'in the bar'),
    (r'trading date', 'bar'), (r'ORDER BY date', 'ORDER BY bar_time'), (r'feature date', 'bar'),
    (r'Price_Stock_Indonesia_IDX', 'price_stock_idx_intraday'), (r'\bobservations\b', 'bars'),
    (r'\bobservation\b', 'bar'), (r'\bdaily\b', 'per-bar'),
]
WORDS04 = [(r'trade_date', 'bar_time'), (r'current Daily close', 'the bar close'), (r'Daily close', 'bar close'),
           (r'\bDaily\b', 'intraday'), (r'recent session', 'bar'), (r'\bsession\b', 'bar')]


def words(text, rules, columns=False):
    if text is None:
        return None
    if columns:
        text = re.sub(r'_(\d+)d(?=_|\b)', r'_\1bar', text)
    for a, b in rules:
        text = re.sub(a, b, text)
    return text


def q(v):
    if v is None:
        return 'NULL'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, list):
        return 'ARRAY[' + ', '.join(q(x) for x in v) + ']::text[]'
    return "'" + str(v).replace("'", "''") + "'"


def arr(v):
    """A Postgres array literal exported as text ('{AVG,MEDIAN}') back to a list."""
    if isinstance(v, list):
        return v
    v = (v or '').strip('{}')
    return [x.strip('"') for x in v.split(',')] if v else []


def carried(daily, table, column, rules, columns):
    d = {k: daily[k] for k in daily}
    d.update(feature_table=table, feature_column=column, grain=GRAIN, source_tables=SOURCE_TABLES,
             source_columns=SOURCE_COLUMNS, refresh_trigger=REFRESH, availability_rule=AVAILABILITY,
             dependency_rule=DEP04 if table == F04 else DEP01, version='v1', is_active=True,
             semantic_review_status='CALCULATION_VERIFIED', point_in_time_safe=False,
             validation_evidence=EVIDENCE + [e for e in arr(daily['validation_evidence']) if not e.startswith('verification/feature04/FULL')][:4])
    for k in ('definition', 'calculation', 'lookback_window', 'minimum_history', 'null_rule', 'analytical_interpretation',
              'recommended_use', 'misuse_warning'):
        d[k] = words(d[k], rules, columns)
    d['definition'] = "Per bar of the row's timeframe (one period = one bar). " + d['definition']
    d['historical_metadata_warning'] = (words(d['historical_metadata_warning'], rules, columns) or '').rstrip() + WARNING_ADD
    return d


def own(table, column, category, role, definition, calculation, unit, null_rule, interpretation, use, misuse,
        groupable=True, aggs=('COUNT', 'COUNT_DISTINCT')):
    return dict(feature_table=table, feature_column=column, grain=GRAIN, feature_category=category,
                definition=definition, calculation=calculation, source_tables=SOURCE_TABLES,
                source_columns=SOURCE_COLUMNS, lookback_window='1 source bar', minimum_history='1 source bar',
                unit=unit, null_rule=null_rule, refresh_trigger=REFRESH,
                dependency_rule=DEP04 if table == F04 else DEP01, version='v1', is_active=True, semantic_role=role,
                allowed_aggregations=list(aggs), ranking_interpretation='NOT_APPLICABLE', is_filterable=True,
                is_groupable=groupable, availability_rule=AVAILABILITY, point_in_time_safe=False,
                historical_metadata_warning=WARNING_ADD.strip(), analytical_interpretation=interpretation,
                recommended_use=use, misuse_warning=misuse, semantic_review_status='CALCULATION_VERIFIED',
                validation_evidence=EVIDENCE)


def identity_rows(table):
    return [
        own(table, 'ticker', 'Identity', 'IDENTITY', 'Exact IDX stock ticker of the bar (never the universe index).',
            'Direct copy of price_stock_idx_intraday.ticker; validate_stock_feature_identity refuses an index.', 'code',
            'Never NULL.', 'Identifies the security; not a ranking value.', 'Join and filter by exact ticker.',
            'Do not expect IHSG here: index intraday features are not built yet (user D4, 2026-10-31).'),
        own(table, 'timeframe', 'Identity', 'IDENTITY', 'Bar length of the row: 5m, 15m, 1h or 4h.',
            'Direct copy of price_stock_idx_intraday.timeframe; one partition per value.', 'interval', 'Never NULL.',
            'Every window and period of the row counts bars of this timeframe.',
            'Always filter one timeframe before comparing or aggregating values.',
            'Never mix timeframes in one window, rank or average: a 20-bar window spans 100 minutes at 5m and 80 hours '
            'at 4h.'),
        own(table, 'bar_time', 'Identity', 'IDENTITY', 'Open time of the bar (timestamptz) as TradingView gives it.',
            'Direct copy of price_stock_idx_intraday.bar_time.', 'timestamp', 'Never NULL.',
            'The bar is complete only at its close; the value describes the bar that opens at bar_time.',
            'Order and join intraday rows by bar_time within one ticker and timeframe.',
            'bar_time is the open, not the time the value became known; use the session close for availability.'),
        own(table, 'session_date', 'Identity', 'DIMENSION', 'IDX trading date of the bar in Asia/Jakarta.',
            'Direct copy of price_stock_idx_intraday.session_date.', 'date', 'Never NULL.',
            'Groups the bars of one session; joins the daily Feature tables and the session quality table.',
            'Join price_stock_idx_intraday_quality on (timeframe, session_date) to keep only COMPLETE sessions.',
            'A session date is not a daily observation: aggregate bars before comparing with daily features.'),
        own(table, 'calculated_at', 'Metadata', 'DIMENSION', 'Time of the calculation that wrote the row.',
            'Statement or job time of the write.', 'timestamp', 'Never NULL.',
            'A calculation timestamp is not historical source availability or publication time.',
            'Audit the calculation execution independently of the bar time.',
            'Never treat calculated_at as the time the market value was known.'),
    ]


def main(path):
    daily = {(r['feature_table'], r['feature_column']): r for r in json.load(open(path))}
    f04 = f04_columns()
    rows04 = identity_rows(F04)
    rows04.append(carried(daily[(D04, 'close')], F04, 'close', WORDS04, False))
    rows04 += [carried(daily[(D04, c)], F04, c, WORDS04, False) for c, _ in f04]
    rows01 = identity_rows(F01)
    rows01 += [carried(daily[(D01, c)], F01, f01_name(c), WORDS01, True) for c in F01_DAILY]
    rows01.append(own(F01, 'bars_per_year', 'Metadata', 'DIMENSION',
                      'Bars per year used to annualise the volatility columns of the row.',
                      'round(252 x the mean IHSG bars of the COMPLETE sessions of the timeframe in '
                      'price_stock_idx_intraday_quality) at calculation time.', 'bars per year', 'Never NULL.',
                      "Annualisation factor of the row's volatility: volatility = stddev of bar returns x "
                      'sqrt(bars_per_year) x 100.', 'Read it to re-derive or compare annualised volatility.',
                      'It follows the session length of the timeframe (shorter Friday sessions lower the mean); do '
                      'not use it as a count of bars in a given year.', groupable=False))
    cols01 = [(f01_name(c), f01_type(c)) for c in F01_DAILY]

    sql = []
    w = sql.append
    w(f"""-- EXEC-INTRADAY-FEATURES S1 (user go 2026-10-31: "D1 - A / D2 - A / D3 - W1 / D4 OK", then "Go").
-- Generated by scripts/onboarding/build_intraday_feature_migration.py from features/feature04/engine.py and the active
-- Feature_Catalog rows of {D01} and {D04} (read-only export, 2026-10-31).
-- Feature 01 and Feature 04 per intraday bar (5m, 15m, 1h, 4h) of the IDX stocks in price_stock_idx_intraday, the
-- daily formulas with one period = one bar:
-- * Feature 01: refresh_feature_01_stock_intraday below is the live refresh_feature_01_stock_daily with the bar key;
--   annualisation sqrt(bars_per_year), bars_per_year derived from price_stock_idx_intraday_quality (252 x the mean IHSG
--   bars of the COMPLETE sessions of the timeframe) and stored on every row (D2 = a: no other change).
-- * Feature 04: features/feature04/engine.py and incremental.py, unchanged, through apps/idx-price-cron/
--   intraday_features.py (W1); the incremental state after the last bar of each series is in feature04_intraday_state.
-- * The universe index never enters (validate_stock_feature_identity, the daily guard; IHSG intraday features later, D4).
-- * Session completeness is not copied: join price_stock_idx_intraday_quality on (timeframe, session_date).
-- * intraday_feature_queue: the loader enqueues the first changed bar of every (ticker, timeframe) it writes, in the
--   same transaction; the feature step of idx-intraday-cron works the queue.
BEGIN;
""")
    for table, cols, extra in ((F01, cols01, ['bars_per_year integer NOT NULL CHECK (bars_per_year > 0)']),
                               (F04, [('close', 'double precision NOT NULL')] + f04, [])):
        lines = ['ticker text NOT NULL', 'timeframe text NOT NULL', 'bar_time timestamptz NOT NULL',
                 'session_date date NOT NULL'] + [f'{c} {t}' for c, t in cols] + extra + [
                 'calculated_at timestamptz NOT NULL DEFAULT statement_timestamp()',
                 f'CONSTRAINT "{table}_pkey" PRIMARY KEY (ticker, timeframe, bar_time)',
                 f"CONSTRAINT \"{table}_timeframe_check\" CHECK (timeframe IN ({', '.join(q(t) for t in TIMEFRAMES)}))"]
        w(f'CREATE TABLE public."{table}" (\n    ' + ',\n    '.join(lines) + '\n) PARTITION BY LIST (timeframe);')
        for t in TIMEFRAMES:
            w(f'CREATE TABLE public."{table}_{t}" PARTITION OF public."{table}" FOR VALUES IN ({q(t)});')
        w(f'CREATE TRIGGER stock_feature_index_guard BEFORE INSERT OR UPDATE OF ticker ON public."{table}"\n'
          f'    FOR EACH ROW EXECUTE FUNCTION public.validate_stock_feature_identity();')
        w('')
    w(SQL_FIXED)
    w(catalog_sql(rows01, rows04, cols01, f04))
    w('COMMIT;')
    print('\n'.join(sql))


SQL_FIXED = r"""CREATE TABLE public.feature04_intraday_state (
    ticker text NOT NULL,
    timeframe text NOT NULL CHECK (timeframe IN ('5m', '15m', '1h', '4h')),
    last_bar_time timestamptz NOT NULL,
    bars integer NOT NULL CHECK (bars > 0),
    state jsonb NOT NULL,
    calculation_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    PRIMARY KEY (ticker, timeframe)
);

CREATE TABLE public.intraday_feature_queue (
    ticker text NOT NULL,
    timeframe text NOT NULL CHECK (timeframe IN ('5m', '15m', '1h', '4h')),
    dirty_from timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'DONE', 'FAILED')),
    attempts integer NOT NULL DEFAULT 0,
    last_error text,
    enqueued_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    done_at timestamptz,
    PRIMARY KEY (ticker, timeframe)
);
CREATE INDEX intraday_feature_queue_open ON public.intraday_feature_queue (timeframe, ticker) WHERE status <> 'DONE';

CREATE OR REPLACE FUNCTION public.refresh_feature_01_stock_intraday(
    p_timeframe text, p_tickers text[], p_from timestamptz DEFAULT NULL)
RETURNS bigint
LANGUAGE plpgsql
AS $fn$
-- The live refresh_feature_01_stock_daily (2026-10-31) with the bar key (ticker, timeframe, bar_time): the same windows
-- and formulas, one period = one bar, volatility annualised with sqrt(bars_per_year). p_from NULL: every bar of the
-- tickers; else the 120 bars before p_from are read as context (the longest dependency: volatility_60bar_change_pct)
-- and the bars from p_from to the end of the series are written.
DECLARE
    affected_rows bigint := 0;
    v_bars_per_year integer;
BEGIN
    IF p_timeframe IS NULL OR p_timeframe NOT IN ('5m', '15m', '1h', '4h') THEN
        RAISE EXCEPTION 'p_timeframe must be 5m, 15m, 1h or 4h, got %', p_timeframe;
    END IF;
    IF p_tickers IS NULL OR cardinality(p_tickers) = 0 THEN
        RETURN 0;
    END IF;
    IF EXISTS (SELECT 1 FROM unnest(p_tickers) AS r(t) WHERE r.t IS NULL OR btrim(r.t) = '') THEN
        RAISE EXCEPTION 'p_tickers cannot contain NULL or blank values';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('public.Feature_01_Stock_Intraday.refresh'), hashtext(p_timeframe));
    SELECT round(252 * avg(index_bars))::integer INTO v_bars_per_year
      FROM public.price_stock_idx_intraday_quality
     WHERE timeframe = p_timeframe AND status = 'COMPLETE' AND index_bars > 0;
    IF v_bars_per_year IS NULL THEN
        RAISE EXCEPTION 'no COMPLETE session of % in price_stock_idx_intraday_quality: bars_per_year cannot be derived',
            p_timeframe;
    END IF;

    INSERT INTO public."Feature_01_Stock_Intraday" (
        ticker, timeframe, bar_time, session_date, close, volume,
        close_1bar_ago, close_5bar_ago, close_20bar_ago, close_60bar_ago,
        return_1bar_pct, return_5bar_pct, return_20bar_pct, return_60bar_pct, abs_return_1bar_pct,
        volatility_5bar_ann_pct, volatility_20bar_ann_pct, volatility_60bar_ann_pct,
        volatility_5bar_change_pct, volatility_20bar_change_pct, volatility_60bar_change_pct,
        volume_avg_20bar, volume_std_20bar, volume_ratio_20bar, volume_zscore_20bar,
        high_20bar, high_60bar, drawdown_20bar_pct, drawdown_60bar_pct, bars_per_year, calculated_at)
    WITH wanted AS (
        SELECT DISTINCT r.t AS ticker FROM unnest(p_tickers) AS r(t) WHERE NOT public.is_universe_index(r.t)
    ),
    bounds AS (
        SELECT w.ticker,
               CASE WHEN p_from IS NULL THEN '-infinity'::timestamptz ELSE coalesce((
                   SELECT b.bar_time FROM public.price_stock_idx_intraday b
                    WHERE b.ticker = w.ticker AND b.timeframe = p_timeframe AND b.bar_time < p_from
                    ORDER BY b.bar_time DESC OFFSET 119 LIMIT 1), '-infinity'::timestamptz) END AS context_from
          FROM wanted w
    ),
    source_rows AS (
        SELECT p.ticker::text AS ticker, p.bar_time, p.session_date, p.close, p.volume
          FROM public.price_stock_idx_intraday p
          JOIN bounds ON bounds.ticker = p.ticker
         WHERE p.timeframe = p_timeframe AND p.bar_time >= bounds.context_from
    ),
    lagged AS (
        SELECT source_rows.*,
               lag(close, 1) OVER w AS close_1bar_ago, lag(close, 5) OVER w AS close_5bar_ago,
               lag(close, 20) OVER w AS close_20bar_ago, lag(close, 60) OVER w AS close_60bar_ago
          FROM source_rows WINDOW w AS (PARTITION BY ticker ORDER BY bar_time)
    ),
    return_metrics AS (
        SELECT lagged.*,
               close::double precision / NULLIF(close_1bar_ago::double precision, 0.0) - 1.0 AS bar_return_decimal,
               (close::double precision / NULLIF(close_1bar_ago::double precision, 0.0) - 1.0) * 100.0 AS return_1bar_pct,
               (close::double precision / NULLIF(close_5bar_ago::double precision, 0.0) - 1.0) * 100.0 AS return_5bar_pct,
               (close::double precision / NULLIF(close_20bar_ago::double precision, 0.0) - 1.0) * 100.0 AS return_20bar_pct,
               (close::double precision / NULLIF(close_60bar_ago::double precision, 0.0) - 1.0) * 100.0 AS return_60bar_pct
          FROM lagged
    ),
    rolling AS (
        SELECT return_metrics.*,
               count(bar_return_decimal) OVER w5 AS return_count_5, count(bar_return_decimal) OVER w20 AS return_count_20,
               count(bar_return_decimal) OVER w60 AS return_count_60,
               stddev_samp(bar_return_decimal) OVER w5 AS return_std_5,
               stddev_samp(bar_return_decimal) OVER w20 AS return_std_20,
               stddev_samp(bar_return_decimal) OVER w60 AS return_std_60,
               count(volume) OVER w20 AS volume_count_20,
               avg(volume::double precision) OVER w20 AS volume_avg_20_raw,
               stddev_samp(volume::double precision) OVER w20 AS volume_std_20_raw,
               count(close) OVER w20 AS close_count_20, count(close) OVER w60 AS close_count_60,
               max(close) OVER w20 AS high_20_raw, max(close) OVER w60 AS high_60_raw
          FROM return_metrics
        WINDOW w5 AS (PARTITION BY ticker ORDER BY bar_time ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
               w20 AS (PARTITION BY ticker ORDER BY bar_time ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
               w60 AS (PARTITION BY ticker ORDER BY bar_time ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
    ),
    window_metrics AS (
        SELECT rolling.*,
               CASE WHEN return_count_5 = 5 THEN return_std_5 * sqrt(v_bars_per_year::double precision) * 100.0 END
                   AS volatility_5bar_ann_pct,
               CASE WHEN return_count_20 = 20 THEN return_std_20 * sqrt(v_bars_per_year::double precision) * 100.0 END
                   AS volatility_20bar_ann_pct,
               CASE WHEN return_count_60 = 60 THEN return_std_60 * sqrt(v_bars_per_year::double precision) * 100.0 END
                   AS volatility_60bar_ann_pct,
               CASE WHEN volume_count_20 = 20 THEN volume_avg_20_raw END AS volume_avg_20bar,
               CASE WHEN volume_count_20 = 20 THEN volume_std_20_raw END AS volume_std_20bar,
               CASE WHEN close_count_20 = 20 THEN high_20_raw END AS high_20bar,
               CASE WHEN close_count_60 = 60 THEN high_60_raw END AS high_60bar
          FROM rolling
    ),
    with_volatility_history AS (
        SELECT window_metrics.*,
               lag(volatility_5bar_ann_pct, 5) OVER w AS volatility_5bar_ago,
               lag(volatility_20bar_ann_pct, 20) OVER w AS volatility_20bar_ago,
               lag(volatility_60bar_ann_pct, 60) OVER w AS volatility_60bar_ago
          FROM window_metrics WINDOW w AS (PARTITION BY ticker ORDER BY bar_time)
    )
    SELECT m.ticker, p_timeframe, m.bar_time, m.session_date, m.close, m.volume,
           m.close_1bar_ago, m.close_5bar_ago, m.close_20bar_ago, m.close_60bar_ago,
           m.return_1bar_pct, m.return_5bar_pct, m.return_20bar_pct, m.return_60bar_pct, abs(m.return_1bar_pct),
           m.volatility_5bar_ann_pct, m.volatility_20bar_ann_pct, m.volatility_60bar_ann_pct,
           CASE WHEN m.volatility_5bar_ann_pct IS NOT NULL AND m.volatility_5bar_ago IS NOT NULL
                     AND m.volatility_5bar_ago <> 0.0
                THEN (m.volatility_5bar_ann_pct / m.volatility_5bar_ago - 1.0) * 100.0 END,
           CASE WHEN m.volatility_20bar_ann_pct IS NOT NULL AND m.volatility_20bar_ago IS NOT NULL
                     AND m.volatility_20bar_ago <> 0.0
                THEN (m.volatility_20bar_ann_pct / m.volatility_20bar_ago - 1.0) * 100.0 END,
           CASE WHEN m.volatility_60bar_ann_pct IS NOT NULL AND m.volatility_60bar_ago IS NOT NULL
                     AND m.volatility_60bar_ago <> 0.0
                THEN (m.volatility_60bar_ann_pct / m.volatility_60bar_ago - 1.0) * 100.0 END,
           m.volume_avg_20bar, m.volume_std_20bar,
           CASE WHEN m.volume_avg_20bar IS NOT NULL AND m.volume_avg_20bar <> 0.0
                THEN m.volume::double precision / m.volume_avg_20bar END,
           CASE WHEN m.volume_std_20bar IS NOT NULL AND m.volume_std_20bar <> 0.0
                THEN (m.volume::double precision - m.volume_avg_20bar) / m.volume_std_20bar END,
           m.high_20bar, m.high_60bar,
           CASE WHEN m.high_20bar IS NOT NULL AND m.high_20bar <> 0
                THEN (m.close::double precision / m.high_20bar::double precision - 1.0) * 100.0 END,
           CASE WHEN m.high_60bar IS NOT NULL AND m.high_60bar <> 0
                THEN (m.close::double precision / m.high_60bar::double precision - 1.0) * 100.0 END,
           v_bars_per_year, statement_timestamp()
      FROM with_volatility_history m
     WHERE p_from IS NULL OR m.bar_time >= p_from
    ON CONFLICT (ticker, timeframe, bar_time) DO UPDATE SET
        session_date = EXCLUDED.session_date, close = EXCLUDED.close, volume = EXCLUDED.volume,
        close_1bar_ago = EXCLUDED.close_1bar_ago, close_5bar_ago = EXCLUDED.close_5bar_ago,
        close_20bar_ago = EXCLUDED.close_20bar_ago, close_60bar_ago = EXCLUDED.close_60bar_ago,
        return_1bar_pct = EXCLUDED.return_1bar_pct, return_5bar_pct = EXCLUDED.return_5bar_pct,
        return_20bar_pct = EXCLUDED.return_20bar_pct, return_60bar_pct = EXCLUDED.return_60bar_pct,
        abs_return_1bar_pct = EXCLUDED.abs_return_1bar_pct,
        volatility_5bar_ann_pct = EXCLUDED.volatility_5bar_ann_pct,
        volatility_20bar_ann_pct = EXCLUDED.volatility_20bar_ann_pct,
        volatility_60bar_ann_pct = EXCLUDED.volatility_60bar_ann_pct,
        volatility_5bar_change_pct = EXCLUDED.volatility_5bar_change_pct,
        volatility_20bar_change_pct = EXCLUDED.volatility_20bar_change_pct,
        volatility_60bar_change_pct = EXCLUDED.volatility_60bar_change_pct,
        volume_avg_20bar = EXCLUDED.volume_avg_20bar, volume_std_20bar = EXCLUDED.volume_std_20bar,
        volume_ratio_20bar = EXCLUDED.volume_ratio_20bar, volume_zscore_20bar = EXCLUDED.volume_zscore_20bar,
        high_20bar = EXCLUDED.high_20bar, high_60bar = EXCLUDED.high_60bar,
        drawdown_20bar_pct = EXCLUDED.drawdown_20bar_pct, drawdown_60bar_pct = EXCLUDED.drawdown_60bar_pct,
        bars_per_year = EXCLUDED.bars_per_year, calculated_at = EXCLUDED.calculated_at;

    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    RETURN affected_rows;
END
$fn$;

DO $grant$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        GRANT SELECT ON public."Feature_01_Stock_Intraday", public."Feature_04_Technical_Indicator_Intraday",
              public.feature04_intraday_state, public.intraday_feature_queue TO pgweb_reader;
        GRANT SELECT ON public."Feature_01_Stock_Intraday_5m", public."Feature_01_Stock_Intraday_15m",
              public."Feature_01_Stock_Intraday_1h", public."Feature_01_Stock_Intraday_4h",
              public."Feature_04_Technical_Indicator_Intraday_5m", public."Feature_04_Technical_Indicator_Intraday_15m",
              public."Feature_04_Technical_Indicator_Intraday_1h", public."Feature_04_Technical_Indicator_Intraday_4h"
              TO pgweb_reader;
    END IF;
END $grant$;
"""


def catalog_sql(rows01, rows04, cols01, cols04):
    out = []
    w = out.append
    w("""INSERT INTO public."Table_Catalog"(table_schema, table_name, category, definition, grain, primary_key_columns,
 source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
 readiness_mode, readiness_date_column, observation_date_column, availability_rule, point_in_time_status)
VALUES""")
    tables = [
        (F01, 'Feature', 'Feature 01 per intraday bar of the IDX stocks: returns, realized volatility, volume and price '
         'positioning over 1, 5, 20 and 60 bars of the row timeframe (5m, 15m, 1h, 4h), the formulas of '
         'Feature_01_Stock_Daily with one period = one bar; volatility annualised with sqrt(bars_per_year). No IHSG. '
         'Session completeness: join price_stock_idx_intraday_quality.', GRAIN,
         ['ticker', 'timeframe', 'bar_time'], 'SQL function refresh_feature_01_stock_intraday',
         ['price_stock_idx_intraday', 'price_stock_idx_intraday_quality'],
         [MIGRATION, 'apps/idx-price-cron/intraday_features.py'],
         'From the first changed bar of each queued (ticker, timeframe) to the end of the series, after each daily load '
         '(idx-intraday-cron); history once by the backfill job.', ['refresh_feature_01_stock_intraday(text,text[],timestamptz)'],
         'DATA_DATE', 'session_date', 'session_date', AVAILABILITY, 'PARTIAL'),
        (F04, 'Feature', 'Feature 04 per intraday bar of the IDX stocks: the technical indicators, TA-Lib candlestick '
         'codes and SMI swing state of Feature_04_Technical_Indicator computed by the same engine '
         '(features/feature04/engine.py, incremental.py) with one period = one bar of the row timeframe (5m, 15m, 1h, '
         '4h). No IHSG. calculation_version per series in feature04_intraday_state.', GRAIN,
         ['ticker', 'timeframe', 'bar_time'], 'Python / TA-Lib (apps/idx-price-cron/intraday_features.py)',
         ['price_stock_idx_intraday'], [MIGRATION, 'apps/idx-price-cron/intraday_features.py', 'features/feature04/engine.py',
                                        'features/feature04/incremental.py'],
         'New bars from the stored state of each queued series after each daily load; a change at or before the last '
         'calculated bar recalculates the whole series; history once by the backfill job (full calculation).', [],
         'DATA_DATE', 'session_date', 'session_date', AVAILABILITY, 'PARTIAL'),
        ('feature04_intraday_state', 'System', 'Incremental Feature 04 state after the last calculated bar of each '
         'intraday series (ticker, timeframe): bars counted, last bar_time, engine state and calculation_version.',
         'One ticker and timeframe', ['ticker', 'timeframe'], 'apps/idx-price-cron/intraday_features.py',
         ['Feature_04_Technical_Indicator_Intraday'], [MIGRATION, 'apps/idx-price-cron/intraday_features.py'],
         'Replaced after every calculation of the series.', [], 'NOT_APPLICABLE', None, None,
         'Operational state, not market data; not exposed to the AI.', 'NOT_APPLICABLE'),
        ('intraday_feature_queue', 'System', 'Intraday feature work: per (ticker, timeframe) the first bar the loader '
         'changed since the last calculation, with status PENDING, DONE or FAILED, attempts and the last error.',
         'One ticker and timeframe', ['ticker', 'timeframe'], 'apps/idx-price-cron/intraday_update.py',
         ['price_stock_idx_intraday'], [MIGRATION, 'apps/idx-price-cron/intraday_update.py', 'apps/idx-price-cron/intraday_features.py'],
         'Written with the bars (earliest changed bar kept); worked by the feature step of idx-intraday-cron; a FAILED '
         'item is retried by the next run.', [], 'NOT_APPLICABLE', None, None,
         'Operational queue, not market data; not exposed to the AI.', 'NOT_APPLICABLE'),
    ]
    vals = []
    for t in tables:
        (name, cat, definition, grain, pk, system, src, paths, rule, funcs, mode, rcol, ocol, avail, pit) = t
        vals.append('(' + ', '.join([q('public'), q(name), q(cat), q(definition), q(grain), q(pk), q(system), q(src),
                                     q(paths), q(rule), q(funcs), q('VERIFIED'), q(mode), q(rcol), q(ocol), q(avail),
                                     q(pit)]) + ')')
    w(',\n'.join(vals) + ';\n')

    # Column_Catalog: the feature tables from their Feature_Catalog definition, the system tables written here
    col_def = {(r['feature_table'], r['feature_column']): r for r in rows01 + rows04}
    system_cols = {
        ('feature04_intraday_state', 'ticker'): 'IDX stock ticker of the series.',
        ('feature04_intraday_state', 'timeframe'): 'Bar length of the series.',
        ('feature04_intraday_state', 'last_bar_time'): 'bar_time of the last bar the state includes.',
        ('feature04_intraday_state', 'bars'): 'Bars of the series the state includes (the next bar has this zero-based index).',
        ('feature04_intraday_state', 'state'): 'features/feature04/incremental.py state after the last bar (JSON).',
        ('feature04_intraday_state', 'calculation_version'): 'engine.VERSION the state and the rows of the series were calculated with.',
        ('feature04_intraday_state', 'updated_at'): 'Time the state was written.',
        ('intraday_feature_queue', 'ticker'): 'IDX stock ticker of the series to calculate.',
        ('intraday_feature_queue', 'timeframe'): 'Bar length of the series to calculate.',
        ('intraday_feature_queue', 'dirty_from'): 'Earliest bar_time the loader wrote or changed since the last calculation.',
        ('intraday_feature_queue', 'status'): 'PENDING, DONE or FAILED.',
        ('intraday_feature_queue', 'attempts'): 'Calculations tried since the item was last enqueued.',
        ('intraday_feature_queue', 'last_error'): 'Class and message of the last failure.',
        ('intraday_feature_queue', 'enqueued_at'): 'Time of the last enqueue.',
        ('intraday_feature_queue', 'done_at'): 'Time the last calculation finished.',
    }
    d_rows = [(t, c, r['definition'], r['unit'], r['null_rule']) for (t, c), r in col_def.items()]
    d_rows += [(t, c, text, None, 'See definition.') for (t, c), text in system_cols.items()]
    w('WITH d(table_name, column_name, definition, unit, null_rule) AS (VALUES\n ' + ',\n '.join(
        '(' + ', '.join(q(x) for x in r) + ')' for r in d_rows) + ')')
    w("""INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 c.column_name IN ('ticker', 'timeframe', 'bar_time') OR (c.table_name IN ('feature04_intraday_state', 'intraday_feature_queue')
  AND c.column_name IN ('ticker', 'timeframe')),
 d.definition,
 CASE WHEN c.table_name = 'Feature_01_Stock_Intraday' THEN 'refresh_feature_01_stock_intraday(text,text[],timestamptz)'
      WHEN c.table_name = 'Feature_04_Technical_Indicator_Intraday' THEN 'features/feature04/engine.py via apps/idx-price-cron/intraday_features.py'
      ELSE 'apps/idx-price-cron/intraday_features.py' END,
 d.unit, d.null_rule, ARRAY['""" + MIGRATION + """'], 'VERIFIED'
FROM information_schema.columns c JOIN d USING (table_name, column_name)
WHERE c.table_schema = 'public' AND c.table_name IN ('Feature_01_Stock_Intraday', 'Feature_04_Technical_Indicator_Intraday',
      'feature04_intraday_state', 'intraday_feature_queue')
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;
""")
    keys = ['feature_table', 'feature_column', 'grain', 'feature_category', 'definition', 'calculation', 'source_tables',
            'source_columns', 'lookback_window', 'minimum_history', 'unit', 'null_rule', 'refresh_trigger',
            'dependency_rule', 'version', 'is_active', 'semantic_role', 'allowed_aggregations',
            'ranking_interpretation', 'is_filterable', 'is_groupable', 'availability_rule', 'point_in_time_safe',
            'historical_metadata_warning', 'analytical_interpretation', 'recommended_use', 'misuse_warning',
            'semantic_review_status', 'validation_evidence']

    def lit(r, k):
        v = r[k]
        if k in ('allowed_aggregations', 'validation_evidence'):
            return q(arr(v))
        if k in ('is_active', 'is_filterable', 'is_groupable', 'point_in_time_safe'):
            return q(v if isinstance(v, bool) else str(v) == 'True')
        return q(v)
    w(f'INSERT INTO public."Feature_Catalog"({", ".join(keys)})\nVALUES\n' + ',\n'.join(
        '(' + ', '.join(lit(r, k) for k in keys) + ')' for r in rows01 + rows04) + ';\n')
    w("""INSERT INTO public."Feature_Relationship_Catalog"(left_feature_table, right_feature_table, left_join_columns,
 right_join_columns, relationship_type, safe_output_grain, requires_preaggregation, definition, version, is_active)
VALUES
('Feature_04_Technical_Indicator_Intraday', 'Feature_01_Stock_Intraday', ARRAY['ticker', 'timeframe', 'bar_time'],
 ARRAY['ticker', 'timeframe', 'bar_time'], 'ONE_TO_ONE', 'ticker x timeframe x bar_time', false,
 'The same bar in both intraday Feature tables: exact join on ticker, timeframe and bar_time.', 'v1', true),
('Feature_01_Stock_Intraday', 'Feature_01_Stock_Daily', ARRAY['ticker', 'session_date'], ARRAY['ticker', 'date'],
 'MANY_TO_ONE', 'ticker x timeframe x bar_time', false,
 'Each bar with the daily Feature 01 row of its session (one timeframe at a time); daily values describe the whole '
 'session close, so they are known only after the session: never read them as known at an earlier bar.', 'v1', true),
('Feature_04_Technical_Indicator_Intraday', 'Feature_04_Technical_Indicator', ARRAY['ticker', 'session_date'],
 ARRAY['ticker', 'trade_date'], 'MANY_TO_ONE', 'ticker x timeframe x bar_time', false,
 'Each bar with the daily Feature 04 row of its session (filter the daily table to asset_type equity and timeframe '
 'Daily, one intraday timeframe at a time); the daily row is known only after the session close.', 'v1', true);
""")
    w("""DO $check$ DECLARE missing int; BEGIN
    SELECT count(*) INTO missing FROM information_schema.columns c
     WHERE c.table_schema = 'public' AND c.table_name IN ('Feature_01_Stock_Intraday', 'Feature_04_Technical_Indicator_Intraday',
           'feature04_intraday_state', 'intraday_feature_queue')
       AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_schema = 'public'
                       AND k.table_name = c.table_name AND k.column_name = c.column_name);
    IF missing > 0 THEN RAISE EXCEPTION '% columns lack a Column_Catalog row', missing; END IF;
    SELECT count(*) INTO missing FROM information_schema.columns c
     WHERE c.table_schema = 'public' AND c.table_name IN ('Feature_01_Stock_Intraday', 'Feature_04_Technical_Indicator_Intraday')
       AND NOT EXISTS (SELECT 1 FROM public."Feature_Catalog" f WHERE f.is_active AND f.feature_table = c.table_name
                       AND f.feature_column = c.column_name);
    IF missing > 0 THEN RAISE EXCEPTION '% feature columns lack an active Feature_Catalog row', missing; END IF;
    SELECT count(*) INTO missing FROM public."Feature_Catalog" f
     WHERE f.is_active AND f.feature_table IN ('Feature_01_Stock_Intraday', 'Feature_04_Technical_Indicator_Intraday')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns c WHERE c.table_schema = 'public'
                       AND c.table_name = f.feature_table AND c.column_name = f.feature_column);
    IF missing > 0 THEN RAISE EXCEPTION '% Feature_Catalog rows name no column', missing; END IF;
    SELECT count(*) INTO missing FROM pg_inherits
     WHERE inhparent IN ('public."Feature_01_Stock_Intraday"'::regclass, 'public."Feature_04_Technical_Indicator_Intraday"'::regclass);
    IF missing <> 8 THEN RAISE EXCEPTION 'expected 8 partitions, found %', missing; END IF;
END $check$;
""")
    return '\n'.join(out)


if __name__ == '__main__':
    main(sys.argv[1])
