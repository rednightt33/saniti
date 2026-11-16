"""EXEC-WATCHLIST L1: read cost of every query of the daily watchlist file on dev (EXPLAIN (ANALYZE, BUFFERS), read-only
pgweb). Prints the execution time, shared buffers (hit + read, 8 kB pages) and the top plan line of each query.
Usage: python3 verification/watchlist/explain_dev.py > verification/watchlist/EXPLAIN_20261116.txt"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import radar_formulas_doc as r  # noqa: E402

q = r.query
P = q("SELECT max(date)::text FROM public.\"Price_Stock_Indonesia_IDX\" WHERE ticker = 'IHSG' AND timeframe = 'Daily' AND is_final")[0][0]
B = q("SELECT max(trade_date)::text FROM public.\"Feature_06_Foreign_Domestic_INDEX\" WHERE ticker = 'IHSG' AND market_board = 'Regular'")[0][0]
STOCK = '(SELECT "Ticker" FROM public."IDX_Stock_Universe" WHERE "Security Type" = \'stock\')'
DATES = (f"SELECT date FROM public.\"Price_Stock_Indonesia_IDX\" WHERE ticker = 'IHSG' AND timeframe = 'Daily' AND is_final "
         f"AND date <= '{P}' ORDER BY date DESC LIMIT 30")
Q = {
    'complete-date check (one date)': f"SELECT (SELECT count(*) FROM public.\"Price_Stock_Indonesia_IDX\" WHERE date = '{P}' AND timeframe = 'Daily' "
                                      f"AND is_final AND ticker IN {STOCK}), (SELECT count(*) FROM public.\"Feature_01_Stock_Daily\" WHERE date = '{P}' "
                                      f"AND ticker IN {STOCK}), (SELECT count(*) FROM public.\"Feature_04_Technical_Indicator\" WHERE trade_date = '{P}' "
                                      f"AND timeframe = 'Daily' AND asset_type = 'equity' AND ticker IN {STOCK})",
    'dates (30 IHSG sessions)': DATES,
    'universe': 'SELECT "Ticker", "Company Name", "Sector" FROM public."IDX_Stock_Universe" WHERE "Security Type" = \'stock\'',
    'feature 01 (one date)': f"SELECT ticker, close, return_1d_pct, return_5d_pct, return_20d_pct, return_60d_pct, volume_ratio_20d, "
                             f"volatility_20d_ann_pct, drawdown_60d_pct FROM public.\"Feature_01_Stock_Daily\" WHERE date = '{P}' AND ticker IN {STOCK}",
    'feature 04 (one date)': f"SELECT ticker, rsi_14, macd_histogram, adx_14, close, ema_50, ema_200 FROM public.\"Feature_04_Technical_Indicator\" "
                             f"WHERE trade_date = '{P}' AND timeframe = 'Daily' AND asset_type = 'equity' AND ticker IN {STOCK}",
    'feature 06 (one broker date)': f"SELECT ticker, foreign_net_1d, foreign_net_5d, foreign_net_20d, foreign_net_percentile_5d_base252d "
                                    f"FROM public.\"Feature_06_Foreign_Domestic\" WHERE trade_date = '{B}' AND market_board = 'Regular' AND ticker IN {STOCK}",
    'closes (30 dates)': f"SELECT ticker, date, close FROM public.\"Price_Stock_Indonesia_IDX\" WHERE date IN ({DATES}) AND timeframe = 'Daily' "
                         f"AND is_final AND ticker IN {STOCK}",
    'corporate actions (30 days)': f"SELECT ticker, event_type, annotation_date, annotation_date_role FROM public.idx_event_annotation "
                                   f"WHERE event_family = 'CORPORATE_ACTION' AND annotation_date > '{P}' AND annotation_date <= date '{P}' + 30 AND ticker IN {STOCK}",
    'corporate actions loaded at': "SELECT max(source_fetched_at) FROM public.idx_event_annotation WHERE event_family = 'CORPORATE_ACTION'",
    'radar (newest date)': 'SELECT DISTINCT ticker, filter_id FROM public."Feature_07_Radar_Result" WHERE status = \'hit\' AND trade_date = '
                           '(SELECT max(trade_date) FROM public."Feature_07_Radar_Result") AND level = \'standard\' AND gate = \'broad\' '
                           'AND rule_version = public.feature_07_rule_version()',
}
print(f'prices date {P}, broker date {B}')
tot_ms = tot_buf = 0
for name, sql in Q.items():
    plan = [x[0] for x in q('EXPLAIN (ANALYZE, BUFFERS) ' + sql)]
    ms = next(float(l.split(':')[1].split()[0]) for l in plan if l.startswith('Execution Time'))
    buf = next((l for l in plan if 'Buffers' in l), '')
    pages = sum(int(x.split('=')[1]) for x in buf.replace(',', ' ').split() if x.startswith(('hit=', 'read=')))
    tot_ms += ms; tot_buf += pages
    print(f'{name:32s} {ms:9.1f} ms {pages:8d} pages ({pages * 8 / 1024:6.1f} MB)  {plan[0].strip()[:90]}'.rstrip())
print(f'{"total":32s} {tot_ms:9.1f} ms {tot_buf:8d} pages ({tot_buf * 8 / 1024:6.1f} MB)')
