"""Local only: prepare() of IHSG with one version of scripts/backfill_index_features.py (old copy or the branch), the
staged calc1..calc6 copied to regular tables reg_<tag>_calc<f> for comparison. compare_sample is skipped (no stored dev
rows locally). Usage: regress_ihsg.py <module_file> <tag> [from_date] [--apply]"""
import importlib.util
import sys
from datetime import date

REPO = '/home/user/saniti'
sys.path[:0] = [REPO + '/scripts', REPO + '/features/feature04']
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

path, tag = sys.argv[1], sys.argv[2]
from_date = date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] != '-' else None
apply = '--apply' in sys.argv
spec = importlib.util.spec_from_file_location('bif_' + tag, path)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
b.compare_sample = lambda *a, **k: b.emit('accepted_sample_skipped_locally')
with psycopg.connect('host=/home/pgr/pg port=55432 user=postgres dbname=ent', row_factory=dict_row, autocommit=True) as db:
    db.execute("SET work_mem='64MB'")
    with db.transaction():
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        info = b.prepare(db, 'IHSG', date(2025, 6, 2), False, from_date=from_date)
    for f in range(1, 7):
        db.execute(f'DROP TABLE IF EXISTS reg_{tag}_calc{f}')
        db.execute(f'CREATE TABLE reg_{tag}_calc{f} AS SELECT * FROM calc{f}')
    if apply:
        import uuid
        b.apply_chunks(db, 'IHSG', uuid.uuid4(), from_date=info['from_date'])
    print('DONE', tag, info['from_date'], info['window_first'])
