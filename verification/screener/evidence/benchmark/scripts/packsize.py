"""INFERENCE aid: rebuild each ticker's price pack the way apps/terminal-publisher/publisher.py does (price_doc +
dataset 'price-pack', json.dumps separators, gzip level 9, mtime 0; float8 values as Python floats) from the pulled rows,
and measure bytes. Not the published bytes themselves (publisher not run; units string copied from publisher.py:159-162)."""
import json, gzip, statistics, time
D = json.load(open('data/price_full.json'))
def doc(t, s, k=0):
    rows = list(zip(s['d'][k:], *[[None if x is None else float(x) for x in s[c][k:]] for c in 'ohlcv']))
    names = ['d', 'o', 'h', 'l', 'c', 'v']
    return {'schema_version': 1, 'dataset': 'price', 'ticker': t, 'year': None,
            'units': {'o': 'IDR per share (index points for an index)', 'v': 'shares'},
            'columns': names, **{n: [r[i] for r in rows] for i, n in enumerate(names)}, 'dataset': 'price-pack'}
def enc(d):
    raw = json.dumps(d, separators=(',', ':'), allow_nan=False).encode()
    return len(raw), len(gzip.compress(raw, compresslevel=9, mtime=0))
t0 = time.time(); full = {}; last750 = {}
for t, s in D.items():
    full[t] = enc(doc(t, s)); last750[t] = enc(doc(t, s, max(0, len(s['d']) - 750)))
el = time.time() - t0
def summ(m):
    g = [v[1] for v in m.values()]; r = [v[0] for v in m.values()]
    return {'tickers': len(g), 'gzip_total_mb': round(sum(g) / 1e6, 2), 'raw_total_mb': round(sum(r) / 1e6, 2), 'gzip_median_kb': round(statistics.median(g) / 1e3, 1),
            'gzip_p90_kb': round(sorted(g)[int(len(g) * 0.9)] / 1e3, 1), 'gzip_max_kb': round(max(g) / 1e3, 1), 'max_ticker': max(m, key=lambda k: m[k][1])}
out = {'full_history_pack': summ(full), 'last_750_bars_pack': summ(last750), 'build_seconds_python': round(el, 1)}
json.dump(out, open('results/packsize.json', 'w'), indent=1); print(json.dumps(out, indent=1))
