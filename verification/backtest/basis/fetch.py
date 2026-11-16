"""EXEC-BACKTEST-REVAMP P9 (option A, user 2026-11-16 "A dulu"; ERRORS M458 item 2): read-only measurement of the basis
between broker prices and published prices around each price-affecting corporate action. For each action of TYPE with
its ex date in the years given, the Regular-board broker VWAP ((buy + sell value) / (100 x (buy + sell lots))) and the
published high, low and close on each session from 21 days before to 21 days after the ex date, through the pgweb
service's read-only role (credentials from the environment, as export.sh). Only SELECT statements are sent; one small
statement per action (the pgweb statement timeout is 30 s).
  PGWEB_HOST=<host> PGWEB_AUTH=<user:password> python3 -I fetch.py OUTDIR TYPE YEAR_FROM YEAR_TO
analyse.py reads the files written here."""
import json, os, subprocess, sys
S, typ, y0, y1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
def q(sql):
    out = subprocess.run(['curl', '-sS', '-m', '120', '-u', os.environ['PGWEB_AUTH'], '--data-urlencode', f'query={sql}',
                          f'https://{os.environ["PGWEB_HOST"]}/api/query'], capture_output=True, text=True).stdout
    d = json.loads(out)
    if 'rows' not in d: raise SystemExit(f'{d}')
    return d['columns'], d['rows'] or []
_, evs = q(f"""SELECT ticker, to_char(ex_date,'YYYY-MM-DD'), to_char(cum_date,'YYYY-MM-DD'), ratio_old, ratio_new, amount_per_share FROM idx_event_annotation
 WHERE event_family='CORPORATE_ACTION' AND event_type='{typ}' AND ex_date BETWEEN '{y0}-01-01' AND '{y1}-12-31' AND ex_date <= '2026-11-06' ORDER BY ex_date""")
out = []
for (t, ex, cum, ro, rn, px) in evs:
    sql = f"""SELECT to_char(b."Date",'YYYY-MM-DD') d, (sum(b."Buy Value")+sum(b."Sell Value"))/nullif(100*(sum(b."Buy Lots")+sum(b."Sell Lots")),0) vwap, max(p.close) close, max(p.high) high, max(p.low) low
      FROM "IDX_Broker_Summary" b JOIN "Price_Stock_Indonesia_IDX" p ON p.ticker=b."Symbol" AND p.timeframe='Daily' AND p.date=b."Date"
      WHERE b."Symbol"='{t}' AND b."Date" BETWEEN date '{ex}' - 21 AND date '{ex}' + 21 AND b."Market Board"='Regular' GROUP BY 1 ORDER BY 1"""
    try: _, rows = q(sql)
    except SystemExit as e: out.append({'t': t, 'ex': ex, 'error': str(e)[:120]}); continue
    out.append({'t': t, 'ex': ex, 'cum': cum, 'old': ro, 'new': rn, 'px': px, 'days': rows})
json.dump(out, open(f'{S}/basis_{typ}_{y0}_{y1}.json', 'w'))
print(typ, y0, y1, len(out), 'events', sum(len(o.get('days', [])) for o in out), 'days', sum('error' in o for o in out), 'errors')
