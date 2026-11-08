"""EDGE Screener unit C live check (EXEC-SCREENER-FLOW-CANDLES P6, the 20 candlestick patterns), to run on Railway dev
after the merge and deploy; the login part as live_parity_dev.py (unit B), which follows live_check_dev.py.

Signs in as the owner through edge-bff (credentials read from edge-bff's Railway variables into memory, never printed
or written), then uses the public EDGE API only:
  1. GET /api/v1/screener/catalog: the publication and engine versions, the limits, the 20 Candlestick entries (the
     judge checks them against verification/screener/P6_CANDLES.md); GET /api/v1/screener/universe: the listed stocks
     with their last close, ADV20, bars and remarks (to choose the sample);
  2. POST /api/v1/screener/run on a wide universe (every listed stock; no price, liquidity, stale or price-break
     filter), pinned to the catalog's price_data: each of the 20 patterns as "Detected" (state, on the evaluated bar) and
     as "Detected within 3" at the defaults, then within 3 with the trend test off (where the pattern offers it, else
     the trend by change), with min_range_ticks 2 and 1, within 5 with a long trend_length (60), within 10 with the
     pattern's own parameters moved; two mixed screens (a candle with RSI(14) < 50, a candle with the flow FL11 > 0) and
     their other halves alone;
  3. a sample of stocks (liquid, illiquid, one near each price band boundary 200 / 500 / 2,000 / 5,000, a corporate
     action remark, a stale one, then a stock for every screen whose pattern no sample stock shows), whose own price
     bars it fetches the way the Terminal page does (POST /api/terminal/v1/bundle, datasets price with packs, then the
     presigned files; their sha256, bytes and rows checked);
  4. the catalog again (the publication must not have moved), then the judge live_candles_compute.mjs: the patterns
     recomputed by an independent implementation on those bars against the Screener's tickers, event dates, bars_ago
     and last event dates, plus the universe-wide relations. It writes OUT/parity.jsonl and OUT/report.json.
Writes nothing to EDGE (a run is a computation: no saved screen, item or watchlist change); signs out at the end. The
Terminal bundle is one ticker per call (terminal-api's /xsection batch of at most 16 names is the worker's route, never
called here); every call is paced (--pace, --bundle-pace); a 503, a 409 BUSY and LIMIT_EXCEEDED owner_cpu_budget are
retried after their Retry-After; a compute_budget refusal is recorded with its numbers (exit 4); the sample stays under
the Terminal's ticker quota (--max-sample, default 20; tickers_per_hour 30 by default, migration 20261025_100).

Usage (repository root; Node 18+ for the judge):
  python3 verification/screener/live_candles_dev.py OUT                       dev: URL and owner credentials from Railway
  EDGE_LOGIN=.. EDGE_INITIAL_PASSWORD=.. python3 verification/screener/live_candles_dev.py OUT --base-url URL
                                                                               another stack (a local one: the credentials
                                                                               of that stack, from the environment)
  node verification/screener/live_candles_compute.mjs OUT                     the judge again on a fetched OUT
Options: --max-sample N, --sample T1,T2 (always in the sample), --pace S (0.5), --bundle-pace S (1.0), --no-compare.
Exit: the judge's: 0 everything matches; 1 a mismatch, or a screen refused other than by a published limit; 2 the
publication changed during the check (run it again); 3 incomplete (a failed request, the Terminal quota, missing bars);
4 every answer matched but a published limit (compute_budget, ...) refused some screen (report.json limit_refused)."""
import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = '8aef1702-030b-49cb-9df7-5ac2e0a42691'          # PROJECT_CONTEXT.md, as live_parity_dev.py
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


def say(*parts):
    text = ' '.join(str(p) for p in parts)
    for secret in sorted(SECRETS, key=len, reverse=True):
        text = text.replace(secret, '[redacted]')
    print(text, flush=True)


# ---- the screens ------------------------------------------------------------------------------------------------------

WIDE = {'security_types': ['stock'], 'include_unclassified': True, 'price_min': None, 'adv20_min_idr': None,
        'min_history_bars': None, 'traded_on_eval_date': False, 'exclude_price_breaks': False, 'tickers': None,
        'metric_filters': []}
# each pattern's own parameters moved away from the defaults (screen <id>:own_w10)
_HAMMER = {'body_max_pct': 40, 'shadow_ratio': 1.5, 'short_shadow_pct': 15, 'trend': 'change', 'trend_length': 5}
_DOJI = {'doji_body_pct': 5, 'short_shadow_pct': 5, 'trend': 'change'}
OWN = {
    'hammer': _HAMMER, 'hanging_man': _HAMMER, 'inverted_hammer': _HAMMER, 'shooting_star': _HAMMER,
    'dragonfly_doji': _DOJI, 'gravestone_doji': _DOJI,
    'bullish_marubozu': {'long_body': 0, 'body_avg_length': 30, 'body_min_pct': 80},
    'bearish_marubozu': {'long_body': 0, 'body_avg_length': 30, 'body_min_pct': 80},
    'bullish_engulfing': {'trend': 'change', 'trend_length': 20}, 'bearish_engulfing': {'trend': 'change', 'trend_length': 20},
    'bullish_harami': {'inside_max_pct': 30, 'long_body': 1.5}, 'bearish_harami': {'inside_max_pct': 30, 'long_body': 1.5},
    'piercing_line': {'open_beyond': 'range', 'penetration_pct': 30}, 'dark_cloud_cover': {'open_beyond': 'range', 'penetration_pct': 30},
    'tweezer_bottom': {'tolerance_ticks': 0}, 'tweezer_top': {'tolerance_ticks': 0},
    'morning_star': {'star_overlap_pct': -10, 'penetration_pct': 30, 'star_body_pct': 50},
    'evening_star': {'star_overlap_pct': -10, 'penetration_pct': 30, 'star_body_pct': 50},
    'three_white_soldiers': {'body_min_pct': 60, 'short_shadow_pct': 10, 'long_body': 0.5},
    'three_black_crows': {'body_min_pct': 60, 'short_shadow_pct': 10, 'long_body': 0.5},
}
RSI_LT_50 = {'kind': 'value', 'metric': {'kind': 'indicator', 'indicator': 'I13', 'output': 'rsi'}, 'op': 'lt', 'value': 50}
FL11_GT_0 = {'kind': 'value', 'metric': {'kind': 'flow', 'metric': 'FL11', 'params': {}}, 'op': 'gt', 'value': 0}
MIXES = [('mix_rsi', 'tweezer_bottom', 'rsi14_lt_50', RSI_LT_50, False),
         ('mix_flow', 'bullish_engulfing', 'fl11_gt_0', FL11_GT_0, True)]


def pattern_ref(pid, params):
    return {'kind': 'pattern', 'type': pid, **({'params': params} if params else {})}


def candle_test(pid, kind, within, params):
    if kind == 'state':
        return {'kind': 'state', 'pattern': pattern_ref(pid, params)}
    return {'kind': 'event', 'signal': {'pattern': pattern_ref(pid, params)}, 'within': within}


def plan_screens(candles):
    """[(name, meta, definition)]: the candle screens of every catalog Candlestick entry, then the mixed ones."""
    out = []
    for m in candles:
        pid = m['id']
        trend = next((p.get('options') or [] for p in m.get('params', []) if p.get('key') == 'trend'), [])
        variants = [('default_state', 'state', None, {}), ('default_w3', 'event', 3, {}),
                    ('trend_alt_w3', 'event', 3, {'trend': 'none' if 'none' in trend else 'change'}),
                    ('tick2_w3', 'event', 3, {'min_range_ticks': 2}), ('tick1_w3', 'event', 3, {'min_range_ticks': 1}),
                    ('long_trend_w5', 'event', 5, {'trend': 'average', 'trend_length': 60}),
                    ('own_w10', 'event', 10, OWN.get(pid, {'trend_length': 20}))]
        for variant, kind, within, params in variants:
            meta = {'pattern': pid, 'variant': variant, 'kind': kind, 'within': within, 'params': params, 'candle_id': 'c'}
            out.append((f'{pid}:{variant}', meta, {'universe': WIDE, 'logic': 'all', 'conditions': [
                {'id': 'c', 'enabled': True, 'test': candle_test(pid, kind, within, params)}]}))
    ids = {m['id'] for m in candles}
    for name, pid, other, test, flow in MIXES:
        out.append((f'other:{other}', {'other': True, 'flow': flow}, {'universe': WIDE, 'logic': 'all', 'conditions': [
            {'id': 'o', 'enabled': True, 'test': test}]}))
        if pid not in ids:
            continue
        meta = {'pattern': pid, 'variant': name, 'kind': 'event', 'within': 3, 'params': {}, 'candle_id': 'c', 'flow': flow,
                'mix': {'candle_screen': f'{pid}:default_w3', 'other_screen': f'other:{other}', 'flow': flow}}
        out.append((f'{pid}:{name}', meta, {'universe': WIDE, 'logic': 'all', 'conditions': [
            {'id': 'c', 'enabled': True, 'test': candle_test(pid, 'event', 3, {})}, {'id': 'o', 'enabled': True, 'test': test}]}))
    return out


# ---- the client -------------------------------------------------------------------------------------------------------

class Edge:
    """The public EDGE API as the page calls it: session cookie, Origin and X-CSRF-Token; paced; JSON answers."""

    def __init__(self, base):
        self.base, self.csrf, self.last, self.calls = base, '', 0.0, {}
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def raw(self, method, path, body=None, pace=0.0):
        wait = pace - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            'Content-Type': 'application/json', 'Origin': self.base, 'Accept-Encoding': 'gzip',
            **({'X-CSRF-Token': self.csrf} if self.csrf else {})})
        t = time.time()
        try:
            with self.opener.open(req, timeout=90) as r:
                raw, status, headers = r.read(), r.status, r.headers
        except urllib.error.HTTPError as e:
            raw, status, headers = e.read(), e.code, e.headers
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            self.last = time.time()
            return 0, {'error': {'code': 'NETWORK', 'message': safe_error(e)}}, {}, round((time.time() - t) * 1000)
        self.last = time.time()
        if headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
        try:
            doc = json.loads(raw) if raw else None
        except ValueError:
            doc = {'error': {'code': 'NOT_JSON', 'message': raw[:200].decode('utf-8', 'replace')}}
        route = re.sub(r'[A-Z0-9]{2,12}$', '{t}', path)
        self.calls[f'{method} {route} {status}'] = self.calls.get(f'{method} {route} {status}', 0) + 1
        return status, doc, headers, round((time.time() - t) * 1000)

    def call(self, method, path, body=None, pace=0.0, retries=3):
        """One call; a 503, a 409 BUSY (the worker's queue) and a LIMIT_EXCEEDED of the owner's compute per minute
        (owner_cpu_budget, with retry_after_seconds) wait their Retry-After and are tried again (at most `retries`
        times); any other answer, a compute_budget refusal included, is returned as it is."""
        for attempt in range(retries + 1):
            status, doc, headers, ms = self.raw(method, path, body, pace)
            err = error_of(doc)
            retry = status == 503 or (status == 409 and err.get('code') == 'BUSY') or (
                err.get('code') == 'LIMIT_EXCEEDED' and (err.get('details') or {}).get('limit') == 'owner_cpu_budget')
            if not retry or attempt == retries:
                return status, doc, ms
            after = seconds(headers.get('Retry-After')) or seconds((err.get('details') or {}).get('retry_after_seconds')) or 2
            say(f'  {status} {err.get("code")}: waiting {after} s')
            time.sleep(min(after, 120))
        return status, doc, ms


def error_of(doc):
    e = (doc or {}).get('error') if isinstance(doc, dict) else None
    if isinstance(e, dict):
        return e
    if isinstance(e, str):
        return {'code': e, 'message': (doc or {}).get('message')}
    d = (doc or {}).get('detail') if isinstance(doc, dict) else None
    if isinstance(d, dict):
        return {'code': d.get('error') or d.get('code'), 'message': d.get('message')}
    return {}


def seconds(x):
    try:
        return max(1, min(3600, int(float(x))))
    except (TypeError, ValueError):
        return None


def credentials(args):
    """(base URL, login, password): the environment's EDGE_LOGIN and EDGE_INITIAL_PASSWORD with --base-url (a local
    stack); otherwise edge-bff's dev variables on Railway, read into memory only."""
    login, password = os.environ.get('EDGE_LOGIN'), os.environ.get('EDGE_INITIAL_PASSWORD')
    if args.base_url and login and password:
        return args.base_url.rstrip('/'), login, password
    v = json.loads(subprocess.run(['railway', 'variable', 'list', '-p', PROJECT, '-s', 'edge-bff', '-e', 'dev', '--json'],
                                  capture_output=True, text=True, timeout=60, check=True).stdout)
    base = (args.base_url or 'https://' + v['RAILWAY_PUBLIC_DOMAIN']).rstrip('/')
    login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD')
    del v
    return base, login, password


# ---- the parts written to OUT -------------------------------------------------------------------------------------------

def catalog_part(status, cat, ms):
    cat = cat if isinstance(cat, dict) else {}
    metrics = cat.get('metrics') or []
    return {'status': status, 'ms': ms, 'versions': cat.get('versions'), 'data': cat.get('data'),
            'error': error_of(cat) if status != 200 else None,
            'limits': [{k: x.get(k) for k in ('name', 'value', 'unit')} for x in cat.get('limits') or []],
            'metrics': [m for m in metrics if m.get('group') == 'Candlestick' or m.get('kind') == 'pattern'],
            'flow_fl11': next(({k: m.get(k) for k in ('id', 'availability', 'reason')} for m in metrics if m.get('id') == 'FL11'), None),
            'rsi_offered': any(i.get('id') == 'I13' for i in cat.get('indicators') or [])}


CELL_KEYS = ('id', 'status', 'value', 'eval_date', 'event_date', 'bars_ago', 'last_event_date', 'reason', 'remark')


def screen_part(name, meta, status, ans, ms):
    ans = ans if isinstance(ans, dict) else {}
    return {'name': name, **meta, 'status': status, 'ms': ms, 'error': error_of(ans) if status != 200 else None,
            'versions': ans.get('versions'), 'data': ans.get('data'), 'universe_counts': ans.get('universe'),
            'conditions': ans.get('conditions'), 'need': ans.get('need'), 'match_count': ans.get('match_count'),
            'near_count': ans.get('near_count'), 'timings_ms': ans.get('timings_ms'),
            'warnings': [w.get('code') for w in ans.get('warnings') or []],
            'rows': [{'ticker': r.get('ticker'), 'status': r.get('status'), 'last_bar_date': r.get('last_bar_date'), 'stale': r.get('stale'),
                      'remarks': r.get('remarks'), 'cells': [{k: c.get(k) for k in CELL_KEYS} for c in r.get('cells') or []]}
                     for r in ans.get('rows') or []]}


def choose_sample(urows, screens, max_n, forced):
    """The stocks whose own bars are fetched, each with why: the asked ones, 3 liquid, 3 illiquid, one near each price
    band boundary, 2 with a corporate action remark, 1 stale; then, for every screen in turn (the defaults first), the
    most liquid stock it lists when no sample stock is among its matches yet."""
    by = {r['ticker']: r for r in urows}
    adv = lambda r: r.get('adv20_idr') or 0
    pick = {}

    def add(t, why):
        if t in pick:
            pick[t].append(why)
            return True
        if len(pick) >= max_n or t not in by:
            return False
        pick[t] = [why]
        return True

    for t in forced:
        if not add(t, 'asked'):
            say(f'  --sample {t}: not a listed stock of this publication (or the sample is full); left out')
    live = [r for r in urows if r.get('bars') and not r.get('stale')]
    for r in sorted(live, key=adv, reverse=True)[:3]:
        add(r['ticker'], f'liquid (ADV20 {adv(r):.3g})')
    for r in sorted([r for r in live if (r.get('bars') or 0) >= 250], key=adv)[:3]:
        add(r['ticker'], f'illiquid (ADV20 {adv(r):.3g})')
    for b in (200, 500, 2000, 5000):
        near = [r for r in live if r.get('last') and abs(r['last'] / b - 1) <= 0.05]
        if near:
            r = min(near, key=lambda r: (abs(r['last'] - b), -adv(r)))
            add(r['ticker'], f'near the {b} price band boundary (last {r["last"]})')
    breaks = [r for r in urows if any((x or {}).get('code') == 'PRICE_BREAK' for x in r.get('remarks') or [])]
    for r in sorted(breaks, key=adv, reverse=True)[:2]:
        add(r['ticker'], 'corporate action remark (PRICE_BREAK ' + ', '.join(x['ex_date'] for x in r['remarks'] if x.get('code') == 'PRICE_BREAK') + ')')
    stale = [r for r in urows if r.get('stale') and r.get('bars')]
    if stale:
        r = max(stale, key=lambda r: (r.get('last_bar') or '', adv(r)))
        add(r['ticker'], f'stale (last bar {r.get("last_bar")})')
    order = sorted([s for s in screens if s['status'] == 200 and s.get('pattern')],
                   key=lambda s: (s['variant'] not in ('default_w3', 'default_state'), s['name']))
    for s in order:
        matched = [r['ticker'] for r in s['rows'] if r['status'] == 'match']
        if matched and not any(t in pick for t in matched):
            if not add(max(matched, key=lambda t: (adv(by.get(t, {})), t)), f'shows {s["name"]}'):
                break
    return [{'ticker': t, 'reasons': w} for t, w in pick.items()]


def fetch_bars(edge, t, pace):
    """The Terminal's own price files of one stock: POST /api/terminal/v1/bundle (the page's call), then each presigned
    file without the session cookie; sha256, bytes and rows checked against the answer. No URL is kept."""
    status, b, ms = edge.call('POST', '/api/terminal/v1/bundle', {'ticker': t, 'datasets': ['price'], 'packs': True}, pace=pace, retries=1)
    part = {'ticker': t, 'status': status, 'ms': ms, 'error': error_of(b) if status != 200 else None, 'files': [], 'docs': [], 'file_problems': []}
    if status != 200:
        return part
    price = ((b or {}).get('datasets') or {}).get('price') or {}
    part.update(data_through=price.get('data_through'), generated_at=(b or {}).get('generated_at'))
    for f in price.get('files') or []:
        meta = {k: f.get(k) for k in ('year', 'pack', 'sha256', 'bytes', 'rows')}
        part['files'].append(meta)
        try:
            with urllib.request.urlopen(f['url'], timeout=90) as r:
                raw = r.read()
        except Exception as e:                      # the URL carries a signature: safe_error drops the query
            part['status'] = 0
            part['error'] = {'code': 'FILE_DOWNLOAD', 'message': safe_error(e)}
            return part
        if hashlib.sha256(raw).hexdigest() != f.get('sha256') or len(raw) != f.get('bytes'):
            part['file_problems'].append(f'{meta["pack"] or meta["year"]}: sha256 or bytes differ from the bundle answer')
        doc = json.loads(gzip.decompress(raw))
        if len(doc.get('d') or []) != f.get('rows'):
            part['file_problems'].append(f'{meta["pack"] or meta["year"]}: {len(doc.get("d") or [])} rows, the answer says {f.get("rows")}')
        part['docs'].append({k: doc.get(k) for k in ('dataset', 'ticker', 'year', 'd', 'o', 'h', 'l', 'c', 'v')})
    return part


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('out')
    ap.add_argument('--base-url')
    ap.add_argument('--max-sample', type=int, default=20)
    ap.add_argument('--sample', default='')
    ap.add_argument('--pace', type=float, default=0.5)
    ap.add_argument('--bundle-pace', type=float, default=1.0)
    ap.add_argument('--no-compare', action='store_true')
    args = ap.parse_args()
    out = Path(args.out)
    (out / 'bars').mkdir(parents=True, exist_ok=True)
    base, login, password = credentials(args)
    SECRETS.update(x for x in (password,) if x)
    edge = Edge(base)
    fetch = {'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'host': urllib.parse.urlparse(base).hostname,
             'pace_s': args.pace, 'bundle_pace_s': args.bundle_pace, 'max_sample': args.max_sample, 'problems': []}

    s, _, _, _ = edge.raw('POST', '/api/v1/auth/sign-in', {'login': login, 'password': password})
    del password
    if s != 200:
        raise SystemExit(f'sign-in failed ({s})')
    SECRETS.update(c.value for c in edge.jar if c.value)
    s, sess, _ = edge.call('GET', '/api/v1/auth/session')
    edge.csrf = (sess or {}).get('csrf_token', '') if isinstance(sess, dict) else ''
    SECRETS.update(x for x in (edge.csrf,) if x)
    del sess

    s, cat, ms = edge.call('GET', '/api/v1/screener/catalog', pace=args.pace)
    before = catalog_part(s, cat, ms)
    del cat
    (out / 'catalog_before.json').write_text(json.dumps(before, indent=1))
    say('catalog', s, ms, json.dumps({'versions': before['versions'], 'data': before['data'], 'candles': sum(m.get('group') == 'Candlestick' for m in before['metrics'])}))
    if s != 200:
        fetch['problems'].append(f'catalog answered {s} {before["error"]}')
    s, uni, ms = edge.call('GET', '/api/v1/screener/universe', pace=args.pace)
    urows = [{k: r.get(k) for k in ('ticker', 'last', 'adv20_idr', 'first_bar', 'last_bar', 'bars', 'stale', 'remarks')}
             for r in ((uni or {}).get('rows') or [] if isinstance(uni, dict) else [])]
    (out / 'universe.json').write_text(json.dumps({'status': s, 'versions': (uni or {}).get('versions') if isinstance(uni, dict) else None, 'rows': urows}))
    del uni
    say('universe', s, ms, len(urows), 'stocks')
    if s != 200:
        fetch['problems'].append(f'universe answered {s}')

    candles = [m for m in before['metrics'] if m.get('group') == 'Candlestick']
    page, seq, screens = f'live-candles-{int(time.time())}', 0, []
    pin = (before.get('versions') or {}).get('price_data')
    for name, meta, definition in plan_screens(candles):
        seq += 1
        body = {'schema_version': 1, 'client_order': {'page': page, 'seq': seq}, 'definition': definition, **({'data_version': pin} if pin else {})}
        s, ans, ms = edge.call('POST', '/api/v1/screener/run', body, pace=args.pace)
        part = screen_part(name, meta, s, ans, ms)
        screens.append(part)
        say('screen', name, s, ms, f'matches={part["match_count"]}' if s == 200 else f'{part["error"].get("code")} {part["error"].get("field") or ""} {(part["error"].get("message") or "")[:160]}')
    (out / 'screens.json').write_text(json.dumps(screens))

    forced = [t.strip().upper() for t in args.sample.split(',') if t.strip()]
    sample = choose_sample(urows, screens, args.max_sample, forced)
    (out / 'sample.json').write_text(json.dumps(sample, indent=1))
    say('sample', len(sample), ' '.join(x['ticker'] for x in sample))
    for x in sample:
        part = fetch_bars(edge, x['ticker'], args.bundle_pace)
        (out / 'bars' / f'{x["ticker"]}.json').write_text(json.dumps(part))
        say('bars', x['ticker'], part['status'], part['ms'], sum(len(d.get('d') or []) for d in part['docs']), 'rows', '; '.join(part['file_problems']))
        if part['status'] != 200:
            fetch['problems'].append(f'{x["ticker"]}: bundle {part["status"]} {(part["error"] or {}).get("code")}')
            if part['status'] == 429:
                fetch['problems'].append('the Terminal quota refused a bundle: the rest of the sample was not fetched')
                break

    s, cat, ms = edge.call('GET', '/api/v1/screener/catalog', pace=args.pace)
    (out / 'catalog_after.json').write_text(json.dumps(catalog_part(s, cat, ms), indent=1))
    del cat
    edge.raw('POST', '/api/v1/auth/sign-out', {})
    fetch.update(finished_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), calls=edge.calls)
    (out / 'fetch.json').write_text(json.dumps(fetch, indent=1))
    if args.no_compare:
        return 0
    judge = subprocess.run(['node', str(HERE / 'live_candles_compute.mjs'), str(out)], capture_output=True, text=True, timeout=1800)
    say(judge.stdout.strip())
    if judge.stderr.strip():
        say(judge.stderr.strip()[-2000:])
    return judge.returncode


if __name__ == '__main__':
    sys.exit(main())
