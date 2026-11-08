"""EDGE Screener unit B live check on Railway dev (2026-11-08, after PR #60): the 20 front-end questions' wire definitions (verification/screener/q20_20261107/results.json, built through the page) run on real data; login part copied from live_check_dev.py (EXEC-SCREENER, dev deploy of 2026-10-29): the deployed Screener's answers
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

Q = json.load(open(Path(__file__).resolve().parent / 'q20_20261107' / 'results.json'))
report = {}
s, cat, ms = call('GET', '/api/v1/screener/catalog')
report['catalog'] = {'status': s, 'data': (cat or {}).get('data'), 'engine': ((cat or {}).get('versions') or {}).get('screener_engine')}
page, seq = f'live-q20-{int(time.time())}', 0
for k, x in Q.items():
    w = x.get('wire')
    if not w:
        continue
    d = w if isinstance(w, dict) else json.loads(w)
    seq += 1
    s, ans, ms = call('POST', '/api/v1/screener/run', {'schema_version': 1, 'client_order': {'page': page, 'seq': seq}, 'definition': d})
    rows = (ans or {}).get('rows', [])
    report[k] = {'title': x.get('title'), 'status': s, 'ms': ms, 'match_count': (ans or {}).get('match_count'),
                 'near': (ans or {}).get('near_count'), 'universe': ((ans or {}).get('universe') or {}).get('count'),
                 'error': ((ans or {}).get('error') or {}).get('code') if s != 200 else None,
                 'message': (((ans or {}).get('error') or {}).get('message') or '')[:220] if s != 200 else None,
                 'sample': [(r['ticker'], [(c.get('value'), c.get('eval_date')) for c in (r.get('cells') or [])][:3]) for r in rows[:3]]}
    print(k, json.dumps(report[k], default=str)[:400], flush=True)
(out / 'report.json').write_text(json.dumps(report, indent=1, default=str))
