#!/usr/bin/env python3
"""EXEC-MU-ACCOUNTS fix round, track guest (verification/edge_multiuser/fix_round/guest.md): a test account of the live
site's pre-launch mode, for one of the user's own addresses and a plan.

The user, 2026-11-19 (EXEC.md EXEC-MU-ACCOUNTS): "Dan hanya admin yang bisa login (saya)", then "A" for trying the free
and paid plans: besides the admin only accounts marked as test accounts (made by the main agent for the user's own
addresses, who set their passwords through "Forgot password") sign in on the live site until the launch.

What it does, in one transaction, with one edge_bff.admin_audit row (actor 'operator', action account.test_mark, the
reason given), which migration 20261119_070's trigger requires for every change of the mark:
- no account with the address: makes one (owner key u_<24 hex>, the username given or made from the address, the names
  given or "Test Account", status active, the address marked verified: it is the user's own and the first reset proves
  the mailbox again), with a password identity no password opens (a random verifier: the user sets the password with
  "Forgot password"), marked test_account;
- an active account with the address: marks it;
- the plan: the default plan needs no subscription; any other plan gets an active subscription (provider 'test',
  provider_ref 'test-account'). A plan that holds '*' (the admin's), the guest plan, an unknown plan, or an account that
  already has an active subscription to another plan is refused (exit 1): the admin changes those in the Phase 4
  dashboard;
- `--off`: removes the mark (the account and its subscription stay).

Run it as a job on the private network (scripts/onboarding/run_job.sh with scripts/onboarding/edge_test_account_job.py),
never over a public URL:
    DATABASE_URL=... python3 scripts/edge_test_account.py --email <address> --plan <plan key> --reason "<why, who asked>"
It needs DATABASE_URL (a role that may write edge_bff.users, identities, subscriptions and admin_audit) and prints only
the user id, the username, the plan and the outcome; never the URL, a secret, a verifier or the address. Exit 1 when the
request is refused (the outcome names why).
"""
import argparse
import json
import os
import re
import secrets
import sys

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

EMAIL = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')
USERNAME = re.compile(r'[a-z0-9_]{3,30}')
PLAN = re.compile(r'[a-z][a-z0-9_]{1,31}')
RESERVED_USERNAMES = {'admin', 'root', 'support', 'edge', 'system'}
NAME = re.compile(r'[^\x00-\x1f\x7f<>]{1,100}')


def unusable_verifier():
    """A verifier of the shape edge-bff reads (app/security.py, scrypt$n=..$<salt>$<hash>) whose hash is random: no
    password derives it, so nobody signs in before the user sets a password with "Forgot password"."""
    return f'scrypt$n=16384,r=8,p=5${secrets.token_hex(16)}${secrets.token_hex(32)}'


def username_for(c, email, wanted):
    """The username given, else the address's local part made to fit ^[a-z0-9_]{3,30}$, with a number when taken."""
    if wanted:
        return wanted
    base = re.sub(r'[^a-z0-9_]', '_', email.split('@')[0].lower())[:24].strip('_') or 'tester'
    base = base if len(base) >= 3 else (base + '_test')[:24]
    if base in RESERVED_USERNAMES:
        base = base + '_test'
    for n in range(0, 1000):
        name = base if n == 0 else f'{base[:24]}_{n}'
        if not c.execute('SELECT 1 FROM edge_bff.users WHERE username = %s', (name,)).fetchone():
            return name
    raise SystemExit('no free username: pass --username')


def audit(c, user_id, before, after, reason):
    c.execute('''INSERT INTO edge_bff.admin_audit(actor_user_id, action, target_user_id, before, after, reason)
        VALUES (NULL, 'account.test_mark', %s, %s, %s, %s)''',
              (user_id, Jsonb({'actor': 'operator', **before}), Jsonb({'actor': 'operator', **after}),
               ('operator: ' + reason)[:1000]))


def apply(url, email, plan, reason, username=None, first='Test', last='Account', off=False):
    """{outcome, user_id, username, plan, test_account}; outcome 'refused_*' names a refusal (nothing changed)."""
    with psycopg.connect(url, row_factory=dict_row) as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', ('edge_test_account:' + email,))
        found = c.execute('''SELECT user_id, username, status, test_account FROM edge_bff.users WHERE email = %s
            AND status <> 'pending' FOR UPDATE''', (email,)).fetchone()
        if off:
            if found is None:
                return {'outcome': 'refused_no_account'}
            if found['test_account']:
                audit(c, found['user_id'], {'test_account': True}, {'test_account': False}, reason)
                c.execute('UPDATE edge_bff.users SET test_account = false WHERE user_id = %s', (found['user_id'],))
            return {'outcome': 'unmarked', 'user_id': found['user_id'], 'username': found['username'],
                    'test_account': False}
        row = c.execute('''SELECT p.plan_key, p.is_default, p.for_guests,
                EXISTS (SELECT 1 FROM edge_bff.plan_capabilities pc WHERE pc.plan_key = p.plan_key
                        AND pc.capability_key IN ('*', 'admin.access') AND pc.value = 'true'::jsonb) AS admin
            FROM edge_bff.plans p WHERE p.plan_key = %s''', (plan,)).fetchone()
        if row is None:
            return {'outcome': 'refused_unknown_plan', 'plan': plan}
        if row['admin'] or row['for_guests']:
            return {'outcome': 'refused_plan_not_for_test_accounts', 'plan': plan}
        if found is not None and found['status'] != 'active':
            return {'outcome': 'refused_account_not_active', 'user_id': found['user_id']}
        if found is None:
            name = username_for(c, email, username)
            created = c.execute('''INSERT INTO edge_bff.users(owner_key, username, email, email_verified_at, first_name,
                    last_name, role, status) VALUES (%s, %s, %s, now(), %s, %s, 'user', 'active')
                RETURNING user_id, username''', ('u_' + secrets.token_hex(12), name, email, first, last)).fetchone()
            c.execute('''INSERT INTO edge_bff.identities(user_id, provider, subject, verifier)
                VALUES (%s, 'password', %s, %s)''', (created['user_id'], str(created['user_id']), unusable_verifier()))
            found = {'user_id': created['user_id'], 'username': created['username'], 'test_account': False}
            outcome = 'created'
        else:
            outcome = 'marked'
        live = c.execute('''SELECT plan_key FROM edge_bff.subscriptions WHERE user_id = %s AND status = 'active'
            AND starts_at <= now() AND (expires_at IS NULL OR expires_at > now())''', (found['user_id'],)).fetchone()
        if live is not None and live['plan_key'] != plan:
            c.rollback()
            return {'outcome': 'refused_other_subscription', 'user_id': found['user_id'], 'plan': live['plan_key']}
        if live is None and not row['is_default']:
            c.execute('''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, provider, provider_ref)
                VALUES (%s, %s, 'active', 'test', 'test-account')''', (found['user_id'], plan))
        if not found['test_account']:
            audit(c, found['user_id'], {'test_account': False, 'plan': live['plan_key'] if live else None},
                  {'test_account': True, 'plan': plan}, reason)
            c.execute('UPDATE edge_bff.users SET test_account = true WHERE user_id = %s', (found['user_id'],))
        return {'outcome': outcome, 'user_id': found['user_id'], 'username': found['username'], 'plan': plan,
                'test_account': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--email', required=True)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--reason', required=True)
    parser.add_argument('--username')
    parser.add_argument('--first-name', default='Test')
    parser.add_argument('--last-name', default='Account')
    parser.add_argument('--off', action='store_true')
    args = parser.parse_args(argv)
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        raise SystemExit('DATABASE_URL is required')
    email = args.email.strip().lower()
    if not EMAIL.fullmatch(email) or len(email) > 254:
        raise SystemExit('--email is one address, e.g. name@example.com')
    if not PLAN.fullmatch(args.plan) or not args.reason.strip():
        raise SystemExit('--plan is a plan key (a-z 0-9 _) and --reason is required')
    if args.username and (not USERNAME.fullmatch(args.username) or args.username in RESERVED_USERNAMES):
        raise SystemExit('--username is a-z 0-9 _ (3 to 30) and not admin, root, support, edge or system')
    if not (NAME.fullmatch(args.first_name.strip()) and NAME.fullmatch(args.last_name.strip())):
        raise SystemExit('--first-name and --last-name are 1 to 100 characters of plain text')
    try:
        done = apply(url, email, args.plan, args.reason.strip(), args.username, args.first_name.strip(),
                     args.last_name.strip(), args.off)
    except psycopg.Error as e:
        # driver errors may include connection details or the address: only the class and the SQLSTATE
        raise SystemExit(json.dumps({'event': 'edge_test_account', 'outcome': 'failed', 'error': type(e).__name__,
                                     'sqlstate': getattr(e, 'sqlstate', None)}))
    print(json.dumps({'event': 'edge_test_account', **done}))
    return 1 if done['outcome'].startswith('refused') else 0


if __name__ == '__main__':
    sys.exit(main())
