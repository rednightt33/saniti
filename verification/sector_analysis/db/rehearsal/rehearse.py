"""EXEC-SECTOR-ANALYSIS S1: local rehearsal of migration 20261126_001 (Feature_08_Group_Daily) on a scratch PostgreSQL 16.

Nothing here touches the dev database. dev_ddl.sql holds the definitions read from dev (read-only, pgweb: columns,
checks, keys, indexes and the catalog triggers of the seven tables the migration reads or writes); the size function is
read from its own migration (20261115_020). The data are synthetic and chosen to prove each rule of the refresh:

  AAAA, BBBB  Financials / Banks, trade every day (AAAA above its EMAs, BBBB below)
  CCCC        Financials / Insurance, suspended on three market dates (no price row), no EMA200
  DDDD        Energy / Coal, listed on the 16th date (no previous close on its first day, no EMA50)
  EEEE        Energy / Coal, traded with volume 0 every day (no weight), close equal to its EMA50 (not above)
  FFFF        Undefined / Undefined (MARKET only); no Feature 04 row on one date
  GGGG        Energy / Oil & Gas, volume 0: its industry has members and no weight (return and level NULL)
  IIII        Consumer Non-Cyclicals / Tobacco, never priced (an industry with no member)
  HHHH        a fund with prices and volume (not a member of any group; it has a weight)

The expected values are computed here in Python from the inserted rows, by a separate implementation of
CONTRACT.md section 2, and compared with every column of every row the function writes. Then the scenarios: idempotent
re-run, the Overview's BREADTH_SQL on the MARKET rows, the gap refusal, a date off the calendar, a reclassified industry,
a second application of the migration, and the grants.

Run: python rehearse.py <libpq conninfo of a superuser on a scratch server> (a database f08_rehearsal is dropped and
created). Prints CHECK lines and a final VERDICT.
"""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import psycopg

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
MIGRATION = REPO / 'database/migrations/20261126_001_feature_08_group_daily.sql'
SIZE_MIGRATION = REPO / 'database/migrations/20261115_020_overview_stock_size.sql'
sys.path.insert(0, str(REPO / 'apps/terminal-publisher'))
import overview  # noqa: E402  the Overview's BREADTH_SQL, compared with the MARKET rows

SECTORS = ['Basic Materials', 'Consumer Cyclicals', 'Consumer Non-Cyclicals', 'Energy', 'Financials', 'Healthcare',
           'Industrials', 'Infrastructures', 'Properties & Real Estate', 'Technology', 'Transportation & Logistic']
STOCKS = {  # ticker: (sector, industry)
    'AAAA': ('Financials', 'Banks'), 'BBBB': ('Financials', 'Banks'), 'CCCC': ('Financials', 'Insurance'),
    'DDDD': ('Energy', 'Coal'), 'EEEE': ('Energy', 'Coal'), 'FFFF': ('Undefined', 'Undefined'),
    'GGGG': ('Energy', 'Oil & Gas'), 'IIII': ('Consumer Non-Cyclicals', 'Tobacco'),
}
FUND = 'HHHH'
N_DATES = 30
FAILURES: list[str] = []


def check(name, ok, detail=''):
    print(f'CHECK {"PASS" if ok else "FAIL"} {name}' + (f' :: {detail}' if detail else ''), flush=True)
    if not ok:
        FAILURES.append(name)


def market_dates():
    out, d = [], dt.date(2026, 1, 5)
    while len(out) < N_DATES:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


DATES = market_dates()
SUSPENDED = set(DATES[10:13])          # CCCC has no price row on these
LISTED_FROM = DATES[15]                # DDDD's first close
FFFF_NO_F04 = DATES[20]


def close_of(t, k):
    """A deterministic close of ticker t on date index k (None: no price row)."""
    d = DATES[k]
    if t == 'CCCC' and d in SUSPENDED:
        return None
    if t == 'DDDD' and d < LISTED_FROM:
        return None
    if t == 'IIII':
        return None
    base = {'AAAA': 1000, 'BBBB': 500, 'CCCC': 200, 'DDDD': 3000, 'EEEE': 50, 'FFFF': 80, 'GGGG': 120, FUND: 1000}[t]
    step = {'AAAA': 10, 'BBBB': -5, 'CCCC': 4, 'DDDD': 25, 'EEEE': 0, 'FFFF': 0, 'GGGG': 1, FUND: 3}[t]
    wiggle = (-1) ** k * {'AAAA': 7, 'BBBB': 3, 'CCCC': 0, 'DDDD': 40, 'EEEE': 0, 'FFFF': 2, 'GGGG': 0, FUND: 0}[t]
    if t == 'FFFF' and k % 3 == 0:     # unchanged against the day before on every third date
        return close_of(t, k - 1) if k else base
    return float(base + step * k + wiggle)


def volume_of(t, k):
    if t in ('EEEE', 'GGGG'):
        return 0.0
    return float({'AAAA': 1000 + 50 * k, 'BBBB': 2000 - 30 * k, 'CCCC': 500, 'DDDD': 100 + 10 * k, 'FFFF': 10,
                  FUND: 400}[t])


def ihsg_close(k):
    return 7000.0 + 13 * k - (-1) ** k * 20


def f04_row(t, k):
    """(close, ema_50, ema_200) of Feature 04, or None for no row."""
    c = close_of(t, k)
    if c is None or (t == 'FFFF' and DATES[k] == FFFF_NO_F04):
        return None
    ema50 = {'AAAA': c * 0.95, 'BBBB': c * 1.05, 'CCCC': c * 0.9, 'DDDD': None, 'EEEE': c, 'FFFF': c * 1.01,
             'GGGG': c * 0.99}[t]
    ema200 = {'AAAA': c * 0.9, 'BBBB': c * 1.1, 'CCCC': None, 'DDDD': None, 'EEEE': c * 0.98, 'FFFF': c * 0.5,
              'GGGG': c * 1.2}[t]
    return c, ema50, ema200


# ---- the expected values (an implementation separate from the SQL) --------------------------------------------------
def weights(k):
    """adv20_value on DATES[k]: sum(close x volume) over the 20 market dates up to it / 20; every ticker with a volume
    and a positive sum (funds included); none before the 20th market date."""
    if k < 19:
        return {}
    out = {}
    for t in [*STOCKS, FUND]:
        s = sum((close_of(t, j) or 0) * volume_of(t, j) for j in range(k - 19, k + 1) if close_of(t, j) is not None)
        if s > 0:
            out[t] = s / 20
    return out


def prev_close(t, k):
    for j in range(k - 1, -1, -1):
        c = close_of(t, j)
        if c is not None:
            return c
    return None


def groups():
    g = [('MARKET', 'IHSG', None, list(STOCKS))]
    g += [('SECTOR', s, s, [t for t, (sec, _) in STOCKS.items() if sec == s]) for s in SECTORS]
    inds = sorted({ind for _, ind in STOCKS.values() if ind != 'Undefined'})
    g += [('INDUSTRY', i, next(sec for sec, ind in STOCKS.values() if ind == i), [t for t, (_, ind) in STOCKS.items() if ind == i])
          for i in inds]
    return g


def expected():
    out, level = {}, {}
    for k, d in enumerate(DATES):
        w0, w1 = weights(k), weights(k - 1) if k else {}
        for kind, name, sector, members in groups():
            closes = {t: close_of(t, k) for t in members if close_of(t, k) is not None}
            f4 = {t: f04_row(t, k) for t in members if f04_row(t, k) is not None}
            pcs = {t: prev_close(t, k) for t in closes}
            both = [t for t in closes if pcs[t] is not None and pcs[t] > 0 and w1.get(t, 0) > 0]
            ret = (100 * sum(w1[t] * (closes[t] / pcs[t] - 1) for t in both) / sum(w1[t] for t in both)) if both else None
            key = (kind, name)
            if key not in level:
                lv = 100.0
            elif ret is None:
                lv = None
            else:
                lv = level[key] * (1 + ret / 100)
            if lv is not None:
                level[key] = lv
            ws = [w0[t] for t in closes if t in w0]
            out[(d, kind, name)] = {
                'sector': sector, 'members': len(closes),
                'n_ema50': sum(1 for r in f4.values() if r[1] is not None),
                'above_ema50': sum(1 for r in f4.values() if r[1] is not None and r[0] > r[1]),
                'n_ema200': sum(1 for r in f4.values() if r[2] is not None),
                'above_ema200': sum(1 for r in f4.values() if r[2] is not None and r[0] > r[2]),
                'adv_1d': sum(1 for t in closes if pcs[t] is not None and closes[t] > pcs[t]),
                'unch_1d': sum(1 for t in closes if pcs[t] is not None and closes[t] == pcs[t]),
                'dec_1d': sum(1 for t in closes if pcs[t] is not None and closes[t] < pcs[t]),
                'weight_basis': 'adv20_value' if ws else None, 'weight_sum': sum(ws) if ws else None,
                'ret_1d_w': ret, 'index_level': lv,
            }
    return out


# ---- setup --------------------------------------------------------------------------------------------------------
def setup(admin):
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute('DROP DATABASE IF EXISTS f08_rehearsal')
        c.execute('CREATE DATABASE f08_rehearsal')
        for role in ('terminal_market_reader', 'pgweb_reader'):
            if not c.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (role,)).fetchone():
                c.execute(f'CREATE ROLE {role} NOLOGIN')
    db = psycopg.conninfo.make_conninfo(admin, dbname='f08_rehearsal')
    with psycopg.connect(db, autocommit=True) as c:
        c.execute((HERE / 'dev_ddl.sql').read_text())
        body = SIZE_MIGRATION.read_text()
        fn = body[body.index('CREATE FUNCTION public.overview_stock_size'):body.index('COMMENT ON FUNCTION public.overview_stock_size')]
        c.execute(fn)
        c.execute('GRANT EXECUTE ON FUNCTION public.overview_stock_size(date) TO terminal_market_reader')
        c.execute('GRANT SELECT ON public."Price_Stock_Indonesia_IDX", public."Feature_Index_Entity", public."IDX_Stock_Universe", '
                  'public."Feature_04_Technical_Indicator" TO terminal_market_reader')
        c.execute("""INSERT INTO public."Feature_Index_Entity" (ticker, entity_kind, name, member_source, sector, has_price, rows_from)
                     VALUES ('IHSG', 'MARKET', 'IDX Composite Index', 'ALL_SOURCE_SYMBOLS', NULL, true, NULL)""")
        for i, s in enumerate(SECTORS):
            c.execute("""INSERT INTO public."Feature_Index_Entity" (ticker, entity_kind, name, member_source, sector, has_price, rows_from)
                         VALUES (%s, 'SECTOR', %s, 'UNIVERSE_SECTOR', %s, true, DATE '2024-01-02')""", (f'IDXS{i:02d}', f'Sector {s}', s))
        uni = 'INSERT INTO public."IDX_Stock_Universe" VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)'
        for t, (sec, ind) in STOCKS.items():
            c.execute(uni, ('Asia', 'ID', f'Company {t}', t, 'IDX', f'IDX:{t}', 'u', 'stock', 'common', 'true', 'ID', 'IDR', 'IDR', 'X', sec, ind))
        c.execute(uni, ('Asia', 'ID', 'Fund', FUND, 'IDX', f'IDX:{FUND}', 'u', 'fund', 'fund', 'false', 'ID', 'IDR', 'IDR', 'X', 'Financials', 'Banks'))
        c.execute(uni, ('Asia', 'ID', 'Composite', 'IHSG', 'IDX', 'IDX:COMPOSITE', 'u', 'index', 'index', 'false', 'ID', 'IDR', 'IDR', 'X', 'Undefined', 'Undefined'))
        price = ('INSERT INTO public."Price_Stock_Indonesia_IDX" (company_name, ticker, tradingview_symbol, date, open, high, low, close, '
                 "volume, source, query_date, timeframe, market_code, market_close_at, is_final, finalized_at) VALUES "
                 "(%s, %s, %s, %s, %s, %s, %s, %s, %s, 'synthetic', %s, 'Daily', 'IDX', %s, true, %s)")
        f04 = ('INSERT INTO public."Feature_04_Technical_Indicator" (ticker, trade_date, timeframe, asset_type, close, ema_50, ema_200, '
               "calculation_version, calculated_at) VALUES (%s, %s, 'Daily', 'equity', %s, %s, %s, 'v4', now())")
        for k, d in enumerate(DATES):
            at = dt.datetime.combine(d, dt.time(9, 0), dt.timezone.utc)
            c.execute(price, ('Composite', 'IHSG', 'IDX:COMPOSITE', d, ihsg_close(k), ihsg_close(k), ihsg_close(k), ihsg_close(k), None, d, at, at))
            for t in [*STOCKS, FUND]:
                cl = close_of(t, k)
                if cl is None:
                    continue
                c.execute(price, (f'Company {t}', t, f'IDX:{t}', d, cl, cl, cl, cl, volume_of(t, k), d, at, at))
                r = f04_row(t, k) if t != FUND else None
                if r:
                    c.execute(f04, (t, d, *r))
        # a non-final row on a later weekday: not a market date for the refresh
        late = DATES[-1] + dt.timedelta(days=3)
        at = dt.datetime.combine(late, dt.time(9, 0), dt.timezone.utc)
        c.execute(price.replace('true, %s)', 'false, %s)'), ('Composite', 'IHSG', 'IDX:COMPOSITE', late, 1, 1, 1, 1, None, late, at, at))
    return db


COLS = ('sector', 'members', 'n_ema50', 'above_ema50', 'n_ema200', 'above_ema200', 'adv_1d', 'unch_1d', 'dec_1d',
        'weight_basis', 'weight_sum', 'ret_1d_w', 'index_level')


def table(c):
    rows = c.execute(f'SELECT date, group_kind, group_name, {", ".join(COLS)} FROM public."Feature_08_Group_Daily" '
                     'ORDER BY 1, 2, 3').fetchall()
    return {(r[0], r[1], r[2]): dict(zip(COLS, r[3:])) for r in rows}


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)
    return a == b


def worker_section(db, before):
    """apps/feature-04-worker/worker.py Feature08Refresher on this database (its SQL as it runs on dev): a finished
    equity run is due, its correction window to the newest date is refreshed in order, then nothing is due; a bond run
    and a run still processing are not due; the backfill lock makes it wait."""
    import types
    from psycopg.rows import dict_row
    for name, attrs in {'engine': {'COLUMNS': (), 'FEATURE_COLUMNS': (), 'TABLE': 'Feature_04_Technical_Indicator',
                                   'VERSION': 'v4', 'dependency_closure': lambda c: tuple(c or ())},
                        'incremental': {'STATE_VERSION': 1, 'calculate_incremental': None,
                                        'validate_incremental_availability': None}}.items():
        sys.modules.setdefault(name, types.SimpleNamespace(**attrs))
    sys.path.insert(0, str(REPO / 'apps/feature-04-worker'))
    import worker
    connector = lambda: psycopg.connect(db, autocommit=True, row_factory=dict_row)
    with psycopg.connect(db, autocommit=True) as c:
        c.execute("""INSERT INTO public."Equity_Market_Schedule" (market_code, exchange, timezone_name, session_close_local,
                     finality_delay_minutes, correction_lookback_sessions, enabled) VALUES ('IDX', 'IDX', 'Asia/Jakarta', '16:00', 30, 5, true)""")
        run = ('INSERT INTO public."Monitoring_Feature04" (execution_id, source_monitor_table, run_type, trigger_source, '
               'update_for_date, status, finished_at) VALUES (%s, %s, %s, %s, %s, %s, %s)')
        c.execute(run, ('f04-daily', 'Monitoring_Price_ALL', 'DAILY', 'SCHEDULED', DATES[-3], 'SUCCESS', 'now'))
        c.execute(run, ('f04-fi', 'Monitoring_Fixed_Income', 'DAILY', 'SCHEDULED', DATES[-1], 'SUCCESS', 'now'))
        c.execute(run, ('f04-open', 'Monitoring_Price_ALL', 'DAILY', 'SCHEDULED', DATES[-1], 'PROCESSING', None))
        due = [r[0] for r in c.execute(worker.FEATURE08_DUE_SQL, (worker.FEATURE08_HORIZON_DAYS,)).fetchall()]
        check('worker: the finished equity run is due (not the bond run, not the open one)', due == [DATES[-3]], str(due))
        wanted = [r[0] for r in c.execute(worker.FEATURE08_DATES_SQL, (DATES[-3], 5)).fetchall()]
        check('worker: its window is the 5 market dates ending at it, through the newest date', wanted == DATES[-7:], str(wanted))
        lock = psycopg.connect(db, autocommit=True)
        lock.execute('SELECT pg_advisory_lock(hashtext(%s))', (worker.FEATURE08_BACKFILL_LOCK,))
        check('worker: waits while the backfill holds its lock', worker.Feature08Refresher(connector=connector).run() == 'waiting')
        lock.close()
        r = worker.Feature08Refresher(connector=connector)
        check('worker: refreshes the due window', r.maybe_run() == 'refreshed')
        check('worker: the values are the same after its refresh', table(c) == before)
        stamped = c.execute("""SELECT count(*) FROM public."Feature_08_Group_Daily" WHERE date >= %s
                               AND calculated_at >= (SELECT finished_at FROM public."Monitoring_Feature04" WHERE execution_id = 'f04-daily')""",
                            (DATES[-7],)).fetchone()[0]
        check('worker: every row of the window was written again', stamped == 7 * len(groups()), str(stamped))
        check('worker: then nothing is due', worker.Feature08Refresher(connector=connector).run() == 'nothing_due')
        # a Telegram retry has no update_for_date: its anchor is the newest final market date at its finish
        c.execute(run, ('f04-retry', 'Monitoring_Price_ALL', 'RETRY_TICKER', 'TELEGRAM', None, 'SUCCESS', 'now'))
        due = [r[0] for r in c.execute(worker.FEATURE08_DUE_SQL, (worker.FEATURE08_HORIZON_DAYS,)).fetchall()]
        check('worker: a finished retry without a date is due on the newest market date', due == [DATES[-1]], str(due))


def publisher_section(db):
    """apps/terminal-publisher/sector.py on this database (every statement it sends, as it runs on dev): available,
    busy, stamp and files with the publisher role's grants; the files' figures against this script's own data. Feature
    01 is a stand-in here (the picker reads only its dates)."""
    sys.path.insert(0, str(REPO / 'apps/terminal-publisher'))
    import sector
    with psycopg.connect(db, autocommit=True) as c:
        c.execute('CREATE TABLE public."Feature_01_Stock_Daily" (ticker text, date date)')
        c.execute('INSERT INTO public."Feature_01_Stock_Daily" SELECT ticker, date FROM public."Price_Stock_Indonesia_IDX" '
                  "WHERE is_final AND ticker <> 'IHSG'")
        c.execute('GRANT SELECT ON public."Feature_01_Stock_Daily" TO terminal_market_reader')
        c.execute('SET ROLE terminal_market_reader')
        check('publisher: available as the publisher role', sector.available(c))
        check('publisher: not busy (filled back to the first series date, no backfill lock)', sector.busy(c) is None, str(sector.busy(c)))
        st = sector.stamp(c)
        check('publisher: the stamp reads every input', all(v is not None for v in st), str(st)[:200])
        files, kept, carry = sector.files(c, {}, [])
        docs = {n: d for n, d, _, _ in files}
        names = sorted(docs)
        indexes = [r[0] for r in c.execute("SELECT ticker FROM public.\"Feature_Index_Entity\" WHERE entity_kind = 'SECTOR'")]
        want = sorted(['sector-meta', 'sector-series', *(f'sector-stocks-{t.lower()}' for t in indexes),
                       *(f'sector-day-{d}' for d in DATES[-sector.DAY_DATES:])])
        check('publisher: every file of the contract', names == want and not kept, f'{len(names)} files')
        meta, series = docs['sector-meta'], docs['sector-series']
        check('publisher: meta names the weight basis and every stock', meta['weight_basis'] == 'adv20_value'
              and meta['stocks']['ticker'] == sorted(STOCKS) and meta['dates'] == [d.isoformat() for d in DATES[-20:]])
        f08 = table(c)
        b = series['breadth']['Financials']
        ok = all(b['a50'][k] == f08[(d, 'SECTOR', 'Financials')]['above_ema50'] and b['members'][k] == f08[(d, 'SECTOR', 'Financials')]['members']
                 for k, d in enumerate(DATES))
        lv = series['industry']['Banks']['level']
        check('publisher: series breadth and industry levels are the Feature 08 rows', ok and all(
            (lv[k] is None) == (f08[(d, 'INDUSTRY', 'Banks')]['index_level'] is None) for k, d in enumerate(DATES)))
        day = docs[f'sector-day-{DATES[-1].isoformat()}']['stocks']
        tick = meta['stocks']['ticker']
        bad = []
        for n, i in enumerate(day['i']):
            t = tick[i]
            k = len(DATES) - 1
            want_r1 = round((close_of(t, k) / close_of(t, k - 1) - 1) * 100, 4) if close_of(t, k - 1) else None
            if day['r1d'][n] != want_r1 or day['close'][n] != round(close_of(t, k), 2):
                bad.append((t, 'r1d', day['r1d'][n], want_r1))
            for e, col in ((50, 1), (200, 2)):
                rows = [f04_row(t, j) for j in range(k, -1, -1) if f04_row(t, j)]
                s = None if rows[0][col] is None else int(rows[0][0] > rows[0][col])
                run_n = 0
                for r in rows:
                    if r[col] is None or int(r[0] > r[col]) != s:
                        break
                    run_n += 1
                want_days = None if s is None else min(run_n, sector.STATUS_CAP)
                if day[f'days{e}'][n] != want_days:
                    bad.append((t, f'days{e}', day[f'days{e}'][n], want_days))
        check('publisher: the newest day file\'s returns and sessions in status equal a count over the rows', not bad, str(bad[:4]))
        c.execute('RESET ROLE')


def main(admin):
    db = setup(admin)
    sql = MIGRATION.read_text()
    with psycopg.connect(db, autocommit=True) as c:
        c.execute(sql)
        check('migration applied (COMMIT, its own checks passed)', True)
        try:
            c.execute(sql)
            check('a second application is refused', False)
        except psycopg.Error as e:
            c.execute('ROLLBACK')
            check('a second application is refused', 'already exists' in str(e), str(e).splitlines()[0])
        for d in DATES:
            c.execute('SELECT public.refresh_feature_08_day(%s)', (d,))
        got, want = table(c), expected()
        diffs = [(k, col, got.get(k, {}).get(col), v[col]) for k, v in want.items() for col in COLS
                 if not same(got.get(k, {}).get(col), v[col])]
        check('every column of every row equals the independent computation', not diffs and set(got) == set(want),
              f'{len(got)} rows, {len(diffs)} differences {diffs[:5]}')
        sys.path.insert(0, str(HERE.parent))
        import validate_feature_08
        vdiffs = [x for d in DATES for x in validate_feature_08.validate(c, d)]
        check('the dev validator (validate_feature_08.py) finds no difference on any date', not vdiffs, str(vdiffs[:3]))
        groups_n = len(groups())
        check('one row per market date and group', len(got) == groups_n * len(DATES), f'{groups_n} groups x {len(DATES)} dates')
        # a few values stated in REHEARSAL.md
        k20 = DATES[20]
        m = got[(k20, 'MARKET', 'IHSG')]
        print('VALUE MARKET', k20, {c_: m[c_] for c_ in COLS})
        print('VALUE Banks', k20, {c_: got[(k20, 'INDUSTRY', 'Banks')][c_] for c_ in COLS})
        print('VALUE Oil & Gas', k20, {c_: got[(k20, 'INDUSTRY', 'Oil & Gas')][c_] for c_ in COLS})
        print('VALUE Tobacco', k20, {c_: got[(k20, 'INDUSTRY', 'Tobacco')][c_] for c_ in COLS})
        print('VALUE Banks first', DATES[0], {c_: got[(DATES[0], 'INDUSTRY', 'Banks')][c_] for c_ in COLS})
        # previous-date weights: the return of DATES[20] with that date's own weights would differ
        w19, w20 = weights(19), weights(20)
        both = ['AAAA', 'BBBB']
        r = lambda w: 100 * sum(w[t] * (close_of(t, 20) / prev_close(t, 20) - 1) for t in both) / sum(w[t] for t in both)
        check('the Banks return uses the previous date\'s weights (and differs from the same-date weights)',
              same(got[(k20, 'INDUSTRY', 'Banks')]['ret_1d_w'], r(w19)) and not same(r(w19), r(w20)),
              f'prev-date {r(w19):.6f}, same-date {r(w20):.6f}')
        # the chain: level(t) = level(t-1) x (1 + ret/100)
        # (the first 19 dates have no weights: overview_stock_size needs 20 market sessions, so the level carries 100)
        b = [got[(d, 'INDUSTRY', 'Banks')] for d in DATES]
        last = lambda i: next(b[j]['index_level'] for j in range(i - 1, -1, -1) if b[j]['index_level'] is not None)
        chain = all(same(b[i]['index_level'], last(i) * (1 + b[i]['ret_1d_w'] / 100))
                    for i in range(1, len(DATES)) if b[i]['ret_1d_w'] is not None)
        carried = all(b[i]['index_level'] is None for i in range(1, 20)) and b[20]['index_level'] is not None
        check('Banks level is chain-linked from 100 and carries over the dates without a return',
              b[0]['index_level'] == 100 and chain and carried)
        nulls = [got[(d, 'INDUSTRY', 'Oil & Gas')]['index_level'] for d in DATES]
        check('an industry without weights: level 100 on the first date, then NULL', nulls[0] == 100 and all(v is None for v in nulls[1:]))
        check('an industry without members: members 0, level NULL after the first date',
              all(got[(d, 'INDUSTRY', 'Tobacco')]['members'] == 0 for d in DATES)
              and all(got[(d, 'INDUSTRY', 'Tobacco')]['index_level'] is None for d in DATES[1:]))
        check('the fund is in no group', all(v['members'] <= len(STOCKS) for v in got.values()))
        # the Overview's BREADTH_SQL on the MARKET rows
        br = {r[0]: r[1:] for r in c.execute(overview.BREADTH_SQL, ([d.isoformat() for d in DATES],)).fetchall()}
        mk = {d.isoformat(): (got[(d, 'MARKET', 'IHSG')]['n_ema50'], got[(d, 'MARKET', 'IHSG')]['above_ema50'],
                              got[(d, 'MARKET', 'IHSG')]['n_ema200'], got[(d, 'MARKET', 'IHSG')]['above_ema200']) for d in DATES}
        check('MARKET breadth equals the Overview BREADTH_SQL on every date', all(tuple(br[d]) == mk[d] for d in mk), f'{len(br)} dates')
        # idempotent: every date again, the same values
        before = table(c)
        for d in DATES:
            c.execute('SELECT public.refresh_feature_08_day(%s)', (d,))
        check('a second refresh of every date writes the same values', table(c) == before)
        # an older date again, then the later ones: the same values
        for d in DATES[5:]:
            c.execute('SELECT public.refresh_feature_08_day(%s)', (d,))
        check('refreshing from an older date onward gives the same values', table(c) == before)
        # the gap refusal
        c.execute('DELETE FROM public."Feature_08_Group_Daily" WHERE date = %s', (DATES[25],))
        try:
            c.execute('SELECT public.refresh_feature_08_day(%s)', (DATES[26],))
            check('a date after a missing date is refused', False)
        except psycopg.Error as e:
            check('a date after a missing date is refused', 'has no row while older dates have' in str(e), str(e).splitlines()[0])
        for d in DATES[25:]:
            c.execute('SELECT public.refresh_feature_08_day(%s)', (d,))
        check('after refreshing in order the values are back', table(c) == before)
        # a date off the calendar
        for bad in (DATES[-1] + dt.timedelta(days=1), DATES[-1] + dt.timedelta(days=3), None):
            try:
                c.execute('SELECT public.refresh_feature_08_day(%s)', (bad,))
                check(f'refresh({bad}) is refused', False)
            except psycopg.Error as e:
                check(f'refresh({bad}) is refused', 'not a market date' in str(e) or 'a market date is required' in str(e),
                      str(e).splitlines()[0])
        # a reclassified industry: the old group's row of that date goes, the new one starts at 100
        c.execute("""UPDATE public."IDX_Stock_Universe" SET "Industry" = 'Banking' WHERE "Ticker" IN ('AAAA', 'BBBB')""")
        c.execute('SELECT public.refresh_feature_08_day(%s)', (DATES[-1],))
        t2 = table(c)
        check('a reclassified industry: the old name has no row on that date, the new one starts at 100',
              (DATES[-1], 'INDUSTRY', 'Banks') not in t2 and t2[(DATES[-1], 'INDUSTRY', 'Banking')]['index_level'] == 100
              and t2[(DATES[-1], 'INDUSTRY', 'Banking')]['members'] == 2)
        c.execute("""UPDATE public."IDX_Stock_Universe" SET "Industry" = 'Banks' WHERE "Ticker" IN ('AAAA', 'BBBB')""")
        c.execute('DELETE FROM public."Feature_08_Group_Daily" WHERE group_name = %s', ('Banking',))
        c.execute('SELECT public.refresh_feature_08_day(%s)', (DATES[-1],))
        t3 = table(c)
        check('back to the original classification', t3 == before,
              str([(k, {c_: (t3.get(k, {}).get(c_), v[c_]) for c_ in COLS if t3.get(k, {}).get(c_) != v[c_]})
                   for k, v in before.items() if t3.get(k) != v][:3]))
        # the catalog
        n = c.execute("""SELECT (SELECT count(*) FROM public."Table_Catalog" WHERE table_name = 'Feature_08_Group_Daily'),
                                (SELECT count(*) FROM public."Column_Catalog" WHERE table_name = 'Feature_08_Group_Daily'),
                                (SELECT count(*) FROM public."Feature_Catalog" WHERE feature_table = 'Feature_08_Group_Daily'
                                 AND is_active AND semantic_review_status = 'CALCULATION_VERIFIED'
                                 AND btrim(analytical_interpretation) <> '' AND btrim(recommended_use) <> ''
                                 AND btrim(misuse_warning) <> '' AND cardinality(validation_evidence) > 0)""").fetchone()
        check('catalog rows: 1 table, 18 columns, 18 active Feature definitions', n == (1, 18, 18), str(n))
        # the grants
        c.execute('SET ROLE terminal_market_reader')
        rows = c.execute('SELECT count(*) FROM public."Feature_08_Group_Daily"').fetchone()[0]
        w = c.execute('SELECT count(*), max(weight_basis) FROM public.feature_08_weight(%s)', (DATES[-1],)).fetchone()
        check('the publisher role reads the table and the weights', rows == len(before) and w[1] == 'adv20_value', f'{rows} rows, {w}')
        try:
            c.execute('SELECT public.refresh_feature_08_day(%s)', (DATES[-1],))
            check('the publisher role cannot run the refresh', False)
        except psycopg.Error as e:
            check('the publisher role cannot run the refresh', 'permission denied' in str(e), str(e).splitlines()[0])
        c.execute('RESET ROLE')
        w = c.execute('SELECT count(*), count(DISTINCT weight_basis), max(weight_basis) FROM public.feature_08_weight(%s)',
                      (DATES[-1],)).fetchone()
        check('feature_08_weight equals overview_stock_size (one basis)', w[1] == 1 and w[0] == c.execute(
            'SELECT count(*) FROM public.overview_stock_size(%s)', (DATES[-1],)).fetchone()[0], str(w))
    worker_section(db, before)
    publisher_section(db)
    print('VERDICT ' + ('PASS' if not FAILURES else f'FAIL {FAILURES}'))
    return 0 if not FAILURES else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else 'host=/var/lib/postgresql/sa_rehearsal port=55432 user=postgres dbname=postgres'))
