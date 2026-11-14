"""EXEC-RADAR R5 (user go 2026-11-14: "Ok go"): the Radar's files, built from the Feature 07 tables.

The Radar page (EDGE, owner only) reads gzip JSON files of the family `radar/`, content-keyed as the xsection files are
(`radar/<name>.<first 16 hex of sha256>.json.gz`) and indexed in state.json `radar` ({name: {key, sha256, bytes, rows,
as_of}}). terminal-api presigns them only for the EDGE gateway key (POST /radar); its /state never shows the index
(bucket.py STATE_FIELDS). verification/radar/FILES.md is the contract with the page.

  radar-meta              filters and rules of the active rule version (labels and thresholds; the admin page shows
                          them), every universe ticker's name, the stock lists with their current members
  radar-days              the result dates (RESULT_DATES newest, oldest first), the gate of each date, the number of hits
                          per date for every filter, level and gate, IHSG's close on each date, the dates with a board
  radar-board-YYYY-MM-DD  one result date (the BOARD_DATES newest): every hit, near and left row of every filter, level
                          and gate, the listed stocks' close, 1D change and 20-session price line, and their measures
  radar-f-<filter>        one filter over every result date: the hits (with their run of days) and the stocks that left
                          (with the condition), and each listed stock's close on every result date

The publisher computes no indicator (the rule results are Feature 07's); it only arranges rows. Every list is ordered
here, so equal tables give equal bytes.
"""
from __future__ import annotations

import datetime as dt
import re

SCHEMA = 1
RESULT_DATES = 250          # D4 (user 2026-11-14 "D4 ok"): 250 result sessions, a date picker of 20
BOARD_DATES = 20
SPARK = 20                  # the card's price line: 20 price sessions ending on the result date
LEVELS = ('loose', 'standard', 'strict')
GATES = ('broad', 'liquid')
NAME = re.compile(r'radar-(?:meta|days|board-\d{4}-\d{2}-\d{2}|f-[a-z0-9_]{1,24})')
M = 'public."Feature_07_Radar_Measure"'
G = 'public."Feature_07_Radar_Gate"'
F = 'public."Feature_07_Radar_Filter"'
R = 'public."Feature_07_Radar_Rule"'
RES = 'public."Feature_07_Radar_Result"'
PRICE = 'public."Price_Stock_Indonesia_IDX"'
INDEX_TICKER = 'IHSG'

PROBE_SQL = "SELECT to_regclass('public.\"Feature_07_Radar_Result\"') IS NOT NULL"
# a first fill (verification/radar/backfill_job.py) holds this lock while it writes: no publication of half-filled tables
BACKFILL_LOCK = 'feature_07_radar_backfill'
BACKFILL_FREE_SQL = 'SELECT pg_try_advisory_lock(hashtext(%s))'
BACKFILL_RELEASE_SQL = 'SELECT pg_advisory_unlock(hashtext(%s))'
# the publication is rebuilt when a result date was (re)computed (every refresh_feature_07_day rewrites its gate row) or
# a newer final price date arrived (the card's price line and the page's price pill)
# QA 2026-11-14: plus the final daily closes from the newest result date on (a close that arrives after IHSG's is a
# change of the board's price line) and the stock lists' membership (the universe menu of radar-meta). Older price
# corrections are not watched: the manual mode `radar` republishes after one.
STAMP_SQL = (f'SELECT (SELECT max(calculated_at)::text FROM {G}), (SELECT count(*) FROM {G}), '
             f"(SELECT max(date)::text FROM {PRICE} WHERE ticker = '{INDEX_TICKER}' AND timeframe = 'Daily' AND is_final), "
             'public.feature_07_rule_version(), '
             f"(SELECT count(*) FROM {PRICE} WHERE timeframe = 'Daily' AND is_final AND date >= (SELECT max(trade_date) FROM {G})), "
             '(SELECT md5(coalesce(string_agg(list_key || \':\' || "Ticker", \',\' ORDER BY list_key, "Ticker"), \'\')) '
             'FROM public."Stock_List_Member")')
GATES_SQL = (f'SELECT trade_date::text, universe_n, broad_cut::float8, liquid_cut::float8, broad_n, liquid_n FROM {G} '
             'ORDER BY trade_date DESC LIMIT %s')
FILTERS_SQL = ('SELECT filter_id, position, column_id, column_label, variant_label, is_default_variant, name, question, '
               f'warning, sort_label, own_levels FROM {F} WHERE rule_version = public.feature_07_rule_version() '
               'ORDER BY position')
RULES_SQL = ('SELECT filter_id, cond_key, level, label, threshold, threshold2, status '
             f'FROM {R} WHERE rule_version = public.feature_07_rule_version() ORDER BY filter_id, level, cond_key')
VERSION = 'rule_version = public.feature_07_rule_version()'
COUNTS_SQL = (f"SELECT trade_date::text, filter_id, level, gate, count(*) FROM {RES} WHERE status = 'hit' "
              f'AND trade_date >= %s AND {VERSION} GROUP BY 1, 2, 3, 4')
HISTORY_SQL = ('SELECT trade_date::text, filter_id, level, gate, ticker, status, run_day, left_reason '
               f"FROM {RES} WHERE status IN ('hit', 'left') AND trade_date >= %s AND {VERSION}")
BOARD_SQL = ('SELECT trade_date::text, filter_id, level, gate, ticker, status, met, cond_n, run_day, left_reason, strong, '
             f'sort_value, flag FROM {RES} WHERE trade_date = ANY(%s::date[]) AND {VERSION}')
# the measures the Candidates table and the cards show (RADAR_PAGE_SPEC.md section 5, own columns)
MEASURES = ('foreign_net_5d', 'total_buy_5d', 'foreign_ratio_5d', 'buy_days_5d', 'foreign_net_5d_pct252',
            'foreign_net_5d_z252', 'foreign_ratio_5d_pct252', 'foreign_ratio_5d_prev', 'foreign_ratio_5d_change',
            'foreign_ratio_5d_pct252_prev', 'foreign_ratio_5d_pct252_change', 'inst_net_5d', 'retail_net_5d', 'fl34_5d',
            'fl34_5d_prev', 'inst_share_5d', 'foreign_net_1d', 'adv20_prev', 'foreign_ratio_1d', 'net_vs_adv20',
            'rz_foreign_ratio_1d', 'rz_net_vs_adv20', 'net_1d_pct252', 's2_rank_broad', 's2_rank_liquid',
            's3_net_buyers', 's3_cr3', 's3_cr3_excess', 's3_intensity', 's3_group_broad', 's3_group_rank_broad',
            's3_intensity_rank_broad', 's3_group_liquid', 's3_group_rank_liquid', 's3_intensity_rank_liquid')
MEASURE_SQL = ('SELECT trade_date::text, ticker, ' + ', '.join(f'{c}::float8' for c in MEASURES) +
               f' FROM {M} WHERE trade_date = ANY(%s::date[]) AND ticker = ANY(%s)')
PRICES_SQL = (f"SELECT ticker, date::text, close::float8 FROM {PRICE} WHERE timeframe = 'Daily' AND is_final "
              'AND date BETWEEN %s AND %s AND ticker = ANY(%s)')


def available(conn):
    return bool(conn.execute(PROBE_SQL).fetchone()[0])


def backfill_running(conn):
    """True while the first fill holds its lock (the lock is taken and given back at once otherwise)."""
    if not conn.execute(BACKFILL_FREE_SQL, (BACKFILL_LOCK,)).fetchone()[0]:
        return True
    conn.execute(BACKFILL_RELEASE_SQL, (BACKFILL_LOCK,))
    return False


def stamp(conn):
    """What the publication of the Radar depends on: [gate max calculated_at, gate rows, newest IHSG price date, rule
    version]. A run whose stamp equals state.json `radar_stamp` carries the index forward."""
    return [None if v is None else str(v) for v in conn.execute(STAMP_SQL).fetchone()]


def num(v, digits=6):
    """A float for JSON: None stays None; NaN and infinities are None (encode refuses them)."""
    if v is None:
        return None
    v = float(v)
    if v != v or v in (float('inf'), float('-inf')):
        return None
    return round(v, digits)


def meta_doc(filters, rules, names, lists):
    """filters: FILTERS_SQL rows; rules: RULES_SQL rows; names: {ticker: name}; lists: [(key, kind, code, name,
    members)]."""
    return {
        'schema': SCHEMA, 'levels': list(LEVELS), 'gates': list(GATES),
        'filters': [{'id': r[0], 'position': r[1], 'column': r[2], 'column_label': r[3], 'variant': r[4],
                     'default_variant': bool(r[5]), 'name': r[6], 'question': r[7], 'warning': r[8], 'sort_label': r[9],
                     'own_levels': bool(r[10])} for r in filters],
        'rules': [{'filter': r[0], 'cond': r[1], 'level': r[2], 'label': r[3], 'threshold': num(r[4]),
                   'threshold2': num(r[5]), 'status': r[6]} for r in rules],
        'names': {t: names[t] for t in sorted(names)},
        'lists': [{'key': k, 'kind': kind, 'code': code, 'name': n, 'members': sorted(members or [])}
                  for k, kind, code, n, members in lists],
    }


def setting(level, gate):
    return f'{level}/{gate}'


def days_doc(gates, counts, filter_ids, levels_of, ihsg, prices_through, boards):
    """gates: GATES_SQL rows, oldest first; counts: COUNTS_SQL rows; levels_of: {filter: levels it has};
    ihsg: {date: close}."""
    dates = [g[0] for g in gates]
    at = {d: i for i, d in enumerate(dates)}
    out = {f: {setting(lv, g): [0] * len(dates) for lv in levels_of[f] for g in GATES} for f in filter_ids}
    for d, f, lv, g, n in counts:
        if d in at and f in out and setting(lv, g) in out[f]:
            out[f][setting(lv, g)][at[d]] = int(n)
    return {
        'schema': SCHEMA, 'dates': dates,
        'gate': {'universe_n': [g[1] for g in gates], 'broad_cut': [num(g[2], 0) for g in gates],
                 'liquid_cut': [num(g[3], 0) for g in gates], 'broad_n': [g[4] for g in gates],
                 'liquid_n': [g[5] for g in gates]},
        'counts': out, 'ihsg': [num(ihsg.get(d), 2) for d in dates],
        'broker_through': dates[-1] if dates else None, 'prices_through': prices_through, 'boards': boards,
    }


def price_line(series, date, n=SPARK):
    """The last n closes up to and including `date` of a sorted [(date, close)] list, the close on `date` (None when it
    has no final price that day) and the 1D change in percent against the price session before."""
    upto = [(d, c) for d, c in series if d <= date]
    line = [c for _, c in upto[-n:]]
    last = upto[-1][1] if upto and upto[-1][0] == date else None
    chg = 100.0 * (upto[-1][1] / upto[-2][1] - 1) if last is not None and len(upto) >= 2 and upto[-2][1] else None
    return line, last, chg


def board_doc(date, rows, measures, prices):
    """One result date. rows: BOARD_SQL rows of the date; measures: {ticker: MEASURE_SQL row}; prices: {ticker:
    sorted [(date, close)]}."""
    rows = sorted(rows, key=lambda r: (r[1], r[3], r[2], r[5], r[4]))
    tickers = sorted({r[4] for r in rows})
    at = {t: i for i, t in enumerate(tickers)}
    lines = [price_line(prices.get(t, []), date) for t in tickers]
    return {
        'schema': SCHEMA, 'date': date,
        'stocks': {'ticker': tickers, 'close': [num(x[1], 2) for x in lines], 'chg_1d': [num(x[2], 4) for x in lines],
                   'spark': [[num(c, 2) for c in x[0]] for x in lines]},
        'rows': {'filter': [r[1] for r in rows], 'stock': [at[r[4]] for r in rows], 'level': [r[2] for r in rows],
                 'gate': [r[3] for r in rows], 'status': [r[5] for r in rows], 'met': [r[6] for r in rows],
                 'cond_n': [r[7] for r in rows], 'run_day': [r[8] for r in rows], 'left_reason': [r[9] for r in rows],
                 'strong': [r[10] for r in rows], 'sort_value': [num(r[11]) for r in rows], 'flag': [r[12] for r in rows]},
        'measures': {'columns': list(MEASURES),
                     'values': [[num(v) for v in measures[t][2:]] if t in measures else None for t in tickers]},
    }


def filter_doc(fid, dates, history, prices):
    """One filter over every result date. history: HISTORY_SQL rows of the filter; prices: {ticker: sorted [(date,
    close)]}; each listed stock's close on every result date (None where it has no final price)."""
    at = {d: i for i, d in enumerate(dates)}
    rows = sorted((r for r in history if r[0] in at), key=lambda r: (r[0], r[3], r[2], r[5], r[4]))
    tickers = sorted({r[4] for r in rows})
    st = {t: i for i, t in enumerate(tickers)}
    hits = [r for r in rows if r[5] == 'hit']
    left = [r for r in rows if r[5] == 'left']
    closes = []
    for t in tickers:
        by = dict(prices.get(t, []))
        closes.append([num(by.get(d), 2) for d in dates])
    return {
        'schema': SCHEMA, 'filter': fid, 'dates': dates,
        'stocks': {'ticker': tickers, 'close': closes},
        'hits': {'date': [at[r[0]] for r in hits], 'stock': [st[r[4]] for r in hits], 'level': [r[2] for r in hits],
                 'gate': [r[3] for r in hits], 'run_day': [r[6] for r in hits]},
        'left': {'date': [at[r[0]] for r in left], 'stock': [st[r[4]] for r in left], 'level': [r[2] for r in left],
                 'gate': [r[3] for r in left], 'left_reason': [r[7] for r in left]},
    }


def filter_name(fid):
    return f'radar-f-{fid.lower()}'


def build(conn, names, lists, stream=None):
    """Every Radar file -> [(name, doc, rows, as_of)], from the Feature 07 tables and the final daily prices.
    names: {ticker: company name} of the universe; lists: [(key, kind, code, name, members)]."""
    stream = stream or (lambda sql, params: conn.execute(sql, params).fetchall())
    gates = list(reversed(conn.execute(GATES_SQL, (RESULT_DATES,)).fetchall()))
    if not gates:
        return []
    dates = [g[0] for g in gates]
    first, newest = dates[0], dates[-1]
    filters = conn.execute(FILTERS_SQL).fetchall()
    rules = conn.execute(RULES_SQL).fetchall()
    ids = [f[0] for f in filters]
    levels_of = {f: [lv for lv in LEVELS if any(r[0] == f and r[2] == lv for r in rules)] for f in ids}
    counts = conn.execute(COUNTS_SQL, (first,)).fetchall()
    history = stream(HISTORY_SQL, (first,))
    boards = dates[-BOARD_DATES:]
    board_rows = stream(BOARD_SQL, (boards,))
    listed = sorted({r[4] for r in board_rows} | {r[4] for r in history})
    # prices from SPARK price sessions before the oldest result date (calendar margin: 2 x SPARK + 10 days)
    lo = (dt.date.fromisoformat(first) - dt.timedelta(days=2 * SPARK + 10)).isoformat()
    hi_row = conn.execute(f"SELECT max(date)::text FROM {PRICE} WHERE ticker = %s AND timeframe = 'Daily' AND is_final",
                          (INDEX_TICKER,)).fetchone()
    prices_through = hi_row[0] if hi_row else None
    prices = {}
    for t, d, c in stream(PRICES_SQL, (lo, prices_through or newest, [*listed, INDEX_TICKER])):
        prices.setdefault(t, []).append((d, c))
    for t in prices:
        prices[t].sort()
    ihsg = dict(prices.get(INDEX_TICKER, []))
    measures = {}
    for r in stream(MEASURE_SQL, (boards, sorted({r[4] for r in board_rows}))):
        measures.setdefault(r[0], {})[r[1]] = r
    out = [('radar-meta', meta_doc(filters, rules, names, lists), len(filters) + len(rules), newest),
           ('radar-days', days_doc(gates, counts, ids, levels_of, ihsg, prices_through, boards), len(dates), newest)]
    by_date = {}
    for r in board_rows:
        by_date.setdefault(r[0], []).append(r)
    for d in boards:
        doc = board_doc(d, by_date.get(d, []), measures.get(d, {}), prices)
        out.append((f'radar-board-{d}', doc, len(doc['rows']['filter']), d))
    by_filter = {}
    for r in history:
        by_filter.setdefault(r[1], []).append(r)
    for f in ids:
        doc = filter_doc(f, dates, by_filter.get(f, []), prices)
        out.append((filter_name(f), doc, len(doc['hits']['date']) + len(doc['left']['date']), newest))
    return out
