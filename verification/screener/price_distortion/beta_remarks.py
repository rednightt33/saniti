"""EXEC-PRICE-DISTORTION F6, the beta check: the Screener's row remarks (badges) on the whole universe after the release.

Signs in as the owner through the beta's edge-bff (credentials read from edge-bff's Railway variables into memory, never
printed, as verification/screener/live_check_dev.py does), then runs one computation (no saved screen): every listed
stock with no price, liquidity, stale or price-break filter, one condition every stock with a close passes
(RSI(14) < 100, so its cells also show PRICE_BREAK_IN_LOOKBACK where RSI's effective window crosses a break). Writes OUT/rows.json
(each row's remarks and cell remarks) and prints, per remark kind, the tickers, and the named tickers' remarks.

Usage: python3 beta_remarks.py OUT [TICKER ...]"""
import gzip, json, re, subprocess, sys, time, urllib.request
from collections import defaultdict
from http.cookiejar import CookieJar
from pathlib import Path

SECRETS = set()
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
named = [t.upper() for t in sys.argv[2:]]
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
        'Content-Type': 'application/json', 'Origin': base, 'Accept-Encoding': 'gzip', **({'X-CSRF-Token': csrf} if csrf else {})})
    t = time.time()
    try:
        with opener.open(req, timeout=120) as r:
            raw, status, enc = r.read(), r.status, r.headers.get('Content-Encoding')
    except urllib.error.HTTPError as e:
        raw, status, enc = e.read(), e.code, e.headers.get('Content-Encoding')
    if enc == 'gzip':
        raw = gzip.decompress(raw)
    return status, (json.loads(raw) if raw else None), round((time.time() - t) * 1000)


s, _, _ = call('POST', '/api/v1/auth/sign-in', {'login': login, 'password': password})
if s != 200:
    raise SystemExit(f'sign-in failed ({s})')
s, sess, _ = call('GET', '/api/v1/auth/session')
csrf = (sess or {}).get('csrf_token', '')
WIDE = {'security_types': ['stock'], 'include_unclassified': True, 'price_min': None, 'adv20_min_idr': None,
        'min_history_bars': None, 'traded_on_eval_date': False, 'exclude_price_breaks': False, 'tickers': None,
        'metric_filters': []}
test = {'kind': 'value', 'metric': {'kind': 'indicator', 'indicator': 'I13', 'output': 'rsi'}, 'op': 'lt', 'value': 100}
body = {'schema_version': 1, 'client_order': {'page': f'pd-check-{int(time.time())}', 'seq': 1},
        'definition': {'universe': WIDE, 'conditions': [{'id': 'a', 'enabled': True, 'test': test}], 'logic': 'all'}}
s, ans, ms = call('POST', '/api/v1/screener/run', body)
if s != 200:
    raise SystemExit(f'run failed ({s}): {json.dumps((ans or {}).get("error"))[:300]}')
rows = ans.get('rows', [])
keep = [{'ticker': r['ticker'], 'status': r['status'], 'last_bar_date': r.get('last_bar_date'), 'remarks': r.get('remarks', []),
         'cell_remarks': [c.get('remark') for c in r.get('cells', []) if c.get('remark')]} for r in rows]
(out / 'rows.json').write_text(json.dumps({'ms': ms, 'versions': ans.get('versions'), 'data': ans.get('data'),
                                           'universe': ans.get('universe'), 'rows': keep}, indent=1))
by = defaultdict(set)
for r in keep:
    for m in r['remarks']:
        by[m['code'] + ('/' + m['kind'] if m.get('kind') else '') + ('/last' if m.get('last_session') else '')].add(r['ticker'])
print(json.dumps({'ms': ms, 'rows': len(keep), 'versions': ans.get('versions'), 'data': ans.get('data')}, default=str)[:600])
for k, ts in sorted(by.items()):
    print(k, len(ts), ' '.join(sorted(ts))[:900])
for t in named:
    r = next((x for x in keep if x['ticker'] == t), None)
    print(t, 'not in the rows' if r is None else json.dumps({'status': r['status'], 'remarks': r['remarks'],
                                                             'cell_remarks': r['cell_remarks']})[:700])
