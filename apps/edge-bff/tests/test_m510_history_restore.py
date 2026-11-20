"""ERRORS M510: the Monitor page opening the conversation of its own address (/c/<id>, at load) is not the user choosing
it, so it leaves the phone's history panel as the user has it. On GitHub's runner the composer test failed three times
in a row: after a reload the test opened the history, and the page's own load, ending later on the slow machine, closed
it again (selectConversation closed the panel for every caller). Here the load is held at its second request (/runs)
until the user has opened the history, so the race happens on every machine, not only on a slow one. A choice from the
history still closes it."""
from test_answer_view import fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, saved, sign_in, submit  # noqa: F401 (fixtures)


def test_the_page_opening_its_own_conversation_leaves_the_opened_history_open(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'First response')
    saved(page)
    assert '/c/conv_' in page.url
    page.set_viewport_size({'width': 390, 'height': 844})
    held = []
    page.route('**/api/v1/runs', lambda route: held.append(route))
    page.reload()
    page.get_by_placeholder('Ask a research question…').wait_for()
    for _ in range(200):
        if held:
            break
        page.wait_for_timeout(25)
    assert held, 'the page did not ask for /runs while loading'
    page.get_by_role('button', name='Open history', exact=True).click()
    history = page.get_by_role('dialog', name='Conversation history', exact=True)
    history.wait_for()
    page.unroute('**/api/v1/runs')
    held[0].continue_()
    saved(page)                                   # the page has opened the conversation of its address
    page.wait_for_timeout(300)
    assert history.is_visible(), 'the page closed the history the user had opened'
    # the user's own choice from the history still closes it
    page.locator('.conversation-list .conversation').first.click()
    history.wait_for(state='hidden')
