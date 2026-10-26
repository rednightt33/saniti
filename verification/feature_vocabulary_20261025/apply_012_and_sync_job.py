"""Feature_Vocabulary corrections (EXEC.md, 2026-10-25): migration 20261025_012 and the vocabulary sync of
scripts/sync_feature_vocabulary.py in ONE transaction. DRYRUN rolls back; APPLY commits, then runs the Feature catalog
audit read-only. Prints OUT lines and JOB_DONE; no secret is printed."""
import json, os, subprocess, sys
import psycopg
from psycopg.rows import dict_row
sys.path.insert(0, "scripts")
from sync_feature_vocabulary import MIGRATION, SOURCES, inventory, sync, validate_seed  # noqa: E402

mode = json.load(open("params.json"))["mode"]
assert mode in ("DRYRUN", "APPLY")
body = open("database/migrations/20261025_012_feature_vocabulary_corrections.sql").read()
start, end = body.find("BEGIN;"), body.rstrip().rfind("COMMIT;")
seed = json.load(open("database/feature_vocabulary_seed.json"))
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, application_name="feature-vocabulary-012") as db:
    db.execute(body[start + len("BEGIN;"):end], prepare=False)
    print("OUT " + json.dumps({"migration": "012 body ok", "copies": db.execute(
        "SELECT copy, sum(updated)::int AS rows FROM m_vocab_copies GROUP BY 1 ORDER BY 1").fetchall()}), flush=True)
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended('feature-vocabulary-sync',0))")
    validate_seed(seed, inventory(db))
    db.execute(open(MIGRATION).read(), prepare=False)
    changed = sync(db, seed); rerun = sync(db, seed)
    assert rerun == 0, rerun
    actual = db.execute('SELECT * FROM public."Feature_Vocabulary" WHERE source_table=ANY(%s)', (SOURCES,)).fetchall()
    validate_seed(actual, inventory(db))
    expected = {(r["source_table"], r["column_name"]): r for r in seed}
    assert all(all(r[c] == expected[(r["source_table"], r["column_name"])][c] for c in seed[0]) for r in actual)
    left = db.execute("""SELECT count(*) AS n FROM public."Feature_Vocabulary" WHERE formula ~ 'Summary_Freq'
                         OR null_rule = 'NULL when the source has no frequency (non-4-letter symbols); never replaced by zero.'""").fetchone()
    sample = db.execute("""SELECT source_table, column_name, unit, null_rule FROM public."Feature_Vocabulary"
        WHERE (source_table, column_name) IN (('Feature_05_Foreign_Domestic_Broker_Detail','buy_freq'),
              ('Feature_06_Foreign_Domestic','foreign_buy_freq_1d'), ('Feature_06_Foreign_Domestic','foreign_net_percentile_5d_base60d'))""").fetchall()
    print("OUT " + json.dumps({"vocabulary_changed": changed, "rerun": rerun, "entries": len(actual), "stale_left": left["n"],
                               "sample": sample}, ensure_ascii=False, default=str), flush=True)
    if mode == "DRYRUN":
        db.rollback()
    else:
        db.commit()
print("OUT " + json.dumps({"committed": mode == "APPLY"}), flush=True)
if mode == "APPLY":
    r = subprocess.run([sys.executable, "scripts/audit_feature_catalog_semantics.py"], capture_output=True, text=True)
    print("OUT " + json.dumps({"audit_rc": r.returncode, "audit": r.stdout[-3000:], "err": r.stderr[-1500:]}), flush=True)
print("JOB_DONE", mode, flush=True)
