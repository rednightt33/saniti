"""EXEC-WATCHLIST L6: independent recalculation of watchlist-stocks from PostgreSQL (read-only pgweb).

Every value of the file is compared with a query written here, not with the publisher's SQL: the universe, last close,
1D and 1M, the 30 trend closes, the 14 indicators (vs EMA recomputed in Python from close and the EMA), the corporate
actions of the window and the Radar screens of the Radar page's default board. Run on a file (the live one, or one built
by build_dev.py), and with --dates on files built here by the publisher module for older dates (the module's date
queries answered with the older date).

Usage: python3 verification/watchlist/validate_watchlist.py FILE.json [--older N]"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'apps/terminal-publisher'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import radar_formulas_doc as r  # noqa: E402

CHECKED, DIFFS = [0], []


def same(a, b, tol):
    CHECKED[0] += 1
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=tol)


def cmp(what, got, want, tol=1e-6):
    if not same(got, want, tol):
        DIFFS.append({'what': what, 'file': got, 'db': want})


def check(doc):
    P, B, R = doc['prices_through'], doc['broker_through'], doc['radar_date']
    q = r.query
    uni = q('SELECT "Ticker", "Company Name", "Sector" FROM public."IDX_Stock_Universe" WHERE "Security Type" = \'stock\' ORDER BY 1')
    CHECKED[0] += 1
    if [u[0] for u in uni] != doc['ticker'] or [u[1] for u in uni] != doc['name'] or [u[2] for u in uni] != doc['sector']:
        DIFFS.append({'what': 'universe', 'file': len(doc['ticker']), 'db': len(uni)})
    at = {t: i for i, t in enumerate(doc['ticker'])}
    f01 = {x[0]: x[1:] for x in q(f'SELECT ticker, close, return_1d_pct, return_20d_pct, return_5d_pct, return_60d_pct, volume_ratio_20d, '
                                   f'volatility_20d_ann_pct, drawdown_60d_pct FROM public."Feature_01_Stock_Daily" WHERE date = \'{P}\'')}
    f04 = {x[0]: x[1:] for x in q(f"SELECT ticker, rsi_14, macd_histogram, adx_14, close, ema_50, ema_200 FROM public.\"Feature_04_Technical_Indicator\" "
                                   f"WHERE trade_date = '{P}' AND timeframe = 'Daily' AND asset_type = 'equity'")}
    f06 = {x[0]: x[1:] for x in q(f"SELECT ticker, foreign_net_1d, foreign_net_5d, foreign_net_20d, foreign_net_percentile_5d_base252d "
                                   f"FROM public.\"Feature_06_Foreign_Domestic\" WHERE trade_date = '{B}' AND market_board = 'Regular'")} if B else {}
    v = doc['values']
    for t, i in at.items():
        a, b, c = f01.get(t, [None] * 8), f04.get(t, [None] * 6), f06.get(t, [None] * 4)
        for name, got, want, tol in (('last', doc['last'][i], a[0], 0.006), ('r1d', doc['r1d'][i], a[1], 6e-5), ('r1m', doc['r1m'][i], a[2], 6e-5),
                                     ('r5d', v['r5d'][i], a[3], 6e-5), ('r3m', v['r3m'][i], a[4], 6e-5), ('volr', v['volr'][i], a[5], 6e-5),
                                     ('vol20', v['vol20'][i], a[6], 6e-5), ('dd60', v['dd60'][i], a[7], 6e-5),
                                     ('rsi', v['rsi'][i], b[0], 6e-5), ('macdh', v['macdh'][i], b[1], 6e-5), ('adx', v['adx'][i], b[2], 6e-5),
                                     ('fn1', v['fn1'][i], c[0], 0.6), ('fn5', v['fn5'][i], c[1], 0.6), ('fn20', v['fn20'][i], c[2], 0.6),
                                     ('fp5', v['fp5'][i], c[3], 0.006)):
            cmp(f'{t} {name}', got, None if want is None else float(want), tol)
        close, e50, e200 = (None if x is None else float(x) for x in b[3:6])
        cmp(f'{t} ema50', v['ema50'][i], (close / e50 - 1) * 100 if close is not None and e50 else None, 6e-5)
        cmp(f'{t} ema200', v['ema200'][i], (close / e200 - 1) * 100 if close is not None and e200 else None, 6e-5)
    # trend: the 30 newest final IHSG dates up to P, each stock's final close on them
    dates = [x[0] for x in q(f"SELECT date::text FROM public.\"Price_Stock_Indonesia_IDX\" WHERE ticker = 'IHSG' AND timeframe = 'Daily' "
                             f"AND is_final AND date <= '{P}' ORDER BY date DESC LIMIT 30")][::-1]
    CHECKED[0] += 1
    if dates != doc['dates']:
        DIFFS.append({'what': 'trend dates', 'file': doc['dates'][:2], 'db': dates[:2]})
    closes = {(t, d): c for t, d, c in q(f"SELECT ticker, date::text, close FROM public.\"Price_Stock_Indonesia_IDX\" WHERE timeframe = 'Daily' "
                                         f"AND is_final AND date BETWEEN '{dates[0]}' AND '{dates[-1]}'")}
    for t, i in at.items():
        for j, d in enumerate(dates):
            want = closes.get((t, d))
            cmp(f'{t} trend {d}', doc['trend'][i][j], None if want is None else float(want), 0.006)
    # corporate actions after P up to 30 days, of universe stocks, as the Terminal's event markers read them
    ev = {}
    for t, a, d, role in q(f"SELECT ticker, event_type, annotation_date::text, coalesce(annotation_date_role, '') FROM public.idx_event_annotation "
                           f"WHERE event_family = 'CORPORATE_ACTION' AND annotation_date > '{P}' AND annotation_date <= date '{P}' + {doc['event_days']}"):
        if t in at and [a, d, role] not in ev.setdefault(t, []):
            ev[t].append([a, d, role])
    CHECKED[0] += 1
    if {t: sorted(x) for t, x in ev.items()} != {t: sorted(x) for t, x in doc['events'].items()}:
        DIFFS.append({'what': 'events', 'file': len(doc['events']), 'db': len(ev)})
    # Radar: default variants of the newest rule version, the page's default level and gate
    rows = q(f"SELECT r.ticker, f.column_label FROM public.\"Feature_07_Radar_Result\" r JOIN public.\"Feature_07_Radar_Filter\" f "
             f"ON f.filter_id = r.filter_id AND f.is_default_variant AND f.rule_version = (SELECT max(rule_version) FROM public.\"Feature_07_Radar_Filter\") "
             f"WHERE r.trade_date = '{R}' AND r.status = 'hit' AND r.level = 'standard' AND r.gate = 'broad'")
    rd = {}
    for t, lab in rows:
        rd.setdefault(t, set()).add(lab)
    CHECKED[0] += 1
    if {t: set(x) for t, x in doc['radar'].items()} != rd:
        DIFFS.append({'what': 'radar', 'file': len(doc['radar']), 'db': len(rd)})


def older(n):
    """Files built by the publisher module for the n market dates before the newest (date queries answered with them)."""
    import build_dev as B
    import watchlist as W
    m = 'IHSG'
    ps = [x[0] for x in r.query(f"SELECT date::text FROM public.\"Price_Stock_Indonesia_IDX\" WHERE ticker = '{m}' AND timeframe = 'Daily' "
                                'AND is_final ORDER BY date DESC LIMIT 12')]
    out = []
    for p in ps[3:3 + 2 * n:2][:n]:
        b = r.query(f"SELECT max(trade_date)::text FROM public.\"Feature_06_Foreign_Domestic_INDEX\" WHERE ticker = '{m}' "
                    f"AND market_board = 'Regular' AND trade_date <= '{p}'")[0][0]
        rr = r.query(f"SELECT max(trade_date)::text FROM public.\"Feature_07_Radar_Result\" WHERE trade_date <= '{b}'")[0][0]

        def run(sql, params, p=p, b=b, rr=rr):
            if sql == W.RECENT_SQL:                   # the module still checks that the date is complete
                return [(p,)]
            if sql == W.BROKER_DATE_SQL:
                return [(b,)]
            if sql == W.RADAR_DATE_SQL:
                return [(rr,)]
            return B.run(sql, params)
        out.append(W.build(run))
    return out


if __name__ == '__main__':
    docs = [json.loads(Path(sys.argv[1]).read_text())]
    if '--older' in sys.argv:
        docs += older(int(sys.argv[sys.argv.index('--older') + 1]))
    for d in docs:
        before = len(DIFFS)
        check(d)
        print(d['prices_through'], d['broker_through'], d['radar_date'], 'differences', len(DIFFS) - before)
    print(json.dumps({'comparisons': CHECKED[0], 'differences': len(DIFFS), 'first': DIFFS[:10]}, default=str))
    sys.exit(1 if DIFFS else 0)
