"""EXEC-MU-ACCOUNTS Phase 3b (CONTRACT.md 8b "3b in detail"): the worker context's allow, limits and digest
(app/allow.py), built from a principal only. The wire of each worker call is checked in test_backtest.py and
test_screener.py; here the expansion itself, against a test release file that holds a lab id."""
import types

import pytest

from app import allow, errors, releases
from app.allow import FAMILIES, KINDS, allow_of, context_of, digest, named
from app.principal import EVERYTHING, Principal, account_principal, switch_off_principal

TEST_RELEASES = {'schema_version': 1, 'items': [
    {'kind': 'indicator', 'id': 'I02', 'stage': 'released'}, {'kind': 'indicator', 'id': 'I01', 'stage': 'released'},
    {'kind': 'indicator', 'id': 'I90', 'stage': 'lab'},
    {'kind': 'flow_indicator', 'id': 'FL11', 'stage': 'released'}, {'kind': 'flow_indicator', 'id': 'FL90', 'stage': 'lab'},
    {'kind': 'candle_pattern', 'id': 'CP01', 'stage': 'released'},
    {'kind': 'screener_metric', 'id': 'rsi', 'stage': 'released'}, {'kind': 'screener_metric', 'id': 'lab_m', 'stage': 'lab'},
    {'kind': 'screener_preset', 'id': 'p1', 'stage': 'released'}]}
SETTINGS = types.SimpleNamespace(owner='owner-1', admin_owners=('owner-1',), multiuser=False)


@pytest.fixture(autouse=True)
def test_releases(monkeypatch):
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases(TEST_RELEASES))


def principal(grants):
    """A switch-on principal of an account whose plan resolved to these grants ({key: (kind, value)})."""
    return account_principal({'user_id': 7, 'owner_key': 'u_' + 'a' * 32, 'username': 'alice', 'role': 'user',
                              'status': 'active', 'plan_key': 'p', 'versions': {},
                              'grants': {k: {'kind': kind, 'value': v} for k, (kind, v) in grants.items()}})


def items(worker, value, kinds=KINDS):
    return {FAMILIES[worker][k]: ('items', value) for k in kinds}


def test_everything_gives_star_for_every_kind_of_both_workers():
    owner = switch_off_principal(SETTINGS, 'owner-1')                       # the switch-off owner EDGE_ADMIN_OWNERS lists
    assert EVERYTHING in owner.capabilities
    for worker in ('backtest', 'screener'):
        assert allow_of(owner, worker) == {k: '*' for k in KINDS}
    assert context_of(owner, 'backtest') == {'rights': ['flow_point_in_time'], 'allow': {k: '*' for k in KINDS}, 'limits': {}}
    star = principal({'*': ('flag', True)})                                 # a plan that holds '*'
    assert allow_of(star, 'screener') == {k: '*' for k in KINDS}


def test_a_switch_off_owner_without_the_admin_listing_is_allowed_nothing():
    other = switch_off_principal(SETTINGS, 'owner-2')
    assert context_of(other, 'backtest') == {'rights': [], 'allow': {k: [] for k in KINDS}, 'limits': {}}


def test_a_paid_plan_of_released_stages_gets_every_released_id_and_no_lab_id():
    paid = principal({**items('backtest', {'stages': ['released']}), **items('screener', {'stages': ['released']})})
    for worker in ('backtest', 'screener'):
        assert allow_of(paid, worker) == {'indicator': ['I01', 'I02'], 'flow_indicator': ['FL11'],
                                          'candle_pattern': ['CP01'], 'screener_metric': ['rsi']}
    assert context_of(paid, 'screener')['rights'] == [] and context_of(paid, 'screener')['limits'] == {}


def test_all_true_is_star_and_ids_only_are_those_ids_of_the_file():
    p = principal({'backtest.indicator': ('items', {'all': True}),
                   'backtest.flow_indicator': ('items', {'ids': ['FL90', 'FL11']}),
                   'backtest.candle_pattern': ('items', {'ids': []}),
                   'screener.metric': ('items', {'ids': ['lab_m', 'not_in_the_file']})})
    assert allow_of(p, 'backtest') == {'indicator': '*', 'flow_indicator': ['FL11', 'FL90'], 'candle_pattern': [],
                                       'screener_metric': ['lab_m']}
    # the Screener reads its own families for three kinds and shares screener.metric
    assert allow_of(p, 'screener') == {'indicator': [], 'flow_indicator': [], 'candle_pattern': [], 'screener_metric': ['lab_m']}


def test_the_digest_follows_rights_allow_and_limits():
    paid = context_of(principal(items('screener', {'stages': ['released']})), 'screener')
    owner = context_of(switch_off_principal(SETTINGS, 'owner-1'), 'screener')
    assert digest(paid) == digest(dict(paid)) and digest(paid) != digest(owner)
    assert digest(paid) != digest({**paid, 'allow': {**paid['allow'], 'indicator': ['I01']}})
    assert digest(paid) != digest({**paid, 'limits': {'max_conditions': 5}})
    assert digest(paid) != digest({**paid, 'rights': ['flow_point_in_time']})
    assert allow.NOTHING == {'rights': [], 'allow': {k: [] for k in KINDS}, 'limits': {}}


def test_a_worker_capability_refusal_gets_the_display_name(monkeypatch):
    monkeypatch.setattr(errors, '_names', {'backtest.indicator': 'Backtest indicators'})
    refused = {'code': 'CAPABILITY_REQUIRED', 'field': 'entry.conditions[0].indicator', 'message': 'I07 is not in the plan.',
               'details': {'kind': 'indicator', 'id': 'I07', 'capability': 'backtest.indicator:I07'}}
    assert named(refused) == {**refused, 'details': {**refused['details'], 'display_name': 'Backtest indicators: I07'}}
    assert named({'code': 'INVALID_CONDITION', 'field': 'x'}) == {'code': 'INVALID_CONDITION', 'field': 'x'}
    assert named({'code': 'CAPABILITY_REQUIRED'}) == {'code': 'CAPABILITY_REQUIRED'}      # nothing to name
    monkeypatch.setattr(errors, '_names', {})
    assert named(refused)['details']['display_name'] == errors.UNNAMED                    # never the internal key


def test_the_principal_dataclass_has_what_allow_reads():
    p = Principal(user_id=None, owner_key='x', username=None, role='user', plan_key=None, status='unknown',
                  expires_at=None, mfa_ok=False, capabilities=frozenset(), version='none')
    assert allow_of(p, 'backtest') == {k: [] for k in KINDS}
