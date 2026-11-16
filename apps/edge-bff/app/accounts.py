"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 1, 2 and 4): the account tables of edge-bff
(migration 20261116_003) through the house Store's connections.

This module is the foundation the auth flows (registration, codes, reset, MFA, email; builder B1b) build on:
- `seed`: user #1 at start, idempotent across replicas (advisory lock);
- `resolve`: the session of a request joined to its account, in one statement (principal.py);
- `owner`: an account by its owner key (the backtest loop's rights at dispatch);
- `find_login`, `create_session`, `signed_in`: the switch-on sign-in (main.py), with at most MAX_SESSIONS per user.

Every statement names the account it reads or changes; the configured owner reaches `seed` as an argument (principal.py).
"""
import json
import logging
import re
import secrets

logger = logging.getLogger('edge_bff.accounts')

OWNER_KEY = re.compile(r'u_[0-9a-f]{24}')
USERNAME = re.compile(r'[a-z0-9_]{3,30}')
RESERVED_USERNAMES = frozenset({'admin', 'root', 'support', 'edge', 'system'})
# The username of user #1 when EDGE_LOGIN does not fit the username rule (or is reserved): 'admin-1' of the task brief
# does not fit ^[a-z0-9_]{3,30}$ (a hyphen), so the seed takes 'admin_1'
SEED_FALLBACK_USERNAME = 'admin_1'
EMAIL = re.compile(r'[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{1,63}')
MAX_SESSIONS = 5                  # CONTRACT.md section 4 "Sessions": at most 5 per user, the oldest is revoked
TOUCH_SECONDS = 60                # CONTRACT.md section 2: last_seen_at is written at most once per 60 s per session
ACTIVE = 'active'


def new_owner_key():
    """A new account's owner key: 'u_' and 24 hexadecimal digits from secrets (CONTRACT.md section 1), never reserved."""
    return 'u_' + secrets.token_hex(12)


def reserved_owner(key):
    """Keys never issued to a new account (Orc's test owners, the shared 'default' and the seed's own)."""
    return key in ('default', 'someone-else', 'edge-private') or key.startswith(('golden-', 'test-'))


def seed_identity(login):
    """(username, email or None) of user #1 from EDGE_LOGIN: the login lower-cased when it fits the username rule and
    is not reserved, else SEED_FALLBACK_USERNAME; the login as the email when it is one."""
    lowered = login.strip().lower()
    username = lowered if USERNAME.fullmatch(lowered) and lowered not in RESERVED_USERNAMES else SEED_FALLBACK_USERNAME
    email = lowered if EMAIL.fullmatch(lowered) and len(lowered) <= 254 else None
    return username, email


class AccountStore:
    def __init__(self, store):
        self.store = store

    # ---- user #1 ----------------------------------------------------------------------------------------------------

    def seed(self, owner, login, verifier, multiuser):
        """User #1 = the configured owner (EDGE_OWNER), role admin, its password identity from EDGE_PASSWORD_VERIFIER.
        Made once, when the table holds no user; every replica takes the same advisory lock, so two starting together
        make one row. While the switch is off the environment is the source of the password, so a changed
        EDGE_PASSWORD_VERIFIER is copied to the identity (sign-in works the same the moment the switch goes on); with
        the switch on the identity is the account's own and is never overwritten. Returns {user_id, username} of user
        #1, or None when the table holds other users and none is the configured owner (logged)."""
        username, email = seed_identity(login)
        with self.store.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('accounts:seed',))
            row = c.execute('SELECT user_id, username FROM edge_bff.users WHERE owner_key=%s', (owner,)).fetchone()
            if row is None:
                if c.execute('SELECT 1 FROM edge_bff.users LIMIT 1').fetchone():
                    logger.warning(json.dumps({'event': 'account_seed_skipped', 'reason': 'users_not_empty'}))
                    return None
                row = c.execute('''INSERT INTO edge_bff.users(owner_key, username, email, email_verified_at, role, status)
                    VALUES (%s, %s, %s, CASE WHEN %s::text IS NULL THEN NULL ELSE now() END, 'admin', 'active')
                    RETURNING user_id, username''', (owner, username, email, email)).fetchone()
                c.execute('''INSERT INTO edge_bff.identities(user_id, provider, subject, verifier)
                    VALUES (%s, 'password', %s, %s)''', (row['user_id'], str(row['user_id']), verifier))
                logger.info(json.dumps({'event': 'account_seeded', 'user_id': row['user_id']}))
            elif not multiuser:
                c.execute('''UPDATE edge_bff.identities SET verifier=%s, updated_at=now()
                    WHERE user_id=%s AND provider='password' AND verifier IS DISTINCT FROM %s''',
                          (verifier, row['user_id'], verifier))
            return dict(row)

    # ---- the principal's rows ---------------------------------------------------------------------------------------

    def resolve(self, hashed, idle_seconds):
        """The session and its account in one statement (CONTRACT.md section 2): an active account, a session neither
        revoked, expired nor idle beyond idle_seconds; last_seen_at is written in the same statement at most once per
        TOUCH_SECONDS. None when any of these fails (the caller answers 401)."""
        with self.store.connect() as c:
            return c.execute('''WITH found AS (
                    SELECT s.token_hash, s.mfa_passed_at, u.user_id, u.owner_key, u.username, u.role, u.status,
                           (s.last_seen_at IS NULL OR s.last_seen_at < now() - make_interval(secs => %(touch)s)) AS stale
                    FROM edge_bff.sessions s JOIN edge_bff.users u ON u.user_id = s.user_id
                    WHERE s.token_hash = %(hashed)s AND s.revoked_at IS NULL AND s.expires_at > now()
                      AND s.owner_key = u.owner_key AND u.status = %(active)s
                      AND coalesce(s.last_seen_at, s.created_at) > now() - make_interval(secs => %(idle)s)),
                touched AS (UPDATE edge_bff.sessions t SET last_seen_at = now() FROM found
                    WHERE t.token_hash = found.token_hash AND found.stale RETURNING 1)
                SELECT user_id, owner_key, username, role, status, mfa_passed_at,
                       EXISTS (SELECT 1 FROM edge_bff.mfa_totp m WHERE m.user_id = found.user_id
                               AND m.confirmed_at IS NOT NULL) AS mfa_enrolled FROM found''',
                             {'hashed': hashed, 'idle': idle_seconds, 'touch': TOUCH_SECONDS, 'active': ACTIVE}).fetchone()

    def owner(self, owner_key):
        """An active account by its owner key (the backtest loop reads its owner's rights when it dispatches), or None."""
        with self.store.connect() as c:
            return c.execute('''SELECT user_id, owner_key, username, role, status FROM edge_bff.users
                WHERE owner_key=%s AND status=%s''', (owner_key, ACTIVE)).fetchone()

    # ---- the switch-on sign-in --------------------------------------------------------------------------------------

    def find_login(self, login):
        """The active or pending account a sign-in names (its username or its email, compared lower-cased) with its
        password verifier, or None (a disabled account is not found). The caller answers EMAIL_NOT_VERIFIED for a
        pending one only after its password was right."""
        lowered = login.strip().lower()
        with self.store.connect() as c:
            return c.execute('''SELECT u.user_id, u.owner_key, u.username, u.role, u.status, i.verifier
                FROM edge_bff.users u JOIN edge_bff.identities i ON i.user_id = u.user_id AND i.provider = 'password'
                WHERE (u.username = %s OR u.email = %s) AND u.status IN (%s, 'pending')
                ORDER BY (u.username = %s) DESC LIMIT 1''', (lowered, lowered, ACTIVE, lowered)).fetchone()

    def create_session(self, hashed, user, seconds, ip_hash=None, mfa_passed=False):
        """A session of the account (owner_key kept beside user_id), then the account's oldest live sessions beyond
        MAX_SESSIONS revoked, in one transaction under the account's lock (two sign-ins at once cannot both keep a
        sixth). Returns the number revoked."""
        with self.store.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('sessions:' + str(user['user_id']),))
            c.execute('''INSERT INTO edge_bff.sessions(token_hash, owner_key, user_id, expires_at, last_seen_at,
                    mfa_passed_at, created_ip_hash)
                VALUES (%s, %s, %s, now() + %s * interval '1 second', now(), CASE WHEN %s THEN now() END, %s)''',
                      (hashed, user['owner_key'], user['user_id'], seconds, mfa_passed, ip_hash))
            return c.execute('''UPDATE edge_bff.sessions SET revoked_at = now() WHERE token_hash IN (
                    SELECT token_hash FROM edge_bff.sessions WHERE user_id = %s AND revoked_at IS NULL AND expires_at > now()
                    ORDER BY created_at DESC, token_hash OFFSET %s)''', (user['user_id'], MAX_SESSIONS)).rowcount

    def signed_in(self, user_id):
        with self.store.connect() as c:
            c.execute('UPDATE edge_bff.users SET last_sign_in_at = now() WHERE user_id = %s', (user_id,))

    def revoke_all(self, user_id):
        """Every live session of the account (password change or reset, disable, role change; CONTRACT.md section 4)."""
        with self.store.connect() as c:
            return c.execute('UPDATE edge_bff.sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL',
                             (user_id,)).rowcount


PENDING_HOURS = 24


def purge_pending(connection):
    """Registrations never verified, 24 h after they were made (CONTRACT.md section 4); their identity and codes go with
    them (ON DELETE CASCADE). Called from Store.cleanup_sessions, the worker loop's hourly cleanup."""
    connection.execute('''DELETE FROM edge_bff.users WHERE status = 'pending' AND email_verified_at IS NULL
        AND created_at < now() - make_interval(hours => %s)''', (PENDING_HOURS,))
