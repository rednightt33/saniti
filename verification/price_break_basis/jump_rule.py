# M560 evidence: a one-session rule for "does the published close carry this action?" on every price action since
# 2018 (read-only pgweb role). Before 2026-09-12 the published history is adjusted (D22 full scan 2026-10-31), so every
# measurable action there should read "adjusted"; the current 15-session median rule (publisher broker_basis `price`)
# is compared on the same actions where the publisher's sessions exist.
import sys, json, math, collections
import os; R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'); sys.path.insert(0, os.path.join(R, 'apps/terminal-publisher')); sys.path.insert(0, os.path.join(R, 'verification/terminal_api'))
import publisher as P, pgq
types = "','".join(P.PRICE_ACTION_TYPES)
sql = f"""
WITH a AS (SELECT ticker, annotation_date d, event_type t, ratio_old::float8 o, ratio_new::float8 n, amount_per_share::float8 x
           FROM public.idx_event_annotation WHERE event_family='CORPORATE_ACTION' AND annotation_date_role='EX_DATE'
           AND event_type IN ('{types}'))
SELECT a.ticker, a.d::text, a.t, a.o, a.n, a.x,
 (SELECT p.close::float8 FROM public."Price_Stock_Indonesia_IDX" p WHERE p.ticker=a.ticker AND p.timeframe='Daily' AND p.is_final AND p.date < a.d ORDER BY p.date DESC LIMIT 1),
 (SELECT p.close::float8 FROM public."Price_Stock_Indonesia_IDX" p WHERE p.ticker=a.ticker AND p.timeframe='Daily' AND p.is_final AND p.date >= a.d ORDER BY p.date LIMIT 1)
FROM a ORDER BY 2"""
r = pgq.q(sql)
if 'error' in r: sys.exit(r['error'][:800])
rows = r['rows']; print('actions', len(rows), f"({r['_ms']} ms)")
c = collections.Counter(); odd = []
for tk, d, t, o, n, x, c0, c1 in rows:
    era = 'before 2026-09-12' if d < '2026-09-12' else 'from 2026-09-12'
    if not (c0 and c1 and c0 > 0 and c1 > 0): c[(era, 'no close')] += 1; continue
    f = P.terms_factor(t, o, n, x, cum_close=c0, later=1.0)
    if f is None: c[(era, 'no terms')] += 1; continue
    if abs(f - 1) < P.BASIS_PRICE_MIN: c[(era, 'too small (<10%)')] += 1; continue
    j = c0 / c1
    side = 'raw' if abs(math.log(j) - math.log(f)) < abs(math.log(j)) else 'adjusted'
    c[(era, side)] += 1
    if (era.startswith('before') and side == 'raw') or not era.startswith('before'): odd.append((tk, d, t, round(f, 3), round(j, 3), side))
for k in sorted(c): print(k, c[k])
print('listed:'); [print(o) for o in odd]
