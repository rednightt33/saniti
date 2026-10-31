"""(catalog_dump_dev.py, EXEC-TERMINAL-IND-CARDS 2026-10-31: the live Screener catalog's indicators and metrics with their
availability, for the final indicator workbook; read-only, the sign-in of live_check_dev.py below.)
EDGE Screener live check on Railway dev (EXEC-SCREENER, dev deploy of 2026-10-29): the deployed Screener's answers
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

s, cat, ms = call('GET', '/api/v1/screener/catalog')
keep = {'status': s, 'ms': ms, 'versions': (cat or {}).get('versions'), 'data': (cat or {}).get('data'),
        'indicators': [{k: i.get(k) for k in ('id', 'key', 'name', 'category', 'availability', 'reason')} for i in (cat or {}).get('indicators', [])],
        'metrics': [{k: m.get(k) for k in ('id', 'group', 'kind', 'label', 'availability', 'reason')} for m in (cat or {}).get('metrics', [])],
        'fundamentals': [{k: m.get(k) for k in ('id', 'group', 'kind', 'label', 'availability', 'reason')} for m in (cat or {}).get('fundamentals', [])],
        'keys': sorted((cat or {}).keys())}
(out / 'catalog.json').write_text(json.dumps(keep, indent=1, default=str))
print(json.dumps({'status': s, 'indicators': len(keep['indicators']), 'metrics': len(keep['metrics']),
                  'fundamentals': len(keep['fundamentals']), 'keys': keep['keys']}))
