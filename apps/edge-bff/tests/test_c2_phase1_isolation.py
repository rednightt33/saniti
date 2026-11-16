"""C2 Phase 1 isolation check (EXEC-MU-ACCOUNTS; CONTRACT.md section 4 "Registration rules"): a registration of an
address whose account is still pending replaces that account's password, requested username, names and phone
(auth_flows.py FlowStore.register, the `if user:` branch) and issues a new code to the same inbox. So someone who cannot
read the inbox can register the victim's address right after the victim did: the victim receives the second code,
enters it (the verify page takes the newest one), is signed in, and the account is active with the other party's
password and username. That party then signs in to the victim's verified account (account pre-hijacking).

The rule: whoever proves the code owns the account; a party that never saw the code never gets a working sign-in to
it."""
from test_auth_flows import PASSWORD, app, cooldown_over, last_code, on, register, verify  # noqa: F401 - fixtures
from test_edge import ORIGIN

VICTIM = 'victim@example.com'
OTHER_PASSWORD = 'another long password'


def sign_in(c, login, password):
    return c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': login, 'password': password})


def test_a_second_registration_of_a_pending_address_never_gives_its_author_the_verified_account(app, store):
    # B1b fix round: the other party registers from its own browser (one TestClient is one browser)
    from fastapi.testclient import TestClient
    other = TestClient(app.app)
    assert register(app, VICTIM, 'victim_real', PASSWORD).status_code == 202
    own = last_code(store, VICTIM)
    cooldown_over(store)                                    # the 60 s send limit of the address has passed
    assert register(other, VICTIM, 'hijacker_name', OTHER_PASSWORD).status_code == 202
    # the newest code in the inbox is the other party's registration's: it does not open the victim's registration
    assert verify(app, last_code(store, VICTIM), VICTIM).status_code == 400
    # the victim enters the code of its own registration and is signed in to the now active account
    assert verify(app, own, VICTIM).status_code == 200
    app.cookies.clear()
    hijack = sign_in(app, 'hijacker_name', OTHER_PASSWORD)
    by_email = sign_in(app, VICTIM, OTHER_PASSWORD)
    assert hijack.status_code == 401 and by_email.status_code == 401, (
        'the second registrant, who never saw the code, signs in to the verified account: '
        f'{hijack.status_code}/{by_email.status_code}')
