"""Interaction/layout regressions through real BFF, queue, SSE and disposable DB; dummy AI only."""
import os
import json
from urllib.parse import urlsplit
import threading
from pathlib import Path

import pytest
from test_browser import server  # shared real-HTTP fixture


@pytest.fixture
def browser_page(request):
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium'),
                                     headless=True, args=['--no-sandbox'])
        artifacts = os.environ.get('EDGE_UI_ARTIFACT_DIR')
        if artifacts:
            Path(artifacts).mkdir(parents=True, exist_ok=True)
        context = browser.new_context(viewport={'width': 1600, 'height': 1000},
                                      **({'record_video_dir': artifacts, 'record_video_size': {'width': 960, 'height': 600}} if artifacts and os.environ.get('EDGE_UI_RECORD_VIDEO') == '1' else {}))
        page = context.new_page()
        page.set_default_timeout(5000)
        # External fonts are optional. Avoid flaky third-party networking in local regressions.
        page.route('https://fonts.*/*', lambda route: route.abort())
        errors, console_errors, http_errors = [], [], []
        page.on("console", lambda message: console_errors.append({"text": message.text, "url": message.location.get("url", "")}) if message.type == "error" else None)
        page.on("response", lambda response: http_errors.append({"path": urlsplit(response.url).path, "status": response.status}) if response.status >= 400 else None)
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            yield page
            assert not errors, errors
            allowed = lambda item: (item['status'] == 401 and item['path'] == '/api/v1/auth/session') or (item['status'] == 503 and item['path'] == '/api/v1/runs' and request.node.name == 'test_submit_error_keyboard_disabled_controls_and_resizing')
            assert not [item for item in http_errors if not allowed(item)], http_errors
            unexpected_console = [item for item in console_errors if not (
                'fonts.' in item['url'] or (item['url'].endswith('/api/v1/auth/session') and '401' in item['text'])
                or (item['url'].endswith('/api/v1/runs') and '503' in item['text'] and request.node.name == 'test_submit_error_keyboard_disabled_controls_and_resizing'))]
            assert not unexpected_console, unexpected_console
            if artifacts:
                (Path(artifacts) / (request.node.name + '.json')).write_text(json.dumps({'page_errors': errors, 'console_errors': console_errors, 'http_errors': http_errors, 'unexpected_console_errors': unexpected_console}, indent=2))
        finally:
            video=page.video
            context.close()
            if video:
                video.save_as(str(Path(artifacts) / (request.node.name + '.webm')))
                video.delete()
            browser.close()


def capture(page, name):
    if directory := os.environ.get('EDGE_UI_ARTIFACT_DIR'):
        page.locator('article.result').evaluate_all('(nodes) => Promise.all(nodes.flatMap(n => n.getAnimations().map(a => a.finished.catch(() => {}))))')
        page.screenshot(path=str(Path(directory) / (name + '.png')))


def wait_until(check, seconds=5):
    import time
    end = time.monotonic() + seconds
    while not check():
        assert time.monotonic() < end, 'condition not met in time'
        time.sleep(0.05)


def sign_in(page, origin):
    page.goto(origin + '/monitor')
    page.get_by_label('Login', exact=True).fill('owner')
    page.get_by_label('Password', exact=True).fill('local-test-password')
    page.get_by_role('button', name='Sign In', exact=True).click()
    page.get_by_placeholder('Ask a research question…').wait_for()


def submit(page, question):
    page.get_by_placeholder('Ask a research question…').fill(question)
    page.get_by_role('button', name='Submit', exact=True).click()


def saved(page, count=1):
    page.wait_for_function('(count) => document.querySelectorAll("article.result").length === count && !document.querySelector(".composer-status")', arg=count)


def no_clipping(page):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Page overflows horizontally'
    for selector in ('.topbar', '.research-workspace', '.workspace-tools', '.composer'):
        box = page.locator(selector).bounding_box()
        assert box and box['x'] >= -1 and box['x'] + box['width'] <= page.viewport_size['width'] + 1, selector
    for label in ('Account menu', 'Show Details', 'Submit'):
        button = page.get_by_role('button', name=label, exact=True)
        if button.is_visible():
            box = button.bounding_box()
            assert box['x'] >= 0 and box['x'] + box['width'] <= page.viewport_size['width'] + 1, label


@pytest.fixture
def dummy_orc(server):
    origin, orc = server
    original = orc.run
    failures = set()
    def run(owner, request_id, payload):
        result = original(owner, request_id, payload)
        question = payload['message']
        if question == 'Dummy failure' and question not in failures:
            failures.add(question)
            result.update(status='FAILED', error={'code': 'DUMMY_FAILURE'})
        elif question == 'Dummy limited':
            result['status'] = 'LIMITED'
        elif question == 'Dummy follow ups':
            result['follow_ups'] = [{'kind': 'FOLLOW_UP', 'label': 'Kapan rapat BI berikutnya?'},
                                    {'kind': 'INSIGHT_IDEA', 'label': 'Bulan apa jual asing BBRI paling besar?'}]
        elif question == 'Dummy stopped':
            result['execution']['stopped'] = True  # EXEC-Y Fase 1: Orc says the user stopped this answer
        if question.startswith('Dummy'):
            result['response'].update(
                answer='GOTO — jawaban dummy untuk pengujian UI.\n\nIni simulasi, bukan analisis investasi.\n\n'
                       + ('Dokumen dapat dikumpulkan per ticker dan dianalisis bersama sumber serta batasan. ' * 8 + '\n\n') * 5,
                assumptions=['Data hanya dummy untuk QA.'], limitations=['Tidak ada panggilan OpenRouter.'],
                methodology='Stub Orc lokal melalui BFF dan SSE asli.')
            result['evidence'] = [{'name': 'IDX — dummy metadata', 'ticker': 'GOTO',
                                   'url': 'https://www.idx.co.id/id/perusahaan-tercatat/keterbukaan-informasi/'}]
            orc.saved[request_id]['run_status'] = result['status']
        return result
    orc.run = run
    return origin, orc


def test_loading_animation_refresh_and_completed_answer(dummy_orc, browser_page):
    origin, orc = dummy_orc
    page = browser_page
    entered, release = threading.Event(), threading.Event()
    original = orc.run
    def blocked(*args):
        entered.set()
        assert release.wait(15)
        return original(*args)
    orc.run = blocked
    sign_in(page, origin)
    try:
        submit(page, 'Dummy GOTO response')
        assert entered.wait(3)
        stop = page.get_by_role('button', name='Stop', exact=True)  # EXEC-X 2026-10-09: the stop button
        stop.wait_for()
        assert stop.is_enabled() and not page.get_by_role('button', name='Submit', exact=True).count()
        assert page.locator('.edge-response-dots i').count() == 3
        assert page.locator('.edge-response-dots i').first.evaluate('(node) => getComputedStyle(node).animationName') == 'edge-response-pulse'
        animation = page.locator('.edge-response-dots i').first
        first_time = animation.evaluate('(node) => node.getAnimations()[0].currentTime')
        page.wait_for_timeout(150)
        assert animation.evaluate('(node) => node.getAnimations()[0].currentTime') > first_time
        capture(page, 'desktop-loading')
        stop.click()
        page.get_by_role('button', name='Stopping…', exact=True).wait_for()
        assert page.get_by_role('button', name='Stopping…', exact=True).is_disabled()
        wait_until(lambda: getattr(orc, 'stopped', []))  # the button turns first; the request follows
        assert orc.stopped[-1].startswith('edge_')
        page.reload()
        page.locator('.edge-inline-progress').wait_for()
        assert 'Dummy GOTO response' in page.locator('.user-message').inner_text()
        page.get_by_placeholder('Ask a research question…').fill('Keep this draft while the answer arrives')
        release.set()
        saved(page)
        assert page.get_by_placeholder('Ask a research question…').input_value() == 'Keep this draft while the answer arrives'
        assert len(orc.calls) == 1  # refreshing the browser never re-executes AI
        assert not page.locator('.edge-response-dots').count()
        assert page.locator('article.result').evaluate('(node) => getComputedStyle(node).animationName') == 'edge-ai-arrival'
        page.locator('.research-scroll').evaluate('(node) => node.scrollTop = 0')
        capture(page, 'desktop-answer-dark')
        page.get_by_role('button', name='Switch to light theme', exact=True).click()
        capture(page, 'desktop-answer-light')
        page.emulate_media(reduced_motion='reduce')
        assert page.locator('article.result').evaluate('(node) => getComputedStyle(node).animationName') == 'none'
        page.get_by_role('tab', name='Sources', exact=True).click()
        assert page.get_by_text('IDX — dummy metadata', exact=True).is_visible()
        capture(page, 'desktop-sources')
    finally:
        release.set()


def test_follow_up_questions_and_insight_ideas_are_clicked_as_the_next_message(dummy_orc, browser_page):
    """EXEC-Y Fase 2: the answer lists what to ask next under two titles; a click sends those words as the next
    message in the same conversation."""
    origin, orc = dummy_orc
    page = browser_page
    sign_in(page, origin)
    submit(page, 'Dummy follow ups')
    saved(page)
    assert page.get_by_text('Pertanyaan lanjutan', exact=True).is_visible()
    assert page.get_by_text('Ide insight', exact=True).is_visible()
    capture(page, 'follow-ups')
    page.get_by_role('button', name='Bulan apa jual asing BBRI paling besar?', exact=True).click()
    saved(page, 2)
    assert orc.calls[-1][2]['message'] == 'Bulan apa jual asing BBRI paling besar?'
    assert orc.calls[-1][2]['conversation_id'] == orc.saved[orc.calls[0][1]]['conversation_id']


def test_stop_and_send_then_edit_and_resend(dummy_orc, browser_page):
    """EXEC-Y Fase 1: typing while a run is active offers Stop & send (the run stops, the message runs next in the
    same conversation); a stopped answer offers its question back (Edit & resend). Enter alone never stops a run."""
    origin, orc = dummy_orc
    page = browser_page
    entered, release = threading.Event(), threading.Event()
    original = orc.run
    def blocked(owner, request_id, payload):
        if payload['message'] == 'Dummy first':
            entered.set()
            assert release.wait(15)
        return original(owner, request_id, payload)
    orc.run = blocked
    sign_in(page, origin)
    try:
        submit(page, 'Dummy first')
        assert entered.wait(3)
        page.get_by_role('button', name='Stop', exact=True).wait_for()
        composer = page.get_by_placeholder('Ask a research question…')
        composer.fill('Dummy stopped')
        composer.press('Enter')
        assert composer.input_value() == 'Dummy stopped' and len(orc.calls) == 0  # Enter does not stop or send
        page.get_by_role('button', name='Stop & send', exact=True).click()
        page.get_by_text('Stopping — waiting for the current step to finish', exact=True).wait_for()
        wait_until(lambda: getattr(orc, 'stopped', []))
        release.set()
        saved(page, 2)
        assert [call[2]['message'] for call in orc.calls] == ['Dummy first', 'Dummy stopped']
        assert orc.calls[1][2]['conversation_id'] == orc.saved[orc.calls[0][1]]['conversation_id']
        page.get_by_role('button', name='Edit & resend', exact=True).click()
        assert composer.input_value() == 'Dummy stopped'
        capture(page, 'stopped-edit-resend')
    finally:
        release.set()


@pytest.mark.parametrize('width,height', [(1280, 800), (1024, 768), (768, 1024), (390, 844), (360, 800)])
def test_responsive_history_details_preferences_and_keyboard(dummy_orc, browser_page, width, height):
    origin, orc = dummy_orc
    page = browser_page
    page.set_viewport_size({'width': width, 'height': height})
    sign_in(page, origin)
    submit(page, 'Dummy first answer')
    saved(page)
    page.locator('.research-scroll').evaluate('(node) => node.scrollTop = 0')
    no_clipping(page)
    if width <= 720:  # user 2026-10-09: the message box uses the page's text size on mobile
        sizes = page.evaluate("() => [getComputedStyle(document.querySelector('.composer textarea')).fontSize, getComputedStyle(document.querySelector('.user-message')).fontSize]")
        assert sizes[0] == sizes[1] == '14px', sizes
    if width <= 720:  # user 2026-10-08: "jump to latest pada mobile view hilangkan saja"
        page.wait_for_function("() => !document.querySelector('.jump-latest') || getComputedStyle(document.querySelector('.jump-latest')).display === 'none'")
    else:
        page.get_by_role('button', name='Jump to latest', exact=True).wait_for()
        page.wait_for_function("() => document.querySelector('.jump-latest').getBoundingClientRect().bottom < document.querySelector('.composer').getBoundingClientRect().top")
    capture(page, f'answer-{width}')
    page.get_by_role('button', name='Pin', exact=True).click()
    page.get_by_role('button', name='Pinned', exact=True).wait_for()
    page.get_by_role('button', name='Bookmark', exact=True).click()
    page.wait_for_function("() => document.querySelector('[aria-label=Bookmark]').getAttribute('aria-pressed') === 'true'")
    if width <= 1050:
        page.get_by_role('button', name='Show Details', exact=True).click()
        details = page.get_by_role('dialog', name='Response details', exact=True)
        details.wait_for()
    else:
        details = page.locator('.details-panel')
    page.get_by_role('button', name='Expand pinned response', exact=True).click()
    assert details.locator('.edge-pin-body').is_visible()
    page.get_by_role('button', name='Expand pinned response', exact=True).click()
    page.get_by_role('tab', name='Sources', exact=True).click()
    assert page.get_by_text('IDX — dummy metadata', exact=True).is_visible()
    capture(page, f'details-{width}')
    if width <= 1050:
        # Drawer keyboard focus cycles within the panel; Escape restores the trigger.
        page.get_by_role('tab', name='Sources', exact=True).focus()
        page.keyboard.press('Tab')
        assert page.evaluate("document.activeElement.closest('#edge-details') !== null")
        page.keyboard.press('Escape')
        assert not page.get_by_role('dialog', name='Response details', exact=True).count()
        page.get_by_role('button', name='Open history', exact=True).click()
        page.get_by_role('dialog', name='Conversation history', exact=True).wait_for()
    page.get_by_role('button', name='Bookmarked 1', exact=True).click()
    assert page.locator('.conversation-list .conversation').count() == 1
    page.get_by_placeholder('Search conversation').fill('no matching title')
    page.get_by_text('No matching conversations', exact=True).wait_for()
    page.get_by_placeholder('Search conversation').fill('Dummy first')
    page.locator('.conversation-list .conversation').wait_for()
    capture(page, f'history-{width}')
    page.locator('.conversation-list .conversation').click()
    page.get_by_role('button', name='Pinned', exact=True).wait_for()
    page.reload()
    page.get_by_placeholder('Ask a research question…').wait_for()
    if width <= 1050:
        page.get_by_role('button', name='Open history', exact=True).click()
    page.locator('.conversation-list .conversation').first.click()
    page.get_by_role('button', name='Pinned', exact=True).wait_for()
    assert page.get_by_role('button', name='Bookmark', exact=True).get_attribute('aria-pressed') == 'true'
    page.get_by_role('button', name='New conversation', exact=True).click()
    submit(page, 'Dummy second answer')
    saved(page)
    if width <= 1050:
        page.get_by_role('button', name='Open history', exact=True).click()
    # Enter on the bookmark button must not activate the enclosing conversation.
    old = page.locator('.conversation-list .conversation').filter(has_text='Dummy first answer')
    old.get_by_role('button', name='Remove bookmark', exact=True).focus()
    page.keyboard.press('Enter')
    old.get_by_role('button', name='Add bookmark', exact=True).wait_for()
    assert page.locator('.conversation.active').inner_text().startswith('Dummy second answer')
    if width <= 1050:
        page.keyboard.press('Escape')
    page.get_by_role('button', name='Account menu', exact=True).click()
    page.get_by_role('menuitem', name='Sign out').wait_for()
    page.keyboard.press('Escape')
    assert not page.get_by_role('menu').count()
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_role('dialog', name='Appearance', exact=True).wait_for()
    page.get_by_role('button', name='Switch theme', exact=True).click()
    page.keyboard.press('Escape')
    assert not page.get_by_role('dialog').count()
    no_clipping(page)
    assert len(orc.calls) == 2


def test_failure_retry_limited_and_multi_turn_history(dummy_orc, browser_page):
    origin, orc = dummy_orc
    page = browser_page
    sign_in(page, origin)
    submit(page, 'Dummy failure')
    page.get_by_role('button', name='Retry', exact=True).wait_for()
    assert 'DUMMY_FAILURE' in page.locator('.run-inline-state').inner_text()
    capture(page, 'desktop-failure')
    first = orc.calls[0][1]
    page.get_by_role('button', name='Retry', exact=True).click()
    assert page.get_by_placeholder('Ask a research question…').input_value() == 'Dummy failure'
    assert len(orc.calls) == 1
    page.get_by_role('button', name='Submit', exact=True).click()
    saved(page, 2)
    assert len(orc.calls) == 2 and orc.calls[1][1] != first
    assert orc.calls[1][2]['conversation_id'] == orc.saved[first]['conversation_id']
    submit(page, 'Dummy limited')
    saved(page, 3)
    assert page.locator('article.result').last.locator('.result-kicker').text_content() == 'EDGE AI · Terbatas'
    page.locator('.research-scroll').evaluate('(node) => node.scrollTop = 0')
    capture(page, 'desktop-history-multiple')
    page.reload()
    page.get_by_placeholder('Ask a research question…').wait_for()
    page.locator('.conversation-list .conversation').first.click()
    saved(page, 3)
    assert page.get_by_role('button', name='Retry', exact=True).count() == 1
    assert page.locator('.edge-flow-accordion').count() == 3
    assert len(orc.calls) == 3


def test_submit_error_keyboard_disabled_controls_and_resizing(dummy_orc, browser_page):
    origin, orc = dummy_orc
    page = browser_page
    sign_in(page, origin)
    composer = page.get_by_placeholder('Ask a research question…')
    composer.fill('Dummy keyboard')
    composer.press('Shift+Enter')
    assert composer.input_value() == 'Dummy keyboard\n' and not orc.calls
    attempts = []
    def unavailable_once(route):
        if route.request.method == 'POST':
            attempts.append(route.request.post_data_json)
            route.fulfill(status=503, content_type='application/json', body='{"error":{"code":"SERVICE_UNAVAILABLE"}}')
        else:
            route.continue_()
    page.route('**/api/v1/runs', unavailable_once)
    composer.press('Enter')
    page.get_by_role('alert').filter(has_text='SERVICE_UNAVAILABLE').wait_for()
    assert composer.input_value() == 'Dummy keyboard\n'
    assert not page.locator('article.result').count() and not orc.calls
    capture(page, 'desktop-submit-error')
    page.unroute('**/api/v1/runs', unavailable_once)
    composer.press('Enter')
    saved(page)
    assert len(orc.calls) == 1
    assert attempts[0]['message'] == orc.calls[0][2]['message']
    page.get_by_role('button', name='Standard', exact=True).click()
    assert page.locator('.mode-menu button').filter(has_text='Deep Research').is_disabled()
    page.keyboard.press('Escape')
    assert not page.locator('.mode-menu').count()
    for label in ('Data Scope', 'Attachments are not available yet', 'Public sharing unavailable', 'Support unavailable', 'Notifications unavailable'):
        assert page.get_by_role('button', name=label, exact=True).is_disabled()
    page.get_by_role('button', name='Account menu', exact=True).click()
    composer.click()
    assert not page.get_by_role('menu').count()
    assert composer.evaluate('(node) => document.activeElement === node')
    resizer = page.get_by_role('separator', name='Resize Details panel', exact=True)
    resizer.focus()
    resizer.press('ArrowLeft')
    assert resizer.get_attribute('aria-valuenow') == '340'
    resizer.dblclick()
    assert resizer.get_attribute('aria-valuenow') == '320'
    page.get_by_role('button', name='Collapse sidebar', exact=True).click()
    assert page.get_by_role('button', name='New conversation', exact=True).is_visible()
    # A persisted collapsed desktop sidebar must still expose mobile history/search.
    page.set_viewport_size({'width': 390, 'height': 844})
    page.get_by_role('button', name='Open history', exact=True).click()
    page.get_by_placeholder('Search conversation').wait_for(state='visible')
    capture(page, 'mobile-history-from-collapsed-desktop')
    page.keyboard.press('Escape')
    page.get_by_role('button', name='Show Details', exact=True).click()
    page.get_by_role('button', name='Close details', exact=True).click()
    page.get_by_role('button', name='Show Details', exact=True).click()
    page.get_by_role('dialog', name='Response details', exact=True).wait_for()
    page.keyboard.press('Escape')
    no_clipping(page)


def test_mobile_research_plan_and_clarification(server, browser_page):
    origin, orc = server
    page = browser_page
    page.set_viewport_size({'width': 390, 'height': 844})
    original=orc.run
    def mobile_reply(*args):
        result=original(*args)
        if args[2]['message'].startswith('Plan'):
            result['response']['answer']='Berikut rencana riset dummy. Pilih setuju, revisi, atau batal.'
        return result
    orc.run=mobile_reply
    sign_in(page, origin)
    submit(page, 'Plan mobile')
    page.get_by_role('button', name='Revisi', exact=True).wait_for()
    saved(page)
    page.locator('.research-scroll').evaluate('(node) => node.scrollTop = 0')
    no_clipping(page)
    capture(page, 'mobile-research-plan')
    page.get_by_role('button', name='Revisi', exact=True).click()
    page.locator('.composer-status').filter(has_text='Describe the plan revision').wait_for()
    page.get_by_placeholder('Ask a research question…').fill('Use one year')
    page.get_by_role('button', name='Submit', exact=True).click()
    saved(page, 2)
    assert orc.calls[-1][2]['plan_reply']['revision_instruction'] == 'Use one year'
    page.get_by_role('button', name='New conversation', exact=True).click()
    submit(page, 'Clarify')
    page.get_by_role('button', name='Quick summary', exact=True).wait_for()
    capture(page, 'mobile-clarification')
    page.get_by_role('button', name='Quick summary', exact=True).click()
    saved(page, 2)
    assert orc.calls[-1][2]['chosen_option'] == 'QUICK_SUMMARY'
    page.get_by_role('button', name='Account menu', exact=True).click()
    page.get_by_role('menuitem', name='Sign out', exact=True).click()
    page.get_by_role('button', name='Sign In', exact=True).wait_for()
    capture(page, 'mobile-login')


def test_download_link_requests_the_exported_file(dummy_orc, browser_page):
    """EXEC-EXPORT (2026-10-12): the Download link was rewritten into an in-page route (#/api/v1/exports/…), so a click
    never requested the file. The link stays a real API request and the browser receives the file."""
    origin, orc = dummy_orc
    page = browser_page
    original = orc.run
    export_id = 'exp_' + 'a' * 24
    def run(owner, request_id, payload):
        result = original(owner, request_id, payload)
        result['artifacts'] = [{'export_id': export_id, 'file_name': 'bbri.xlsx', 'format': 'XLSX'}]
        return result
    orc.run = run
    page.route('**/api/v1/exports/' + export_id, lambda route: route.fulfill(
        status=200, body=b'PK\x03\x04 dummy', headers={
            'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'content-disposition': 'attachment; filename="bbri.xlsx"'}))
    sign_in(page, origin)
    submit(page, 'Dummy export')
    saved(page)
    link = page.get_by_role('link', name='Download bbri.xlsx', exact=True)
    href = link.get_attribute('href')
    assert '#' not in href and href.endswith('/api/v1/exports/' + export_id)
    with page.expect_download() as download:
        link.click()
    assert download.value.suggested_filename == 'bbri.xlsx'


def test_typing_does_not_redraw_the_page(dummy_orc, browser_page):
    """EXEC-TYPING (2026-10-12): every keystroke rebuilt the whole page (all answers and tables), 76-211 ms per letter
    with 15 answers. Typing now stores the text; only a change between empty and non-empty redraws (the box style and
    the Submit button), and Enter sends the text typed last."""
    origin, orc = dummy_orc
    page = browser_page
    sign_in(page, origin)
    submit(page, 'Dummy first')
    saved(page)
    box = page.get_by_placeholder('Ask a research question…')
    box.click()
    page.keyboard.type('h')  # empty -> non-empty redraws once
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1000)  # the history reload after an answer redraws once on its own
    page.evaluate("""() => { window.__created = 0; const create = document.createElement.bind(document);
        document.createElement = (...args) => { window.__created += 1; return create(...args); }; }""")
    page.keyboard.type('alo dunia', delay=20)
    page.wait_for_timeout(100)
    assert page.evaluate('window.__created') == 0
    assert box.input_value() == 'halo dunia'
    assert page.evaluate('document.activeElement === document.querySelector(".composer textarea")')
    assert page.get_by_role('button', name='Submit', exact=True).is_enabled()
    page.keyboard.press('Enter')
    saved(page, 2)
    assert orc.calls[-1][2]['message'] == 'halo dunia'
    assert box.input_value() == ''
    assert page.get_by_role('button', name='Submit', exact=True).is_disabled()


def test_typing_while_an_answer_arrives_keeps_focus(dummy_orc, browser_page):
    """EXEC-TYPING (user 2026-10-12: "tidak bisa typing, atau hanya bisa typing 1 huruf per 1 huruf"): a redraw while
    an answer ran or arrived moved the message box, a moved element loses focus, and the next letters went nowhere.
    The element that had focus gets it back with its caret after every redraw."""
    origin, orc = dummy_orc
    page = browser_page
    entered, release = threading.Event(), threading.Event()
    original = orc.run
    def blocked(*args):
        entered.set()
        assert release.wait(15)
        return original(*args)
    orc.run = blocked
    sign_in(page, origin)
    submit(page, 'Dummy running')
    assert entered.wait(10)
    box = page.get_by_placeholder('Ask a research question…')
    box.click()
    for letter in 'halo dunia':
        page.keyboard.type(letter)
        page.wait_for_timeout(40)
    release.set()  # the answer arrives while the user keeps typing
    for letter in ' apa kabar':
        page.keyboard.type(letter)
        page.wait_for_timeout(60)
    saved(page)
    page.keyboard.type('!')
    assert box.input_value() == 'halo dunia apa kabar!'
    assert page.evaluate('document.activeElement === document.querySelector(".composer textarea")')


def test_answer_table_sorts_by_its_column_titles(dummy_orc, browser_page):
    """EXEC-SORT (user 2026-10-12, "A. correct"): a click on a column title sorts descending, the second ascending, the
    third restores the original order; the hovered title shows the sort icon, the sorted one its arrow; a Total row
    stays last; numbers are read in Indonesian (Rp, miliar/triliun, %, −) and an empty cell goes last."""
    origin, orc = dummy_orc
    page = browser_page
    original = orc.run
    table = ('| Saham | Net asing | Return |\n|---|---|---|\n| BBRI | Rp 628,5 miliar | 2,87% |\n'
             '| BBCA | −Rp 1,2 triliun | −2,10% |\n| BMRI | Rp 176,6 miliar |  |\n| TLKM | Rp 1.506 miliar | 0,35% |\n'
             '| Total | Rp 1.111,0 miliar | |\n')
    def run(owner, request_id, payload):
        result = original(owner, request_id, payload)
        result['response']['answer'] = 'Ringkasan.\n\n' + table + '\nSelesai.'
        return result
    orc.run = run
    sign_in(page, origin)
    submit(page, 'Dummy table')
    saved(page)
    grid = page.locator('article.result .edge-md-table table')
    first = lambda: grid.locator('tbody tr td:first-child').all_inner_texts()
    assert first() == ['BBRI', 'BBCA', 'BMRI', 'TLKM', 'Total']
    title = grid.locator('th').nth(1)
    title.hover()
    assert title.locator('.edge-sort-icon').evaluate('n => getComputedStyle(n).opacity') == '1'
    assert grid.locator('th').nth(0).locator('.edge-sort-icon').evaluate('n => getComputedStyle(n).opacity') == '0'
    title.locator('button').click()
    assert first() == ['TLKM', 'BBRI', 'BMRI', 'BBCA', 'Total']
    assert title.get_attribute('aria-sort') == 'descending'
    title.locator('button').click()
    assert first() == ['BBCA', 'BMRI', 'BBRI', 'TLKM', 'Total']
    assert title.get_attribute('aria-sort') == 'ascending'
    grid.locator('th').nth(2).locator('button').click()  # another column: descending, empty cell last
    assert first() == ['BBRI', 'TLKM', 'BBCA', 'BMRI', 'Total']
    submit(page, 'Dummy table again')  # a redraw keeps the first answer's order
    saved(page, 2)
    assert first()[:5] == ['BBRI', 'TLKM', 'BBCA', 'BMRI', 'Total']
    grid.first.locator('th').nth(2).locator('button').click()
    grid.first.locator('th').nth(2).locator('button').click()
    assert grid.first.locator('tbody tr td:first-child').all_inner_texts() == ['BBRI', 'BBCA', 'BMRI', 'TLKM', 'Total']
    assert grid.first.locator('th').nth(2).get_attribute('aria-sort') == 'none'


def test_a_table_built_by_the_backend_sorts_and_keeps_its_row_line_below(dummy_orc, browser_page):
    """EXEC-TABLE (user 2026-10-13, "Ya, tampilkan"): a table orc builds from a released output arrives as the same
    Markdown table (sortable as before) with the line "Menampilkan N dari M baris" under it, shown as a plain italic line
    outside the table."""
    origin, orc = dummy_orc
    page = browser_page
    original = orc.run
    table = ('| Sektor | Median | Saham (porsi) |\n|---|---|---|\n| Basic / Ind | 7,0% | 5 (12,5%) |\n'
             '| Energy | 4,3% | 12 (30,0%) |\n| Tech | – | 3 (7,5%) |\n\n_Menampilkan 3 dari 4 baris._')
    def run(owner, request_id, payload):
        result = original(owner, request_id, payload)
        result['response']['answer'] = 'Median per sektor.\n\n' + table + '\n\nSelesai.'
        return result
    orc.run = run
    sign_in(page, origin)
    submit(page, 'Dummy built table')
    saved(page)
    grid = page.locator('article.result .edge-md-table table')
    first = lambda: grid.locator('tbody tr td:first-child').all_inner_texts()
    assert first() == ['Basic / Ind', 'Energy', 'Tech']
    grid.locator('th').nth(1).locator('button').click()  # descending; the dash (no value) goes last
    assert first() == ['Basic / Ind', 'Energy', 'Tech']
    grid.locator('th').nth(1).locator('button').click()
    assert first() == ['Energy', 'Basic / Ind', 'Tech']
    line = page.locator('article.result em', has_text='Menampilkan 3 dari 4 baris.')
    assert line.count() == 1 and grid.locator('em').count() == 0


def test_left_panel_shows_each_question_and_hides_a_deleted_conversation(dummy_orc, browser_page):
    """EXEC-UI-1012 B1 ("B1. (i)"): every conversation in the left panel shows its latest question under the title,
    not only the selected one. EXEC-DELETE ("pakai B hanya sembunyikan di front end tapi backend bisa akses if
    needed", confirmation "Ok"): the trash button next to the bookmark asks first, then hides the conversation from the
    list; it stays hidden after a reload, and Cancel keeps it."""
    origin, orc = dummy_orc
    page = browser_page
    sign_in(page, origin)
    submit(page, 'Dummy first question')
    saved(page)
    page.get_by_role('button', name='New conversation').first.click()
    submit(page, 'Dummy second question')
    saved(page)
    page.reload()
    page.get_by_placeholder('Ask a research question…').wait_for()
    rows = page.locator('.conversation-list .conversation')
    page.wait_for_function('() => document.querySelectorAll(".conversation-list .conversation").length === 2')
    assert sorted(rows.locator('small').all_inner_texts()) == ['Dummy first question', 'Dummy second question']
    first = rows.filter(has_text='Dummy first question')
    first.get_by_role('button', name='Delete Dummy first question').click()
    dialog = page.get_by_role('dialog')
    assert 'will be removed from your list' in dialog.inner_text()
    dialog.get_by_role('button', name='Cancel', exact=True).click()
    assert rows.count() == 2
    first.get_by_role('button', name='Delete Dummy first question').click()
    page.get_by_role('dialog').get_by_role('button', name='Delete', exact=True).click()
    page.wait_for_function('() => document.querySelectorAll(".conversation-list .conversation").length === 1')
    page.reload()
    page.get_by_placeholder('Ask a research question…').wait_for()
    page.wait_for_function('() => document.querySelectorAll(".conversation-list .conversation").length === 1')
    assert rows.locator('small').all_inner_texts() == ['Dummy second question']


def test_the_first_answer_is_headed_by_the_router_title(dummy_orc, browser_page):
    """EXEC-UI-1012 C: the first question's answer and the left panel show the router's short title; the YOU bubble
    keeps the user's words."""
    origin, orc = dummy_orc
    page = browser_page
    original = orc.run
    def run(owner, request_id, payload):
        result = original(owner, request_id, payload)
        result['mode4'] = {'router': {'route': 'ANALYSIS', 'title': 'Harga Saham BBCA'}}
        return result
    orc.run = run
    sign_in(page, origin)
    submit(page, 'Dummy kasih saya data BBCA harga sebulan terakhir')
    saved(page)
    assert page.locator('article.result h1').inner_text() == 'Harga Saham BBCA'
    assert 'Dummy kasih saya data BBCA harga sebulan terakhir' in page.locator('main').inner_text()
    page.reload()
    page.get_by_placeholder('Ask a research question…').wait_for()
    page.wait_for_function('() => document.querySelectorAll(".conversation-list .conversation").length === 1')
    assert page.locator('.conversation-list .conversation strong').inner_text() == 'Harga Saham BBCA'


def test_details_sections_resize_by_drag_and_collapse(dummy_orc, browser_page):
    """EXEC-DETAILS (user 2026-10-12): the line between Pinned responses and Response History is pressed and dragged
    up or down (kept after a reload); each section title collapses and expands its section."""
    origin, orc = dummy_orc
    page = browser_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    sign_in(page, origin)
    for i in range(3):
        submit(page, f'Dummy pin {i}')
        saved(page, i + 1)
    for i in range(3):
        page.get_by_role('button', name='Pin', exact=True).first.click()
        page.wait_for_function('(n) => document.querySelectorAll(".edge-pin-card").length === n', arg=i + 1)
    pins = page.locator('.edge-pins')
    page.wait_for_function('() => document.querySelectorAll(".edge-pin-card").length === 3')
    before = pins.bounding_box()['height']
    handle = page.get_by_role('separator', name='Resize pinned responses')
    box = handle.bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 150, steps=8)
    page.mouse.up()
    after = pins.bounding_box()['height']
    assert after > before + 120
    page.reload()
    page.get_by_placeholder('Ask a research question…').wait_for()
    page.locator('.conversation-list .conversation').first.click()
    page.wait_for_function('() => document.querySelectorAll(".edge-pin-card").length === 3')
    assert abs(page.locator('.edge-pins').bounding_box()['height'] - after) < 3
    page.get_by_role('separator', name='Resize pinned responses').focus()
    page.keyboard.press('ArrowUp')
    assert page.locator('.edge-pins').bounding_box()['height'] < after - 20
    toggle = page.get_by_role('button', name='Pinned responses')
    assert toggle.get_attribute('aria-expanded') == 'true'
    toggle.click()
    assert toggle.get_attribute('aria-expanded') == 'false' and page.locator('.edge-pin-card').count() == 0
    assert page.get_by_role('separator', name='Resize pinned responses').count() == 0
    history = page.get_by_role('button', name='Response History')
    history.click()
    assert history.get_attribute('aria-expanded') == 'false' and page.locator('.edge-flow-accordion').count() == 0
    history.click()
    toggle.click()
    assert page.locator('.edge-pin-card').count() == 3 and page.locator('.edge-flow-accordion').count() == 3


def test_details_split_drags_by_touch_on_a_phone(dummy_orc, browser_page):
    """EXEC-DETAILS: on a phone the line between Pinned responses and Response History follows a finger, and with
    both sections collapsed their titles stay together at the top."""
    origin, orc = dummy_orc
    ctx = browser_page.context.browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True)
    page = ctx.new_page()
    try:
        sign_in(page, origin)
        for i in range(2):
            submit(page, f'Dummy touch {i}')
            saved(page, i + 1)
            page.get_by_role('button', name='Pin', exact=True).first.click()
        page.get_by_role('button', name='Show Details', exact=True).click()
        page.wait_for_function('() => document.querySelectorAll(".edge-pin-card").length === 2')
        pins = page.locator('.edge-pins')
        before = pins.bounding_box()['height']
        box = page.locator('.edge-pins-resizer').bounding_box()
        x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        cdp = ctx.new_cdp_session(page)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
        for step in range(1, 9):
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y + step * 15}]})
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        page.wait_for_timeout(200)
        assert pins.bounding_box()['height'] > before + 90
        page.get_by_role('button', name='Pinned responses').tap()
        page.get_by_role('button', name='Response History').tap()
        heads = [page.get_by_role('button', name=n).bounding_box()['y'] for n in ('Pinned responses', 'Response History')]
        assert 0 < heads[1] - heads[0] < 80
        assert not page.evaluate('() => document.documentElement.scrollWidth > window.innerWidth')
    finally:
        ctx.close()


def test_each_answer_shows_how_long_it_took(dummy_orc, browser_page):
    """EXEC-DURATION (user 2026-10-12: "tambahkan berapa lama each run_id progress, tampilkan di edge sebelah tokens/
    reported cost dan dibagian response history"): Orc's execution.duration_ms is shown next to the tokens and in the
    Response History line."""
    origin, orc = dummy_orc
    page = browser_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    original = orc.run
    def run(owner, request_id, payload):
        result = original(owner, request_id, payload)
        result.setdefault('execution', {})['duration_ms'] = 395718 if 'lama' in payload['message'] else 42400
        return result
    orc.run = run
    sign_in(page, origin)
    submit(page, 'Dummy lama')
    saved(page)
    assert page.locator('article.result .edge-duration').inner_text().endswith('6m 36s')
    submit(page, 'Dummy cepat')
    saved(page, 2)
    assert page.locator('article.result .edge-duration').nth(1).inner_text().endswith('42s')
    history = page.locator('.edge-flow-accordion summary small').all_inner_texts()
    assert any(text.endswith('· 6m 36s') for text in history) and any(text.endswith('· 42s') for text in history)
