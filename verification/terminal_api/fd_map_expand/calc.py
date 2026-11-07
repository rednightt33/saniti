"""Figures for fd_map_window_options.html (user 2026-11-07: "kalau seandainya foreign x dometic ini mau di expand, kira2
informasi apa yang deserve kita show? ... coba propose 10 opsi dalam 1 HTML").

Mirrors the Terminal's Foreign x Domestic map exactly (apps/edge-bff/terminal/src/app/broker.ts bandarBalance,
src/data/brokerAgg.ts fdSplit, fdQuadrant): on one board, the Top N net buyers and sellers of all investor types; each one's
net split by the investor type of its trades; x = foreign part, y = domestic part, verdict = x + y, all in % of the total
buy value of the period. Usage: python3 -I calc.py <bk_TICKER.json> <px_TICKER.json> <out.json>
(the stand-in snapshot of verification/terminal_api/terminal_look/serve.mjs; the data are not committed)."""
import collections
import json
import statistics
import sys

BK, PX, OUT = sys.argv[1:4]
rows = json.load(open(BK))['rows']
px = {r[0]: r[4] for r in json.load(open(PX))['rows']}
BOARDS = ('Regular', 'Nego', 'Cash')
dates = sorted({r[0] for r in rows})
by = collections.defaultdict(list)                     # (date, board) -> rows
for d, b, inv, board, bv, sv, *_ in rows:
    by[(d, board)].append((b, inv, bv, sv))
FLAT = 0.05
QUAD = ['Both accumulating', 'Domestic absorbing, foreign leaving', 'Foreign absorbing, domestic leaving', 'Both distributing',
        'No net flow', 'Domestic accumulating, foreign flat', 'Domestic distributing, foreign flat',
        'Foreign accumulating, domestic flat', 'Foreign distributing, domestic flat']


def quadrant(x, y):
    fx, fy = abs(x) < FLAT, abs(y) < FLAT
    if fx and fy: return 4
    if fx: return 5 if y > 0 else 6
    if fy: return 7 if x > 0 else 8
    return 0 if x > 0 and y > 0 else 1 if x < 0 and y > 0 else 2 if x > 0 else 3


def verdict(r):
    a = abs(r)
    return 'Neutral' if a < 6 else ('Big ' if a >= 10 else '') + ('Acc' if r > 0 else 'Dist')


def point(ds, n=3, boards=('Regular',), detail=False):
    """the map's point for the sessions ds: x, y, verdict in % of total buy value"""
    allb = collections.defaultdict(lambda: [0.0, 0.0]); part = collections.defaultdict(lambda: {'Foreign': 0.0, 'Domestic': 0.0})
    for d in ds:
        for bd in boards:
            for b, inv, bv, sv in by[(d, bd)]:
                allb[b][0] += bv; allb[b][1] += sv; part[b][inv] = part[b].get(inv, 0.0) + bv - sv
    nets = [(b, v[0] - v[1]) for b, v in allb.items()]
    buyers = sorted([x for x in nets if x[1] > 0], key=lambda x: (-x[1], x[0]))[:n]
    sellers = sorted([x for x in nets if x[1] < 0], key=lambda x: (x[1], x[0]))[:n]
    total = sum(v[0] for v in allb.values())
    if total <= 0:
        return None
    nf = sum(part[b]['Foreign'] for b, _ in buyers + sellers); nd = sum(part[b]['Domestic'] for b, _ in buyers + sellers)
    x, y = nf / total * 100, nd / total * 100
    out = {'x': round(x, 2), 'y': round(y, 2), 'r': round(x + y, 2), 'q': quadrant(x, y), 'v': verdict(x + y), 'total': round(total)}
    if detail:
        out['buyers'] = [{'b': b, 'net': round(v), 'f': round(part[b]['Foreign']), 'd': round(part[b]['Domestic'])} for b, v in buyers]
        out['sellers'] = [{'b': b, 'net': round(v), 'f': round(part[b]['Foreign']), 'd': round(part[b]['Domestic'])} for b, v in sellers]
        out['nf'], out['nd'] = round(nf), round(nd)
        # every broker's foreign and domestic net (the drivers view), and the Top N's share of all buying
        out['drivers'] = sorted([{'b': b, 'f': round(part[b]['Foreign']), 'd': round(part[b]['Domestic'])} for b in allb],
                                key=lambda o: -(abs(o['f']) + abs(o['d'])))[:8]
        out['topn_buy_share'] = round(sum(allb[b][0] for b, _ in buyers + sellers) / total * 100, 1)
    return out


END = len(dates)
cur5 = dates[END - 5:END]
res = {'ticker': 'BBRI', 'board': 'Regular', 'n': 3, 'end': dates[-1], 'sessions': len(dates), 'quadrants': QUAD}
res['now'] = {w: point(dates[END - w:END], detail=(w == 5)) for w in (1, 5, 20)}
res['now'][5]['from'] = cur5[0]
# 2. the 5D point's trail: one rolling 5D point per session over the last 20 sessions
res['trail'] = [{'d': dates[k - 1], **point(dates[k - 5:k])} for k in range(END - 19, END + 1)]
# 3. 60 sessions of rolling 5D x, y, verdict, with the close
res['series'] = [{'d': dates[k - 1], 'c': px.get(dates[k - 1]), **{k2: v for k2, v in point(dates[k - 5:k]).items() if k2 in ('x', 'y', 'r')}}
                 for k in range(END - 59, END + 1)]
# 4. the daily quadrant of the last 30 sessions, and the current run
daily = [{'d': d, **point([d])} for d in dates[-30:]]
res['daily'] = [{'d': o['d'], 'q': o['q'], 'r': o['r']} for o in daily]
run = 0
for o in reversed(daily):
    if o['q'] != daily[-1]['q']: break
    run += 1
res['run'] = run
# 5. the current 5D against every rolling 5D of the history held (the page's own data)
hist = [point(dates[k - 5:k]) for k in range(5, END + 1)]
for key in ('x', 'y', 'r'):
    vals = sorted(h[key] for h in hist)
    c = res['now'][5][key]
    res.setdefault('pct', {})[key] = {'pct': round(sum(1 for v in vals if v <= c) / len(vals) * 100), 'min': vals[0], 'med': round(statistics.median(vals), 2),
                                       'max': vals[-1], 'cur': c, 'n': len(vals)}
# 7. Top N sensitivity: the current 5D for N = 1..10
res['topn'] = [{'n': n, **{k: v for k, v in point(cur5, n=n).items() if k in ('x', 'y', 'r', 'q')}} for n in range(1, 11)]
# 8. boards: Regular, Nego, Cash and all boards
res['boards'] = {bd: point(cur5, boards=(bd,)) for bd in BOARDS}
res['boards']['All'] = point(cur5, boards=BOARDS)
# 9. after the same quadrant: every earlier session whose rolling 5D point sat in the current quadrant, the close 5 and 20
# sessions later (sessions with a later close only)
q = res['now'][5]['q']; after = []
for k in range(5, END + 1):
    p = hist[k - 5]
    d = dates[k - 1]
    if p['q'] != q or k - 1 + 20 >= END or d not in px: continue
    c0, c5, c20 = px[d], px.get(dates[k - 1 + 5]), px.get(dates[k - 1 + 20])
    if c5 and c20: after.append({'d': d, 'r5': round((c5 / c0 - 1) * 100, 2), 'r20': round((c20 / c0 - 1) * 100, 2)})
# consecutive sessions in the quadrant are one episode: the sessions above are not independent
eps = sum(1 for k in range(5, END + 1) if hist[k - 5]['q'] == q and (k == 5 or hist[k - 6]['q'] != q) and k - 1 + 20 < END)
res['after'] = {'q': q, 'n': len(after), 'episodes': eps, 'med5': round(statistics.median([a['r5'] for a in after]), 2) if after else None,
                'med20': round(statistics.median([a['r20'] for a in after]), 2) if after else None,
                'up20': sum(1 for a in after if a['r20'] > 0), 'cases': after[-6:]}
# 10. how much the reading stands for: the Top N's share of all buying, the average daily buy value, against the history
res['size'] = {'topn_buy_share': res['now'][5]['topn_buy_share'], 'avg_daily_buy': round(res['now'][5]['total'] / 5),
               'hist_avg_daily_buy': round(statistics.mean(h['total'] for h in hist) / 5)}
# ---- for the window options (user 2026-11-07: "A") ----
# every broker of the 5D period: net, its foreign and domestic parts, buy and sell value, share of all buying
def brokers(ds, boards=('Regular',)):
    m = collections.defaultdict(lambda: {'buy': 0.0, 'sell': 0.0, 'Foreign': 0.0, 'Domestic': 0.0})
    for d in ds:
        for bd in boards:
            for b, inv, bv, sv in by[(d, bd)]:
                m[b]['buy'] += bv; m[b]['sell'] += sv; m[b][inv] += bv - sv
    total = sum(v['buy'] for v in m.values())
    out = [{'b': b, 'net': round(v['buy'] - v['sell']), 'f': round(v['Foreign']), 'd': round(v['Domestic']), 'buy': round(v['buy']),
            'sell': round(v['sell']), 'share': round(v['buy'] / total * 100, 2)} for b, v in m.items()]
    return sorted(out, key=lambda o: -abs(o['net']))
res['brokers'] = brokers(cur5)[:16]
res['broker_count'] = len(brokers(cur5))
# the map's point for longer and shorter periods ending at the same session
res['periods'] = {w: point(dates[END - w:END]) for w in (1, 5, 10, 20, 60, 120)}
# each period's 30-session sparkline of its own rolling verdict
res['spark'] = {w: [point(dates[k - w:k])['r'] for k in range(END - 29, END + 1)] for w in (5, 20, 60)}
# the last 60 sessions' daily points (1D), for a heat strip
res['daily60'] = [{'d': dates[k - 1], **{kk: vv for kk, vv in point([dates[k - 1]]).items() if kk in ('x', 'y', 'r', 'q')}} for k in range(END - 59, END + 1)]
# Top N x board: the 5D verdict for N = 1..10 on Regular and on all boards
res['grid'] = {bd: [point(cur5, n=n, boards=bds)['r'] for n in range(1, 11)] for bd, bds in (('Regular', ('Regular',)), ('All boards', BOARDS))}
# 120 sessions of rolling 5D with the running percentile band of the 5D verdict over the history held before each session
hist_r = [h['r'] for h in hist]
band = []
for k in range(END - 119, END + 1):
    past = sorted(hist_r[:k - 5 + 1])
    q = lambda f: past[min(len(past) - 1, int(f * (len(past) - 1)))]
    band.append({'d': dates[k - 1], 'r': hist_r[k - 5], 'p10': q(.1), 'p50': q(.5), 'p90': q(.9), 'c': px.get(dates[k - 1])})
res['band'] = band
json.dump(res, open(OUT, 'w'), separators=(',', ':'))
print(json.dumps({k: res[k] for k in ('end', 'run', 'pct', 'after', 'size')}, indent=1)[:2500])
print('now', res['now'])
