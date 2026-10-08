#!/usr/bin/env python3
"""PROPOSED approved-rollout helper; requires DATABASE_URL and EDGE_DB_PASSWORD, never logs either.
Only provisions the new edge_bff login/group; rejects unexpected existing privileges before rotation.
"""
import os
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
LOGIN, GROUP = 'edge_bff_login', 'edge_bff_runtime'
TABLES = {'sessions','jobs','conversation_ui'}

def main():
    url,password=os.environ.get('DATABASE_URL',''),os.environ.get('EDGE_DB_PASSWORD','')
    if not url or len(password)<32:raise RuntimeError('DATABASE_URL and strong EDGE_DB_PASSWORD required')
    with psycopg.connect(url,row_factory=dict_row) as c:
        if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(GROUP,)).fetchone():raise RuntimeError('Apply EDGE migration first')
        existing=c.execute('SELECT * FROM pg_roles WHERE rolname=%s',(LOGIN,)).fetchone()
        if existing:
            if any(existing[k] for k in ('rolsuper','rolcreatedb','rolcreaterole','rolreplication','rolbypassrls')):raise RuntimeError('Existing EDGE login has elevated privileges; reconcile first')
            membership={r['rolname'] for r in c.execute('SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles u ON u.oid=m.member WHERE u.rolname=%s',(LOGIN,))}
            if membership!={GROUP}:raise RuntimeError('Existing EDGE memberships differ; reconcile first')
        verb='ALTER' if existing else 'CREATE'
        c.execute(sql.SQL(verb+' ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20 PASSWORD {}').format(sql.Identifier(LOGIN),sql.Literal(password)))
        c.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier(GROUP),sql.Identifier(LOGIN)))
        for name,value in [('statement_timeout','5s'),('lock_timeout','2s'),('idle_in_transaction_session_timeout','15s'),('search_path','edge_bff,pg_catalog')]:
            c.execute(sql.SQL('ALTER ROLE {} SET {} = {}').format(sql.Identifier(LOGIN),sql.Identifier(name),sql.Literal(value)))
        # Include inherited PUBLIC rights: a grant there is still a leak even with a dedicated login.
        reachable=c.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%%' AND c.relkind IN ('r','p','v','m','f') AND has_table_privilege(%s,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')",(LOGIN,)).fetchall()
        if {(r['nspname'],r['relname']) for r in reachable}!={('edge_bff',name) for name in TABLES}:raise RuntimeError('EDGE has unexpected reachable relations; provisioning rolled back')
        for name in TABLES:
            for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
                if not c.execute('SELECT has_table_privilege(%s,%s,%s) AS allowed',(LOGIN,'edge_bff.'+name,privilege)).fetchone()['allowed']:raise RuntimeError('Incomplete EDGE grants')
    print('EDGE login provisioned; only three operational tables reachable')

if __name__=='__main__':
    try:main()
    except Exception:
        # Driver errors may include credentials; never print the exception.
        raise SystemExit('EDGE provisioning failed; inspect roles/grants read-only without printing secrets')
