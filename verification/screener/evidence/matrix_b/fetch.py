"""Read-only fetch of daily OHLCV + Feature 04 (atr_14, bb_*, close) for sample tickers -> data/<T>.json"""
import json, os, sys
sys.path.insert(0, '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/tools')
import pgq2
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'); os.makedirs(OUT, exist_ok=True)
F04 = ['atr_14', 'bb_upper_20', 'bb_middle_20', 'bb_lower_20', 'close', 'calculation_version']
def rows(sql):
    r = pgq2.q(sql)
    if 'error' in r: raise SystemExit(r['error'])
    return r['rows']
for t in sys.argv[1:]:
    assert t.isalnum() and t.isupper()
    p = rows(f"""select date::text, open::float8, high::float8, low::float8, close::float8, volume::float8 from public."Price_Stock_Indonesia_IDX"
        where ticker='{t}' and timeframe='Daily' and is_final order by date""")
    tbl = 'Feature_04_Technical_Indicator_INDEX' if t == 'IHSG' else 'Feature_04_Technical_Indicator'
    f = rows(f"""select trade_date::text, {', '.join(c + ('::float8' if c!='calculation_version' else '') for c in F04)} from public."{tbl}"
        where ticker='{t}' and timeframe='Daily' order by trade_date""")
    fd = {r[0]: r[1:] for r in f}
    d = {'ticker': t, 'T': [r[0][:10] for r in p]}
    for k, j in zip('OHLCV', range(1, 6)): d[k] = [r[j] for r in p]
    d['f04'] = {c: [fd.get(r[0], [None]*len(F04))[i] for r in p] for i, c in enumerate(F04)}
    d['f04_dates_equal'] = [r[0] for r in f] == [r[0] for r in p]
    json.dump(d, open(os.path.join(OUT, t + '.json'), 'w'))
    print(t, len(p), 'bars', d['T'][0], '..', d['T'][-1], 'f04 rows', len(f), 'dates equal', d['f04_dates_equal'], set(d['f04']['calculation_version']))
