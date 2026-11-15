"""EXEC-INDEX-GROUP-HISTORY stage 6 read-back (read-only, dev through pgweb): checks of the stored entity rows that do not
use the script's own code.
1. Per kind (INDEX, SECTOR, GROUP) the stored rows per table, their first and last date: every entity starts at its
   rows_from, a group has no Feature 01/04 row.
2. For sample entities, the stored foreign cumulative net (Feature 06 INDEX, board Regular) on the first stored date
   equals the sum of the members' raw foreign buy minus sell from 2016-01-04 through that date (members by date from
   the history tables, the rule of the module text of scripts/backfill_index_entities.py).
3. The stored Feature 05 INDEX buy value of one date equals the members' raw sum (by broker, investor type, board).
Usage: python3 verification/index_group_history/readback_check.py [TICKER ...]"""
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, 'verification/terminal_api')
if not os.environ.get('DATABASE_URL'):
    import pgq  # noqa: E402

SAMPLES = sys.argv[1:] or ['GPRAJOGO', 'GSALIM', 'LQ45', 'IDXENERGY']
if os.path.exists('params.json'):
    SAMPLES = json.load(open('params.json')).get('tickers') or SAMPLES
MEMBERS = '''WITH lists AS (
    SELECT h.list_key, h."Ticker" AS symbol, h.pit_valid_from AS f, coalesce(h.pit_valid_to, 'infinity'::date) AS t
    FROM public."Stock_List_Member_History" h WHERE h.pit_valid_to IS NULL OR h.pit_valid_from < h.pit_valid_to),
  list_first AS (SELECT list_key, min(f) AS first FROM lists GROUP BY 1),
  universe AS (SELECT h."Ticker" AS symbol, h."Sector" AS sector, h."Security Type" AS kind, h.pit_valid_from AS f,
    coalesce(h.pit_valid_to, 'infinity'::date) AS t FROM public."IDX_Stock_Universe_History" h
    WHERE h.pit_valid_to IS NULL OR h.pit_valid_from < h.pit_valid_to),
  stock_first AS (SELECT symbol, min(f) AS first FROM universe GROUP BY 1),
  m AS (
    SELECT e.ticker, l.symbol, CASE WHEN l.f = lf.first THEN '-infinity'::date ELSE l.f END AS vf, l.t AS vt
    FROM public."Feature_Index_Entity" e JOIN lists l USING (list_key) JOIN list_first lf USING (list_key)
    WHERE e.member_source = 'STOCK_LIST' AND e.ticker = '{t}'
    UNION ALL
    SELECT e.ticker, u.symbol, CASE WHEN u.f = sf.first THEN '-infinity'::date ELSE u.f END, u.t
    FROM public."Feature_Index_Entity" e JOIN universe u ON u.sector = e.sector AND u.kind = 'stock'
    JOIN stock_first sf USING (symbol) WHERE e.member_source = 'UNIVERSE_SECTOR' AND e.ticker = '{t}')'''




if os.environ.get('DATABASE_URL'):  # on orc-test-runner (the long sums exceed pgweb's statement timeout)
    import psycopg  # noqa: E402
    from psycopg.rows import dict_row  # noqa: E402
    DB = psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, autocommit=True, application_name='index-readback')
    DB.execute('SET default_transaction_read_only = on')


def q(sql):
    if os.environ.get('DATABASE_URL'):
        return DB.execute(sql).fetchall()
    r = pgq.q(sql)
    if 'error' in r:
        raise SystemExit(r['error'] + '\n' + sql[:400])
    return [dict(zip(r['columns'], row)) for row in r['rows']]


out = {'per_kind': q('''SELECT e.entity_kind, count(DISTINCT f.ticker) AS entities, count(*) AS rows, min(f.trade_date)::text AS first,
        max(f.trade_date)::text AS last, bool_and(f.trade_date >= e.rows_from) AS from_rows_from
        FROM public."Feature_06_Foreign_Domestic_INDEX" f JOIN public."Feature_Index_Entity" e USING (ticker)
        WHERE e.ticker <> 'IHSG' GROUP BY 1 ORDER BY 1'''),
       'groups_with_price_rows': q('''SELECT count(*) AS n FROM public."Feature_01_Stock_Daily_INDEX" f
        JOIN public."Feature_Index_Entity" e USING (ticker) WHERE e.entity_kind = 'GROUP' ''')[0]['n']}
checks = []
for t in SAMPLES:
    first = q(f'''SELECT min(trade_date)::text AS d FROM public."Feature_06_Foreign_Domestic_INDEX"
                  WHERE ticker = '{t}' AND market_board = 'Regular' ''')[0]['d']
    stored = q(f'''SELECT foreign_cumulative_net::text AS v FROM public."Feature_06_Foreign_Domestic_INDEX"
                   WHERE ticker = '{t}' AND market_board = 'Regular' AND trade_date = '{first}' ''')[0]['v']
    members = q(MEMBERS.format(t=t) + ' SELECT symbol, vf::text AS vf, vt::text AS vt FROM m')
    vals = ','.join(f"('{x['symbol']}','{x['vf']}'::date,'{x['vt']}'::date)" for x in members)
    syms = ','.join(f"'{x['symbol']}'" for x in members)
    # the member symbols named in the statement, so the broker table is read through its key, symbol by symbol
    raw = q(f'''WITH m(symbol, vf, vt) AS (VALUES {vals})
        SELECT (sum(b."Buy Value") - sum(b."Sell Value"))::text AS v FROM public."IDX_Broker_Summary" b
        JOIN m ON m.symbol = b."Symbol" AND b."Date" >= m.vf AND b."Date" < m.vt
        WHERE b."Symbol" IN ({syms}) AND b."Date" <= '{first}' AND b."Investor Type" = 'Foreign'
          AND b."Market Board" = 'Regular' ''')[0]['v']
    day = q(f'''SELECT max(trade_date)::text AS d FROM public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX" WHERE ticker = '{t}' ''')[0]['d']
    f05 = q(f'''SELECT sum(buy_value)::text AS v, count(*) AS n FROM public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX"
                WHERE ticker = '{t}' AND trade_date = '{day}' ''')[0]
    raw05 = q(f'''WITH m(symbol, vf, vt) AS (VALUES {vals})
        SELECT sum(b."Buy Value")::text AS v, count(DISTINCT (b."Broker", b."Investor Type", b."Market Board")) AS n
        FROM public."IDX_Broker_Summary" b JOIN m ON m.symbol = b."Symbol" AND b."Date" >= m.vf AND b."Date" < m.vt
        WHERE b."Symbol" IN ({syms}) AND b."Date" = '{day}' ''')[0]
    checks.append({'ticker': t, 'first_date': first, 'cumulative_stored': stored, 'cumulative_raw': raw,
                   'cumulative_equal': stored is not None and raw is not None and Decimal(stored) == Decimal(raw),
                   'f05_date': day, 'f05_stored': f05, 'f05_raw': raw05,
                   'f05_equal': f05['v'] == raw05['v'] and f05['n'] == raw05['n']})
out['checks'] = checks
out['verdict'] = 'PASS' if all(c['cumulative_equal'] and c['f05_equal'] for c in checks) and not out['groups_with_price_rows'] else 'REVIEW'
print('OUT ' + json.dumps(out, default=str), flush=True)
print('VERDICT ' + out['verdict'], flush=True)
print('JOB_DONE', flush=True)
