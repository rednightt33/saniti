"""Live checker S1 (2026-11-20): the live site never offers the AI Monitor (CONTRACT 8b "3e", section 17; the user's
"4 ok", 2026-11-19), and its page must not either: GET /api/v1/auth/config names the tabs this site does not offer
(`hidden_tabs`, from principal.BETA_ONLY_TABS on the live site), and the shell shows neither their rail entries nor the
brand's Monitor target nor Research, and loads no model list. A visitor and a signed-in account see the same rail
without the Monitor; the beta (the switch off) keeps it. Needs EDGE_TEST_POSTGRES_URL, Playwright with EDGE_TEST_CHROMIUM
and the built Terminal page."""
import dataclasses

import pytest
from fastapi.testclient import TestClient

playwright = pytest.importorskip('playwright.sync_api')

from app.main import create_app  # noqa: E402
from conftest import FakeOrc  # noqa: E402
from e2e_people import CHROMIUM, ROOT, Live, browser_context, register, shell_navigate  # noqa: E402

RAIL = '.side-nav button, .side-nav a, .topbar button'


@pytest.fixture
def live_site(settings, store, monkeypatch):
    # registration open (prelaunch off) only so the test can make an account; the rail rule is the site's, not the mode's
    on = Live(dataclasses.replace(settings, site='live', guests_enabled=True, prelaunch_enabled=False, orc_url='', orc_key=''),
              store, monkeypatch)
    on.terminal.apply_header = True
    try:
        yield on
    finally:
        on.close()


def rail_names(page):
    page.locator('.side-nav').first.wait_for(timeout=20000)
    return [n.strip() for n in page.locator(RAIL).evaluate_all(
        "ns => ns.map(n => n.getAttribute('aria-label') || n.getAttribute('data-tip') || n.innerText || '')") if n.strip()]


def test_the_config_names_the_tabs_the_live_site_does_not_offer(settings, store):
    live = dataclasses.replace(settings, site='live', multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
                               orc_url='', orc_key='', environment='local')
    with TestClient(create_app(live, store, FakeOrc())) as c:
        assert c.get('/api/v1/auth/config').json()['hidden_tabs'] == ['admin', 'monitor']
    with TestClient(create_app(settings, store, FakeOrc())) as c:          # the beta, switch off: as before
        assert c.get('/api/v1/auth/config').json() == {'multiuser': False}


def test_the_live_rail_offers_no_monitor_to_a_visitor_or_an_account(live_site):
    if not (ROOT / 'static' / 'terminal-app' / 'index.html').is_file():
        pytest.skip('the Terminal page is not built (cd apps/edge-bff/terminal && npm run build)')
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=live_site.terminal.browser_args())
        try:
            visitor = browser_context(browser).new_page()
            asked = []
            visitor.on('request', lambda r: asked.append(r.url))
            visitor.goto(live_site.origin + '/terminal')
            names = rail_names(visitor)
            assert not [n for n in names if 'Monitor' in n or n == 'Research'], names
            assert 'Terminal' in ' '.join(names), names
            account = browser_context(browser).new_page()
            account.on('request', lambda r: asked.append(r.url))
            register(account, live_site, 'rail_user', 'rail@example.com')
            shell_navigate(account, '/terminal')
            names = rail_names(account)
            assert not [n for n in names if 'Monitor' in n or n == 'Research'], names
            assert not [u for u in asked if '/api/v1/models' in u], 'the live page asked for the model list'
        finally:
            browser.close()


def test_a_visitor_is_never_offered_an_account_no_one_can_create(settings, store):
    """Live checker G3: in the pre-launch mode registration is closed, so a visitor's refusal says to sign in and that
    registration opens soon; with registration open it also offers to create an account (app/errors.py words, set at
    create_app from the mode)."""
    from app import errors
    details = {'visitor': True, 'capability': 'terminal.tickers', 'display_name': 'Terminal tickers'}
    try:
        prelaunch = dataclasses.replace(settings, site='live', multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
                                        orc_url='', orc_key='', environment='local', prelaunch_enabled=True)
        create_app(prelaunch, store, FakeOrc())
        closed = errors.words('CAPABILITY_REQUIRED', 403, details)
        assert closed == 'Terminal tickers needs an EDGE account. Sign in to use it; registration opens soon.'
        create_app(dataclasses.replace(prelaunch, prelaunch_enabled=False), store, FakeOrc())
        assert 'Sign in or create one' in errors.words('CAPABILITY_REQUIRED', 403, details)
    finally:
        errors.set_registration_open(True)


def test_a_live_start_without_the_terminal_settings_is_refused(settings):
    """Live checker S6: a reference that resolved empty would have started a live site with no Terminal and /ready 200."""
    import pytest as _pytest
    live = dataclasses.replace(settings, site='live', multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
                               orc_url='', orc_key='', environment='dev', origin='https://app.edgefinance.id',
                               secure_cookie=True, database_url='postgresql://edge_bff_login@db.invalid/edge',
                               email_log_allowed=True, terminal_url='', terminal_proxy_key='')
    with _pytest.raises(ValueError, match='serves the Terminal'):
        live.validate()
    dataclasses.replace(live, terminal_url='http://terminal-api.railway.internal:8080', terminal_proxy_key='k' * 40).validate()
