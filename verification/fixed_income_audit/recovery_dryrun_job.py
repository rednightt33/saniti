"""EXEC-FI-DATE A check (user go 2026-11-01): the new recovery mode, --dry-run (nothing written, no monitoring row, no
notice), for every enabled market. Prints the loader's recovery_window and dry_run_completed events. Ends with JOB_DONE."""
import json, subprocess, sys
for market in ("ID", "US"):
    r = subprocess.run([sys.executable, '-u', 'fixed_income_update.py', '--market', market, '--mode', 'recovery', '--dry-run'],
                       capture_output=True, text=True, timeout=900)
    for line in r.stdout.splitlines():
        if '"recovery_window"' in line or 'dry_run_completed' in line or 'bar_rejected' in line:
            print('OUT', market, line, flush=True)
    print('OUT', json.dumps({'market': market, 'exit': r.returncode, 'stderr_tail': r.stderr[-800:]}), flush=True)
print('JOB_DONE RECOVERY_DRYRUN', flush=True)
