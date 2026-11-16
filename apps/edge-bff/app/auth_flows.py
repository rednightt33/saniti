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
- Sending: at most one email per address per 60 s and 10 per day (SEND_EMAIL); inside those limits nothing is sent and
  nothing changes, with the same 202. Sends per client address are recorded (SEND_IP), not enforced.
- A reset revokes every session and signs nobody in (200 {"next": "sign_in"}); a change revokes the other sessions;
  both send a notification email.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
import time

from fastapi import Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors

from . import email_texts, mfa, passwords
from .accounts import EMAIL, RESERVED_USERNAMES, USERNAME, new_owner_key
from .errors import Refusal
from .mailer import OutboxStore, enqueue, svix_verify
from .principal import ADMIN_ACCESS, Principal
from .security import password_verifier, token_hash, verify_password
from .throttle import CODE_USER, MFA_USER, SEND_EMAIL, SEND_IP, SIGNIN_LOGIN, Throttle, client_address

COOKIE = 'edge_session'
CODE_SECONDS = 300
RESEND_SECONDS = 60
CODE = re.compile(r'[0-9]{6}')
PURPOSES = ('register', 'reset')
ACCEPTED = {'status': 'CODE_SENT', 'resend_after_s': RESEND_SECONDS}


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
    if not EMAIL.fullmatch(email) or len(email) > 254:
        raise invalid({field: 'Enter an email address like name@example.com.'})
    return email


def checked_name(value, field):
    name = ' '.join((value or '').split())
    if not 1 <= len(name) <= 100:
        raise invalid({field: 'Enter 1 to 100 characters.'})
    return name


def checked_passwords(body):
    reason = passwords.length_problem(body.get('password'))
    if reason:
        raise invalid({'password': reason})
    if body.get('password_repeat') != body['password']:
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
        return self.throttle.key_hash(limit.scope, key)

    @staticmethod
    def _lock(c, email):
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('register:' + email,))

    def _may_send(self, c, email, ip):
        """Count the send try of the client address (recorded only); True when the address may get an email now."""
        Throttle._add(c, SEND_IP, self._h(SEND_IP, ip))
        if Throttle._wait(c, SEND_EMAIL, self._h(SEND_EMAIL, email)):
            return False
        return c.execute('''SELECT 1 FROM edge_bff.email_outbox WHERE to_email=%s
            AND created_at > now() - make_interval(secs => %s) LIMIT 1''', (email, RESEND_SECONDS)).fetchone() is None

    def _send(self, c, purpose, email, mail, expires_at=None, key=None):
        Throttle._add(c, SEND_EMAIL, self._h(SEND_EMAIL, email))
        return enqueue(c, purpose, email, mail, expires_at, key)

    def _issue_code(self, c, user_id, purpose, email):
        """A new code (the live one consumed first) and its email, in the caller's transaction."""
        c.execute('''UPDATE edge_bff.email_codes SET consumed_at=now()
            WHERE user_id=%s AND purpose=%s AND consumed_at IS NULL''', (user_id, purpose))
        code = f'{secrets.randbelow(10 ** 6):06d}'
        row = c.execute('''INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, expires_at)
            VALUES (%s,%s,%s, now() + make_interval(secs => %s)) RETURNING code_id, expires_at''',
                        (purpose, user_id, self.code_hash(user_id, purpose, code), CODE_SECONDS)).fetchone()
        self._send(c, purpose, email, email_texts.code_email(purpose, code), row['expires_at'], f'code:{row["code_id"]}')
        return True

    def _check_code(self, c, user, purpose, code):
        """('ok', code row) | ('invalid', None) | ('limited', seconds). A wrong try raises the code's attempts (the code
        is dead at 5) and the user's daily count; the daily cap is read first, so a new code never resets it."""
        if user is None:
            hmac.compare_digest(self.code_hash(0, purpose, code), self.code_hash(0, purpose, '000000'))
            return 'invalid', None
        wait = Throttle._wait(c, CODE_USER, self._h(CODE_USER, str(user['user_id'])))
        if wait:
            return 'limited', wait
        row = c.execute('''SELECT code_id, code_hash, attempts FROM edge_bff.email_codes WHERE user_id=%s AND purpose=%s
            AND consumed_at IS NULL AND expires_at > now() AND attempts < 5 FOR UPDATE''', (user['user_id'], purpose)).fetchone()
        given = self.code_hash(user['user_id'], purpose, code if CODE.fullmatch(code or '') else 'x')
        if row and hmac.compare_digest(row['code_hash'], given):
            return 'ok', row
        if row:
            c.execute('''UPDATE edge_bff.email_codes SET attempts=attempts+1,
                consumed_at=CASE WHEN attempts+1 >= 5 THEN now() END WHERE code_id=%s''', (row['code_id'],))
        Throttle._add(c, CODE_USER, self._h(CODE_USER, str(user['user_id'])))
        return 'invalid', None

    # ---- registration -----------------------------------------------------------------------------------------------

    def register(self, f, verifier, ip):
        """True when an email was queued. A new or pending address gets a pending account (its username requested,
        not held) and a code; an active or disabled one gets the "account exists" email."""
        with self.store.connect() as c:
            self._lock(c, f['email'])
            if not self._may_send(c, f['email'], ip):
                return False
            user = c.execute('SELECT user_id, status FROM edge_bff.users WHERE email=%s FOR UPDATE', (f['email'],)).fetchone()
            if user and user['status'] != 'pending':
                return bool(self._send(c, 'account_exists', f['email'], email_texts.account_exists_email()))
            if user:
                c.execute('''UPDATE edge_bff.users SET requested_username=%s, first_name=%s, last_name=%s, phone_e164=%s
                    WHERE user_id=%s''', (f['username'], f['first_name'], f['last_name'], f['phone'], user['user_id']))
                c.execute('''UPDATE edge_bff.identities SET verifier=%s, updated_at=now()
                    WHERE user_id=%s AND provider='password' ''', (verifier, user['user_id']))
                user_id = user['user_id']
            else:
                user_id = c.execute('''INSERT INTO edge_bff.users(owner_key, username, requested_username, email,
                        first_name, last_name, phone_e164, role, status)
                    VALUES (%s, NULL, %s, %s, %s, %s, %s, 'user', 'pending') RETURNING user_id''',
                                    (new_owner_key(), f['username'], f['email'], f['first_name'], f['last_name'],
                                     f['phone'])).fetchone()['user_id']
                c.execute("""INSERT INTO edge_bff.identities(user_id, provider, subject, verifier)
                    VALUES (%s, 'password', %s, %s)""", (user_id, str(user_id), verifier))
            return self._issue_code(c, user_id, 'register', f['email'])

    def verify_registration(self, email, code, username=None):
        """('ok', user) with the account active and its code consumed | ('taken', None) (the code stays live) |
        ('invalid', None) | ('limited', seconds)."""
        with self.store.connect() as c:
            self._lock(c, email)
            user = c.execute('''SELECT user_id, owner_key, requested_username FROM edge_bff.users
                WHERE email=%s AND status='pending' FOR UPDATE''', (email,)).fetchone()
            outcome, found = self._check_code(c, user, 'register', code)
            if outcome != 'ok':
                return outcome, found
            name = username or user['requested_username']
            if c.execute('SELECT 1 FROM edge_bff.users WHERE username=%s', (name,)).fetchone():
                return 'taken', None
            try:
                with c.transaction():
                    active = c.execute('''UPDATE edge_bff.users SET username=%s, requested_username=NULL, status='active',
                        email_verified_at=now() WHERE user_id=%s RETURNING user_id, owner_key, username, role, status''',
                                       (name, user['user_id'])).fetchone()
            except pg_errors.UniqueViolation:
                return 'taken', None
            c.execute('UPDATE edge_bff.email_codes SET consumed_at=now() WHERE code_id=%s', (found['code_id'],))
            return 'ok', active

    def resend(self, email, purpose, ip):
        """A new code for a pending registration (register) or an active account (reset), within the send limits;
        True when one was queued."""
        with self.store.connect() as c:
            self._lock(c, email)
            if not self._may_send(c, email, ip):
                return False
            user = c.execute('SELECT user_id, status FROM edge_bff.users WHERE email=%s FOR UPDATE', (email,)).fetchone()
            wanted = 'pending' if purpose == 'register' else 'active'
            if not user or user['status'] != wanted:
                return False
            return self._issue_code(c, user['user_id'], purpose, email)

    def reset(self, email, code, verifier):
        """('ok', user) with the password replaced, every session revoked and the notification queued | ('invalid',
        None) | ('limited', seconds)."""
        with self.store.connect() as c:
            self._lock(c, email)
            user = c.execute("SELECT user_id, email FROM edge_bff.users WHERE email=%s AND status='active' FOR UPDATE",
                             (email,)).fetchone()
            outcome, found = self._check_code(c, user, 'reset', code)
            if outcome != 'ok':
                return outcome, found
            c.execute('UPDATE edge_bff.email_codes SET consumed_at=now() WHERE code_id=%s', (found['code_id'],))
            self._set_password(c, user['user_id'], verifier)
            c.execute('UPDATE edge_bff.sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL',
                      (user['user_id'],))
            enqueue(c, 'password_changed', user['email'], email_texts.password_changed_email())
            return 'ok', user

    @staticmethod
    def _set_password(c, user_id, verifier):
        c.execute('''UPDATE edge_bff.identities SET verifier=%s, updated_at=now() WHERE user_id=%s AND provider='password' ''',
                  (verifier, user_id))

    def account(self, user_id):
        with self.store.connect() as c:
            return c.execute('''SELECT u.user_id, u.email, u.username, i.verifier FROM edge_bff.users u
                JOIN edge_bff.identities i ON i.user_id=u.user_id AND i.provider='password' WHERE u.user_id=%s''',
                             (user_id,)).fetchone()

    def change(self, user_id, verifier, keep_token_hash, email):
        """The new password, every other session revoked, the notification queued."""
        with self.store.connect() as c:
            self._set_password(c, user_id, verifier)
            c.execute('''UPDATE edge_bff.sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL
                AND token_hash<>%s''', (user_id, keep_token_hash))
            if email:
                enqueue(c, 'password_changed', email, email_texts.password_changed_email())

    # ---- MFA --------------------------------------------------------------------------------------------------------

    def totp(self, user_id):
        with self.store.connect() as c:
            return c.execute('SELECT nonce, confirmed_at, last_step FROM edge_bff.mfa_totp WHERE user_id=%s',
                             (user_id,)).fetchone()

    def enroll(self, user_id, nonce, hashes):
        with self.store.connect() as c:
            c.execute('''INSERT INTO edge_bff.mfa_totp(user_id, nonce) VALUES (%s,%s) ON CONFLICT (user_id)
                DO UPDATE SET nonce=EXCLUDED.nonce, created_at=now(), confirmed_at=NULL, last_step=NULL''', (user_id, nonce))
            c.execute('DELETE FROM edge_bff.mfa_recovery_codes WHERE user_id=%s', (user_id,))
            for h in hashes:
                c.execute('INSERT INTO edge_bff.mfa_recovery_codes(user_id, code_hash) VALUES (%s,%s)', (user_id, h))

    def use_step(self, user_id, step):
        """True when the step is after the last one used (then it is the last one, and the enrolment is confirmed)."""
        with self.store.connect() as c:
            return c.execute('''UPDATE edge_bff.mfa_totp SET last_step=%s, confirmed_at=coalesce(confirmed_at, now())
                WHERE user_id=%s AND (last_step IS NULL OR last_step < %s) RETURNING user_id''',
                             (step, user_id, step)).fetchone() is not None

    def use_recovery(self, user_id, code_hash):
        with self.store.connect() as c:
            return c.execute('''UPDATE edge_bff.mfa_recovery_codes SET used_at=now()
                WHERE user_id=%s AND code_hash=%s AND used_at IS NULL RETURNING user_id''',
                             (user_id, code_hash)).fetchone() is not None

    def mfa_passed(self, token_hash_):
        with self.store.connect() as c:
            c.execute('UPDATE edge_bff.sessions SET mfa_passed_at=now() WHERE token_hash=%s', (token_hash_,))


class AuthFlows:
    def __init__(self, settings, store, auth, throttle, sender=None, pwned_fetch=None):
        self.settings, self.auth, self.throttle, self.sender = settings, auth, throttle, sender
        self.store = FlowStore(settings, store, throttle)
        self.outbox = OutboxStore(store)
        self.pwned_fetch = pwned_fetch          # tests replace the range API
        self.clock = time.time                  # tests freeze the TOTP clock

    def wake(self):
        if self.sender is not None:
            self.sender.wake()

    async def breached(self, password):
        return await asyncio.to_thread(passwords.pwned, password, self.pwned_fetch)

    async def new_verifier(self, password):
        if await self.breached(password):
            raise Refusal(400, 'PASSWORD_BREACHED', {'fields': ['password']})
        return await asyncio.to_thread(password_verifier, password)

    def routes(self, app, session_answer):
        settings, auth, store = self.settings, self.auth, self.store

        async def switched_on():
            if not settings.multiuser:
                raise Refusal(404, 'NOT_FOUND')

        def signed_in(p, token, status=200):
            response = JSONResponse(session_answer(p), status_code=status)
            response.set_cookie(COOKIE, token, max_age=settings.session_seconds, httponly=True,
                                secure=settings.secure_cookie, samesite='strict', path='/')
            return response

        def code_refusal(outcome, found):
            if outcome == 'limited':
                return Refusal(429, 'LIMIT_REACHED', {'limit': 'code_tries', 'retry_after_s': found},
                               {'Retry-After': str(found)})
            return Refusal(400, 'CODE_INVALID_OR_EXPIRED', {'fields': ['code']})

        @app.get('/api/v1/auth/config')
        async def config():
            """Public: whether registration and "Forgot password?" are open (the sign-in page reads it)."""
            return {'multiuser': settings.multiuser}

        @app.post('/api/v1/auth/register', status_code=202)
        async def register(request: Request, _on=Depends(switched_on)):
            b = fields_of(await request.body(), ('username', 'first_name', 'last_name', 'email', 'phone', 'password',
                                                 'password_repeat'),
                          ('username', 'first_name', 'last_name', 'email', 'password', 'password_repeat'))
            phone = None
            if (b.get('phone') or '').strip():
                phone = passwords.normal_phone(b['phone'])
                if phone is None:
                    raise invalid({'phone': 'Enter a phone number with its country code, e.g. +62 812 3456 7890 or 0812 3456 7890.'})
            f = {'username': checked_username(b['username']), 'first_name': checked_name(b['first_name'], 'first_name'),
                 'last_name': checked_name(b['last_name'], 'last_name'), 'email': checked_email(b['email']),
                 'phone': phone}
            verifier = await self.new_verifier(checked_passwords(b))
            if await asyncio.to_thread(store.register, f, verifier, client_address(request)):
                self.wake()
            return JSONResponse(ACCEPTED, status_code=202)

        @app.post('/api/v1/auth/register/verify')
        async def register_verify(request: Request, _on=Depends(switched_on)):
            b = fields_of(await request.body(), ('email', 'code', 'username'), ('email', 'code'))
            email = checked_email(b['email'])
            username = checked_username(b['username']) if (b.get('username') or '').strip() else None
            outcome, found = await asyncio.to_thread(store.verify_registration, email, b['code'].strip(), username)
            if outcome == 'taken':
                raise Refusal(409, 'USERNAME_TAKEN', {'fields': ['username']})
            if outcome != 'ok':
                raise code_refusal(outcome, found)
            token = secrets.token_hex(32)
            await asyncio.to_thread(auth.accounts.create_session, token_hash(token), found, settings.session_seconds,
                                    self.throttle.key_hash('signin_ip', client_address(request)))
            await asyncio.to_thread(auth.accounts.signed_in, found['user_id'])
            p = await auth.resolve(token)
            if p is None:
                raise Refusal(401, 'UNAUTHENTICATED')
            return signed_in(p, token)

        @app.post('/api/v1/auth/code/resend', status_code=202)
        async def code_resend(request: Request, _on=Depends(switched_on)):
            b = fields_of(await request.body(), ('email', 'purpose'), ('email', 'purpose'))
            if b['purpose'] not in PURPOSES:
                raise invalid({'purpose': 'purpose is register or reset.'})
            if await asyncio.to_thread(store.resend, checked_email(b['email']), b['purpose'], client_address(request)):
                self.wake()
            return JSONResponse(ACCEPTED, status_code=202)

        @app.post('/api/v1/auth/password/forgot', status_code=202)
        async def password_forgot(request: Request, _on=Depends(switched_on)):
            b = fields_of(await request.body(), ('email',), ('email',))
            if await asyncio.to_thread(store.resend, checked_email(b['email']), 'reset', client_address(request)):
                self.wake()
            return JSONResponse(ACCEPTED, status_code=202)

        @app.post('/api/v1/auth/password/reset')
        async def password_reset(request: Request, _on=Depends(switched_on)):
            b = fields_of(await request.body(), ('email', 'code', 'password', 'password_repeat'),
                          ('email', 'code', 'password', 'password_repeat'))
            email = checked_email(b['email'])
            verifier = await self.new_verifier(checked_passwords(b))
            outcome, found = await asyncio.to_thread(store.reset, email, b['code'].strip(), verifier)
            if outcome != 'ok':
                raise code_refusal(outcome, found)
            self.wake()
            response = JSONResponse({'next': 'sign_in'})
            response.delete_cookie(COOKIE, path='/')
            return response

        @app.post('/api/v1/auth/password/change')
        async def password_change(request: Request, _on=Depends(switched_on), p: Principal = Depends(auth.writer)):
            b = fields_of(await request.body(), ('current_password', 'password', 'password_repeat'),
                          ('current_password', 'password', 'password_repeat'))
            key = f'change:{p.user_id}'
            wait = await asyncio.to_thread(self.throttle.attempt, SIGNIN_LOGIN, key)
            if wait:
                raise Refusal(429, 'SIGN_IN_RATE_LIMIT', {'retry_after_s': wait}, {'Retry-After': str(wait)})
            account = await asyncio.to_thread(store.account, p.user_id)
            if not account or not await asyncio.to_thread(verify_password, b['current_password'], account['verifier']):
                raise Refusal(400, 'CURRENT_PASSWORD_INVALID', {'fields': ['current_password']})
            verifier = await self.new_verifier(checked_passwords(b))
            await asyncio.to_thread(self.throttle.clear, SIGNIN_LOGIN, key)
            await asyncio.to_thread(store.change, p.user_id, verifier, token_hash(p.token), account['email'])
            self.wake()
            return {'status': 'PASSWORD_CHANGED'}

        @app.post('/api/v1/auth/sign-out-all')
        async def sign_out_all(_on=Depends(switched_on), p: Principal = Depends(auth.writer)):
            await asyncio.to_thread(auth.accounts.revoke_all, p.user_id)
            response = JSONResponse({'authenticated': False})
            response.delete_cookie(COOKIE, path='/')
            return response

        @app.post('/api/v1/auth/mfa/enroll')
        async def mfa_enroll(_on=Depends(switched_on), p: Principal = Depends(auth.need(ADMIN_ACCESS, write=True))):
            """otpauth URI and 10 recovery codes, shown once. A confirmed enrolment is replaced only by a session that
            passed MFA (else 403 MFA_REQUIRED: a password alone never resets the second factor)."""
            current = await asyncio.to_thread(store.totp, p.user_id)
            if current and current['confirmed_at'] and not p.mfa_ok:
                raise Refusal(403, 'MFA_REQUIRED')
            nonce = secrets.token_bytes(16)
            codes = [mfa.new_recovery_code() for _ in range(mfa.RECOVERY_CODES)]
            await asyncio.to_thread(store.enroll, p.user_id, nonce,
                                    [mfa.recovery_hash(settings.mfa_key, p.user_id, x) for x in codes])
            secret = mfa.secret_of(settings.mfa_key, p.user_id, nonce)
            return {'otpauth_uri': mfa.otpauth_uri(secret, p.username or str(p.user_id)),
                    'secret': base64.b32encode(secret).decode().rstrip('='), 'recovery_codes': codes}

        @app.post('/api/v1/auth/mfa/verify')
        async def mfa_verify(request: Request, _on=Depends(switched_on), p: Principal = Depends(auth.writer)):
            b = fields_of(await request.body(), ('code', 'recovery_code'), ())
            code, recovery = (b.get('code') or '').strip(), (b.get('recovery_code') or '').strip()
            if bool(code) == bool(recovery):
                raise invalid({'code': 'Send code (6 digits from the authenticator app) or recovery_code, not both.'})
            key = f'mfa:{p.user_id}'
            wait = await asyncio.to_thread(self.throttle.attempt, MFA_USER, key)
            if wait:
                raise Refusal(429, 'LIMIT_REACHED', {'limit': 'mfa_tries', 'retry_after_s': wait}, {'Retry-After': str(wait)})
            row = await asyncio.to_thread(store.totp, p.user_id) if p.user_id is not None else None
            if row is None:
                raise Refusal(400, 'MFA_NOT_ENROLLED')
            if code:
                step = mfa.matching_step(mfa.secret_of(settings.mfa_key, p.user_id, row['nonce']), code,
                                         mfa.step_now(self.clock))
                ok = step is not None and await asyncio.to_thread(store.use_step, p.user_id, step)
            else:
                ok = row['confirmed_at'] is not None and await asyncio.to_thread(
                    store.use_recovery, p.user_id, mfa.recovery_hash(settings.mfa_key, p.user_id, recovery))
            if not ok:
                raise Refusal(400, 'MFA_CODE_INVALID', {'fields': ['code' if code else 'recovery_code']})
            await asyncio.to_thread(self.throttle.clear, MFA_USER, key)
            await asyncio.to_thread(store.mfa_passed, token_hash(p.token))
            return session_answer(await auth.resolve(p.token))

        @app.post('/api/v1/hooks/email/resend')
        async def resend_hook(request: Request, _on=Depends(switched_on)):
            """Resend's bounces and complaints (CONTRACT.md sections 5 and 6): no session; the Svix signature over the
            raw body proves the sender; a repeated svix-id changes nothing."""
            raw = getattr(request, '_body', None) or await request.body()
            if not svix_verify(request.headers, raw, settings.resend_webhook_secret):
                raise Refusal(401, 'HOOK_SIGNATURE_INVALID')
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
