"""EXEC-FI-DATE B check (user go 2026-11-01): one manual weekly consensus check per market with the deployed code
(fixed_income_update.py --mode consensus). Report only: nothing is written; each report goes to Telegram. JOB_DONE."""
import json, subprocess, sys
for market in ("ID", "US"):
    r = subprocess.run([sys.executable, '-u', 'fixed_income_update.py', '--market', market, '--mode', 'consensus'],
                       capture_output=True, text=True, timeout=1500)
    for line in r.stdout.splitlines():
        if 'consensus_' in line or 'telegram_notify' in line:
            print('OUT', market, line[:3000], flush=True)
    print('OUT', json.dumps({'market': market, 'exit': r.returncode, 'stderr_tail': r.stderr[-800:]}), flush=True)
print('JOB_DONE CONSENSUS', flush=True)
