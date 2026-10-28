"""Measure gzip JSON sizes of price docs shaped as publisher.py price_doc/encode, from read-only pgweb queries."""
import importlib.util, json, gzip, sys, random
spec = importlib.util.spec_from_file_location('pgq2', '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/tools/pgq2.py')
pg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pg)
def rows_of(tickers):
    lst = ','.join("'%s'" % t for t in tickers)
    r = pg.q(f"""select ticker, date::date::text, open::float8, high::float8, low::float8, close::float8, volume::float8
      from public."Price_Stock_Indonesia_IDX" where timeframe='Daily' and is_final and ticker in ({lst}) order by ticker, date""")
    if 'error' in r: sys.exit(r['error'])
    out = {}
    for t, d, o, h, l, c, v in r['rows']:
        out.setdefault(t, []).append((d, o, h, l, c, v))
    return out
def encode(doc):
    raw = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode()
    return len(raw), len(gzip.compress(raw, compresslevel=9, mtime=0))
def price_doc(t, rows):
    names = ['d', 'o', 'h', 'l', 'c', 'v']
    return {'schema_version': 1, 'dataset': 'price-pack', 'ticker': t, 'year': None,
            'units': {'o': 'IDR per share (index points for an index)', 'v': 'shares'}, 'columns': names,
            **{n: [r[i] for r in rows] for i, n in enumerate(names)}}
tick = pg.q('select "Ticker" from public."IDX_Stock_Universe" order by 1')['rows']
allt = [x[0] for x in tick]
random.seed(7)
sample = ['BBCA', 'GOTO', 'IHSG', 'MAPI', 'BBRI'] + random.sample([t for t in allt if t not in ('BBCA','GOTO','IHSG','MAPI','BBRI')], 25)
data = rows_of(sample)
tot_rows = tot_gz = 0
print('ticker rows raw gz | last260 gz | last520 gz')
for t in sample:
    rows = data.get(t, [])
    if not rows: print(t, 'no rows'); continue
    raw, gz = encode(price_doc(t, rows))
    _, g260 = encode(price_doc(t, rows[-260:])); _, g520 = encode(price_doc(t, rows[-520:]))
    tot_rows += len(rows); tot_gz += gz
    print(t, len(rows), raw, gz, '|', g260, '|', g520)
print('bytes per row (gz, full packs):', round(tot_gz / tot_rows, 2))
# cross-sectional recent window: one doc, all sample tickers, last K bars, columnar with a ticker column
for K in (260, 400, 520):
    rows = [(t,) + r for t in sample for r in data.get(t, [])[-K:]]
    names = ['t', 'd', 'o', 'h', 'l', 'c', 'v']
    doc = {'schema_version': 1, 'columns': names, **{n: [r[i] for r in rows] for i, n in enumerate(names)}}
    raw, gz = encode(doc)
    print(f'cross-section K={K}: tickers={len(sample)} rows={len(rows)} raw={raw} gz={gz} gz/row={gz/len(rows):.2f} extrapolated_845={gz/len(sample)*845/1e6:.2f} MB')
