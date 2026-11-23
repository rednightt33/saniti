"""EXEC-MU-ACCOUNTS "A preview release stage" (the user 2026-11-23: "ada indikator baru di main --> promote ke live,
tapi saya mau promote ke live hanya admin saja yang bisa lihat, user paid tidak bisa lihat"; the plan "B"): an item at
the preview stage is on both sites and held only by a principal whose grants name it (the admin's `*`, its id); no plan
holds it by stage (releases.GRANT_STAGES and the database's capability_value_check), so a paid, free or guest principal
never holds it, and it is not beta-only.

Through the real principals of both sites (live_of: EDGE_SITE=live with the switch on; beta_on: the same on the beta):
the catalog route, the workers' allow, the tab catalogs (the Screener's with its presets, the Backtest's Flow list), the
guest plan and every plan the migrations seed. The preview items are derived from the repository's release file (the
first item of each kind the catalogs list), as the lab tests do (tests/test_3f_tab_catalogs.py), and each check runs on
the unfiltered document first, where it must find the item (the self-test).
"""
import json

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import catalog, releases
from app.allow import allow_of
from app.main import create_app
from app.principal import guest_principal, holds, live_view, read_grants, valid_value
from app.rights import catalog_for, rights_of
from conftest import FakeOrc
from test_3f_tab_catalogs import FUNDAMENTAL, PATTERN, beta_on, ids, other, screener_doc, shown_screener
from test_beta_live_site import live_of, sign_in_admin
from test_phase3a_gates import db, override, paid_user
from test_principal import make_user

PREVIEW = releases.PREVIEW


@pytest.fixture
def preview_one_of_each(monkeypatch):
    """The repository's release file with one item of each kind the catalogs list at the preview stage (as
    test_3f_tab_catalogs.lab_one_of_each does for lab). {name: (kind, id)}."""
    chosen = {'indicator': ('indicator', releases.entries('indicator')[0]['id']),
              'flow': ('flow_indicator', releases.entries('flow_indicator')[0]['id']),
              'candle': ('candle_pattern', releases.entries('candle_pattern')[0]['id']),
              'pattern': ('screener_metric', PATTERN[0]), 'fundamental': ('screener_metric', FUNDAMENTAL[0]),
              'preset': ('screener_preset', releases.entries('screener_preset')[0]['id'])}
    assert all(releases.stage_of(k, i) == 'released' for k, i in chosen.values())
    picked = set(chosen.values())
    items = [{'kind': k, 'id': e['id'], 'stage': PREVIEW if (k, e['id']) in picked else 'released'}
             for k in releases.KINDS for e in releases.entries(k)]                      # the others released, whatever today's file holds
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases({
        'schema_version': 1, 'items': items, 'tabs': [{'id': t, 'stage': st} for t, st in releases.CURRENT.tabs().items()]}))
    return chosen


def held_ids(c, kind):
    r = c.get(f'/api/v1/catalog/{kind}')
    assert r.status_code == 200, r.text
    return {e['id']: e['stage'] for e in r.json()['entries']}


def preview_in(data, chosen):
    """Every preview id the shown Screener catalog lists, with its `release` mark ({id: mark or None})."""
    previews = {i for _, i in chosen.values()}
    return {e['id']: e.get('release') for name in ('indicators', 'metrics', 'fundamentals', 'presets')
            for e in data.get(name, []) if isinstance(e, dict) and isinstance(e.get('id'), str) and e['id'] in previews}


@pytest.mark.parametrize('site', ['live', 'beta'])
def test_the_admin_holds_a_preview_item_on_both_sites_and_a_paid_account_never(settings, store, preview_one_of_each,
                                                                                site):
    chosen = preview_one_of_each
    ind, flow = chosen['indicator'][1], chosen['flow'][1]
    app = create_app((live_of if site == 'live' else beta_on)(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        admin = app.state.auth.owner_principal(settings.owner)
        assert getattr(admin, 'live', False) is (site == 'live')
        assert held_ids(c, 'indicator')[ind] == PREVIEW and held_ids(c, 'flow_indicator')[flow] == PREVIEW
        for worker in ('backtest', 'screener'):
            allow = allow_of(admin, worker)
            if site == 'live':                                  # live: each id on its own, never "*"
                assert ind in allow['indicator'] and flow in allow['flow_indicator'], (worker, allow)
            else:
                assert allow['indicator'] == '*' and allow['flow_indicator'] == '*'
        alice = paid_user(store, f'pv_{site}')
        paid = app.state.auth.owner_principal(alice['owner_key'])
        assert not paid.can(f'terminal.indicator:{ind}') and not paid.can(f'terminal.flow_indicator:{flow}')
        assert paid.can(f'terminal.indicator:{other("indicator", chosen)}')       # the released ones stay held
        for worker in ('backtest', 'screener'):
            allow = allow_of(paid, worker)
            assert ind not in allow['indicator'] and flow not in allow['flow_indicator'], (worker, allow)
            assert other('indicator', chosen) in allow['indicator']
        free = app.state.auth.owner_principal(make_user(store, f'pv_free_{site}', 'free-password')['owner_key'])
        assert not free.can(f'terminal.indicator:{ind}') and ind not in allow_of(free, 'backtest')['indicator']


def test_the_screener_catalog_lists_a_preview_item_marked_to_the_live_admin_and_never_to_a_paid_account(
        settings, store, preview_one_of_each):
    chosen, doc = preview_one_of_each, screener_doc(preview_one_of_each)
    assert len(preview_in(json.loads(doc.raw), chosen)) == len(chosen), 'the self-test: the document has every item'
    app = create_app(live_of(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        admin = app.state.auth.owner_principal(settings.owner)
        paid = app.state.auth.owner_principal(paid_user(store, 'pv_screener')['owner_key'])
        mine = preview_in(shown_screener(app, doc, admin), chosen)
        assert mine == {i: PREVIEW for _, i in chosen.values()}, mine          # held, each carrying its mark
        theirs = shown_screener(app, doc, paid)
        assert preview_in(theirs, chosen) == {}, theirs
        assert other('indicator', chosen) in ids(theirs, 'indicators')
        assert other('screener_preset', chosen) in ids(theirs, 'presets')
    # no principal (the stored examples' view): no preview item
    assert preview_in(json.loads(app.state.screeners.catalog_for(doc, [], None, None).raw), chosen) == {}


def test_the_backtest_flow_list_marks_a_preview_item_for_its_holder_and_leaves_it_out_for_the_others(
        settings, store, preview_one_of_each):
    chosen = preview_one_of_each
    flows = [{'id': chosen['flow'][1], 'access': 'all'}, {'id': other('flow_indicator', chosen), 'access': 'all'}]
    app = create_app(live_of(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        admin = app.state.auth.owner_principal(settings.owner)
        paid = app.state.auth.owner_principal(paid_user(store, 'pv_backtest')['owner_key'])
        assert catalog_for({'flow_indicators': flows}, rights_of(admin), admin)['flow_indicators'] == [
            {**flows[0], 'release': PREVIEW}, flows[1]]
        assert catalog_for({'flow_indicators': flows}, rights_of(paid), paid)['flow_indicators'] == [flows[1]]
    assert catalog_for({'flow_indicators': flows}, [], None)['flow_indicators'] == [flows[1]]


def plan_grants(store):
    """{plan_key: (grants, kinds)} of every plan the migrations seed, read as every plan's are (read_grants)."""
    rows = db(store, '''SELECT pc.plan_key, pc.capability_key, c.kind, pc.value FROM edge_bff.plan_capabilities pc
        JOIN edge_bff.capabilities c USING (capability_key)''')
    plans = {r['plan_key'] for r in db(store, 'SELECT plan_key FROM edge_bff.plans')}
    by = {p: {} for p in plans}
    for r in rows:
        by[r['plan_key']][r['capability_key']] = {'kind': r['kind'], 'value': r['value']}
    return {p: read_grants(g) for p, g in by.items()}


def test_no_plan_but_one_holding_everything_holds_a_preview_item(store, preview_one_of_each):
    """Derived over every seeded plan (paid, free, the guest plan, the test plans): only a plan holding `*` holds a
    preview item, and no other plan gives an item family {"all": true} (which would hold it too)."""
    plans = plan_grants(store)
    assert len(plans) >= 3, plans                                            # paid, free and the guest plan at least
    item_families = set(releases.KIND_OF_FAMILY)
    for plan, (grants, kinds) in plans.items():
        everything = grants.get('*') is True
        if not everything:
            assert not [f for f in item_families if kinds.get(f) == 'items' and grants[f].get('all') is True], plan
        for kind, item_id in preview_one_of_each.values():
            got = {f: holds(grants, kinds, f'{f}:{item_id}') for f in releases.FAMILIES_OF_KIND[kind]}
            assert any(got.values()) is everything, (plan, kind, item_id, got)
    guest = db(store, 'SELECT plan_key FROM edge_bff.plans WHERE for_guests')[0]['plan_key']
    visitor = guest_principal({'plan_key': guest, 'grants': {k: {'kind': plans[guest][1][k], 'value': v}
                                                             for k, v in plans[guest][0].items()}}, 'client-key')
    for kind, item_id in preview_one_of_each.values():
        assert not any(visitor.can(f'{f}:{item_id}') for f in releases.FAMILIES_OF_KIND[kind]), (kind, item_id)


def test_a_grant_cannot_name_the_preview_stage(store):
    """The guarantee is the database's (capability_value_check, migration 20261117_003) and the reader's (valid_value):
    a value {"stages": ["preview"]} is refused at write time and, read anyway, is not held."""
    assert valid_value('items', {'stages': ['released']}) and valid_value('items', {'stages': ['lab']})
    assert not valid_value('items', {'stages': ['preview']})
    user = make_user(store, 'pv_grant', 'grant-password')
    with pytest.raises(psycopg.Error, match='does not fit capability'):
        override(store, user['user_id'], 'terminal.indicator', '{"stages": ["preview"]}')
    grants, kinds = read_grants({'terminal.indicator': {'kind': 'items', 'value': {'stages': ['preview']}}})
    assert 'terminal.indicator' not in grants                               # not granted (fail closed)


def test_an_ungated_item_at_preview_is_held_only_by_its_holder(monkeypatch):
    """A universe attribute every Screener answer shows is never preview (tests/test_releases.py, the rule for items no
    worker gates by id); if one were, holds_entry would not give it to every principal (closed)."""
    attribute = sorted(catalog.SHOWN_ATTRIBUTES)[0]
    items = [{'kind': k, 'id': e['id'], 'stage': PREVIEW if (k, e['id']) == ('screener_metric', attribute) else e['stage']}
             for k in releases.KINDS for e in releases.entries(k)]
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases({
        'schema_version': 1, 'items': items, 'tabs': [{'id': t, 'stage': st} for t, st in releases.CURRENT.tabs().items()]}))

    class Plain:
        live = False

        def can(self, key):
            return False

    class Everything(Plain):
        def can(self, key):
            return True

    assert not catalog.holds_entry(Plain(), 'screener_metric', attribute)
    assert catalog.holds_entry(Everything(), 'screener_metric', attribute)
    other_attribute = sorted(catalog.SHOWN_ATTRIBUTES)[1]
    assert catalog.holds_entry(Plain(), 'screener_metric', other_attribute)     # a released one: everyone, as before


def test_a_preview_item_is_not_beta_only_and_a_live_view_keeps_the_admin_grants(preview_one_of_each):
    from app.principal import beta_only
    for kind, item_id in preview_one_of_each.values():
        for family in releases.FAMILIES_OF_KIND[kind]:
            assert not beta_only(f'{family}:{item_id}'), (family, item_id)
    from test_allow import principal
    star = live_view(principal({'*': ('flag', True)}))
    kind, item_id = preview_one_of_each['indicator']
    assert star.live and '*' not in star.capabilities and star.can(f'terminal.indicator:{item_id}')
