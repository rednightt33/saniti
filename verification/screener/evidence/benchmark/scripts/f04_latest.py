"""Pull Feature_04 equity rows for the newest date (bounded: one trade_date, ~828 rows) for a parity spot check."""
import importlib.util, json
BASE = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad'
spec = importlib.util.spec_from_file_location('pgq2', BASE + '/tools/pgq2.py'); pg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pg)
r = pg.q('select ticker, to_char(trade_date,\'YYYY-MM-DD\') d, close, sma_20, sma_50, ema_12, ema_26, ema_50, ema_200, rsi_14, macd, macd_signal, macd_histogram, atr_14, bb_upper_20, bb_middle_20, bb_lower_20, adx_14 '
         'from public."Feature_04_Technical_Indicator" where asset_type=\'equity\' and timeframe=\'Daily\' and trade_date = date \'2026-10-27\'')
assert 'error' not in r, r.get('error')
cols = r['columns']; rows = [dict(zip(cols, x)) for x in r['rows']]
json.dump(rows, open(BASE + '/audit/benchmark/data/f04_20261027.json', 'w'))
print(len(rows), r['_ms'], 'ms')
