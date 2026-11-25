"""EXEC-PRICE-DISTORTION F6, the beta check of the Backtest: a single-stock run with a Flow entry condition over a
corporate action, and the trades' flags.distortions and the result's warnings.

Signs in as the owner through the beta's edge-bff (credentials read from edge-bff's Railway variables into memory, never
printed), submits one backtest per named ticker (POST /api/v1/backtests; each counts as a trial of its strategy line,
decision K3, as any run does), follows it to its end and reads /result. Prints per ticker: the state, the trades, the
trades with a distortion flag and their kinds, the warnings' codes. Writes OUT/<ticker>.json (the trades' dates and flags).

Usage: python3 beta_backtest.py OUT FROM TO TICKER [TICKER ...]"""
import gzip, json, subprocess, sys, time, urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
start, end, tickers = sys.argv[2], sys.argv[3], [t.upper() for t in sys.argv[4:]]
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-p', '8aef1702-030b-49cb-9df7-5ac2e0a42691', '-s', 'edge-bff',
                               '-e', 'dev', '--json'], capture_output=True, text=True, timeout=60, check=True).stdout)
base = 'https://' + v['RAILWAY_PUBLIC_DOMAIN']
login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD')
del v
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
csrf = ''


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={
        'Content-Type': 'application/json', 'Origin': base, 'Accept-Encoding': 'gzip', **({'X-CSRF-Token': csrf} if csrf else {})})
    try:
        with opener.open(req, timeout=120) as r:
            raw, status, enc = r.read(), r.status, r.headers.get('Content-Encoding')
    except urllib.error.HTTPError as e:
        raw, status, enc = e.read(), e.code, e.headers.get('Content-Encoding')
    if enc == 'gzip':
        raw = gzip.decompress(raw)
    return status, (json.loads(raw) if raw else None)


s, _ = call('POST', '/api/v1/auth/sign-in', {'login': login, 'password': password})
if s != 200:
    raise SystemExit(f'sign-in failed ({s})')
s, sess = call('GET', '/api/v1/auth/session')
csrf = (sess or {}).get('csrf_token', '')
# the entry: a Flow value read in lots (FL01 Transaction Size · Lot, the top buyers at its defaults) above its average, short
# holds so the run trades; FLOW_METRIC=FLxx:output picks another
import os
fm, fo = (os.environ.get('FLOW_METRIC') or 'FL01:buy').split(':')
# lots are compared with their own 20-session average (a fixed number is refused for lots): above it by 0 %
flow = {'id': 'f', 'kind': 'test', 'test': {'kind': 'value', 'metric': {'kind': 'transform', 'fn': 'vs_average',
        'of': {'kind': 'flow', 'metric': fm, 'output': fo, 'params': {}}, 'args': {'ma': 'SMA', 'length': 20, 'form': 'percent'}},
                                            'op': 'gt', 'value': 0}}
for t in tickers:
    body = {'schema_version': 1, 'mode': 'single', 'single': {'ticker': t, 'benchmark': 'buy_and_hold'},
            'period': {'from': start, 'to': end, 'oos_fraction': 0},
            'entry': {'logic': 'all', 'at_least': 1, 'window_bars': 1, 'conditions': [flow]},
            'exit': {'atr_length': 14, 'stop': {'mode': 'pct', 'pct': 0.07, 'atr_mult': 2, 'reward_risk_x': 2, 'line': {'indicator': 'I09', 'output': 'supertrend'}},
                     'take_profit': {'mode': 'pct', 'pct': 0.15, 'r_multiple': 2, 'atr_mult': 3},
                     'trailing': {'mode': 'none', 'pct': 0.05, 'chandelier_length': 22, 'chandelier_mult': 3, 'line': {'indicator': 'I01', 'output': 'sma'}},
                     'max_hold_bars': 5, 'signals': {'logic': 'any', 'conditions': []}},
            'sizing': {'capital_idr': 100e6, 'allocation_fraction': 1},
            'costs': {'buy_fee': 0.0015, 'sell_fee': 0.0025, 'slippage': 0.0005, 'skip_ara_open_gap': True, 'ara_gap_fraction': 0.2},
            'robustness': {'monte_carlo_runs': 0, 'seed': 7, 'sensitivity': False}}
    s, ans = call('POST', '/api/v1/backtests', body)
    if s not in (200, 201, 202):
        print(t, 'submit', s, json.dumps((ans or {}).get('error') or ans)[:400]); continue
    rid = ans.get('request_id') or ans.get('id')
    for _ in range(240):
        s, st = call('GET', f'/api/v1/backtests/{rid}')
        if (st or {}).get('state') in ('FINISHED', 'FAILED', 'CANCELLED'):
            break
        time.sleep(2)
    if st.get('state') != 'FINISHED':
        print(t, st.get('state'), json.dumps(st.get('error'))[:400]); continue
    s, res = call('GET', f'/api/v1/backtests/{rid}/result')
    trades = (res or {}).get('trades') or []
    marked = [x for x in trades if (x.get('flags') or {}).get('distortions')]
    kinds = sorted({d['kind'] for x in marked for d in x['flags']['distortions']})
    warn = sorted({w.get('code') for w in ((res or {}).get('meta') or {}).get('warnings', []) if isinstance(w, dict)})
    (out / f'{t}.json').write_text(json.dumps({'request_id': rid, 'trades': [{k: x.get(k) for k in ('entry_date', 'exit_date', 'flags')} for x in trades],
                                               'warnings': ((res or {}).get('meta') or {}).get('warnings')}, indent=1, default=str))
    print(t, 'FINISHED', 'trades', len(trades), 'marked', len(marked), 'kinds', kinds, 'warnings', warn)
