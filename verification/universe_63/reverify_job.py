"""EXEC-UNIVERSE-BROKER S1.2b: the sessions after the newest broker summary date (2026-11-04, 2026-11-05) for the codes
added to the universe, through the price cron's own recovery (--mode recovery --reverify-all --target-date D), so its
P2 no-trade rule and monitoring apply (a no-trade pair is cross-checked once the broker summary of D is loaded).
params.json: {"dates": ["2026-11-04", ...]}"""
import json, subprocess, sys
for d in json.load(open('params.json'))['dates']:
    run = subprocess.run([sys.executable, 'apps/idx-price-cron/price_update.py', '--mode', 'recovery', '--reverify-all',
                          '--target-date', d, '--request-bars', '7'], capture_output=True, text=True, timeout=1800)
    lines = [l for l in run.stdout.splitlines() if '"event"' in l][-3:]
    print('RESULT ' + json.dumps({'date': d, 'rc': run.returncode, 'tail': lines,
                                  'stderr': run.stderr.strip().splitlines()[-1:] if run.returncode else []}), flush=True)
print('JOB_DONE', flush=True)
