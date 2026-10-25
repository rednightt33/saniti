#!/usr/bin/env python3
"""EXEC-TERMINAL-API Phase 7: validate terminal-api and the published files against PostgreSQL (read-only).

Needs RAILWAY_TOKEN (to read TERMINAL_ADMIN_KEY in memory, never printed) and the pgweb helper `pgq.py` next to it.
Creates (or reuses) the test subscriber validator@terminal.test with a random password held in memory, and disables
it at the end. Prints one line per check: PASS / FAIL with the evidence. Run from this folder.
"""
import datetime as dt
import gzip
import http.cookiejar
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

from pgq import q

API = 'https://terminal-api-dev.up.railway.app'
ORIGIN = API
BASE = f'{API}/api/terminal/v1'
EMAIL = 'validator@terminal.test'
results = []


def check(name, ok, evidence):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {evidence}", flush=True)


def admin_key():
    out = subprocess.run(['railway', 'variable', 'list', '-s', 'terminal-api', '-e', 'dev', '--json'],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)['TERMINAL_ADMIN_KEY']


class Client:
    def __init__(self, origin=ORIGIN):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.origin = origin

    def call(self, method, url, body=None, headers=None):
        h = {'content-type': 'application/json', 'origin': self.origin, **(headers or {})}
        req = urllib.request.Request(url, method=method, headers=h,
                                     data=json.dumps(body).encode() if body is not None else None)
        t = time.monotonic()
        try:
            with self.opener.open(req, timeout=60) as r:
                raw, status, hdrs = r.read(), r.status, r.headers
        except urllib.error.HTTPError as e:
            raw, status, hdrs = e.read(), e.code, e.headers
        ms = round((time.monotonic() - t) * 1000)
        try:
            data = json.loads(raw)
        except ValueError:
            data = raw
        return status, data, hdrs, ms


def download(url, origin=ORIGIN):
    req = urllib.request.Request(url, headers={'origin': origin})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), r.headers


def sql_one(text):
    r = q(text)
    if 'error' in r:
        raise RuntimeError(r['error'][:300])
    return r['rows']


def main():
    key = admin_key()
    adm = {'x-terminal-admin-key': key}
    c = Client()
    password = secrets.token_urlsafe(18)

    # ---- accounts (admin) ----------------------------------------------------------------------------------
    s, d, _, _ = c.call('GET', f'{BASE}/admin/subscribers', headers=adm)
    existing = [x for x in d.get('subscribers', []) if x['email'] == EMAIL]
    until = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()
    if existing:
        sid = existing[0]['subscriber_id']
        c.call('POST', f'{BASE}/admin/subscribers/{sid}', {'password': password, 'active': True, 'expires_at': until},
               headers=adm)
    else:
        s, d, _, _ = c.call('POST', f'{BASE}/admin/subscribers', {'email': EMAIL, 'display_name': 'Phase 7 validator',
                                                                   'password': password, 'expires_at': until},
                            headers=adm)
        check('admin add subscriber', s == 201, d)
        sid = d['subscriber_id']
    s, _, _, _ = Client().call('GET', f'{BASE}/admin/subscribers', headers={'x-terminal-admin-key': 'wrong'})
    check('admin route refuses a wrong key', s == 401, s)

    # ---- auth ----------------------------------------------------------------------------------------------
    s, d, _, _ = Client().call('GET', f'{BASE}/manifest/BBCA')
    check('data refused without a session', s == 401, (s, d))
    s, d, _, _ = Client().call('POST', f'{BASE}/auth/sign-in', {'email': EMAIL, 'password': 'not the password'})
    check('wrong password refused with a generic message', s == 401 and d['error'] == 'sign_in_failed', (s, d))
    s, d, _, _ = Client(origin='https://evil.example').call('POST', f'{BASE}/auth/sign-in',
                                                            {'email': EMAIL, 'password': password})
    check('sign-in from another origin refused', s == 403, (s, d))
    s, d, hdrs, _ = c.call('POST', f'{BASE}/auth/sign-in', {'email': EMAIL, 'password': password})
    cookie = hdrs.get('set-cookie', '')
    check('sign-in sets an HttpOnly Secure cookie', s == 200 and 'HttpOnly' in cookie and 'Secure' in cookie,
          (s, cookie.split(';', 1)[1] if ';' in cookie else cookie))

    # ---- manifest ------------------------------------------------------------------------------------------
    s, m, _, ms = c.call('GET', f'{BASE}/manifest/BBCA')
    check('manifest BBCA', s == 200 and 'broker' in m['datasets'] and 'price' in m['datasets'],
          {'window': m.get('window'), 'through': {k: v['data_through'] for k, v in m['datasets'].items()}, 'ms': ms})
    price_through = sql_one('SELECT max(date)::text FROM "Price_Stock_Indonesia_IDX" WHERE timeframe=\'Daily\' AND is_final')[0][0]
    broker_through = sql_one('SELECT max(trade_date)::text FROM "Feature_05_Foreign_Domestic_Broker_Detail"')[0][0]
    check('data_through equals the database', m['datasets']['price']['data_through'] == price_through and
          m['datasets']['broker']['data_through'] == broker_through,
          (m['datasets']['price']['data_through'], price_through, m['datasets']['broker']['data_through'], broker_through))
    s, _, _, _ = c.call('GET', f'{BASE}/manifest/IHSG')
    s2, m2, _, _ = c.call('GET', f'{BASE}/manifest/IHSG')
    check('IHSG has price only', s == 200 and 'broker' not in m2['datasets'], list(m2.get('datasets', {})))

    # ---- files: broker BBCA 2023 vs SQL --------------------------------------------------------------------
    s, f, _, ms = c.call('POST', f'{BASE}/files', {'ticker': 'BBCA', 'dataset': 'broker', 'years': [2023]})
    check('presigned broker file issued', s == 200 and f['expires_in_seconds'] == 120, (s, ms))
    body, hdrs = download(f['files'][0]['url'])
    import hashlib
    check('file sha256 equals the manifest', hashlib.sha256(body).hexdigest() == f['files'][0]['sha256'], len(body))
    check('bucket answers CORS for the terminal origin', hdrs.get('access-control-allow-origin') == ORIGIN,
          hdrs.get('access-control-allow-origin'))
    try:
        _, h2 = download(f['files'][0]['url'], origin='https://evil.example')
        evil = h2.get('access-control-allow-origin')
    except urllib.error.HTTPError as e:
        evil = f'HTTP {e.code}'
    check('bucket gives no CORS grant to another origin', evil in (None, '') or str(evil).startswith('HTTP'), evil)
    doc = json.loads(gzip.decompress(body))
    rows = list(zip(*(doc[k] for k in ('d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl'))))
    sql = sql_one('SELECT count(*), sum(buy_value)::float8, sum(sell_value)::float8, sum(buy_lots)::float8, '
                  'sum(sell_lots)::float8 FROM "Feature_05_Foreign_Domestic_Broker_Detail" '
                  "WHERE ticker='BBCA' AND trade_date BETWEEN '2023-01-01' AND '2023-12-31'")[0]
    got = (len(rows), sum(r[4] for r in rows), sum(r[5] for r in rows), sum(r[6] for r in rows), sum(r[7] for r in rows))
    close = all(abs(a - b) <= max(1e-6, abs(b) * 1e-12) for a, b in zip(got, sql))
    check('broker file = SQL (rows, Σbuy, Σsell, Σlots) BBCA 2023', close, {'file': got, 'sql': sql})
    check('ticker isolation (one ticker in the file)', doc['ticker'] == 'BBCA', doc['ticker'])
    check('dates ascending', [r[0] for r in rows] == sorted(r[0] for r in rows), (rows[0][0], rows[-1][0]))
    check('odd lots kept as decimals', any(r[7] != int(r[7]) for r in rows), 'fractional sell lots present')

    # filters computed the way the frontend will, against SQL
    def agg(day, inv=None, board=None, brokers=None):
        out = {}
        for r in rows:
            if r[0] != day or (inv and r[2] != inv) or (board and r[3] != board) or (brokers and r[1] not in brokers):
                continue
            out.setdefault(r[1], [0.0, 0.0])
            out[r[1]][0] += r[4]
            out[r[1]][1] += r[5]
        return out
    day = '2023-12-18'
    for inv, board in ((None, None), ('Foreign', None), ('Domestic', 'Regular'), (None, 'Nego')):
        mine = agg(day, inv, board)
        where = ''.join([f" AND investor_type='{inv}'" if inv else '', f" AND market_board='{board}'" if board else ''])
        ref = {b: [bv, sv] for b, bv, sv in sql_one(
            'SELECT broker, sum(buy_value)::float8, sum(sell_value)::float8 FROM '
            f"\"Feature_05_Foreign_Domestic_Broker_Detail\" WHERE ticker='BBCA' AND trade_date='{day}'{where} "
            'GROUP BY 1')}
        check(f'broker summary {day} investor={inv or "All"} board={board or "All"}', mine == ref,
              f'{len(mine)} brokers')
    # flow timeline: 3 brokers, Foreign, all boards; daily and cumulative vs SQL window function
    sel = {'AK', 'YP', 'ZP'}
    daily = {}
    for r in rows:
        if r[1] in sel and r[2] == 'Foreign':
            daily[r[0]] = daily.get(r[0], 0.0) + r[4] - r[5]
    ref = sql_one("SELECT trade_date::text, sum(net_value)::float8, sum(sum(net_value)) OVER (ORDER BY trade_date)::float8 "
                  "FROM \"Feature_05_Foreign_Domestic_Broker_Detail\" WHERE ticker='BBCA' AND trade_date BETWEEN "
                  "'2023-01-01' AND '2023-12-31' AND broker = ANY('{AK,YP,ZP}') AND investor_type='Foreign' "
                  'GROUP BY 1 ORDER BY 1')
    run, ok = 0.0, len(ref) == len(daily)
    for d_, net, cum in ref:
        run += daily.get(d_, 0.0)
        ok = ok and abs(daily.get(d_, 0.0) - net) < 1e-3 and abs(run - cum) < 1e-3
    check('flow timeline daily and cumulative (AK,YP,ZP Foreign) = SQL', ok, f'{len(ref)} sessions, end {run:,.0f}')

    # ---- files: price BBCA 2026 vs SQL ---------------------------------------------------------------------
    s, f, _, _ = c.call('POST', f'{BASE}/files', {'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]})
    body, _ = download(f['files'][0]['url'])
    p = json.loads(gzip.decompress(body))
    sql = sql_one("SELECT count(*), min(date)::text, max(date)::text, sum(close)::float8, sum(volume)::float8 FROM "
                  "\"Price_Stock_Indonesia_IDX\" WHERE ticker='BBCA' AND timeframe='Daily' AND is_final AND "
                  "date BETWEEN '2026-01-01' AND '2026-12-31'")[0]
    got = (len(p['d']), p['d'][0], p['d'][-1], sum(p['c']), sum(p['v']))
    check('price file = SQL BBCA 2026', got[:3] == tuple(sql[:3]) and abs(got[3] - sql[3]) < 1e-6 and
          abs(got[4] - sql[4]) < 1e-3, {'file': got, 'sql': sql})

    # ---- errors --------------------------------------------------------------------------------------------
    s, d, _, _ = c.call('POST', f'{BASE}/files', {'ticker': 'BBCA', 'dataset': 'price', 'years': [2015]})
    check('unpublished year answers 404 with the published years', s == 404 and 'published years' in d['message'], s)
    s, d, _, _ = c.call('GET', f'{BASE}/manifest/NOPE')
    check('unknown ticker 404', s == 404, d)
    s, d, _, _ = c.call('POST', f'{BASE}/files', {'ticker': 'BBCA', 'dataset': 'broker', 'years': [2023], 'x': 1})
    check('unknown field refused 400', s == 400, d.get('fields') if isinstance(d, dict) else d)

    # ---- history fallback ----------------------------------------------------------------------------------
    s, h, _, ms = c.call('GET', f'{BASE}/history/price?ticker=BBCA&from=2018-01-01&to=2020-12-31')
    sql = sql_one("SELECT count(*), sum(close)::float8 FROM \"Price_Stock_Indonesia_IDX\" WHERE ticker='BBCA' AND "
                  "timeframe='Daily' AND is_final AND date BETWEEN '2018-01-01' AND '2020-12-31'")[0]
    check('history price 2018-2020 = SQL', s == 200 and len(h['d']) == sql[0] and abs(sum(h['c']) - sql[1]) < 1e-6,
          {'rows': len(h.get('d', [])), 'sql': sql, 'ms': ms})
    s, h, _, ms = c.call('GET', f'{BASE}/history/broker?ticker=BBCA&from=2019-01-01&to=2019-12-31'
                                f'&brokers=YP&brokers=AK&investor_type=Foreign&market_board=Regular')
    sql = sql_one("SELECT count(*), sum(net_value)::float8 FROM \"Feature_05_Foreign_Domestic_Broker_Detail\" WHERE "
                  "ticker='BBCA' AND trade_date BETWEEN '2019-01-01' AND '2019-12-31' AND broker IN ('YP','AK') "
                  "AND investor_type='Foreign' AND market_board='Regular'")[0]
    net = sum(b - s_ for b, s_ in zip(h.get('bv', []), h.get('sv', [])))
    check('history broker 2019 YP+AK Foreign Regular = SQL', s == 200 and len(h['d']) == sql[0] and
          abs(net - sql[1]) < 1e-3, {'rows': len(h.get('d', [])), 'sql': sql, 'ms': ms})
    s, d, _, _ = c.call('GET', f'{BASE}/history/price?ticker=BBCA&from=2022-01-01&to=2022-02-01')
    check('history refuses dates inside the published window', s == 400 and d['error'] == 'use_published_files', s)

    # ---- audit (pgweb cannot read terminal.*; the admin list carries the audit summary) ---------------------
    s, d, _, _ = c.call('GET', f'{BASE}/admin/subscribers', headers=adm)
    me = [x for x in d['subscribers'] if x['email'] == EMAIL][0]
    check('access is audited (bytes_day > 0, last_access set)', me['bytes_day'] > 0 and me['last_access'], me)

    # ---- sign-out and disable ------------------------------------------------------------------------------
    s, _, _, _ = c.call('POST', f'{BASE}/auth/sign-out')
    s2, _, _, _ = c.call('GET', f'{BASE}/manifest/BBCA')
    check('sign-out ends the session', s == 200 and s2 == 401, (s, s2))
    c2 = Client()
    c2.call('POST', f'{BASE}/auth/sign-in', {'email': EMAIL, 'password': password})
    c.call('POST', f'{BASE}/admin/subscribers/{sid}', {'active': False, 'disabled_reason': 'Phase 7 validator, done'},
           headers=adm)
    s, _, _, _ = c2.call('GET', f'{BASE}/manifest/BBCA')
    check('disabling the account ends its sessions', s == 401, s)

    failed = [n for n, ok in results if not ok]
    print(f'SUMMARY {len(results) - len(failed)}/{len(results)} PASS; failed: {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
