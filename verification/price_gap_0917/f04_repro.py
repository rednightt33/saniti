"""Read-only: the Feature 04 engine from Git (pinned TA-Lib 0.6.8, numpy 2.3.5) on the stored price history,
against every stored Feature_04 row of the same stocks. Nothing is written."""
import json, random, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'features' / 'feature04')); sys.path.insert(0, str(ROOT / 'verification' / 'terminal_api'))
import pgq
from engine import FEATURE_COLUMNS, VERSION, calculate
def sql(q):
    for _ in range(4):
        r = pgq.q(q)
        if 'error' not in r: return r['columns'], r['rows']
    raise SystemExit(r['error'][:300])
_, allt = sql('''select distinct ticker from "Feature_04_Technical_Indicator" where asset_type='equity' and trade_date='2026-10-30' ''')
pool = sorted(t for (t,) in allt if t not in ('AHAP','BUVA','ENRG','FORU','PBSA','VKTR','BBCA','TLKM','GOTO','BBRI','WIFI'))
sample = ['AHAP','BUVA','ENRG','FORU','PBSA','VKTR','BBCA','TLKM','GOTO','BBRI','WIFI'] + random.Random(20261030).sample(pool, 19)
def same(a, b):
    if a is None or b is None: return a is None and b is None
    try: return abs(float(a) - float(b)) <= 1e-10 + 1e-12 * abs(float(b))
    except (TypeError, ValueError): return str(a) == str(b)
tot = {'stocks': 0, 'rows': 0, 'values': 0, 'differ': 0, 'exact_differ': 0, 'version_other': 0}
bad = []
for t in sample:
    cols, rows = sql(f'''select p.ticker,p.date::date::text as date,p.open,p.high,p.low,p.close,p.volume,p.timeframe,p.tradingview_symbol,p.source,
        p.query_date,p.ingestion_time,'equity'::text as asset_type,u."Security Type" as security_type,u."TradingView Symbol" as universe_tradingview_symbol
        from "Price_Stock_Indonesia_IDX" p join "IDX_Stock_Universe" u on u."Ticker"=p.ticker
        where p.ticker='{t}' and p.timeframe='Daily' and p.is_final order by p.date''')
    hist = [dict(zip(cols, r)) for r in rows]
    calc = {str(r['trade_date']): r for r in calculate(hist)}
    cols, rows = sql(f'''select trade_date::date::text as trade_date, calculation_version, {",".join(FEATURE_COLUMNS)}
        from "Feature_04_Technical_Indicator" where asset_type='equity' and ticker='{t}' and timeframe='Daily' order by trade_date''')
    tot['stocks'] += 1
    for r in rows:
        s = dict(zip(cols, r)); c = calc.get(s['trade_date'])
        tot['rows'] += 1; tot['version_other'] += s['calculation_version'] != VERSION
        if c is None: bad.append((t, s['trade_date'], 'not calculated')); continue
        for k in FEATURE_COLUMNS:
            tot['values'] += 1
            if not same(c[k], s[k]):
                tot['differ'] += 1
                bad.append((t, s['trade_date'], k, c[k], s[k]))
            elif c[k] != s[k] and not (isinstance(c[k], float) and float(s[k]) == c[k]):
                tot['exact_differ'] += 1
    print(t, len(rows), 'rows', flush=True)
print(json.dumps(tot)); json.dump(bad, open("f04_diffs.json","w"), default=str); from collections import Counter; print(Counter((b[0], b[1][:4], b[2]) for b in bad if len(b) > 3)); print("latest diff date", max((b[1] for b in bad), default=None))
