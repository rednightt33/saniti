"""EXEC-OVERVIEW O2 (user go 2026-11-15: "1 ok, 2 ok, 3 ok, go"): the Market Overview's files.

The Overview page (EDGE, owner only) reads gzip JSON files of the family `overview/`, content-keyed as the Radar's are
(`overview/<name>.<first 16 hex of sha256>.json.gz`) and indexed in state.json `overview` ({name: {key, sha256, bytes,
rows, as_of}}). terminal-api presigns them only for the EDGE gateway key. OVERVIEW_FORMULAS.md explains every figure.

  overview-meta            every common stock (name, sector; "Undefined" is "Other"), the 11 IDX sectors with their
                           index, the stock lists with their members, the market and benchmark index, the dates with a
                           day file, the size basis
  overview-series          per market date (SERIES_SESSIONS newest, oldest first): the closes of IHSG, LQ45 and the 11
                           sector indexes; the stocks above EMA50 and EMA200; and per broker date the market's foreign
                           buying and selling and its Regular turnover
  overview-day-YYYY-MM-DD  one market date (the DAY_DATES newest): the market and benchmark (OHLC, prior close), IHSG's
                           20-day volatility and its rank in its own year, breadth, turnover and foreign flow at the
                           newest broker date up to it, every stock's close, returns, size, foreign net and EMA flags,
                           and IHSG's 5-minute bars of that session and 1-hour bars of the 5 sessions ending on it

Everything the page shows that does not depend on the user's choice (universe, period, metric) is computed here; the
rest (the treemap, top movers, sector aggregates of a universe) is arranged by the page from these rows. Every list is
ordered here, so equal tables give equal bytes.

What a run reads (measured on dev 2026-11-15, read-only EXPLAIN ANALYZE): Feature 04 is 2.5 GB and the rows of one date
of its older history are spread over the whole table (correlation of trade_date -0.04), so 60 dates read 14,102 pages in
11 s and 300 timed out. The stocks above EMA50/EMA200 per date and the day files are therefore carried from the previous
publication (`files`, carry): a run reads Feature 04 only for dates it has not counted yet (one recent date: 0.4 s) and
rebuilds a day file only when its broker date or its Feature 04 rows changed. The first run, or the manual mode
`overview`, counts every series date once, BREADTH_CHUNK dates per statement (a large read: AGENTS.md "Postgres memory
after large updates").
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

SCHEMA = 1
DAY_DATES = 20              # the date picker, as the Radar's (EXEC-OVERVIEW: "20 tanggal terakhir")
SERIES_SESSIONS = 300       # 1Y (252 sessions) back from the oldest picker date, and the year start for YTD
VOL_WINDOW = 20             # decision 2026-11-15: 20-day volatility (Feature 01's formula), labelled 20D
VOL_BASE = 252              # its rank in IHSG's own previous 252 values (the Radar's convention: strictly below / 252)
TURNOVER_BASE = 20          # turnover against the average of the 20 broker dates before
FOREIGN_SUM = 10            # the KPI's 10-session foreign net
FLOW_PERIODS = (('1D', 1), ('5D', 5), ('1M', 20), ('3M', 60))
INTRADAY_5D = 5             # the 5D chart: 1-hour bars of the 5 sessions ending on the date
BREADTH_CHUNK = 20          # dates per Feature 04 count: a first run's 300 dates in one statement would take ~55 s cold
                            # (60 dates read 14,102 pages in 11 s on dev) against the publisher login's 120 s timeout
BENCHMARK = 'LQ45'          # the design's second KPI card (an INDEX entity of Feature_Index_Entity)
OTHER = 'Other'             # decision 5: a stock whose sector is "Undefined"
NAME = re.compile(r'overview-(?:meta|series|day-\d{4}-\d{2}-\d{2})')

PRICE = 'public."Price_Stock_Indonesia_IDX"'
F01 = 'public."Feature_01_Stock_Daily"'
F04 = 'public."Feature_04_Technical_Indicator"'
F06 = 'public."Feature_06_Foreign_Domestic"'
F06I = 'public."Feature_06_Foreign_Domestic_INDEX"'
ENTITY = 'public."Feature_Index_Entity"'
UNIVERSE = 'public."IDX_Stock_Universe"'
INTRADAY = 'public.price_stock_idx_intraday'

PROBE_SQL = "SELECT to_regprocedure('public.overview_stock_size(date)') IS NOT NULL"
MARKET_SQL = f"SELECT ticker FROM {ENTITY} WHERE entity_kind = 'MARKET'"
SECTORS_SQL = f"SELECT ticker, sector FROM {ENTITY} WHERE entity_kind = 'SECTOR' ORDER BY sector"
STOCKS_SQL = f'SELECT "Ticker", "Company Name", "Sector" FROM {UNIVERSE} WHERE "Security Type" = \'stock\' ORDER BY 1'
DATES_SQL = (f"SELECT date::text FROM {PRICE} WHERE ticker = %s AND timeframe = 'Daily' AND is_final "
             'ORDER BY date DESC LIMIT %s')
STOCK_SET = f'(SELECT "Ticker" FROM {UNIVERSE} WHERE "Security Type" = \'stock\')'
# one index probe per date (DISTINCT over the dates' rows took 2.4 s on dev; this 0.05 s)
FEATURE_DATES_SQL = (f'SELECT d::text FROM unnest(%s::date[]) AS d WHERE EXISTS (SELECT 1 FROM {F01} AS f '
                     'WHERE f.date = d)')
F04_DATES_SQL = (f'SELECT d::text FROM unnest(%s::date[]) AS d WHERE EXISTS (SELECT 1 FROM {F04} AS t '
                 "WHERE t.trade_date = d AND t.timeframe = 'Daily' AND t.asset_type = 'equity')")
CLOSES_SQL = (f'SELECT ticker, date::text, open::float8, high::float8, low::float8, close::float8 FROM {PRICE} '
              "WHERE ticker = ANY(%s) AND timeframe = 'Daily' AND is_final AND date BETWEEN %s AND %s")
DAY_SQL = (f'SELECT f.ticker, f.close::float8, f.return_1d_pct::float8, f.return_5d_pct::float8, '
           f'f.return_20d_pct::float8, t.close > t.ema_50, t.close > t.ema_200 FROM {F01} AS f '
           f'LEFT JOIN {F04} AS t ON t.ticker = f.ticker AND t.trade_date = f.date AND t.timeframe = \'Daily\' '
           f"AND t.asset_type = 'equity' WHERE f.date = %s AND f.ticker IN {STOCK_SET}")
SIZE_SQL = 'SELECT ticker, size_value, size_basis FROM public.overview_stock_size(%s)'
STOCK_FLOW_SQL = (f'SELECT ticker, foreign_net_1d::float8, foreign_net_5d::float8, foreign_net_20d::float8, '
                  f"foreign_net_60d::float8 FROM {F06} WHERE trade_date = %s AND market_board = 'Regular' "
                  f'AND ticker IN {STOCK_SET}')
MARKET_FLOW_SQL = (f'SELECT trade_date::text, foreign_buy_1d::float8, foreign_sell_1d::float8, domestic_buy_1d::float8 '
                   f"FROM {F06I} WHERE ticker = %s AND market_board = 'Regular' AND trade_date >= %s ORDER BY 1")
BREADTH_SQL = (f'SELECT t.trade_date::text, count(t.ema_50), count(*) FILTER (WHERE t.close > t.ema_50), '
               f'count(t.ema_200), count(*) FILTER (WHERE t.close > t.ema_200) FROM {F04} AS t '
               "WHERE t.trade_date = ANY(%s::date[]) AND t.timeframe = 'Daily' AND t.asset_type = 'equity' "
               f'AND t.ticker IN {STOCK_SET} GROUP BY 1')
SIZE_FN_SQL = "SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure('public.overview_stock_size(date)')"
INTRADAY_SQL = (f'SELECT session_date::text, extract(epoch FROM bar_time)::bigint, close::float8 FROM {INTRADAY} '
                'WHERE ticker = %s AND timeframe = %s AND session_date BETWEEN %s AND %s ORDER BY bar_time')
# what the publication depends on: the newest market price date, broker (Feature 06 _INDEX) date, Feature 01 and 04
# dates, Feature 01's rows over the picker's dates (a late correction or a recomputed date), the stocks with their
# sector, the stock lists' membership, the size function (a new basis) and this module's code (a new formula). Feature
# 04's rows are not counted (a count over its picker dates read 2,443 pages on dev): a recomputed older date of Feature
# 04 is published by the manual mode `overview`.
STAMP_SQL = (f"SELECT (SELECT max(date)::text FROM {PRICE} WHERE ticker = %(m)s AND timeframe = 'Daily' AND is_final), "
             f"(SELECT max(trade_date)::text FROM {F06I} WHERE ticker = %(m)s AND market_board = 'Regular'), "
             f'(SELECT max(date)::text FROM {F01}), '
             f"(SELECT max(trade_date)::text FROM {F04} WHERE timeframe = 'Daily' AND asset_type = 'equity'), "
             f'(SELECT count(*) FROM {F01} WHERE date >= %(lo)s), '
             f'(SELECT md5(coalesce(string_agg("Ticker" || \':\' || coalesce("Sector", \'\'), \',\' ORDER BY "Ticker"), \'\')) '
             f'FROM {UNIVERSE} WHERE "Security Type" = \'stock\'), '
             '(SELECT md5(coalesce(string_agg(list_key || \':\' || "Ticker", \',\' ORDER BY list_key, "Ticker"), \'\')) '
             'FROM public."Stock_List_Member"), '
             "(SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure('public.overview_stock_size(date)'))")
CODE = hashlib.md5(Path(__file__).read_bytes()).hexdigest()


MAINTAINED_BY = ('daily', 'backfill', 'overview')     # the modes that rebuild the files when their stamp changed
UNAVAILABLE = 'overview_stock_size not created'        # migration 20261115_020 not applied yet


def available(conn):
    return bool(conn.execute(PROBE_SQL).fetchone()[0])


def busy(conn):
    """A reason not to publish now, or None (the Radar's first fill has one; the Overview none)."""
    return None


def market(conn):
    row = conn.execute(MARKET_SQL).fetchone()
    return row[0] if row else None


def stamp(conn):
    """The stamp of the publication (STAMP_SQL and the code fingerprint). A run whose stamp equals state.json
    `overview_stamp` carries the index forward."""
    m = market(conn)
    dates = [r[0] for r in conn.execute(DATES_SQL, (m, DAY_DATES)).fetchall()] if m else []
    lo = dates[-1] if dates else '9999-12-31'
    row = conn.execute(STAMP_SQL, {'m': m, 'lo': lo}).fetchone()
    return [None if v is None else str(v) for v in row] + [CODE]


def num(v, digits=6):
    """A float for JSON: None stays None; NaN and infinities are None."""
    if v is None:
        return None
    v = float(v)
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, digits) if digits else round(v)


def volatility(closes, i, window=VOL_WINDOW):
    """Feature 01's volatility_20d_ann_pct on a close series: STDDEV_SAMP of the `window` daily returns ending at i,
    times sqrt(252), in percent; None unless all `window` returns exist."""
    if i < window:
        return None
    rets = []
    for k in range(i - window + 1, i + 1):
        a, b = closes[k - 1], closes[k]
        if a is None or b is None or a == 0:
            return None
        rets.append(b / a - 1)
    mean = sum(rets) / window
    var = sum((r - mean) ** 2 for r in rets) / (window - 1)
    return math.sqrt(var) * math.sqrt(252) * 100


def below_rank(current, history):
    """The Radar's own-history rank: 100 x (previous values strictly below today's) / len, None unless every previous
    value exists."""
    if current is None or not history or any(h is None for h in history):
        return None
    return 100.0 * sum(1 for h in history if h < current) / len(history)


def ohlc(rows, d):
    r = rows.get(d)
    return None if r is None else {'open': num(r[0], 2), 'high': num(r[1], 2), 'low': num(r[2], 2), 'close': num(r[3], 2)}


def meta_doc(stocks, sectors, lists, market_ticker, day_dates, size_basis, prices_through, broker_through):
    """stocks: STOCKS_SQL rows; sectors: SECTORS_SQL rows; lists: [(key, kind, code, name, members)]."""
    known = {s for _, s in sectors}
    return {
        'schema': SCHEMA, 'market': market_ticker, 'benchmark': BENCHMARK,
        'stocks': {'ticker': [t for t, _, _ in stocks], 'name': [n for _, n, _ in stocks],
                   'sector': [s if s in known else OTHER for _, _, s in stocks]},
        'sectors': [{'name': s, 'index': t} for t, s in sectors] + [{'name': OTHER, 'index': None}],
        'lists': [{'key': k, 'kind': kind, 'code': code, 'name': n, 'members': sorted(members or [])}
                  for k, kind, code, n, members in lists],
        'dates': day_dates, 'size_basis': size_basis, 'prices_through': prices_through, 'broker_through': broker_through,
        'periods': {'flow': [p for p, _ in FLOW_PERIODS]},
    }


def series_doc(dates, closes, sectors, market_ticker, breadth, flow):
    """dates: market dates, oldest first; closes: {ticker: {date: (o, h, l, c)}}; breadth: {date: (n50, above50, n200,
    above200)}; flow: MARKET_FLOW_SQL rows (broker dates)."""
    line = lambda t: [num(closes.get(t, {}).get(d, (None,) * 4)[3], 2) for d in dates]
    pct = lambda a, n: num(100.0 * a / n, 2) if n else None
    return {
        'schema': SCHEMA, 'dates': dates,
        'index': {market_ticker: line(market_ticker), BENCHMARK: line(BENCHMARK)},
        'sector': {s: line(t) for t, s in sectors},
        'above_ema50': [pct(breadth[d][1], breadth[d][0]) if d in breadth else None for d in dates],
        'above_ema200': [pct(breadth[d][3], breadth[d][2]) if d in breadth else None for d in dates],
        'breadth_n': [[breadth[d][0], breadth[d][2]] if d in breadth else None for d in dates],
        'flow': {'dates': [r[0] for r in flow], 'foreign_buy': [num(r[1], 0) for r in flow],
                 'foreign_sell': [num(r[2], 0) for r in flow],
                 'turnover': [num((r[1] or 0) + (r[3] or 0), 0) if r[1] is not None or r[3] is not None else None
                              for r in flow]},
    }


def market_figures(flow, broker_date):
    """Turnover, the foreign net KPI and the Foreign Flow periods at broker_date (MARKET_FLOW_SQL rows, oldest first);
    None when no broker date reaches it."""
    at = next((i for i in range(len(flow) - 1, -1, -1) if flow[i][0] <= broker_date), None) if broker_date else None
    if at is None:
        return None
    turnover = lambda r: (r[1] or 0) + (r[3] or 0)
    base = flow[max(0, at - TURNOVER_BASE):at]
    avg = sum(turnover(r) for r in base) / len(base) if len(base) == TURNOVER_BASE else None
    periods = {}
    for name, n in FLOW_PERIODS:
        rows = flow[at - n + 1:at + 1] if at - n + 1 >= 0 else []
        if len(rows) < n:
            periods[name] = None
            continue
        buy, sell = sum(r[1] or 0 for r in rows), sum(r[2] or 0 for r in rows)
        periods[name] = {'buy': num(buy, 0), 'sell': num(sell, 0), 'net': num(buy - sell, 0), 'from': rows[0][0]}
    ten = flow[at - FOREIGN_SUM + 1:at + 1] if at - FOREIGN_SUM + 1 >= 0 else []
    return {
        'date': flow[at][0], 'turnover': num(turnover(flow[at]), 0), 'turnover_avg20': num(avg, 0),
        'turnover_ratio': num(turnover(flow[at]) / avg, 4) if avg else None,
        'foreign_net_1d': num((flow[at][1] or 0) - (flow[at][2] or 0), 0),
        'foreign_net_10d': num(sum((r[1] or 0) - (r[2] or 0) for r in ten), 0) if len(ten) == FOREIGN_SUM else None,
        'periods': periods,
    }


def day_doc(d, prev_d, stock_index, rows, sizes, size_basis, stock_flow, closes, market_ticker, vol, flow_figs, bars):
    """One market date. rows: DAY_SQL rows; sizes: {ticker: size}; stock_flow: {ticker: STOCK_FLOW_SQL row} at the
    broker date; closes: {ticker: {date: (o, h, l, c)}}; vol: (value, rank); bars: {'5m': [...], '1h': [...]}."""
    rows = sorted(rows, key=lambda r: stock_index[r[0]])
    r1 = [r[2] for r in rows]
    idx = lambda t: {**(ohlc(closes.get(t, {}), d) or {}), 'prior_close': num((closes.get(t, {}).get(prev_d) or (None,) * 4)[3], 2)}
    flag = lambda v: None if v is None else int(bool(v))
    fl = lambda t, k: num(stock_flow[t][k], 0) if t in stock_flow else None
    return {
        'schema': SCHEMA, 'date': d, 'prior_date': prev_d, 'size_basis': size_basis,
        'index': {market_ticker: idx(market_ticker), BENCHMARK: idx(BENCHMARK)},
        'volatility': {'window': VOL_WINDOW, 'value': num(vol[0], 4), 'rank_1y': num(vol[1], 2)},
        'breadth': {'advancers': sum(1 for v in r1 if v is not None and v > 0),
                    'decliners': sum(1 for v in r1 if v is not None and v < 0),
                    'unchanged': sum(1 for v in r1 if v is not None and v == 0)},
        'market': flow_figs,
        'stocks': {'i': [stock_index[r[0]] for r in rows], 'close': [num(r[1], 2) for r in rows],
                   'r1d': [num(r[2], 4) for r in rows], 'r5d': [num(r[3], 4) for r in rows],
                   'r1m': [num(r[4], 4) for r in rows], 'size': [num(sizes.get(r[0]), 0) for r in rows],
                   'above_ema50': [flag(r[5]) for r in rows], 'above_ema200': [flag(r[6]) for r in rows],
                   'fnet_1d': [fl(r[0], 1) for r in rows], 'fnet_5d': [fl(r[0], 2) for r in rows],
                   'fnet_1m': [fl(r[0], 3) for r in rows], 'fnet_3m': [fl(r[0], 4) for r in rows]},
        'intraday': {tf: {'t': [b[0] for b in v], 'c': [num(b[1], 2) for b in v]} for tf, v in sorted(bars.items())},
    }


def files(conn, names, lists, stream=None, carry=None, previous=None, present=None):
    """Every Overview file to write -> (files [(name, doc, rows, as_of)], kept [day file names whose previous index
    entry stays], carry for state.json). names: unused (the stocks come from the universe); lists: [(key, kind, code,
    name, members)]; carry: the previous run's (None: count and build everything); previous: the previous index; present:
    the keys under overview/ in the bucket."""
    stream = stream or (lambda sql, params: conn.execute(sql, params).fetchall())
    previous, present = previous or {}, present or set()
    m = market(conn)
    if not m:
        return [], [], None
    need = SERIES_SESSIONS + VOL_BASE + VOL_WINDOW + 1
    market_dates = list(reversed([r[0] for r in conn.execute(DATES_SQL, (m, need)).fetchall()]))
    if not market_dates:
        return [], [], None
    with_features = {r[0] for r in stream(FEATURE_DATES_SQL, (market_dates[-DAY_DATES * 2:],))}
    day_dates = [d for d in market_dates if d in with_features][-DAY_DATES:]
    if not day_dates:
        return [], [], None
    series_dates = market_dates[-SERIES_SESSIONS:]
    size_fn = (conn.execute(SIZE_FN_SQL).fetchone() or (None,))[0]
    if not (isinstance(carry, dict) and carry.get('code') == CODE and carry.get('size_fn') == size_fn):
        carry = None                       # another formula or size basis: count and build everything again
    stocks = conn.execute(STOCKS_SQL).fetchall()
    stock_index = {t: i for i, (t, _, _) in enumerate(stocks)}
    sectors = conn.execute(SECTORS_SQL).fetchall()
    closes = {}
    for t, d, o, h, lo, c in stream(CLOSES_SQL, ([m, BENCHMARK, *(t for t, _ in sectors)], market_dates[0], market_dates[-1])):
        closes.setdefault(t, {})[d] = (o, h, lo, c)
    with_f04 = {r[0] for r in stream(F04_DATES_SQL, (series_dates,))}
    breadth = {d: tuple(v) for d, v in ((carry or {}).get('breadth') or {}).items() if d in with_f04}
    todo = [d for d in series_dates if d in with_f04 and d not in breadth]
    for k in range(0, len(todo), BREADTH_CHUNK):     # bounded statements, whatever the number of dates to count
        breadth.update({r[0]: tuple(r[1:]) for r in stream(BREADTH_SQL, (todo[k:k + BREADTH_CHUNK],))})
    flow = stream(MARKET_FLOW_SQL, (m, market_dates[0]))
    mc = [closes.get(m, {}).get(d, (None,) * 4)[3] for d in market_dates]
    vols = [volatility(mc, i) for i in range(len(mc))]
    at = {d: i for i, d in enumerate(market_dates)}
    days, kept, basis, day_stamps = [], [], None, {}
    for d in day_dates:
        i = at[d]
        figs = market_figures(flow, d)
        broker_date = figs['date'] if figs else None
        name = f'overview-day-{d}'
        day_stamps[d] = [broker_date, d in with_f04]
        entry = previous.get(name)
        if (carry and (carry.get('days') or {}).get(d) == day_stamps[d] and entry
                and entry['key'][len('v1/'):] in present):
            kept.append(name)
            continue
        prev_d = market_dates[i - 1] if i else None
        hist = vols[i - VOL_BASE:i] if i >= VOL_BASE else []
        vol = (vols[i], below_rank(vols[i], hist) if len(hist) == VOL_BASE else None)
        rows = [r for r in stream(DAY_SQL, (d,)) if r[0] in stock_index]
        size_rows = stream(SIZE_SQL, (d,))
        sizes = {t: v for t, v, _ in size_rows}
        day_basis = size_rows[0][2] if size_rows else None
        basis = day_basis or basis
        stock_flow = {r[0]: r for r in stream(STOCK_FLOW_SQL, (broker_date,))} if broker_date else {}
        five = market_dates[max(0, i - INTRADAY_5D + 1)]
        bars = {'5m': [(t, c) for s, t, c in stream(INTRADAY_SQL, (m, '5m', d, d))],
                '1h': [(t, c) for s, t, c in stream(INTRADAY_SQL, (m, '1h', five, d))]}
        doc = day_doc(d, prev_d, stock_index, rows, sizes, day_basis, stock_flow, closes, m, vol, figs, bars)
        days.append((name, doc, len(doc['stocks']['i']), d))
    if basis is None:                      # every day file was kept: the newest day's basis (one cheap call)
        size_rows = stream(SIZE_SQL, (day_dates[-1],))
        basis = size_rows[0][2] if size_rows else None
    prices_through = market_dates[-1]
    broker_through = flow[-1][0] if flow else None
    series_flow = [r for r in flow if r[0] >= series_dates[0]]
    out = [('overview-meta', meta_doc(stocks, sectors, lists, m, day_dates, basis, prices_through, broker_through),
            len(stocks), day_dates[-1]),
           ('overview-series', series_doc(series_dates, closes, sectors, m, breadth, series_flow), len(series_dates),
            day_dates[-1])]
    new_carry = {'code': CODE, 'size_fn': size_fn, 'days': day_stamps,
                 'breadth': {d: list(breadth[d]) for d in series_dates if d in breadth}}
    return out + days, kept, new_carry
