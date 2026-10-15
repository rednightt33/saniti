"""EXEC-UI-1015 (user 2026-10-15): a details section the reader opened stays open while the page redraws (U1, M156);
one small gap between the last message and the composer (U2); a reading column of about 768 px with the side panels
open or closed (U3); a table over ten rows folds the rest behind one button (U4); the thinking level and the lane sit
in the chosen model card, and on a phone the menu is a panel above the composer (U5)."""
import copy

from test_answer_view import FIXTURES, article, fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, saved, sign_in, submit  # noqa: F401 (fixtures)

ROWS = 30
TABLE = ('Rincian per saham.\n\n| Saham | Return |\n|---|---|\n'
         + '\n'.join(f'| S{i:02d} | {i},00% |' for i in range(1, ROWS + 1)) + '\n| Total | 99,00% |')


def envelope(answer=None):
    built = copy.deepcopy(FIXTURES['answer_table'])
    if answer is not None:
        built['response']['answer'] = answer
    return built


FIXTURES['ui1015_long_table'] = envelope(TABLE)
FIXTURES['ui1015_notes'] = envelope()


def test_an_opened_note_stays_open_while_the_page_redraws_on_scroll(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 1280, 'height': 700})
    sign_in(page, origin)
    submit(page, 'fx:ui1015_notes')
    saved(page)
    notes = article(page).locator('details.edge-notes').first
    notes.locator('summary').click()
    assert notes.evaluate('n => n.open')
    marker = notes.evaluate('n => (n._probe = "same", n._probe)')
    for top in (0, 50, 400, 120):  # every scroll redraws the view (M156)
        page.evaluate("t => { const s = document.querySelector('.research-scroll'); s.scrollTop = t; s.dispatchEvent(new Event('scroll')); }", top)
        page.wait_for_timeout(120)
    assert notes.evaluate('n => n._probe') == marker  # the same node, patched in place
    assert notes.evaluate('n => n.open')
    notes.locator('summary').click()  # the reader can still close it
    page.evaluate("() => { const s = document.querySelector('.research-scroll'); s.scrollTop = 10; s.dispatchEvent(new Event('scroll')); }")
    page.wait_for_timeout(120)
    assert not notes.evaluate('n => n.open')


def test_one_gap_above_the_composer_and_a_768_column_with_panels_open_or_closed(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 1920, 'height': 1000})
    sign_in(page, origin)
    submit(page, 'fx:ui1015_notes')
    saved(page)
    bottom = "() => { const s = document.querySelector('.research-scroll'); s.scrollTo({top: s.scrollHeight, behavior: 'instant'}); }"
    measure = """() => { const ex = [...document.querySelectorAll('.research-exchange')].at(-1), comp = document.querySelector('.composer');
        return {gap: comp.getBoundingClientRect().top - ex.getBoundingClientRect().bottom,
                exchange: ex.getBoundingClientRect().width, composer: comp.getBoundingClientRect().width}; }"""
    page.evaluate(bottom)
    page.wait_for_timeout(300)
    first = page.evaluate(measure)
    assert 14 <= first['gap'] <= 22, first
    assert first['exchange'] <= 768.5 and first['composer'] <= 768.5, first
    show = page.get_by_role('button', name='Show Details', exact=True)
    if show.count():
        show.click()
    else:
        page.get_by_title('Close details').click()
    page.evaluate(bottom)
    page.wait_for_timeout(300)
    second = page.evaluate(measure)
    assert second['exchange'] <= 768.5 and second['composer'] <= 768.5 and abs(second['exchange'] - first['exchange']) <= 1, second


def test_a_long_table_shows_ten_rows_and_folds_the_rest_behind_one_button(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 1280, 'height': 900})
    sign_in(page, origin)
    submit(page, 'fx:ui1015_long_table')
    saved(page)
    table = article(page).locator('.edge-answer table.data-table')
    visible = lambda: table.locator('tbody tr:visible').all_inner_texts()
    rows = visible()
    assert len(rows) == 11 and rows[0].startswith('S01') and rows[9].startswith('S10') and rows[-1].startswith('Total')
    more = article(page).locator('.edge-table-more')
    assert more.inner_text() == 'Tampilkan 20 baris lagi' and more.get_attribute('aria-expanded') == 'false'
    more.click()
    assert len(visible()) == ROWS + 1 and more.inner_text() == 'Sembunyikan baris'
    more.click()
    assert len(visible()) == 11
    # sorting orders every row, then the first ten of that order show: descending puts S30 first
    table.locator('th').nth(1).locator('button').click()
    rows = visible()
    assert rows[0].startswith('S30') and rows[9].startswith('S21') and rows[-1].startswith('Total')
    # a redraw (scroll) keeps the open state of the fold
    more.click()
    page.evaluate("() => { const s = document.querySelector('.research-scroll'); s.scrollTop = 30; s.dispatchEvent(new Event('scroll')); }")
    page.wait_for_timeout(120)
    assert len(visible()) == ROWS + 1
    more.click()
    # the wide dialog shows every row
    article(page).locator('.edge-table-expand').click()
    dialog = page.locator('.edge-table-dialog')
    dialog.wait_for()
    assert dialog.locator('tbody tr:visible').count() == ROWS + 1 and not dialog.locator('.edge-table-more').count()
    page.keyboard.press('Escape')


def test_the_level_and_lane_sit_in_the_chosen_model_card(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 1280, 'height': 900})
    sign_in(page, origin)
    page.locator('.edge-model-trigger:not([disabled])').click()
    cards = page.locator('.edge-model-card')
    assert cards.count() == 4 and page.locator('.edge-model-card.chosen').count() == 1
    chosen = page.locator('.edge-model-card.chosen')
    levels = chosen.locator('.edge-model-levels[role=radiogroup] button')
    assert levels.count() >= 2 and page.locator('.edge-model-levels').count() == chosen.locator('.edge-model-levels').count()
    # the settings sit right of the model's name, inside the card
    card, controls = chosen.bounding_box(), chosen.locator('.edge-model-controls').bounding_box()
    name = chosen.locator('.edge-model-option').bounding_box()
    assert controls['x'] >= name['x'] + name['width'] - 1 and controls['x'] + controls['width'] <= card['x'] + card['width'] + 1
    index = next(i for i in range(4) if not cards.nth(i).evaluate('n => n.classList.contains("chosen")'))
    other = cards.nth(index)
    other.locator('.edge-model-option').click()
    assert other.evaluate('n => n.classList.contains("chosen")') and other.locator('.edge-model-controls').count() == 1
    assert page.locator('.edge-model-controls').count() == 1
    page.keyboard.press('Escape')


def test_on_a_phone_the_model_menu_is_a_panel_above_the_composer(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    page.set_viewport_size({'width': 390, 'height': 700})
    sign_in(page, origin)
    page.locator('.edge-model-trigger:not([disabled])').click()
    menu = page.locator('.edge-model-menu')
    menu.wait_for()
    box, composer = menu.bounding_box(), page.locator('.composer').bounding_box()
    header = page.locator('.topbar').bounding_box()
    assert abs(box['x'] - composer['x']) <= 1 and abs(box['width'] - composer['width']) <= 1, (box, composer)
    assert box['y'] + box['height'] <= composer['y'] + 1, (box, composer)  # above the composer, never over it
    assert box['y'] >= header['y'] + header['height'] - 1, (box, header)  # never over the header
    assert page.evaluate("() => getComputedStyle(document.querySelector('.edge-model-menu')).overflowY === 'auto'")
    for x, y in ((box['x'] + 6, box['y'] + 30), (box['x'] + box['width'] / 2, box['y'] + 8), (box['x'] + 6, box['y'] + box['height'] - 20)):
        assert page.evaluate("([x, y]) => !!document.elementFromPoint(x, y)?.closest('.edge-model-menu')", [x, y]), (x, y)
    chosen = page.locator('.edge-model-card.chosen')
    assert chosen.locator('.edge-model-levels button').count() >= 2
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.keyboard.press('Escape')
