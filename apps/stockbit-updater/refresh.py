"""Feature refresh of the stockbit-updater service: IDX_Broker_Summary -> F05 -> F02 -> F03, F05 -> F06, then the
INDEX tables (UPDATE_TABLE.md part A, section 4; the routines are the database's own, unchanged).

What to refresh is derived from the data, not from the dates the loader wrote: every date whose per-date totals in
IDX_Broker_Summary differ from Feature 05 (rows, buy, sell, lots, known frequency rows and frequency). A manual upload
(for example the non-four-letter symbols the user loads separately, decision K1) or a correction of an old date is
picked up the same way. Each step is checked as in the 2026-10-25 runs and stops the refresh when a check fails.
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

PER_DATE = f"""
WITH s AS (SELECT "Date" AS d, count(*) n, sum("Buy Value") bv, sum("Sell Value") sv, sum("Buy Lots") bl,
                  sum("Sell Lots") sl, count(buy_freq) fr, sum(buy_freq) bf, sum(sell_freq) sf
           FROM {SRC} GROUP BY 1),
     f AS (SELECT trade_date AS d, count(*) n, sum(buy_value) bv, sum(sell_value) sv, sum(buy_lots) bl,
                  sum(sell_lots) sl, count(buy_freq) fr, sum(buy_freq) bf, sum(sell_freq) sf
           FROM {F05} GROUP BY 1)
SELECT coalesce(s.d, f.d), s.d IS NULL
FROM s FULL JOIN f ON f.d = s.d
WHERE s.d IS NULL OR f.d IS NULL OR (s.n, s.bv, s.sv, s.bl, s.sl, s.fr, coalesce(s.bf, 0), coalesce(s.sf, 0))
      IS DISTINCT FROM (f.n, f.bv, f.sv, f.bl, f.sl, f.fr, coalesce(f.bf, 0), coalesce(f.sf, 0))
ORDER BY 1"""

ROW_DIFF = f"""SELECT (SELECT count(*) FROM {SRC} WHERE "Date" = %(d)s), (SELECT count(*) FROM {F05} WHERE trade_date = %(d)s),
  (SELECT count(*) FROM {SRC} b LEFT JOIN {F05} f
     ON f.ticker=b."Symbol" AND f.trade_date=b."Date" AND f.broker=b."Broker" AND f.investor_type=b."Investor Type"
    AND f.market_board=b."Market Board"
   WHERE b."Date" = %(d)s AND (f.ticker IS NULL OR f.buy_value<>b."Buy Value" OR f.sell_value<>b."Sell Value"
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


def changed_dates(emit) -> list[date]:
    t0 = time.monotonic()
    with connect() as c:
        c.execute("SET LOCAL statement_timeout = '30min'")
        rows = c.execute(PER_DATE).fetchall()
    orphan = [d for d, source_missing in rows if source_missing]
    if orphan:
        # a Feature 05 date without any source row: never deleted here, the user decides (UPDATE_TABLE.md)
        raise RefreshFailed(f'Feature 05 holds dates absent from IDX_Broker_Summary: {orphan[:5]}')
    dates = [d for d, _ in rows]
    emit('refresh_plan', changed_dates=[str(d) for d in dates], seconds=round(time.monotonic() - t0, 1))
    return dates


def refresh_broker_features(emit) -> dict:
    dates = changed_dates(emit)
    if not dates:
        return {'changed_dates': [], 'f05_rows': 0, 'f02_tickers': 0, 'f03_dates': 0, 'f06_tickers': 0}
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
            'f03_dates': len(f03_dates), 'f06_tickers': len(tickers), 'seconds': round(time.monotonic() - started, 1)}


def index_needed(broker_changed: bool) -> bool:
    if broker_changed:
        return True
    with connect() as c:  # a newer IHSG price than the INDEX Feature 01 table also needs the INDEX rebuild
        return c.execute("""SELECT (SELECT max(date) FROM public."Price_Stock_Indonesia_IDX" WHERE ticker='IHSG')
            > (SELECT max(date) FROM public."Feature_01_Stock_Daily_INDEX")""").fetchone()[0] or False


def refresh_index(emit, ticker: str = 'IHSG', sample: date = date(2026, 8, 31)) -> dict:
    """scripts/backfill_index_features.py prepare + apply_chunks (UPDATE_TABLE.md step 5), as the 2026-10-25 run."""
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
        with db.transaction():
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            b.prepare(db, ticker, sample, False)
        b.apply_chunks(db, ticker, uuid.uuid4())
        newest = {f: str(db.execute(f'SELECT max({"date" if f in (1, 2, 3) else "trade_date"}) AS d '
                                    f'FROM public."{t}_INDEX"').fetchone()['d']) for f, t in b.BASE.items()}
        for t in b.BASE.values():
            db.execute(f'ANALYZE public."{t}_INDEX"')
    emit('index_done', newest=newest, seconds=round(time.monotonic() - t0, 1))
    return {'newest': newest, 'seconds': round(time.monotonic() - t0, 1)}
