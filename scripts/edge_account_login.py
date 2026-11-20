#!/usr/bin/env python3
"""EXEC-MU-ACCOUNTS option A (ERRORS M513 A1, site S3, switch-on S5): the operator sets an EDGE account's login name and
first password, audited, from values kept as Railway variables.

The user, 2026-11-20: "1. yes, feel free to suggest login ID dan passwordnya. kalau bisa jadikan ini variable di
railway". The live site's admin is user #1, seeded as `admin_1` (the beta's login `edge` is a reserved username) and
without an email address, so no reset reaches it. Its login name and a generated first password are kept as variables
of edge-bff-live (EDGE_ADMIN_USERNAME, EDGE_ADMIN_INITIAL_PASSWORD) for the user to read in Railway, and this script
writes them into the account. The site never reads those variables: the switch-on sign-in checks the account's own rows
(edge_bff.users.username or email, the password identity). To change the login again, change the variables and run the
job again.

What it does, in one transaction, with one edge_bff.admin_audit row (actor 'operator', action account.login_set, the
reason given; before and after name the username and whether a password was set, never a verifier or a password):
- finds the active account by its current username (--username);
- ACCOUNT_NEW_USERNAME (or --new-username): sets the username, by the site's rule (^[a-z0-9_]{3,30}$, not reserved,
  not taken; the table's CHECK and UNIQUE hold the same);
- ACCOUNT_NEW_PASSWORD (environment only, never an argument): sets the password identity's verifier with edge-bff's own
  app/security.py (password_verifier), at least 16 characters (a generated first password; the site's own rule is 8 to
  256), and clears the identity's failure count and lock. identities.seed_verifier_sha256 is left as it is, so the
  beta's switch-off seed sees the account's own password and keeps it (app/accounts.py seed; ERRORS R2-2): the beta's
  sign-in keeps reading EDGE_PASSWORD_VERIFIER, and the beta's login does not change.
- The sessions, the second factor and the email address stay as they are ("Sign out everywhere" on the site ends the
  sessions).
After the commit it reads the account back: the username, and that the stored verifier opens with the password.

Run it as a job on the private network (scripts/onboarding/run_job.sh with scripts/onboarding/edge_account_login_job.py,
the values as Railway references in RUN_JOB_EXTRA_VARS), never over a public URL:
    DATABASE_URL=... ACCOUNT_NEW_USERNAME=... ACCOUNT_NEW_PASSWORD=... \
        python3 scripts/edge_account_login.py --username <current username> --reason "<why, who asked>"
It needs DATABASE_URL (a role that may update edge_bff.users and identities and add to edge_bff.admin_audit) and prints
only the user id, the usernames before and after, whether a password was set and the outcome; never the URL, a password,
a verifier or an email address. Exit 1 when the request is refused (the outcome names why; nothing changed).
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

USERNAME = re.compile(r'[a-z0-9_]{3,30}')                       # app/accounts.py USERNAME (a test compares them)
RESERVED_USERNAMES = frozenset({'admin', 'root', 'support', 'edge', 'system'})   # app/accounts.py RESERVED_USERNAMES
FIRST_PASSWORD_MIN = 16


def security_module():
    """edge-bff's app/security.py, by its file: beside this script when the job stages it, else in the repository."""
    here = Path(__file__).resolve().parent
    for path in (here / 'security.py', here.parent / 'apps' / 'edge-bff' / 'app' / 'security.py'):
        if path.is_file():
            spec = importlib.util.spec_from_file_location('edge_bff_security', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise SystemExit('edge-bff app/security.py not found (stage it beside the script)')


def username_problem(name):
    if not USERNAME.fullmatch(name):
        return 'refused_username_rule'
    if name in RESERVED_USERNAMES:
        return 'refused_username_reserved'
    return None


def apply(url, username, reason, new_username=None, new_password=None, security=None):
    """{outcome, user_id, username_before, username_after, password_set}; outcome 'refused_*' names a refusal (nothing
    changed)."""
    security = security or security_module()
    if not new_username and not new_password:
        return {'outcome': 'refused_nothing_to_set'}
    if new_username:
        new_username = new_username.strip().lower()
        problem = username_problem(new_username)
        if problem:
            return {'outcome': problem}
    if new_password is not None and len(security.normal_password(new_password)) < FIRST_PASSWORD_MIN:
        return {'outcome': 'refused_password_short', 'minimum': FIRST_PASSWORD_MIN}
    if new_password is not None and len(security.normal_password(new_password)) > 256:
        return {'outcome': 'refused_password_long'}
    with psycopg.connect(url, row_factory=dict_row) as c:
        found = c.execute('''SELECT u.user_id, u.username, i.verifier, i.seed_verifier_sha256
            FROM edge_bff.users u JOIN edge_bff.identities i ON i.user_id = u.user_id AND i.provider = 'password'
            WHERE u.username = %s AND u.status = 'active' FOR UPDATE OF u, i''', (username,)).fetchone()
        if found is None:
            return {'outcome': 'refused_no_active_account'}
        after = found['username']
        if new_username and new_username != found['username']:
            if c.execute('SELECT 1 FROM edge_bff.users WHERE username = %s', (new_username,)).fetchone():
                return {'outcome': 'refused_username_taken', 'user_id': found['user_id']}
            c.execute('UPDATE edge_bff.users SET username = %s WHERE user_id = %s',
                      (new_username, found['user_id']))
            after = new_username
        if new_password is not None:
            c.execute('''UPDATE edge_bff.identities SET verifier = %s, sign_in_failures = 0, sign_in_locked_until = NULL,
                    updated_at = now() WHERE user_id = %s AND provider = 'password' ''',
                      (security.password_verifier(new_password), found['user_id']))
        c.execute('''INSERT INTO edge_bff.admin_audit(actor_user_id, action, target_user_id, before, after, reason)
            VALUES (NULL, 'account.login_set', %s, %s, %s, %s)''',
                  (found['user_id'], Jsonb({'actor': 'operator', 'username': found['username']}),
                   Jsonb({'actor': 'operator', 'username': after, 'password_set': new_password is not None}),
                   ('operator: ' + reason)[:1000]))
    with psycopg.connect(url, row_factory=dict_row) as c:
        back = c.execute('''SELECT u.username, i.verifier, i.seed_verifier_sha256 FROM edge_bff.users u
            JOIN edge_bff.identities i ON i.user_id = u.user_id AND i.provider = 'password' WHERE u.user_id = %s''',
                         (found['user_id'],)).fetchone()
    result = {'outcome': 'set', 'user_id': found['user_id'], 'username_before': found['username'],
              'username_after': back['username'], 'password_set': new_password is not None}
    if new_password is not None:
        result['password_opens'] = security.verify_password(new_password, back['verifier'])
        # the beta's seed keeps a verifier whose sha256 is not its own mark (app/accounts.py seed_mark)
        result['beta_seed_keeps_it'] = back['seed_verifier_sha256'] != hashlib.sha256(back['verifier'].encode()).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--username', required=True, help='the account\'s current username')
    parser.add_argument('--reason', required=True)
    parser.add_argument('--new-username', default=None, help='else ACCOUNT_NEW_USERNAME')
    args = parser.parse_args(argv)
    url = os.environ.get('DATABASE_URL')
    if not url:
        print(json.dumps({'outcome': 'refused_no_database_url'}))
        return 2
    new_username = args.new_username or os.environ.get('ACCOUNT_NEW_USERNAME') or None
    new_password = os.environ.get('ACCOUNT_NEW_PASSWORD') or None
    result = apply(url, args.username.strip().lower(), args.reason, new_username, new_password)
    print(json.dumps(result))
    ok = result['outcome'] == 'set' and result.get('password_opens', True) and result.get('beta_seed_keeps_it', True)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
