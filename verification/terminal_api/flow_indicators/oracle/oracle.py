#!/usr/bin/env python3
"""Independent reference implementation ("oracle") of the broker-flow indicators FL01-FL39.

Written only from verification/terminal_api/flow_indicators/FORMULAS.md and the parameter registry
(apps/edge-bff/terminal/src/data/flowRegistry.json); no TypeScript/JavaScript implementation was read.

Arithmetic is exact: broker values (IDR) and shares (lots x 100) are integers in the source, every
indicator value is kept as an int or Fraction and is converted to a float (correctly rounded) only when
written. Percentile ties are therefore exact ties.

Usage (from anywhere):  python3 oracle.py [--refresh] [TICKER ...]
Reads   cases.json (next to this file)
Caches  cache/<TICKER>.json.gz, cache/broker_profile.json   (raw rows as fetched through pgweb)
Writes  out/<TICKER>.json
"""
import argparse
import gzip
import heapq
import json
import os
import sys
import time
from decimal import Decimal
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))  # verification/terminal_api (pgq)
import pgq  # noqa: E402

CACHE_DIR = os.path.join(HERE, 'cache')
OUT_DIR = os.path.join(HERE, 'out')
REGISTRY = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', 'apps', 'edge-bff', 'terminal', 'src',
                                        'data', 'flowRegistry.json'))
BOARD_MAP = {'Regular': 'Regular', 'Nego': 'Nego', 'Tunai': 'Cash', 'Cash': 'Cash'}
ALL_BOARDS = ('Regular', 'Nego', 'Cash')
ALL_INV = ('Foreign', 'Domestic')

# Aggregate vector: buy value, sell value, buy shares, sell shares, buy freq, sell freq,
# rows with null buy freq, rows with null sell freq, row count.
BV, SV, BS, SS, BF, SF, BFN, SFN, NR = range(9)
ZERO = (0,) * 9


# ----------------------------------------------------------------------------------------------- data
def query(sql):
    last = None
    for attempt in range(4):
        r = pgq.q(sql)
        if 'error' not in r:
            return r['rows']
        last = r['error']
        time.sleep(2 + 3 * attempt)
    raise RuntimeError('query failed: ' + str(last)[:400])


def fetch_profile(refresh):
    path = os.path.join(CACHE_DIR, 'broker_profile.json')
    if os.path.exists(path) and not refresh:
        return json.load(open(path))
    rows = query('select broker_code, broker_classification from "IDX_Broker_Profile" order by broker_code')
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump(rows, open(path, 'w'))
    return rows


def fetch_ticker(tk, cfg, refresh):
    path = os.path.join(CACHE_DIR, f'{tk}.json.gz')
    meta = {'ticker': tk, 'price_through': cfg['price_through'], 'broker_through': cfg['broker_through']}
    if os.path.exists(path) and not refresh:
        with gzip.open(path, 'rt') as fh:
            d = json.load(fh)
        if d.get('meta') == meta:
            return d
    bt, pt = cfg['broker_through'], cfg['price_through']
    f05 = '"Feature_05_Foreign_Domestic_Broker_Detail"'
    first, count = query(f"select min(trade_date)::text, count(*) from {f05} "
                         f"where ticker = '{tk}' and trade_date <= '{bt}'")[0]
    broker = []
    for y in range(int(first[:4]), int(bt[:4]) + 1):
        broker.extend(query(
            f"select trade_date::text, broker, investor_type, market_board, buy_value::text, sell_value::text, "
            f"buy_lots::text, sell_lots::text, buy_freq, sell_freq from {f05} "
            f"where ticker = '{tk}' and trade_date >= '{y}-01-01' and trade_date < '{y + 1}-01-01' "
            f"and trade_date <= '{bt}' order by trade_date, broker, investor_type, market_board"))
    if len(broker) != int(count):
        raise RuntimeError(f'{tk}: fetched {len(broker)} broker rows, table has {count}')
    price = query(
        f"select date::text, close::text, volume::text from \"Price_Stock_Indonesia_IDX\" "
        f"where ticker = '{tk}' and timeframe = 'Daily' and is_final and date <= '{pt}' order by date")
    insider = query(
        f"select annotation_date::text, action, value_idr::text, event_key from public.idx_event_annotation "
        f"where event_family = 'INSIDER' and ticker = '{tk}' order by annotation_date, event_key")
    d = {'meta': meta, 'broker': broker, 'price': price, 'insider': insider}
    os.makedirs(CACHE_DIR, exist_ok=True)
    with gzip.open(path, 'wt') as fh:
        json.dump(d, fh, separators=(',', ':'))
    return d


def num(text):
    """Exact number from a numeric text: int when integral, else Fraction."""
    d = Decimal(text)
    return int(d) if d == d.to_integral_value() else Fraction(d)


def shares(lots_text):
    d = Decimal(lots_text) * 100
    return int(d) if d == d.to_integral_value() else Fraction(d)


class Ticker:
    def __init__(self, tk, raw, cfg):
        self.tk = tk
        bt = cfg['broker_through']
        price = raw['price']
        self.dates = [r[0] for r in price]
        if len(set(self.dates)) != len(self.dates):
            raise RuntimeError(f'{tk}: duplicate price dates')
        self.n = len(self.dates)
        self.idx = {d: i for i, d in enumerate(self.dates)}
        self.close = [num(r[1]) for r in price]
        self.volume = [num(r[2]) for r in price]
        self.rows = [[] for _ in range(self.n)]
        self.dropped_dates = set()
        self.dropped_rows = 0
        for d, b, inv, board, bv, sv, bl, sl, bf, sf in raw['broker']:
            if d > bt:
                continue
            i = self.idx.get(d)
            if i is None:  # broker session without a price candle: not part of any daily candle
                self.dropped_rows += 1
                self.dropped_dates.add(d)
                continue
            self.rows[i].append((b, inv, BOARD_MAP[board], num(bv), num(sv), shares(bl), shares(sl),
                                 0 if bf is None else int(bf), 0 if sf is None else int(sf),
                                 1 if bf is None else 0, 1 if sf is None else 0, 1))
        self.has = [bool(r) for r in self.rows]
        hits = [i for i, h in enumerate(self.has) if h]
        self.first = hits[0] if hits else self.n
        self.last = hits[-1] if hits else -1
        self.insider = [0] * self.n
        self.insider_off_candle = []
        for d, action, value, _key in raw['insider']:
            if action not in ('BUY', 'SELL'):
                continue
            v = num(value) if value is not None else 0
            i = self.idx.get(d)
            if i is None:
                self.insider_off_candle.append((d, action, value))
                continue
            self.insider[i] += v if action == 'BUY' else -v
        self._agg = {}
        self._prefix = {}
        self._base = {}

    def valid(self, t, w):
        """Flow output at t over a window of w candles: t has data and t-w+1 is not before the first data."""
        return self.has[t] and t - w + 1 >= self.first

    def agg(self, boards, invs):
        key = (frozenset(boards), frozenset(invs))
        res = self._agg.get(key)
        if res is not None:
            return res
        res = []
        bset, iset = key
        for rows in self.rows:
            d = {}
            for r in rows:
                if r[2] in bset and r[1] in iset:
                    a = d.get(r[0])
                    v = r[3:]
                    d[r[0]] = list(v) if a is None else [x + y for x, y in zip(a, v)]
            res.append(d)
        self._agg[key] = res
        return res

    def prefix(self, boards, invs):
        key = (frozenset(boards), frozenset(invs))
        res = self._prefix.get(key)
        if res is not None:
            return res
        res = [ZERO]
        for d in self.agg(boards, invs):
            tot = list(res[-1])
            for v in d.values():
                tot = [x + y for x, y in zip(tot, v)]
            res.append(tuple(tot))
        self._prefix[key] = res
        return res


def wsum(P, a, b):
    """Sum of per-candle totals over candles a..b inclusive."""
    return [x - y for x, y in zip(P[b + 1], P[a])]


def rolling(agg, w):
    """Yield (t, dict broker -> vector summed over candles max(0,t-w+1)..t). The dict is live: do not keep it."""
    roll = {}
    for t in range(len(agg)):
        for b, v in agg[t].items():
            a = roll.get(b)
            roll[b] = list(v) if a is None else [x + y for x, y in zip(a, v)]
        if t - w >= 0:
            for b, v in agg[t - w].items():
                a = [x - y for x, y in zip(roll[b], v)]
                if a[NR] == 0:
                    del roll[b]
                else:
                    roll[b] = a
        yield t, roll


def vsum(vecs):
    s = list(ZERO)
    for v in vecs:
        s = [x + y for x, y in zip(s, v)]
    return s


def freq(v, j):
    """Frequency sum, None when a row in it has none."""
    return None if v[j + 2] else v[j]


def ratio(a, b):
    if a is None or b is None or b == 0:
        return None
    return Fraction(a, b)


def score(v, rank):
    if rank == 'net_buy':
        return v[BV] - v[SV]
    if rank == 'gross_buy':
        return v[BV]
    if rank == 'net_sell':
        return v[SV] - v[BV]
    raise ValueError(rank)


def top_n(roll, n, rank):
    """Top-N cohort: score > 0 eligible, the N highest, ties by broker code A-Z."""
    elig = []
    for b, v in roll.items():
        s = score(v, rank)
        if s > 0:
            elig.append((-s, b))
    return [b for _, b in heapq.nsmallest(n, elig)]


def F(x):
    return Fraction(str(x)) if not isinstance(x, (int, Fraction)) else Fraction(x)


def filt(p):
    return tuple(p.get('boards') or ALL_BOARDS), tuple(p.get('investors') or ALL_INV)


# ------------------------------------------------------------------------------------- cohort pass
def base_pass(T, p, w):
    """Per candle t (None where the window rule gives null): (cohort, S_C, S_A filter, S_A board-only)."""
    boards, invs = filt(p)
    scope = p.get('scope', 'topn')
    n_top = int(p.get('top', 3))
    rank = p.get('rank', 'net_buy')
    sel = tuple(p.get('brokers') or ())
    key = (scope, sel if scope == 'selected' else (), n_top if scope == 'topn' else 0,
           rank if scope == 'topn' else '', boards, invs, w)
    if key in T._base:
        return T._base[key]
    agg = T.agg(boards, invs)
    PF = T.prefix(boards, invs)
    PB = T.prefix(boards, ALL_INV)
    out = [None] * T.n
    for t, roll in rolling(agg, w):
        if not T.valid(t, w):
            continue
        SA = wsum(PF, t - w + 1, t)
        SB = wsum(PB, t - w + 1, t)
        if scope == 'all':
            C, SC = None, SA
        else:
            C = list(sel) if scope == 'selected' else top_n(roll, n_top, rank)
            SC = vsum(roll[b] for b in C if b in roll)
        out[t] = (C, SC, SA, SB)
    T._base[key] = out
    return out


def per_t(B, fn):
    return [None if r is None else fn(*r) for r in B]


def lots_per_tx(v, side):
    if side == 'buy':
        sh, f = v[BS], freq(v, BF)
    else:
        sh, f = v[SS], freq(v, SF)
    if f is None or f == 0:
        return None
    return Fraction(sh, 100 * f)


def percentile(series, baseline):
    """Mid-rank percentile of x_t among the non-null values at the `baseline` candles before t."""
    n = len(series)
    first = next((i for i, v in enumerate(series) if v is not None), None)
    out = [None] * n
    if first is None:
        return out
    uniq = sorted(set(v for v in series if v is not None))
    rk = {v: i for i, v in enumerate(uniq)}
    r = [None if v is None else rk[v] for v in series]
    for t in range(n):
        x = r[t]
        if x is None or t - first < baseline:
            continue
        win = [r[k] for k in range(t - baseline, t) if r[k] is not None]
        if not win:
            continue
        lt = sum(1 for v in win if v < x)
        eq = sum(1 for v in win if v == x)
        out[t] = Fraction(100 * lt + 50 * eq, len(win))
    return out


# ----------------------------------------------------------------------------------------- formulas
def s_fl01(T, p):
    B = base_pass(T, p, int(p['window']))
    return {'buy': per_t(B, lambda C, SC, SA, SB: lots_per_tx(SC, 'buy')),
            'sell': per_t(B, lambda C, SC, SA, SB: lots_per_tx(SC, 'sell'))}


def s_fl02(T, p):
    B = base_pass(T, p, int(p['window']))
    return {'buy': per_t(B, lambda C, SC, SA, SB: ratio(SC[BV], freq(SC, BF))),
            'sell': per_t(B, lambda C, SC, SA, SB: ratio(SC[SV], freq(SC, SF)))}


def s_fl03(T, p):
    B = base_pass(T, p, int(p['window']))
    return {'buy': per_t(B, lambda C, SC, SA, SB: ratio(100 * SC[BS], SA[BS])),
            'sell': per_t(B, lambda C, SC, SA, SB: ratio(100 * SC[SS], SA[SS]))}


def _share_f(c, a):
    if c is None or a is None:
        return None
    return ratio(100 * c, a)


def s_fl04(T, p):
    B = base_pass(T, p, int(p['window']))
    return {'buy': per_t(B, lambda C, SC, SA, SB: _share_f(freq(SC, BF), freq(SA, BF))),
            'sell': per_t(B, lambda C, SC, SA, SB: _share_f(freq(SC, SF), freq(SA, SF)))}


def _vs_market(SC, SA, side):
    js, jf = (BS, BF) if side == 'buy' else (SS, SF)
    vol = ratio(SC[js], SA[js])
    fc, fa = freq(SC, jf), freq(SA, jf)
    if fc is None or fa is None:
        return None
    fr = ratio(fc, fa)
    if vol is None or fr is None or fr == 0:
        return None
    return vol / fr


def s_fl05(T, p):
    B = base_pass(T, p, int(p['window']))
    return {'buy': per_t(B, lambda C, SC, SA, SB: _vs_market(SC, SA, 'buy')),
            'sell': per_t(B, lambda C, SC, SA, SB: _vs_market(SC, SA, 'sell'))}


def _bs_ratio(SC):
    b, s = lots_per_tx(SC, 'buy'), lots_per_tx(SC, 'sell')
    if b is None or s is None or s == 0:
        return None
    return b / s


def s_fl06(T, p):
    B = base_pass(T, p, int(p['window']))
    return {'ratio': per_t(B, lambda C, SC, SA, SB: _bs_ratio(SC))}


def s_fl07(T, p):
    B = base_pass(T, p, int(p['window']))
    board = p.get('denom', 'board') == 'board'
    return {'value': per_t(B, lambda C, SC, SA, SB: ratio(100 * SC[BS], (SB if board else SA)[BS]))}


def s_fl08(T, p):
    B = base_pass(T, p, int(p['window']))
    side = p.get('side', 'buy')
    x = per_t(B, lambda C, SC, SA, SB: lots_per_tx(SC, side))
    return {'value': percentile(x, int(p['baseline']))}


def _imbalance(SC):
    b, s = freq(SC, BF), freq(SC, SF)
    if b is None or s is None:
        return None
    return ratio(b - s, b + s)


def s_fl09(T, p):
    B = base_pass(T, p, int(p['window']))
    p08 = percentile(per_t(B, lambda C, SC, SA, SB: lots_per_tx(SC, 'buy')), int(p['baseline']))
    f05 = per_t(B, lambda C, SC, SA, SB: _vs_market(SC, SA, 'buy'))
    f07 = per_t(B, lambda C, SC, SA, SB: ratio(100 * SC[BS], SB[BS]))  # FL07, default denominator (board)
    f11 = per_t(B, lambda C, SC, SA, SB: ratio(100 * (SC[BV] - SC[SV]), SB[BV]))  # FL11, default denominator
    f10 = per_t(B, lambda C, SC, SA, SB: _imbalance(SC))
    use_imb = bool(p.get('use_imb'))
    pct_min, ratio_min, part_min = F(p['pct_min']), F(p['ratio_min']), F(p['part_min'])
    flow_min, imb_min = F(p['flow_min']), F(p['imb_min'])
    out = [None] * T.n
    for t in range(T.n):
        ins = [p08[t], f05[t], f07[t], f11[t]] + ([f10[t]] if use_imb else [])
        if any(v is None for v in ins):
            continue
        ok = (p08[t] >= pct_min and f05[t] >= ratio_min and f07[t] >= part_min and f11[t] > flow_min
              and (not use_imb or f10[t] >= imb_min))
        out[t] = Fraction(1 if ok else 0)
    return {'value': out}


def s_fl10(T, p):
    B = base_pass(T, p, int(p['window']))
    return {'value': per_t(B, lambda C, SC, SA, SB: _imbalance(SC))}


def _fl11_series(T, p):
    B = base_pass(T, p, int(p['window']))
    board = p.get('denom', 'board') == 'board'
    return per_t(B, lambda C, SC, SA, SB: ratio(100 * (SC[BV] - SC[SV]), (SB if board else SA)[BV]))


def s_fl11(T, p):
    return {'value': _fl11_series(T, p)}


def _cohort_net(d, C):
    if C is None:
        return sum(v[BV] - v[SV] for v in d.values())
    return sum(d[b][BV] - d[b][SV] for b in C if b in d)


def s_fl12(T, p):
    w = int(p['window'])
    B = base_pass(T, p, w)
    agg = T.agg(*filt(p))
    out = [None] * T.n
    for t, r in enumerate(B):
        if r is None:
            continue
        C = r[0]
        cnt = sum(1 for k in range(t - w + 1, t + 1) if _cohort_net(agg[k], C) > 0)
        out[t] = Fraction(100 * cnt, w)
    return {'value': out}


def s_fl13(T, p):
    w = int(p['window'])
    buy, sell = [None] * T.n, [None] * T.n
    for t, roll in rolling(T.agg(*filt(p)), w):
        if not T.valid(t, w):
            continue
        tb = sum(v[BS] for v in roll.values())
        ts = sum(v[SS] for v in roll.values())
        if tb:
            buy[t] = Fraction(sum(v[BS] * v[BS] for v in roll.values()), tb * tb)
        if ts:
            sell[t] = Fraction(sum(v[SS] * v[SS] for v in roll.values()), ts * ts)
    return {'buy': buy, 'sell': sell}


def s_fl14(T, p):
    h = s_fl13(T, p)
    return {'asym': [None if b is None or s is None else b - s for b, s in zip(h['buy'], h['sell'])]}


def s_fl15(T, p):
    w, n_top = int(p['window']), int(p['top'])
    out = [None] * T.n
    for t, roll in rolling(T.agg(*filt(p)), w):
        if not T.valid(t, w):
            continue
        vals = [v[BS] for v in roll.values()]
        out[t] = ratio(100 * sum(heapq.nlargest(n_top, vals)), sum(vals))
    return {'value': out}


def _pos_nets(roll):
    return [v[BV] - v[SV] for v in roll.values() if v[BV] - v[SV] > 0]


def s_fl16(T, p):
    w, n_top = int(p['window']), int(p['top'])
    out = [None] * T.n
    for t, roll in rolling(T.agg(*filt(p)), w):
        if not T.valid(t, w):
            continue
        pos = _pos_nets(roll)
        out[t] = ratio(100 * sum(heapq.nlargest(n_top, pos)), sum(pos))
    return {'value': out}


def s_fl17(T, p):
    B = base_pass(T, p, int(p['window']))
    return {'value': per_t(B, lambda C, SC, SA, SB: ratio(SC[BV], SC[BS]))}  # BV / (100 BL) = BV / shares


def _anchor_idx(T, date):
    return next((i for i, d in enumerate(T.dates) if d >= date), T.n)


def _frozen_cohort(T, p, a):
    scope = p.get('scope', 'topn')
    if scope == 'selected':
        return list(p.get('brokers') or [])
    if scope == 'all':
        return None
    agg = T.agg(*filt(p))
    tot = {}
    for k in range(a, T.last + 1):
        for b, v in agg[k].items():
            x = tot.get(b)
            tot[b] = list(v) if x is None else [i + j for i, j in zip(x, v)]
    return top_n(tot, int(p.get('top', 3)), p.get('rank', 'net_buy'))


def _cohort_vec(d, C):
    return vsum(d.values()) if C is None else vsum(d[b] for b in C if b in d)


def s_fl18(T, p):
    a = _anchor_idx(T, p['anchor'])
    out = [None] * T.n
    if a < T.first:
        return {'value': out}
    C = _frozen_cohort(T, p, a)
    agg = T.agg(*filt(p))
    cum = list(ZERO)
    for t in range(a, T.n):
        cum = [x + y for x, y in zip(cum, _cohort_vec(agg[t], C))]
        if T.has[t]:
            out[t] = ratio(cum[BV], cum[BS])
    return {'value': out}


def _fl19_series(T, p):
    a = _anchor_idx(T, p['anchor'])
    out = [None] * T.n
    if a < T.first:
        return out
    C = _frozen_cohort(T, p, a)
    agg = T.agg(*filt(p))
    Q, K = 0, Fraction(0)  # Q in shares, K in IDR; K/Q = K/(100 Q_lots)
    for t in range(a, T.n):
        if not T.has[t]:
            continue
        v = _cohort_vec(agg[t], C)
        q = v[BS] - v[SS]
        if q > 0:
            px = Fraction(v[BV], v[BS])
            if Q <= 0:
                K = max(Q + q, 0) * px
            else:
                K += q * px
        elif q < 0 and Q > 0:
            K = K * Fraction(max(Q + q, 0), Q)
        Q += q
        out[t] = K / Q if Q > 0 else None
    return out


def s_fl19(T, p):
    return {'value': _fl19_series(T, p)}


def _dist(close, ref):
    if ref is None or ref == 0:
        return None
    return 100 * Fraction(close) / ref - 100


def s_fl20(T, p):
    c = _fl19_series(T, p)
    return {'value': [_dist(T.close[t], c[t]) for t in range(T.n)]}


def s_fl21(T, p):
    return {'value': percentile(_fl11_series(T, p), int(p['baseline']))}


def s_fl22(T, p):
    w = int(p['window'])
    out = [None] * T.n
    for t, roll in rolling(T.agg(*filt(p)), w):
        if not T.valid(t, w):
            continue
        active = [v for v in roll.values() if v[BV] > 0 or v[SV] > 0]
        if active:
            out[t] = Fraction(100 * sum(1 for v in active if v[BV] - v[SV] > 0), len(active))
    return {'value': out}


def fl23_default_brokers(T):
    idxs = [i for i in range(T.n) if T.has[i]][-20:]
    agg = T.agg(ALL_BOARDS, ALL_INV)
    tot = {}
    for k in idxs:
        for b, v in agg[k].items():
            tot[b] = tot.get(b, 0) + v[BV] - v[SV]
    elig = [(-x, b) for b, x in tot.items() if x > 0]
    return [b for _, b in heapq.nsmallest(3, elig)]


def s_fl23(T, p):
    brokers = p['brokers']
    if brokers == 'top3_net_buy_20':
        brokers = fl23_default_brokers(T)
    brokers = list(brokers)
    lot = p.get('unit', 'lot') == 'lot'
    cum_view = p.get('view', 'cum') == 'cum'
    s = _anchor_idx(T, p['start'])
    agg = T.agg(*filt(p))
    names = brokers + (['total'] if p.get('total') else [])
    out = {b: [None] * T.n for b in names}
    if s < T.first:
        return out
    cum = {b: 0 for b in brokers}
    for t in range(s, T.n):
        d = agg[t]
        day = {}
        for b in brokers:
            v = d.get(b)
            x = 0 if v is None else ((v[BS] - v[SS]) if lot else (v[BV] - v[SV]))
            day[b] = x
            cum[b] += x
        if not T.has[t]:
            continue
        src = cum if cum_view else day
        for b in brokers:
            out[b][t] = Fraction(src[b], 100) if lot else Fraction(src[b])
        if p.get('total'):
            tot = sum(src[b] for b in brokers)
            out['total'][t] = Fraction(tot, 100) if lot else Fraction(tot)
    return out


def _bandar(roll, n_top):
    nets = [(v[BV] - v[SV], b) for b, v in roll.items()]
    buyers = heapq.nsmallest(n_top, [(-x, b) for x, b in nets if x > 0])
    sellers = heapq.nsmallest(n_top, [(x, b) for x, b in nets if x < 0])
    nb = sum(-x for x, _ in buyers)
    ns = sum(x for x, _ in sellers)
    tbv = sum(v[BV] for v in roll.values())
    return nb, ns, tbv


def _fl24_series(T, p, w):
    n_top = int(p['top'])
    pct, rp = [None] * T.n, [None] * T.n
    for t, roll in rolling(T.agg(*filt(p)), w):
        if not T.valid(t, w):
            continue
        nb, ns, tbv = _bandar(roll, n_top)
        pct[t] = ratio(100 * (nb + ns), tbv)
        rp[t] = Fraction(nb + ns)
    return pct, rp


def s_fl24(T, p):
    return {'value': _fl24_series(T, p, int(p['window']))[0]}


def s_fl25(T, p):
    return {'value': _fl24_series(T, p, int(p['window']))[1]}


def s_fl26(T, p):
    lim = int(p['window'])
    B = base_pass(T, p, lim)
    agg = T.agg(*filt(p))
    out = [None] * T.n
    s = 0
    for t in range(T.n):
        r = B[t]
        if r is None:  # no data (no row) or the limit window not yet full
            s = 0
            continue
        net = _cohort_net(agg[t], r[0])
        if net > 0:
            s = s + 1 if s > 0 else 1
        elif net < 0:
            s = s - 1 if s < 0 else -1
        else:
            s = 0
        s = max(-lim, min(lim, s))
        out[t] = Fraction(s)
    return {'value': out}


def s_fl27(T, p):
    r, b = int(p['recent']), int(p['baseline'])
    volx, move = F(p['volx']), F(p['move'])
    vol, cl = T.volume, T.close
    out = [None] * T.n
    for t in range(T.n):
        if t - r - b + 1 < 0:
            continue
        sr = sum(vol[t - r + 1:t + 1])
        sb = sum(vol[t - r - b + 1:t - r + 1])
        if sb == 0 or cl[t - r] == 0:
            continue
        vol_ok = Fraction(sr, r) / Fraction(sb, b) >= volx
        move_ok = 100 * abs(Fraction(cl[t]) / cl[t - r] - 1) <= move
        out[t] = Fraction(1 if (vol_ok and move_ok) else 0)
    return {'value': out}


def s_fl28(T, p):
    w = int(p['window'])
    out = [None] * T.n
    for t in range(w - 1, T.n):
        out[t] = Fraction(sum(T.close[k] * T.volume[k] for k in range(t - w + 1, t + 1)), w)
    return {'value': out}


def s_fl29(T, p):
    w = int(p['window'])
    one, _ = _fl24_series(T, p, 1)
    thr = F(p['threshold'])
    out = [None] * T.n
    for t in range(T.n):
        if not T.valid(t, w):
            continue
        cnt = sum(1 for k in range(t - w + 1, t + 1) if one[k] is not None and one[k] > thr)
        out[t] = Fraction(100 * cnt, w)
    return {'value': out}


def s_fl30(T, p):
    w = int(p['window'])
    invs = tuple(p.get('investors') or ALL_INV)
    PX = T.prefix(('Nego', 'Cash'), invs)
    PA = T.prefix(ALL_BOARDS, invs)
    out = [None] * T.n
    for t in range(T.n):
        if T.valid(t, w):
            out[t] = ratio(100 * wsum(PX, t - w + 1, t)[BV], wsum(PA, t - w + 1, t)[BV])
    return {'value': out}


def s_fl31(T, p):
    w = int(p['window'])
    out = [None] * T.n
    for t in range(w - 1, T.n):
        out[t] = Fraction(sum(T.insider[t - w + 1:t + 1]))
    return {'value': out}


def s_fl32(T, p):
    b = int(p['baseline'])
    P = T.prefix(*filt(p))
    out = [None] * T.n
    for t in range(T.n):
        if not T.has[t] or t - b < T.first:
            continue
        cur = freq(wsum(P, t, t), BF)
        base = freq(wsum(P, t - b, t - 1), BF)
        if cur is None or base is None or base == 0:
            continue
        out[t] = Fraction(b * cur, base)
    return {'value': out}


def s_fl33(T, p):
    r, b = int(p['recent']), int(p['baseline'])
    P = T.prefix(*filt(p))
    out = [None] * T.n
    for t in range(T.n):
        if not T.has[t] or t - r - b + 1 < T.first:
            continue
        R = wsum(P, t - r + 1, t)
        S = wsum(P, t - r - b + 1, t - r)
        ar = ratio(R[BV], freq(R, BF))
        as_ = ratio(S[BV], freq(S, BF))
        if ar is None or as_ is None or as_ == 0:
            continue
        out[t] = 100 * (ar / as_ - 1)
    return {'value': out}


def broker_list(spec, profile):
    if isinstance(spec, str) and spec.startswith('class:'):
        cls = spec[len('class:'):]
        return sorted(code for code, c in profile if c == cls)
    return list(spec)


def s_fl34(T, p, profile):
    w = int(p['window'])
    inst = set(broker_list(p['inst'], profile))
    ret = set(broker_list(p['retail'], profile))
    if inst & ret:
        raise ValueError('FL34: a broker is in both lists: ' + ','.join(sorted(inst & ret)))
    out = [None] * T.n
    for t, roll in rolling(T.agg(*filt(p)), w):
        if not T.valid(t, w):
            continue
        ni = sum(v[BV] - v[SV] for b, v in roll.items() if b in inst)
        nr = sum(v[BV] - v[SV] for b, v in roll.items() if b in ret)
        out[t] = ratio(100 * (ni - nr), sum(v[BV] for v in roll.values()))
    return {'value': out}


def s_fl35(T, p):
    w = int(p['window'])
    agg = T.agg(*filt(p))
    out = [None] * T.n
    for t, roll in rolling(agg, w):
        if not T.valid(t, w):
            continue
        elig = [(-(v[BV] - v[SV]), b) for b, v in roll.items() if v[BV] - v[SV] > 0]
        if not elig:
            continue
        top = min(elig)[1]
        cnt = 0
        for k in range(t - w + 1, t + 1):
            v = agg[k].get(top)
            if v is not None and v[BV] - v[SV] > 0:
                cnt += 1
        out[t] = Fraction(100 * cnt, w)
    return {'value': out}


def s_fl36(T, p):
    B = base_pass(T, p, int(p['window']))
    return {'value': per_t(B, lambda C, SC, SA, SB: ratio(100 * (SC[BV] + SC[SV]), 2 * SB[BV]))}


def s_fl37(T, p):
    B = base_pass(T, p, int(p['window']))
    x = per_t(B, lambda C, SC, SA, SB: Fraction(SC[BV] - SC[SV]))
    return {'value': percentile(x, int(p['baseline']))}


def s_fl38(T, p):
    w = int(p['window'])
    out = [None] * T.n
    for t, roll in rolling(T.agg(*filt(p)), w):
        if not T.valid(t, w):
            continue
        pos = _pos_nets(roll)
        tot = sum(pos)
        if tot:
            out[t] = Fraction(sum(x * x for x in pos), tot * tot)
    return {'value': out}


def s_fl39(T, p):
    B = base_pass(T, p, int(p['window']))
    vw = per_t(B, lambda C, SC, SA, SB: ratio(SC[BV], SC[BS]))
    return {'value': [_dist(T.close[t], vw[t]) for t in range(T.n)]}


SERIES = {f'FL{i:02d}': globals()[f's_fl{i:02d}'] for i in range(1, 40)}


def run_case(T, case, profile, registry):
    iid, p = case['id'], case['params']
    fn = SERIES[iid]
    full = fn(T, p, profile) if iid == 'FL34' else fn(T, p)
    reg_out = registry[iid]['outputs']
    if reg_out == ['buy', 'sell']:
        side = p.get('side', 'buy')
        names = ['buy', 'sell'] if side == 'both' else [side]
    elif iid == 'FL23':
        names = list(full.keys())
    else:
        names = list(reg_out)
    missing = [nm for nm in names if nm not in full]
    if missing:
        raise RuntimeError(f'{iid}: no series for outputs {missing}')
    return {nm: full[nm] for nm in names}


def to_json_value(v):
    return None if v is None else float(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('tickers', nargs='*')
    ap.add_argument('--refresh', action='store_true', help='refetch the raw data instead of the cache')
    args = ap.parse_args()
    cfg = json.load(open(os.path.join(HERE, 'cases.json')))
    registry = {ind['id']: ind for ind in json.load(open(REGISTRY))['indicators']}
    tickers = args.tickers or cfg['tickers']
    rf = cfg['report_from']
    if cfg.get('timeframe', 'D') != 'D':
        raise SystemExit('only the daily timeframe is implemented')
    os.makedirs(OUT_DIR, exist_ok=True)
    t_all = time.time()
    profile = fetch_profile(args.refresh)
    for tk in tickers:
        t0 = time.time()
        raw = fetch_ticker(tk, cfg, args.refresh)
        t1 = time.time()
        T = Ticker(tk, raw, cfg)
        rep = [i for i, d in enumerate(T.dates) if d >= rf]
        res = []
        for case in cfg['cases']:
            outs = run_case(T, case, profile, registry)
            res.append({'id': case['id'], 'case': case['case'], 'params': case['params'],
                        'outputs': {nm: [[T.dates[i], to_json_value(s[i])] for i in rep] for nm, s in outs.items()}})
        with open(os.path.join(OUT_DIR, f'{tk}.json'), 'w') as fh:
            json.dump({'ticker': tk, 'cases': res}, fh, separators=(',', ':'))
        nodata = [T.dates[i] for i in rep if not T.has[i]]
        print(f'{tk}: candles {T.n} ({T.dates[0]}..{T.dates[-1]}), first data {T.dates[T.first]}, '
              f'last data {T.dates[T.last]}, report candles {len(rep)}, no-data report candles {nodata}, '
              f'broker rows on non-candle dates {T.dropped_rows} on {len(T.dropped_dates)} dates '
              f'(>= report_from: {sorted(d for d in T.dropped_dates if d >= rf)[:8]}'
              f'{"..." if len([d for d in T.dropped_dates if d >= rf]) > 8 else ""}), '
              f'insider BUY/SELL off-candle: {[(d, a) for d, a, _ in T.insider_off_candle if d >= rf]}, '
              f'fetch {t1 - t0:.1f}s compute {time.time() - t1:.1f}s', flush=True)
    print(f'total {time.time() - t_all:.1f}s')


if __name__ == '__main__':
    main()
