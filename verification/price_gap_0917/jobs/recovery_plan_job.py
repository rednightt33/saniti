"""EXEC-PRICE-GAP-0917 S7 check (orc-test-runner, scripts/onboarding/run_job.sh): the recovery's plan against live
data, read-only (`recovery_window.py --plan-only`: no price run, no monitoring row, no notice). Ends with JOB_DONE."""
import subprocess
import sys

try:
    r = subprocess.run([sys.executable, '-u', 'recovery_window.py', '--plan-only'], capture_output=True, text=True,
                       timeout=600)
    for line in r.stdout.splitlines():
        print('OUT ' + line, flush=True)
    if r.returncode:
        print('ERR ' + r.stderr[-2000:], flush=True)
finally:
    print('JOB_DONE', flush=True)
