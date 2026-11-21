"""EXEC-MU-ACCOUNTS 3e, the example mode (ERRORS M527): a read-only probe for the Screener's example of 30 October 2026.
The Screener evaluates every stock at its newest bar (no evaluation date), so its example is the real screener-worker
run on its own input files cut at that date. This probe reads what terminal-api publishes for the worker (GET /state:
the publication and its xsection index; GET /reference/*: the reference files' metadata) and prints, for each file, its
name, bytes, rows and dates only, never a value of the data: whether the files the worker reads reach back far enough
before the date (the broker day files) and what lies after it.

params.json: {"as_of": "2026-10-30"}
Run (terminal-api's origin and the screener-worker's proxy key as Railway references for the run only, never values):
  RUN_JOB_EXTRA_VARS='TERMINAL_URL=${{screener-worker.TERMINAL_URL}} TERMINAL_PROXY_KEY=${{screener-worker.TERMINAL_PROXY_KEY}}' \
    scripts/onboarding/run_job.sh verification/edge_multiuser/example_mode/screener_probe_job.py <params.json> <log>
"""
import json
import os
import re
import urllib.error
import urllib.request

p = json.load(open('params.json'))
ISO = re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}')


def get(path):
    req = urllib.request.Request(os.environ['TERMINAL_URL'].rstrip('/') + '/api/terminal/v1' + path,
                                 headers={'x-terminal-proxy-key': os.environ['TERMINAL_PROXY_KEY'], 'accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def shape(x, depth=0):
    """The keys of a document with the type of each value; dates and counts shown, other values hidden."""
    if isinstance(x, dict):
        return {k: shape(v, depth + 1) for k, v in list(x.items())[:40]} if depth < 3 else 'object'
    if isinstance(x, list):
        return f'list[{len(x)}]'
    if isinstance(x, str):
        return x if ISO.match(x) else 'str'
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return 'number'
    return x


def main():
    as_of = p['as_of']
    status, state = get('/state')
    print('OUT ' + json.dumps({'step': 'state', 'status': status, 'shape': shape(state)}), flush=True)
    index = (state or {}).get('xsection') or (state or {}).get('files') or {}
    files = index.get('files') if isinstance(index, dict) and 'files' in index else index
    entries = files.items() if isinstance(files, dict) else ((f.get('name'), f) for f in files or [])
    broker, other = [], []
    for name, f in entries:
        meta = {k: v for k, v in (f or {}).items() if k in ('bytes', 'rows', 'as_of', 'first', 'last', 'through')}
        (broker if str(name).startswith('broker-') else other).append((name, meta))
    for name, meta in other:
        print('OUT ' + json.dumps({'step': 'file', 'name': name, **meta}), flush=True)
    days = sorted(n[len('broker-'):] for n, _ in broker)
    print('OUT ' + json.dumps({'step': 'broker_days', 'files': len(days), 'first': days[:1], 'last': days[-1:],
                               'on_or_before_as_of': sum(d <= as_of for d in days), 'after_as_of': sum(d > as_of for d in days),
                               'bytes': sum((m.get('bytes') or 0) for _, m in broker)}), flush=True)
    for ref in ('tickers', 'brokers', 'stock_lists'):
        status, doc = get('/reference/' + ref)
        print('OUT ' + json.dumps({'step': 'reference', 'name': ref, 'status': status, 'shape': shape(doc)}), flush=True)
    print('VERDICT PROBED', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:  # noqa: BLE001 - the class only: a driver error may carry connection details
        print('ERR ' + type(e).__name__, flush=True)
        raise SystemExit(1)
    print('JOB_DONE', flush=True)
