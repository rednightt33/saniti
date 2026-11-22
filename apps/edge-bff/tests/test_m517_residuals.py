"""ERRORS M517's residuals as they stand, held for the user's decision (EXEC.md, Pending decisions UD21 and UD22).

Each test asserts today's behaviour, found by the test-out of 2026-11-22 (workflow wf_c72ae04c-a73, sign-in area,
ATK-1 and CW-2). They are not a guarantee that the behaviour is right: when the user decides (accept, a challenge, or
a change of the limits), the test changes with the decision, and its docstring names the row it answers. AGENTS.md
"Findings and fixes", rule 7: a latent gap is asked, not only held.
"""
from fastapi.testclient import TestClient

from test_a2_stranger import ELSEWHERE, OWNER, at, owner_browser, sign_in
from test_auth_flows import PASSWORD, app, cooldown_over, db, hour_over, on, outbox, register  # noqa: F401 (fixtures)
from app import throttle


def test_ud22_three_other_clients_push_the_owners_pending_registration_out_of_the_sign_in_compare(app, store):
    """UD22 (CW-2): three registrations of the same address from three other client addresses take the three places
    a sign-in compares (PENDING_CHECKED), so the owner's own pending password answers 401 and no restart email goes."""
    assert register(app).status_code == 202
    body = {'username': 'eve_one', 'first_name': 'Eve', 'last_name': 'One', 'email': 'ana@example.com',
            'phone': '0812 3456 7890', 'password': 'the strangers password', 'password_repeat': 'the strangers password'}
    for n, ip in enumerate(('198.51.100.71', '198.51.100.72', '198.51.100.73')):
        hour_over(store)
        answer = TestClient(app.app).post('/api/v1/auth/register', headers=at(ip), json={**body, 'username': f'eve_{n}'})
        assert answer.status_code == 202, answer.text
    cooldown_over(store)
    mails = len(outbox(store, 'ana@example.com'))
    answer = sign_in(TestClient(app.app), PASSWORD, ELSEWHERE, 'ana@example.com')
    assert (answer.status_code, len(outbox(store, 'ana@example.com')) - mails) == (401, 0), (
        'UD22 changed: the owner\'s pending registration is no longer pushed out; update EXEC.md UD22 and this test')


def test_ud21_a_stranger_on_the_owners_network_holds_a_browser_the_account_never_signed_in_on(app, store):
    """UD21 (ATK-1): a stranger on the owner's own network who knows the login spends the per-login limit; a browser
    the account never signed in on there then waits (429). The owner's known browser is not affected (the A2 suite)."""
    owner_browser(app, store)
    stranger = TestClient(app.app)
    for _ in range(throttle.SIGNIN_LOGIN.allowed):
        sign_in(stranger, 'guess', OWNER)
    assert sign_in(TestClient(app.app), PASSWORD, OWNER).status_code == 429, (
        'UD21 changed: a new browser on the shared network is no longer held; update EXEC.md UD21 and this test')
