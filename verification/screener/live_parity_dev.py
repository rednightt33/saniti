"""EDGE Screener unit B live parity (2026-11-08): for a few stocks, the Screener's flow cells (P4 broker day files) against the same indicators computed the Terminal's way from the Terminal's own per-stock files (/api/terminal bundle: price pack, broker year files and archive), a path independent of the broker day files. Writes OUT/<ticker>.json for live_parity_compute.mjs; login part copied from live_check_dev.py (EXEC-SCREENER, dev deploy of 2026-10-29): the deployed Screener's answers
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

TICKERS = ['BBCA', 'BBRI', 'ASII', 'TPIA', 'PGAS', 'GOTO']
WIDE = {'security_types': ['stock'], 'include_unclassified': True, 'price_min': None, 'adv20_min_idr': None,
        'min_history_bars': None, 'traded_on_eval_date': False, 'exclude_price_breaks': False, 'tickers': TICKERS,
        'metric_filters': []}
flow = lambda m, **p: {'kind': 'flow', 'metric': m, 'params': p}
CONDS = {'fl24': {'kind': 'value', 'metric': flow('FL24'), 'op': 'gt', 'value': -1e9},
         'fl26': {'kind': 'value', 'metric': flow('FL26'), 'op': 'gt', 'value': -1e9},
         'fl11': {'kind': 'value', 'metric': flow('FL11'), 'op': 'gt', 'value': -1e9}}
page = f'live-parity-{int(time.time())}'
s, ans, ms = call('POST', '/api/v1/screener/run', {'schema_version': 1, 'client_order': {'page': page, 'seq': 1},
    'definition': {'universe': WIDE, 'conditions': [{'id': k, 'enabled': True, 'test': t} for k, t in CONDS.items()], 'logic': 'any'}})
cells = {r['ticker']: {c['id']: [c.get('value'), c.get('eval_date')] for c in r.get('cells', [])} for r in (ans or {}).get('rows', [])}
print('screen', s, ms, json.dumps(cells)[:600], flush=True)
for t in TICKERS:
    s, b, _ = call('POST', '/api/terminal/v1/bundle', {'ticker': t, 'datasets': ['price', 'broker'], 'packs': True})
    if s != 200:
        print('bundle', t, s, flush=True); continue
    docs = {}
    for name in ('price', 'broker'):
        docs[name] = []
        for f in (b.get('datasets', {}).get(name, {}) or {}).get('files', []):
            with urllib.request.urlopen(f['url'], timeout=60) as r:
                docs[name].append(json.loads(gzip.decompress(r.read())))
    (out / f'{t}.json').write_text(json.dumps({'ticker': t, 'screener': cells.get(t), 'price': docs['price'], 'broker': docs['broker']}))
    print('files', t, len(docs['price']), len(docs['broker']), flush=True)
