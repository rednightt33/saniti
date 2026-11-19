"""EXEC-MU-ACCOUNTS re-check round 2 (checker C2-TRACE): two edge-bff services on one database.

The user plans a beta site (the service edge-bff, following main) and a live site (a second edge-bff service, moved to a
tested version on the user's go), both on the same PostgreSQL and the same workers (EXEC.md EXEC-MU-ACCOUNTS,
"Production environment", details open). Both services run the same start-up step and the same queue loops over the
shared edge_bff tables, each with its own configuration (EDGE_MULTIUSER, EDGE_PASSWORD_VERIFIER, EDGE_ADMIN_OWNERS) and
its own code version (releases.json, allow.FAMILIES).

These tests fail on ae9a1d8f: the result of a request depends on which service's start or loop touched the shared row.
Rule they hold: a row made under one site's rules is read and changed only under those rules. They wait in
verification/edge_multiuser/access_tiers/pending/ until the beta/live design is decided (pending/README.md).
"""
import dataclasses

import psycopg
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


def test_a_job_queued_on_the_switch_on_site_is_dispatched_when_the_switch_off_site_claims_it(on, store, workers):
    """Beta has EDGE_MULTIUSER on, live has it off (the order of a switch-on tried on beta first). A paid account's
    backtest queued on beta must run whichever service's loop claims it. Today the live loop claims it and resolves its
    owner with live's switch-off mapping (principal.owner_principal -> switch_off_principal: an owner EDGE_ADMIN_OWNERS
    does not list holds nothing), so the paid account's job ends FAILED CAPABILITY_REQUIRED backtest.run without any
    worker call."""
    live = dataclasses.replace(on, multiuser=False)
    with TestClient(create_app(on, store, FakeOrc())) as beta:
        paid_user(store, 'alice')
        h = sign_in(beta, 'alice', 'alice-password')
        job = beta.post(BT, headers=h, json={**single(), 'client_request_id': 'beta-job'})
        assert job.status_code == 202, job.text
    before = len(workers[0].posted('/v1/jobs'))
    with TestClient(create_app(live, store, FakeOrc())) as site:
        run_next(site)                                     # the live service's queue loop takes the oldest queued job
    row = db(store, 'SELECT state, error FROM edge_bff.backtest_jobs WHERE request_id = %s', job.json()['request_id'])[0]
    assert (row['error'] or {}).get('code') != 'CAPABILITY_REQUIRED', row
    assert len(workers[0].posted('/v1/jobs')) == before + 1, 'the paid account\'s job never reached the worker'


def test_a_start_of_the_switch_off_site_keeps_the_password_user_one_set_on_the_switch_on_site(on, settings, store):
    """User #1 (the seed, EDGE_OWNER) signs in on beta (switch on) with the password of its account identity; a password
    change or reset there replaces that identity's verifier (auth_flows.py FlowStore._set_password). Today every start of
    live (switch off) copies live's EDGE_PASSWORD_VERIFIER over it (accounts.py AccountStore.seed, the `elif not
    multiuser` branch), so the admin's beta password silently reverts to the environment's at each live deploy."""
    with TestClient(create_app(on, store, FakeOrc())):
        pass                                               # beta starts first: user #1 is seeded
    chosen = password_verifier('the-admins-new-beta-password')
    db(store, '''UPDATE edge_bff.identities SET verifier = %s WHERE provider = 'password' AND user_id =
        (SELECT user_id FROM edge_bff.users WHERE owner_key = %s)''', chosen, on.owner)   # a change made on beta
    with TestClient(create_app(settings, store, FakeOrc())):
        pass                                               # live (switch off) is deployed
    assert seed_verifier(store, on.owner) == chosen
    assert verify_password('the-admins-new-beta-password', seed_verifier(store, on.owner))
