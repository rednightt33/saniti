"""The user, 2026-11-20 (EXEC option A): development happens on the beta and reaches the live site only on request, and
moving `live` takes whole commits of the beta, so what is not ready must be switched off on the live site by itself.
Every tab (the first part of a capability key, a page of the shell) has a live switch in catalog/releases.json `tabs`,
and a catalog item its stage in `items` (tests/test_releases.py); an unlisted tab or item is 'lab', on the beta only.

This test fails when a capability tab or a page of the shell has no entry (it must be listed, lab or released, or be
one of principal.BETA_ONLY_TABS), and shows that a lab tab is held by no one on the live site, the admin's '*'
included, is hidden from the live rail (auth/config hidden_tabs), and stays on the beta. LIVE_PROMOTION.md says how a
tab or an item is released."""
import dataclasses
import re
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

from app import releases
from app.main import create_app
from app.principal import BETA_ONLY_TABS, Principal, beta_only
from conftest import FakeOrc
from test_beta_live_site import live_of

SHELL = Path(__file__).resolve().parents[1] / 'static' / 'edge-app.js'


def shell_pages():
    """The pages of the shell a signed-in principal opens (the route table's auth:true entries)."""
    return {m.group(1) for m in re.finditer(r'\{path:"/([a-z0-9_-]+)", names:\[[^\]]*\], auth:true', SHELL.read_text())}


def test_every_capability_tab_and_page_of_the_shell_has_a_live_switch(database):
    with psycopg.connect(database) as c:
        tabs = {r[0] for r in c.execute("SELECT DISTINCT split_part(capability_key, '.', 1) FROM edge_bff.capabilities "
                                        "WHERE capability_key <> '*'")}
    pages = shell_pages()
    assert tabs and pages >= {'terminal', 'backtest', 'screener'}, (tabs, pages)
    switched = set(releases.CURRENT.tabs()) | BETA_ONLY_TABS
    missing = sorted((tabs | pages) - switched)
    assert not missing, (f'no live switch for {missing}: list each in catalog/releases.json "tabs" as "released" with '
                         'the user\'s go (LIVE_PROMOTION.md); no tab may be "lab" (the beta only) until LAB_TAB_HELD_UNTIL '
                         'is closed (test_no_tab_is_at_the_lab_stage_yet)')


# What still lets a lab tab reach visitors, after 3f (its ultracode checker, 2026-11-21, SERVE-3 and TR-13;
# FUTURE_PLAN.md "Before the first lab item or tab"): 3f serves a lab tab's own page app (<tab>-app) to the admin on the
# beta only, but its rail entry, route, frame wrapper and words are in the public shell (static/edge-app.js,
# static/edge-labels.js), the live site's public auth/config names it in hidden_tabs, and a tab that is a page of the
# shell itself ships its whole code there. A lab tab waits until the shell keeps it from visitors too.
LAB_TAB_HELD_UNTIL = ("the shell builds its rail and routes from the principal's tabs and keeps a lab tab's words and "
                      "page out of its public files, and auth/config names no lab tab")


def test_no_tab_is_at_the_lab_stage_yet():
    assert releases.lab_tabs() == frozenset(), (f'{sorted(releases.lab_tabs())} at the lab stage: a lab tab waits until '
                                                f'{LAB_TAB_HELD_UNTIL} (FUTURE_PLAN.md)')
    released = {t for t, st in releases.CURRENT.tabs().items() if st == 'released'}
    # 'support' (Phase 4, the contact-support panel's capability support.send; a dialog of the rail, not a page): the
    # user, 2026-11-22: "saya minta dibuatkan panel sebelah kiri di live iconnya kotak surat", "go"
    assert released == {'terminal', 'backtest', 'screener', 'watchlist', 'radar', 'overview', 'support'}, (
        f'the released tabs are {sorted(released)}: a new tab enters "released" only with the user\'s go and with this '
        'list (LIVE_PROMOTION.md section 3; 3f round 2, TRC2-8)')


def lab(monkeypatch, tab='newpage'):
    data = {'schema_version': 1, 'items': [], 'tabs': [{'id': 'terminal', 'stage': 'released'},
                                                        {'id': tab, 'stage': 'lab'}]}
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases(data, 'test'))


def test_a_lab_tab_is_held_by_no_one_on_the_live_site_and_by_the_admin_on_the_beta(monkeypatch):
    lab(monkeypatch)
    assert beta_only('newpage.view') and beta_only('newpage.indicator:I01')
    assert not beta_only('terminal.view')
    assert beta_only('unlisted.view')                       # a tab the file does not list is lab too
    assert not beta_only('*')                               # '*' is not a tab
    admin = Principal(user_id=1, owner_key='o', username='a', role='admin', plan_key='admin', status='active',
                      expires_at=None, mfa_ok=True, capabilities=frozenset({'*'}))
    assert admin.can('newpage.view')                        # the beta (the switch off): the admin sees it
    assert not dataclasses.replace(admin, live=True).can('newpage.view')    # the live site: no one, '*' included
    assert dataclasses.replace(admin, live=True).can('terminal.view')


def test_the_live_rail_hides_a_lab_tab_and_the_beta_does_not(settings, store, monkeypatch):
    lab(monkeypatch)
    live = dataclasses.replace(live_of(settings), environment='local')
    with TestClient(create_app(live, store, FakeOrc())) as c:
        assert c.get('/api/v1/auth/config').json()['hidden_tabs'] == ['admin', 'monitor', 'newpage']
    with TestClient(create_app(dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40),
                               store, FakeOrc())) as c:
        assert c.get('/api/v1/auth/config').json()['hidden_tabs'] == []


def test_the_release_file_refuses_a_malformed_tab():
    import pytest
    for tabs, why in (([{'id': 'Bad Tab', 'stage': 'lab'}], 'tab name'), ([{'id': 'x', 'stage': 'beta'}], 'unknown stage'),
                      ([{'id': 'x', 'stage': 'lab'}, {'id': 'x', 'stage': 'released'}], 'repeats'),
                      ('terminal', 'must be a list')):
        with pytest.raises(releases.ReleaseFileError, match=why):
            releases.Releases({'schema_version': 1, 'items': [], 'tabs': tabs}, 'test')
