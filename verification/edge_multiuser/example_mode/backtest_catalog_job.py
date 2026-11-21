"""EXEC-MU-ACCOUNTS 3e, the example mode (ERRORS M527): reads the Backtest worker's catalog (GET /v1/catalog) and prints
the part of it, cut to the example's period, that the example's request is built on (the rule of
apps/edge-bff/backtest/tests/example-part.ts catalogPart: the dates, versions, flow block and limits; the lists cut to the
example's ticker as a stock and the brokers its default setup names; no grouping, no Flow indicator). backtest_request.ts
builds the page's request on it; capture_backtest.json holds both (built_on, request), and the capture stops when the
worker's catalog no longer holds the part as it is. Read-only; the part holds no market value (versions, dates, limits,
one ticker and broker code).

params.json: {"worker_url": "http://backtest-worker.railway.internal:8080", "as_of": "2026-10-30",
              "first": "2025-10-30", "ticker": "MAPI", "brokers": ["YU"]}
Run (the key as a Railway reference for the run only, never a value; the publisher's modules as extras):
  RUN_JOB_EXTRA_VARS='BACKTEST_WORKER_KEY=${{backtest-worker.BACKTEST_WORKER_KEY}}' \
    scripts/onboarding/run_job.sh verification/edge_multiuser/example_mode/backtest_catalog_job.py <params.json> <log> \
    apps/terminal-publisher/publisher.py apps/terminal-publisher/radar.py apps/terminal-publisher/watchlist.py \
    apps/terminal-publisher/overview.py apps/terminal-publisher/examples.py
"""
import json
import os
import urllib.request

import examples

p = json.load(open('params.json'))


def main():
    req = urllib.request.Request(p['worker_url'].rstrip('/') + '/v1/catalog',
                                 headers={'x-backtest-worker-key': os.environ['BACKTEST_WORKER_KEY']})
    with urllib.request.urlopen(req, timeout=120) as r:
        cat = examples.backtest_catalog(json.loads(r.read()), p['first'], p['as_of'])
    flow, named = cat.get('flow') or {}, set(p['brokers'])
    part = {'schema_version': cat.get('schema_version'), 'engine_version': cat.get('engine_version'),
            'registry_version': cat.get('registry_version'), 'first_date': cat.get('first_date'),
            'data_through': cat.get('data_through'),
            'tickers': [{'ticker': t['ticker'], 'type': t['type']} for t in cat.get('tickers') or []
                        if t.get('ticker') == p['ticker'] and t.get('type') == 'stock'],
            'groupings': [],
            'flow': {'available': flow.get('available'), 'reason': flow.get('reason'),
                     'brokers': [b for b in flow.get('brokers') or [] if b in named], 'data_through': flow.get('data_through')},
            'limits': cat.get('limits')}
    if not part['tickers'] or sorted(part['flow']['brokers']) != sorted(named):
        print('VERDICT REFUSED ' + json.dumps(f"the worker's catalog has no stock {p['ticker']} or not every broker of "
                                              f"{sorted(named)}"), flush=True)
        raise SystemExit(1)
    print('PART ' + json.dumps(part), flush=True)
    print('VERDICT CATALOG_PART', flush=True)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 - the class only
        print('ERR ' + type(e).__name__, flush=True)
        raise SystemExit(1)
    print('JOB_DONE', flush=True)
