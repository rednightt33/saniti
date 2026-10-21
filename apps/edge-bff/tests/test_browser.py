"""Supplied HTML through the actual BFF + local Postgres; Orc is deterministic, no paid calls."""
from dataclasses import replace
import socket
import os
import threading
import time
import pytest
import uvicorn
from app.main import create_app
from conftest import FakeOrc


def test_dependency_wait_then_session_initialization_is_visible_without_duplicate_dispatch(server):
    """Real BFF queue + Postgres + browser, deterministic upstream; no paid model call."""
    playwright = pytest.importorskip('playwright.sync_api')
    origin, orc = server
    ready, finish = threading.Event(), threading.Event()
    original_run = orc.run
    orc.execution_ready = lambda owner: ready.is_set()
    def run(owner, request_id, payload):
        orc.PROGRESS = {request_id: {'status': 'RUNNING', 'elapsed_ms': 0, 'earlier_steps': 0,
                                    'steps': [{'label': 'Initiating sandbox session.', 'state': 'running',
                                               'started_ms': 0, 'duration_ms': 0}]}}
        assert finish.wait(20)
        return original_run(owner, request_id, payload)
    orc.run = run
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium'),
                                     headless=True, args=['--no-sandbox'])
        try:
            page = browser.new_page()
            page.route('https://fonts.*/*', lambda route: route.abort())
            page.goto(origin + '/monitor')
            page.locator('#auth-login').fill('owner')
            page.locator('#auth-password').fill('local-test-password')
            page.get_by_role('button', name='Sign In', exact=True).click()
            composer = page.get_by_placeholder('Ask a research question…')
            composer.fill('Calculate in sandbox')
            page.get_by_role('button', name='Submit', exact=True).click()
            page.get_by_text('Waiting for services to be ready.', exact=True).first.wait_for()
            assert not orc.calls
            ready.set()
            page.get_by_text('Initiating sandbox session.', exact=True).first.wait_for()
            finish.set()
            page.locator('article.result').wait_for()
            assert len(orc.calls) == 1
        finally:
            ready.set()
            finish.set()
            browser.close()

@pytest.fixture
def server(settings,store):
    class BrowserOrc(FakeOrc):
        def run(self,owner,id,payload):
            time.sleep(0.1)
            result=super().run(owner,id,payload)
            if payload['message'].startswith('Plan'):
                result['status']='AWAITING_CONFIRMATION'
                result['response']['response_type']='RESEARCH_PLAN_CONFIRMATION'
                result['response']['research_plan']={'plan_version':'research_plan/v1','objective':'Research GOTO'}
                result['continuation']={'plan_id':'rp_'+'a'*24}
            elif payload['message']=='Clarify':
                result['status']='NEEDS_CLARIFICATION'
                result['response'].update(response_type='CLARIFICATION',answer='',clarification_question='Choose a route')
            self.saved[id]['run_status']=result['status'];return result
    orc=BrowserOrc()
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    settings=replace(settings,origin=f'http://127.0.0.1:{port}',worker_enabled=True,poll_seconds=0.02)
    application=create_app(settings,store,orc)
    server=uvicorn.Server(uvicorn.Config(application,log_level='critical',access_log=False))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(0.02)
    assert server.started
    try:yield settings.origin,orc
    finally:server.should_exit=True;thread.join(timeout=10);sock.close()

def test_private_html_real_submit_reload_preferences_and_continuations(server):
    playwright=pytest.importorskip('playwright.sync_api')
    origin,orc=server
    with playwright.sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1600,'height':1000})
        page.route('https://fonts.*/*',lambda route:route.abort())
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(origin+'/monitor')
        page.locator('#auth-login').fill('owner');page.locator('#auth-password').fill('local-test-password')
        page.get_by_role('button',name='Sign In',exact=True).click()
        composer=page.get_by_placeholder('Ask a research question…')
        composer.wait_for();composer.fill('Explain GOTO');page.get_by_role('button',name='Submit',exact=True).click()
        page.locator('article.result').wait_for()
        assert page.evaluate('window.pwned') is None
        assert 'Saved answer' in page.locator('article.result').inner_text()
        page.locator('.edge-model-trigger:not([disabled])').wait_for()
        assert page.locator('.edge-model-trigger').inner_text().split()[:3]==['DeepSeek','V4.1','Flash']
        assert page.locator('.edge-model-trigger img.edge-model-logo').get_attribute('src')=='/model-logos/deepseek-color.svg'
        assert page.get_by_role('button',name='Public sharing unavailable').is_disabled()
        page.get_by_role('button',name='Pin',exact=True).click()
        page.get_by_role('button',name='Pinned',exact=True).wait_for()
        page.get_by_role('button',name='Bookmark',exact=True).click()
        page.wait_for_function("() => document.querySelector('[aria-label=Bookmark]').getAttribute('aria-pressed')==='true'")
        page.get_by_role('tab',name='Sources',exact=True).click()
        assert page.get_by_text('No source or evidence metadata returned for this response.').is_visible()
        assert page.evaluate("localStorage.getItem('edge-auth-monitor-conversations')") is None
        page.reload();composer.wait_for()
        page.locator('.conversation-list .conversation[role=button]').first.click()
        page.locator('article.result').wait_for()
        assert page.get_by_role('button',name='Pinned',exact=True).is_visible()
        assert page.get_by_role('button',name='Bookmark',exact=True).get_attribute('aria-pressed')=='true'
        for action,label in (('APPROVE','Approve & run'),('REVISE','Revise'),('CANCEL','Cancel')):
            page.get_by_role('button',name='New conversation',exact=True).click()
            composer.fill('Plan '+action);page.get_by_role('button',name='Submit',exact=True).click()
            button=page.get_by_role('button',name=label,exact=True);button.wait_for();button.click()
            if action=='REVISE':composer.fill('Use one year');page.get_by_role('button',name='Submit',exact=True).click()
            page.wait_for_function("() => document.querySelector('.composer-status')===null")
            # the reply is sent after the click's redraw: wait for Orc to receive it (the composer can be idle before)
            for _ in range(100):
                if 'plan_reply' in orc.calls[-1][2]:break
                page.wait_for_timeout(50)
            assert orc.calls[-1][2]['plan_reply']['action']==action
            if action=='REVISE':assert orc.calls[-1][2]['plan_reply']['revision_instruction']=='Use one year'
        page.get_by_role('button',name='New conversation',exact=True).click();composer.fill('Clarify');page.get_by_role('button',name='Submit',exact=True).click()
        page.get_by_role('button',name='Quick summary',exact=True).click();page.wait_for_timeout(350)
        assert orc.calls[-1][2]['chosen_option']=='QUICK_SUMMARY'
        assert len({id for _,id,_ in orc.calls})==len(orc.calls)
        assert all(payload.get('model')=='deepseek/deepseek-v4.1-flash' and payload.get('reasoning_level')=='high'
                   and 'analysis_path' not in payload for _,_,payload in orc.calls)  # EXEC-MODELS: EDGE starts on DeepSeek high
        page.get_by_role('button',name='Account menu',exact=True).click();page.get_by_role('menuitem',name='Sign out').click()
        page.get_by_role('button',name='Sign In',exact=True).wait_for()
        assert errors==[],errors
        browser.close()

def test_sse_delivers_while_orc_waits_and_refresh_resumes(server):
    import httpx
    origin,orc=server
    release=threading.Event();entered=threading.Event();run=orc.run
    def blocked(*args):entered.set();release.wait(timeout=10);return run(*args)
    orc.run=blocked
    with httpx.Client(base_url=origin,timeout=3) as c:
        auth=c.post('/api/v1/auth/sign-in',headers={'Origin':origin},json={'login':'owner','password':'local-test-password'}).json()
        headers={'Origin':origin,'X-CSRF-Token':auth['csrf_token']}
        accepted=c.post('/api/v1/runs',headers=headers,json={'message':'Wait for actual AI','submission_key':'stream'}).json()
        id=accepted['request_id'];assert entered.wait(timeout=3)
        try:
            with c.stream('GET','/api/v1/runs/'+id+'/events') as response:
                lines=response.iter_lines()
                first=next(lines);assert first.startswith('id: ')
                assert next(lines)=='event: snapshot'
                assert 'RUNNING' in next(lines)
                # M153: while nothing changes the stream sends a named ping the page can see (not an SSE comment)
                rest=[next(lines) for _ in range(3)]
                assert 'event: ping' in rest
                # The async event loop still serves health and refresh recovery while the Orc thread waits.
                assert c.get('/health').status_code==200
                assert c.get('/api/v1/runs').json()['active']['request_id']==id
        finally:release.set()
        for _ in range(100):
            snapshot=c.get('/api/v1/runs/'+id).json()
            if snapshot['state']=='FINISHED':break
            time.sleep(0.02)
        assert snapshot['state']=='FINISHED' and len(orc.calls)==1


def test_the_model_choice_lists_prices_changes_levels_and_is_remembered(server):
    """EXEC-MODELS (user 2026-10-13): four models (EXEC-LOGOS: MiMo V2.6 Pro removed) with their input and output price
    per one million tokens, the levels each takes, DeepSeek V4.1 Flash high at first, the choice sent with the message and kept after a reload."""
    playwright=pytest.importorskip('playwright.sync_api')
    origin,orc=server
    with playwright.sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1600,'height':1000})
        page.route('https://fonts.*/*',lambda route:route.abort())
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(origin+'/monitor')
        page.locator('#auth-login').fill('owner');page.locator('#auth-password').fill('local-test-password')
        page.get_by_role('button',name='Sign In',exact=True).click()
        composer=page.get_by_placeholder('Ask a research question…');composer.wait_for()
        trigger=page.locator('.edge-model-trigger:not([disabled])');trigger.wait_for()
        assert 'High' in trigger.inner_text()
        trigger.click()
        options=page.locator('.edge-model-option')
        assert options.count()==4
        # EXEC-LOGOS: each model shows its brand logo, served from this origin
        assert page.locator('.edge-model-option .edge-model-logo').count()==4
        assert all(page.evaluate("u=>fetch(u).then(r=>r.ok&&r.headers.get('content-type').startsWith('image/svg'))",u) for u in ['/model-logos/deepseek-color.svg','/model-logos/zai.svg','/model-logos/xiaomimimo.svg','/model-logos/qwen-color.svg'])
        glm=options.filter(has_text='GLM 5.3 Flash')
        assert '$0.026' in glm.inner_text() and '$0.90' in glm.inner_text()
        assert 'Prices updated' in page.locator('.edge-model-head').inner_text()
        assert [b.inner_text() for b in page.locator('.edge-model-levels button').all()]==['Low','High','Max']
        options.filter(has_text='MiMo V2.6 Flash').click()
        assert [b.inner_text() for b in page.locator('.edge-model-levels button').all()]==['Off','On']
        glm.click();page.locator('.edge-model-levels button',has_text='Max').click()
        page.keyboard.press('Escape');assert not page.locator('.edge-model-menu').count()
        composer.fill('Explain BBRI');page.get_by_role('button',name='Submit',exact=True).click()
        page.locator('article.result').wait_for()
        assert orc.calls[-1][2]['model']=='z-ai/glm-5.3-flash' and orc.calls[-1][2]['reasoning_level']=='max'
        assert 'lane' not in orc.calls[-1][2] and not page.locator('.edge-model-lanes').count()  # no lane_selection
        # EXEC-UI-1015E (user 2026-10-15, "ini nama mode saja langsung"): the model's name, its id in the tooltip
        assert 'GLM 5.3 Flash · Max' in page.locator('.edge-run-model').first.inner_text()
        assert page.locator('.edge-run-model-name').first.get_attribute('title') == 'z-ai/glm-5.3-flash'
        # EXEC-UI-1013B (gambar 2): the model's logo left of its name in the answer's header
        header_logo = page.locator('.edge-run-model').first.locator('.edge-model-logo')
        assert header_logo.count() == 1 and header_logo.is_visible()
        page.reload();ready=page.locator('.edge-model-trigger:not([disabled])');ready.wait_for()
        assert 'GLM 5.3 Flash' in ready.inner_text() and 'Max' in ready.inner_text()
        assert errors==[],errors
        browser.close()


def test_on_a_phone_the_model_choice_shows_the_logo_name_and_level(server):
    """EXEC-LOGOS (user 2026-10-13, "kasih logo untuk setiap model ya di HP"): on a phone the trigger shows the model's
    logo, and since 2026-10-21 (user: "tinggal tambah model name dan reasoning type") its name and level too; the
    one-colour logos (Z.ai, MiMo) take the text colour; every option in the menu has its logo."""
    playwright=pytest.importorskip('playwright.sync_api')
    origin,orc=server
    with playwright.sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
        page.route('https://fonts.*/*',lambda route:route.abort())
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(origin+'/monitor')
        page.locator('#auth-login').fill('owner');page.locator('#auth-password').fill('local-test-password')
        page.get_by_role('button',name='Sign In',exact=True).click()
        trigger=page.locator('.edge-model-trigger:not([disabled])');trigger.wait_for()
        logo=trigger.locator('.edge-model-logo')
        page.wait_for_function("() => document.querySelector('.edge-model-trigger img.edge-model-logo')?.complete && document.querySelector('.edge-model-trigger img.edge-model-logo').naturalWidth>0")
        box=logo.bounding_box();assert box and box['width']>=16 and box['height']>=16
        assert trigger.locator('.edge-model-name').is_visible() and trigger.locator('.edge-model-level').is_visible()
        trigger.click()
        options=page.locator('.edge-model-option');assert options.count()==4
        assert all(options.nth(i).locator('.edge-model-logo').is_visible() for i in range(4))
        mimo=options.filter(has_text='MiMo V2.6 Flash').locator('.edge-model-logo.mono')
        assert 'xiaomimimo.svg' in mimo.evaluate("e=>getComputedStyle(e).maskImage||getComputedStyle(e).webkitMaskImage")
        mimo.click();page.keyboard.press('Escape')
        assert trigger.locator('.edge-model-logo.mono').get_attribute('aria-label')=='MiMo V2.6 Flash'
        assert errors==[],errors
        browser.close()


def test_without_the_model_list_the_choice_is_hidden_and_the_message_goes_without_it(settings,store):
    playwright=pytest.importorskip('playwright.sync_api')
    from app.client import OrcError

    class NoModels(FakeOrc):
        def models(self,owner):raise OrcError()
    orc=NoModels()
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    local=replace(settings,origin=f'http://127.0.0.1:{port}',worker_enabled=True,poll_seconds=0.02)
    server=uvicorn.Server(uvicorn.Config(create_app(local,store,orc),log_level='critical',access_log=False))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(0.02)
    try:
        with playwright.sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1600,'height':1000})
            page.route('https://fonts.*/*',lambda route:route.abort())
            page.goto(local.origin+'/monitor')
            page.locator('#auth-login').fill('owner');page.locator('#auth-password').fill('local-test-password')
            page.get_by_role('button',name='Sign In',exact=True).click()
            composer=page.get_by_placeholder('Ask a research question…');composer.wait_for();page.wait_for_timeout(300)
            assert not page.locator('.edge-model-trigger').count()
            composer.fill('Explain GOTO');page.get_by_role('button',name='Submit',exact=True).click()
            page.locator('article.result').wait_for()
            assert 'model' not in orc.calls[-1][2] and 'reasoning_level' not in orc.calls[-1][2]
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close()


def _blocked_stream_page(server, pw):
    """A page whose run stream never answers (the iOS case: the EventSource is dead and fires no error)."""
    origin,orc=server
    browser=pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    page.route('https://fonts.*/*',lambda route:route.abort())
    page.route('**/api/v1/runs/*/events',lambda route:None)  # never fulfilled: the stream hangs silently
    page.goto(origin+'/monitor')
    page.locator('#auth-login').fill('owner');page.locator('#auth-password').fill('local-test-password')
    page.get_by_role('button',name='Sign In',exact=True).click()
    composer=page.get_by_placeholder('Ask a research question…');composer.wait_for()
    return browser,page,composer


def test_a_silent_run_stream_is_replaced_and_the_answer_shows_without_a_reload(server):
    """M153 (EXEC-UI-1013B): on iPhone the answer appeared only after a refresh; a stream silent for 15 s is replaced
    and the run's status is read, so the answer shows."""
    playwright=pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw:
        browser,page,composer=_blocked_stream_page(server,pw)
        composer.fill('Explain BBRI');page.get_by_role('button',name='Submit',exact=True).click()
        page.locator('article.result').wait_for(timeout=30000)
        assert 'Saved answer' in page.locator('article.result').inner_text()
        browser.close()


def test_a_page_shown_again_reads_the_run_at_once(server):
    """M153: when the page becomes visible again (back from another app) the run's status is read at once."""
    playwright=pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw:
        browser,page,composer=_blocked_stream_page(server,pw)
        composer.fill('Explain BBRI');page.get_by_role('button',name='Submit',exact=True).click()
        page.wait_for_timeout(1500)  # the worker has answered; the hung stream has not told the page
        assert not page.locator('article.result').count()
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        page.locator('article.result').wait_for(timeout=5000)
        browser.close()


def test_every_message_runs_the_fast_lane_without_a_lane_choice(server):
    """EXEC-UI-1015D (user 2026-10-15, "bisa buat semua jalur cepat ... sehingga kita tidak perlu ada opsi jalur"): while
    Orc reports lane_selection every message is sent as lane "fast" and the picker offers no lane, even when the old
    toggle left "standard" in this browser; the answer's header names the fast lane. Without lane_selection no lane is
    sent (test_the_model_choice_lists_prices_changes_levels_and_is_remembered)."""
    playwright=pytest.importorskip('playwright.sync_api')
    origin,orc=server
    orc.MODELS={**orc.MODELS,'lane_selection':True}
    with playwright.sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1600,'height':1000})
        page.route('https://fonts.*/*',lambda route:route.abort())
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(origin+'/monitor')
        page.evaluate("() => localStorage.setItem('edge-lane', 'standard')")  # left by the old toggle
        page.locator('#auth-login').fill('owner');page.locator('#auth-password').fill('local-test-password')
        page.get_by_role('button',name='Sign In',exact=True).click()
        composer=page.get_by_placeholder('Ask a research question…');composer.wait_for()
        trigger=page.locator('.edge-model-trigger:not([disabled])');trigger.wait_for()
        trigger.click()
        assert not page.locator('.edge-model-lanes').count() and 'Lane' not in page.locator('.edge-model-menu').inner_text()
        page.keyboard.press('Escape')
        composer.fill('Explain BBRI cepat');page.get_by_role('button',name='Submit',exact=True).click()
        page.locator('article.result').wait_for()
        assert orc.calls[-1][2]['lane']=='fast'
        # EXEC-UI-1015E (user 2026-10-15, "tidak perlu ada fast lane, karena ini default"): the lane is not named
        page.locator('.edge-run-model').first.wait_for()
        assert 'Fast lane' not in page.locator('.edge-run-model').first.inner_text()
        assert errors==[],errors
        browser.close()
