"""EDGE backtest: real end-to-end check in Railway dev (user approval 2026-10-26: steps 3-5 of the backtest plan).

The production page (/backtest-app/ on the dev edge-bff) runs in Chromium, signed in as the owner. Its own requests go
page -> edge-bff (job row) -> backtest-worker -> terminal-api (/bundle) -> bucket (terminal-display) -> worker ->
edge-bff (result parts) -> page. The script records every backtest API call the page makes, screenshots the results,
then checks the stored results through the API: shape and finiteness, reconciliation (trades to cash and equity),
determinism (the identical request twice), events per ticker, a refused request, cancel, and the trial count.
Credentials (EDGE_LOGIN, EDGE_INITIAL_PASSWORD) are read from Railway into memory; they are never printed or saved.
Every backtest the script runs counts as a trial of its strategy line for the owner (decision K3), as any run does.

Usage: RAILWAY_TOKEN=... EDGE_TEST_CHROMIUM=<chrome> python e2e_dev.py OUT_DIR [--skip-page] [--only single|portfolio|cancel]
Writes OUT_DIR/report.json, the result payloads (result-*.json), the recorded calls (calls.json) and screenshots.
"""
import argparse
import gzip
import json
import math
import os
import sys
import time
import urllib.request

PID, EID = '8aef1702-030b-49cb-9df7-5ac2e0a42691', '4d3e5af2-302b-4a2e-84e2-7d7476d6ff49'
VIEWPORTS = [(1600, 1000), (1280, 800), (390, 844)]
TABS = ['overview', 'returns', 'trades', 'risk', 'robust', 'list']
EPS = 2.0 ** -53


def gql(query, variables):
    req = urllib.request.Request('https://backboard.railway.com/graphql/v2', json.dumps({'query': query, 'variables': variables}).encode(),
                                 {'Content-Type': 'application/json', 'Project-Access-Token': os.environ['RAILWAY_TOKEN'],
                                  'User-Agent': 'saniti-backtest-e2e/1'})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())['data']


def service_vars(name):
    sid = {e['node']['name']: e['node']['id'] for e in gql('query($id:String!){project(id:$id){services{edges{node{id name}}}}}',
                                                            {'id': PID})['project']['services']['edges']}[name]
    return gql('query($p:String!,$e:String!,$s:String!){variables(projectId:$p,environmentId:$e,serviceId:$s)}',
               {'p': PID, 'e': EID, 's': sid})['variables']


class Api:
    """The public backtest API with the browser context's session cookie (the same session the page uses)."""

    def __init__(self, ctx, base, csrf):
        self.ctx, self.base, self.csrf = ctx, base, csrf

    def get(self, path):
        r = self.ctx.request.get(self.base + path, timeout=120_000)
        return r.status, r.body()

    def post(self, path, body):
        r = self.ctx.request.post(self.base + path, data=json.dumps(body), timeout=120_000,
                                  headers={'Content-Type': 'application/json', 'Origin': self.base, 'X-CSRF-Token': self.csrf})
        return r.status, r.body()

    def json(self, path):
        status, body = self.get(path)
        return status, json.loads(body or b'{}')

    def wait(self, request_id, limit_s=1200):
        t0, seen = time.time(), []
        while True:
            _, st = self.json(f'/api/v1/backtests/{request_id}')
            p = st.get('progress') or {}
            mark = (st.get('state'), p.get('phase'))
            if not seen or seen[-1][1:] != mark:
                seen.append((round(time.time() - t0, 1), *mark))
            if st.get('state') in ('FINISHED', 'FAILED', 'CANCELLED') or time.time() - t0 > limit_s:
                return st, seen
            time.sleep(1)


def finite_everywhere(value, path='$'):
    """paths of non-finite numbers (the contract sends null for 'no value', never NaN or Infinity)"""
    bad = []
    if isinstance(value, float) and not math.isfinite(value):
        bad.append(path)
    elif isinstance(value, dict):
        for k, v in value.items():
            bad += finite_everywhere(v, f'{path}.{k}')
    elif isinstance(value, list):
        for i, v in enumerate(value):
            bad += finite_everywhere(v, f'{path}[{i}]')
    return bad


def reconcile(result, capital):
    """trades to cash and equity: when the run ends flat (end_of_test closes every position), the final equity is the
    capital plus the sum of the trades' P&L; each trade's P&L is proceeds - cost and its return pnl / cost. Tolerance:
    float8 rounding of each term, sum(|x|) * 2**-53 (no chosen tolerance)."""
    trades = result['trades']
    out = {'trades': len(trades)}
    terms = [capital] + [t['pnl_idr'] for t in trades]
    total = math.fsum(terms)
    final = result['equity'][-1]
    tol = math.fsum(abs(x) for x in terms + [final]) * EPS * max(1, len(terms))
    out['final_equity'] = final
    out['capital_plus_pnl'] = total
    out['equity_matches'] = abs(final - total) <= tol
    worst = 0.0
    for t in trades:
        worst = max(worst, abs(t['pnl_idr'] - (t['proceeds_idr'] - t['cost_idr'])) / max(1.0, abs(t['cost_idr'])))
    out['pnl_is_proceeds_minus_cost_rel'] = worst
    out['returns_match'] = all(abs(t['return'] - t['pnl_idr'] / t['cost_idr']) <= 4 * EPS * max(1.0, abs(t['return'])) for t in trades if t['cost_idr'])
    out['exposure_in_0_1'] = all(-EPS <= x <= 1 + 4 * EPS for x in result['exposure'])
    out['lots_whole'] = all(t['shares'] % 100 == 0 and t['shares'] == t['lots'] * 100 for t in trades)
    out['no_overlap_same_ticker'] = no_overlap(trades)
    by = {}
    for t in trades:
        by[t['ticker']] = by.get(t['ticker'], 0.0) + t['pnl_idr']
    rows = {r['ticker']: r for r in result['tables']['per_ticker']}
    out['per_ticker_pnl_matches'] = all(abs(rows[k]['pnl_idr'] - v) <= max(1.0, abs(v)) * 64 * EPS for k, v in by.items() if k in rows)
    return out


def no_overlap(trades):
    last = {}
    for t in sorted(trades, key=lambda t: (t['ticker'], t['entry_date'])):
        if t['ticker'] in last and t['entry_date'] < last[t['ticker']]:
            return False
        last[t['ticker']] = t['exit_date']
    return True


def strip_run_fields(result):
    """what may differ between two runs of the identical request: the duration and the trial bookkeeping before the
    run (prior and this_run); the trial total and everything computed from it must be equal (K3)"""
    r = json.loads(json.dumps(result))
    r['meta'].pop('duration_ms', None)
    r['meta']['trials'].pop('prior', None)
    r['meta']['trials'].pop('this_run', None)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--skip-page', action='store_true')
    ap.add_argument('--only', choices=['single', 'portfolio', 'cancel'])
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    from playwright.sync_api import sync_playwright

    v = service_vars('edge-bff')
    base = 'https://' + v['RAILWAY_PUBLIC_DOMAIN']
    login, password = v['EDGE_LOGIN'], v['EDGE_INITIAL_PASSWORD']
    del v
    report = {'base': base, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'steps': {}}
    calls = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None,
                                     proxy={'server': os.environ['HTTPS_PROXY']} if os.environ.get('HTTPS_PROXY') else None)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        r = ctx.request.post(base + '/api/v1/auth/sign-in', data=json.dumps({'login': login, 'password': password}),
                             headers={'Content-Type': 'application/json', 'Origin': base})
        del password
        if r.status != 200:
            raise SystemExit(f'sign-in failed ({r.status})')
        api = Api(ctx, base, r.json()['csrf_token'])

        status, cat = api.json('/api/v1/backtests/catalog')
        report['catalog'] = {'status': status, 'tickers': len(cat.get('tickers', [])), 'universes': len(cat.get('universes', [])),
                             'data_through': cat.get('data_through'), 'first_date': cat.get('first_date'),
                             'flow': {k: cat.get('flow', {}).get(k) for k in ('available', 'data_through', 'reason')},
                             'engine_version': cat.get('engine_version'), 'registry_version': cat.get('registry_version'),
                             'limits': cat.get('limits')}

        page = ctx.new_page()

        def on_response(resp):
            u = resp.url
            if '/api/v1/backtests' in u or '/api/terminal/v1/bundle' in u or 'storageapi.dev' in u:
                req = resp.request
                entry = {'method': req.method, 'url': u.split('?')[0], 'status': resp.status,
                         'ms': round(req.timing.get('responseEnd', 0), 1) if req.timing else None}
                if req.method == 'POST' and u.endswith('/api/v1/backtests'):
                    entry['body'] = json.loads(req.post_data or '{}')
                    try:
                        entry['answer'] = resp.json()
                    except Exception:
                        pass
                try:
                    entry['bytes'] = len(resp.body())
                except Exception:
                    entry['bytes'] = None
                calls.append(entry)
        page.on('response', on_response)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)[:300]))
        page.on('console', lambda m: errors.append(m.text[:300]) if m.type == 'error' else None)

        def page_run(label, setup=None):
            t0 = time.time()
            if setup:
                setup()
            n0 = len(calls)
            page.click('#runTop')
            page.wait_for_function("() => !document.getElementById('runTop').disabled", timeout=1_200_000)
            note = page.inner_text('#runNote')
            submit = next((c for c in calls[n0:] if c.get('body') is not None), None)
            shots = []
            for w, h in VIEWPORTS:
                page.set_viewport_size({'width': w, 'height': h})
                for t in TABS:
                    page.click(f'#rtabs [data-tab="{t}"]')
                    page.wait_for_timeout(700)
                    path = os.path.join(a.out, f'{label}-{t}-{w}x{h}.png')
                    page.screenshot(path=path, full_page=True)
                    shots.append(os.path.basename(path))
            page.set_viewport_size({'width': 1600, 'height': 1000})
            return {'seconds': round(time.time() - t0, 1), 'run_note': note, 'submit': submit, 'screenshots': shots}

        if not a.skip_page:
            t0 = time.time()
            page.goto(base + '/backtest-app/', wait_until='domcontentloaded')
            page.wait_for_function("() => !document.getElementById('runTop').disabled", timeout=180_000)
            report['steps']['page_boot_seconds'] = round(time.time() - t0, 1)
            page.screenshot(path=os.path.join(a.out, 'boot-1600x1000.png'), full_page=True)

        def check_result(label, request_id, capital, single):
            st, phases = api.wait(request_id)
            out = {'request_id': request_id, 'state': st.get('state'), 'error': st.get('error'), 'phases': phases,
                   'duration_ms': st.get('duration_ms'), 'result_bytes_gzip': st.get('result_bytes'),
                   'created_at': st.get('created_at'), 'started_at': st.get('started_at'), 'finished_at': st.get('finished_at')}
            if st.get('state') != 'FINISHED':
                return out, None
            status, raw = api.get(f'/api/v1/backtests/{request_id}/result')
            res = json.loads(raw)
            out['result_status'] = status
            out['result_json_bytes'] = len(raw)
            out['result_gzip_bytes'] = len(gzip.compress(raw, 6))
            out['non_finite'] = finite_everywhere(res)[:10]
            out['meta'] = {k: res['meta'].get(k) for k in ('engine_version', 'registry_version', 'data_version', 'request_hash',
                                                           'lineage_key', 'mode', 'data_through', 'benchmark', 'seed')}
            out['meta']['tickers'] = len(res['meta']['tickers'])
            out['meta']['warnings'] = [w['code'] for w in res['meta']['warnings']]
            out['meta']['trials'] = {k: res['meta']['trials'][k] for k in ('prior', 'this_run', 'total')}
            out['period'] = [res['dates'][0], res['dates'][-1], len(res['dates'])]
            out['stats_all'] = {k: res['stats']['all'].get(k) for k in ('total_return', 'cagr', 'sharpe', 'max_drawdown') if k in res['stats']['all']}
            out['reconcile'] = reconcile(res, capital)
            out['robustness'] = {'monte_carlo': res['robustness']['monte_carlo'] is not None,
                                 'sensitivity_cells': None if not res['robustness']['sensitivity'] else
                                 sum(1 for row in res['robustness']['sensitivity']['cells'] for c in row if c is not None),
                                 'deflated': res['robustness']['deflated']}
            tick = res['meta']['tickers'][0] if res['meta']['tickers'] else None
            if tick:
                es, ev = api.json(f'/api/v1/backtests/{request_id}/events?ticker={tick}')
                out['events'] = {'ticker': tick, 'status': es, 'conditions': len(ev.get('conditions', [])),
                                 'exit_tracks': len(ev.get('exits', {}))}
            if single:
                out['events_in_result'] = {'conditions': len(res['events'].get('conditions', [])),
                                           'entries': len(res['events']['entries']), 'skipped': len(res['events']['skipped'])}
            with open(os.path.join(a.out, f'result-{label}.json'), 'w') as f:
                json.dump(res, f)
            return out, res

        def submit(body):
            status, raw = api.post('/api/v1/backtests', body)
            return status, json.loads(raw or b'{}')

        if a.only in (None, 'single'):
            s = page_run('single') if not a.skip_page else {}
            req = (s.get('submit') or {}).get('body')
            rid = ((s.get('submit') or {}).get('answer') or {}).get('request_id')
            if req is None:
                raise SystemExit('the page did not submit a backtest')
            out, res = check_result('single', rid, req['sizing']['capital_idr'], True)
            out['page'] = {k: s[k] for k in ('seconds', 'run_note')} if s else None
            report['steps']['single'] = out
            # the identical request again: the same numbers, the same trial total (K3), the same request hash
            status, ans = submit(req)
            out2, res2 = check_result('single-repeat', ans.get('request_id'), req['sizing']['capital_idr'], True) if status == 202 else ({'status': status, 'answer': ans}, None)
            same = res is not None and res2 is not None and strip_run_fields(res) == strip_run_fields(res2)
            report['steps']['single_repeat'] = {**out2, 'identical_apart_from_duration_and_prior_trials': same}
            # a request the worker refuses at submit (422 before queueing)
            bad = json.loads(json.dumps(req))
            bad['period']['to'] = '2100-01-01'
            status, ans = submit(bad)
            report['steps']['refused_at_submit'] = {'status': status, 'error': ans.get('error')}

        if a.only in (None, 'portfolio'):
            def to_portfolio():
                page.click('#viewSeg [data-v="signals"]')
                page.click('#sumbox [data-st="1"]')
                page.click('#modeSeg [data-m="portfolio"]')
                page.wait_for_timeout(500)
                page.wait_for_function("() => !document.getElementById('runTop').disabled", timeout=600_000)
                page.screenshot(path=os.path.join(a.out, 'portfolio-signals-1600x1000.png'), full_page=True)
            s = page_run('portfolio', to_portfolio)
            req = (s.get('submit') or {}).get('body')
            rid = ((s.get('submit') or {}).get('answer') or {}).get('request_id')
            out, _ = check_result('portfolio', rid, req['sizing']['capital_idr'], False)
            out['page'] = {k: s[k] for k in ('seconds', 'run_note')}
            out['universe'] = req['portfolio']['universe']
            report['steps']['portfolio'] = out
            report['portfolio_request'] = req

        if a.only in (None, 'cancel'):
            req = report.get('portfolio_request')
            if req:
                body = json.loads(json.dumps(req))
                body['robustness']['monte_carlo_runs'] = body['robustness']['monte_carlo_runs']
                body['period']['oos_fraction'] = body['period']['oos_fraction']
                body['portfolio']['max_positions'] = max(1, body['portfolio']['max_positions'] - 1)  # a new variant, not the stored result
                status, ans = submit(body)
                rid = ans.get('request_id')
                time.sleep(3)
                cs, cans = api.post(f'/api/v1/backtests/{rid}/cancel', {})
                st, phases = api.wait(rid, 300)
                report['steps']['cancel'] = {'submit_status': status, 'cancel_status': cs, 'state': st.get('state'),
                                             'phases': phases, 'error': st.get('error')}

        report['page_errors'] = errors[:20]
        report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        api.post('/api/v1/auth/sign-out', {})
        browser.close()

    for c in calls:
        c.pop('answer', None) if c.get('method') != 'POST' else None
    with open(os.path.join(a.out, 'calls.json'), 'w') as f:
        json.dump(calls, f, indent=1)
    with open(os.path.join(a.out, 'report.json'), 'w') as f:
        json.dump(report, f, indent=1)
    print(json.dumps({k: report['steps'][k].get('state') if isinstance(report['steps'][k], dict) else report['steps'][k]
                      for k in report['steps']}))


if __name__ == '__main__':
    main()
