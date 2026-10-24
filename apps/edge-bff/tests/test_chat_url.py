"""EXEC-CHAT-URL (user 2026-10-24: "B saja ya", after "chat gpt dan claude punya URL masing2 untuk setiap chat"): every
conversation has its own address, /c/<conversation_id>. Choosing a conversation shows its address, a reload or a new tab
at that address opens it, Back and Forward move between conversations, signing in at it opens it, and an older
#/monitor?c=<id> link still opens and is rewritten. Served through the real BFF; no AI call."""
from test_answer_view import fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, saved, sign_in, submit  # noqa: F401 (fixtures)


def path(page, origin):
    return page.url.removeprefix(origin)


def two_conversations(page, origin, orc):
    sign_in(page, origin)
    submit(page, 'harga BBRI minggu ini')
    saved(page)
    first = orc.calls[-1][2].get('conversation_id') or orc.saved[orc.calls[-1][1]]['conversation_id']
    page.wait_for_function('(id) => location.pathname === "/c/" + id', arg=first)
    page.get_by_role('button', name='New conversation').click()
    page.wait_for_function('() => location.pathname === "/monitor"')
    submit(page, 'harga BBCA minggu ini')
    saved(page)
    second = orc.saved[orc.calls[-1][1]]['conversation_id']
    page.wait_for_function('(id) => location.pathname === "/c/" + id', arg=second)
    return first, second


def test_each_conversation_has_its_own_address_and_back_moves_between_them(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    first, second = two_conversations(page, origin, orc)
    page.locator('.conversation-list').get_by_text('harga BBRI minggu ini').first.click()
    page.wait_for_function('(id) => location.pathname === "/c/" + id', arg=first)
    page.go_back()
    page.wait_for_function('(id) => location.pathname === "/c/" + id', arg=second)
    page.locator('article.result').first.wait_for()
    assert 'BBCA' in page.locator('.research-exchange').first.inner_text()
    page.reload()  # the address opens the same conversation
    page.locator('article.result').first.wait_for(timeout=10000)
    assert path(page, origin) == f'/c/{second}' and 'BBCA' in page.locator('.research-exchange').first.inner_text()


def test_a_conversation_address_opens_in_a_new_tab_and_after_signing_in(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    first, _ = two_conversations(page, origin, orc)
    tab = page.context.new_page()
    tab.goto(f'{origin}/c/{first}')
    tab.locator('article.result').first.wait_for(timeout=10000)
    assert 'BBRI' in tab.locator('.research-exchange').first.inner_text()
    tab.context.clear_cookies()  # signed out: the address survives signing in
    tab.goto(f'{origin}/c/{first}')
    tab.get_by_label('Login', exact=True).fill('owner')
    tab.get_by_label('Password', exact=True).fill('local-test-password')
    tab.get_by_role('button', name='Sign In', exact=True).click()
    tab.locator('article.result').first.wait_for(timeout=10000)
    assert path(tab, origin) == f'/c/{first}' and 'BBRI' in tab.locator('.research-exchange').first.inner_text()
    old = tab.context.new_page()  # an older hash link still opens and is rewritten
    old.goto(f'{origin}/index.html#/monitor?c={first}')
    old.locator('article.result').first.wait_for(timeout=10000)
    old.wait_for_function('(id) => location.pathname === "/c/" + id && !location.hash', arg=first)
    assert page.request.get(f'{origin}/c/not-a-conversation').status == 404
