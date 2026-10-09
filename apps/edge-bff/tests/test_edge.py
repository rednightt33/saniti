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


def test_stop_button_ends_a_queued_run_here_and_asks_orc_for_a_running_one(settings,store):
    """EXEC-X 2026-10-09: a queued run never reaches Orc; a running one is flagged at Orc (only its owner's);
    nothing running answers 409; the stop needs the CSRF token. EXEC-Y Fase 1: a claimed run stopped before its
    dispatch is never sent to Orc."""
    orc=FakeOrc()
    with TestClient(create_app(settings,store,orc)) as c:
        h=login(c);assert c.get('/api/v1/auth/session').json()['capabilities']['cancel'] is True
        id=c.post('/api/v1/runs',headers=h,json={'message':'Queued','submission_key':'q'}).json()['request_id']
        assert c.post('/api/v1/runs/'+id+'/stop',headers=ORIGIN,json={}).status_code==403
        r=c.post('/api/v1/runs/'+id+'/stop',headers=h,json={});assert r.status_code==202 and r.json()=={'status':'STOPPED'}
        s=c.get('/api/v1/runs/'+id).json();assert s['state']=='FAILED' and s['error_code']=='STOPPED_BY_USER'
        assert store.claim(90) is None and not orc.calls and not getattr(orc,'stopped',[])
        assert c.post('/api/v1/runs/'+id+'/stop',headers=h,json={}).status_code==409  # already ended
        id=c.post('/api/v1/runs',headers=h,json={'message':'Claimed','submission_key':'r'}).json()['request_id']
        row=store.claim(90);assert row['request_id']==id and store.stop_queued(settings.owner,id) is None
        r=c.post('/api/v1/runs/'+id+'/stop',headers=h,json={});assert r.status_code==202 and r.json()=={'status':'STOPPING'}
        assert orc.stopped==[id]
        asyncio.run(Worker(settings,store,orc).process(row))  # marked before dispatch: never sent to Orc
        s=c.get('/api/v1/runs/'+id).json();assert s['state']=='FAILED' and s['error_code']=='STOPPED_BY_USER' and not orc.calls
        assert c.post('/api/v1/runs/'+id+'/stop',headers=h,json={}).status_code==409
        assert c.post('/api/v1/runs/edge_missing/stop',headers=h,json={}).status_code==404


def test_a_dispatched_run_is_flagged_at_orc_and_its_answer_still_arrives(settings,store):
    class Running(FakeOrc):
        def stop(self,owner,id):self.stopped=getattr(self,'stopped',[])+[id];return 'STOPPING'
    orc=Running()
    with TestClient(create_app(settings,store,orc)) as c:
        h=login(c);id=c.post('/api/v1/runs',headers=h,json={'message':'Run','submission_key':'d'}).json()['request_id']
        row=store.claim(90);assert store.attempted(row)  # dispatched
        assert c.post('/api/v1/runs/'+id+'/stop',headers=h,json={}).json()=={'status':'STOPPING'} and orc.stopped==[id]


def test_a_message_sent_while_a_run_is_active_stops_it_and_runs_next_in_its_conversation(settings,store):
    """S3: Send while running = stop that run, then this message runs by itself once it ended; one waiting message;
    a plain send while running is still refused; the waiting message takes the stopped run's conversation."""
    orc=FakeOrc()
    with TestClient(create_app(settings,store,orc)) as c:
        h=login(c)
        first=c.post('/api/v1/runs',headers=h,json={'message':'First','submission_key':'a'}).json()['request_id']
        row=store.claim(90);assert row['request_id']==first
        assert c.post('/api/v1/runs',headers=h,json={'message':'Plain','submission_key':'p'}).status_code==409
        r=c.post('/api/v1/runs',headers=h,json={'message':'Instead','submission_key':'b','after_stop':True})
        assert r.status_code==202 and r.json()['after_request_id']==first and r.json()['state']=='QUEUED',r.text
        second=r.json()['request_id']
        assert c.post('/api/v1/runs',headers=h,json={'message':'Third','submission_key':'c','after_stop':True}).status_code==409
        assert store.claim(90) is None  # waits for the run it follows
        s2=c.get('/api/v1/runs/'+second).json();assert s2['state']=='QUEUED' and s2['message']=='Instead'
        conv='conv_'+'a'*32
        with store.connect() as db:db.execute('UPDATE edge_bff.jobs SET conversation_id=%s WHERE request_id=%s',(conv,first))
        asyncio.run(Worker(settings,store,orc).process(row))
        assert c.get('/api/v1/runs/'+first).json()['error_code']=='STOPPED_BY_USER'
        nxt=store.claim(90);assert nxt['request_id']==second and nxt['conversation_id']==conv and nxt['input']['conversation_id']==conv
        assert 'after_stop' not in nxt['input'] and nxt['input']['after_request_id']==first
        orc.saved['seed']={'request_id':'seed','conversation_id':conv,'turn_status':'COMPLETED','run_status':'COMPLETED','response':{},'user_message':'x'}
        asyncio.run(Worker(settings,store,orc).process(nxt))
        assert orc.calls[-1][2]['conversation_id']==conv and c.get('/api/v1/runs/'+second).json()['state']=='FINISHED'


def test_orc_client_stop_reads_202_and_404_and_never_forwards_upstream_text():
    def handler(request):
        assert request.url.path=='/v1/agent/run/edge_1/stop' and request.headers['x-saniti-owner']=='o'
        return httpx.Response({'edge_1':202}.get(request.url.path.split('/')[-2],404),json={'status':'x'})
    settings=type('S',(),{'orc_key':'k'})()
    client=OrcClient(settings,httpx.Client(base_url='http://orc',transport=httpx.MockTransport(handler)))
    assert client.stop('o','edge_1')=='STOPPING'
    broken=OrcClient(settings,httpx.Client(base_url='http://orc',transport=httpx.MockTransport(lambda r:httpx.Response(500,text='secret upstream'))))
    with pytest.raises(OrcError):broken.stop('o','edge_1')
    missing=OrcClient(settings,httpx.Client(base_url='http://orc',transport=httpx.MockTransport(lambda r:httpx.Response(404))))
    assert missing.stop('o','edge_2')=='NOT_RUNNING'


def test_a_waiting_message_can_itself_be_stopped(settings,store):
    orc=FakeOrc()
    with TestClient(create_app(settings,store,orc)) as c:
        h=login(c)
        first=c.post('/api/v1/runs',headers=h,json={'message':'First','submission_key':'a'}).json()['request_id']
        row=store.claim(90)
        second=c.post('/api/v1/runs',headers=h,json={'message':'Next','submission_key':'b','after_stop':True}).json()['request_id']
        assert c.post('/api/v1/runs/'+second+'/stop',headers=h,json={}).json()=={'status':'STOPPED'}
        asyncio.run(Worker(settings,store,orc).process(row))
        s=c.get('/api/v1/runs/'+second).json();assert s['state']=='FAILED' and s['error_code']=='STOPPED_BY_USER'
        assert store.claim(90) is None and not orc.calls
        assert c.post('/api/v1/runs',headers=h,json={'message':'Next','submission_key':'b','after_stop':True}).json()['request_id']==second  # idempotent
