"""EXEC-X (M124): the answer view reads the response's structure. Responses are real saved Orc envelopes from dev
(UI GT 2026-10-08 and golden run c; tests/fixtures/orc_responses.json), served through the real BFF, queue and SSE; the
pause fixture is built with Orc's own stop_policy. No AI call is made."""
from dataclasses import replace
import copy
import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from app.main import create_app
from conftest import FakeOrc
from test_visual import browser_page, capture, saved, sign_in, submit  # noqa: F401 (fixture)

FIXTURES = json.loads((Path(__file__).parent / 'fixtures' / 'orc_responses.json').read_text())


class FixtureOrc(FakeOrc):
    """A message "fx:<name>" answers with that saved envelope; anything else is FakeOrc's plain answer."""
    def run(self, owner, id, payload):
        time.sleep(0.05)
        result = super().run(owner, id, payload)
        name = payload['message'].removeprefix('fx:')
        if name in FIXTURES:
            saved_envelope = copy.deepcopy(FIXTURES[name])
            saved_envelope.update(request_id=id, conversation=result['conversation'])
            result = saved_envelope
            self.saved[id].update(response=result, run_status=result['status'])
        return result


@pytest.fixture
def fixture_server(settings, store):
    orc = FixtureOrc()
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    settings = replace(settings, origin=f'http://127.0.0.1:{port}', worker_enabled=True, poll_seconds=0.02)
    server = uvicorn.Server(uvicorn.Config(create_app(settings, store, orc), log_level='critical', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True); thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    try:
        yield settings.origin, orc
    finally:
        server.should_exit = True; thread.join(timeout=10); sock.close()


def article(page, index=-1):
    return page.locator('article.result').nth(index)


def capture_answer(page, name, width=1280):
    """With EDGE_UI_ARTIFACT_DIR: the whole latest answer as one image (a tall viewport, so nothing is cut)."""
    if directory := os.environ.get('EDGE_UI_ARTIFACT_DIR'):
        size = page.viewport_size
        page.set_viewport_size({'width': width, 'height': 4600})
        article(page).screenshot(path=str(Path(directory) / (name + '.png')), animations='disabled')
        page.set_viewport_size(size)


def test_markdown_answer_renders_headings_bold_and_tables_as_elements(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:answer_table')
    saved(page)
    answer = article(page).locator('.edge-answer')
    text = answer.inner_text()
    assert '**' not in text and '|---' not in text and '## ' not in text
    assert answer.locator('h3').count() >= 1 and answer.locator('strong').count() >= 1
    table = answer.locator('table.data-table')
    assert table.count() == 1 and table.locator('tbody tr').count() == 2
    assert 'Setelah sinyal' in table.locator('thead').inner_text()
    assert article(page).locator('.result-kicker').text_content() == 'EDGE'
    assert page.locator('.workspace-tools .pill').inner_text().endswith('Completed')  # the frame stays English
    page.get_by_role('tab', name='Sources', exact=True).click()
    assert page.locator('.sources').get_by_text('Conversation data record').is_visible()
    capture(page, 'x-answer-table-dark')
    capture_answer(page, 'full-answer-table-dark')
    page.get_by_role('button', name='Switch to light theme', exact=True).click()
    capture(page, 'x-answer-table-light')
    capture_answer(page, 'full-answer-table-light')


def test_plan_card_has_no_raw_json_and_its_buttons_reply_in_indonesian(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:plan_v1')
    saved(page)
    plan = article(page).locator('.edge-plan')
    plan.wait_for()
    assert not article(page).locator('pre').count()  # no JSON dump in the answer view
    assert '"plan_version"' not in article(page).inner_text()
    experiments = FIXTURES['plan_v1']['response']['research_plan']['experiments']
    assert plan.locator('.edge-plan-item').count() == len(experiments)
    assert 'Experiment 1' in plan.text_content() and 'Horizon' in plan.text_content()
    assert 'Awaiting approval' in plan.inner_text()
    assert page.locator('.workspace-tools .pill').inner_text().endswith('Awaiting approval')
    capture(page, 'x-plan-v1-dark')
    capture_answer(page, 'full-plan-v1-dark')
    capture_answer(page, 'full-plan-v1-mobile', 390)
    page.set_viewport_size({'width': 390, 'height': 844})
    article(page).locator('.edge-plan').scroll_into_view_if_needed()
    capture(page, 'x-plan-v1-mobile')
    page.set_viewport_size({'width': 1600, 'height': 1000})
    # EXEC-CHOICES: the "Response choices" panel under the plan: a labelled separator, Setujui as the main choice sent
    # at once, Revisi completed in the message box first
    panel = article(page).locator('.edge-response-choices')
    assert panel.locator('.edge-boundary-label').inner_text().upper() == 'YOUR NEXT STEP'
    approve = panel.get_by_role('button', name='Approve & run', exact=True)
    revise = panel.get_by_role('button', name='Revise', exact=True)
    # V4 (user 2026-10-14): a choice sent at once has no subtitle ("Kirim balasan langsung" removed)
    assert 'primary' in approve.get_attribute('class') and approve.locator('small').count() == 0
    assert 'Fill in the message box first' in revise.inner_text() and 'Write' in revise.inner_text()
    calls = len(orc.calls)
    revise.click()
    page.locator('.composer-status').wait_for()
    assert len(orc.calls) == calls and 'Chosen' in revise.inner_text()  # nothing sent: the user writes first
    page.locator('.composer-status').get_by_role('button', name='Dismiss').click()
    approve.click()
    saved(page, 2)
    call = orc.calls[-1][2]
    assert call['plan_reply']['action'] == 'APPROVE' and call['message'] == 'Setujui rencana riset'
    chosen = article(page, 0).locator('.edge-choice.sent')
    assert chosen.count() == 1 and 'Chosen · reply sent' in chosen.inner_text() and chosen.is_disabled()


def test_values_to_confirm_and_thresholds_are_readable(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:plan_confirm')
    saved(page)
    text = article(page).inner_text()
    assert 'Nilai yang perlu Anda konfirmasi' in text and '**' not in text
    rule = FIXTURES['plan_confirm']['response']['research_plan']['experiments'][0]['success_rule']
    shown = {'>=': '≥', '<=': '≤'}.get(rule['operator'], rule['operator'])
    assert f"{shown} 1%" in article(page).locator('.edge-plan').inner_text()
    capture(page, 'x-plan-confirm-dark')
    capture_answer(page, 'full-plan-confirm-dark')


def test_multi_angle_plan_and_its_findings_with_backend_numbers(fixture_server, browser_page):
    """A case the UI GT did not show: research_plan/v2 angles, then angle findings titled from the plan."""
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:plan_v2')
    saved(page)
    angles = FIXTURES['plan_v2']['response']['research_plan']['angles']
    assert article(page).locator('.edge-plan-item').count() == len(angles)
    assert 'Angle 1' in article(page).locator('.edge-plan').text_content()
    submit(page, 'fx:findings_v2')
    saved(page, 2)
    findings = article(page).locator('.edge-finding')
    reported = FIXTURES['findings_v2']['response']['research_findings']
    assert findings.count() == len(reported)
    titles = {a['angle_id']: a['title'] for a in angles}
    first = reported[0]
    if first['angle_id'] in titles:
        assert titles[first['angle_id']] in findings.first.inner_text()
    assert findings.first.locator('.edge-badge').count() == 1
    assert findings.locator('.edge-metrics').count() >= 1
    assert 'Answer' in findings.first.text_content()
    article(page).locator('.edge-finding').first.scroll_into_view_if_needed()
    capture(page, 'x-findings-v2-dark')
    capture_answer(page, 'full-findings-v2-dark')


def test_single_experiment_finding_shows_the_backend_verdict(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:findings_v1')
    saved(page)
    finding = article(page).locator('.edge-finding')
    assert finding.count() == len(FIXTURES['findings_v1']['response']['research_findings'])
    assert finding.first.locator('.edge-badge').inner_text().strip() in {
        'Supported', 'Partly supported', 'Not supported', 'Inconclusive', 'Not evaluated'}


def test_marked_claims_carry_their_note(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:annotated')
    saved(page)
    notes = {a['note'] for a in FIXTURES['annotated']['annotations']}
    claims = article(page).locator('em.edge-claim')
    assert claims.count() >= 1 and claims.first.get_attribute('title') in notes


def test_a_pause_shows_its_choices_as_buttons_once(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:paused')
    saved(page)
    pause = FIXTURES['paused']['execution']['pause']
    card = article(page).locator('.edge-response-choices.pause')
    assert 'This answer is paused' in card.inner_text() and pause['reason'] in card.inner_text()
    assert pause['question'] not in article(page).locator('.edge-answer').inner_text()  # not shown twice
    assert article(page).locator('.result-kicker').text_content() == 'EDGE · Paused'
    assert page.locator('.workspace-tools .pill').inner_text().endswith('Paused')
    capture(page, 'x-paused-dark')
    capture_answer(page, 'full-paused-dark')
    needs, plain = [o for o in pause['options'] if o['needs_input']], [o for o in pause['options'] if not o['needs_input']]
    calls = len(orc.calls)
    card.get_by_role('button', name=needs[0]['label'], exact=True).click()
    page.locator('.composer-status').filter(has_text=needs[0]['label']).wait_for()
    assert len(orc.calls) == calls  # the user writes the change first
    page.locator('.composer-status').get_by_role('button', name='Dismiss').click()
    card.get_by_role('button', name=plain[0]['label'], exact=True).click()
    saved(page, 2)
    call = orc.calls[-1][2]
    assert call['message'] == plain[0]['label'] and 'plan_reply' not in call and 'chosen_option' not in call
    # the answered pause is no longer the latest answer: its choices are disabled
    assert article(page, 0).locator('.edge-response-choices.pause button').first.is_disabled()


def test_markdown_never_turns_text_into_code_or_unsafe_links(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    original = orc.run
    def hostile(owner, id, payload):
        result = original(owner, id, payload)
        result['response']['answer'] = ('## Judul <img src=x onerror="window.pwned=1">\n\n'
                                        '[klik](javascript:window.pwned=2) dan [IDX](https://www.idx.co.id/)\n\n'
                                        '| a | b |\n|---|---|\n| <script>window.pwned=3</script> | **x** |\n\n'
                                        'nama_kolom_snake_case tetap utuh')
        result['response']['research_plan'] = None
        return result
    orc.run = hostile
    sign_in(page, origin)
    submit(page, 'Hostile')
    saved(page)
    answer = article(page).locator('.edge-answer')
    assert page.evaluate('window.pwned') is None
    assert answer.locator('img, script').count() == 0
    links = answer.locator('a')
    assert links.count() == 1 and links.first.get_attribute('href') == 'https://www.idx.co.id/'
    assert 'javascript:' in answer.inner_text()  # shown as text, not a link
    assert 'nama_kolom_snake_case' in answer.inner_text() and not answer.locator('em').count()


def test_unknown_fields_and_values_still_show_readably(fixture_server, browser_page):
    """Derive, do not enumerate: a field or verdict the view does not know yet shows with a readable label."""
    origin, orc = fixture_server
    page = browser_page
    original = orc.run
    def novel(owner, id, payload):
        result = original(owner, id, {**payload, 'message': 'fx:findings_v1'})
        result['response']['research_findings'][0]['verdict'] = 'SOMETHING_NEW'
        result['response']['research_findings'][0]['interpretation']['macro_context'] = 'Konteks makro baru.'
        return result
    orc.run = novel
    sign_in(page, origin)
    submit(page, 'Novel')
    saved(page)
    finding = article(page).locator('.edge-finding').first
    assert finding.locator('.edge-badge.neutral').inner_text().strip() == 'SOMETHING_NEW'
    assert 'Macro context' in finding.inner_text() and 'Konteks makro baru.' in finding.inner_text()


def test_numbered_choices_are_buttons_that_send_their_words_and_the_question_shows_once(fixture_server, browser_page):
    """EXEC-UI-1013B (gambar 1, run edge_a912d6a1): a router question whose choices share a route came as numbered
    lines, shown twice and not clickable. Each choice is a button that sends its words; the question is shown once,
    without the numbered lines; "Tulis jawaban lain" stays."""
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original = orc.run
    question = 'Berapa ambang akumulasi (X), lama akumulasi (Y), dan horizon return 10%?'
    labels = ['X = Rp10 miliar, Y = 5 hari, return 10% dalam 10 hari', 'X = Rp25 miliar, Y = 3 hari, return 10% dalam 20 hari',
              'X dan Y dari sebaran data', 'Jelaskan dulu cara akumulasi broker diukur']
    text = '\n'.join([question] + [f'{m} {l}' for m, l in zip('①②③④', labels)]
                     + ['Balas dengan nomor pilihan, atau tulis maksud Anda.'])

    def asked(owner, id, payload):
        result = original(owner, id, {**payload, 'message': 'fx:answer_table'})
        result.update(status='NEEDS_CLARIFICATION', options=[],
                      mode4={'round': 'ASK_BACK', 'turn_kind': 'ASK_BACK', 'question': question, 'choices': labels})
        result['response'] = {**result['response'], 'response_type': 'CLARIFICATION', 'answer': text,
                              'clarification_question': text, 'methodology': None}
        orc.saved[id]['response'] = result
        return result
    orc.run = asked
    submit(page, 'cari saham akumulasi broker')
    saved(page)
    body = article(page).inner_text()
    assert body.count(question) == 1 and '①' not in body and 'Balas dengan nomor' not in body
    panel = article(page).locator('.edge-response-choices')
    assert [panel.get_by_role('button', name=l, exact=True).count() for l in labels] == [1, 1, 1, 1]
    assert panel.get_by_role('button', name='Write another answer', exact=True).count() == 1
    orc.run = original
    panel.get_by_role('button', name=labels[2], exact=True).click()
    saved(page, 2)
    assert orc.calls[-1][2]['message'] == labels[2] and not orc.calls[-1][2].get('chosen_option')


def test_an_ask_back_offers_its_routes_and_writing_another_answer(fixture_server, browser_page):
    """EXEC-CHOICES: an ask-back question's routes are sent at once (Eksplorasi says it includes the news research);
    "Tulis jawaban lain" only opens the message box."""
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original = orc.run

    def asked(owner, id, payload):
        result = original(owner, id, {**payload, 'message': 'fx:answer_table'})
        result.update(status='NEEDS_CLARIFICATION', options=[{'label': 'Ringkasan cepat', 'route': 'QUICK_SUMMARY'},
                                                             {'label': 'Eksplorasi', 'route': 'EXPLORE'}])
        result['response'] = {**result['response'], 'response_type': 'CLARIFICATION', 'answer': 'TLKM yang mana?',
                              'clarification_question': 'TLKM yang mana?'}
        orc.saved[id]['response'] = result
        return result
    orc.run = asked
    submit(page, 'TLKM gimana?')
    saved(page)
    panel = article(page).locator('.edge-response-choices')
    explore = panel.get_by_role('button', name='Eksplorasi', exact=True)
    assert 'Includes news research' in explore.inner_text()
    other = panel.get_by_role('button', name='Write another answer', exact=True)
    calls = len(orc.calls)
    other.click()
    page.locator('.composer-status').filter(has_text='Write your answer in the message box').wait_for()
    assert len(orc.calls) == calls
    orc.run = original
    explore.click()
    saved(page, 2)
    assert orc.calls[-1][2]['chosen_option'] == 'EXPLORE'


def test_sources_list_the_answers_tables_with_an_export_request(fixture_server, browser_page):
    """EXEC-IMPL-1016 Fase 4.1 (EDGE-CTX B, user 2026-10-15): Sources shows the tables this answer released (name,
    address, rows, columns, data date), each with "Ask AI to export data", which sends the export request as the
    user's message; the evidence list stays, folded, as the references of the figures; an earlier answer's table is
    not listed."""
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original = orc.run

    def released(owner, id, payload):
        result = original(owner, id, {**payload, 'message': 'fx:answer_table'})
        record = dict(result.get('data_record') or {})
        record['outputs'] = [
            {'ref': 'out.1', 'output_id': 'o1', 'name': 'Net_beli_broker_asing', 'label': 'DATA_COVERAGE_VERIFIED',
             'type': 'TABLE', 'columns': ['broker', 'net_value', 'date'], 'row_count': 12, 'request_id': id,
             'data_as_of': '2026-10-15', 'definition': {'notes': 'Net beli harian per broker asing.'}},
            {'ref': 'out.2', 'output_id': 'o2', 'name': 'ringkasan', 'type': 'JSON', 'columns': [], 'row_count': None,
             'request_id': id},
            {'ref': 'out.0', 'output_id': 'o0', 'name': 'older', 'columns': ['x'], 'row_count': 3,
             'request_id': 'edge_earlier'}]
        result['data_record'] = record
        result['evidence'] = (result.get('evidence') or []) + [{'kind': 'REFERENCED', 'claim': 'out.1.rows[0].net_value',
                                                               'label': 'Dari data pasar: net value'}]
        orc.saved[id]['response'] = result
        return result
    orc.run = released
    submit(page, 'broker asing pembeli terbesar')
    saved(page)
    orc.run = original
    page.get_by_role('tab', name='Sources', exact=True).click()
    sources = page.locator('.sources')
    assert sources.get_by_text('Result tables (1)').is_visible()
    assert sources.get_by_text('Net beli broker asing', exact=True).is_visible()
    assert sources.locator('.edge-source-ref').first.inner_text() == 'out.1'
    table = sources.locator('.edge-source').first.inner_text()
    assert 'Rows\n12' in table and 'Columns\n3' in table and 'Data as of\n2026-10-15' in table and '{n}' not in table
    assert 'older' not in sources.inner_text() and 'ringkasan' not in sources.inner_text()
    assert 'DATA_COVERAGE_VERIFIED' not in sources.inner_text() and 'Net beli harian per broker asing.' in table
    folded = sources.locator('details.edge-source-folded')
    assert folded.count() == 1 and folded.locator('summary').inner_text().startswith('Figure references')
    assert not folded.evaluate('node => node.open')
    capture(page, 'x-sources-tables-dark')
    sources.get_by_role('button', name='Ask AI to export data', exact=True).click()
    saved(page, 2)
    assert orc.calls[-1][2]['message'] == 'Ekspor data tabel out.1 (Net beli broker asing) ke Excel'


def test_a_running_answer_shows_its_steps_from_orc(fixture_server, browser_page):
    """EXEC-IMPL-1016 Fase 4.3 (UI-1015B, user 2026-10-15): while Orc runs the answer, EDGE shows the time so far,
    the step running now and the finished steps (folded), read through the BFF; the steps go when the answer lands."""
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original = orc.run
    release = threading.Event()

    def slow(owner, id, payload):
        orc.PROGRESS = {id: {'status': 'RUNNING', 'elapsed_ms': 42000, 'earlier_steps': 0, 'steps': [
            {'label': 'Memahami pertanyaan', 'state': 'done', 'started_ms': 0, 'duration_ms': 3000},
            {'label': 'Permintaan data', 'state': 'refused', 'started_ms': 3000, 'duration_ms': 2000},
            {'label': 'Kode analisis', 'state': 'running', 'started_ms': 5000, 'duration_ms': 37000}]}}
        release.wait(timeout=20)
        return original(owner, id, {**payload, 'message': 'fx:answer_table'})
    orc.run = slow
    try:
        submit(page, 'net beli asing BBRI')
        progress = page.locator('.edge-run-progress')
        progress.wait_for(timeout=10000)
        assert progress.locator('.edge-run-progress-time').inner_text() == '42s'
        assert 'Kode analisis' in progress.locator('.edge-run-progress-now').inner_text()
        done = progress.locator('details.edge-run-progress-done')
        assert done.locator('summary').inner_text() == 'Steps done (2)' and not done.evaluate('n => n.open')
        done.locator('summary').click()
        assert 'refused, trying again' in done.inner_text() and 'Memahami pertanyaan' in done.inner_text()
        capture(page, 'x-run-progress-dark')
    finally:
        release.set()
        orc.run = original
    saved(page)
    assert page.locator('.edge-run-progress').count() == 0


SELECT_JS = """(selector) => { const answers = document.querySelectorAll('article.result'), last = answers[answers.length - 1];
    const [css, text] = selector.split('|'); const node = [...last.querySelectorAll(css)].find(n => !text || n.textContent.includes(text));
    node.scrollIntoView({block: 'center'});
    const range = document.createRange(); range.selectNodeContents(node); const s = window.getSelection(); s.removeAllRanges(); s.addRange(range);
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, {acceptNode: t => t.textContent.trim() ? 1 : 3});
    const first = walker.nextNode(), word = document.createRange(); word.setStart(first, 0); word.setEnd(first, Math.min(3, first.length));
    const box = word.getBoundingClientRect(); return {x: box.left + box.width / 2, y: box.top + box.height / 2}; }"""


def attach_by_right_click(page, selector):
    menu = page.locator('.edge-selection-menu')
    for _ in range(3):  # a refresh of the answer while selecting drops the selection, as it would for a user
        page.evaluate(SELECT_JS, selector)
        page.wait_for_timeout(250)  # the layout settles (the composer grows with a chip) before the click
        point = page.evaluate(SELECT_JS, selector)
        page.mouse.click(point['x'], point['y'], button='right')
        if menu.count():
            break
        page.wait_for_timeout(300)
    assert menu.is_visible() and menu.get_by_role('menuitem', name='Copy', exact=True).is_visible()
    if os.environ.get('EDGE_UI_ARTIFACT_DIR'):
        page.screenshot(path=os.path.join(os.environ['EDGE_UI_ARTIFACT_DIR'], 'x-selection-menu.png'))
    menu.get_by_role('menuitem', name='Attach selection as context', exact=True).click()
    assert menu.count() == 0


def built_answer(orc):
    original = orc.run

    def built(owner, id, payload):
        result = original(owner, id, {**payload, 'message': 'fx:answer_table'})
        result['answer_tables'] = [{'ref': 'out.o2', 'output_id': 'out_abc', 'rows': [4, 9],
                                    'titles': ['Ukuran', 'Setelah sinyal', 'Baseline', 'Selisih (95% CI)', 'p'],
                                    'columns': ['measure', 'signal', 'base', 'diff', 'p']}]
        result['answer_figures'] = [{'ref': 'out.o1.rows[_row=0].events', 'shown': '19'},
                                    {'ref': 'out.o1.rows[_row=0].baseline_days', 'shown': '449'}]
        orc.saved[id]['response'] = result
        return result
    return original, built


def test_a_selection_anywhere_in_an_answer_attaches_with_its_figures_by_right_click(fixture_server, browser_page):
    """EXEC-IMPL-1017 Fase 3 (user 2026-10-16: "sama seperti select as context tanpa ada menu tambahan ... klik kanan
    kayak claude"): a table has no attach controls; text selected in the answer (a sentence or table cells) opens
    EDGE's menu (Copy, Attach selection as context) on a right click; the passage travels with the next question with
    the value reference of every figure and cell inside it."""
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original, built = built_answer(orc)
    orc.run = built
    submit(page, 'uji sinyal volume')
    saved(page)
    orc.run = original
    answer = article(page)
    assert answer.locator('.edge-table-attach').count() == 0 and answer.locator('tr.edge-row-pickable').count() == 0
    figures = answer.locator('span.edge-fig')
    assert figures.count() == 2 and figures.nth(1).get_attribute('data-fig-ref') == 'out.o1.rows[_row=0].baseline_days'
    attach_by_right_click(page, '.edge-answer p|Periode studi')  # "Periode studi ... 19 hari ... 449 hari ..."
    attach_by_right_click(page, '.edge-md-table tbody tr:nth-child(2)')  # the second row of the built table
    chips = page.locator('.edge-attached-chip')
    assert chips.count() == 2 and '2 figures' in chips.nth(0).inner_text()
    capture(page, 'x-attach-selection')
    def reproduced(owner, id, payload):
        result = original(owner, id, payload)
        result.update(attached=[{'kind': 'TEXT', 'quote': 'Periode studi 2 Jan 2023', 'figures': ['19', '449']}],
                      reproductions=[{'figure': '449', 'original': 'out.o1.rows[_row=0].baseline_days',
                                      'result': 'out.o9.rows[_row=0].days', 'status': 'MATCH'}])
        orc.saved[id]['response'] = result
        return result
    orc.run = reproduced
    submit(page, 'ini dari mana?')
    saved(page, 2)
    orc.run = original
    answer = article(page)
    assert 'Attachment: “Periode studi 2 Jan 2023” · 2 figures' in answer.locator('.edge-attached-line').inner_text()
    assert 'exactly equal to 449' in answer.locator('.edge-reproduced').inner_text()
    sent = orc.calls[-1][2]['attachments']
    assert [a['kind'] for a in sent] == ['TEXT', 'TEXT'] and sent[0]['section'] == 'ANSWER'
    assert [f['ref'] for f in sent[0]['figures']] == ['out.o1.rows[_row=0].events', 'out.o1.rows[_row=0].baseline_days']
    assert 'Periode studi' in sent[0]['quote'] and sent[0]['request_id']
    assert {f['ref'] for f in sent[1]['figures']} >= {'out.o2.rows[_row=9].measure', 'out.o2.rows[_row=9].signal'}
    assert page.locator('.edge-attached-chip').count() == 0  # sent with the question


def test_on_a_phone_a_selection_shows_the_floating_bar(fixture_server, browser_page):
    """EXEC-IMPL-1017 Fase 3 (user 2026-10-16: "di ponsel memakai tombol mengambang"): a touch screen has no right
    click; selecting text in an answer shows a small bar under it with the same two actions."""
    origin, orc = fixture_server
    ctx = browser_page.context.browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True)
    page = ctx.new_page()
    try:
        sign_in(page, origin)
        original, built = built_answer(orc)
        orc.run = built
        submit(page, 'uji sinyal volume')
        saved(page)
        orc.run = original
        page.evaluate(SELECT_JS, '.edge-answer p|Periode studi')
        bar = page.locator('.edge-selection-menu.floating')
        bar.wait_for(state='visible', timeout=3000)
        capture(page, 'x-attach-floating-phone')
        bar.get_by_role('menuitem', name='Attach selection as context', exact=True).click()
        assert page.locator('.edge-attached-chip').count() == 1
    finally:
        ctx.close()


def test_a_failed_answer_gives_its_question_and_attachments_back(fixture_server, browser_page):
    """E11 (EXEC-1018B, M178): a run that ends without an answer (failed or stopped) gives its question and its
    attachments back to the composer, so nothing the user wrote or picked is lost; a completed run clears them."""
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original, built = built_answer(orc)
    orc.run = built
    submit(page, 'uji sinyal volume')
    saved(page)
    attach_by_right_click(page, '.edge-md-table tbody tr:nth-child(2)')
    assert page.locator('.edge-attached-chip').count() == 1

    def failing(owner, id, payload):
        result = original(owner, id, payload)
        result.update(status='FAILED', error={'code': 'DUMMY_FAILURE'})
        return result
    orc.run = failing
    try:
        submit(page, 'baris ini dari mana?')
        composer = page.get_by_placeholder('Ask a research question…')
        for _ in range(200):  # Orc received the question (the composer was cleared when it was accepted)
            if len(orc.calls) == 2:
                break
            page.wait_for_timeout(50)
        assert len(orc.calls) == 2
        # the message box by its placeholder: an attachment's note is a textarea too (EXEC-UI-1025)
        page.wait_for_function("() => document.querySelector('textarea[placeholder^=\"Ask a research\"]').value === 'baris ini dari mana?'", timeout=15000)
        assert page.locator('.edge-attached-chip').count() == 1
        assert len(orc.calls[-1][2]['attachments']) == 1  # the same chip was sent, and came back
    finally:
        orc.run = original


def test_the_run_clock_counts_each_second_and_never_goes_back(fixture_server, browser_page):
    """E12 (EXEC-1018B, user 2026-10-16 "as smooth as 1 detik"): the running time moves by one second each second
    between Orc's readings; a reading that is behind the shown time never moves it back."""
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original = orc.run
    release = threading.Event()

    def slow(owner, id, payload):
        orc.PROGRESS = {id: {'status': 'RUNNING', 'elapsed_ms': 42000, 'earlier_steps': 0, 'steps': [
            {'label': 'Kode analisis', 'state': 'running', 'started_ms': 0, 'duration_ms': 42000}]}}
        release.wait(timeout=30)
        return original(owner, id, {**payload, 'message': 'fx:answer_table'})
    orc.run = slow
    try:
        submit(page, 'net beli asing BBRI')
        clock = page.locator('.edge-run-clock')
        clock.wait_for(timeout=10000)
        seen = []
        for _ in range(9):  # 4.5 s: across at least one more reading (every 2.5 s) of the same, older elapsed time
            seen.append(int(clock.get_attribute('data-seconds')))
            page.wait_for_timeout(500)
        assert seen == sorted(seen), seen  # never back
        assert 3 <= seen[-1] - seen[0] <= 5, seen  # about one per second
        assert page.evaluate("() => matchMedia('(prefers-reduced-motion: reduce)').matches") or \
            clock.evaluate("c => getComputedStyle(c).animationName") in ('edge-tick-odd', 'edge-tick-even')
        page.emulate_media(reduced_motion='reduce')
        assert clock.evaluate("c => getComputedStyle(c).animationName") == 'none'
    finally:
        page.emulate_media(reduced_motion='no-preference')
        release.set()
        orc.run = original
    saved(page)
