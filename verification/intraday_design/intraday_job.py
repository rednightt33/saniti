"""EXEC-INTRADAY-IDX: run apps/idx-price-cron/intraday_update.py on orc-test-runner (scripts/onboarding/run_job.sh with
price_update.py, intraday_update.py and requirements.txt as extras). params.json: {"args": ["--mode", "backfill", ...]}.
Every output line is passed through as OUT; ends with JOB_DONE. No secret is printed."""
import json
import subprocess
import sys

args = json.load(open('params.json'))['args']
try:
    proc = subprocess.Popen([sys.executable, '-u', 'intraday_update.py', *args], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        print('OUT ' + line.rstrip(), flush=True)
    print('VERDICT ' + json.dumps({'exit_code': proc.wait()}), flush=True)
finally:
    print('JOB_DONE', flush=True)
