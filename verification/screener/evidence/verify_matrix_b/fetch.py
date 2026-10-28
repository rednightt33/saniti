# Independent fetch (verify_matrix_b): price bars + Feature 04 + Feature 01 for given tickers, read-only via pgweb.
import sys, json, os
sys.path.insert(0, '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/tools')
from pgq2 import q
D = os.path.dirname(os.path.abspath(__file__))
def rows(sql):
    r = q(sql)
    if 'error' in r: raise SystemExit(r['error'])
    return r['columns'], r['rows']
for t in sys.argv[1:]:
    assert t.isalnum()
    _, p = rows(f"""select to_char(date,'YYYY-MM-DD'), open::float8, high::float8, low::float8, close::float8, volume::float8
                    from "Price_Stock_Indonesia_IDX" where ticker='{t}' and is_final order by date""")
    _, f4 = rows(f"""select to_char(trade_date,'YYYY-MM-DD'), bb_upper_20::float8, bb_middle_20::float8, bb_lower_20::float8, atr_14::float8, close::float8
                     from "Feature_04_Technical_Indicator" where ticker='{t}' and timeframe='Daily' order by trade_date""")
    _, f1 = rows(f"""select to_char(date,'YYYY-MM-DD'), volume_avg_20d::float8, volume_ratio_20d::float8, volatility_20d_ann_pct::float8
                     from "Feature_01_Stock_Daily" where ticker='{t}' order by date""")
    out = dict(ticker=t, T=[r[0] for r in p], O=[r[1] for r in p], H=[r[2] for r in p], L=[r[3] for r in p], C=[r[4] for r in p], V=[r[5] for r in p],
               f4={r[0]: r[1:] for r in f4}, f1={r[0]: r[1:] for r in f1})
    json.dump(out, open(os.path.join(D, 'data', t + '.json'), 'w'))
    print(t, len(p), 'bars', len(f4), 'f04', len(f1), 'f01')
