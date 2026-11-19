"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 1, 2 and 4): the account tables of edge-bff
(migration 20261116_003) through the house Store's connections.

This module is the foundation the auth flows (registration, codes, reset, MFA, email; builder B1b) build on:
- `seed`: user #1 at start, idempotent across replicas (advisory lock);
- `resolve`: the session of a request joined to its account and its plan's grants, in one statement (principal.py);
- `owner`: an account by its owner key with its grants (the backtest loop's rights at dispatch; the sign-in's MFA);
- `seed_subscription`: user #1's subscription to the plan that holds every capability (Phase 2), idempotent;
- `find_login`, `sign_in_try`, `create_session`, `signed_in`: the switch-on sign-in (main.py), with at most
  MAX_SESSIONS per user and at most PASSWORD_FAILURE_CAP consecutive failed passwords per account.

Credential writes and the sessions they rest on are serialised by the account's users row (SELECT ... FOR UPDATE,
`lock_account`): `create_session` takes it and checks, in its own transaction, the proof the request rests on (the
verifier the sign-in proved, or the pending session an MFA verify replaces); a password reset or change and
`revoke_all` take it before they write. So a sign-in, change or verify proved before a reset is refused after it, and a
session made before the reset is seen and revoked by it (ERRORS R2-9).

Every statement names the account it reads or changes; the configured owner reaches `seed` as an argument (principal.py).
"""
import hashlib
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
EMAIL_MAX = 254                   # the longest address an account may have: registration, sign-in and reset share it
MAX_SESSIONS = 5                  # CONTRACT.md section 4 "Sessions": at most 5 per user, the oldest is revoked
MAX_PENDING_SESSIONS = 3          # sessions waiting for the admin's second factor, capped apart (C1 note)
PENDING_CHECKED = 3               # pending registrations of an address a sign-in compares its password with
TOUCH_SECONDS = 60                # CONTRACT.md section 2: last_seen_at is written at most once per 60 s per session
ACTIVE = 'active'
EVERYTHING = '*'
# NIST SP 800-63B-4 3.2.2 (ERRORS R1-16): at most 100 consecutive failed passwords per account, over both its logins
# (username and email) and every client address. The 100th starts a lock of PASSWORD_LOCK_SECONDS during which a
# sign-in of the account is answered as a wrong password (OWASP Authentication: the same answer whether the password is
# wrong or the account locked). A success, a password reset proved by the email code (the way back, R1-9) or a change
# clears it; after a lock the count restarts at PASSWORD_RESTART, as the MFA counts do (ERRORS M478 N2)
PASSWORD_FAILURE_CAP, PASSWORD_RESTART, PASSWORD_LOCK_SECONDS = 100, 90, 86400
# market-ai-orc's test-key owners (app/conversations.py TEST_OWNER_RE, M475): a caller holding MARKET_AI_ORC_TEST_KEY
# may name exactly these (tests/test_cp0_reserved_owner.py compares the two patterns, so they cannot drift apart)
ORC_TEST_OWNER = re.compile(r'golden-[A-Za-z0-9._:@-]+|test-[A-Za-z0-9._:@-]+|someone-else')
ORC_SHARED_OWNER = 'default'      # Orc's one shared owner before M475

# EXEC-MU-ACCOUNTS Phase 2 (CONTRACT.md 8a "Resolution"): the CTEs that follow a CTE `found` (one account: user_id,
# owner_key, username, role, status) and resolve its grants within the same statement:
# - live: its active subscription that has started and not ended (expiry decided now, never by a cron);
# - plan: the live subscription's plan and end, else the default plan (no end);
# - lapsed: without a live one, the plan of its most recent subscription that ended: active past its end, or marked
#   expired with or without an end (C1 Phase 2 N3; access.expired_plan);
# - plan_rows: the plan's plan_capabilities; overrides: its overrides that have not ended;
# - merged: an override replaces the plan's value of its key (or adds the key), with the capability's kind.
GRANTS = '''
    live AS (SELECT s.plan_key, s.expires_at FROM edge_bff.subscriptions s JOIN found ON s.user_id = found.user_id
        WHERE s.status = 'active' AND s.starts_at <= now() AND (s.expires_at IS NULL OR s.expires_at > now())
        ORDER BY s.starts_at DESC LIMIT 1),
    plan AS (SELECT coalesce((SELECT plan_key FROM live),
                             (SELECT plan_key FROM edge_bff.plans WHERE is_default)) AS plan_key,
                    (SELECT expires_at FROM live) AS plan_expires_at),
    lapsed AS (SELECT s.plan_key FROM edge_bff.subscriptions s JOIN found ON s.user_id = found.user_id
        WHERE NOT EXISTS (SELECT 1 FROM live)
          AND ((s.status = 'active' AND s.expires_at <= now()) OR s.status = 'expired')
        ORDER BY coalesce(s.expires_at, s.last_event_at, s.created_at) DESC LIMIT 1),
    plan_rows AS (SELECT pc.capability_key, pc.value, pc.version FROM edge_bff.plan_capabilities pc
        JOIN plan ON pc.plan_key = plan.plan_key),
    overrides AS (SELECT o.capability_key, o.value FROM edge_bff.user_capability_overrides o
        JOIN found ON o.user_id = found.user_id WHERE o.expires_at IS NULL OR o.expires_at > now()),
    merged AS (SELECT m.capability_key, m.value, c.kind FROM (
            SELECT capability_key, value FROM overrides
            UNION ALL
            SELECT capability_key, value FROM plan_rows p
            WHERE NOT EXISTS (SELECT 1 FROM overrides o WHERE o.capability_key = p.capability_key)) m
        JOIN edge_bff.capabilities c ON c.capability_key = m.capability_key)'''
# the columns those CTEs give: the resolved plan and its end, the ended plan, the grants {key: {kind, value}}, the
# plan_capabilities versions {key: version}, and the ended plan's own grants (PLAN_EXPIRED is decided by them)
GRANT_COLUMNS = '''plan.plan_key, plan.plan_expires_at, (SELECT plan_key FROM lapsed) AS expired_plan,
        (SELECT coalesce(jsonb_object_agg(capability_key, jsonb_build_object('kind', kind, 'value', value)), '{}'::jsonb)
         FROM merged) AS grants,
        (SELECT coalesce(jsonb_object_agg(capability_key, version), '{}'::jsonb) FROM plan_rows) AS versions,
        (SELECT coalesce(jsonb_object_agg(pc.capability_key, jsonb_build_object('kind', c.kind, 'value', pc.value)),
                         '{}'::jsonb)
         FROM edge_bff.plan_capabilities pc JOIN edge_bff.capabilities c ON c.capability_key = pc.capability_key
         WHERE pc.plan_key = (SELECT plan_key FROM lapsed)) AS expired_grants'''


def new_owner_key():
    """A new account's owner key: 'u_' and 24 hexadecimal digits from secrets (CONTRACT.md section 1), never reserved."""
    return 'u_' + secrets.token_hex(12)


def orc_reserved_owner(key):
    """An owner key Orc reserves: one its test key may name, or its old shared owner. EDGE_OWNER and EDGE_ADMIN_OWNERS
    may not be one (config.py validate; ERRORS R1-3), or user #1's data would sit within the test key's reach."""
    return key == ORC_SHARED_OWNER or ORC_TEST_OWNER.fullmatch(key) is not None


def reserved_owner(key):
    """Keys never issued to a new account (Orc's reserved owners and the seed's own)."""
    return orc_reserved_owner(key) or key == 'edge-private' or key.startswith(('golden-', 'test-'))


def seed_mark(verifier):
    """identities.seed_verifier_sha256 of a verifier the seed writes: its sha256 (hex), never the verifier itself."""
    return hashlib.sha256((verifier or '').encode()).hexdigest()


def seed_identity(login):
    """(username, email or None) of user #1 from EDGE_LOGIN: the login lower-cased when it fits the username rule and
    is not reserved, else SEED_FALLBACK_USERNAME; the login as the email when it is one."""
    lowered = login.strip().lower()
    username = lowered if USERNAME.fullmatch(lowered) and lowered not in RESERVED_USERNAMES else SEED_FALLBACK_USERNAME
    email = lowered if EMAIL.fullmatch(lowered) and len(lowered) <= EMAIL_MAX else None
    return username, email


class AccountStore:
    def __init__(self, store):
        self.store = store

    # ---- user #1 ----------------------------------------------------------------------------------------------------

    def seed(self, owner, login, verifier, multiuser):
        """User #1 = the configured owner (EDGE_OWNER), role admin, its password identity from EDGE_PASSWORD_VERIFIER.
        Made once, when the table holds no user; every replica takes the same advisory lock, so two starting together
        make one row. While the switch is off a changed EDGE_PASSWORD_VERIFIER is copied to the identity (sign-in works
        the same the moment the switch goes on), but only over the seed's own copy: identities.seed_verifier_sha256
        holds the sha256 of the verifier the seed last wrote, so once the account set its own password (a change or a
        reset with the switch on, on the live site) the identity differs from it and is never overwritten again (ERRORS
        R2-2: a switch-off start, such as every beta deploy, would bring back the password the admin replaced). With
        the switch on the identity is the account's own and is never overwritten. The switch-off sign-in itself reads
        EDGE_PASSWORD_VERIFIER, not the identity (main.py). Returns {user_id, username} of user #1, or None when the
        table holds other users and none is the configured owner (logged)."""
        username, email = seed_identity(login)
        mark = seed_mark(verifier)
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
                c.execute('''INSERT INTO edge_bff.identities(user_id, provider, subject, verifier, seed_verifier_sha256)
                    VALUES (%s, 'password', %s, %s, %s)''', (row['user_id'], str(row['user_id']), verifier, mark))
                logger.info(json.dumps({'event': 'account_seeded', 'user_id': row['user_id']}))
            elif not multiuser:
                held = c.execute('''SELECT verifier, seed_verifier_sha256 FROM edge_bff.identities
                    WHERE user_id=%s AND provider='password' FOR UPDATE''', (row['user_id'],)).fetchone()
                if held is not None and held['seed_verifier_sha256'] != seed_mark(held['verifier']):
                    # the account's own password (set with the switch on): kept; the switch-off sign-in still takes
                    # EDGE_PASSWORD_VERIFIER, the switch-on one this identity
                    logger.info(json.dumps({'event': 'account_seed_password_kept', 'user_id': row['user_id']}))
                elif held is not None and (held['verifier'] != verifier or held['seed_verifier_sha256'] != mark):
                    c.execute('''UPDATE edge_bff.identities SET verifier=%s, seed_verifier_sha256=%s, updated_at=now()
                        WHERE user_id=%s AND provider='password' ''', (verifier, mark, row['user_id']))
            return dict(row)

    # ---- the principal's rows ---------------------------------------------------------------------------------------

    def resolve(self, hashed, idle_seconds):
        """The session, its account and the account's resolved grants in one statement (CONTRACT.md sections 2 and 8a):
        an active account, a session neither revoked, expired nor idle beyond idle_seconds; last_seen_at is written in
        the same statement at most once per TOUCH_SECONDS. The grants (GRANTS): the active, unexpired subscription's
        plan, else the default plan; that plan's plan_capabilities; the account's unexpired overrides, each replacing
        the plan's value of its key. None when a session or account check fails (the caller answers 401)."""
        with self.store.connect() as c:
            return c.execute('''WITH found AS (
                    SELECT s.token_hash, s.mfa_passed_at, u.user_id, u.owner_key, u.username, u.role, u.status,
                           (s.last_seen_at IS NULL OR s.last_seen_at < now() - make_interval(secs => %(touch)s)) AS stale
                    FROM edge_bff.sessions s JOIN edge_bff.users u ON u.user_id = s.user_id
                    WHERE s.token_hash = %(hashed)s AND s.revoked_at IS NULL AND s.expires_at > now()
                      AND s.owner_key = u.owner_key AND u.status = %(active)s
                      AND coalesce(s.last_seen_at, s.created_at) > now() - make_interval(secs => %(idle)s)),
                touched AS (UPDATE edge_bff.sessions t SET last_seen_at = now() FROM found
                    WHERE t.token_hash = found.token_hash AND found.stale RETURNING 1),''' + GRANTS + '''
                SELECT found.user_id, owner_key, username, role, status, mfa_passed_at,
                       EXISTS (SELECT 1 FROM edge_bff.mfa_totp m WHERE m.user_id = found.user_id
                               AND m.confirmed_at IS NOT NULL) AS mfa_enrolled, ''' + GRANT_COLUMNS + '''
                FROM found CROSS JOIN plan''',
                             {'hashed': hashed, 'idle': idle_seconds, 'touch': TOUCH_SECONDS, 'active': ACTIVE}).fetchone()

    def owner(self, owner_key):
        """An active account by its owner key with its resolved grants (as resolve), or None: the backtest loop reads
        its owner's rights when it dispatches, the switch-on sign-in decides by them whether MFA is needed."""
        with self.store.connect() as c:
            return c.execute('''WITH found AS (SELECT user_id, owner_key, username, role, status FROM edge_bff.users
                    WHERE owner_key = %(owner)s AND status = %(active)s),''' + GRANTS + '''
                SELECT found.user_id, owner_key, username, role, status, ''' + GRANT_COLUMNS + '''
                FROM found CROSS JOIN plan''', {'owner': owner_key, 'active': ACTIVE}).fetchone()

    # ---- the seed subscription of user #1 (CONTRACT.md 8a "User #1") ------------------------------------------------

    def seed_subscription(self, user_id):
        """User #1 gets an active manual subscription with no end to the plan that holds every capability ('*'). The
        plan is found by data: exactly one plan holds '*' = true; otherwise nothing is given and account_seed_plan_ambiguous is
        logged at warning. Given once (C1/C2/C3 Phase 2): only to the seed row (the one owner key not of the 'u_' form,
        users_one_seed), and only while it has no subscription row at all, whatever its status. From then on the
        subscription is the admin's: a cancelled or ended one is never given back at a restart. Idempotent (every
        replica takes the same advisory lock). Returns the plan key given or held, or None."""
        with self.store.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('accounts:seed_subscription',))
            seed = c.execute('SELECT owner_key FROM edge_bff.users WHERE user_id = %s', (user_id,)).fetchone()
            if seed is None or OWNER_KEY.fullmatch(seed['owner_key']):
                logger.warning(json.dumps({'event': 'account_seed_plan_refused', 'user_id': user_id,
                                           'reason': 'not the seed account'}))
                return None
            # the plan whose '*' is true: a flag may be false since the M480 fix round, so a row alone holds nothing
            # (re-check R1-25)
            plans = [r['plan_key'] for r in c.execute('''SELECT DISTINCT plan_key FROM edge_bff.plan_capabilities
                WHERE capability_key = %s AND value = 'true'::jsonb ORDER BY plan_key''', (EVERYTHING,)).fetchall()]
            if len(plans) != 1:
                logger.warning(json.dumps({'event': 'account_seed_plan_ambiguous', 'plans': len(plans)}))
                return None
            held = c.execute('''SELECT plan_key, status FROM edge_bff.subscriptions WHERE user_id = %s
                ORDER BY (status = 'active') DESC, created_at DESC LIMIT 1''', (user_id,)).fetchone()
            if held is not None:
                return held['plan_key'] if held['status'] == 'active' else None
            c.execute('''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, expires_at, provider, provider_ref)
                VALUES (%s, %s, 'active', NULL, 'manual', 'seed')''', (user_id, plans[0]))
            logger.info(json.dumps({'event': 'account_seed_subscribed', 'user_id': user_id}))
            return plans[0]

    # ---- the switch-on sign-in --------------------------------------------------------------------------------------

    def find_login(self, login):
        """The active account a sign-in names (its username or its email, compared lower-cased) with its password
        verifier, or None (a disabled or pending one is not found here)."""
        lowered = login.strip().lower()
        with self.store.connect() as c:
            return c.execute('''SELECT u.user_id, u.owner_key, u.username, u.role, u.status, u.email, i.verifier
                FROM edge_bff.users u JOIN edge_bff.identities i ON i.user_id = u.user_id AND i.provider = 'password'
                WHERE (u.username = %s OR u.email = %s) AND u.status = %s
                ORDER BY (u.username = %s) DESC LIMIT 1''', (lowered, lowered, ACTIVE, lowered)).fetchone()

    def sign_in_try(self, user_id):
        """One password try of the account, decided and counted in one statement before the password is checked (the
        R2-12 lesson: tries sent together cannot all pass a count each read before the others added theirs). True when
        the try may be checked (it is counted; a success clears the count), False while the account is locked. A lock
        that has ended restarts the count at PASSWORD_RESTART; the try that reaches PASSWORD_FAILURE_CAP starts the
        lock (that try is still checked: it is the 100th)."""
        with self.store.connect() as c:
            return c.execute('''UPDATE edge_bff.identities SET
                    sign_in_failures = (CASE WHEN sign_in_locked_until IS NOT NULL THEN %(restart)s
                                             ELSE sign_in_failures END) + 1,
                    sign_in_locked_until = CASE WHEN (CASE WHEN sign_in_locked_until IS NOT NULL THEN %(restart)s
                                                           ELSE sign_in_failures END) + 1 >= %(cap)s
                                                THEN now() + make_interval(secs => %(lock)s) END
                WHERE user_id = %(user)s AND provider = 'password'
                  AND (sign_in_locked_until IS NULL OR sign_in_locked_until <= now())
                RETURNING sign_in_failures''', {'user': user_id, 'restart': PASSWORD_RESTART,
                                               'cap': PASSWORD_FAILURE_CAP,
                                               'lock': PASSWORD_LOCK_SECONDS}).fetchone() is not None

    def pending_logins(self, login):
        """The newest PENDING_CHECKED pending registrations of an address with their verifiers (a sign-in with the right
        password of one restarts its verification; ERRORS M478 C1 P1-M1)."""
        lowered = login.strip().lower()
        with self.store.connect() as c:
            return c.execute('''SELECT u.user_id, u.owner_key, u.email, u.role, u.status, i.verifier
                FROM edge_bff.users u JOIN edge_bff.identities i ON i.user_id = u.user_id AND i.provider = 'password'
                WHERE u.email = %s AND u.status = 'pending' ORDER BY u.created_at DESC, u.user_id DESC LIMIT %s''',
                             (lowered, PENDING_CHECKED)).fetchall()

    @staticmethod
    def lock_account(c, user_id):
        """The account's users row, locked for the rest of the caller's transaction (the module docstring); None when
        the account is not active."""
        return c.execute('SELECT user_id FROM edge_bff.users WHERE user_id = %s AND status = %s FOR UPDATE',
                         (user_id, ACTIVE)).fetchone()

    def create_session(self, hashed, user, seconds, ip_hash=None, mfa_passed=False, mfa_user=False, proved=None,
                       replaces=None, rehash=None):
        """A session of the account (owner_key kept beside user_id), then the account's oldest live sessions beyond the
        cap revoked, in one transaction under the account's lock (two sign-ins at once cannot both keep one too many).
        For an account that needs MFA (mfa_user), a session that has not passed it is pending: pending sessions have
        their own cap (MAX_PENDING_SESSIONS) and never count towards, or revoke, the MAX_SESSIONS real ones (C1 note).
        The proof the session rests on is checked under the lock (ERRORS R2-9): `proved`, the verifier a sign-in
        proved, must still be the account's (its failure count is then cleared, and `rehash`, the same password at the
        current cost, takes its place: ERRORS R2-29); `replaces`, the pending session an MFA verify upgrades, must still
        be live, and is revoked in the same transaction. Returns the number revoked, or None when the account or the
        proof no longer holds (nothing is made)."""
        pending = mfa_user and not mfa_passed
        with self.store.connect() as c:
            if self.lock_account(c, user['user_id']) is None:
                return None
            if proved is not None and c.execute('''UPDATE edge_bff.identities
                    SET sign_in_failures = 0, sign_in_locked_until = NULL, verifier = coalesce(%(new)s, verifier),
                        updated_at = CASE WHEN %(new)s::text IS NULL THEN updated_at ELSE now() END
                    WHERE user_id = %(user)s AND provider = 'password' AND verifier = %(proved)s
                    RETURNING user_id''', {'new': rehash, 'user': user['user_id'], 'proved': proved}).fetchone() is None:
                return None
            if replaces is not None and c.execute('''UPDATE edge_bff.sessions SET revoked_at = now()
                    WHERE token_hash = %s AND user_id = %s AND revoked_at IS NULL AND expires_at > now()
                    RETURNING token_hash''', (replaces, user['user_id'])).fetchone() is None:
                return None
            c.execute('''INSERT INTO edge_bff.sessions(token_hash, owner_key, user_id, expires_at, last_seen_at,
                    mfa_passed_at, created_ip_hash)
                VALUES (%s, %s, %s, now() + %s * interval '1 second', now(), CASE WHEN %s THEN now() END, %s)''',
                      (hashed, user['owner_key'], user['user_id'], seconds, mfa_passed, ip_hash))
            return c.execute('''UPDATE edge_bff.sessions SET revoked_at = now() WHERE token_hash IN (
                    SELECT token_hash FROM edge_bff.sessions WHERE user_id = %(user)s AND revoked_at IS NULL
                      AND expires_at > now()
                      AND (CASE WHEN %(pending)s THEN mfa_passed_at IS NULL
                                ELSE (mfa_passed_at IS NOT NULL OR NOT %(mfa_user)s) END)
                    ORDER BY created_at DESC, token_hash OFFSET %(cap)s)''',
                             {'user': user['user_id'], 'pending': pending, 'mfa_user': mfa_user,
                              'cap': MAX_PENDING_SESSIONS if pending else MAX_SESSIONS}).rowcount

    def signed_in(self, user_id):
        with self.store.connect() as c:
            c.execute('UPDATE edge_bff.users SET last_sign_in_at = now() WHERE user_id = %s', (user_id,))

    def revoke_all(self, user_id):
        """Every live session of the account (password change or reset, disable, role change; CONTRACT.md section 4),
        under the account's lock: a session being made from an earlier proof is either seen here or refused."""
        with self.store.connect() as c:
            c.execute('SELECT user_id FROM edge_bff.users WHERE user_id = %s FOR UPDATE', (user_id,))
            return c.execute('UPDATE edge_bff.sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL',
                             (user_id,)).rowcount


PENDING_HOURS = 24


def purge_pending(connection, limit=None):
    """Registrations never verified, 24 h after they were made (CONTRACT.md section 4); their identity and codes go with
    them (ON DELETE CASCADE). At most limit of them (None: every one); the accounts deleted. Called from Store.purge, the
    hourly housekeeping (worker.Housekeeping)."""
    return connection.execute('''DELETE FROM edge_bff.users WHERE user_id IN (SELECT user_id FROM edge_bff.users
        WHERE status = 'pending' AND email_verified_at IS NULL AND created_at < now() - make_interval(hours => %s)
        LIMIT %s)''', (PENDING_HOURS, limit)).rowcount


# EXEC-MU-ACCOUNTS "Decisions from the fix round" item 2 (user 2026-11-19: "a"): email codes, outbox rows and webhook
# deliveries are kept 30 days (the outbox and the deliveries by migration 20261119_012's functions, which hold the same
# number; tests/test_decisions_small.py ages a row of each to either side of it)
EMAIL_RETENTION_DAYS = 30


def purge_codes(connection, limit=None):
    """Email codes that can no longer be used, EMAIL_RETENTION_DAYS after they ended: used (consumed_at) or, never
    used, expired (expires_at, 300 s after they were made). A live code is never deleted, so the one-live-code rule
    (email_codes_one_live) and the 5 tries are unchanged. At most limit of them (None: every one); the codes deleted.
    Called from Store.purge, the hourly housekeeping (worker.Housekeeping; store.PURGES 'codes')."""
    return connection.execute('''DELETE FROM edge_bff.email_codes WHERE code_id IN (SELECT code_id FROM edge_bff.email_codes
        WHERE coalesce(consumed_at, expires_at) < now() - make_interval(days => %s) ORDER BY code_id LIMIT %s)''',
                              (EMAIL_RETENTION_DAYS, limit)).rowcount
