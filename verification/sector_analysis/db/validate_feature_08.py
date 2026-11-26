"""EXEC-SECTOR-ANALYSIS S1: independent check of Feature_08_Group_Daily on chosen dates (read-only).

For each date it reads the raw rows (the final daily prices of the market's 21 newest sessions up to the date and each
member's own previous close, the Feature 04 rows of the date, the stock universe, the SECTOR and MARKET entities) and
recomputes in Python, by its own code and not by the SQL of the migration, every column of every group: members,
EMA50/EMA200 breadth (the Overview's rule), advancers/unchanged/decliners, the weight sum (adv20_value: sum of close x
volume over the 20 market sessions up to the date / 20), the weighted return with the previous date's weights, and the
level against the previous row (level / previous non-NULL level - 1 = ret / 100). It reports every difference.

  python validate_feature_08.py <date> [<date> ...]     (DATABASE_URL in the environment; prints OUT lines, VERDICT)
  import: validate(conn, date) -> [differences]          (backfill_job.py runs it on its check dates)
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter

PRICE = 'public."Price_Stock_Indonesia_IDX"'
COLS = ('sector', 'members', 'n_ema50', 'above_ema50', 'n_ema200', 'above_ema200', 'adv_1d', 'unch_1d', 'dec_1d',
        'weight_basis', 'weight_sum', 'ret_1d_w')


def close_enough(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def expected(q, d):
    """{(group_kind, group_name): {column: value}} of date d recomputed from the raw rows, or None when d is not a
    market date. q(sql, params) -> rows (a psycopg connection's, or a read-only relay's)."""
    import datetime as dt
    d = dt.date.fromisoformat(d) if isinstance(d, str) else d
    market = q("SELECT ticker FROM public.\"Feature_Index_Entity\" WHERE entity_kind = 'MARKET'")[0][0]
    sectors = {r[0] for r in q("SELECT sector FROM public.\"Feature_Index_Entity\" WHERE entity_kind = 'SECTOR'")}
    days = [r[0] for r in q(f"SELECT date FROM {PRICE} WHERE ticker = %s AND timeframe = 'Daily' AND is_final AND date <= %s "
                            'ORDER BY date DESC LIMIT 21', (market, d))]
    days = [dt.date.fromisoformat(x[:10]) if isinstance(x, str) else x for x in days]
    if not days or days[0] != d:
        return None
    universe = q('SELECT "Ticker", "Sector", "Industry" FROM public."IDX_Stock_Universe" WHERE "Security Type" = \'stock\'')
    stocks = {t: (s, i) for t, s, i in universe}
    # every price row of the 21 sessions (every security: the weight function sizes funds and indexes too)
    rows = q(f"SELECT ticker, date, close::float8, volume::float8 FROM {PRICE} WHERE timeframe = 'Daily' AND is_final "
             'AND date = ANY(%s)', (days,))
    by = {}
    for t, day, c, v in rows:
        day = dt.date.fromisoformat(day[:10]) if isinstance(day, str) else day
        by.setdefault(t, {})[day] = (float(c), None if v is None else float(v))

    def adv20(at):
        window = days[at:at + 20]
        if len(window) < 20:
            return {}
        out = {}
        for t, series in by.items():
            vals = [series[x][0] * series[x][1] for x in window if x in series and series[x][1] is not None]
            if vals and sum(vals) > 0:
                out[t] = sum(vals) / 20
        return out
    w0, w1 = adv20(0), adv20(1)
    closes = {t: by[t][d][0] for t in stocks if t in by and d in by[t]}
    prev = {t: None if c is None else float(c) for t, c in q(
        f"SELECT x.t, (SELECT p.close::float8 FROM {PRICE} p WHERE p.ticker = x.t AND p.timeframe = 'Daily' "
        'AND p.is_final AND p.date < %s ORDER BY p.date DESC LIMIT 1) FROM unnest(%s::text[]) AS x(t)', (d, sorted(closes)))}
    f4 = {t: (c, e50, e200) for t, c, e50, e200 in q(
        'SELECT ticker, close, ema_50, ema_200 FROM public."Feature_04_Technical_Indicator" WHERE trade_date = %s '
        "AND timeframe = 'Daily' AND asset_type = 'equity'", (d,)) if t in stocks}
    inds = {}
    for t, (s, i) in stocks.items():
        if i != 'Undefined':
            inds.setdefault(i, Counter())[s] += 1
    groups = [('MARKET', market, None, list(stocks))]
    groups += [('SECTOR', s, s, [t for t, (ss, _) in stocks.items() if ss == s]) for s in sorted(sectors)]
    groups += [('INDUSTRY', i, min(c.items(), key=lambda kv: (-kv[1], kv[0]))[0],
                [t for t, (_, ii) in stocks.items() if ii == i]) for i, c in sorted(inds.items())]
    out = {}
    for kind, name, sector, members in groups:
        m = [t for t in members if t in closes]
        f = [f4[t] for t in members if t in f4]
        both = [t for t in m if prev.get(t) and prev[t] > 0 and w1.get(t, 0) > 0]
        ws = [w0[t] for t in m if t in w0]
        out[(kind, name)] = {
            'sector': sector, 'members': len(m),
            'n_ema50': sum(1 for r in f if r[1] is not None), 'above_ema50': sum(1 for r in f if r[1] is not None and r[0] > r[1]),
            'n_ema200': sum(1 for r in f if r[2] is not None), 'above_ema200': sum(1 for r in f if r[2] is not None and r[0] > r[2]),
            'adv_1d': sum(1 for t in m if prev.get(t) is not None and closes[t] > prev[t]),
            'unch_1d': sum(1 for t in m if prev.get(t) is not None and closes[t] == prev[t]),
            'dec_1d': sum(1 for t in m if prev.get(t) is not None and closes[t] < prev[t]),
            'weight_basis': 'adv20_value' if ws else None, 'weight_sum': sum(ws) if ws else None,
            'ret_1d_w': 100 * sum(w1[t] * (closes[t] / prev[t] - 1) for t in both) / sum(w1[t] for t in both) if both else None}
    return out


def compare(stored, want):
    """[(group, column, stored, expected)] between {(kind, name): row} dicts."""
    diffs = []
    for key, w in want.items():
        got = stored.get(key)
        if got is None:
            diffs.append((f'{key[0]}:{key[1]}', 'row', None, 'missing'))
            continue
        diffs += [(f'{key[0]}:{key[1]}', k, got[k], v) for k, v in w.items() if not close_enough(got[k], v)]
    diffs += [(f'{k}:{n}', 'row', 'present', 'not a current group') for k, n in sorted(set(stored) - set(want))]
    return diffs


def validate(conn, d):
    """Differences between the stored rows of date d and the recomputation, and of each level against the group's
    previous row: [(group, column, stored, expected)]."""
    q = lambda sql, p=(): conn.execute(sql, p).fetchall()
    want = expected(q, d)
    if want is None:
        return [('*', 'date', None, f'{d} is not a market date')]
    stored = {(r[0], r[1]): dict(zip(COLS, r[2:])) for r in q(
        f'SELECT group_kind, group_name, {", ".join(COLS)} FROM public."Feature_08_Group_Daily" WHERE date = %s', (d,))}
    diffs = compare(stored, want)
    for kind, name, ret, level in q(
            """SELECT g.group_kind, g.group_name, g.ret_1d_w, g.index_level FROM public."Feature_08_Group_Daily" g
               WHERE g.date = %s""", (d,)):
        pl = q("""SELECT index_level FROM public."Feature_08_Group_Daily" WHERE group_kind = %s AND group_name = %s
                  AND date < %s AND index_level IS NOT NULL ORDER BY date DESC LIMIT 1""", (kind, name, d))
        first = not q('SELECT 1 FROM public."Feature_08_Group_Daily" WHERE group_kind = %s AND group_name = %s AND date < %s LIMIT 1',
                      (kind, name, d))
        level_want = 100.0 if first else (None if ret is None else (pl[0][0] if pl else 100.0) * (1 + ret / 100))
        if not close_enough(level, level_want):
            diffs.append((f'{kind}:{name}', 'index_level', level, level_want))
    return diffs


def main(dates):
    import psycopg
    bad = 0
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, application_name='feature-08-validate') as conn:
        conn.execute('SET default_transaction_read_only = on')
        for d in dates:
            diffs = validate(conn, d)
            bad += len(diffs)
            print('OUT ' + json.dumps({'q': 'validate', 'date': d, 'differences': len(diffs), 'first': diffs[:5]}, default=str), flush=True)
    print('VERDICT ' + ('VALIDATE_OK' if not bad else f'VALIDATE_DIFF {bad}'), flush=True)
    return 0 if not bad else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
