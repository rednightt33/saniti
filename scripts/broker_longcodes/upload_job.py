"""EXEC-UNIVERSE-BROKER S3 stage U6: upload the checked rows of longcode_broker.py (rows/<date>.csv.gz, the 15 columns of
IDX_Broker_Summary) for the codes that are not four letters. Runs on orc-test-runner (scripts/onboarding/run_job.sh) with
the rows folder beside it. The user's filter (2026-11-05): a key not in the table is inserted; a key there with the same
15 values is dropped; a key there with other values is reported and never overwritten. Four-letter codes are refused.

Per date, one transaction, as the loader's upload_day: the loader's advisory lock (stockbit-full-broker-summary-import)
is held for the whole job, so no broker round writes at the same time; the publisher's write lock is held (shared), so
terminal-publisher waits (EXEC-PUBLISH-FLOW). After the insert, the new rows are read back and compared with the staged
rows; a difference rolls the date back. DRYRUN rolls every date back and reports the same counts.

params.json: {"mode": "DRYRUN" | "APPLY", "dates": ["2026-09-01", ...] (empty: every file in rows/), "large_write": true}
Prints one DATE line per date and a SUMMARY line."""
import gzip
import json
import os
import re
from pathlib import Path

import psycopg
from psycopg import sql

COLS = ['Date', 'Symbol', 'Broker', 'Investor Type', 'Market Board', 'Buy Value', 'Sell Value', 'Net Value',
        'Buy Lots', 'Sell Lots', 'Net Lots', 'Avg Buy', 'Avg Sell', 'buy_freq', 'sell_freq']
KEYS = COLS[:5]
FOUR = re.compile(r'^[A-Z]{4}$')
LOADER_LOCK = 'stockbit-full-broker-summary-import'
PUBLISH_WRITE_LOCK = 'terminal_publish_write'

P = json.load(open('params.json'))
MODE = P['mode']
assert MODE in ('DRYRUN', 'APPLY')
files = sorted(Path('rows').glob('*.csv.gz'))
dates = P.get('dates') or [f.name[:10] for f in files]
cols = sql.SQL(',').join(map(sql.Identifier, COLS))
keys = sql.SQL(',').join(map(sql.Identifier, KEYS))
join_on = sql.SQL(' AND ').join(sql.SQL('t.{c} = s.{c}').format(c=sql.Identifier(c)) for c in KEYS)
same = sql.SQL(' AND ').join(sql.SQL('t.{c} IS NOT DISTINCT FROM s.{c}').format(c=sql.Identifier(c)) for c in COLS[5:])


def out(kind, **fields):
    print(f'{kind} ' + json.dumps(fields, default=str), flush=True)


totals = {'dates': 0, 'staged': 0, 'inserted': 0, 'same': 0, 'different': 0}
with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, application_name='broker-longcodes-upload') as db:
    if not db.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (LOADER_LOCK,)).fetchone()[0]:
        raise SystemExit('the broker loader holds its lock (a round is running); nothing written')
    db.execute('SELECT pg_advisory_lock_shared(hashtext(%s))', (PUBLISH_WRITE_LOCK,))
    actual = [r[0] for r in db.execute("""SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='IDX_Broker_Summary' ORDER BY ordinal_position""").fetchall()]
    if actual != COLS:
        raise SystemExit('IDX_Broker_Summary differs from the 15-column template; nothing written')
    for day in dates:
        path = Path('rows') / f'{day}.csv.gz'
        with gzip.open(path, 'rt', newline='') as f:
            header = f.readline().rstrip('\r\n').split(',')
            body = f.read()
        if header != COLS:
            raise SystemExit(f'{path}: header differs from the table columns')
        try:
            with db.transaction():
                db.execute("SET LOCAL lock_timeout='20s'")
                db.execute("SET LOCAL statement_timeout='10min'")
                db.execute('CREATE TEMP TABLE stage_lc (LIKE public."IDX_Broker_Summary" INCLUDING DEFAULTS) ON COMMIT DROP')
                with db.cursor() as cur:
                    with cur.copy(sql.SQL("COPY stage_lc ({}) FROM STDIN WITH (FORMAT csv, NULL '')").format(cols)) as copy:
                        copy.write(body)
                n, dates_in, four, dup = db.execute(sql.SQL(
                    '''SELECT count(*), count(DISTINCT "Date"), count(*) FILTER (WHERE "Symbol" ~ '^[A-Z]{{4}}$'),
                              count(*) - (SELECT count(*) FROM (SELECT DISTINCT {} FROM stage_lc) k) FROM stage_lc''').format(keys)
                ).fetchone()
                if dates_in != 1 or str(db.execute('SELECT min("Date") FROM stage_lc').fetchone()[0]) != day:
                    raise ValueError('rows of another date in the file')
                if four or dup:
                    raise ValueError(f'four-letter rows {four}, duplicate keys {dup}')
                matched = db.execute(sql.SQL(
                    '''SELECT count(*) FILTER (WHERE {same}), count(*) FILTER (WHERE NOT ({same}))
                       FROM stage_lc s JOIN public."IDX_Broker_Summary" t ON {on}''').format(same=same, on=join_on)).fetchone()
                examples = db.execute(sql.SQL(
                    '''SELECT s."Symbol", s."Broker", s."Investor Type", s."Market Board" FROM stage_lc s
                       JOIN public."IDX_Broker_Summary" t ON {on} WHERE NOT ({same}) LIMIT 5''').format(
                    on=join_on, same=same)).fetchall()
                inserted = db.execute(sql.SQL(
                    '''INSERT INTO public."IDX_Broker_Summary" ({c}) SELECT {c} FROM stage_lc s
                       WHERE NOT EXISTS (SELECT 1 FROM public."IDX_Broker_Summary" t WHERE {on})
                       ON CONFLICT ({k}) DO NOTHING''').format(c=cols, on=join_on, k=keys)).rowcount
                if inserted != n - matched[0] - matched[1]:
                    raise ValueError(f'inserted {inserted}, expected {n - matched[0] - matched[1]}')
                readback = db.execute(sql.SQL(
                    '''SELECT count(*) FROM stage_lc s LEFT JOIN public."IDX_Broker_Summary" t ON {on}
                       WHERE t."Symbol" IS NULL OR NOT ({same})''').format(on=join_on, same=same)).fetchone()[0]
                if readback != matched[1]:
                    raise ValueError(f'read back: {readback} staged rows absent or different, {matched[1]} expected')
                result = dict(date=day, staged=n, inserted=inserted, same=matched[0], different=matched[1],
                              different_examples=examples)
                if MODE == 'DRYRUN':
                    raise RuntimeError('DRYRUN')
        except RuntimeError as e:
            if str(e) != 'DRYRUN':
                raise
        out('DATE', mode=MODE, **result)
        totals['dates'] += 1
        for k in ('staged', 'inserted', 'same', 'different'):
            totals[k] += result[k]
    db.execute('SELECT pg_advisory_unlock_shared(hashtext(%s))', (PUBLISH_WRITE_LOCK,))
    db.execute('SELECT pg_advisory_unlock(hashtext(%s))', (LOADER_LOCK,))
out('SUMMARY', mode=MODE, **totals)
print('JOB_DONE', MODE, flush=True)
