#!/usr/bin/env python3
"""EXEC-MU-ACCOUNTS Phase 1 (ERRORS M478 re-check N2): the operator unlock of an EDGE account's second factor.

Clears the consecutive-failure counts and the locks of the account's TOTP enrolment (edge_bff.mfa_totp) and of its
password (edge_bff.identities sign_in_failures and sign_in_locked_until, migration 20261119_010: NIST's cap of 100
consecutive failures; ERRORS R1-16, the way back of an admin without an email address, who has no reset) and writes one
edge_bff.admin_audit row in the same transaction (actor 'operator', the reason given). It changes nothing else: the
enrolment, the recovery codes, the password and the sessions stay.

Run it as a job on the private network (scripts/onboarding/run_job.sh, like the migrations), never over a public URL:
    DATABASE_URL=... python3 scripts/edge_mfa_unlock.py --username <username> --reason "<why, who asked>"
It needs DATABASE_URL (a role that may update edge_bff.mfa_totp and add to edge_bff.admin_audit) and prints only the
user id and the counts before and after; never the URL, a secret or an email address. Exit 1 when no such account
exists (an account without an enrolment still has its password's lock lifted, 3c check C3-18).
"""
import argparse
import json
import os
import re
import sys

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

USERNAME = re.compile(r'[a-z0-9_]{3,30}')


def unlock(url, username, reason):
    """{user_id, before, after}, or None when no account has that username. The password's lock is lifted whether or
    not the account has an enrolment: an account without one is locked by its password alone (3c check C3-18); the
    enrolment's counts are cleared when it has one."""
    with psycopg.connect(url, row_factory=dict_row) as c:
        user = c.execute('SELECT user_id FROM edge_bff.users WHERE username = %s FOR UPDATE', (username,)).fetchone()
        if user is None:
            return None
        before, after = {}, {}
        row = c.execute('''SELECT totp_failures, recovery_failures, totp_locked_until, recovery_locked_until
            FROM edge_bff.mfa_totp WHERE user_id = %s FOR UPDATE''', (user['user_id'],)).fetchone()
        if row is not None:
            before.update({k: row[k].isoformat() if hasattr(row[k], 'isoformat') else row[k]
                           for k in ('totp_failures', 'recovery_failures', 'totp_locked_until', 'recovery_locked_until')})
            c.execute('''UPDATE edge_bff.mfa_totp SET totp_failures=0, recovery_failures=0, totp_locked_until=NULL,
                recovery_locked_until=NULL WHERE user_id=%s''', (user['user_id'],))
            after.update({'totp_failures': 0, 'recovery_failures': 0, 'totp_locked_until': None,
                          'recovery_locked_until': None})
        password = c.execute('''SELECT sign_in_failures, sign_in_locked_until FROM edge_bff.identities
            WHERE user_id=%s AND provider='password' FOR UPDATE''', (user['user_id'],)).fetchone()
        if password is not None:
            before.update({'sign_in_failures': password['sign_in_failures'],
                           'sign_in_locked_until': password['sign_in_locked_until'].isoformat()
                           if password['sign_in_locked_until'] else None})
            c.execute('''UPDATE edge_bff.identities SET sign_in_failures=0, sign_in_locked_until=NULL
                WHERE user_id=%s AND provider='password' ''', (user['user_id'],))
            after.update({'sign_in_failures': 0, 'sign_in_locked_until': None})
        c.execute('''INSERT INTO edge_bff.admin_audit(actor_user_id, action, target_user_id, before, after, reason)
            VALUES (NULL, 'mfa.unlock', %s, %s, %s, %s)''',
                  (user['user_id'], Jsonb({'actor': 'operator', **before}), Jsonb({'actor': 'operator', **after}),
                   ('operator: ' + reason)[:1000]))
        return {'user_id': user['user_id'], 'before': before, 'after': after}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--username', required=True)
    parser.add_argument('--reason', required=True)
    args = parser.parse_args(argv)
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        raise SystemExit('DATABASE_URL is required')
    if not USERNAME.fullmatch(args.username) or not args.reason.strip():
        raise SystemExit('--username is a-z 0-9 _ (3 to 30) and --reason is required')
    try:
        done = unlock(url, args.username, args.reason.strip())
    except psycopg.Error:
        # driver errors may include connection details: never print them
        raise SystemExit('EDGE MFA unlock failed; inspect read-only without printing secrets')
    if done is None:
        print(json.dumps({'event': 'edge_mfa_unlock', 'outcome': 'not_found'}))
        return 1
    print(json.dumps({'event': 'edge_mfa_unlock', 'outcome': 'unlocked', **done}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
