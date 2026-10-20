"""EXEC 2026-10-20 (user screenshots): the table icons' gap, an even answer head with the evidence line in the metadata
row's type and a green check, a question-made title cut at a word, visible hover on the conversation buttons, "Data
Scope" in the model picker's type, a shadow instead of a darker border on the message box in use, the progress close
under the question and followed to the bottom, and no "Standard" label."""
import threading

from test_answer_view import article, fixture_server  # noqa: F401 (fixture)
from test_ui_1019b import with_kept_table
from test_visual import browser_page, capture, saved, sign_in, submit  # noqa: F401 (fixtures)

LONG = ('lakukan scan terhadap kondisi market terkahir, identify candle yang ada buying power dan perlawanan '
        '(piercing, hammer, engulfing, marubozu) sort by transaction volume')


def answered(orc, message):
    original = orc.run

    def run(owner, id, payload):
        return original(owner, id, {**payload, 'message': 'fx:answer_table'})
    return original, run


def test_the_answer_head_is_even_and_the_evidence_line_reads_like_the_metadata(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original, run = answered(orc, LONG)
    orc.run = run
    try:
        submit(page, LONG)
        saved(page)
    finally:
        orc.run = original
    # the fixture answers under its own name, so the cut is checked on the function the views use
    cut = page.evaluate("q => Edge.shortTitle(q)", LONG)
    assert cut.endswith('…') and len(cut) <= 80 and (cut[:-1] + ' ') in (LONG + ' '), cut
    assert page.evaluate("q => Edge.shortTitle(q)", 'pendek') == 'pendek'
    head = article(page).evaluate("""a => { const r = n => n.getBoundingClientRect(), s = n => getComputedStyle(n);
      const h = a.querySelector('h1'), m = a.querySelector('.result-metadata'), t = a.querySelector('.edge-evidence-line'),
            b = t.querySelector('.edge-badge'), req = m.querySelector('span'), ans = a.querySelector('.edge-answer');
      return {title: h.textContent, titleGap: r(m).top - r(h).bottom, evidenceGap: r(t).top - r(m).bottom,
              answerGap: r(ans).top - r(t).bottom, font: [s(b).fontFamily, s(b).fontSize], requestFont: [s(req).fontFamily,
              s(req).fontSize], check: !!t.querySelector('svg.edge-evidence-check circle[fill="#16a34a"]')}; }""")
    assert abs(head['titleGap'] - head['evidenceGap']) <= 1, head
    assert 22 <= head['answerGap'] <= 26, head
    assert head['font'] == head['requestFont'] and head['check'], head
    capture(page, 'ui-1020-answer-head')


def test_conversation_buttons_show_their_hover_on_a_selected_row(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:answer_table')
    saved(page)
    row = page.locator('.conversation-list .conversation[role=button]').first
    assert 'active' in row.get_attribute('class')
    button = row.locator('.conversation-bookmark').first
    button.hover()
    page.wait_for_timeout(250)
    row_bg = row.evaluate("n => getComputedStyle(n).backgroundColor")
    button_bg = button.evaluate("n => getComputedStyle(n).backgroundColor")
    assert button_bg != row_bg and button_bg not in ('rgba(0, 0, 0, 0)', 'transparent'), (row_bg, button_bg)


def test_data_scope_matches_the_model_picker_and_the_box_in_use_has_a_shadow(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    page.locator('.composer .edge-model-trigger:not([disabled])').wait_for()
    font = "n => { const t = n.querySelector('.edge-model-name') || n, s = getComputedStyle(t); " \
           "return [s.fontFamily, s.fontSize, s.fontWeight]; }"
    picker = page.locator('.composer .edge-model-trigger').evaluate(font)
    scope = page.locator('.composer [title="Data Scope is not available yet"]').evaluate(font)
    assert picker == scope, (picker, scope)
    composer = page.locator('.composer')
    idle = composer.evaluate("n => getComputedStyle(n).borderColor")
    page.locator('textarea').click()
    page.locator('textarea').fill('abc')
    used = composer.evaluate("n => [getComputedStyle(n).borderColor, getComputedStyle(n).boxShadow]")
    assert used[0] == idle and used[1] != 'none', (idle, used)


def test_the_table_icons_stand_eight_pixels_above_the_table(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original, built = with_kept_table(orc)
    orc.run = built
    try:
        submit(page, 'uji sinyal volume')
        saved(page)
    finally:
        orc.run = original
    gap = article(page).locator('.edge-md-table-frame').first.evaluate(
        "f => f.querySelector('.edge-md-table').getBoundingClientRect().top - "
        "f.querySelector('.edge-table-tools').getBoundingClientRect().bottom")
    assert 7 <= gap <= 9, gap


def test_progress_sits_under_the_question_follows_to_the_bottom_and_has_no_lane_label(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 1280, 'height': 700})
    sign_in(page, origin)
    for n in range(2):  # enough conversation above to scroll
        submit(page, 'fx:answer_table')
        saved(page, n + 1)
    original = orc.run
    release = threading.Event()
    steps = [{'label': 'Understanding the question', 'state': 'done', 'started_ms': 0, 'duration_ms': 2000}]

    def slow(owner, id, payload):
        orc.PROGRESS = {id: {'status': 'RUNNING', 'elapsed_ms': 5000, 'earlier_steps': 0, 'steps': steps}}
        release.wait(timeout=30)
        return original(owner, id, {**payload, 'message': 'fx:answer_table'})
    orc.run = slow
    try:
        submit(page, 'untuk menjalankan pertanyaan tersebut, boleh describe dimana proses terlama terjadi?')
        page.locator('.edge-run-progress').wait_for(timeout=10000)
        gap = page.evaluate("""() => { const w = document.querySelector('.edge-inline-progress-wrap');
            const f = w.previousElementSibling; return w.querySelector('.edge-inline-progress span:last-child')
              .getBoundingClientRect().top - f.querySelector('.user-sent-at').getBoundingClientRect().bottom; }""")
        assert gap <= 26, gap
        assert 'Standard' not in page.locator('.composer-status').first.inner_text()
        # more steps arrive: the page stays at the bottom while it follows
        for n in range(8):
            steps.append({'label': f'Step {n}', 'state': 'done', 'started_ms': 2000 + n, 'duration_ms': 1000})
        steps.append({'label': 'Thinking', 'state': 'running', 'started_ms': 9000, 'duration_ms': 3000})
        page.locator('.edge-run-progress-done summary').wait_for(timeout=10000)
        page.locator('.edge-run-progress-done summary').evaluate("s => s.parentElement.open = true")
        page.wait_for_timeout(700)
        rest = page.locator('.research-scroll').evaluate("s => s.scrollHeight - s.scrollTop - s.clientHeight")
        assert rest <= 2, rest
        capture(page, 'ui-1020-progress')
    finally:
        release.set()
        orc.run = original
    saved(page, 3)
