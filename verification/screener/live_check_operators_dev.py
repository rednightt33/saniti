"""EDGE Screener operators live check on Railway dev (EXEC-SCREENER-FLOW-CANDLES unit A, PR #59, 2026-11-07); login part copied from live_check_dev.py (EXEC-SCREENER, dev deploy of 2026-10-29): the deployed Screener's answers
against the database.

Signs in as the owner through edge-bff (credentials read from edge-bff's Railway variables into memory, never printed,
the way verification/backtest/page_timing_dev.py does), then through the public EDGE API only:
  1. GET /api/v1/screener/catalog: data version, publication time, presets and their counts;
  2. POST /api/v1/screener/run, a wide universe (every listed stock, no price, liquidity, stale or price-break filter)
     and one VALUE condition per Feature 04 column that the parity record (verification/screener/F04_PARITY.md) maps to
     a default indicator: RSI(14) < 30, close above SMA(20) as a state, MACD histogram > 0, ADX(14) > 25;
  3. writes OUT/run_<name>.json (tickers, statuses and cell values) for the database comparison
     (`compare_f04.sql` beside it is run through pgweb, read-only).
Writes nothing to EDGE: a run is a computation (no saved screen, no watchlist change).

Usage: python3 live_check_dev.py OUT"""
import gzip, json, os, re, subprocess, sys, time, traceback, urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

SECRETS = set()


def safe_error(e, limit=300):
    text = str(e)
    for secret in sorted(SECRETS, key=len, reverse=True):
        text = text.replace(secret, '[redacted]')
    text = re.sub(r'(https?://[^\s?#"\']+)[?#][^\s"\']*', r'\1?[query]', text)
    return f'{type(e).__name__}: {text[:limit]}'


def uncaught(kind, e, tb):
    sys.stderr.write('Traceback (most recent call last):\n' + ''.join(traceback.format_tb(tb)) + safe_error(e) + '\n')


sys.excepthook = uncaught

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-p', '8aef1702-030b-49cb-9df7-5ac2e0a42691', '-s', 'edge-bff', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
base = 'https://' + v['RAILWAY_PUBLIC_DOMAIN']
login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD')
del v
SECRETS.update(x for x in (password,) if x)
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
        with opener.open(req, timeout=60) as r:
            raw = r.read(); status = r.status; enc = r.headers.get('Content-Encoding')
    except urllib.error.HTTPError as e:
        raw = e.read(); status = e.code; enc = e.headers.get('Content-Encoding')
    if enc == 'gzip':
        raw = gzip.decompress(raw)
    return status, (json.loads(raw) if raw else None), round((time.time() - t) * 1000)


s, _, _ = call('POST', '/api/v1/auth/sign-in', {'login': login, 'password': password})
if s != 200:
    raise SystemExit(f'sign-in failed ({s})')
SECRETS.update(c.value for c in jar if c.value)
s, sess, _ = call('GET', '/api/v1/auth/session')
csrf = (sess or {}).get('csrf_token', ''); SECRETS.update(x for x in (csrf,) if x)

report = {}
s, cat, ms = call('GET', '/api/v1/screener/catalog')
ops = (cat or {}).get('operators') or {}
report['catalog'] = {'status': s, 'ms': ms, 'engine': ((cat or {}).get('versions') or {}).get('screener_engine'),
                     'data': (cat or {}).get('data'), 'tests': sorted(t['key'] for t in ops.get('tests', [])),
                     'measures': sorted(m['fn'] for m in ops.get('measures', []))}
WIDE = {'security_types': ['stock'], 'include_unclassified': True, 'price_min': None, 'adv20_min_idr': None,
        'min_history_bars': None, 'traded_on_eval_date': False, 'exclude_price_breaks': False, 'tickers': None,
        'metric_filters': []}
rsi = {'kind': 'indicator', 'indicator': 'I13', 'output': 'rsi'}
val = lambda m, op, v, v2=None: {'kind': 'value', 'metric': m, 'op': op, 'value': v, **({'value2': v2} if v2 is not None else {})}
tr = lambda fn, of, **a: {'kind': 'transform', 'fn': fn, 'of': of, 'args': a}
SCREENS = {
    'rsi_percentile60_ge_90': val(tr('percentile', rsi, length=60), 'ge', 90),
    'rsi_zscore20_gt_2': val(tr('zscore', rsi, length=20), 'gt', 2),
    'rsi_gt_50_3_of_5': {'kind': 'window', 'mode': 'at_least', 'length': 5, 'count': 3, 'test': val(rsi, 'gt', 50)},
    'close_gt_sma20_streak_3': {'kind': 'window', 'mode': 'streak', 'length': 3, 'test': {'kind': 'state',
        'lhs': {'kind': 'price', 'field': 'close'}, 'op': 'gt', 'rhs': {'kind': 'indicator', 'indicator': 'I01', 'output': 'sma', 'params': {'length': 20}}}},
    'rsi_rank_ge_90': val({'kind': 'rank', 'of': rsi}, 'ge', 90),
    'rsi_outside_30_70': val(rsi, 'outside', 30, 70),
}
page, seq = f'live-ops-{int(time.time())}', 0
for name, test in SCREENS.items():
    seq += 1
    body = {'schema_version': 1, 'client_order': {'page': page, 'seq': seq},
            'definition': {'universe': WIDE, 'conditions': [{'id': 'a', 'enabled': True, 'test': test}], 'logic': 'all'}}
    s, ans, ms = call('POST', '/api/v1/screener/run', body)
    rows = (ans or {}).get('rows', [])
    report[name] = {'status': s, 'ms': ms, 'match_count': (ans or {}).get('match_count'),
                    'error': ((ans or {}).get('error') or {}).get('code') if s != 200 else None,
                    'sample': [(r['ticker'], (r.get('cells') or [{}])[0].get('value')) for r in rows[:3]]}
(out / 'report.json').write_text(json.dumps(report, indent=1, default=str))
print(json.dumps(report, default=str)[:3000])
