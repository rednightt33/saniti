"""Close the four stockbit-updater rounds of 2026-11-09 left RUNNING when Postgres OOM-killed their connection
(user go 2026-11-09 "Boleh"). Exactly these execution_ids, only while RUNNING; refuses unless all four match.
Run with scripts/onboarding/run_job.sh; prints OUT lines and JOB_DONE. No secret is printed."""
import json
import os

import psycopg

IDS = ['65a2b6cb-6ad9-41ae-be44-5d0124b1dcbe', '552c9a44-ce42-4e34-a234-4290f2dab630',
       '12372c4d-650f-4981-bf2b-985772ce93d1', '28c3b97f-63d0-4f1b-a221-a0e7ae6694b0']
ERROR = ('Terputus: Postgres OOM (limit 512 MB) memutus koneksi; container dijalankan ulang oleh Railway. '
         'Ditutup manual 2026-11-09 (putaran 325f4864 menyelesaikan langkah berikutnya).')
with psycopg.connect(os.environ['DATABASE_URL']) as c:
    rows = c.execute("""UPDATE public."Monitoring_Stockbit_Update"
                        SET status = 'FAILED', last_error = %s, finished_at = updated_at, updated_at = now()
                        WHERE execution_id = ANY(%s::uuid[]) AND status = 'RUNNING' AND finished_at IS NULL
                        RETURNING execution_id::text, finished_at""", (ERROR, IDS)).fetchall()
    if sorted(r[0] for r in rows) != sorted(IDS):
        c.rollback()
        print('ERR ' + json.dumps({'q': 'close', 'error': f'expected 4 RUNNING rows, matched {len(rows)}'}), flush=True)
    else:
        c.commit()
        print('OUT ' + json.dumps({'q': 'close', 'rows': [[r[0], str(r[1])] for r in rows]}), flush=True)
print('JOB_DONE CLOSE_STALE_ROUNDS', flush=True)
