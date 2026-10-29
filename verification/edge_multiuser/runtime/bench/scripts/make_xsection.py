"""Build the proposed screener `price` xsection file (AUDIT.md TARGET ARCHITECTURE 6.5 "Phase 1 files": one columnar
document, columns t,d,o,h,l,c,v ordered by ticker then date, plus tickers: [{t, pack_sha256, first, last, rows}]) from
the real full history dump, with the publisher's encoding (json.dumps compact, floats as publisher SQL float8, gzip -9,
mtime 0). Scratch only; read-only on the repository. Usage: python3 -I make_xsection.py <price_full.json> <out_dir>"""
import gzip, hashlib, json, sys, time

src, out = sys.argv[1], sys.argv[2]
t0 = time.time()
D = json.load(open(src))
packs = json.load(open(src.rsplit('/', 1)[0] + '/packs/index.json'))
cols = {c: [] for c in 'tdohlcv'}
tickers = []
for t in sorted(D):
    s = D[t]
    n = len(s['d'])
    cols['t'] += [t] * n
    cols['d'] += s['d']
    for c in 'ohlcv':
        cols[c] += [None if x is None else float(x) for x in s[c]]
    tickers.append({'t': t, 'pack_sha256': packs[t]['sha256'], 'first': s['d'][0], 'last': s['d'][-1], 'rows': n})
doc = {'schema_version': 1, 'dataset': 'price-xsection', 'units': {'o': 'IDR per share (index points for an index)', 'v': 'shares'},
       'columns': ['t', 'd', 'o', 'h', 'l', 'c', 'v'], **cols, 'tickers': tickers}
raw = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode()
body = gzip.compress(raw, compresslevel=9, mtime=0)
open(f'{out}/xsection_price.json.gz', 'wb').write(body)
meta = {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'inflated_bytes': len(raw), 'rows': len(cols['t']),
        'tickers': len(tickers), 'build_s': round(time.time() - t0, 1)}
json.dump(meta, open(f'{out}/xsection_price.meta.json', 'w'), indent=1)
print(json.dumps(meta))
