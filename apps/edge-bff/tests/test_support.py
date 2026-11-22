"""Phase 4, the contact-support panel (the user, 2026-11-22: "saya minta dibuatkan panel sebelah kiri di live iconnya
kotak surat ... Ada yang submit maka langsung ke admin dan telegram dan ke email pribadi saya"; "hanya yang login ...
lampiran hanya 2A"; "go"; app/support.py, migration 20261122_001).

What a message keeps and where it goes: the ticket and its images in edge_bff, one email per active admin with an
address (Reply goes to the sender, the images attached when it is sent), a Telegram summary through telegram-monitor
(source EDGE_Support, its own secret). What is refused, and when: a visitor, a pending second factor, an account without
support.send, a request that states a larger size, all before its body is read (one of no stated size is read up to the
cap, after the same checks); each field with its reason;
the account's messages per hour and per day; the images of every ticket together."""
import asyncio
import base64
import dataclasses
import hashlib
import json
import logging
import sys
import threading
import time

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import support as support_module
from app.config import Settings
from app.errors import Refusal
from app.mailer import EmailSender
from app.main import create_app
from app.support import IMAGE_BYTES, PATH, REASONS, REQUEST_BYTES
from conftest import FakeOrc
from test_edge import ORIGIN, login
from test_principal import make_user, sign_in

PNG = b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 4
JPEG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00' + bytes(200)
WEBP = b'RIFF' + (112).to_bytes(4, 'little') + b'WEBPVP8 ' + bytes(100)
GIF = b'GIF89a' + bytes(100)
NOTIFY = 'http://telegram-monitor.invalid/notify'
SECRET = 's' * 40
ADMIN = 'https://admin.example.test'
DETAILS = {'page': '/terminal', 'frame': '/terminal-app/', 'viewport': '1440x900', 'timezone': 'Asia/Jakarta',
           'language': 'en-US'}


def db(store, sql, *args):
    with store.connect() as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


def b64(raw):
    return base64.b64encode(raw).decode('ascii')


def image(raw, name='screen.png', kind='image/png'):
    return {'name': name, 'type': kind, 'data': b64(raw)}


def message(**change):
    return {'kind': 'bug', 'subject': 'The chart does not load', 'body': 'I open BBCA.\nThe chart stays empty.',
            'details': dict(DETAILS), 'images': [], **change}


def error_of(r):
    return r.json()['error']


def wait_for(check, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(0.02)
    return check()


@pytest.fixture
def on(settings):
    return dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
                               telegram_notify_url=NOTIFY, telegram_support_secret=SECRET, admin_origin=ADMIN)


class Telegram:
    """telegram-monitor's /notify as a fake: each summary it is sent, answered with `status`."""

    def __init__(self, status=200):
        self.status, self.seen = status, []

    def __call__(self, request):
        self.seen.append({'url': str(request.url), 'secret': request.headers.get('x-notify-secret'),
                          'body': json.loads(request.content)})
        return httpx.Response(self.status, json={'ok': self.status == 200})

    def transport(self):
        return httpx.MockTransport(self)


def app_of(settings, store, telegram=None):
    app = create_app(settings, store, FakeOrc())
    app.state.support.transport = (telegram or Telegram()).transport()
    return app


class Reads:
    """The app with every read of a request's body counted (an ASGI receive of http.request): a refusal made before
    the body is read leaves the count where it was."""

    def __init__(self, app):
        self.app, self.reads = app, 0
        self.state = app.state

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def counted():
            message = await receive()
            if message['type'] == 'http.request':
                self.reads += 1
            return message
        return await self.app(scope, counted, send)


def admin_user(store, name, password, **kw):
    """An account that holds the admin right by its grant (the plan holding '*', make_user's default for the role), as
    the admin page counts it; the role alone grants nothing (the Phase 4 checker's support-1)."""
    return make_user(store, name, password, role='admin', **kw)


# ---- a message, its images, its email and its summary --------------------------------------------------------------

def test_an_account_sends_a_message_kept_with_its_images_emailed_to_the_admins_and_summarised(on, store):
    telegram = Telegram()
    with TestClient(app_of(on, store, telegram)) as c:
        admin_user(store, 'boss', 'boss-password', email='boss@example.com')
        admin_user(store, 'gone', 'gone-password', status='disabled', email='gone@example.com')
        make_user(store, 'rolly', 'rolly-password', role='admin', everything=False, email='rolly@example.com')  # role only
        granted = make_user(store, 'grace', 'grace-password', email='grace@example.com')    # a plain account given it
        db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'admin.access', 'true'::jsonb, 'an admin by override')''', granted['user_id'])
        make_user(store, 'carol', 'carol-password', email='carol@example.com')          # not an admin: no copy
        alice = make_user(store, 'alice', 'alice-password', email='alice@example.com')
        h = sign_in(c, 'alice', 'alice-password')
        r = c.post(PATH, headers={**h, 'User-Agent': 'Mozilla/5.0 (test)'}, json=message(
            subject='  The chart does not load  ', body='I open BBCA <img src=x onerror=alert(1)>.\r\nThe chart stays empty.',
            images=[image(PNG, 'C:\\Users\\a\\screen.PNG'), image(JPEG, 'shot.png'), {'data': b64(WEBP)}]))
        assert r.status_code == 201, r.text
        ticket = r.json()['ticket_id']
        assert set(r.json()) == {'ticket_id', 'created_at'}
        row = db(store, 'SELECT * FROM edge_bff.support_tickets')[0]
        assert (row['ticket_id'], row['user_id'], row['site'], row['kind'], row['subject'], row['images'], row['status']) == (
            ticket, alice['user_id'], 'beta', 'bug', 'The chart does not load', 3, 'new')
        assert row['body'] == 'I open BBCA <img src=x onerror=alert(1)>.\nThe chart stays empty.'
        d = row['details']
        assert {k: d[k] for k in DETAILS} == DETAILS
        assert (d['browser'], d['site'], d['plan']) == ('Mozilla/5.0 (test)', 'beta', 'free') and d['sent_at']
        assert set(d) == set(DETAILS) | {'browser', 'build', 'site', 'plan', 'sent_at'}
        # the type each file's first bytes say, its name ending in that type's extension (never the name's or the type's)
        files = db(store, 'SELECT position, filename, content_type, bytes, sha256, body FROM edge_bff.support_attachments '
                          'ORDER BY position')
        assert [(f['position'], f['filename'], f['content_type'], f['bytes']) for f in files] == [
            (1, 'screen.png', 'image/png', len(PNG)), (2, 'shot.jpg', 'image/jpeg', len(JPEG)), (3, 'image.webp', 'image/webp', len(WEBP))]
        assert [bytes(f['body']) for f in files] == [PNG, JPEG, WEBP]
        assert [f['sha256'] for f in files] == [hashlib.sha256(x).hexdigest() for x in (PNG, JPEG, WEBP)]
        # one email per active admin with an address, queued with the ticket; Reply goes to the sender
        mails = db(store, 'SELECT to_email, purpose, status, payload FROM edge_bff.email_outbox ORDER BY outbox_id')
        assert [(m['to_email'], m['purpose'], m['status']) for m in mails] == [('boss@example.com', 'support', 'pending'),
                                                                            ('grace@example.com', 'support', 'pending')]
        mail = mails[0]['payload']
        assert mail['subject'] == f'EDGE support #{ticket}: Bug / Something not working: The chart does not load'
        assert (mail['reply_to'], mail['private']) == ('alice@example.com', True)
        assert mail['attachments'] == [{'ticket_id': ticket, 'position': 1, 'filename': 'screen.png'},
                                       {'ticket_id': ticket, 'position': 2, 'filename': 'shot.jpg'},
                                       {'ticket_id': ticket, 'position': 3, 'filename': 'image.webp'}]
        assert 'I open BBCA <img src=x onerror=alert(1)>.\nThe chart stays empty.' in mail['text']
        assert 'timezone: Asia/Jakarta' in mail['text'] and 'Images: 3 attached.' in mail['text']
        assert f'{ADMIN}/admin?ticket={ticket}' in mail['text'] and 'from alice (free)' in mail['text']
        assert '<img' not in mail['html'] and '&lt;img src=x onerror=alert(1)&gt;' in mail['html']
        # the summary to telegram-monitor after the commit: its own source and secret, never the text or an address
        sent = wait_for(lambda: db(store, 'SELECT telegram_sent_at FROM edge_bff.support_tickets')[0]['telegram_sent_at'])
        assert sent and db(store, 'SELECT telegram_attempts FROM edge_bff.support_tickets')[0]['telegram_attempts'] == 1
        assert telegram.seen == [{'url': NOTIFY, 'secret': SECRET, 'body': {
            'source_table': 'EDGE_Support', 'execution_id': f'support-{ticket}',
            'details': {'ticket_id': ticket, 'site': 'beta', 'kind': 'bug', 'subject': 'The chart does not load',
                        'sender': 'alice', 'plan': 'free', 'images': 3, 'link': f'{ADMIN}/admin?ticket={ticket}'}}}]


def test_the_largest_message_fits_the_request_cap(on, store):
    """Three images of IMAGE_BYTES each and the longest texts: the request cap (REQUEST_BYTES) lets the largest legal
    message through, so a refusal for size names a message the dialog would refuse too."""
    big = b'\x89PNG\r\n\x1a\n' + bytes(IMAGE_BYTES - 8)
    with TestClient(app_of(on, store)) as c:
        make_user(store, 'alice', 'alice-password')
        h = sign_in(c, 'alice', 'alice-password')
        body = json.dumps(message(subject='s' * 120, body='b' * 5000, images=[image(big, 'x' * 300 + '.png')] * 3,
                                  details={k: 'd' * n for k, n in support_module.PAGE_DETAILS.items()})).encode()
        assert len(body) <= REQUEST_BYTES
        r = c.post(PATH, headers={**h, 'Content-Type': 'application/json'}, content=body)
        assert r.status_code == 201, r.text
        files = db(store, 'SELECT bytes, filename FROM edge_bff.support_attachments ORDER BY position')
        assert [f['bytes'] for f in files] == [IMAGE_BYTES] * 3 and all(len(f['filename']) == 120 for f in files)


# ---- refused before the body is read --------------------------------------------------------------------------------

def test_a_visitor_a_pending_second_factor_and_an_account_without_the_right_are_refused_before_the_body_is_read(on, store):
    app = Reads(app_of(on, store))
    with TestClient(app) as c:
        admin_user(store, 'boss', 'boss-password', email='boss@example.com')
        alice = make_user(store, 'alice', 'alice-password')

        def refused(status, code, headers, **request):
            before = app.reads
            r = c.post(PATH, headers=headers, **request)
            assert (r.status_code, error_of(r)['code']) == (status, code), r.text
            assert app.reads == before, f'{code}: the body was read'
            return r
        refused(401, 'UNAUTHENTICATED', ORIGIN, json=message())                               # a visitor
        refused(401, 'UNAUTHENTICATED', ORIGIN, content=iter([b'{', b'}']))                   # one of no stated size
        c.cookies.set('edge_session', 'x' * 43)
        refused(401, 'UNAUTHENTICATED', ORIGIN, json=message())                               # no such session
        c.cookies.clear()
        refused(403, 'ORIGIN_REJECTED', {}, json=message())
        h = sign_in(c, 'alice', 'alice-password')
        r = refused(413, 'REQUEST_TOO_LARGE', {**h, 'Content-Length': str(REQUEST_BYTES + 1)}, content=b'{}')
        assert error_of(r)['details'] == {'limit': 'support_request', 'allowed': REQUEST_BYTES}
        refused(413, 'REQUEST_TOO_LARGE', {**h, 'Content-Length': 'many'}, content=b'{}')       # a size that is no number
        # no stated size (a proxy may forward a body chunked): read only after the session check, up to REQUEST_BYTES
        before = app.reads
        r = c.post(PATH, headers={**h, 'Content-Type': 'application/json'}, content=iter([json.dumps(message()).encode()]))
        assert r.status_code == 201 and app.reads > before, r.text
        db(store, "INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason) "
                  "VALUES (%s, 'support.send', 'false'::jsonb, 'test')", alice['user_id'])
        r = refused(403, 'CAPABILITY_REQUIRED', h, json=message())
        assert error_of(r)['details']['capability'] == 'support.send' and 'Contact support' in error_of(r)['message']
        db(store, 'DELETE FROM edge_bff.user_capability_overrides')
        before = app.reads
        assert c.post(PATH, headers=h, json=message()).status_code == 201 and app.reads > before   # the same request, allowed
        # a CSRF token that does not match: read (the session may send), then refused by the route's own check
        r = c.post(PATH, headers={**h, 'X-CSRF-Token': 'wrong'}, json=message())
        assert (r.status_code, error_of(r)['code']) == (403, 'CSRF_INVALID')
        h = sign_in(c, 'boss', 'boss-password')                                                # the second factor waits
        r = refused(403, 'MFA_REQUIRED', h, json=message())
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.support_tickets')[0]['n'] == 2


def test_an_account_past_its_messages_or_its_uploads_is_refused_before_the_body_is_read(on, store):
    """The Phase 4 checker's support-3: the work one account causes is bounded before the body is read: its 5 messages
    an hour (and 20 a day) and 30 uploads an hour, refused ones counted too (throttle.SUPPORT_UPLOAD)."""
    app = Reads(app_of(dataclasses.replace(on, support_per_hour=2), store))
    with TestClient(app) as c:
        make_user(store, 'alice', 'alice-password')
        h = sign_in(c, 'alice', 'alice-password')
        for _ in range(2):
            assert c.post(PATH, headers=h, json=message()).status_code == 201
        before = app.reads
        r = c.post(PATH, headers=h, json=message(images=[image(PNG)]))
        assert (r.status_code, error_of(r)['details']['limit'], app.reads) == (429, 'support_hour', before), r.text
        assert r.headers['Retry-After'] == str(error_of(r)['details']['retry_after_s'])
    db(store, 'DELETE FROM edge_bff.support_tickets')
    db(store, 'DELETE FROM edge_bff.auth_throttle')
    app = Reads(app_of(on, store))
    with TestClient(app) as c:
        h = sign_in(c, 'alice', 'alice-password')
        for _ in range(30):                                       # refused uploads (no valid kind) count as well
            assert c.post(PATH, headers=h, json=message(kind='nonsense')).status_code == 400
        before = app.reads
        r = c.post(PATH, headers=h, json=message())
        assert (r.status_code, error_of(r)['details']['limit'], app.reads) == (429, 'support_uploads', before), r.text
        assert 'Too many messages were started' in error_of(r)['message']
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.support_tickets')[0]['n'] == 0


def test_the_image_ceiling_is_one_lock_for_every_sender(on, store):
    """The checker's deploy-2: the sum of every ticket's images is checked under one lock for all senders, so two
    accounts sending at once cannot both pass the ceiling: while another holds it, an upload with images waits."""
    import threading
    alice = make_user(store, 'alice', 'alice-password')
    p = type('P', (), {'user_id': alice['user_id'], 'plan_key': 'free'})()
    tickets = support_module.SupportStore(store, on)
    done = threading.Event()
    with store.connect() as holder:
        holder.execute('SELECT pg_advisory_xact_lock(%s, %s)', (0x5350, 0))
        worker = threading.Thread(target=lambda: (tickets.create(p, 'bug', 'S', 'B', {}, [('s.png', 'image/png', PNG)]),
                                                  done.set()))
        worker.start()
        assert not done.wait(1.0), 'an upload with images passed the ceiling while another sender held it'
    worker.join(10)
    assert done.is_set()
    # without images no ceiling is read and nothing waits for it
    with store.connect() as holder:
        holder.execute('SELECT pg_advisory_xact_lock(%s, %s)', (0x5350, 0))
        tickets.create(p, 'bug', 'S', 'B', {}, [])


def test_the_limits_words_count_one_message_and_several():
    from app.errors import words
    one = words('LIMIT_REACHED', 429, {'limit': 'support_hour', 'allowed': 1, 'retry_after_s': 120})
    several = words('LIMIT_REACHED', 429, {'limit': 'support_day', 'allowed': 20, 'retry_after_s': 3600})
    assert one.startswith('You can send 1 support message per hour. Wait ') and 'messages' not in one
    assert several.startswith('You can send 20 support messages per day. Wait ')


def test_the_beta_owner_sends_with_the_switch_off(settings, store):
    """The beta (EDGE_MULTIUSER unset): the owner, user #1, holds every capability and sends as itself."""
    with TestClient(app_of(dataclasses.replace(settings, telegram_notify_url=NOTIFY, telegram_support_secret=SECRET),
                           store)) as c:
        h = login(c)
        r = c.post(PATH, headers=h, json=message(kind='question'))
        assert r.status_code == 201, r.text
        row = db(store, 'SELECT t.user_id, t.site, t.kind, u.owner_key FROM edge_bff.support_tickets t '
                        'JOIN edge_bff.users u USING (user_id)')[0]
        assert (row['owner_key'], row['site'], row['kind']) == ('local-test-owner', 'beta', 'question')


# ---- each field and its reason --------------------------------------------------------------------------------------

FIELD_CASES = [          # (what, the change, the field named, its reason)
    ('another kind', {'kind': 'other'}, 'kind', 'kind'),
    ('no kind', {'kind': None}, 'kind', 'kind'),
    ('an empty subject', {'subject': ' \n\t '}, 'subject', 'subject'),
    ('a long subject', {'subject': 'x' * 121}, 'subject', 'subject'),
    ('a subject with a direction mark', {'subject': 'abc\u202edef'}, 'subject', 'hidden'),
    ('a subject with a zero-width space', {'subject': 'ad\u200bmin'}, 'subject', 'hidden'),
    ('a subject that is a number', {'subject': 5}, 'subject', 'subject'),
    ('an empty description', {'body': ' \n\t '}, 'body', 'body'),
    ('a long description', {'body': 'x' * 5001}, 'body', 'body'),
    ('a description with a NUL', {'body': 'a\x00b'}, 'body', 'hidden'),
    ('a description with a paragraph separator', {'body': 'a\u2029b'}, 'body', 'hidden'),
    ('four images', {'images': [image(PNG)] * 4}, 'images', 'images'),
    ('images that are not a list', {'images': 'x'}, 'images', 'images'),
    ('an image without data', {'images': [{'name': 'a.png'}]}, 'images', 'image_data'),
    ('an image that is not base64', {'images': [{'data': 'not base64!'}]}, 'images', 'image_data'),
    ('an image with a stray character', {'images': [{'data': b64(PNG)[:8] + '*' + b64(PNG)[8:]}]}, 'images', 'image_data'),
    ('an empty image', {'images': [{'data': ''}]}, 'images', 'image_data'),
    ('a GIF named and typed PNG', {'images': [image(GIF)]}, 'images', 'image_type'),
    ('a text named PNG', {'images': [image(b'hello world, not a picture')]}, 'images', 'image_type'),
    ('an image one byte too large', {'images': [image(b'\x89PNG\r\n\x1a\n' + bytes(IMAGE_BYTES - 7))]}, 'images', 'image_size'),
    ('a detail the page does not send', {'details': {'cookie': 'x'}}, 'details', 'details'),
    ('a long detail', {'details': {'page': 'x' * 201}}, 'details', 'details'),
    ('a detail with a direction mark', {'details': {'page': '/term\u202einal'}}, 'details', 'details'),
    ('details that are a list', {'details': ['x']}, 'details', 'details'),
    ('a detail that is a number', {'details': {'page': 5}}, 'details', 'details'),
]


def test_each_field_is_refused_with_its_reason_and_nothing_is_kept(on, store):
    with TestClient(app_of(on, store)) as c:
        make_user(store, 'alice', 'alice-password')
        h = sign_in(c, 'alice', 'alice-password')
        raw = {**h, 'Content-Type': 'application/json'}
        for name, change, field, reason in FIELD_CASES:
            r = c.post(PATH, headers=h, json=message(**change))
            assert (r.status_code, error_of(r)['code']) == (400, 'INVALID_INPUT'), (name, r.text)
            assert error_of(r)['details'] == {'fields': [field], 'reasons': {field: REASONS[reason]}}, name
        # a lone surrogate (which no database or email carries) comes only as a JSON escape
        r = c.post(PATH, headers=raw, content=json.dumps(message(subject='a\ud800b')).encode())
        assert error_of(r)['details'] == {'fields': ['subject'], 'reasons': {'subject': REASONS['hidden']}}, r.text
        for name, content in (('not JSON', b'{"kind": '), ('a list', b'[]'), ('text', 'caf\xe9'.encode('latin-1'))):
            r = c.post(PATH, headers=raw, content=content)
            assert (r.status_code, error_of(r)['details']) == (400, {'fields': ['request'], 'reasons': {
                'request': REASONS['request']}}), name
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.support_tickets')[0]['n'] == 0
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.email_outbox')[0]['n'] == 0


def test_a_subject_is_one_line_and_emoji_and_scripts_keep_their_joiners(on, store):
    family = '\U0001F468\u200d\U0001F469\u200d\U0001F467'          # one emoji made of three, joined (U+200D)
    persian = 'می\u200cخواهم'                                        # a word that needs the non-joiner (U+200C)
    newest = '\U0001FAE9'          # an emoji of Unicode 16, not yet assigned in this Python's Unicode (Cn): kept
    with TestClient(app_of(on, store)) as c:
        make_user(store, 'alice', 'alice-password')
        h = sign_in(c, 'alice', 'alice-password')
        r = c.post(PATH, headers=h, json=message(subject=f' Two\nlines\tand  {family} ',
                                                 body=f'{persian}\n\tindented\n{family} {newest}'))
        assert r.status_code == 201, r.text
        row = db(store, 'SELECT subject, body FROM edge_bff.support_tickets')[0]
        assert row['subject'] == f'Two lines and {family}'
        assert row['body'] == f'{persian}\n\tindented\n{family} {newest}'


# ---- the limits ---------------------------------------------------------------------------------------------------------

def test_the_hourly_and_daily_limits_count_each_account_and_say_when_to_send_again(on, store):
    with TestClient(app_of(dataclasses.replace(on, support_per_hour=2, support_per_day=3), store)) as c:
        make_user(store, 'alice', 'alice-password')
        make_user(store, 'bob', 'bob-password')
        h = sign_in(c, 'alice', 'alice-password')
        assert [c.post(PATH, headers=h, json=message()).status_code for _ in range(2)] == [201, 201]
        r = c.post(PATH, headers=h, json=message())
        d = error_of(r)['details']
        assert (r.status_code, error_of(r)['code'], d['limit'], d['allowed']) == (429, 'LIMIT_REACHED', 'support_hour', 2)
        assert 3500 < d['retry_after_s'] <= 3601 and r.headers['retry-after'] == str(d['retry_after_s'])
        assert error_of(r)['message'].startswith('You can send 2 support messages per hour. Wait ')
        assert 'plan' not in error_of(r)['message']
        db(store, "UPDATE edge_bff.support_tickets SET created_at = created_at - interval '2 hours'")
        assert c.post(PATH, headers=h, json=message()).status_code == 201
        r = c.post(PATH, headers=h, json=message())
        d = error_of(r)['details']
        assert (r.status_code, d['limit'], d['allowed']) == (429, 'support_day', 3) and 79000 < d['retry_after_s'] <= 79201
        assert error_of(r)['message'].startswith('You can send 3 support messages per day. Wait ')
        h = sign_in(c, 'bob', 'bob-password')                                                 # bob counts his own
        assert c.post(PATH, headers=h, json=message()).status_code == 201
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.support_tickets')[0]['n'] == 4


def test_two_messages_of_one_account_are_counted_one_after_the_other(on, store):
    """The count and the insert hold a lock per account (pg_advisory_xact_lock(0x5350, user_id)): a second message of
    the same account waits for the first one's commit, so two at once cannot both pass the limit; another account's
    message does not wait."""
    tickets = support_module.SupportStore(store, dataclasses.replace(on, support_per_hour=1))
    alice, bob = make_user(store, 'alice', 'alice-password'), make_user(store, 'bob', 'bob-password')

    def principal(user):
        return type('P', (), {'user_id': user['user_id'], 'plan_key': 'free'})()
    done = {}

    def send(user):
        try:
            done[user['username']] = tickets.create(principal(user), 'bug', 's', 'b', {}, [])
        except Refusal as e:
            done[user['username']] = e
    with psycopg.connect(on.database_url, autocommit=True) as holder:
        holder.execute('SELECT pg_advisory_lock(%s, %s)', (0x5350, alice['user_id']))
        waiting = threading.Thread(target=send, args=(alice,))
        waiting.start()
        send(bob)                                                                    # another account: not held
        waiting.join(0.5)
        assert waiting.is_alive() and 'alice' not in done and isinstance(done['bob'], dict)
        holder.execute('SELECT pg_advisory_unlock(%s, %s)', (0x5350, alice['user_id']))
        waiting.join(5)
    assert isinstance(done['alice'], dict)
    send(alice)
    assert isinstance(done['alice'], Refusal) and done['alice'].details['limit'] == 'support_hour'


def test_the_images_of_every_ticket_together_stay_under_the_storage_ceiling(on, store):
    picture = b'\x89PNG\r\n\x1a\n' + bytes(600 * 1024)
    with TestClient(app_of(dataclasses.replace(on, support_storage_mb=1), store)) as c:
        make_user(store, 'alice', 'alice-password')
        h = sign_in(c, 'alice', 'alice-password')
        assert c.post(PATH, headers=h, json=message(images=[image(picture)])).status_code == 201
        r = c.post(PATH, headers=h, json=message(images=[image(picture)]))
        assert (r.status_code, error_of(r)['code'], error_of(r)['details']) == (503, 'SUPPORT_STORAGE_FULL', {'fields': ['images']})
        assert 'without images' in error_of(r)['message']
        assert c.post(PATH, headers=h, json=message()).status_code == 201                   # the text alone still goes
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.support_attachments')[0]['n'] == 1


# ---- the email and the Telegram summary ---------------------------------------------------------------------------------

def send_one(on, store, **change):
    with TestClient(app_of(on, store)) as c:
        admin_user(store, 'boss', 'boss-password', email='boss@example.com')
        make_user(store, 'alice', 'alice-password', email='alice@example.com')
        h = sign_in(c, 'alice', 'alice-password')
        r = c.post(PATH, headers=h, json=message(**change))
        assert r.status_code == 201, r.text
        return r.json()['ticket_id']


def test_the_email_goes_with_its_images_and_reply_to_the_sender(on, store):
    ticket = send_one(on, store, images=[image(PNG), image(JPEG, 'b.jpg')])
    seen = []

    def resend(request):
        seen.append((request.headers['idempotency-key'], json.loads(request.content)))
        return httpx.Response(200, json={'id': 'em_1'})
    sender = EmailSender(dataclasses.replace(on, email_mode='resend', resend_api_key='re_test_key',
                                             email_from='EDGE <no-reply@mail.example.com>'),
                         store, transport=httpx.MockTransport(resend))

    async def go():
        assert await sender.step() is True
        await sender.aclose()
    asyncio.run(go())
    key, body = seen[0]
    assert (body['to'], body['reply_to']) == (['boss@example.com'], 'alice@example.com')
    assert body['subject'] == f'EDGE support #{ticket}: Bug / Something not working: The chart does not load'
    assert body['attachments'] == [{'filename': 'screen.png', 'content': b64(PNG)}, {'filename': 'b.jpg', 'content': b64(JPEG)}]
    assert key.startswith(f'support:{ticket}:') and set(body) == {'from', 'to', 'subject', 'text', 'html', 'reply_to', 'attachments'}
    row = db(store, 'SELECT status, provider_id, payload FROM edge_bff.email_outbox')[0]
    assert (row['status'], row['provider_id'], row['payload']) == ('sent', 'em_1', None)


@pytest.mark.parametrize('images,mode', [([image(PNG)], 'resend'), ([], 'resend'), ([], 'log')])
def test_an_email_whose_ticket_is_gone_is_not_sent(on, store, images, mode):
    """With or without images, sent or logged (the checker's support-2: a ticket without images was emailed after
    it was deleted)."""
    send_one(on, store, images=images)
    db(store, 'DELETE FROM edge_bff.support_tickets')                       # deleted by hand, or its account since
    seen = []
    sender = EmailSender(dataclasses.replace(on, email_mode=mode, resend_api_key='re_test_key',
                                             email_from='EDGE <no-reply@mail.example.com>'),
                         store, transport=httpx.MockTransport(lambda r: (seen.append(r), httpx.Response(200, json={}))[1]))

    async def go():
        await sender.step()
        await sender.aclose()
    asyncio.run(go())
    assert seen == [] and db(store, 'SELECT status, payload FROM edge_bff.email_outbox')[0] == {'status': 'expired', 'payload': None}


@pytest.mark.parametrize('environment', ['local', 'dev'])
def test_the_log_mode_never_writes_the_senders_words(on, store, caplog, environment):
    send_one(on, store, subject='My secret subject', body='My private description')
    sender = EmailSender(dataclasses.replace(on, environment=environment), store)
    with caplog.at_level(logging.INFO, logger='edge_bff.email'):
        asyncio.run(sender.step())
    assert 'My secret subject' not in caplog.text and 'My private description' not in caplog.text
    assert 'boss@example.com' not in caplog.text and '"private": true' in caplog.text
    row = db(store, 'SELECT status, provider_id, payload FROM edge_bff.email_outbox')[0]
    assert (row['status'], row['provider_id'], row['payload']) == ('sent', 'log', None)


def test_a_summary_not_accepted_is_sent_again_at_most_five_times_within_a_day(on, store):
    failing = Telegram(status=500)
    with TestClient(app_of(on, store, failing)) as c:
        make_user(store, 'alice', 'alice-password')
        h = sign_in(c, 'alice', 'alice-password')
        ticket = c.post(PATH, headers=h, json=message()).json()['ticket_id']
        assert wait_for(lambda: db(store, 'SELECT telegram_attempts FROM edge_bff.support_tickets')[0]['telegram_attempts'] == 1)
    row = db(store, 'SELECT telegram_sent_at, telegram_attempts FROM edge_bff.support_tickets')[0]
    assert row['telegram_sent_at'] is None

    async def retry(telegram):
        support = support_module.Support(on, store, transport=telegram.transport())
        await support.retry_telegram()
        await support.aclose()
    asyncio.run(retry(Telegram(status=202)))                # another attempt under way there: not yet sent
    assert db(store, 'SELECT telegram_sent_at, telegram_attempts FROM edge_bff.support_tickets')[0] == {
        'telegram_sent_at': None, 'telegram_attempts': 2}
    for _ in range(5):
        asyncio.run(retry(failing))
    assert len(failing.seen) == 4                       # the first try, the 202 and three more: TELEGRAM_ATTEMPTS, then left alone
    assert db(store, 'SELECT telegram_attempts FROM edge_bff.support_tickets')[0]['telegram_attempts'] == 5
    db(store, 'UPDATE edge_bff.support_tickets SET telegram_attempts = 1')
    accepting = Telegram()
    asyncio.run(retry(accepting))
    assert accepting.seen[0]['body']['execution_id'] == f'support-{ticket}'
    assert accepting.seen[0]['body']['details']['images'] == 0
    assert db(store, 'SELECT telegram_sent_at FROM edge_bff.support_tickets')[0]['telegram_sent_at'] is not None
    asyncio.run(retry(accepting))
    assert len(accepting.seen) == 1                                                # accepted: never again
    db(store, "UPDATE edge_bff.support_tickets SET telegram_sent_at = NULL, created_at = now() - interval '25 hours'")
    asyncio.run(retry(accepting))
    assert len(accepting.seen) == 1                                                # older than a day: left to the admin page


def test_no_summary_without_telegram_monitors_address_or_secret(on, store):
    telegram = Telegram()
    for change in ({'telegram_notify_url': ''}, {'telegram_support_secret': ''}):
        with TestClient(app_of(dataclasses.replace(on, **change), store, telegram)) as c:
            make_user(store, 'alice', 'alice-password')
            h = sign_in(c, 'alice', 'alice-password')
            assert c.post(PATH, headers=h, json=message()).status_code == 201
        db(store, 'DELETE FROM edge_bff.users WHERE username = %s', 'alice')
    assert telegram.seen == []


def test_the_admin_link_is_https_only_and_a_ticket_without_admin_email_is_logged(on, store, caplog):
    assert support_module.admin_link(on, 7) == f'{ADMIN}/admin?ticket=7'
    assert support_module.admin_link(dataclasses.replace(on, admin_origin='http://admin.example.test'), 7) == ''
    assert support_module.admin_link(dataclasses.replace(on, admin_origin=''), 7) == ''
    with caplog.at_level(logging.WARNING, logger='edge_bff.support'):
        with TestClient(app_of(on, store)) as c:
            make_user(store, 'alice', 'alice-password')
            h = sign_in(c, 'alice', 'alice-password')
            assert c.post(PATH, headers=h, json=message()).status_code == 201
    assert 'support_no_recipient' in caplog.text
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.email_outbox')[0]['n'] == 0


# ---- the settings and the table's own checks ------------------------------------------------------------------------------

def test_the_settings_hold_their_ranges(settings, monkeypatch):
    dataclasses.replace(settings, support_per_hour=1, support_per_day=1000, support_storage_mb=100000).validate()
    for good in ('http://telegram-monitor.railway.internal:8080/notify', 'http://telegram-monitor.invalid/notify'):
        dataclasses.replace(settings, telegram_notify_url=good).validate()
    for change in ({'support_per_hour': 0}, {'support_per_hour': 101}, {'support_per_day': 0}, {'support_storage_mb': 0},
                   {'admin_origin': 'http://admin.example.test'}, {'admin_origin': 'https://admin.example.test/admin'},
                   {'telegram_notify_url': 'https://telegram-monitor.invalid/'},
                   {'telegram_notify_url': 'ftp://telegram-monitor.invalid/notify'},
                   # the checker's deploy-3: no host, and a port reference that resolved empty
                   {'telegram_notify_url': 'http://:/notify'},
                   {'telegram_notify_url': 'http://telegram-monitor.railway.internal:/notify'}):
        with pytest.raises(ValueError):
            dataclasses.replace(settings, **change).validate()
    monkeypatch.setenv('EDGE_SUPPORT_PER_HOUR', '0')                                 # an explicit 0 is not the default
    from app.config import count_or
    assert count_or('EDGE_SUPPORT_PER_HOUR', 5) == 0 and count_or('EDGE_SUPPORT_UNSET_NAME', 5) == 5
    assert Settings.__dataclass_fields__['telegram_support_secret'].repr is False


def test_the_tables_refuse_what_the_route_refuses(on, store):
    alice = make_user(store, 'alice', 'alice-password')
    ticket = db(store, '''INSERT INTO edge_bff.support_tickets(user_id, site, kind, subject, body, details)
        VALUES (%s, 'live', 'data', 'A title', 'A body', '{}'::jsonb) RETURNING ticket_id''', alice['user_id'])[0]['ticket_id']
    bad_tickets = [("'mars'", "'data'", "'A title'", "'A body'", "'{}'"), ("'live'", "'spam'", "'A title'", "'A body'", "'{}'"),
                   ("'live'", "'data'", "' padded '", "'A body'", "'{}'"), ("'live'", "'data'", "repeat('x', 121)", "'A body'", "'{}'"),
                   ("'live'", "'data'", "'A title'", "'   '", "'{}'"), ("'live'", "'data'", "'A title'", "'A body'", "'[1]'")]
    for site, kind, subject, body, details in bad_tickets:
        with pytest.raises(psycopg.errors.CheckViolation):
            db(store, f'INSERT INTO edge_bff.support_tickets(user_id, site, kind, subject, body, details) '
                      f'VALUES (%s, {site}, {kind}, {subject}, {body}, {details}::jsonb)', alice['user_id'])
    with pytest.raises(psycopg.errors.CheckViolation):
        db(store, "UPDATE edge_bff.support_tickets SET status = 'done' WHERE ticket_id = %s", ticket)   # without done_at
    good = (ticket, 1, 'a.png', 'image/png', len(PNG), hashlib.sha256(PNG).hexdigest(), PNG)
    for change in ({2: 'a/b.png'}, {3: 'image/gif'}, {4: len(PNG) + 1}, {5: '0' * 64}, {1: 4}):
        row = list(good)
        for i, v in change.items():
            row[i] = v
        with pytest.raises(psycopg.errors.CheckViolation):
            db(store, 'INSERT INTO edge_bff.support_attachments(ticket_id, position, filename, content_type, bytes, sha256, body) '
                      'VALUES (%s, %s, %s, %s, %s, %s, %s)', *row)
    db(store, 'INSERT INTO edge_bff.support_attachments(ticket_id, position, filename, content_type, bytes, sha256, body) '
              'VALUES (%s, %s, %s, %s, %s, %s, %s)', *good)
    db(store, 'DELETE FROM edge_bff.users WHERE user_id = %s', alice['user_id'])                     # goes with the account
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.support_attachments')[0]['n'] == 0


def test_telegram_monitor_accepts_every_summary_edge_bff_sends():
    """The two services hold one shape (telegram-monitor parse_edge_support, edge-bff telegram_details): each summary
    edge-bff can make is one the monitor sends, the longest subject and the beta owner's (no plan) included."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / 'telegram-monitor' / 'telegram_monitor.py'
    spec = importlib.util.spec_from_file_location('telegram_monitor_contract', path)
    monitor = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = monitor                     # its dataclasses read their own module while they are made
    spec.loader.exec_module(monitor)
    assert monitor.SUPPORT_SOURCE == support_module.TELEGRAM_SOURCE
    assert set(monitor.SUPPORT_KINDS) == set(support_module.KINDS) and monitor.SUPPORT_IMAGES == support_module.IMAGES
    assert monitor.SUPPORT_SUBJECT_CHARS == support_module.SUBJECT_CHARS
    family = '\U0001F468\u200d\U0001F469\u200d\U0001F467'
    for kind in support_module.KINDS:
        for site, plan, images, link, subject in (('live', 'free', 0, '', 'A'), ('beta', None, 3, f'{ADMIN}/admin?ticket=99', 'x' * 120),
                                                  ('live', 'paid', 1, f'{ADMIN}/admin?ticket=99', f'{family} '.strip() * 10)):
            info = {'ticket_id': 99, 'site': site, 'kind': kind, 'subject': support_module.clean_line(subject, 120, 'subject'),
                    'sender': {'username': 'owner', 'plan': plan}, 'images': [{}] * images, 'link': link}
            details = support_module.telegram_details(info)
            notice = monitor.parse_edge_support(f'support-{info["ticket_id"]}', details)
            assert (notice.ticket_id, notice.kind, notice.subject, notice.images) == (99, kind, info['subject'], images)


def test_the_dialog_holds_the_servers_limits_and_its_kinds_the_emails_words():
    """The shell's dialog checks what the server checks (static/edge-app.js SUPPORT_LIMITS, one JSON line) and names the
    issue types as the email does (static/edge-labels.js support.kinds, email_texts.SUPPORT_KINDS): one value each."""
    import re
    import subprocess
    from pathlib import Path
    from app import email_texts
    static = Path(__file__).resolve().parents[1] / 'static'
    line = re.search(r'^const SUPPORT_LIMITS = (\{.*\});$', (static / 'edge-app.js').read_text(), re.M)
    assert line, 'SUPPORT_LIMITS is one JSON line in static/edge-app.js'
    limits = json.loads(line.group(1))
    assert limits == {'images': support_module.IMAGES, 'image_bytes': support_module.IMAGE_BYTES,
                      'subject': support_module.SUBJECT_CHARS, 'body': support_module.BODY_CHARS,
                      'types': [kind for kind, _ in support_module.SIGNATURES], 'details': support_module.PAGE_DETAILS}
    out = subprocess.run(['node', '-e', "global.window={};require(process.argv[1]);"
                          "console.log(JSON.stringify(window.EdgeLabels.support.kinds))", str(static / 'edge-labels.js')],
                         capture_output=True, text=True, timeout=30, check=True).stdout
    kinds = json.loads(out)
    assert list(kinds) == list(support_module.KINDS) and kinds == email_texts.SUPPORT_KINDS


def test_on_the_live_site_an_account_and_the_admin_send_and_a_visitor_is_refused(settings, store):
    """The live site, where the user asked for the panel ("panel sebelah kiri di live"): a test account on the free plan
    (the pre-launch mode lets it in) is offered support.send by its session answer (the shell's Edge.can) and sends; the
    admin past its second factor sends through the live site's view (every released capability); a visitor, guests on,
    is refused before the body is read; every ticket and its summary say the live site."""
    from test_beta_live_site import live_of, sign_in_admin
    live = dataclasses.replace(live_of(settings), guests_enabled=True, telegram_notify_url=NOTIFY,
                               telegram_support_secret=SECRET, admin_origin=ADMIN)
    telegram = Telegram()
    app = Reads(app_of(live, store, telegram))
    with TestClient(app) as c:
        alice = make_user(store, 'alice', 'alice-password', email='alice@example.com')
        with store.connect() as conn:                       # the mark comes with its audit row (scripts/edge_test_account.py)
            conn.execute('''INSERT INTO edge_bff.admin_audit(action, target_user_id, after, reason)
                VALUES ('account.test_mark', %s, '{"test_account": true}', 'test: the live site in pre-launch')''',
                         (alice['user_id'],))
            conn.execute('UPDATE edge_bff.users SET test_account = true WHERE user_id = %s', (alice['user_id'],))
        visitor = {**ORIGIN, 'x-forwarded-for': '203.0.113.7, 152.233.40.1'}
        assert c.get('/api/v1/auth/guest', headers=visitor).status_code == 200            # a guest principal exists
        before = app.reads
        r = c.post(PATH, headers=visitor, json=message())
        assert (r.status_code, error_of(r)['code'], app.reads) == (401, 'UNAUTHENTICATED', before)
        h = sign_in(c, 'alice', 'alice-password')
        assert 'support.send' in c.get('/api/v1/auth/session').json()['access']['capabilities']
        assert c.post(PATH, headers=h, json=message()).status_code == 201
        c.cookies.clear()
        h = sign_in_admin(c, store)
        assert c.post(PATH, headers=h, json=message(kind='feature')).status_code == 201
        rows = db(store, "SELECT site, details->>'site' AS said, details->>'plan' AS plan FROM edge_bff.support_tickets "
                         'ORDER BY ticket_id')
        assert [(r['site'], r['said']) for r in rows] == [('live', 'live'), ('live', 'live')] and rows[0]['plan'] == 'free'
        assert wait_for(lambda: len(telegram.seen) == 2)
        assert {s['body']['details']['site'] for s in telegram.seen} == {'live'}


def test_a_tickets_images_go_90_days_after_it_is_done_and_its_text_stays(on, store):
    """The user, 2026-11-22: "2B": the hourly housekeeping deletes a ticket's images 90 days after the ticket is marked
    done (store.PURGES 'support_images'), records when, keeps the text and the count of what was attached, and holds to
    the batch bound; a ticket not done, done lately, or without images is left as it is."""
    from app.store import PURGES
    assert 'support_images' in PURGES and support_module.IMAGE_DAYS == 90
    tickets = support_module.SupportStore(store, on)
    alice = make_user(store, 'alice', 'alice-password')
    p = type('P', (), {'user_id': alice['user_id'], 'plan_key': 'free'})()
    made = {name: tickets.create(p, 'bug', name, f'the {name} text', {}, [('a.png', 'image/png', PNG)] * n)['ticket_id']
            for name, n in (('old', 2), ('older', 1), ('recent', 1), ('open', 1), ('bare', 0))}
    for name, days in (('old', 91), ('older', 120), ('recent', 89), ('bare', 200)):
        db(store, "UPDATE edge_bff.support_tickets SET status = 'done', done_at = now() - make_interval(days => %s) "
                  "WHERE ticket_id = %s", days, made[name])
    db(store, "UPDATE edge_bff.support_tickets SET created_at = now() - interval '200 days' WHERE ticket_id = %s", made['open'])
    held = lambda: db(store, 'SELECT coalesce(sum(bytes), 0) AS b FROM edge_bff.support_attachments')[0]['b']
    before = held()
    assert [store.purge('support_images', 1) for _ in range(3)] == [1, 1, 0]          # oldest first, one per batch
    rows = {r['subject']: r for r in db(store, '''SELECT t.subject, t.body, t.images, t.images_purged_at,
        (SELECT count(*) FROM edge_bff.support_attachments a WHERE a.ticket_id = t.ticket_id) AS kept
        FROM edge_bff.support_tickets t''')}
    assert {n: (r['kept'], r['images'], r['images_purged_at'] is not None) for n, r in rows.items()} == {
        'old': (0, 2, True), 'older': (0, 1, True), 'recent': (1, 1, False), 'open': (1, 1, False), 'bare': (0, 0, False)}
    assert rows['old']['body'] == 'the old text'
    assert held() == before - 3 * len(PNG)                                             # the storage ceiling frees
