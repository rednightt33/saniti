"""3f (EXEC option A item 4; CONTRACT 8a "Tab catalogs"; ERRORS M520): the Screener's and the Backtest's catalogs, as the
workers answer them, list items too. edge-bff decides each entry as /api/v1/catalog does (catalog.tab_list):

- a lab item only for a principal that holds it (an id the release file does not list is lab);
- an entry the workers mark access 'admin' (a point-in-time Flow version) only with the right flow_point_in_time;
- a preset that reads an entry left out is left out too;
- on the live site no lab item for anyone, '*' included, and no point-in-time version (the admin rights are
  beta-only); a kept lab entry carries release 'lab'.

The lab items are derived from the repository's release file: the first item of each kind the catalogs list is switched
to lab, so the tests follow the registries. Each check is also run on the unfiltered document, where it must find the
leak (the self-test of the look-ahead gate's kind).
"""
import dataclasses
import gzip
import json

import pytest
from fastapi.testclient import TestClient

from app import releases
from app.allow import allow_of
from app.main import create_app
from app.rights import POINT_IN_TIME, catalog_for, rights_of
from app.screener import Doc
from conftest import FakeOrc
from test_beta_live_site import live_of, sign_in_admin
from test_phase3a_gates import db, paid_plan, paid_user, subscribe
from test_principal import make_user
from app.screener import ITEM_LISTS
from pathlib import Path

METRICS = json.loads((Path(__file__).resolve().parents[1] / 'screener' / 'src' / 'core' / 'screener-metrics.json').read_text())['metrics']
FUNDAMENTAL = [m['id'] for m in METRICS if m['kind'] == 'universe' and 'fundamental' in m['group'].lower() and not m.get('row')]
PATTERN = [m['id'] for m in METRICS if m['kind'] == 'pattern']


def beta_on(settings):
    return dataclasses.replace(live_of(settings), site='beta', orc_url=settings.orc_url, orc_key=settings.orc_key)


@pytest.fixture
def lab_one_of_each(monkeypatch):
    """The repository's release file with one item of each kind the catalogs list at the lab stage, as a principal meets
    them in the worker's grammar (3f checker CAT-2): a technical indicator, a Flow indicator, a candle pattern, a Screener
    pattern metric, a fundamental and a preset. {name: (kind, id)}."""
    chosen = {'indicator': ('indicator', releases.entries('indicator')[0]['id']),
              'flow': ('flow_indicator', releases.entries('flow_indicator')[0]['id']),
              'candle': ('candle_pattern', releases.entries('candle_pattern')[0]['id']),
              'pattern': ('screener_metric', PATTERN[0]), 'fundamental': ('screener_metric', FUNDAMENTAL[0]),
              'preset': ('screener_preset', releases.entries('screener_preset')[0]['id'])}
    assert all(releases.stage_of(k, i) == 'released' for k, i in chosen.values())
    lab = set(chosen.values())
    items = [{'kind': k, 'id': e['id'], 'stage': releases.LAB if (k, e['id']) in lab else e['stage']}
             for k in releases.KINDS for e in releases.entries(k)]
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases({
        'schema_version': 1, 'items': items, 'tabs': [{'id': t, 'stage': st} for t, st in releases.CURRENT.tabs().items()]}))
    return chosen


def other(kind, chosen, among=None):
    """A released item of the kind, beside the lab ones (among: only these ids)."""
    lab = {i for k, i in chosen.values() if k == kind}
    return next(e['id'] for e in releases.entries(kind) if e['id'] not in lab and e['stage'] == 'released'
                and (among is None or e['id'] in among))


def admin_flow():
    """A Flow indicator the workers mark admin-only (a point-in-time version): one of the release file's Flow ids that
    is not the lab one; the mark is the workers' (the doc below carries it, as the real workers do since M520)."""
    return releases.entries('flow_indicator')[-1]['id']


def ref(name, item_id):
    """A reference of the Screener's grammar to the item, by the key the worker's own walk reads (definitionItems)."""
    return {'indicator': {'kind': 'indicator', 'indicator': item_id}, 'flow': {'kind': 'flow', 'metric': item_id},
            'candle': {'kind': 'pattern', 'type': item_id}, 'pattern': {'kind': 'pattern', 'type': item_id},
            'fundamental': {'kind': 'universe', 'attr': item_id}}[name]


def condition(reference):
    return {'universe': {}, 'conditions': [{'id': 'a', 'enabled': True, 'test': {'kind': 'state', 'metric': reference}}]}


def screener_doc(chosen):
    """A Screener catalog in the worker's shape: one lab and one released entry of each list's kinds, the admin-marked
    Flow version, and presets reading each lab item in the real grammar, with the worker's `items` and, for the candle,
    without them (an older worker's preset: the definition is then the only guard)."""
    pit, ids = admin_flow(), {n: i for n, (_, i) in chosen.items()}
    data = {
        'indicators': [{'id': ids['indicator']}, {'id': other('indicator', chosen)}],
        'metrics': [{'id': ids['flow'], 'kind': 'flow'}, {'id': other('flow_indicator', chosen), 'kind': 'flow'},
                    {'id': pit, 'kind': 'flow', 'access': 'admin'},
                    {'id': ids['candle'], 'kind': 'pattern'}, {'id': other('candle_pattern', chosen), 'kind': 'pattern'},
                    {'id': ids['pattern'], 'kind': 'pattern'}, {'id': other('screener_metric', chosen, PATTERN), 'kind': 'pattern'},
                    {'id': ['not', 'an', 'id'], 'kind': 'pattern'}],                     # no item (3f checker CAT-7)
        'fundamentals': [{'id': ids['fundamental'], 'kind': 'universe'},
                         {'id': other('screener_metric', chosen, FUNDAMENTAL), 'kind': 'universe'}],
        'presets': [{'id': ids['preset'], 'definition': {}, 'items': []},
                    {'id': other('screener_preset', chosen), 'definition': {}, 'items': []}]
                   + [{'id': f'reads-{n}', 'definition': condition(ref(n, ids[n])), 'items': [{'kind': chosen[n][0], 'id': ids[n]}]}
                      for n in ('indicator', 'flow', 'pattern', 'fundamental')]
                   + [{'id': 'reads-candle', 'definition': condition(ref('candle', ids['candle']))},
                      {'id': 'reads-admin-flow', 'definition': condition(ref('flow', pit)), 'items': [{'kind': 'flow_indicator', 'id': pit}]}],
    }
    raw = json.dumps(data).encode()
    return Doc(key='catalog', raw=raw, gz=gzip.compress(raw), etag='"catalog-etag"', price_data=None)


def lab_leaks(data, chosen):
    """Every lab id (and preset reading one) the shown catalog still lists: [] when none."""
    lab = {i for _, i in chosen.values()}
    found = [e['id'] for name in ('indicators', 'metrics', 'fundamentals') for e in data.get(name, [])
             if isinstance(e.get('id'), str) and e['id'] in lab]
    found += [p['id'] for p in data.get('presets', []) if p['id'] in lab or p['id'].startswith('reads-') and p['id'] != 'reads-admin-flow']
    return found


def shown_screener(app, doc, p):
    return json.loads(app.state.screeners.catalog_for(doc, rights_of(p), allow_of(p, 'screener'), p).raw)


def ids(data, name):
    return [e['id'] for e in data[name] if isinstance(e.get('id'), str)]


def test_the_screener_catalog_lists_a_lab_item_only_to_a_principal_that_holds_it(settings, store, lab_one_of_each):
    chosen, doc = lab_one_of_each, screener_doc(lab_one_of_each)
    ids_of = {n: i for n, (_, i) in chosen.items()}
    assert lab_leaks(json.loads(doc.raw), chosen), 'the self-test: the unfiltered document has the lab items'
    app = create_app(beta_on(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        admin = app.state.auth.owner_principal(settings.owner)
        alice = app.state.auth.owner_principal(paid_user(store, 'alice')['owner_key'])
        shown = shown_screener(app, doc, alice)
        assert lab_leaks(shown, chosen) == [], shown
        assert admin_flow() not in ids(shown, 'metrics') and 'reads-admin-flow' not in ids(shown, 'presets')
        assert other('indicator', chosen) in ids(shown, 'indicators') and other('screener_preset', chosen) in ids(shown, 'presets')
        assert ids(shown, 'fundamentals') == [other('screener_metric', chosen, FUNDAMENTAL)]      # 3f checker TR-7
        assert {'id': ['not', 'an', 'id'], 'kind': 'pattern'} in shown['metrics']                 # no item: kept (CAT-7)
        mine = shown_screener(app, doc, admin)                                  # '*' on the beta: everything
        assert ids(mine, 'metrics') == ids(json.loads(doc.raw), 'metrics')
        assert [e['id'] for e in mine['metrics'] + mine['fundamentals'] if e.get('release') == releases.LAB] == [
            ids_of['flow'], ids_of['candle'], ids_of['pattern'], ids_of['fundamental']]
        assert mine['indicators'][0] == {'id': ids_of['indicator'], 'release': 'lab'}
        assert [x['release'] for x in mine['presets'] if x['id'] == ids_of['preset']] == ['lab']   # CAT-6
        assert shown_screener(app, doc, alice) == shown                         # kept per what decides it


def test_a_preset_that_reads_an_entry_left_out_is_left_out_by_its_definition_alone(settings, store, lab_one_of_each):
    """3f checker TR-6, CAT-2: the preset rule on its own. The admin holds every lab item but not the right
    flow_point_in_time once the session lacks it, so the presets left out are the ones that read the admin-only version;
    a preset without the worker's `items` is left out by its definition (reads_any, the grammar's keys) alone."""
    chosen, doc = lab_one_of_each, screener_doc(lab_one_of_each)
    app = create_app(beta_on(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        admin = app.state.auth.owner_principal(settings.owner)
        without_right = json.loads(app.state.screeners.catalog_for(doc, [], allow_of(admin, 'screener'), admin).raw)
        assert 'reads-admin-flow' not in ids(without_right, 'presets') and 'reads-candle' in ids(without_right, 'presets')
        # the candle as an entry left out: the preset without `items` names it only as {"kind": "pattern", "type": id}
        lab_candle = chosen['candle'][1]
        assert app.state.screeners.catalog_for(doc, [], None, None) is not doc
        gone = json.loads(app.state.screeners.catalog_for(doc, [], None, None).raw)
        assert lab_candle not in ids(gone, 'metrics') and 'reads-candle' not in ids(gone, 'presets')
        assert chosen['preset'][1] not in ids(gone, 'presets')                  # CAT-6: without a principal, no lab preset


@pytest.fixture
def nopreset_plan(store):
    """A plan granting what the paid plan grants but screener.preset (no row at all): its principal's grants of the
    presets read as the live admin's do (grant_key), which is the case of 3f checker CAT-4. Removed afterwards, since
    the plans are part of the seeded catalog the other tests read."""
    paid = paid_plan(store)
    db(store, "INSERT INTO edge_bff.plans(plan_key, display_name) VALUES ('nopreset', 'No presets')")
    db(store, """INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) SELECT 'nopreset', capability_key, value
        FROM edge_bff.plan_capabilities WHERE plan_key = %s AND capability_key <> 'screener.preset'""", paid)
    try:
        yield 'nopreset'
    finally:
        db(store, "DELETE FROM edge_bff.subscriptions WHERE plan_key = 'nopreset'")
        db(store, "DELETE FROM edge_bff.plan_capabilities WHERE plan_key = 'nopreset'")
        db(store, "DELETE FROM edge_bff.plans WHERE plan_key = 'nopreset'")


def test_on_the_live_site_the_admin_and_an_account_without_presets_never_share_a_catalog_copy(settings, store,
                                                                                            lab_one_of_each, nopreset_plan):
    """3f checker CAT-4 (before 3f too): on the live site the admin's grants of the presets read like those of an account
    whose plan has no screener.preset row, and their allows are the same, so whichever asked first decided the other's
    presets, ETag and 304 included. The copies are now kept per the presets held."""
    doc = screener_doc(lab_one_of_each)
    for order in ('admin first', 'account first'):
        app = create_app(live_of(settings), store, FakeOrc())
        with TestClient(app) as c:
            sign_in_admin(c, store)
            user = make_user(store, f'nopreset_{order.split()[0]}', 'a long enough password')
            subscribe(store, user['user_id'], nopreset_plan)
            admin = app.state.auth.owner_principal(settings.owner)
            account = app.state.auth.owner_principal(user['owner_key'])
            assert allow_of(admin, 'screener') == allow_of(account, 'screener'), 'the case needs the same allow'
            first, second = (admin, account) if order == 'admin first' else (account, admin)
            got = {'first': shown_screener(app, doc, first)['presets'], 'second': shown_screener(app, doc, second)['presets']}
            mine, theirs = (got['first'], got['second']) if first is admin else (got['second'], got['first'])
            assert [x['id'] for x in theirs] == [], order
            assert other('screener_preset', lab_one_of_each) in [x['id'] for x in mine], order


def test_the_kinds_that_share_a_catalog_list_repeat_no_id():
    """3f checker CAT-1: a list of the Screener's catalog holds several kinds (screener.ITEM_LISTS) and an entry's kind
    is the one that lists its id, so no id may be listed by two of them."""
    for name, kinds, _ in ITEM_LISTS:
        seen = {}
        for kind in kinds:
            for e in releases.entries(kind):
                assert e['id'] not in seen, f'{e["id"]} is a {seen.get(e["id"])} and a {kind}, both listed in {name}'
                seen[e['id']] = kind


def test_on_the_live_site_no_catalog_lists_a_lab_item_to_anyone(settings, store, lab_one_of_each):
    chosen, doc = lab_one_of_each, screener_doc(lab_one_of_each)
    app = create_app(live_of(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        for owner in (settings.owner, paid_user(store, 'bob')['owner_key']):
            p = app.state.auth.owner_principal(owner)
            assert lab_leaks(shown_screener(app, doc, p), chosen) == [], owner
            flows = [{'id': chosen['flow'][1], 'access': 'all'}, {'id': other('flow_indicator', chosen), 'access': 'all'}]
            assert [x['id'] for x in catalog_for({'flow_indicators': flows}, rights_of(p), p)['flow_indicators']] == [
                other('flow_indicator', chosen)], owner
        # the admin rights are beta-only (principal.beta_only, ADMIN_RIGHT_CAPABILITIES): on live the point-in-time
        # versions are left out for the admin too
        admin = app.state.auth.owner_principal(settings.owner)
        assert POINT_IN_TIME not in rights_of(admin)
        assert admin_flow() not in ids(shown_screener(app, doc, admin), 'metrics')


def test_the_backtest_catalog_lists_a_lab_flow_indicator_only_to_a_principal_that_holds_it(settings, store,
                                                                                         lab_one_of_each):
    chosen = lab_one_of_each
    flows = [{'id': chosen['flow'][1], 'access': 'all'}, {'id': other('flow_indicator', chosen), 'access': 'all'},
             {'id': admin_flow(), 'access': 'admin'}, 'not-an-entry']
    unlisted = {'id': 'FL_NOT_IN_THE_RELEASE_FILE', 'access': 'all'}             # unlisted means lab
    catalog = {'flow_indicators': flows + [unlisted], 'limits': {}}
    app = create_app(beta_on(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        admin = app.state.auth.owner_principal(settings.owner)
        alice = app.state.auth.owner_principal(paid_user(store, 'alice')['owner_key'])
        assert catalog_for(catalog, rights_of(alice), alice)['flow_indicators'] == [flows[1], 'not-an-entry']
        mine = catalog_for(catalog, rights_of(admin), admin)['flow_indicators']
        assert mine == [{**flows[0], 'release': 'lab'}, flows[1], flows[2], 'not-an-entry', {**unlisted, 'release': 'lab'}]
    assert catalog_for(catalog, [], None)['flow_indicators'] == [flows[1], 'not-an-entry']   # no principal holds no lab item
