"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md section 5): the email outbox, its sender loop and the Resend
webhook.

- `enqueue(c, ...)` writes an email into edge_bff.email_outbox on the caller's connection, so a code and its email are
  one transaction. A code email carries expires_at = the code's expiry and is never sent after it.
- `EmailSender.run` is its own asyncio task beside the backtest loop (EDGE_EMAIL_ENABLED, with the worker), never
  behind an AI run: it claims one row at a time with FOR UPDATE SKIP LOCKED and a lease, so several instances never send
  one row twice, and is woken by `wake()` after an insert (else it looks every POLL_SECONDS).
  - EDGE_EMAIL_MODE=log (default): the email is written to the log, the code masked unless EDGE_ENVIRONMENT=local, and
    the row is marked sent with its payload kept (so a dev tester reads the code from the outbox row);
  - EDGE_EMAIL_MODE=resend: POST https://api.resend.com/emails with Idempotency-Key = the row's key; the payload is
    nulled once sent. A failure is retried after 5 s, 30 s and 2 min, then the row is failed.
  - An address in edge_bff.email_suppression is never sent to (status suppressed).
- The webhook POST /api/v1/hooks/email/resend proves itself by its Svix signature (svix-id, svix-timestamp within
  5 minutes, svix-signature v1 = base64 HMAC-SHA256 over "id.timestamp.body" with the base64 secret after "whsec_");
  each svix-id is applied once (edge_bff.email_hook_events); a bounce or complaint adds the address to the suppression
  list.
"""
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import secrets
import time

import httpx
from psycopg.types.json import Jsonb

from . import logs
from .security import same_ascii

logger = logging.getLogger('edge_bff.email')
if not logger.hasHandlers():
    _handler = logs.handler()                # Railway's level on each JSON line (app/logs.py, live checker F3)
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

RESEND_URL = 'https://api.resend.com/emails'
BACKOFF_SECONDS = (5, 30, 120)          # after the 1st, 2nd and 3rd failed try; the 4th failure is final
LEASE_SECONDS = 60
POLL_SECONDS = 5.0
SEND_TIMEOUT = 15.0
ATTACHMENT_TIMEOUT = 60.0                 # an email with images (up to about 20 MB as base64)
HOOK_TOLERANCE_SECONDS = 300
SUPPRESS = {'email.bounced': 'bounce', 'email.complained': 'complaint'}


def enqueue(c, purpose, to_email, mail, expires_at=None, key=None):
    """One outbox row on the caller's connection (its transaction); the row's id, or None for a repeated key."""
    row = c.execute('''INSERT INTO edge_bff.email_outbox(idempotency_key, purpose, to_email, payload, expires_at)
        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (idempotency_key) DO NOTHING RETURNING outbox_id''',
                    (key or f'{purpose}:{secrets.token_hex(16)}', purpose, to_email, Jsonb(mail), expires_at)).fetchone()
    return row['outbox_id'] if row else None


def purge_outbox(c, limit=None):
    """ERRORS R2-24 and the retention decided 2026-11-19 ("a", 30 days; migration 20261119_012): the sent, failed,
    expired or suppressed rows made more than 30 days ago (every address, an account's too), and those older than 24 h
    of addresses with no row in edge_bff.users (a registration never verified, purged after 24 h as CONTRACT 4 says, or
    an address never registered); never a row still pending or sending; at most limit of them (None: the function's own
    cap, 10 000), through
    edge_bff.purge_email_outbox(integer) (edge_bff_runtime holds no DELETE on the outbox). Returns how many were deleted.
    Called from Store.purge, the hourly housekeeping (worker.Housekeeping; store.PURGES 'outbox')."""
    return c.execute('SELECT edge_bff.purge_email_outbox(%s) AS n', (limit,)).fetchone()['n']


def purge_hook_events(c, limit=None):
    """The retention decided 2026-11-19 ("a", 30 days; migration 20261119_012): the webhook deliveries received more
    than 30 days ago, at most limit of them (None: the function's own cap, 10 000), through
    edge_bff.purge_email_hook_events(integer) (edge_bff_runtime holds no DELETE on edge_bff.email_hook_events). A
    delivery repeated after that is past Svix's retries and its signature's 5-minute tolerance (HOOK_TOLERANCE_SECONDS),
    so the svix-id it was kept for is no longer needed. Called from Store.purge (store.PURGES 'hook_events')."""
    return c.execute('SELECT edge_bff.purge_email_hook_events(%s) AS n', (limit,)).fetchone()['n']


def masked_address(email):
    local, _, domain = email.partition('@')
    return (local[:1] + '***@' + domain) if domain else '***'


def masked(text, mask):
    for secret in mask or ():
        text = text.replace(secret, '•' * len(secret))
    return text


class OutboxStore:
    def __init__(self, store):
        self.store = store

    def claim(self):
        """The next row to send under a new lease (its attempts raised by one), or None. Rows past expires_at become
        expired and rows to a suppressed address become suppressed on the way, both with their payload nulled."""
        with self.store.connect() as c:
            c.execute('''UPDATE edge_bff.email_outbox SET status='expired', payload=NULL, lease_token=NULL,
                    lease_expires_at=NULL
                WHERE expires_at <= now() AND (status='pending' OR (status='sending' AND lease_expires_at < now()))''')
            c.execute('''UPDATE edge_bff.email_outbox o SET status='suppressed', payload=NULL, lease_token=NULL,
                    lease_expires_at=NULL
                WHERE (status='pending' OR (status='sending' AND lease_expires_at < now()))
                  AND EXISTS (SELECT 1 FROM edge_bff.email_suppression s WHERE s.email = o.to_email)''')
            row = c.execute('''SELECT outbox_id FROM edge_bff.email_outbox
                WHERE (status='pending' AND next_at <= now()) OR (status='sending' AND lease_expires_at < now())
                ORDER BY next_at, outbox_id FOR UPDATE SKIP LOCKED LIMIT 1''').fetchone()
            if row is None:
                return None
            return c.execute('''UPDATE edge_bff.email_outbox SET status='sending', lease_token=%s,
                    lease_expires_at=now() + make_interval(secs => %s), attempts=attempts+1
                WHERE outbox_id=%s RETURNING *''', (secrets.token_hex(16), LEASE_SECONDS, row['outbox_id'])).fetchone()

    def sent(self, row, provider_id, keep_payload):
        with self.store.connect() as c:
            return c.execute('''UPDATE edge_bff.email_outbox SET status='sent', sent_at=now(), provider_id=%s,
                    payload=CASE WHEN %s THEN payload END, lease_token=NULL, lease_expires_at=NULL
                WHERE outbox_id=%s AND lease_token=%s''', (provider_id, keep_payload, row['outbox_id'],
                                                          row['lease_token'])).rowcount

    def failed(self, row):
        """Back to pending after BACKOFF_SECONDS[attempts-1], or failed (payload nulled) after the last try."""
        final = row['attempts'] > len(BACKOFF_SECONDS)
        delay = 0 if final else BACKOFF_SECONDS[row['attempts'] - 1]
        with self.store.connect() as c:
            return c.execute('''UPDATE edge_bff.email_outbox SET status=CASE WHEN %s THEN 'failed' ELSE 'pending' END,
                    payload=CASE WHEN %s THEN NULL ELSE payload END, next_at=now() + make_interval(secs => %s),
                    lease_token=NULL, lease_expires_at=NULL
                WHERE outbox_id=%s AND lease_token=%s''', (final, final, delay, row['outbox_id'],
                                                          row['lease_token'])).rowcount

    def expired(self, row):
        with self.store.connect() as c:
            c.execute('''UPDATE edge_bff.email_outbox SET status='expired', payload=NULL, lease_token=NULL,
                lease_expires_at=NULL WHERE outbox_id=%s AND lease_token=%s''', (row['outbox_id'], row['lease_token']))

    def ticket_exists(self, ticket_id):
        """Phase 4 (the checker's support-2): whether the support ticket an email is about still exists."""
        with self.store.connect() as c:
            return c.execute('SELECT 1 FROM edge_bff.support_tickets WHERE ticket_id = %s', (int(ticket_id),)).fetchone() is not None

    def attachments(self, refs):
        """Phase 4, the contact-support panel: the images a support email names ([{ticket_id, position, filename}]) as
        Resend's attachments ({filename, content: base64}), read when the email is sent; None when one is gone (its ticket
        or its account was deleted since: the email is then not sent)."""
        out = []
        with self.store.connect() as c:
            for ref in refs:
                row = c.execute('SELECT filename, body FROM edge_bff.support_attachments WHERE ticket_id=%s AND position=%s',
                                (int(ref['ticket_id']), int(ref['position']))).fetchone()
                if row is None:
                    return None
                out.append({'filename': row['filename'], 'content': base64.b64encode(bytes(row['body'])).decode('ascii')})
        return out

    def hook_event(self, svix_id, event_type, recipients):
        """Apply one webhook delivery once: False when its svix-id was seen before (nothing changes)."""
        with self.store.connect() as c:
            if not c.execute('''INSERT INTO edge_bff.email_hook_events(svix_id, event_type) VALUES (%s,%s)
                    ON CONFLICT DO NOTHING RETURNING svix_id''', (svix_id, (event_type or '')[:100])).fetchone():
                return False
            reason = SUPPRESS.get(event_type)
            for email in recipients if reason else ():
                c.execute('''INSERT INTO edge_bff.email_suppression(email, reason) VALUES (%s,%s)
                    ON CONFLICT (email) DO UPDATE SET reason=EXCLUDED.reason, at=now()''', (email, reason))
            return True


class EmailSender:
    def __init__(self, settings, store, transport=None, clock=time.monotonic):
        self.settings, self.outbox = settings, OutboxStore(store)
        self.transport, self.clock = transport, clock
        self.stopped, self.event, self.loop = False, None, None   # the event is made in the loop that runs the sender
        self.client = None

    def wake(self):
        """Called from a route after its insert committed (any thread): the loop looks at once."""
        if self.event is not None and self.loop is not None:
            self.loop.call_soon_threadsafe(self.event.set)

    def stop(self):
        self.stopped = True
        self.wake()

    async def aclose(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def run(self):
        self.stopped, self.event, self.loop = False, asyncio.Event(), asyncio.get_running_loop()
        while not self.stopped:
            try:
                busy = await self.step()
            except Exception as e:                      # noqa: BLE001 - logged by class only (no secret in it)
                logger.warning(json.dumps({'event': 'email_loop_failed', 'error': type(e).__name__}))
                busy = False
            if not busy and not self.stopped:
                try:
                    await asyncio.wait_for(self.event.wait(), timeout=POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
                self.event.clear()

    async def step(self):
        """Send one row; False when there was none."""
        row = await asyncio.to_thread(self.outbox.claim)
        if row is None:
            return False
        await self.deliver(row)
        return True

    async def deliver(self, row):
        if row['expires_at'] is not None and row['expires_at'] <= datetime.now(timezone.utc):
            await asyncio.to_thread(self.outbox.expired, row)
            return
        mail = row['payload'] or {}
        # an email about a support ticket goes only while its ticket exists, with or without images (the checker's
        # support-2: the check rode on the images alone, so a ticket deleted by hand was still emailed in full)
        if mail.get('ticket_id') is not None and not await asyncio.to_thread(self.outbox.ticket_exists, mail['ticket_id']):
            await asyncio.to_thread(self.outbox.expired, row)
            logger.info(json.dumps({'event': 'email_dropped', 'outbox_id': row['outbox_id'], 'purpose': row['purpose'],
                                    'why': 'ticket_gone'}))
            return
        if self.settings.email_mode != 'resend' and mail.get('private'):
            # Phase 4 (the contact-support panel): the sender's own words never reach the log, the address masked
            logger.info(json.dumps({'event': 'email_logged', 'outbox_id': row['outbox_id'], 'purpose': row['purpose'],
                                    'to': masked_address(row['to_email']), 'private': True}))
            await asyncio.to_thread(self.outbox.sent, row, 'log', False)
            return
        if self.settings.email_mode != 'resend':
            local = self.settings.environment == 'local'
            logger.info(json.dumps({'event': 'email_logged', 'outbox_id': row['outbox_id'], 'purpose': row['purpose'],
                                    'to': row['to_email'] if local else masked_address(row['to_email']),
                                    'subject': mail.get('subject') if local else masked(mail.get('subject', ''), mail.get('mask')),
                                    'text': mail.get('text') if local else masked(mail.get('text', ''), mail.get('mask'))},
                                   ensure_ascii=False))
            await asyncio.to_thread(self.outbox.sent, row, 'log', True)
            return
        body = {'from': self.settings.email_from, 'to': [row['to_email']], 'subject': mail.get('subject', ''),
                'text': mail.get('text', ''), 'html': mail.get('html', '')}
        if mail.get('reply_to'):
            body['reply_to'] = mail['reply_to']
        if mail.get('attachments'):
            files = await asyncio.to_thread(self.outbox.attachments, mail['attachments'])
            if files is None:
                await asyncio.to_thread(self.outbox.expired, row)
                logger.info(json.dumps({'event': 'email_dropped', 'outbox_id': row['outbox_id'], 'purpose': row['purpose'],
                                        'why': 'attachment_gone'}))
                return
            body['attachments'] = files
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=SEND_TIMEOUT, transport=self.transport)
        try:
            answer = await self.client.post(RESEND_URL, headers={
                'Authorization': f'Bearer {self.settings.resend_api_key}', 'Idempotency-Key': row['idempotency_key']},
                json=body, timeout=ATTACHMENT_TIMEOUT if 'attachments' in body else SEND_TIMEOUT)
            ok = 200 <= answer.status_code < 300
            provider = (answer.json() or {}).get('id') if ok else None
        except (httpx.HTTPError, ValueError):
            ok, provider, answer = False, None, None
        if ok:
            await asyncio.to_thread(self.outbox.sent, row, str(provider or '')[:200] or None, False)
            logger.info(json.dumps({'event': 'email_sent', 'outbox_id': row['outbox_id'], 'purpose': row['purpose']}))
        else:
            await asyncio.to_thread(self.outbox.failed, row)
            logger.warning(json.dumps({'event': 'email_send_failed', 'outbox_id': row['outbox_id'], 'attempt': row['attempts'],
                                       'status': answer.status_code if answer is not None else None}))


def svix_verify(headers, raw, secret, now=None):
    """True when the Svix headers sign this body with the secret (whsec_<base64>) and the timestamp is within 5 min."""
    if not secret or not secret.startswith('whsec_'):
        return False
    msg_id, stamp, signatures = (headers.get('svix-id') or ''), (headers.get('svix-timestamp') or ''), \
        (headers.get('svix-signature') or '')
    if not msg_id or not signatures or not all(x.isascii() for x in (msg_id, stamp, signatures)) or not stamp.isdigit():
        return False
    if abs((now if now is not None else time.time()) - int(stamp)) > HOOK_TOLERANCE_SECONDS:
        return False
    try:
        key = base64.b64decode(secret[len('whsec_'):])
    except ValueError:
        return False
    expected = base64.b64encode(hmac.new(key, f'{msg_id}.{stamp}.'.encode() + (raw or b''), hashlib.sha256).digest()).decode()
    return any(version == 'v1' and same_ascii(sig, expected)
               for version, _, sig in (part.partition(',') for part in signatures.split()))
