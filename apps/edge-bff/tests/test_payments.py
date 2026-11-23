"""Step 7, the payment shell (CONTRACT.md 11; FINDINGS.md test 8): a duplicate notification gives one change; a bad
signature or a wrong amount gives no change; an older event is ignored; a settled order never goes back; a missed
notification is reconciled; the routes are off until EDGE_PAYMENTS_PROVIDER names their provider. Midtrans' offline
parts (its signature, status words, amount and event key) are checked against values computed here; nothing reaches
Midtrans or any network."""
import dataclasses
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import hooks
from app.config import LIVE
from app.main import create_app
from app.payments import adapters
from app.payments.adapters import (Event, MidtransAdapter, PaymentNotConfigured, TestAdapter, midtrans_signature,
                                   midtrans_status, midtrans_verify, rupiah, sign_test_provider, valid_order_id)
from app.payments.orders import PaymentStore, new_order_id
from conftest import FakeOrc, RoleStore
from test_principal import make_user

SECRET = 's' * 40
PATH = '/api/v1/hooks/payments/test'
T0 = datetime(2026, 11, 23, 10, 0, tzinfo=timezone(timedelta(hours=7)))


def db(store, sql, *args):
    with store.connect() as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


@pytest.fixture
def paying(settings):
    return dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
                               payments_provider='test', payments_secret=SECRET)


@pytest.fixture
def client(paying, store):
    with TestClient(create_app(paying, store, FakeOrc())) as c:
        yield c


def a_plan(store, holder=True):
    """A plan key read from the data, never named in code (test_plan_catalog's rule): a plan to pay for (not the
    default, not the visitors', not one holding '*'), or with holder=False the default plan."""
    if not holder:
        return db(store, 'SELECT plan_key FROM edge_bff.plans WHERE is_default')[0]['plan_key']
    return db(store, """SELECT plan_key FROM edge_bff.plans p WHERE NOT is_default AND NOT for_guests AND NOT EXISTS (
        SELECT 1 FROM edge_bff.plan_capabilities pc WHERE pc.plan_key = p.plan_key AND pc.capability_key = '*')
        ORDER BY plan_key LIMIT 1""")[0]['plan_key']


def order(store, user_id, plan_key, amount=50000, days=30, ttl=86400):
    return PaymentStore(store).create_order(user_id, plan_key, days, amount, 'test', ttl)


def notify(c, body, secret=SECRET):
    raw = json.dumps(body).encode()
    return c.post(PATH, content=raw, headers={'content-type': 'application/json',
                                              'x-edge-test-signature': sign_test_provider(raw, secret)})


def event(order_id, status, n, amount=50000, at=None, currency='IDR'):
    return {'event_id': f'ev-{n}', 'order_id': order_id, 'status': status, 'amount_idr': amount, 'currency': currency,
            'event_at': (at or T0).isoformat()}


def subscriptions(store, user_id):
    return db(store, "SELECT * FROM edge_bff.subscriptions WHERE user_id = %s ORDER BY subscription_id", user_id)


# ---- the routes are off until switched on ---------------------------------------------------------------------------

def test_the_payment_routes_are_off_until_the_provider_is_named_and_each_is_a_signed_hook(settings, store):
    assert {f'/api/v1/hooks/payments/{p}' for p in adapters.VERIFIERS} <= set(hooks.HOOK_ROUTES)
    off = dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40, payments_secret=SECRET)
    with TestClient(create_app(off, store, FakeOrc())) as c:
        r = notify(c, event('edge-x', 'settled', 1))
        assert r.status_code == 404 and r.json()['error']['code'] == 'NOT_FOUND'
    with TestClient(create_app(dataclasses.replace(off, payments_provider='test'), store, FakeOrc())) as c:
        r = c.post('/api/v1/hooks/payments/midtrans', content=b'{}', headers={'content-type': 'application/json'})
        assert r.status_code == 404                                     # another provider's route stays off
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.payment_events')[0]['n'] == 0


def test_the_settings_refuse_midtrans_before_its_phase_and_the_test_provider_on_the_live_site(settings):
    base = dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40, payments_secret=SECRET)
    base.validate()                                                     # unset: fine
    dataclasses.replace(base, payments_provider='test').validate()
    for wrong, words in ((dict(payments_provider='midtrans'), 'not built yet'),
                         (dict(payments_provider='test', site=LIVE, orc_url='', orc_key=''), 'beta only'),
                         (dict(payments_provider='test', multiuser=False), 'EDGE_MULTIUSER=true'),
                         (dict(payments_provider='test', payments_secret='short'), 'at least 32'),
                         (dict(payments_provider='stripe'), 'not a provider')):
        with pytest.raises(ValueError, match=words):
            dataclasses.replace(base, **wrong).validate()


# ---- the state machine through the route ------------------------------------------------------------------------------

def test_a_settled_notification_starts_the_plan_once_and_its_duplicate_changes_nothing(client, store):
    user = make_user(store, 'payer_one', 'payer-password')
    plan = a_plan(store)
    o = order(store, user['user_id'], plan)
    assert valid_order_id(o['order_id']) and o['status'] == 'pending'
    r = notify(client, event(o['order_id'], 'settled', 1))
    assert r.status_code == 200 and r.json() == {'status': 'applied'}
    subs = subscriptions(store, user['user_id'])
    assert [(s['plan_key'], s['status'], s['provider'], s['provider_ref']) for s in subs] == [(plan, 'active', 'test', o['order_id'])]
    ends = subs[0]['expires_at']
    assert timedelta(days=29, hours=23) < ends - subs[0]['starts_at'] <= timedelta(days=30, minutes=1)
    again = notify(client, event(o['order_id'], 'settled', 1))
    assert again.status_code == 200 and again.json() == {'status': 'duplicate'}
    assert subscriptions(store, user['user_id'])[0]['expires_at'] == ends and len(subscriptions(store, user['user_id'])) == 1
    row = PaymentStore(store).order(o['order_id'])
    assert row['status'] == 'settled' and row['paid_at'] is not None and row['subscription_id'] == subs[0]['subscription_id']
    kept = PaymentStore(store).events(o['order_id'])
    assert [(e['outcome'], e['applied']) for e in kept] == [('applied', True)] and 'signature' not in kept[0]['payload']


def test_a_bad_signature_or_a_wrong_amount_or_currency_changes_nothing(client, store):
    user = make_user(store, 'payer_two', 'payer-password')
    o = order(store, user['user_id'], a_plan(store))
    r = notify(client, event(o['order_id'], 'settled', 1), secret='x' * 40)
    assert r.status_code == 401 and r.json()['error']['code'] == 'HOOK_SIGNATURE_INVALID'
    assert notify(client, event(o['order_id'], 'settled', 2, amount=5000)).json() == {'status': 'amount_mismatch'}
    assert notify(client, event(o['order_id'], 'settled', 3, currency='USD')).json() == {'status': 'amount_mismatch'}
    assert PaymentStore(store).order(o['order_id'])['status'] == 'pending' and subscriptions(store, user['user_id']) == []
    assert [e['outcome'] for e in PaymentStore(store).events(o['order_id'])] == ['amount_mismatch', 'amount_mismatch']


def test_an_older_event_is_ignored_and_a_settled_order_never_goes_back(client, store):
    user = make_user(store, 'payer_three', 'payer-password')
    o = order(store, user['user_id'], a_plan(store))
    assert notify(client, event(o['order_id'], 'pending', 1, at=T0 + timedelta(minutes=2))).json() == {'status': 'no_change'}
    assert notify(client, event(o['order_id'], 'settled', 2, at=T0 + timedelta(minutes=5))).json() == {'status': 'applied'}
    assert notify(client, event(o['order_id'], 'failed', 3, at=T0 + timedelta(minutes=1))).json() == {'status': 'older'}
    assert notify(client, event(o['order_id'], 'expired', 4, at=T0 + timedelta(hours=30))).json() == {'status': 'no_change'}
    assert PaymentStore(store).order(o['order_id'])['status'] == 'settled'
    assert len(subscriptions(store, user['user_id'])) == 1


def test_a_renewal_extends_the_same_plan_and_another_live_plan_is_held_for_the_admin(client, store):
    user = make_user(store, 'payer_four', 'payer-password')
    plan, other = a_plan(store), a_plan(store, holder=False)
    db(store, '''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, expires_at, provider, provider_ref)
        VALUES (%s, %s, 'active', now() + interval '10 days', 'manual', 'admin-page')''', user['user_id'], plan)
    before = subscriptions(store, user['user_id'])[0]['expires_at']
    o = order(store, user['user_id'], plan)
    assert notify(client, event(o['order_id'], 'settled', 1)).json() == {'status': 'applied'}
    subs = subscriptions(store, user['user_id'])
    assert len(subs) == 1 and subs[0]['expires_at'] - before == timedelta(days=30)
    o2 = order(store, user['user_id'], other)
    assert notify(client, event(o2['order_id'], 'settled', 2)).json() == {'status': 'held'}
    row = PaymentStore(store).order(o2['order_id'])
    assert (row['status'], row['held_reason'], row['subscription_id']) == ('settled', 'plan_conflict', None)
    assert subscriptions(store, user['user_id'])[0]['expires_at'] == subs[0]['expires_at']


def test_a_refund_and_a_payment_after_the_order_ended_are_held_and_an_unknown_order_is_kept(client, store):
    user = make_user(store, 'payer_five', 'payer-password')
    plan = a_plan(store)
    paid = order(store, user['user_id'], plan)
    notify(client, event(paid['order_id'], 'settled', 1))
    assert notify(client, event(paid['order_id'], 'refunded', 2, amount=None)).json() == {'status': 'held'}
    assert PaymentStore(store).order(paid['order_id'])['held_reason'] == 'refund_review'
    assert subscriptions(store, user['user_id'])[0]['status'] == 'active'           # the admin decides
    late = order(store, user['user_id'], plan)
    assert notify(client, event(late['order_id'], 'expired', 3)).json() == {'status': 'applied'}
    assert notify(client, event(late['order_id'], 'settled', 4)).json() == {'status': 'held'}
    assert PaymentStore(store).order(late['order_id'])[('held_reason')] == 'settled_after_end'
    assert notify(client, event('edge-nobody', 'settled', 5)).json() == {'status': 'unknown_order'}
    assert [e['outcome'] for e in PaymentStore(store).events('edge-nobody')] == ['unknown_order']


def test_a_notification_the_shell_cannot_read_names_its_field(client):
    assert notify(client, {'event_id': 'e', 'order_id': 'edge-a', 'status': 'paid?'}).json()['error']['details'] == \
        {'fields': ['status']}
    raw = b'not json'
    r = client.post(PATH, content=raw, headers={'content-type': 'application/json',
                                                'x-edge-test-signature': sign_test_provider(raw, SECRET)})
    assert r.status_code == 400 and r.json()['error']['details'] == {'fields': ['body']}


# ---- reconciliation (the stub for the test provider) --------------------------------------------------------------------

def test_a_missed_notification_is_reconciled_and_a_lapsed_order_ends(store):
    user = make_user(store, 'payer_six', 'payer-password')
    plan = a_plan(store)
    missed = order(store, user['user_id'], plan)
    lapsed = order(store, user['user_id'], plan, ttl=1)
    db(store, "UPDATE edge_bff.payment_orders SET created_at = created_at - interval '1 hour', "
              "expires_at = now() - interval '1 minute' WHERE order_id = %s", lapsed['order_id'])
    provider = TestAdapter(SECRET, records={missed['order_id']: {'event_id': 'record', 'status': 'settled',
                                                                 'amount_idr': 50000, 'currency': 'IDR'}})
    payments = PaymentStore(store)
    assert payments.reconcile('test', provider) == {lapsed['order_id']: 'expired', missed['order_id']: 'applied'}
    assert payments.order(missed['order_id'])['status'] == 'settled' and len(subscriptions(store, user['user_id'])) == 1
    assert payments.order(lapsed['order_id'])['status'] == 'expired'
    assert payments.reconcile('test', provider) == {}                                 # nothing pending is left


def test_the_shell_works_as_the_runtime_role(store, database):
    """The runtime role's grants (migration 20261123_001): an order made, an event applied, the subscription started,
    a reconciliation run, as edge_bff_runtime."""
    user = make_user(store, 'payer_role', 'payer-password')
    plan = a_plan(store)
    role = RoleStore(database, 'edge_bff_runtime')
    try:
        payments = PaymentStore(role)
        o = payments.create_order(user['user_id'], plan, 30, 50000, 'test', 3600)
        got = payments.apply_event('test', Event(o['order_id'], 'ev-role', 'settled', 50000, 'IDR', T0, {'n': 1}))
        assert got.outcome == 'applied' and payments.reconcile('test', TestAdapter(SECRET)) == {}
    finally:
        role.close()
    assert [s['status'] for s in subscriptions(store, user['user_id'])] == ['active']


# ---- Midtrans' offline parts -------------------------------------------------------------------------------------------

def midtrans_body(order_id='edge-0123456789abcdef01234567', status='settlement', code='200', gross='50000.00', key='SB-k'):
    body = {'order_id': order_id, 'status_code': code, 'gross_amount': gross, 'transaction_status': status,
            'currency': 'IDR', 'transaction_time': '2026-11-23 10:00:00', 'payment_type': 'qris'}
    body['signature_key'] = hashlib.sha512(f'{order_id}{code}{gross}{key}'.encode()).hexdigest()
    return body


def test_midtrans_signature_status_amount_and_key_are_read_offline():
    body = midtrans_body()
    assert midtrans_signature(body['order_id'], '200', '50000.00', 'SB-k') == body['signature_key']
    raw = json.dumps(body).encode()
    assert midtrans_verify({}, raw, 'SB-k') and not midtrans_verify({}, raw, 'SB-other') and not midtrans_verify({}, raw, '')
    assert not midtrans_verify({}, json.dumps({**body, 'gross_amount': '5000.00'}).encode(), 'SB-k')
    assert [midtrans_status(s) for s in ('settlement', 'pending', 'deny', 'cancel', 'expire', 'failure', 'refund',
                                         'partial_refund', 'authorize')] == \
        ['settled', 'pending', 'failed', 'cancelled', 'expired', 'failed', 'refunded', 'refunded', None]
    assert (midtrans_status('capture', 'accept'), midtrans_status('capture', 'challenge'),
            midtrans_status('settlement', 'deny')) == ('settled', 'pending', 'failed')
    assert [rupiah(x) for x in ('50000.00', '50000', '0.50', '-1', 'abc', None)] == [50000, 50000, None, None, None, None]
    e = MidtransAdapter('SB-k').verify_webhook({}, raw)
    assert (e.status, e.amount_idr, e.event_key, e.event_at.utcoffset()) == \
        ('settled', 50000, f"{body['order_id']}:settlement:200", timedelta(hours=7))
    assert 'signature_key' not in e.payload
    assert valid_order_id(new_order_id()) and len(new_order_id()) <= 50 and not valid_order_id('a' * 51)
    assert not valid_order_id('edge 1') and not valid_order_id('edge/1')


def test_midtrans_makes_no_call_before_its_phase_and_its_route_applies_nothing_unconfirmed(settings, store, monkeypatch):
    m = MidtransAdapter('SB-k')
    for call in (lambda: m.create_checkout({'order_id': 'edge-a'}, None, {'finish': 'https://x'}),
                 lambda: m.fetch_status('edge-a')):
        with pytest.raises(PaymentNotConfigured, match='Midtrans phase'):
            call()
    # the route, switched on past the settings check (which refuses midtrans): verified, then 503, nothing kept
    forced = dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
                                 payments_provider='midtrans', payments_secret='SB-k')
    monkeypatch.setattr(type(forced), 'validate', lambda self: None)
    with TestClient(create_app(forced, store, FakeOrc())) as c:
        raw = json.dumps(midtrans_body(key='SB-k')).encode()
        r = c.post('/api/v1/hooks/payments/midtrans', content=raw, headers={'content-type': 'application/json'})
        assert r.status_code == 503 and r.json()['error']['code'] == 'SERVICE_UNAVAILABLE'
        bad = c.post('/api/v1/hooks/payments/midtrans', content=json.dumps(midtrans_body(key='other')).encode(),
                     headers={'content-type': 'application/json'})
        assert bad.status_code == 401
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.payment_events')[0]['n'] == 0
