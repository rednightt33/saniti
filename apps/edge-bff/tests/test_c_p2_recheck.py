"""EXEC-MU-ACCOUNTS ultracode re-check of Phase 2 (checker C-P2, 2026-11-18; user: "Cek juga fase sebelumnya ... Jangan
sampai fase 3C di bangun dari broken block fase2 sebelumnya"). Failing tests of VERIFIED findings in the Phase 2
entitlements (app/principal.py, app/accounts.py; CONTRACT.md sections 2, 8 and 8a) that Phase 3c builds on:

1. Principal.refusal() decides PLAN_EXPIRED only for flags and item families. For a list or a limit (the Terminal's
   terminal.tickers and terminal.history_days, the two restrictions 3c refuses through p.refusal in main.py
   refuse_capability) it always answers CAPABILITY_REQUIRED, also when the plan that ended set no such restriction
   (no row = every ticker, no history limit). CONTRACT.md 8a: "PLAN_EXPIRED is the refusal code when a route needs a
   capability only the expired plan held". The same expired account is told "renew" for the broker data set and
   "upgrade" for a second ticker or older history.
2. read_grants gives every principal whose list value is malformed the same list object (RESTRICTIVE['list']): a
   consumer that adds to the list it was handed (p.limit('terminal.tickers')) widens the next such principal, another
   account included.
3. seed_subscription counts a plan holding '*' = false (a flag may be false since the M480 fix round) as holding every
   capability: one such row makes the seed plan ambiguous, and an admin plan whose '*' is false is still given to
   user #1.
"""
import logging

import pytest

from app import principal as principal_module
from app.accounts import AccountStore
from app.principal import Auth, account_principal, read_grants
from test_plan_catalog import on, subscribe  # noqa: F401 - the fixture `on`
from test_principal import db, make_user


# ---- 1. PLAN_EXPIRED for the Terminal's list and limit restrictions -------------------------------------------------

def test_an_ended_plan_without_a_ticker_list_or_history_limit_gives_plan_expired(on, store):
    alice = make_user(store, 'alice', 'alice-password')
    # the plan that grants the broker data set and sets neither restriction (found by data, as the code does)
    plan = db(store, '''SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = 'terminal.dataset'
        AND value = '{"all": true}'::jsonb''')[0]['plan_key']
    held = {r['capability_key'] for r in db(store, 'SELECT capability_key FROM edge_bff.plan_capabilities '
                                                   'WHERE plan_key = %s', plan)}
    assert '*' not in held and not held & {'terminal.tickers', 'terminal.history_days'}
    subscribe(store, alice['user_id'], plan, starts="now() - interval '2 days'", expires="now() - interval '1 second'")
    p = Auth(on, store).owner_principal(alice['owner_key'])
    assert p.expired_plan == plan
    # the default plan restricts both: one ticker, 730 days
    assert isinstance(p.limit('terminal.tickers'), list) and isinstance(p.limit('terminal.history_days'), int)
    # an item family the ended plan held: renewing it is the fix (passes today)
    assert p.refusal('terminal.dataset:broker').code == 'PLAN_EXPIRED'
    # the ended plan showed every ticker and every date: renewing it is the fix here too (fails today:
    # CAPABILITY_REQUIRED, "Upgrade the plan")
    for key in ('terminal.tickers', 'terminal.history_days'):
        refused = p.refusal(key)
        assert (key, refused.code) == (key, 'PLAN_EXPIRED'), refused.details
        assert refused.details.get('expired_plan') == plan


def test_a_terminal_window_of_0_days_is_judged_against_the_ended_plans_own_window(on, store, monkeypatch):
    """R1-23 (the user 2026-11-22, group A "OK fix it"): the 0-day refusal of the Terminal's dated routes passed no
    amount, so an account whose ended plan had its own window (here the windowed plan's days) was told "upgrade"
    (CAPABILITY_REQUIRED) where renewing the plan is the way (PLAN_EXPIRED). The database refuses a window of 0
    (capability_value_check: 1 to 36600), so 0 reaches this refusal only as the value of a limit that cannot be read
    (terminal_access._limit), as here. A dated request asks at least one day; the history route asks the whole history.
    And a refusal carries what was asked (refused.asked), which main.py refuse_capability uses when it builds it again."""
    from app import terminal_access
    alice = make_user(store, 'alice_w0', 'alice-password')
    windowed = db(store, "SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = 'terminal.history_days' "
                         "AND value::text ~ '^[1-9][0-9]*$' ORDER BY plan_key LIMIT 1")[0]['plan_key']
    subscribe(store, alice['user_id'], windowed, starts="now() - interval '2 days'", expires="now() - interval '1 second'")
    p = Auth(on, store).owner_principal(alice['owner_key'])
    assert p.expired_plan == windowed
    real = terminal_access.capabilities
    monkeypatch.setattr(terminal_access, 'capabilities', lambda q: {**real(q), 'history_days': 0})
    with pytest.raises(Exception) as dated:
        terminal_access.check(p, 'POST', 'files', {}, b'{"ticker": "BBCA", "dataset": "prices"}')
    assert (dated.value.code, dated.value.details.get('expired_plan')) == ('PLAN_EXPIRED', windowed)
    refused = p.refusal('terminal.history_days', amount=100000)
    assert refused.code == 'CAPABILITY_REQUIRED' and refused.asked == (None, 100000)
    assert p.refusal('terminal.history_days', *refused.asked).code == 'CAPABILITY_REQUIRED'


# ---- 2. the most restrictive list is never shared between principals ------------------------------------------------

def row_of(user_id, grants):
    return {'user_id': user_id, 'owner_key': 'u_' + f'{user_id:024x}', 'username': f'user{user_id}', 'role': 'user',
            'status': 'active', 'plan_key': 'p', 'grants': grants, 'versions': {}, 'mfa_passed_at': None}


def test_a_malformed_list_reads_as_a_new_empty_list_for_each_principal(caplog):
    malformed = {'terminal.view': {'kind': 'flag', 'value': True},
                 'terminal.tickers': {'kind': 'list', 'value': 'BBCA'}}        # a string, not an array
    try:
        with caplog.at_level(logging.WARNING, 'edge_bff.principal'):
            a = account_principal(row_of(1, malformed))
            given = a.limit('terminal.tickers')
            assert given == []
            try:
                given.append('BBRI')           # a consumer that adds to the list it was given (a benchmark ticker)
            except AttributeError:
                return                         # an immutable value cannot leak
            b = account_principal(row_of(2, malformed))                       # another account
        assert b.limit('terminal.tickers') == [], 'a list one principal changed reached another account'
        assert read_grants(malformed)[0]['terminal.tickers'] == []
    finally:
        restrictive = principal_module.RESTRICTIVE.get('list')
        if isinstance(restrictive, list):
            restrictive.clear()                # never leave the module's value changed for the other tests


# ---- 3. the seed plan is the one plan whose '*' is true -------------------------------------------------------------

def star_plans(store):
    return {r['plan_key']: r['value'] for r in db(store, '''SELECT plan_key, value FROM edge_bff.plan_capabilities
        WHERE capability_key = '*' ''')}


def test_the_seed_plan_is_the_plan_whose_star_is_true(settings, store, caplog):
    seed = AccountStore(store).seed(settings.owner, settings.login, settings.password_verifier, False)
    before = star_plans(store)
    [admin] = [k for k, v in before.items() if v is True]
    other = db(store, 'SELECT plan_key FROM edge_bff.plans WHERE plan_key <> %s ORDER BY plan_key LIMIT 1',
               admin)[0]['plan_key']
    try:
        # an explicit "not everything" on another plan: the trigger accepts it (a flag may be false)
        db(store, '''INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES (%s, '*', 'false')''',
           other)
        with caplog.at_level(logging.WARNING, 'edge_bff.accounts'):
            given = AccountStore(store).seed_subscription(seed['user_id'])
        assert given == admin, f'seed plan {given!r}; log: {caplog.text}'   # fails today: None, "ambiguous"
        db(store, 'DELETE FROM edge_bff.subscriptions WHERE user_id = %s', seed['user_id'])
        db(store, 'DELETE FROM edge_bff.plan_capabilities WHERE plan_key = %s AND capability_key = %s', other, '*')
        # the one plan naming '*' says false: no plan holds every capability, so nothing is given
        db(store, '''UPDATE edge_bff.plan_capabilities SET value = 'false' WHERE plan_key = %s AND capability_key = '*' ''',
           admin)
        assert AccountStore(store).seed_subscription(seed['user_id']) is None
    finally:
        db(store, 'DELETE FROM edge_bff.subscriptions WHERE user_id = %s', seed['user_id'])
        db(store, 'DELETE FROM edge_bff.plan_capabilities WHERE plan_key = %s AND capability_key = %s', other, '*')
        db(store, '''UPDATE edge_bff.plan_capabilities SET value = 'true' WHERE plan_key = %s AND capability_key = '*' ''',
           admin)
    assert star_plans(store) == before
