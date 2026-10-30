"""EXEC-UI-1020C (user 2026-10-20 screenshots; go "Jalankan exec"): the GLM/MiMo logo in the run label in the main text
colour, no red border on a failed run, the pinned title never covering "No pinned responses", an open response card
visible in dark mode as in light, and one thin scrollbar in the Details panel."""
from test_answer_view import article, fixture_server  # noqa: F401 (fixture)
from test_ui_1019b import stalled_run
from test_visual import browser_page, capture, saved, sign_in, submit  # noqa: F401 (fixtures)


def glm_run(orc, original):
    def run(owner, id, payload):
        result = original(owner, id, payload)
        result['execution'].update(model='z-ai/glm-5.3-flash', reasoning_level='high')
        orc.saved[id].update(response=result)
        return result
    return run


def theme(page, name):
    button = page.get_by_role('button', name=f'Switch to {name} theme', exact=True)
    if button.count():
        button.click()
        page.wait_for_timeout(250)


def test_the_glm_logo_in_the_run_label_has_the_main_text_colour(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original = orc.run
    orc.run = glm_run(orc, original)
    try:
        submit(page, 'fx:answer_table')
        saved(page)
    finally:
        orc.run = original
    for name in ('dark', 'light'):
        theme(page, name)
        colours = article(page).evaluate("""a => { const logo = a.querySelector('.edge-run-model .edge-model-logo.mono');
          return [getComputedStyle(logo).backgroundColor, getComputedStyle(a.querySelector('h1')).color,
                  getComputedStyle(a.querySelector('.result-metadata')).color]; }""")
        assert colours[0] == colours[1] != colours[2], (name, colours)


def test_a_failed_run_has_no_red_border(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original = orc.run
    orc.run = stalled_run(orc, original, 'PROVIDER_STALLED')
    try:
        submit(page, 'net beli asing BBRI')
        state = page.locator('.run-inline-state.failed')
        state.wait_for(timeout=15000)
    finally:
        orc.run = original
    border, neutral = state.evaluate("""n => { const probe = document.createElement('div');
      probe.style.borderTop = '1px solid var(--border)'; n.parentElement.appendChild(probe);
      const colour = getComputedStyle(probe).borderTopColor; probe.remove();
      return [getComputedStyle(n).borderTopColor, colour]; }""")
    assert border == neutral, (border, neutral)
    assert state.get_by_role('button', name='Retry', exact=True).is_visible()


def test_the_pinned_title_never_covers_its_first_row_and_cards_show_in_both_themes(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:answer_table')
    saved(page)
    for name in ('dark', 'light'):
        theme(page, name)
        found = page.locator('.details-panel').evaluate("""p => { const r = n => n.getBoundingClientRect();
          const head = p.querySelector('.edge-pins-head'), empty = p.querySelector('.edge-pins-empty');
          const card = p.querySelector('.edge-flow-accordion[open] > summary');
          const panel = getComputedStyle(p.querySelector('.edge-details-upper .edge-flow-list') || p).backgroundColor;
          const bg = n => { for (; n; n = n.parentElement) { const c = getComputedStyle(n).backgroundColor;
                            if (c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') return c; } return null; };
          return {gap: r(empty).top - r(head).bottom, card: getComputedStyle(card).backgroundColor,
                  behind: bg(card.parentElement), width: getComputedStyle(p.querySelector('.edge-pins')).scrollbarWidth,
                  border: getComputedStyle(card).borderTopWidth, shadow: getComputedStyle(card).boxShadow}; }""")
        assert found['gap'] >= 0, (name, found)
        # MONITOR-REVAMP (AI_revamp.html .hist): a response card is the panel's surface raised by its border and shadow
        assert found['border'] == '1px' and found['shadow'] != 'none', (name, found)
        assert found['width'] == 'thin', (name, found)
        capture(page, f'ui-1020c-details-{name}')
