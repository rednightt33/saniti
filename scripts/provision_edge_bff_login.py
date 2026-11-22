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
# EDGE backtest (migration 20261026_005): reachable once that migration is applied, then all three, each with exactly the
# privileges the migration grants it (what app/backtest.py does: jobs are never deleted, results never updated, the K3
# trials never deleted)
BACKTEST_GRANTS = {'backtest_jobs':{'SELECT','INSERT','UPDATE'},'backtest_results':{'SELECT','INSERT','DELETE'},
                   'backtest_trials':{'SELECT','INSERT','UPDATE'}}
BACKTEST_TABLES = set(BACKTEST_GRANTS)
# EDGE screener (migration 20261028_001, EXEC-SCREENER P12 a): reachable once that migration is applied, then both, each
# with exactly the privileges the migration grants it (what app/screener.py does: saved items are listed, created,
# replaced and deleted; watchlist rows are added and removed, never updated)
SCREENER_GRANTS = {'screener_items':{'SELECT','INSERT','UPDATE','DELETE'},'watchlist_items':{'SELECT','INSERT','DELETE'}}
SCREENER_TABLES = set(SCREENER_GRANTS)
# EXEC-TERMINAL-LAYOUTS (migration 20261106_001): the Terminal's saved layouts are listed, created, replaced, marked and deleted
LAYOUT_GRANTS = {'terminal_layouts':{'SELECT','INSERT','UPDATE','DELETE'}}
# EXEC-IND-PRESETS (migration 20261106_002): the Terminal's indicator presets, the same operations
PRESET_GRANTS = {'indicator_presets':{'SELECT','INSERT','UPDATE','DELETE'}}
PRESET_TABLES = set(PRESET_GRANTS)
# EXEC-DRAW-PANES (migration 20261107_001): the Terminal's drawings are read, created, replaced and deleted
DRAWING_GRANTS = {'terminal_drawings':{'SELECT','INSERT','UPDATE','DELETE'}}
DRAWING_TABLES = set(DRAWING_GRANTS)
LAYOUT_TABLES = set(LAYOUT_GRANTS)
# EXEC-WATCHLIST (migration 20261116_001): the Watchlist's named lists are listed, created, renamed, re-chosen and deleted
WATCHLIST_GRANTS = {'watchlist_lists':{'SELECT','INSERT','UPDATE','DELETE'}}
WATCHLIST_TABLES = set(WATCHLIST_GRANTS)
# EXEC-MU-ACCOUNTS Phase 0 (migration 20261116_002): the sign-in throttle is read, counted (insert or update) and purged
THROTTLE_GRANTS = {'auth_throttle':{'SELECT','INSERT','UPDATE','DELETE'}}
THROTTLE_TABLES = set(THROTTLE_GRANTS)
# EXEC-MU-ACCOUNTS Phase 1 (migration 20261116_003): the account tables, each with exactly what edge-bff does to it; the
# outbox and suppression list are never deleted from, the audit is only read and added to (no UPDATE, no DELETE)
ACCOUNT_GRANTS = {'users':{'SELECT','INSERT','UPDATE','DELETE'},'identities':{'SELECT','INSERT','UPDATE','DELETE'},
                  'email_codes':{'SELECT','INSERT','UPDATE','DELETE'},'mfa_totp':{'SELECT','INSERT','UPDATE','DELETE'},
                  'mfa_recovery_codes':{'SELECT','INSERT','UPDATE','DELETE'},'email_outbox':{'SELECT','INSERT','UPDATE'},
                  'email_suppression':{'SELECT','INSERT','UPDATE'},'admin_audit':{'SELECT','INSERT'},
                  'user_preferences':{'SELECT','INSERT','UPDATE','DELETE'}}
ACCOUNT_TABLES = set(ACCOUNT_GRANTS)
# the identity sequences of those tables: USAGE only (nextval through the column default)
ACCOUNT_SEQUENCES = {'users_user_id_seq','email_codes_code_id_seq','email_outbox_outbox_id_seq','admin_audit_audit_id_seq'}
# EXEC-MU-ACCOUNTS Phase 1 auth flows (migration 20261117_001): each Resend webhook delivery once (read and added)
REGISTRATION_GRANTS = {'email_hook_events':{'SELECT','INSERT'}}
REGISTRATION_TABLES = set(REGISTRATION_GRANTS)
# EXEC-MU-ACCOUNTS Phase 2 (migration 20261117_003): the plan catalog is only read (a migration or an operator changes
# it); the overrides and subscriptions are read, added and updated, never deleted
CATALOG_GRANTS = {'plans':{'SELECT'},'capabilities':{'SELECT'},'plan_capabilities':{'SELECT'},
                  'user_capability_overrides':{'SELECT','INSERT','UPDATE'},'subscriptions':{'SELECT','INSERT','UPDATE'}}
CATALOG_TABLES = set(CATALOG_GRANTS)
# the subscriptions' identity sequence: USAGE only (nextval through the column default)
CATALOG_SEQUENCES = {'subscriptions_subscription_id_seq'}
# EXEC-MU-ACCOUNTS 3e (migration 20261121_001, ERRORS M527): the example mode's stored files are only read (the capture
# job writes them as the database owner; app/examples.py lists and reads them)
EXAMPLE_GRANTS = {'example_files':{'SELECT'}}
EXAMPLE_TABLES = set(EXAMPLE_GRANTS)
# Phase 4, the contact-support panel (migration 20261122_001): a ticket and its images are read, added and deleted; a
# ticket is updated (its status and delivery), an image never
SUPPORT_GRANTS = {'support_tickets':{'SELECT','INSERT','UPDATE','DELETE'},'support_attachments':{'SELECT','INSERT','DELETE'}}
SUPPORT_TABLES = set(SUPPORT_GRANTS)
# a table of a later migration is held to exactly its grants, TRUNCATE included
EXACT_GRANTS = {**BACKTEST_GRANTS, **SCREENER_GRANTS, **LAYOUT_GRANTS, **PRESET_GRANTS, **DRAWING_GRANTS, **WATCHLIST_GRANTS, **THROTTLE_GRANTS, **ACCOUNT_GRANTS, **REGISTRATION_GRANTS, **CATALOG_GRANTS, **EXAMPLE_GRANTS, **SUPPORT_GRANTS}

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
        found={(r['nspname'],r['relname']) for r in reachable};backtest={('edge_bff',name) for name in BACKTEST_TABLES}
        screener={('edge_bff',name) for name in SCREENER_TABLES};layouts={('edge_bff',name) for name in LAYOUT_TABLES};presets={('edge_bff',name) for name in PRESET_TABLES};drawings={('edge_bff',name) for name in DRAWING_TABLES};watchlists={('edge_bff',name) for name in WATCHLIST_TABLES};throttle={('edge_bff',name) for name in THROTTLE_TABLES};accounts={('edge_bff',name) for name in ACCOUNT_TABLES};registration={('edge_bff',name) for name in REGISTRATION_TABLES};catalog={('edge_bff',name) for name in CATALOG_TABLES};example={('edge_bff',name) for name in EXAMPLE_TABLES};support={('edge_bff',name) for name in SUPPORT_TABLES}
        # each later migration's tables: all of them or none (a migration grants its tables together)
        if found-backtest-screener-layouts-presets-drawings-watchlists-throttle-accounts-registration-catalog-example-support!={('edge_bff',name) for name in TABLES} or found&backtest not in (set(),backtest) \
                or found&screener not in (set(),screener) or found&layouts not in (set(),layouts) or found&presets not in (set(),presets) or found&drawings not in (set(),drawings) or found&watchlists not in (set(),watchlists) or found&throttle not in (set(),throttle) or found&accounts not in (set(),accounts) or found&registration not in (set(),registration) or found&catalog not in (set(),catalog) or found&example not in (set(),example) or found&support not in (set(),support):raise RuntimeError('EDGE has unexpected reachable relations; provisioning rolled back')
        for name in sorted(TABLES|(BACKTEST_TABLES if found&backtest else set())|(SCREENER_TABLES if found&screener else set())|(LAYOUT_TABLES if found&layouts else set())|(PRESET_TABLES if found&presets else set())|(DRAWING_TABLES if found&drawings else set())|(WATCHLIST_TABLES if found&watchlists else set())|(THROTTLE_TABLES if found&throttle else set())|(ACCOUNT_TABLES if found&accounts else set())|(REGISTRATION_TABLES if found&registration else set())|(CATALOG_TABLES if found&catalog else set())|(EXAMPLE_TABLES if found&example else set())|(SUPPORT_TABLES if found&support else set())):
            granted=EXACT_GRANTS.get(name,{'SELECT','INSERT','UPDATE','DELETE'})
            # a backtest or screener table is held to exactly its grants, TRUNCATE included (it would empty the trials as
            # DELETE would, and every owner's saved items at once)
            for privilege in ('SELECT','INSERT','UPDATE','DELETE',*(('TRUNCATE','REFERENCES','TRIGGER') if name in EXACT_GRANTS else ())):
                allowed=c.execute('SELECT has_table_privilege(%s,%s,%s) AS allowed',(LOGIN,'edge_bff.'+name,privilege)).fetchone()['allowed']
                if privilege in granted and not allowed:raise RuntimeError('Incomplete EDGE grants')
                if privilege not in granted and allowed:raise RuntimeError('Unexpected EDGE grants; reconcile first')
            # QA round 3 (L6): PUBLIC holds nothing on an EDGE table (every role would reach it; the login's own grants hide
            # a PUBLIC SELECT); live 2026-11-06: none of the 8 tables has a PUBLIC privilege
            if c.execute("SELECT has_table_privilege('public',%s,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS any",('edge_bff.'+name,)).fetchone()['any']:raise RuntimeError('PUBLIC can use an EDGE table; reconcile first')
        if found&accounts:
            # the account sequences: USAGE only, nothing for PUBLIC (Phase 1; the subscriptions' too, Phase 2)
            for name in sorted(ACCOUNT_SEQUENCES|(CATALOG_SEQUENCES if found&catalog else set())):
                held={p for p in ('USAGE','SELECT','UPDATE') if c.execute('SELECT has_sequence_privilege(%s,%s,%s) AS a',(LOGIN,'edge_bff.'+name,p)).fetchone()['a']}
                if held!={'USAGE'}:raise RuntimeError('Unexpected EDGE sequence grants; reconcile first')
                if c.execute("SELECT has_sequence_privilege('public',%s,'USAGE,SELECT,UPDATE') AS a",('edge_bff.'+name,)).fetchone()['a']:raise RuntimeError('PUBLIC can use an EDGE sequence; reconcile first')
        # fix round (re-check R1-41): has_table_privilege is false for a privilege held on columns only, so every check
        # above misses one (a column UPDATE on the audit, a column SELECT on a market table). EDGE's grants are
        # table-level only: any column privilege the login holds, itself, through a role it belongs to or through
        # PUBLIC, on any relation outside the system schemas, is unexpected.
        columns=c.execute("SELECT n.nspname,c.relname,a.attname,x.privilege_type FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(a.attacl) x WHERE a.attacl IS NOT NULL AND NOT a.attisdropped AND a.attnum>0 AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%%' AND CASE WHEN x.grantee=0 THEN true ELSE pg_has_role(%s,x.grantee,'USAGE') END",(LOGIN,)).fetchall()
        if columns:raise RuntimeError(f'Unexpected EDGE column grants on {len(columns)} column(s); reconcile first (read pg_attribute.attacl)')
    print(f'EDGE login provisioned; only the {len(found)} operational tables reachable, no column-level grant')

if __name__=='__main__':
    try:main()
    except Exception:
        # Driver errors may include credentials; never print the exception.
        raise SystemExit('EDGE provisioning failed; inspect roles/grants read-only without printing secrets')
