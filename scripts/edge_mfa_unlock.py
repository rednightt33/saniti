#!/usr/bin/env python3
"""EXEC-MU-ACCOUNTS Phase 1 (ERRORS M478 re-check N2): the operator unlock of an EDGE account's second factor.

Clears the consecutive-failure counts and the locks of the account's TOTP enrolment (edge_bff.mfa_totp) and writes one
edge_bff.admin_audit row in the same transaction (actor 'operator', the reason given). It changes nothing else: the
enrolment, the recovery codes and the sessions stay.

Run it as a job on the private network (scripts/onboarding/run_job.sh, like the migrations), never over a public URL:
    DATABASE_URL=... python3 scripts/edge_mfa_unlock.py --username <username> --reason "<why, who asked>"
It needs DATABASE_URL (a role that may update edge_bff.mfa_totp and add to edge_bff.admin_audit) and prints only the
user id and the counts before and after; never the URL, a secret or an email address. Exit 1 when no such account or
no enrolment exists.
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
    """{user_id, before, after}, or None when the account or its enrolment does not exist."""
    with psycopg.connect(url, row_factory=dict_row) as c:
        row = c.execute('''SELECT m.user_id, m.totp_failures, m.recovery_failures, m.totp_locked_until,
                m.recovery_locked_until FROM edge_bff.users u JOIN edge_bff.mfa_totp m ON m.user_id = u.user_id
            WHERE u.username = %s FOR UPDATE OF m''', (username,)).fetchone()
        if row is None:
            return None
        before = {k: row[k] for k in ('totp_failures', 'recovery_failures', 'totp_locked_until', 'recovery_locked_until')}
        c.execute('''UPDATE edge_bff.mfa_totp SET totp_failures=0, recovery_failures=0, totp_locked_until=NULL,
            recovery_locked_until=NULL WHERE user_id=%s''', (row['user_id'],))
        after = {'totp_failures': 0, 'recovery_failures': 0, 'totp_locked_until': None, 'recovery_locked_until': None}
        c.execute('''INSERT INTO edge_bff.admin_audit(actor_user_id, action, target_user_id, before, after, reason)
            VALUES (NULL, 'mfa.unlock', %s, %s, %s, %s)''',
                  (row['user_id'], Jsonb({'actor': 'operator', **before}), Jsonb({'actor': 'operator', **after}),
                   ('operator: ' + reason)[:1000]))
        return {'user_id': row['user_id'], 'before': before, 'after': after}


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
