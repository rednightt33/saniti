"""EXEC-MU-ACCOUNTS fix round, track guest: run scripts/edge_test_account.py as a job on the private network.

run_job.sh starts `python -u job.py` without arguments, so this wrapper reads them from params.json:
    {"email": "<the user's own address>", "plan": "<plan key>", "reason": "<why, who asked>", "off": false}
Stage it with the script as an extra:
    scripts/onboarding/run_job.sh scripts/onboarding/edge_test_account_job.py params.json log.txt scripts/edge_test_account.py
Only for the user's own addresses, with the user's go (EXEC.md EXEC-MU-ACCOUNTS, the pre-launch mode). Keep params.json
out of Git (it names an address). Prints what the script prints (user id, username, plan, outcome), never a secret or
the address.
"""
import json
import sys

import edge_test_account

p = json.load(open("params.json"))
args = ["--email", str(p["email"]), "--plan", str(p["plan"]), "--reason", str(p["reason"])]
args += ["--off"] if p.get("off") else []
args += ["--username", str(p["username"])] if p.get("username") else []
code = edge_test_account.main(args)
print("JOB_DONE")
sys.exit(code)
