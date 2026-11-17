"""EXEC-MU-ACCOUNTS Phase 2 (CONTRACT.md sections 8 and 8a): the release catalog and GET /api/v1/catalog/{kind}.

- catalog/releases.json is complete against the registries read from the repository (a new indicator, Flow indicator,
  candlestick pattern, Screener metric or preset fails here until it has an entry) and names no id they lack;
- app/releases.py: an unknown id is 'lab', a malformed file fails at load naming the problem, KIND_OF_FAMILY covers
  every item family of section 8a;
- the route returns exactly the entries the principal holds, 404 NOT_FOUND for an unknown kind, 401 signed out.

The route tests use principals whose `can` this file controls (the auth dependency overridden in the test app): the
Phase 1 Principal (app/principal.py) knows `*` and exact keys only, the item grants of section 8a ({"ids"},
{"stages"}, {"all"}) arrive with the Phase 2 principal. Two tests also go through the real sign-in with the switch off.
"""
import dataclasses
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import releases
from app.main import create_app
from app.releases import KIND_OF_FAMILY, KINDS, ReleaseFileError, Releases, stage_of
from conftest import FakeOrc
from test_edge import login

BFF = Path(__file__).resolve().parents[1]
FILE = BFF / 'catalog' / 'releases.json'


def ids(path, *keys):
    data = json.loads((BFF / path).read_text(encoding='utf-8'))
    for key in keys:
        data = data[key]
    return [row['id'] for row in data]


def registry_ids():
    """Each kind's ids from the registries the product reads (CONTRACT.md 8a, 'Kinds and their registries')."""
    indicators = ids('terminal/src/data/indRegistry.json')
    # the Backtest and Screener registries are built from indRegistry.json and must carry the same indicator ids
    assert set(ids('backtest/src/core/backtest-registry.json', 'indicators')) == set(indicators)
    assert set(ids('screener/src/core/screener-registry.json', 'indicators')) == set(indicators)
    candles = ids('backtest/src/core/candle-registry.json', 'patterns')
    assert set(ids('screener/src/core/screener-registry.json', 'candles')) == set(candles)
    return {
        'indicator': indicators,
        # the Terminal's FL01-FL52, plus the Screener's own entries (fnet, ksei_net) of screener-registry.json flows
        'flow_indicator': list(dict.fromkeys(ids('terminal/src/data/flowRegistry.json', 'indicators')
                                             + ids('screener/src/core/screener-registry.json', 'flows'))),
        'candle_pattern': candles,
        'screener_metric': ids('screener/src/core/screener-metrics.json', 'metrics'),
        'screener_preset': ids('screener/src/core/presets.json', 'presets'),
    }


def test_every_registry_id_has_an_entry_and_every_entry_names_a_registry_id():
    current = releases.load(FILE)
    registries = registry_ids()
    assert set(registries) == set(KINDS)
    listed = {kind: [e['id'] for e in current.entries(kind)] for kind in KINDS}
    missing = [(kind, i) for kind in KINDS for i in registries[kind] if i not in listed[kind]]
    assert not missing, (
        'These registry items have no release stage in apps/edge-bff/catalog/releases.json. Add one line per item to '
        '"items" (a new item starts in the lab):\n'
        + '\n'.join(f'    {{"kind": "{kind}", "id": "{i}", "stage": "lab"}},' for kind, i in missing))
    stale = [(kind, i) for kind in KINDS for i in listed[kind] if i not in registries[kind]]
    assert not stale, ('apps/edge-bff/catalog/releases.json names items no registry has; remove these entries or fix '
                       f'the id: {stale}')


def test_every_item_of_today_is_released():
    """User decision 2026-11-17: every item that exists today starts 'released'."""
    current = releases.load(FILE)
    assert {e['stage'] for kind in KINDS for e in current.entries(kind)} == {'released'}
    assert {kind: len(current.entries(kind)) for kind in KINDS} == {
        'indicator': 53, 'flow_indicator': 54, 'candle_pattern': 20, 'screener_metric': 55, 'screener_preset': 26}


def test_the_module_loads_the_repository_file_and_an_unknown_id_is_lab():
    assert releases.PATH == FILE and releases.CURRENT.entries('indicator') == releases.load(FILE).entries('indicator')
    assert stage_of('indicator', 'I01') == 'released'
    assert stage_of('flow_indicator', 'FL24') == 'released'
    assert stage_of('indicator', 'I99999') == 'lab'
    assert stage_of('no_such_kind', 'I01') == 'lab'
    with pytest.raises(KeyError):
        releases.entries('no_such_kind')


def test_kind_of_family_covers_every_item_family_of_section_8a():
    assert KIND_OF_FAMILY == {
        'terminal.indicator': 'indicator', 'backtest.indicator': 'indicator', 'screener.indicator': 'indicator',
        'terminal.flow_indicator': 'flow_indicator', 'backtest.flow_indicator': 'flow_indicator',
        'screener.flow_indicator': 'flow_indicator', 'backtest.candle_pattern': 'candle_pattern',
        'screener.candle_pattern': 'candle_pattern', 'screener.metric': 'screener_metric',
        'screener.preset': 'screener_preset'}
    assert set(KIND_OF_FAMILY.values()) == set(KINDS)
    # every item family the seed names (8a "Capability rows"), terminal.dataset and monitor.model excepted (they have
    # no release stage: data sets and models, not catalog items)
    seeded = {'terminal.indicator', 'terminal.flow_indicator', 'terminal.dataset', 'backtest.indicator',
              'backtest.flow_indicator', 'backtest.candle_pattern', 'screener.indicator', 'screener.flow_indicator',
              'screener.candle_pattern', 'screener.metric', 'screener.preset', 'monitor.model'}
    assert seeded - set(KIND_OF_FAMILY) == {'terminal.dataset', 'monitor.model'}


def item(kind='indicator', id='I01', stage='released'):
    return {'kind': kind, 'id': id, 'stage': stage}


@pytest.mark.parametrize('data, words', [
    ({'schema_version': 1, 'items': [item(), item()]}, 'repeats indicator'),
    ({'schema_version': 1, 'items': [item(kind='widget')]}, "unknown kind 'widget'"),
    ({'schema_version': 1, 'items': [item(stage='beta')]}, "unknown stage 'beta'"),
    ({'schema_version': 1, 'items': [item(id='')]}, 'non-empty id'),
    ({'schema_version': 1, 'items': [item(id=' I01')]}, 'non-empty id'),
    ({'schema_version': 1, 'items': [{'kind': 'indicator', 'id': 'I01'}]}, 'exactly kind, id and stage'),
    ({'schema_version': 1, 'items': [{**item(), 'extra': 1}]}, 'exactly kind, id and stage'),
    ({'schema_version': 2, 'items': []}, 'schema_version must be 1'),
    ({'schema_version': 1, 'items': {}}, 'items must be a list'),
    ({'schema_version': 1, 'items': [], 'stages': {}}, 'unknown top-level keys'),
    ([], 'must be a JSON object'),
])
def test_a_malformed_file_fails_at_load_with_a_clear_message(tmp_path, data, words):
    path = tmp_path / 'releases.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ReleaseFileError, match='releases.json') as caught:
        releases.load(path)
    assert words in str(caught.value)


def test_a_file_that_is_not_json_or_missing_fails_at_load(tmp_path):
    path = tmp_path / 'releases.json'
    path.write_text('{"schema_version": 1, "items": [')
    with pytest.raises(ReleaseFileError, match='not valid JSON'):
        releases.load(path)
    with pytest.raises(ReleaseFileError, match='missing'):
        releases.load(tmp_path / 'absent.json')


def test_a_lab_item_is_lab_and_entries_keep_file_order():
    r = Releases({'schema_version': 1, 'items': [item(id='I02'), item(id='I01', stage='lab'), item('screener_preset',
                                                                                                    'brk52')]})
    assert r.stage_of('indicator', 'I01') == 'lab' and r.stage_of('indicator', 'I02') == 'released'
    assert r.stage_of('indicator', 'I03') == 'lab'
    assert r.entries('indicator') == [{'id': 'I02', 'stage': 'released'}, {'id': 'I01', 'stage': 'lab'}]
    assert r.entries('candle_pattern') == []


# ---- the route ----------------------------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class StubPrincipal:
    """A principal holding the section 8a grants: `*`, flag keys, and per family an items value {"ids", "stages",
    "all"} (an item <family>:<id> is held when its id is in ids, its release stage in stages, or all is true)."""
    grants: dict
    owner_key: str = 'test-catalog-owner'

    def can(self, key):
        if '*' in self.grants or self.grants.get(key) is True:
            return True
        family, _, item_id = key.partition(':')
        value = self.grants.get(family)
        if not item_id or not isinstance(value, dict) or family not in KIND_OF_FAMILY:
            return False
        return (item_id in value.get('ids', ()) or value.get('all') is True
                or stage_of(KIND_OF_FAMILY[family], item_id) in value.get('stages', ()))


@pytest.fixture
def lab_file(tmp_path, monkeypatch):
    """A release file with one lab indicator (I02) beside released ones, in place of the repository's."""
    path = tmp_path / 'releases.json'
    path.write_text(json.dumps({'schema_version': 1, 'note': 'test', 'items': [
        item(id='I01'), item(id='I02', stage='lab'), item(id='I03'), item('flow_indicator', 'FL24'),
        item('screener_metric', 'rs'), item('screener_preset', 'brk52', 'lab')]}))
    monkeypatch.setattr(releases, 'CURRENT', releases.load(path))


def app_as(settings, store, principal):
    app = create_app(settings, store, FakeOrc())
    app.dependency_overrides[app.state.session_dependency] = lambda: principal
    return app


def entries_of(c, kind):
    r = c.get(f'/api/v1/catalog/{kind}')
    assert r.status_code == 200, r.text
    assert r.json()['kind'] == kind
    return r.json()['entries']


def test_everything_holds_every_entry_at_any_stage(settings, store, lab_file):
    with TestClient(app_as(settings, store, StubPrincipal({'*': True}))) as c:
        assert entries_of(c, 'indicator') == [{'id': 'I01', 'stage': 'released'}, {'id': 'I02', 'stage': 'lab'},
                                              {'id': 'I03', 'stage': 'released'}]
        assert entries_of(c, 'screener_preset') == [{'id': 'brk52', 'stage': 'lab'}]
        assert entries_of(c, 'candle_pattern') == []


def test_released_stage_on_one_family_holds_only_released_entries_of_that_kind(settings, store, lab_file):
    p = StubPrincipal({'terminal.indicator': {'stages': ['released']}})
    with TestClient(app_as(settings, store, p)) as c:
        assert entries_of(c, 'indicator') == [{'id': 'I01', 'stage': 'released'}, {'id': 'I03', 'stage': 'released'}]
        for kind in ('flow_indicator', 'screener_metric', 'screener_preset', 'candle_pattern'):
            assert entries_of(c, kind) == []


def test_ids_grant_holds_exactly_those_ids_and_any_family_of_the_kind_counts(settings, store, lab_file):
    with TestClient(app_as(settings, store, StubPrincipal({'terminal.indicator': {'ids': ['I01']}}))) as c:
        assert entries_of(c, 'indicator') == [{'id': 'I01', 'stage': 'released'}]
        assert entries_of(c, 'flow_indicator') == []
    # a lab id granted by id in another tab's family of the same kind is held too
    p = StubPrincipal({'terminal.indicator': {'ids': ['I01']}, 'screener.indicator': {'ids': ['I02']},
                       'screener.preset': {'all': True}})
    with TestClient(app_as(settings, store, p)) as c:
        assert entries_of(c, 'indicator') == [{'id': 'I01', 'stage': 'released'}, {'id': 'I02', 'stage': 'lab'}]
        assert entries_of(c, 'screener_preset') == [{'id': 'brk52', 'stage': 'lab'}]


def test_an_unknown_kind_is_not_found_and_names_the_known_kinds(settings, store):
    with TestClient(app_as(settings, store, StubPrincipal({'*': True}))) as c:
        r = c.get('/api/v1/catalog/feature')
        assert r.status_code == 404
        error = r.json()['error']
        assert error['code'] == 'NOT_FOUND' and error['message']
        assert error['details'] == {'kind': 'feature', 'known_kinds': list(KINDS)}


def test_signed_out_is_unauthenticated(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        for kind in ('indicator', 'feature'):
            r = c.get(f'/api/v1/catalog/{kind}')
            assert r.status_code == 401 and r.json()['error']['code'] == 'UNAUTHENTICATED'


def test_switch_off_sign_in_through_the_real_principal(settings, store):
    """The real Phase 1 principal: the test settings list no admin owner (no capability, an empty catalog); listed in
    EDGE_ADMIN_OWNERS it holds `*` and every entry of the repository file."""
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        login(c)
        assert entries_of(c, 'indicator') == []
    admins = dataclasses.replace(settings, admin_owners=(settings.owner,))
    with TestClient(create_app(admins, store, FakeOrc())) as c:
        login(c)
        assert entries_of(c, 'flow_indicator') == releases.entries('flow_indicator')
        assert len(entries_of(c, 'indicator')) == 53
