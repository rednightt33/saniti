"""EXEC-MU-ACCOUNTS option A (ERRORS M513 A1, site S3, switch-on S5): scripts/edge_account_login.py sets an account's
login name and first password from the operator's values, audited. On the live site (switch on) the new login with the
new password is a right password (MFA_REQUIRED: the admin's second step) and the old name or the old password is not;
the beta (switch off) keeps its own login, which reads EDGE_PASSWORD_VERIFIER, and its seed keeps the account's new
password at its next start. A taken, reserved or malformed name, a short password or an unknown account change nothing
(exit 1). The script's username rule is the site's own (app/accounts.py)."""
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import accounts
from app.main import create_app
from conftest import FakeOrc
from test_auth_flows import db, error_code
from test_beta_live_site import PASSWORD as OWNER_PASSWORD, live_of
from test_edge import ORIGIN

NEW_NAME = 'edge_k3x9q2'
NEW_PASSWORD = 'a generated first password 42'


@pytest.fixture
def operator(database, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        'edge_account_login', Path(__file__).resolve().parents[3] / 'scripts/edge_account_login.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('DATABASE_URL', database)

    def run(username, new_name=None, new_password=None):
        for name, value in (('ACCOUNT_NEW_USERNAME', new_name), ('ACCOUNT_NEW_PASSWORD', new_password)):
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)
        return module.main(['--username', username, '--reason', 'the user asked, 2026-11-20'])
    run.module = module
    return run


def sign_in(c, login, password):
    return c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': login, 'password': password})


def account(store):
    return db(store, "SELECT u.username, i.verifier, i.seed_verifier_sha256, i.sign_in_failures FROM edge_bff.users u "
                     "JOIN edge_bff.identities i USING (user_id) WHERE u.role = 'admin'")


def test_the_new_login_signs_in_on_the_live_site_and_the_beta_keeps_its_own(settings, store, operator, capsys):
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:      # seeds user #1 as 'owner'
        assert operator('owner', NEW_NAME, NEW_PASSWORD) == 0, capsys.readouterr().out
        printed = capsys.readouterr().out
        assert NEW_PASSWORD not in printed and 'scrypt$' not in printed
        first = db(store, "SELECT user_id FROM edge_bff.users WHERE role = 'admin'")[0]['user_id']
        assert json.loads(printed.strip().splitlines()[-1]) == {
            'outcome': 'set', 'user_id': first, 'username_before': 'owner', 'username_after': NEW_NAME,
            'password_set': True, 'password_opens': True, 'beta_seed_keeps_it': True}
        r = sign_in(c, NEW_NAME, NEW_PASSWORD)
        assert (r.status_code, error_code(r)) == (403, 'MFA_REQUIRED')          # the right password; then the code
        assert sign_in(c, 'owner', NEW_PASSWORD).status_code == 401              # the old name is gone
        assert sign_in(c, NEW_NAME, OWNER_PASSWORD).status_code == 401           # and the old password
    with TestClient(create_app(settings, store, FakeOrc())) as beta:            # the beta's start: its seed runs
        assert sign_in(beta, 'owner', OWNER_PASSWORD).status_code == 200        # the beta's login, as before
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        r = sign_in(c, NEW_NAME, NEW_PASSWORD)
        assert (r.status_code, error_code(r)) == (403, 'MFA_REQUIRED')          # the seed kept the new password
    audit = db(store, "SELECT action, target_user_id, before, after, reason FROM edge_bff.admin_audit")
    assert audit == [{'action': 'account.login_set', 'target_user_id': first,
                      'before': {'actor': 'operator', 'username': 'owner'},
                      'after': {'actor': 'operator', 'username': NEW_NAME, 'password_set': True},
                      'reason': 'operator: the user asked, 2026-11-20'}]


def test_a_refused_request_changes_nothing(settings, store, operator, capsys):
    with TestClient(create_app(live_of(settings), store, FakeOrc())):
        pass
    db(store, "INSERT INTO edge_bff.users(owner_key, username, email, email_verified_at, role, status) "
              "VALUES (%s, 'taken_name', 'taken@example.com', now(), 'user', 'active')", 'u_' + 'a' * 24)
    before = account(store)
    cases = [(('owner', 'taken_name', None), 'refused_username_taken'),
             (('owner', 'admin', None), 'refused_username_reserved'),
             (('owner', 'Has Space', None), 'refused_username_rule'),
             (('owner', None, 'short pw 1'), 'refused_password_short'),
             (('nobody_here', NEW_NAME, NEW_PASSWORD), 'refused_no_active_account'),
             (('owner', None, None), 'refused_nothing_to_set')]
    for args, outcome in cases:
        capsys.readouterr()
        assert operator(*args) == 1, args
        assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])['outcome'] == outcome, args
    assert account(store) == before
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.admin_audit') == [{'n': 0}]


def test_the_scripts_username_rule_is_the_sites(operator):
    assert operator.module.USERNAME.pattern == accounts.USERNAME.pattern
    assert operator.module.RESERVED_USERNAMES == accounts.RESERVED_USERNAMES
