# M559 evidence: the publisher's own broker_basis rule on dev's rows now, for every ticker the Screener flags
# (read-only pgweb role; secrets in memory only)
import sys, json, datetime as dt
import os; R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'); sys.path.insert(0, os.path.join(R, 'apps/terminal-publisher')); sys.path.insert(0, os.path.join(R, 'verification/terminal_api'))
import publisher as P, pgq
T = ['FORU', 'BAJA', 'ENRG', 'VKTR', 'AHAP', 'BRNA', 'BUVA', 'PBSA', 'MGLV', 'PSSI', 'PPGL', 'BMAS']
types = "','".join(P.PRICE_ACTION_TYPES)
def rows(sql):
    r = pgq.q(sql)
    if 'error' in r: sys.exit(r['error'][:500])
    return r['rows'] or []
through = rows('SELECT max(trade_date)::text FROM public."Feature_05_Foreign_Domestic_Broker_Detail"')[0][0]
print('broker data through', through)
out = {}
for t in T:
    acts = rows(P.BASIS_ACTIONS_SQL.replace('%s', f"'{t}'", 1).replace('= ANY(%s)', f"IN ('{types}')"))
    acts = [tuple(a[:5]) + (a[5] in (True, 'true', 't'),) for a in acts]
    days = {}
    for ex, *_ in acts:
        if ex <= through:
            d = dt.date.fromisoformat(ex)
            lo, hi = (d - dt.timedelta(days=P.BASIS_WINDOW_DAYS)).isoformat(), (d + dt.timedelta(days=P.BASIS_WINDOW_DAYS)).isoformat()
            sql = P.BASIS_DAYS_SQL.replace('%s', f"'{t}'", 1).replace('BETWEEN %s AND %s', f"BETWEEN '{lo}' AND '{hi}'")
            for r in rows(sql): days[r[0]] = tuple(r)
    b = P.broker_basis(acts, [days[d] for d in sorted(days)], through)
    recent = [dict(zip(P.BASIS_COLUMNS, r)) for r in b if r[0] >= '2026-09-12']
    out[t] = recent
    for r in recent: print(t, r['ex'], r['type'], 'status', r['status'], 'price', r['price'], 'terms', r['terms'], 'pre/post', r['pre'], r['post'], 'decided', r['decided'])
json.dump(out, open(sys.argv[1], 'w'), indent=1)
