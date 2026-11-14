"""Feature refresh of the stockbit-updater service: IDX_Broker_Summary -> F05 -> F02 -> F03, F05 -> F06, then the
INDEX tables (UPDATE_TABLE.md part A, section 4; the routines are the database's own, unchanged), and at the end of
the round the Radar tables of Feature 07 (refresh_radar, EXEC-RADAR).

What to refresh is derived from the data, not from the dates the loader wrote: every date whose per-date totals in
IDX_Broker_Summary differ from Feature 05 (rows, buy, sell, lots, known frequency rows and frequency). A manual upload
(for example the non-four-letter symbols the user loads separately, decision K1) or a correction of an old date is
picked up the same way. Each step is checked as in the 2026-10-25 runs and stops the refresh when a check fails.

EXEC-UNIVERSE-BROKER S2 (2026-11-05): Feature 05 holds only tickers of IDX_Stock_Universe from now on
(refresh_feature_05), so every comparison with it uses the universe rows of IDX_Broker_Summary; a ticker added to the
universe makes its dates differ and is computed by the next refresh. The IHSG INDEX tables sum every symbol, so their
rebuild is due when the all-symbol totals of a date differ from Feature_05_..._INDEX (index_needed); an upload of
codes outside the universe changes only that.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import date, timedelta

import psycopg

F02 = 'public."Feature_02_Broker_Rolling"'
F03 = 'public."Feature_03_Stock_Broker_Daily"'
F05 = 'public."Feature_05_Foreign_Domestic_Broker_Detail"'
F06 = 'public."Feature_06_Foreign_Domestic"'
SRC = 'public."IDX_Broker_Summary"'
F05_INDEX = 'public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX"'
UNIVERSE = '(SELECT "Ticker" FROM public."IDX_Stock_Universe")'

# One pass over the source: the universe totals of each date (compared with Feature 05) and the all-symbol totals
# (compared with the IHSG INDEX table). Columns: date, Feature 05 differs, source has no universe row, INDEX differs.
PER_DATE_TEMPLATE = f"""
WITH s AS (SELECT "Date" AS d,
                  count(*) FILTER (WHERE u) n, sum("Buy Value") FILTER (WHERE u) bv, sum("Sell Value") FILTER (WHERE u) sv,
                  sum("Buy Lots") FILTER (WHERE u) bl, sum("Sell Lots") FILTER (WHERE u) sl,
                  count(buy_freq) FILTER (WHERE u) fr, sum(buy_freq) FILTER (WHERE u) bf, sum(sell_freq) FILTER (WHERE u) sf,
                  sum("Buy Value") abv, sum("Sell Value") asv, sum("Buy Lots") abl, sum("Sell Lots") asl,
                  sum(buy_freq) abf, sum(sell_freq) asf
           FROM (SELECT b.*, b."Symbol" IN {UNIVERSE} AS u FROM {SRC} b WHERE {{dates}}) x GROUP BY 1),
     f AS (SELECT trade_date AS d, count(*) n, sum(buy_value) bv, sum(sell_value) sv, sum(buy_lots) bl,
                  sum(sell_lots) sl, count(buy_freq) fr, sum(buy_freq) bf, sum(sell_freq) sf
           FROM {F05} WHERE ticker IN {UNIVERSE} AND {{f_dates}} GROUP BY 1),
     i AS (SELECT trade_date AS d, sum(buy_value) bv, sum(sell_value) sv, sum(buy_lots) bl, sum(sell_lots) sl,
                  sum(buy_freq) bf, sum(sell_freq) sf
           FROM {F05_INDEX} WHERE ticker = 'IHSG' AND {{f_dates}} GROUP BY 1),
     j AS (SELECT coalesce(s.d, f.d, i.d) AS d,
                  (coalesce(s.n, 0) > 0 OR f.d IS NOT NULL) AND (f.d IS NULL OR coalesce(s.n, 0) = 0
                   OR (s.n, s.bv, s.sv, s.bl, s.sl, s.fr, coalesce(s.bf, 0), coalesce(s.sf, 0))
                      IS DISTINCT FROM (f.n, f.bv, f.sv, f.bl, f.sl, f.fr, coalesce(f.bf, 0), coalesce(f.sf, 0))) AS f05,
                  f.d IS NOT NULL AND coalesce(s.n, 0) = 0 AS source_missing,
                  (s.abv, s.asv, s.abl, s.asl, coalesce(s.abf, 0), coalesce(s.asf, 0))
                    IS DISTINCT FROM (i.bv, i.sv, i.bl, i.sl, coalesce(i.bf, 0), coalesce(i.sf, 0)) AS idx
           FROM s FULL JOIN f ON f.d = s.d FULL JOIN i ON i.d = coalesce(s.d, f.d))
SELECT d, f05, source_missing, idx FROM j WHERE f05 OR idx ORDER BY 1"""
# EXEC-INDEX-INCREMENTAL (2): the full plan reads the three tables whole; the bounded plan only the candidate dates
PER_DATE_FULL = PER_DATE = PER_DATE_TEMPLATE.format(dates='true', f_dates='true')
PER_DATE_BOUNDED = PER_DATE_TEMPLATE.format(dates='"Date" = ANY(%(dates)s)', f_dates='trade_date = ANY(%(dates)s)')
PLAN_FULL_EVERY = timedelta(days=7)
# The last round whose refresh succeeded (its start is the watermark), the last full plan, the dates written since the
# watermark (every write statement on IDX_Broker_Summary stamps broker_summary_date_quality.checked_at per date,
# trigger broker_summary_remark_new; TRUNCATE does not, the weekly full plan covers it) and any universe change since.
PLAN_STATE = """
WITH w AS (SELECT max(started_at) AS mark FROM public."Monitoring_Stockbit_Update"
            WHERE mode = 'APPLY' AND status = 'SUCCESS' AND features IS NOT NULL),
     f AS (SELECT max(started_at) AS mark FROM public."Monitoring_Stockbit_Update"
            WHERE mode = 'APPLY' AND status = 'SUCCESS' AND features ->> 'plan_used' = 'FULL')
SELECT w.mark, f.mark,
       (SELECT coalesce(array_agg(trade_date ORDER BY trade_date), '{}') FROM public.broker_summary_date_quality q
         WHERE q.checked_at > w.mark),
       EXISTS (SELECT 1 FROM public."IDX_Stock_Universe_History" h
                WHERE h.recorded_from > w.mark OR h.recorded_to > w.mark)
FROM w, f"""

ROW_DIFF = f"""SELECT (SELECT count(*) FROM {SRC} WHERE "Date" = %(d)s AND "Symbol" IN {UNIVERSE}),
  (SELECT count(*) FROM {F05} WHERE trade_date = %(d)s AND ticker IN {UNIVERSE}),
  (SELECT count(*) FROM {SRC} b LEFT JOIN {F05} f
     ON f.ticker=b."Symbol" AND f.trade_date=b."Date" AND f.broker=b."Broker" AND f.investor_type=b."Investor Type"
    AND f.market_board=b."Market Board"
   WHERE b."Date" = %(d)s AND b."Symbol" IN {UNIVERSE} AND (f.ticker IS NULL OR f.buy_value<>b."Buy Value" OR f.sell_value<>b."Sell Value"
     OR f.buy_lots<>b."Buy Lots" OR f.sell_lots<>b."Sell Lots" OR f.buy_freq IS DISTINCT FROM b.buy_freq
     OR f.sell_freq IS DISTINCT FROM b.sell_freq))"""

RECON06 = f"""WITH s AS (
    SELECT trade_date, ticker, market_board,
           coalesce(sum(buy_value) FILTER (WHERE investor_type='Foreign'),0) fb,
           coalesce(sum(sell_value) FILTER (WHERE investor_type='Foreign'),0) fs,
           coalesce(sum(buy_value) FILTER (WHERE investor_type='Domestic'),0) db,
           coalesce(sum(sell_value) FILTER (WHERE investor_type='Domestic'),0) ds
    FROM {F05} WHERE trade_date >= %(a)s GROUP BY 1,2,3)
SELECT count(*), count(*) FILTER (WHERE f.ticker IS NULL OR f.foreign_buy_1d<>s.fb OR f.foreign_sell_1d<>s.fs
           OR f.domestic_buy_1d<>s.db OR f.domestic_sell_1d<>s.ds OR f.foreign_net_1d<>s.fb-s.fs
           OR f.domestic_net_1d<>s.db-s.ds),
       (SELECT count(*) FROM {F06} WHERE trade_date >= %(a)s)
FROM s LEFT JOIN {F06} f USING (trade_date, ticker, market_board)"""


# EXEC-RADAR R2: what the Radar must recalculate is derived from the data, as the broker plan is. A Regular Feature 06 row
# of a universe ticker newer than its Radar measure row (or without one), from the first Radar date on, marks the ticker
# from that date; a date whose measures are newer than its gate row (a day step that did not finish) marks the dates.
F07 = 'public."Feature_07_Radar_Measure"'
F07_GATE = 'public."Feature_07_Radar_Gate"'
F07_RESULT = 'public."Feature_07_Radar_Result"'
RADAR_TICKERS = f"""SELECT f.ticker, min(f.trade_date) FROM {F06} f
LEFT JOIN {F07} m ON m.ticker = f.ticker AND m.trade_date = f.trade_date
WHERE f.market_board = 'Regular' AND f.ticker IN {UNIVERSE} AND f.trade_date >= %(first)s
  AND (m.ticker IS NULL OR f.calculated_at > m.calculated_at)
GROUP BY 1 ORDER BY 1"""
RADAR_STALE_DAY = f"""SELECT min(m.trade_date) FROM (SELECT trade_date, max(calculated_at) AS at FROM {F07} GROUP BY 1) m
LEFT JOIN {F07_GATE} g USING (trade_date) WHERE g.trade_date IS NULL OR m.at > g.calculated_at"""
# from the first recalculated date: every Regular session of a universe ticker has a measure row with the same daily
# foreign net and buying as Feature 06 (sums, exact numerics), every measure date has its gate row (universe 0 only
# before any stock has 5 sessions) and no measure row was left without its date's cross-section (QA 2026-11-14)
RECON07 = f"""WITH f AS (SELECT count(*) AS n, sum(foreign_buy_1d - foreign_sell_1d) AS net, sum(foreign_buy_1d + domestic_buy_1d) AS buy
                FROM {F06} WHERE market_board = 'Regular' AND trade_date >= %(a)s AND ticker IN {UNIVERSE}),
     m AS (SELECT count(*) AS n, sum(foreign_net_1d) AS net, sum(total_buy_1d) AS buy,
                  count(*) FILTER (WHERE g2_eligible IS NULL) AS no_xs, count(DISTINCT trade_date) AS dates
           FROM {F07} WHERE trade_date >= %(a)s AND ticker IN {UNIVERSE})
SELECT f.n, m.n, (SELECT count(*) FROM {F07_GATE} WHERE trade_date >= %(a)s), m.dates,
       f.net IS NOT DISTINCT FROM m.net AND f.buy IS NOT DISTINCT FROM m.buy, m.no_xs
FROM f, m"""
# a first fill (verification/radar/backfill_job.py) holds this lock while it writes; a round leaves the Radar to it
RADAR_BACKFILL_LOCK = 'feature_07_radar_backfill'
# the outlier note of a result reads the corporate actions in its stock's 5 sessions: when the round's event load
# changed any, the result dates of the boards the page offers are computed again (publisher radar.BOARD_DATES)
RADAR_EVENT_DATES = 20


class RefreshFailed(RuntimeError):
    pass


def connect():
    return psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=30, application_name='stockbit-updater-refresh')


def run_in(sql_text: str, args=(), timeout='30min'):
    with connect() as c:
        c.execute(f"SET LOCAL statement_timeout = '{timeout}'")
        c.execute('SET LOCAL max_parallel_workers_per_gather = 0')
        value = c.execute(sql_text, args).fetchone()
        c.commit()
        return value


def analyze(table: str) -> None:
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as c:
        c.execute(f'ANALYZE {table}')


INDEX_DUE: list[date] = []  # dates whose all-symbol totals differ from the IHSG INDEX table (set by changed_dates)


def plan(rows) -> tuple[list[date], list[date]]:
    """PER_DATE rows -> (dates Feature 05 must refresh, dates the INDEX rebuild must cover)."""
    orphan = [d for d, _, source_missing, _ in rows if source_missing]
    if orphan:
        # a Feature 05 date without any universe source row: never deleted here, the user decides (UPDATE_TABLE.md)
        raise RefreshFailed(f'Feature 05 holds dates absent from IDX_Broker_Summary: {orphan[:5]}')
    return [d for d, f05, _, _ in rows if f05], [d for d, _, _, idx in rows if idx]


PLAN_INFO: dict = {}  # how the last plan was made (kept in Monitoring_Stockbit_Update.features)


def bounded_candidates(c, now=None):
    """(candidate dates, None) for the bounded plan, or (None, why the full plan is needed)."""
    mark, full_mark, dates, universe_changed = c.execute(PLAN_STATE).fetchone()
    if mark is None:
        return None, 'no earlier successful refresh'
    if universe_changed:
        return None, 'IDX_Stock_Universe changed since the last refresh'
    now = now or c.execute('SELECT now()').fetchone()[0]
    if full_mark is None or now - full_mark > PLAN_FULL_EVERY:
        return None, 'no full plan in the last 7 days'
    return list(dates), None


def changed_dates(emit) -> list[date]:
    """PLAN_MODE: SHADOW (default: both plans, the full one is used, a difference is reported), BOUNDED (the bounded
    plan when it may be used), FULL (the full plan only)."""
    mode = os.environ.get('PLAN_MODE', 'SHADOW').upper()
    t0 = time.monotonic()
    with connect() as c:
        c.execute("SET LOCAL statement_timeout = '30min'")
        candidates, why_full, bounded_rows, bounded_s = None, 'PLAN_MODE=FULL', None, None
        if mode != 'FULL':
            try:  # the bounded plan never stops a round: any error means the full plan (savepoint keeps the transaction)
                with c.transaction():
                    candidates, why_full = bounded_candidates(c)
                    if candidates is not None:
                        b0 = time.monotonic()
                        bounded_rows = c.execute(PER_DATE_BOUNDED, {'dates': candidates}).fetchall() if candidates else []
                        bounded_s = round(time.monotonic() - b0, 1)
            except psycopg.Error as exc:
                candidates, bounded_rows, why_full = None, None, f'bounded plan unavailable: {type(exc).__name__}'
        if bounded_rows is None:
            candidates = None
        full_rows = full_s = None
        if candidates is None or mode != 'BOUNDED':
            f0 = time.monotonic()
            full_rows = c.execute(PER_DATE_FULL).fetchall()
            full_s = round(time.monotonic() - f0, 1)
    used = full_rows if full_rows is not None else bounded_rows
    dates, index_dates = plan(used)
    INDEX_DUE[:] = index_dates
    info = {'plan_mode': mode, 'plan_used': 'FULL' if full_rows is not None else 'BOUNDED', 'plan_why_full': why_full,
            'plan_candidates': [str(d) for d in candidates] if candidates is not None else None,
            'plan_full_seconds': full_s, 'plan_bounded_seconds': bounded_s}
    if full_rows is not None and bounded_rows is not None:
        info['plan_shadow_equal'] = plan(bounded_rows) == (dates, index_dates)
        if not info['plan_shadow_equal']:
            b_dates, b_index = plan(bounded_rows)
            info['plan_shadow_bounded'] = {'changed': [str(d) for d in b_dates], 'index': [str(d) for d in b_index]}
    PLAN_INFO.clear(); PLAN_INFO.update(info)
    emit('refresh_plan', changed_dates=[str(d) for d in dates], index_dates=[str(d) for d in index_dates],
         seconds=round(time.monotonic() - t0, 1), **info)
    return dates


def refresh_broker_features(emit) -> dict:
    dates = changed_dates(emit)
    if not dates:
        return {'changed_dates': [], 'f05_rows': 0, 'f02_tickers': 0, 'f03_dates': 0, 'f06_tickers': 0, **PLAN_INFO}
    started, first = time.monotonic(), dates[0]
    f05_rows = 0
    for d in dates:  # F05 one date at a time, checked row by row against the source before commit
        with connect() as c:
            c.execute("SET LOCAL statement_timeout = '30min'")
            c.execute('SET LOCAL max_parallel_workers_per_gather = 0')
            rows = c.execute('SELECT public.refresh_feature_05(%s, %s)', (d, d + timedelta(days=1))).fetchone()[0]
            src, f05, differing = c.execute(ROW_DIFF, {'d': d}).fetchone()
            if differing or src != f05 or rows != src:
                c.rollback()
                raise RefreshFailed(f'Feature 05 {d}: source {src}, written {rows}, stored {f05}, differing {differing}')
            c.commit()
        f05_rows += rows
    analyze(F05)
    emit('f05_done', dates=len(dates), rows=f05_rows)
    with connect() as c:  # per ticker, the first changed date it appears on (source or Feature 05)
        tickers = c.execute(f"""SELECT ticker, min(trade_date) FROM {F05} WHERE trade_date = ANY(%s) GROUP BY 1
                                ORDER BY 1""", (dates,)).fetchall()
    for i, (t, d) in enumerate(tickers, 1):
        run_in('SELECT public.refresh_feature_02(%s, %s)', (t, d))
        if i % 100 == 0 or i == len(tickers):
            emit('f02_progress', done=i, of=len(tickers), seconds=round(time.monotonic() - started, 1))
    analyze(F02)
    src_n, f02_n = run_in(f"""SELECT (SELECT count(*) FROM {F05} WHERE trade_date >= %(a)s),
                                     (SELECT count(*) FROM {F02} WHERE date >= %(a)s)""", {'a': first})
    if src_n != f02_n:
        raise RefreshFailed(f'Feature 02 rows {f02_n} != Feature 05 rows {src_n} from {first}')
    with connect() as c:
        f03_dates = [r[0] for r in c.execute(f'SELECT DISTINCT date FROM {F02} WHERE date >= %s ORDER BY 1', (first,))]
    for d in f03_dates:
        run_in('SELECT public.refresh_feature_03_stock_broker_daily(%s, NULL)', (d,))
    analyze(F03)
    groups, f03_n = run_in(f"""SELECT (SELECT count(*) FROM (SELECT DISTINCT date, ticker, market_board FROM {F02}
                                       WHERE date >= %(a)s) g), (SELECT count(*) FROM {F03} WHERE date >= %(a)s)""",
                           {'a': first})
    if groups != f03_n:
        raise RefreshFailed(f'Feature 03 rows {f03_n} != Feature 02 groups {groups} from {first}')
    emit('f02_f03_done', tickers=len(tickers), f03_dates=len(f03_dates), f02_rows=f02_n, f03_rows=f03_n)
    for i, (t, d) in enumerate(tickers, 1):
        run_in('SELECT public.refresh_feature_06(%s, %s)', (t, d))
    analyze(F06)
    groups6, differing6, f06_n = run_in(RECON06, {'a': first}, '60min')
    if differing6 or groups6 != f06_n:
        raise RefreshFailed(f'Feature 06 reconcile: groups {groups6}, rows {f06_n}, differing {differing6}')
    emit('f06_done', tickers=len(tickers), rows=f06_n)
    return {'changed_dates': [str(d) for d in dates], 'f05_rows': f05_rows, 'f02_tickers': len(tickers),
            'f03_dates': len(f03_dates), 'f06_tickers': len(tickers), 'seconds': round(time.monotonic() - started, 1),
            **PLAN_INFO}


def refresh_radar(emit, events_changed: bool = False) -> dict:
    """EXEC-RADAR R2: after Feature 03 and 06 (and the round's events, which the outlier note reads), recalculate the
    Radar measures of every ticker whose Feature 06 rows are newer, then every date from the first one, in date order
    (a run of days reads the date before); when the round's event load changed a corporate action, also the
    RADAR_EVENT_DATES newest dates. Skipped until the backfill has written the first rows, and while a backfill runs."""
    started = time.monotonic()
    with connect() as c:
        if c.execute('SELECT to_regclass(%s)', (F07,)).fetchone()[0] is None:
            emit('radar_skipped', reason='Feature 07 is not created yet')
            return {'skipped': 'Feature 07 is not created yet'}
        if not c.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (RADAR_BACKFILL_LOCK,)).fetchone()[0]:
            emit('radar_skipped', reason='the Radar backfill is running')
            return {'skipped': 'backfill running'}
        c.execute('SELECT pg_advisory_unlock(hashtext(%s))', (RADAR_BACKFILL_LOCK,))
        first = c.execute(f'SELECT min(trade_date) FROM {F07}').fetchone()[0]
        if first is None:
            emit('radar_skipped', reason='Feature 07 has no rows; the Radar backfill writes the first ones')
            return {'skipped': 'not backfilled'}
        tickers = c.execute(RADAR_TICKERS, {'first': first}).fetchall()
        event_from = None
        if events_changed:
            event_from = c.execute(f"""SELECT min(d) FROM (SELECT DISTINCT trade_date AS d FROM {F07_GATE}
                                       ORDER BY 1 DESC LIMIT %s) x""", (RADAR_EVENT_DATES,)).fetchone()[0]
    for i, (t, d) in enumerate(tickers, 1):
        run_in('SELECT public.refresh_feature_07(%s, %s)', (t, d))
        if i % 200 == 0 or i == len(tickers):
            emit('radar_progress', done=i, of=len(tickers), seconds=round(time.monotonic() - started, 1))
    if tickers:
        analyze(F07)
    with connect() as c:
        stale = c.execute(RADAR_STALE_DAY).fetchone()[0]
    starts = [d for d in [min((d for _, d in tickers), default=None), stale, event_from] if d is not None]
    if not starts:
        emit('radar_done', tickers=0, dates=0, seconds=round(time.monotonic() - started, 1))
        return {'tickers': 0, 'dates': [], 'seconds': round(time.monotonic() - started, 1)}
    since = min(starts)
    with connect() as c:
        days = [r[0] for r in c.execute(f'SELECT DISTINCT trade_date FROM {F07} WHERE trade_date >= %s ORDER BY 1',
                                        (since,))]
    for d in days:
        run_in('SELECT public.refresh_feature_07_day(%s)', (d,))
    analyze(F07_RESULT)
    regular, measured, gates, dated, sums_equal, no_xs = run_in(RECON07, {'a': since}, '60min')
    if regular != measured or gates != dated or not sums_equal or no_xs:
        raise RefreshFailed(f'Feature 07 reconcile from {since}: Regular rows {regular}, measure rows {measured}, '
                            f'gate rows {gates} for {dated} dates, daily sums equal to Feature 06 {sums_equal}, '
                            f'rows without their cross-section {no_xs}')
    emit('radar_done', tickers=len(tickers), dates=len(days), since=str(since), rows=measured,
         seconds=round(time.monotonic() - started, 1))
    return {'tickers': len(tickers), 'since': str(since), 'dates': [str(d) for d in days], 'rows': measured,
            'seconds': round(time.monotonic() - started, 1)}


def index_needed(broker_changed: bool) -> bool:
    if broker_changed or INDEX_DUE:  # INDEX_DUE: all-symbol totals differ, e.g. an upload of codes outside the universe
        return True
    with connect() as c:  # a newer IHSG price than the INDEX Feature 01 table also needs the INDEX rebuild
        return c.execute("""SELECT (SELECT max(date) FROM public."Price_Stock_Indonesia_IDX" WHERE ticker='IHSG')
            > (SELECT max(date) FROM public."Feature_01_Stock_Daily_INDEX")""").fetchone()[0] or False


def index_from_date(c) -> date:
    """EXEC-INDEX-INCREMENTAL: the first date the IHSG broker INDEX rows must be recomputed from: the earliest date whose
    all-symbol totals differ (INDEX_DUE), else (a newer IHSG price only) the day after the newest stored INDEX session."""
    if INDEX_DUE:
        return min(INDEX_DUE)
    newest = c.execute("""SELECT max(date) FROM public."Feature_03_Stock_Broker_Daily_INDEX" WHERE ticker = 'IHSG'""").fetchone()
    newest = newest['max'] if isinstance(newest, dict) else newest[0]
    return (newest + timedelta(days=1)) if newest else None


def refresh_index(emit, ticker: str = 'IHSG', sample: date = date(2026, 8, 31)) -> dict:
    """scripts/backfill_index_features.py prepare + apply_chunks (UPDATE_TABLE.md step 5). EXEC-INDEX-INCREMENTAL: the
    broker INDEX features from the first changed date (warmup window before it), prices in full; INDEX_FULL=1 forces
    the full rebuild of the 2026-10-25 run."""
    sys.path.insert(0, '/app/scripts')
    import backfill_index_features as b
    from psycopg.rows import dict_row
    t0 = time.monotonic()
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, autocommit=True,
                         application_name='stockbit-updater-index') as db:
        db.execute("SET statement_timeout='20min'")
        db.execute("SET lock_timeout='10s'")
        db.execute("SET work_mem='64MB'")
        db.execute('SET max_parallel_workers_per_gather=0')
        if not db.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok', ('index-bulk:' + ticker,)).fetchone()['ok']:
            raise RefreshFailed('Another INDEX writer is active')
        from_date = None if os.environ.get('INDEX_FULL') == '1' else index_from_date(db)
        with db.transaction():
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            info = b.prepare(db, ticker, sample, False, from_date=from_date)
        b.apply_chunks(db, ticker, uuid.uuid4(), from_date=info['from_date'])
        newest = {f: str(db.execute(f'SELECT max({"date" if f in (1, 2, 3) else "trade_date"}) AS d '
                                    f'FROM public."{t}_INDEX"').fetchone()['d']) for f, t in b.BASE.items()}
        for t in b.BASE.values():
            db.execute(f'ANALYZE public."{t}_INDEX"')
    emit('index_done', newest=newest, from_date=info['from_date'], window_first=info['window_first'],
         seconds=round(time.monotonic() - t0, 1))
    return {'newest': newest, 'from_date': str(info['from_date']) if info['from_date'] else None,
            'window_first': str(info['window_first']) if info['window_first'] else None,
            'seconds': round(time.monotonic() - t0, 1)}
