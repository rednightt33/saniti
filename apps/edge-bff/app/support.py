"""EXEC-MU-ACCOUNTS Phase 4, the contact-support panel (the user, 2026-11-22: "saya minta dibuatkan panel sebelah kiri di
live iconnya kotak surat ... Ada yang submit maka langsung ke admin dan telegram dan ke email pribadi saya"; "hanya yang
login ... lampiran hanya 2A"; "go"; EXEC.md option A item 5; migration 20261122_001).

  POST /api/v1/support    a signed-in account's message (support.send, CSRF): JSON {kind, subject, body, details,
                          images: [{name, type, data}]} -> 201 {ticket_id, created_at}

A visitor holds no support.send (the guest plan), so the rail's mailbox asks it to sign in (the shell's lock box). The
message is kept in edge_bff.support_tickets and its images in edge_bff.support_attachments, the admins' emails are
queued in the same transaction (the outbox the live site's sender sends; Reply goes to the sender), and after the commit
a Telegram summary goes to telegram-monitor (source EDGE_Support, its own secret: the one that also requests
publications never leaves the services that already hold it). The admin page (the beta) reads the tickets.

Guarantees (AGENTS.md "Gates and evidence"; each refusal names the field and the fix):
- only the kinds of the dialog; a subject of 1-120 characters (one line) and a description of 1-5000, without a hidden
  or control character but the description's line breaks and tabs (text_rules.hidden_character); the details the page adds (its keys only, short strings) and edgefinance's own (the browser,
  the build, the site, the plan, the time), never a password, token or cookie;
- at most IMAGES images, each a PNG, JPG or WebP as its own first bytes say (never as the name or the stated type
  says), at most IMAGE_BYTES; the images of every ticket together at most settings.support_storage_mb;
- at most settings.support_per_hour messages per account per hour and settings.support_per_day per day, counted under
  a lock per account so two at once cannot both pass;
- the request is at most REQUEST_BYTES and is read only after its session is found to hold support.send (main.py
  protections: a visitor's large body is never read).
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone

import httpx
from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from . import email_texts, mailer, text_rules, wake
from .errors import Refusal
from .principal import Principal

logger = logging.getLogger('edge_bff.support')

PATH = '/api/v1/support'
CAPABILITY = 'support.send'
KINDS = ('bug', 'question', 'account', 'billing', 'feature', 'data')
SUBJECT_CHARS = 120
BODY_CHARS = 5000
IMAGES = 3
IMAGE_BYTES = 5 * 1024 * 1024
NAME_CHARS = 120
# the images travel base64 inside the JSON (4/3 of their bytes) beside the text: three of the largest and 64 KiB more
REQUEST_BYTES = IMAGES * ((IMAGE_BYTES + 2) // 3 * 4) + 64 * 1024
# the image types, each known by its own first bytes (the stated type and the name only name the file)
SIGNATURES = (('image/png', lambda b: b.startswith(b'\x89PNG\r\n\x1a\n')),
              ('image/jpeg', lambda b: b.startswith(b'\xff\xd8\xff')),
              ('image/webp', lambda b: len(b) >= 12 and b[:4] == b'RIFF' and b[8:12] == b'WEBP'))
# the details the page may add (the shell's SupportDialog): key -> at most this many characters
PAGE_DETAILS = {'page': 200, 'frame': 200, 'viewport': 20, 'timezone': 60, 'language': 35}
USER_AGENT_CHARS = 300
TELEGRAM_SOURCE = 'EDGE_Support'
TELEGRAM_ATTEMPTS = 5

REASONS = {
    'kind': 'Choose an issue type from the list.',
    'subject': f'Write a short title of 1 to {SUBJECT_CHARS} characters.',
    'hidden': ('Remove the hidden or control character (it may come from copying text from another page), then send '
               'again.'),
    'body': f'Describe the issue in 1 to {BODY_CHARS} characters.',
    'images': f'Attach at most {IMAGES} images: PNG, JPG or WebP, each 5 MB or smaller.',
    'image_type': 'Attach PNG, JPG or WebP images only; this file is not one of them.',
    'image_size': 'Each image must be 5 MB or smaller; make the screenshot smaller or crop it.',
    'image_data': 'An image could not be read; attach it again.',
    'details': 'The page details could not be read; reload the page and send again.',
    'request': 'This message could not be read. Reload the page and send it again.',
}


def invalid(**reasons):
    """400 INVALID_INPUT naming each field and how to fix it (the shape of app/auth_flows.py invalid)."""
    return Refusal(400, 'INVALID_INPUT', {'fields': list(reasons), 'reasons': reasons})


def clean_line(value, limit, field):
    """A one-line text: NFC, each run of white space (a line break or a tab included) one space and none at the ends,
    1..limit characters, else the field's refusal; a hidden or control character (text_rules.hidden_character) is
    refused with its own reason."""
    if not isinstance(value, str):
        raise invalid(**{field: REASONS[field]})
    text = ' '.join(unicodedata.normalize('NFC', value).split())
    if not text or len(text) > limit:
        raise invalid(**{field: REASONS[field]})
    if text_rules.hidden_character(text):
        raise invalid(**{field: REASONS['hidden']})
    return text


def clean_body(value):
    """The description: NFC, line breaks as \\n, 1..BODY_CHARS characters, else its refusal; a hidden or control
    character but the line break and the tab is refused with its own reason."""
    if not isinstance(value, str):
        raise invalid(body=REASONS['body'])
    text = unicodedata.normalize('NFC', value).replace('\r\n', '\n').replace('\r', '\n')
    if not text.strip() or len(text) > BODY_CHARS:
        raise invalid(body=REASONS['body'])
    if text_rules.hidden_character(text, allow='\n\t'):
        raise invalid(body=REASONS['hidden'])
    return text


def image_type(data):
    """The image type its first bytes say, or None."""
    return next((kind for kind, matches in SIGNATURES if matches(data)), None)


def safe_name(value, kind):
    """A file name to show and attach: its last part, without control characters or slashes, at most NAME_CHARS, ending
    in the extension of the type its bytes say; 'image.<ext>' when nothing is left."""
    ext = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}[kind]
    name = value if isinstance(value, str) else ''
    name = text_rules.without_hidden(unicodedata.normalize('NFC', name)).replace('\\', '/').rsplit('/', 1)[-1].strip()
    stem = re.sub(r'\.[A-Za-z0-9]{1,5}$', '', name)[:NAME_CHARS - len(ext) - 1].strip(' .') or 'image'
    return f'{stem}.{ext}'


def clean_images(value):
    """[(name, type, bytes)] of the request's images, each checked (module docstring), or the refusal."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > IMAGES:
        raise invalid(images=REASONS['images'])
    out = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get('data'), str):
            raise invalid(images=REASONS['image_data'])
        data = item['data']
        if len(data) > (IMAGE_BYTES + 2) // 3 * 4 + 8:
            raise invalid(images=REASONS['image_size'])
        try:
            raw = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            raise invalid(images=REASONS['image_data']) from None
        if not raw:
            raise invalid(images=REASONS['image_data'])
        if len(raw) > IMAGE_BYTES:
            raise invalid(images=REASONS['image_size'])
        kind = image_type(raw)
        if kind is None:
            raise invalid(images=REASONS['image_type'])
        out.append((safe_name(item.get('name'), kind), kind, raw))
    return out


def clean_details(value, request, settings, p):
    """The ticket's details: the page's own keys (PAGE_DETAILS, short strings; another key or shape is refused) and
    EDGE's: the browser (User-Agent, cut), the build, the site, the plan, the time sent."""
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - set(PAGE_DETAILS):
        raise invalid(details=REASONS['details'])
    out = {}
    for key, limit in PAGE_DETAILS.items():
        v = value.get(key)
        if v is None:
            continue
        if not isinstance(v, str) or len(v) > limit or text_rules.hidden_character(v):
            raise invalid(details=REASONS['details'])
        out[key] = v
    agent = text_rules.without_hidden(request.headers.get('user-agent', ''))[:USER_AGENT_CHARS]
    out.update({'browser': agent, 'build': (settings.commit_sha or '')[:12], 'site': settings.site,
                'plan': p.plan_key or '', 'sent_at': datetime.now(timezone.utc).isoformat(timespec='seconds')})
    return out


class SupportStore:
    """The tickets, their images and the admins' emails, in the shared database (blocking calls, run in a thread)."""

    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    def create(self, p, kind, subject, body, details, images):
        """The ticket's row (and its images and the admins' emails) in one transaction, under a lock per account, or a
        LIMIT_REACHED refusal; returns {ticket_id, created_at, sender, recipients}."""
        s = self.settings
        with self.store.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(%s, %s)', (0x5350, int(p.user_id) & 0x7fffffff))
            counts = c.execute('''SELECT count(*) FILTER (WHERE created_at > now() - interval '1 hour') AS hour,
                    count(*) AS day, min(created_at) FILTER (WHERE created_at > now() - interval '1 hour') AS first_hour,
                    min(created_at) AS first_day
                FROM edge_bff.support_tickets WHERE user_id = %s AND created_at > now() - interval '1 day' ''',
                                  (p.user_id,)).fetchone()
            for window, used, allowed, first, span in (('hour', counts['hour'], s.support_per_hour, counts['first_hour'], 3600),
                                                       ('day', counts['day'], s.support_per_day, counts['first_day'], 86400)):
                if used >= allowed:
                    wait = 60
                    if first is not None:
                        wait = max(1, int(span - (datetime.now(timezone.utc) - first).total_seconds()) + 1)
                    raise Refusal(429, 'LIMIT_REACHED', {'limit': f'support_{window}', 'allowed': allowed,
                                                         'retry_after_s': wait}, {'Retry-After': str(wait)})
            if images:
                held = c.execute('SELECT coalesce(sum(bytes), 0) AS held FROM edge_bff.support_attachments').fetchone()['held']
                if held + sum(len(raw) for _, _, raw in images) > s.support_storage_mb * 1024 * 1024:
                    raise Refusal(503, 'SUPPORT_STORAGE_FULL', {'fields': ['images']})
            row = c.execute('''INSERT INTO edge_bff.support_tickets(user_id, site, kind, subject, body, details, images)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s) RETURNING ticket_id, created_at''',
                            (p.user_id, s.site, kind, subject, body, json.dumps(details), len(images))).fetchone()
            ticket = row['ticket_id']
            for position, (name, kind_of, raw) in enumerate(images, start=1):
                c.execute('''INSERT INTO edge_bff.support_attachments(ticket_id, position, filename, content_type, bytes,
                        sha256, body) VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                          (ticket, position, name, kind_of, len(raw), hashlib.sha256(raw).hexdigest(), raw))
            sender = c.execute('SELECT username, email FROM edge_bff.users WHERE user_id = %s', (p.user_id,)).fetchone()
            recipients = [r['email'] for r in c.execute(
                '''SELECT email FROM edge_bff.users WHERE role = 'admin' AND status = 'active' AND email IS NOT NULL
                   ORDER BY user_id''').fetchall()]
            info = {'ticket_id': ticket, 'created_at': row['created_at'], 'site': s.site, 'kind': kind,
                    'subject': subject, 'body': body, 'details': details,
                    'images': [{'position': i, 'filename': n, 'content_type': t, 'bytes': len(raw)}
                               for i, (n, t, raw) in enumerate(images, start=1)],
                    'sender': {'username': (sender or {}).get('username'), 'email': (sender or {}).get('email'),
                               'plan': p.plan_key}, 'link': admin_link(s, ticket)}
            for to in recipients:
                mail = email_texts.support_email(info)
                mailer.enqueue(c, 'support', to, mail, key=f'support:{ticket}:{hashlib.sha256(to.encode()).hexdigest()[:16]}')
        if not recipients:
            # kept and summarised all the same; the admin page lists it (an admin account with an address is missing)
            logger.warning(json.dumps({'event': 'support_no_recipient', 'ticket_id': ticket}))
        info['emails'] = len(recipients)
        return info

    def delivered(self, ticket_id, ok):
        with self.store.connect() as c:
            if ok:
                c.execute('UPDATE edge_bff.support_tickets SET telegram_sent_at = now(), telegram_attempts = '
                          'telegram_attempts + 1 WHERE ticket_id = %s AND telegram_sent_at IS NULL', (ticket_id,))
            else:
                c.execute('UPDATE edge_bff.support_tickets SET telegram_attempts = telegram_attempts + 1 '
                          'WHERE ticket_id = %s AND telegram_sent_at IS NULL', (ticket_id,))

    def undelivered(self, limit=20):
        """Tickets of the last day whose Telegram summary is not accepted yet and has attempts left (oldest first)."""
        with self.store.connect() as c:
            rows = c.execute('''SELECT t.ticket_id, t.site, t.kind, t.subject, t.images, u.username, t.details->>'plan' AS plan
                FROM edge_bff.support_tickets AS t JOIN edge_bff.users AS u USING (user_id)
                WHERE t.telegram_sent_at IS NULL AND t.telegram_attempts < %s AND t.created_at > now() - interval '1 day'
                ORDER BY t.ticket_id LIMIT %s''', (TELEGRAM_ATTEMPTS, limit)).fetchall()
        return [{'ticket_id': r['ticket_id'], 'site': r['site'], 'kind': r['kind'], 'subject': r['subject'],
                 'images': [None] * r['images'], 'sender': {'username': r['username'], 'plan': r['plan']},
                 'link': admin_link(self.settings, r['ticket_id'])} for r in rows]


def admin_link(settings, ticket_id):
    """The ticket on the admin page (the beta, EDGE_ADMIN_ORIGIN), or '' when that origin is not set."""
    origin = (settings.admin_origin or '').rstrip('/')
    return f'{origin}/admin?ticket={int(ticket_id)}' if origin.startswith('https://') else ''


def telegram_details(info):
    """The summary telegram-monitor accepts for EDGE_Support (its parse_edge_support, the same fixed shape)."""
    sender = info.get('sender') or {}
    return {'ticket_id': int(info['ticket_id']), 'site': info['site'], 'kind': info['kind'],
            'subject': info['subject'][:SUBJECT_CHARS], 'sender': (sender.get('username') or '')[:30],
            'plan': (sender.get('plan') or '')[:32], 'images': len(info.get('images') or []), 'link': info.get('link') or ''}


class Support:
    """The route and the Telegram delivery."""

    def __init__(self, settings, store, transport=None):
        self.settings, self.tickets = settings, SupportStore(store, settings)
        self.transport = transport
        self.http = None
        self.tasks = set()

    async def aclose(self):
        if self.http is not None:
            await self.http.aclose()
            self.http = None

    def client(self):
        if self.http is None:
            self.http = httpx.AsyncClient(timeout=httpx.Timeout(10.0),
                                          transport=self.transport or wake.async_transport('telegram-monitor'))
        return self.http

    async def to_telegram(self, info):
        """The summary to telegram-monitor; True when it sent it (now or before). Never raises."""
        s = self.settings
        if not (s.telegram_notify_url and s.telegram_support_secret):
            return False
        try:
            answer = await self.client().post(s.telegram_notify_url, headers={'X-Notify-Secret': s.telegram_support_secret},
                                              json={'source_table': TELEGRAM_SOURCE, 'execution_id': f"support-{int(info['ticket_id'])}",
                                                    'details': telegram_details(info)})
            # 200: sent now or before (telegram-monitor's log keeps one per ticket); 202 is another attempt still under
            # way there, which may yet fail, so the ticket stays to be retried (its retry then reads 200)
            ok = answer.status_code == 200
        except httpx.HTTPError:
            ok, answer = False, None
        if not ok:
            logger.warning(json.dumps({'event': 'support_telegram_failed', 'ticket_id': info['ticket_id'],
                                       'status': answer.status_code if answer is not None else None}))
        try:
            await asyncio.to_thread(self.tickets.delivered, info['ticket_id'], ok)
        except Exception as e:  # noqa: BLE001 - the class only
            logger.warning(json.dumps({'event': 'support_telegram_mark_failed', 'error': type(e).__name__}))
        return ok

    async def retry_telegram(self):
        """The housekeeping turn: summaries not accepted yet, again (each ticket at most TELEGRAM_ATTEMPTS times)."""
        for info in await asyncio.to_thread(self.tickets.undelivered):
            await self.to_telegram(info)

    def routes(self, app, auth):
        writer = auth.need(CAPABILITY, write=True)

        async def send(request: Request, p: Principal = Depends(writer)):
            if p.user_id is None:
                raise Refusal(403, 'CAPABILITY_REQUIRED', {'capability': CAPABILITY})
            try:
                # the body protections read (main.py, at most REQUEST_BYTES), replayed to the route
                data = json.loads(await request.body() or b'')
            except (ValueError, UnicodeDecodeError):
                raise invalid(request=REASONS['request']) from None
            if not isinstance(data, dict):
                raise invalid(request=REASONS['request'])
            kind = data.get('kind')
            if kind not in KINDS:
                raise invalid(kind=REASONS['kind'])
            subject = clean_line(data.get('subject'), SUBJECT_CHARS, 'subject')
            body = clean_body(data.get('body'))
            images = clean_images(data.get('images'))
            details = clean_details(data.get('details'), request, self.settings, p)
            info = await asyncio.to_thread(self.tickets.create, p, kind, subject, body, details, images)
            task = asyncio.create_task(self.to_telegram(info))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            logger.info(json.dumps({'event': 'support_ticket', 'ticket_id': info['ticket_id'], 'kind': kind,
                                    'images': len(images)}))
            return JSONResponse(status_code=201, content={'ticket_id': info['ticket_id'],
                                                         'created_at': info['created_at'].isoformat()})

        app.post(PATH, name='support_send')(send)
