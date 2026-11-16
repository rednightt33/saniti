"""EXEC-BACKTEST-REVAMP deploy check on Railway dev (user 2026-11-16 at Gate 3, "go deploy"; EXEC.md deploy step 4):
what e2e_dev.py does not run. Signed in as the owner (an admin: EDGE_ADMIN_OWNERS defaults to EDGE_OWNER, app/rights.py),
read routes and two backtests only:
  1. the backtest catalog as the session sees it: flow_indicators (FL11 available; the point-in-time ones, FL18 among
     them, present for an admin), grammar_refusals;
  2. a run with a Flow A-C condition in the shared grammar (FL11 crosses above its 20-day average), ending on the
     broker data's day; it must trade;
  3. a run with a point-in-time D condition (close above FL18 anchored), as an admin;
  4. the signals preview of the Flow condition.
Each run counts as a trial of its strategy line for the owner, as any run does. Credentials are read from Railway into
memory as e2e_dev.py does, never printed or saved. Writes OUT_DIR/report.json.
  RAILWAY_TOKEN=dummy EDGE_TEST_CHROMIUM=<chrome> python revamp_dev_check.py OUT_DIR [--ticker BBRI]
(the session proxy injects the Railway credential; a dummy value lets it)."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_dev as e2e  # noqa: E402

REQUEST = {
    "schema_version": 1, "mode": "single", "single": {"ticker": "BBRI", "benchmark": "buy_and_hold"},
    "period": {"from": "2023-01-02", "to": None, "oos_fraction": 0.3},
    "entry": {"logic": "all", "at_least": 1, "window_bars": 5, "conditions": []},
    "exit": {"atr_length": 14, "stop": {"mode": "pct", "pct": 0.07, "atr_mult": 2, "reward_risk_x": 2,
                                        "line": {"indicator": "I09", "output": "supertrend"}},
             "take_profit": {"mode": "pct", "pct": 0.15, "r_multiple": 2, "atr_mult": 3},
             "trailing": {"mode": "none", "pct": 0.05, "chandelier_length": 22, "chandelier_mult": 3,
                          "line": {"indicator": "I01", "output": "sma"}},
             "max_hold_bars": 20, "signals": {"logic": "any", "conditions": []}},
    "sizing": {"capital_idr": 100000000, "allocation_fraction": 1},
    "costs": {"buy_fee": 0.0015, "sell_fee": 0.0025, "slippage": 0.0005, "skip_ara_open_gap": True, "ara_gap_fraction": 0.2},
    "robustness": {"monte_carlo_runs": 1000, "seed": 7, "sensitivity": True},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--ticker', default='BBRI')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    from playwright.sync_api import sync_playwright
    v = e2e.service_vars('edge-bff')
    base = (v.get('EDGE_PUBLIC_ORIGIN') or ('https://' + v['RAILWAY_PUBLIC_DOMAIN'])).rstrip('/')
    login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD')
    del v
    report = {'base': base, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'checks': {}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None,
                                     proxy={'server': os.environ['HTTPS_PROXY']} if os.environ.get('HTTPS_PROXY') else None)
        ctx = browser.new_context()
        r = ctx.request.post(base + '/api/v1/auth/sign-in', data=json.dumps({'login': login, 'password': password}),
                             headers={'Content-Type': 'application/json', 'Origin': base})
        del password
        if r.status != 200:
            raise SystemExit(f'sign-in failed ({r.status})')
        api = e2e.Api(ctx, base, r.json()['csrf_token'], time.sleep)
        status, cat = api.json('/api/v1/backtests/catalog')
        fl = {x['id']: x for x in cat.get('flow_indicators') or []}
        through = (cat.get('flow') or {}).get('data_through') or cat['data_through']
        report['catalog'] = {'status': status, 'engine_version': cat.get('engine_version'), 'flow': cat.get('flow'),
                             'flow_indicators': len(fl), 'available': sum(1 for x in fl.values() if x.get('available')),
                             'admin_entries': sorted(k for k, x in fl.items() if x.get('access') == 'admin'),
                             'FL11': fl.get('FL11'), 'FL18': fl.get('FL18'),
                             'grammar_refusals': sorted((cat.get('grammar_refusals') or {}).keys())}
        report['checks']['catalog'] = bool(status == 200 and fl.get('FL11', {}).get('available')
                                           and 'FL18' in fl and fl['FL18'].get('access') == 'admin'
                                           and report['catalog']['grammar_refusals'])

        def run(name, conditions):
            q = json.loads(json.dumps(REQUEST))
            q['single']['ticker'] = a.ticker
            q['period']['to'] = through
            q['entry']['conditions'] = conditions
            json.dump(q, open(f'{a.out}/request-{name}.json', 'w'), indent=1)
            code, ans, t0 = api.submit(q)
            if code != 202:
                report['runs'][name] = {'submit_status': code, 'answer': ans}
                return False
            st, timeline = api.follow(ans['request_id'], t0, 900)
            out = {'request_id': ans['request_id'], 'state': st.get('state'), 'error': st.get('error'), 'seconds': round(time.monotonic() - t0, 1),
                   'timeline': timeline}
            if st.get('state') == 'FINISHED':
                c, res = api.json(f"/api/v1/backtests/{ans['request_id']}/result")
                json.dump(res, open(f'{a.out}/result-{name}.json', 'w'))
                ent = ((res.get('events') or {}).get('entries') or {}).get(a.ticker) or {}
                out.update({'result_status': c, 'trades': len(res.get('trades') or []), 'entry_on_days': len(ent.get('on') or []),
                            'warnings': [w.get('code') for w in (res.get('meta') or {}).get('warnings') or []],
                            'engine_version': (res.get('meta') or {}).get('engine_version'),
                            'finite': not e2e.finite_everywhere(res)})
            report['runs'][name] = out
            return out['state'] == 'FINISHED' and out.get('finite', False)

        report['runs'] = {}
        # an event, not a level: an entry fires when its condition switches on, so a level the stock holds on every day
        # (FL11 above 0 for BBRI, 7.5 to 56 over 2025-2026) has no entry and a run of it no trade (2026-11-16)
        fl11 = {'kind': 'flow', 'metric': 'FL11', 'params': {}}
        flow = [{'id': 'f1', 'enabled': True, 'kind': 'test',
                 'test': {'kind': 'event', 'within': 1, 'signal': {'lhs': fl11, 'op': 'crosses_above', 'rhs': {
                     'kind': 'transform', 'fn': 'ma', 'of': fl11, 'args': {'ma': 'SMA', 'length': 20}}}}}]
        point = [{'id': 'd1', 'enabled': True, 'kind': 'test',
                  'test': {'kind': 'state', 'lhs': {'kind': 'price', 'field': 'close'}, 'op': 'gt',
                           'rhs': {'kind': 'flow', 'metric': 'FL18', 'params': {'anchor': '2024-01-02'}}}}]
        report['checks']['run_flow_A_C'] = run('flow', flow) and report['runs']['flow'].get('trades', 0) > 0
        report['checks']['run_point_in_time_D_admin'] = run('pit', point)
        code, prev = api.post('/api/v1/backtests/signals', {'schema_version': 1, 'tickers': [a.ticker],
                                                            'period': {'from': '2023-01-02', 'to': through},
                                                            'entry': {'logic': 'all', 'at_least': 1, 'window_bars': 5, 'conditions': flow}})
        rows = prev.get('rows') or []
        report['preview'] = {'status': code, 'rows': [{k: x.get(k) for k in ('ticker', 'entry_signals', 'error')} for x in rows],
                             'error': prev.get('error')}
        report['checks']['preview_flow'] = code == 200 and bool(rows) and (rows[0].get('entry_signals') or 0) > 0
        browser.close()
    report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    report['failed'] = [k for k, ok in report['checks'].items() if not ok]
    json.dump(report, open(f'{a.out}/report.json', 'w'), indent=1)
    print(json.dumps({'checks': report['checks'], 'catalog': {k: report['catalog'][k] for k in ('flow_indicators', 'available', 'admin_entries')},
                      'runs': {k: {x: y for x, y in v.items() if x != 'timeline'} for k, v in report['runs'].items()},
                      'preview': report['preview'], 'failed': report['failed']}, indent=1))
    sys.exit(1 if report['failed'] else 0)


if __name__ == '__main__':
    main()
