"""EXEC-SCREENER-STOCK-LISTS (user 2026-11-09 "Lakukan implementasi db terlebih dahulu ... verified by reading the code"):
read-only check of the Stock_List tables the Screener will read, on dev, before the publisher writes the stock_lists
reference file. Nothing is written. publisher.py is shipped beside this job, so the statement is the publisher's own.

Parts (one OUT line each, short; ERRORS R08):
  lists      per kind: lists, enabled, with members, members, last_seen_at range (the publisher's STOCK_LISTS_SQL)
  universe   members against IDX_Stock_Universe: in it, of Security Type stock, outside it (the Screener's universe is
             the stocks of IDX_Stock_Universe)
  per_list   per list: code, kind, members, members that are stocks of the universe (lists with none are named)
  load_log   the last five Stock_List_Load_Log rows (status, counts, finished_at)
  explain    EXPLAIN (ANALYZE, BUFFERS) of STOCK_LISTS_SQL
"""
import json
import os
import sys
import time

import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publisher as pub  # noqa: E402

P = json.load(open('params.json'))


def out(part, **kw):
    print('OUT ' + json.dumps({'part': part, **kw}, default=str), flush=True)


def main():
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True,
                         options=f"-c default_transaction_read_only=on -c statement_timeout={int(P.get('statement_timeout_ms', 60000))}") as c:
        print('READONLY ' + json.dumps(c.execute('SHOW transaction_read_only').fetchone()), flush=True)
        t = time.monotonic()
        rows = c.execute(pub.STOCK_LISTS_SQL).fetchall()
        out('query', rows=len(rows), ms=round(1000 * (time.monotonic() - t), 1))
        uni = {r[0]: r[2] for r in c.execute(pub.UNIVERSE_SQL).fetchall()}
        for kind in ('INDEX', 'KONGLO'):
            ks = [r for r in rows if r[1] == kind]
            seen = [r[5] for r in ks if r[5] is not None]
            out('lists', kind=kind, lists=len(ks), with_members=sum(1 for r in ks if r[6]), members=sum(len(r[6]) for r in ks),
                last_seen_min=min(seen) if seen else None, last_seen_max=max(seen) if seen else None)
        members = {m for r in rows for m in r[6]}
        stocks = {m for m in members if uni.get(m) == 'stock'}
        out('universe', member_tickers=len(members), in_universe=sum(1 for m in members if m in uni), stocks=len(stocks),
            other_types=sorted({uni[m] for m in members if m in uni and uni[m] != 'stock'}),
            outside=len([m for m in members if m not in uni]), outside_sample=sorted(m for m in members if m not in uni)[:12],
            universe_stocks=sum(1 for v in uni.values() if v == 'stock'),
            universe_stocks_in_no_list=sum(1 for k, v in uni.items() if v == 'stock' and k not in members))
        per = [{'code': r[2], 'kind': r[1][0], 'n': len(r[6]), 'stocks': sum(1 for m in r[6] if uni.get(m) == 'stock')} for r in rows]
        for k in range(0, len(per), 11):
            out('per_list', lists=per[k:k + 11])
        out('no_stock', lists=[p['code'] for p in per if not p['stocks']])
        dup_names = sorted({r[3] for r in rows if sum(1 for x in rows if x[3] == r[3]) > 1})
        out('names', duplicate_names=dup_names, longest=max(len(r[3]) for r in rows) if rows else 0,
            sample_konglo=[r[3] for r in rows if r[1] == 'KONGLO'][:6])
        log = c.execute('SELECT run_id, status, lists_applied, members, added, removed, finished_at FROM public."Stock_List_Load_Log" '
                        'ORDER BY run_id DESC LIMIT 5').fetchall()
        out('load_log', rows=[list(r) for r in log])
        plan = c.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + pub.STOCK_LISTS_SQL).fetchone()[0][0]
        top = plan['Plan']
        out('explain', execution_ms=plan.get('Execution Time'), planning_ms=plan.get('Planning Time'), node=top.get('Node Type'),
            rows=top.get('Actual Rows'), shared_hit=top.get('Shared Hit Blocks'), shared_read=top.get('Shared Read Blocks'))
        print('JOB_DONE', flush=True)


if __name__ == '__main__':
    main()
