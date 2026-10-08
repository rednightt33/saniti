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
    assert article(page).locator('.result-kicker').text_content() == 'EDGE AI · Selesai'
    assert page.locator('.workspace-tools .pill').inner_text().endswith('Completed')  # the frame stays English
    page.get_by_role('tab', name='Sources', exact=True).click()
    assert page.locator('.sources').get_by_text('Catatan data percakapan').is_visible()
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
    assert 'Eksperimen 1' in plan.text_content() and 'Horizon' in plan.text_content()
    assert 'Menunggu persetujuan' in plan.inner_text()
    assert page.locator('.workspace-tools .pill').inner_text().endswith('Awaiting approval')
    capture(page, 'x-plan-v1-dark')
    capture_answer(page, 'full-plan-v1-dark')
    capture_answer(page, 'full-plan-v1-mobile', 390)
    page.set_viewport_size({'width': 390, 'height': 844})
    article(page).locator('.edge-plan').scroll_into_view_if_needed()
    capture(page, 'x-plan-v1-mobile')
    page.set_viewport_size({'width': 1600, 'height': 1000})
    page.get_by_role('button', name='Setujui & jalankan', exact=True).click()
    saved(page, 2)
    call = orc.calls[-1][2]
    assert call['plan_reply']['action'] == 'APPROVE' and call['message'] == 'Setujui rencana riset'


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
    assert 'Sudut 1' in article(page).locator('.edge-plan').text_content()
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
    assert 'Jawaban' in findings.first.text_content()
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
        'Didukung', 'Didukung sebagian', 'Tidak didukung', 'Belum konklusif', 'Tidak dievaluasi'}


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
    card = article(page).locator('.edge-callout.pause')
    assert 'Jawaban ini dijeda' in card.inner_text() and pause['reason'] in card.inner_text()
    assert pause['question'] not in article(page).locator('.edge-answer').inner_text()  # not shown twice
    assert article(page).locator('.result-kicker').text_content() == 'EDGE AI · Dijeda'
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
    assert article(page, 0).locator('.edge-callout.pause button').first.is_disabled()


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
