"""EXEC-OVERVIEW O1: read-only EXPLAIN (ANALYZE, BUFFERS) of every statement apps/terminal-publisher/overview.py runs,
in its current form, on dev through pgweb (verification/terminal_api/pgq.py). Prints a Markdown table (REHEARSAL.md).

  python3 verification/overview/explain_dev.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/terminal_api'))
sys.path.insert(0, str(ROOT / 'apps/terminal-publisher'))
from pgq import q  # noqa: E402
import overview as o  # noqa: E402

lit = lambda v: "'" + v + "'"
arr = lambda vs: "ARRAY[" + ",".join(lit(v) for v in vs) + "]::date[]"
need = o.SERIES_SESSIONS + o.VOL_BASE + o.VOL_WINDOW + 1
dates = [r[0] for r in q(o.DATES_SQL.replace('%s', "'IHSG'", 1).replace('%s', str(need)))['rows']][::-1]
series = dates[-o.SERIES_SESSIONS:]
sectors = [r[0] for r in q(o.SECTORS_SQL)['rows']]
body = open(ROOT / 'database/migrations/20261115_020_overview_stock_size.sql').read().split('AS $function$')[1].split('$function$')[0].replace('p_date', "DATE '2026-11-13'")
cases = {
  'DATES (593)': o.DATES_SQL % ("'IHSG'", need),
  'FEATURE_DATES (40)': o.FEATURE_DATES_SQL % (arr(dates[-40:]),),
  'F04_DATES (300)': o.F04_DATES_SQL % (arr(series),),
  'CLOSES (13 tickers, 593 dates)': o.CLOSES_SQL % ("ARRAY[" + ",".join(lit(t) for t in ['IHSG', 'LQ45', *sectors]) + "]", lit(dates[0]), lit(dates[-1])),
  'DAY (13 Nov)': o.DAY_SQL % ("'2026-11-13'",),
  'SIZE body (13 Nov)': body,
  'STOCK_FLOW (9 Nov)': o.STOCK_FLOW_SQL % ("'2026-11-09'",),
  'MARKET_FLOW': o.MARKET_FLOW_SQL % ("'IHSG'", lit(dates[0])),
  'BREADTH (1 date)': o.BREADTH_SQL % (arr(['2026-11-13']),),
  'BREADTH (5 dates)': o.BREADTH_SQL % (arr(series[-5:]),),
  'BREADTH (one chunk: 20 older dates)': o.BREADTH_SQL % (arr(series[100:100 + o.BREADTH_CHUNK]),),
  'INTRADAY 5m (1 session)': o.INTRADAY_SQL % ("'IHSG'", "'5m'", "'2026-11-13'", "'2026-11-13'"),
  'INTRADAY 1h (5 sessions)': o.INTRADAY_SQL % ("'IHSG'", "'1h'", lit(series[-5]), "'2026-11-13'"),
  'STAMP': o.STAMP_SQL % {'m': "'IHSG'", 'lo': lit(dates[-o.DAY_DATES])},
}
print('| Statement | Execution | Buffers (top node) | Seq scans |')
print('|---|---:|---|---|')
for name, sql in cases.items():
    r = q('EXPLAIN (ANALYZE, BUFFERS) ' + sql)
    if 'error' in r:
        print(f'| {name} | ERROR | {str(r["error"])[:120]} | |'); continue
    plan = [row[0] for row in r['rows']]
    ex = next((l for l in plan if 'Execution Time' in l), '').strip().replace('Execution Time: ', '')
    buf = next((l.strip() for l in plan if 'Buffers' in l), '').replace('Buffers: ', '')
    seq = sorted({l.split('Seq Scan on ')[1].split()[0] for l in plan if 'Seq Scan on ' in l})
    print(f'| {name} | {ex} | {buf[:70]} | {", ".join(seq) or "none"} |')
