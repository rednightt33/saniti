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
        page.get_by_role('button', name='Processing…', exact=True).wait_for()
        assert page.get_by_role('button', name='Processing…', exact=True).is_disabled()
        assert page.locator('.edge-response-dots i').count() == 3
        assert page.locator('.edge-response-dots i').first.evaluate('(node) => getComputedStyle(node).animationName') == 'edge-response-pulse'
        animation = page.locator('.edge-response-dots i').first
        first_time = animation.evaluate('(node) => node.getAnimations()[0].currentTime')
        page.wait_for_timeout(150)
        assert animation.evaluate('(node) => node.getAnimations()[0].currentTime') > first_time
        assert not page.get_by_role('button', name='Stop', exact=True).count()  # server cancellation is unavailable
        capture(page, 'desktop-loading')
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
    assert 'EDGE AI · LIMITED' in page.locator('article.result').last.inner_text()
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
    for label in ('Server model', 'Data Scope', 'Attachments are not available yet', 'Public sharing unavailable', 'Support unavailable', 'Notifications unavailable'):
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
    page.get_by_role('button', name='REVISE', exact=True).wait_for()
    saved(page)
    page.locator('.research-scroll').evaluate('(node) => node.scrollTop = 0')
    no_clipping(page)
    capture(page, 'mobile-research-plan')
    page.get_by_role('button', name='REVISE', exact=True).click()
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
