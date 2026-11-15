"""Read-only from dev (pgweb), written into the local rehearsal database only."""
import sys, json
sys.path.insert(0, 'verification/terminal_api')
import pgq, psycopg
LOCAL = 'host=/home/pgr/pg port=55432 user=postgres dbname=igh'
PULL = [
    ('IDX_Stock_Universe_History', 'SELECT * FROM public."IDX_Stock_Universe_History"'),
    ('Reference_History_Capture_Log', 'SELECT * FROM public."Reference_History_Capture_Log"'),
    ('IDX_Stock_Universe', 'SELECT * FROM public."IDX_Stock_Universe"'),
    ('Universe_Fixed_income', 'SELECT * FROM public."Universe_Fixed_income"'),
    ('Stock_List', 'SELECT * FROM public."Stock_List"'),
    ('Table_Catalog', '''SELECT * FROM public."Table_Catalog" WHERE table_name LIKE '%\\_INDEX' OR table_name IN ('IDX_Stock_Universe','Stock_List','Stock_List_Member','Stock_List_Member_History')'''),
    ('Column_Catalog', '''SELECT * FROM public."Column_Catalog" WHERE table_name IN ('IDX_Stock_Universe','Stock_List')'''),
    ('Database_Table_Status', '''SELECT * FROM public."Database_Table_Status" WHERE "Table Name" IN ('IDX_Stock_Universe','IDX_Stock_Universe_History','Reference_History_Capture_Log','Price_Stock_Indonesia_IDX')'''),
    ('Price_Stock_Indonesia_IDX', '''SELECT * FROM public."Price_Stock_Indonesia_IDX" WHERE ticker IN ('IHSG','BBCA') AND date >= '2026-09-15' '''),
    ('price_stock_idx_intraday', '''SELECT * FROM public.price_stock_idx_intraday WHERE ticker IN ('IHSG','BBCA') AND timeframe = '1h' AND session_date >= '2026-09-15' '''),
    ('Feature_01_Stock_Daily_INDEX', '''SELECT * FROM public."Feature_01_Stock_Daily_INDEX" WHERE ticker='IHSG' AND date >= '2026-11-01' '''),
    ('Feature_06_Foreign_Domestic_INDEX', '''SELECT * FROM public."Feature_06_Foreign_Domestic_INDEX" WHERE ticker='IHSG' AND trade_date >= '2026-11-01' '''),
]
with psycopg.connect(LOCAL, autocommit=False) as c:
    c.execute("SET session_replication_role = replica")      # loading copies: no triggers fire while seeding
    for table, sql in PULL:
        r = pgq.q(sql)
        if 'error' in r: raise SystemExit(table + ': ' + r['error'])
        cols = r['columns']
        local_cols = [x[0] for x in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s AND is_generated='NEVER' AND (identity_generation IS NULL OR identity_generation<>'ALWAYS')", (table,)).fetchall()]
        use = [i for i, n in enumerate(cols) if n in local_cols]
        names = ','.join('"%s"' % cols[i] for i in use)
        with c.cursor().copy(f'COPY public."{table}" ({names}) FROM STDIN') as cp:
            for row in r['rows']:
                cp.write_row([(json.dumps(row[i]) if isinstance(row[i], (dict, list)) else row[i]) for i in use])
        print(table, len(r['rows']))
    c.commit()
