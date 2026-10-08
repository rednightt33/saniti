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
        assert page.get_by_role('button',name='Server model').is_disabled()
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
        for action in ('APPROVE','REVISE','CANCEL'):
            page.get_by_role('button',name='New conversation',exact=True).click()
            composer.fill('Plan '+action);page.get_by_role('button',name='Submit',exact=True).click()
            button=page.get_by_role('button',name=action,exact=True);button.wait_for();button.click()
            if action=='REVISE':composer.fill('Use one year');page.get_by_role('button',name='Submit',exact=True).click()
            page.wait_for_function("() => document.querySelector('.composer-status')===null")
            page.wait_for_timeout(300)
            assert orc.calls[-1][2]['plan_reply']['action']==action
            if action=='REVISE':assert orc.calls[-1][2]['plan_reply']['revision_instruction']=='Use one year'
        page.get_by_role('button',name='New conversation',exact=True).click();composer.fill('Clarify');page.get_by_role('button',name='Submit',exact=True).click()
        page.get_by_role('button',name='Quick summary',exact=True).click();page.wait_for_timeout(350)
        assert orc.calls[-1][2]['chosen_option']=='QUICK_SUMMARY'
        assert len({id for _,id,_ in orc.calls})==len(orc.calls)
        assert all('model' not in payload and 'analysis_path' not in payload for _,_,payload in orc.calls)
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
