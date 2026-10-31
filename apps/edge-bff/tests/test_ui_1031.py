"""M317 (user 2026-10-31, phone screenshots A-E): every status dot has the colour of its run's state and none is grey,
also for a conversation the page has not opened yet (A, D); the reasoning level reads as its label and the answer head
keeps one rhythm (B); the folded sections share one gap and the phone's action row keeps one gap (C); the phone's
session row holds Details and the run's state (D); a folded list's bullets sit inside the card (E)."""
from test_answer_view import article, fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, capture, saved, sign_in, submit  # noqa: F401 (fixtures)

PHONE = {'width': 375, 'height': 812}
TONES = """() => [
  Edge.statusTone('running'), Edge.statusTone('submitted'), Edge.statusTone('failed'), Edge.statusTone('completed', 'FAILED'),
  Edge.statusTone('completed', 'COMPLETED'), Edge.statusTone('completed', 'AWAITING_CONFIRMATION'),
  Edge.statusTone('completed', 'NEEDS_CLARIFICATION'), Edge.statusTone('completed', 'LIMITED'),
  Edge.statusTone('completed', 'COMPLETED', true), Edge.statusTone('completed', 'COMPLETED', false, true), Edge.statusTone(undefined)]"""
DOT = "n => [getComputedStyle(n).backgroundColor, getComputedStyle(n).boxShadow]"
GREY = ('rgb(220, 220, 220)', 'rgb(51, 51, 51)', 'rgb(143, 143, 143)')


def test_every_status_dot_has_a_colour_and_none_is_grey(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    page.set_viewport_size(PHONE)
    sign_in(page, origin)
    assert page.evaluate(TONES) == ['info', 'info', 'negative', 'negative', 'positive', 'warning', 'warning', 'warning',
                                    'warning', 'warning', 'new']
    submit(page, 'fx:plan_v1')  # a plan awaiting approval: yellow
    saved(page)
    page.get_by_role('button', name='New Chat', exact=True).click()
    submit(page, 'fx:answer_table')  # a completed answer: green
    saved(page)
    # the list API gives each row its latest question's state, so a row this page never opened is coloured too
    rows = page.evaluate("async () => (await Edge.conversations()).map(c => c.lastRun)")
    assert {'status': 'completed', 'domainStatus': 'AWAITING_CONFIRMATION'} in rows, rows
    assert {'status': 'completed', 'domainStatus': 'COMPLETED'} in rows, rows
    page.reload()
    page.get_by_placeholder('Ask a research question…').wait_for()
    page.get_by_role('button', name='Open history').click()
    dots = page.locator('.conversation-list .conversation-state')
    dots.first.wait_for()
    classes = sorted(c.split('edge-tone-')[1] for c in dots.evaluate_all('ns => ns.map(n => n.className)'))
    assert classes == ['positive', 'warning'], classes
    for colour, ring in dots.evaluate_all(f'ns => ns.map({DOT})'):
        assert colour not in GREY and colour != 'rgba(0, 0, 0, 0)', colour
    capture(page, 'm315-list')


def test_the_phone_session_row_holds_details_and_the_coloured_state(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    page.set_viewport_size(PHONE)
    sign_in(page, origin)
    submit(page, 'fx:answer_table')
    saved(page)
    bar = page.locator('.workspace-tools')
    box = bar.evaluate("""b => { const r = n => n.getBoundingClientRect(), d = b.querySelector('[aria-label="Show Details"]'),
        p = b.querySelector('.pill'), dot = b.querySelector('.live-dot,.pulse');
      return {details: r(d), pill: r(p), bar: r(b), label: getComputedStyle(b.querySelector('.edge-session-label')).display,
              dot: getComputedStyle(dot).backgroundColor, tone: dot.className}; }""")
    # one row: the state on the Details row's right, inside the bar; "Research session" left out for the room
    assert abs((box['pill']['top'] + box['pill']['bottom']) - (box['details']['top'] + box['details']['bottom'])) <= 2, box
    assert box['pill']['left'] > box['details']['right'] and box['pill']['right'] <= box['bar']['right'], box
    assert box['label'] == 'none' and 'edge-tone-positive' in box['tone'] and box['dot'] not in GREY, box
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    capture(page, 'm315-session-row')


def test_the_answer_head_folds_and_actions_keep_one_rhythm(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    page.set_viewport_size(PHONE)
    sign_in(page, origin)
    submit(page, 'fx:answer_table')
    saved(page)
    a = article(page)
    a.locator('details.edge-notes[data-section=ASSUMPTIONS]>summary').click()
    m = a.evaluate("""a => { const r = n => n.getBoundingClientRect(), meta = a.querySelector('.result-metadata');
      const items = [...meta.children].map(r), lines = [...new Set(items.map(x => Math.round(x.top)))].sort((x, y) => x - y);
      const d = a.querySelector('details.edge-notes[data-section=ASSUMPTIONS]'), s = d.querySelector('summary'),
            li = d.querySelector('li'), range = document.createRange(); range.selectNodeContents(s);
      const label = range.getClientRects()[0].left; range.selectNodeContents(li);
      const level = meta.querySelector('.edge-run-model-level');
      const acts = [...a.querySelectorAll('.result-actions>*')].map(r);
      return {titleGap: r(meta).top - r(a.querySelector('h1')).bottom, evidenceGap: r(a.querySelector('.edge-evidence-line')).top - r(meta).bottom,
              heights: items.map(x => Math.round(x.height)), lines, level: level && level.textContent,
              composerLevel: document.querySelector('.composer .edge-model-level')?.textContent,
              composerTransform: getComputedStyle(document.querySelector('.composer .edge-model-level')).textTransform,
              liText: range.getClientRects()[0].left, label, card: r(a).left, marker: r(li).left - parseFloat(getComputedStyle(d.querySelector('ul')).paddingLeft),
              acts: acts.map(x => [Math.round(x.left), Math.round(x.right), Math.round(x.top)])}; }""")
    # B: one 8 px rhythm from the title to the evidence line, every metadata item one 20 px line
    assert abs(m['titleGap'] - 8) <= 1 and abs(m['evidenceGap'] - 8) <= 1, m
    assert set(m['heights']) == {20}, m
    assert all(abs((y - x) - 28) <= 1 for x, y in zip(m['lines'], m['lines'][1:])), m
    if m['level'] is not None:
        assert m['level'].strip(' ·') == m['level'].strip(' ·').capitalize(), m
    assert m['composerTransform'] == 'none', m
    # E: the bullets' text starts under the fold's title, the list inside the card
    assert abs(m['liText'] - m['label']) <= 2 and m['marker'] > m['card'], m
    # C: the action row's buttons on one line keep one gap (Branch is not pushed right)
    row = [x for x in m['acts'] if x[2] == m['acts'][0][2]]
    gaps = [b[0] - a_[1] for a_, b in zip(row, row[1:])]
    assert max(gaps) - min(gaps) <= 1, m
    capture(page, 'm315-answer')


def test_the_suggestion_folds_and_the_notes_share_one_gap(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    page.set_viewport_size(PHONE)
    sign_in(page, origin)
    submit(page, 'fx:follow_ups')
    saved(page)
    gaps = article(page).evaluate("""a => { const s = [...a.querySelectorAll('.edge-discs>details>summary')].map(n => n.getBoundingClientRect());
      return s.slice(1).map((x, i) => Math.round(x.top - s[i].bottom)); }""")
    assert len(gaps) >= 2 and max(gaps) - min(gaps) <= 1, gaps


def test_no_draft_label_and_history_shares_the_list_colours(fixture_server, browser_page):
    """User 2026-10-31 ("hapus huruf draft"; "response history hurufnya boleh dirapihkan"): the empty page and the phone's
    session row show no "Draft"; a Response history line takes the list's colour and the Pinned title's type."""
    origin, orc = fixture_server
    page = browser_page
    page.set_viewport_size(PHONE)
    sign_in(page, origin)
    assert 'Draft' not in page.locator('.research-workspace').inner_text()
    page.set_viewport_size({'width': 1440, 'height': 900})
    submit(page, 'fx:plan_v1')
    saved(page)
    item = page.locator('.edge-flow-accordion>summary').first
    item.wait_for()
    got = item.evaluate("""s => { const t = getComputedStyle(s.querySelector('strong')), d = s.querySelector('.edge-history-dot');
      return {size: t.fontSize, weight: t.fontWeight, line: t.lineHeight, dot: d && d.className}; }""")
    assert got['size'] == '12px' and got['weight'] == '500' and got['line'] == '17px', got
    assert got['dot'] and 'warning' in got['dot'], got


def test_the_conversation_fades_above_the_message_box_and_an_answer_read_to_its_end_is_not_faded(fixture_server, browser_page):
    """User 2026-10-31 (screenshot, "garis pembatas ... dihilangkan"): the conversation ended in a hard edge above the
    message box, an answer card cut across like a dividing line; its last pixels now fade into the page, inside the
    space under the last answer."""
    origin, _ = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 1440, 'height': 800})
    sign_in(page, origin)
    submit(page, 'fx:table_align')
    saved(page)
    for width, fade in ((1440, 24), (390, 8)):
        page.set_viewport_size({'width': width, 'height': 800})
        page.wait_for_timeout(300)
        scroll = page.locator('.research-scroll')
        assert f'calc(100% - {fade}px)' in scroll.evaluate('s => getComputedStyle(s).maskImage || getComputedStyle(s).webkitMaskImage')
        scroll.evaluate('s => s.scrollTo({top: s.scrollHeight, behavior: "instant"})')
        page.wait_for_timeout(300)
        last = page.locator('article.result').last.bounding_box()
        view = scroll.bounding_box()
        assert last['y'] + last['height'] <= view['y'] + view['height'] - fade + 1, (width, last, view)


def test_a_table_is_as_wide_as_its_content_with_even_gaps_and_a_line_above_its_titles(fixture_server, browser_page):
    """User 2026-10-31 (screenshot): "jarak antara kolom ke kolom tidak even sama seperti sebelumnya" (the table was
    stretched over the card and the spare width went to the wide columns) and "tambah border" above the titles."""
    origin, _ = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    sign_in(page, origin)
    submit(page, 'fx:table_align')
    saved(page)
    for table in page.locator('article.result').last.locator('.edge-md-table').all():
        spare = table.evaluate("""f => { const t = f.querySelector('table');
            const width = e => { const r = document.createRange(); r.selectNodeContents(e); return r.getBoundingClientRect().width; };
            // a long text column wraps within 28 characters (EXEC-UI-1015D), its lines ragged: it is left out
            return [...t.querySelectorAll('thead th')].map((th, i) => t.querySelector(`tbody tr td:nth-child(${i + 1})`).classList.contains('edge-col-text') ? null : th.getBoundingClientRect().width - Math.max(
                (th.querySelector('.edge-sort-label') || th).getBoundingClientRect().width,
                ...[...t.querySelectorAll(`tbody tr td:nth-child(${i + 1})`)].map(width))); }""")
        inner = [s for s in spare[1:-1] if s is not None]  # the first and last columns have no outer padding
        assert inner and max(inner) - min(inner) <= 3, spare
        assert table.evaluate("f => f.querySelector('table').getBoundingClientRect().width <= f.getBoundingClientRect().width + 1")
        top, bottom = table.locator('thead th').first.evaluate(
            "th => [getComputedStyle(th).borderTopWidth + ' ' + getComputedStyle(th).borderTopColor, getComputedStyle(th).borderBottomWidth + ' ' + getComputedStyle(th).borderBottomColor]")
        assert top == bottom and top.startswith('1px'), (top, bottom)
