"""EDGE Screener live check on Railway dev (EXEC-SCREENER, dev deploy of 2026-10-29): the deployed Screener's answers
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
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'edge-bff', '-e', 'dev', '--json'],
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
report['catalog'] = {'status': s, 'ms': ms, 'versions': (cat or {}).get('versions'), 'data': (cat or {}).get('data'),
                     'presets': [{k: p.get(k) for k in ('id', 'name', 'available', 'match_count', 'near_count')}
                                 for p in (cat or {}).get('presets', [])]}

WIDE = {'security_types': ['stock'], 'include_unclassified': True, 'price_min': None, 'adv20_min_idr': None,
        'min_history_bars': None, 'traded_on_eval_date': False, 'exclude_price_breaks': False, 'tickers': None,
        'metric_filters': []}
ind = lambda i, o, **p: {'kind': 'indicator', 'indicator': i, 'output': o, **({'params': p} if p else {})}
SCREENS = {
    'rsi14_lt_30': {'kind': 'value', 'metric': ind('I13', 'rsi'), 'op': 'lt', 'value': 30},
    'close_gt_sma20': {'kind': 'state', 'lhs': {'kind': 'price', 'field': 'close'}, 'op': 'gt', 'rhs': ind('I01', 'sma')},
    'macd_hist_gt_0': {'kind': 'value', 'metric': ind('I06', 'histogram'), 'op': 'gt', 'value': 0},
    'adx14_gt_25': {'kind': 'value', 'metric': ind('I07', 'adx'), 'op': 'gt', 'value': 25},
}
seq = 0
for name, test in SCREENS.items():
    seq += 1
    body = {'schema_version': 1, 'client_order': {'page': 'live-check', 'seq': seq},
            'definition': {'universe': WIDE, 'conditions': [{'id': 'a', 'enabled': True, 'test': test}], 'logic': 'all'}}
    s, ans, ms = call('POST', '/api/v1/screener/run', body)
    rows = (ans or {}).get('rows', [])
    (out / f'run_{name}.json').write_text(json.dumps({
        'status': s, 'ms': ms, 'error': (ans or {}).get('error') if s != 200 else None,
        'versions': (ans or {}).get('versions'), 'data': (ans or {}).get('data'), 'universe': (ans or {}).get('universe'),
        'conditions': (ans or {}).get('conditions'), 'match_count': (ans or {}).get('match_count'),
        'timings_ms': (ans or {}).get('timings_ms'),
        'rows': [{'ticker': r['ticker'], 'status': r['status'], 'last_bar_date': r['last_bar_date'],
                  'cells': [{k: c.get(k) for k in ('status', 'value', 'lhs', 'rhs', 'eval_date', 'reason')}
                            for c in r.get('cells', [])]} for r in rows]}, indent=1))
    report[name] = {'status': s, 'ms': ms, 'match_count': (ans or {}).get('match_count'),
                    'universe': (ans or {}).get('universe'), 'timings_ms': (ans or {}).get('timings_ms')}
(out / 'report.json').write_text(json.dumps(report, indent=1, default=str))
print(json.dumps(report, default=str)[:3000])
