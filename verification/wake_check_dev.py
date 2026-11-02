"""EXEC-U4-WORKERS live check (user go 2026-11-02: "Jalankan U4 sekarang"): the first EDGE request after screener-worker
and backtest-worker went to sleep, through the public EDGE API only, read-only (a screen and a catalog are computations;
nothing is saved).

Signs in as the owner through edge-bff (credentials read from edge-bff's Railway variables into memory, never printed,
as verification/screener/live_check_dev.py does), then:
  1. GET /api/v1/backtests/catalog (edge-bff asks backtest-worker /v1/catalog when its own copy is older than
     CATALOG_CACHE_SECONDS);
  2. POST /api/v1/screener/run, RSI(14) < 30 on the wide universe; a 503 SCREENER_NOT_READY (the worker is up and
     loading the publication) is asked again every 2 s, as the Screener page does, until it answers.
Prints and writes OUT/wake_check.json: each call's status, time and answer size. The wake itself (attempts, seconds) is in
edge-bff's `downstream_wake` log lines.

Usage: python3 wake_check_dev.py OUT"""
import gzip, json, subprocess, sys, time, urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'edge-bff', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
base = 'https://' + v['RAILWAY_PUBLIC_DOMAIN']
login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD')
del v
jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf = ''


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={
        'Content-Type': 'application/json', 'Origin': base, 'Accept-Encoding': 'gzip',
        **({'X-CSRF-Token': csrf} if csrf else {})})
    t = time.time()
    try:
        with opener.open(req, timeout=90) as r:
            raw = r.read(); status = r.status; enc = r.headers.get('Content-Encoding')
    except urllib.error.HTTPError as e:
        raw = e.read(); status = e.code; enc = e.headers.get('Content-Encoding')
    if enc == 'gzip':
        raw = gzip.decompress(raw)
    return status, (json.loads(raw) if raw else None), round(time.time() - t, 2), len(raw)


s, _, _, _ = call('POST', '/api/v1/auth/sign-in', {'login': login, 'password': password})
if s != 200:
    raise SystemExit(f'sign-in failed ({s})')
s, sess, _, _ = call('GET', '/api/v1/auth/session')
csrf = (sess or {}).get('csrf_token', '')

report = {'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
s, cat, sec, n = call('GET', '/api/v1/backtests/catalog')
report['backtest_catalog'] = {'status': s, 'seconds': sec, 'bytes': n,
                              'error': (cat or {}).get('error') if s != 200 else None}
print('backtest catalog', report['backtest_catalog'], flush=True)

WIDE = {'security_types': ['stock'], 'include_unclassified': True, 'price_min': None, 'adv20_min_idr': None,
        'min_history_bars': None, 'traded_on_eval_date': False, 'exclude_price_breaks': False, 'tickers': None,
        'metric_filters': []}
test = {'kind': 'value', 'metric': {'kind': 'indicator', 'indicator': 'I13', 'output': 'rsi'}, 'op': 'lt', 'value': 30}
page, seq, tries, t0 = f'wake-check-{int(time.time())}', 0, [], time.time()
while time.time() - t0 < 180:
    seq += 1
    body = {'schema_version': 1, 'client_order': {'page': page, 'seq': seq},
            'definition': {'universe': WIDE, 'conditions': [{'id': 'a', 'enabled': True, 'test': test}], 'logic': 'all'}}
    s, ans, sec, n = call('POST', '/api/v1/screener/run', body)
    tries.append({'status': s, 'seconds': sec, 'code': ((ans or {}).get('error') or {}).get('code') if s != 200 else None,
                  'rows': len((ans or {}).get('rows') or []) if s == 200 else None})
    print('screener run', tries[-1], flush=True)
    if s != 503:
        break
    time.sleep(2)
report['screener_run'] = {'tries': tries, 'total_seconds': round(time.time() - t0, 2)}
(out / 'wake_check.json').write_text(json.dumps(report, indent=1))
print(json.dumps({'backtest_catalog_s': report['backtest_catalog']['seconds'],
                  'screener_total_s': report['screener_run']['total_seconds'], 'screener_tries': len(tries)}))
