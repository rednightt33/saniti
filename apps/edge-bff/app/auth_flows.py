"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 4, 5 and 6): registration, email codes, password
reset and change, sign-out everywhere, admin MFA and the Resend webhook.

With EDGE_MULTIUSER off every route here answers 404 NOT_FOUND (before any session check), except the public
GET /api/v1/auth/config, which answers {"multiuser": false}; nothing else changes.

Rules (OWASP Authentication and Forgot Password cheat sheets, NIST SP 800-63B-4):
- No enumeration: register, code/resend and password/forgot answer the same 202 for any valid input, whether or not the
  email or username belongs to an account, and run the same password hashing. An existing address gets the "account
  exists" email instead of a code. A taken username is answered (409 USERNAME_TAKEN) only after the email code is proved.
- Codes: 6 digits from secrets, stored as HMAC-SHA256 with EDGE_CODE_SECRET, valid 300 s, 5 tries each, at most 20
  failed tries per user per day (a new code does not reset the count), compared in constant time; one live code per
  user and purpose. A wrong, expired or used code answers the same 400 CODE_INVALID_OR_EXPIRED.
  The failed reset codes are also counted per address, whether or not it has an account (ERRORS R1-8), so the 429 after
  20 tells nothing about the address; a USERNAME_TAKEN answer uses one of the code's 5 tries (R1-12).
- Sending: at most one code email per address per 60 s (a notification email never holds a code back: R2-10) and 10
  emails per day (SEND_EMAIL); one pending registration is mailed at most 3 times a day (its code, resends and sign-in
  restarts: REGISTRATION_MAIL, R1-13); inside those limits nothing is sent and nothing changes, with the same 202.
  Sends per client address are recorded (SEND_IP), not enforced.
- A reset revokes every session and signs nobody in (200 {"next": "sign_in"}); it also lifts the account's sign-in
  limits (the consecutive-failure cap, and the per-login count of the resetting client: R1-9, R1-16). A change revokes
  the other sessions. Both send a notification email. Each writes under the account's lock and only while what it
  rests on still holds (the session, the verifier proved: R2-9; accounts.py).
- Admin MFA: a confirmed enrolment is replaced only by a session that passed MFA, and only once a code of the new
  authenticator proves it: until then the new one waits beside it (pending_nonce, pending recovery codes) and the
  confirmed factor keeps working (R1-7). A code confirms only the enrolment it was checked against (R2-11), and the
  consecutive-failure cap is decided and counted under the enrolment's row lock (R2-12).
- Password work (derivations, Pwned Passwords) runs on passwords.PasswordWork, never on the default executor (R2-37).
"""
import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timezone
from typing import NamedTuple

from fastapi import Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors

from . import email_texts, hooks, mfa, passwords, releases
from .accounts import ACCOUNT_SESSIONS, EMAIL, EMAIL_MAX, RESERVED_USERNAMES, USERNAME, AccountStore, new_owner_key
from .errors import Refusal
from .mailer import OutboxStore, enqueue
from .config import LIVE
from .principal import BETA_ONLY_TABS, Principal
from .security import (DEVICE_COOKIE, DEVICE_SECONDS, REGISTRATION_COOKIE as REGISTRATION, RESET_COOKIE,
                       SESSION_COOKIE, cookie_name, device_of, device_token, normal_password, password_verifier,
                       registration_path, token_hash, verify_password)
from .text_rules import person_name
from .throttle import (CODE_ADDRESS, CODE_USER, DEVICE_MAIL, DEVICE_SIGNIN, MFA_USER, PASSWORD_CHANGE, REGISTER_DAY,
                       REGISTER_HOUR, REGISTRATION_MAIL, SEND_EMAIL, SEND_EMAIL_CLIENT, SEND_IP, SIGNIN_IP, SIGNIN_LOGIN,
                       Throttle, client_address, normal_login)

COOKIE = SESSION_COOKIE                     # by its name on the origin: cookie_name (re-check R2-22)
CODE_SECONDS = 300
RESEND_SECONDS = 60
CODE = re.compile(r'[0-9]{6}')
PURPOSES = ('register', 'reset')
# the purposes of edge_bff.email_codes (its CHECK): an outbox row of one of these carries a code (_issue_code sends it
# under the code's purpose); the 60-second gap between code emails of an address reads only these rows (ERRORS R2-10)
CODE_PURPOSES = ('register', 'reset', 'email_change')
ACCEPTED = {'status': 'CODE_SENT', 'resend_after_s': RESEND_SECONDS}
# ERRORS M478 (C1 P1-H1, C2 #1): every registration is bound to the browser that started it by this HttpOnly cookie; the
# email code activates a registration only together with it
REGISTRATION_COOKIE = REGISTRATION         # by its name and path on the origin: cookie_name, registration_path
REGISTRATION_SECONDS = 86400
REGISTRATION_TOKEN = re.compile(r'[0-9a-f]{64}')
# The A2 fix (ERRORS M513 A2, M517): a password reset's codes are bound to the browser that asked for them by this
# HttpOnly cookie (every "Forgot password?" and reset resend answer sets it, kept when the browser holds a valid one),
# as a registration's are by REGISTRATION_COOKIE: another browser's wrong codes, or its own request for a code, never
# use up or replace them
RESET_SECONDS = 3600
TOTP_FAILURE_CAP, RECOVERY_FAILURE_CAP = 100, 10
TOTP_RESTART, RECOVERY_RESTART = 90, 8          # the count after a lock ends: 10 (2) more tries before the next lock
LOCK_SECONDS = 86400
# the two ways past MFA in edge_bff.mfa_totp: each one's failure count, lock end, cap and restart count (FlowStore.mfa_try)
MFA_WAYS = {'totp': ('totp_failures', 'totp_locked_until', TOTP_FAILURE_CAP, TOTP_RESTART),
            'recovery': ('recovery_failures', 'recovery_locked_until', RECOVERY_FAILURE_CAP, RECOVERY_RESTART)}


def mfa_way_locked(row, kind, now):
    """True while the way `kind` ('totp' or 'recovery') of an enrolment row is locked: its count at the cap and its
    lock not yet ended (a lock that has ended restarts the count at the next try). FlowStore.mfa_try decides a lock with
    it, and MFA_LOCKED names the other way as open (details.use) only when it says False for that way (ERRORS M519)."""
    count, until, cap, _restart = MFA_WAYS[kind]
    return row[count] >= cap and row[until] is not None and now < row[until]
# EXEC-MU-ACCOUNTS "Decisions after the fix round" (the main agent's design value, told to the user 2026-11-19): starting
# a new authenticator beside a confirmed one needs the second factor passed within this many seconds (the session's
# mfa_passed_at); an older pass verifies again first (POST /api/v1/auth/mfa/verify makes a session passed now)
MFA_RECENT_SECONDS = 600


class CheckedStep(NamedTuple):
    """A TOTP step a code matched, with the enrolment (its nonce) it was checked against: use_step confirms that
    enrolment only (ERRORS R2-11), never whatever the account holds by then."""
    nonce: bytes
    step: int


def invalid(reasons):
    """400 INVALID_INPUT naming each field and how to fix it (never its value)."""
    return Refusal(400, 'INVALID_INPUT', {'fields': list(reasons), 'reasons': reasons})


def fields_of(raw, allowed, required):
    """The body's string fields: a JSON object with only `allowed` keys, every `required` one present, all strings (or
    null for an optional one); 400 INVALID_INPUT otherwise."""
    try:
        body = json.loads(raw or b'null')
    except (ValueError, RecursionError):
        raise invalid({'body': 'Send a JSON object.'}) from None
    if not isinstance(body, dict):
        raise invalid({'body': 'Send a JSON object.'})
    unknown = sorted(set(body) - set(allowed))
    if unknown:
        raise invalid({k: 'This field is not accepted here; remove it.' for k in unknown})
    missing = [k for k in required if not isinstance(body.get(k), str) or not body[k].strip()]
    wrong = [k for k in body if body[k] is not None and not isinstance(body[k], str)]
    if missing or wrong:
        raise invalid({k: 'This field is required as text.' for k in missing + wrong})
    for k, v in body.items():
        if isinstance(v, str) and ('\x00' in v or any('\ud800' <= ch <= '\udfff' for ch in v) or len(v) > 1024):
            raise invalid({k: 'This field holds a character that cannot be stored, or is too long.'})
    return body


def checked_username(value, field='username'):
    name = (value or '').strip().lower()
    if not USERNAME.fullmatch(name):
        raise invalid({field: 'A username is 3 to 30 characters: a-z, 0-9 or _, e.g. budi_santoso.'})
    if name in RESERVED_USERNAMES:
        raise invalid({field: 'This username is reserved. Choose another one.'})
    return name


def checked_email(value, field='email'):
    email = (value or '').strip().lower()
    if not EMAIL.fullmatch(email) or len(email) > EMAIL_MAX:
        raise invalid({field: 'Enter an email address like name@example.com.'})
    return email


def checked_name(value, field):
    """A first or last name by the one rule for a person's name (app/text_rules.py, re-check R2-18): NFC, one space
    between words, 1 to 100 characters, no control, hidden format or markup character."""
    name, problem = person_name(value)
    if problem:
        raise invalid({field: problem})
    return name


def checked_passwords(body):
    reason = passwords.length_problem(body.get('password'))
    if reason:
        raise invalid({'password': reason})
    if not isinstance(body.get('password_repeat'), str) or \
            normal_password(body['password_repeat']) != normal_password(body['password']):
        raise invalid({'password_repeat': 'The two passwords differ. Type the same password twice.'})
    return body['password']


class FlowStore:
    """The flows' SQL, every statement naming the account; locks per email so two requests for one address are serial."""

    def __init__(self, settings, store, throttle):
        self.settings, self.store, self.throttle = settings, store, throttle

    def code_hash(self, user_id, purpose, code):
        return hmac.new(self.settings.code_secret.encode(), b'edge_bff.email_codes\x00' + purpose.encode() + b'\x00'
                        + str(user_id).encode() + b'\x00' + code.encode(), hashlib.sha256).hexdigest()

    def _h(self, limit, key):
        return self.throttle.key_hash(limit, key)

    @staticmethod
    def _lock(c, email):
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('register:' + email,))

    def _may_send(self, c, email, ip, binding=None, device=None):
        """Count the send try of the client address (recorded only); True when the address may get a code email now.
        The budget (the A2 fix, ERRORS M517): a browser where the account's password was proved (`device`, its nonce:
        security.device_of) asks under its own DEVICE_MAIL; any other request under the address's SEND_EMAIL and the
        address's SEND_EMAIL_CLIENT from this client, so one stranger cannot spend the address's day and no number of
        them can spend the owner's own browser's. The gap: no code email in the last RESEND_SECONDS to the address, or,
        for a reset bound to a browser (`binding`), to that browser (its code emails, found through their outbox key
        code:<code_id>), so a stranger's request never holds the owner's back. A notification
        (password_changed, account_exists) is not a code and never holds the next code back (ERRORS R2-10: it held back
        the very reset it tells the owner to ask for)."""
        Throttle._add(c, SEND_IP, self._h(SEND_IP, ip))
        if device is not None:
            if Throttle._wait(c, DEVICE_MAIL, self._h(DEVICE_MAIL, (email, device))):
                return False
        elif Throttle._wait(c, SEND_EMAIL, self._h(SEND_EMAIL, email)) or \
                Throttle._wait(c, SEND_EMAIL_CLIENT, self._h(SEND_EMAIL_CLIENT, (email, ip))):
            return False
        if binding is not None:
            # the outbox rows of the address in the gap (its to_email index), each joined to its code by the code's
            # own key (code:<code_id>, the primary key of email_codes; A2 checker ATK-4: a join on the text of the key
            # scanned every code kept)
            return c.execute('''SELECT 1 FROM edge_bff.email_outbox o JOIN edge_bff.email_codes k
                    ON k.code_id = CASE WHEN o.idempotency_key ~ '^code:[0-9]{1,18}$'
                                        THEN substr(o.idempotency_key, 6)::bigint END
                WHERE o.to_email = %s AND o.purpose = 'reset' AND k.binding_hash = %s
                  AND o.created_at > now() - make_interval(secs => %s) LIMIT 1''',
                             (email, binding, RESEND_SECONDS)).fetchone() is None
        return c.execute('''SELECT 1 FROM edge_bff.email_outbox WHERE to_email=%s AND purpose = ANY(%s)
            AND created_at > now() - make_interval(secs => %s) LIMIT 1''',
                         (email, list(CODE_PURPOSES), RESEND_SECONDS)).fetchone() is None

    def _send(self, c, purpose, email, mail, expires_at=None, key=None, ip=None, device=None):
        """Queue one email and count it in the budget _may_send read: the device's own, or the address's and the
        address's from this client."""
        if device is not None:
            Throttle._add(c, DEVICE_MAIL, self._h(DEVICE_MAIL, (email, device)))
        else:
            Throttle._add(c, SEND_EMAIL, self._h(SEND_EMAIL, email))
            Throttle._add(c, SEND_EMAIL_CLIENT, self._h(SEND_EMAIL_CLIENT, (email, ip or 'unknown')))
        return enqueue(c, purpose, email, mail, expires_at, key)

    def device_valid(self, c, user_id, token):
        """The nonce of this browser's device token when it is one of the account `user_id`, signed over the account's
        current verifier (security.device_of); else None. Nothing is counted: a reset request asks under DEVICE_MAIL with
        it, which bounds that browser's mails on its own, so the owner's own wrong passwords (DEVICE_SIGNIN) never take
        its reset mail away (A2 checker ATK-2: a person who forgot the password mistypes it first)."""
        if user_id is None or not token:
            return None
        row = c.execute('''SELECT verifier FROM edge_bff.identities WHERE user_id=%s AND provider='password' ''',
                        (user_id,)).fetchone()
        return device_of(self.settings.session_secret, token, user_id, row['verifier'] if row else None)

    def device_try(self, user_id, token):
        """A password try of this browser under its own failure limit, decided and counted in one step before the
        password is checked (Throttle.attempt on DEVICE_SIGNIN; A2 checker ATK-3: a burst read the count before any
        try added to it, the R2-12 lesson): the device's nonce when its token is valid (device_valid) and the try is
        within DEVICE_SIGNIN (then the try is counted; a success clears it); None otherwise, and the try goes the way
        of any browser's (the per-login limit and the account's lock). The sign-in and the password change."""
        if user_id is None or not token:
            return None
        with self.store.connect() as c:
            nonce = self.device_valid(c, user_id, token)
        if nonce is None or self.throttle.attempt(DEVICE_SIGNIN, (str(user_id), nonce)):
            return None
        return nonce

    def _issue_code(self, c, user_id, purpose, email, ip=None, device=None, binding=None):
        """A new code (the live one of the same browser binding consumed first) and its email, in the caller's
        transaction; False (nothing changes) when the code is a pending registration's and that registration was mailed
        REGISTRATION_MAIL times today. `binding` (a reset's: the SHA-256 of the browser's reset cookie) binds the code to
        that browser: another browser's live code stays live (the A2 fix), one per account, purpose and binding
        (email_codes_one_live_per_browser)."""
        if purpose == 'register':
            mailed = self._h(REGISTRATION_MAIL, str(user_id))
            if Throttle._wait(c, REGISTRATION_MAIL, mailed):
                return False
            Throttle._add(c, REGISTRATION_MAIL, mailed)
        c.execute('''UPDATE edge_bff.email_codes SET consumed_at=now()
            WHERE user_id=%s AND purpose=%s AND consumed_at IS NULL AND binding_hash IS NOT DISTINCT FROM %s''',
                  (user_id, purpose, binding))
        code = f'{secrets.randbelow(10 ** 6):06d}'
        row = c.execute('''INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, expires_at, binding_hash)
            VALUES (%s,%s,%s, now() + make_interval(secs => %s), %s) RETURNING code_id, expires_at''',
                        (purpose, user_id, self.code_hash(user_id, purpose, code), CODE_SECONDS, binding)).fetchone()
        self._send(c, purpose, email, email_texts.code_email(purpose, code), row['expires_at'], f'code:{row["code_id"]}',
                   ip, device)
        return True

    def _check_code(self, c, user, purpose, code, email=None, client=None, binding=None):
        """('ok', code row) | ('invalid', None) | ('limited', seconds). A wrong try raises the code's attempts (the code
        is dead at 5) and the user's daily count; the daily cap is read first, so a new code never resets it. With
        `email` (a reset, typed by anyone) the address's own daily count is read and raised too, whether or not the
        address has an account, so the cap answers alike for every address (ERRORS R1-8). A reset's two daily counts are
        keyed by the client address too (`client`, throttle.client_address; the user's "2a" 2026-11-20, 3c check C3-17):
        a stranger's wrong codes from one address never block the owner's code from another, so the 100-failure sign-in
        lock keeps its way back. Since the A2 fix a browser that asked for its code is the key instead of its client
        address (`binding`), so a stranger on the owner's own network does not block it either (A2 checker ATK-1); a
        browser without a reset cookie stays keyed by its client address. Either way every wrong try is counted, an
        account's or not, so the 429 still tells nothing about the address. A reset's code is the one of this browser (`binding`, the SHA-256 of its reset cookie;
        the A2 fix): a browser without one of its own reaches only a code made before the binding (binding_hash NULL),
        so a stranger's wrong codes never use up the owner's tries. Guessing stays bounded by the 5 tries of each code
        and the address's 10 emails a day (at most 50 guesses a day against 10^6; an owner's own browser asks under its
        own budget, DEVICE_MAIL, and holds the account's password). The caller holds the address's lock (_lock), so the
        read and the count of one address are serial."""
        # the A2 checker ATK-1: a reset from a browser that asked for its code (`binding`) counts under that browser,
        # not its client address, so a stranger on the owner's network fills only its own browser's counts
        who = f'browser:{binding}' if binding else (client or 'unknown')
        by_address = self._h(CODE_ADDRESS, (email, who)) if email else None
        by_user = None if user is None else self._h(
            CODE_USER, (str(user['user_id']), who) if email else str(user['user_id']))
        wait = (Throttle._wait(c, CODE_ADDRESS, by_address) if by_address else 0) or (
            Throttle._wait(c, CODE_USER, by_user) if by_user else 0)
        if wait:
            return 'limited', wait
        row = None
        if user is None:
            hmac.compare_digest(self.code_hash(0, purpose, code), self.code_hash(0, purpose, '000000'))
        else:
            row = c.execute('''SELECT code_id, code_hash, attempts FROM edge_bff.email_codes WHERE user_id=%s
                AND purpose=%s AND consumed_at IS NULL AND expires_at > now() AND attempts < 5
                AND (binding_hash = %s OR binding_hash IS NULL)
                ORDER BY binding_hash IS NULL, code_id DESC LIMIT 1 FOR UPDATE''',
                            (user['user_id'], purpose, binding)).fetchone()
            given = self.code_hash(user['user_id'], purpose, code if CODE.fullmatch(code or '') else 'x')
            if row and hmac.compare_digest(row['code_hash'], given):
                return 'ok', row
            if row:
                c.execute('''UPDATE edge_bff.email_codes SET attempts=attempts+1,
                    consumed_at=CASE WHEN attempts+1 >= 5 THEN now() END WHERE code_id=%s''', (row['code_id'],))
            Throttle._add(c, CODE_USER, by_user)
        if by_address:
            Throttle._add(c, CODE_ADDRESS, by_address)
        return 'invalid', None

    # ---- registration -----------------------------------------------------------------------------------------------

    def register(self, f, verifier, ip, registration, held=None):
        """(queued, keep_held). queued: an email was queued. An address without an account gets a new pending
        registration of its own (bound to the browser by `registration`, the SHA-256 of its new registration cookie; an
        earlier pending registration of the address is never changed) and a code; an address with an account gets the
        "account exists" email. keep_held (ERRORS R1-11, the N3 class): nothing was made and `held`, the hash of the
        cookie this browser already holds, names a pending registration of this same address, so the browser keeps
        that cookie and the code already mailed still finishes it (only its holder learns that its row exists)."""
        with self.store.connect() as c:
            self._lock(c, f['email'])
            made = self._register(c, f, verifier, ip, registration)
            if made is not None:
                return made, False
            return False, held is not None and self._registration(c, f['email'], held) is not None

    def _register(self, c, f, verifier, ip, registration):
        """True or False (queued) when a row or an email was made, None when nothing changed (the limits)."""
        if not self._may_send(c, f['email'], ip):
            return None
        # ERRORS M478 re-check (N4): a new registration mails an address at most once per hour and three times per day
        # from one client address (the A2 fix: the key was the address alone, so one stranger held its owner back); a
        # later one in the hour answers the same 202 and changes nothing (the earlier code is not re-sent). The
        # address's own ceiling is SEND_EMAIL with SEND_EMAIL_CLIENT: strangers on three or more clients can still
        # spend its day (the residual of ERRORS M517)
        key = self._h(REGISTER_HOUR, (f['email'], ip or 'unknown'))
        if Throttle._wait(c, REGISTER_HOUR, key) or Throttle._wait(c, REGISTER_DAY, key):
            return None
        Throttle._add(c, REGISTER_HOUR, key)
        if c.execute("SELECT 1 FROM edge_bff.users WHERE email=%s AND status<>'pending'", (f['email'],)).fetchone():
            return bool(self._send(c, 'account_exists', f['email'], email_texts.account_exists_email(), ip=ip))
        # the A2 checker CW-2: the client address a registration came from (its keyed hash), so a sign-in compares the
        # newest registration of each client (accounts.pending_logins) and one stranger's registrations cannot push the
        # owner's out of the ones it compares; no earlier registration is changed or removed (ERRORS M478, R1-11)
        client = self._h(SIGNIN_IP, ip or 'unknown')
        user_id = c.execute('''INSERT INTO edge_bff.users(owner_key, username, requested_username, email,
                first_name, last_name, phone_e164, role, status, registration_hash, registration_client_hash)
            VALUES (%s, NULL, %s, %s, %s, %s, %s, 'user', 'pending', %s, %s) RETURNING user_id''',
                            (new_owner_key(), f['username'], f['email'], f['first_name'], f['last_name'],
                             f['phone'], registration, client)).fetchone()['user_id']
        c.execute("""INSERT INTO edge_bff.identities(user_id, provider, subject, verifier)
            VALUES (%s, 'password', %s, %s)""", (user_id, str(user_id), verifier))
        return self._issue_code(c, user_id, 'register', f['email'], ip)

    @staticmethod
    def _registration(c, email, registration):
        """The pending registration of this address that this browser's cookie names, or None."""
        if not registration:
            return None
        return c.execute('''SELECT user_id, owner_key, requested_username, email FROM edge_bff.users
            WHERE email=%s AND status='pending' AND registration_hash=%s FOR UPDATE''', (email, registration)).fetchone()

    def verify_registration(self, email, code, registration, username=None):
        """('ok', user) with this browser's registration active (its own password, username, names and phone), its code
        consumed and every other pending registration of the address deleted | ('taken', None) (the code stays live, one
        of its 5 tries used: ERRORS R1-12, so one code cannot look up any number of usernames) | ('invalid', None) |
        ('limited', seconds). Without the registration's cookie a code proves nothing."""
        with self.store.connect() as c:
            self._lock(c, email)
            user = self._registration(c, email, registration)
            outcome, found = self._check_code(c, user, 'register', code)
            if outcome != 'ok':
                return outcome, found

            def taken():
                c.execute('''UPDATE edge_bff.email_codes SET attempts=attempts+1,
                    consumed_at=CASE WHEN attempts+1 >= 5 THEN now() END WHERE code_id=%s''', (found['code_id'],))
                return 'taken', None
            name = username or user['requested_username']
            if c.execute('SELECT 1 FROM edge_bff.users WHERE username=%s', (name,)).fetchone():
                return taken()
            try:
                with c.transaction():
                    active = c.execute('''UPDATE edge_bff.users SET username=%s, requested_username=NULL, status='active',
                        email_verified_at=now(), registration_hash=NULL WHERE user_id=%s
                        RETURNING user_id, owner_key, username, role, status''', (name, user['user_id'])).fetchone()
            except pg_errors.UniqueViolation as e:
                return taken() if 'username' in (e.diag.constraint_name or '') else ('invalid', None)
            c.execute('UPDATE edge_bff.email_codes SET consumed_at=now() WHERE code_id=%s', (found['code_id'],))
            c.execute("DELETE FROM edge_bff.users WHERE email=%s AND status='pending' AND user_id<>%s",
                      (email, user['user_id']))
            # the verifier this browser set (the A2 fix: the browser that finished the registration gets its device token)
            verifier = c.execute('''SELECT verifier FROM edge_bff.identities WHERE user_id=%s AND provider='password' ''',
                                 (user['user_id'],)).fetchone()
            return 'ok', {**active, 'verifier': verifier['verifier'] if verifier else None}

    def resend(self, email, purpose, ip, registration=None, binding=None, device_token=None):
        """A new code for this browser's pending registration (register) or for an active account (reset), within the
        send limits; True when one was queued. A reset's code is bound to this browser (`binding`), and a browser where
        the account's password was proved (`device_token`, its device cookie) asks under its own budget (_may_send)."""
        with self.store.connect() as c:
            self._lock(c, email)
            if purpose == 'register':
                if not self._may_send(c, email, ip):
                    return False
                user = self._registration(c, email, registration)
                return bool(user) and self._issue_code(c, user['user_id'], purpose, email, ip)
            user = c.execute("SELECT user_id FROM edge_bff.users WHERE email=%s AND status='active' FOR UPDATE",
                             (email,)).fetchone()
            device = self.device_valid(c, user['user_id'], device_token) if user else None
            if not self._may_send(c, email, ip, binding, device) or not user:
                return False
            return self._issue_code(c, user['user_id'], purpose, email, ip, device, binding)

    def restart(self, user_id, email, ip, registration):
        """A sign-in with the right password of a pending registration (ERRORS M478, C1 P1-M1): within the send limits,
        the registration moves to this browser (its cookie) and a fresh code is mailed; True when one was queued."""
        with self.store.connect() as c:
            self._lock(c, email)
            if not self._may_send(c, email, ip):
                return False
            # a registration at its day's mails (REGISTRATION_MAIL) gets no code, so it must not move either: moved to a
            # cookie that was never sent, the code already mailed would finish it on no browser (3c check C3-19)
            if Throttle._wait(c, REGISTRATION_MAIL, self._h(REGISTRATION_MAIL, str(user_id))):
                return False
            if not c.execute('''UPDATE edge_bff.users SET registration_hash=%s WHERE user_id=%s AND status='pending'
                    RETURNING user_id''', (registration, user_id)).fetchone():
                return False
            return self._issue_code(c, user_id, 'register', email, ip)

    def reset(self, email, code, verifier, client=None, binding=None):
        """('ok', user {user_id, email, username}) with the password replaced, every session revoked and the
        notification queued | ('invalid', None) | ('limited', seconds). The account's users row is locked first
        (accounts.py: a sign-in or change proved before the reset is then refused, a session made before it revoked).
        `client`: the client address the reset's code counts are keyed by; `binding`: the SHA-256 of this browser's
        reset cookie, whose code it is (_check_code)."""
        with self.store.connect() as c:
            self._lock(c, email)
            user = c.execute('''SELECT user_id, email, username FROM edge_bff.users WHERE email=%s AND status='active'
                FOR UPDATE''', (email,)).fetchone()
            outcome, found = self._check_code(c, user, 'reset', code, email, client, binding)
            if outcome != 'ok':
                return outcome, found
            c.execute('UPDATE edge_bff.email_codes SET consumed_at=now() WHERE code_id=%s', (found['code_id'],))
            self._set_password(c, user['user_id'], verifier)
            c.execute(f'UPDATE edge_bff.sessions SET revoked_at=now() WHERE {ACCOUNT_SESSIONS} AND revoked_at IS NULL',
                      (user['user_id'], user['user_id']))
            # a reset proved by the email code is a recovery: it clears the MFA failure counts and locks (N2)
            c.execute('''UPDATE edge_bff.mfa_totp SET totp_failures=0, recovery_failures=0, totp_locked_until=NULL,
                recovery_locked_until=NULL WHERE user_id=%s''', (user['user_id'],))
            enqueue(c, 'password_changed', user['email'], email_texts.password_changed_email())
            return 'ok', user

    @staticmethod
    def _set_password(c, user_id, verifier):
        """The new verifier; a new password also ends the consecutive-failure count and lock of the old one (R1-16)."""
        c.execute('''UPDATE edge_bff.identities SET verifier=%s, updated_at=now(), sign_in_failures=0,
            sign_in_locked_until=NULL WHERE user_id=%s AND provider='password' ''', (verifier, user_id))

    def account(self, user_id):
        with self.store.connect() as c:
            return c.execute('''SELECT u.user_id, u.email, u.username, i.verifier FROM edge_bff.users u
                JOIN edge_bff.identities i ON i.user_id=u.user_id AND i.provider='password' WHERE u.user_id=%s''',
                             (user_id,)).fetchone()

    def change(self, user_id, verifier, keep_token_hash, email, proved):
        """'ok': the new password, every other session revoked, the notification queued. Under the account's lock and
        only while the proof still holds (ERRORS R2-9): 'session_ended' when the changing session was revoked meanwhile
        (a reset, a sign-out everywhere), 'password_changed' when the verifier the current password proved was
        replaced meanwhile; nothing changes then."""
        with self.store.connect() as c:
            if AccountStore.lock_account(c, user_id) is None or not c.execute('''SELECT 1 FROM edge_bff.sessions
                    WHERE token_hash=%s AND user_id=%s AND revoked_at IS NULL AND expires_at > now()''',
                                                                               (keep_token_hash, user_id)).fetchone():
                return 'session_ended'
            if not c.execute('''SELECT 1 FROM edge_bff.identities WHERE user_id=%s AND provider='password'
                    AND verifier=%s''', (user_id, proved)).fetchone():
                return 'password_changed'
            self._set_password(c, user_id, verifier)
            c.execute(f'''UPDATE edge_bff.sessions SET revoked_at=now() WHERE {ACCOUNT_SESSIONS} AND revoked_at IS NULL
                AND token_hash<>%s''', (user_id, user_id, keep_token_hash))
            if email:
                enqueue(c, 'password_changed', email, email_texts.password_changed_email())
            return 'ok'

    # ---- MFA --------------------------------------------------------------------------------------------------------

    TOTP_COLUMNS = '''nonce, confirmed_at, last_step, pending_nonce, totp_failures, recovery_failures,
        totp_locked_until, recovery_locked_until'''

    def totp(self, user_id):
        """The account's enrolment row, read without a lock (MFA_NOT_ENROLLED; the decisions are made by mfa_try)."""
        with self.store.connect() as c:
            return c.execute(f'SELECT {self.TOTP_COLUMNS} FROM edge_bff.mfa_totp WHERE user_id=%s', (user_id,)).fetchone()

    def enroll(self, user_id, nonce, hashes, session_hash):
        """'ok' | 'mfa_required', decided and written under the enrolment's row lock (ERRORS R2-9: the permission is
        part of the write). With no confirmed enrolment the account's one candidate is replaced (the first enrolment,
        CONTRACT 4: any session of the account, the admin enrols at switch-on). With a confirmed one only a session that
        passed MFA within MFA_RECENT_SECONDS may start a new one (session_hash: the request's session, read in this
        transaction by the database's clock; a pass made earlier, or none, verifies again first), and it waits beside
        the confirmed one (pending_nonce and recovery codes marked pending) until a code of the new authenticator
        confirms it (use_step): the confirmed factor, its replay guard and its recovery codes keep working meanwhile
        (ERRORS R1-7). Failure counts are kept: only a success clears them."""
        with self.store.connect() as c:
            c.execute('INSERT INTO edge_bff.mfa_totp(user_id, nonce) VALUES (%s,%s) ON CONFLICT (user_id) DO NOTHING',
                      (user_id, nonce))
            row = c.execute('SELECT nonce, confirmed_at FROM edge_bff.mfa_totp WHERE user_id=%s FOR UPDATE',
                            (user_id,)).fetchone()
            if row['confirmed_at'] is None:
                c.execute('''UPDATE edge_bff.mfa_totp SET nonce=%s, created_at=now(), last_step=NULL, pending_nonce=NULL,
                    pending_created_at=NULL WHERE user_id=%s''', (nonce, user_id))
                c.execute('DELETE FROM edge_bff.mfa_recovery_codes WHERE user_id=%s', (user_id,))
                pending = False
            elif not c.execute('''SELECT 1 FROM edge_bff.sessions WHERE token_hash=%s AND user_id=%s
                    AND revoked_at IS NULL AND expires_at > now()
                    AND mfa_passed_at > now() - make_interval(secs => %s)''',
                               (session_hash, user_id, MFA_RECENT_SECONDS)).fetchone():
                return 'mfa_required'
            else:
                c.execute('UPDATE edge_bff.mfa_totp SET pending_nonce=%s, pending_created_at=now() WHERE user_id=%s',
                          (nonce, user_id))
                c.execute('DELETE FROM edge_bff.mfa_recovery_codes WHERE user_id=%s AND pending', (user_id,))
                pending = True
            for h in hashes:
                c.execute('INSERT INTO edge_bff.mfa_recovery_codes(user_id, code_hash, pending) VALUES (%s,%s,%s)',
                          (user_id, h, pending))
            return 'ok'

    def mfa_try(self, user_id, kind, now, check):
        """One MFA try decided, checked and (when wrong) counted in one transaction under the enrolment's row lock, so
        tries sent together reach the check one at a time against the count the previous one left (ERRORS R2-12; NIST
        SP 800-63B-4: at most TOTP_FAILURE_CAP consecutive failures). A lock that has ended restarts the count (N2).
        check(row, c) answers, on the same connection: a CheckedStep (a TOTP code matched; use_step confirms it after
        this transaction), True (a recovery code was used), or None (wrong). Returns ('not_enrolled', None),
        ('locked', row), ('invalid', None), ('matched', CheckedStep) or ('ok', None)."""
        count, until, cap, restart = MFA_WAYS[kind]
        with self.store.connect() as c:
            row = c.execute(f'SELECT {self.TOTP_COLUMNS} FROM edge_bff.mfa_totp WHERE user_id=%s FOR UPDATE',
                            (user_id,)).fetchone()
            if row is None:
                return 'not_enrolled', None
            if row[count] >= cap:
                if mfa_way_locked(row, kind, now):
                    return 'locked', row
                row = c.execute(f'''UPDATE edge_bff.mfa_totp SET {count}=%s, {until}=NULL WHERE user_id=%s
                    RETURNING {self.TOTP_COLUMNS}''', (restart, user_id)).fetchone()
            found = check(row, c)
            if found is None:
                c.execute(f'''UPDATE edge_bff.mfa_totp SET {count}={count}+1,
                    {until}=CASE WHEN {count}+1 >= %s THEN %s ELSE {until} END WHERE user_id=%s''',
                          (cap, int(now) + LOCK_SECONDS, user_id))
                return 'invalid', None
            if isinstance(found, CheckedStep):
                return 'matched', found
            c.execute('''UPDATE edge_bff.mfa_totp SET totp_failures=0, recovery_failures=0, totp_locked_until=NULL,
                recovery_locked_until=NULL WHERE user_id=%s''', (user_id,))
            return 'ok', None

    @staticmethod
    def recovery_check(user_id, code_hash):
        """The check of mfa_try for a recovery code: one unused code of the confirmed enrolment (never one of a
        re-enrolment still waiting) is used, in mfa_try's transaction."""
        def check(row, c):
            if row['confirmed_at'] is None:
                return None
            return c.execute('''UPDATE edge_bff.mfa_recovery_codes SET used_at=now() WHERE user_id=%s AND code_hash=%s
                AND used_at IS NULL AND NOT pending RETURNING user_id''', (user_id, code_hash)).fetchone() and True
        return check

    def use_step(self, user_id, checked):
        """True when `checked` (a CheckedStep) still names an enrolment of the account (ERRORS R2-11: never the one
        another session wrote after the check) and its step is after the last one used: that enrolment is then the
        confirmed one with this step as its last. A waiting re-enrolment proved this way replaces the confirmed one,
        its recovery codes the old ones (ERRORS R1-7)."""
        nonce, step = checked
        with self.store.connect() as c:
            if c.execute('''UPDATE edge_bff.mfa_totp SET last_step=%s, confirmed_at=coalesce(confirmed_at, now()),
                    totp_failures=0, recovery_failures=0, totp_locked_until=NULL, recovery_locked_until=NULL
                WHERE user_id=%s AND nonce=%s AND (last_step IS NULL OR last_step < %s) RETURNING user_id''',
                         (step, user_id, nonce, step)).fetchone():
                return True
            if not c.execute('''UPDATE edge_bff.mfa_totp SET nonce=pending_nonce, pending_nonce=NULL,
                    pending_created_at=NULL, created_at=now(), confirmed_at=now(), last_step=%s, totp_failures=0,
                    recovery_failures=0, totp_locked_until=NULL, recovery_locked_until=NULL
                WHERE user_id=%s AND pending_nonce=%s RETURNING user_id''', (step, user_id, nonce)).fetchone():
                return False
            c.execute('DELETE FROM edge_bff.mfa_recovery_codes WHERE user_id=%s AND NOT pending', (user_id,))
            c.execute('UPDATE edge_bff.mfa_recovery_codes SET pending=false WHERE user_id=%s', (user_id,))
            return True

    def mfa_failed(self, user_id, kind, cap, lock_until):
        """One more consecutive failure of `kind` (totp or recovery); reaching the cap starts a lock until lock_until.
        For a matched code use_step refused (a replayed step, an enrolment replaced since the check)."""
        count, until = {'totp': ('totp_failures', 'totp_locked_until'),
                        'recovery': ('recovery_failures', 'recovery_locked_until')}[kind]
        with self.store.connect() as c:
            c.execute(f'''UPDATE edge_bff.mfa_totp SET {count}={count}+1,
                {until}=CASE WHEN {count}+1 >= %s THEN %s ELSE {until} END WHERE user_id=%s''', (cap, lock_until, user_id))


class AuthFlows:
    def __init__(self, settings, store, auth, throttle, sender=None, pwned_fetch=None, password_work=None):
        self.settings, self.auth, self.throttle, self.sender = settings, auth, throttle, sender
        self.store = FlowStore(settings, store, throttle)
        self.outbox = OutboxStore(store)
        self.pwned_fetch = pwned_fetch          # tests replace the range API
        self.clock = time.time                  # tests freeze the TOTP clock
        self.with_registration = None           # set by routes()
        # the A2 fix (ERRORS M517): the cookie of a browser where an account's password was proved (security.device_of)
        self.device_cookie = cookie_name(DEVICE_COOKIE, settings.secure_cookie)
        # ERRORS R2-37: the derivations and the Pwned Passwords calls run here, never on the default executor
        self.password_work = password_work or passwords.PasswordWork()

    def wake(self):
        if self.sender is not None:
            self.sender.wake()

    def set_device(self, response, user_id, verifier):
        """This browser's device cookie (the A2 fix, ERRORS M517): a new token of the account over its current verifier
        (security.device_token), set where the browser just proved the account's password (a sign-in, a password
        change). HttpOnly, SameSite=Strict, on the registration cookie's path (__Host- on https)."""
        response.set_cookie(self.device_cookie, device_token(self.settings.session_secret, user_id, verifier),
                            max_age=DEVICE_SECONDS, httponly=True, secure=self.settings.secure_cookie,
                            samesite='strict', path=registration_path(self.settings.secure_cookie))
        return response

    async def breached(self, password):
        return await self.password_work.run(passwords.pwned, password, self.pwned_fetch)

    async def restart_registration(self, response, row, ip, request=None):
        """A switch-on sign-in refused 401 (main.py). Every such answer carries a registration cookie, so the headers
        never differ: when the password was a pending registration's, that registration moves to a new cookie and a
        fresh code is mailed (within the send limits); otherwise this browser's own registration cookie is set again
        unchanged (N3: a mistyped sign-in never orphans a registration), or an unused one when it has none."""
        name = cookie_name(REGISTRATION_COOKIE, self.settings.secure_cookie)
        held = request.cookies.get(name, '') if request is not None else ''
        fresh = secrets.token_hex(32)
        moved = row is not None and await asyncio.to_thread(self.store.restart, row['user_id'], row['email'], ip,
                                                            token_hash(fresh))
        if moved:
            self.wake()
        registration = fresh if moved or not REGISTRATION_TOKEN.fullmatch(held) else held
        if self.with_registration is not None:
            self.with_registration(response, registration)
        return response

    async def new_verifier(self, password):
        """The verifier of a new password (refused when breached), on the password pool; the caller holds a request
        slot of it (password_work.admitted_request)."""
        if await self.breached(password):
            raise Refusal(400, 'PASSWORD_BREACHED', {'fields': ['password']})
        return await self.password_work.run(password_verifier, password)

    async def check_second_factor(self, user_id, code, recovery):
        """The account's second factor (POST /api/v1/auth/mfa/verify; and, Phase 4, the admin page's code step on the
        beta, app/admin.py, the user's "1A" of 2026-11-22): one of code (6 digits) or recovery_code. Returns once it
        passed; else raises its refusal (INVALID_INPUT, LIMIT_REACHED, MFA_NOT_ENROLLED, MFA_LOCKED, MFA_CODE_INVALID)."""
        settings, store = self.settings, self.store
        code, recovery = (code or '').strip() if isinstance(code, str) else '', \
            (recovery or '').strip() if isinstance(recovery, str) else ''
        if bool(code) == bool(recovery):
            raise invalid({'code': 'Send code (6 digits from the authenticator app) or recovery_code, not both.'})
        key = str(user_id)
        wait = await asyncio.to_thread(self.throttle.attempt, MFA_USER, key)
        if wait:
            raise Refusal(429, 'LIMIT_REACHED', {'limit': 'mfa_tries', 'retry_after_s': wait}, {'Retry-After': str(wait)})
        if user_id is None or await asyncio.to_thread(store.totp, user_id) is None:
            raise Refusal(400, 'MFA_NOT_ENROLLED')
        # NIST SP 800-63B-4: at most 100 consecutive failed codes per account (10 for recovery codes), counted
        # across every window and cleared only by a success (ERRORS M478, C1 P1-M2), decided, checked and counted
        # under the enrolment's row lock (FlowStore.mfa_try, ERRORS R2-12). A lock lasts LOCK_SECONDS from the
        # failure that reached the cap; then the count restarts just below it (N2). A password reset by email code
        # or the operator (scripts/edge_mfa_unlock.py) clears it earlier.
        kind, cap = ('totp', TOTP_FAILURE_CAP) if code else ('recovery', RECOVERY_FAILURE_CAP)
        now = self.clock()
        if code:
            def check(row, _c):
                # the confirmed (or first) enrolment first, then a re-enrolment waiting beside it (R1-7)
                for nonce in (row['nonce'], row['pending_nonce']):
                    if nonce is not None:
                        step = mfa.matching_step(mfa.secret_of(settings.mfa_key, user_id, bytes(nonce)), code,
                                                 mfa.step_now(self.clock))
                        if step is not None:
                            return CheckedStep(bytes(nonce), step)
                return None
        else:
            check = FlowStore.recovery_check(user_id, mfa.recovery_hash(settings.mfa_key, user_id, recovery))
        outcome, found = await asyncio.to_thread(store.mfa_try, user_id, kind, now, check)
        if outcome == 'not_enrolled':
            raise Refusal(400, 'MFA_NOT_ENROLLED')
        if outcome == 'locked':
            # details.use names the other way while it is open, by mfa_try's own lock test on the same row (none:
            # both are locked, so the page waits for the unlock or a password reset; ERRORS M519)
            other, open_way = ('recovery', 'recovery_code') if code else ('totp', 'code')
            raise Refusal(403, 'MFA_LOCKED', {
                'locked': 'code' if code else 'recovery_code',
                'unlock_at': datetime.fromtimestamp(found[f'{kind}_locked_until'], timezone.utc).isoformat(),
                **({} if mfa_way_locked(found, other, now) else {'use': open_way})})
        # a matched code confirms the enrolment it was checked against, if that is still the account's (R2-11);
        # a replayed step or an enrolment replaced since the check counts as a failure
        ok = outcome == 'ok' or (outcome == 'matched' and await asyncio.to_thread(store.use_step, user_id, found))
        if not ok:
            if outcome == 'matched':
                await asyncio.to_thread(store.mfa_failed, user_id, kind, cap, int(now) + LOCK_SECONDS)
            raise Refusal(400, 'MFA_CODE_INVALID', {'fields': ['code' if code else 'recovery_code']})
        await asyncio.to_thread(self.throttle.clear, MFA_USER, key)

    def routes(self, app, session_answer):
        settings, auth, store = self.settings, self.auth, self.store
        session_cookie = cookie_name(COOKIE, settings.secure_cookie)
        registration_cookie = cookie_name(REGISTRATION_COOKIE, settings.secure_cookie)
        registration_at = registration_path(settings.secure_cookie)
        reset_cookie = cookie_name(RESET_COOKIE, settings.secure_cookie)
        device_cookie = self.device_cookie

        async def switched_on():
            if not settings.multiuser:
                raise Refusal(404, 'NOT_FOUND')

        async def registration_open():
            """Track guest: the pre-launch mode of the live site (Settings.prelaunch; the user, 2026-11-19: "Terbuka, tapi
            belum bisa mendaftar") closes registration with a plain sentence (403 REGISTRATION_CLOSED, the same for
            every address, so it tells nothing about one); the reset of an account's password stays open (the test
            accounts set theirs with it)."""
            if settings.prelaunch:
                raise Refusal(403, 'REGISTRATION_CLOSED')

        def signed_in(p, token, status=200):
            response = JSONResponse(session_answer(p), status_code=status)
            response.set_cookie(session_cookie, token, max_age=settings.session_seconds, httponly=True,
                                secure=settings.secure_cookie, samesite='strict', path='/')
            return response

        def registration_of(request):
            raw = request.cookies.get(registration_cookie, '')
            return token_hash(raw) if REGISTRATION_TOKEN.fullmatch(raw) else None

        def with_registration(response, token):
            response.set_cookie(registration_cookie, token, max_age=REGISTRATION_SECONDS, httponly=True,
                                secure=settings.secure_cookie, samesite='strict', path=registration_at)
            return response
        self.with_registration = with_registration

        def with_reset(request, response):
            """This browser's reset binding (the A2 fix): the valid token its reset cookie holds, else a new one, set on
            the answer either way (every "Forgot password?" answer carries it, whatever the address, so the headers say
            nothing about one); the SHA-256 the codes keep (binding_hash)."""
            raw = request.cookies.get(reset_cookie, '')
            token = raw if REGISTRATION_TOKEN.fullmatch(raw) else secrets.token_hex(32)
            response.set_cookie(reset_cookie, token, max_age=RESET_SECONDS, httponly=True,
                                secure=settings.secure_cookie, samesite='strict', path=registration_at)
            return token_hash(token)

        def reset_binding(request):
            raw = request.cookies.get(reset_cookie, '')
            return token_hash(raw) if REGISTRATION_TOKEN.fullmatch(raw) else None

        def code_refusal(outcome, found):
            if outcome == 'limited':
                return Refusal(429, 'LIMIT_REACHED', {'limit': 'code_tries', 'retry_after_s': found},
                               {'Retry-After': str(found)})
            return Refusal(400, 'CODE_INVALID_OR_EXPIRED', {'fields': ['code']})

        @app.get('/api/v1/auth/config')
        async def config():
            """Public: whether registration and "Forgot password?" are open (the sign-in page reads it). Track guest,
            with the switch on: `registration` (false in the pre-launch mode: the register page says it opens soon),
            `prelaunch`, `guests` (a visitor opens the Terminal) and `upgrade_contact` (the upgrade box's contact, null
            when not set: the box says the contact comes soon). With the switch off the answer is as before."""
            if not settings.multiuser:
                return {'multiuser': False}
            # live checker S1 (2026-11-20): the tabs this site never offers (principal.BETA_ONLY_TABS on the live site:
            # the Monitor and the admin pages), so the shell shows neither their rail entries nor their buttons.
            # 3f checker SERVE-3 (the lab gap; the user's go 2026-11-22): this answer is public, so it names no lab tab
            # (it named them, telling every visitor what is being built); a lab tab has no entry in the public shell to
            # hide (tests/test_live_switch.py holds its id out of the shell's files) and its capability is masked on
            # the live site for every principal (principal.live_view)
            hidden = sorted(BETA_ONLY_TABS) if settings.site == LIVE else []
            return {'multiuser': True, 'registration': not settings.prelaunch, 'prelaunch': settings.prelaunch,
                    'guests': settings.guests, 'upgrade_contact': settings.upgrade_contact or None, 'hidden_tabs': hidden,
                    # the footer's Privacy and Terms links, null until their texts exist (EXEC option A, 2026-11-20)
                    'legal': {'privacy': settings.privacy_url or None, 'terms': settings.terms_url or None}}

        @app.post('/api/v1/auth/register', status_code=202)
        async def register(request: Request, _on=Depends(switched_on), _open=Depends(registration_open)):
            b = fields_of(await request.body(), ('username', 'first_name', 'last_name', 'email', 'phone', 'password',
                                                 'password_repeat'),
                          ('username', 'first_name', 'last_name', 'email', 'phone', 'password', 'password_repeat'))
            # the phone is a required field (user: "isian wajib seperti First Name, Last Name, ID, Email, Phone Number")
            phone = passwords.normal_phone(b['phone'])
            if phone is None:
                raise invalid({'phone': 'Enter a phone number with its country code, e.g. +62 812 3456 7890 or 0812 3456 7890.'})
            f = {'username': checked_username(b['username']), 'first_name': checked_name(b['first_name'], 'first_name'),
                 'last_name': checked_name(b['last_name'], 'last_name'), 'email': checked_email(b['email']),
                 'phone': phone}
            async with self.password_work.admitted_request():
                verifier = await self.new_verifier(checked_passwords(b))
            # every valid registration answers alike and gets a registration cookie of its own (stored only as a hash,
            # and only when a pending registration was made with it). ERRORS R1-11: when nothing was made, a browser
            # whose own cookie names a pending registration of this address keeps it, so its mailed code still works
            registration, held = secrets.token_hex(32), request.cookies.get(registration_cookie, '')
            held = held if REGISTRATION_TOKEN.fullmatch(held) else None
            queued, keep_held = await asyncio.to_thread(store.register, f, verifier, client_address(request),
                                                        token_hash(registration), token_hash(held) if held else None)
            if queued:
                self.wake()
            return with_registration(JSONResponse(ACCEPTED, status_code=202), held if keep_held else registration)

        @app.post('/api/v1/auth/register/verify')
        async def register_verify(request: Request, _on=Depends(switched_on), _open=Depends(registration_open)):
            b = fields_of(await request.body(), ('email', 'code', 'username'), ('email', 'code'))
            email = checked_email(b['email'])
            username = checked_username(b['username']) if (b.get('username') or '').strip() else None
            outcome, found = await asyncio.to_thread(store.verify_registration, email, b['code'].strip(),
                                                     registration_of(request), username)
            if outcome == 'taken':
                raise Refusal(409, 'USERNAME_TAKEN', {'fields': ['username']})
            if outcome != 'ok':
                raise code_refusal(outcome, found)
            token = secrets.token_hex(32)
            await asyncio.to_thread(auth.accounts.create_session, token_hash(token), found, settings.session_seconds,
                                    self.throttle.key_hash(SIGNIN_IP, client_address(request)))
            await asyncio.to_thread(auth.accounts.signed_in, found['user_id'])
            p = await auth.resolve(token)
            if p is None:
                raise Refusal(401, 'UNAUTHENTICATED')
            # CONTRACT.md 8a: every answer made for a principal carries its X-Edge-Entitlements, this signed-in answer
            # too (as the sign-in's; re-check R2-40 item 4)
            request.state.principal = p
            response = signed_in(p, token)
            response.delete_cookie(registration_cookie, path=registration_at, secure=settings.secure_cookie)
            if found.get('verifier'):
                # the A2 fix (ERRORS M517): this browser set the account's password and proved its mailbox
                self.set_device(response, found['user_id'], found['verifier'])
            return response

        @app.post('/api/v1/auth/code/resend', status_code=202)
        async def code_resend(request: Request, _on=Depends(switched_on)):
            b = fields_of(await request.body(), ('email', 'purpose'), ('email', 'purpose'))
            if b['purpose'] not in PURPOSES:
                raise invalid({'purpose': 'purpose is register or reset.'})
            if b['purpose'] == 'register':
                await registration_open()
            response = JSONResponse(ACCEPTED, status_code=202)
            binding = with_reset(request, response) if b['purpose'] == 'reset' else None
            if await asyncio.to_thread(store.resend, checked_email(b['email']), b['purpose'], client_address(request),
                                       registration_of(request), binding, request.cookies.get(device_cookie)):
                self.wake()
            return response

        @app.post('/api/v1/auth/password/forgot', status_code=202)
        async def password_forgot(request: Request, _on=Depends(switched_on)):
            b = fields_of(await request.body(), ('email',), ('email',))
            response = JSONResponse(ACCEPTED, status_code=202)
            binding = with_reset(request, response)
            if await asyncio.to_thread(store.resend, checked_email(b['email']), 'reset', client_address(request), None,
                                       binding, request.cookies.get(device_cookie)):
                self.wake()
            return response

        @app.post('/api/v1/auth/password/reset')
        async def password_reset(request: Request, _on=Depends(switched_on)):
            b = fields_of(await request.body(), ('email', 'code', 'password', 'password_repeat'),
                          ('email', 'code', 'password', 'password_repeat'))
            email = checked_email(b['email'])
            async with self.password_work.admitted_request():
                verifier = await self.new_verifier(checked_passwords(b))
            address = client_address(request)
            outcome, found = await asyncio.to_thread(store.reset, email, b['code'].strip(), verifier, address,
                                                     reset_binding(request))
            if outcome != 'ok':
                raise code_refusal(outcome, found)
            # ERRORS R1-9: the reset proved the mailbox, and its answer says to sign in next: this client's sign-in
            # count of the account's logins goes (the account's failure cap went with the new password, _set_password)
            await asyncio.to_thread(self.throttle.clear, SIGNIN_LOGIN, *((normal_login(login), address)
                                                                         for login in (found['username'], found['email'])
                                                                         if login))
            self.wake()
            response = JSONResponse({'next': 'sign_in'})
            response.delete_cookie(session_cookie, path='/', secure=settings.secure_cookie)
            response.delete_cookie(reset_cookie, path=registration_at, secure=settings.secure_cookie)
            return response

        @app.post('/api/v1/auth/password/change')
        async def password_change(request: Request, _on=Depends(switched_on), p: Principal = Depends(auth.writer)):
            b = fields_of(await request.body(), ('current_password', 'password', 'password_repeat'),
                          ('current_password', 'password', 'password_repeat'))
            # its own counter (ERRORS R1-10: it shared the sign-in's, so the login 'change:<id>' typed at sign-in locked it)
            key = str(p.user_id)
            async with self.password_work.admitted_request():
                wait = await asyncio.to_thread(self.throttle.attempt, PASSWORD_CHANGE, key)
                if wait:
                    # the account's own password-change tries, not a place's sign-ins (3c check C3-21)
                    raise Refusal(429, 'LIMIT_REACHED', {'limit': 'password_change', 'retry_after_s': wait},
                                  {'Retry-After': str(wait)})
                account = await asyncio.to_thread(store.account, p.user_id)
                # a current password is a password try of the account like a sign-in's: counted in the same statement
                # before the check, and refused while the account is locked (CONTRACT.md section 4, at most 100
                # consecutive failures; 3c check C3-20); a right one ends the run of failures. The A2 fix (ERRORS M517):
                # from a browser where the password was proved before (its device cookie, under its own failure limit)
                # the try neither counts towards nor waits for that lock, as at the sign-in
                device = await asyncio.to_thread(store.device_try, p.user_id, request.cookies.get(device_cookie))
                tried = True if device else await asyncio.to_thread(auth.accounts.sign_in_try, p.user_id)
                proved = bool(account) and await self.password_work.run(verify_password, b['current_password'],
                                                                         account['verifier'])
                if not (proved and tried):
                    raise Refusal(400, 'CURRENT_PASSWORD_INVALID', {'fields': ['current_password']})
                if device:
                    await asyncio.to_thread(self.throttle.clear, DEVICE_SIGNIN, (str(p.user_id), device))
                else:
                    await asyncio.to_thread(auth.accounts.sign_in_proved, p.user_id)
                verifier = await self.new_verifier(checked_passwords(b))
            # ERRORS R2-9: written only while this session is live and the proved verifier is still the account's
            outcome = await asyncio.to_thread(store.change, p.user_id, verifier, token_hash(p.token), account['email'],
                                              account['verifier'])
            if outcome == 'session_ended':
                raise Refusal(401, 'UNAUTHENTICATED')
            if outcome == 'password_changed':
                raise Refusal(400, 'CURRENT_PASSWORD_INVALID', {'fields': ['current_password']})
            await asyncio.to_thread(self.throttle.clear, PASSWORD_CHANGE, key)
            self.wake()
            # this browser proved the old password and set the new one: its device token follows the new verifier (the
            # tokens of every other browser end with the old one)
            response = JSONResponse({'status': 'PASSWORD_CHANGED'})
            self.set_device(response, p.user_id, verifier)
            return response

        @app.post('/api/v1/auth/sign-out-all')
        async def sign_out_all(_on=Depends(switched_on), p: Principal = Depends(auth.writer)):
            await asyncio.to_thread(auth.accounts.revoke_all, p.user_id)
            response = JSONResponse({'authenticated': False})
            response.delete_cookie(session_cookie, path='/', secure=settings.secure_cookie)
            return response

        @app.post('/api/v1/auth/mfa/enroll')
        async def mfa_enroll(_on=Depends(switched_on), p: Principal = Depends(auth.second_factor_holder())):
            """otpauth URI and 10 recovery codes, shown once. A confirmed enrolment is replaced only by a session that
            passed MFA within the last MFA_RECENT_SECONDS (else 403 MFA_REQUIRED with details.recent_s: a password alone
            never resets the second factor, and an older pass enters a fresh code first, POST /api/v1/auth/mfa/verify),
            and only once a code of the new authenticator confirms it (FlowStore.enroll, ERRORS R1-7): until then the
            confirmed one works."""
            nonce = secrets.token_bytes(16)
            codes = [mfa.new_recovery_code() for _ in range(mfa.RECOVERY_CODES)]
            if await asyncio.to_thread(store.enroll, p.user_id, nonce,
                                       [mfa.recovery_hash(settings.mfa_key, p.user_id, x) for x in codes],
                                       token_hash(p.token)) != 'ok':
                raise Refusal(403, 'MFA_REQUIRED', {'mfa_enrolled': True, 'recent_s': MFA_RECENT_SECONDS})
            secret = mfa.secret_of(settings.mfa_key, p.user_id, nonce)
            return {'otpauth_uri': mfa.otpauth_uri(secret, p.username or str(p.user_id)),
                    'secret': base64.b32encode(secret).decode().rstrip('='), 'recovery_codes': codes}

        @app.post('/api/v1/auth/mfa/verify')
        async def mfa_verify(request: Request, _on=Depends(switched_on), p: Principal = Depends(auth.writer)):
            b = fields_of(await request.body(), ('code', 'recovery_code'), ())
            await self.check_second_factor(p.user_id, b.get('code'), b.get('recovery_code'))
            # OWASP Session Management: a new session token at the privilege change. ERRORS R2-9: made only while the
            # pending session is still live, and that session is revoked in the same transaction, so a reset or a
            # sign-out everywhere since this request began leaves no session behind
            token = secrets.token_hex(32)
            if await asyncio.to_thread(auth.accounts.create_session, token_hash(token),
                                       {'user_id': p.user_id, 'owner_key': p.owner_key}, settings.session_seconds,
                                       self.throttle.key_hash(SIGNIN_IP, client_address(request)), True, True,
                                       None, token_hash(p.token)) is None:
                raise Refusal(401, 'UNAUTHENTICATED')
            fresh = await auth.resolve(token)
            if fresh is None:
                raise Refusal(401, 'UNAUTHENTICATED')
            return signed_in(fresh, token)

        @app.post('/api/v1/hooks/email/resend')
        async def resend_hook(request: Request, _on=Depends(switched_on),
                              raw=Depends(hooks.signed('/api/v1/hooks/email/resend',
                                                       lambda: settings.resend_webhook_secret))):
            """Resend's bounces and complaints (CONTRACT.md sections 5 and 6): no session; the Svix signature over the
            raw body proves the sender (hooks.signed, before this body runs: re-check R1-15); a repeated svix-id changes
            nothing."""
            try:
                event = json.loads(raw)
                kind = event.get('type') if isinstance(event, dict) else None
                to = (event.get('data') or {}).get('to') if isinstance(event, dict) else None
            except (ValueError, AttributeError):
                raise Refusal(400, 'INVALID_INPUT', {'fields': ['body']}) from None
            recipients = [x.strip().lower() for x in (to if isinstance(to, list) else [to] if isinstance(to, str) else [])
                          if isinstance(x, str) and EMAIL.fullmatch(x.strip().lower())]
            applied = await asyncio.to_thread(self.outbox.hook_event, request.headers.get('svix-id'), kind, recipients)
            return jsonable_encoder({'status': 'applied' if applied else 'duplicate'})
