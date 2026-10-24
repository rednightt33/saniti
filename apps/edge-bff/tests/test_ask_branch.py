"""EXEC-ASK-BRANCH in EDGE (user 2026-10-24: Branch "satu tab baru terpisah sama seperti feature chat GPT"; a side chat
"untuk nanya jawaban yang dikasih oleh AI"; "Ok untuk Q1 dan Q2"): Branch opens a new tab with the conversation that
continues the answer (its turns up to there, then a divider); "Ask about this answer" opens the answer's side chat in a
panel, which is not in the conversation list and is linked under the answer; a selected passage can be asked about
there. Served through the real BFF and queue; Orc is the test double; no AI call."""
from test_answer_view import SELECT_JS, article, fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, capture, saved, sign_in, submit  # noqa: F401 (fixtures)


def answered(page, origin, question='harga BBRI minggu ini'):
    sign_in(page, origin)
    submit(page, question)
    saved(page)


def test_branch_opens_a_new_tab_that_continues_the_answer(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    answered(page, origin)
    parent = orc.calls[-1]
    with page.context.expect_page() as opened:
        article(page).locator('.edge-branch-action').click()
    tab = opened.value
    tab.wait_for_load_state()
    tab.locator('.edge-branch-divider').wait_for(timeout=10000)
    assert 'Branched from' in tab.locator('.edge-branch-divider').inner_text()
    assert tab.locator('.research-exchange.inherited').count() == 1
    assert '/c/conv_' in tab.url and '#' not in tab.url and len(orc.branched) == 1 and orc.branched[0][1] == 0
    branch_id = tab.url.split('/c/')[1][:37]  # EXEC-CHAT-URL: the conversation's own address
    assert branch_id != parent[2].get('conversation_id')
    tab.get_by_placeholder('Ask a research question…').fill('lanjut dari sini')
    tab.get_by_role('button', name='Submit', exact=True).click()
    tab.wait_for_function('() => document.querySelectorAll("article.result").length === 2 && !document.querySelector(".composer-status")')
    assert orc.calls[-1][2]['conversation_id'] == branch_id
    divider = tab.locator('.edge-branch-divider').bounding_box()
    own = tab.locator('.research-exchange:not(.inherited)').bounding_box()
    assert divider['y'] < own['y']  # the divider sits before the branch's own question
    if (directory := __import__('os').environ.get('EDGE_UI_ARTIFACT_DIR')):
        tab.screenshot(path=f'{directory}/branch-tab.png')
    tab.close()


def test_the_side_chat_asks_about_one_answer_and_is_not_in_the_list(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    answered(page, origin)
    answered_id = orc.calls[-1][1]
    article(page).locator('.edge-ask-action').click()
    page.locator('.edge-side-chat iframe').wait_for()
    frame = page.frame_locator('.edge-side-frame')
    frame.locator('.edge-branch-divider').wait_for(timeout=10000)
    # EXEC-UI-1025 (user 2026-10-24): the side chat opens empty; the answer is named, not repeated
    assert 'Asking about the answer to “harga BBRI minggu ini”' in frame.locator('.edge-branch-divider').inner_text()
    assert frame.locator('.research-exchange').count() == 0 and frame.locator('.edge-side-empty').is_visible()
    assert frame.locator('.conversation-panel').is_hidden() and frame.locator('.edge-branch-action').count() == 0
    frame.get_by_placeholder('Ask a research question…').fill('kenapa naik?')
    frame.get_by_role('button', name='Submit', exact=True).click()
    frame.locator('article.result').first.wait_for(timeout=10000)
    side_id = orc.calls[-1][2]['conversation_id']
    assert side_id and side_id != orc.saved[answered_id]['conversation_id']
    capture(page, 'side-chat-open')
    page.get_by_role('button', name='Close side chat', exact=True).click()
    assert page.locator('.edge-side-chat').count() == 0
    article(page).locator('.edge-ask-action', has_text='Side chat (1)').wait_for(timeout=10000)
    assert page.locator('.conversation-list .conversation-item, .conversation-list [data-conversation-id]').count() <= 1
    article(page).locator('.edge-ask-action').click()  # the same side chat opens again
    page.frame_locator('.edge-side-frame').locator('article.result').first.wait_for(timeout=10000)
    assert len(orc.branched) == 1


def test_a_selected_passage_is_asked_about_in_the_side_chat(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    answered(page, origin)
    menu = page.locator('.edge-selection-menu')
    for _ in range(3):
        point = page.evaluate(SELECT_JS, '.edge-answer p|')
        page.mouse.click(point['x'], point['y'], button='right')
        if menu.count():
            break
        page.wait_for_timeout(300)
    menu.get_by_role('menuitem', name='Ask in side chat', exact=True).click()
    frame = page.frame_locator('.edge-side-frame')
    frame.locator('.edge-attached-chip').wait_for(timeout=10000)
    assert frame.locator('.edge-attached-chip').count() == 1
    assert page.locator('.composer .edge-attached-chip').count() == 0  # attached in the side chat, not the main box


def test_only_edge_itself_may_frame_edge(settings, store):
    """The side chat frames EDGE inside EDGE; any other site is still refused (frame-ancestors 'self')."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from conftest import FakeOrc
    with TestClient(create_app(settings, store, FakeOrc())) as client:
        policy = client.get('/monitor').headers['Content-Security-Policy']
    assert "frame-ancestors 'self'" in policy and "frame-ancestors 'none'" not in policy


def test_on_a_phone_the_side_chat_covers_the_page_and_its_header_is_clear(fixture_server, browser_page):
    """Live QA 2026-10-24 (phone): the page's menu buttons (z-index 125) showed over the side chat's header."""
    origin, orc = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 390, 'height': 844})
    answered(page, origin)
    article(page).locator('.edge-ask-action').click()
    page.frame_locator('.edge-side-frame').locator('.edge-branch-divider').wait_for(timeout=10000)
    head = page.locator('.edge-side-head').bounding_box()
    covered = page.evaluate("""([y, w]) => [...Array(13).keys()].map(i => 10 + i * (w - 20) / 12)
        .filter(x => !document.elementFromPoint(x, y)?.closest('.edge-side-chat'))""", [head['y'] + head['height'] / 2, head['width']])
    assert covered == [] and head['width'] >= 389, covered
    capture(page, 'side-chat-phone')


def test_links_edge_builds_open_when_the_page_was_opened_at_the_root(fixture_server, browser_page):
    """User 2026-10-24 (screenshots): EDGE opened at "/" built its links as /index.html#/monitor?c=..., which the BFF did
    not serve ({"detail":"Not Found"} in the Branch tab and the side chat). Every link EDGE builds must open, whichever
    page path ("/", "/monitor", "/login") the user started from."""
    origin, orc = fixture_server
    page = browser_page
    page.goto(origin + '/')
    page.get_by_label('Login', exact=True).fill('owner')
    page.get_by_label('Password', exact=True).fill('local-test-password')
    page.get_by_role('button', name='Sign In', exact=True).click()
    page.get_by_placeholder('Ask a research question…').wait_for()
    submit(page, 'harga BBRI minggu ini')
    saved(page)
    with page.context.expect_page() as opened:
        article(page).locator('.edge-branch-action').click()
    tab = opened.value
    tab.wait_for_load_state()
    tab.locator('.edge-branch-divider').wait_for(timeout=10000)
    article(page).locator('.edge-ask-action').click()
    page.frame_locator('.edge-side-frame').locator('.edge-branch-divider').wait_for(timeout=10000)
    page.reload()  # the address bar EDGE wrote after signing in opens again
    page.get_by_placeholder('Ask a research question…').wait_for(timeout=10000)
    tab.close()
