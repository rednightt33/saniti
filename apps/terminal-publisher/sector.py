"""EXEC-SECTOR-ANALYSIS S2 (user decisions UD66 A-J and UD67 "1A 2A 3 go", 2026-11-26): the Sector Analysis page's files.

The page (EDGE tab `sector`) reads gzip JSON files of the family `sector/`, content-keyed and indexed in state.json
`sector` exactly as the Overview's ({name: {key, sha256, bytes, rows, as_of}}); terminal-api presigns them only for the
EDGE gateway key. The build contract is verification/sector_analysis/CONTRACT.md section 3; SECTOR_FORMULAS.md explains
every figure.

  sector-meta              the market and benchmarks, the weight basis and its label, the periods, the 11 IDX sectors
                           (name, short name, index ticker), the industries with their sector, every common stock
                           (name, sector, "Other" for Undefined; industry, null for Undefined), the 20 picker dates
                           (the Overview's), prices_through and breadth_through
  sector-series            the 300 newest market dates (the Overview's series dates): the closes of IHSG, LQ45 and the
                           11 sector indexes; per group (IHSG and every sector) the breadth of Feature_08_Group_Daily
                           (members, EMA50/EMA200 counts, advancers/unchanged/decliners); per industry its index level and
                           members
  sector-day-YYYY-MM-DD    one picker date: every common stock with a final close on it (aligned by `i`, its position in
                           meta.stocks): close, volume, 1D/1W/1M/3M returns from the final closes over market sessions
                           (1, 5, 20, 60), the weight, the EMA50/EMA200 flags and distances, the sessions in the current
                           status against each EMA (capped at STATUS_CAP) and the first session of that status
  sector-stocks-<index>    one per sector, the index ticker lowercased (sector-stocks-idxfinance: terminal-api's name
                           rule): the 300 series dates and every stock's daily close, read only when the page opens that
                           sector's stock lines or stock beta

Everything the page computes from the user's choice (periods, ranks, the rotation map, pairs, correlations, beta) stays
in the page; every weight comes from public.feature_08_weight (decision D1: one pluggable basis, named in the files).
Every list is ordered here, so equal tables give equal bytes; a file is written only when its bytes change (publish_page).

What a run reads, and what it carries (CONTRACT.md section 3: history carried from the previous publication):
- Feature_08_Group_Daily over the 300 series dates: one primary-key range (about 70 rows a date, 21,000 rows), read
  whole each run: it is the stored aggregate of Feature 04 (the expensive read moved into the database, migration
  20261126_001), and reading it whole keeps a repaired older date from being published stale;
- the stocks' daily closes of the 300 series dates: carried from the previous sector-stocks files through the Overview's
  own code path (overview.stock_history): only new dates, the recheck window and stocks not held (a listing, the
  "Other" stocks, which no sector file holds) are read;
- a day file is rebuilt only when its inputs changed (the Overview's day_key/still_valid rule: its base and the content
  fingerprints of the newest RECHECK_SESSIONS dates, ERRORS M442); its sessions in status come from the previous date's
  day file (built in this run, or the previous publication's) plus one session; a stock that file cannot answer (not
  in it, or no status there) is counted back over its own Feature 04 rows (F04_HISTORY_SQL, primary key per ticker,
  STATUS_CAP + 1 rows). The first run, or the manual mode `sector`, reads every series date and counts every stock back
  once (about 18 statements of 50 tickers, 0.05-3.2 s each on dev: verification/sector_analysis/db/EXPLAIN.md).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import overview

SCHEMA = 1
DAY_DATES = overview.DAY_DATES                  # decision I: the 20 newest market dates, the Overview's picker
SERIES_SESSIONS = overview.SERIES_SESSIONS      # 300: the Overview's series dates
RECHECK_SESSIONS = overview.RECHECK_SESSIONS    # ERRORS M442: the newest dates fingerprinted by content on every run
STATUS_CAP = 300                                # CONTRACT 3.3: sessions in status counted back at most 300 ("300+")
HISTORY_TICKERS = 50                            # tickers per F04_HISTORY_SQL statement (0.05-3.2 s on dev)
READ_THREADS = 4                                # parallel reads of the previous publication's files (bucket, ~0.55 s each)
BENCHMARK = overview.BENCHMARK                  # LQ45, the second benchmark of Beta & Correlation
OTHER = overview.OTHER                          # a stock whose sector is "Undefined"
UNDEFINED = 'Undefined'
# decision E: the Overview's sessions (apps/edge-bff/overview/src/model.ts: 1M 20, 3M 60, 1Y YEAR = 252)
PERIODS = {'1D': 1, '3D': 3, '1W': 5, '2W': 10, '1M': 20, '3M': 60, '6M': 120, '1Y': 252}
RETURNS = (('r1d', 1), ('r5d', 5), ('r1m', 20), ('r3m', 60))
# the Overview page's short sector names (apps/edge-bff/overview/src/model.ts SHORT; tests/test_sector.py holds the two
# equal); a sector not named keeps its name
SHORT = {'Basic Materials': 'Basic Mat.', 'Consumer Cyclicals': 'Cons. Cyc', 'Consumer Non-Cyclicals': 'Non-Cyc',
         'Infrastructures': 'Infra', 'Properties & Real Estate': 'Property', 'Transportation & Logistic': 'Transport',
         'Healthcare': 'Health', 'Technology': 'Tech'}
# decision D1: the page names the weight by this label; a new basis without a label shows its own name
BASIS_LABELS = {'adv20_value': '20-day average traded value', 'market_cap': 'market capitalisation'}
NAME = re.compile(r'sector-(?:meta|series|day-\d{4}-\d{2}-\d{2}|stocks-[a-z0-9]{1,18})')
STOCKS_PREFIX = 'sector-stocks-'

PRICE = overview.PRICE
F04 = overview.F04
F08 = 'public."Feature_08_Group_Daily"'
UNIVERSE = overview.UNIVERSE
STOCK_SET = overview.STOCK_SET
BACKFILL_LOCK = 'feature_08_group_backfill'     # verification/sector_analysis/db/backfill/backfill_job.py holds it

PROBE_SQL = ("SELECT to_regclass('public.\"Feature_08_Group_Daily\"') IS NOT NULL "
             "AND to_regprocedure('public.feature_08_weight(date)') IS NOT NULL")
LOCK_FREE_SQL = 'SELECT pg_try_advisory_lock(hashtext(%s))'
LOCK_RELEASE_SQL = 'SELECT pg_advisory_unlock(hashtext(%s))'
FILLED_SQL = f"SELECT EXISTS (SELECT 1 FROM {F08} WHERE date = %s AND group_kind = 'MARKET')"
STOCKS_SQL = (f'SELECT "Ticker", "Company Name", "Sector", "Industry" FROM {UNIVERSE} WHERE "Security Type" = \'stock\' '
              'ORDER BY 1')
F08_SQL = (f'SELECT date::text, group_kind, group_name, members, n_ema50, above_ema50, n_ema200, above_ema200, adv_1d, '
           f'unch_1d, dec_1d, index_level FROM {F08} WHERE date BETWEEN %s AND %s')
# the day's rows: the final close and volume, and Feature 04's own close against its EMAs (the Overview's DAY_SQL reads
# the flags the same way)
DAY_SQL = (f'SELECT p.ticker::text, p.close::float8, p.volume::float8, t.close, t.ema_50, t.ema_200 FROM {PRICE} AS p '
           f'LEFT JOIN {F04} AS t ON t.ticker = p.ticker AND t.trade_date = p.date AND t.timeframe = \'Daily\' '
           f"AND t.asset_type = 'equity' WHERE p.date = %s AND p.timeframe = 'Daily' AND p.is_final AND p.ticker IN {STOCK_SET}")
WEIGHT_SQL = 'SELECT ticker, weight, weight_basis FROM public.feature_08_weight(%s)'
# a stock's own Feature 04 rows back from a date (status above/below each EMA), STATUS_CAP + 1 of them per ticker
F04_HISTORY_SQL = (f'SELECT x.ticker, h.trade_date::text, h.close > h.ema_50, h.close > h.ema_200 '
                   f'FROM unnest(%s::text[]) AS x(ticker) CROSS JOIN LATERAL (SELECT t.trade_date, t.close, t.ema_50, '
                   f"t.ema_200 FROM {F04} AS t WHERE t.ticker = x.ticker AND t.timeframe = 'Daily' AND t.asset_type = 'equity' "
                   f'AND t.trade_date <= %s ORDER BY t.trade_date DESC LIMIT {STATUS_CAP + 1}) AS h')
# ERRORS M442: the content of Feature 04 within the recheck window (the day files read its close and EMA values, not only
# the flags the Overview fingerprints); prices are the Overview's FP_PRICE_SQL
FP_F04_SQL = (f"SELECT trade_date::text, md5(string_agg(ticker || ':' || close::text || ':' || coalesce(ema_50::text, '') "
              f"|| ':' || coalesce(ema_200::text, ''), ',' ORDER BY ticker)) FROM {F04} WHERE trade_date = ANY(%s::date[]) "
              f"AND timeframe = 'Daily' AND asset_type = 'equity' AND ticker IN {STOCK_SET} GROUP BY 1")
F08_FP_SQL = (f"SELECT md5(coalesce(string_agg(date::text || ':' || group_kind || ':' || group_name || ':' || members || ':' "
              f"|| n_ema50 || ':' || above_ema50 || ':' || n_ema200 || ':' || above_ema200 || ':' || adv_1d || ':' || unch_1d "
              f"|| ':' || dec_1d || ':' || coalesce(index_level::text, ''), ',' ORDER BY date, group_kind, group_name), '')) "
              f'FROM {F08} WHERE date BETWEEN %s AND %s')
WEIGHT_FN_SQL = ("SELECT md5(string_agg(md5(prosrc), ',' ORDER BY proname)) FROM pg_proc WHERE oid IN "
                 "(to_regprocedure('public.feature_08_weight(date)'), to_regprocedure('public.overview_stock_size(date)'))")
# what the publication depends on besides the window fingerprints and Feature 08's content: the newest market price
# date, Feature 01's newest date (the picker, as the Overview's), Feature 04's newest date, the stocks with their name,
# sector and industry, and the weight functions (a new basis)
STAMP_SQL = (f"SELECT (SELECT max(date)::text FROM {PRICE} WHERE ticker = %(m)s AND timeframe = 'Daily' AND is_final), "
             f'(SELECT max(date)::text FROM {overview.F01}), '
             f"(SELECT max(trade_date)::text FROM {F04} WHERE timeframe = 'Daily' AND asset_type = 'equity'), "
             f'(SELECT md5(coalesce(string_agg("Ticker" || \':\' || "Company Name" || \':\' || "Sector" || \':\' || "Industry", '
             f'\',\' ORDER BY "Ticker"), \'\')) FROM {UNIVERSE} WHERE "Security Type" = \'stock\')')
CODE = hashlib.md5(Path(__file__).read_bytes()).hexdigest()

MAINTAINED_BY = ('daily', 'backfill', 'sector')    # the modes that rebuild the files when their stamp changed
UNAVAILABLE = 'Feature_08_Group_Daily or feature_08_weight not created'   # migration 20261126_001 not applied yet


def available(conn):
    return bool(conn.execute(PROBE_SQL).fetchone()[0])


def backfill_running(conn):
    """True while the backfill job holds its lock (the lock is taken and given back at once otherwise)."""
    if not conn.execute(LOCK_FREE_SQL, (BACKFILL_LOCK,)).fetchone()[0]:
        return True
    conn.execute(LOCK_RELEASE_SQL, (BACKFILL_LOCK,))
    return False


def busy(conn):
    """A reason not to publish now, or None (QA 2026-11-14: never publish half-filled tables): the backfill is running,
    or Feature 08 does not reach back to the first series date yet (its history is the backfill's)."""
    if backfill_running(conn):
        return 'the Feature 08 backfill is running'
    m = overview.market(conn)
    dates = [r[0] for r in conn.execute(overview.DATES_SQL, (m, SERIES_SESSIONS)).fetchall()] if m else []
    if dates and not conn.execute(FILLED_SQL, (dates[-1],)).fetchone()[0]:
        return f'Feature 08 has no row on the first series date {dates[-1]} (run the backfill)'
    return None


num = overview.num
digest = overview.digest


def window_inputs(run, m):
    """(window, fingerprints) of the newest RECHECK_SESSIONS market dates: {'price:<d>', 'f04:<d>': md5 of those rows};
    a key that is absent has no row yet (a late load). run(sql, params) -> rows."""
    window = sorted(r[0] for r in run(overview.DATES_SQL, (m, RECHECK_SESSIONS)))
    fp = {}
    if window:
        fp.update((f'price:{d}', h) for d, h in run(overview.FP_PRICE_SQL, (window,)))
        fp.update((f'f04:{d}', h) for d, h in run(FP_F04_SQL, (window,)))
    return window, fp


def day_key(d, prior, tickers, fp):
    """What a day file was built from: its base (its prior market date, the stock list it indexes) and the fingerprints
    of its inputs within the recheck window (prices and Feature 04 up to the date: the returns, the weight and the
    sessions in status read them)."""
    return {'base': [prior, tickers], 'win': {k: v for k, v in fp.items() if k.split(':', 1)[1] <= d}}


still_valid = overview.still_valid


def stamp(conn):
    """The stamp of the publication: STAMP_SQL, the weight functions, Feature 08's content over the series dates, the
    window fingerprints and this module's code. A run whose stamp equals state.json `sector_stamp` carries the index."""
    m = overview.market(conn)
    if not m:
        return [None, CODE]
    run = lambda sql, params: conn.execute(sql, params).fetchall()
    dates = [r[0] for r in run(overview.DATES_SQL, (m, SERIES_SESSIONS))]
    row = conn.execute(STAMP_SQL, {'m': m}).fetchone()
    f08 = run(F08_FP_SQL, (dates[-1], dates[0]))[0][0] if dates else None
    wfn = conn.execute(WEIGHT_FN_SQL).fetchone()[0]
    return [None if v is None else str(v) for v in row] + [wfn, f08, digest(window_inputs(run, m)[1]), CODE]


def short_of(name):
    return SHORT.get(name, name)


def industry_sectors(stocks):
    """{industry: its sector}: the sector of most of its stocks (ties: the first by name), the migration's mode() rule
    (refresh_feature_08_day `ind`); 'Undefined' is not an industry."""
    counts = {}
    for _, _, s, ind in stocks:
        if ind and ind != UNDEFINED:
            counts.setdefault(ind, Counter())[s] += 1
    return {ind: min(c.items(), key=lambda kv: (-kv[1], kv[0]))[0] for ind, c in counts.items()}


def meta_doc(stocks, sectors, market_ticker, day_dates, basis, prices_through, breadth_through):
    """stocks: STOCKS_SQL rows (ticker, name, sector, industry); sectors: overview.SECTORS_SQL rows (index, sector)."""
    known = {s for _, s in sectors}
    inds = industry_sectors(stocks)
    return {
        'schema': SCHEMA, 'market': market_ticker, 'benchmarks': [market_ticker, BENCHMARK],
        'weight_basis': basis, 'weight_label': BASIS_LABELS.get(basis, basis) if basis else None,
        'periods': dict(PERIODS),
        'sectors': [{'name': s, 'short': short_of(s), 'index': t} for t, s in sorted(sectors, key=lambda r: r[1])],
        'industries': [{'name': i, 'sector': inds[i]} for i in sorted(inds)],
        'stocks': {'ticker': [t for t, *_ in stocks], 'name': [n for _, n, _, _ in stocks],
                   'sector': [s if s in known else OTHER for _, _, s, _ in stocks],
                   'industry': [ind if ind in inds else None for _, _, _, ind in stocks]},
        'dates': list(day_dates), 'prices_through': prices_through, 'breadth_through': breadth_through,
    }


BREADTH_KEYS = (('members', 3), ('n50', 4), ('a50', 5), ('n200', 6), ('a200', 7), ('adv', 8), ('unch', 9), ('dec', 10))


def series_doc(dates, closes, sectors, market_ticker, f08, industries):
    """dates: the series dates, oldest first; closes: {ticker: {date: (o, h, l, c)}} (overview.CLOSES_SQL); f08: F08_SQL
    rows; industries: the industry names of sector-meta. A date without a Feature 08 row is null."""
    rows = {(r[1], r[2], r[0]): r for r in f08}
    line = lambda t: [num(closes.get(t, {}).get(d, (None,) * 4)[3], 2) for d in dates]

    def breadth(kind, name):
        got = [rows.get((kind, name, d)) for d in dates]
        return {k: [None if r is None else r[i] for r in got] for k, i in BREADTH_KEYS}

    def industry(name):
        got = [rows.get(('INDUSTRY', name, d)) for d in dates]
        return {'level': [None if r is None else num(r[11], 6) for r in got],
                'members': [None if r is None else r[3] for r in got]}
    by_name = sorted(sectors, key=lambda r: r[1])
    return {
        'schema': SCHEMA, 'dates': list(dates),
        'index': {market_ticker: line(market_ticker), BENCHMARK: line(BENCHMARK)},
        'sector': {s: line(t) for t, s in by_name},
        'breadth': {market_ticker: breadth('MARKET', market_ticker), **{s: breadth('SECTOR', s) for _, s in by_name}},
        'industry': {i: industry(i) for i in sorted(industries)},
    }


def run_length(rows, d):
    """(days, since) of the status on d from a stock's own Feature 04 rows (F04_HISTORY_SQL: (date, status), newest
    first): the consecutive rows ending on d with the same status, at most STATUS_CAP (since None at the cap); (None,
    None) without a status on d."""
    if not rows or rows[0][0] != d or rows[0][1] is None:
        return None, None
    s, n, since = rows[0][1], 0, None
    for day, v in rows:
        if v is None or v != s:
            break
        n += 1
        since = day
        if n >= STATUS_CAP:
            return STATUS_CAP, None
    return n, since


def statuses(prev, t, k, s, d, ask):
    """(days, since) of stock t's status s (1/0) against EMA k (50 or 200) on d, from prev (the previous market date's
    day file as {ticker: row}) plus one session; when prev cannot answer, `ask(t)` is called and None returned (counted
    back from the stock's own rows afterwards)."""
    if s is None:
        return None, None
    p = prev.get(t) if prev else None
    if p is None or p[f'above_ema{k}'] is None or p[f'days{k}'] is None:
        ask(t)
        return None
    if p[f'above_ema{k}'] != s:
        return 1, d
    days = p[f'days{k}'] + 1
    return (STATUS_CAP, None) if days >= STATUS_CAP else (days, p[f'since{k}'])


def rows_of(doc, tickers):
    """A sector-day document as {ticker: {field: value}} (tickers: meta.stocks.ticker of the run; a document of another
    stock list, or none, gives {})."""
    if not isinstance(doc, dict) or doc.get('schema') != SCHEMA:
        return {}
    st = doc.get('stocks') or {}
    keys = [k for k in st if k != 'i']
    out = {}
    for n, i in enumerate(st.get('i') or []):
        if isinstance(i, int) and 0 <= i < len(tickers):
            out[tickers[i]] = {k: st[k][n] for k in keys}
    return out


def day_doc(d, prior, stock_index, rows, weights, hist, dates, status):
    """One picker date. rows: DAY_SQL rows; weights: {ticker: weight}; hist: {ticker: {date: close}} of the series dates
    (dates, oldest first); status: {ticker: (days50, since50, days200, since200)}."""
    rows = sorted(rows, key=lambda r: stock_index[r[0]])
    at = dates.index(d)

    def ret(t, n):
        if at - n < 0:
            return None
        a, b = hist.get(t, {}).get(dates[at - n]), hist.get(t, {}).get(d)
        return num((b / a - 1) * 100, 4) if a and b is not None and a > 0 else None
    flag = lambda c, e: None if c is None or e is None else int(c > e)
    dist = lambda c, e: None if c is None or e is None or e <= 0 else num((c / e - 1) * 100, 4)
    col = lambda f: [f(r) for r in rows]
    st = lambda t, j: (status.get(t) or (None,) * 4)[j]
    return {
        'schema': SCHEMA, 'date': d, 'prior_date': prior,
        'stocks': {'i': col(lambda r: stock_index[r[0]]), 'close': col(lambda r: num(r[1], 2)),
                   'volume': col(lambda r: num(r[2], 0)),
                   **{k: col(lambda r, n=n: ret(r[0], n)) for k, n in RETURNS},
                   'weight': col(lambda r: num(weights.get(r[0]), 0)),
                   'above_ema50': col(lambda r: flag(r[3], r[4])), 'above_ema200': col(lambda r: flag(r[3], r[5])),
                   'd_ema50': col(lambda r: dist(r[3], r[4])), 'd_ema200': col(lambda r: dist(r[3], r[5])),
                   'days50': col(lambda r: st(r[0], 0)), 'days200': col(lambda r: st(r[0], 2)),
                   'since50': col(lambda r: st(r[0], 1)), 'since200': col(lambda r: st(r[0], 3))},
    }


def stocks_name(index_ticker):
    """sector-stocks-<index ticker lowercased> (terminal-api keeps names matching ^[a-z0-9][a-z0-9_-]{0,31}$)."""
    return STOCKS_PREFIX + index_ticker.lower()


def stocks_doc(sector, tickers, dates, hist):
    return {'schema': SCHEMA, 'sector': sector, 'dates': list(dates), 'ticker': list(tickers),
            'close': [[num(hist.get(t, {}).get(d), 2) for d in dates] for t in tickers]}


def previous_closes(read, previous, tickers):
    """The previous publication's sector-stocks files merged in the overview-stocks shape overview.stock_history reads
    ({schema, ticker, dates, fnet_dates, close, fnet}), or None. A file of other dates than the first one read is left
    out (its stocks are then read again)."""
    names = sorted(n for n in previous if n.startswith(STOCKS_PREFIX))
    if not names or read is None:
        return None
    with ThreadPoolExecutor(READ_THREADS) as pool:
        docs = list(pool.map(lambda n: _safe(read, n), names))
    known, out = set(tickers), {'schema': overview.STOCKS_SCHEMA, 'ticker': [], 'dates': None, 'fnet_dates': [],
                                'close': [], 'fnet': []}
    for doc in docs:
        if not (isinstance(doc, dict) and doc.get('schema') == SCHEMA and isinstance(doc.get('ticker'), list)
                and isinstance(doc.get('close'), list) and len(doc['close']) == len(doc['ticker'])):
            continue
        if out['dates'] is None:
            out['dates'] = doc.get('dates') or []
        if doc.get('dates') != out['dates']:
            continue
        for t, row in zip(doc['ticker'], doc['close']):
            if t in known and t not in out['ticker'] and isinstance(row, list) and len(row) == len(out['dates']):
                out['ticker'].append(t)
                out['close'].append(row)
                out['fnet'].append([])
    return out if out['ticker'] else None


def _safe(read, name):
    try:
        return read(name)
    except Exception:  # noqa: BLE001 - unreadable: those stocks are read again rather than fail the publication
        return None


def count_back(stream, tickers, d):
    """{ticker: (days50, since50, days200, since200)} on d from each stock's own Feature 04 rows (F04_HISTORY_SQL),
    HISTORY_TICKERS stocks per statement."""
    out = {}
    tickers = sorted(tickers)
    for k in range(0, len(tickers), HISTORY_TICKERS):
        hist = {}
        for t, day, a50, a200 in stream(F04_HISTORY_SQL, (tickers[k:k + HISTORY_TICKERS], d)):
            hist.setdefault(t, []).append((day, a50, a200))
        for t in tickers[k:k + HISTORY_TICKERS]:
            rows = sorted(hist.get(t, []), reverse=True)
            to_int = lambda v: None if v is None else int(bool(v))
            d50 = run_length([(day, to_int(a)) for day, a, _ in rows], d)
            d200 = run_length([(day, to_int(b)) for day, _, b in rows], d)
            out[t] = (d50[0], d50[1], d200[0], d200[1])
    return out


def files(conn, names, lists, stream=None, carry=None, previous=None, present=None, read=None):
    """Every Sector Analysis file to write -> (files [(name, doc, rows, as_of)], kept [day file names whose previous
    index entry stays], carry for state.json). names, lists: unused (the stocks come from the universe); carry: the
    previous run's (None: build everything from the database); previous: the previous index; present: the keys under
    sector/ in the bucket; read(name): the previous publication's file of that name (decoded), or None."""
    stream = stream or (lambda sql, params: conn.execute(sql, params).fetchall())
    previous, present = previous or {}, present or set()
    m = overview.market(conn)
    if not m:
        return [], [], None
    market_dates = list(reversed([r[0] for r in conn.execute(overview.DATES_SQL, (m, SERIES_SESSIONS)).fetchall()]))
    if not market_dates:
        return [], [], None
    with_f01 = {r[0] for r in stream(overview.FEATURE_DATES_SQL, (market_dates[-DAY_DATES * 2:],))}
    day_dates = [d for d in market_dates if d in with_f01][-DAY_DATES:]
    if not day_dates:
        return [], [], None
    weight_fn = (conn.execute(WEIGHT_FN_SQL).fetchone() or (None,))[0]
    full_history = carry is None                 # the first run or the manual mode: nothing of the previous files
    if not (isinstance(carry, dict) and carry.get('code') == CODE and carry.get('weight_fn') == weight_fn):
        carry = None                             # another formula or weight basis: every day file again
    stocks = conn.execute(STOCKS_SQL).fetchall()
    tickers = [t for t, *_ in stocks]
    stock_index = {t: i for i, t in enumerate(tickers)}
    sectors = conn.execute(overview.SECTORS_SQL).fetchall()
    closes = {}
    for t, d, o, h, lo, c in stream(overview.CLOSES_SQL, ([m, BENCHMARK, *(t for t, _ in sectors)], market_dates[0],
                                                          market_dates[-1])):
        closes.setdefault(t, {})[d] = (o, h, lo, c)
    f08 = stream(F08_SQL, (market_dates[0], market_dates[-1]))
    window, fp = window_inputs(stream, m)
    # the stocks' closes of the series dates (overview.stock_history: carried, the window and new stocks read again)
    prev_stocks = None if full_history else previous_closes(read, previous, tickers)
    hist, _, _ = overview.stock_history(stream, prev_stocks, tickers, market_dates, [], set(window), set())
    tick_digest = digest(tickers)
    at = {d: i for i, d in enumerate(market_dates)}
    built, kept, day_stamps, docs_now, basis = [], [], {}, {}, None

    def doc_of(d):
        """The day file of market date d as {ticker: row}: built in this run, or (with a valid carry) the previous
        publication's; {} when neither."""
        if d in docs_now:
            return docs_now[d]
        name = f'sector-day-{d}'
        held = ((carry or {}).get('days') or {}).get(d)
        # only a file built on the same stock list (its positions) by this code (carry valid)
        if carry is None or name not in previous or read is None or not isinstance(held, dict) \
                or (held.get('base') or [None, None])[1:] != [tick_digest]:
            return {}
        docs_now[d] = rows_of(_safe(read, name), tickers)
        return docs_now[d]
    for d in day_dates:
        i = at[d]
        prior = market_dates[i - 1] if i else None
        name = f'sector-day-{d}'
        day_stamps[d] = day_key(d, prior, tick_digest, fp)
        entry = previous.get(name)
        if (carry and still_valid((carry.get('days') or {}).get(d), day_stamps[d]) and entry
                and entry['key'][len('v1/'):] in present):
            kept.append(name)
            continue
        rows = [r for r in stream(DAY_SQL, (d,)) if r[0] in stock_index]
        wrows = stream(WEIGHT_SQL, (d,))
        weights = {t: w for t, w, _ in wrows}
        basis = (wrows[0][2] if wrows else None) or basis
        prev = doc_of(prior) if prior else {}
        ask, status = set(), {}
        for r in rows:
            t = r[0]
            s50 = None if r[3] is None or r[4] is None else int(r[3] > r[4])
            s200 = None if r[3] is None or r[5] is None else int(r[3] > r[5])
            a = statuses(prev, t, 50, s50, d, ask.add)
            b = statuses(prev, t, 200, s200, d, ask.add)
            status[t] = (*(a or (None, None)), *(b or (None, None)))
        if ask:                                  # the stocks the previous day file cannot answer: counted back
            counted = count_back(stream, ask, d)
            for t in ask:
                status[t] = merge(status[t], counted.get(t, (None,) * 4))
        doc = day_doc(d, prior, stock_index, rows, weights, hist, market_dates, status)
        docs_now[d] = rows_of(doc, tickers)
        built.append((name, doc, len(doc['stocks']['i']), d))
    if basis is None:                            # every day file was kept: the newest day's basis (one cheap call)
        wrows = stream(WEIGHT_SQL, (day_dates[-1],))
        basis = wrows[0][2] if wrows else None
    known = {s for _, s in sectors}
    inds = industry_sectors(stocks)
    with_market = sorted(r[0] for r in f08 if r[1] == 'MARKET')
    meta = meta_doc(stocks, sectors, m, day_dates, basis, market_dates[-1], with_market[-1] if with_market else None)
    out = [('sector-meta', meta, len(tickers), day_dates[-1]),
           ('sector-series', series_doc(market_dates, closes, sectors, m, f08, inds), len(market_dates), day_dates[-1])]
    by_sector = {}
    for t, _, s, _ in stocks:
        if s in known:
            by_sector.setdefault(s, []).append(t)
    for t, s in sorted(sectors, key=lambda r: r[1]):
        members = by_sector.get(s, [])
        out.append((stocks_name(t), stocks_doc(s, members, market_dates, hist), len(members), day_dates[-1]))
    new_carry = {'code': CODE, 'weight_fn': weight_fn, 'days': day_stamps}
    return out + built, kept, new_carry


def merge(old, new):
    """A stock's (days50, since50, days200, since200): the values the previous day file gave, the counted ones for the
    EMA it could not answer (old holds None there)."""
    pick = lambda o, n: o if o[0] is not None else n
    return (*pick(old[:2], new[:2]), *pick(old[2:], new[2:]))
