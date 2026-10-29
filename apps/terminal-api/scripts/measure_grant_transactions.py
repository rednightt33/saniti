#!/usr/bin/env python3
"""EXEC-MU-RUNTIME T3 evidence: transactions and statements terminal-api sends to PostgreSQL per grant and per read.

Runs a terminal-api app package (this repository's, or an older one extracted with `git show`) in process against a
DISPOSABLE PostgreSQL built from the repository's terminal migrations (never the dev database), with an in-memory
bucket (one ticker, BBCA, with packs). It counts, from the server log (log_statement = 'all', lines of the login
terminal_api_login between markers the script writes), the BEGINs and the other statements of:

  grants: N x POST /bundle {ticker: BBCA, packs: true} with a known account (after a warm-up grant and read);
  reads:  N x GET /manifest/BBCA and N x GET /state.

Usage (the login's password in TERMINAL_DB_PASSWORD, never printed):
  measure_grant_transactions.py --app-dir DIR --host 127.0.0.1 --port 55611 --db terminal_t --log PG_LOG --label L
      [--service NAME] [--n 20]
The app is created with the gateway key (subscriber edge-owner@terminal.local) unless --service names a service whose
key is set (after Phase 1b only). Prints one JSON line.
"""
import argparse
import dataclasses
import json
import os
import re
import sys
import time


class MemoryBucket:
    """The Bucket interface main.py uses, in memory: one ticker with price, broker and events files and packs."""

    def __init__(self):
        sha = lambda c: c * 64
        price = {str(y): {'key': f'v1/price/BBCA/{y}.{sha("a")}.json.gz', 'sha256': sha('a'), 'bytes': 2000, 'rows': 240,
                          'first': f'{y}-01-02', 'last': f'{y}-12-30'} for y in range(2021, 2027)}
        broker = {str(y): {'key': f'v1/broker/BBCA/{y}.{sha("b")}.json.gz', 'sha256': sha('b'), 'bytes': 250_000,
                           'rows': 24000, 'first': f'{y}-01-02', 'last': f'{y}-12-30'} for y in range(2021, 2027)}
        events = {'all': {'key': f'v1/events/BBCA/all.{sha("c")}.json.gz', 'sha256': sha('c'), 'bytes': 9000, 'rows': 120,
                          'first': '2009-01-20', 'last': '2026-11-03'}}
        self.m = {'window': {'first_year': 2021, 'last_year': 2026}, 'datasets': {
            'price': {'data_through': '2026-10-27', 'files': price}, 'events': {'data_through': '2026-10-27', 'files': events},
            'broker': {'data_through': '2026-10-27', 'files': broker}},
            'packs': {'price': {'key': f'v1/pack/BBCA/price.{sha("d")}.json.gz', 'sha256': sha('d'), 'bytes': 42_106,
                                'rows': 2100},
                      'broker-archive': {'key': f'v1/pack/BBCA/broker-archive.{sha("e")}.json.gz', 'sha256': sha('e'),
                                         'bytes': 2_200_000, 'rows': 90_000, 'years': [2021, 2024]}}}

    def manifest(self, ticker):
        return self.m if ticker == 'BBCA' else None

    def state(self):
        return {'finished_at': '2026-10-28T12:58:02Z', 'price_through': '2026-10-28', 'broker_through': '2026-10-27',
                'broker_behind_sessions': 1, 'xsection': None, 'refs': None}

    def presign(self, key, ttl):
        return f'https://bucket.example/{key}?X-Amz-Expires={ttl}'

    def logo(self, ticker):
        return None


def marker(admin_url, text):
    import psycopg
    with psycopg.connect(admin_url, autocommit=True) as c:
        c.execute('SELECT %s::text AS mark', (text,))


def count(log_path, start, a, b):
    """BEGINs and other statements of terminal_api_login between the markers a and b (log from byte `start`)."""
    with open(log_path, encoding='utf-8', errors='replace') as f:
        f.seek(start)
        text = f.read()
    i, j = text.index(f"'{a}'"), text.index(f"'{b}'")
    begins = statements = 0
    for line in text[i:j].splitlines():
        if ' terminal_api_login ' not in line or not re.search(r'(statement|execute [^:]*): ', line):
            continue
        sql = re.split(r'(?:statement|execute [^:]*): ', line, maxsplit=1)[1].strip().upper()
        if sql == 'BEGIN':
            begins += 1
        elif sql not in ('COMMIT', 'ROLLBACK'):
            statements += 1
    return begins, statements


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-dir', required=True)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, required=True)
    ap.add_argument('--db', required=True)
    ap.add_argument('--log', required=True)
    ap.add_argument('--label', required=True)
    ap.add_argument('--service', default='')
    ap.add_argument('--n', type=int, default=20)
    a = ap.parse_args()
    if a.host not in ('127.0.0.1', 'localhost'):
        raise SystemExit('a disposable local server only')
    sys.path.insert(0, a.app_dir)
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app

    password = os.environ['TERMINAL_DB_PASSWORD']
    url = f'postgresql://terminal_api_login:{password}@{a.host}:{a.port}/{a.db}'
    admin_url = f'postgresql://postgres@{a.host}:{a.port}/postgres'
    proxy_key, service_key = 'g' * 40, 's' * 40
    fields = {f.name for f in dataclasses.fields(Settings)}
    extra = {'service_keys': ((a.service, service_key),)} if a.service and 'service_keys' in fields else {}
    settings = Settings(database_url=url, admin_key='k' * 40, bucket_name='b', bucket_endpoint='https://e',
                        bucket_region='auto', bucket_access_key_id='x', bucket_secret_access_key='y',
                        allowed_origins=('https://edge.example',), secure_cookie=False, proxy_key=proxy_key,
                        proxy_subscriber='edge-owner@terminal.local', **extra)
    key = service_key if extra else proxy_key
    start = os.path.getsize(a.log)
    tag = f'{a.label}-{int(time.time())}'
    with TestClient(create_app(settings, None, MemoryBucket()), headers={'x-terminal-proxy-key': key}) as client:
        ok = lambda r: r.status_code == 200 or sys.exit(f'{r.request.url.path}: {r.status_code} {r.text[:300]}')
        ok(client.get('/api/terminal/v1/manifest/BBCA'))                   # warm-up: account known, prune done
        ok(client.post('/api/terminal/v1/bundle', json={'ticker': 'BBCA', 'packs': True}))
        marker(admin_url, f'{tag}-grants')
        t0 = time.perf_counter()
        for _ in range(a.n):
            ok(client.post('/api/terminal/v1/bundle', json={'ticker': 'BBCA', 'packs': True}))
        grant_ms = (time.perf_counter() - t0) * 1000 / a.n
        marker(admin_url, f'{tag}-reads')
        t0 = time.perf_counter()
        for _ in range(a.n):
            ok(client.get('/api/terminal/v1/manifest/BBCA'))
            ok(client.get('/api/terminal/v1/state'))
        read_ms = (time.perf_counter() - t0) * 1000 / (2 * a.n)
        marker(admin_url, f'{tag}-end')
    time.sleep(0.3)
    g_tx, g_st = count(a.log, start, f'{tag}-grants', f'{tag}-reads')
    r_tx, r_st = count(a.log, start, f'{tag}-reads', f'{tag}-end')
    print(json.dumps({'label': a.label, 'caller': a.service or 'gateway', 'n': a.n,
                      'per_grant': {'transactions': g_tx / a.n, 'statements': g_st / a.n, 'ms_in_process': round(grant_ms, 2)},
                      'per_read': {'transactions': r_tx / (2 * a.n), 'statements': r_st / (2 * a.n),
                                   'ms_in_process': round(read_ms, 2)}}))


if __name__ == '__main__':
    main()
