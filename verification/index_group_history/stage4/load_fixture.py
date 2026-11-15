"""Read-only from dev (pgweb) into the local stage 4 test database `ent`. Small fixture: nine member stocks of four
small KONGLO groups, raw broker rows and stock Feature 05 rows 2024-01-02..2025-10-31, prices of IHSG/LQ45/IDXBASIC."""
import json
import sys
import time

sys.path.insert(0, 'verification/terminal_api')
import pgq  # noqa: E402
import psycopg  # noqa: E402

LOCAL = 'host=/home/pgr/pg port=55432 user=postgres dbname=ent'
SYMS = ['AMMN', 'BRMS', 'BBHI', 'MEGA', 'CITA', 'NCKL', 'TIRT', 'ARCI', 'BWPT']
ENT = ['IHSG', 'LQ45', 'IDXBASIC', 'GAGOES', 'GCTCORP', 'GHARITA', 'GRAJAWALI']
S = "(" + ",".join(f"'{s}'" for s in SYMS) + ")"
E = "(" + ",".join(f"'{s}'" for s in ENT) + ")"
LISTS = "(SELECT list_key FROM public.\"Feature_Index_Entity\" WHERE ticker IN " + E + " AND list_key IS NOT NULL)"


def months():
    y, m = 2024, 1
    while (y, m) <= (2025, 10):
        ny, nm = (y + (m == 12), m % 12 + 1)
        yield f'{y}-{m:02d}-01', f'{ny}-{nm:02d}-01'
        y, m = ny, nm


PULL = [
    ('IDX_Broker_Profile', 'SELECT * FROM public."IDX_Broker_Profile"'),
    ('IDX_Stock_Universe', f'SELECT * FROM public."IDX_Stock_Universe" WHERE "Ticker" IN {S} OR "Ticker" IN {E}'),
    ('IDX_Stock_Universe_History', f'SELECT * FROM public."IDX_Stock_Universe_History" WHERE "Ticker" IN {S} OR "Ticker" IN {E}'),
    ('Stock_List', f'SELECT * FROM public."Stock_List" WHERE list_key IN {LISTS}'),
    ('Stock_List_Member_History', f'SELECT * FROM public."Stock_List_Member_History" WHERE list_key IN {LISTS} AND list_key NOT IN (\'INDEX:550\',\'INDEX:467\')'),
    ('Feature_Index_Entity', f'SELECT * FROM public."Feature_Index_Entity" WHERE ticker IN {E}'),
    ('Price_Stock_Indonesia_IDX', f'SELECT * FROM public."Price_Stock_Indonesia_IDX" WHERE ticker IN (\'IHSG\',\'LQ45\',\'IDXBASIC\') AND timeframe=\'Daily\' AND is_final'),
]
for lo, hi in months():
    PULL.append(('IDX_Broker_Summary', f'SELECT * FROM public."IDX_Broker_Summary" WHERE "Symbol" IN {S} AND "Date" >= \'{lo}\' AND "Date" < \'{hi}\''))
    PULL.append(('Feature_05_Foreign_Domestic_Broker_Detail', f'SELECT * FROM public."Feature_05_Foreign_Domestic_Broker_Detail" WHERE ticker IN {S} AND trade_date >= \'{lo}\' AND trade_date < \'{hi}\''))

with psycopg.connect(LOCAL, autocommit=False) as c:
    c.execute("SET session_replication_role = replica")
    for table, q in PULL:
        t = time.time()
        r = pgq.q(q)
        if 'error' in r:
            raise SystemExit(table + ': ' + r['error'])
        cols = r['columns']
        local = [x[0] for x in c.execute("""SELECT column_name FROM information_schema.columns WHERE table_schema='public'
            AND table_name=%s AND is_generated='NEVER' AND (identity_generation IS NULL OR identity_generation<>'ALWAYS')""", (table,))]
        use = [i for i, n in enumerate(cols) if n in local]
        names = ','.join('"%s"' % cols[i] for i in use)
        with c.cursor().copy(f'COPY public."{table}" ({names}) FROM STDIN') as cp:
            for row in r['rows']:
                cp.write_row([(json.dumps(row[i]) if isinstance(row[i], (dict, list)) else row[i]) for i in use])
        print(table, len(r['rows']), round(time.time() - t, 1), 's', flush=True)
    c.commit()
