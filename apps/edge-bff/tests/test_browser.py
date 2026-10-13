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
        assert page.locator('.edge-model-trigger').inner_text().split()[:4]==['D','DeepSeek','V4.1','Flash']
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
        for action,label in (('APPROVE','Setujui & jalankan'),('REVISE','Revisi'),('CANCEL','Batalkan')):
            page.get_by_role('button',name='New conversation',exact=True).click()
            composer.fill('Plan '+action);page.get_by_role('button',name='Submit',exact=True).click()
            button=page.get_by_role('button',name=label,exact=True);button.wait_for();button.click()
            if action=='REVISE':composer.fill('Use one year');page.get_by_role('button',name='Submit',exact=True).click()
            page.wait_for_function("() => document.querySelector('.composer-status')===null")
            page.wait_for_timeout(300)
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
    """EXEC-MODELS (user 2026-10-13): five models with their input and output price per one million tokens, the levels
    each takes, DeepSeek V4.1 Flash high at first, the choice sent with the message and kept after a reload."""
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
        assert 'Tinggi' in trigger.inner_text()
        trigger.click()
        options=page.locator('.edge-model-option')
        assert options.count()==5
        glm=options.filter(has_text='GLM 5.3 Flash')
        assert '$0.026' in glm.inner_text() and '$0.90' in glm.inner_text()
        assert 'Harga diperbarui' in page.locator('.edge-model-head').inner_text()
        assert [b.inner_text() for b in page.locator('.edge-model-levels button').all()]==['Rendah','Sedang','Tinggi']
        options.filter(has_text='MiMo V2.6 Pro').click()
        assert [b.inner_text() for b in page.locator('.edge-model-levels button').all()]==['Mati','Nyala']
        glm.click();page.locator('.edge-model-levels button',has_text='Sedang').click()
        page.keyboard.press('Escape');assert not page.locator('.edge-model-menu').count()
        composer.fill('Explain BBRI');page.get_by_role('button',name='Submit',exact=True).click()
        page.locator('article.result').wait_for()
        assert orc.calls[-1][2]['model']=='z-ai/glm-5.3-flash' and orc.calls[-1][2]['reasoning_level']=='medium'
        assert 'z-ai/glm-5.3-flash · Sedang' in page.locator('.edge-run-model').first.inner_text()
        page.reload();ready=page.locator('.edge-model-trigger:not([disabled])');ready.wait_for()
        assert 'GLM 5.3 Flash' in ready.inner_text() and 'Sedang' in ready.inner_text()
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
