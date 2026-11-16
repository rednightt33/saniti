"""EXEC-INDEX-GROUP-HISTORY stage 7 (user go 2026-11-15: "Langsung go tahap 4-9, ..."): migration 20261115_004 (the
INDEX catalog texts for indexes, sectors and groups) and the vocabulary sync of scripts/sync_feature_vocabulary.py with
the rebuilt seed, in ONE transaction (the pattern of verification/feature_vocabulary_20261025/apply_012_and_sync_job.py).
DRYRUN rolls back; APPLY commits, then runs the Feature catalog audit read-only. Prints OUT lines and JOB_DONE.
Extras: scripts, database."""
import json
import subprocess
import sys

import os
import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, "scripts")
from sync_feature_vocabulary import MIGRATION, SOURCES, inventory, sync, validate_seed  # noqa: E402

mode = json.load(open("params.json"))["mode"]
assert mode in ("DRYRUN", "APPLY")
body = open("database/migrations/20261115_004_index_entities_catalog.sql").read()
start, end = body.find("BEGIN;"), body.rstrip().rfind("COMMIT;")
seed = json.load(open("database/feature_vocabulary_seed.json"))
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, application_name="index-entities-catalog") as db:
    db.execute(body[start + len("BEGIN;"):end], prepare=False)
    copies = db.execute("SELECT target, text_column, sum(updated)::int AS rows FROM m_count GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
    print("OUT " + json.dumps({"migration": "004 body ok", "copies": copies}), flush=True)
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended('feature-vocabulary-sync',0))")
    validate_seed(seed, inventory(db))
    db.execute(open(MIGRATION).read(), prepare=False)
    changed = sync(db, seed)
    rerun = sync(db, seed)
    assert rerun == 0, rerun
    actual = db.execute('SELECT * FROM public."Feature_Vocabulary" WHERE source_table=ANY(%s)', (SOURCES,)).fetchall()
    validate_seed(actual, inventory(db))
    expected = {(r["source_table"], r["column_name"]): r for r in seed}
    assert all(all(r[c] == expected[(r["source_table"], r["column_name"])][c] for c in seed[0]) for r in actual)
    # the Indonesian meaning the model reads is the vocabulary definition of the same column
    differ = db.execute('''SELECT a.table_name, a.column_name FROM public."AI_column_catalog" a
        JOIN public."Feature_Vocabulary" v ON v.source_schema = 'public' AND v.source_table = a.table_name
         AND v.column_name = a.column_name AND v.language_code = 'id-ID'
        WHERE a.table_name LIKE '%\\_INDEX' AND a.description_id_status = 'REVIEWED'
          AND a.description_id IS DISTINCT FROM v.definition''').fetchall()
    assert not differ, differ[:5]
    sample = db.execute('''SELECT table_name, left(description, 260) AS description FROM public."AI_table_catalog"
        WHERE table_name LIKE '%\\_INDEX' ORDER BY 1''').fetchall()
    print("OUT " + json.dumps({"vocabulary_changed": changed, "rerun": rerun, "entries": len(actual),
                               "description_id_differ": len(differ), "descriptions": sample}, ensure_ascii=False,
                              default=str), flush=True)
    if mode == "DRYRUN":
        db.rollback()
    else:
        db.commit()
print("OUT " + json.dumps({"committed": mode == "APPLY"}), flush=True)
if mode == "APPLY":
    r = subprocess.run([sys.executable, "scripts/audit_feature_catalog_semantics.py"], capture_output=True, text=True)
    print("OUT " + json.dumps({"audit_rc": r.returncode, "audit": r.stdout[-3000:], "err": r.stderr[-1500:]}), flush=True)
print("VERDICT PASS", flush=True)
print("JOB_DONE", mode, flush=True)
