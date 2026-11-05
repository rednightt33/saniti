"""EXEC-UNIVERSE-BROKER S1.2 (user go 2026-11-05: "ok"): daily price history of the 63 codes added to IDX_Stock_Universe,
one code at a time with scripts/backfill_idx_price_ticker.py (its own checks, P3 no-trade rule), on orc-test-runner.

params.json: {"mode": "PREFLIGHT" | "APPLY", "start": "2018-01-02", "end": "2026-11-05",
              "tickers": [...], "fingerprints": {ticker: sha256} (APPLY), "accepted_extra": {ticker: [dates]} (optional)}
PREFLIGHT runs the script read-only per code and prints its history_preflight line. APPLY runs it with ACTION=apply and
the fingerprint of the reviewed preflight; a code whose source changed since then is refused by the script itself.
Prints one RESULT line per code and a SUMMARY line."""
import json
import os
import subprocess
import sys
import time

p = json.load(open('params.json'))
mode = p['mode']
assert mode in ('PREFLIGHT', 'APPLY')
results = []
for ticker in p['tickers']:
    env = {**os.environ, 'TICKER': ticker, 'START_DATE': p['start'], 'END_DATE': p['end'],
           'ACCEPTED_EXTRA_DATES': json.dumps(p.get('accepted_extra', {}).get(ticker, []))}
    if mode == 'APPLY':
        env.update(ACTION='apply', EXPECTED_FINGERPRINT=p['fingerprints'][ticker])
    started = time.monotonic()
    run = subprocess.run([sys.executable, 'scripts/backfill_idx_price_ticker.py'], env=env, capture_output=True,
                         text=True, timeout=600)
    events = []
    for line in run.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    pre = next((e for e in events if e.get('event') == 'history_preflight'), {})
    done = next((e for e in events if e.get('event') == 'history_committed'), None)
    error = (run.stderr.strip().splitlines() or [''])[-1][:300] if run.returncode else None
    result = {'ticker': ticker, 'rc': run.returncode, 'seconds': round(time.monotonic() - started, 1),
              'selected_rows': pre.get('selected_rows'), 'first': pre.get('first'), 'last': pre.get('last'),
              'missing_vs_bbca': pre.get('missing_vs_bbca'), 'no_trade_proven': pre.get('missing_no_trade_proven'),
              'unproven': pre.get('missing_unproven'), 'extra': pre.get('extra_vs_bbca'),
              'zero_volume': pre.get('zero_volume_rows'), 'fingerprint': pre.get('fingerprint'),
              'committed': done, 'error': error}
    results.append(result)
    print('RESULT ' + json.dumps(result, default=str), flush=True)
    time.sleep(1)
ok = [r for r in results if r['rc'] == 0]
print('SUMMARY ' + json.dumps({'mode': mode, 'codes': len(results), 'ok': len(ok),
                               'refused': [r['ticker'] for r in results if r['rc'] != 0],
                               'rows': sum((r['committed'] or {}).get('inserted_rows', 0) for r in results)}), flush=True)
print('JOB_DONE', mode, flush=True)
