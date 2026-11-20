"""The A2 fix (EXEC.md option A, the next execution, item 2; ERRORS M513 A2 and M517; CONTRACT.md section 4 "Throttle").

The class: a limit keyed by something a stranger can name (a login, an address, a code) let anyone who knows it spend
the owner's allowance: lock the password sign-in (100 consecutive failures), spend the address's 10 code emails a day,
use up a reset code's 5 tries, or replace the owner's live code by asking for one. The fix keys each of them apart from
strangers by what a stranger cannot hold:
- the account's own browser: a device cookie, signed over the account's current verifier, set where the password was
  proved (security.device_of). Under its own limits (DEVICE_SIGNIN, DEVICE_MAIL) it is past the account's lock and the
  address's daily emails;
- a reset's browser: its codes are bound to the browser that asked (the reset cookie, email_codes.binding_hash);
- the client: one client address causes at most SEND_EMAIL_CLIENT of an address's code emails a day, and a
  registration's hourly and daily counts are the address's from that client.

Each test names a case of the class; the last one shows where it does not reach (a new browser of the owner after
three strangers spent the address's day), the residual the records state."""
import re

import pytest
from fastapi.testclient import TestClient

from app import security, throttle
from app.accounts import PASSWORD_FAILURE_CAP
from test_auth_flows import (PASSWORD, app, cooldown_over, db, error_code, last_code, make_account, on,  # noqa: F401
                             outbox, register)
from test_edge import ORIGIN

OWNER, STRANGER, ELSEWHERE = '198.51.100.20', '203.0.113.7', '192.0.2.44'


def at(address):
    return {**ORIGIN, 'X-Forwarded-For': address}


def sign_in(c, password=PASSWORD, address=OWNER, login='ana_putri'):
    return c.post('/api/v1/auth/sign-in', headers=at(address), json={'login': login, 'password': password})


def forgot(c, address, email='ana@example.com'):
    return c.post('/api/v1/auth/password/forgot', headers=at(address), json={'email': email})


def reset(c, code, address, password='my new password', email='ana@example.com'):
    return c.post('/api/v1/auth/password/reset', headers=at(address),
                  json={'email': email, 'code': code, 'password': password, 'password_repeat': password})


def identity(store, email='ana@example.com'):
    return db(store, "SELECT sign_in_failures, sign_in_locked_until FROM edge_bff.identities i JOIN edge_bff.users u "
                     "USING (user_id) WHERE u.email = %s AND i.provider = 'password'", email)[0]


def lock_by_strangers(store, app_client):
    """99 failures already (other addresses, earlier windows), then one stranger's wrong password: the 100th locks."""
    db(store, "UPDATE edge_bff.identities SET sign_in_failures = %s WHERE user_id = (SELECT user_id FROM edge_bff.users "
              "WHERE email = 'ana@example.com')", PASSWORD_FAILURE_CAP - 1)
    assert sign_in(TestClient(app_client.app), 'a stranger guess', STRANGER).status_code == 401
    assert identity(store)['sign_in_locked_until'] is not None


def owner_browser(app_client, store):
    """The account made in `app_client` (its browser holds the device cookie since the registration)."""
    make_account(app_client, store)
    assert 'edge_device' in app_client.cookies, 'the browser that finished the registration has no device cookie'
    return app_client


# ---- the lock of consecutive failures ------------------------------------------------------------------------------------

def test_a_stranger_who_fills_the_lock_does_not_lock_the_owners_own_browser(app, store):
    owner = owner_browser(app, store)
    lock_by_strangers(store, app)
    before = identity(store)
    # the owner's own browser signs in with its password; the lock stays for every other browser
    r = sign_in(owner)
    assert r.status_code == 200, r.text
    assert identity(store) == before                       # a known browser's success leaves the strangers' count
    assert sign_in(TestClient(app.app), PASSWORD, ELSEWHERE).status_code == 401      # a new browser: still locked
    # and the password change from the owner's browser works under the lock too
    h = {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}
    r = owner.post('/api/v1/auth/password/change', headers=h,
                   json={'current_password': PASSWORD, 'password': 'a second password', 'password_repeat': 'a second password'})
    assert r.status_code == 200, r.text
    assert 'edge_device' in r.headers.get('set-cookie', '')                          # its token follows the new password


def test_a_known_browsers_wrong_passwords_have_their_own_limit_then_count_as_anyones(app, store):
    owner = owner_browser(app, store)
    for _ in range(throttle.DEVICE_SIGNIN.allowed):
        assert sign_in(owner, 'not the password').status_code == 401
    assert identity(store)['sign_in_failures'] == 0                     # the device's own failures, not the account's
    # the sign-in limit per login and client (15 min) passes; the device's day does not
    db(store, "UPDATE edge_bff.auth_throttle SET window_start = window_start - interval '16 minutes' "
              "WHERE scope = 'signin_email'")
    assert sign_in(owner, 'not the password').status_code == 401
    assert identity(store)['sign_in_failures'] == 1                     # past its limit the browser counts as any other


def test_a_device_token_ends_with_the_password_it_was_made_for(app, store):
    owner = owner_browser(app, store)
    other = TestClient(app.app)
    assert sign_in(other, PASSWORD, ELSEWHERE).status_code == 200      # a second browser of the owner, its own token
    r = sign_in(owner)
    h = {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}
    assert owner.post('/api/v1/auth/password/change', headers=h,
                      json={'current_password': PASSWORD, 'password': 'a second password',
                            'password_repeat': 'a second password'}).status_code == 200
    lock_by_strangers(store, app)
    assert sign_in(owner, 'a second password').status_code == 200                    # its token follows the change
    assert sign_in(other, 'a second password', ELSEWHERE).status_code == 401        # the old token ended with it


def test_a_tampered_or_another_accounts_device_token_is_ignored(app, store, on):
    owner = owner_browser(app, store)
    bea = TestClient(app.app)
    make_account(bea, store, 'bea@example.com', 'bea_sari')
    lock_by_strangers(store, app)
    token = owner.cookies.get('edge_device')
    user_id, issued, nonce, mac = token.split('.')
    flipped = f'{user_id}.{issued}.{nonce}.{"0" if mac[0] != "0" else "1"}{mac[1:]}'
    for cookie in (flipped, bea.cookies.get('edge_device'), 'not a token'):
        c = TestClient(app.app)
        c.cookies.set('edge_device', cookie)
        assert sign_in(c, PASSWORD, ELSEWHERE).status_code == 401, cookie[:12]
    assert security.device_of(on.session_secret, token, int(user_id), 'another verifier') is None


# ---- a reset's codes --------------------------------------------------------------------------------------------------

def test_a_strangers_requests_and_wrong_codes_never_touch_the_owners_code(app, store):
    owner_browser(app, store)
    owner = TestClient(app.app)                      # the owner on any browser: its reset is bound to that browser
    assert forgot(owner, OWNER).status_code == 202
    code = last_code(store, 'ana@example.com')
    stranger = TestClient(app.app)
    cooldown_over(store)
    assert forgot(stranger, STRANGER).status_code == 202            # the stranger's own code, mailed to the owner
    assert len([r for r in outbox(store, 'ana@example.com') if r['purpose'] == 'reset']) == 2
    wrong = '000000' if code != '000000' else '111111'
    for c in (stranger, TestClient(app.app)):                       # with its own code, and with none at all
        for _ in range(5):
            assert error_code(reset(c, wrong, STRANGER)) == 'CODE_INVALID_OR_EXPIRED'
    r = reset(owner, code, OWNER)                                   # the owner's code: live, its 5 tries untouched
    assert r.status_code == 200, r.text


def test_a_code_typed_in_another_browser_is_refused_with_words_that_say_where_to_ask(app, store):
    owner_browser(app, store)
    asked, typed = TestClient(app.app), TestClient(app.app)
    forgot(asked, OWNER)
    r = reset(typed, last_code(store, 'ana@example.com'), OWNER)
    assert error_code(r) == 'CODE_INVALID_OR_EXPIRED'
    assert 'another browser' in r.json()['error']['message'] and 'on this page' in r.json()['error']['message']
    assert reset(asked, last_code(store, 'ana@example.com'), OWNER).status_code == 200


def test_every_forgot_answer_sets_the_reset_cookie_alike_whatever_the_address(app, store):
    owner_browser(app, store)

    def shape(r):
        cookie = r.headers.get('set-cookie', '')
        return r.status_code, r.json(), re.sub(r'edge_reset=[0-9a-f]{64}', 'edge_reset=<token>', cookie)
    known, unknown = forgot(TestClient(app.app), OWNER), forgot(TestClient(app.app), OWNER, 'nobody@example.com')
    assert shape(known) == shape(unknown) and 'edge_reset=<token>' in shape(known)[2]
    assert 'HttpOnly' in shape(known)[2] and 'SameSite=strict' in shape(known)[2]


def test_a_code_made_before_the_binding_still_finishes_its_reset(app, store, on):
    """Codes an older edge-bff made (binding_hash NULL) stay usable for their 300 s from any browser, as before."""
    owner_browser(app, store)
    user_id = db(store, "SELECT user_id FROM edge_bff.users WHERE email = 'ana@example.com'")[0]['user_id']
    flows = app.app.state.auth_flows
    db(store, "INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, expires_at) "
              "VALUES ('reset', %s, %s, now() + interval '300 seconds')", user_id, flows.store.code_hash(user_id, 'reset', '424242'))
    assert reset(TestClient(app.app), '424242', OWNER).status_code == 200


# ---- the address's code emails ----------------------------------------------------------------------------------------

def test_one_client_spends_at_most_its_part_of_an_addresss_day(app, store):
    owner_browser(app, store)
    stranger = TestClient(app.app)
    for _ in range(12):
        cooldown_over(store)
        forgot(stranger, STRANGER)
    assert len([r for r in outbox(store, 'ana@example.com') if r['purpose'] == 'reset']) == throttle.SEND_EMAIL_CLIENT.allowed
    cooldown_over(store)
    owner = TestClient(app.app)                                      # the owner, anywhere else, on a new browser
    forgot(owner, OWNER)
    assert reset(owner, last_code(store, 'ana@example.com'), OWNER).status_code == 200


def code_mails(store):
    """The code emails of the address today: its registration's and its resets' (one SEND_EMAIL budget)."""
    return len([r for r in outbox(store, 'ana@example.com') if r['purpose'] in ('register', 'reset')])


def test_the_owners_known_browser_gets_its_code_after_strangers_spent_the_addresss_day_and_a_new_one_does_not(app, store):
    owner = owner_browser(app, store)                  # its registration's code: 1 of the address's 10
    for client in ('203.0.113.7', '203.0.113.8', '203.0.113.9'):     # three strangers: 4 + 4 + 1 = the other 9
        stranger = TestClient(app.app)
        for _ in range(5):
            cooldown_over(store)
            forgot(stranger, client)
    assert code_mails(store) == throttle.SEND_EMAIL.allowed
    cooldown_over(store)
    # the residual (ERRORS M517): a browser the account never signed in on waits for the day, as before the fix
    newcomer = TestClient(app.app)
    forgot(newcomer, ELSEWHERE)
    assert code_mails(store) == throttle.SEND_EMAIL.allowed
    # the owner's own browser asks under its own day (DEVICE_MAIL) and finishes its reset
    forgot(owner, OWNER)
    assert code_mails(store) == throttle.SEND_EMAIL.allowed + 1
    assert reset(owner, last_code(store, 'ana@example.com'), OWNER).status_code == 200


# ---- registration -------------------------------------------------------------------------------------------------------

def test_one_strangers_registration_of_an_address_does_not_hold_the_owners_back(app, store):
    stranger = TestClient(app.app)
    body = {'username': 'eve_one', 'first_name': 'Eve', 'last_name': 'One', 'email': 'ana@example.com',
            'phone': '0812 3456 7890', 'password': 'the strangers password', 'password_repeat': 'the strangers password'}
    assert stranger.post('/api/v1/auth/register', headers=at(STRANGER), json=body).status_code == 202
    cooldown_over(store)
    # within the same hour, the owner's own registration from its own place is made and mailed (it was held for the
    # hour when the count was the address's alone)
    assert register(app).status_code == 202
    assert len([r for r in outbox(store, 'ana@example.com') if r['purpose'] == 'register']) == 2
    r = app.post('/api/v1/auth/register/verify', headers=ORIGIN,
                 json={'email': 'ana@example.com', 'code': last_code(store, 'ana@example.com')})
    assert r.status_code == 200 and r.json()['username'] == 'ana_putri', r.text


@pytest.mark.parametrize('limit', [throttle.SEND_EMAIL_CLIENT, throttle.DEVICE_MAIL, throttle.DEVICE_SIGNIN])
def test_the_new_limits_are_counted_in_existing_scopes(limit):
    # the table's scope CHECK lists its scopes (20261119_071); the new counters live inside existing ones
    assert limit.scope in ('signin_email', 'send_email') and limit.enforced
