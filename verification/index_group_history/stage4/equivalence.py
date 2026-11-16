"""Local only. For each entity of the local fixture, in one session:
(1) Feature 02 whole entity (one statement) = per broker/investor/board pair (the IHSG way);
(2) Feature 06 from the collapsed rows = from the broker rows (both over the same window).
Prints one line per entity and check."""
import sys
from datetime import date

REPO = '/home/user/saniti'
sys.path[:0] = [REPO + '/scripts', REPO + '/features/feature04']
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
import backfill_index_entities as x  # noqa: E402
import backfill_index_features as b  # noqa: E402

UNTIL = date(2025, 9, 30)


def snapshot(db, src, dst):
    db.execute(f'DROP TABLE IF EXISTS {dst}')
    db.execute(f'CREATE TEMP TABLE {dst} AS SELECT * FROM {src}')


def differ(db, a, c, skip=('calculated_at',)):
    cols = [r['attname'] for r in db.execute(f"""SELECT attname FROM pg_attribute WHERE attrelid='pg_temp.{a}'::regclass
        AND attnum>0 AND NOT attisdropped ORDER BY attnum""") if r['attname'] not in skip]
    s = ','.join(f'"{n}"' for n in cols)
    n = db.execute(f'SELECT count(*) AS n FROM ((SELECT {s} FROM {a} EXCEPT ALL SELECT {s} FROM {c}) UNION ALL '
                   f'(SELECT {s} FROM {c} EXCEPT ALL SELECT {s} FROM {a})) z').fetchone()['n']
    rows = db.execute(f'SELECT (SELECT count(*) FROM {a}) AS a, (SELECT count(*) FROM {c}) AS c').fetchone()
    return n, rows['a'], rows['c']


with psycopg.connect('host=/home/pgr/pg port=55432 user=postgres dbname=ent', row_factory=dict_row, autocommit=True) as db:
    db.execute("SET work_mem='64MB'")
    ents = x.load_entities(db)
    p = x.plan(db, ents, UNTIL)
    names = [e['ticker'] for e in p['entities']]
    x.stage_members(db, names)
    x.create_read_tables(db)
    x.read_months(db, p['first'], p['last'], names, names, p['window_first'])
    for e in p['entities']:
        t = e['ticker']
        with db.transaction():
            x.stage_entity(db, e, p['window_first'], e['from_date'], e['mode'], p['first'], p['first'])
        # (1) Feature 02: rerun per pair into calc2 and compare with the whole-entity rows
        snapshot(db, 'calc2', 'whole2')
        db.execute('DROP TABLE feature_02_v2_daily_base')
        db.execute('TRUNCATE calc2, calc3')
        b.stage2(db, t, whole=False)
        print('F02', t, 'differing=%s whole=%s per_pair=%s' % differ(db, 'whole2', 'calc2'), flush=True)
        # (2) Feature 06: broker rows of the window (bulk5, the IHSG path) vs collapsed rows of the same window
        db.execute('DELETE FROM collapsed6 WHERE trade_date < %s', (p['window_first'],))
        for name in ('strict5', 'frequency_daily', 'frequency_masks'):
            db.execute(f'DROP TABLE {name}')
        db.execute('TRUNCATE calc5, calc6')
        b.stage6(db, t, collapsed='collapsed6')
        snapshot(db, 'calc6', 'collapsed_calc6')
        for name in ('strict5', 'frequency_daily', 'frequency_masks'):
            db.execute(f'DROP TABLE {name}')
        db.execute('TRUNCATE calc5, calc6')
        b.stage6(db, t)
        print('F06', t, 'differing=%s collapsed=%s broker=%s' % differ(db, 'collapsed_calc6', 'calc6'), flush=True)
