"""EXEC-BACKTEST-REVAMP P9: the observed basis jump at each action (median broker VWAP / close before the ex date over
the median after it) against the factor its terms give (split and reverse split new/old; bonus (old + new)/old; rights
issue P/TERP with TERP = (old P + new X)/(old + new), P the broker VWAP on the last session before the ex date, X the
exercise price), and the close's continuity across the ex date. Reads the files fetch.py wrote.
  python3 -I analyse.py OUTDIR"""
import json, sys, glob, statistics as st, collections
S = sys.argv[1]
def f_th(typ, o, n, px, P):
    o, n = float(o), float(n)
    if typ == 'STOCK_SPLIT' or typ == 'REVERSE_SPLIT': return n / o
    if typ == 'BONUS_SHARE': return (o + n) / o
    if typ == 'RIGHT_ISSUE':
        X = float(px); terp = (o * P + n * X) / (o + n)
        return P / terp
res = collections.defaultdict(collections.Counter); ex_rows = collections.defaultdict(list)
for f in sorted(glob.glob(f'{S}/basis_*_*_*.json')):
    typ = f.split('basis_')[1].rsplit('_', 2)[0]
    for e in json.load(open(f)):
        days = [(d, float(v), float(c)) for d, v, c, h, l in e.get('days', []) if v not in (None, '') and c not in (None, '') and float(c) > 0 and float(v) > 0]
        pre = [v / c for d, v, c in days if d < e['ex']]; post = [v / c for d, v, c in days if d >= e['ex']]
        if len(pre) < 3 or len(post) < 3: res[typ]['too few days'] += 1; continue
        P = [v for d, v, c in days if d < e['ex']][-1]
        th = f_th(typ, e['old'], e['new'], e.get('px'), P)
        jump = st.median(pre) / st.median(post)
        cpre = [c for d, v, c in days if d < e['ex']][-1]; cpost = [c for d, v, c in days if d >= e['ex']][0]
        cjump = cpre / cpost
        near = lambda a, b, tol=0.04: abs(a / b - 1) <= tol
        if abs(th - 1) < 0.02: k = 'factor ~1 (no basis change expected)'
        elif near(jump, th): k = 'broker raw, price adjusted (jump = factor)'
        elif near(jump, 1) and near(cjump, 1, 0.25): k = 'both on one basis (jump 1, close smooth)'
        elif near(jump, 1) and near(cjump, th, 0.25): k = 'neither adjusted (jump 1, close jumps)'
        else: k = 'other'
        res[typ][k] += 1; ex_rows[(typ, k)].append((e['t'], e['ex'], round(th, 3), round(jump, 3), round(st.median(post), 3), round(cjump, 3), e['ex'][:4]))
for typ, c in res.items():
    print(typ, dict(c))
for (typ, k), rows in sorted(ex_rows.items()):
    yrs = collections.Counter(r[-1] for r in rows)
    print(f'  {typ} | {k}: {len(rows)} years {dict(sorted(yrs.items()))} e.g. {rows[:3]}')


# rights issues by the direction of their factor
c = collections.Counter(); odd = []; errs = []
for f in sorted(glob.glob(f'{S}/basis_RIGHT_ISSUE_*.json')):
    for e in json.load(open(f)):
        days = [(d, float(v), float(cl)) for d, v, cl, h, l in e.get('days', []) if v not in (None, '') and cl not in (None, '') and float(cl) > 0 and float(v) > 0]
        pre = [v / cl for d, v, cl in days if d < e['ex']]; post = [v / cl for d, v, cl in days if d >= e['ex']]
        if len(pre) < 3 or len(post) < 3: continue
        P = [v for d, v, cl in days if d < e['ex']][-1]; o, n, X = float(e['old']), float(e['new']), float(e['px'])
        th = P / ((o * P + n * X) / (o + n)); jump = st.median(pre) / st.median(post)
        band = 'f>1.02' if th > 1.02 else 'f<0.98' if th < 0.98 else 'f~1'
        k = 'jump=f' if abs(jump / th - 1) <= 0.04 else 'jump=1' if abs(jump - 1) <= 0.04 else 'other'
        c[(band, k)] += 1
        if band == 'f>1.02': errs.append(abs(jump / th - 1))
        if (band, k) in [('f>1.02', 'other'), ('f>1.02', 'jump=1')]: odd.append((e['t'], e['ex'], o, n, X, round(P, 1), round(th, 3), round(jump, 3)))
for k, v in sorted(c.items()): print(k, v)
errs.sort(); print('f>1.02: |jump/f-1| median', round(st.median(errs), 4), 'p90', round(errs[int(0.9*len(errs))], 4), 'n', len(errs))
print('odd', odd)
