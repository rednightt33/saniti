"""EXEC-MU-ACCOUNTS option A (ERRORS M513 A1): run scripts/edge_account_login.py as a job on the private network.

run_job.sh starts `python -u job.py` without arguments on orc-test-runner, so this wrapper reads them from params.json:
    {"username": "<the account's current username>", "reason": "<why, who asked>", "set": ["username", "email",
     "password"]}
`set` names what to write from the live admin's variables, which live on orc-test-runner itself since 2026-11-20 (moved
from edge-bff-live so the public process never holds them; EXEC option A): EDGE_ADMIN_USERNAME, EDGE_ADMIN_EMAIL and
EDGE_ADMIN_INITIAL_PASSWORD. To change the live admin's login, change those variables on orc-test-runner, then:
    scripts/onboarding/run_job.sh scripts/onboarding/edge_account_login_job.py params.json log.txt \
        scripts/edge_account_login.py apps/edge-bff/app/security.py
Prints what the script prints (user id, usernames, whether an address and a password were set and read back, the
outcome), never a password, a verifier or an address.
"""
import json
import os
import sys

import edge_account_login

FROM = {"username": ("EDGE_ADMIN_USERNAME", "ACCOUNT_NEW_USERNAME"),
        "email": ("EDGE_ADMIN_EMAIL", "ACCOUNT_NEW_EMAIL"),
        "password": ("EDGE_ADMIN_INITIAL_PASSWORD", "ACCOUNT_NEW_PASSWORD")}

p = json.load(open("params.json"))
wanted = p.get("set") or []
unknown = [w for w in wanted if w not in FROM]
missing = [FROM[w][0] for w in wanted if w in FROM and not os.environ.get(FROM[w][0])]
if unknown or missing or not wanted:
    print(json.dumps({"outcome": "refused_params", "unknown": unknown, "missing_variables": missing,
                      "set": wanted}))
    print("JOB_DONE")
    sys.exit(2)
for w in wanted:
    source, target = FROM[w]
    os.environ[target] = os.environ[source]
code = edge_account_login.main(["--username", str(p["username"]), "--reason", str(p["reason"])])
print("JOB_DONE")
sys.exit(code)
