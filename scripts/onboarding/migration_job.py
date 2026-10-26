"""NEW_TABLE_ONBOARDING_PLAN.md step 5: rehearse (DRYRUN) or apply (APPLY) onboarding migrations, then probe the result
as the AI roles see it. The pattern of EXEC-ONBOARD-1 (Feature 04).

params.json:
  {"mode": "DRYRUN", "migrations": ["20261101_001_onboard_feature06.sql"],
   "probes": [["reader_count", "market_ai_sql_reader", "SELECT count(*) FROM public.\"Feature_06_Foreign_Domestic\""],
              ["explain_cross_section", null, "EXPLAIN (ANALYZE, BUFFERS) SELECT ... WHERE trade_date = DATE '2026-10-21'"]]}
  mode        DRYRUN: every migration runs without its final COMMIT inside one open transaction, the probes run inside
              that transaction, then ROLLBACK (nothing is kept; locks are held for the duration, so rehearse a large
              CREATE INDEX on a copy or measure it in APPLY with CONCURRENTLY). APPLY: each migration commits, then the
              probes run read-only;
  migrations  files staged next to this job (pass them as extras to run_job.sh), applied in order;
  probes      [name, role or null, statement]: a role probe runs under SET LOCAL ROLE (the AI reader must read the
              exposed object and must NOT read a hidden base table: an expected refusal prints as ERR).

Prints `MIG ... sha256=` per file, `OUT`/`ERR` per probe, then JOB_DONE. No secret is printed.
"""
import hashlib
import json
import os
import time

import psycopg
from psycopg import sql

p = json.load(open("params.json"))
mode = p.get("mode", "DRYRUN")
assert mode in ("DRYRUN", "APPLY"), mode


def out(name, rows, ms):
    for i in range(0, max(len(rows), 1), 6):
        print("OUT " + json.dumps({"q": name, "ms": ms, "part": i // 6, "rows": rows[i:i + 6]}, default=str), flush=True)


with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
    if mode == "DRYRUN":
        conn.execute("BEGIN")
    for name in p["migrations"]:
        raw = open(name, "rb").read()
        body = raw.decode()
        print(f"MIG {mode} {name} sha256={hashlib.sha256(raw).hexdigest()}", flush=True)
        if mode == "APPLY":
            conn.execute(body)
            continue
        # the file's own BEGIN/COMMIT are left out so every file runs in the one rehearsal transaction. They are
        # located on lines that are not comments, so a commented rollback example ("-- COMMIT;") after the real
        # COMMIT cannot make the rehearsal commit (ERRORS M225); a second statement-level COMMIT refuses the file.
        lines = body.splitlines(keepends=True)
        offsets, pos = [], 0
        for line in lines:
            offsets.append(pos)
            pos += len(line)
        begins = [i for i, line in enumerate(lines) if line.strip().upper() == "BEGIN;"]
        commits = [i for i, line in enumerate(lines) if line.strip().upper() == "COMMIT;"]
        assert len(begins) == 1 and len(commits) == 1 and begins[0] < commits[0], \
            f"{name}: expected exactly one BEGIN; line and one COMMIT; line"
        assert all(not line.strip() or line.lstrip().startswith("--") for line in lines[commits[0] + 1:]), \
            f"{name}: only comments may follow COMMIT;"
        conn.execute(body[offsets[begins[0]] + len(lines[begins[0]]):offsets[commits[0]]])
        print(f"MIG DRYRUN_BODY_OK {name}", flush=True)
    if mode == "APPLY":
        conn.execute("BEGIN READ ONLY")
    for name, role, statement in p.get("probes") or []:
        conn.execute("SAVEPOINT probe")
        try:
            if role:
                conn.execute(f"SET LOCAL ROLE {sql.Identifier(role).as_string(conn)}")
            started = time.monotonic()
            rows = [list(r) for r in conn.execute(statement).fetchall()]
            out(name, rows, round((time.monotonic() - started) * 1000))
            conn.execute("RELEASE SAVEPOINT probe")
        except Exception as e:  # noqa: BLE001 - a refused probe is a result, not a failure of the job
            conn.execute("ROLLBACK TO SAVEPOINT probe")
            print("ERR " + json.dumps({"q": name, "error": f"{type(e).__name__}: {str(e)[:300]}"}), flush=True)
        conn.execute("RESET ROLE")
    conn.execute("ROLLBACK")
print("JOB_DONE MIGRATION", mode, flush=True)
