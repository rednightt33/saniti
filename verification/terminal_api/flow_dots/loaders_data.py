"""EXEC-FLOW-NEW-3 (user 2026-11-08: "Untuk loaders, coba kasih saya 10 objek dalam satu HTML to decide"): the figures of
the Loaders options, from the Terminal stand-in's BBRI broker rows (Regular board, both investor types), the formulas
of calc/flow.ts loadersTable (net lots, cost A and B, distance, buy days) plus the proposed columns.
Usage: python3 loaders_data.py <bk_BBRI.json> <px_BBRI.json> <out.json>"""
import json, sys
bk, px, out = sys.argv[1:4]
B = json.load(open(bk)); P = json.load(open(px))
close = {r[0]: r[4] for r in P['rows']}
rows = [r for r in B['rows'] if r[3] == 'Regular']
days = sorted({r[0] for r in rows})[-60:]
S, E = days[0], days[-1]
rows = [r for r in rows if S <= r[0] <= E]
per = {}
for d, b, inv, _, bv, sv, bl, sl, *_ in rows:
    x = per.setdefault(b, {}).setdefault(d, [0, 0, 0, 0, 0, 0])   # bv sv bl sl foreign-net-lots total-net-lots
    x[0] += bv; x[1] += sv; x[2] += bl; x[3] += sl
    if inv == 'Foreign': x[4] += bl - sl
    x[5] += bl - sl
tot_lots = sum(r[6] for r in rows)
last = close[E]
res = {}
for b, byd in per.items():
    BV = BL = Q = K = 0.0; buy = 0; n = 0; cum = []; cost = []; c = 0; lastbuy = None; streak = 0; sdir = 0; fnet = 0
    for d in days:
        v = byd.get(d)
        if v is None:
            cum.append(c); cost.append(BV / (100 * BL) if BL else None); continue
        n += 1; q = v[2] - v[3]; BV += v[0]; BL += v[2]; fnet += v[4]
        if q > 0:
            buy += 1; lastbuy = d; price = v[0] / v[2] if v[2] else 0
            K = max(Q + q, 0) * price if Q <= 0 else K + q * price
        elif q < 0 and Q > 0:
            K = K * max(Q + q, 0) / Q
        Q += q; c += q; cum.append(c); cost.append(BV / (100 * BL) if BL else None)
        s = 1 if q > 0 else -1 if q < 0 else 0
        if s and s == sdir: streak += 1
        elif s: sdir, streak = s, 1
    net = Q
    avg = BV / (100 * BL) if BL else None
    model = K / (100 * Q) if Q > 0 else None
    n5 = sum((byd[d][2] - byd[d][3]) for d in days[-5:] if d in byd)
    res[b] = dict(b=b, lots=net, avg=avg, model=model, dist=None if not avg else 100 * (last / avg - 1),
                  buyDays=buy, days=n, net5=n5, pl=None if not avg else net * 100 * (last - avg),
                  vol=100 * net / tot_lots if tot_lots else None, foreign=None if not net else 100 * fnet / net,
                  lastBuy=lastbuy, streak=streak * sdir, cum=cum, cost=cost)
load = sorted([r for r in res.values() if r['lots'] > 0], key=lambda r: -r['lots'])[:10]
sell = sorted([r for r in res.values() if r['lots'] < 0], key=lambda r: r['lots'])[:5]
pos = sum(r['lots'] for r in res.values() if r['lots'] > 0)
json.dump(dict(ticker='BBRI', start=S, end=E, last=last, days=days, ohlc=[[d] + [r for r in P['rows'] if r[0] == d][0][1:5] for d in days], board='Regular', sessions=len(days), totalLots=tot_lots,
               positive=pos, load=load, sell=sell), open(out, 'w'))
print(S, E, last, [(r['b'], r['lots']) for r in load[:5]], [(r['b'], r['lots']) for r in sell[:2]])
