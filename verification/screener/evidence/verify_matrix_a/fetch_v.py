"""Independent read-only fetch (verifier): price + Feature 04 for sample tickers via pgweb. Writes data/<T>.json."""
import importlib.util, json, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pgq2', '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/tools/pgq2.py')
pg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pg)
COLS = ['sma_20','sma_50','ema_12','ema_26','ema_50','ema_200','rsi_14','macd','macd_signal','macd_histogram','atr_14','bb_upper_20','bb_middle_20','bb_lower_20','adx_14','close','calculation_version']
for t in sys.argv[1:]:
    assert t.isalnum()
    # price exactly as the publisher's PRICE_SQL filter (Daily, is_final), all history
    p = pg.q(f"""select date::text d, open::float8 o, high::float8 h, low::float8 l, close::float8 c, volume::float8 v
      from public."Price_Stock_Indonesia_IDX" where ticker='{t}' and timeframe='Daily' and is_final order by date""")
    f = pg.q(f"""select trade_date::text d, {', '.join(c + '::float8' if c!='calculation_version' else c for c in COLS)}
      from public."Feature_04_Technical_Indicator" where ticker='{t}' and timeframe='Daily' and asset_type='equity' order by trade_date""")
    if 'error' in p or 'error' in f: print(t, p.get('error'), f.get('error')); continue
    json.dump({'ticker': t, 'price': {'cols': p['columns'], 'rows': p['rows']}, 'f04': {'cols': f['columns'], 'rows': f['rows']}}, open(os.path.join(HERE, 'data', t + '.json'), 'w'))
    print(t, len(p['rows']), len(f['rows']), p['_ms'], f['_ms'])
