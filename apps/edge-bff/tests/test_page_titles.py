"""EXEC-TERMINAL-IND-EDIT (user 2026-11-05: "apapun tabnya selalu tulisannya Edge, Sign In, and Monitor. Boleh diganti
misalkan Edge, - terminal, backtest, screener"): the browser tab names the page; the words are in edge-labels.js."""
import re

from test_answer_view import fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, sign_in  # noqa: F401 (fixtures)


def test_the_tab_title_names_each_page(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    # the framed apps are other builds; a blank page stands in so this test reads only the EDGE shell
    for app in ('terminal-app', 'backtest-app', 'screener-app'):
        page.route(re.compile(rf'.*/{app}/.*'), lambda route: route.fulfill(status=200, content_type='text/html',
                                                                          body='<!doctype html><title>frame</title>'))
    page.goto(origin + '/monitor')
    page.get_by_label('Login', exact=True).wait_for()
    assert page.title() == 'EDGE — Sign In'
    sign_in(page, origin)
    assert page.title() == 'EDGE — Monitor'
    for nav, title in (('Terminal', 'EDGE — Terminal'), ('Backtest', 'EDGE — Backtest'), ('Screener', 'EDGE — Screener'),
                       ('Monitor', 'EDGE — Monitor')):
        page.locator('header.topbar nav').get_by_role('button', name=nav, exact=True).click()
        page.wait_for_function('t => document.title === t', arg=title)
    # a page opened directly by its address gets its own title, and back/forward keeps it in step
    page.goto(origin + '/screener')
    page.wait_for_function("() => document.title === 'EDGE — Screener'")
    page.go_back()
    page.wait_for_function("() => document.title === 'EDGE — Monitor'")
