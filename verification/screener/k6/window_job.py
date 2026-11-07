"""K6 (EXEC-SCREENER-FLOW-CANDLES P0; user 2026-11-07 "K6 boleh"): one read-only measurement of Feature 05 for the
screener's broker window (K1: 60 sessions). Nothing is written.

params.json:
  sessions   how many of the latest Feature 05 trade dates the window holds (K1: 60)
  sizes      window lengths whose file size is measured (e.g. [20, 41, 60]; 41 is the old Phase 2 design)
  months     true: buy_freq/sell_freq coverage over the whole history, one statement per calendar month
  statement_timeout_ms, work_mem

Parts (one OUT line per part, short lines: ERRORS R08):
  (a) per session of the window: rows, tickers, NULL buy_freq/sell_freq, split by the current universe (stock kind:
      every security whose "Security Type" is not index, publisher.data_kind) and by four-letter codes; the date's
      broker_summary_date_quality status; the read time.
  (b) the size of one cross-ticker window file encoded as publisher.py encodes a broker file (columnar JSON with
      separators (',', ':'), gzip level 9; columns t + BROKER_COLUMNS, rows ordered by ticker, date, broker, investor
      type, board), for each length in `sizes`, universe rows only, and once for every Feature 05 code. The JSON is
      streamed into the compressor column by column, so the job never holds the text; values are written with
      json's own encoders, so the bytes equal json.dumps of the same document (checked on the first ticker: OUT
      encode_check).
  (c) whole-history coverage per month (months=true): rows and rows without buy_freq or sell_freq, all codes,
      four-letter codes and current-universe codes; the dates whose universe rows lack a frequency.
  (d) broker_summary_date_quality over the whole history: dates per status, stock_freq_share below 1.

Run with scripts/onboarding/run_job.sh (read-only session: default_transaction_read_only=on, printed as READONLY).
"""
import json
import os
import re
import time
import zlib
from array import array
from datetime import date

import psycopg

P = json.load(open('params.json'))
SESSIONS = int(P.get('sessions', 60))
SIZES = sorted({int(n) for n in P.get('sizes', [SESSIONS]) if 0 < int(n) <= SESSIONS})
F05 = 'public."Feature_05_Foreign_Domestic_Broker_Detail"'
# publisher.py BROKER_COLUMNS with the ticker in front: one cross-ticker file instead of one file per ticker
COLUMNS = ['t', 'd', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf']
FOUR = re.compile(r'^[A-Z]{4}$')
ENC_STR = json.encoder.encode_basestring_ascii        # json.dumps(ensure_ascii=True) writes strings with this
ENC_FLOAT = float.__repr__                            # json's floatstr for a finite float (allow_nan=False)


def out(part, **fields):
    print('OUT ' + json.dumps({'part': part, **fields}, default=str, separators=(',', ':')), flush=True)


def err(part, e):
    print('ERR ' + json.dumps({'part': part, 'error': f'{type(e).__name__}: {str(e)[:300]}'}), flush=True)


def fnum(v):
    return 'null' if v is None else (ENC_FLOAT(v) if isinstance(v, float) else str(int(v)))


conn = psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, connect_timeout=30,
                       options=(f"-c default_transaction_read_only=on "
                                f"-c statement_timeout={int(P.get('statement_timeout_ms', 600000))} "
                                f"-c work_mem={P.get('work_mem', '64MB')} -c max_parallel_workers_per_gather=0 "
                                f"-c application_name=k6_window_job"))
print('READONLY ' + json.dumps(conn.execute('SHOW transaction_read_only').fetchone()), flush=True)
t_job = time.time()

# ---- the universe as the publisher reads it (UNIVERSE_SQL); stock kind = every type except index ----------------------
universe = conn.execute('SELECT "Ticker", "Security Type" FROM public."IDX_Stock_Universe"').fetchall()
U = {t for t, typ in universe if typ != 'index'}
types = {}
for _, typ in universe:
    types[typ] = types.get(typ, 0) + 1
out('universe', securities=len(universe), stock_kind=len(U), by_type=types)

# ---- (a) the latest trade dates of Feature 05, from its trade_date index (one index probe per date) -------------------
dates = [r[0] for r in conn.execute(
    f'WITH RECURSIVE d(t) AS (SELECT max(trade_date) FROM {F05} '
    f'UNION ALL SELECT (SELECT max(trade_date) FROM {F05} WHERE trade_date < d.t) FROM d WHERE d.t IS NOT NULL) '
    f'SELECT t FROM d WHERE t IS NOT NULL LIMIT %s', (SESSIONS,)).fetchall()]
dates.sort()
quality = dict(conn.execute('SELECT trade_date, status FROM public.broker_summary_date_quality '
                            'WHERE trade_date = ANY(%s)', (dates,)).fetchall())
out('window', sessions=len(dates), first=dates[0] if dates else None, last=dates[-1] if dates else None)

# compact column store of the window rows (about 60 bytes a row): codes as vocabulary ids, numbers in typed arrays
vocab, ids = [], {}


def vid(s):
    i = ids.get(s)
    if i is None:
        i = ids[s] = len(vocab)
        vocab.append(s)
    return i


col_t, col_d, col_b, col_i, col_m = array('I'), array('H'), array('I'), array('I'), array('I')
col_bv, col_sv, col_bl, col_sl = array('d'), array('d'), array('d'), array('d')
col_bf, col_sf = array('q'), array('q')               # -1 = NULL (Feature 05 CHECK: freq >= 0)
col_gap = array('B')
read_ms = 0
for di, day in enumerate(dates):
    t0 = time.time()
    try:
        rows = conn.execute(
            f'SELECT ticker, broker, investor_type, market_board, buy_value::float8, sell_value::float8, '
            f'buy_lots::float8, sell_lots::float8, source_balance_gap, buy_freq, sell_freq FROM {F05} '
            f'WHERE trade_date = %s', (day,)).fetchall()
    except Exception as e:  # noqa: BLE001 - one failed date must not hide the others
        err(f'session:{day}', e)
        continue
    ms = round((time.time() - t0) * 1000)
    read_ms += ms
    s = {'rows': len(rows), 'tickers': len({r[0] for r in rows}), 'null_bf': 0, 'null_sf': 0,
         'u_rows': 0, 'u_tickers': len({r[0] for r in rows if r[0] in U}), 'u_null_any': 0,
         'four_rows': 0, 'four_null_any': 0, 'other_rows': 0, 'other_null_any': 0}
    for (tk, br, it, mb, bv, sv, bl, sl, gap, bf, sf) in rows:
        nb, ns = bf is None, sf is None
        s['null_bf'] += nb
        s['null_sf'] += ns
        if tk in U:
            s['u_rows'] += 1
            s['u_null_any'] += nb or ns
        if FOUR.match(tk):
            s['four_rows'] += 1
            s['four_null_any'] += nb or ns
        else:
            s['other_rows'] += 1
            s['other_null_any'] += nb or ns
        col_t.append(vid(tk)); col_d.append(di); col_b.append(vid(br)); col_i.append(vid(it)); col_m.append(vid(mb))
        col_bv.append(bv); col_sv.append(sv); col_bl.append(bl); col_sl.append(sl)
        col_bf.append(-1 if nb else bf); col_sf.append(-1 if ns else sf); col_gap.append(1 if gap else 0)
    out('session', d=day, status=quality.get(day, 'NONE'), ms=ms, **s)
    del rows
out('window_read', rows=len(col_t), read_ms=read_ms, job_s=round(time.time() - t_job, 1))

# ---- (b) file size of the window, encoded as publisher.encode would ------------------------------------------------
DATE_STR = [ENC_STR(d.isoformat()) for d in dates]
VOCAB_STR = [ENC_STR(v) for v in vocab]
n_all = len(col_t)
# row order: ticker, date, broker, investor type, board (the publisher's per-ticker order with the ticker in front),
# as one integer key a row (a tuple key a row would cost about 150 bytes each)
rank = {v: r for r, v in enumerate(sorted(set(vocab)))}
vrank = array('I', [rank[v] for v in vocab])
V = len(vocab) + 1
order = sorted(range(n_all), key=lambda k: (((vrank[col_t[k]] * 64 + col_d[k]) * V + vrank[col_b[k]]) * V
                                            + vrank[col_i[k]]) * V + vrank[col_m[k]])


def header(n_sessions):
    head = {'schema_version': 1, 'dataset': 'broker_window', 'sessions': [d.isoformat() for d in dates[-n_sessions:]],
            'units': {'bv': 'IDR', 'sv': 'IDR', 'bl': 'lots (100 shares; odd lots as fractions)', 'sl': 'lots',
                      'bf': 'buy transactions', 'sf': 'sell transactions'},
            'investor_type': 'source investor identity (Foreign/Domestic), not broker domicile', 'columns': COLUMNS}
    return json.dumps(head, separators=(',', ':'), allow_nan=False)[:-1]      # without the closing brace


# one cell's JSON text per column, written as json.dumps writes the value (str, float repr, int, null)
CELL = {'t': lambda k: VOCAB_STR[col_t[k]], 'd': lambda k: DATE_STR[col_d[k]],
        'b': lambda k: VOCAB_STR[col_b[k]], 'i': lambda k: VOCAB_STR[col_i[k]], 'm': lambda k: VOCAB_STR[col_m[k]],
        'bv': lambda k: ENC_FLOAT(col_bv[k]), 'sv': lambda k: ENC_FLOAT(col_sv[k]),
        'bl': lambda k: ENC_FLOAT(col_bl[k]), 'sl': lambda k: ENC_FLOAT(col_sl[k]),
        'bf': lambda k: 'null' if col_bf[k] < 0 else str(col_bf[k]),
        'sf': lambda k: 'null' if col_sf[k] < 0 else str(col_sf[k])}


def gaps_of(rows):
    return [list(g) for g in sorted({(vocab[col_t[k]], dates[col_d[k]].isoformat(), vocab[col_m[k]])
                                     for k in rows if col_gap[k]})]


def stream(n_sessions, rows, put):
    put(header(n_sessions))
    for name in COLUMNS:
        f = CELL[name]
        put(f',"{name}":[')
        for i in range(0, len(rows), 50000):
            put((',' if i else '') + ','.join(map(f, rows[i:i + 50000])))
        put(']')
    put(',"gap":' + json.dumps(gaps_of(rows), separators=(',', ':')) + '}')


def encode_window(n_sessions, universe_only):
    first = len(dates) - n_sessions
    rows = [k for k in order if col_d[k] >= first and (not universe_only or vocab[col_t[k]] in U)]
    gz = zlib.compressobj(9, zlib.DEFLATED, 31)       # gzip container, level 9: publisher.encode compresslevel=9
    size = {'raw': 0, 'gz': 0}

    def put(text):
        b = text.encode()
        size['raw'] += len(b)
        size['gz'] += len(gz.compress(b))
    stream(n_sessions, rows, put)
    size['gz'] += len(gz.flush())
    return {'sessions': n_sessions, 'universe_only': universe_only, 'rows': len(rows),
            'tickers': len({col_t[k] for k in rows}), 'raw_bytes': size['raw'], 'gzip_bytes': size['gz'],
            'gzip_mb': round(size['gz'] / 1e6, 2), 'bytes_per_row': round(size['gz'] / max(len(rows), 1), 2)}


# the streamed text equals json.dumps of the same document, and its streamed gzip size equals gzip.compress of it
# (publisher.encode): checked on the first ticker's rows of the window
try:
    import gzip
    k0 = [k for k in order if col_t[k] == col_t[order[0]]] if order else []
    doc = json.loads(header(len(dates)) + '}')
    for name in COLUMNS:
        doc[name] = [json.loads(CELL[name](k)) for k in k0]
    doc['gap'] = gaps_of(k0)
    ref = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode()
    parts = []
    stream(len(dates), k0, parts.append)
    streamed = ''.join(parts).encode()
    gz = zlib.compressobj(9, zlib.DEFLATED, 31)
    chunked = sum(len(gz.compress(p.encode())) for p in parts) + len(gz.flush())
    out('encode_check', ticker=vocab[col_t[order[0]]] if order else None, rows=len(k0), same_text=ref == streamed,
        gzip_publisher=len(gzip.compress(ref, compresslevel=9, mtime=0)), gzip_streamed=chunked)
except Exception as e:  # noqa: BLE001
    err('encode_check', e)

for n in SIZES:
    try:
        t0 = time.time()
        out('file', **encode_window(n, True), encode_s=round(time.time() - t0, 1))
    except Exception as e:  # noqa: BLE001
        err(f'file:{n}', e)
try:
    t0 = time.time()
    out('file', **encode_window(len(dates), False), encode_s=round(time.time() - t0, 1))
except Exception as e:  # noqa: BLE001
    err('file:all', e)
del order, col_t, col_d, col_b, col_i, col_m, col_bv, col_sv, col_bl, col_sl, col_bf, col_sf, col_gap

# ---- (c) buy_freq/sell_freq over the whole history, one statement per calendar month ------------------------------
if P.get('months', True):
    lo, hi = conn.execute(f'SELECT min(trade_date), max(trade_date) FROM {F05}').fetchone()
    out('history', first=lo, last=hi)
    y, m = lo.year, lo.month
    total = {}
    null_dates = []
    while (y, m) <= (hi.year, hi.month):
        start, end = date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1)
        t0 = time.time()
        try:
            # per date: hash aggregate over the month's rows (trade_date index range); the universe is a hash join
            rows = conn.execute(
                f'SELECT f.trade_date, count(*), '
                f'count(*) FILTER (WHERE f.buy_freq IS NULL), count(*) FILTER (WHERE f.sell_freq IS NULL), '
                f"count(*) FILTER (WHERE f.ticker ~ '^[A-Z]{{4}}$'), "
                f"count(*) FILTER (WHERE f.ticker ~ '^[A-Z]{{4}}$' AND (f.buy_freq IS NULL OR f.sell_freq IS NULL)), "
                f'count(u.t), count(u.t) FILTER (WHERE f.buy_freq IS NULL OR f.sell_freq IS NULL) '
                f'FROM {F05} f LEFT JOIN unnest(%s::text[]) u(t) ON u.t = f.ticker '
                f'WHERE f.trade_date >= %s AND f.trade_date < %s GROUP BY f.trade_date ORDER BY 1',
                (sorted(U), start, end)).fetchall()
            keys = ['rows', 'null_bf', 'null_sf', 'four_rows', 'four_null_any', 'u_rows', 'u_null_any']
            month = {k: sum(r[i + 1] for r in rows) for i, k in enumerate(keys)}
            for k, v in month.items():
                total[k] = total.get(k, 0) + v
            null_dates += [f'{r[0].isoformat()}:{r[7]}/{r[6]}' for r in rows if r[7]]
            out('month', ym=f'{y}-{m:02d}', dates=len(rows), ms=round((time.time() - t0) * 1000), **month,
                u_dates_with_null=sum(1 for r in rows if r[7]))
        except Exception as e:  # noqa: BLE001
            err(f'month:{y}-{m:02d}', e)
        y, m = y + (m == 12), m % 12 + 1
    out('history_total', **total)
    for i in range(0, len(null_dates), 20):
        out('u_null_dates', chunk=i // 20, dates=null_dates[i:i + 20])

# ---- (d) the date-quality table over the whole history -------------------------------------------------------------
try:
    rows = conn.execute('SELECT status, count(*), min(trade_date), max(trade_date), '
                        'count(*) FILTER (WHERE stock_freq_share < 1), min(stock_freq_share) '
                        'FROM public.broker_summary_date_quality GROUP BY 1 ORDER BY 1').fetchall()
    for r in rows:
        out('date_quality', status=r[0], dates=r[1], first=r[2], last=r[3], freq_share_below_1=r[4],
            min_freq_share=float(r[5]) if r[5] is not None else None)
    low = conn.execute('SELECT trade_date, stock_freq_share::float8, status FROM public.broker_summary_date_quality '
                       'WHERE stock_freq_share < 0.99 ORDER BY 1').fetchall()
    for i in range(0, len(low), 20):
        out('date_quality_low', chunk=i // 20, dates=[f'{d.isoformat()}:{round(s, 4)}:{st}' for d, s, st in low[i:i + 20]])
except Exception as e:  # noqa: BLE001
    err('date_quality', e)

out('done', job_s=round(time.time() - t_job, 1))
print('JOB_DONE', flush=True)
