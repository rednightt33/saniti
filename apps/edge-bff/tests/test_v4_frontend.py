"""V4 (user 2026-10-14, EDGE screenshots): a table opens in a wide dialog; Return on a phone adds a line; a choice sent
at once has no "Kirim balasan langsung"; no empty band between "AI request running" and the composer on a phone."""
import socket
import threading
import time
from dataclasses import replace

import pytest
import uvicorn

from app.main import create_app
from test_answer_view import FixtureOrc, article, fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, saved, sign_in, submit  # noqa: F401 (fixture)


def test_a_table_opens_in_a_wide_dialog_with_its_title_and_closes_with_escape(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:answer_table')
    saved(page)
    frame = article(page).locator('.edge-md-table-frame')
    assert frame.count() == 1
    frame.get_by_role('button', name='Enlarge table', exact=True).click()
    dialog = page.get_by_role('dialog')
    dialog.wait_for()
    assert dialog.locator('table.data-table tbody tr').count() == 2
    assert dialog.locator('#dialog-description').inner_text() == '2 rows'
    assert dialog.locator('#dialog-title').inner_text().startswith('Hasil uji')  # the section's heading
    box = dialog.bounding_box()
    assert box['width'] >= 1400 - 60  # wide: most of the 1600 px window
    page.keyboard.press('Escape')
    page.wait_for_function('() => !document.querySelector("[role=dialog]")')
    page.set_viewport_size({'width': 390, 'height': 760})
    frame.get_by_role('button', name='Enlarge table', exact=True).click()
    box = page.get_by_role('dialog').bounding_box()
    assert box['x'] <= 1 and box['width'] >= 389  # full screen on a phone
    page.get_by_role('dialog').get_by_role('button', name='Close', exact=True).click()


def test_return_adds_a_line_on_a_touch_phone_and_enter_sends_with_a_mouse(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    phone = page.context.browser.new_context(viewport={'width': 390, 'height': 760}, has_touch=True, is_mobile=True)
    try:
        touch = phone.new_page()
        touch.route('https://fonts.*/*', lambda route: route.abort())
        sign_in(touch, origin)
        assert touch.evaluate('matchMedia("(pointer: coarse)").matches')
        box = touch.get_by_placeholder('Ask a research question…')
        box.click()
        box.type('baris satu')
        touch.keyboard.press('Enter')
        box.type('baris dua')
        assert box.input_value() == 'baris satu\nbaris dua' and len(orc.calls) == 0
    finally:
        phone.close()
    sign_in(page, origin)
    page.get_by_placeholder('Ask a research question…').fill('Explain GOTO')
    page.get_by_placeholder('Ask a research question…').press('Enter')
    saved(page)
    assert len(orc.calls) == 1


class SlowOrc(FixtureOrc):
    def run(self, owner, id, payload):
        time.sleep(4 if payload['message'].startswith('slow') else 0)
        return super().run(owner, id, payload)


@pytest.fixture
def slow_server(settings, store):
    orc = SlowOrc()
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    settings = replace(settings, origin=f'http://127.0.0.1:{port}', worker_enabled=True, poll_seconds=0.02)
    server = uvicorn.Server(uvicorn.Config(create_app(settings, store, orc), log_level='critical', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True); thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    try:
        yield settings.origin
    finally:
        server.should_exit = True; thread.join(timeout=10); sock.close()


def test_on_a_phone_the_running_line_sits_right_above_the_composer(slow_server, browser_page):
    page = browser_page
    page.set_viewport_size({'width': 390, 'height': 664})
    sign_in(page, slow_server)
    submit(page, 'Explain GOTO')
    saved(page)
    submit(page, 'slow question')
    page.locator('.edge-inline-progress').wait_for()
    time.sleep(0.5)
    gap = page.evaluate('''() => {
        // MONITOR-REVAMP (AI_revamp.html): the running answer is a card; its bottom edge is measured
        const progress = [...document.querySelectorAll(".edge-inline-progress-wrap")].pop().getBoundingClientRect();
        return document.querySelector(".composer").getBoundingClientRect().top - progress.bottom; }''')
    assert 0 <= gap <= 20, gap  # was 60 px (22 exchange margin + 32 scroll padding + 6 composer margin)
