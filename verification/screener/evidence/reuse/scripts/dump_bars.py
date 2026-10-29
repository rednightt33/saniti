"""Dump daily final bars of sample tickers (read-only pgweb) to JSON for the warm-up measurement."""
import importlib.util, json, sys, random
spec = importlib.util.spec_from_file_location('pgq2', '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/tools/pgq2.py')
pg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pg)
allt = [x[0] for x in pg.q('select "Ticker" from public."IDX_Stock_Universe" where "Security Type"=\'stock\' order by 1')['rows']]
random.seed(11)
sample = ['BBCA', 'GOTO', 'MAPI', 'BBRI', 'TLKM', 'ANTM', 'BUMI', 'ADRO'] + random.sample([t for t in allt if t not in ('BBCA','GOTO','MAPI','BBRI','TLKM','ANTM','BUMI','ADRO')], 32)
out = {}
for k in range(0, len(sample), 10):
    part = sample[k:k+10]
    lst = ','.join("'%s'" % t for t in part)
    r = pg.q(f"""select ticker, date::date::text, open::float8, high::float8, low::float8, close::float8, volume::float8
      from public."Price_Stock_Indonesia_IDX" where timeframe='Daily' and is_final and ticker in ({lst}) order by ticker, date""")
    if 'error' in r: sys.exit(r['error'])
    for t, d, o, h, l, c, v in r['rows']:
        b = out.setdefault(t, {'T': [], 'O': [], 'H': [], 'L': [], 'C': [], 'V': []})
        b['T'].append(d); b['O'].append(o); b['H'].append(h); b['L'].append(l); b['C'].append(c); b['V'].append(v)
json.dump(out, open(sys.argv[1], 'w'))
print({t: len(b['T']) for t, b in out.items()})
