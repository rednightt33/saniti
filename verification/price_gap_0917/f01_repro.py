"""Read-only: the SELECT inside the live refresh_feature_01_stock_daily, run through pgweb for a sample of stocks
(or every stock with --all), against every stored Feature_01_Stock_Daily row of those stocks. Nothing is written."""
import json, random, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'terminal_api'))
import pgq
r = pgq.q("select pg_get_functiondef('public.refresh_feature_01_stock_daily'::regproc)")
body = r['rows'][0][0]
cols = re.search(r'INSERT INTO public\."Feature_01_Stock_Daily" \((.*?)\)\s*WITH', body, re.S).group(1)
cols = [c.strip() for c in cols.split(',')]
select = body[body.index('WITH source_rows AS ('):body.index('ON CONFLICT (ticker, date)')]
def run(tickers):
    arr = "ARRAY[%s]::text[]" % ','.join(f"'{t}'" for t in tickers)
    q = select.replace('p_tickers', arr).replace('p_changed_date', 'NULL::date')
    cmp = ' OR '.join(f'c.{x} IS DISTINCT FROM s.{x}' for x in cols if x not in ('ticker', 'date'))
    sqltext = f'''with calc as (select * from ({q}) as x({",".join(cols)}))
      select count(*) filter (where s.ticker is null) as only_calc, count(*) filter (where c.ticker is null) as only_stored,
             count(*) filter (where c.ticker is not null and s.ticker is not null) as both_,
             count(*) filter (where c.ticker is not null and s.ticker is not null and ({cmp})) as differ
      from calc c full join (select * from "Feature_01_Stock_Daily" where ticker = any({arr})) s using (ticker, date)'''
    sqltext = sqltext.replace('c.ticker is', 'c.date is').replace('s.ticker is', 's.close is')
    return pgq.q(sqltext)
allt = [x[0] for x in pgq.q('select distinct ticker from "Feature_01_Stock_Daily"' + ('' if '--all' in sys.argv[1:] else ' where date = \'2026-10-30\''))['rows']]
fixed = ['AHAP','BUVA','ENRG','FORU','PBSA','VKTR','BBCA','TLKM','GOTO','BBRI','WIFI']
sample = sorted(allt) if '--all' in sys.argv[1:] else fixed + random.Random(20261030).sample(sorted(set(allt) - set(fixed)), 49)
out = {'only_calc': 0, 'only_stored': 0, 'both': 0, 'differ': 0}
for i in range(0, len(sample), 10):
    r = run(sample[i:i + 10])
    if 'error' in r: raise SystemExit(r['error'][:500])
    a, b, c, d = r['rows'][0]
    out['only_calc'] += a; out['only_stored'] += b; out['both'] += c; out['differ'] += d
    print(sample[i:i + 10], r['rows'][0], r['_ms'], 'ms', flush=True)
print(json.dumps({'stocks': len(sample), **out}))
