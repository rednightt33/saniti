"""EXEC option A, the example mode (the user, 2026-11-21: "mode contoh pakai opsi A"; EXEC.md): a read-only check of the
data on the proposed example date and the days around it, so the user can confirm the date before the cut is made.

For each table in params.json (the tables the examples would read), the job finds its date column and its ticker
column in information_schema, then reports:
- max(date);
- the rows per date over the window;
- where no date-leading index exists, the rows per date of the given tickers instead.

Guards (AGENTS.md "Postgres memory after large updates"): every query runs in one READ ONLY transaction with a 30 s
statement timeout, and only after its EXPLAIN shows no sequential scan of the table. A query that would read a table
whole is reported as skipped, never run. Prints OUT lines (JSON), VERDICT and JOB_DONE. No secret is printed.

Run: scripts/onboarding/run_job.sh verification/edge_multiuser/example_mode/date_check_job.py \
       verification/edge_multiuser/example_mode/params.json <log>
"""
import datetime
import json
import os

import psycopg

p = json.load(open('params.json'))
DATE_COLUMNS = ('date', 'trade_date', 'Date')
TICKER_COLUMNS = ('ticker', 'Ticker', 'Symbol', 'symbol', 'stock_code', 'index_code', 'code')


def out(**kw):
    print('OUT ' + json.dumps(kw, default=str), flush=True)


def q(name):
    return '"' + name.replace('"', '""') + '"'


def plan_reads_whole(conn, sql, args):
    """(True when the plan scans the table whole, the plan's first line). EXPLAIN only plans; the values are bound on the
    client so the plan is the one the real query gets."""
    with psycopg.ClientCursor(conn) as cc:
        text = '\n'.join(r[0] for r in cc.execute('EXPLAIN ' + sql, args).fetchall())
    seq = [line.strip() for line in text.splitlines() if 'Seq Scan' in line]
    return bool(seq), (seq[0] if seq else text.splitlines()[0] if text else '')[:160]


def main():
    day = datetime.date.fromisoformat(p['date'])
    start, end = datetime.date.fromisoformat(p['from']), datetime.date.fromisoformat(p['to'])
    tickers = p['tickers']
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=False) as conn, conn.cursor() as c:
        c.execute('SET TRANSACTION READ ONLY')
        c.execute("SET LOCAL statement_timeout = '30s'")
        c.execute('SET LOCAL max_parallel_workers_per_gather = 0')
        skipped = 0
        for table in p['tables']:
            cols = {r[0]: r[1] for r in c.execute(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
                (table,)).fetchall()}
            if not cols:
                out(table=table, error='no such table'); skipped += 1; continue
            dc = next((n for n in DATE_COLUMNS if cols.get(n) == 'date'), None)
            tc = next((n for n in TICKER_COLUMNS if n in cols), None)
            row = {'table': table, 'date_column': dc, 'ticker_column': tc}
            if dc is None:
                out(**row, error='no date column'); skipped += 1; continue
            sql = f'SELECT max({q(dc)}) FROM public.{q(table)}'
            whole, head = plan_reads_whole(conn, sql, ())
            row['max_date'] = None if whole else c.execute(sql).fetchone()[0]
            if whole:
                row['max_date_skipped'] = head
            sql = (f'SELECT {q(dc)}, count(*) FROM public.{q(table)} WHERE {q(dc)} BETWEEN %s AND %s '
                   f'GROUP BY 1 ORDER BY 1')
            whole, head = plan_reads_whole(conn, sql, (start, end))
            if not whole:
                row['rows_per_date'] = {str(d): n for d, n in c.execute(sql, (start, end)).fetchall()}
            elif tc is not None:
                sql = (f'SELECT {q(dc)}, count(*) FROM public.{q(table)} WHERE {q(tc)} = ANY(%s) '
                       f'AND {q(dc)} BETWEEN %s AND %s GROUP BY 1 ORDER BY 1')
                whole, head = plan_reads_whole(conn, sql, (tickers, start, end))
                if not whole:
                    row['ticker_rows_per_date'] = {str(d): n for d, n in c.execute(sql, (tickers, start, end)).fetchall()}
            if whole:
                row['window_skipped'] = head; skipped += 1
            per = row.get('rows_per_date') or row.get('ticker_rows_per_date') or {}
            row['on_date'] = per.get(str(day), 0)
            out(**row)
        conn.rollback()
    print(f'VERDICT {"PARTIAL" if skipped else "OK"} skipped={skipped}', flush=True)
    print('JOB_DONE', flush=True)


main()
