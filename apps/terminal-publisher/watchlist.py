"""EXEC-WATCHLIST L4 (user go 2026-11-16: "Go"): the Watchlist page's daily file.

The Watchlist page (EDGE, per account) keeps each user's lists in edge-bff (edge_bff.watchlist_lists/_items) and reads
the market figures of every common stock from one gzip JSON file of the family `watchlist/`, content-keyed as the
Overview's are (`watchlist/watchlist-stocks.<first 16 hex of sha256>.json.gz`) and indexed in state.json `watchlist`.
terminal-api presigns it only for the EDGE gateway key. WATCHLIST_FORMULAS.md explains every figure.

  watchlist-stocks   the dates of the data; the indicator catalog (the page offers only what this file holds); and for
                     every common stock: name, sector, last close, 1D and 1M return, the closes of the TREND_SESSIONS
                     newest sessions, the stored indicator values, its corporate actions of the next EVENT_DAYS days and
                     the Radar screens it meets on the Radar's newest date

Light by decision (user 2026-11-16: "selight as possible yang mana tidak perlu ada calculation lagi"): every value is a
stored column read as it is; the only arithmetic is the distance to an EMA (close / EMA - 1 of the same Feature 04 row).
No history, no percentile, nothing carried between runs. Read cost on dev (2026-11-16, EXPLAIN ANALYZE, every query of a
run): 0.23 s, 8,945 shared pages (verification/watchlist/EXPLAIN_20261116.txt): not a large update.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA = 1
NAME = re.compile(r'watchlist-stocks')
TREND_SESSIONS = 30          # the card's and table's trend line: the newest 30 closes
EVENT_DAYS = 30              # corporate actions after the price date, calendar days
RADAR_LEVEL = 'standard'     # the Radar page's default board (apps/edge-bff/radar/src/app.ts: lv 1, gate 'broad'): a
RADAR_GATE = 'broad'         # badge says what the Radar shows when it opens
DEFAULT_INDICATORS = ('rsi', 'volr', 'dd60', 'fn5')

PRICE = 'public."Price_Stock_Indonesia_IDX"'
F01 = 'public."Feature_01_Stock_Daily"'
F04 = 'public."Feature_04_Technical_Indicator"'
F06 = 'public."Feature_06_Foreign_Domestic"'
F06I = 'public."Feature_06_Foreign_Domestic_INDEX"'
ENTITY = 'public."Feature_Index_Entity"'
UNIVERSE = 'public."IDX_Stock_Universe"'
ACTION = 'public.stockbit_corporate_action'
RADAR = 'public."Feature_07_Radar_Result"'
RADAR_FILTER = 'public."Feature_07_Radar_Filter"'
STOCK_SET = f'(SELECT "Ticker" FROM {UNIVERSE} WHERE "Security Type" = \'stock\')'

# The catalog: key, name, short label, how it is measured, family, unit, which date it belongs to (price or broker),
# whether its sign is coloured, and the stored column it is read from. The page offers exactly these.
CATALOG = (
    ('rsi', 'RSI (14)', 'RSI', 'Wilder, 14 sessions', 'Technical', 'index', 'price', False, 'Feature 04 rsi_14'),
    ('macdh', 'MACD histogram', 'MACD hist.', '12, 26, 9', 'Technical', 'price', 'price', True, 'Feature 04 macd_histogram'),
    ('adx', 'ADX (14)', 'ADX', 'trend strength', 'Technical', 'index', 'price', False, 'Feature 04 adx_14'),
    ('ema50', 'Price vs EMA 50', 'vs EMA 50', 'close ÷ EMA 50 − 1', 'Technical', 'pct', 'price', True,
     'Feature 04 close / ema_50 - 1'),
    ('ema200', 'Price vs EMA 200', 'vs EMA 200', 'close ÷ EMA 200 − 1', 'Technical', 'pct', 'price', True,
     'Feature 04 close / ema_200 - 1'),
    ('r5d', 'Return 5D', 'Return 5D', '5 sessions', 'Price & volume', 'pct', 'price', True, 'Feature 01 return_5d_pct'),
    ('r3m', 'Return 3M', 'Return 3M', '60 sessions', 'Price & volume', 'pct', 'price', True, 'Feature 01 return_60d_pct'),
    ('volr', 'Volume vs 20D average', 'Volume', 'today ÷ 20-session average', 'Price & volume', 'ratio', 'price', False,
     'Feature 01 volume_ratio_20d'),
    ('vol20', 'Volatility 20D', 'Volatility', 'annualized', 'Price & volume', 'pct', 'price', False,
     'Feature 01 volatility_20d_ann_pct'),
    ('dd60', 'From 60D high', 'From 60D high', 'close vs highest close of 60 sessions', 'Price & volume', 'pct', 'price',
     False, 'Feature 01 drawdown_60d_pct'),
    ('fn1', 'Foreign net 1D', 'Foreign 1D', 'Regular board · Rp', 'Foreign flow', 'rp', 'broker', True,
     'Feature 06 foreign_net_1d'),
    ('fn5', 'Foreign net 5D', 'Foreign 5D', 'Regular board · Rp', 'Foreign flow', 'rp', 'broker', True,
     'Feature 06 foreign_net_5d'),
    ('fn20', 'Foreign net 20D', 'Foreign 20D', 'Regular board · Rp', 'Foreign flow', 'rp', 'broker', True,
     'Feature 06 foreign_net_20d'),
    ('fp5', 'Foreign net 5D rank', 'Foreign rank', 'vs own 252 sessions (stored)', 'Foreign flow', 'rank', 'broker', False,
     'Feature 06 foreign_net_percentile_5d_base252d'),
)
KEYS = tuple(c[0] for c in CATALOG)

PROBE_SQL = (f"SELECT to_regclass('{RADAR}') IS NOT NULL AND to_regclass('{ACTION}') IS NOT NULL "
             f"AND to_regclass('{RADAR_FILTER}') IS NOT NULL")
MARKET_SQL = f"SELECT ticker FROM {ENTITY} WHERE entity_kind = 'MARKET'"
# the price date: the newest date that has the market's final close and Feature 01 and Feature 04 rows (a run before the
# feature workers finished shows the previous complete date, never a mix)
PRICE_DATE_SQL = (f"SELECT p.date::text FROM {PRICE} AS p WHERE p.ticker = %(m)s AND p.timeframe = 'Daily' AND p.is_final "
                  f"AND EXISTS (SELECT 1 FROM {F01} AS f WHERE f.date = p.date) "
                  f"AND EXISTS (SELECT 1 FROM {F04} AS t WHERE t.trade_date = p.date AND t.timeframe = 'Daily' "
                  f"AND t.asset_type = 'equity') ORDER BY p.date DESC LIMIT 1")
BROKER_DATE_SQL = f"SELECT max(trade_date)::text FROM {F06I} WHERE ticker = %(m)s AND market_board = 'Regular'"
RADAR_DATE_SQL = f'SELECT max(trade_date)::text FROM {RADAR}'
EVENTS_LOADED_SQL = f'SELECT max(last_seen_at)::date::text FROM {ACTION}'
DATES_SQL = (f"SELECT date::text FROM {PRICE} WHERE ticker = %(m)s AND timeframe = 'Daily' AND is_final AND date <= %(p)s "
             'ORDER BY date DESC LIMIT %(n)s')
STOCKS_SQL = f'SELECT "Ticker", "Company Name", "Sector" FROM {UNIVERSE} WHERE "Security Type" = \'stock\' ORDER BY 1'
F01_SQL = (f'SELECT ticker, close::float8, return_1d_pct::float8, return_20d_pct::float8, return_5d_pct::float8, '
           f'return_60d_pct::float8, volume_ratio_20d::float8, volatility_20d_ann_pct::float8, drawdown_60d_pct::float8 '
           f'FROM {F01} WHERE date = %(p)s AND ticker IN {STOCK_SET}')
F04_SQL = (f'SELECT ticker, rsi_14::float8, macd_histogram::float8, adx_14::float8, '
           f'CASE WHEN ema_50 > 0 THEN (close / ema_50 - 1) * 100 END::float8, '
           f'CASE WHEN ema_200 > 0 THEN (close / ema_200 - 1) * 100 END::float8 '
           f"FROM {F04} WHERE trade_date = %(p)s AND timeframe = 'Daily' AND asset_type = 'equity' AND ticker IN {STOCK_SET}")
F06_SQL = (f'SELECT ticker, foreign_net_1d::float8, foreign_net_5d::float8, foreign_net_20d::float8, '
           f'foreign_net_percentile_5d_base252d::float8 FROM {F06} '
           f"WHERE trade_date = %(b)s AND market_board = 'Regular' AND ticker IN {STOCK_SET}")
CLOSES_SQL = (f"SELECT ticker, date::text, close::float8 FROM {PRICE} WHERE date = ANY(%(d)s::date[]) AND timeframe = 'Daily' "
              f'AND is_final AND ticker IN {STOCK_SET}')
EVENTS_SQL = (f'SELECT DISTINCT ticker, action_type, annotation_date::text, coalesce(annotation_date_role, \'\') FROM {ACTION} '
              f'WHERE source_removed_at IS NULL AND annotation_date > %(p)s::date AND annotation_date <= %(p)s::date + %(days)s '
              f'AND ticker IN {STOCK_SET} ORDER BY 3, 1, 2, 4')
# the Radar's board columns: one per column id, read at its default variant (S6Δ: Ratio), with the board's label
RADAR_FILTERS_SQL = (f'SELECT f.filter_id, f.column_label, f.name, f.position FROM {RADAR_FILTER} AS f '
                     f'WHERE f.is_default_variant AND f.rule_version = (SELECT max(rule_version) FROM {RADAR_FILTER}) '
                     'ORDER BY f.position')
RADAR_SQL = (f"SELECT DISTINCT ticker, filter_id FROM {RADAR} WHERE trade_date = %(r)s AND status = 'hit' "
             'AND level = %(level)s AND gate = %(gate)s')

CODE = hashlib.md5(Path(__file__).read_bytes()).hexdigest()
MAINTAINED_BY = ('daily', 'backfill', 'watchlist')    # the modes that rebuild the file when its stamp changed
UNAVAILABLE = 'Feature_07_Radar_Result, Feature_07_Radar_Filter or stockbit_corporate_action missing'


def available(conn):
    return bool(conn.execute(PROBE_SQL).fetchone()[0])


def busy(conn):
    """A reason not to publish now, or None (none: every read is one date)."""
    return None


def num(v, digits):
    return None if v is None else round(float(v), digits)


def build(run):
    """The file's document from run(sql, params) -> rows, or None when there is no market or no complete price date."""
    m = (run(MARKET_SQL, {}) or [[None]])[0][0]
    if not m:
        return None
    p = (run(PRICE_DATE_SQL, {'m': m}) or [[None]])[0][0]
    if not p:
        return None
    b = (run(BROKER_DATE_SQL, {'m': m}) or [[None]])[0][0]
    r = (run(RADAR_DATE_SQL, {}) or [[None]])[0][0]
    loaded = (run(EVENTS_LOADED_SQL, {}) or [[None]])[0][0]
    dates = sorted(x[0] for x in run(DATES_SQL, {'m': m, 'p': p, 'n': TREND_SESSIONS}))
    stocks = run(STOCKS_SQL, {})
    tickers = [t for t, _, _ in stocks]
    at = {t: i for i, t in enumerate(tickers)}
    n = len(tickers)
    vals = {k: [None] * n for k in KEYS}
    last, r1d, r1m = [None] * n, [None] * n, [None] * n
    for t, close, d1, d20, d5, d60, volr, vol20, dd60 in run(F01_SQL, {'p': p}):
        i = at[t]
        last[i], r1d[i], r1m[i] = num(close, 2), num(d1, 4), num(d20, 4)
        vals['r5d'][i], vals['r3m'][i], vals['volr'][i] = num(d5, 4), num(d60, 4), num(volr, 4)
        vals['vol20'][i], vals['dd60'][i] = num(vol20, 4), num(dd60, 4)
    for t, rsi, macdh, adx, e50, e200 in run(F04_SQL, {'p': p}):
        i = at[t]
        vals['rsi'][i], vals['macdh'][i], vals['adx'][i] = num(rsi, 4), num(macdh, 4), num(adx, 4)
        vals['ema50'][i], vals['ema200'][i] = num(e50, 4), num(e200, 4)
    if b:
        for t, f1, f5, f20, fp5 in run(F06_SQL, {'b': b}):
            i = at[t]
            vals['fn1'][i], vals['fn5'][i], vals['fn20'][i], vals['fp5'][i] = num(f1, 0), num(f5, 0), num(f20, 0), num(fp5, 2)
    trend = [[None] * len(dates) for _ in range(n)]
    di = {d: j for j, d in enumerate(dates)}
    for t, d, c in run(CLOSES_SQL, {'d': dates}):
        trend[at[t]][di[d]] = num(c, 2)
    events = {}
    for t, kind, d, role in run(EVENTS_SQL, {'p': p, 'days': EVENT_DAYS}):
        events.setdefault(t, []).append([kind, d, role])
    filters = run(RADAR_FILTERS_SQL, {})
    label = {f: lab for f, lab, _, _ in filters}
    radar = {}
    if r:
        for t, f in sorted(run(RADAR_SQL, {'r': r, 'level': RADAR_LEVEL, 'gate': RADAR_GATE})):
            if f in label:
                radar.setdefault(t, []).append(f)
        order = {f: pos for f, _, _, pos in filters}
        radar = {t: [label[f] for f in sorted(fs, key=order.get)] for t, fs in sorted(radar.items())}
    return {
        'schema': SCHEMA, 'prices_through': p, 'broker_through': b, 'radar_date': r, 'events_loaded': loaded,
        'event_days': EVENT_DAYS, 'radar_board': {'level': RADAR_LEVEL, 'gate': RADAR_GATE},
        'dates': dates,
        'catalog': [{'key': k, 'name': nm, 'short': sh, 'note': note, 'family': fam, 'unit': unit, 'date': dk, 'signed': sg}
                    for k, nm, sh, note, fam, unit, dk, sg, _ in CATALOG],
        'default': list(DEFAULT_INDICATORS),
        'radar_filters': [{'label': lab, 'name': nm} for _, lab, nm, _ in filters],
        'ticker': tickers, 'name': [nm for _, nm, _ in stocks], 'sector': [sec for _, _, sec in stocks],
        'last': last, 'r1d': r1d, 'r1m': r1m, 'trend': trend, 'values': vals,
        'events': dict(sorted(events.items())), 'radar': radar,
    }


def digest(doc):
    return hashlib.md5(json.dumps(doc, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def stamp(conn):
    """The stamp of the publication: the file's own content (a run is cheap, so the stamp is exact rather than a proxy of
    its inputs, ERRORS M442's lesson) and this module's code. A run whose stamp equals state.json `watchlist_stamp`
    carries the index forward."""
    doc = build(lambda sql, params: conn.execute(sql, params).fetchall())
    return [None if doc is None else digest(doc), CODE]


def files(conn, names, lists, stream=None, carry=None, previous=None, present=None, read=None):
    """(files [(name, document, rows, as_of)], kept names, carry). names, lists, carry, previous, present and read are the
    family interface's; this file needs none of them (one date, nothing carried)."""
    run = stream or (lambda sql, params: conn.execute(sql, params).fetchall())
    doc = build(run)
    if doc is None:
        return [], [], {'code': CODE}
    return [('watchlist-stocks', doc, len(doc['ticker']), doc['prices_through'])], [], {'code': CODE}
