"""EXEC-UI-1024 (user 2026-10-24, with screenshots): the running status row in the message box is middle aligned
("1B ditengah dalam artian middle align, bukan center"), the empty Sources text starts where the panel's content starts
("1 C ya"), and attached passages are marked yellow in their answer, several can be attached, and each carries its own
comment while the message stays the general question ("2A-C yes benar"). Served through the real BFF and queue; no AI
call."""
import threading

from test_answer_view import attach_by_right_click, built_answer, fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, capture, saved, sign_in, submit  # noqa: F401 (fixtures)


def test_while_an_answer_runs_the_message_box_says_its_button_stops_it(fixture_server, browser_page):
    """MONITOR-REVAMP (user 2026-10-29, AI_revamp.html .cbar): the box has no running row (EXEC-UI-1024 1B); the hint
    beside the send button says what it does now, and the button is the red Stop."""
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original, release = orc.run, threading.Event()

    def slow(owner, id, payload):
        release.wait(timeout=20)
        return original(owner, id, payload)
    orc.run = slow
    try:
        submit(page, 'net beli asing BBRI')
        stop = page.get_by_role('button', name='Stop', exact=True)
        stop.wait_for(timeout=10000)
        assert 'stop' in stop.get_attribute('class') and not page.locator('.composer-running').count()
        assert page.locator('.composer .edge-send-hint').inner_text() == 'Running\u2026 press to stop'
        capture(page, 'ui1024-running-row')
    finally:
        release.set()
        orc.run = original
    saved(page)


def test_the_empty_sources_text_starts_where_the_panel_content_starts(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'apa itu saham?')
    saved(page)
    page.get_by_role('tab', name='Sources', exact=True).click()
    empty = page.locator('.sources-empty')
    empty.wait_for()
    place = empty.evaluate("""n => { const panel = n.closest('.edge-details-upper').getBoundingClientRect();
        const text = document.createRange(); text.selectNodeContents(n); const box = text.getBoundingClientRect();
        return {left: box.left - panel.left, top: box.top - panel.top}; }""")
    assert 10 <= place['left'] <= 18 and place['top'] <= 30, place
    assert page.locator('.edge-details-upper .details-empty').count() == 0


def test_attached_passages_are_marked_and_each_carries_its_own_comment(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original, built = built_answer(orc)
    orc.run = built
    submit(page, 'uji sinyal volume')
    saved(page)
    orc.run = original
    attach_by_right_click(page, '.edge-answer p|Periode studi')
    attach_by_right_click(page, '.edge-md-table tbody tr:nth-child(2)')
    chips = page.locator('.edge-attached-chip')
    assert chips.count() == 2
    marked = page.evaluate("""() => { const h = CSS.highlights && CSS.highlights.get('edge-attached');
        return h ? [...h].map(r => r.toString().replace(/\\s+/g, ' ').trim()) : null; }""")
    assert marked is not None and len(marked) == 2 and 'Periode studi' in marked[0], marked
    capture(page, 'ui1024-marked')
    chips.nth(0).locator('.edge-attached-comment').fill('kenapa periodenya mulai 2023?')
    submit(page, 'tolong jelaskan')
    saved(page, 2)
    sent = orc.calls[-1][2]
    assert sent['message'] == 'tolong jelaskan'
    assert [a.get('comment') for a in sent['attachments']] == ['kenapa periodenya mulai 2023?', None]
    assert page.evaluate("() => !CSS.highlights.has('edge-attached')")  # sent: nothing is attached any more


def test_an_attachment_is_a_quote_with_a_plain_note_under_it(fixture_server, browser_page):
    """EXEC-UI-1025 (user 2026-10-24, screenshot: the boxed comment field, "dibuat lebih nice"; benchmark ChatGPT and
    Claude; "Buat tanpa side bar accent"): the passage shows as a quote (no accent bar, at most two lines), the note is
    written under it without a box, and a long note grows the field instead of scrolling one line."""
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original, built = built_answer(orc)
    orc.run = built
    submit(page, 'uji sinyal volume')
    saved(page)
    orc.run = original
    attach_by_right_click(page, '.edge-answer p|Periode studi')
    chip = page.locator('.composer .edge-attached-chip')
    note = chip.locator('.edge-attached-comment')
    style = note.evaluate("n => { const c = getComputedStyle(n); return [c.borderTopWidth, c.borderBottomWidth, c.borderLeftWidth, c.backgroundColor]; }")
    # MONITOR-REVAMP (user 2026-10-29, AI_revamp.html .att): the note sits under a dashed line, without a box; the
    # attachment is a framed card with no side accent bar
    assert style[:3] == ['1px', '0px', '0px'] and style[3] in ('rgba(0, 0, 0, 0)', 'transparent'), style
    assert note.evaluate("n => getComputedStyle(n).borderTopStyle") == 'dashed'
    assert chip.evaluate("n => getComputedStyle(n).borderLeftWidth === getComputedStyle(n).borderRightWidth")
    assert chip.locator('.edge-attached-text').evaluate("n => getComputedStyle(n).webkitLineClamp") == '2'
    short = note.bounding_box()['height']
    note.fill('baris satu ' * 30)
    note.dispatch_event('input')
    assert note.bounding_box()['height'] > short
    capture(page, 'ui1025-quote')
