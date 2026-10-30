"""EXEC-UI-1015C (user 2026-10-15, "Ok, confirmed. Go."). Desktop: the session bar above the chat is gone, its Details,
bookmark and share buttons sit in the rail, and each response in Response History has a way back to it in the
conversation. Phone: the rail's menu and "+" sit in the header between the logo and search, the chat takes the full
width, the session bar stays, and settings opens from the account menu. The EDGE "E" is the favicon, public like the
page."""
import copy
import urllib.request

from test_answer_view import fixture_server  # noqa: F401 (fixture)
from test_ui_1015 import FIXTURES  # noqa: F401 (registers the ui1015 fixtures)
from test_visual import browser_page, capture, dummy_orc, saved, server, sign_in, submit  # noqa: F401 (fixtures)


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
        # MONITOR-REVAMP (AI_revamp.html .nav-acts): an open desktop sidebar carries Details and Share beside its menu
        # button and bookmarks from the conversation's row; the folded rail keeps Bookmark
        for name in ('Bookmark', 'Share latest answer') if width <= 1050 else ('Share latest answer',):
            button = page.get_by_role('button', name=name, exact=True)
            assert button.is_visible()
            b = button.bounding_box()
            assert rail['x'] <= b['x'] and b['x'] + b['width'] <= rail['x'] + rail['width'] + 1, (width, name)
        # MONITOR-REVAMP (user 2026-10-30): the sidebar's Share opens the Share menu of the latest answer
        page.get_by_role('button', name='Share latest answer', exact=True).click()
        menu = page.locator('.conversation-panel .edge-share-menu')
        menu.wait_for()
        assert menu.get_by_role('menuitem').all_inner_texts() == ['PDF (document)', 'PNG (image)', 'Word (document)']
        m = menu.bounding_box()
        assert m['x'] >= 0 and m['x'] + m['width'] <= width, (width, m)
        assert page.evaluate('([x, y]) => Boolean(document.elementFromPoint(x, y)?.closest(".edge-share-menu"))',
                             [m['x'] + m['width'] / 2, m['y'] + m['height'] - 8])  # not clipped by the sidebar
        page.get_by_role('button', name='Share latest answer', exact=True).click()
        menu.wait_for(state='detached')
        if width <= 1050:
            page.get_by_role('button', name='Bookmark', exact=True).click()
            page.wait_for_function("() => document.querySelector('[aria-label=Bookmark]').getAttribute('aria-pressed') === 'true'")
        else:
            page.locator('.conversation.active').get_by_role('button', name='Add bookmark', exact=True).click()
            page.locator('.conversation.active').get_by_role('button', name='Remove bookmark', exact=True).wait_for(state='attached')
        if width > 1050:  # details open by default on a wide screen: the rail button closes and opens it
            page.get_by_role('button', name='Hide Details', exact=True).click()
            page.locator('.details-panel').wait_for(state='hidden')
        page.get_by_role('button', name='Show Details', exact=True).click()
        page.get_by_text('Response history', exact=True).wait_for()
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
    first = page.locator('.edge-flow-accordion').last  # newest-first history: oldest response is last
    if not first.evaluate('n => n.open'):
        first.locator('summary').click()
    page.wait_for_timeout(200)
    before = page.evaluate(scroll)
    first.get_by_role('button', name='Go to message').click()
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
    first = page.locator('.edge-flow-accordion').last  # retain the test's jump to the oldest response
    if not first.evaluate('n => n.open'):
        first.locator('summary').click()
    run_id = first.get_attribute('id').replace('edge-history-', '')
    first.get_by_role('button', name='Go to message').click()
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
        plus = page.get_by_role('button', name='New Chat', exact=True).bounding_box()
        for b in (menu, plus):  # inside the header, between the logo and search
            assert top['y'] <= b['y'] and b['y'] + b['height'] <= top['y'] + top['height'] + 1
        assert brand['x'] + brand['width'] < menu['x'] < menu['x'] + menu['width'] <= plus['x']
        assert plus['x'] + plus['width'] <= search['x'], (width, plus, search)
        assert box(page, '.research-workspace')['width'] >= width - 1  # no rail
        assert page.locator('.workspace-tools').is_visible()  # the phone session bar stays
        assert not page.get_by_role('button', name='Settings', exact=True).is_visible()
        page.get_by_role('button', name='Account menu', exact=True).click()
        page.get_by_role('menuitem', name='Settings', exact=True).click()
        page.get_by_role('dialog', name='Appearance', exact=True).wait_for()
        page.keyboard.press('Escape')
        page.get_by_role('button', name='Open history', exact=True).click()  # the history drawer still opens
        page.get_by_placeholder('Search conversations').wait_for(state='visible')
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


BROKERS = ('Pembeli teratas.\n\n| Saham | Tanggal efektif | Broker | Net beli (Rp) |\n|---|---|---|---:|\n'
           '| TPIA | 31 Mei 2024 | BK – J.P. Morgan Sekuritas Indonesia | 1.274.504.292.525 |\n'
           '| BRMS | 25 Nov 2025 | YU – CGS International Sekuritas Indonesia | 1.556.195.108.075 |\n'
           '| ENRG | 25 Nov 2025 | KI – Ciptadana Sekuritas Asia | 539.600.000 |\n')
SHORT = 'Return.\n\n| Saham | 20h sebelum | 20h sesudah |\n|---|---:|---:|\n| ENRG | −8,1% | 42,9% |\n| RAJA | −16,6% | 17,5% |\n'
FIXTURES['ui1015d_brokers'] = copy.deepcopy(FIXTURES['answer_table'])
FIXTURES['ui1015d_brokers']['response']['answer'] = BROKERS
FIXTURES['ui1015d_short'] = copy.deepcopy(FIXTURES['answer_table'])
FIXTURES['ui1015d_short']['response']['answer'] = SHORT


def test_answer_tables_are_compact_and_never_break_a_word(fixture_server, browser_page):
    """EXEC-UI-1015D (user 2026-10-15, "jarak antara kolom tidak compact. seek best practice"): a table is as wide as its
    content, short columns (codes, dates, numbers) stay on one line, a text column wraps between words only, and on a
    phone the first column stays in view while the table scrolls sideways. The header reads "EDGE · Completed" (UI-1015E)."""
    origin, _ = fixture_server
    page = browser_page
    for width in (1440, 390):
        page.set_viewport_size({'width': width, 'height': 900})
        sign_in(page, origin)
        submit(page, 'fx:ui1015d_short')
        saved(page)
        submit(page, 'fx:ui1015d_brokers')
        saved(page, 2)
        short = page.locator('article.result').nth(0).locator('.edge-md-table')
        table_width = short.locator('table').evaluate('t => t.getBoundingClientRect().width')
        frame_width = short.evaluate('f => f.getBoundingClientRect().width')
        natural = short.locator('table').evaluate("t => { const w = t.style.width; t.style.width = 'max-content'; "
                                                  "const n = t.getBoundingClientRect().width; t.style.width = w; return n; }")
        # MONITOR-REVAMP (user 2026-10-29, AI_revamp.html .tblscroll): at least as wide as its content, and on a wide
        # screen the whole framed box
        assert table_width >= natural - 1 and table_width <= frame_width, (width, table_width, natural)
        if width > 720:
            assert frame_width - table_width <= 3, (table_width, frame_width)
        cells = page.locator('article.result').nth(1).locator('tbody tr').first.locator('td')
        one_line = cells.nth(0).evaluate('td => parseFloat(getComputedStyle(td).lineHeight)')
        for column in (0, 1, 3):  # code, date, amount: one line each
            assert cells.nth(column).evaluate("td => getComputedStyle(td).whiteSpace") == 'nowrap'
        broker = cells.nth(2)
        assert broker.evaluate("td => getComputedStyle(td).overflowWrap") == 'normal'
        words = broker.evaluate("""td => { const range = document.createRange(), text = td.firstChild ? td : null, out = [];
            const walker = document.createTreeWalker(td, NodeFilter.SHOW_TEXT); let node;
            while ((node = walker.nextNode())) { for (const m of node.textContent.matchAll(/\\S+/g)) {
              range.setStart(node, m.index); range.setEnd(node, m.index + m[0].length); out.push(range.getClientRects().length); } }
            return out; }""")
        assert words and all(rects == 1 for rects in words), words  # no word split across lines
        if width == 390:
            assert cells.nth(0).evaluate("td => getComputedStyle(td).position") == 'sticky'
        kicker = page.locator('article.result').nth(1).locator('.result-kicker')
        # EXEC-UI-1015E (user 2026-10-15): the earlier muted, letter-spaced style, "Completed" as written
        assert kicker.text_content() == 'EDGE'  # user 2026-10-21: Completed is not written
        weight, transform, spacing = kicker.evaluate(
            "k => { const s = getComputedStyle(k); return [s.fontWeight, s.textTransform, "
            "(parseFloat(s.letterSpacing) || 0) / parseFloat(s.fontSize)]; }")
        assert (weight, transform) == ('500', 'none') and spacing == 0  # MONITOR-REVAMP (AI_revamp.html .kick): no letter spacing
        assert kicker.evaluate("k => getComputedStyle(k).color") == kicker.evaluate(
            "k => getComputedStyle(k.closest('article').querySelector('.result-metadata')).color")
        page.context.clear_cookies()


ALIGN = """Perbandingan YTD per tahun:

| Tahun | Saham | YTD | Hari |
|:---:|---|:---:|---|
| 2019 | BBRI | 7,7% | 193 |
| 2019 | BMRI | −10,8% | 193 |
| 2020 | BBRI | −24,8% | 194 |

Posisi tahun ini:

| Saham | YTD 2026 | Ayunan wajar 185 hari | Jarak vs ayunan |
|---|---|---|---|
| BBRI | −15,3% | 28% | −0,54 |
| BMRI | −22,0% | 29% | −0,76 |

Broker teratas:

| Saham | Tanggal efektif | Broker | Beli bersih |
|---|---|---|---|
| TPIA | 31 Mei 2024 | BK – J.P. Morgan Sekuritas Indonesia | Rp 1,2 miliar |
| GGRM | 31 Mei 2024 | AK – UBS Sekuritas Indonesia | Rp 71,5 miliar |
"""
# the lines a title's text takes (its text nodes only: the sort icon sits beside the text, not on a line of its own)
TEXT_LINES = """s => { const w = document.createTreeWalker(s, NodeFilter.SHOW_TEXT); const tops = new Set();
    for (let n = w.nextNode(); n; n = w.nextNode()) { const r = document.createRange(); r.selectNodeContents(n);
      [...r.getClientRects()].filter(x => x.width > 0).forEach(x => tops.add(Math.round(x.top))); }
    return tops.size; }"""
FIXTURES['table_align'] = copy.deepcopy(FIXTURES['answer_table'])
FIXTURES['table_align']['response']['answer'] = ALIGN


def test_tables_align_left_and_middle_keep_titles_on_one_line_and_draw_no_vertical_line(fixture_server, browser_page):
    """E13 (EXEC-1018B, user 2026-10-16 "Nama kolom rata kiri dan center, isi juga rata kiri"; replaces EXEC-TABLE-ALIGN's
    right-aligned quantities and fourteen-character titles): every title and cell left-aligned and vertically centred,
    numbers included and whatever alignment the writer typed; a title up to fourteen characters (EXEC-UI-1019B; was
    twenty-eight) stays on one line, so the column is its widest title or value plus the same padding; no vertical
    line, also with the phone's sticky first column."""
    origin, _ = fixture_server
    page = browser_page
    for width in (1440, 390):
        page.set_viewport_size({'width': width, 'height': 900})
        sign_in(page, origin)
        submit(page, 'fx:table_align')
        saved(page)
        tables = page.locator('article.result').last.locator('.edge-md-table table')
        for table in range(3):
            # MONITOR-REVAMP (user 2026-10-29, AI_revamp.html .md .tbl): text left and numbers right; the titles sit in
            # the middle of their row, the values start at the top of theirs
            cells = tables.nth(table).evaluate("""t => [...t.rows].flatMap(r => [...r.cells].map(c => {
                const inner = c.querySelector('.edge-sort') || c; return [c.tagName, c.classList.contains('num'),
                getComputedStyle(c).textAlign, getComputedStyle(inner).textAlign, getComputedStyle(c).verticalAlign]; }))""")
            assert all((align == 'right' if num and tag == 'TD' else inner in ('left', 'start'))
                       and valign == ('middle' if tag == 'TH' else 'top') for tag, num, align, inner, valign in cells), (width, table, cells[:6])
        title = tables.nth(1).locator('th').nth(2)
        lines = title.locator('.edge-sort-label').evaluate(TEXT_LINES)
        cell = tables.nth(1).locator('tbody tr').first.locator('td').nth(2)
        assert lines == 2  # EXEC-UI-1019B: "Ayunan wajar 185 hari" is longer than 14 characters, so it wraps
        assert cell.evaluate("td => getComputedStyle(td).whiteSpace") == 'nowrap'
        # a column's title starts where its values start (the same padding everywhere)
        for column in (1, 2, 3):
            if tables.nth(1).locator('tbody tr').first.locator('td').nth(column).evaluate("td => td.classList.contains('num')"):
                continue  # MONITOR-REVAMP (AI_revamp.html .md .tbl .num): a number column's values stand on the right
            head_left = tables.nth(1).locator('th').nth(column).locator('.edge-sort-label').evaluate(
                "s => { const r = document.createRange(); r.selectNodeContents(s); return r.getBoundingClientRect().left; }")
            cell_left = tables.nth(1).locator('tbody tr').first.locator('td').nth(column).evaluate(
                "td => { const r = document.createRange(); r.selectNodeContents(td); return r.getBoundingClientRect().left; }")
            assert abs(head_left - cell_left) <= 4, (column, head_left, cell_left)
        for table in range(3):
            shadows = tables.nth(table).evaluate("""t => [...t.querySelectorAll('th,td')].map(c => {
                const s = getComputedStyle(c); return [s.boxShadow, s.borderLeftWidth, s.borderRightWidth]; })""")
            assert all(box == 'none' and left == '0px' and right == '0px' for box, left, right in shadows), shadows[:3]
        # MONITOR-REVAMP (AI_revamp.html .tblscroll): the table fills its framed box, as wide as the answer
        for table in range(3):
            fill = tables.nth(table).evaluate("t => t.parentElement.clientWidth - t.getBoundingClientRect().width")
            assert fill <= 1 or width <= 720, (width, table, fill)
        # the phone's sticky first cell takes its row's hover colour (the row reads as one band)
        row = tables.nth(1).locator('tbody tr').first
        row.locator('td').nth(1).hover()
        first, other = row.evaluate("r => [...r.cells].slice(0, 2).map(c => getComputedStyle(c).backgroundColor)")
        row_color = row.evaluate("r => getComputedStyle(r).backgroundColor")
        assert first == other, (width, first, other, row_color)  # MONITOR-REVAMP: every cell of the row takes the hover fill
        if directory := __import__('os').environ.get('EDGE_UI_ARTIFACT_DIR'):
            page.locator('article.result').last.locator('.edge-answer').screenshot(path=f'{directory}/table-align-{width}.png')
        page.context.clear_cookies()


TITLES = """Judul pendek dan panjang:

| Saham | Rata-rata nilai beli bersih asing harian | Ayunan wajar 185 hari |
|---|---|---|
| BBRI | Rp 1,2 miliar | 28% |
| BMRI | Rp 71,5 miliar | 29% |
"""
FIXTURES['table_titles'] = copy.deepcopy(FIXTURES['answer_table'])
FIXTURES['table_titles']['response']['answer'] = TITLES


def test_a_short_title_never_wraps_and_a_long_title_folds_within_its_width(fixture_server, browser_page):
    """E13 (EXEC-1018B; EXEC-UI-1019B narrowed it to fourteen characters): a short title stays on one line at every width
    (on a phone the table scrolls sideways instead); a longer title folds between words within about fourteen."""
    origin, _ = fixture_server
    page = browser_page
    lines = TEXT_LINES
    for width in (1440, 390):
        page.set_viewport_size({'width': width, 'height': 900})
        sign_in(page, origin)
        submit(page, 'fx:table_titles')
        saved(page)
        heads = page.locator('article.result').last.locator('.edge-md-table table th')
        assert heads.nth(0).evaluate("t => t.classList.contains('edge-title-long')") is False
        assert heads.nth(1).evaluate("t => t.classList.contains('edge-title-long')") is True
        # EXEC-UI-1019B (user 2026-10-19 "label width >X maka teks di wrapped"): a title longer than 14 characters wraps
        # between words within 14ch, so a column is no wider than its values need
        assert heads.nth(2).evaluate("t => t.classList.contains('edge-title-long')") is True
        assert heads.nth(2).locator('.edge-sort-label').evaluate(lines) == 2, width
        assert heads.nth(1).locator('.edge-sort-label').evaluate(lines) >= 3, width
        assert heads.nth(0).locator('.edge-sort-label').evaluate(lines) == 1, width
        heads.nth(0).evaluate("t => t.closest('.edge-md-table').scrollIntoView({block: 'center'})")
        capture(page, f'e13-table-titles-{width}')
        page.context.clear_cookies()
