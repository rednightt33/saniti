"""EXEC-UI-1015C (user 2026-10-15, "Ok, confirmed. Go."). Desktop: the session bar above the chat is gone, its Details,
bookmark and share buttons sit in the rail, and each response in Response History has a way back to it in the
conversation. Phone: the rail's menu and "+" sit in the header between the logo and search, the chat takes the full
width, the session bar stays, and settings opens from the account menu. The EDGE "E" is the favicon, public like the
page."""
import urllib.request

from test_answer_view import fixture_server  # noqa: F401 (fixture)
from test_ui_1015 import FIXTURES  # noqa: F401 (registers the ui1015 fixtures)
from test_visual import browser_page, dummy_orc, saved, server, sign_in, submit  # noqa: F401 (fixtures)


def box(page, selector):
    return page.locator(selector).first.bounding_box()


def test_on_a_desktop_the_session_bar_is_gone_and_its_buttons_sit_in_the_rail(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    for width in (1440, 900):  # expanded rail, and the narrow 52 px rail
        page.set_viewport_size({'width': width, 'height': 900})
        sign_in(page, origin)
        submit(page, 'fx:ui1015_notes')
        saved(page)
        assert not page.locator('.workspace-tools').is_visible()
        rail = box(page, '.conversation-panel')
        for name in ('Bookmark', 'Public sharing unavailable'):
            button = page.get_by_role('button', name=name, exact=True)
            assert button.is_visible()
            b = button.bounding_box()
            assert rail['x'] <= b['x'] and b['x'] + b['width'] <= rail['x'] + rail['width'] + 1, (width, name)
        assert page.get_by_role('button', name='Public sharing unavailable', exact=True).is_disabled()
        page.get_by_role('button', name='Bookmark', exact=True).click()
        page.wait_for_function("() => document.querySelector('[aria-label=Bookmark]').getAttribute('aria-pressed') === 'true'")
        if width > 1050:  # details open by default on a wide screen: the rail button closes and opens it
            page.get_by_role('button', name='Hide Details', exact=True).click()
            page.locator('.details-panel').wait_for(state='hidden')
        page.get_by_role('button', name='Show Details', exact=True).click()
        page.get_by_text('Response History', exact=True).wait_for()
        page.context.clear_cookies()


def test_response_history_leads_back_to_each_response(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 1440, 'height': 800})
    sign_in(page, origin)
    submit(page, 'fx:ui1015_notes')
    saved(page)
    submit(page, 'fx:ui1015_long_table')
    saved(page, 2)
    scroll = "() => document.querySelector('.research-scroll').scrollTop"
    first = page.locator('.edge-flow-accordion').first
    if not first.evaluate('n => n.open'):
        first.locator('summary').click()
    page.wait_for_timeout(200)
    before = page.evaluate(scroll)
    first.get_by_role('button', name='Lihat di percakapan').click()
    page.wait_for_timeout(900)  # smooth scroll
    assert page.evaluate(scroll) < before  # moved up to the first response
    top = page.evaluate("""() => { const ex = document.querySelectorAll('.research-exchange')[0], s = document.querySelector('.research-scroll');
        return ex.querySelector('article.result').getBoundingClientRect().top - s.getBoundingClientRect().top; }""")
    assert -40 <= top <= 80, top
    assert page.locator('.edge-history-jump').count() == 2


def test_a_jump_from_the_bottom_of_a_long_conversation_is_not_pulled_back(fixture_server, browser_page):
    """Live 2026-10-15: from the bottom of a long conversation, the first scroll event of a smooth jump came while the
    view was still near the bottom, switched auto-follow back on and auto-follow pulled the view down again. The same
    held for a pin and for a section link."""
    origin, _ = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 1440, 'height': 800})
    sign_in(page, origin)
    for n in range(1, 5):
        submit(page, 'fx:ui1015_long_table')
        saved(page, n)
    page.evaluate("() => { const s = document.querySelector('.research-scroll'); s.scrollTo({top: s.scrollHeight, behavior: 'instant'}); s.dispatchEvent(new Event('scroll')); }")
    page.wait_for_timeout(400)
    first = page.locator('.edge-flow-accordion').first
    if not first.evaluate('n => n.open'):
        first.locator('summary').click()
    run_id = first.get_attribute('id').replace('edge-history-', '')
    first.get_by_role('button', name='Lihat di percakapan').click()
    page.wait_for_timeout(1500)
    top = page.evaluate("""id => { const n = document.getElementById(id + '-response') || document.getElementById('edge-exchange-' + id),
        s = document.querySelector('.research-scroll'); return n.getBoundingClientRect().top - s.getBoundingClientRect().top; }""", run_id)
    assert -40 <= top <= 80, top


def test_on_a_phone_menu_and_new_sit_in_the_header_and_the_chat_is_full_width(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    for width in (390, 360):
        page.set_viewport_size({'width': width, 'height': 844})
        sign_in(page, origin)
        submit(page, 'fx:ui1015_notes')
        saved(page)
        top = box(page, '.topbar')
        brand = box(page, '.topbar .brand-mark')
        search = box(page, '.top-actions .search')
        menu = page.get_by_role('button', name='Open history', exact=True).bounding_box()
        plus = page.get_by_role('button', name='New conversation', exact=True).bounding_box()
        for b in (menu, plus):  # inside the header, between the logo and search
            assert top['y'] <= b['y'] and b['y'] + b['height'] <= top['y'] + top['height'] + 1
        assert brand['x'] + brand['width'] < menu['x'] < menu['x'] + menu['width'] <= plus['x']
        assert plus['x'] + plus['width'] <= search['x'], (width, plus, search)
        assert box(page, '.research-workspace')['width'] >= width - 1  # no rail
        assert page.locator('.workspace-tools').is_visible()  # the phone session bar stays
        assert not page.get_by_role('button', name='Settings', exact=True).is_visible()
        page.get_by_role('button', name='Account menu', exact=True).click()
        page.get_by_role('menuitem', name='Pengaturan', exact=True).click()
        page.get_by_role('dialog', name='Appearance', exact=True).wait_for()
        page.keyboard.press('Escape')
        page.get_by_role('button', name='Open history', exact=True).click()  # the history drawer still opens
        page.get_by_placeholder('Search conversation').wait_for(state='visible')
        page.keyboard.press('Escape')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.context.clear_cookies()


def test_the_favicon_is_public(fixture_server):
    origin, _ = fixture_server
    for path, kind, size in (('/favicon.svg', 'image/svg+xml', None), ('/favicon-32.png', 'image/png', 32),
                             ('/apple-touch-icon.png', 'image/png', 180)):
        with urllib.request.urlopen(origin + path) as response:  # no session cookie
            assert response.status == 200 and response.headers['Content-Type'].startswith(kind)
            body = response.read()
        if size:
            assert body[:8] == b'\x89PNG\r\n\x1a\n'
            assert int.from_bytes(body[16:20], 'big') == size and int.from_bytes(body[20:24], 'big') == size
    with urllib.request.urlopen(origin + '/monitor') as response:
        page = response.read().decode()
    for link in ('href="/favicon.svg"', 'href="/favicon-32.png"', 'rel="apple-touch-icon" href="/apple-touch-icon.png"'):
        assert link in page


def test_a_provider_outage_shows_the_plain_line_and_a_retry(dummy_orc, browser_page):
    """M160: Orc's plain line (error.user_message) is shown instead of the code, with Retry."""
    origin, _ = dummy_orc
    page = browser_page
    sign_in(page, origin)
    submit(page, 'Dummy provider down')
    page.get_by_role('button', name='Retry', exact=True).wait_for()
    text = page.locator('.run-inline-state').inner_text()
    assert 'Layanan AI sedang tidak tersedia' in text and 'SERVICE_UNAVAILABLE' not in text
    page.reload()
    page.locator('.conversation').first.click()  # the saved run, read again from the server, says the same
    page.get_by_role('button', name='Retry', exact=True).wait_for()
    assert 'Layanan AI sedang tidak tersedia' in page.locator('.run-inline-state').inner_text()
