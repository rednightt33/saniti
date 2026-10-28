"""Write the rebuilt price packs (same encoding as publisher.py encode/price_doc) to data/packs/<T>.json.gz + index.json
(sha256, bytes) so the core's real decode path (datafile.ts inflateVerified + priceSeries) can be timed. Scratch only."""
import json, gzip, hashlib
D = json.load(open('data/price_full.json')); idx = {}
for t, s in D.items():
    rows = list(zip(s['d'], *[[None if x is None else float(x) for x in s[c]] for c in 'ohlcv']))
    names = ['d', 'o', 'h', 'l', 'c', 'v']
    doc = {'schema_version': 1, 'dataset': 'price', 'ticker': t, 'year': None, 'units': {'o': 'IDR per share (index points for an index)', 'v': 'shares'},
           'columns': names, **{n: [r[i] for r in rows] for i, n in enumerate(names)}}
    doc['dataset'] = 'price-pack'
    body = gzip.compress(json.dumps(doc, separators=(',', ':'), allow_nan=False).encode(), compresslevel=9, mtime=0)
    open(f'data/packs/{t}.json.gz', 'wb').write(body); idx[t] = {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
json.dump(idx, open('data/packs/index.json', 'w')); print(len(idx), sum(v['bytes'] for v in idx.values()))
