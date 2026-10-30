"""EXEC-TERMINAL-FLOW-IND S2 check (read-only): the published broker files against Feature 05, per ticker and year:
rows and the sums of bv, sv, bl, sl, bf, sf. Both the yearly files and the archive pack (rows of every year before the
last two). Also ref/brokers: the classification column and its counts against IDX_Broker_Profile.

The full publisher `verify` mode reads every file one after the other (about 0.55 s a bucket request); this samples:
the tickers given, or BBCA, TLKM, BBRI, GOTO, WIFI plus N random stocks (fixed seed, so a rerun checks the same ones).
Credentials are read from Railway into memory only and never printed; SQL goes through pgweb (read-only role).

Usage: python storage_freq_check.py [--random N] [TICKER ...]
"""
import argparse
import gzip
import json
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
from botocore.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))          # verification/terminal_api (pgq)
import pgq  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--random', type=int, default=30)
ap.add_argument('tickers', nargs='*')
args = ap.parse_args()

v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'terminal-publisher', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
s3 = boto3.client('s3', endpoint_url=v['TERMINAL_BUCKET_ENDPOINT'], region_name=v['TERMINAL_BUCKET_REGION'],
                  aws_access_key_id=v['TERMINAL_BUCKET_ACCESS_KEY_ID'], aws_secret_access_key=v['TERMINAL_BUCKET_SECRET_ACCESS_KEY'],
                  config=Config(s3={'addressing_style': 'virtual'}, signature_version='s3v4', read_timeout=60, max_pool_connections=32))
B = v['TERMINAL_BUCKET_NAME']
del v
raw = lambda k: s3.get_object(Bucket=B, Key=k if k.startswith('v1/') else 'v1/' + k)['Body'].read()
doc = lambda k: json.loads(gzip.decompress(raw(k)))


def sql(q):
    """pgweb allows a few connections per role (other read-only checks may hold some): a refusal is tried again"""
    for attempt in range(6):
        r = pgq.q(q)
        if 'error' not in r:
            return r['rows']
        if 'too many connections' not in str(r['error']):
            break
        time.sleep(3 + 4 * attempt)
    raise SystemExit('pgweb: ' + str(r['error'])[:300])


state = json.loads(raw('state.json'))
through = state['broker_through']
tick = doc('ref/tickers.json.gz')
stocks = [t for t, typ in zip(tick['ticker'], tick['type']) if typ == 'stock']
tickers = args.tickers or (['BBCA', 'TLKM', 'BBRI', 'GOTO', 'WIFI']
                           + random.Random(20261030).sample([t for t in stocks if t not in ('BBCA', 'TLKM', 'BBRI', 'GOTO', 'WIFI')], args.random))

COLS = ['bv', 'sv', 'bl', 'sl', 'bf', 'sf']


def tally(docs):
    """per year: rows and column sums; a null bf/sf is counted apart"""
    out = defaultdict(lambda: Counter())
    for d in docs:
        if d.get('columns', [])[-2:] != ['bf', 'sf']:
            out['_'] ['no_counts_files'] += 1
        for k in range(len(d['d'])):
            y = d['d'][k][:4]; c = out[y]; c['rows'] += 1
            for col in COLS:
                x = d[col][k] if col in d else None
                if x is None:
                    c[col + '_null'] += 1
                else:
                    c[col] += x
    return out


def published(t):
    """the yearly files (every year) per year; the archive pack (the years before the last two, the same rows again for
    the page's single download) must hold exactly the yearly files' rows of its years"""
    m = json.loads(raw(f'manifest/{t}.json'))
    yearly = tally([doc(f['key']) for f in m['datasets'].get('broker', {}).get('files', {}).values()])
    arch = (m.get('packs') or {}).get('broker-archive')
    if arch:
        a = tally([doc(arch['key'])])
        lo, hi = arch.get('years', [None, None])
        for y in sorted(k for k in set(a) | set(yearly) if k != '_' and lo is not None and lo <= int(k) <= hi):
            if a.get(y) != yearly.get(y):
                yearly['_']['archive_differs_' + y] += 1
    return yearly


def expected(t):
    rows = sql(f"""select extract(year from trade_date)::int, count(*), sum(buy_value)::float8, sum(sell_value)::float8,
                   sum(buy_lots)::float8, sum(sell_lots)::float8, sum(buy_freq)::bigint, sum(sell_freq)::bigint,
                   count(*) filter (where buy_freq is null), count(*) filter (where sell_freq is null)
                   from "Feature_05_Foreign_Domestic_Broker_Detail" where ticker = '{t}' and trade_date <= '{through}'
                   group by 1 order by 1""")
    return {str(r[0]): r[1:] for r in rows}


def check(t):
    got, want = published(t), expected(t)
    problems = []
    if got.get('_'):
        problems.append('; '.join(f'{k} {n}' for k, n in got['_'].items()))
    for y in sorted(set(want) | {k for k in got if k != '_'}):
        g, w = got.get(y, Counter()), want.get(y)
        if not w:
            problems.append(f'{y}: published, not in SQL'); continue
        n, bv, sv, bl, sl, bf, sf, bfn, sfn = w
        close = lambda a, b: abs((a or 0) - (b or 0)) <= 1e-6 * max(1, abs(a or 0), abs(b or 0))
        for name, a, b in (('rows', g['rows'], n), ('bv', g['bv'], bv), ('sv', g['sv'], sv), ('bl', g['bl'], bl),
                           ('sl', g['sl'], sl), ('bf', g['bf'], int(bf or 0)), ('sf', g['sf'], int(sf or 0)),
                           ('bf_null', g['bf_null'], bfn), ('sf_null', g['sf_null'], sfn)):
            if not close(a, b):
                problems.append(f'{y} {name}: published {a} SQL {b}')
    return t, len(want), sum(w[0] for w in want.values()), problems


with ThreadPoolExecutor(2) as ex:   # two pgweb connections at most
    results = list(ex.map(check, tickers))
bad = [r for r in results if r[3]]
for t, years, rows, problems in results:
    print(f"{t}: {years} years, {rows} rows, {'OK' if not problems else 'MISMATCH ' + '; '.join(problems[:4])}")

ref = doc('ref/brokers.json.gz')
prof = dict(sql('select broker_code, broker_classification from "IDX_Broker_Profile"'))
ref_cls = dict(zip(ref['code'], ref.get('classification', [None] * len(ref['code']))))
diff = {b: (ref_cls.get(b), prof.get(b)) for b in set(prof) | set(ref_cls) if ref_cls.get(b) != prof.get(b)}
print('ref/brokers columns', ref['columns'], 'classes', dict(Counter(ref_cls.values())), 'differences vs IDX_Broker_Profile', diff or 'none')
print(f"broker_through {through}; tickers {len(results)}, mismatching {len(bad)}")
sys.exit(1 if bad or diff else 0)
