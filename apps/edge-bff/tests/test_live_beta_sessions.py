"""Live checker S2 (2026-11-20): user #1 is one person on both sites. Its beta sessions are switch-off sessions of the
configured owner key without an account row (user_id NULL, app/store.py session_create), so "Sign out everywhere", a
password change and a reset on the live site end them too (app/accounts.py ACCOUNT_SESSIONS). Another owner's
switch-off session is never touched, and an ordinary account has none."""
import hashlib
import secrets

from app.accounts import AccountStore
from test_principal import db, make_user


def switch_off_session(store, owner):
    token = secrets.token_hex(16)
    hashed = hashlib.sha256(token.encode()).hexdigest()
    store.session_create(hashed, owner, 3600)
    return hashed


def live_row(store, hashed):
    return db(store, 'SELECT revoked_at IS NULL AS live FROM edge_bff.sessions WHERE token_hash = %s', hashed)[0]['live']


def test_ending_user_1s_sessions_ends_its_beta_sessions_too(settings, store):
    accounts = AccountStore(store)
    accounts.seed(settings.owner, settings.login, settings.password_verifier, True)
    seed = db(store, 'SELECT user_id FROM edge_bff.users WHERE owner_key = %s', settings.owner)[0]['user_id']
    other = make_user(store, 'someone', 'someone-password')
    beta = switch_off_session(store, settings.owner)              # the beta's session of user #1
    stranger = switch_off_session(store, 'edge-other-owner')     # a switch-off session of another owner key
    assert live_row(store, beta) and live_row(store, stranger)
    accounts.revoke_all(other['user_id'])                         # an ordinary account: nothing of user #1's
    assert live_row(store, beta)
    assert accounts.revoke_all(seed) >= 1
    assert not live_row(store, beta)
    assert live_row(store, stranger)
