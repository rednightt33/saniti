"""Close the two stockbit-updater rounds still RUNNING after 2026-11-09 although their deployments are gone (user go
2026-11-09: "jalankan nomor 1"): c7705209 (deployment 33e76340, started by Railway's redeploy after the usage-limit stop and
removed before any write) and e3331473 (2026-10-27, deployment 255ca937, long gone). They kept terminal-publisher waiting
(loaders_writing: a RUNNING round within ROUND_RUNNING_HOURS). Exactly these execution_ids, only while RUNNING; refuses
unless both match. Run with scripts/onboarding/run_job.sh; prints OUT lines and JOB_DONE. No secret is printed."""
import json
import os

import psycopg

IDS = ['c7705209-f09a-4bf3-805c-596984c11ae4', 'e3331473-678d-453c-acb3-122855c64fee']
ERROR = ('Ditutup manual 2026-11-09: deployment putaran ini sudah tidak ada (dihentikan atau diganti) sehingga baris tetap '
         'RUNNING dan menahan terminal-publisher. Tidak ada data yang ditulis putaran ini setelah baris terakhir diperbarui.')
with psycopg.connect(os.environ['DATABASE_URL']) as c:
    rows = c.execute("""UPDATE public."Monitoring_Stockbit_Update"
                        SET status = 'FAILED', last_error = %s, finished_at = updated_at, updated_at = now()
                        WHERE execution_id = ANY(%s::uuid[]) AND status = 'RUNNING' AND finished_at IS NULL
                        RETURNING execution_id::text, finished_at""", (ERROR, IDS)).fetchall()
    if sorted(r[0] for r in rows) != sorted(IDS):
        c.rollback()
        print('ERR ' + json.dumps({'q': 'close', 'error': f'expected 2 RUNNING rows, matched {len(rows)}'}), flush=True)
    else:
        c.commit()
        print('OUT ' + json.dumps({'q': 'close', 'rows': [[r[0], str(r[1])] for r in rows]}), flush=True)
print('JOB_DONE CLOSE_DEAD_ROUNDS_2', flush=True)
