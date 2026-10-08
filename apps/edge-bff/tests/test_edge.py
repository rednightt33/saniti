import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from app.client import OrcClient,OrcError
from app.main import create_app
from app.security import token_hash
from app.store import StoreError
from app.worker import Worker
from conftest import FakeOrc
ORIGIN={'Origin':'http://testserver'}
def login(c):
    r=c.post('/api/v1/auth/sign-in',headers=ORIGIN,json={'login':'owner','password':'local-test-password'});assert r.status_code==200,r.text
    return {**ORIGIN,'X-CSRF-Token':r.json()['csrf_token']}

@pytest.mark.parametrize('status',['COMPLETED','NEEDS_CLARIFICATION','AWAITING_CONFIRMATION','LIMITED','FAILED'])
def test_saved_status_sse_and_metadata(settings,store,status):
    orc=FakeOrc(status)
    with TestClient(create_app(settings,store,orc)) as c:
        h=login(c);r=c.post('/api/v1/runs',headers=h,json={'message':'Explain GOTO','submission_key':'one'});assert r.status_code==202,r.text
        id=r.json()['request_id'];assert c.get('/api/v1/runs').json()['active']['request_id']==id
        asyncio.run(Worker(settings,store,orc).process(store.claim(90)))
        s=c.get('/api/v1/runs/'+id).json();assert s['state']=='FINISHED' and s['run_status']==status and s['response']==orc.saved[id]['response']
        stream=c.get('/api/v1/runs/'+id+'/events',headers={'Last-Event-ID':str(s['state_version'])})
        assert stream.status_code==200 and 'event: snapshot' in stream.text and 'Saved answer' in stream.text
        assert 'no-transform' in stream.headers['cache-control'] and stream.headers['x-accel-buffering']=='no' and stream.headers['content-encoding']=='identity'
        conv=s['conversation_id'];assert c.patch('/api/v1/conversations/'+conv+'/preferences',headers=h,json={'bookmarked':True}).json()['bookmarked']
        assert c.patch('/api/v1/runs/'+id+'/preferences',headers=h,json={'pinned':True}).json()['pinned_request_ids']==[id]
        assert c.get('/api/v1/conversations?bookmarked=true').json()['items'][0]['conversation_id']==conv
        assert c.get('/api/v1/conversations/'+conv+'/messages').json()['messages'][0]['response']==s['response']
        assert type(store)(settings.database_url).conversation(settings.owner,conv)['bookmarked']
        assert c.post('/api/v1/auth/sign-out',headers=h,json={}).status_code==200 and c.get('/api/v1/runs/'+id).status_code==401

def test_auth_csrf_validation_and_storage(settings,store):
    with TestClient(create_app(settings,store,FakeOrc())) as c:
        assert c.get('/api/v1/conversations').status_code==401
        assert c.post('/api/v1/auth/sign-in',json={'login':'owner','password':'local-test-password'}).status_code==403
        assert c.post('/api/v1/auth/sign-in',headers=ORIGIN,json={'login':'owner','password':'wrong'}).status_code==401
        h=login(c);cookie=c.cookies['edge_session']
        with store.connect() as db:
            s=db.execute('SELECT * FROM edge_bff.sessions').fetchone();assert s['token_hash']==token_hash(cookie) and s['token_hash']!=cookie
            db.execute('UPDATE edge_bff.sessions SET revoked_at=now() WHERE token_hash=%s',(token_hash(cookie),))
        assert c.get('/api/v1/auth/session').status_code==401
        h=login(c);assert c.post('/api/v1/runs',headers=ORIGIN,json={'message':'Hello','submission_key':'x'}).status_code==403
        for bad in ({'model':'other'},{'owner':'foreign'},{'analysis_path':'ANALYSIS'},{'history':[]},{'message':' '}):
            r=c.post('/api/v1/runs',headers=h,json={'message':'Hello','submission_key':'x',**bad});assert r.status_code==422,r.text
        assert c.post('/api/v1/runs',headers=h,json={'message':'x'*140000,'submission_key':'x'}).status_code==413

def test_concurrent_idempotency_and_owner_isolation(settings,store):
    with ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(lambda _:store.submit(settings.owner,'same',{'message':'One'}),range(6)))
    assert len({r['request_id'] for r,_ in rows})==1 and sum(created for _,created in rows)==1
    with pytest.raises(StoreError,match='SUBMISSION_CONFLICT'):store.submit(settings.owner,'same',{'message':'Changed'})
    with pytest.raises(StoreError,match='RUN_IN_PROGRESS'):store.submit(settings.owner,'another',{'message':'One'})
    with pytest.raises(StoreError,match='RUN_NOT_FOUND'):store.job('foreign',rows[0][0]['request_id'])
    foreign,_=store.submit('foreign','a',{'message':'Private'})
    with TestClient(create_app(settings,store,FakeOrc())) as c:
        login(c);assert c.get('/api/v1/runs/'+foreign['request_id']).status_code==404 and c.get('/api/v1/runs/'+foreign['request_id']+'/events').status_code==404

def test_recovery_after_dispatch_timeout_never_reexecutes(settings,store):
    class LostReply(FakeOrc):
        def run(self,*args):super().run(*args);raise OrcError(ambiguous=True)
    orc=LostReply();job,_=store.submit(settings.owner,'recover',{'message':'Recover'})
    asyncio.run(Worker(settings,store,orc).process(store.claim(90)))
    assert store.job(settings.owner,job['request_id'])['state']=='FINISHED' and len(orc.calls)==1

def test_restart_reclaims_lease_and_fences_stale_worker(settings,store):
    orc=FakeOrc();job,_=store.submit(settings.owner,'restart',{'message':'Restart'});old=store.claim(90);assert store.attempted(old)
    orc.run(settings.owner,job['request_id'],job['input'])
    with store.connect() as c:c.execute("UPDATE edge_bff.jobs SET lease_expires_at=now()-interval '1 second'")
    assert not store.heartbeat(old['request_id'],old['lease_token'],90)
    new=store.claim(90);assert new['lease_token']!=old['lease_token'] and store.transition(old,'FAILED') is None
    asyncio.run(Worker(settings,store,orc).process(new))
    assert len(orc.calls)==1 and store.job(settings.owner,job['request_id'])['state']=='FINISHED'

def test_not_saved_and_expired_canonical_history(settings,store):
    class Unsaved(FakeOrc):
        def run(self,*args):r=super().run(*args);r['conversation']['persistence']='NOT_SAVED';return r
    orc=Unsaved();job,_=store.submit(settings.owner,'unsaved',{'message':'Not saved'})
    asyncio.run(Worker(settings,store,orc).process(store.claim(90)));assert store.job(settings.owner,job['request_id'])['error_code']=='RESULT_NOT_SAVED'
    orc=FakeOrc();job,_=store.submit(settings.owner,'expired',{'message':'Expire'});asyncio.run(Worker(settings,store,orc).process(store.claim(90)))
    conv=store.job(settings.owner,job['request_id'])['conversation_id'];orc.saved.clear()
    with TestClient(create_app(settings,store,orc)) as c:
        h=login(c);assert c.get('/api/v1/runs/'+job['request_id']).json()['expired']
        assert c.get('/api/v1/conversations/'+conv+'/messages').status_code==410
        assert c.patch('/api/v1/runs/'+job['request_id']+'/preferences',headers=h,json={'pinned':True}).status_code==409

@pytest.mark.parametrize('extra',[{'chosen_option':'QUICK_SUMMARY'},*[{'plan_reply':{'plan_id':'rp_'+'a'*24,'action':a,**({'revision_instruction':'Use one year'} if a=='REVISE' else {})}} for a in ('APPROVE','REVISE','CANCEL')]])
def test_continuations_without_mode_override(settings,extra):
    bodies=[]
    def handler(req):
        import json
        bodies.append(json.loads(req.content));return httpx.Response(200,json={'status':'COMPLETED'})
    c=OrcClient(settings,httpx.Client(base_url=settings.orc_url,transport=httpx.MockTransport(handler)))
    c.run(settings.owner,'edge_'+'a'*32,{'message':'Reply','model':'drop','analysis_path':'drop',**extra})
    assert bodies==[{'message':'Reply',**extra,'request_id':'edge_'+'a'*32,'history_mode':'SERVER'}]

def test_private_diagnostics_and_fixed_headers(settings):
    seen=[]
    def handler(req):seen.append(req);return httpx.Response(200,json={'answer':'Safe','reasoning':'private','nested':{'memo_note':'private','url':'http://orc.railway.internal:8080/private'}})
    c=OrcClient(settings,httpx.Client(base_url=settings.orc_url,transport=httpx.MockTransport(handler)));r=c.request(settings.owner,'edge_'+'a'*32)
    assert 'reasoning' not in r and 'memo_note' not in r['nested'] and 'railway.internal' not in str(r)
    assert seen[0].headers['x-saniti-owner']==settings.owner and seen[0].headers['authorization']=='Bearer '+settings.orc_key

def test_restricted_runtime_and_no_response_copy(store):
    with store.connect() as c:
        columns=c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='edge_bff' AND table_name='jobs'").fetchall();assert not {'response','reasoning','events'} & {x['column_name'] for x in columns}
        c.execute('SET LOCAL ROLE edge_bff_runtime');c.execute('SELECT * FROM edge_bff.jobs LIMIT 0')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM public.market_private')

def test_provisioned_login_can_only_access_operational_schema(database,monkeypatch):
    import importlib.util
    from pathlib import Path
    import secrets
    from urllib.parse import urlsplit,urlunsplit
    helper=Path(__file__).resolve().parents[3]/'scripts/provision_edge_bff_login.py'
    spec=importlib.util.spec_from_file_location('edge_provision',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setenv('DATABASE_URL',database);monkeypatch.setenv('EDGE_DB_PASSWORD',secrets.token_hex(24))
    try:
        module.main()
        p=urlsplit(database);netloc='edge_bff_login:'+os.environ['EDGE_DB_PASSWORD']+'@'+p.netloc.split('@')[-1]
        restricted=urlunsplit((p.scheme,netloc,p.path,p.query,p.fragment))
        with psycopg.connect(restricted) as c:
            c.execute('SELECT * FROM edge_bff.jobs LIMIT 0')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM public.market_private')
    finally:
        with psycopg.connect(database) as c:
            c.execute('DROP OWNED BY edge_bff_login');c.execute('DROP ROLE edge_bff_login')

@pytest.mark.parametrize('detail',[{'code':'HISTORY_MODE_UNAVAILABLE'},'Not Found'])
def test_unavailable_orc_read_route_is_not_an_absent_request(settings,detail):
    client=OrcClient(settings,httpx.Client(base_url=settings.orc_url,transport=httpx.MockTransport(lambda _:httpx.Response(404,json={'detail':detail}))))
    with pytest.raises(OrcError,match='ORC_REQUEST_READ_UNAVAILABLE'):client.request(settings.owner,'edge_'+'a'*32)
    client=OrcClient(settings,httpx.Client(base_url=settings.orc_url,transport=httpx.MockTransport(lambda _:httpx.Response(404,json={'detail':{'code':'REQUEST_NOT_FOUND'}}))))
    assert client.request(settings.owner,'edge_'+'a'*32) is None

def test_deployment_refuses_admin_credentials_and_short_deadline(settings):
    from dataclasses import replace
    configured=replace(settings,environment='dev',secure_cookie=True,origin='https://edge.example',orc_url='http://market-ai-orc.railway.internal:8080')
    with pytest.raises(ValueError,match='dedicated edge_bff_login'):configured.validate()
    configured=replace(configured,database_url='postgresql://edge_bff_login@postgres.railway.internal/railway')
    configured.validate()
    with pytest.raises(ValueError,match='timeout'):replace(configured,orc_timeout_seconds=3600).validate()
