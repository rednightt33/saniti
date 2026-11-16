"""EXEC-MU-ACCOUNTS Phase 1 (ERRORS M478): run scripts/edge_mfa_unlock.py as a job on the private network.

run_job.sh starts `python -u job.py` without arguments, so this wrapper reads them from params.json:
    {"username": "<username>", "reason": "<why, who asked>"}
Stage it with the unlock script as an extra:
    scripts/onboarding/run_job.sh scripts/onboarding/edge_mfa_unlock_job.py params.json log.txt scripts/edge_mfa_unlock.py
Only with the user's approval for that account (EXEC.md EXEC-MU-ACCOUNTS, Phase 1 deploy step 9). Prints what the
unlock script prints (user id and counts), never a secret.
"""
import json
import sys

import edge_mfa_unlock

p = json.load(open("params.json"))
code = edge_mfa_unlock.main(["--username", str(p["username"]), "--reason", str(p["reason"])])
print("JOB_DONE")
sys.exit(code)
