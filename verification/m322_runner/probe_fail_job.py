"""RUNNER-RETRY live check (user 2026-11-01 "OK": restart policy NEVER): a job that fails (exit 3) runs once and is not
started again; the wrapper prints JOB_EXIT 3 and the runner guard counts the job as finished."""
import json
print('OUT ' + json.dumps({'q': 'runner_never_probe', 'note': 'exits with 3 on purpose'}), flush=True)
raise SystemExit(3)
