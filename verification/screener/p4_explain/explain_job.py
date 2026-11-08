"""P4 release (EXEC-SCREENER-FLOW-CANDLES, user go 2026-11-08 "Ok merge"): read-only EXPLAIN (ANALYZE, BUFFERS) of the
three statements the publisher runs for the Screener's broker day files, on dev, before their first fill (AGENTS.md
Performance: bounded plans before a new high-frequency query; P4_BROKER_DAYS.md section 2). Nothing is written.

The statements are publisher.py's own constants (publisher.py is shipped beside this job), so the plans are of the exact
SQL the publisher runs:
  window   BROKER_DAYS_WINDOW_SQL with 60: the index skip scan for the 60 newest trade dates
  day      BROKER_DAY_SQL for the newest date and the stock tickers of the universe
  stamps   BROKER_DAY_STAMPS_SQL over the 60 dates (the sweep run's aggregate, about 1.47 M rows)

params.json: statement_timeout_ms, work_mem, large_write (the stamps read is a large read: run_job.sh / the coordinator
runs the Postgres restart check after it). OUT lines are short (ERRORS R08).
"""
import json
import os
import sys
import time

import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publisher as pub  # noqa: E402

P = json.load(open('params.json'))


def out(kind, **kw):
    print('OUT ' + json.dumps({'part': kind, **kw}, default=str), flush=True)


def explain(c, name, sql, params):
    t = time.monotonic()
    plan = c.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + sql, params).fetchone()[0][0]
    top = plan['Plan']
    def walk(n, depth=0, acc=None):
        acc = [] if acc is None else acc
        acc.append({'d': depth, 'node': n.get('Node Type'), 'index': n.get('Index Name'), 'rows': n.get('Actual Rows'),
                    'loops': n.get('Actual Loops'), 'ms': n.get('Actual Total Time'),
                    'hit': n.get('Shared Hit Blocks'), 'read': n.get('Shared Read Blocks')})
        for k in n.get('Plans', []):
            walk(k, depth + 1, acc)
        return acc
    nodes = walk(top)
    out(name, execution_ms=plan.get('Execution Time'), planning_ms=plan.get('Planning Time'),
        wall_s=round(time.monotonic() - t, 2), rows=top.get('Actual Rows'),
        shared_hit=top.get('Shared Hit Blocks'), shared_read=top.get('Shared Read Blocks'))
    for k in range(0, len(nodes), 4):
        out(name + '_nodes', nodes=nodes[k:k + 4])
    seq = [n for n in nodes if n['node'] == 'Seq Scan']
    out(name + '_verdict', seq_scans=len(seq), index_nodes=sorted({n['index'] for n in nodes if n['index']}))
    return plan


def main():
    url = os.environ['DATABASE_URL']
    with psycopg.connect(url, autocommit=True,
                         options=(f"-c default_transaction_read_only=on "
                                  f"-c statement_timeout={int(P.get('statement_timeout_ms', 600000))} "
                                  f"-c work_mem={P.get('work_mem', '64MB')}")) as c:
        print('READONLY ' + json.dumps(c.execute('SHOW transaction_read_only').fetchone()), flush=True)
        window = [d for (d,) in c.execute(pub.BROKER_DAYS_WINDOW_SQL, (pub.BROKER_DAY_SESSIONS,)).fetchall()]
        out('window_dates', first=window[0] if window else None, last=window[-1] if window else None, n=len(window))
        explain(c, 'window', pub.BROKER_DAYS_WINDOW_SQL, (pub.BROKER_DAY_SESSIONS,))
        # the stock tickers of the universe, as the publisher's run builds `kind` (publisher.data_kind on Security Type)
        rows = c.execute(pub.UNIVERSE_SQL).fetchall()
        stocks = sorted(r[0] for r in rows if pub.data_kind(r[2]) == 'stock')
        out('stocks', n=len(stocks))
        if window:
            explain(c, 'day', pub.BROKER_DAY_SQL, (window[-1], stocks))
            explain(c, 'stamps', pub.BROKER_DAY_STAMPS_SQL, (window, stocks))
        print('JOB_DONE', flush=True)


if __name__ == '__main__':
    main()
