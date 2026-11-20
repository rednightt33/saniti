"""C2-E2E (EXEC-MU-ACCOUNTS re-check of Phases 0-3b, round 2, lens "switch on, end to end, as three people"): failing
tests of what a person sees in a real browser with EDGE_MULTIUSER on (harness: tests/e2e_people.py).

1. The Monitor shows a plan refusal as its internal code ("CAPABILITY_REQUIRED", "MFA_REQUIRED") instead of its words
   (CONTRACT.md section 3; ERRORS M471). Every account but the admin lands on it after sign-in or registration, because
   the Monitor is admin only (decision D1: the paid plan holds monitor.example, not monitor.view).
2. The shell never reads its session again when X-Edge-Entitlements changes (CONTRACT.md 8a and 12): an account whose
   plan is raised to one that needs the second factor stays in the workspace, every route answers MFA_REQUIRED, and the
   authenticator set-up appears only after a reload.
3. Phase 3c (p3c-int 41067e7d, apps/edge-bff/app/terminal_access.py check) refuses every reference file to the free plan
   (decision D3), and the Terminal page draws nothing without the ticker list (terminal/src/data/live.ts liveData awaits
   reference('tickers')), so the free plan's one holding, BBCA's daily price, is not shown.

Needs EDGE_TEST_POSTGRES_URL, Playwright with EDGE_TEST_CHROMIUM, and (test 3) the built Terminal page."""
import time

import pytest

playwright = pytest.importorskip('playwright.sync_api')

from e2e_people import (CHROMIUM, ROOT, Live, browser_context, register, shell_navigate,  # noqa: E402
                        signed_in_workspace, terminal_drawn)


@pytest.fixture
def live(settings, store, monkeypatch):
    on = Live(settings, store, monkeypatch)
    try:
        yield on
    finally:
        on.close()


@pytest.fixture
def chromium(live):
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=live.terminal.browser_args())
        try:
            yield browser
        finally:
            browser.close()


def test_the_monitor_shows_a_plan_refusal_in_words_not_its_code(live, chromium):
    """A free account (and a paid one, D1) does not hold monitor.view. Before 3e the Monitor opened and its conversation
    list answered 403 CAPABILITY_REQUIRED, shown once as the code (index.html Monitor: setApiError(e.message)); since 3e
    (CONTRACT 8b) the shell shows LockedTabPage in its place, in words that name the tab and the plan, never a code,
    until the Monitor's example (decision D4) is built."""
    page = browser_context(chromium).new_page()
    register(page, live, 'free_user', 'free@example.com')
    # fix round: a new account lands on the Terminal (re-check R2-14), so the Monitor is opened from the rail
    assert page.evaluate('() => location.pathname') == '/terminal'
    shell_navigate(page, '/monitor')
    card = page.locator('main.locked-tab[data-locked-tab="monitor"] .locked-tab-card')
    card.wait_for(timeout=15000)
    shown = card.inner_text()
    assert 'CAPABILITY_REQUIRED' not in shown and 'Monitor is not in your plan' in shown, shown
    assert page.get_by_placeholder('Ask a research question…').count() == 0
    live.subscribe('free_user', 'paid')                 # the paid plan holds monitor.example only (D1)
    page.reload()
    card.wait_for(timeout=15000)
    assert 'Monitor is not in your plan' in card.inner_text()


def test_a_plan_raised_to_one_that_needs_mfa_asks_for_the_authenticator_without_a_reload(live, chromium):
    """A signed-in paid account is raised to the plan that holds '*' (Phase 4's admin page; here its subscription row).
    From the next request its session needs the second factor (role_needs_mfa) and every answer carries a new
    X-Edge-Entitlements. The shell keeps Edge.auth from the sign-in (edge-client.js reads no header), so access.next stays
    null: authMode never shows /mfa, not even at /mfa, and the frames say "Enter the code from your authenticator app"
    to an account that has none (mfa_enrolled false). Only a reload shows the set-up."""
    page = browser_context(chromium).new_page()
    register(page, live, 'paid_user', 'paid@example.com')
    live.subscribe('paid_user', 'paid')
    page.reload()
    signed_in_workspace(page)                           # fix round: the landing page (re-check R2-14)
    live.subscribe('paid_user', 'admin')
    shell_navigate(page, '/terminal')                   # the frame's calls answer MFA_REQUIRED with the new version
    time.sleep(3)
    shell_navigate(page, '/monitor')                    # the shell's own calls too
    time.sleep(3)
    server = page.evaluate("() => fetch('/api/v1/auth/session').then(r => r.json()).then(d => d.access)")
    assert server['next'] == 'mfa' and server['mfa_enrolled'] is False          # the server's side is right
    shell = page.evaluate('() => Edge.auth && Edge.auth.access')
    assert shell['version'] == server['version'], 'the shell kept the session of the plan before the change'
    page.get_by_text('Set up your authenticator').wait_for(timeout=10000)


def test_the_free_plans_terminal_draws_bbca_with_the_answers_phase_3c_gives_it(live, chromium):
    """The free plan holds terminal.view, terminal.dataset {ids: [price]} and terminal.tickers [BBCA] (8a seed; D3 = B:
    the BBCA daily price only, no reference lists). With today's answers the Terminal draws BBCA (the control). Phase 3c
    (p3c-int terminal_access.check: `head == 'reference'` -> _dataset(caps, 'reference')) refuses every reference file
    with 403 CAPABILITY_REQUIRED terminal.dataset:reference, serves BBCA's price and locks the other datasets. liveData
    awaits the ticker list before it draws, so the page shows only the refusal, and BBCA is never drawn. (Refusing only
    reference/tickers is enough; the locks alone are drawn.) A fix on the 3c side (CONTRACT.md 8b lets /reference
    "refuse or filter") changes the answers set below to the ones 3c then gives this principal; the assertion stays."""
    if not (ROOT / 'static' / 'terminal-app' / 'index.html').is_file():
        pytest.skip('the Terminal page is not built (cd apps/edge-bff/terminal && npm run build)')
    page = browser_context(chromium).new_page()
    register(page, live, 'free_user', 'free@example.com')
    page.evaluate("() => localStorage.setItem('ml.symbol', 'BBCA')")      # the one ticker the plan holds (3e picks it)
    shell_navigate(page, '/terminal')
    drawn, text = terminal_drawn(page)
    assert drawn, f'control: the Terminal did not draw BBCA with every reference file served: {text[:300]}'
    # the answers of Phase 3c for this principal (CONTRACT.md 8b "3c in detail"), after the re-check fix (R2-32, fix
    # round track terminal): terminal-api answers the header edge-bff really sends with its own code (e2e_people.py
    # FakeTerminalApi.apply_header): each reference file as the plan's own copy (BBCA alone), the other datasets locked,
    # BBCA's price as the cut of the last 730 days, both relayed by edge-bff from this origin
    live.terminal.apply_header = True
    calls, downloads = len(live.terminal.calls), len(live.terminal.downloads)
    page.reload()
    drawn, text = terminal_drawn(page)
    assert drawn, ('with the reference files refused (D3) the free plan\'s Terminal draws nothing, BBCA included: '
                   f'{text[:300]}')
    asked = [c['path'] for c in live.terminal.calls[calls:]]
    # track guest (decision 1 of 2026-11-19; this test asked for the BBCA-alone copy of the ticker list): the ticker
    # list is the plan's whole copy now, byte for byte the list this browser keeps from the first load (its cache by
    # sha256), so it is announced and not downloaded again; a file with data per ticker still comes as the plan's copy
    assert '/api/terminal/v1/reference/tickers' in asked, asked
    assert any(p.startswith('/api/terminal/v1/reference/brokers/cut') for p in asked), asked
    assert any(p.startswith('/api/terminal/v1/cut/BBCA/price') for p in asked), asked
    assert not [k for k in live.terminal.downloads[downloads:] if k.startswith('ref/')], 'a full reference list was downloaded'


def test_the_free_plans_terminal_opens_on_bbca_with_nothing_remembered(live, chromium):
    """Re-check R2-32 (fix round, track terminal): with no ticker remembered the page draws the plan's own ticker, BBCA,
    and no other ticker's data. Track guest (decision 1 of 2026-11-19, which replaces D3 = B's "tanpa daftar ticker"):
    the ticker list it is given is the whole list (searchable, the others locked), and the page skips its default
    (MAPI), which the plan does not hold, for the plan's first ticker."""
    if not (ROOT / 'static' / 'terminal-app' / 'index.html').is_file():
        pytest.skip('the Terminal page is not built (cd apps/edge-bff/terminal && npm run build)')
    live.terminal.apply_header = True
    page = browser_context(chromium).new_page()
    register(page, live, 'free_user', 'free@example.com')
    shell_navigate(page, '/terminal')
    drawn, text = terminal_drawn(page)
    assert drawn, f'the free plan\'s Terminal did not draw BBCA: {text[:300]}'
    assert 'BBCA' in text and 'BBRI' not in text and 'TLKM' not in text, text[:400]
    tickers = [c for c in live.terminal.calls if c['path'].startswith('/api/terminal/v1/reference/tickers/cut')]
    assert tickers, [c['path'] for c in live.terminal.calls]
