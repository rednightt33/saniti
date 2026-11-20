"""EXEC-MU-ACCOUNTS option A (ERRORS M513 A1): run scripts/edge_account_login.py as a job on the private network.

run_job.sh starts `python -u job.py` without arguments, so this wrapper reads them from params.json:
    {"username": "<the account's current username>", "reason": "<why, who asked>"}
The new values come as Railway references, set on the runner for the run only and removed afterwards (never values):
    RUN_JOB_EXTRA_VARS='ACCOUNT_NEW_USERNAME=${{edge-bff-live.EDGE_ADMIN_USERNAME}}
        ACCOUNT_NEW_PASSWORD=${{edge-bff-live.EDGE_ADMIN_INITIAL_PASSWORD}}' \
    scripts/onboarding/run_job.sh scripts/onboarding/edge_account_login_job.py params.json log.txt \
        scripts/edge_account_login.py apps/edge-bff/app/security.py
Prints what the script prints (user id, usernames, whether a password was set and opens, the outcome), never a password,
a verifier or an address.
"""
import json
import sys

import edge_account_login

p = json.load(open("params.json"))
code = edge_account_login.main(["--username", str(p["username"]), "--reason", str(p["reason"])])
print("JOB_DONE")
sys.exit(code)
