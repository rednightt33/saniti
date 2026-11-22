"""EXEC-MU-ACCOUNTS Phase 4, the admin page (CONTRACT.md 10; EXEC.md option A item 5; the user, 2026-11-22: "1A 2A 3A"
and "1A, 2B, 3A"): its data routes. They exist on the beta only: admin.access is a beta-only capability, so the live site
answers 404 before any session is read. Each is behind auth.admin_page: the admin right, and the authenticator code (on
the beta, whose sessions count as past the second factor, the page's own code step, POST /api/v1/admin/step-up).

  GET  /api/v1/admin/step-up              {needed, enrolled, available}: whether this session must enter the code first
  POST /api/v1/admin/step-up              {code}: the 6-digit code of user #1's authenticator (the live site's; never a
                                          recovery code, which is single-use and kept for the live sign-in): the
                                          session is renewed as one that passed it (the beta; 404 with the switch on)
  GET  /api/v1/admin/overview             counts: accounts by status and plan, sessions, support tickets, emails
  GET  /api/v1/admin/users                the accounts, newest first, each address and phone masked;
                                          ?q= (any part of a username or name, or an address in full: a masked
                                          address is never narrowed letter by letter) ?status= ?plan= ?before= ?limit=
  GET  /api/v1/admin/users/{id}           one account: plan history, overrides, sessions, usage, the audit about it
  POST /api/v1/admin/users/{id}/reveal    {field: email|phone, reason}: the value in full, audited in the same transaction
                                          (an account without one answers null: nothing shown, nothing audited)
  GET  /api/v1/admin/audit                the audit, newest first; ?action= ?actor= ?target= ?since= ?until= ?before=
  GET  /api/v1/admin/audit.csv            the same rows as a spreadsheet file (text_rules.export_cell on every cell), at
                                          most CSV_ROWS: more is refused, naming the dates to narrow (never cut short)
  GET  /api/v1/admin/plans                the plans and what each holds (read-only, the user's 2A: a change is a migration)
  GET  /api/v1/admin/settings             the site's settings that are no secret (SHOWN_SETTINGS)
  GET  /api/v1/admin/support              the support tickets, newest first; ?status=new|done|all ?before= ?limit=
  GET  /api/v1/admin/support/{id}         one ticket in full; its sender's address masked
  GET  /api/v1/admin/support/{id}/images/{n}  one image, as its own type, sandboxed, never cached, never sniffed
  POST /api/v1/admin/support/{id}/status  {status: done|new}: audited; done starts its images' 90 days (the user's 2B)
  POST /api/v1/admin/support/{id}/telegram    its Telegram summary sent again now (one not delivered yet)
  DELETE /api/v1/admin/support/{id}       {reason}: the ticket and its images deleted, audited (the user's 2B)

The audit (edge_bff.admin_audit, append-only) holds ids, keys, kinds and status, never a person's words, name or
address; the reason is what the admin typed. A refusal names the field and the fix (AGENTS.md "Gates and evidence").
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

from . import email_texts, mailer, support as support_module, text_rules
from .errors import Refusal
from .principal import Principal
from .security import csrf_token, token_hash

logger = logging.getLogger('edge_bff.admin')

PAGE = 50
PAGE_MAX = 200
CSV_ROWS = 10000
REASON_CHARS = 1000
STATUSES = ('pending', 'active', 'disabled')
# the settings the admin page shows: none is a secret, an address with a password or a key (a new setting is shown only
# once it is named here; tests/test_admin.py holds that every one exists and none is a repr=False field)
SHOWN_SETTINGS = ('site', 'multiuser', 'prelaunch_enabled', 'guests_enabled', 'environment', 'origin', 'email_mode',
                  'email_from', 'email_enabled', 'housekeeping_enabled', 'session_seconds', 'session_idle_seconds',
                  'support_per_hour', 'support_per_day', 'support_storage_mb', 'admin_origin', 'upgrade_contact',
                  'privacy_url', 'terms_url', 'guest_calls_per_hour', 'commit_sha')
# the image's own type and a policy that runs nothing (main.py keeps a response's own default-src 'none' sandbox policy)
IMAGE_CSP = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
USAGE = (('backtest_jobs', 'edge_bff.backtest_jobs', 'owner_key'), ('screener_items', 'edge_bff.screener_items', 'owner_key'),
         ('watchlist_items', 'edge_bff.watchlist_items', 'owner_key'), ('terminal_layouts', 'edge_bff.terminal_layouts', 'owner_key'),
         ('terminal_drawings', 'edge_bff.terminal_drawings', 'owner_key'))

# the plan an account resolves to now: its live subscription's, else the default plan (accounts.py resolve, the same rule)
PLAN_OF = '''coalesce((SELECT s.plan_key FROM edge_bff.subscriptions s WHERE s.user_id = u.user_id AND s.status = 'active'
                AND s.starts_at <= now() AND (s.expires_at IS NULL OR s.expires_at > now())
                ORDER BY s.starts_at DESC, s.subscription_id DESC LIMIT 1),
             (SELECT plan_key FROM edge_bff.plans WHERE is_default))'''
PLAN_ENDS = '''(SELECT s.expires_at FROM edge_bff.subscriptions s WHERE s.user_id = u.user_id AND s.status = 'active'
                AND s.starts_at <= now() AND (s.expires_at IS NULL OR s.expires_at > now())
                ORDER BY s.starts_at DESC, s.subscription_id DESC LIMIT 1)'''


def invalid(**reasons):
    return Refusal(400, 'INVALID_INPUT', {'fields': list(reasons), 'reasons': reasons})


def masked_phone(phone):
    """+62•••••••890: the country's first digits and the last three."""
    if not phone:
        return None
    return phone[:3] + '•' * max(0, len(phone) - 6) + phone[-3:]


def account_row(r):
    """An account as the admin page lists it: the address and the phone masked (a reveal shows them, audited)."""
    return {'user_id': r['user_id'], 'username': r['username'], 'first_name': r['first_name'], 'last_name': r['last_name'],
            'email': mailer.masked_address(r['email']) if r['email'] else None, 'phone': masked_phone(r['phone_e164']),
            'role': r['role'], 'status': r['status'], 'test_account': r['test_account'], 'plan': r['plan_key'],
            'plan_ends': r['plan_ends'], 'created_at': r['created_at'], 'last_sign_in_at': r['last_sign_in_at']}


def page_limit(value):
    try:
        n = int(value) if value not in (None, '') else PAGE
    except (TypeError, ValueError):
        raise invalid(limit=f'A whole number from 1 to {PAGE_MAX}.') from None
    if not 1 <= n <= PAGE_MAX:
        raise invalid(limit=f'A whole number from 1 to {PAGE_MAX}.')
    return n


def cursor(value, field='before'):
    if value in (None, ''):
        return None
    if not str(value).isdigit() or len(str(value)) > 18:
        raise invalid(**{field: 'The number of the last row shown (from the answer\'s next).'})
    return int(value)


def moment(value, field):
    if value in (None, ''):
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        raise invalid(**{field: 'A date such as 2026-11-22, or a time such as 2026-11-22T08:30:00+07:00.'}) from None


def reason_of(value, required=True):
    """The admin's reason: one line or more, 1..REASON_CHARS characters, no hidden or control character but line breaks."""
    if value is None and not required:
        return None
    text = value.strip() if isinstance(value, str) else ''
    if not text and not required:
        return None
    if not text or len(text) > REASON_CHARS or text_rules.hidden_character(text, allow='\n'):
        raise invalid(reason=f'Write why, in 1 to {REASON_CHARS} characters (it is kept in the audit).')
    return text


def like(q):
    """A search string for ILIKE: its own % and _ taken as they are."""
    return '%' + re.sub(r'([\\%_])', r'\\\1', q) + '%'


def audit(c, actor, action, target=None, before=None, after=None, reason=None):
    c.execute('''INSERT INTO edge_bff.admin_audit(actor_user_id, action, target_user_id, before, after, reason)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)''',
              (actor, action, target, None if before is None else json.dumps(before),
               None if after is None else json.dumps(after), reason))


class AdminStore:
    """The admin page's reads and its support actions, in the shared database (blocking calls, run in a thread)."""

    def __init__(self, store):
        self.store = store

    def overview(self):
        with self.store.connect() as c:
            users = c.execute(f'''SELECT u.status, {PLAN_OF} AS plan_key, u.test_account, count(*) AS n FROM edge_bff.users u
                GROUP BY 1, 2, 3''').fetchall()
            sessions = c.execute('''SELECT count(*) AS n FROM edge_bff.sessions WHERE revoked_at IS NULL
                AND expires_at > now()''').fetchone()['n']
            tickets = c.execute('''SELECT count(*) FILTER (WHERE status = 'new') AS new, count(*) FILTER (WHERE status = 'done')
                AS done, count(*) FILTER (WHERE telegram_sent_at IS NULL) AS unsent FROM edge_bff.support_tickets''').fetchone()
            images = c.execute('SELECT coalesce(sum(bytes), 0) AS b FROM edge_bff.support_attachments').fetchone()['b']
            outbox = c.execute('''SELECT count(*) FILTER (WHERE status IN ('pending', 'sending')) AS waiting,
                count(*) FILTER (WHERE status = 'failed' AND created_at > now() - interval '7 days') AS failed_7d
                FROM edge_bff.email_outbox''').fetchone()
        by_status, by_plan, tests = {}, {}, 0
        for r in users:
            by_status[r['status']] = by_status.get(r['status'], 0) + r['n']
            if r['status'] == 'active':
                by_plan[r['plan_key']] = by_plan.get(r['plan_key'], 0) + r['n']
            tests += r['n'] if r['test_account'] else 0
        return {'accounts': {'by_status': by_status, 'active_by_plan': by_plan, 'test_accounts': tests},
                'sessions_live': sessions, 'support': {**tickets, 'images_bytes': images},
                'emails': dict(outbox)}

    def users(self, q, status, plan, before, limit):
        with self.store.connect() as c:
            rows = c.execute(f'''SELECT * FROM (SELECT u.user_id, u.username, u.first_name, u.last_name, u.email,
                    u.phone_e164, u.role, u.status, u.test_account, u.created_at, u.last_sign_in_at,
                    {PLAN_OF} AS plan_key, {PLAN_ENDS} AS plan_ends FROM edge_bff.users u
                    WHERE (%(before)s::bigint IS NULL OR u.user_id < %(before)s)
                      AND (%(status)s::text IS NULL OR u.status = %(status)s)
                      AND (%(q)s::text IS NULL OR u.username ILIKE %(q)s OR lower(u.email) = lower(%(address)s)
                           OR (coalesce(u.first_name, '') || ' ' || coalesce(u.last_name, '')) ILIKE %(q)s)) x
                WHERE (%(plan)s::text IS NULL OR x.plan_key = %(plan)s)
                ORDER BY x.user_id DESC LIMIT %(limit)s''',
                             {'before': before, 'status': status, 'q': like(q) if q else None, 'address': q,
                              'plan': plan, 'limit': limit + 1}).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        return {'users': [account_row(r) for r in rows], 'next': rows[-1]['user_id'] if more else None}

    def user(self, user_id):
        with self.store.connect() as c:
            r = c.execute(f'''SELECT u.*, {PLAN_OF} AS plan_key, {PLAN_ENDS} AS plan_ends FROM edge_bff.users u
                WHERE u.user_id = %s''', (user_id,)).fetchone()
            if r is None:
                return None
            subs = c.execute('''SELECT subscription_id, plan_key, status, starts_at, expires_at, provider, created_at
                FROM edge_bff.subscriptions WHERE user_id = %s ORDER BY starts_at DESC, subscription_id DESC''',
                             (user_id,)).fetchall()
            overrides = c.execute('''SELECT capability_key, value, reason, expires_at, created_at FROM
                edge_bff.user_capability_overrides WHERE user_id = %s ORDER BY capability_key''', (user_id,)).fetchall()
            sessions = c.execute('''SELECT count(*) FILTER (WHERE revoked_at IS NULL AND expires_at > now()) AS live,
                max(last_seen_at) AS last_seen FROM edge_bff.sessions WHERE user_id = %s''', (user_id,)).fetchone()
            mfa = c.execute('SELECT confirmed_at IS NOT NULL AS confirmed FROM edge_bff.mfa_totp WHERE user_id = %s',
                            (user_id,)).fetchone()
            usage = {name: c.execute(f'SELECT count(*) AS n FROM {table} WHERE {column} = %s',
                                     (r['owner_key'],)).fetchone()['n'] for name, table, column in USAGE}
            usage['support_tickets'] = c.execute('SELECT count(*) AS n FROM edge_bff.support_tickets WHERE user_id = %s',
                                                 (user_id,)).fetchone()['n']
            trail = c.execute('''SELECT a.audit_id, a.at, a.action, a.actor_user_id, x.username AS actor, a.before, a.after,
                a.reason FROM edge_bff.admin_audit a LEFT JOIN edge_bff.users x ON x.user_id = a.actor_user_id
                WHERE a.target_user_id = %s ORDER BY a.audit_id DESC LIMIT 50''', (user_id,)).fetchall()
        return {'account': account_row(r), 'email_verified_at': r['email_verified_at'],
                'mfa': 'confirmed' if mfa and mfa['confirmed'] else 'pending' if mfa else 'none',
                'subscriptions': [dict(x) for x in subs], 'overrides': [dict(x) for x in overrides],
                'sessions': dict(sessions), 'usage': usage, 'audit': [dict(x) for x in trail]}

    def reveal(self, actor, user_id, field, reason):
        """The address or the phone of an account in full, and its audit row, in one transaction: (False, None) when no
        such account, (True, None) when it has none (nothing shown, so nothing audited), else (True, the value)."""
        column = {'email': 'email', 'phone': 'phone_e164'}[field]
        with self.store.connect() as c:
            r = c.execute(f'SELECT {column} AS value FROM edge_bff.users WHERE user_id = %s', (user_id,)).fetchone()
            if r is None:
                return False, None
            if r['value'] is None:
                return True, None
            audit(c, actor, 'account.reveal', user_id, after={'field': field}, reason=reason)
        return True, r['value']

    def audit_rows(self, action, actor, target, since, until, before, limit):
        with self.store.connect() as c:
            rows = c.execute('''SELECT a.audit_id, a.at, a.action, a.actor_user_id, x.username AS actor, a.target_user_id,
                    y.username AS target, a.before, a.after, a.reason
                FROM edge_bff.admin_audit a LEFT JOIN edge_bff.users x ON x.user_id = a.actor_user_id
                LEFT JOIN edge_bff.users y ON y.user_id = a.target_user_id
                WHERE (%(action)s::text IS NULL OR a.action = %(action)s) AND (%(actor)s::bigint IS NULL OR a.actor_user_id = %(actor)s)
                  AND (%(target)s::bigint IS NULL OR a.target_user_id = %(target)s)
                  AND (%(since)s::timestamptz IS NULL OR a.at >= %(since)s) AND (%(until)s::timestamptz IS NULL OR a.at < %(until)s)
                  AND (%(before)s::bigint IS NULL OR a.audit_id < %(before)s)
                ORDER BY a.audit_id DESC LIMIT %(limit)s''',
                             {'action': action, 'actor': actor, 'target': target, 'since': since, 'until': until,
                              'before': before, 'limit': limit + 1}).fetchall()
        more = len(rows) > limit
        rows = [dict(r) for r in rows[:limit]]
        return {'audit': rows, 'next': rows[-1]['audit_id'] if more else None}

    def plans(self):
        with self.store.connect() as c:
            plans = c.execute('SELECT plan_key, display_name, is_default, for_guests FROM edge_bff.plans ORDER BY plan_key').fetchall()
            caps = c.execute('''SELECT capability_key, kind, unit, display_name, means, value_min, value_max, item_pattern
                FROM edge_bff.capabilities ORDER BY capability_key''').fetchall()
            values = c.execute('''SELECT plan_key, capability_key, value, version, updated_at FROM edge_bff.plan_capabilities
                ORDER BY plan_key, capability_key''').fetchall()
        return {'plans': [dict(r) for r in plans], 'capabilities': [dict(r) for r in caps],
                'values': [dict(r) for r in values]}

    def tickets(self, status, before, limit):
        with self.store.connect() as c:
            rows = c.execute('''SELECT t.ticket_id, t.created_at, t.site, t.kind, t.subject, t.images, t.status, t.done_at,
                    t.telegram_sent_at, t.images_purged_at, u.username, t.details->>'plan' AS plan
                FROM edge_bff.support_tickets t JOIN edge_bff.users u USING (user_id)
                WHERE (%(status)s::text IS NULL OR t.status = %(status)s) AND (%(before)s::bigint IS NULL OR t.ticket_id < %(before)s)
                ORDER BY t.ticket_id DESC LIMIT %(limit)s''', {'status': status, 'before': before, 'limit': limit + 1}).fetchall()
        more = len(rows) > limit
        # the issue type in the words the person chose it by (the dialog's and the email's, email_texts.SUPPORT_KINDS)
        rows = [{**r, 'kind_label': email_texts.SUPPORT_KINDS.get(r['kind'], r['kind'])} for r in rows[:limit]]
        return {'tickets': rows, 'next': rows[-1]['ticket_id'] if more else None}

    def ticket(self, ticket_id):
        with self.store.connect() as c:
            t = c.execute('''SELECT t.*, u.username, u.email, x.username AS done_by FROM edge_bff.support_tickets t
                JOIN edge_bff.users u USING (user_id) LEFT JOIN edge_bff.users x ON x.user_id = t.done_by_user_id
                WHERE t.ticket_id = %s''', (ticket_id,)).fetchone()
            if t is None:
                return None
            files = c.execute('''SELECT position, filename, content_type, bytes FROM edge_bff.support_attachments
                WHERE ticket_id = %s ORDER BY position''', (ticket_id,)).fetchall()
        return {'ticket_id': t['ticket_id'], 'created_at': t['created_at'], 'site': t['site'], 'kind': t['kind'],
                'kind_label': email_texts.SUPPORT_KINDS.get(t['kind'], t['kind']), 'subject': t['subject'], 'body': t['body'], 'details': t['details'], 'status': t['status'],
                'done_at': t['done_at'], 'done_by': t['done_by'], 'images': t['images'],
                'images_purged_at': t['images_purged_at'], 'files': [dict(f) for f in files],
                # the day the hourly purge deletes its images (the user's 2B: support.IMAGE_DAYS after done), or None
                'images_due': (t['done_at'] + timedelta(days=support_module.IMAGE_DAYS)
                               if t['done_at'] and t['images'] and t['images_purged_at'] is None else None),
                'telegram_sent_at': t['telegram_sent_at'], 'telegram_attempts': t['telegram_attempts'],
                'sender': {'user_id': t['user_id'], 'username': t['username'],
                           'email': mailer.masked_address(t['email']) if t['email'] else None}}

    def image(self, ticket_id, position):
        with self.store.connect() as c:
            return c.execute('''SELECT filename, content_type, body FROM edge_bff.support_attachments
                WHERE ticket_id = %s AND position = %s''', (ticket_id, position)).fetchone()

    def set_status(self, actor, ticket_id, status, reason):
        """A ticket marked done (its images' 90 days start, the user's 2B) or new again, audited; None when not found."""
        with self.store.connect() as c:
            t = c.execute('SELECT user_id, status FROM edge_bff.support_tickets WHERE ticket_id = %s FOR UPDATE',
                          (ticket_id,)).fetchone()
            if t is None:
                return None
            if t['status'] != status:
                c.execute('''UPDATE edge_bff.support_tickets SET status = %s,
                    done_at = CASE WHEN %s = 'done' THEN now() END, done_by_user_id = CASE WHEN %s = 'done' THEN %s END
                    WHERE ticket_id = %s''', (status, status, status, actor, ticket_id))
                audit(c, actor, 'support.status', t['user_id'], before={'ticket_id': ticket_id, 'status': t['status']},
                      after={'ticket_id': ticket_id, 'status': status}, reason=reason)
            return status

    def delete(self, actor, ticket_id, reason):
        """A ticket and its images deleted by hand (the user's 2B), audited by ids and kinds only; False when not found."""
        with self.store.connect() as c:
            t = c.execute('''DELETE FROM edge_bff.support_tickets WHERE ticket_id = %s
                RETURNING user_id, kind, status, images, images_purged_at IS NOT NULL AS purged''', (ticket_id,)).fetchone()
            if t is None:
                return False
            audit(c, actor, 'support.delete', t['user_id'], before={
                'ticket_id': ticket_id, 'kind': t['kind'], 'status': t['status'], 'images': t['images'],
                'images_purged': t['purged']}, reason=reason)
        return True

    def summary(self, settings, ticket_id):
        """What the Telegram summary of a ticket says (support.telegram_details reads it), or None."""
        with self.store.connect() as c:
            r = c.execute('''SELECT t.ticket_id, t.site, t.kind, t.subject, t.images, t.telegram_sent_at, u.username,
                t.details->>'plan' AS plan FROM edge_bff.support_tickets t JOIN edge_bff.users u USING (user_id)
                WHERE t.ticket_id = %s''', (ticket_id,)).fetchone()
        if r is None:
            return None
        return {'ticket_id': r['ticket_id'], 'site': r['site'], 'kind': r['kind'], 'subject': r['subject'],
                'images': [None] * r['images'], 'sender': {'username': r['username'], 'plan': r['plan']},
                'link': support_module.admin_link(settings, r['ticket_id']), 'sent': r['telegram_sent_at'] is not None}


def csv_of(rows):
    """The audit as a spreadsheet file: every cell through text_rules.export_cell (a leading = + - @ never a formula)."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator='\r\n')
    w.writerow(['audit_id', 'at', 'action', 'actor_user_id', 'actor', 'target_user_id', 'target', 'before', 'after', 'reason'])
    for r in rows:
        w.writerow([text_rules.export_cell(x) for x in (
            r['audit_id'], r['at'].isoformat() if r['at'] else '', r['action'], r['actor_user_id'], r['actor'],
            r['target_user_id'], r['target'], json.dumps(r['before']) if r['before'] is not None else '',
            json.dumps(r['after']) if r['after'] is not None else '', r['reason'])])
    return out.getvalue()


class Admin:
    """The admin page's routes (module docstring)."""

    def __init__(self, settings, store, flows, support, session_cookie):
        self.settings, self.flows, self.support = settings, flows, support
        self.data = AdminStore(store)
        self.store = store
        self.session_cookie = session_cookie

    def routes(self, app, auth):
        settings, data = self.settings, self.data
        reader, writer = auth.admin_page(), auth.admin_page(write=True)

        async def body_of(request):
            try:
                b = json.loads(await request.body() or b'{}')
            except (ValueError, UnicodeDecodeError):
                raise invalid(request='The request could not be read. Reload the page and try again.') from None
            if not isinstance(b, dict):
                raise invalid(request='The request could not be read. Reload the page and try again.')
            return b

        @app.get('/api/v1/admin/step-up')
        async def step_up_state(p: Principal = Depends(auth.admin())):
            enrolled = p.user_id is not None and await asyncio.to_thread(self.flows.store.totp, p.user_id) is not None
            return {'needed': not p.step_up, 'enrolled': enrolled, 'available': bool(settings.mfa_key)}

        @app.post('/api/v1/admin/step-up')
        async def step_up(request: Request, p: Principal = Depends(auth.admin(write=True))):
            if settings.multiuser:
                raise Refusal(404, 'NOT_FOUND')      # with the switch on the sign-in itself asked for the code
            if not settings.mfa_key:
                # the authenticator's secret is derived from EDGE_MFA_KEY, the live site's (config.shared_key_marks); the
                # page's words name no setting (tests/test_contract_requirements.py), the log tells the operator
                logger.warning(json.dumps({'event': 'admin_step_up_unavailable', 'missing': ['EDGE_MFA_KEY']}))
                raise Refusal(503, 'MFA_UNAVAILABLE')
            b = await body_of(request)
            if b.get('recovery_code') not in (None, ''):
                # the user's "1A" names the authenticator's 6-digit code; a recovery code is single-use and shared with
                # the live site, so one spent here would be gone there
                raise invalid(recovery_code='The admin page takes the 6-digit code from your authenticator app only. Keep '
                                            'your recovery codes for signing in on the live site.')
            try:
                await self.flows.check_second_factor(p.user_id, b.get('code'), None)
            except Refusal as refused:
                if refused.code != 'MFA_LOCKED':
                    raise
                # the way still open on the live sign-in (details.use) is no way here: the page says to wait
                raise Refusal(refused.status, refused.code, {**{k: v for k, v in refused.details.items() if k != 'use'},
                                                             'step_up': True}, refused.headers) from None
            token = secrets.token_hex(32)
            if not await asyncio.to_thread(self.store.session_step_up, token_hash(p.token), token_hash(token), p.owner_key):
                raise Refusal(401, 'UNAUTHENTICATED')
            response = JSONResponse({'step_up': True, 'csrf_token': csrf_token(token, settings.session_secret)})
            response.set_cookie(self.session_cookie, token, max_age=settings.session_seconds, httponly=True,
                                secure=settings.secure_cookie, samesite='strict', path='/')
            return response

        @app.get('/api/v1/admin/overview')
        async def overview(p: Principal = Depends(reader)):
            found = await asyncio.to_thread(data.overview)
            return {**found, 'site': settings.site, 'commit': (settings.commit_sha or '')[:12],
                    'support_storage_mb': settings.support_storage_mb}

        @app.get('/api/v1/admin/users')
        async def users(q: str = '', status: str = '', plan: str = '', before: str = '', limit: str = '',
                        p: Principal = Depends(reader)):
            q = q.strip()
            if len(q) > 100 or text_rules.hidden_character(q):
                raise invalid(q='Search by 1 to 100 characters of a username, a name or an address.')
            if status and status not in STATUSES:
                raise invalid(status=f"One of {', '.join(STATUSES)}.")
            if plan and not re.fullmatch(r'[a-z][a-z0-9_]{1,31}', plan):
                raise invalid(plan='A plan key, as GET /api/v1/admin/plans lists them.')
            return await asyncio.to_thread(data.users, q or None, status or None, plan or None, cursor(before),
                                           page_limit(limit))

        @app.get('/api/v1/admin/users/{user_id}')
        async def user(user_id: int, p: Principal = Depends(reader)):
            found = await asyncio.to_thread(data.user, user_id)
            if found is None:
                raise Refusal(404, 'NOT_FOUND')
            return found

        @app.post('/api/v1/admin/users/{user_id}/reveal')
        async def reveal(user_id: int, request: Request, p: Principal = Depends(writer)):
            b = await body_of(request)
            field = b.get('field')
            if field not in ('email', 'phone'):
                raise invalid(field='email or phone.')
            found, value = await asyncio.to_thread(data.reveal, p.user_id, user_id, field, reason_of(b.get('reason')))
            if not found:
                raise Refusal(404, 'NOT_FOUND')
            return {'field': field, 'value': value}

        def audit_filters(action, actor, target, since, until):
            if action and not re.fullmatch(r'[a-z][a-z0-9_.]{0,63}', action):
                raise invalid(action='An action as the audit names it, such as account.reveal.')
            return (action or None, cursor(actor, 'actor'), cursor(target, 'target'), moment(since, 'since'),
                    moment(until, 'until'))

        @app.get('/api/v1/admin/audit')
        async def audit_list(action: str = '', actor: str = '', target: str = '', since: str = '', until: str = '',
                             before: str = '', limit: str = '', p: Principal = Depends(reader)):
            found = await asyncio.to_thread(data.audit_rows, *audit_filters(action, actor, target, since, until),
                                            cursor(before), page_limit(limit))
            return found

        @app.get('/api/v1/admin/audit.csv')
        async def audit_csv(action: str = '', actor: str = '', target: str = '', since: str = '', until: str = '',
                            p: Principal = Depends(reader)):
            found = await asyncio.to_thread(data.audit_rows, *audit_filters(action, actor, target, since, until),
                                            None, CSV_ROWS)
            if found['next'] is not None:
                raise invalid(since=f'More than {CSV_ROWS:,} rows match. Choose a shorter period (since and until) and '
                                    'download again.')
            return Response(csv_of(found['audit']), media_type='text/csv; charset=utf-8',
                            headers={'Content-Disposition': 'attachment; filename="edge-audit.csv"',
                                     'Cache-Control': 'private, no-store'})

        @app.get('/api/v1/admin/plans')
        async def plans(p: Principal = Depends(reader)):
            return await asyncio.to_thread(data.plans)

        @app.get('/api/v1/admin/settings')
        async def shown_settings(p: Principal = Depends(reader)):
            return {'settings': {name: getattr(settings, name) for name in SHOWN_SETTINGS},
                    'telegram_summary': bool(settings.telegram_notify_url and settings.telegram_support_secret)}

        @app.get('/api/v1/admin/support')
        async def tickets(status: str = 'new', before: str = '', limit: str = '', p: Principal = Depends(reader)):
            if status not in ('new', 'done', 'all'):
                raise invalid(status='new, done or all.')
            return await asyncio.to_thread(data.tickets, None if status == 'all' else status, cursor(before),
                                           page_limit(limit))

        @app.get('/api/v1/admin/support/{ticket_id}')
        async def ticket(ticket_id: int, p: Principal = Depends(reader)):
            found = await asyncio.to_thread(data.ticket, ticket_id)
            if found is None:
                raise Refusal(404, 'NOT_FOUND')
            return found

        @app.get('/api/v1/admin/support/{ticket_id}/images/{position}')
        async def image(ticket_id: int, position: int, p: Principal = Depends(reader)):
            found = await asyncio.to_thread(data.image, ticket_id, position)
            if found is None:
                raise Refusal(404, 'NOT_FOUND')
            name = re.sub(r'[^A-Za-z0-9._-]', '_', found['filename'])[:120] or 'image'
            return Response(bytes(found['body']), media_type=found['content_type'], headers={
                'Content-Disposition': f'inline; filename="{name}"', 'Cache-Control': 'private, no-store',
                'Content-Security-Policy': IMAGE_CSP, 'Cross-Origin-Resource-Policy': 'same-origin'})

        @app.post('/api/v1/admin/support/{ticket_id}/status')
        async def ticket_status(ticket_id: int, request: Request, p: Principal = Depends(writer)):
            b = await body_of(request)
            if b.get('status') not in ('done', 'new'):
                raise invalid(status='done or new.')
            done = await asyncio.to_thread(data.set_status, p.user_id, ticket_id, b['status'],
                                           reason_of(b.get('reason'), required=False))
            if done is None:
                raise Refusal(404, 'NOT_FOUND')
            return await asyncio.to_thread(data.ticket, ticket_id)

        @app.post('/api/v1/admin/support/{ticket_id}/telegram')
        async def ticket_telegram(ticket_id: int, p: Principal = Depends(writer)):
            info = await asyncio.to_thread(data.summary, settings, ticket_id)
            if info is None:
                raise Refusal(404, 'NOT_FOUND')
            if not (settings.telegram_notify_url and settings.telegram_support_secret):
                logger.warning(json.dumps({'event': 'support_telegram_unavailable', 'ticket_id': ticket_id,
                                           'missing': [n for n, v in (('TELEGRAM_NOTIFY_URL', settings.telegram_notify_url),
                                                                      ('TELEGRAM_SUPPORT_SECRET',
                                                                       settings.telegram_support_secret)) if not v]}))
                raise Refusal(503, 'TELEGRAM_UNAVAILABLE')
            sent = info['sent'] or await self.support.to_telegram(info)
            return {'sent': bool(sent)}

        @app.delete('/api/v1/admin/support/{ticket_id}')
        async def ticket_delete(ticket_id: int, request: Request, p: Principal = Depends(writer)):
            b = await body_of(request)
            if not await asyncio.to_thread(data.delete, p.user_id, ticket_id, reason_of(b.get('reason'))):
                raise Refusal(404, 'NOT_FOUND')
            return {'deleted': True}
