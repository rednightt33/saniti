"""Verifier: read-only fetch of the full Daily/final price history for every ticker (batches of 30 tickers by indexed
ticker predicate) and Feature 04 rows since 2026-04-01. Writes data_all/price_<batch>.json and data_all/f04_<batch>.json."""
import importlib.util, json, os, time
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pgq2', '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/tools/pgq2.py')
pg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pg)
out = os.path.join(HERE, 'data_all'); os.makedirs(out, exist_ok=True)
r = pg.q('select distinct ticker from public."Price_Stock_Indonesia_IDX" where date >= \'2026-01-01\' order by 1')
tickers = [x[0] for x in r['rows']]
assert all(t.isalnum() for t in tickers)
print('tickers', len(tickers))
COLS = ['sma_20','sma_50','ema_12','ema_26','ema_50','ema_200','rsi_14','macd','macd_signal','macd_histogram','atr_14','bb_upper_20','bb_middle_20','bb_lower_20','adx_14']
for b in range(0, len(tickers), 30):
    chunk = tickers[b:b+30]; lst = ','.join(f"'{t}'" for t in chunk)
    p = pg.q(f"""select ticker, date::text, open::float8, high::float8, low::float8, close::float8, volume::float8
       from public."Price_Stock_Indonesia_IDX" where ticker in ({lst}) and timeframe='Daily' and is_final order by ticker, date""")
    f = pg.q(f"""select ticker, trade_date::text, {', '.join(c + '::float8' for c in COLS)} from public."Feature_04_Technical_Indicator"
       where ticker in ({lst}) and timeframe='Daily' and asset_type='equity' and trade_date >= '2026-04-01' order by ticker, trade_date""")
    if 'error' in p or 'error' in f: print('ERR', b, p.get('error'), f.get('error')); continue
    json.dump({'cols': p['columns'], 'rows': p['rows']}, open(os.path.join(out, f'price_{b:04d}.json'), 'w'))
    json.dump({'cols': f['columns'], 'rows': f['rows']}, open(os.path.join(out, f'f04_{b:04d}.json'), 'w'))
    print(b, len(p['rows']), len(f['rows']), p['_ms'], f['_ms'], flush=True)
