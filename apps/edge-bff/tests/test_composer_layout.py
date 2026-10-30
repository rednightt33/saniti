"""EXEC-UI-1019: real HTTP/queue/DB, mouse and emulated touch; no paid AI calls."""
import json
import os
from pathlib import Path

import pytest

from test_answer_view import fixture_server  # noqa: F401
from test_visual import capture, saved, sign_in, submit


@pytest.fixture(params=[(1920, 1080, False), (1280, 800, False), (390, 844, True), (360, 740, True)],
                ids=['desktop-wide', 'desktop-compact', 'mobile', 'mobile-small'])
def device_page(request):
    from playwright.sync_api import sync_playwright
    width, height, touch = request.param
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': width, 'height': height}, is_mobile=touch, has_touch=touch)
        page = context.new_page()
        page.set_default_timeout(6000)
        page.route('https://fonts.*/*', lambda route: route.abort())
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            yield page, touch, request.node.callspec.id
            assert not errors, errors
        finally:
            context.close()
            browser.close()


def aligned(page):
    dimensions = page.evaluate("""() => {
        const response = document.querySelector('article.result').getBoundingClientRect();
        const composer = document.querySelector('.composer').getBoundingClientRect();
        return {left:response.left-composer.left, right:response.right-composer.right,
                width:response.width, composerWidth:composer.width, overflow:document.documentElement.scrollWidth-innerWidth,
                debug:[...document.querySelectorAll('.research-workspace,.research-scroll,.research-exchange,.composer')].slice(-4).map(n=>({cls:n.className,x:n.getBoundingClientRect().x,width:n.getBoundingClientRect().width,client:n.clientWidth,offset:n.offsetWidth,padding:getComputedStyle(n).padding,margin:getComputedStyle(n).margin,scrollbar:getComputedStyle(n).getPropertyValue('--edge-conversation-scrollbar'),transform:getComputedStyle(n).transform,left:getComputedStyle(n).left,right:getComputedStyle(n).right,position:getComputedStyle(n).position,scrollLeft:n.scrollLeft,offsetLeft:n.offsetLeft}))};
    }""")
    assert abs(dimensions['left']) <= 1 and abs(dimensions['right']) <= 1, json.dumps(dimensions)
    assert dimensions['overflow'] <= 0, dimensions
    return dimensions


def drag(page, touch, amount):
    handle = page.get_by_role('separator', name='Resize message box', exact=True)
    box = handle.bounding_box()
    x, y = box['x'] + box['width']/2, box['y'] + box['height']/2
    if touch:
        cdp = page.context.new_cdp_session(page)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
        for i in range(1, 9):
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y-amount*i/8}]})
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        cdp.detach()
    else:
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x, y-amount, steps=8)
        page.mouse.up()


def test_alignment_and_border_resize(fixture_server, device_page):
    origin, _ = fixture_server
    page, touch, name = device_page
    sign_in(page, origin)
    submit(page, 'fx:answer_table')
    saved(page)
    # Force a classic, non-overlay scrollbar too (the user's Windows screenshots have one).
    page.add_style_tag(content='.research-scroll{overflow-y:scroll!important;scrollbar-gutter:stable;scrollbar-width:auto}.research-scroll::-webkit-scrollbar{width:16px}')
    page.wait_for_timeout(200)
    if not touch:
        assert page.locator('.research-scroll').evaluate('n=>n.offsetWidth-n.clientWidth') > 0
    measurements = {'before': aligned(page)}
    field = page.locator('.composer textarea')
    start = field.bounding_box()['height']
    drag(page, touch, 110)
    page.wait_for_timeout(120)
    grown = field.bounding_box()['height']
    assert grown >= start + 80, (start, grown)
    field.fill('A manually resized draft')
    field.press('End')
    field.press('x')
    assert abs(field.bounding_box()['height'] - grown) <= 1
    drag(page, touch, -60)
    page.wait_for_timeout(120)
    assert field.bounding_box()['height'] <= grown - 45
    handle = page.get_by_role('separator', name='Resize message box', exact=True)
    handle.focus()
    smaller = field.bounding_box()['height']
    page.keyboard.press('ArrowUp')
    assert field.bounding_box()['height'] >= smaller + 20
    measurements['resized'] = aligned(page)
    field.focus()
    capture(page, 'ui1019-' + name + '-resized')
    # MONITOR-REVAMP (user 2026-10-29): the page starts light; the dark theme is one press away
    page.get_by_role('button', name='Switch to dark theme', exact=True).click()
    page.wait_for_timeout(400)  # theme colour transitions must settle before visual review
    aligned(page)
    capture(page, 'ui1019-' + name + '-dark')
    # Bound height on a small/rotated viewport; toolbar and conversation stay usable.
    page.set_viewport_size({'width': 740 if touch else 1280, 'height': 390 if touch else 620})
    page.wait_for_timeout(200)
    field_box, panel_box = field.bounding_box(), page.locator('.composer').bounding_box()
    assert panel_box['y'] >= 55 and panel_box['y'] + panel_box['height'] <= page.viewport_size['height'] + 1
    assert field_box['height'] <= page.viewport_size['height'] * .55
    aligned(page)
    capture(page, 'ui1019-' + name + '-short-viewport')
    if directory := os.environ.get('EDGE_UI_ARTIFACT_DIR'):
        (Path(directory) / ('ui1019-' + name + '-alignment.json')).write_text(json.dumps(measurements, indent=2))


def test_submit_history_and_fixed_headers(fixture_server, device_page):
    origin, _ = fixture_server
    page, touch, name = device_page
    sign_in(page, origin)
    if not touch:
        page.get_by_title('Close details', exact=True).click()
    field = page.locator('.composer textarea')
    field.fill('First response')
    if touch:
        field.press('Enter')  # touch keyboard retains multiline editing
        assert field.input_value().endswith('\n')
        assert page.locator('article.result').count() == 0
        page.get_by_role('button', name='Send', exact=True).click()
    else:
        field.press('Shift+Enter')
        assert field.input_value().endswith('\n')
        assert page.locator('article.result').count() == 0
        field.press('Enter')
    saved(page)
    assert not page.locator('.details-panel').is_visible()
    for i in range(1, 8):
        page.locator('article.result').last.get_by_role('button', name='Pin', exact=True).click()
        submit(page, f'Response {i+1:02d}')
        saved(page, i+1)
        assert not page.locator('.details-panel').is_visible()
    page.locator('article.result').last.get_by_role('button', name='Pin', exact=True).click()
    # Explicitly open the panel; each header stays at its own scroll area's top.
    if touch:
        page.get_by_role('button', name='Show Details', exact=True).click()
    else:
        page.get_by_title('Show Details', exact=True).click()
    panel = page.locator('.details-panel')
    panel.wait_for(state='visible')
    titles = panel.locator('.edge-flow-accordion > summary strong').all_inner_texts()
    assert titles == [f'Response {i:02d}' for i in range(8, 1, -1)] + ['First response']
    pin_titles = panel.locator('.edge-pin-title').all_inner_texts()
    assert pin_titles == ['First response'] + [f'Response {i:02d}' for i in range(2, 9)]
    for container, header in [('.edge-pins', '.edge-pins-head'), ('.edge-details-upper', '.edge-history-head')]:
        scroll = page.locator(container)
        scroll.evaluate('n=>n.scrollTop=0')
        page.wait_for_timeout(100)
        before = page.locator(header).bounding_box()['y']
        scroll.evaluate('n=>n.scrollTop=n.scrollHeight')
        page.wait_for_timeout(100)
        # MONITOR-REVAMP (AI_revamp.html .sec): Pinned responses grows with its cards (up to half the panel), so it may
        # scroll only a little; the title still never moves
        assert scroll.evaluate('n=>n.scrollTop') > 0
        after = page.locator(header).bounding_box()['y']
        assert abs(before-after) <= 1, (container, before, after)
        assert page.locator(header + ' button').is_visible()
    capture(page, 'ui1019-' + name + '-headers-scrolled')
    # Collapse/reopen stays interactive and the history order survives server reload.
    for label in ('Pinned responses', 'Response history'):
        toggle = panel.get_by_role('button', name=label, exact=True)
        toggle.tap() if touch else toggle.click()
        assert toggle.get_attribute('aria-expanded') == 'false'
        toggle.tap() if touch else toggle.click()
        assert toggle.get_attribute('aria-expanded') == 'true'
        toggle.focus()
        toggle.press('Enter')
        assert toggle.get_attribute('aria-expanded') == 'false'
        toggle.press('Space')
        assert toggle.get_attribute('aria-expanded') == 'true'
        toggle.click()  # a real mouse can follow touch/keyboard without being swallowed
        assert toggle.get_attribute('aria-expanded') == 'false'
        toggle.click()
        assert toggle.get_attribute('aria-expanded') == 'true'
    page.reload()
    field.wait_for()
    if touch:
        page.get_by_role('button', name='Open history', exact=True).click()
    page.locator('.conversation-list .conversation').first.click()
    saved(page, 8)
    if touch:
        page.get_by_role('button', name='Show Details', exact=True).click()
    assert panel.locator('.edge-flow-accordion > summary strong').all_inner_texts() == titles
    assert panel.locator('.edge-pin-title').all_inner_texts() == pin_titles
    capture(page, 'ui1019-' + name + '-history')
    if touch:
        page.get_by_title('Close details', exact=True).click()
    submit(page, 'Newest response with panel open on desktop')
    saved(page, 9)
    if touch:
        assert not panel.is_visible()
        page.get_by_role('button', name='Show Details', exact=True).click()
    else:
        assert panel.is_visible()
    newest = panel.locator('.edge-flow-accordion > summary').first
    assert newest.locator('strong').inner_text() == 'Newest response with panel open on desktop'
    assert newest.bounding_box()['y'] >= page.locator('.edge-history-head').bounding_box()['y'] + page.locator('.edge-history-head').bounding_box()['height'] - 1
