"""Read-only bounded pull of final daily OHLCV from public."Price_Stock_Indonesia_IDX" through pgweb (pgq2.q).
Chunks: one calendar half-year per query (each must finish < 30 s statement_timeout). Writes
data/raw_<chunk>.json (pgweb rows) and data/price_full.json (columnar per ticker) + pull_log.json."""
import importlib.util, json, os, sys, time
BASE = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad'
spec = importlib.util.spec_from_file_location('pgq2', BASE + '/tools/pgq2.py'); pg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pg)
OUT = BASE + '/audit/benchmark/data'
chunks = []
for y in range(2018, 2027):
    chunks.append((f'{y}-01-01', f'{y}-07-01')); chunks.append((f'{y}-07-01', f'{y+1}-01-01'))
log = []; per = {}
t_all = time.time()
for a, b in chunks:
    sql = ('select ticker, to_char(date,\'YYYY-MM-DD\') d, open::float8 o, high::float8 h, low::float8 l, close::float8 c, volume::float8 v '
           'from public."Price_Stock_Indonesia_IDX" where timeframe=\'Daily\' and is_final '
           f"and date >= '{a}' and date < '{b}' order by ticker, date")
    t = time.time(); r = pg.q(sql); wall = time.time() - t
    if 'error' in r:
        print('ERROR', a, b, r['error'][:300]); log.append({'from': a, 'to': b, 'error': r['error'][:300], 'ms': r['_ms']}); continue
    rows = r['rows']; nbytes = len(json.dumps(r))
    log.append({'from': a, 'to': b, 'rows': len(rows), 'ms': r['_ms'], 'json_bytes': nbytes, 'stats': r.get('stats')})
    print(a, b, len(rows), r['_ms'], 'ms', nbytes, 'bytes', flush=True)
    for tk, d, o, h, l, c, v in rows:
        s = per.setdefault(tk, {'d': [], 'o': [], 'h': [], 'l': [], 'c': [], 'v': []})
        s['d'].append(d); s['o'].append(o); s['h'].append(h); s['l'].append(l); s['c'].append(c); s['v'].append(v)
total_wall = time.time() - t_all
# ensure chronological per ticker (chunks are chronological, rows ordered within chunk)
for tk, s in per.items():
    assert all(s['d'][i] < s['d'][i + 1] for i in range(len(s['d']) - 1)), tk
with open(OUT + '/price_full.json', 'w') as f: json.dump(per, f, separators=(',', ':'))
# 3-year subset from 2023-10-01
sub = {}
for tk, s in per.items():
    k = next((i for i, d in enumerate(s['d']) if d >= '2023-10-01'), None)
    if k is None: continue
    sub[tk] = {c: s[c][k:] for c in s}
with open(OUT + '/price_3y.json', 'w') as f: json.dump(sub, f, separators=(',', ':'))
summ = {'chunks': log, 'total_wall_s': round(total_wall, 2), 'tickers_full': len(per), 'rows_full': sum(len(s['d']) for s in per.values()),
        'bytes_full_json': os.path.getsize(OUT + '/price_full.json'), 'tickers_3y': len(sub), 'rows_3y': sum(len(s['d']) for s in sub.values()),
        'bytes_3y_json': os.path.getsize(OUT + '/price_3y.json'), 'sum_query_ms': sum(c.get('ms', 0) for c in log)}
json.dump(summ, open(OUT + '/pull_log.json', 'w'), indent=1)
print(json.dumps({k: v for k, v in summ.items() if k != 'chunks'}, indent=1))
