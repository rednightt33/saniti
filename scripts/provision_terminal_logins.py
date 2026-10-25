#!/usr/bin/env python3
"""EXEC-TERMINAL-API: create or rotate the two terminal logins after migration 20261025_001.

Requires DATABASE_URL (admin), TERMINAL_DB_PASSWORD and TERMINAL_PUBLISHER_DB_PASSWORD; never prints any of them.
terminal_api_login       -> terminal_runtime (schema terminal) + terminal_market_reader (four market tables)
terminal_publisher_login -> terminal_market_reader only
Rejects elevated or unexpected privileges, and checks afterwards that each login reaches exactly the expected relations.
"""
import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

MARKET = {('public', t) for t in ('Price_Stock_Indonesia_IDX', 'Feature_05_Foreign_Domestic_Broker_Detail',
                                   'IDX_Broker_Profile', 'IDX_Stock_Universe')}
TERMINAL = {('terminal', t) for t in ('subscriber', 'session', 'access_log', 'sign_in_attempt', 'quota',
                                      'quota_override', 'admin_log')}
LOGINS = {
    'terminal_api_login': {'env': 'TERMINAL_DB_PASSWORD', 'groups': {'terminal_runtime', 'terminal_market_reader'},
                           'reach': MARKET | TERMINAL, 'limit': 20,
                           'settings': [('statement_timeout', '10s'), ('lock_timeout', '2s'),
                                        ('idle_in_transaction_session_timeout', '15s'),
                                        ('search_path', 'terminal,pg_catalog')]},
    'terminal_publisher_login': {'env': 'TERMINAL_PUBLISHER_DB_PASSWORD', 'groups': {'terminal_market_reader'},
                                 'reach': MARKET, 'limit': 4,
                                 'settings': [('statement_timeout', '120s'), ('lock_timeout', '2s'),
                                              ('idle_in_transaction_session_timeout', '60s'),
                                              ('default_transaction_read_only', 'on'),
                                              ('search_path', 'pg_catalog')]},
}
ELEVATED = ('rolsuper', 'rolcreatedb', 'rolcreaterole', 'rolreplication', 'rolbypassrls')


def main():
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        raise RuntimeError('DATABASE_URL required')
    with psycopg.connect(url, row_factory=dict_row) as c:
        for group in ('terminal_runtime', 'terminal_market_reader'):
            if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (group,)).fetchone():
                raise RuntimeError('Apply migration 20261025_001 first')
        for login, spec in LOGINS.items():
            password = os.environ.get(spec['env'], '')
            if len(password) < 32:
                raise RuntimeError(f"strong {spec['env']} required")
            existing = c.execute('SELECT * FROM pg_roles WHERE rolname=%s', (login,)).fetchone()
            if existing:
                if any(existing[k] for k in ELEVATED):
                    raise RuntimeError(f'{login} has elevated privileges; reconcile first')
                member_of = {r['rolname'] for r in c.execute(
                    'SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid '
                    'JOIN pg_roles u ON u.oid=m.member WHERE u.rolname=%s', (login,))}
                if not member_of <= spec['groups']:
                    raise RuntimeError(f'{login} memberships differ; reconcile first')
            verb = 'ALTER' if existing else 'CREATE'
            c.execute(sql.SQL(verb + ' ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS '
                              'CONNECTION LIMIT {} PASSWORD {}').format(
                sql.Identifier(login), sql.Literal(spec['limit']), sql.Literal(password)))
            for group in sorted(spec['groups']):
                c.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier(group), sql.Identifier(login)))
            for name, value in spec['settings']:
                c.execute(sql.SQL('ALTER ROLE {} SET {} = {}').format(
                    sql.Identifier(login), sql.Identifier(name), sql.Literal(value)))
            # Include inherited PUBLIC rights: a grant there is still a leak even with a dedicated login.
            reach = c.execute(
                "SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%%' "
                "AND c.relkind IN ('r','p','v','m','f') "
                "AND has_table_privilege(%s, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')",
                (login,)).fetchall()
            got = {(r['nspname'], r['relname']) for r in reach}
            if got != spec['reach']:
                raise RuntimeError(f'{login} reaches unexpected relations ({len(got)}); provisioning rolled back')
            print(f'{login} provisioned; reaches exactly {len(got)} relations')


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as e:
        raise SystemExit(f'terminal provisioning failed: {e}')
    except Exception:
        # Driver errors may include credentials; never print the exception.
        raise SystemExit('terminal provisioning failed; inspect roles/grants read-only without printing secrets')
