import os
from pathlib import Path
import uuid
from urllib.parse import urlsplit,urlunsplit
import psycopg
import pytest
from app.config import Settings
from app.security import password_verifier
from app.store import Store

@pytest.fixture(scope='session')
def database():
    admin=os.environ.get('EDGE_TEST_POSTGRES_URL','')
    if not admin: pytest.skip('EDGE_TEST_POSTGRES_URL requires a disposable Postgres')
    name='edge_test_'+uuid.uuid4().hex[:12];p=urlsplit(admin);url=urlunsplit((p.scheme,p.netloc,'/'+name,p.query,p.fragment))
    with psycopg.connect(admin,autocommit=True) as c:c.execute(f'CREATE DATABASE "{name}"')
    try:
        with psycopg.connect(url,autocommit=True) as c:
            c.execute((Path(__file__).resolve().parents[3]/'database/migrations/20261008_002_create_edge_bff.sql').read_text())
            c.execute('CREATE TABLE public.market_private(secret text)')
        yield url
    finally:
        with psycopg.connect(admin,autocommit=True) as c:
            c.execute(f'DROP DATABASE "{name}" WITH (FORCE)');c.execute('DROP ROLE edge_bff_runtime')

@pytest.fixture
def store(database):
    with psycopg.connect(database) as c:c.execute('TRUNCATE edge_bff.sessions,edge_bff.jobs,edge_bff.conversation_ui')
    return Store(database)

@pytest.fixture
def settings(database):
    return Settings(database_url=database,orc_url='http://orc.invalid',orc_key='local-test-key',owner='local-test-owner',login='owner',password_verifier=password_verifier('local-test-password'),session_secret='local-test-secret-'*3,origin='http://testserver',environment='local',secure_cookie=False,worker_enabled=False,poll_seconds=0.005)

class FakeOrc:
    def __init__(self,status='COMPLETED'):self.status=status;self.saved={};self.calls=[]
    def run(self,owner,id,payload):
        self.calls.append((owner,id,payload.copy()));conv=payload.get('conversation_id') or 'conv_'+uuid.uuid4().hex
        result={'request_id':id,'status':self.status,'response':{'response_type':'ANSWER','answer':'Saved answer <script>window.pwned=true</script>','assumptions':[],'limitations':[],'clarification_question':None,'research_plan':None},'execution':{'model':'fixture-model','cost':0.001,'total_tokens':42},'conversation':{'conversation_id':conv,'persistence':'SAVED'},'options':[{'label':'Quick summary','route':'QUICK_SUMMARY'}]}
        self.saved[id]={'request_id':id,'conversation_id':conv,'turn_status':'COMPLETED','run_status':self.status,'response':result,'user_message':payload['message']};return result
    def stop(self,owner,id):self.stopped=getattr(self,'stopped',[])+[id];return 'NOT_RUNNING' if id in self.saved else 'STOPPING'
    def request(self,owner,id):return self.saved.get(id)
    def messages(self,owner,conv,after=-1,limit=20):
        turns=[dict(t,turn_index=i,status=t['turn_status'],created_at='2026-10-08T00:00:00+00:00',completed_at='2026-10-08T00:00:01+00:00') for i,t in enumerate(self.saved.values()) if t['conversation_id']==conv];turns=[t for t in turns if t['turn_index']>after]
        if not turns and not any(t['conversation_id']==conv for t in self.saved.values()):return None
        return {'conversation_id':conv,'messages':turns[:limit],'has_more':len(turns)>limit,'next_after':turns[limit-1]['turn_index'] if len(turns)>limit else None,'research_plan':None}
    def close(self):pass
