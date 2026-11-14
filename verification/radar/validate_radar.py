"""EXEC-RADAR R4: independent recalculation of the Radar measures, gates, ranks and results.

Written from SCREENER_LIBRARY.md (sections 2, 9, 11-13), verification/radar/RADAR_PAGE_SPEC.md section 5 and the user's
decisions in EXEC.md EXEC-RADAR, without reading the SQL functions of migration 20261114_001. It reads CSV extracts of
the source tables and of the Feature_07 tables and reports every difference.

Inputs (a directory, header-less CSV, columns in this order):
  f06.csv       trade_date, ticker, market_board, foreign_buy_1d, foreign_sell_1d, foreign_net_1d, domestic_buy_1d, ...
  f03.csv       date, ticker, market_board, total_buy_value, institutional_net_value, retail_net_value   (Regular rows)
  f05.csv       trade_date, ticker, broker, investor_type, market_board, buy_value, sell_value          (Regular rows)
  universe.csv  Ticker
  events.csv    ticker, annotation_date, event_family, event_type, annotation_date_role
  out_measure.csv, out_gate.csv, out_result.csv   COPY ... WITH CSV HEADER of the three Feature_07 tables

Usage: python3 -I validate_radar.py <dir> --dates 2026-11-03,2026-11-09 [--tickers 40 --seed 7]   (--tickers 0: all)
Sessions follow Feature 06: the dates a ticker traded on any board; a session without a Regular trade counts zero.
"""
import argparse
import csv
import math
import random
import sys
from collections import defaultdict

import numpy as np

TOL = 1e-9


def fnum(v):
    return None if v in ('', None) else float(v)


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def below_pct(cur, hist):
    return 100.0 * sum(1 for h in hist if h < cur) / len(hist)


def robust_z(cur, hist, min_n=200):
    vals = [h for h in hist if h is not None]
    if cur is None or len(vals) < min_n:
        return None
    med = float(np.median(vals))
    mad = float(np.median([abs(v - med) for v in vals]))
    if mad == 0:
        return None
    return (cur - med) / (1.4826 * mad)


def load(d):
    reg = defaultdict(dict)          # ticker -> date -> (fb, fs, db)
    sess = defaultdict(set)
    for r in csv.reader(open(f'{d}/f06.csv')):
        sess[r[1]].add(r[0])
        if r[2] == 'Regular':
            reg[r[1]][r[0]] = (float(r[3]), float(r[4]), float(r[6]))
    f3 = defaultdict(dict)
    for r in csv.reader(open(f'{d}/f03.csv')):
        if r[2] == 'Regular':
            f3[r[1]][r[0]] = (float(r[3]), float(r[4]), float(r[5]))
    f5 = defaultdict(lambda: defaultdict(list))   # ticker -> date -> [(broker, buy, sell)]
    for r in csv.reader(open(f'{d}/f05.csv')):
        if r[4] == 'Regular':
            f5[r[1]][r[0]].append((r[2], float(r[5]), float(r[6])))
    uni = {r[0] for r in csv.reader(open(f'{d}/universe.csv'))}
    ev = defaultdict(list)
    for r in csv.reader(open(f'{d}/events.csv')):
        if r[2] == 'CORPORATE_ACTION':
            ev[r[0]].append((r[1], r[3]))
    return reg, sess, f3, f5, uni, ev


def measures(ticker, reg, sess, f3):
    """Every measure of every Regular session of one ticker, keyed by date."""
    dates = sorted(sess[ticker])
    R, C = reg.get(ticker, {}), f3.get(ticker, {})
    n = len(dates)
    f = [R[d][0] - R[d][1] if d in R else 0.0 for d in dates]
    t = [R[d][0] + R[d][2] if d in R else 0.0 for d in dates]
    tb3 = [C[d][0] if d in C else 0.0 for d in dates]
    no3 = [d in R and d not in C for d in dates]          # a Regular session without its Feature 03 row
    inst = [C[d][1] if d in C else 0.0 for d in dates]
    ret = [C[d][2] if d in C else 0.0 for d in dates]
    f5 = [None] * n; t5 = [None] * n; r5 = [None] * n; fl34 = [None] * n; u1 = [None] * n; u3 = [None] * n
    rows = {}
    for i in range(n):
        if i >= 4:
            f5[i] = sum(f[i - 4:i + 1]); t5[i] = sum(t[i - 4:i + 1])
            r5[i] = 100 * f5[i] / t5[i] if t5[i] > 0 else None
            tb = sum(tb3[i - 4:i + 1])
            whole = not any(no3[i - 4:i + 1])
            fl34[i] = 100 * (sum(inst[i - 4:i + 1]) - sum(ret[i - 4:i + 1])) / tb if tb > 0 and whole else None
        u1[i] = 100 * f[i] / t[i] if t[i] > 0 else None
        if i >= 20:
            adv = sum(t[i - 20:i]) / 20
            u3[i] = 100 * f[i] / adv if adv > 0 else None
    # the ratio's own history skips sessions without a ratio (A1: gaps are skipped)
    have = [i for i in range(n) if r5[i] is not None]
    pr5 = [None] * n
    for q, i in enumerate(have):
        if q >= 252:
            pr5[i] = below_pct(r5[i], [r5[j] for j in have[q - 252:q]])
    for i in range(n):
        if dates[i] not in R:
            continue
        m = {'s5_from': dates[i - 4] if i >= 4 else None, 'foreign_net_1d': f[i], 'total_buy_1d': t[i],
             'total_buy_5d': t5[i], 'foreign_net_5d': f5[i], 'foreign_ratio_5d': r5[i]}
        if i >= 4:
            w = f[i - 4:i + 1]
            m['buy_days_5d'] = sum(1 for x in w if x > 0)
            m['foreign_net_5d_max_day'] = max(w)
            m['foreign_net_5d_max_date'] = max((dates[i - 4 + k] for k in range(5) if w[k] == max(w)))
            tb = sum(tb3[i - 4:i + 1])
            if any(no3[i - 4:i + 1]):
                m['inst_net_5d'] = m['retail_net_5d'] = m['inst_share_5d'] = m['inst_buy_days_5d'] = None
            else:
                m['inst_net_5d'] = sum(inst[i - 4:i + 1]); m['retail_net_5d'] = sum(ret[i - 4:i + 1])
                m['inst_share_5d'] = 100 * m['inst_net_5d'] / tb if tb > 0 else None
                m['inst_buy_days_5d'] = sum(1 for x in inst[i - 4:i + 1] if x > 0)
        else:
            for k in ('buy_days_5d', 'foreign_net_5d_max_day', 'foreign_net_5d_max_date', 'inst_net_5d', 'retail_net_5d',
                      'inst_share_5d', 'inst_buy_days_5d'):
                m[k] = None
        hist = f5[i - 252:i] if i >= 252 else None
        if hist is not None and all(h is not None for h in hist):
            m['foreign_net_5d_pct252'] = below_pct(f5[i], hist)
            sd = float(np.std(hist, ddof=1))
            m['foreign_net_5d_z252'] = (f5[i] - float(np.mean(hist))) / sd if sd > 0 else None
        else:
            m['foreign_net_5d_pct252'] = m['foreign_net_5d_z252'] = None
        m['foreign_ratio_5d_pct252'] = pr5[i]
        m['foreign_ratio_5d_prev'] = r5[i - 5] if i >= 5 else None
        m['foreign_ratio_5d_change'] = r5[i] - r5[i - 5] if i >= 5 and r5[i] is not None and r5[i - 5] is not None else None
        m['foreign_ratio_5d_pct252_prev'] = pr5[i - 5] if i >= 5 else None
        m['foreign_ratio_5d_pct252_change'] = (pr5[i] - pr5[i - 5]) if i >= 5 and pr5[i] is not None and pr5[i - 5] is not None else None
        m['fl34_5d'] = fl34[i]
        m['fl34_5d_prev'] = fl34[i - 5] if i >= 5 else None
        m['adv20_prev'] = sum(t[i - 20:i]) / 20 if i >= 20 else None
        m['foreign_ratio_1d'] = u1[i]
        m['net_vs_adv20'] = u3[i]
        lo = max(0, i - 252)
        m['rz_foreign_ratio_1d'] = robust_z(u1[i], u1[lo:i])
        m['rz_net_vs_adv20'] = robust_z(u3[i], u3[lo:i])
        m['net_1d_pct252'] = below_pct(f[i], f[i - 252:i]) if i >= 252 else None
        rows[dates[i]] = m
    return rows


def type_b(values):
    """100 x (others strictly below) / (n - 1)."""
    n = len(values)
    if n < 2:
        return {k: None for k in values}
    return {k: 100.0 * sum(1 for w in values.values() if w < v) / (n - 1) for k, v in values.items()}


def cross_section(day, M, uni, f5):
    market = sorted({d for rows in M.values() for d in rows})
    last16 = set(d for d in market if d <= day)
    last16 = set(sorted(last16)[-16:])
    X = {}
    for tk, rows in M.items():
        if day not in rows:
            continue
        m = rows[day]
        x = {'g2_eligible': tk in uni and m['total_buy_5d'] is not None and sum(1 for d in rows if d in last16) >= 5}
        X[tk] = x
    pop = {tk: M[tk][day]['total_buy_5d'] for tk, x in X.items() if x['g2_eligible']}
    vals = np.array(list(pop.values()), dtype=float)
    cut = {'broad': float(np.percentile(vals, 50)), 'liquid': float(np.percentile(vals, 80))}
    gate = {'trade_date': day, 'universe_n': len(pop), 'broad_cut': cut['broad'], 'liquid_cut': cut['liquid']}
    for tk, x in X.items():
        for g in ('broad', 'liquid'):
            x[f'gate_{g}'] = bool(x['g2_eligible'] and pop[tk] >= cut[g])
    gate['broad_n'] = sum(x['gate_broad'] for x in X.values()); gate['liquid_n'] = sum(x['gate_liquid'] for x in X.values())
    # S3 from broker rows of the stock's own 5 sessions
    for tk, x in X.items():
        for k in ('s3_net_buyers', 's3_cr3', 's3_cr3_excess', 's3_intensity'):
            x[k] = None
        if not x['gate_broad']:
            continue
        lo = M[tk][day]['s5_from']
        net, buy = defaultdict(float), defaultdict(float)
        for d, recs in f5.get(tk, {}).items():
            if lo <= d <= day:
                for b, bv, sv in recs:
                    net[b] += bv - sv; buy[b] += bv
        if not net:
            continue
        pos = sorted((v for v in net.values() if v > 0), reverse=True)
        x['s3_net_buyers'] = len(pos)
        tot = sum(buy.values())
        if pos:
            x['s3_cr3'] = sum(pos[:3]) / sum(pos)
            x['s3_cr3_excess'] = x['s3_cr3'] - 3.0 / len(pos)
        x['s3_intensity'] = (sum(pos) / tot) if tot > 0 else None
    for g in ('broad', 'liquid'):
        s2 = {tk: M[tk][day]['foreign_ratio_5d_change'] for tk, x in X.items()
              if x[f'gate_{g}'] and M[tk][day]['foreign_net_5d'] > 0 and M[tk][day]['foreign_ratio_5d_change'] is not None}
        rk = type_b(s2)
        s3 = {tk: x for tk, x in X.items() if x[f'gate_{g}'] and x['s3_net_buyers'] is not None and x['s3_net_buyers'] >= 10
              and x['s3_cr3_excess'] is not None and x['s3_intensity'] is not None}
        edges = np.percentile([x['s3_net_buyers'] for x in s3.values()], [20, 40, 60, 80]) if s3 else []
        grp = {tk: sum(1 for e in edges if e < x['s3_net_buyers']) for tk, x in s3.items()}
        gr = {}
        for gi in set(grp.values()):
            gr.update(type_b({tk: s3[tk]['s3_cr3_excess'] for tk in s3 if grp[tk] == gi}))
        ir = type_b({tk: x['s3_intensity'] for tk, x in s3.items()})
        for tk, x in X.items():
            x[f's2_rank_{g}'] = rk.get(tk)
            x[f's3_group_{g}'] = grp.get(tk)
            x[f's3_group_rank_{g}'] = gr.get(tk)
            x[f's3_intensity_rank_{g}'] = ir.get(tk)
    return X, gate


# RADAR_PAGE_SPEC.md section 5 and PLAN.md RADAR (S6-delta thresholds provisional, option C)
LEVELS = ('loose', 'standard', 'strict')
TH = {
    'S1': {'C': (90, 95, 95)},
    'S2': {'C': (75, 90, 95)},
    'S3': {'B': (70, 80, 90), 'C': (60, 75, 90)},
    'S6': {'B': (3, 5, 10), 'C': (90, 95, 98)},
    'S6D_RATIO': {'B': (3, 5, 10), 'C': (90, 95, 98), 'D': (12, 20, 35)},
    'S6D_RANK': {'B': (3, 5, 10), 'C': (90, 95, 98), 'D': (40, 65, 90)},
    'S6D_BOTH': {'B': (3, 5, 10), 'C': (90, 95, 98), 'D': (12, 20, 35), 'D2': (40, 65, 90)},
    'S7': {'A': (10, 20, 40), 'D': (2, 5, 10)},      # D: SCREENER_LIBRARY.md 12.3 6a
}


def ge(v, t):
    return v is not None and v >= t


def conditions(fid, li, m, x, g):
    th = lambda c: TH[fid][c][li]
    if fid == 'S1':
        c = ge(m['foreign_net_5d_pct252'], th('C')) and (li < 2 or ge(m['foreign_net_5d_z252'], 2))
        return [m['foreign_net_5d'] > 0, ge(m['foreign_ratio_5d'], 5), c, ge(m['buy_days_5d'], 3)]
    if fid == 'S2':
        ch = m['foreign_ratio_5d_change']
        return [m['foreign_net_5d'] > 0, ch is not None and ch > 0, ge(x[f's2_rank_{g}'], th('C'))]
    if fid == 'S3':
        return [ge(x['s3_net_buyers'], 10), ge(x[f's3_group_rank_{g}'], th('B')), ge(x[f's3_intensity_rank_{g}'], th('C'))]
    if fid.startswith('S6'):
        base = [m['foreign_net_5d'] > 0, ge(m['foreign_ratio_5d'], th('B')), ge(m['foreign_ratio_5d_pct252'], th('C'))]
        if fid == 'S6':
            return base
        if fid == 'S6D_RATIO':
            return base + [ge(m['foreign_ratio_5d_change'], th('D'))]
        if fid == 'S6D_RANK':
            return base + [ge(m['foreign_ratio_5d_pct252_change'], th('D'))]
        return base + [ge(m['foreign_ratio_5d_change'], th('D')) and ge(m['foreign_ratio_5d_pct252_change'], th('D2'))]
    if fid == 'S7':
        a = m['fl34_5d'] is not None and m['fl34_5d_prev'] is not None and m['fl34_5d'] - m['fl34_5d_prev'] >= th('A')
        return [a, ge(m['fl34_5d'], 0), m['inst_net_5d'] is not None and m['inst_net_5d'] > 0, ge(m['inst_share_5d'], th('D'))]
    if fid == 'S8':
        z = [v for v in (m['rz_foreign_ratio_1d'], m['rz_net_vs_adv20']) if v is not None]
        return [bool(z) and max(z) >= 3, ge(m['net_vs_adv20'], 10), ge(m['net_1d_pct252'], 95)]
    raise KeyError(fid)


FILTERS = ('S1', 'S2', 'S3', 'S6', 'S6D_RATIO', 'S6D_RANK', 'S6D_BOTH', 'S7', 'S8')


def results(day, M, X):
    out = {}
    for tk, x in X.items():
        m = M[tk][day]
        for g in ('broad', 'liquid'):
            if not x[f'gate_{g}']:
                continue
            for fid in FILTERS:
                for li, lv in enumerate(LEVELS):
                    if fid == 'S8' and lv != 'standard':
                        continue
                    c = conditions(fid, 1 if fid == 'S8' else li, m, x, g)
                    req = c[:2] if fid == 'S8' else c
                    hit = all(req)
                    if hit or sum(1 for v in c if not v) == 1:     # near: every condition but one (S8: one of A, B)
                        out[(fid, lv, g, tk)] = ('hit' if hit else 'near', sum(1 << k for k, v in enumerate(c) if v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir'); ap.add_argument('--dates', required=True)
    ap.add_argument('--tickers', type=int, default=40); ap.add_argument('--seed', type=int, default=7)
    a = ap.parse_args()
    reg, sess, f3, f5, uni, ev = load(a.dir)
    days = a.dates.split(',')
    print('recalculating measures for', len(sess), 'tickers', flush=True)
    M = {tk: measures(tk, reg, sess, f3) for tk in sess}
    db_m = {(r['ticker'], r['trade_date']): r for r in csv.DictReader(open(f'{a.dir}/out_measure.csv'))}
    db_g = {r['trade_date']: r for r in csv.DictReader(open(f'{a.dir}/out_gate.csv'))}
    db_r = defaultdict(dict)
    for r in csv.DictReader(open(f'{a.dir}/out_result.csv')):
        db_r[r['trade_date']][(r['filter_id'], r['level'], r['gate'], r['ticker'])] = r
    bad = 0
    rnd = random.Random(a.seed)
    for day in days:
        X, gate = cross_section(day, M, uni, f5)
        for k, v in gate.items():
            if k != 'trade_date' and not close(float(v), fnum(db_g[day][k])):
                bad += 1; print('GATE', day, k, v, db_g[day][k])
        if a.tickers > 0:
            sample = rnd.sample(sorted(tk for tk, x in X.items() if x['g2_eligible']), a.tickers)
            sample += sorted(tk for tk in X if X[tk]['gate_liquid'])[:20]
        else:                                   # --tickers 0: every ticker with a measure row that date
            sample = sorted(X)
        for tk in sorted(set(sample)):
            row = db_m.get((tk, day))
            if row is None:
                bad += 1; print('MISSING ROW', tk, day); continue
            want = dict(M[tk][day]); want.update(X[tk])
            for k, v in want.items():
                got = row[k]
                if k.endswith('_date') or k == 's5_from':
                    ok = (v or '') == got
                elif k.startswith('g2') or k.startswith('gate_'):
                    ok = (got == 't') == bool(v)
                else:
                    ok = close(None if v is None else float(v), fnum(got))
                if not ok:
                    bad += 1
                    if bad < 60:
                        print('DIFF', day, tk, k, v, got)
        mine = results(day, M, X)
        market = sorted({d for rows in M.values() for d in rows if d < day})
        prev_day = market[-1] if market else None
        prev_hits = set()
        if prev_day:
            Xp, _ = cross_section(prev_day, M, uni, f5)
            prev_hits = {k for k, v in results(prev_day, M, Xp).items() if v[0] == 'hit'}
        want = {}
        for k, (st, met) in mine.items():
            if st == 'hit' or k not in prev_hits:          # a near that was a hit the date before is stored as left
                want[k] = (st, met)
        for k in prev_hits:
            if k not in mine or mine[k][0] != 'hit':
                fid, lv, g, tk = k
                if k in mine:
                    met = mine[k][1]
                    reason = next(c for b, c in enumerate('ABCD') if not met & (1 << b))
                else:
                    met = None
                    reason = 'gate' if tk in X else 'no_data'
                    if tk in X and X[tk][f'gate_{g}']:  # in the gate but two or more conditions short
                        c = conditions(fid, 1 if fid == 'S8' else LEVELS.index(lv), M[tk][day], X[tk], g)
                        met = sum(1 << b for b, v in enumerate(c) if v)
                        reason = next(ch for b, ch in enumerate('ABCD') if not met & (1 << b))
                want[k] = ('left', met, reason)
        theirs = {}
        for k, r in db_r[day].items():
            met = int(r['met']) if r['met'] != '' else None
            theirs[k] = (r['status'], met, r['left_reason']) if r['status'] == 'left' else (r['status'], met)
        for k in sorted(set(want) | set(theirs)):
            if want.get(k) != theirs.get(k):
                bad += 1
                if bad < 120:
                    print('RESULT', day, k, 'mine', want.get(k), 'db', theirs.get(k))
        # a run of days continues the previous date's run (checked against the stored chain)
        db_prev = db_r.get(prev_day, {})
        for k, r in db_r[day].items():
            if r['status'] == 'hit':
                p = db_prev.get(k)
                expect = (int(p['run_day']) + 1) if p and p['status'] == 'hit' and prev_day in db_r else 1
                if prev_day in db_r and int(r['run_day']) != expect:
                    bad += 1; print('RUN_DAY', day, k, r['run_day'], 'expected', expect)
        print(day, 'checked', len(set(sample)), 'tickers;', len(mine), 'hit/near rows', flush=True)
    print('DIFFERENCES', bad)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
