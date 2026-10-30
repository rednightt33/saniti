"""EXEC-FASTLANE V5 (user 2026-10-14; every lane and English months since 2026-10-30): dates in an answer read "7 October 2026", a month "September 2024"
and a year "2020"; a pinned response opened on a phone closes Details
first; a question sent while reading higher up scrolls down to it. The phone model menu (a bottom sheet in V5) became
a panel above the composer in EXEC-UI-1015 U5: tests/test_ui_1015.py."""
import copy

from test_answer_view import FIXTURES, article, fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, dummy_orc, saved, server, sign_in, submit  # noqa: F401 (fixtures)

DATED = ('Periode 2026-10-07 sampai 2024-09; jam 2026-10-07T10:00 dan `2024-01-02` tetap.\n\n'
         '| Tahun | Bulan | Return |\n|---|---|---|\n| 2.020 | 2024-09 | 1,50% |\n| 2.021 | 2024-10 | 2,10% |')


def dated(lane):
    envelope = copy.deepcopy(FIXTURES['answer_table'])
    envelope['response'].update(answer=DATED, assumptions=['Data sampai 2026-08-31.'], limitations=[],
                                methodology='Return harian 2026-01-02 s.d. 2026-08-31.')
    envelope.setdefault('execution', {})['lane'] = lane
    return envelope


FIXTURES['v5_fast_dates'] = dated('fast')
FIXTURES['v5_standard_dates'] = dated('standard')


def test_dates_in_every_answer_are_written_out_in_english(fixture_server, browser_page):
    # user 2026-10-30 ("format date ... DD MMMM YYYY", chose "19 October 2026"): every lane, months in English
    origin, _ = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:v5_fast_dates')
    saved(page)
    # MONITOR-REVAMP (AI_revamp.html .discs): Assumptions, Limitations and Methodology fold; they are opened to read them
    article(page).locator('.edge-discs details').evaluate_all('nodes => nodes.forEach(node => { node.open = true; })')
    text = article(page).inner_text()
    assert 'Periode 7 October 2026 sampai September 2024' in text
    assert '2026-10-07T10:00' in text and '2024-01-02' in text  # a time and code keep their text
    cells = article(page).locator('.edge-answer table.data-table tbody tr').first.locator('td').all_inner_texts()
    assert cells[:2] == ['2020', 'September 2024']
    assert '31 August 2026' in text and '2 January 2026' in text  # assumptions and methodology too
    header = article(page).locator('.edge-answer th').nth(1).locator('button')
    header.click()  # a written-out month still sorts as a date: descending puts October first
    assert article(page).locator('.edge-answer tbody tr').first.locator('td').nth(1).inner_text() == 'October 2024'
    submit(page, 'fx:v5_standard_dates')
    saved(page, 2)
    standard = article(page).inner_text()
    assert 'Periode 7 October 2026 sampai September 2024' in standard and '2.020' not in standard  # the standard lane too


def test_a_pinned_response_opened_on_a_phone_closes_details_and_shows_the_response(dummy_orc, browser_page):
    origin, _ = dummy_orc
    page = browser_page
    page.set_viewport_size({'width': 390, 'height': 760})
    sign_in(page, origin)
    submit(page, 'Dummy pin first')
    saved(page)
    page.get_by_role('button', name='Pin', exact=True).first.click()
    page.get_by_role('button', name='Pinned', exact=True).wait_for()
    for i in range(2):
        submit(page, f'Dummy later {i}')
        saved(page, i + 2)
    page.get_by_role('button', name='Show Details', exact=True).click()
    page.get_by_role('dialog', name='Response details', exact=True).wait_for()
    page.get_by_role('button', name='Expand pinned response', exact=True).click()
    page.get_by_role('button', name='View full response →', exact=True).click()
    page.wait_for_function("() => !document.querySelector('[role=dialog][aria-label=\"Response details\"]')")
    page.wait_for_function("""() => { const node = document.querySelectorAll('article.result')[0], view = document.querySelector('.research-scroll');
        const top = node.getBoundingClientRect().top - view.getBoundingClientRect().top; return top >= -2 && top <= 80; }""")


def test_a_question_sent_while_reading_higher_up_scrolls_down_to_it(dummy_orc, browser_page):
    origin, _ = dummy_orc
    page = browser_page
    page.set_viewport_size({'width': 1280, 'height': 800})
    sign_in(page, origin)
    for i in range(2):
        submit(page, f'Dummy long {i}')
        saved(page, i + 1)
    page.evaluate("() => { const view = document.querySelector('.research-scroll'); view.scrollTo({top: 0}); view.dispatchEvent(new Event('scroll')); }")
    page.wait_for_function("() => document.querySelector('.research-scroll').scrollTop === 0")
    submit(page, 'Dummy long 2')
    # the new question comes into view at once, before its answer arrives
    page.wait_for_function("""() => { const asked = [...document.querySelectorAll('.user-message')].at(-1), view = document.querySelector('.research-scroll');
        if (!asked || !asked.innerText.includes('Dummy long 2')) return false;
        const box = asked.getBoundingClientRect(), frame = view.getBoundingClientRect();
        return box.top >= frame.top - 2 && box.top < frame.bottom - 40; }""")
    saved(page, 3)
