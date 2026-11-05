"""EXEC-UNIVERSE-BROKER S1.5 (user go 2026-11-05): publish the 63 codes added to the universe, with terminal-publisher's own
code (publisher.py next to this file, the deployed revision), on orc-test-runner. The bucket and database variables are
Railway references to terminal-publisher's (run_job.sh RUN_JOB_EXTRA_VARS); nothing secret is in params.json.
params.json: {"steps": [{"mode": "broker-range", "from": "2016-01-01", "to": "2026-12-31", "tickers": [...]},
                        {"mode": "logos"}, {"mode": "verify", "tickers": [...]}]}
Each step runs publisher.main(['publisher.py', mode]) with its TERMINAL_FROM / TERMINAL_TO / TERMINAL_TICKERS."""
import json
import os
import sys

import publisher

for step in json.load(open('params.json'))['steps']:
    for k in ('TERMINAL_FROM', 'TERMINAL_TO', 'TERMINAL_TICKERS'):
        os.environ.pop(k, None)
    if step.get('from'):
        os.environ['TERMINAL_FROM'], os.environ['TERMINAL_TO'] = step['from'], step['to']
    if step.get('tickers'):
        os.environ['TERMINAL_TICKERS'] = ','.join(step['tickers'])
    print('STEP ' + json.dumps({'mode': step['mode'], 'tickers': len(step.get('tickers') or [])}), flush=True)
    rc = publisher.main(['publisher.py', step['mode']])
    print('STEP_DONE ' + json.dumps({'mode': step['mode'], 'rc': rc}), flush=True)
    if rc:
        sys.exit(rc)
print('JOB_DONE', flush=True)
