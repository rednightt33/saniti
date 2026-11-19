"""EXEC-MU-ACCOUNTS re-check round 2 (checker C2-TRACE, ERRORS R2-38): two edge-bff services on one database.

The user's plan (EXEC.md EXEC-MU-ACCOUNTS, "Production environment", 2026-11-19): a beta site (the service edge-bff, its
Railway address, the admin only, EDGE_MULTIUSER off as today) and a live site (edge-bff-live, the user's domain,
EDGE_MULTIUSER on), both on the same PostgreSQL and the same workers. EDGE_SITE (beta|live) tells them apart. Both run
the same start-up step and the same queue loops over the shared edge_bff tables, each with its own configuration and
its own code version.

These tests failed on ae9a1d8f (in verification/edge_multiuser/access_tiers/pending/ until the design was decided): the
result of a request depended on which service's start or loop touched the shared row. Rule they hold: a row made under
one site's rules is read and changed only under those rules.

Changed with the decided design (fix round, track site): the checker wrote them for a beta with the switch on and a live
site with it off, the order the decision reversed (config.validate now refuses both outside a developer machine). They
hold the same rule for the decided pairing: a live site's queued job is claimed by the live site's loop only, and a
start of the beta (switch off) keeps the password user #1 set on the live site.
"""
import dataclasses

from fastapi.testclient import TestClient

from app.main import create_app
from app.security import password_verifier, verify_password
from conftest import FakeOrc
from test_backtest import run_next, single
from test_phase3a_gates import BT, paid_user
from test_principal import db, on, sign_in, workers  # noqa: F401 - the fixtures


def seed_verifier(store, owner):
    return db(store, '''SELECT i.verifier FROM edge_bff.identities i JOIN edge_bff.users u ON u.user_id = i.user_id
        WHERE u.owner_key = %s AND i.provider = 'password' ''', owner)[0]['verifier']


def sites(on):
    """(beta, live): the beta with the switch off (as today), the live site with it on (EDGE_SITE=live). The live site
    is the one after the launch (EDGE_PRELAUNCH=false): the pre-launch mode, on by default on live since the decision of
    2026-11-19 ("Terbuka, tapi belum bisa mendaftar"; track guest), lets only the admin and test accounts sign in, and a
    paid account signs in here."""
    return dataclasses.replace(on, multiuser=False), dataclasses.replace(on, site='live', prelaunch_enabled=False)


def test_a_job_queued_on_the_live_site_is_dispatched_by_the_live_site_only(on, store, workers):
    """A paid account's backtest queued on the live site must run under the live site's rules. Before the fix the beta's
    loop could claim it and resolve its owner with the beta's switch-off mapping (principal.owner_principal ->
    switch_off_principal: an owner EDGE_ADMIN_OWNERS does not list holds nothing), so the job ended FAILED
    CAPABILITY_REQUIRED backtest.run without any worker call. Now the beta's loop never claims it (backtest_jobs.site),
    and the live site's loop dispatches it."""
    beta, live = sites(on)
    with TestClient(create_app(live, store, FakeOrc())) as site:
        paid_user(store, 'alice')
        h = sign_in(site, 'alice', 'alice-password')
        job = site.post(BT, headers=h, json={**single(), 'client_request_id': 'live-job'})
        assert job.status_code == 202, job.text
    request_id = job.json()['request_id']
    before = len(workers[0].posted('/v1/jobs'))
    with TestClient(create_app(beta, store, FakeOrc())) as site:
        assert site.app.state.backtests.store.claim(90) is None      # the beta's queue loop takes nothing of the live's
    row = db(store, 'SELECT state, error, site FROM edge_bff.backtest_jobs WHERE request_id = %s', request_id)[0]
    assert (row['state'], row['site']) == ('QUEUED', 'live'), row
    with TestClient(create_app(live, store, FakeOrc())) as site:
        assert run_next(site) == request_id                          # the live site's loop takes it
    row = db(store, 'SELECT state, error FROM edge_bff.backtest_jobs WHERE request_id = %s', request_id)[0]
    assert (row['error'] or {}).get('code') != 'CAPABILITY_REQUIRED', row
    assert len(workers[0].posted('/v1/jobs')) == before + 1, 'the paid account\'s job never reached the worker'


def test_a_start_of_the_beta_site_keeps_the_password_user_one_set_on_the_live_site(on, store):
    """User #1 (the seed, EDGE_OWNER) signs in on the live site (switch on) with the password of its account identity; a
    password change or reset there replaces that identity's verifier (auth_flows.py FlowStore._set_password). Before
    the fix every start of the beta (switch off) copied the beta's EDGE_PASSWORD_VERIFIER over it (accounts.py
    AccountStore.seed, the `elif not multiuser` branch), so the admin's live password silently reverted to the
    environment's at each beta deploy. Now the seed copies only over its own copy (identities.seed_verifier_sha256)."""
    beta, live = sites(on)
    with TestClient(create_app(live, store, FakeOrc())):
        pass                                               # the live site starts first: user #1 is seeded
    chosen = password_verifier('the-admins-new-live-password')
    db(store, '''UPDATE edge_bff.identities SET verifier = %s WHERE provider = 'password' AND user_id =
        (SELECT user_id FROM edge_bff.users WHERE owner_key = %s)''', chosen, live.owner)   # a change made on live
    with TestClient(create_app(beta, store, FakeOrc())):
        pass                                               # the beta (switch off) is deployed
    assert seed_verifier(store, live.owner) == chosen
    assert verify_password('the-admins-new-live-password', seed_verifier(store, live.owner))
