"""EXEC-PRICE-GAP-0917 S0/S6 (read-only, pgweb): md5 per stock of every Feature_01_Stock_Daily and
Feature_04_Technical_Indicator row before a date (whole rows as text, Feature 04 with calculated_at, so a rewrite of
equal values shows too). Run before and after the run; `compare` lists the stocks whose hash changed.

Usage: python snapshot_hashes.py take OUT.json [BEFORE_DATE]  |  python snapshot_hashes.py compare A.json B.json"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'terminal_api'))
import pgq  # noqa: E402


def sql(q):
    for attempt in range(6):
        r = pgq.q(q)
        if 'error' not in r:
            return r['rows']
        if 'too many connections' not in str(r['error']):
            break
        time.sleep(3 + 4 * attempt)
    raise SystemExit('pgweb: ' + str(r['error'])[:300])


def take(out, before='2026-09-17'):
    tickers = [r[0] for r in sql('select distinct ticker from "Feature_01_Stock_Daily" order by 1')]
    res = {'before': before, 'f01': {}, 'f04': {}}
    for i in range(0, len(tickers), 25):
        part = ','.join(f"'{t}'" for t in tickers[i:i + 25])
        for t, h, n in sql(f'''select ticker, md5(string_agg(f::text, '|' order by date)), count(*)
                               from "Feature_01_Stock_Daily" f where ticker in ({part}) and date < '{before}' group by ticker'''):
            res['f01'][t] = [h, n]
        for t, h, n in sql(f'''select ticker, md5(string_agg(f::text, '|' order by trade_date)), count(*)
                               from "Feature_04_Technical_Indicator" f where asset_type='equity' and timeframe='Daily'
                               and ticker in ({part}) and trade_date < '{before}' group by ticker'''):
            res['f04'][t] = [h, n]
    Path(out).write_text(json.dumps(res))
    print('stocks', len(tickers), 'f01 hashed', len(res['f01']), 'rows', sum(v[1] for v in res['f01'].values()),
          'f04 hashed', len(res['f04']), 'rows', sum(v[1] for v in res['f04'].values()))


def compare(a, b):
    A, B = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    for table in ('f01', 'f04'):
        changed = sorted(t for t in set(A[table]) | set(B[table]) if A[table].get(t) != B[table].get(t))
        print(table, 'stocks', len(B[table]), 'changed', len(changed), changed[:20])


if __name__ == '__main__':
    take(*sys.argv[2:]) if sys.argv[1] == 'take' else compare(*sys.argv[2:])
