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
from test_phase3a_gates import paid_user

LISTED = ('indicator', 'flow_indicator', 'candle_pattern', 'screener_metric', 'screener_preset')


def beta_on(settings):
    return dataclasses.replace(live_of(settings), site='beta', orc_url=settings.orc_url, orc_key=settings.orc_key)


@pytest.fixture
def lab_one_of_each(monkeypatch):
    """The repository's release file with the first item of each listed kind at the lab stage: {kind: id}."""
    chosen = {kind: releases.entries(kind)[0]['id'] for kind in LISTED}
    assert all(releases.stage_of(k, i) == 'released' for k, i in chosen.items())
    items = [{'kind': k, 'id': e['id'], 'stage': releases.LAB if chosen.get(k) == e['id'] else e['stage']}
             for k in releases.KINDS for e in releases.entries(k)]
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases({
        'schema_version': 1, 'items': items, 'tabs': [{'id': t, 'stage': st} for t, st in releases.CURRENT.tabs().items()]}))
    return chosen


def other(kind, chosen):
    """A released item of the kind, beside the lab one."""
    return next(e['id'] for e in releases.entries(kind) if e['id'] != chosen[kind] and e['stage'] == 'released')


def admin_flow():
    """A Flow indicator the workers mark admin-only (a point-in-time version): one of the release file's Flow ids that
    is not the lab one; the mark is the workers' (the doc below carries it, as the real workers do since M520)."""
    return releases.entries('flow_indicator')[-1]['id']


def condition(kind, item_id):
    ref = {'kind': 'indicator', 'indicator': item_id} if kind == 'indicator' else {'kind': 'flow' if kind == 'flow_indicator' else 'pattern', 'metric': item_id}
    return {'universe': {}, 'conditions': [{'id': 'a', 'enabled': True, 'test': {'kind': 'state', 'metric': ref}}]}


def screener_doc(chosen):
    """A Screener catalog in the worker's shape: one lab and one released entry of each list's kinds, the admin-marked
    Flow version, and presets reading each of them (with the worker's `items`)."""
    pit = admin_flow()
    data = {
        'indicators': [{'id': chosen['indicator']}, {'id': other('indicator', chosen)}],
        'metrics': [{'id': chosen['flow_indicator'], 'kind': 'flow'}, {'id': other('flow_indicator', chosen), 'kind': 'flow'},
                    {'id': pit, 'kind': 'flow', 'access': 'admin'},
                    {'id': chosen['candle_pattern'], 'kind': 'pattern'}, {'id': other('candle_pattern', chosen), 'kind': 'pattern'},
                    {'id': chosen['screener_metric'], 'kind': 'universe'}, {'id': other('screener_metric', chosen), 'kind': 'universe'}],
        'fundamentals': [],
        'presets': [{'id': chosen['screener_preset'], 'definition': {}, 'items': []},
                    {'id': other('screener_preset', chosen), 'definition': {}, 'items': []}]
                   + [{'id': f'reads-{kind}', 'definition': condition(kind, chosen[kind]), 'items': [{'kind': kind, 'id': chosen[kind]}]}
                      for kind in ('indicator', 'flow_indicator', 'candle_pattern', 'screener_metric')]
                   + [{'id': 'reads-admin-flow', 'definition': condition('flow_indicator', pit), 'items': [{'kind': 'flow_indicator', 'id': pit}]}],
    }
    raw = json.dumps(data).encode()
    return Doc(key='catalog', raw=raw, gz=gzip.compress(raw), etag='"catalog-etag"', price_data=None)


def lab_leaks(data, chosen):
    """Every lab id (and preset reading one) the shown catalog still lists: [] when none."""
    lab = set(chosen.values())
    found = [e['id'] for name in ('indicators', 'metrics', 'fundamentals') for e in data.get(name, []) if e.get('id') in lab]
    found += [p['id'] for p in data.get('presets', []) if p['id'] in lab or p['id'].startswith('reads-') and p['id'] != 'reads-admin-flow']
    return found


def shown_screener(app, doc, p):
    return json.loads(app.state.screeners.catalog_for(doc, rights_of(p), allow_of(p, 'screener'), p).raw)


def ids(data, name):
    return [e['id'] for e in data[name]]


def test_the_screener_catalog_lists_a_lab_item_only_to_a_principal_that_holds_it(settings, store, lab_one_of_each):
    chosen, doc = lab_one_of_each, screener_doc(lab_one_of_each)
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
        mine = shown_screener(app, doc, admin)                                  # '*' on the beta: everything
        assert ids(mine, 'metrics') == ids(json.loads(doc.raw), 'metrics')
        assert [e for e in mine['metrics'] if e.get('release') == releases.LAB] == [
            {'id': chosen['flow_indicator'], 'kind': 'flow', 'release': 'lab'},
            {'id': chosen['candle_pattern'], 'kind': 'pattern', 'release': 'lab'},
            {'id': chosen['screener_metric'], 'kind': 'universe', 'release': 'lab'}]
        assert mine['indicators'][0] == {'id': chosen['indicator'], 'release': 'lab'}
        assert shown_screener(app, doc, alice) == shown                         # kept per what decides it


def test_on_the_live_site_no_catalog_lists_a_lab_item_to_anyone(settings, store, lab_one_of_each):
    chosen, doc = lab_one_of_each, screener_doc(lab_one_of_each)
    app = create_app(live_of(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        for owner in (settings.owner, paid_user(store, 'bob')['owner_key']):
            p = app.state.auth.owner_principal(owner)
            assert lab_leaks(shown_screener(app, doc, p), chosen) == [], owner
            flows = [{'id': chosen['flow_indicator'], 'access': 'all'}, {'id': other('flow_indicator', chosen), 'access': 'all'}]
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
    flows = [{'id': chosen['flow_indicator'], 'access': 'all'}, {'id': other('flow_indicator', chosen), 'access': 'all'},
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
