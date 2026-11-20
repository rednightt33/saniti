"""EXEC-MU-ACCOUNTS Phase 3b (CONTRACT.md 8b "3b in detail"): the worker context's allow, limits and digest
(app/allow.py), built from a principal only. The wire of each worker call is checked in test_backtest.py and
test_screener.py; here the expansion itself, against a test release file that holds a lab id."""
import re
import types
from pathlib import Path

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
    {'kind': 'screener_preset', 'id': 'p1', 'stage': 'released'}],
    'tabs': [{'id': t, 'stage': st} for t, st in releases.load().tabs().items()]}     # the repository's tabs
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
    p = principal({'terminal.indicator': ('items', {'all': True}),
                   'terminal.flow_indicator': ('items', {'ids': ['FL90', 'FL11']}),
                   'backtest.candle_pattern': ('items', {'ids': ['CP01']}),
                   'screener.metric': ('items', {'ids': ['lab_m', 'not_in_the_file']})})
    assert allow_of(p, 'backtest') == {'indicator': '*', 'flow_indicator': ['FL11', 'FL90'], 'candle_pattern': ['CP01'],
                                       'screener_metric': ['lab_m']}
    # the 3b follow-up (user decision 2026-11-18, "gate-nya adalah terminal"): both workers read the Terminal's
    # indicator and Flow grants and share screener.metric; the candlestick patterns keep a family per worker
    assert allow_of(p, 'screener') == {'indicator': '*', 'flow_indicator': ['FL11', 'FL90'], 'candle_pattern': [],
                                       'screener_metric': ['lab_m']}


def test_the_indicator_and_flow_families_of_both_workers_are_the_terminals():
    """CONTRACT.md 8b "3b follow-up": one source, so no tab can differ from the Terminal; the removed tab families
    (migration 20261118_001) grant nothing even when a stale row would still name one."""
    for worker in ('backtest', 'screener'):
        assert FAMILIES[worker]['indicator'] == 'terminal.indicator'
        assert FAMILIES[worker]['flow_indicator'] == 'terminal.flow_indicator'
    stale = principal({'backtest.indicator': ('items', {'all': True}), 'screener.flow_indicator': ('items', {'all': True})})
    for worker in ('backtest', 'screener'):
        assert allow_of(stale, worker) == {k: [] for k in KINDS}


ROOT = Path(__file__).resolve().parents[3]


def worker_families(path, name):
    """A worker's family table ({kind: family}) read from its TypeScript source as data."""
    src = (ROOT / path).read_text(encoding='utf-8')
    block = re.search(name + r'[^=]*= (?:Object\.freeze\()?\{(.*?)\}', src, re.S)
    assert block, f'{path}: {name} not found'
    return dict(re.findall(r"(\w+): '([a-z_.]+)'", block.group(1)))


def test_each_worker_names_the_family_edge_bff_checks_in_its_refusal():
    """A worker's 403 CAPABILITY_REQUIRED carries details.capability = <family>:<id>; the family must be the one
    allow.FAMILIES expands for that worker, so the refusal names the grant the plan lacks and its display_name is the
    catalog's (errors.display_name of a family that has a capabilities row)."""
    assert worker_families('apps/backtest-worker/src/access.ts', 'export const FAMILY') == FAMILIES['backtest']
    assert worker_families('apps/screener-worker/src/run.ts', 'export const CAPABILITY_FAMILY') == FAMILIES['screener']


def test_the_digest_follows_rights_allow_and_limits():
    paid = context_of(principal(items('screener', {'stages': ['released']})), 'screener')
    owner = context_of(switch_off_principal(SETTINGS, 'owner-1'), 'screener')
    assert digest(paid) == digest(dict(paid)) and digest(paid) != digest(owner)
    assert digest(paid) != digest({**paid, 'allow': {**paid['allow'], 'indicator': ['I01']}})
    assert digest(paid) != digest({**paid, 'limits': {'max_conditions': 5}})
    assert digest(paid) != digest({**paid, 'rights': ['flow_point_in_time']})
    assert allow.NOTHING == {'rights': [], 'allow': {k: [] for k in KINDS}, 'limits': {}}


def test_a_worker_capability_refusal_gets_the_display_name(monkeypatch):
    monkeypatch.setattr(errors, '_names', {'terminal.indicator': 'Terminal indicators'})
    refused = {'code': 'CAPABILITY_REQUIRED', 'field': 'entry.conditions[0].indicator', 'message': 'I07 is not in the plan.',
               'details': {'kind': 'indicator', 'id': 'I07', 'capability': 'terminal.indicator:I07'}}
    assert named(refused) == {**refused, 'details': {**refused['details'], 'display_name': 'Terminal indicators: I07'}}
    assert named({'code': 'INVALID_CONDITION', 'field': 'x'}) == {'code': 'INVALID_CONDITION', 'field': 'x'}
    assert named({'code': 'CAPABILITY_REQUIRED'}) == {'code': 'CAPABILITY_REQUIRED'}      # nothing to name
    monkeypatch.setattr(errors, '_names', {})
    assert named(refused)['details']['display_name'] == errors.UNNAMED                    # never the internal key


def test_a_relayed_message_that_carries_the_internal_key_is_worded_by_edge_bff(monkeypatch):
    """Re-check R1-34: a service's message that names the capability key (or its family) reaches the person in
    edge-bff's words, with the item's name; a message without the key stays the worker's (it names the condition)."""
    monkeypatch.setattr(errors, '_names', {'terminal.indicator': 'Terminal indicators'})
    for message in ('I07 is not in the plan (terminal.indicator:I07).', 'needs terminal.indicator', '', None):
        refused = {'code': 'CAPABILITY_REQUIRED', 'field': 'entry.conditions[0].indicator', 'message': message,
                   'details': {'kind': 'indicator', 'id': 'I07', 'capability': 'terminal.indicator:I07'}}
        out = named(refused)
        assert out['message'] == ('Terminal indicators: I07 is not part of your EDGE plan. Upgrade the plan to use it; '
                                  'you are still signed in.'), message
        assert out['field'] == refused['field'] and out['details']['capability'] == 'terminal.indicator:I07'


def test_the_principal_dataclass_has_what_allow_reads():
    p = Principal(user_id=None, owner_key='x', username=None, role='user', plan_key=None, status='unknown',
                  expires_at=None, mfa_ok=False, capabilities=frozenset(), version='none')
    assert allow_of(p, 'backtest') == {k: [] for k in KINDS}
